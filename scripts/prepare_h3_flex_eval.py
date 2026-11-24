"""Prepare three paired shots; never submits GPU jobs."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
from h3_batch import prepare

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'runs/pika-flex-eval-20261102'


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def main():
    RUN.mkdir(parents=True,exist_ok=True)
    old=ROOT/'runs/h3-eval-20261012'
    expression=json.loads((old/'baseline-spec.json').read_text(encoding='utf-8'))[0]
    action,fight=json.loads((old/'action-round-2/spec.json').read_text(encoding='utf-8'))
    rows=[]
    for src,name,title in [(expression,'expression05','疑虑表情 · 5 秒'),(action,'prop10','跑跳与开合伞 · 10 秒'),(fight,'fight10','双人打斗与争伞 · 10 秒')]:
        job=copy.deepcopy(src);job['name']=name
        text=Path(job['prompt']).read_text(encoding='utf-8')
        if name=='prop10':
            text=text.replace('fifteen-second','ten-second')
            for a,b in [('0-3 seconds','0-2 seconds'),('3-6 seconds','2-4 seconds'),('6-9 seconds','4-6 seconds'),('9-12 seconds','6-8 seconds'),('12-15 seconds','8-10 seconds')]:text=text.replace(a,b)
            job['seconds']=10
        if name=='fight10':
            text=text.replace('fifteen-second','ten-second')
            for a,b in [('0-3 seconds','0-2 seconds'),('3-6 seconds','2-4 seconds'),('6-9 seconds','4-6 seconds'),('9-12 seconds','6-8 seconds'),('12-15 seconds','8-10 seconds')]:text=text.replace(a,b)
            job['seconds']=10
        prompt=RUN/'prompts'/f'{name}.txt';prompt.parent.mkdir(exist_ok=True)
        if prompt.exists() and prompt.read_text(encoding='utf-8')!=text:raise ValueError('Do not overwrite changed evaluation prompt')
        prompt.write_text(text,encoding='utf-8');job['prompt']=str(prompt.relative_to(ROOT));rows.append(job)
    for variant,profile in [('baseline','ref2v-768p-8step'),('flex','ref2v-flex-768p-6step')]:
        spec=[{**job,'profile':profile} for job in rows];path=RUN/f'{variant}-spec.json'
        if path.exists() and json.loads(path.read_text(encoding='utf-8'))!=spec:raise ValueError('Existing evaluation spec differs')
        write(path,spec)
        plans=prepare(path)
        for p in plans:write(RUN/'planned'/variant/(p['name']+'.json'),p)
    write(RUN/'authorization.json',dict(campaign='pika-flex-eval-20261102',
        user_request='下载配置 Pika H3 Flex，作为可选档，与当前768p配置生成不同片段比较速度和质量，保留当前默认。',
        shot_names=[r['name'] for r in rows],planned_submissions=6,max_total_submissions_per_logical_shot=2,
        purpose='Each logical shot has baseline and Flex takes in the SAME campaign; no extra visual retries.',
        order=['baseline/expression05','flex/expression05','flex/fight10','baseline/fight10','baseline/prop10','flex/prop10'],
        control='Same prompt, ordered references, seed, resolution, frame count, base model, encoders, VAEs and memory patches. Different LoRA and sampler schedule. Flex also saves FLAC.',
        cache_caveat='First baseline may include cold loading; compare server total and separately log sampling durations. No global speedup inferred from single samples.'))
    checks={
        'expression05':['只有一个少年，年龄与服装保持','疑虑严肃表情持续到末帧，无笑容','固定机位，无多余切镜'],
        'prop10':['跑出门并跃过矮凳','转身与横移可辨','伞的开合由手部动作完成','伞柄和伞杆连续、无消失或重复','末段仍有返回动作'],
        'fight10':['始终只有两人，身份服装不交换','攻防与低踢可辨','伞始终收拢并保持一件','争伞双方分离、手部接触合理','末段有解脱、跪地和恢复动作']}
    write(RUN/'review-checklist.json',checks)
    from PIL import Image,ImageOps,ImageDraw
    board=Image.new('RGB',(960,330*len(rows)),'#171d27');d=ImageDraw.Draw(board)
    for row,job in enumerate(rows):
        d.text((8,row*330+6),job['name'],fill='white')
        for col,ref in enumerate(job['refs']):
            with Image.open(ref) as im:im=ImageOps.contain(im.convert('RGB'),(310,285))
            board.paste(im,(col*320+(320-im.width)//2,row*330+30))
            d.text((col*320+8,row*330+312),f'Picture {col+1}',fill='white')
    board.save(RUN/'reference-board.jpg',quality=92)
    print(json.dumps({'campaign':'pika-flex-eval-20261102','shots':[(r['name'],r['seconds']) for r in rows],'preflight':'both profiles passed'},ensure_ascii=False))


if __name__=='__main__':main()
