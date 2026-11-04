"""CraftLink v1 synchronous SDK. Credentials stay in memory or a caller-owned private channel."""
import json
import socket

class CraftLinkError(RuntimeError):
    def __init__(self, response):
        super().__init__(response.get('error', str(response)))
        self.code=response.get('code','transport')
        self.response=response

class Client:
    def __init__(self,address,token):
        host,port=address.rsplit(':',1)
        if host!='127.0.0.1':raise ValueError('CraftLink v1 accepts loopback only')
        self.address=(host,int(port))
        self.token=token
    def request(self,method,params=None):
        with socket.create_connection(self.address,timeout=5) as sock:
            sock.settimeout(90)
            message=json.dumps(dict(token=self.token,method=method,params=params or {})).encode()+b'\n'
            if len(message)>1024*1024:raise ValueError('request exceeds 1 MiB')
            sock.sendall(message)
            line=sock.makefile('rb').readline(8*1024*1024+1)
            if len(line)>8*1024*1024:raise ValueError('response exceeds 8 MiB')
            response=json.loads(line)
            if not response.get('ok'):raise CraftLinkError(response)
            return response.get('result')
    def register_application(self,manifest):return self.request('register_application',manifest)
    def subscribe_to_changes(self,after=0,timeout_ms=20000):
        return self.request('subscribe_to_changes',dict(after=after,timeout_ms=timeout_ms))
