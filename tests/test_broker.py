import base64,concurrent.futures,json,os,pathlib,socket,socketserver,sqlite3,subprocess,sys,tempfile,threading,time,unittest,uuid
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(ROOT/'sdk'))
from smoke import Broker
from craftlink import Client,CraftLinkError

def uid():return str(uuid.uuid4())

class BrokerTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'runtime').mkdir(exist_ok=True)
        # Inherit workspace ACLs: Python 3.13 private tempfile ACLs exclude this
        # workstation's sandbox execution identity. Retain these tiny fixtures.
        self.directory=ROOT/'runtime'/('broker-test-'+uid())
        self.directory.mkdir()
        self.broker=Broker(self.directory);self.client=self.broker.client
        manifest=json.loads((ROOT/'manifests/vectorcraft.json').read_text())
        self.client.register_application(manifest)
    def tearDown(self):
        self.broker.close()
    def test_blocking_subscription_replay_and_idempotency(self):
        change=dict(object=uid(),document=uid(),application='vectorcraft',kind='rectangle',expected=0,value=dict(name='first',opacity=1),native=None)
        tx=dict(operation=uid(),changes=[change])
        with concurrent.futures.ThreadPoolExecutor(1) as pool:
            waiting=pool.submit(self.client.subscribe_to_changes,0,2000)
            time.sleep(.1);self.assertFalse(waiting.done())
            receipt=self.client.request('commit_transaction',tx)
            events=waiting.result(4)
        self.assertEqual(len(events),1);self.assertEqual(events[0]['sequence'],receipt['sequence'])
        self.assertEqual(self.client.request('commit_transaction',tx),receipt)
        self.assertEqual(self.client.subscribe_to_changes(receipt['sequence'],0),[])
    def test_permissions_schema_and_filesystem(self):
        with self.assertRaises(CraftLinkError) as rejected:Client(self.broker.address,'bad').request('applications')
        self.assertEqual(rejected.exception.code,'authentication')
        m=json.loads((ROOT/'manifests/figcraft.json').read_text());m['schema']=2
        with self.assertRaises(CraftLinkError):self.client.register_application(m)
        with self.assertRaises(CraftLinkError) as cap:
            self.client.request('negotiate_capabilities',dict(application='vectorcraft',kind='rectangle',properties=['mask'],write=True))
        self.assertEqual(cap.exception.code,'capability')
        outside=ROOT/'runtime'/(uid()+'.vectorcraft');outside.write_text('synthetic boundary test')
        try:
            with self.assertRaises(CraftLinkError) as boundary:
                self.client.request('bind_native',dict(id=uid(),object=uid(),profile='vectorcraft',port=1,path=str(outside),node=2,baseline={},applied=0))
            self.assertEqual(boundary.exception.code,'capability')
        finally:outside.unlink()
    def test_mcp_real_stdio_and_generated_app(self):
        env=os.environ.copy();env.update(CRAFTLINK_ADDRESS=self.broker.address,CRAFTLINK_TOKEN=self.broker.token)
        messages=[dict(jsonrpc='2.0',id=1,method='initialize',params={}),dict(jsonrpc='2.0',id=2,method='tools/list'),dict(jsonrpc='2.0',id=3,method='tools/call',params=dict(name='craftlink',arguments=dict(method='applications')))]
        mcp=subprocess.run([sys.executable,str(ROOT/'sdk/mcp_server.py')],env=env,input=''.join(json.dumps(x)+'\n' for x in messages),text=True,capture_output=True,check=True,timeout=10)
        replies=[json.loads(x) for x in mcp.stdout.splitlines()]
        self.assertEqual(len(replies),3);self.assertEqual(replies[1]['result']['tools'][0]['name'],'craftlink');self.assertFalse(replies[2]['result']['isError'])
        ref=subprocess.run([sys.executable,str(ROOT/'examples/generated_app.py'),self.broker.address],input=self.broker.token+'\n',text=True,capture_output=True,check=True,timeout=10)
        self.assertTrue(json.loads(ref.stdout)['registered'])
        self.assertEqual(len(self.client.request('applications')),2)
    def test_native_wait_does_not_hold_metadata_lock(self):
        obj=uid()
        self.client.request('commit_transaction',dict(operation=uid(),changes=[dict(object=obj,document=uid(),application='vectorcraft',kind='rectangle',expected=0,value=dict(name='A',opacity=1),native=None)]))
        native=self.directory/'blocked.vectorcraft';native.write_text('synthetic native boundary fixture')
        entered=threading.Event();release=threading.Event()
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0));listener.listen(2)
            def stall():
                conn,_=listener.accept()
                with conn:
                    conn.recv(4096);entered.set();release.wait(5)
            thread=threading.Thread(target=stall);thread.start()
            with concurrent.futures.ThreadPoolExecutor(1) as pool:
                pending=pool.submit(self.client.request,'bind_native',dict(id=uid(),object=obj,profile='vectorcraft',port=listener.getsockname()[1],path=str(native),node=2,baseline=dict(name='A',opacity=1),applied=0))
                try:
                    self.assertTrue(entered.wait(3));start=time.monotonic()
                    self.assertEqual(self.client.request('resolve_link',dict(object=obj))['revision'],1)
                    self.assertLess(time.monotonic()-start,1)
                finally:release.set();thread.join()
                with self.assertRaises(CraftLinkError):pending.result(5)

    def test_live_snapshot_rejects_aba_revision_even_with_equal_properties(self):
        native=self.directory/'aba.vectorcraft';native.write_text('synthetic native snapshot fixture')
        credential=self.directory/'aba.credential';credential.write_text('unit-test-native-credential-not-a-real-secret')
        state=dict(name='base',revision=1);stop=threading.Event();observed=[]
        class Handler(socketserver.StreamRequestHandler):
            def handle(inner):
                inner.connection.settimeout(2)
                auth=json.loads(inner.rfile.readline(4097))
                if auth.get('method')!='auth':return
                inner.wfile.write(b'{"ok":true}\n');inner.wfile.flush()
                try:request=json.loads(inner.rfile.readline(8193));method=request['method']
                except (OSError,ValueError):return
                if method=='document.inspect':
                    answer=dict(id=1,revision=state['revision'],path=str(native),capabilities=dict(conditionalExecute=1,documentChangeEvents=1),nodes=[dict(id=2,kind='Rectangle',name=state['name'],opacity=1)])
                elif method=='engine.execute' and request['params']['command']=='file.saveCopy':
                    observed.append(request['params'].get('expected'))
                    # Native A -> B -> A while exporting B. Properties alone miss it.
                    state['revision']+=2
                    answer=dict(dataBase64=base64.b64encode(b'snapshot-of-intermediate-B').decode())
                elif method=='events.poll':
                    stop.wait(.05);answer=dict(events=[],cursor=0,reset=False,dropped=0)
                elif method=='engine.execute' and request['params']['command']=='object.setProps':
                    state.update(name=request['params']['params']['name'],revision=state['revision']+1);answer={}
                else:return
                try:inner.wfile.write((json.dumps(dict(ok=True,result=answer))+'\n').encode())
                except OSError:pass
        class Server(socketserver.ThreadingTCPServer):
            daemon_threads=True
        with Server(('127.0.0.1',0),Handler) as server:
            worker=threading.Thread(target=server.serve_forever,kwargs=dict(poll_interval=.05));worker.start()
            try:
                obj=uid()
                self.client.request('commit_transaction',dict(operation=uid(),changes=[dict(object=obj,document=uid(),application='vectorcraft',kind='rectangle',expected=0,value=dict(name='base',opacity=1),native=None)]))
                binding=uid()
                registered=self.client.request('bind_native',dict(id=binding,object=obj,profile='vectorcraft',port=server.server_address[1],path=str(native),node=2,baseline=dict(name='base',opacity=1),applied=1,live=True,token_file=str(credential)))
                state.update(name='new-A',revision=2)
                with self.assertRaises(CraftLinkError) as rejected:self.client.request('native_changed',dict(binding=binding))
                self.assertEqual(rejected.exception.code,'conflict')
                head=self.client.request('resolve_link',dict(object=obj))
                self.assertEqual(head['revision'],1);self.assertEqual(head['value']['name'],'base')
                self.assertIn(dict(document=1,revision=2),observed)
                # Deterministic post-crash fixture: old projection side effect
                # completed, its receipt did not, and a newer head committed.
                # No native binding may act while these canonical edits are made.
                self.broker.close()
                with sqlite3.connect(self.directory/'.craftlink/craftlink.sqlite') as db:db.execute('DELETE FROM bindings')
                self.broker=Broker(self.directory);self.client=self.broker.client
                for revision,name in [(1,'old-projection'),(2,'latest-canonical')]:
                    self.client.request('commit_transaction',dict(operation=uid(),changes=[dict(object=obj,document=head['document'],application='vectorcraft',kind='rectangle',expected=revision,value=dict(name=name,opacity=1),native=None)]))
                self.broker.close();state.update(name='old-projection',revision=20)
                record=registered.copy();record.update(pending=dict(name='old-projection',opacity=1),status='applying')
                with sqlite3.connect(self.directory/'.craftlink/craftlink.sqlite') as db:db.execute('INSERT INTO bindings VALUES (?,?)',(binding,json.dumps(record)))
                self.broker=Broker(self.directory);self.client=self.broker.client
                end=time.monotonic()+4
                while time.monotonic()<end:
                    receipt=self.client.request('bindings')[0]
                    if receipt['status']=='current' and receipt['applied']==3:break
                    time.sleep(.02)
                else:self.fail('interrupted pending projection did not recover')
                self.assertEqual(state['name'],'latest-canonical')
                self.assertEqual(self.client.request('resolve_link',dict(object=obj))['revision'],3)
            finally:
                stop.set();server.shutdown();worker.join()

if __name__=='__main__':unittest.main()
