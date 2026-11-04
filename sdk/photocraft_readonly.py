"""Read-only native layer metadata; no pixel conversion or shared-store publication."""
import json
import pathlib
import socket
import time
import uuid

from craftlink import CraftLinkError


def failure(code, message):
    return CraftLinkError(dict(code=code, error=message))


def layer_objects(document, inspection):
    """Map native IDs under a caller-persisted document UUID, retaining hierarchy."""
    document = uuid.UUID(str(document))
    if not isinstance(inspection, dict) or not isinstance(inspection.get('layers'), list):
        raise failure('invalid', 'PhotoCraft did not return a layer tree')
    if len(inspection['layers']) > 10000:
        raise failure('capability', 'Layer tree exceeds the inspection contract')
    pending = [(layer, None, 0) for layer in reversed(inspection['layers'])]
    objects, seen = [], set()
    while pending:
        layer, parent, depth = pending.pop()
        if len(objects) >= 10000 or depth > 64 or not isinstance(layer, dict):
            raise failure('capability', 'Layer tree exceeds the inspection contract')
        native = layer.get('id')
        name, kind = layer.get('name'), layer.get('kind')
        children = layer.get('children', [])
        if (type(native) is not int or native < 1 or native in seen
                or not isinstance(name, str) or len(name) > 16384
                or not isinstance(kind, str) or len(kind) > 128
                or not isinstance(children, list) or len(children) > 10000):
            raise failure('invalid', 'Invalid or duplicate native layer metadata')
        seen.add(native)
        identity = str(uuid.uuid5(document, 'photocraft.layer:' + str(native)))
        objects.append(dict(object=identity, document=str(document), kind='photocraft.layer',
                            native_id=native, name=name, native_kind=kind, parent=parent))
        pending.extend((child, identity, depth + 1) for child in reversed(children))
        if len(pending) > 10000:
            raise failure('capability', 'Layer tree exceeds the inspection contract')
    return objects


class PhotoCraftInspector:
    """Connect only to an explicitly supplied, authenticated loopback native session.

    The selected document must remain active. The supplied document UUID is owned
    and persisted by the caller; it cannot be recovered from a path or layer name.
    """
    def __init__(self, port, credential_file, document):
        if type(port) is not int or not 0 < port < 65536:
            raise ValueError('A native loopback port is required')
        self.port = port
        self.credential_file = pathlib.Path(credential_file)
        self.document = uuid.UUID(str(document))

    @staticmethod
    def manifest():
        path = pathlib.Path(__file__).resolve().parents[1] / 'manifests/photocraft-readonly.json'
        return json.loads(path.read_text(encoding='utf-8'))

    def register_application(self, client):
        return client.register_application(self.manifest())

    @staticmethod
    def _reply(sock, deadline, limit):
        data = bytearray()
        while b'\n' not in data:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise failure('missing', 'PhotoCraft inspection timed out')
            sock.settimeout(remaining)
            chunk = sock.recv(min(4096, limit + 1 - len(data)))
            if not chunk:
                raise failure('missing', 'PhotoCraft closed the connection')
            data.extend(chunk)
            if len(data) > limit:
                raise failure('capability', 'PhotoCraft reply exceeds the inspection limit')
        return json.loads(data)

    def enumerate_objects(self):
        try:
            if not self.credential_file.is_file():
                raise failure('missing', 'Native credential file is unavailable')
            with self.credential_file.open('rb') as source:
                raw = source.read(67)
            if len(raw) > 66:
                raise failure('authentication', 'Invalid native credential file')
            token = raw.strip().decode('ascii')
            if len(token) != 64 or any(c not in '0123456789abcdefABCDEF' for c in token):
                raise failure('authentication', 'Invalid native credential file')
            deadline = time.monotonic() + 5
            with socket.create_connection(('127.0.0.1', self.port), timeout=1) as sock:
                sock.settimeout(1)
                sock.sendall((json.dumps(dict(id=1, method='auth', params=dict(token=token))) + '\n').encode())
                authenticated = self._reply(sock, deadline, 4096)
                if not isinstance(authenticated, dict) or authenticated.get('ok') is not True:
                    raise failure('authentication', 'Native authentication rejected')
                sock.settimeout(max(.001, deadline - time.monotonic()))
                sock.sendall((json.dumps(dict(id=2, method='engine.execute',
                                             params=dict(command='document.inspect', params={}))) + '\n').encode())
                reply = self._reply(sock, deadline, 1024 * 1024)
            if not isinstance(reply, dict) or reply.get('ok') is not True:
                raise failure('missing', 'Native document inspection is unavailable')
            return layer_objects(self.document, reply.get('result'))
        except (OSError, UnicodeError, ValueError, RecursionError):
            # Never echo native error bodies, credential contents or local paths.
            raise failure('missing', 'Native layer inspection is unavailable') from None

    def apply_changes(self, *_args, **_kwargs):
        raise failure('capability', 'PhotoCraft layer inspection is read-only')
