"""Build a single-person Krea2 outfit/reference editor using the installed schema."""
import hashlib
import json
import pathlib
import shutil
import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'workflows/krea2-reference'
NAME = 'krea2_reference_outfit_slider'
PROMPT = ('Change her navy T-shirt to a fully opaque burgundy long-sleeve crew-neck knit sweater. '
          'Keep the same person, facial features, hairstyle, pose, beige trousers, background and lighting. '
          'Natural clothing catalog photograph.')


def build():
    schema = requests.get('http://127.0.0.1:8188/object_info', timeout=20).json()
    api, layout = {}, {}

    def add(i, kind, title, pos, size, **params):
        api[str(i)] = dict(class_type=kind, inputs=params, _meta=dict(title=title))
        layout[i] = (pos, size)

    add(1, 'UNETLoader', '模型 | Krea 2 RAW FP8', [20, 20], [350, 90], unet_name='krea2_raw_fp8_scaled.safetensors', weight_dtype='default')
    add(2, 'CLIPLoader', '模型 | Qwen3-VL FP8', [20, 150], [350, 115], clip_name='qwen3vl_4b_fp8_scaled.safetensors', type='krea2', device='default')
    add(3, 'VAELoader', '模型 | VAE', [20, 305], [350, 70], vae_name='qwen_image_vae.safetensors')
    add(4, 'LoraLoaderModelOnly', '加速 | Turbo 1.0', [410, 20], [370, 110], model=['1', 0], lora_name='krea2_turbo_lora_rank_64_bf16.safetensors', strength_model=1.0)
    add(15, 'LoraLoaderModelOnly', '人物编辑 | Identity Edit r64 / 1.0', [410, 180], [370, 110], model=['4', 0], lora_name='krea2_identity_edit_v1_2_r64.safetensors', strength_model=1.0)
    add(5, 'LoraLoaderModelOnly', '③ 丰满度 | 0=关闭；先试 -1 / 0 / +1', [410, 340], [370, 115], model=['15', 0], lora_name='breast_size_v2_krea2_loraholic.safetensors', strength_model=0.0)
    add(13, 'LoadImage', '① 上传人物参考图', [20, 470], [350, 530], image='krea2_reference_person.png')
    add(14, 'VAEEncode', '参考图编码', [410, 850], [300, 70], pixels=['13', 0], vae=['3', 0])
    add(6, 'Krea2EditGroundedEncode', '② 换装指令 | 写想改变的内容', [830, 20], [440, 310], clip=['2', 0], prompt=PROMPT, image=['13', 0], grounding_px=768, system_prompt='')
    add(7, 'Krea2EditGroundedEncode', '负向 | 保持空白', [830, 385], [440, 225], clip=['2', 0], prompt='', image=['13', 0], grounding_px=768, system_prompt='')
    add(8, 'EmptySD3LatentImage', '分辨率 | 768×1024 / 单张', [410, 530], [370, 120], width=768, height=1024, batch_size=1)
    add(16, 'Krea2EditModelPatch', '④ 参考保持 | ref_boost 默认 4', [830, 675], [440, 295], model=['5', 0], source_latent=['14', 0], ref_boost=4.0, ref_boost_a=1.0, fit_mode='fit', vae=['3', 0], source_image=['13', 0], target_latent=['8', 0])
    add(9, 'KSampler', '⑤ 生成 | 固定 seed 便于比较', [1320, 20], [350, 340], model=['16', 0], positive=['6', 0], negative=['7', 0], latent_image=['8', 0], seed=20260921, steps=10, cfg=1.0, sampler_name='euler', scheduler='simple', denoise=1.0)
    add(10, 'VAEDecode', '解码', [1320, 420], [350, 70], samples=['9', 0], vae=['3', 0])
    add(11, 'SaveImage', '结果 | 保存到 krea2-reference', [1720, 20], [520, 700], images=['10', 0], filename_prefix='krea2-reference/outfit')
    note = ('①上传人物图 → ②写换装指令 → 运行。默认 slider=0。\n'
            'ref_boost=4，grounding_px=768，10 步，CFG=1，denoise=1。\n'
            '实测：参考模式换装有效，但 slider 0/+2 的丰满度变化很弱。\n'
            '若需体型微调，把换装结果交给 krea2_local_clothed_adjust。\n'
            '脸部相似度不是绝对锁定，请检查结果。来源与实测见 README.md。')
    export_graph(api, layout, NAME, note, schema)
    origin = ROOT / 'ComfyUI/custom_nodes/comfyui-krea2edit/workflows/krea2_identity_edit.json'
    shutil.copy2(origin, BUNDLE / 'sources/author-workflow.json')
    (BUNDLE / 'sources/workflow-provenance.json').write_text(json.dumps({
        'source': 'https://github.com/lbouaraba/comfyui-krea2edit/blob/86f886dac23013d88996e3a2e99093ba44d322fb/workflows/krea2_identity_edit.json',
        'sha256': hashlib.sha256(origin.read_bytes()).hexdigest(),
        'adaptations': ['single reference', 'RAW FP8 + existing Turbo adapter', 'r64 identity adapter',
                        'optional body slider default off', '768x1024', 'core resolution node', 'schema-checked wiring'],
    }, indent=2), encoding='utf-8')


def export_graph(api, layout, workflow_name, note, schema):
    nodes, links = [], []
    widget_types = {'STRING', 'INT', 'FLOAT', 'BOOLEAN', 'COMBO'}
    for key, entry in api.items():
        i, kind, params = int(key), entry['class_type'], entry['inputs']
        info = schema[kind]
        sockets, widgets = [], []
        for section in ('required', 'optional'):
            for name, spec in info['input'].get(section, {}).items():
                typ, opts = spec[0], spec[1] if len(spec) > 1 else {}
                is_widget = isinstance(typ, list) or typ in widget_types
                if is_widget:
                    default = opts.get('default', typ[0] if isinstance(typ, list) else opts.get('options', [''])[0] if typ == 'COMBO' else '' if typ == 'STRING' else 0)
                    widgets.append(params.get(name, default))
                    if opts.get('control_after_generate') or (kind == 'KSampler' and name == 'seed'):
                        widgets.append('fixed')
                else:
                    sockets.append(dict(name=name, type=typ, link=None))
        if kind == 'LoadImage':
            widgets.append('image')
        pos, size = layout[i]
        nodes.append(dict(id=i, type=kind, title=entry['_meta']['title'], pos=pos, size=size,
                          flags={}, order=len(nodes), mode=0, inputs=sockets,
                          outputs=[dict(name=n, type=t, links=[]) for n, t in zip(info['output_name'], info['output'])],
                          properties={'Node name for S&R': kind}, widgets_values=widgets))
    by_id = {str(n['id']): n for n in nodes}
    for key, entry in api.items():
        for name, value in entry['inputs'].items():
            if not isinstance(value, list):
                continue
            src, out = value
            target = by_id[key]
            slot = next(j for j, x in enumerate(target['inputs']) if x['name'] == name)
            lid = len(links) + 1
            links.append([lid, int(src), out, int(key), slot, by_id[src]['outputs'][out]['type']])
            by_id[src]['outputs'][out]['links'].append(lid)
            target['inputs'][slot]['link'] = lid
    note_id = max(map(int, api)) + 1
    nodes.append(dict(id=note_id, type='Note', title='使用说明', pos=[1320, 800], size=[430, 280], flags={}, order=len(nodes), mode=0, inputs=[], outputs=[], properties={}, widgets_values=[note]))
    workflow = dict(last_node_id=note_id, last_link_id=len(links), nodes=nodes, links=links, groups=[], config={}, version=0.4,
                    extra={'ds': {'scale': 0.58, 'offset': [40, 50]}, 'frontendVersion': '1.51.10'})
    for target in (BUNDLE, ROOT / 'ComfyUI/user/default/workflows/Krea2-Study'):
        target.mkdir(parents=True, exist_ok=True)
        (target / f'{workflow_name}.json').write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding='utf-8')
    (BUNDLE / f'{workflow_name}.api.json').write_text(json.dumps(api, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Built', BUNDLE / f'{workflow_name}.json')


def build_local():
    schema = requests.get('http://127.0.0.1:8188/object_info', timeout=20).json()
    api = json.loads((ROOT / 'workflows/krea2-raw-slider/krea2_raw_slider_fast.api.json').read_text(encoding='utf-8'))
    api.pop('8')
    layout = {1: ([20,20],[350,90]), 2: ([20,150],[350,115]), 3: ([20,305],[350,70]),
              4: ([410,20],[370,110]), 5: ([410,180],[370,115]), 6: ([830,20],[440,230]),
              7: ([830,300],[440,100]), 9: ([1320,20],[350,340]), 10: ([1320,420],[350,70]),
              11: ([2150,20],[500,700])}
    prompt = ('Clothing catalog photograph of an adult woman wearing a fully opaque burgundy long-sleeve '
              'crew-neck knit sweater and beige trousers. Natural proportions, realistic knit fabric, '
              'neutral standing pose, soft studio daylight, plain gray background.')
    api['5']['inputs']['strength_model'] = 0.0
    api['5']['_meta']['title'] = '② 丰满度 | 0 基准；先试 -1 / 0 / +1'
    api['6']['inputs']['text'] = prompt
    api['6']['_meta']['title'] = '③ 描述要保留的衣服'
    api['9']['inputs'].update(steps=12, denoise=0.6, latent_image=['20',0])
    api['9']['_meta']['title'] = '④ 局部重绘 | denoise 0.6'
    api['11']['inputs'].update(images=['21',0], filename_prefix='krea2-reference/local-adjust')

    def add(i, kind, title, pos, size, **params):
        api[str(i)] = dict(class_type=kind, inputs=params, _meta=dict(title=title))
        layout[i] = (pos, size)

    add(13,'LoadImage','① 上传换装结果 | 脸部将保留原图',[20,470],[350,500],image='krea2_outfit_result.png')
    add(14,'VAEEncode','编码原图',[410,820],[330,70],pixels=['13',0],vae=['3',0])
    add(15,'SolidMask','遮罩底图 | 尺寸必须与原图一致',[410,350],[370,120],value=0.0,width=768,height=1024)
    add(16,'SolidMask','躯干区域大小 | 换图后调整',[410,520],[370,120],value=1.0,width=460,height=440)
    add(18,'FeatherMask','柔化区域边缘',[830,460],[370,140],mask=['16',0],left=40,top=40,right=40,bottom=40)
    add(19,'MaskComposite','躯干位置 | x/y 不应覆盖脸部',[830,660],[370,140],destination=['15',0],source=['18',0],x=150,y=325,operation='add')
    add(20,'SetLatentNoiseMask','只重绘遮罩区域',[1320,570],[350,70],samples=['14',0],mask=['19',0])
    add(21,'ImageCompositeMasked','保留遮罩以外原始像素',[1750,420],[350,180],destination=['13',0],source=['10',0],x=0,y=0,resize_source=False,mask=['19',0])
    add(22,'MaskToImage','遮罩预览转换',[20,1070],[350,60],mask=['19',0])
    add(23,'PreviewImage','白色=可编辑；黑色=保留',[410,1070],[360,470],images=['22',0])
    export_graph(api,layout,'krea2_local_clothed_adjust',
        '用于换装后的局部体型微调。默认 slider=0，先固定 seed 比较 -1/0/+1。\n'
        '示例遮罩只适合当前 768×1024 人像！上传其他图后必须改底图尺寸、区域大小和 x/y。\n'
        '检查遮罩预览：白色覆盖衣服躯干，黑色保留脸和背景。\n'
        '也可在上传图的遮罩编辑器涂抹衣服区域，把 MASK 输出接到重绘节点和最终合成节点。\n'
        '最后合成会保留遮罩以外像素；衣物纹理、轮廓和遮罩内背景可能变化。',schema)


if __name__ == '__main__':
    build()
    build_local()
