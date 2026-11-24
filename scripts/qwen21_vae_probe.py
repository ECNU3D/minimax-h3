"""Isolate reference VAE reconstruction, without diffusion or text conditioning."""
from qwen_image_pipeline import ROOT,INSTALL,URL,VAE,input_image
from workflow_client import run_job,sha256,save_json
from generate import request
from PIL import Image
import numpy as np

def main():
    q=request(URL,'/queue')
    assert not q['queue_running'] and not q['queue_pending']
    p=ROOT/'h3_director/data/runs/0eec903135ac/R08_v0/character_front.png'
    g={'1':dict(class_type='LoadImage',inputs=dict(image=input_image(dict(path=str(p),sha256=sha256(p))))),
       '2':dict(class_type='VAELoader',inputs=dict(vae_name=VAE)),
       '3':dict(class_type='VAEEncode',inputs=dict(pixels=['1',0],vae=['2',0])),
       '4':dict(class_type='VAEDecode',inputs=dict(samples=['3',0],vae=['2',0])),
       '13':dict(class_type='SaveImage',inputs=dict(images=['4',0],filename_prefix='director-qwen21/vae_probe'))}
    folder=ROOT/'runs/qwen21-cleanup-20260922/vae_probe'
    r=run_job(g,folder,url=URL,output_root=INSTALL/'ComfyUI/output')
    out=next(f['path'] for f in r['files'] if f['node_id']=='13')
    a=np.asarray(Image.open(p).convert('RGB')).astype(float)
    b=np.asarray(Image.open(out).convert('RGB')).astype(float)
    mse=float(np.mean((a-b)**2))
    data=dict(input=str(p),output=out,mse=mse,psnr=float(10*np.log10(255**2/mse)))
    save_json(folder/'metrics.json',data);print(data)
    request(URL,'/free',dict(unload_models=True,free_memory=True))

if __name__=='__main__':main()
