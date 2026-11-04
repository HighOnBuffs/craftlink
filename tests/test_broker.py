import concurrent.futures,json,os,pathlib,socket,subprocess,sys,tempfile,threading,time,unittest,uuid
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

if __name__=='__main__':unittest.main()
