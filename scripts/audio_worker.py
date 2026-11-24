"""One isolated GPU stage: SFX, voice design, voice reuse, or instrumental BGM."""
import argparse
import json
import os
from pathlib import Path
import random
import sys
import time
import traceback

from audio_common import ROOT, Monitor, completed, save_audio, sha256, write_json

os.environ['TORCHDYNAMO_DISABLE'] = '1'
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', default=str(ROOT/'configs/audio-film-test.json'))
    p.add_argument('--run-dir', required=True, type=Path)
    p.add_argument('--stage', required=True, choices=['sfx','design','clone','music'])
    a = p.parse_args()
    config = json.loads(Path(a.config).read_text(encoding='utf-8'))
    cfg = config[a.stage]
    model_path = ROOT/cfg['model']
    if not (model_path/'snapshot-verified.json').exists():
        raise RuntimeError('Model download has not completed verification: '+str(model_path))
    folder = a.run_dir.resolve()/a.stage
    folder.mkdir(parents=True, exist_ok=True)
    snapshots = [json.loads((model_path/'snapshot-verified.json').read_text(encoding='utf-8'))]
    if a.stage == 'music':
        snapshots.append(json.loads((model_path/cfg['dit']/'snapshot-verified.json').read_text(encoding='utf-8')))
    pinned = [dict(repo=s['repo'], revision=s['revision'], files=[(f['source_path'],f['sha256']) for f in s['files']]) for s in snapshots]
    identities = {job['id']:dict(stage=a.stage, config=cfg, job=job, snapshots=pinned) for job in cfg['jobs']}
    if a.stage == 'clone':
        reference = a.run_dir.resolve()/'design'/(cfg['reference_id']+'.wav')
        for ident in identities.values():
            ident.update(reference_sha256=sha256(reference), reference_text=config['design']['text'])
    pending = [job for job in cfg['jobs'] if not completed(folder, job, identities[job['id']])]
    if not pending: print('STAGE_ALREADY_COMPLETE',a.stage); return
    import numpy as np
    import torch
    if not torch.cuda.is_available(): raise RuntimeError('CUDA unavailable')
    torch.set_num_threads(8)
    with Monitor() as monitor:
        started = time.perf_counter()
        try:
            if a.stage == 'sfx':
                sys.path.insert(0, str(ROOT/'audio/MOSS-TTS'))
                from moss_soundeffect_v2.pipeline_moss_soundeffect import MossSoundEffectPipeline
                model = MossSoundEffectPipeline.from_pretrained(str(model_path), device='cpu', torch_dtype=torch.bfloat16)
                model.engine.device = 'cuda'
                model.engine.enable_cpu_offload()
            elif a.stage in ['design','clone']:
                from qwen_tts import Qwen3TTSModel
                model = Qwen3TTSModel.from_pretrained(str(model_path), device_map='cuda:0', dtype=torch.bfloat16, attn_implementation='sdpa')
                if a.stage == 'clone':
                    voice_prompt = model.create_voice_clone_prompt(ref_audio=str(reference), ref_text=config['design']['text'], x_vector_only_mode=False)
            else:
                model, llm = load_music(model_path, cfg)
            load_seconds = time.perf_counter()-started
            for job in pending:
                random.seed(job['seed']); np.random.seed(job['seed']); torch.manual_seed(job['seed'])
                torch.cuda.manual_seed_all(job['seed']); torch.cuda.reset_peak_memory_stats()
                t0 = time.perf_counter()
                if a.stage == 'sfx':
                    audio = model(job['prompt'], seconds=job['seconds'], num_inference_steps=cfg['steps'], cfg_scale=cfg['cfg'], sigma_shift=cfg['sigma_shift'], seed=job['seed'])
                    wave, sr = audio[0].detach().float().cpu().numpy().T, model.sample_rate
                elif a.stage == 'design':
                    waves, sr = model.generate_voice_design(text=cfg['text'], language='Chinese', instruct=job['instruct'], max_new_tokens=1024)
                    wave = waves[0]
                elif a.stage == 'clone':
                    waves, sr = model.generate_voice_clone(text=job['text'], language='Chinese', voice_clone_prompt=voice_prompt, max_new_tokens=1024)
                    wave = waves[0]
                else:
                    wave, sr = generate_music(model, llm, cfg, job, folder)
                torch.cuda.synchronize()
                save_audio(folder, job, identities[job['id']], wave, sr, time.perf_counter()-t0,
                    dict(cuda_peak_allocated_bytes=torch.cuda.max_memory_allocated(), cuda_peak_reserved_bytes=torch.cuda.max_memory_reserved()))
            status = 'success'
        except Exception:
            status = 'failed'
            write_json(folder/'error.json', dict(traceback=traceback.format_exc(), time=time.time()))
            raise
        finally:
            write_json(folder/'stage.json', dict(status=locals().get('status','failed'),
                elapsed_seconds=time.perf_counter()-started, load_seconds=locals().get('load_seconds'),
                torch=torch.__version__, cuda=torch.version.cuda, gpu=torch.cuda.get_device_name(),
                samples=monitor.samples))

def load_music(model_path, cfg):
    """Load only the selected SFT and shared components; use the Windows PyTorch LM."""
    sys.path.insert(0, str(ROOT/'audio/ACE-Step-1.5'))
    os.environ['ACESTEP_CHECKPOINTS_DIR'] = str(model_path)
    import acestep.model_downloader as downloader
    # Upstream's default precheck also requires unused Turbo weights. The selected
    # SFT is checked separately by initialize_service; restrict this shared list.
    downloader.MAIN_MODEL_COMPONENTS = ['vae','Qwen3-Embedding-0.6B',cfg['lm']]
    from acestep.handler import AceStepHandler
    from acestep.llm_inference import LLMHandler
    model = AceStepHandler()
    message, success = model.initialize_service(project_root=str(ROOT/'audio/ACE-Step-1.5'),
        config_path=cfg['dit'], device='cuda', use_flash_attention=False, compile_model=False,
        offload_to_cpu=True, offload_dit_to_cpu=True, quantization=None, use_mlx_dit=False)
    if not success: raise RuntimeError(message)
    llm = LLMHandler()
    message, success = llm.initialize(checkpoint_dir=str(model_path), lm_model_path=cfg['lm'],
        backend='pt', device='cuda', offload_to_cpu=True)
    if not success: raise RuntimeError(message)
    return model, llm

def generate_music(model, llm, cfg, job, folder):
    import soundfile as sf
    from acestep.inference import GenerationParams, GenerationConfig, generate_music as generate
    params = GenerationParams(caption=job['caption'], lyrics='[Instrumental]', instrumental=True,
        bpm=job['bpm'], keyscale=job['keyscale'], duration=cfg['duration'],
        inference_steps=cfg['steps'], guidance_scale=cfg['cfg'], seed=job['seed'],
        thinking=True, use_cot_caption=False, use_cot_metas=False)
    gen_config = GenerationConfig(batch_size=1, use_random_seed=False, seeds=[job['seed']], audio_format='wav')
    result = generate(model, llm, params, gen_config, save_dir=str(folder/'raw'/job['id']))
    if not result.success: raise RuntimeError(str(result.error))
    write_json(folder/(job['id']+'.ace-result.json'), dict(status_message=result.status_message,
        audios=[{k:v for k,v in item.items() if k != 'tensor'} for item in result.audios]))
    return sf.read(result.audios[0]['path'], dtype='float32')

if __name__ == '__main__': main()
