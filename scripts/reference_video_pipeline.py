"""Text -> anchored character views / scene / prop / firstframe -> native H3 Ref2VA video."""
import argparse
import copy
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace
from PIL import Image, ImageDraw, ImageFont
from generate import ROOT, graph as video_graph, request
from generate_image import graph as image_graph
from workflow_client import run_job, save_json, sha256
from export_editor_workflow import export

def contact_sheet(assets, output):
    labels=[name for name in ['character_front','character_side','character_back','scene','prop','firstframe'] if name in assets]
    labels.extend(name for name in assets if name not in labels)
    canvas=Image.new('RGB',(1200,460*((len(labels)+2)//3)),'#1c2430'); draw=ImageDraw.Draw(canvas)
    for i,name in enumerate(labels):
        im=Image.open(assets[name]['path']).convert('RGB'); im.thumbnail((380,410))
        x=(i%3)*400+(400-im.width)//2; y=(i//3)*460
        canvas.paste(im,(x,y)); draw.text(((i%3)*400+14,y+427),name,fill='white')
    canvas.save(output)
    if not all(name in assets for name in ['character_front','character_side','character_back']):
        return
    portraits=[Image.open(assets[n]['path']).convert('RGB') for n in labels[:3]]
    width=max(im.width for im in portraits); height=max(im.height for im in portraits)
    sheet=Image.new('RGB',(width*3,height+64),'#e5e7e8'); draw=ImageDraw.Draw(sheet)
    font=ImageFont.load_default(size=30)
    for i,(im,label) in enumerate(zip(portraits,['FRONT','RIGHT PROFILE','BACK'])):
        sheet.paste(im,(i*width+(width-im.width)//2,0)); draw.text((i*width+24,height+15),label,fill='#202b35',font=font)
    sheet.save(Path(output).with_name('character-turnaround.png'))

def merge_graphs(graphs, assets):
    merged={}; producers={}; offset=0
    for name,g in graphs.items():
        mapping={k:str(offset+int(k)) for k in g}
        redirects={}
        for key,n in g.items():
            if n['class_type']=='LoadImage':
                src=(ROOT/'ComfyUI/input'/n['inputs']['image']).resolve()
                digest=sha256(src)
                if digest in producers:
                    redirects[key]=producers[digest]
        for key,n in g.items():
            if key in redirects:
                continue
            node=copy.deepcopy(n)
            for field,value in node['inputs'].items():
                if isinstance(value,list) and len(value)==2 and isinstance(value[0],str) and value[0] in mapping:
                    node['inputs'][field]=redirects.get(value[0],[mapping[value[0]],value[1]])
            merged[mapping[key]]=node
        if name in assets:
            producers[assets[name]['sha256']]=[mapping['12'],0]
        offset+=1000
    return merged

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=ROOT/'configs/greenhouse-reference-video.json')
    parser.add_argument('--run-dir',type=Path,default=ROOT/'runs/white_reference_demo')
    parser.add_argument('--until',choices=['references','video'],default='video')
    parser.add_argument('--force',action='store_true')
    parser.add_argument('--force-stage',action='append',default=[],help='Recompute one named stage; repeat for dependent stages if their inputs changed')
    parser.add_argument('--url',default='http://127.0.0.1:8188')
    args=parser.parse_args(); folder=args.run_dir.resolve(); folder.mkdir(parents=True,exist_ok=True)
    config=json.loads(args.config.read_text(encoding='utf-8-sig'))
    manifest=dict(config=config,config_path=str(args.config.resolve()),status='running',assets={},jobs={},started_at=time.time(),
                  software={p:importlib.metadata.version(p) for p in ['torch','comfy-kitchen','sageattention','triton-windows']})
    manifest['model_manifests']={name:json.loads((ROOT/'docs'/name).read_text(encoding='utf-8')) for name in
        ['image-models-manifest.json','int8-reference-manifest.json','models-manifest.json','reference-models-manifest.json']}
    manifest['software']['comfyui_commit']=subprocess.check_output(['git','-C',str(ROOT/'ComfyUI'),'rev-parse','HEAD'],text=True).strip()
    manifest['software']['kjnodes_commit']=subprocess.check_output(['git','-C',str(ROOT/'ComfyUI/custom_nodes/ComfyUI-KJNodes'),'rev-parse','HEAD'],text=True).strip()
    save_json(folder/'config.snapshot.json',config)
    assets={}; graphs={}
    external=config.get('external_references',{})
    for key,ref in external.items():
        if sha256(Path(ref['path']))!=ref['sha256']: raise ValueError('External reference changed: '+key)
    manifest['external_references']=external
    try:
        for stage in config['stages']:
            name=stage['name']
            if not name.replace('_','').isalnum(): raise ValueError('Stage name must be alphanumeric with underscores')
            refs=[(assets.get(n) or external[n])['path'] for n in stage['references']]
            prompt=(ROOT/stage['prompt_file']).read_text(encoding='utf-8-sig')
            g=image_graph(prompt,refs,stage['width'],stage['height'],stage['seed'],stage.get('variant',config['image_variant']),stage.get('steps'),f'references/{folder.name}/{name}')
            graphs[name]=g
            result=run_job(g,folder/'jobs'/name,args.url,args.force or name in args.force_stage)
            output=next(x for x in result['files'] if x['node_id']=='13')
            destination=folder/'assets'/(name+'.png'); destination.parent.mkdir(exist_ok=True)
            shutil.copy2(output['path'],destination)
            assets[name]=dict(path=str(destination),sha256=sha256(destination),width=stage['width'],height=stage['height'],references=stage['references'],prompt=prompt)
            manifest['assets']=assets; manifest['jobs'][name]=dict(prompt_id=result['prompt_id'],server_seconds=result.get('server_seconds'),record=str(folder/'jobs'/name/'job.json'))
            save_json(folder/'manifest.json',manifest)
        contact_sheet(assets,folder/'assets/reference-board.jpg')
        request(args.url,'/free',{'unload_models':True,'free_memory':True})
        if args.until=='video':
            v=config['video']; refs=[]
            for name in v['references']:
                src=Path(assets[name]['path']); filename='pipeline_'+sha256(src)[:16]+src.suffix
                shutil.copy2(src,ROOT/'ComfyUI/input'/filename); refs.append(filename)
            params=SimpleNamespace(prompt_file=str(ROOT/v['prompt_file']),references=v['references'],comfy_references=refs,image=None,
                width=v['width'],height=v['height'],seconds=v['seconds'],seed=v['seed'],steps=v['steps'],base=False,int8=True,
                head_chunks=v['head_chunks'],ffn_chunks=v['ffn_chunks'],memory_efficient_sage=True,crop_720p=False,crop_1080p=False,name=folder.name+'_h3_768p')
            g=video_graph(params); graphs['video']=g
            result=run_job(g,folder/'jobs/video',args.url,args.force or 'video' in args.force_stage,timeout=7200)
            manifest['video']=result['files'][0]
            manifest['jobs']['video']=dict(prompt_id=result['prompt_id'],server_seconds=result.get('server_seconds'),record=str(folder/'jobs/video/job.json'))
            inspection=subprocess.run([sys.executable,str(ROOT/'scripts/inspect_video.py'),manifest['video']['path']],check=True,capture_output=True,text=True,encoding='utf-8')
            manifest['video_inspection']=json.loads(inspection.stdout)
        combined=merge_graphs(graphs,assets)
        save_json(folder/'workflow_combined_api.json',combined)
        editor=folder/'workflow_combined_editor.json'
        export(combined,editor,args.url,'# Local reference assets → H3 768p\n\nFLUX.2 Klein 4B + H3 Ref2VA. The resumable CLI pipeline is the tested execution path. This flat combined graph is exported for inspection; running all stages together may have a higher memory peak. See docs/reference-video-pipeline.md.')
        shutil.copy2(editor,ROOT/'ComfyUI/user/default/workflows'/('Reference-to-H3-'+folder.name+'.json'))
        manifest['status']='success' if args.until=='video' else 'references_ready'
        save_json(folder/'manifest.json',manifest)
        request(args.url,'/free',{'unload_models':True,'free_memory':True})
        print(json.dumps({'status':manifest['status'],'manifest':str(folder/'manifest.json'),'video':manifest.get('video'),'reference_board':str(folder/'assets/reference-board.jpg')},ensure_ascii=False),flush=True)
    except Exception as exc:
        manifest['status']='error'; manifest['error']=str(exc); save_json(folder/'manifest.json',manifest)
        raise

if __name__=='__main__':
    main()
