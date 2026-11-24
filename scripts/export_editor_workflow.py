"""Build a flat editor workflow from our API graph and the installed node schemas."""
import argparse
import json
from pathlib import Path
import uuid
from generate import ROOT, request
from workflow_client import save_json

def export(graph, path, url='http://127.0.0.1:8188', title='Local reference workflow'):
    info=request(url,'/object_info')
    nodes=[]; links=[]; by_id={}; pending=[]
    for order,(key,definition) in enumerate(graph.items()):
        schema=info[definition['class_type']]
        node=dict(id=int(key),type=definition['class_type'],pos=[(order%4)*390,(order//4)*330],size=[360,270],flags={},order=order,mode=0,
                  inputs=[],outputs=[],properties={'Node name for S&R':definition['class_type']},widgets_values=[])
        inputs={**schema['input'].get('required',{}),**schema['input'].get('optional',{})}
        for name, spec in list(inputs.items()):
            if spec[0]=='COMFY_AUTOGROW_V3':
                template=spec[1]['template']['input']['required']
                child_spec=next(iter(template.values()))
                for field in definition['inputs']:
                    if field.startswith(name+'.'):
                        inputs[field]=child_spec
        for name, spec in inputs.items():
            if name not in definition['inputs']:
                continue
            value=definition['inputs'][name]
            if isinstance(value,list) and len(value)==2 and isinstance(value[0],str) and value[0] in graph:
                link_id=len(pending)+1
                pending.append([link_id,int(value[0]),value[1],int(key),len(node['inputs']),spec[0]])
                node['inputs'].append(dict(name=name,type=spec[0],link=link_id))
            else:
                node['widgets_values'].append(value)
                if name in ('seed','noise_seed'):
                    node['widgets_values'].append('fixed')
        for slot,typ in enumerate(schema['output']):
            names=schema.get('output_name',schema['output'])
            node['outputs'].append(dict(name=names[slot],type=typ,links=[],slot_index=slot))
        nodes.append(node); by_id[int(key)]=node
    for link in pending:
        by_id[link[1]]['outputs'][link[2]]['links'].append(link[0]); links.append(link)
    note_id=max(by_id)+1
    nodes.append(dict(id=note_id,type='MarkdownNote',pos=[0,-290],size=[1120,240],flags={},order=len(nodes),mode=0,
                      inputs=[],outputs=[],properties={},widgets_values=[title]))
    workflow=dict(id=str(uuid.uuid5(uuid.NAMESPACE_URL,str(Path(path).resolve()))),revision=0,last_node_id=note_id,last_link_id=len(links),
                  nodes=nodes,links=links,groups=[],config={},extra={'ds':{'scale':0.65,'offset':[150,350]}},version=0.4)
    save_json(path,workflow)
    return workflow

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('api',type=Path); p.add_argument('output',type=Path); p.add_argument('--title',default='Local reference workflow')
    a=p.parse_args(); export(json.loads(a.api.read_text(encoding='utf-8')),a.output,title=a.title)
