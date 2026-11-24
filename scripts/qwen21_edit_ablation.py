"""Controlled local Qwen image-only comparisons; preserve all jobs and original assets."""
import copy
import json
import argparse
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from qwen_image_pipeline import build,URL,INSTALL,ROOT
from generate import request
from workflow_client import run_job,save_json,sha256
from export_editor_workflow import export

FOLDER=ROOT/'runs/qwen21-cleanup-20260922'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--suffix',default='')
    parser.add_argument('--cases',nargs='*')
    parser.add_argument('--int8',action='store_true')
    args=parser.parse_args()
    queue=request(URL,'/queue')
    if queue['queue_running'] or queue['queue_pending']:raise RuntimeError('GPU service is busy')
    old=ROOT/'h3_director/data/runs/0eec903135ac'
    config=json.loads((old/'R10_v0/config.json').read_text(encoding='utf-8'))
    stage=config['stages'][0];prompt=Path(stage['prompt_file']).read_text(encoding='utf-8')
    refs=[config['external_references'][k] for k in stage['references']]
    clean=prompt.replace('轻微35mm胶片颗粒。','干净的数字摄影画面，平滑均匀的白色背景。')+'只参考人物身份与结构，不复制输入图的噪点、斑点、颗粒或锐化光晕，保留自然皮肤和布料细节。'
    anchor=old/'R08_v0/character_front.png'
    rgb=FOLDER/'anchor_rgb.png'
    if not rgb.exists():Image.open(anchor).convert('RGB').save(rgb)
    rgbref=[dict(path=str(rgb),sha256=sha256(rgb),key='R08_rgb')]
    cases=[('steps40',40,prompt,refs),('clean25',25,clean,refs),('clean40',40,clean,refs),
           ('anchor40',40,clean,[dict(path=str(anchor),sha256=sha256(anchor),key='clean_identity_anchor:R08')]),
           ('cfg2_clean40',40,clean,refs),('cache_off40',40,clean,refs),('ref512_clean40',40,clean,refs),
           ('simple_edit40',40,'Change the clothes of the man in <image1> to a bright red jacket and black pants. Replace the background with a clean, solid white studio background. Keep the same face and pose. Clean realistic studio photography.',refs),
           ('vision_only40',40,clean,refs),('rgb_anchor40',40,clean,rgbref),
           ('blur_anchor40',40,clean,[dict(path=str(anchor),sha256=sha256(anchor),key='R08')]),
           ('rgba_anchor40',40,clean,[dict(path=str(anchor),sha256=sha256(anchor),key='R08')]),
           ('rgba_dirty40',40,clean,refs),
           ('flux_vae_anchor40',40,clean,[dict(path=str(anchor),sha256=sha256(anchor),key='R08')]),
           ('newseed_anchor40',40,clean,[dict(path=str(anchor),sha256=sha256(anchor),key='R08')]),
           ('newseed_dirty40',40,clean,refs)]
    results=[]
    for name,steps,text,inputs in cases:
        if args.cases and name not in args.cases:continue
        case=name
        name+=args.suffix
        folder=FOLDER/'ablation'/name;folder.mkdir(parents=True,exist_ok=True)
        graph,effective=build({**stage,'name':name},text,inputs,profile='legacy-v1')
        if args.int8:graph['2']['inputs']['clip_name']='qwen3vl_8b_int8_convrot.safetensors'
        if case.startswith('newseed_'):graph['6']['inputs']['seed']=918273645
        graph['6']['inputs']['steps']=steps
        if case=='cfg2_clean40':
            graph['6']['inputs']['cfg']=2
            graph['4']['inputs']['negative_prompt']='噪点，噪声，胶片颗粒，斑点，过度锐化，黑色斑块，脏污背景，重复纹理，马赛克'
        if case=='cache_off40':
            graph['8']=dict(class_type='QwenImage21Cache',inputs=dict(model=['1',0],device='off',dtype='default'))
            graph['6']['inputs']['model']=['8',0]
        if case=='ref512_clean40':graph['4']['inputs']['resolution']=512
        if case=='vision_only40':graph['4']['inputs'].pop('vae')
        if case=='blur_anchor40':
            graph['30']=dict(class_type='ImageBlur',inputs=dict(image=['20',0],blur_radius=1,sigma=1.0))
            graph['4']['inputs']['images.image_1']=['30',0]
        if case.startswith('rgba_'):
            graph['30']=dict(class_type='JoinImageWithAlpha',inputs=dict(image=['20',0],alpha=['20',1]))
            graph['4']['inputs']['images.image_1']=['30',0]
        if case=='flux_vae_anchor40':
            graph['30']=dict(class_type='VAELoader',inputs=dict(vae_name='flux2-vae.safetensors'))
            graph['31']=dict(class_type='VAEEncode',inputs=dict(pixels=['20',0],vae=['30',0]))
            graph['32']=dict(class_type='VAEDecode',inputs=dict(samples=['31',0],vae=['30',0]))
            graph['33']=dict(class_type='SaveImage',inputs=dict(images=['32',0],filename_prefix='director-qwen21/flux_vae_reference'))
            graph['4']['inputs']['images.image_1']=['32',0]
        save_json(folder/'experiment.json',dict(case=name,steps=steps,prompt=text,effective_prompt=effective,references=inputs,seed=graph['6']['inputs']['seed'],requested_seed=stage['seed']))
        export(graph,folder/'workflow_editor.json',url=URL,title=name)
        result=run_job(graph,folder,url=URL,output_root=INSTALL/'ComfyUI/output')
        results.append(dict(name=name,path=next(f['path'] for f in result['files'] if f['node_id']=='13'),seconds=result['server_seconds']))
        save_json(FOLDER/('ablation-results'+args.suffix+'.json'),results)
    request(URL,'/free',dict(unload_models=True,free_memory=True))

if __name__=='__main__':main()
