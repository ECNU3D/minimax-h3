"""Submit a local MiniMax H3 job; save its request, result and timing."""
import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import uuid

import psutil

ROOT = pathlib.Path(__file__).resolve().parents[1]
NATIVE_LANDSCAPE = (1344, 768)
NATIVE_PORTRAIT = (768, 1344)
DEFAULT_PROMPT = """integrated_multimodal_description: A single continuous cinematic close-up of a small orange paper boat floating slowly from left to right on a calm garden pond. Gentle ripples spread around the boat. Soft morning sunlight, green leaves reflected in the water. The camera stays still. Realistic water, clear coherent motion, no cuts, no text.
overall_soundscape: Gentle rippling water and a few quiet birds chirping in the garden.
non_diegetic_music: None."""

class ComfyHTTPError(RuntimeError):
    def __init__(self, status, body):
        self.status, self.body = status, body
        try:
            self.payload = json.loads(body)
        except (ValueError, TypeError):
            self.payload = {}
        # ComfyUI's validation branch returns this envelope before queue.put().
        self.submission_rejected = (status == 400 and isinstance(self.payload, dict)
            and isinstance(self.payload.get('error'), dict) and 'node_errors' in self.payload
            and 'prompt_id' not in self.payload)
        super().__init__(f'ComfyUI HTTP {status}: {body}')


def request(base, route, data=None):
    payload = None if data is None else json.dumps(data).encode("utf-8")
    req = urllib.request.Request(base + route, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            body = response.read()
            return json.loads(body) if body.strip() else {}
    except urllib.error.HTTPError as exc:
        raise ComfyHTTPError(exc.code, exc.read().decode("utf-8", errors="replace")) from exc

def graph(args):
    if __package__:
        from .h3_preview_config import PROFILES as PREVIEW_PROFILES, SPARSE_INPUTS
    else:
        from h3_preview_config import PROFILES as PREVIEW_PROFILES, SPARSE_INPUTS
    if __package__:
        from .h3_flex_config import PROFILE as FLEX_PROFILE, LORA as FLEX_LORA, SIGMAS as FLEX_SIGMAS
    else:
        from h3_flex_config import PROFILE as FLEX_PROFILE, LORA as FLEX_LORA, SIGMAS as FLEX_SIGMAS
    flex = getattr(args, 'profile', None) == FLEX_PROFILE
    if flex and (not args.references or args.base or (args.width, args.height) != (1344, 768)):
        raise ValueError('Pika Flex requires image references, its adapter and native 1344x768')
    preview = getattr(args, 'profile', None) in PREVIEW_PROFILES
    if preview and (not args.references or (args.width, args.height) != (960, 544) or args.base):
        raise ValueError('Preview profiles require references, Turbo and 960x544')
    lab = getattr(args, 'profile', None) == 'ref2v-lab'
    profile_pdd = getattr(args, 'profile', None) == 'ref2v-pdd-8step'
    profile_768p = getattr(args, 'profile', None) in ('ref2v-768p-8step', 'ref2v-pdd-8step')
    dimensions_768p = (NATIVE_LANDSCAPE,) if profile_pdd else (NATIVE_LANDSCAPE, NATIVE_PORTRAIT)
    if profile_768p and (not args.references or (args.width, args.height) not in dimensions_768p or args.base):
        sizes = ' or '.join(f'{width}x{height}' for width, height in dimensions_768p)
        raise ValueError(f'{args.profile} requires references, Turbo and native {sizes}')
    prompt = pathlib.Path(args.prompt_file).read_text(encoding="utf-8-sig") if args.prompt_file else DEFAULT_PROMPT
    frames = max(5, round(args.seconds * 24))
    frames += (5 - frames % 17) % 17
    nodes = {}
    def node(key, kind, **inputs):
        nodes[str(key)] = {"class_type": kind, "inputs": inputs}
    reference_mode = bool(args.references) or lab
    ref_image_size = getattr(args, 'ref_image_size', 'match')
    if ref_image_size not in ('match', 'max'):
        raise ValueError('ref_image_size must be match or max')
    unet = "minimax_h3_ref2va_pruned_fp8_scaled.safetensors" if reference_mode else "minimax_h3_fl2va_pruned_fp8_scaled.safetensors"
    if args.int8:
        unet = unet.replace("fp8_scaled", "int8_convrot")
    node(1, "UNETLoader", unet_name=unet, weight_dtype="default")
    node(2, "CLIPLoader", clip_name="qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", type="minimax", device="default")
    node(3, "VAELoader", vae_name="minimax_h3_video_vae_fp16.safetensors")
    node(4, "VAELoader", vae_name="minimax_h3_audio_vae_fp32.safetensors")
    node(5, "MiniMaxH3ImageToVideo", clip=["2", 0], vae=["3", 0], prompt=prompt, width=args.width, height=args.height, length=frames)
    if reference_mode:
        node(5, "MiniMaxH3ReferenceToVideo", clip=["2", 0], vae=["3", 0], audio_vae=["4", 0], prompt=prompt,
             width=args.width, height=args.height, length=frames, ref_image_size=ref_image_size)
        for index, filename in enumerate(args.comfy_references):
            key = 20 + index
            node(key, "LoadImage", image=filename)
            nodes["5"]["inputs"][f"ref_images.ref_image_{index}"] = [str(key), 0]
        if lab or flex:
            for index, filename in enumerate(args.comfy_audio_references):
                key = 40 + index
                node(key, 'LoadAudio', audio=filename)
                nodes['5']['inputs'][f'ref_audios.ref_audio_{index}'] = [str(key), 0]
    if args.image:
        node(17, "LoadImage", image=args.comfy_image)
        node(18, "ResizeAndPadImage", image=["17", 0], target_width=args.width, target_height=args.height, padding_color="white", interpolation="lanczos")
        nodes["5"]["inputs"]["first_frame"] = ["18", 0]
    model = ["1", 0]
    if not args.base:
        lora = "minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors" if reference_mode else "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors"
        if profile_768p or lab:
            lora = 'minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors'
        if profile_pdd:
            lora = 'MiniMax-H3-Ref2VA-Acc-8Step_pruned_comfy.safetensors'
        if flex:
            lora = FLEX_LORA
        node(6, "LoraLoaderModelOnly", model=model, lora_name=lora, strength_model=args.lab_settings['lora_strength'] if lab else 1.0)
        model = ["6", 0]
    if profile_768p or lab or preview or flex:
        node(33, 'MiniMaxH3SigmaShift', model=model, shift_video=args.lab_settings['shift_video'] if lab else 12.0, shift_audio=args.lab_settings['shift_audio'] if lab else 3.0)
        model = ['33', 0]
    if args.memory_efficient_sage:
        node(32, "MiniMaxH3MemoryEfficientSageAttentionPatch", model=model)
        model = ["32", 0]
    if args.head_chunks:
        node(30, "MiniMaxLowVRAMAttention", model=model, head_chunks=args.head_chunks)
        model = ["30", 0]
    if args.ffn_chunks:
        node(31, "MiniMaxChunkFeedForward", model=model, chunks=args.ffn_chunks, seq_threshold=4096)
        model = ["31", 0]
    if getattr(args, 'profile', None) == 'ref2v-preview-sol-4step':
        node(34, 'BlockSparseAttention', model=model, **SPARSE_INPUTS)
        model = ['34', 0]
    node(7, "BasicGuider", model=model, conditioning=["5", 0])
    node(8, "RandomNoise", noise_seed=args.seed)
    node(9, "KSamplerSelect", sampler_name="euler" if profile_768p or preview else "res_multistep")
    node(10, "BasicScheduler", model=model, scheduler="simple", steps=8 if profile_768p else (args.steps or (20 if args.base else (4 if reference_mode else 8))), denoise=1.0)
    if flex:
        nodes['9']['inputs']['sampler_name'] = 'lcm'
        node(10, 'ManualSigmas', sigmas=FLEX_SIGMAS)
    if lab:
        nodes['9']['inputs']['sampler_name']=args.lab_settings['sampler']
        nodes['10']['inputs'].update(steps=args.lab_settings['steps'],denoise=args.lab_settings['denoise'])
    node(11, "SamplerCustomAdvanced", noise=["8", 0], guider=["7", 0], sampler=["9", 0], sigmas=["10", 0], latent_image=["5", 1])
    node(12, "VAEDecode", samples=["11", 0], vae=["3", 0])
    node(13, "VAEDecodeAudio", samples=["11", 0], vae=["4", 0])
    if lab or flex:
        node(19, 'SaveAudioAdvanced', audio=['13',0], filename_prefix=f'audio/{args.name}', format='flac')
    images = ["12", 0]
    if args.crop_720p:
        node(16, "ImageCrop", image=images, width=1280, height=720, x=0, y=8)
        images = ["16", 0]
    elif args.crop_1080p:
        node(16, "ImageCrop", image=images, width=1920, height=1080, x=0, y=4)
        images = ["16", 0]
    node(14, "CreateVideo", images=images, audio=["13", 0], fps=24.0)
    node(15, "SaveVideo", video=["14", 0], filename_prefix=f"video/{args.name}", format="mp4", codec="h264")
    if profile_768p or lab or preview or flex:
        # These are the actual pre-encode VAE images, not frames extracted from MP4.
        for index, frame in enumerate(sorted(set([0, 24, 48, 72, 96, frames - 1]))):
            if frame >= frames:
                continue
            key = 100 + index * 2
            node(key, 'ImageFromBatch', image=['12', 0], batch_index=frame, length=1)
            node(key + 1, 'SaveImage', images=[str(key), 0], filename_prefix=f'diagnostics/{args.name}/frame_{frame:04}')
    return nodes

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8188")
    parser.add_argument("--prompt-file")
    parser.add_argument("--image", help="Local first-frame image; copied into this installation's ComfyUI input directory")
    parser.add_argument("--references", nargs="+", help="One to nine ordered reference images for Ref2VA, tagged <Picture 1> etc.; not first/last frames")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=384)
    parser.add_argument("--crop-720p", action="store_true", help="Crop 1280x736 generation to exact 1280x720 before encoding")
    parser.add_argument("--crop-1080p", action="store_true", help="Crop 1920x1088 generation to exact 1920x1080 before encoding")
    parser.add_argument("--seconds", type=float, default=5)
    parser.add_argument("--seed", type=int, default=20260910)
    parser.add_argument("--steps", type=int)
    parser.add_argument("--base", action="store_true", help="Use base weights without Turbo LoRA, default 20 steps")
    parser.add_argument("--int8", action="store_true", help="Use the separately downloaded CUDA 13 INT8 ConvRot diffusion model")
    parser.add_argument("--memory-efficient-sage", action="store_true", help="Use the KJNodes H3-specific memory-efficient SageAttention patch")
    parser.add_argument("--head-chunks", type=int, choices=range(1, 57), default=0, help="Enable KJNodes H3 low-VRAM attention with this many head groups")
    parser.add_argument("--ffn-chunks", type=int, choices=range(1, 65), default=0, help="Enable KJNodes H3 token-wise feedforward chunks")
    parser.add_argument("--name", default="h3_smoke")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.references and (args.image or len(args.references) > 9):
        parser.error("Use either --image or one to nine --references")
    if args.width % 32 or args.height % 32:
        parser.error("Width and height must be multiples of 32")
    if args.crop_720p and (args.width, args.height) != (1280, 736):
        parser.error("--crop-720p requires --width 1280 --height 736")
    if args.crop_1080p and ((args.width, args.height) != (1920, 1088) or args.crop_720p):
        parser.error("--crop-1080p requires --width 1920 --height 1088 and cannot be combined with --crop-720p")
    if not args.name.replace("_", "").replace("-", "").isalnum():
        parser.error("Name must contain only letters, numbers, underscores and hyphens")
    def copy_image(filename):
        source = pathlib.Path(filename).resolve()
        if not source.is_file():
            parser.error(f"Image does not exist: {source}")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()[:12]
        stored_name = f"h3_reference_{digest}{source.suffix.lower()}"
        target = ROOT / "ComfyUI" / "input" / stored_name
        target.parent.mkdir(parents=True, exist_ok=True)
        if source != target.resolve():
            shutil.copy2(source, target)
        return stored_name
    if args.image:
        args.comfy_image = copy_image(args.image)
    if args.references:
        args.comfy_references = [copy_image(filename) for filename in args.references]
    workflow = graph(args)
    path = ROOT / "workflows" / f"{args.name}_api.json"
    path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Workflow: {path}", flush=True)
    if args.dry_run:
        return
    started = time.time()
    submitted = request(args.url, "/prompt", {"prompt": workflow, "client_id": str(uuid.uuid4())})
    prompt_id = submitted["prompt_id"]
    record = {"prompt_id": prompt_id, "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "settings": vars(args)}
    result_path = ROOT / "logs" / f"{args.name}_{prompt_id}.json"
    result_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(f"Submitted {prompt_id}", flush=True)
    last_notice = 0
    resource_path = result_path.with_suffix(".resources.jsonl")
    resource_samples = []
    while True:
        sample = {"elapsed_seconds": round(time.time() - started, 2), "ram_available_bytes": psutil.virtual_memory().available,
                  "system_ram_used_bytes": psutil.virtual_memory().used, "swap_used_bytes": psutil.swap_memory().used}
        gpu = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,utilization.gpu,temperature.gpu,power.draw", "--format=csv,noheader,nounits"], capture_output=True, text=True)
        if gpu.returncode == 0:
            values = gpu.stdout.strip().splitlines()[0].split(",")
            sample.update(dict(zip(("gpu_memory_used_mib", "gpu_util_percent", "gpu_temperature_c", "gpu_power_w"), (float(value.strip()) for value in values))))
        resource_samples.append(sample)
        with resource_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(sample) + "\n")
        history = request(args.url, "/history/" + prompt_id)
        if prompt_id in history:
            result = history[prompt_id]
            record.update(elapsed_seconds=round(time.time() - started, 2), history=result)
            record["resource_summary"] = {
                "sampling_note": "Approximately 5-second samples; whole-GPU memory includes desktop and other processes, not a precise allocation peak.",
                "sample_count": len(resource_samples),
                "min_ram_available_gib": round(min(x["ram_available_bytes"] for x in resource_samples) / 2**30, 3),
                "max_gpu_memory_used_mib": max((x.get("gpu_memory_used_mib", 0) for x in resource_samples)),
                "max_gpu_temperature_c": max((x.get("gpu_temperature_c", 0) for x in resource_samples)),
            }
            result_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({"status": result.get("status", {}).get("status_str"), "elapsed_seconds": record["elapsed_seconds"],
                              "outputs": result.get("outputs"), "resources": record["resource_summary"],
                              "details": str(result_path)}, ensure_ascii=False, indent=2), flush=True)
            if result.get("status", {}).get("status_str") != "success":
                raise SystemExit("Generation failed; inspect saved result and logs/comfy.stderr.log")
            return
        elapsed = time.time() - started
        if elapsed - last_notice >= 60:
            print(f"Running, elapsed {elapsed:.0f}s. Progress: logs/comfy.stderr.log", flush=True)
            last_notice = elapsed
        time.sleep(5)

if __name__ == "__main__":
    main()
