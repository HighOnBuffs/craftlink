"""Real installed GUI process integration. Synthetic files only, new directory each run."""
import concurrent.futures, hashlib, json, pathlib, queue, secrets, sqlite3, subprocess, sys, threading, time, uuid
from native_apps import App, ROOT, call, command
sys.path.insert(0,str(ROOT/'sdk'))
from craftlink import Client, CraftLinkError

def uid():return str(uuid.uuid4())
def find(v,node):
    if isinstance(v,dict):
        if v.get('id')==node and ('kind' in v or 'type' in v):return v
        for value in v.values():
            found=find(value,node)
            if found:return found
    if isinstance(v,list):
        for value in v:
            found=find(value,node)
            if found:return found

class Broker:
    def __init__(self,root):
        self.token=secrets.token_hex(32)
        self.log=open(root/'broker.log','ab')
        self.process=subprocess.Popen([str(ROOT/'target/debug/craftlink-broker.exe'),str(root)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.process.stdin.write((self.token+'\n').encode());self.process.stdin.flush()
        ready=queue.Queue()
        threading.Thread(target=lambda:ready.put(self.process.stdout.readline()),daemon=True).start()
        try:line=ready.get(timeout=30)
        except queue.Empty:
            self.close()
            raise TimeoutError('broker startup')
        if not line:
            self.close()
            raise RuntimeError('broker exited: '+str(self.process.poll()))
        self.address=json.loads(line)['address'];self.client=Client(self.address,self.token)
    def close(self):
        if self.process.poll() is None:self.process.terminate();self.process.wait(10)
        self.process.stdin.close();self.process.stdout.close()
        self.log.close()

def main():
    directory=ROOT/'runtime'/('smoke-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uid()[:6]);directory.mkdir(parents=True)
    results={'directory':str(directory),'checks':{},'latency_ms':{},'pids':{}}
    apps=[];broker=None
    try:
        for name in ['vectorcraft','figcraft']:
            app=App(name,directory);apps.append(app);results['pids'][name]=app.process.pid
            command(app.port,'file.new',{})
            app.node=command(app.port,'shape.rectangle',dict(x=20,y=20,width=120,height=80))['id'] if name=='vectorcraft' else None
            app.native=directory/(name+'.'+name)
            command(app.port,'file.save',dict(path=str(app.native)))
            app.binding=uid()
        source,target=apps
        broker=Broker(directory);client=broker.client;results['pids']['broker']=broker.process.pid
        for name in ['vectorcraft','figcraft']:client.register_application(json.loads((ROOT/'manifests'/(name+'.json')).read_text()))
        obj,doc=uid(),uid();initial={'name':'CraftLink rectangle','opacity':1.0}
        change=dict(object=obj,document=doc,application='vectorcraft',kind='rectangle',expected=0,value=initial,native=None)
        client.request('commit_transaction',dict(operation=uid(),changes=[change]))
        for app in [source]:
            native=find(call(app.port,'document.inspect'),app.node)
            client.request('bind_native',dict(id=app.binding,object=obj,profile=app.name,port=app.port,path=str(app.native),node=app.node,baseline=dict(name=native['name'],opacity=native.get('opacity',1)),applied=0))
        placement=uid()
        place=dict(id=target.binding,source_binding=source.binding,profile='figcraft',port=target.port,path=str(target.native),document=uid(),placement=placement,link=uid(),operation=uid())
        placed=client.request('place_link',place);target.node=placed['node']
        assert client.request('place_link',place)==placed
        assert [obj,placement] in client.request('dependencies')
        assert find(call(target.port,'document.inspect'),target.node)['name']==initial['name']
        results['checks']['native_link_placement']=True
        def wait_name(app,name):
            end=time.monotonic()+12
            while time.monotonic()<end:
                node=find(call(app.port,'document.inspect'),app.node)
                if node.get('name')==name:return node
                time.sleep(.03)
            raise AssertionError('propagation timeout '+json.dumps(client.request('bindings')))
        def wait_status(binding,status):
            end=time.monotonic()+12
            while time.monotonic()<end:
                value=next(b for b in client.request('bindings') if b['id']==binding)
                if value['status']==status:return value
                time.sleep(.03)
            raise AssertionError('binding status timeout '+json.dumps(value))
        start=time.perf_counter()
        command(source.port,'object.setProps',dict(ids=[source.node],name='Source change',opacity=60))
        command(source.port,'file.save',dict(path=str(source.native)))
        n=wait_name(target,'Source change');assert abs(n.get('opacity',1)-.6)<.00001
        results['latency_ms']['source_save_to_target']=round((time.perf_counter()-start)*1000,2)
        results['checks']['source_save_auto_update']=True
        start=time.perf_counter()
        command(target.port,'node.set',dict(ids=[target.node],props=dict(name='Receiver change',opacity=.35)))
        # Deterministically exercise a late projection event while a new native
        # edit is unsaved. A true no-op broker commit must not mislabel conflict.
        current=client.request('resolve_link',dict(object=obj))
        noop=change.copy();noop.update(expected=current['revision'],value=current['value'],native=current['native'])
        client.request('commit_transaction',dict(operation=uid(),changes=[noop]))
        assert next(b for b in client.request('bindings') if b['id']==target.binding)['status']!='conflicted'
        command(target.port,'file.save',dict(path=str(target.native)))
        n=wait_name(source,'Receiver change');assert abs(n.get('opacity',1)-.35)<.00001
        results['latency_ms']['receiver_save_to_source']=round((time.perf_counter()-start)*1000,2)
        results['checks']['reverse_native_edit']=True
        head=client.request('resolve_link',dict(object=obj));rev=head['revision']
        op=uid();undo=client.request('undo',dict(operation=op,object=obj,expected=rev));wait_name(target,'Source change');wait_name(source,'Source change')
        assert client.request('undo',dict(operation=op,object=obj,expected=rev))==undo
        client.request('redo',dict(operation=uid(),object=obj,expected=rev+1));wait_name(target,'Receiver change');wait_name(source,'Receiver change')
        results['checks']['native_undo_redo']=True
        before=client.request('resolve_link',dict(object=obj));saved=[(a.name,a.native,a.node,a.binding) for a in apps]
        for app in apps:app.close()
        apps=[];broker.close();broker=Broker(directory);client=broker.client
        for name,path,node,binding in saved:
            app=App(name,directory,path);apps.append(app);app.native=path;app.node=node;app.binding=binding
            client.request('reconnect',dict(binding=binding,port=app.port))
            assert find(call(app.port,'document.inspect'),node)['name']=='Receiver change'
        source,target=apps
        assert client.request('resolve_link',dict(object=obj))==before
        assert all(b['applied']==before['revision'] for b in client.request('bindings'))
        results['checks']['save_close_reopen_identity_revision']=True
        replay=client.subscribe_to_changes(0,0);assert replay and replay[-1]['sequence']>=before['revision']
        results['checks']['restart_event_replay']=True
        # A broker-managed edit races with an independently edited receiving native app.
        command(target.port,'node.set',dict(ids=[target.node],props=dict(name='Concurrent local',opacity=.2)))
        stale=before.copy();change.update(expected=before['revision'],value=dict(name='Committed concurrent',opacity=.8))
        client.request('commit_transaction',dict(operation=uid(),changes=[change]))
        binding=wait_status(target.binding,'conflicted')
        assert binding['status']=='conflicted',binding
        assert find(call(target.port,'document.inspect'),target.node)['name']=='Concurrent local'
        conflicts=client.request('conflicts');assert conflicts and conflicts[-1]['request']['live_native']
        # Verify the saved unsaved-work snapshot has actual bytes and a valid content hash.
        h=conflicts[-1]['request']['live_native'];assert hashlib.sha256((directory/'.craftlink/blobs'/h).read_bytes()).hexdigest()==h
        results['checks']['native_conflict_preserves_unsaved_snapshot']=True
        try:client.request('commit_transaction',dict(operation=uid(),changes=[change]));raise AssertionError('stale commit accepted')
        except CraftLinkError as e:assert e.code=='conflict'
        results['checks']['optimistic_conflict']=True
        client.request('resolve_conflict',dict(binding=target.binding,choice='committed'));wait_name(target,'Committed concurrent')
        # Auth and native filesystem boundary.
        try:Client(broker.address,'wrong').request('applications');raise AssertionError('bad auth accepted')
        except CraftLinkError as e:assert e.code=='authentication'
        results['checks']['authentication_rejects_wrong_token']=True
        target.close()
        current=client.request('resolve_link',dict(object=obj));change.update(expected=current['revision'],value=dict(name='Offline update',opacity=.7))
        client.request('commit_transaction',dict(operation=uid(),changes=[change]))
        assert wait_status(target.binding,'missing')['status']=='missing'
        target=App('figcraft',directory,target.native);apps[-1]=target;target.native=saved[1][1];target.node=saved[1][2];target.binding=saved[1][3]
        client.request('reconnect',dict(binding=target.binding,port=target.port));wait_name(target,'Offline update')
        results['checks']['offline_reconnect']=True
        # Hold an actual app process so a broker commit cannot finish its native
        # projection. Kill the broker after observing the durable SQLite head.
        import psutil
        current=client.request('resolve_link',dict(object=obj))
        change.update(expected=current['revision'],value=dict(name='Crash recovered',opacity=.45))
        crash_tx=dict(operation=uid(),changes=[change.copy()])
        paused=psutil.Process(target.process.pid)
        paused.suspend()
        try:
            with concurrent.futures.ThreadPoolExecutor(1) as pool:
                start_commit=time.monotonic()
                future=pool.submit(client.request,'commit_transaction',crash_tx)
                receipt=future.result(timeout=2.5)
                assert receipt['revisions'][obj]==current['revision']+1
                results['latency_ms']['commit_while_receiver_suspended']=round((time.monotonic()-start_commit)*1000,2)
                assert client.request('resolve_link',dict(object=obj))['revision']==current['revision']+1
                end=time.monotonic()+6
                while True:
                    with sqlite3.connect(directory/'.craftlink/craftlink.sqlite') as db:
                        persisted=json.loads(db.execute('SELECT data FROM objects WHERE id=?',(obj,)).fetchone()[0])
                    if persisted['revision']==current['revision']+1:break
                    if time.monotonic()>end:raise AssertionError('durable head not observed before crash')
                    time.sleep(.01)
                broker.close();broker=None
                try:future.result(timeout=5)
                except (OSError,ValueError,CraftLinkError):pass
        finally:paused.resume()
        broker=Broker(directory);client=broker.client
        recovered=client.request('commit_transaction',crash_tx)
        assert recovered['revisions'][obj]==current['revision']+1
        wait_name(source,'Crash recovered');wait_name(target,'Crash recovered')
        results['checks']['broker_crash_after_commit_before_projection']=True
        # Missing-file status and relocation keep the same global link identity.
        target.close();relocated=directory/'relocated.figcraft';target.native.rename(relocated)
        current=client.request('resolve_link',dict(object=obj))
        change.update(expected=current['revision'],value=dict(name='Relocated update',opacity=.5))
        client.request('commit_transaction',dict(operation=uid(),changes=[change]))
        assert wait_status(target.binding,'missing')['status']=='missing'
        old_target=target;target=App('figcraft',directory,relocated);apps[-1]=target
        target.native=relocated;target.node=old_target.node;target.binding=old_target.binding
        client.request('reconnect',dict(binding=target.binding,port=target.port,path=str(relocated)))
        wait_name(target,'Relocated update')
        results['checks']['missing_file_relocation']=True
        # Third application contract registration is performed by a separate reference process.
        ref=subprocess.run([sys.executable,str(ROOT/'examples/generated_app.py'),broker.address],input=broker.token+'\n',text=True,capture_output=True,timeout=15,check=True)
        results['checks']['third_application_registration']=json.loads(ref.stdout)['registered']
        # Broker-free native editing/saving still works.
        broker.close();broker=None
        command(source.port,'object.setProps',dict(ids=[source.node],name='Standalone'))
        command(source.port,'file.save',dict(path=str(source.native)))
        results['checks']['standalone_workflow']=find(call(source.port,'document.inspect'),source.node)['name']=='Standalone'
        results['ok']=True
    except Exception as exc:
        results['ok']=False;results['error']=repr(exc)
        if broker:
            try:results['bindings_at_failure']=broker.client.request('bindings')
            except Exception:pass
        raise
    finally:
        if broker:broker.close()
        for app in apps:app.close()
        (directory/'result.json').write_text(json.dumps(results,indent=2))
        print(json.dumps(results,indent=2),flush=True)

if __name__=='__main__':main()
