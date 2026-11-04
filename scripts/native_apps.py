"""Owned native test processes; no changes to installed apps or existing sessions."""
import json, os, pathlib, socket, subprocess, time

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOKENS = {}

def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]

def call(port, method, params=None):
    with socket.create_connection(('127.0.0.1', port), timeout=8) as sock:
        sock.settimeout(65)
        reader=sock.makefile('rb')
        if port in TOKENS:
            credential=TOKENS[port].read_text().strip()
            sock.sendall((json.dumps(dict(id=0,method='auth',params=dict(token=credential)))+'\n').encode())
            auth=json.loads(reader.readline(4097))
            if not auth.get('ok'):raise RuntimeError('Native authentication rejected')
        sock.sendall((json.dumps(dict(id=1, method=method, params=params or {}))+'\n').encode())
        line=reader.readline(8*1024*1024+1)
        result=json.loads(line)
        if not result.get('ok'):
            raise RuntimeError(f'{method}: {result}')
        return result.get('result')

def command(port, name, params=None):
    return call(port,'engine.execute',dict(command=name,params=params or {}))

class App:
    def __init__(self, name, directory, native=None):
        self.name=name
        self.directory=pathlib.Path(directory).resolve()
        self.directory.mkdir(parents=True,exist_ok=True)
        self.port=free_port()
        profile=self.directory/(name+'-profile')
        profile.mkdir(exist_ok=True)
        env=os.environ.copy()
        env[name.upper()+'_CONFIG_DIR']=str(profile)
        args=[str(pathlib.Path(os.environ.get('ProgramFiles','C:/Program Files'))/name.title()/(name+'.exe')),'--control',str(self.port),'--automation-read-root',str(self.directory),'--automation-write-root',str(self.directory)]
        # Product directory capitalizes the second C as well.
        args[0]=str(pathlib.Path(os.environ.get('ProgramFiles','C:/Program Files'))/({'vectorcraft':'VectorCraft','figcraft':'FigCraft','photocraft':'PhotoCraft'}[name])/(name+'.exe'))
        args[0]=env.get('CRAFTLINK_'+name.upper()+'_EXE',args[0])
        self.token_file=profile/('control-'+str(self.port)+'.token')
        if name=='photocraft':
            env.pop('PHOTOCRAFT_CONTROL_TOKEN',None)
            args.extend(['--new-instance','--control-token-file',str(self.token_file)])
        if native: args.append(str(native))
        self.log=open(self.directory/(name+'.log'),'ab')
        startup=subprocess.STARTUPINFO() if os.name=='nt' else None
        if startup:
            startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow=0
        self.process=subprocess.Popen(args,env=env,stdout=self.log,stderr=self.log,startupinfo=startup)
        try:
            end=time.monotonic()+45
            while time.monotonic()<end:
                if self.process.poll() is not None: raise RuntimeError(f'{name} exited: {self.process.returncode}')
                try:
                    if self.token_file.is_file():TOKENS[self.port]=self.token_file
                    call(self.port,'engine.commands',{})
                    return
                except (OSError,ValueError,RuntimeError): time.sleep(.2)
            raise TimeoutError(name+' startup')
        except BaseException:
            self.close()
            raise
    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try: self.process.wait(10)
            except subprocess.TimeoutExpired: self.process.kill();self.process.wait()
        self.log.close()
        TOKENS.pop(self.port,None)

if __name__=='__main__':
    directory=ROOT/'runtime'/'probe'
    apps=[]
    try:
        for name in ['vectorcraft','figcraft']:
            app=App(name,directory);apps.append(app)
            command(app.port,'file.new',{})
            created=command(app.port,'shape.rectangle',dict(x=20,y=20,width=120,height=80))
            print(name,'create',json.dumps(created),flush=True)
            print(name,'inspect',json.dumps(call(app.port,'document.inspect',{}))[:7000],flush=True)
            command(app.port,'file.save',dict(path=str(directory/(name+'.'+name))))
    finally:
        for app in apps:app.close()
