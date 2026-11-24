"""Persisted GPU FIFO with parallel video reviews. Video submits only via h3_batch."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
import urllib.request
import urllib.error
import zipfile
from .project import ROOT,LOCK,uid,read,write,digest,selected,validate_shot,current
from .paths import APP,PYTHON,HARNESS
from .assets import settings,references,ordered_assets,mask_reference
from .agent import runtime as agent_runtime,provider as agent_provider

COMFY='http://127.0.0.1:8188'
SINGLE_JOBS={'asset','shot','shot_auto','preflight','review'}

def queue_compatible(jobs,kind):
    return not jobs or kind in SINGLE_JOBS and all(j['kind'] in SINGLE_JOBS and j['status']!='interrupted' for j in jobs)

def owns_item(job,target):
    if job.get('target')==target:return True
    if job['kind']=='shot_auto':
        p=job['snapshot'];shot=next(s for s in p['shots'] if s['id']==job['target'])
        return target in {a['id'] for a in ordered_assets(p,[a for a in p['assets'] if a['id'] in shot['refs']])}
    return False

def shot_clear_targets(job):
    """Only unfinished work that can write a shot may block its archival."""
    shots=job['snapshot'].get('shots',[]);kind=job['kind']
    if kind in ('shot','shot_auto','review'):
        return [s['id'] for s in shots if s['id']==job.get('target')]
    if kind=='parse':return [s['id'] for s in shots]
    if kind in ('auto','shots_auto'):
        # Batches skip existing videos and never revisit completed items.
        return [s['id'] for s in shots if 'shots/'+s['id'] not in job.get('done',[]) and
                (not selected(s) or 'shots/'+s['id'] in job.get('retryStates',{}))]
    return []

def shot_signature(project,target):
    from .production import shot_dimensions
    shot=next(s for s in project['shots'] if s['id']==target)
    refs=[dict(id=key,version=selected(next(a for a in project['assets'] if a['id']==key))) for key in shot['refs']]
    profile=project.get('videoProfile')
    return json.dumps(dict(shot={k:shot.get(k) for k in ('prompt','seed','seconds','refs')},
                           dimensions=shot_dimensions(profile,shot),refs=refs,profile=profile),sort_keys=True,ensure_ascii=False)

class Paused(Exception): pass
class Stop(Exception): pass
class Human(Exception): pass
class QualityReviewRequired(Human): pass
class ReviewUnavailable(QualityReviewRequired): pass

def queue(url=COMFY):
    from .local_service import ServiceUnavailable
    try:
        with urllib.request.urlopen(url+'/queue',timeout=5) as r:return json.load(r)
    except (urllib.error.URLError,OSError) as error:
        raise ServiceUnavailable('ComfyUI 本地生成服务无法连接（127.0.0.1:8188），请检查启动日志；未自动重启或重复提交。') from error

def budget(p):
    folder=ROOT/'runs/h3-budgets'/p['campaign']
    return {'ledger':read(folder/'budget.json') if (folder/'budget.json').exists() else {},
            'stop':read(folder/'STOP.json') if (folder/'STOP.json').exists() else None,
            'stopPath':str(folder/'STOP.json')}

class Runner:
    def __init__(self,store,start=True):
        from .lab_store import LabStore
        self.lab=LabStore(store.folder)
        self.store=store; self.file=store.folder/'jobs.json'
        from .prompt_optimizer import PromptOptimizer
        self.optimizer=PromptOptimizer(self,start=start)
        self.jobs=read(self.file) if self.file.exists() else []
        for j in self.jobs:
            if j['status']=='running':
                j['status']='interrupted'; j['message']='服务重启，可能仍有在途生成；仅可原任务恢复并对账。'
        from .async_shots import recover
        recover(self)
        self.save()
        if start:
            threading.Thread(target=self.loop,daemon=True).start()
            from .async_shots import REVIEW_WORKERS
            for _ in range(REVIEW_WORKERS):threading.Thread(target=self.loop,args=('review',),daemon=True).start()
    def save(self): write(self.file,self.jobs)
    def busy(self,pid): return bool(self.pending(pid))
    def pending(self,pid): return [j for j in self.jobs if j['projectId']==pid and (j['status'] in ('queued','running','interrupted','paused') or any(t['status']=='running' for t in j.get('shotTasks',[])))]
    def next_queued(self):
        # A restarted server must reconcile the previous in-flight job first.
        if any(j['status']=='interrupted' for j in self.jobs):return None
        return next((j for j in self.jobs if j['status']=='queued'),None)
    def can_edit(self,pid,action,target=None):
        jobs=self.pending(pid)
        if not jobs:return True
        if action=='clear-shot':return not any(target in shot_clear_targets(j) for j in jobs)
        if not queue_compatible(jobs,'shot'):return False
        if action in ('asset','input','shot','video-mode'):return True
        return action in ('accept','select','upload','clear-asset','restore-asset','restore-shot') and not any(owns_item(j,target) for j in jobs)
    def enqueue(self,pid,kind,target=None,auto_review=True,options=None,revision=None):
        with LOCK:
            if kind not in ('asset','shot','auto','assets_auto','shots_auto','shot_auto','review','export','preflight','parse','dependencies'): raise ValueError('未知任务类型')
            pending=self.pending(pid)
            if not queue_compatible(pending,kind):
                raise ValueError('项目有批量流程或待对账任务，请先完成；独立图片、单镜、预检和审查任务可连续排队')
            p=self.store.get(pid)
            if revision is not None and revision!=p['revision']:raise ValueError('工作空间已更新，请重新打开自动制作设置')
            if kind in ('shot','auto','shots_auto','shot_auto','preflight'):
                from .production import selected_profile
                # Freeze the default at enqueue time. Old persisted tasks/specs keep their original recipe.
                p['videoProfile']=selected_profile(p)
            if options is not None:
                if kind not in ('auto','assets_auto','shots_auto'):raise ValueError('批量设置仅用于自动制作')
                from .production import configure
                configure(p,options,{'assets_auto':'assets','shots_auto':'shots'}.get(kind,'all'));auto_review=p['autoReview']
                agent_runtime(p)  # Validate subscription model/effort before saving selections.
            if budget(p)['stop'] and kind in ('shot','auto','shot_auto','shots_auto'): raise ValueError('此项目已 STOP，需人工处理；不可自动更换预算')
            if kind in ('shot','preflight'):
                s=next(s for s in p['shots'] if s['id']==target)
                errors=validate_shot(p,s)
                if errors: raise ValueError('；'.join(errors))
            if kind=='asset' and not any(a['id']==target for a in p['assets']): raise ValueError('资产不存在')
            if kind=='asset': references(p,next(a for a in p['assets'] if a['id']==target))
            if kind=='asset':
                a=next(a for a in p['assets'] if a['id']==target)
                signature=lambda x:json.dumps({k:x.get(k) for k in ('prompt','seed','sidePrompt','backPrompt','provider','imageMode','imageVariant','generationRefs','editMask')},sort_keys=True,ensure_ascii=False)
                if any(x['kind']=='asset' and x['target']==target and signature(next(a for a in x['snapshot']['assets'] if a['id']==target))==signature(a) for x in pending):
                    raise ValueError('相同资产和参数已经排队；修改提示词后可再提交一个版本')
            if kind=='shot_auto':
                s=next(s for s in p['shots'] if s['id']==target)
                errors=validate_shot(p,s,False)
                if errors: raise ValueError('；'.join(errors))
            if kind in ('shot','shot_auto','preflight'):
                matching={'preflight'} if kind=='preflight' else {'shot','shot_auto'}
                if any(x['kind'] in matching and x['target']==target and shot_signature(x['snapshot'],target)==shot_signature(p,target) for x in pending):
                    raise ValueError('相同镜头和参数已经排队；修改提示词或参数后可再提交一个版本')
            if kind=='review':
                item=next((x for x in p['assets']+p['shots'] if x['id']==target),None)
                if not item or not selected(item):raise ValueError('没有可审查的版本')
                if any(owns_item(x,target) for x in pending):raise ValueError('此素材已有待执行任务，请完成后再审查；其他素材可继续排队')
            if kind=='parse' and (any(x['versions'] for x in p['assets']+p['shots'])): raise ValueError('已有生成素材，请新建项目智能导入以保留制作版本')
            if kind=='assets_auto' and not p['assets']:raise ValueError('先导入或新增参考资产')
            if kind in ('assets_auto','auto','shot_auto'):ordered_assets(p)
            if kind in ('auto','shots_auto'):
                errors=[s['name']+'：'+'；'.join(validate_shot(p,s,False)) for s in p['shots'] if not selected(s) and validate_shot(p,s,False)]
                if errors: raise ValueError('\n'.join(errors))
                if not p['shots']: raise ValueError('先导入分镜脚本')
            if kind=='shots_auto':
                from .production import require_references
                require_references(p,[s for s in p['shots'] if not selected(s)])
            j=dict(id=uid(),projectId=pid,projectName=p['name'],kind=kind,target=target,status='queued',
                   created=time.time(),message='等待执行',done=[],progress=0,paused=False,autoReview=bool(auto_review),snapshot=copy.deepcopy(p))
            if kind in ('shot','auto','shots_auto','shot_auto','preflight'):j['videoProfile']=p['videoProfile']
            if kind in ('shot','shot_auto','preflight'):
                from .production import shot_dimensions
                j['videoDimensions']=list(shot_dimensions(p['videoProfile'],s))
            if options is not None:
                self.store.save(p);j['snapshot']=copy.deepcopy(p);j['productionSettings']=copy.deepcopy(p['productionSettings'])
            self.jobs.append(j); self.save(); return j
    def control(self,jid,action):
        with LOCK:
            j=next(j for j in self.jobs if j['id']==jid)
            if j.get('archivedByReset'):raise ValueError('该任务已随项目清空归档，不能直接恢复旧输入')
            from .async_shots import control
            if j.get('shotTasks') is not None:return control(self,j,action)
            live=j['snapshot'] if j['kind']=='lab' else self.store.get(j['projectId'])
            if action=='pause' and j['status'] in ('queued','running'):
                j['paused']=True
                if j['status']=='queued': j['status']='paused'
                j['message']='当前生成完成后暂停；不会中断 ComfyUI'
            elif action=='resume' and (j['status'] in ('paused','interrupted') or (j['kind']=='parse' and j['status']=='failed')):
                others=[x for x in self.pending(j['projectId']) if x['id']!=j['id']]
                if not queue_compatible(others,j['kind']): raise ValueError('此项目已有其他流程或待对账任务')
                if budget(j['snapshot'])['stop'] and j['kind'] in ('auto','shot','shot_auto','shots_auto','preflight','lab'): raise ValueError('STOP 不可自动恢复')
                if j['kind']=='parse' and any(x['versions'] for x in live['assets']+live['shots']):raise ValueError('已有生成素材，不能重跑旧解析覆盖制作版本；请新建项目导入')
                j.setdefault('attempts',[]).append({**{k:copy.deepcopy(j[k]) for k in ('status','message','stage','startedAt','finishedAt','events') if k in j},'agentProvider':j['snapshot'].get('agentProvider','deepseek'),'agentModel':j['snapshot'].get('agentModel'),'agentThinking':j['snapshot'].get('agentThinking')})
                # A deliberate rerun uses today's director selection; production inputs stay frozen.
                for key,default in [('agentProvider','deepseek'),('agentModel','gpt-5.6-sol'),('agentThinking','high')]:
                    j['snapshot'][key]=live.get(key,default)
                for key in ('startedAt','finishedAt','stage','lastActivityAt'):j.pop(key,None)
                j['events']=[];j['message']='等待按当前导演 Agent 设置继续原任务'
                j['paused']=False; j['status']='queued'
            elif action=='cancel' and j['status'] in ('queued','paused'):
                j['status']='cancelled'; j['message']='已取消后续步骤，已生成素材保留'
            else: raise ValueError('当前状态不支持此操作')
            self.save(); return j
    def update(self,j,message):
        with LOCK:
            j.get('_task',j)['message']=message; self.save()
    def checkpoint(self,j):
        if j.get('_parent',j)['paused']: raise Paused()
    def loop(self,lane='gpu'):
        while True:
            if not self.run_once(lane):time.sleep(.2)
    def run_once(self,lane='gpu'):
        from .async_shots import run_once
        return run_once(self,lane)
    def event(self,j,event):
        # Only our explicit metadata protocol is public, never SDK prompt/reasoning text.
        if event.get('type')!='director.progress': return
        stage=event.get('stage')
        labels={'parse':'解析原文','repair':'修正解析结果','audit':'独立 Agent 校对','validate':'校验原文与引用','save':'保存导入结果','review':'视觉审查'}
        messages={'started':'已开始','thread.started':'会话已建立','turn.started':'模型处理中','item.started':'模型处理中','item.updated':'收到模型活动','item.completed':'收到模型事件','turn.completed':'模型调用完成','completed':'完成','failed':'失败'}
        if stage not in labels or event.get('event') not in messages:return
        entry={k:event[k] for k in ('stage','event','threadId','model','thinking','attempt','outputChars','usage') if k in event}
        entry['at']=time.time(); entry['message']=labels[stage]+' · '+messages[event['event']]
        j=j.get('_task',j)
        with LOCK:
            j['stage']=stage; j['message']=entry['message']; j['lastActivityAt']=entry['at']
            j['events']=(j.get('events',[])+[entry])[-200:]; self.save()
    def command(self,args,folder,j):
        folder.mkdir(parents=True,exist_ok=True)
        log=folder/'process.log'; env=os.environ.copy(); env['PYTHONUTF8']='1'
        # Secrets belong to the reviewer, never to image/video subprocesses.
        for k in list(env):
            if 'API_KEY' in k: env.pop(k)
        with log.open('a',encoding='utf-8') as f:
            offset=log.stat().st_size; buffer=''
            proc=subprocess.Popen([str(x) for x in args],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,env=env,
                                  creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            with LOCK:
                target=j.get('_task',j);target['pid']=proc.pid;target['log']=str(log);self.save()
            while True:
                try: code=proc.wait(timeout=1)
                except subprocess.TimeoutExpired: code=None
                with log.open('r',encoding='utf-8',errors='replace') as reader:
                    reader.seek(offset); buffer+=reader.read(); offset=reader.tell()
                rows=buffer.split('\n'); buffer=rows.pop()
                for row in rows:
                    if row.startswith('{"type":"director.progress",'):
                        try:self.event(j,json.loads(row))
                        except (ValueError,TypeError):pass
                if code is not None:break
        with LOCK: j.get('_task',j).pop('pid',None);self.save()
        if code==20: raise Stop('生产执行器已 STOP：'+budget(j['snapshot'])['stopPath'])
        if code==10: raise Human('任务结果尚未明确，保留在途任务，停止自动执行。记录：'+str(log))
        if code==30 and any(str(x)==str(HARNESS) for x in args):raise ReviewUnavailable('视觉审核超时，未取得结论；素材已保留，可单独重新审核。记录：'+str(log))
        if code: raise RuntimeError('执行失败，详见 '+str(log)+'\n'+log.read_text(encoding='utf-8',errors='replace')[-1200:])
    def idle(self):
        q=queue()
        if q['queue_running'] or q['queue_pending']: raise Human('ComfyUI 正在执行其他任务，请等待队列空闲后再操作。')
    def ensure_local(self,j,qwen=False):
        from .local_service import ensure_running
        folder=self.store.folder/'runs'/j['id']
        if qwen:
            from .qwen_service import ensure_running as ensure_qwen
            ensure_qwen(folder,lambda message:self.update(j,message),lambda:self.checkpoint(j),allow_start=not j.get('qwenServiceReady'))
            with LOCK:j['qwenServiceReady']=True;self.save()
            return
        recorded=any(folder.rglob('job.json')) or any(folder.rglob('submission.json'))
        ensure_running(folder,lambda message:self.update(j,message),lambda:self.checkpoint(j),
                       allow_start=not j.get('localServiceReady') and not recorded,peer_url='http://127.0.0.1:8190')
        with LOCK:j['localServiceReady']=True;self.save()
    def persist_item(self,p,category,item):
        with LOCK:
            live=self.store.get(p['id']); idx=next(i for i,x in enumerate(live[category]) if x['id']==item['id'])
            current_item=live[category][idx]
            # A queued job owns its outputs, not edits made after submission.
            versions={v['id']:v for v in current_item['versions']}
            # Existing takes may have received a concurrent review/human approval.
            # Generation adds immutable versions; review writes use persist_review.
            for v in item['versions']:versions.setdefault(v['id'],copy.deepcopy(v))
            current_item['versions']=list(versions.values())
            current_item['selected']=item['selected']
            if category=='shots' and selected(item):
                # Dimensions are output metadata in the director, not editable shot inputs.
                for key in ('width','height'):
                    if key in selected(item):current_item[key]=selected(item)[key]
            if item['history'] and item['history'][-1].get('reason')=='agent_revision' and current_item['prompt']==item['history'][-1]['prompt']:
                for key in ('prompt','seed','sidePrompt','backPrompt'):
                    if key in item:current_item[key]=item[key]
            for entry in item['history']:
                if entry not in current_item['history']:current_item['history'].append(copy.deepcopy(entry))
            self.store.save(live); self.save()
    def asset(self,p,a,j,attempt=0):
        folder=self.store.folder/'runs'/j['id']/(a['id']+f'_v{attempt}')
        self.update(j,'生成参考图 · '+a['name'])
        refs=references(p,a); cfg=settings(a)
        if cfg['provider']=='codex': return self.codex_asset(p,a,j,folder,refs,attempt)
        qwen=cfg['imageVariant']=='qwen21'
        if qwen:self.ensure_local(j,qwen=True)
        else:self.ensure_local(j)
        get_queue=(lambda:queue('http://127.0.0.1:8190')) if qwen else queue
        edit_mask=mask_reference(p,a,refs)
        self.update(j,'生成参考图 · '+a['name'])
        configpath=folder/'config.json'
        if not configpath.exists():
            q=get_queue()
            if q['queue_running'] or q['queue_pending']:raise Human('图片服务正在执行其他任务')
            folder.mkdir(parents=True,exist_ok=True)
            names=['character_front','character_side','character_back'] if a['kind']=='character' else [a['kind']]
            stages=[]
            for n in names:
                prompt=a['sidePrompt'] if n=='character_side' else a['backPrompt'] if n=='character_back' else a['prompt']
                f=folder/(n+'.txt'); f.write_text(prompt,encoding='utf-8')
                w,h=(768,1152) if a['kind']=='character' else (1344,768) if a['kind'] in ('scene','keyframe') else (1024,1024)
                stages.append(dict(name=n,prompt_file=str(f),width=w,height=h,seed=a['seed']+names.index(n),references=['character_front'] if n in ('character_side','character_back') else [f'input_{i}' for i in range(len(refs))]))
                if edit_mask and n==names[0]:stages[-1]['edit_mask']=edit_mask
            config=dict(image_variant=cfg['imageVariant'],stages=stages,external_references={f'input_{i}':r for i,r in enumerate(refs)})
            if qwen:config['qwen_workflow_profile']='independent-reference-seed-v2'
            write(configpath,config)
        q=get_queue(); own={read(f).get('prompt_id') for f in (folder/'jobs').glob('*/job.json')}
        if {x[1] for x in q['queue_running']+q['queue_pending']}-own: raise Human('其他任务占用 ComfyUI，未提交参考图')
        self.command([ROOT/'tools/qwen21/env/Scripts/python.exe' if qwen else PYTHON,ROOT/('scripts/qwen_image_pipeline.py' if qwen else 'scripts/reference_video_pipeline.py'),'--config',configpath,'--run-dir',folder,'--until','references'],folder,j)
        m=read(folder/'manifest.json'); files=[dict(label=n,**v) for n,v in m['assets'].items()]
        version=dict(id=j['id']+'_'+a['id']+f'_{attempt}',created=time.time(),files=files,prompt=a['prompt'],seed=a['seed'],
                     record=str(folder/'manifest.json'),review=None,humanAccepted=False,viewPrompts=[a['sidePrompt'],a['backPrompt']],generation=cfg,inputReferences=refs)
        if edit_mask:version['editMaskReference']=edit_mask
        version=next((x for x in a['versions'] if x['id']==version['id']),version)
        self.add_version(p,'assets',a,version)
        return version,folder
    def codex_asset(self,p,a,j,folder,refs,attempt):
        from .codex_bridge import generate
        files=[]
        names=['character_front','character_side','character_back'] if a['kind']=='character' else [a['kind']]
        for n in names:
            self.checkpoint(j); self.update(j,'Codex Image Gen · '+a['name']+' · '+n)
            prompt=a['sidePrompt'] if n=='character_side' else a['backPrompt'] if n=='character_back' else a['prompt']
            inputs=[files[0]] if len(files) else refs
            generated=generate(prompt,inputs,folder/n)
            if len(generated)!=1: raise Human('Codex 返回多张图片，请先人工核对执行记录')
            files.append(dict(generated[0],label=n))
        manifest=dict(status='references_ready',provider='codex-image-gen',generation=settings(a),prompt=a['prompt'],
            viewPrompts=[a['sidePrompt'],a['backPrompt']],inputReferences=refs,files=files,seedSupported=False)
        write(folder/'manifest.json',manifest)
        v=dict(id=j['id']+'_'+a['id']+f'_{attempt}',created=time.time(),files=files,prompt=a['prompt'],seed=a['seed'],
            record=str(folder/'manifest.json'),review=None,humanAccepted=False,viewPrompts=manifest['viewPrompts'],generation=settings(a),inputReferences=refs)
        self.add_version(p,'assets',a,v); return v,folder
    def shot(self,p,s,j,attempt=0,preflight=False):
        errors=validate_shot(p,s)
        if errors: raise ValueError('；'.join(errors))
        folder=self.store.folder/'runs'/j['id']/(s['id']+f'_v{attempt}'); folder.mkdir(parents=True,exist_ok=True)
        self.update(j,('离线预检 · ' if preflight else '生成镜头 · ')+s['name'])
        specpath=folder/'spec.json'
        if not specpath.exists():
            prompt=folder/'prompt.txt'; prompt.write_text(s['prompt'],encoding='utf-8')
            refs=[selected(next(a for a in p['assets'] if a['id']==key))['files'][0]['path'] for key in s['refs']]
            profile=p.get('videoProfile','legacy-ref2v-4step')
            from .production import shot_dimensions
            width,height=shot_dimensions(profile,s)
            write(specpath,[dict(name=s['id'],prompt=str(prompt),refs=refs,seed=s['seed'],width=width,height=height,seconds=s['seconds'],profile=profile)])
        # Explicit project mode: variable references, 1–9 images. No budget override.
        args=[PYTHON,ROOT/'scripts/h3_batch.py','--spec',specpath,'--run-dir',folder,'--campaign',p['campaign'],'--allow-reference-override']
        self.command(args,folder,j)
        if preflight: return
        self.ensure_local(j)
        self.update(j,'生成镜头 · '+s['name'])
        self.command(args+['--execute'],folder,j)
        result=read(folder/s['id']/'result.json')
        inputs=read(folder/s['id']/'inputs.json')
        version=dict(id=j['id']+'_'+s['id']+f'_{attempt}',created=time.time(),files=[dict(label='video',**result['video'])],
                     prompt=inputs['prompt'],seed=inputs['seed'],seconds=inputs['seconds'],width=inputs['width'],height=inputs['height'],references=inputs['references'],
                     profile=inputs.get('profile','legacy-ref2v-4step'),campaign=p['campaign'],
                     record=str(folder/s['id']/'result.json'),review=None,humanAccepted=False)
        version=next((x for x in s['versions'] if x['id']==version['id']),version)
        s['width'],s['height']=version['width'],version['height']
        self.add_version(p,'shots',s,version); return version,folder
    def add_version(self,p,category,item,v):
        if not any(x['id']==v['id'] for x in item['versions']): item['versions'].append(v)
        item['selected']=v['id']; self.persist_item(p,category,item)
    def persist_review(self,p,category,item,v):
        with LOCK:
            live=self.store.get(p['id'])
            current_item=next((x for x in live[category] if x['id']==item['id']),None)
            current_version=next((x for x in current_item['versions'] if x['id']==v['id']),None) if current_item else None
            if current_version is None:return  # Cleared/archived results must never be resurrected.
            for key in ('review','reviewError','reviewHistory'):
                if key in v:current_version[key]=copy.deepcopy(v[key])
                else:current_version.pop(key,None)
            self.store.save(live);self.save()
    def review(self,p,category,item,v,folder,j):
        self.update(j,'Agent 视觉初筛 · '+item['name'])
        folder.mkdir(parents=True,exist_ok=True)
        for f in v['files'] + v.get('references',[]) + v.get('inputReferences',[]) + ([v['editMaskReference']] if v.get('editMaskReference') else []):
            if digest(Path(f['path'])) != f['sha256']: raise ValueError('审查素材与生成记录哈希不一致：'+f['path'])
        images=[]
        evidence=dict(method='image-attachments',sourceFiles=v['files'],references=v.get('references',[]),audioReviewed=False)
        if category=='shots':
            import av
            for i,ref in enumerate(v['references']): images.append(dict(label=f'参考 Picture {i+1}',path=ref['path']))
            framefolder=folder/'review-frames'; framefolder.mkdir(exist_ok=True)
            with av.open(v['files'][0]['path']) as c:
                fps=float(c.streams.video[0].average_rate); stride=max(1,round(fps/2))
                last=None; saved=-1; frame_count=0
                for index,frame in enumerate(c.decode(video=0)):
                    last=frame; frame_count=index+1
                    if index%stride: continue
                    picture=frame.to_image(); picture.thumbnail((960,960))
                    target=framefolder/f'frame_{index:04}.jpg'; picture.save(target,quality=85)
                    timestamp=float(frame.time) if frame.time is not None else index/fps
                    images.append(dict(label=f'视频 {timestamp:.3f}s',path=str(target),frameIndex=index,timestamp=timestamp))
                    saved=index
                if last is not None and saved != frame_count-1:
                    picture=last.to_image(); picture.thumbnail((960,960))
                    target=framefolder/f'frame_{frame_count-1:04}.jpg'; picture.save(target,quality=85)
                    timestamp=float(last.time) if last.time is not None else (frame_count-1)/fps
                    images.append(dict(label=f'视频末帧 {timestamp:.3f}s',path=str(target),frameIndex=frame_count-1,timestamp=timestamp))
                if frame_count==0: raise ValueError('视频没有可解码帧，未请求视觉审查')
                evidence.update(method='sampled-video-frames',decodedFrames=frame_count,fps=fps,sampleIntervalSeconds=stride/fps,
                                sampledFrames=sum('frameIndex' in x for x in images))
        else:
            evidence['inputReferences']=v.get('inputReferences',[])
            images=[dict(label='生成输入参考 '+str(i+1),path=f['path']) for i,f in enumerate(v.get('inputReferences',[]))]+[dict(label=f['label'],path=f['path']) for f in v['files']]
            if v.get('editMaskReference'):
                evidence['editMaskReference']=v['editMaskReference']
                images.append(dict(label='编辑选区蒙版：白色可改，黑色保持原图',path=v['editMaskReference']['path']))
        for index,img in enumerate(images): img.update(attachment=index+1,sha256=digest(Path(img['path'])))
        evidence['attachments']=images
        req=folder/'review-input.json'; out=folder/'review.json'
        profile=dict(purpose='H3 reference assets' if category=='assets' else 'H3 storyboard video',dimensionsSource='pipeline config',
            expectedViews=['front','side facing image right','back'] if item.get('kind')=='character' else [item.get('kind','video')],
            imageDimensions=[{k:f.get(k) for k in ('label','width','height')} for f in v['files']])
        limit=self.retry_limit(j);attempt=j.get('retryStates',{}).get(category+'/'+item['id'],{}).get('attempt',0)
        remaining=max(0,limit-attempt)
        if category=='shots':remaining=min(remaining,max(0,2-len(budget(p)['ledger'].get('attempts',{}).get(item['id'],[]))))
        write(req,dict(kind=item.get('kind','video'),prompt=v['prompt'],viewPrompts=v.get('viewPrompts') if item.get('kind')=='character' else None,
            information=item.get('info',''),images=images,evidence=evidence,outputProfile=profile,
            retryContext=dict(maxRetries=limit,retriesUsed=attempt,retriesRemaining=remaining,previousDecisions=[r for r in j.get('retryEvents',[]) if r['item']==category+'/'+item['id']]),**agent_runtime(p)))
        try:
            self.command(['node',HARNESS,req,out],folder,j)
            from .review_result import validate_result
            result=validate_result(read(out))
        except (ReviewUnavailable,RuntimeError,ValueError,KeyError,TypeError,OSError) as error:
            # This boundary covers reviewer invocation/output only. Generation,
            # media integrity, STOP, pauses and persistence failures still stop.
            timeout=isinstance(error,ReviewUnavailable)
            message=str(error) if timeout else '视觉审核未完成，素材已保留供人工检查：'+str(error)[-1800:]
            with LOCK:
                if v.get('review'):v.setdefault('reviewHistory',[]).append(v['review'])
                v['review']=None
                v['reviewError']=dict(kind='timeout' if timeout else 'failed',message=message,at=time.time())
                self.persist_review(p,category,item,v)
            raise ReviewUnavailable(message) from error
        with LOCK:
            if v.get('review'): v.setdefault('reviewHistory',[]).append(v['review'])
            v.pop('reviewError',None)
            v['review']=result; self.persist_review(p,category,item,v)
        return v['review']
    def retry_limit(self,j):
        from .production import retry_limit
        return retry_limit(j.get('productionSettings',{}).get('maxRetries',1))
    def generate_review(self,p,category,item,j,existing=None):
        # Persist the retry cursor so pauses/restarts cannot reset the user's cap.
        limit=self.retry_limit(j);key=category+'/'+item['id']
        state=j.setdefault('retryStates',{}).setdefault(key,dict(attempt=0))
        while True:
            attempt=state['attempt']
            self.checkpoint(j)
            if existing is not None and attempt==0:
                v,folder=existing,self.store.folder/'runs'/j['id']/item['id']
            else:
                v,folder=self.asset(p,item,j,attempt) if category=='assets' else self.shot(p,item,j,attempt)
            if not j['autoReview']: return
            r=self.review(p,category,item,v,folder,j)
            if r['verdict']=='pass': return
            self.checkpoint(j)
            self.prepare_retry(p,category,item,v,r,j)
    def prepare_retry(self,p,category,item,v,r,j,persist=True):
        limit=self.retry_limit(j);key=category+'/'+item['id']
        state=j.setdefault('retryStates',{}).setdefault(key,dict(attempt=0))
        attempt=state['attempt']
        # Old persisted reviews used a nonempty revisedPrompt as their only action.
        action=r.get('retryAction','revise_prompt' if r.get('revisedPrompt','').strip() else 'none')
        if r['verdict']!='revise' or action=='none':raise QualityReviewRequired(item['name']+' 需要人工检查：'+r['summary'])
        if action not in ('revise_prompt','reroll'):raise QualityReviewRequired(item['name']+' 的重试决策无效，交人工检查')
        prompt=r.get('revisedPrompt','');views=r.get('revisedViewPrompts',[])
        if action=='revise_prompt' and (not isinstance(prompt,str) or not prompt.strip() or not isinstance(views,list) or len(views) not in (0,2) or any(not isinstance(x,str) or not x.strip() for x in views)):
            raise QualityReviewRequired(item['name']+' 的修订提示词无效，未提交')
        if action=='reroll' and (prompt or views):raise QualityReviewRequired(item['name']+' 的抽卡决策夹带提示词修改，未提交')
        if attempt>=limit:raise QualityReviewRequired(item['name']+f' 已达到最大重试次数 {limit}，仍未通过初筛，交人工检查')
        if category=='shots':
            attempts=budget(p)['ledger'].get('attempts',{}).get(item['id'],[])
            if len(attempts)>=2: raise QualityReviewRequired('该镜头两次提交额度已用完，保留结果供人工处理')
            candidate=copy.deepcopy(item)
            if action=='revise_prompt':candidate['prompt']=prompt
            if validate_shot(p,candidate): raise QualityReviewRequired('Agent 修订的参考标签不合法，未提交')
        before={k:item.get(k) for k in ('prompt','sidePrompt','backPrompt','seed')}
        item['history'].append(dict(**before,at=time.time(),reason='agent_revision',retryAction=action,retryReason=r.get('retryReason',r['summary'])))
        if action=='revise_prompt':
            item['prompt']=prompt
            if category=='assets' and views:item['sidePrompt'],item['backPrompt']=views
        item['seed']+=1
        state['attempt']=attempt+1
        j.setdefault('retryEvents',[]).append(dict(item=key,name=item['name'],attempt=attempt+1,maxRetries=limit,action=action,reason=r.get('retryReason',r['summary']),sourceVersion=v['id'],before=before,after={k:item.get(k) for k in before},at=time.time()))
        if persist:self.persist_item(p,category,item)
    def pending_review(self,j,item,reason,category='assets',persist=True):
        v=selected(item)
        field='pendingReviews' if category=='assets' else 'pendingShotReviews'
        with LOCK:
            rows=[r for r in j.get(field,[]) if r['id']!=item['id']]
            rows.append(dict(id=item['id'],name=item['name'],version=v['id'],reason=reason))
            j[field]=rows
            j['message']=item['name']+' 已保留供集中审核，继续制作其余'+('参考图' if category=='assets' else '分镜')
            if persist:self.save()
    def finish_reference_reviews(self,j,complete=False):
        if not j.get('pendingReviews'):return
        with LOCK:
            if complete:j['progress']=100
            j['stage']='manual_review'
            self.save()
        raise Human(f'参考图批量处理完成，{len(j["pendingReviews"])} 个资产待集中人工审核。请到参考图页面查看“待人工审核”；未开始后续分镜。')
    def finish_shot_reviews(self,j):
        if not j.get('pendingShotReviews'):return
        with LOCK:j['progress']=100;j['stage']='manual_review';self.save()
        raise Human(f'分镜批量处理完成，{len(j["pendingShotReviews"])} 个镜头待集中人工审核。视频已保留，请到分镜制作查看。')
    def execute(self,j,dispatch=False):
        if j['kind']=='lab':
            from .lab import execute
            return execute(self,j)
        p=j['snapshot']; kind=j['kind']
        if kind=='dependencies':
            from .assets import apply_dependencies
            folder=self.store.folder/'runs'/j['id'];folder.mkdir(parents=True,exist_ok=True)
            source=next((s for s in reversed(p['sources']) if s.get('role')=='references'),None)
            write(folder/'input.json',dict(source=source,assets=[{k:a.get(k) for k in ('id','name','prompt','description','aliases')} for a in p['assets']],**agent_runtime(p)))
            self.command(['node',APP/'agent/reference-dependencies.mjs',folder/'input.json',folder/'output.json'],folder,j)
            result=read(folder/'output.json');apply_dependencies(p,result['assets'])
            with LOCK:
                live=self.store.get(p['id']);apply_dependencies(live,result['assets']);live['dependencyReport']=result;self.store.save(live)
            return
        if kind=='parse':
            from .importer import apply_parse,import_source
            folder=self.store.folder/'runs'/j['id']; folder.mkdir(parents=True,exist_ok=True)
            source=import_source(p['sources']) if p['sources'] else None
            if not source: raise ValueError('没有可解析的原始文档')
            self.update(j,('Codex 订阅' if agent_provider(p)=='codex' else 'DeepSeek')+' 正在解析原文、资产和镜头对应关系')
            payload=dict(text=source['text'],filename=source['name'],source=source,**agent_runtime(p))
            cached=read(folder/'parse-output.json') if (folder/'parse-output.json').exists() else {}
            compatible=cached.get('sourceSha256')==hashlib.sha256(source['text'].encode()).hexdigest() and cached.get('provider','deepseek')==agent_provider(p) and (agent_provider(p)!='deepseek' or cached.get('thinking')=='max') and (agent_provider(p)!='codex' or (cached.get('requestedModel')==p.get('agentModel','gpt-5.6-sol') and cached.get('thinking')==p.get('agentThinking','high')))
            valid=False
            compatible=compatible and all('referenceAssetIds' in asset for asset in cached.get('assets',[]))
            if compatible:
                try:apply_parse(copy.deepcopy(p),source,cached);valid=True
                except (ValueError,KeyError,TypeError,IndexError):
                    payload['repairCandidate']=cached
                    write(folder/('parse-before-repair-'+str(time.time_ns())+'.json'),cached)
            write(folder/'parse-input.json',payload)
            if not valid:
                self.command(['node',APP/'agent/parse-storyboard.mjs',folder/'parse-input.json',folder/'parse-output.json'],folder,j)
            self.event(j,dict(type='director.progress',stage='save',event='started'))
            apply_parse(p,source,read(folder/'parse-output.json'))
            with LOCK:
                live=self.store.get(p['id'])
                for key in ('assets','shots','importReport'):live[key]=p[key]
                self.store.save(live)
            self.event(j,dict(type="director.progress",stage="save",event="completed"))
            return
        if kind=='preflight': return self.shot(p,next(s for s in p['shots'] if s['id']==j['target']),j,preflight=True)
        if kind=='export': return self.export(p,j)
        if kind=='review':
            for category in ('assets','shots'):
                item=next((x for x in p[category] if x['id']==j['target']),None)
                if item:
                    v=selected(item)
                    if not v: raise ValueError('没有可审查的版本')
                    return self.review(p,category,item,v,self.store.folder/'runs'/j['id'],j)
            raise ValueError('素材不存在')
        todo=[]
        if kind=='shots_auto':
            from .production import require_references
            require_references(p,[s for s in p['shots'] if not selected(s)])
        if kind=='asset': todo=[('assets',next(a for a in p['assets'] if a['id']==j['target']))]
        elif kind=='shot': todo=[('shots',next(s for s in p['shots'] if s['id']==j['target']))]
        elif kind=='assets_auto':todo=[('assets',a) for a in ordered_assets(p)]
        elif kind=='shots_auto':todo=[('shots',s) for s in p['shots']]
        elif kind=='shot_auto':
            s=next(s for s in p['shots'] if s['id']==j['target'])
            todo=[('assets',a) for a in ordered_assets(p,[next(a for a in p['assets'] if a['id']==key) for key in s['refs']])]+[('shots',s)]
        else:
            todo=[('assets',a) for a in ordered_assets(p)]+[('shots',s) for s in p['shots']]
        if dispatch and any(category=='shots' for category,item in todo):
            from .async_shots import schedule,Deferred
            # References keep their existing approval gate; videos hand off to two lanes.
            asset_todo=[row for row in todo if row[0]=='assets']
        else:asset_todo=todo
        for category,item in asset_todo:
            if category=='shots':self.finish_reference_reviews(j)
            key=category+'/'+item['id']
            if key in j['done']: continue
            self.checkpoint(j)
            v=selected(item)
            defer=(category=='assets' and kind in ('auto','shot_auto','assets_auto')) or (category=='shots' and kind in ('auto','shots_auto'))
            regenerate=category=='assets' and kind=='assets_auto' and j.get('productionSettings',{}).get('regenerateAssets',False)
            if defer and v and not regenerate and key not in j.get('retryStates',{}):
                if not v.get('humanAccepted') and (v.get('review') or {}).get('verdict')!='pass':
                    self.pending_review(j,item,'已有素材继续保留，请集中审核；需要重做时单独生成新版本',category)
                with LOCK:
                    j['done'].append(key);j['progress']=round(90*len(j['done'])/max(1,len(todo)));self.save()
                continue
            try:
                if not regenerate and kind in ('auto','shot_auto','assets_auto','shots_auto') and v and current(p,category,item):
                    if j['autoReview'] and not v.get('humanAccepted') and (v.get('review') or {}).get('verdict')!='pass':
                        self.generate_review(p,category,item,j,existing=v)
                else: self.generate_review(p,category,item,j)
            except QualityReviewRequired as error:
                if not defer:raise
                self.pending_review(j,item,str(error),category)
            if defer and not j['autoReview'] and selected(item) and not selected(item).get('humanAccepted') and (selected(item).get('review') or {}).get('verdict')!='pass':
                self.pending_review(j,item,'未开启自动初筛，请人工检查当前版本',category)
            with LOCK:
                j['done'].append(key); j['progress']=round(90*len(j['done'])/max(1,len(todo))); self.save()
        if dispatch and any(category=='shots' for category,item in todo):
            self.finish_reference_reviews(j)
            if schedule(self,j,[item for category,item in todo if category=='shots']):raise Deferred()
        self.checkpoint(j)
        self.finish_reference_reviews(j,complete=kind=='assets_auto')
        self.finish_shot_reviews(j)
        if kind=='auto': self.export(p,j)
    def export(self,p,j):
        self.update(j,'整理 Trae 剪辑交接包')
        from .handoff import export_paths
        with LOCK:
            paths=export_paths(self.store.folder/'exports',p,j)
            self.save()
        folder=Path(paths['folder'])
        rows=[]; missing=[]
        for s in p['shots']:
            v=selected(s)
            if not v: missing.append(s['name']); continue
            source=Path(v['files'][0]['path'])
            if digest(source)!=v['files'][0]['sha256']: raise ValueError('源素材哈希已改变：'+s['name'])
            dest=folder/'media'/(s['id']+source.suffix); dest.parent.mkdir(exist_ok=True); shutil.copy2(source,dest)
            rows.append(dict(shot=s['id'],name=s['name'],media='media/'+dest.name,sha256=digest(dest),requestedSeconds=s['seconds'],
                             information=s['info'],prompt=v['prompt'],originalPrompt=s.get('originalPrompt',''),version=v['id'],
                             review=v.get('review'),reviewError=v.get('reviewError'),humanAccepted=v.get('humanAccepted',False)))
        from .handoff import write_handoff
        manifest=write_handoff(folder,p,rows,missing,delivery_root=paths['deliveryRoot'])
        archive=Path(paths['archive'])
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for f in folder.rglob('*'):
                if f.is_file(): z.write(f,f.relative_to(folder))
        with LOCK:
            live=self.store.get(p['id'])
            record=dict(id=j['id'],path=str(archive),folder=str(folder),created=time.time(),shots=len(rows),missing=missing,delivery=manifest['delivery'])
            live['exports']=[e for e in live['exports'] if e['id']!=j['id']]+[record]
            self.store.save(live)
