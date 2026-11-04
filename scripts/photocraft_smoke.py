"""Real authenticated PhotoCraft read-only metadata + SDK registration acceptance.

No cross-app pixel transfer, write adapter or shared-store publication is claimed.
"""
import hashlib
import json
import pathlib
import subprocess
import sys

from native_apps import App, ROOT, call, command
from smoke import Broker, uid

sys.path.insert(0, str(ROOT / 'sdk'))
from craftlink import CraftLinkError
from photocraft_readonly import PhotoCraftInspector


def digest(path):
    files = sorted(path.rglob('*')) if path.is_dir() else [path]
    result = hashlib.sha256()
    for file in files:
        if file.is_file():
            result.update(str(file.relative_to(path) if path.is_dir() else file.name).encode())
            result.update(file.read_bytes())
    return result.hexdigest()


def main():
    root = ROOT / 'runtime' / ('photocraft-' + uid()[:8])
    root.mkdir(parents=True)
    app = broker = None
    credentials = []
    result = dict(checks={})
    try:
        app = App('photocraft', root)
        credentials.append(app.token_file)
        command(app.port, 'file.new', dict(width=64, height=48, name='CraftLink read-only fixture', background='transparent'))
        command(app.port, 'layer.new.group', dict(name='Native group'))
        command(app.port, 'layer.new.layer', dict(name='Native pixel layer'))
        saved = call(app.port, 'app.save', dict(path='readonly.pcraft'))
        assert saved.get('warnings') == []
        native = root / 'readonly.pcraft'
        before = digest(native)
        identity = root / 'document-id.json'
        identity.write_text(json.dumps(dict(document=uid())), encoding='utf-8')
        document = json.loads(identity.read_text(encoding='utf-8'))['document']
        adapter = PhotoCraftInspector(app.port, app.token_file, document)
        broker = Broker(root)
        example = subprocess.run([sys.executable, str(ROOT / 'examples/photocraft_layers.py'), broker.address,
                                  str(app.port), str(app.token_file), document], input=broker.token + '\n',
                                 text=True, capture_output=True, check=True, timeout=10)
        assert broker.token not in example.stdout + example.stderr
        objects = json.loads(example.stdout)
        assert len(objects) == 3 and len({o['object'] for o in objects}) == 3
        group = next(o for o in objects if o['name'] == 'Native group')
        child = next(o for o in objects if o['name'] == 'Native pixel layer')
        assert child['parent'] == group['object'] and child['native_kind'] == 'Pixel'
        assert broker.client.request('applications')[0]['write'] is False
        result['checks']['real_layer_hierarchy_and_sdk_registration'] = True

        for edit in [lambda: adapter.apply_changes(dict(name='refused')),
                     lambda: broker.client.request('negotiate_capabilities', dict(application='photocraft.inspector',
                                                   kind='photocraft.layer', properties=['name'], write=True)),
                     lambda: broker.client.request('commit_transaction', dict(operation=uid(), changes=[dict(
                         object=child['object'], document=document, application='photocraft.inspector',
                         kind='photocraft.layer', expected=0, value=dict(name='refused'), native=None)]))]:
            try:
                edit()
                raise AssertionError('read-only edit accepted')
            except CraftLinkError as rejected:
                assert rejected.code == 'capability'
        assert adapter.enumerate_objects() == objects and digest(native) == before
        assert broker.client.request('enumerate_objects') == []
        result['checks']['local_and_broker_writes_rejected_without_native_changes'] = True

        wrong = root / 'wrong.credential'
        wrong.write_text('0' * 64, encoding='ascii')
        credentials.append(wrong)
        try:
            PhotoCraftInspector(app.port, wrong, document).enumerate_objects()
            raise AssertionError('wrong native credential accepted')
        except CraftLinkError as rejected:
            assert rejected.code == 'authentication' and '0' * 64 not in str(rejected)
        result['checks']['native_authentication_required'] = True

        app.close()
        app = None
        try:
            adapter.enumerate_objects()
            raise AssertionError('closed app accepted')
        except CraftLinkError as unavailable:
            assert unavailable.code == 'missing'
        result['checks']['unavailable_native_source_is_explicit'] = True

        app = App('photocraft', root)
        credentials.append(app.token_file)
        opened = call(app.port, 'app.open', dict(path='readonly.pcraft'))
        assert opened.get('warnings') == []
        document = json.loads(identity.read_text(encoding='utf-8'))['document']
        reopened = PhotoCraftInspector(app.port, app.token_file, document).enumerate_objects()
        assert reopened == objects and digest(native) == before
        command(app.port, 'layer.new.layer', dict(name='Standalone after inspection'))
        assert len(PhotoCraftInspector(app.port, app.token_file, document).enumerate_objects()) == 4
        assert call(app.port, 'app.save', dict(path='standalone.pcraft')).get('warnings') == []
        result['checks']['save_reopen_identity_and_standalone_workflow'] = True
        result['ok'] = True
    finally:
        if broker:
            broker.close()
        if app:
            app.close()
        for credential in credentials:
            credential.unlink(missing_ok=True)
        (root / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
