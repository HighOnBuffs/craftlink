"""Minimal future-app registration example: no CraftLink core changes or app-name branch."""
import json,pathlib,sys,uuid
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'sdk'))
from craftlink import Client
client=Client(sys.argv[1],sys.stdin.readline().strip())
manifest=dict(schema=1,application='example.generated.notes',version='1.0',object_types={'note':['text']},representations=['text/plain'],read=True,write=True,history='broker',transactions='broker',lifecycle='external stdio',authentication='broker bearer',filesystem='no native filesystem access',fidelity='semantic text')
client.register_application(manifest)
obj=str(uuid.uuid4())
client.request('commit_transaction',dict(operation=str(uuid.uuid4()),changes=[dict(object=obj,document=str(uuid.uuid4()),application=manifest['application'],kind='note',expected=0,value=dict(text='A future application'),native=None)]))
assert client.request('resolve_link',dict(object=obj))['value']['text']=='A future application'
print(json.dumps(dict(registered=True,object=obj)))
