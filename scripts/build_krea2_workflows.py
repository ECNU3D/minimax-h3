"""Adapt the installed official Krea template to two flat, core-only workflows."""
import copy
import hashlib
import json
import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'workflows/krea2-raw-slider'
SOURCE = ROOT / '.venv-cu130/Lib/site-packages/comfyui_workflow_templates_json/templates/image_krea2_turbo_t2i.json'
PROMPT = ('Studio fashion photograph of a 30-year-old adult woman, standing naturally, '
          'head to knees visible, wearing a fully opaque fitted navy blue crew-neck T-shirt '
          'and straight beige trousers. Relaxed arms at her sides. Neutral gray background, '
          'soft even daylight, realistic anatomy, natural skin texture, understated clothing catalog photography.')
SLIDER = 'breast_size_v2_krea2_loraholic.safetensors'


def build(fast):
    nodes, links, api = [], [], {}

    def node(i, kind, title, pos, size, inputs, outputs, widgets, params):
        nodes.append(dict(id=i, type=kind, title=title, pos=pos, size=size, flags={}, order=len(nodes), mode=0,
                          inputs=[dict(name=n, type=t, link=None) for n, t in inputs],
                          outputs=[dict(name=n, type=t, links=[]) for n, t in outputs],
                          properties={'Node name for S&R': kind, 'cnr_id': 'comfy-core', 'ver': '0.35.0'},
                          widgets_values=widgets))
        api[str(i)] = {'class_type': kind, 'inputs': params, '_meta': {'title': title}}

    def link(src, dst, name):
        a = next(n for n in nodes if n['id'] == src)
        b = next(n for n in nodes if n['id'] == dst)
        slot = next(i for i, p in enumerate(b['inputs']) if p['name'] == name)
        lid = len(links) + 1
        links.append([lid, src, 0, dst, slot, a['outputs'][0]['type']])
        a['outputs'][0]['links'].append(lid)
        b['inputs'][slot]['link'] = lid
        api[str(dst)]['inputs'][name] = [str(src), 0]

    node(1, 'UNETLoader', '01 | Krea 2 RAW FP8', [30, 70], [390, 90], [], [('MODEL', 'MODEL')],
         ['krea2_raw_fp8_scaled.safetensors', 'default'],
         dict(unet_name='krea2_raw_fp8_scaled.safetensors', weight_dtype='default'))
    node(2, 'CLIPLoader', '02 | Qwen3-VL 4B FP8', [30, 250], [390, 115], [], [('CLIP', 'CLIP')],
         ['qwen3vl_4b_fp8_scaled.safetensors', 'krea2', 'default'],
         dict(clip_name='qwen3vl_4b_fp8_scaled.safetensors', type='krea2', device='default'))
    node(3, 'VAELoader', '03 | Qwen Image VAE', [30, 450], [390, 70], [], [('VAE', 'VAE')],
         ['qwen_image_vae.safetensors'], dict(vae_name='qwen_image_vae.safetensors'))
    if fast:
        node(4, 'LoraLoaderModelOnly', '04 | Turbo adapter / strength 1.0', [470, 50], [400, 110],
             [('model', 'MODEL')], [('MODEL', 'MODEL')], ['krea2_turbo_lora_rank_64_bf16.safetensors', 1.0],
             dict(lora_name='krea2_turbo_lora_rank_64_bf16.safetensors', strength_model=1.0))
        link(1, 4, 'model')
    node(5, 'LoraLoaderModelOnly', '05 | Breast slider / 0 = off', [470, 230], [400, 110],
         [('model', 'MODEL')], [('MODEL', 'MODEL')], [SLIDER, 1.0],
         dict(lora_name=SLIDER, strength_model=1.0))
    link(4 if fast else 1, 5, 'model')
    node(6, 'CLIPTextEncode', '06 | Prompt', [470, 460], [430, 220],
         [('clip', 'CLIP')], [('CONDITIONING', 'CONDITIONING')], [PROMPT], dict(text=PROMPT))
    link(2, 6, 'clip')
    node(7, 'CLIPTextEncode', '07 | Negative prompt (empty baseline)', [470, 750], [430, 130],
         [('clip', 'CLIP')], [('CONDITIONING', 'CONDITIONING')], [''], dict(text=''))
    link(2, 7, 'clip')
    node(8, 'EmptyLatentImage', '08 | Resolution / batch 1', [30, 640], [390, 120], [], [('LATENT', 'LATENT')],
         [1024, 1024, 1], dict(width=1024, height=1024, batch_size=1))
    steps, cfg = (8, 1.0) if fast else (52, 4.5)
    node(9, 'KSampler', f'09 | {steps} steps / CFG {cfg}', [960, 80], [340, 320],
         [('model', 'MODEL'), ('positive', 'CONDITIONING'), ('negative', 'CONDITIONING'), ('latent_image', 'LATENT')],
         [('LATENT', 'LATENT')], [20260921, 'fixed', steps, cfg, 'euler', 'simple', 1.0],
         dict(seed=20260921, steps=steps, cfg=cfg, sampler_name='euler', scheduler='simple', denoise=1.0))
    for src, name in [(5, 'model'), (6, 'positive'), (7, 'negative'), (8, 'latent_image')]:
        link(src, 9, name)
    node(10, 'VAEDecode', '10 | Decode', [960, 510], [320, 70],
         [('samples', 'LATENT'), ('vae', 'VAE')], [('IMAGE', 'IMAGE')], [], {})
    link(9, 10, 'samples')
    link(3, 10, 'vae')
    name = 'krea2_raw_slider_fast' if fast else 'krea2_raw_slider_quality'
    node(11, 'SaveImage', '11 | Save image', [1370, 70], [520, 600], [('images', 'IMAGE')], [],
         ['krea2-study/' + name], dict(filename_prefix='krea2-study/' + name))
    link(10, 11, 'images')
    note = ('RTX 5080 16GB / 32GB RAM\n'
            'Change slider strength in node 05. Start with -1, 0, +1; keep seed fixed.\n'
            'Negative = smaller; positive = larger. A slider can also change pose/clothing.\n'
            'No trigger word is required by this slider.\n'
            + ('FAST: RAW + official rank-64 Turbo adapter. 8 steps / CFG 1.\n' if fast else
               'RAW: 52 steps / ComfyUI CFG 4.5. No Turbo adapter.\n'
               'Official code CFG 3.5 uses cond + 3.5*(cond-uncond); ComfyUI equivalent is 4.5.\n')
            + 'Uses the native ComfyUI Krea sampling shift 1.15; not a bit-exact official-code reproduction.\n'
            'Adapted from official image_krea2_turbo_t2i template; see sources/.')
    nodes.append(dict(id=12, type='Note', title='Read me / 学习说明', pos=[960, 690], size=[700, 250],
                      flags={}, order=len(nodes), mode=0, inputs=[], outputs=[], properties={}, widgets_values=[note]))
    workflow = dict(last_node_id=12, last_link_id=len(links), nodes=nodes, links=links, groups=[], config={},
                    extra={'ds': {'scale': 0.7, 'offset': [40, 30]}, 'frontendVersion': '1.51.10'}, version=0.4)
    for target in [BUNDLE, ROOT / 'ComfyUI/user/default/workflows/Krea2-Study']:
        target.mkdir(parents=True, exist_ok=True)
        (target / (name + '.json')).write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding='utf-8')
    (BUNDLE / (name + '.api.json')).write_text(json.dumps(api, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    (BUNDLE / 'sources').mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE, BUNDLE / 'sources/official_image_krea2_turbo_t2i.json')
    (BUNDLE / 'sources/template-provenance.json').write_text(json.dumps({
        'source': 'https://github.com/Comfy-Org/workflow_templates/blob/main/templates/image_krea2_turbo_t2i.json',
        'installed_package': 'comfyui-workflow-templates 0.11.57',
        'sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'adaptations': ['flat core nodes', 'RAW FP8 base', 'Loraholic Krea2 v2 slider',
                        'separate RAW / distilled presets', 'direct text entry', 'fixed seed'],
    }, indent=2), encoding='utf-8')
    build(False)
    build(True)
    print('Created editor workflows and API graphs for RAW and fast preview.')
