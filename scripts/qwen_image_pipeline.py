"""Local Qwen 2.1 image stages for the director; immutable inputs and resumable jobs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

from PIL import Image
from generate import ROOT, request
from workflow_client import run_job, save_json, sha256
from export_editor_workflow import export

INSTALL = ROOT / 'tools/qwen21'
URL = 'http://127.0.0.1:8190'
MODEL = 'qwen_image_2.1_int8_convrot.safetensors'
ENCODER = 'qwen3vl_8b_w4a8.safetensors'
VAE = 'qwen_image_2.1_vae_bf16.safetensors'
REVISION = 'ace0edeb3791a594ddfa36ed5f41a178a394e921'
EDIT_PROFILE = 'independent-reference-seed-v2'


def sampling_seed(stage, refs, mask=None, profile=EDIT_PROFILE):
    """Keep reruns reproducible without reusing the noise that made an input image."""
    if profile not in ('legacy-v1', EDIT_PROFILE):raise ValueError('Unknown Qwen workflow profile: '+profile)
    requested=int(stage['seed'])
    if not refs or profile=='legacy-v1':return requested
    identity=dict(profile=profile,seed=requested,stage=stage['name'],
                  references=[r['sha256'] for r in refs],mask=mask['sha256'] if mask else None)
    derived=int.from_bytes(hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).digest()[:8],'big') & ((1<<63)-1)
    return derived if derived!=requested else (derived+1) % (1<<63)


def input_image(ref):
    source = Path(ref['path'])
    if sha256(source) != ref['sha256']:
        raise ValueError('Input changed: ' + str(source))
    name = ref['sha256'] + source.suffix.lower()
    dest = INSTALL / 'ComfyUI/input' / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists() or sha256(dest) != ref['sha256']:
        shutil.copy2(source, dest)
    return name


def validate_mask(base, mask):
    with Image.open(base) as original, Image.open(mask) as selection:
        if original.size != selection.size:
            raise ValueError('选区尺寸必须与原图一致')
        if selection.convert('L').getextrema()[1] == 0:
            raise ValueError('请先画出编辑选区')


def composite_exact(base, generated, mask, target):
    validate_mask(base, mask)
    with Image.open(base) as original, Image.open(generated) as result, Image.open(mask) as selection:
        mode = 'RGBA' if 'A' in original.getbands() else 'RGB'
        original = original.convert(mode)
        result = result.convert(mode).resize(original.size, Image.Resampling.LANCZOS)
        Image.composite(result, original, selection.convert('L')).save(target)


def build(stage, prompt, refs, mask=None, profile=EDIT_PROFILE):
    def node(kind, **inputs):return dict(class_type=kind, inputs=inputs)
    actual = prompt
    if mask:
        actual = ('以图1为待编辑原图，图2为黑白选区蒙版。仅修改图2白色区域对应的内容，黑色区域保持原样；'
                  '输出完整编辑后的图1，不显示蒙版。编辑要求：' + prompt)
    graph = {
        '1': node('UNETLoader', unet_name=MODEL, weight_dtype='default'),
        '2': node('CLIPLoader', clip_name=ENCODER, type='qwen_image', device='default'),
        '3': node('VAELoader', vae_name=VAE),
        '4': node('TextEncodeQwenImage21', clip=['2', 0], prompt=actual, negative_prompt='', resolution=1024),
        '5': node('EmptyLatentImage', width=stage['width'], height=stage['height'], batch_size=1),
        '6': node('KSampler', model=['1', 0], positive=['4', 0], negative=['4', 1], latent_image=['5', 0],
                  seed=sampling_seed(stage,refs,mask,profile), steps=25, cfg=1, sampler_name='euler', scheduler='simple', denoise=1),
        '7': node('VAEDecode', samples=['6', 0], vae=['3', 0]),
        '13': node('SaveImage', images=['7', 0], filename_prefix='director-qwen21/' + stage['name']),
    }
    ordered = [*refs, mask] if mask else refs
    for i, ref in enumerate(ordered):
        key = str(20+i)
        graph[key] = node('LoadImage', image=input_image(ref))
        graph['4']['inputs']['images.image_'+str(i+1)] = [key, 0]
    if refs:
        graph['4']['inputs']['vae'] = ['3', 0]
        # Conditioning references use their native dimensions; requested output keeps the asset's canvas.
        graph['4']['inputs']['resolution'] = 0
    if mask:
        validate_mask(refs[0]['path'], mask['path'])
        with Image.open(refs[0]['path']) as im:
            graph['5']['inputs'].update(width=max(32, round(im.width/32)*32), height=max(32, round(im.height/32)*32))
    return graph, actual


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--until', choices=['references'], default='references')
    args = parser.parse_args()
    folder = args.run_dir.resolve();folder.mkdir(parents=True, exist_ok=True)
    config = json.loads(args.config.read_text(encoding='utf-8-sig'))
    # Existing run configs retain their original graph and submission receipts on resume.
    profile=config.get('qwen_workflow_profile','legacy-v1')
    verification = json.loads((ROOT/'runs/qwen21-20260921/model-verification.json').read_text(encoding='utf-8'))
    manifest = dict(status='running', provider='local', image_variant='qwen21', model_revision=REVISION,
        models=verification, comfy_commit=subprocess.check_output(['git','-C',str(INSTALL/'ComfyUI'),'rev-parse','HEAD'],text=True).strip(),
        workflow_profile=profile,config=config, assets={})
    save_json(folder/'manifest.json', manifest)
    available = dict(config.get('external_references', {}))
    for stage in config['stages']:
        prompt = Path(stage['prompt_file']).read_text(encoding='utf-8').strip()
        refs = [available[key] for key in stage.get('references', [])]
        mask = stage.get('edit_mask')
        graph, actual = build(stage, prompt, refs, mask,profile=profile)
        jobdir = folder/'jobs'/stage['name']
        jobdir.mkdir(parents=True, exist_ok=True)
        export(graph, jobdir/'workflow_editor.json', url=URL, title='Qwen 2.1 · '+stage['name'])
        record = run_job(graph, jobdir, url=URL, output_root=INSTALL/'ComfyUI/output')
        files = [f for f in record['files'] if f['node_id']=='13']
        if len(files)!=1:raise RuntimeError('Expected exactly one output')
        target = folder/(stage['name']+'.png')
        if mask:composite_exact(refs[0]['path'], files[0]['path'], mask['path'], target)
        else:shutil.copy2(files[0]['path'], target)
        with Image.open(target) as im:width,height=im.size
        result = dict(path=str(target),sha256=sha256(target),width=width,height=height,prompt=prompt,
            effective_prompt=actual,seed=graph['6']['inputs']['seed'],requested_seed=stage['seed'],
            workflow_profile=profile,references=refs,edit_mask=mask,
            raw_output=files[0],server_seconds=record.get('server_seconds'),job=str(jobdir/'job.json'))
        if mask:result['compositing']='Pillow Image.composite, mask=L; outside mask exactly preserved including alpha'
        available[stage['name']]=result;manifest['assets'][stage['name']]=result
        save_json(folder/'manifest.json',manifest)
    manifest['status']='references_ready';save_json(folder/'manifest.json',manifest)
    request(URL,'/free',{'unload_models':True,'free_memory':True})


if __name__=='__main__':
    try:main()
    except TimeoutError as exc:
        print(str(exc),file=sys.stderr);sys.exit(10)
