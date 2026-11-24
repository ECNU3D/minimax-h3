"""Compare clean mother branching and iterative references with recorded jobs."""
import argparse,json
from pathlib import Path
from qwen_image_pipeline import ROOT,INSTALL,URL,build
from workflow_client import run_job,save_json,sha256
from generate import request
from export_editor_workflow import export

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--int8',action='store_true');args=ap.parse_args()
    folder=ROOT/'runs/qwen21-cleanup-20260922'/('chain_int8' if args.int8 else 'chain_w4a8')
    p=json.loads((folder.parent/'project.before.json').read_text(encoding='utf-8'))
    assets={a['id']:a for a in p['assets']}
    q=request(URL,'/queue');assert not q['queue_running'] and not q['queue_pending']
    outputs={}
    old=Path(assets['R08']['versions'][1]['files'][0]['path'])
    outputs['old_flux']=dict(path=str(old),sha256=sha256(old),key='R08_v1_flux')
    cases=[('mother','R08',None),('R09_branch','R09','mother'),('R10_branch','R10','mother'),('R10_chain','R10','R09_branch'),('R10_flux','R10','old_flux')]
    for name,key,ref in cases:
        a=assets[key];prompt=a['prompt'].replace('轻微35mm胶片颗粒。','干净的数字摄影画面。')
        inputs=[outputs[ref]] if ref else []
        g,actual=build(dict(name=folder.name+'_'+name,width=768,height=1152,seed=a['seed']),prompt,inputs,profile='legacy-v1')
        g['6']['inputs']['steps']=40
        if args.int8:g['2']['inputs']['clip_name']='qwen3vl_8b_int8_convrot.safetensors'
        run=folder/name;run.mkdir(parents=True,exist_ok=True)
        save_json(run/'inputs.json',dict(prompt=actual,references=inputs,seed=a['seed']))
        export(g,run/'workflow_editor.json',url=URL,title=name)
        r=run_job(g,run,url=URL,output_root=INSTALL/'ComfyUI/output')
        out=next(f for f in r['files'] if f['node_id']=='13');outputs[name]=dict(out,key=name)
        save_json(folder/'results.json',outputs)
    request(URL,'/free',dict(unload_models=True,free_memory=True))

if __name__=='__main__':main()
