"""Generate or edit reference images locally with FLUX.2 Klein 4B."""
import argparse
import json
from pathlib import Path
import shutil
from generate import ROOT
from workflow_client import run_job, sha256

def graph(prompt, references=(), width=1024, height=1024, seed=20260913, variant='distilled', steps=None, prefix='references/image'):
    if width%16 or height%16:
        raise ValueError('Image width/height must be multiples of 16')
    nodes={}
    def node(key, kind, **inputs):
        nodes[str(key)]={'class_type':kind,'inputs':inputs}
        return [str(key),0]
    model=node(1,'UNETLoader',unet_name='flux-2-klein-'+('base-' if variant=='base' else '')+'4b-fp8.safetensors',weight_dtype='default')
    clip=node(2,'CLIPLoader',clip_name='qwen_3_4b.safetensors',type='flux2',device='default')
    vae=node(3,'VAELoader',vae_name='flux2-vae.safetensors')
    positive=node(4,'CLIPTextEncode',clip=clip,text=prompt)
    negative=node(5,'CLIPTextEncode',clip=clip,text='')
    for index, path in enumerate(references):
        path=Path(path).resolve()
        filename='pipeline_'+sha256(path)[:16]+path.suffix.lower()
        target=ROOT/'ComfyUI/input'/filename
        if target.resolve()!=path:
            shutil.copy2(path,target)
        key=20+index*5
        image=node(key,'LoadImage',image=filename)
        image=node(key+1,'ImageScaleToTotalPixels',image=image,upscale_method='lanczos',megapixels=1.0,resolution_steps=16)
        latent=node(key+2,'VAEEncode',pixels=image,vae=vae)
        positive=node(key+3,'ReferenceLatent',conditioning=positive,latent=latent)
        negative=node(key+4,'ReferenceLatent',conditioning=negative,latent=latent)
    guider=node(6,'CFGGuider',model=model,positive=positive,negative=negative,cfg=5.0 if variant=='base' else 1.0)
    noise=node(7,'RandomNoise',noise_seed=seed)
    latent=node(8,'EmptyFlux2LatentImage',width=width,height=height,batch_size=1)
    sampler=node(9,'KSamplerSelect',sampler_name='euler')
    sigmas=node(10,'Flux2Scheduler',steps=steps or (20 if variant=='base' else 4),width=width,height=height)
    sampled=node(11,'SamplerCustomAdvanced',noise=noise,guider=guider,sampler=sampler,sigmas=sigmas,latent_image=latent)
    image=node(12,'VAEDecode',samples=sampled,vae=vae)
    node(13,'SaveImage',images=image,filename_prefix=prefix)
    return nodes

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prompt-file',required=True,type=Path)
    parser.add_argument('--references',nargs='*',default=[])
    parser.add_argument('--width',type=int,default=1024)
    parser.add_argument('--height',type=int,default=1024)
    parser.add_argument('--seed',type=int,default=20260913)
    parser.add_argument('--variant',choices=['base','distilled'],default='distilled')
    parser.add_argument('--steps',type=int)
    parser.add_argument('--run-dir',type=Path,required=True)
    parser.add_argument('--force',action='store_true')
    parser.add_argument('--url',default='http://127.0.0.1:8188')
    args=parser.parse_args()
    g=graph(args.prompt_file.read_text(encoding='utf-8-sig'),args.references,args.width,args.height,args.seed,args.variant,args.steps,'references/'+args.run_dir.name)
    result=run_job(g,args.run_dir,args.url,args.force)
    print(json.dumps({'files':result['files'],'manifest':str(args.run_dir/'job.json')},ensure_ascii=False))

if __name__=='__main__':
    main()
