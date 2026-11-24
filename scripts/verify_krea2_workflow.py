"""Run one bounded image-only smoke test and retain its prompt and output hashes."""
import argparse
import hashlib
import json
import pathlib
import subprocess
import time
import uuid
import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'workflows/krea2-raw-slider'
BASE = 'http://127.0.0.1:8188'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preset', choices=['fast', 'quality'], required=True)
    parser.add_argument('--strength', type=float, default=1.0)
    parser.add_argument('--base-only', action='store_true', help='Verify base components while slider download is pending')
    parser.add_argument('--prompt-file', type=pathlib.Path)
    parser.add_argument('--width', type=int, default=1024)
    parser.add_argument('--height', type=int, default=1024)
    args = parser.parse_args()
    if min(args.width, args.height) < 256 or args.width % 16 or args.height % 16:
        parser.error('Dimensions must be multiples of 16 and at least 256')
    queue = requests.get(BASE + '/queue', timeout=10).json()
    if queue['queue_running'] or queue['queue_pending']:
        raise SystemExit('Server has another job. No test submitted.')
    stem = 'krea2_raw_slider_' + args.preset
    graph = json.loads((BUNDLE / (stem + '.api.json')).read_text(encoding='utf-8'))
    graph['5']['inputs']['strength_model'] = args.strength
    graph['8']['inputs'].update(width=args.width, height=args.height)
    if args.prompt_file:
        graph['6']['inputs']['text'] = args.prompt_file.read_text(encoding='utf-8').strip()
    if args.base_only:
        graph['9']['inputs']['model'] = graph['5']['inputs']['model']
        del graph['5']
    run = ROOT / 'runs' / ('krea2-study-' + time.strftime('%Y%m%d-%H%M%S') + '-' + args.preset)
    run.mkdir(parents=True, exist_ok=False)
    for filename in ['models-manifest.json', 'model-verification.json']:
        (run / filename).write_bytes((BUNDLE / filename).read_bytes())
    graph['11']['inputs']['filename_prefix'] = 'krea2-study/' + run.name
    workflow = json.loads((BUNDLE / (stem + '.json')).read_text(encoding='utf-8'))
    next(n for n in workflow['nodes'] if n['id'] == 5)['widgets_values'][1] = args.strength
    next(n for n in workflow['nodes'] if n['id'] == 6)['widgets_values'][0] = graph['6']['inputs']['text']
    next(n for n in workflow['nodes'] if n['id'] == 8)['widgets_values'] = [args.width, args.height, 1]
    if args.base_only:
        next(n for n in workflow['nodes'] if n['id'] == 5)['mode'] = 4
    next(n for n in workflow['nodes'] if n['id'] == 11)['widgets_values'][0] = graph['11']['inputs']['filename_prefix']
    (run / 'prompt.json').write_text(json.dumps(graph, indent=2), encoding='utf-8')
    (run / 'workflow.json').write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding='utf-8')
    stats = requests.get(BASE + '/system_stats', timeout=10).json()
    (run / 'system_stats.json').write_text(json.dumps(stats, indent=2), encoding='utf-8')
    started = time.time()
    response = requests.post(BASE + '/prompt', json={'prompt': graph, 'client_id': str(uuid.uuid4()),
                              'extra_data': {'extra_pnginfo': {'workflow': workflow}}}, timeout=30)
    (run / 'submission.json').write_text(response.text, encoding='utf-8')
    response.raise_for_status()
    submission = response.json()
    if submission.get('node_errors'):
        raise RuntimeError(submission['node_errors'])
    pid = submission['prompt_id']
    print('SUBMITTED', pid, run, flush=True)
    memory = []
    while time.time() - started < 1800:
        history = requests.get(BASE + '/history/' + pid, timeout=15).json().get(pid)
        try:
            memory.append({'seconds': round(time.time()-started, 2), 'gpu': subprocess.check_output(
                ['nvidia-smi', '--query-gpu=memory.used,memory.total', '--format=csv,noheader,nounits'],
                text=True, timeout=5).strip()})
        except (OSError, subprocess.SubprocessError):
            pass
        if history:
            (run / 'history.json').write_text(json.dumps(history, indent=2), encoding='utf-8')
            (run / 'gpu-memory.json').write_text(json.dumps(memory, indent=2), encoding='utf-8')
            if history['status']['status_str'] != 'success':
                print(json.dumps(history['status']), flush=True)
                raise SystemExit('Image execution failed; see history.json.')
            outputs = []
            for output in history['outputs'].values():
                for item in output.get('images', []):
                    path = ROOT / 'ComfyUI/output' / item['subfolder'] / item['filename']
                    outputs.append({'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
            if not outputs:
                raise RuntimeError('No image outputs')
            manifest = {'status': 'execution_success_visual_review_pending', 'preset': args.preset,
                        'slider_strength': 0 if args.base_only else args.strength,
                        'slider_enabled': not args.base_only and args.strength != 0,
                        'elapsed_seconds': round(time.time()-started, 2),
                        'prompt_id': pid, 'outputs': outputs, 'model_manifest': str(BUNDLE / 'models-manifest.json'),
                        'references': [], 'width': args.width, 'height': args.height, 'seed': graph['9']['inputs']['seed']}
            (run / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
            print(json.dumps(manifest, indent=2), flush=True)
            return
        time.sleep(5)
    (run / 'status.json').write_text(json.dumps({'status': 'timeout_in_flight_not_cancelled', 'prompt_id': pid}), encoding='utf-8')
    raise SystemExit('Timed out; server job was not cancelled. Inspect history before any new submission.')


if __name__ == '__main__':
    main()
