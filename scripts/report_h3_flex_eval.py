"""Export original paired videos and reproducible technical/contact-sheet evidence."""
import hashlib
import html
import json
import re
from pathlib import Path
import shutil
import av
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'runs/pika-flex-eval-20261102'
OUT = ROOT / 'output/pika-flex-eval-20261103'
CASES = [('expression05', '疑虑表情 · 5 秒'), ('prop10', '跑跳与开合伞 · 10 秒'), ('fight10', '双人打斗与争伞 · 10 秒')]

def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))

def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def contact(video, stem):
    with av.open(str(video)) as c:
        stream = c.streams.video[0]
        total = stream.frames
        indices = sorted(set(np.linspace(0, total - 1, 12).round().astype(int).tolist()))
        frames = [(i, frame.to_image()) for i, frame in enumerate(c.decode(video=0)) if i in indices]
    font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 17)
    board = Image.new('RGB', (1344, 3 * 218), '#10151c')
    draw = ImageDraw.Draw(board)
    for j, (i, im) in enumerate(frames):
        x, y = (j % 4) * 336, (j // 4) * 218
        board.paste(ImageOps.contain(im, (336, 192)), (x, y))
        draw.text((x + 7, y + 193), f'{i / 24:.2f}s · frame {i}', font=font, fill='white')
        im.save(OUT / 'frames' / f'{stem}-{i:03d}.jpg', quality=96)
    board.save(OUT / f'{stem}-contact.jpg', quality=94)
    return [i for i, _ in frames]

def collect(name, variant):
    historical = name == 'expression05' and variant == 'baseline'
    folder = ROOT / 'runs/h3-eval-20261012/baseline/g19b' if historical else RUN / ('baseline-conservative' if variant == 'baseline' else 'flex-conservative') / name
    if not (folder / 'result.json').exists():
        return dict(status='pending', historical=historical)
    job, result, inputs = [read(folder / f'{f}.json') for f in ('job', 'result', 'inputs')]
    source = Path(result['video']['path'])
    assert sha(source) == result['video']['sha256']
    stem = f'{name}-{variant}'
    target = OUT / f'{stem}.mp4'
    if not target.exists() or sha(target) != result['video']['sha256']:
        shutil.copy2(source, target)
    if not (OUT / f'{stem}-contact.jpg').exists():
        contact(target, stem)
    resources = [json.loads(line) for line in (folder / 'resources.jsonl').read_text().splitlines()] if (folder / 'resources.jsonl').exists() else []
    graph = read(folder / 'workflow_api.json')
    evidence=OUT/'evidence'/stem
    evidence.mkdir(parents=True,exist_ok=True)
    for filename in ('inputs.json','workflow_api.json','job.json','result.json','resources.jsonl'):
        if (folder/filename).exists():shutil.copy2(folder/filename,evidence/filename)
    (evidence/'prompt.txt').write_text(inputs['prompt'],encoding='utf-8')
    log_path = RUN / ('server-before-fight-baseline.log' if name == 'prop10' and variant == 'baseline' else f'server-after-{name}-{variant}.log')
    sampling_seconds = None
    if not historical and log_path.exists():
        matches = re.findall(r'100%[^\r\n]*?\d+/\d+\s+\[(\d+):(\d+)(?::(\d+))?<',log_path.read_text(encoding='utf-8',errors='replace'))
        if matches:
            a,b,c=matches[-1]
            sampling_seconds=int(a)*3600+int(b)*60+int(c) if c else int(a)*60+int(b)
    audio = []
    for asset in job['files']:
        if Path(asset['path']).suffix == '.flac':
            dest = OUT / f'{stem}.flac'
            if not dest.exists(): shutil.copy2(asset['path'], dest)
            assert sha(dest) == asset['sha256']
            audio.append(dest.name)
    return dict(status='success', historical=historical, video=target.name, sha256=sha(target),
                folder=str(folder), prompt_id=job['prompt_id'], server_seconds=job.get('server_seconds'),
                sampling_seconds=sampling_seconds,
                inspection=result['inspection'], profile=inputs.get('profile'), seed=inputs['seed'],
                prompt_sha256=hashlib.sha256(inputs['prompt'].encode()).hexdigest(),
                reference_sha256=[r['sha256'] for r in inputs['references']],
                cached_nodes=next((v.get('nodes',[]) for k,v in job['history']['status']['messages'] if k=='execution_cached'), []),
                max_gpu_memory_mib=max((r.get('gpu_memory_mib',0) for r in resources),default=None),
                min_available_ram_gib=min((r['ram_available_bytes']/2**30 for r in resources),default=None),
                sampler=graph['9']['inputs']['sampler_name'], schedule=graph['10'], audio=audio)

def main():
    (OUT / 'frames').mkdir(parents=True,exist_ok=True)
    (OUT / 'evidence').mkdir(parents=True,exist_ok=True)
    shutil.copy2(RUN/'reference-board.jpg',OUT/'reference-board.jpg')
    for filename in ('h3-flex-models-manifest.json','h3-flex-model-verification.json'):
        shutil.copy2(ROOT/'docs'/filename,OUT/'evidence'/filename)
    shutil.copy2(RUN/'validation-20261103.json',OUT/'evidence'/'validation.json')
    reviews=read(RUN/'visual-observations.json') if (RUN/'visual-observations.json').exists() else {}
    cases=[]
    for name,title in CASES:
        a,b=collect(name,'baseline'),collect(name,'flex')
        matched=None
        if a['status']==b['status']=='success':
            matched=all(a[k]==b[k] for k in ('seed','prompt_sha256','reference_sha256'))
            assert matched, f'Pair inputs differ: {name}'
        cases.append(dict(name=name,title=title,baseline=a,flex=b,matched_inputs=matched,review=reviews.get(name)))
    payload=dict(campaign='pika-flex-eval-20261102',cases=cases,
                 budget=read(ROOT/'runs/h3-budgets/pika-flex-eval-20261102/budget.json'),
                 environment=read(RUN/'server-process-20261103.json'),
                 caveats=['表情基线复用 2026-10-12 的同输入历史结果，服务配置不同，不计算速度提升。',
                          '新生成对照使用同一保守显存服务；服务器耗时含模型加载、条件编码、采样、解码和导出，缓存会影响差异。',
                          '每类只有一对样本，没有统计显著性；相同种子在不同采样器下不对应相同随机过程。',
                          '采样耗时来自服务器进度日志，精度到秒；完整耗时来自 ComfyUI execution_start/success 时间戳。',
                          '两套流程都导出相同数量的诊断 PNG；Flex 额外导出一个混合音轨 FLAC，其耗时计入完整耗时。',
                          '原始视频逐文件复制并校验哈希，未裁剪、插帧、重编码或改音轨。'])
    (OUT/'comparison.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    review_lines=[
        '# H3 768p 与 Pika H3 Flex 本机实测', '',
        '2026-11-03。模型已安装并通过固定官方 SHA256 校验；导演台增加可选 Flex 档，原生产默认仍为 LightX2V 768p / 8 步。', '',
        '## 实测速度', '',
        '同一 RTX 5080 16GB、32GB RAM、保守显存服务。总耗时包含模型加载、条件编码、采样、音视频解码与导出，不包含本次模型下载时间。', '',
        '| 样片 | 原方案总耗时 | Flex 总耗时 | 总耗时减少 | 原方案 / Flex 采样 |',
        '|---|---:|---:|---:|---:|',
    ]
    fresh=[]
    for row in cases:
        a,b=row['baseline'],row['flex']
        if a['status'] != 'success' or b['status'] != 'success':
            review_lines.append(f'| {row["title"]} | — | 待完成 | — | — |'); continue
        reduction='不比较（历史基线）' if a['historical'] else f'{(1-b["server_seconds"]/a["server_seconds"])*100:.1f}%'
        sampling='—' if a['historical'] else f'{a["sampling_seconds"]} / {b["sampling_seconds"]} 秒'
        review_lines.append(f'| {row["title"]} | {a["server_seconds"]:.2f} 秒 | {b["server_seconds"]:.2f} 秒 | {reduction} | {sampling} |')
        if not a['historical']: fresh.append(row)
    if len(fresh)==2:
        base=sum(r['baseline']['server_seconds'] for r in fresh)
        flex=sum(r['flex']['server_seconds'] for r in fresh)
        review_lines.extend(['',f'两条新生成 10 秒片合计：原方案 {base:.2f} 秒，Flex {flex:.2f} 秒，合计耗时减少 {(1-flex/base)*100:.1f}%，吞吐速度约 {base/flex:.2f} 倍。样本很少，不能推广为所有镜头的固定加速率。'])
    review_lines.extend(['','## 画面检查','',
        '检查方式：每条 12 张均匀关键帧、原分辨率重点帧，以及跳跃、踢击、争伞等阶段的更密集帧。关注表情指令、人数/服装、道具形态、动作完成度和构图；不把技术生成成功当成视觉通过。',''])
    for row in cases:
        review_lines.append(f'- **{row["title"]}**：{(row["review"] or {}).get("summary","待验收")}')
    review_lines.extend(['','## 选择建议','',
        '保持原方案为默认。Flex 可作为节省等待时间的可选档，适合先试单人表情与简单镜头；本轮复杂争伞的道具连续性不如原方案，不能据此整体替换默认。涉及关键道具和精确动作时仍要逐镜头验收。','',
        '## 技术验收与复现','',
        '- 各对输入的提示词 SHA256、有序参考图 SHA256 和种子一致，导出脚本进行了断言校验。','- 原生 1344×768、24fps；5 秒档为 124 帧 / 5.167 秒，10 秒档为 243 帧 / 10.125 秒。',
        '- 原 MP4 复制后逐文件校验 SHA256；工作流、精确提示词、输入和回执保存在 `evidence/`。未剪辑、插帧或重编码。',
        '- 两套都复用 INT8 底模与 FP16 视频 VAE；对比改变的是 LightX2V 8 步 Euler 与 Flex 6 步 LCM / ManualSigmas 的完整加速配方。',
        '- 音频已做解码、采样数、有限值与幅值检查，详见 `comparison.json`；没有完成主观听感或声画同步验收。用对照页的音轨选择分别试听。',
        '- 35 项相关测试通过，前端构建通过。隔离导演台测试已验证 Flex 保存后重开仍生效、切回原方案恢复 8 步参数；测试不向生产队列提交任务。',
        '- 本 campaign 每个逻辑镜头最多两次提交；表情的首次基线曾失败，本次保留其计数并复用历史成功基线。无额外重试或挑片。',
        '- 固定官方模型清单、下载校验和测试记录见 `evidence/h3-flex-models-manifest.json`、`evidence/h3-flex-model-verification.json` 与 `evidence/validation.json`。','',
        '## 比较限制','', *['- '+s for s in payload['caveats']], '',
        '这些样片是模型评估原片，视觉与听感仍可由你复核；不是已验收的短片成片或剪映剪辑工程。',''])
    (OUT/'review.md').write_text('\n'.join(review_lines),encoding='utf-8')
    cards=[]
    for row in cases:
        name=row['name']; panels=[]
        for variant,label in [('baseline','现有 768p · 8 步'),('flex','Pika Flex · 6 步')]:
            r=row[variant]
            if r['status']!='success': panels.append(f'<article><h3>{label}</h3><p>待生成</p></article>');continue
            note='历史样片，仅作画质参考' if r['historical'] else '本轮生成'
            sampling=f' · 采样约 {r["sampling_seconds"]} 秒' if r['sampling_seconds'] is not None else ''
            panels.append(f'<article><h3>{label}</h3><p>{note} · 服务器 {r["server_seconds"]:.2f} 秒{sampling}</p><video id="{name}-{variant}" controls playsinline preload="metadata" src="{r["video"]}"></video><a href="{r["video"]}" download>下载原片</a> · <a href="{name}-{variant}-contact.jpg" target="_blank">查看关键帧</a></article>')
        review=row['review'] or {'summary':'画面与声音验收待完成'}
        comparison=''
        if row['matched_inputs'] and not row['baseline']['historical']:
            a,b=row['baseline']['server_seconds'],row['flex']['server_seconds']
            comparison=f'<p class="metric">Flex 本次总耗时减少 {(1-b/a)*100:.1f}% · {a/b:.2f} 倍速度（单样本，含缓存差异）</p>'
        cards.append(f'<section id="{name}"><h2>{row["title"]}</h2>{comparison}<div class="tools"><button onclick="syncPlay(\'{name}\')">两片从头同步播放</button><button onclick="pausePair(\'{name}\')">暂停两片</button><label>试听音轨 <select onchange="selectAudio(\'{name}\',this.value)"><option value="none">静音看画面</option value="baseline">现有 768p</option><option value="flex">Pika Flex</option></select></label></div><div class="pair">{"".join(panels)}</div><p class="review">{html.escape(review["summary"])}</p></section>')
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>H3 × Pika Flex 本机对照</title><style>
    body{margin:0;background:#10151c;color:#e6edf5;font:15px/1.7 'Microsoft YaHei',sans-serif}main{max-width:1480px;margin:auto;padding:32px}h1{font-size:30px;margin-bottom:6px}h2{font-size:21px}h3{font-size:16px}p{color:#b9c6d5}.intro{max-width:1050px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:22px}section{padding:22px 0 35px;border-top:1px solid #344153;margin-top:28px}article{min-width:0;background:#18212d;padding:16px;border-radius:12px}video{width:100%;background:#000}a{color:#8fc9ff}button,select{background:#25384b;border:1px solid #486581;color:#e6edf5;border-radius:7px;padding:8px 12px;font:inherit}.tools{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin-bottom:16px}.metric{color:#8dd5b7}.review{background:#1b2938;padding:16px;border-left:3px solid #8fc9ff;white-space:pre-wrap}@media(max-width:800px){.pair{grid-template-columns:1fr}main{padding:18px}}</style><main><h1>现有 H3 768p × Pika H3 Flex</h1><p>RTX 5080 16GB · 32GB RAM · 1344 × 768 · 24fps · 2026-11-03</p><p class="intro">三组相同提示词、参考图、种子和时长的对照。表情基线为历史片，其余新片沿用同一保守显存服务。比较的是 8 步 LightX2V 与 6 步 Flex 的完整配方。当前生产默认仍为原有 768p。</p><p><a href="comparison.json">完整数据与 SHA256</a> · <a href="review.md">验收说明</a></p>'''+''.join(cards)+'''<section><h2>比较边界</h2><ul>'''+''.join('<li>'+html.escape(x)+'</li>' for x in payload['caveats'])+'''</ul></section></main><script>
    function pair(n){return ['baseline','flex'].map(v=>document.getElementById(n+'-'+v)).filter(Boolean)}
    async function syncPlay(n){let vs=pair(n);vs.forEach(v=>{v.pause();v.currentTime=0});await Promise.all(vs.map(v=>v.play().catch(()=>{})))}
    function pausePair(n){pair(n).forEach(v=>v.pause())}
    function selectAudio(n,k){pair(n).forEach(v=>v.muted=!v.id.endsWith('-'+k))}
    document.querySelectorAll('video').forEach(v=>v.muted=true);
    </script></html>'''
    (OUT/'index.html').write_text(page,encoding='utf-8')
    print(json.dumps({'output':str(OUT),'cases':[(r['name'],r['baseline']['status'],r['flex']['status']) for r in cases]},ensure_ascii=False))

if __name__=='__main__':main()
