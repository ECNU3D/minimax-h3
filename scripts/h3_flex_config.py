"""Opt-in Pika Flex Ref2VA recipe, independent of every existing default."""
PROFILE = 'ref2v-flex-768p-6step'
LORA = 'pika_h3_flex_ref2va_v1_bf16.safetensors'
# Published Comfy schedule after H3's video shift. Audio shift stays 3.
SIGMAS = '1.0, 0.972973, 0.923077, 0.8, 0.571429, 0.333333, 0.0'


def settings(width, height):
    if (width, height) != (1344, 768):
        raise ValueError('Pika H3 Flex profile requires native 1344x768')
    return dict(profile=PROFILE, sampler='lcm', scheduler='ManualSigmas', sigmas=SIGMAS,
                steps=6, shift_video=12.0, shift_audio=3.0, lora=LORA,
                lora_strength=1.0, guider='BasicGuider',
                video_vae='minimax_h3_video_vae_fp16.safetensors',
                raw_audio='FLAC from VAEDecodeAudio; no sample-rate override',
                diagnostic_frames='pre-encode PNG: 0,24,48,72,96,last')
