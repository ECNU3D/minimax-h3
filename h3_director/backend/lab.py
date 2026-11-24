"""Independent single-shot lab, sharing the director's serial bounded worker."""
import base64
import copy
from pathlib import Path
import sys
import time
from .project import ROOT,LOCK,uid,write,read,digest
from .paths import PYTHON
from .lab_store import compose
from .production import selected_profile,PREVIEW_PROFILE,FLEX_PROFILE

def preview(experiment):
    return selected_profile(experiment)==PREVIEW_PROFILE

def effective_settings(experiment):
    cfg=dict(experiment['settings'])
    if preview(experiment):cfg.update(steps=4,sampler='euler',turbo=True,lora_strength=1.0,shift_video=12.0,shift_audio=3.0,denoise=1.0)
    if selected_profile(experiment)==FLEX_PROFILE:cfg.update(steps=6,sampler='lcm',turbo=True,lora_strength=1.0,shift_video=12.0,shift_audio=3.0,denoise=1.0)
    return cfg


def plan(runner,experiment,folder):
    from .lab_templates import prompt_issues
    issues=prompt_issues(experiment)
    if issues:raise ValueError('；'.join(issues))
    folder.mkdir(parents=True,exist_ok=True)
    for ref in experiment['references']+experiment['audioReferences']:
        if digest(ref['path'])!=ref['sha256']:raise ValueError('参考素材已改变：'+ref['label'])
    prompt=folder/'prompt.txt';prompt.write_text(compose(experiment),encoding='utf-8')
    spec=folder/'spec.json';cfg=effective_settings(experiment)
    quick=preview(experiment)
    flex=selected_profile(experiment)==FLEX_PROFILE
    if quick and not experiment['references']:raise ValueError('常规快速预览需要 1–9 张参考图；纯文本测试请使用 768p 模式')
    if quick and experiment['audioReferences']:raise ValueError('常规快速预览尚未接入音频参考，请使用 768p 模式')
    if flex and not experiment['references']:raise ValueError('当前 Flex 档需要 1–9 张参考图')
    write(spec,[dict(name='shot',prompt=str(prompt),refs=[r['path'] for r in experiment['references']],
        audio_refs=[r['path'] for r in experiment['audioReferences']],width=960 if quick else 1344,height=544 if quick else 768,
        seconds=cfg['seconds'],seed=cfg['seed'],profile=PREVIEW_PROFILE if quick else FLEX_PROFILE if flex else 'ref2v-lab',**({} if quick or flex else dict(lab_settings=cfg)))])
    # Import the exact production planner; this does not contact or submit to ComfyUI.
    scripts=str(ROOT/'scripts')
    if scripts not in sys.path:sys.path.insert(0,scripts)
    from h3_batch import prepare
    result=prepare(spec,allow_reference_override=True)[0]
    write(folder/'workflow.json',result['workflow']);write(folder/'inputs.json',result['inputs'])
    return result


def enqueue(runner,e,revision,mode):
    from .runner import budget
    if revision!=e['revision']:raise ValueError('测试已更新，请刷新后重试')
    if runner.busy('lab_'+e['id']):raise ValueError('该测试有未完成任务，请先完成或恢复原任务')
    if mode not in ('preflight','run'):raise ValueError('测试模式无效')
    if mode=='run':
        b=budget(e)
        if b['stop']:raise ValueError('本轮已 STOP，请检查记录；不可自动重试')
        if len(b['ledger'].get('attempts',{}).get('shot',[]))>=2:raise ValueError('本轮两次提交已用完；需要继续时，请手动开启新一轮测试')
    jid=uid();folder=runner.lab.path(e['id']).parent/'runs'/jid
    result=plan(runner,e,folder)
    j=dict(id=jid,projectId='lab_'+e['id'],projectName=e['name'],labId=e['id'],kind='lab',mode=mode,
           target='shot',status='queued',created=time.time(),message='等待单镜测试',done=[],progress=0,
           paused=False,autoReview=False,snapshot=copy.deepcopy(e),folder=str(folder),fingerprint=result['fingerprint'])
    runner.jobs.append(j);runner.save();return j


def execute(runner,j):
    folder=Path(j['folder']);runner.checkpoint(j)
    args=[PYTHON,ROOT/'scripts/h3_batch.py','--spec',folder/'spec.json','--run-dir',folder,
          '--campaign',j['snapshot']['campaign'],'--allow-reference-override']
    runner.update(j,'校验单镜参数、参考顺序与声音输出工作流')
    runner.command(args,folder,j)
    if j['mode']=='preflight':
        j['message']='离线预检通过，未提交生成';return
    from .local_service import ensure_running
    recorded=any(folder.rglob('job.json')) or any(folder.rglob('submission.json'))
    ensure_running(folder,lambda m:runner.update(j,m),lambda:runner.checkpoint(j),
                   allow_start=not j.get('localServiceReady') and not recorded)
    j['localServiceReady']=True;runner.save();runner.checkpoint(j)
    runner.update(j,'生成快速预览及 MP4 原生音轨' if preview(j['snapshot']) else '生成单个分镜及原生音轨 · 同时保存 FLAC 和 MP4')
    runner.command(args+['--execute'],folder,j)
    record=read(folder/'shot/job.json');files=record['files']
    if not preview(j['snapshot']) and not any(Path(f['path']).suffix.lower()=='.flac' for f in files):raise ValueError('未收到编码前 FLAC，请检查工作流记录')
    from .lab_audio import inspect_audio
    audio={}
    for index,f in enumerate(files):
        if Path(f['path']).suffix.lower() in ('.mp4','.flac'):
            try:audio[str(index)]=inspect_audio(f['path'])
            except Exception as exc:audio[str(index)]={'error':str(exc)}
    write(folder/'audio-inspection.json',audio)
    with LOCK:j['files']=files;j['audioInspection']=audio;j['message']='生成完成，声音与画面待试听验收';runner.save()


def public_job(j):
    out={k:copy.deepcopy(v) for k,v in j.items() if k not in ('snapshot','pid')}
    out['settings']=effective_settings(j['snapshot']);out['prompt']=compose(j['snapshot']);out['campaign']=j['snapshot']['campaign']
    out['videoProfile']=selected_profile(j['snapshot'])
    out['promptLanguage']=j['snapshot'].get('promptLanguage')
    for index,f in enumerate(out.get('files',[])):f['url']=f'/api/lab/{j["labId"]}/runs/{j["id"]}/files/{index}'
    out['workflowUrl']=f'/api/lab/{j["labId"]}/runs/{j["id"]}/workflow'
    out['logUrl']=f'/api/lab/{j["labId"]}/runs/{j["id"]}/log'
    return out


def get(handler,parts):
    runner=handler.server.runner;store=runner.lab
    if parts==['api','lab','templates']:
        from .lab_templates import catalog
        return handler.respond(catalog())
    if len(parts)==2:return handler.respond([dict(id=e['id'],name=e['name'],updated=e['updated']) for e in store.list()])
    e=store.get(parts[2])
    if len(parts)==3:
        result=store.public(e);result['jobs']=[public_job(j) for j in reversed(runner.jobs) if j.get('labId')==e['id']]
        return handler.respond(result)
    if len(parts)==5 and parts[3]=='references':
        ref=next(r for r in e['references']+e['audioReferences'] if r['id']==parts[4])
        return handler.send_file(Path(ref['path']))
    if len(parts)>=6 and parts[3]=='runs':
        j=next(j for j in runner.jobs if j.get('labId')==e['id'] and j['id']==parts[4])
        if len(parts)==7 and parts[5]=='files':
            index=int(parts[6])
            if index<0:raise ValueError('非法索引')
            return handler.send_file(Path(j['files'][index]['path']))
        if len(parts)==6 and parts[5] in ('workflow','log'):
            return handler.send_file(Path(j['folder'])/('workflow.json' if parts[5]=='workflow' else 'process.log'))
    raise ValueError('测试接口不存在')


def mutate(handler,parts,d):
    runner=handler.server.runner;store=runner.lab
    if parts==['api','lab','templates','open']:
        from .lab_templates import template,create_case
        template(d['templateId'])
        e=next((e for e in store.list() if e.get('templateId')==d['templateId']),None)
        return handler.respond(store.public(e or create_case(store,d['templateId'])))
    if len(parts)==2:
        if d.get('templateId'):
            from .lab_templates import create_case
            e=create_case(store,d['templateId'])
        elif d.get('projectId'):e=store.import_shot(handler.server.store.get(d['projectId']),d['shotId'])
        else:e=store.create(d.get('name','单镜声音测试'))
        return handler.respond(store.public(e),201)
    e=store.get(parts[2]);action=parts[3] if len(parts)==4 else ''
    if d.get('revision')!=e['revision']:raise ValueError('测试已更新，请刷新后重试')
    if action=='save':return handler.respond(store.public(store.update(e['id'],d['changes'],d['revision'])))
    if action in ('preflight','run'):
        j=enqueue(runner,e,d['revision'],action);return handler.respond(public_job(j),202)
    if action=='upload':
        suffix=Path(d['filename']).suffix.lower()
        if suffix not in ('.png','.jpg','.jpeg','.webp','.wav','.flac','.mp3','.m4a','.ogg'):raise ValueError('不支持的文件格式')
        content=base64.b64decode(d['content'],validate=True)
        if len(content)>40*1024*1024:raise ValueError('单个参考素材上限 40 MB')
        path=store.path(e['id']).parent/('upload_'+uid()+suffix)
        try:
            path.write_bytes(content);store.copy_reference(e,path,d['filename'],audio=bool(d.get('audio')))
            store.save(e)
        finally:path.unlink(missing_ok=True)
        return handler.respond(store.public(e))
    if action=='new-round':
        from .runner import budget
        if runner.busy('lab_'+e['id']):raise ValueError('请先完成或对账原任务')
        b=budget(e)
        if 'reserved' in b['ledger'].get('outcomes',{}).values():raise ValueError('仍有未对账提交，请先检查队列和历史，不能新开预算')
        e['rounds'].append(dict(campaign=e['campaign'],ended=time.time(),reason='user_new_round'))
        e['campaign']='lab_'+uid();store.save(e)
        return handler.respond(store.public(e))
    raise ValueError('未知测试操作')
