"""Run one bounded image-reference test, preserving graph, reference and provenance."""
import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import time
import uuid
import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'workflows/krea2-reference'
BASE = 'http://127.0.0.1:8188'


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--strength', type=float, default=0)
    parser.add_argument('--ref-boost', type=float, default=4)
    parser.add_argument('--prompt-file', type=pathlib.Path)
    parser.add_argument('--workflow', choices=['outfit', 'local'], default='outfit')
    args = parser.parse_args()
    queue = requests.get(BASE + '/queue', timeout=10).json()
    if queue['queue_running'] or queue['queue_pending']:
        raise SystemExit('Server busy; no submission.')
    stem = 'krea2_reference_outfit_slider' if args.workflow == 'outfit' else 'krea2_local_clothed_adjust'
    graph = json.loads((BUNDLE / (stem + '.api.json')).read_text(encoding='utf-8'))
    workflow = json.loads((BUNDLE / (stem + '.json')).read_text(encoding='utf-8'))
    graph['5']['inputs']['strength_model'] = args.strength
    if args.workflow == 'outfit': graph['16']['inputs']['ref_boost'] = args.ref_boost
    prompt_key = 'prompt' if args.workflow == 'outfit' else 'text'
    if args.prompt_file:
        graph['6']['inputs'][prompt_key] = args.prompt_file.read_text(encoding='utf-8').strip()
    run = ROOT / 'runs' / ('krea2-reference-' + time.strftime('%Y%m%d-%H%M%S'))
    run.mkdir(parents=True, exist_ok=False)
    graph['11']['inputs']['filename_prefix'] = 'krea2-reference/' + run.name
    for node in workflow['nodes']:
        if node['id'] == 5: node['widgets_values'][1] = args.strength
        if node['id'] == 16 and args.workflow == 'outfit': node['widgets_values'][0] = args.ref_boost
        if node['id'] == 6: node['widgets_values'][0] = graph['6']['inputs'][prompt_key]
        if node['id'] == 11: node['widgets_values'][0] = graph['11']['inputs']['filename_prefix']
    reference = ROOT / 'ComfyUI/input' / graph['13']['inputs']['image']
    shutil.copy2(reference, run / 'reference.png')
    for bundle, prefix in [(BUNDLE, 'identity'), (ROOT / 'workflows/krea2-raw-slider', 'base')]:
        for name in ['models-manifest.json', 'model-verification.json']:
            shutil.copy2(bundle / name, run / (prefix + '-' + name))
    write(run / 'prompt.json', graph)
    write(run / 'workflow.json', workflow)
    write(run / 'system_stats.json', requests.get(BASE + '/system_stats', timeout=10).json())
    manifest = dict(status='prepared', references=[dict(order=1, path=str(reference), sha256=hashlib.sha256(reference.read_bytes()).hexdigest())],
                    seed=graph['9']['inputs']['seed'], width=768, height=1024, slider_strength=args.strength,
                    workflow=args.workflow, ref_boost=args.ref_boost if args.workflow == 'outfit' else None,
                    grounding_px=768 if args.workflow == 'outfit' else None, steps=graph['9']['inputs']['steps'],
                    denoise=graph['9']['inputs']['denoise'], cfg=1, instruction=graph['6']['inputs'][prompt_key])
    write(run / 'manifest.json', manifest)
    started = time.time()
    try:
        response = requests.post(BASE + '/prompt', json=dict(prompt=graph, client_id=str(uuid.uuid4()),
            extra_data={'extra_pnginfo': {'workflow': workflow}}), timeout=30)
        (run / 'submission.json').write_text(response.text, encoding='utf-8')
        response.raise_for_status()
        submission = response.json()
        if submission.get('node_errors'): raise RuntimeError(submission['node_errors'])
    except Exception:
        manifest['status'] = 'submission_failed_or_uncertain_inspect_queue'
        write(run / 'manifest.json', manifest)
        raise
    pid = submission['prompt_id']
    manifest.update(status='submitted', prompt_id=pid)
    write(run / 'manifest.json', manifest)
    print('SUBMITTED', pid, run, flush=True)
    samples = []
    while time.time() - started < 900:
        history = requests.get(BASE + '/history/' + pid, timeout=15).json().get(pid)
        try:
            samples.append(dict(seconds=round(time.time()-started, 2), gpu=subprocess.check_output(
                ['nvidia-smi', '--query-gpu=memory.used,memory.total', '--format=csv,noheader,nounits'], text=True, timeout=5).strip()))
        except (OSError, subprocess.SubprocessError): pass
        if history:
            write(run / 'history.json', history)
            write(run / 'gpu-memory.json', samples)
            manifest.update(status='execution_failed', elapsed_seconds=round(time.time()-started, 2))
            if history['status']['status_str'] == 'success':
                outputs = []
                for entry in history['outputs'].values():
                    for item in entry.get('images', []):
                        if item.get('type') != 'output': continue
                        path = ROOT / 'ComfyUI/output' / item['subfolder'] / item['filename']
                        outputs.append(dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
                if outputs: manifest.update(status='execution_success_visual_review_pending', outputs=outputs)
            write(run / 'manifest.json', manifest)
            print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)
            if manifest['status'] == 'execution_failed': raise SystemExit('Failed; inspect history.json before retry.')
            return
        time.sleep(5)
    manifest['status'] = 'timeout_in_flight_not_cancelled'
    write(run / 'manifest.json', manifest)
    raise SystemExit('Timed out; inspect server before another submission. Job not cancelled.')


if __name__ == '__main__':
    main()
