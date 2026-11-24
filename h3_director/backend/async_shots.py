"""Persisted GPU FIFO and three independent video-review workers.

Each task belongs to its original job/campaign and retains its attempt directory.
No worker submits directly: GPU work still calls Runner.shot -> h3_batch.py.
All dispatch decisions and state transitions hold the shared store lock.
"""
import copy
import time
from pathlib import Path
from .project import LOCK, selected, current, uid
from .runner import Paused, Stop, Human, QualityReviewRequired, budget, shot_signature

REVIEW_WORKERS = 3
TERMINAL = {'success','failed','STOP','needs_review','cancelled'}


class Deferred(Exception):
    pass


def recover(runner):
    for job in runner.jobs:
        if 'shotTasks' not in job:continue
        for task in job['shotTasks']:
            task.pop('pid',None)
            if task['status']=='running':
                if job['status'] in TERMINAL:
                    if task['phase']=='review':
                        task.update(status='cancelled',message='服务重启；所属任务已停止，未完成检测可单独重审')
                        continue
                    job['recoveryTerminal']=job['status']
                    job.update(status='interrupted',message='已停止任务仍有未确认的生成，请先对账；STOP 预算不自动恢复')
                task['status']='queued'
                task['reconcile']=True
        # Interrupted parent remains a global dispatch barrier until explicit resume.


def append_task(job,item,phase='generate',version=None,folder=None):
    attempt=job.setdefault('retryStates',{}).setdefault('shots/'+item['id'],dict(attempt=0))['attempt']
    task=dict(id=uid(),target=item['id'],name=item['name'],attempt=attempt,phase=phase,
              status='queued',ticket=time.time_ns(),created=time.time(),message='等待生成' if phase=='generate' else '等待 Agent 检测')
    if version:task['version']=version['id']
    if folder:task['folder']=str(folder)
    job['shotTasks'].append(task)
    return task


def schedule(runner,job,shots):
    with LOCK:
        if 'shotTasks' in job:
            return any(t['status'] in ('queued','running') for t in job['shotTasks'])
        runner.checkpoint(job)
        # Build the whole plan off to the side: pending_review saves must not publish
        # a partial shot list if the process exits during batch expansion.
        persisted_job=job;job=copy.deepcopy(job)
        job['shotTasks']=[];job['reviewConcurrency']=REVIEW_WORKERS
        p=job['snapshot'];kind=job['kind']
        for item in shots:
            key='shots/'+item['id']
            if key in job['done']:continue
            v=selected(item)
            if kind in ('auto','shots_auto') and v and key not in job.get('retryStates',{}):
                if not v.get('humanAccepted') and (v.get('review') or {}).get('verdict')!='pass':
                    # This job is an unpublished copy. Persist the whole expansion
                    # once below, instead of rewriting all historic snapshots per clip.
                    runner.pending_review(job,item,'已有素材继续保留，请集中审核；需要重做时单独生成新版本','shots',persist=False)
                job['done'].append(key)
                continue
            # A resumed legacy retry must reuse its persisted attempt, not skip it.
            state=job.get('retryStates',{}).get(key,{})
            if kind=='shot_auto' and v and current(p,'shots',item) and not state.get('attempt'):
                if job['autoReview'] and not v.get('humanAccepted') and (v.get('review') or {}).get('verdict')!='pass':
                    append_task(job,item,'review',v,runner.store.folder/'runs'/job['id']/item['id'])
                else:job['done'].append(key)
            else:append_task(job,item)
        job['stage']='parallel_shots'
        # Expansion preserves the parent's FIFO position. Only retries get a new tail ticket.
        for index,task in enumerate(job['shotTasks']):task['ticket']=int(job['created']*1e9)+index
        job['message']='视频按队列生成；Agent 检测并行运行，重试追加队尾'
        persisted_job.update(job)
        runner.save()
        return bool(job['shotTasks'])


def context(job,task):
    # Process IDs, logs and SDK events belong to the task, never a sibling worker.
    return {**job,'_parent':job,'_task':task}


def summary(job):
    tasks=job['shotTasks']
    counts={phase:{status:sum(t['phase']==phase and t['status']==status for t in tasks)
                   for status in ('queued','running')} for phase in ('generate','review')}
    job['queueSummary']=counts
    job['message']=(f"视频生成 {counts['generate']['running']} 个进行中 / {counts['generate']['queued']} 个排队；"
                    f"Agent 检测 {counts['review']['running']} 个进行中 / {counts['review']['queued']} 个排队")


def settle(runner,job):
    summary(job)
    active=any(t['status']=='running' for t in job['shotTasks'])
    pending=any(t['status']=='queued' for t in job['shotTasks'])
    if job['status'] in TERMINAL:return
    if job.get('cancelRequested'):
        if not active:job.update(status='cancelled',message='已取消后续步骤，已生成素材与已返回审核结果保留',finishedAt=time.time())
        else:job['message']='正在取消后续任务；等待已开始的生成与检测结束并保存结果'
    elif job.get('paused'):
        if not active:job.update(status='paused',message='已暂停后续生成与检测，可继续原任务')
        else:job['message']='正在暂停；等待已开始的生成与检测结束，不再派发后续任务'
    elif not active and not pending:
        # Finish/export is serialized with normal jobs; completion waits for every review/retry.
        job['status']='queued'
        job['message']='生成与检测已结束，正在汇总结果'


def complete_item(runner,job,item):
    key='shots/'+item['id']
    if key not in job['done']:job['done'].append(key)
    total=len({t['target'] for t in job['shotTasks']})
    done=sum('shots/'+target in job['done'] for target in {t['target'] for t in job['shotTasks']})
    job['progress']=round(90*done/max(1,total))


def stop_job(runner,job,status,message):
    job.update(status=status,message=message,finishedAt=time.time())
    for task in job.get('shotTasks',[]):
        if task['status']=='queued':task.update(status='cancelled',message='所属任务已停止；不再自动提交')


def choose(runner,lane):
    # Enforce one GPU and a bounded reviewer pool even for manual run_once callers.
    running_tasks=[t for j in runner.jobs for t in j.get('shotTasks',[]) if t['status']=='running']
    running_jobs=[j for j in runner.jobs if j['status']=='running' and 'shotTasks' not in j]
    if lane=='gpu' and (any(t['phase']=='generate' for t in running_tasks) or any(j['kind']!='review' for j in running_jobs)):return None
    if lane=='review' and (sum(t['phase']=='review' for t in running_tasks)+sum(j['kind']=='review' for j in running_jobs)>=REVIEW_WORKERS):return None
    if any(j['status']=='interrupted' for j in runner.jobs):return None
    choices=[]
    for job in runner.jobs:
        if job['status']=='queued' and ((job['kind']=='review')==(lane=='review')):
            choices.append((int(job['created']*1e9),job,None))
        if job['status'] not in ('running','queued') or job.get('paused') or job.get('cancelRequested'):continue
        for task in job.get('shotTasks',[]):
            if task['status']=='queued' and ((task['phase']=='review')==(lane=='review')):
                choices.append((task['ticket'],job,task))
    if not choices:return None
    _,job,task=min(choices,key=lambda x:x[0])
    job['status']='running';job.setdefault('startedAt',time.time());job.pop('finishedAt',None)
    if task:
        task.update(status='running',startedAt=time.time(),message='正在生成视频' if task['phase']=='generate' else 'Agent 检测进行中');summary(job)
    runner.save()
    return job,task


def run_once(runner,lane):
    with LOCK:chosen=choose(runner,lane)
    if chosen is None:return False
    job,task=chosen
    if task:
        run_task(runner,job,task)
        return True
    try:
        runner.execute(job,dispatch=True)
        with LOCK:
            job.update(status='success',progress=100)
            if job['kind']!='lab':job['message']='执行完成；视觉初筛与人工验收分别记录'
    except Deferred:
        with LOCK:settle(runner,job)
    except Paused:
        with LOCK:job.update(status='paused',message='已暂停后续步骤，可原任务继续')
    except Stop as e:
        with LOCK:stop_job(runner,job,'STOP',str(e))
    except Human as e:
        with LOCK:stop_job(runner,job,'needs_review',str(e))
    except Exception as e:
        with LOCK:stop_job(runner,job,'failed',str(e)[-1800:])
    with LOCK:
        if job['status'] in TERMINAL:job['finishedAt']=time.time()
        runner.save()
    return True


def retry_is_current(runner,job,item,version):
    live=runner.store.get(job['projectId'])
    # Enqueue freezes the current recipe even for projects saved before videoProfile existed.
    live['videoProfile']=job['snapshot'].get('videoProfile')
    latest=next((s for s in live['shots'] if s['id']==item['id']),None)
    if not latest or latest.get('selected')!=version['id'] or shot_signature(live,item['id'])!=shot_signature(job['snapshot'],item['id']):
        raise QualityReviewRequired('镜头或参考素材已更新，旧版本检测结果已保留；不自动覆盖或重生成')
    # A newer explicitly queued take takes precedence over an old review's retry.
    if any(j['id']!=job['id'] and j['projectId']==job['projectId'] and j['status'] in ('queued','running','paused','interrupted')
           and j.get('target')==item['id'] and j['kind'] in ('shot','shot_auto') for j in runner.jobs):
        raise QualityReviewRequired('此镜头已有其他生成任务，旧版本检测不再追加重试')


def run_task(runner,job,task):
    p=job['snapshot'];item=next(s for s in p['shots'] if s['id']==task['target']);ctx=context(job,task)
    try:
        if task['phase']=='generate':
            runner.checkpoint(ctx)
            if budget(p)['stop']:raise Stop('生产执行器已 STOP：'+budget(p)['stopPath'])
            # Retry inputs may have been edited while this task waited at the FIFO tail.
            if task['attempt']:
                with LOCK:retry_is_current(runner,job,item,selected(item))
            v,folder=runner.shot(p,item,ctx,task['attempt'])
            with LOCK:
                task.update(version=v['id'],folder=str(folder),finishedAt=time.time())
                if job['autoReview'] and not job.get('cancelRequested') and job['status'] not in TERMINAL:
                    task.update(phase='review',status='queued',ticket=time.time_ns(),message='生成完成，等待 Agent 检测')
                else:
                    task['status']='success';complete_item(runner,job,item)
                    if not job['autoReview'] and job['kind'] in ('auto','shots_auto'):
                        runner.pending_review(job,item,'未开启自动初筛，请人工检查当前版本','shots')
        else:
            v=next(v for v in item['versions'] if v['id']==task['version'])
            result=runner.review(p,'shots',item,v,Path(task['folder']),ctx)
            with LOCK:
                task.update(status='success',message='Agent 检测完成',finishedAt=time.time())
                if job.get('cancelRequested') or job['status'] in TERMINAL:pass
                elif result['verdict']=='pass':complete_item(runner,job,item)
                else:
                    if budget(p)['stop']:raise Stop('生产执行器已 STOP：'+budget(p)['stopPath'])
                    retry_is_current(runner,job,item,v)
                    runner.prepare_retry(p,'shots',item,v,result,job,persist=False)
                    retry=append_task(job,item)
                    retry['message']='Agent 建议重生成，已追加生成队列末尾'
                    task['retryTask']=retry['id']
                    task['message']='检测要求重生成，重试已追加生成队尾'
                    # Persist the incremented cursor together with its queued successor.
                    runner.persist_item(p,'shots',item)
    except QualityReviewRequired as error:
        with LOCK:
            task.update(status='needs_review',message=str(error),finishedAt=time.time())
            if job['status'] not in TERMINAL and not job.get('cancelRequested'):
                runner.pending_review(job,item,str(error),'shots');complete_item(runner,job,item)
    except Paused:
        with LOCK:task['status']='queued'
    except Exception as error:
        with LOCK:
            task.update(status='failed',message=str(error)[-1800:],finishedAt=time.time())
            # A late reviewer error cannot downgrade a production STOP from another worker.
            if isinstance(error,Stop) or job['status'] not in TERMINAL:
                stop_job(runner,job,'STOP' if isinstance(error,Stop) else 'needs_review' if isinstance(error,Human) else 'failed',str(error)[-1800:])
    finally:
        with LOCK:
            terminal_message=job['message'] if job['status'] in TERMINAL else None
            settle(runner,job)
            if terminal_message is not None:job['message']=terminal_message
            runner.save()


def control(runner,job,action):
    if action=='pause' and job['status'] in ('queued','running'):
        job['paused']=True
        settle(runner,job)
    elif action=='cancel' and job['status'] in ('queued','running','paused'):
        job['cancelRequested']=True;job['paused']=True
        for task in job['shotTasks']:
            if task['status']=='queued':task.update(status='cancelled',message='已取消后续步骤')
        settle(runner,job)
    elif action=='resume' and job['status'] in ('paused','interrupted') and not job.get('cancelRequested'):
        if budget(job['snapshot'])['stop']:raise ValueError('STOP 不可自动恢复')
        from .runner import queue_compatible
        others=[j for j in runner.pending(job['projectId']) if j['id']!=job['id']]
        if not queue_compatible(others,job['kind']):raise ValueError('此项目已有其他流程或待对账任务')
        live=runner.store.get(job['projectId'])
        for key in ('agentProvider','agentModel','agentThinking'):
            if key in live:job['snapshot'][key]=live[key]
        job['paused']=False;job['status']='running'
        settle(runner,job)
    else:raise ValueError('当前状态不支持此操作')
    runner.save()
    return job
