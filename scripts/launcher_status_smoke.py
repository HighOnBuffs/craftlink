"""Actual launcher native-client example -> running broker -> owned VectorCraft.
The launcher singleton shell is never started. UI rendering is tested separately.
"""
import json,os,pathlib,subprocess,time
from native_apps import App,ROOT,call,command
from smoke import Broker,find,uid

def main():
    executable=os.environ.get('CRAFTLINK_LAUNCHER_STATUS_EXE')
    if not executable:raise RuntimeError('Explicit isolated native status example required')
    root=ROOT/'runtime'/('launcher-'+uid()[:8]);root.mkdir(parents=True)
    app=None;broker=None;credential=root/'test.credential';result=dict(checks={})
    try:
        app=App('vectorcraft',root);command(app.port,'file.new',{})
        node=command(app.port,'shape.rectangle',dict(x=10,y=10,width=80,height=40))['id']
        path=root/'status.vectorcraft';command(app.port,'file.save',dict(path=str(path)))
        broker=Broker(root);client=broker.client
        client.register_application(json.loads((ROOT/'manifests/vectorcraft.json').read_text()))
        obj=uid();change=dict(object=obj,document=uid(),application='vectorcraft',kind='rectangle',expected=0,value=dict(name='Launcher probe',opacity=1),native=None)
        client.request('commit_transaction',dict(operation=uid(),changes=[change]))
        native=find(call(app.port,'document.inspect'),node)
        binding=uid();client.request('bind_native',dict(id=binding,object=obj,profile='vectorcraft',port=app.port,path=str(path),node=node,baseline=dict(name=native['name'],opacity=native.get('opacity',1)),applied=0))
        with os.fdopen(os.open(credential,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as output:output.write(broker.token)
        def inspect():
            output=subprocess.run([executable,str(client.address[1]),str(credential)],capture_output=True,text=True,check=True,timeout=6)
            assert broker.token not in output.stdout+output.stderr
            return json.loads(output.stdout)
        rows=inspect();assert len(rows)==1 and rows[0]['profile']=='vectorcraft' and rows[0]['status']=='current' and rows[0]['applied']==1
        result['checks']['native_launcher_client_reads_real_app_binding']=True
        app.close();app=None
        change.update(expected=1,value=dict(name='Offline probe',opacity=.7));client.request('commit_transaction',dict(operation=uid(),changes=[change]))
        end=time.monotonic()+8
        while time.monotonic()<end:
            if inspect()[0]['status']=='missing':break
            time.sleep(.03)
        else:raise AssertionError('missing status not observed')
        result['checks']['native_launcher_client_observes_unavailable_source']=True
        credential.write_text('wrong-test-credential-for-rejection-only')
        refused=subprocess.run([executable,str(client.address[1]),str(credential)],capture_output=True,text=True,timeout=6)
        assert refused.returncode!=0 and broker.token not in refused.stdout+refused.stderr
        result['checks']['native_launcher_client_refuses_wrong_credential']=True;result['ok']=True
    finally:
        credential.unlink(missing_ok=True)
        if broker:broker.close()
        if app:app.close()
        (root/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2),flush=True)

if __name__=='__main__':main()
