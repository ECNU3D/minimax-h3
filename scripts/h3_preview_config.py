"""Explicit, fixed 544p preview recipes; production defaults remain independent."""

PROFILES = ('ref2v-preview-4step', 'ref2v-preview-sol-4step')
SPARSE_INPUTS = dict(selection='sol-attn', **{'selection.tau': 1.3},
                     start_percent=0.2, end_percent=1.0, dense_blocks='',
                     min_tokens=12288, extra_tokens=256,
                     sink_conditioning='exact_kv_and_rows', verbose=True)


def settings(profile, width, height):
    if profile not in PROFILES or (width, height) != (960, 544):
        raise ValueError('Quick preview requires an explicit preview profile and 960x544')
    return dict(profile=profile, purpose='prompt_preview_not_final_quality',
                sampler='euler', scheduler='simple', steps=4,
                shift_video=12.0, shift_audio=3.0, lora_strength=1.0,
                lora='minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors',
                reference_resize='match',
                sparse_attention=dict(SPARSE_INPUTS) if profile == PROFILES[1] else None,
                diagnostic_frames='pre-encode PNG: 0,24,48,72,96,last')
