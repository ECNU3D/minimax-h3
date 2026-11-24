"""Plan or resume sequential H3 jobs using immutable inputs and server job IDs.

Default is offline preflight. --execute submits work; this script never restarts
ComfyUI or cancels a server job. --timeout only bounds this client's waiting.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
from types import SimpleNamespace

from generate import graph, request, ComfyHTTPError
from workflow_client import ROOT, run_job, save_json, sha256
from h3_budget import Budget, BudgetStop
from h3_preview_config import PROFILES as PREVIEW_PROFILES, settings as preview_settings
from h3_flex_config import PROFILE as FLEX_PROFILE, settings as flex_settings


def prepare(spec, only=None, allow_reference_override=False):
    jobs = json.loads(Path(spec).read_text(encoding='utf-8-sig'))
    if not isinstance(jobs, list) or not jobs:
        raise ValueError('Spec must be a nonempty JSON list')
    names = [j['name'] for j in jobs]
    if len(names) != len(set(names)):
        raise ValueError('Duplicate shot names')
    selected = set(only or names)
    missing = selected - set(names)
    if missing:
        raise ValueError(f'Unknown --only names: {sorted(missing)}; available: {names}')
    plans = []
    for job in jobs:
        if job['name'] not in selected:
            continue
        name = job['name']
        if not re.fullmatch(r'[A-Za-z0-9_-]+', name):
            raise ValueError(f'Invalid name: {name}')
        prompt_file = (ROOT / job['prompt']).resolve()
        prompt = prompt_file.read_text(encoding='utf-8-sig')
        refs = [(ROOT / f).resolve() for f in job['refs']]
        # Only the explicitly opted-in lab accepts a clean text-only Ref2VA case.
        minimum = 0 if job.get('profile') == 'ref2v-lab' and allow_reference_override else 1
        if not minimum <= len(refs) <= 9:
            raise ValueError(f'{name}: expected {minimum}-9 references')
        if len(refs) != 3 and not allow_reference_override:
            raise ValueError(f'{name}: current default requires exactly 3 references; '
                             'an explicitly chosen legacy shot needs --allow-reference-override')
        tags = {int(n) for n in re.findall(r'<Picture\s+(\d+)>', prompt)}
        if tags != set(range(1, len(refs) + 1)):
            raise ValueError(f'{name}: Picture tags {sorted(tags)} do not match {len(refs)} ordered references')
        assets = [dict(path=str(p), sha256=sha256(p)) for p in refs]
        params = dict(width=int(job.get('width', 1344)), height=int(job.get('height', 768)),
                      seconds=float(job.get('seconds', 10)), seed=int(job['seed']))
        if params['width'] <= 0 or params['height'] <= 0 or params['width'] % 32 or params['height'] % 32:
            raise ValueError(f'{name}: positive video dimensions must be multiples of 32')
        if not 0 < params['seconds'] <= 15:
            raise ValueError(f'{name}: seconds outside local planning range (0,15]')
        stored = ['h3_reference_' + a['sha256'][:16] + p.suffix.lower() for a, p in zip(assets, refs)]
        profile = job.get('profile', 'legacy-ref2v-4step')
        ref_image_size = job.get('ref_image_size', 'match')
        if ref_image_size not in ('match', 'max'):
            raise ValueError(f'{name}: ref_image_size must be match or max')
        if profile not in ('legacy-ref2v-4step', 'ref2v-768p-8step', 'ref2v-pdd-8step', 'ref2v-lab', FLEX_PROFILE) + PREVIEW_PROFILES:
            raise ValueError(f'Unknown H3 profile: {profile}')
        new_profile = profile in ('ref2v-768p-8step', 'ref2v-pdd-8step')
        lab = profile == 'ref2v-lab'
        flex = profile == FLEX_PROFILE
        audio_assets=[]; audio_stored=[]
        if lab:
            from h3_lab_config import settings
            lab_settings=settings({**job.get('lab_settings',{}), 'seed':params['seed'],'seconds':params['seconds']})
            if (params['width'],params['height'])!=(1344,768):raise ValueError('测试工作流固定为原生 1344×768')
        if lab or flex:
            audio_refs=[(ROOT/f).resolve() for f in job.get('audio_refs',[])]
            if len(audio_refs)>3:raise ValueError('最多 3 个音频参考')
            audio_tags={int(n) for n in re.findall(r'<Audio\s+(\d+)>',prompt)}
            if audio_tags!=set(range(1,len(audio_refs)+1)):raise ValueError('Audio 标签与音频参考顺序不符')
            audio_assets=[dict(path=str(p),sha256=sha256(p)) for p in audio_refs]
            audio_stored=['h3_audio_'+a['sha256'][:16]+p.suffix.lower() for a,p in zip(audio_assets,audio_refs)]
        contract = dict(name=name, prompt=prompt, references=assets, **params,
                        steps=8 if new_profile else 4, head_chunks=4, ffn_chunks=8, int8=True)
        # Preserve old match fingerprints for safe resume; max is explicitly fingerprinted.
        if ref_image_size != 'match':
            contract['ref_image_size'] = ref_image_size
        if new_profile:
            contract.update(profile=profile, sampler='euler', scheduler='simple',
                            shift_video=12.0, shift_audio=3.0, lora_strength=1.0,
                            diagnostic_frames='pre-encode PNG: 0,24,48,72,96,last')
        if profile in PREVIEW_PROFILES:
            contract.update(preview_settings(profile, params['width'], params['height']))
        if flex:
            contract.update(flex_settings(params['width'], params['height']), audio_references=audio_assets)
        if lab:
            contract.update(profile=profile,**lab_settings,scheduler='simple',audio_references=audio_assets,
                            raw_audio='FLAC from VAEDecodeAudio; no sample-rate override',guider='BasicGuider')
            if not refs:contract['reference_policy']='lab_optional_0_to_9'
        models = {f: json.loads((ROOT / 'docs' / f).read_text(encoding='utf-8')) for f in
                  ['models-manifest.json', 'reference-models-manifest.json', 'int8-reference-manifest.json']}
        contract['model_manifests'] = models
        if new_profile or lab:
            models['h3-768p-models-manifest.json'] = json.loads((ROOT / 'docs/h3-768p-models-manifest.json').read_text(encoding='utf-8'))
        if profile == 'ref2v-pdd-8step':
            models['h3-pdd-models-manifest.json'] = json.loads((ROOT / 'docs/h3-pdd-models-manifest.json').read_text(encoding='utf-8'))
        if flex:
            models['h3-flex-models-manifest.json'] = json.loads((ROOT / 'docs/h3-flex-models-manifest.json').read_text(encoding='utf-8'))
        digest = hashlib.sha256(json.dumps(contract, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        args = SimpleNamespace(**params, prompt_file=str(prompt_file), references=refs, comfy_references=stored,
            ref_image_size=ref_image_size,
            image=None, steps=8 if new_profile else 4, profile=profile, base=False, int8=True, head_chunks=4, ffn_chunks=8,
            memory_efficient_sage=True, crop_720p=False, crop_1080p=False,
            name=f'h3_{name}_{digest[:12]}')
        if lab:
            args.base=not lab_settings['turbo'];args.lab_settings=lab_settings
        if lab or flex:
            args.comfy_audio_references=audio_stored
        plans.append(dict(name=name, fingerprint=digest, inputs=contract, workflow=graph(args),
                          copies=list(zip([str(p) for p in refs], stored))+list(zip([a['path'] for a in audio_assets],audio_stored))))
    return plans


def check_server(workflow, url):
    """Read-only runtime check before charging a submission reservation."""
    info = request(url, '/object_info')
    missing = sorted({n['class_type'] for n in workflow.values()} - set(info))
    if missing:
        raise ValueError('ComfyUI missing required nodes: ' + ', '.join(missing)
                         + '. Start the documented CUDA13 / SageAttention / KJNodes profile.')
    errors = []
    for node in workflow.values():
        schema = info[node['class_type']].get('input', {})
        fields = {**schema.get('required', {}), **schema.get('optional', {})}
        for key, value in node['inputs'].items():
            spec = fields.get(key)
            if isinstance(value, str) and spec and isinstance(spec[0], list) and value not in spec[0]:
                errors.append(f'{node["class_type"]}.{key}: {value}')
    if errors:
        raise ValueError('ComfyUI unavailable model/option: ' + '; '.join(errors))
    return dict(status='ready', node_types=sorted({n['class_type'] for n in workflow.values()}))


def execute(plans, run_dir, url, timeout, campaign):
    folder = Path(run_dir).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    # Exclusive OS file creation prevents two local launchers submitting the same batch.
    # A killed client can leave a lock; inspect its PID before manually removing it.
    import os
    budget = Budget(ROOT / 'runs/h3-budgets' / campaign)
    budget.folder.mkdir(parents=True, exist_ok=True)
    budget.check()
    lock = budget.folder / '.client.lock'
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise RuntimeError(f'Client lock exists; inspect PID and queue before removing: {lock}')
    with os.fdopen(fd, 'w') as stream:
        stream.write(str(os.getpid()))
    try:
        for plan in plans:
            shot_dir = folder / plan['name']
            contract_file = shot_dir / 'inputs.json'
            if contract_file.exists():
                previous = json.loads(contract_file.read_text(encoding='utf-8'))
                if previous != plan['inputs']:
                    raise ValueError(f'Changed inputs: use a NEW run directory for {plan["name"]}')
            queue = request(url, '/queue')
            active = {x[1] for x in queue['queue_running'] + queue['queue_pending']}
            job_file = shot_dir / 'job.json'
            attempt_key = str(shot_dir)
            own = json.loads(job_file.read_text(encoding='utf-8')).get('prompt_id') if job_file.exists() else None
            if active - {own}:
                raise RuntimeError('Other queued/running jobs exist. Leave server intact; resume this batch after they finish.')
            for source, target in plan['copies']:
                # Check again immediately before copying, so preflight is not stale.
                expected = next(a['sha256'] for a in plan['inputs']['references']+plan['inputs'].get('audio_references',[]) if a['path'] == source)
                if sha256(source) != expected:
                    raise ValueError(f'Reference changed since preflight: {source}')
                destination = ROOT / 'ComfyUI/input' / target
                destination.parent.mkdir(parents=True, exist_ok=True)
                if not destination.exists() or sha256(destination) != expected:
                    shutil.copy2(source, destination)
            save_json(contract_file, plan['inputs'])
            if not job_file.exists():
                save_json(shot_dir / 'server-preflight.json', check_server(plan['workflow'], url))
                budget.reserve(plan['name'], attempt_key)
            try:
                result = run_job(plan['workflow'], shot_dir, url, timeout=timeout)
            except Exception as exc:
                state = json.loads(job_file.read_text(encoding='utf-8')) if job_file.exists() else {}
                if not state and isinstance(exc, ComfyHTTPError) and exc.submission_rejected:
                    budget.rejected(attempt_key)
                elif isinstance(exc, TimeoutError):
                    budget.halt(f'Client wait budget exhausted; server job {state.get("prompt_id")} may still run. '
                                'Do not cancel or resubmit. User-directed reconciliation is required.')
                elif state.get('status') == 'error':
                    budget.finish(plan['name'], attempt_key, False)
                elif state.get('status') == 'running':
                    budget.halt(f'Cannot reconcile in-flight job {state.get("prompt_id")}: {exc}. Do not resubmit.')
                elif not state:
                    budget.halt(f'Submission outcome is unknown: {exc}. Reconcile /queue and /history; no automatic retry.')
                raise
            budget.finish(plan['name'], attempt_key, True)
            videos = [f for f in result['files'] if Path(f['path']).suffix.lower() == '.mp4']
            if len(videos) != 1:
                raise RuntimeError(f'Expected one recorded MP4 in {job_file}, got {len(videos)}')
            # Decode evidence stays separate from human acceptance.
            import subprocess
            import sys
            inspection = subprocess.run([sys.executable, str(ROOT / 'scripts/inspect_video.py'), videos[0]['path']],
                capture_output=True, text=True, encoding='utf-8', check=True)
            save_json(shot_dir / 'result.json', dict(execution_status='success', visual_status='pending',
                fingerprint=plan['fingerprint'], prompt_id=result['prompt_id'], video=videos[0],
                inspection=json.loads(inspection.stdout)))
            print(json.dumps(dict(shot=plan['name'], video=videos[0]['path'], visual_status='pending'), ensure_ascii=False), flush=True)
    finally:
        lock.unlink(missing_ok=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--spec', type=Path, required=True)
    p.add_argument('--run-dir', type=Path, required=True)
    p.add_argument('--only', help='Exact comma-separated names from spec, e.g. ep03_s04,ep03_s05')
    p.add_argument('--allow-reference-override', action='store_true')
    p.add_argument('--execute', action='store_true')
    p.add_argument('--url', default='http://127.0.0.1:8188')
    p.add_argument('--timeout', type=int, default=900)
    p.add_argument('--campaign', help='Stable user-approved production batch ID; shared across run directories')
    args = p.parse_args()
    if args.timeout < 1:
        p.error('--timeout must be positive')
    plans = prepare(args.spec, args.only.split(',') if args.only else None, args.allow_reference_override)
    if not args.execute:
        print(json.dumps(dict(mode='offline-preflight', shots=[dict(name=x['name'], fingerprint=x['fingerprint'],
            references=len(x['copies']), frames=x['workflow']['5']['inputs']['length']) for x in plans]), indent=2))
        return
    if not args.campaign or not re.fullmatch(r'[A-Za-z0-9_-]+', args.campaign):
        p.error('--execute requires a stable ASCII --campaign ID')
    execute(plans, args.run_dir, args.url, args.timeout, args.campaign)


if __name__ == '__main__':
    try:
        main()
    except BudgetStop as exc:
        print(json.dumps(dict(status='STOP', exit_code=20, reason=str(exc), action='END_GOAL_LOOP'), ensure_ascii=False), flush=True)
        raise SystemExit(20)
    except TimeoutError as exc:
        print(json.dumps(dict(status='PENDING', exit_code=10, reason=str(exc), action='END_TURN_RESUME_SAME_JOB_ONLY'), ensure_ascii=False), flush=True)
        raise SystemExit(10)
    except Exception as exc:
        print(json.dumps(dict(status='ERROR', exit_code=1, reason=str(exc), action='CLASSIFY_BEFORE_RETRY'), ensure_ascii=False), flush=True)
        raise SystemExit(1)
