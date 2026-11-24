"""Run/resume the four local image-only Qwen 2.1 examples, preserving evidence."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import time
import uuid

import psutil
from PIL import Image
from generate import ROOT, request, ComfyHTTPError
from workflow_client import save_json, sha256
from export_editor_workflow import export

URL = 'http://127.0.0.1:8190'
INSTALL = ROOT / 'tools/qwen21'
RUN = ROOT / 'runs/qwen21-20260921'


def build(config, example):
    def node(kind, **inputs):
        return dict(class_type=kind, inputs=inputs)
    g = {
        '1': node('UNETLoader', unet_name=config['model'], weight_dtype='default'),
        '2': node('CLIPLoader', clip_name=config['encoder'], type='qwen_image', device='default'),
        '3': node('VAELoader', vae_name=config['vae']),
        '4': node('TextEncodeQwenImage21', clip=['2', 0], prompt=example['prompt'], negative_prompt='', resolution=1024),
        '5': node('EmptyLatentImage', width=example['width'], height=example['height'], batch_size=1),
        '6': node('KSampler', model=['1', 0], positive=['4', 0], negative=['4', 1],
                  latent_image=['5', 0], seed=example['seed'], steps=config['steps'], cfg=config['cfg'],
                  sampler_name=config['sampler'], scheduler=config['scheduler'], denoise=1),
        '7': node('VAEDecode', samples=['6', 0], vae=['3', 0]),
        '8': node('SaveImage', images=['7', 0], filename_prefix='qwen21/' + example['name']),
    }
    if example['references']:
        g['4']['inputs']['vae'] = ['3', 0]
        g['6']['inputs']['latent_image'] = ['4', 2]
        del g['5']
        for i, ref in enumerate(example['references'], 1):
            key = str(10 + i)
            g[key] = node('LoadImage', image=ref + '.png')
            g['4']['inputs']['images.image_' + str(i)] = [key, 0]
    return g


def run(example, graph):
    folder = RUN / 'jobs' / example['name']
    folder.mkdir(parents=True, exist_ok=True)
    save_json(folder / 'workflow_api.json', graph)
    workflow = export(graph, folder / 'workflow_editor.json', url=URL, title=example['title'])
    workflow_dir = INSTALL / 'ComfyUI/user/default/workflows'
    workflow_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(folder / 'workflow_editor.json', workflow_dir / (example['name'] + '.json'))
    state_path = folder / 'job.json'
    graph_hash = sha256(folder / 'workflow_api.json')
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding='utf-8'))
        if state['graph_sha256'] != graph_hash:
            raise RuntimeError('This example changed. Use a distinct example name to preserve the old run.')
        if state['status'] == 'success':
            if sha256(state['path']) != state['sha256']:
                raise RuntimeError('Saved output was modified.')
            return state
        if state['status'] != 'running':
            raise RuntimeError(f'Inspect failed/uncertain submission before retrying: {state_path}')
    else:
        state = dict(status='submitting', graph_sha256=graph_hash, example=example,
                     started_at=time.time(), client_id=str(uuid.uuid4()))
        state['ordered_references'] = [dict(path=str(RUN / 'images' / (ref + '.png')),
                                          sha256=sha256(RUN / 'images' / (ref + '.png')))
                                       for ref in example['references']]
        save_json(state_path, state)
        try:
            result = request(URL, '/prompt', dict(prompt=graph, client_id=state['client_id'],
                             extra_data={'extra_pnginfo': {'workflow': workflow}}))
        except ComfyHTTPError as exc:
            state.update(status='rejected' if exc.submission_rejected else 'unknown', error=exc.payload or exc.body)
            save_json(state_path, state)
            raise
        state.update(status='running', prompt_id=result['prompt_id'])
        save_json(state_path, state)
    print('Running', example['name'], state['prompt_id'], flush=True)
    deadline = time.monotonic() + 1800
    while time.monotonic() < deadline:
        history = request(URL, '/history/' + state['prompt_id'])
        if state['prompt_id'] in history:
            entry = history[state['prompt_id']]
            state.update(history=entry, status=entry['status']['status_str'])
            save_json(state_path, state)
            if state['status'] != 'success':
                raise RuntimeError(f'Execution failed: {state_path}')
            events = dict(entry['status']['messages'])
            item = entry['outputs']['8']['images'][0]
            source = (INSTALL / 'ComfyUI/output' / item['subfolder'] / item['filename']).resolve()
            source.relative_to((INSTALL / 'ComfyUI/output').resolve())
            target = RUN / 'images' / (example['name'] + '.png')
            target.parent.mkdir(exist_ok=True)
            shutil.copy2(source, target)
            with Image.open(target) as im:
                state.update(width=im.width, height=im.height, mode=im.mode)
                if im.mode == 'RGBA':
                    state['alpha_extrema'] = im.getchannel('A').getextrema()
                    state['transparent_fraction'] = im.getchannel('A').histogram()[0] / (im.width * im.height)
            samples = [json.loads(x) for x in (folder / 'resources.jsonl').read_text().splitlines()]
            state.update(path=str(target), sha256=sha256(target), source_path=str(source),
                         server_seconds=(events['execution_success']['timestamp'] - events['execution_start']['timestamp']) / 1000,
                         sampled_peak_gpu_mib=max(x['gpu_memory_mib'] for x in samples),
                         min_available_ram_gib=min(x['ram_available_bytes'] for x in samples) / 2**30)
            save_json(state_path, state)
            print('Done', example['name'], state['server_seconds'], 'seconds', flush=True)
            return state
        queue = request(URL, '/queue')
        if state['prompt_id'] not in [x[1] for x in queue['queue_running'] + queue['queue_pending']]:
            if state['prompt_id'] not in request(URL, '/history/' + state['prompt_id']):
                raise RuntimeError('Job disappeared; inspect saved state rather than automatically resubmitting.')
        gpu = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.used,utilization.gpu',
                                       '--format=csv,noheader,nounits'], text=True)
        memory, utilization = map(float, gpu.strip().splitlines()[0].split(','))
        sample = dict(time=time.time(), gpu_memory_mib=memory, gpu_util_percent=utilization,
                      ram_available_bytes=psutil.virtual_memory().available)
        with (folder / 'resources.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(sample) + '\n')
        time.sleep(3)
    raise TimeoutError('Polling timed out. The server job is NOT cancelled; resume the same example.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only', help='Run/resume one named example')
    args = parser.parse_args()
    config = json.loads((ROOT / 'configs/qwen21-examples.json').read_text(encoding='utf-8'))
    verification = json.loads((RUN / 'model-verification.json').read_text(encoding='utf-8'))
    save_json(RUN / 'config.snapshot.json', config)
    save_json(RUN / 'environment.json', dict(comfy_commit=subprocess.check_output(
        ['git', '-C', str(INSTALL / 'ComfyUI'), 'rev-parse', 'HEAD'], text=True).strip(),
        packages={p: importlib.metadata.version(p) for p in ['torch', 'transformers', 'comfy-kitchen', 'comfy-aimdo', 'comfyui-frontend-package']},
        models=verification, system=request(URL, '/system_stats')))
    for example in config['examples']:
        if args.only and example['name'] != args.only:
            continue
        for ref in example['references']:
            source = RUN / 'images' / (ref + '.png')
            dest = INSTALL / 'ComfyUI/input' / source.name
            dest.parent.mkdir(exist_ok=True)
            shutil.copy2(source, dest)
        run(example, build(config, example))
    request(URL, '/free', {'unload_models': True, 'free_memory': True})


if __name__ == '__main__':
    main()
