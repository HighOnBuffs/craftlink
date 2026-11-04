"""Real candidate FigCraft + installed VectorCraft, unsaved edits and guarded writes.

Set CRAFTLINK_FIGCRAFT_EXE to the isolated native candidate built from the event
PR plus the existing upstream control-token PR. No installed binary is replaced.
"""
import hashlib,json,os,pathlib,sys,time,uuid
from native_apps import App,ROOT,TOKENS,call,command
from smoke import Broker,find,uid

def main():
    if not os.environ.get('CRAFTLINK_FIGCRAFT_EXE'):raise RuntimeError('Explicit isolated FigCraft candidate required')
    root=ROOT/'runtime'/('live-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uid()[:6]);root.mkdir(parents=True)
    apps=[];broker=None;result=dict(checks={},latency_ms={})
    try:
        for name in ['vectorcraft','figcraft']:
            app=App(name,root);apps.append(app);command(app.port,'file.new',{})
            app.node=command(app.port,'shape.rectangle',dict(x=10,y=10,width=120,height=80))['id']
            app.native=root/(name+'.'+name);app.binding=uid();command(app.port,'file.save',dict(path=str(app.native)))
        vector,fig=apps
        assert fig.token_file.is_file(),'candidate must require native authentication'
        broker=Broker(root);client=broker.client
        for name in ['vectorcraft','figcraft']:client.register_application(json.loads((ROOT/'manifests'/(name+'.json')).read_text()))
        obj,doc=uid(),uid();initial=dict(name='Live rectangle',opacity=1)
        change=dict(object=obj,document=doc,application='vectorcraft',kind='rectangle',expected=0,value=initial,native=None)
        client.request('commit_transaction',dict(operation=uid(),changes=[change]))
        for app in apps:
            node=find(call(app.port,'document.inspect'),app.node)
            binding=dict(id=app.binding,object=obj,profile=app.name,port=app.port,path=str(app.native),node=app.node,baseline=dict(name=node['name'],opacity=node.get('opacity',1)),applied=0)
            if app is fig:binding.update(live=True,token_file=str(fig.token_file))
            client.request('bind_native',binding)
        def wait(app,name):
            end=time.monotonic()+12
            while time.monotonic()<end:
                state=call(app.port,'document.inspect');node=find(state,app.node)
                if node['name']==name:return state
                time.sleep(.02)
            raise AssertionError(json.dumps(client.request('bindings')))
        wait(vector,'Live rectangle');wait(fig,'Live rectangle')
        original=hashlib.sha256(fig.native.read_bytes()).hexdigest()
        start=time.perf_counter();command(fig.port,'node.set',dict(ids=[fig.node],props=dict(name='Unsaved native',opacity=.4)))
        wait(vector,'Unsaved native')
        result['latency_ms']['unsaved_fig_to_vector']=round((time.perf_counter()-start)*1000,2)
        assert hashlib.sha256(fig.native.read_bytes()).hexdigest()==original
        assert call(fig.port,'document.inspect')['dirty']
        result['checks']['unsaved_source_propagates_without_native_save']=True
        head=client.request('resolve_link',dict(object=obj));assert head['native']['application']=='figcraft'
        # A repeated native event must not create a second operation/revision.
        client.request('native_changed',dict(binding=fig.binding))
        assert client.request('resolve_link',dict(object=obj))['revision']==head['revision']
        result['checks']['duplicate_notification_no_revision_churn']=True
        start=time.perf_counter();command(vector.port,'object.setProps',dict(ids=[vector.node],name='Reverse guarded',opacity=70));command(vector.port,'file.save',dict(path=str(vector.native)))
        wait(fig,'Reverse guarded');result['latency_ms']['vector_save_to_guarded_fig']=round((time.perf_counter()-start)*1000,2)
        assert hashlib.sha256(fig.native.read_bytes()).hexdigest()==original
        result['checks']['reverse_projection_keeps_receiver_unsaved']=True
        stale=call(fig.port,'document.inspect')
        command(fig.port,'node.set',dict(ids=[fig.node],props=dict(name='Concurrent native')))
        try:
            call(fig.port,'engine.execute',dict(command='node.set',params=dict(ids=[fig.node],props=dict(name='Must not overwrite')),expected=dict(document=stale['id'],revision=stale['revision'])))
            raise AssertionError('stale native write accepted')
        except RuntimeError as e:assert 'conflict:' in str(e)
        assert find(call(fig.port,'document.inspect'),fig.node)['name']=='Concurrent native'
        wait(vector,'Concurrent native');result['checks']['native_compare_and_set_rejects_stale_edit']=True
        credential=TOKENS.pop(fig.port)
        try:
            try:call(fig.port,'document.inspect');raise AssertionError('unauthenticated read accepted')
            except RuntimeError:pass
        finally:TOKENS[fig.port]=credential
        result['checks']['native_authentication_required']=True
        before=client.request('resolve_link',dict(object=obj))
        client.request('undo',dict(operation=uid(),object=obj,expected=before['revision']))
        wait(fig,'Reverse guarded');wait(vector,'Reverse guarded')
        client.request('redo',dict(operation=uid(),object=obj,expected=before['revision']+1))
        wait(fig,'Concurrent native');wait(vector,'Concurrent native');result['checks']['live_managed_undo_redo']=True
        command(fig.port,'file.save',dict(path=str(fig.native)));saved=fig.native;binding=fig.binding;node=fig.node;fig.close()
        fig=App('figcraft',root,saved);apps[-1]=fig;fig.native=saved;fig.node=node;fig.binding=binding
        client.request('reconnect',dict(binding=binding,port=fig.port,token_file=str(fig.token_file)))
        wait(fig,'Concurrent native');assert client.request('resolve_link',dict(object=obj))['object']==obj
        result['checks']['live_save_reopen_identity']=True
        broker.close();broker=None
        command(fig.port,'node.set',dict(ids=[fig.node],props=dict(name='Standalone native')));command(fig.port,'file.save',dict(path=str(fig.native)))
        result['checks']['candidate_standalone_workflow']=True
        result['ok']=True
    except BaseException as e:
        result['ok']=False;result['error']=repr(e)
        if broker:
            try:result['bindings']=broker.client.request('bindings')
            except Exception:pass
        raise
    finally:
        if broker:broker.close()
        for app in apps:app.close()
        (root/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2),flush=True)

if __name__=='__main__':main()
