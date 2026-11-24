"""Run approved audio stages sequentially, then remix an existing video without new frames."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import urlopen

from audio_common import ROOT, sha256, write_json

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', type=Path, default=ROOT/'configs/audio-film-test.json')
    p.add_argument('--run-dir', type=Path, default=ROOT/'runs/audio_film_test')
    p.add_argument('--only', choices=['design','clone','sfx','music','mix'])
    a = p.parse_args()
    a.config = a.config.resolve(); a.run_dir = a.run_dir.resolve()
    cfg = json.loads(a.config.read_text(encoding='utf-8'))
    video = ROOT/cfg['source_video']
    if sha256(video) != cfg['source_video_sha256']: raise ValueError('Source video changed')
    # Do not unload another user's queued work. Audio stages share the GPU.
    try:
        with urlopen('http://127.0.0.1:8188/queue', timeout=3) as r: queue = json.load(r)
    except OSError: queue = {}
    if queue.get('queue_running') or queue.get('queue_pending'):
        raise RuntimeError('ComfyUI has active/pending work; retry when the GPU is free.')
    a.run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = a.run_dir/'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}
    if manifest.get('config_sha256', sha256(a.config)) != sha256(a.config):
        raise ValueError('Changed configuration: use a new run directory.')
    manifest.update(status='running', subjective_review='pending_user_review',
        config=str(a.config), config_sha256=sha256(a.config), source_video=str(video),
        source_video_sha256=sha256(video), video_generation=False)
    manifest.setdefault('stages', {})
    env = os.environ.copy(); env['PYTHONUTF8'] = '1'
    stages = [a.only] if a.only else ['design','clone','sfx','music','mix']
    for stage in stages:
        env_name = {'design':'tts','clone':'tts','sfx':'sfx','music':'music','mix':'tts'}[stage]
        python = ROOT/f'audio/env-{env_name}/Scripts/python.exe'
        command = [str(python),str(ROOT/'scripts'/('audio_mix.py' if stage=='mix' else 'audio_worker.py')),
                   '--config',str(a.config),'--run-dir',str(a.run_dir)]
        if stage != 'mix': command += ['--stage',stage]
        started = time.time()
        manifest['stages'][stage] = dict(status='running',started=started)
        write_json(manifest_path,manifest)
        print('STAGE_START',stage,flush=True)
        with (a.run_dir/(stage+'.log')).open('a',encoding='utf-8') as log:
            result = subprocess.run(command,env=env,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            if stage == 'mix' and result.returncode == 0:
                for helper in ['audio_review.py','audio_validate.py']:
                    post = [str(python),str(ROOT/'scripts'/helper),'--run-dir',str(a.run_dir)]
                    if helper == 'audio_validate.py': post += ['--config',str(a.config)]
                    result = subprocess.run(post,env=env,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
                    if result.returncode: break
        manifest['stages'][stage].update(status='success' if result.returncode==0 else 'failed',
            elapsed_seconds=time.time()-started, exit_code=result.returncode)
        write_json(manifest_path,manifest)
        if result.returncode:
            manifest['status']='failed';write_json(manifest_path,manifest)
            raise RuntimeError(f'{stage} failed; see {a.run_dir/(stage+".log")}')
        print('STAGE_COMPLETE',stage,flush=True)
    manifest['status'] = 'success' if all(manifest['stages'].get(s,{}).get('status')=='success' for s in ['design','clone','sfx','music','mix']) else 'partial'
    write_json(manifest_path,manifest)

if __name__ == '__main__': main()
