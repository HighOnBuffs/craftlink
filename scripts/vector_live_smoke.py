"""Two real authenticated candidates; unsaved name/opacity in both directions.

Requires CRAFTLINK_VECTORCRAFT_EXE and CRAFTLINK_FIGCRAFT_EXE. Installed binaries
and user documents are never replaced. Results are individual smoke samples.
"""
import hashlib
import json
import os
import time

from native_apps import App, ROOT, TOKENS, call, command
from smoke import Broker, find, uid


def save(app):
    # VectorCraft's native background save acknowledgement precedes disk IO.
    # Reuse its existing foreground automation option before closing a process.
    if app.name == 'vectorcraft':
        return call(app.port, 'app.save', dict(path=str(app.native), wait=True))
    return command(app.port, 'file.save', dict(path=str(app.native)))


def main():
    for product in ['VECTORCRAFT', 'FIGCRAFT']:
        if not os.environ.get('CRAFTLINK_' + product + '_EXE'):
            raise RuntimeError('Explicit isolated ' + product + ' candidate required')
    root = ROOT / 'runtime' / ('vector-live-' + uid()[:8])
    root.mkdir(parents=True)
    apps, broker = [], None
    result = dict(checks={}, latency_ms={})
    try:
        for name in ['vectorcraft', 'figcraft']:
            app = App(name, root)
            apps.append(app)
            assert app.token_file.is_file(), 'Candidate must generate a native credential'
            command(app.port, 'file.new', {})
            app.node = command(app.port, 'shape.rectangle', dict(x=10, y=10, width=120, height=80))['id']
            app.native, app.binding = root / (name + '.' + name), uid()
            save(app)
            state = call(app.port, 'document.inspect')
            app.document_uid = state.get('uid', state.get('id'))
        vector, fig = apps
        broker = Broker(root)
        client = broker.client
        for name in ['vectorcraft', 'figcraft']:
            client.register_application(json.loads((ROOT / 'manifests' / (name + '.json')).read_text(encoding='utf-8')))
        obj, document = uid(), uid()
        client.request('commit_transaction', dict(operation=uid(), changes=[dict(
            object=obj, document=document, application='vectorcraft', kind='rectangle', expected=0,
            value=dict(name='Both live', opacity=1), native=None)]))
        for app in apps:
            node = find(call(app.port, 'document.inspect'), app.node)
            client.request('bind_native', dict(id=app.binding, object=obj, profile=app.name, port=app.port,
                path=str(app.native), node=app.node, baseline=dict(name=node['name'], opacity=node.get('opacity', 1)),
                applied=0, live=True, token_file=str(app.token_file)))

        def wait(app, name, opacity=None):
            end = time.monotonic() + 12
            while time.monotonic() < end:
                state = call(app.port, 'document.inspect', dict(document=app.document_uid))
                node = find(state, app.node)
                if node['name'] == name and (opacity is None or abs(node.get('opacity', 1) - opacity) < .00001):
                    return state
                time.sleep(.02)
            raise AssertionError(json.dumps(client.request('bindings')))

        wait(vector, 'Both live'); wait(fig, 'Both live')
        for app in apps:
            save(app)
        hashes = {app.name: hashlib.sha256(app.native.read_bytes()).hexdigest() for app in apps}
        start = time.perf_counter()
        command(vector.port, 'object.setProps', dict(ids=[vector.node], name='Unsaved Vector', opacity=40))
        wait(fig, 'Unsaved Vector', .4)
        result['latency_ms']['unsaved_vector_to_fig'] = round((time.perf_counter() - start) * 1000, 2)
        result['checks']['unsaved_vector_to_fig'] = True
        start = time.perf_counter()
        command(fig.port, 'node.set', dict(ids=[fig.node], props=dict(name='Unsaved Fig', opacity=.7)))
        wait(vector, 'Unsaved Fig', .7)
        result['latency_ms']['unsaved_fig_to_vector'] = round((time.perf_counter() - start) * 1000, 2)
        for app in apps:
            assert hashlib.sha256(app.native.read_bytes()).hexdigest() == hashes[app.name]
            assert call(app.port, 'document.inspect')['dirty']
        result['checks']['bidirectional_projections_leave_both_native_files_unsaved'] = True

        before = client.request('resolve_link', dict(object=obj))['revision']
        for app in apps:
            client.request('native_changed', dict(binding=app.binding))
        assert client.request('resolve_link', dict(object=obj))['revision'] == before
        result['checks']['duplicate_notification_no_revision_churn'] = True

        command(vector.port, 'edit.undo', {})
        wait(fig, 'Unsaved Vector', .4)
        command(vector.port, 'edit.redo', {})
        wait(fig, 'Unsaved Fig', .7)
        result['checks']['native_vector_undo_redo_propagates'] = True

        stale = call(vector.port, 'document.inspect')
        command(vector.port, 'object.setProps', dict(ids=[vector.node], name='Race winner', opacity=60))
        current = call(vector.port, 'document.inspect')
        try:
            call(vector.port, 'engine.execute', dict(command='object.setProps', params=dict(ids=[vector.node], name='Lost edit'),
                 expected=dict(document=stale['uid'], revision=stale['revision'])))
            raise AssertionError('Stale native revision was accepted')
        except RuntimeError as rejected:
            assert 'conflict:' in str(rejected)
        assert find(call(vector.port, 'document.inspect'), vector.node)['name'] == 'Race winner'
        assert call(vector.port, 'document.inspect')['revision'] == current['revision']
        wait(fig, 'Race winner', .6)
        result['checks']['stale_vector_guard_cannot_overwrite_concurrent_native_edit'] = True

        for app in apps:
            credential = TOKENS.pop(app.port)
            try:
                edit = (dict(command='object.setProps', params=dict(ids=[app.node], name='Denied')) if app is vector
                        else dict(command='node.set', params=dict(ids=[app.node], props=dict(name='Denied'))))
                for method, params in [('document.inspect', {}), ('engine.execute', edit)]:
                    try:
                        call(app.port, method, params)
                        raise AssertionError('Unauthenticated native request was accepted')
                    except RuntimeError:
                        pass
                wrong = root / (app.name + '.wrong-credential')
                wrong.write_text('0' * 64, encoding='ascii')
                TOKENS[app.port] = wrong
                try:
                    call(app.port, 'document.inspect')
                    raise AssertionError('Wrong native credential was accepted')
                except RuntimeError:
                    pass
                finally:
                    wrong.unlink()
            finally:
                TOKENS[app.port] = credential
            assert find(call(app.port, 'document.inspect'), app.node)['name'] == 'Race winner'
        result['checks']['both_native_endpoints_require_authentication'] = True

        head = client.request('resolve_link', dict(object=obj))
        client.request('undo', dict(operation=uid(), object=obj, expected=head['revision']))
        wait(vector, 'Unsaved Fig', .7); wait(fig, 'Unsaved Fig', .7)
        client.request('redo', dict(operation=uid(), object=obj, expected=head['revision'] + 1))
        wait(vector, 'Race winner', .6); wait(fig, 'Race winner', .6)
        result['checks']['managed_undo_redo_converges_both_native_apps'] = True

        broker.close(); broker = None
        command(vector.port, 'object.setProps', dict(ids=[vector.node], name='Broker offline', opacity=55))
        broker = Broker(root); client = broker.client
        wait(fig, 'Broker offline', .55)
        assert client.request('resolve_link', dict(object=obj))['object'] == obj
        result['checks']['broker_restart_recovers_unsaved_source_and_subscriptions'] = True

        for index, app in enumerate(list(apps)):
            save(app)
            node, binding, path, name, port = app.node, app.binding, app.native, app.name, app.port
            app.close()
            replacement = App(name, root, path, port=port)
            replacement.node, replacement.binding, replacement.native = node, binding, path
            state = call(replacement.port, 'document.inspect')
            replacement.document_uid = state.get('uid', state.get('id'))
            apps[index] = replacement
            client.request('reconnect', dict(binding=binding, port=replacement.port, token_file=str(replacement.token_file)))
            wait(replacement, 'Broker offline', .55)
        vector, fig = apps
        command(vector.port, 'object.setProps', dict(ids=[vector.node], name='After reconnect', opacity=35))
        wait(fig, 'After reconnect', .35)
        command(fig.port, 'node.set', dict(ids=[fig.node], props=dict(name='Reverse after reconnect', opacity=.25)))
        wait(vector, 'Reverse after reconnect', .25)
        assert client.request('resolve_link', dict(object=obj))['document'] == document
        result['checks']['both_native_reopens_preserve_link_identity_and_live_updates'] = True

        # Both links stay bound while users work in other native tabs.
        foreground = {}
        for app in apps:
            command(app.port, 'file.new', {})
            other = command(app.port, 'shape.rectangle', dict(x=200, y=200, width=30, height=40))['id']
            if app is vector:
                call(app.port, 'ui.pointer', dict(events=[
                    dict(kind='down', x=215, y=220, space='doc'),
                    dict(kind='drag', x=220, y=225, space='doc')]))
            state = call(app.port, 'document.inspect')
            foreground[app.name] = (state.get('uid', state.get('id')), other, find(state, other), state['revision'])
        start = time.perf_counter()
        call(fig.port, 'engine.execute', dict(document=fig.document_uid, command='node.set',
            params=dict(ids=[fig.node], props=dict(name='Background Fig', opacity=.45))))
        wait(vector, 'Background Fig', .45)
        result['latency_ms']['background_fig_to_vector'] = round((time.perf_counter() - start) * 1000, 2)
        state = call(vector.port, 'document.inspect', dict(document=vector.document_uid))
        start = time.perf_counter()
        call(vector.port, 'engine.execute', dict(document=vector.document_uid, command='object.setProps',
            params=dict(ids=[vector.node], name='Background Vector', opacity=65),
            expected=dict(document=vector.document_uid, revision=state['revision'])))
        wait(fig, 'Background Vector', .65)
        result['latency_ms']['background_vector_to_fig'] = round((time.perf_counter() - start) * 1000, 2)
        for app in apps:
            state = call(app.port, 'document.inspect')
            document_id, node_id, original, revision = foreground[app.name]
            assert state.get('uid', state.get('id')) == document_id
            assert find(state, node_id) == original, 'Foreground object changed'
            assert state['revision'] == revision, 'Foreground document was mutated'
        result['checks']['bidirectional_background_documents_preserve_foreground_tabs'] = True
        cursor = call(vector.port, 'events.poll', dict(after=0, timeoutMs=0))['cursor']
        call(vector.port, 'ui.pointer', dict(events=[dict(kind='up', x=220, y=225, space='doc')]))
        assert call(vector.port, 'events.poll', dict(after=cursor, timeoutMs=0))['cursor'] == cursor + 1
        result['checks']['background_projection_preserves_unrelated_native_drag'] = True

        broker.close(); broker = None
        command(vector.port, 'document.activate', dict(index=0))
        command(vector.port, 'object.setProps', dict(ids=[vector.node], name='Standalone'))
        save(vector)
        old = call(vector.port, 'document.inspect')
        command(vector.port, 'document.activate', dict(index=1))
        try:
            call(vector.port, 'engine.execute', dict(document=foreground['vectorcraft'][0], command='object.setProps',
                 params=dict(ids=[vector.node], name='Wrong tab'),
                 expected=dict(document=old['uid'], revision=old['revision'])))
            raise AssertionError('Mismatched document guard was accepted')
        except RuntimeError as rejected:
            assert 'conflict:' in str(rejected)
        assert call(vector.port, 'document.inspect')['uid'] == foreground['vectorcraft'][0]
        assert find(call(vector.port, 'document.inspect', dict(document=old['uid'])), vector.node)['name'] == 'Standalone'
        result['checks']['standalone_save_and_mismatched_document_protection'] = True

        # Exercise native mouse-tool dispatch, not a substitute transform command.
        other = foreground['vectorcraft'][1]
        command(vector.port, 'tool.select', dict(tool='selection'))
        command(vector.port, 'select.set', dict(ids=[other]))
        before = call(vector.port, 'document.inspect')
        cursor = call(vector.port, 'events.poll', dict(after=0, timeoutMs=0))['cursor']
        start = time.perf_counter()
        bounds = find(before, other)['bounds']
        x, y = bounds['x'] + bounds['width']/2, bounds['y'] + bounds['height']/2
        events = [dict(kind='down', x=x, y=y, space='doc')]
        events += [dict(kind='drag', x=x+i, y=y+i, space='doc') for i in range(1, 26)]
        events += [dict(kind='up', x=x+25, y=y+25, space='doc')]
        call(vector.port, 'ui.pointer', dict(events=events))
        after = call(vector.port, 'document.inspect')
        feed = call(vector.port, 'events.poll', dict(after=cursor, timeoutMs=0))
        assert feed['cursor'] == cursor + 1, 'Native gesture must publish exactly one committed invalidation'
        assert find(after, other)['bounds'] != find(before, other)['bounds'], 'Native drag did not move the object'
        assert len(after['history']) == len(before['history']) + 1
        result['latency_ms']['native_drag_25_samples_commit_and_observe'] = round((time.perf_counter() - start) * 1000, 2)
        command(vector.port, 'edit.undo', {})
        assert find(call(vector.port, 'document.inspect'), other)['bounds'] == find(before, other)['bounds']
        command(vector.port, 'edit.redo', {})
        assert find(call(vector.port, 'document.inspect'), other)['bounds'] == find(after, other)['bounds']
        result['checks']['native_pointer_drag_coalesces_and_undo_redo_preserves_geometry'] = True
        result['ok'] = True
    finally:
        if broker:
            broker.close()
        for app in apps:
            app.close()
        (root / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
