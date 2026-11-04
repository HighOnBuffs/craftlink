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
                state = call(app.port, 'document.inspect')
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

        broker.close(); broker = None
        command(vector.port, 'object.setProps', dict(ids=[vector.node], name='Standalone'))
        save(vector)
        old = call(vector.port, 'document.inspect')
        command(vector.port, 'file.new', {})
        try:
            call(vector.port, 'engine.execute', dict(command='object.setProps', params=dict(ids=[vector.node], name='Wrong tab'),
                 expected=dict(document=old['uid'], revision=old['revision'])))
            raise AssertionError('Inactive native document was overwritten')
        except RuntimeError as rejected:
            assert 'conflict:' in str(rejected)
        result['checks']['standalone_save_and_inactive_document_protection'] = True
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
