"""Local ComfyUI jobs with request fingerprints, resumable polling and output hashes."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
import uuid
import psutil
from generate import ROOT, request, ComfyHTTPError

def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)

def run_job(graph, folder, url='http://127.0.0.1:8188', force=False, timeout=3600, output_root=None):
    output_root = Path(output_root or ROOT / 'ComfyUI/output').resolve()
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(json.dumps(graph, sort_keys=True).encode()).hexdigest()
    state_path = folder / 'job.json'
    state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {}
    receipt_path = folder / 'submission.json'
    if not state and receipt_path.exists():
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        raise RuntimeError(f'Previous submission {receipt.get("status")}; reconcile or use a budgeted new attempt: {receipt_path}')
    if state and force:
        queue = request(url, '/queue')
        active = [x[1] for x in queue['queue_running'] + queue['queue_pending']]
        if state['prompt_id'] in active:
            raise RuntimeError(f'Existing job is still queued/running; resume without --force: {folder}')
        archive = folder / 'attempts' / state['prompt_id']
        archive.mkdir(parents=True, exist_ok=True)
        for name in ['job.json', 'workflow_api.json', 'resources.jsonl']:
            source = folder / name
            if source.exists():
                shutil.move(str(source), str(archive / name))
        state = {}
    if state and state['graph_sha256'] != digest:
        raise ValueError(f'Configuration changed: use a new run folder or --force: {folder}')
    if state.get('status') == 'success':
        if not all(Path(x['path']).is_file() and sha256(x['path']) == x['sha256'] for x in state['files']):
            raise ValueError(f'Saved output missing or modified: {folder}')
        print(f'REUSE {folder.name}', flush=True)
        return state
    save_json(folder / 'workflow_api.json', graph)
    if not state:
        receipt = dict(client_id=str(uuid.uuid4()), graph_sha256=digest, status='submitting', started_at=time.time())
        save_json(receipt_path, receipt)
        try:
            response = request(url, '/prompt', {'prompt':graph, 'client_id':receipt['client_id']})
        except ComfyHTTPError as exc:
            receipt.update(status='rejected' if exc.submission_rejected else 'unknown', http_status=exc.status, response=exc.payload or exc.body)
            save_json(receipt_path, receipt)
            raise
        receipt.update(status='accepted', response=response)
        save_json(receipt_path, receipt)
        state = dict(prompt_id=response['prompt_id'], graph_sha256=digest, status='running', started_at=time.time(), files=[])
        save_json(state_path, state)
    prompt_id = state['prompt_id']
    print(f'JOB {folder.name} {prompt_id}', flush=True)
    last_notice = 0
    poll_started = time.monotonic()
    while time.monotonic() - poll_started < timeout:
        elapsed = time.time() - state['started_at']
        history = request(url, '/history/' + prompt_id)
        if prompt_id in history:
            history = history[prompt_id]
            state['history'] = history
            state['status'] = history['status']['status_str']
            state['elapsed_seconds'] = round(elapsed, 3)
            events = {k:v for k,v in history['status']['messages']}
            if 'execution_success' in events:
                state['server_seconds'] = (events['execution_success']['timestamp']-events['execution_start']['timestamp'])/1000
            if state['status'] == 'success':
                files = []
                for node_id, output in history['outputs'].items():
                    for item in output.get('images', []) + output.get('audio', []):
                        if item['type'] != 'output':
                            continue
                        path = (output_root / item.get('subfolder','') / item['filename']).resolve()
                        path.relative_to(output_root)
                        files.append(dict(node_id=node_id, path=str(path), sha256=sha256(path), bytes=path.stat().st_size))
                state['files'] = files
            save_json(state_path, state)
            if state['status'] != 'success':
                raise RuntimeError(f'Generation failed: {state_path}')
            print(f'DONE {folder.name}: {state.get("server_seconds",elapsed):.2f}s', flush=True)
            return state
        queue = request(url, '/queue')
        active = [x[1] for x in queue['queue_running'] + queue['queue_pending']]
        if prompt_id not in active:
            if prompt_id in request(url, '/history/' + prompt_id):
                continue
            raise RuntimeError(f'Job disappeared from server (restart/history cleared). Inspect {state_path}; then --force to resubmit.')
        sample = dict(elapsed_seconds=round(elapsed,2), ram_available_bytes=psutil.virtual_memory().available)
        gpu = subprocess.run(['nvidia-smi','--query-gpu=memory.used,utilization.gpu,temperature.gpu,power.draw','--format=csv,noheader,nounits'],capture_output=True,text=True)
        if gpu.returncode == 0:
            sample.update(dict(zip(['gpu_memory_mib','gpu_util_percent','gpu_temperature_c','gpu_power_w'],map(float,gpu.stdout.strip().splitlines()[0].split(',')))))
        with (folder / 'resources.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(sample)+'\n')
        if elapsed-last_notice >= 60:
            print(f'RUNNING {folder.name}: {elapsed:.0f}s', flush=True)
            last_notice=elapsed
        time.sleep(3)
    raise TimeoutError(f'Polling timed out; server job may still run. Resume with the same run folder: {folder}')
