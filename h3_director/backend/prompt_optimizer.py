"""Explicit DeepSeek prompt proposals; never submits video or changes a campaign."""
import copy
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time

from .project import LOCK,uid,read,write,selected
from .paths import APP,ROOT

SECTIONS=('subject_definitions','summary','retention_analysis','detailed_description','overall_soundscape','non_diegetic_music')
SKILL=APP/'agent/skills/h3-prompt-writing'

def complete(fields):
    return fields['prompt'] if 'soundscape' not in fields else fields['prompt'].rstrip()+'\noverall_soundscape:\n'+fields['soundscape']+'\nnon_diegetic_music:\n'+fields['music']

def validate_candidate(text,source):
    if not isinstance(text,str) or not 20<len(text)<=50000:raise ValueError('优化提示词为空或过长')
    matches=list(re.finditer(r'(?m)^\s*('+'|'.join(SECTIONS)+r')\s*:\s*',text))
    if [m[1] for m in matches]!=list(SECTIONS) or text[:matches[0].start()].strip():raise ValueError('优化结果未按官方六段结构输出')
    sections={m[1]:text[m.end():matches[i+1].start() if i+1<len(matches) else len(text)].strip() for i,m in enumerate(matches)}
    if not all(sections.values()):raise ValueError('优化结果存在空 section')
    for tag in ('Picture','Audio','Video'):
        found={int(x) for x in re.findall(r'<'+tag+r'\s+(\d+)>',text)}
        expected={i+1 for i,r in enumerate(source['context'].get(tag,[]))}
        if found!=expected:raise ValueError(tag+' 标签与原参考素材不一致')
    original=complete(source['fields'])
    dialogue=lambda t:re.findall(r'<d>(.*?)</d>',t,re.S)
    old=dialogue(original);new=dialogue(text)
    if old and old!=new:raise ValueError('优化结果改动、遗漏或重复了原台词，未采用')
    if dialogue(sections['overall_soundscape']+sections['non_diegetic_music']):raise ValueError('台词只能写在 detailed_description 中')
    from .lab_templates import prompt_issues
    body='\n\n'.join(k+':\n'+sections[k] for k in SECTIONS[:4])
    issues=prompt_issues(dict(prompt=body,soundscape=sections['overall_soundscape'],music=sections['non_diegetic_music']))
    if issues:raise ValueError('优化结果存在冲突：'+'；'.join(issues))
    return dict(prompt=body,soundscape=sections['overall_soundscape'],music=sections['non_diegetic_music'])

class PromptOptimizer:
    def __init__(self,runner,start=True):
        self.runner=runner;self.folder=runner.store.folder/'prompt-optimizations';self.start=start
        self.slots=threading.Semaphore(1)
        for path in self.folder.glob('*/proposal.json'):
            record=read(path)
            if record['status'] in ('queued','running'):
                record.update(status='failed',error='服务重启中断优化；原提示词未改动，可手动重新优化。');write(path,record)
    def path(self,key):
        if not isinstance(key,str) or not re.fullmatch('[a-f0-9]{12}',key):raise ValueError('优化记录 ID 无效')
        return self.folder/key/'proposal.json'
    def source(self,scope,owner,target):
        if scope=='project':
            p=self.runner.store.get(owner);item=next(s for s in p['shots'] if s['id']==target)
            refs=[]
            for key in item['refs']:
                a=next(a for a in p['assets'] if a['id']==key);v=selected(a)
                refs.append(dict(id=key,name=a['name'],description=a.get('description',''),prompt=a['prompt'],
                                 sha256=(v.get('files') or [{}])[0].get('sha256') if v else None))
            return dict(fields={'prompt':item['prompt']},context=dict(seconds=item['seconds'],Picture=refs,Audio=[],Video=[],information=item.get('info','')),revision=p['revision']),p,item
        if scope=='lab' and target=='shot':
            p=self.runner.lab.get(owner)
            fields={k:copy.deepcopy(p[k]) for k in ('prompt','soundscape','music','promptLanguage','promptVariants')}
            context=dict(seconds=p['settings']['seconds'],Picture=[{k:r.get(k) for k in ('id','label','sha256')} for r in p['references']],
                         Audio=[{k:r.get(k) for k in ('id','label','sha256')} for r in p['audioReferences']],Video=[])
            return dict(fields=fields,context=context,revision=p['revision']),p,p
        raise ValueError('不支持的提示词来源')
    def listing(self,scope,owner,target):
        self.source(scope,owner,target)
        rows=[read(p) for p in self.folder.glob('*/proposal.json')]
        return sorted([r for r in rows if (r['scope'],r['owner'],r['target'])==(scope,owner,target)],key=lambda r:r['created'],reverse=True)
    def create(self,data):
        scope,owner,target=(data.get(k) for k in ('scope','owner','target'))
        source,_,_=self.source(scope,owner,target)
        if source['revision']!=data.get('revision'):raise ValueError('内容已更新，请刷新或保存后再优化')
        if not source['fields']['prompt'].strip():raise ValueError('请先填写提示词')
        language=data.get('language','zh')
        if language not in ('zh','en'):raise ValueError('正文语言无效')
        if any(r['status'] in ('queued','running') for r in self.listing(scope,owner,target)):raise ValueError('当前分镜已有优化任务，请等待结果')
        provenance=read(SKILL/'source.json')
        guides={name:(SKILL/name).read_bytes() for name in provenance['files']}
        for name,entry in provenance['files'].items():
            if hashlib.sha256(guides[name]).hexdigest()!=entry['sha256']:raise ValueError('官方 skill 文件校验失败')
        record=dict(id=uid(),scope=scope,owner=owner,target=target,created=time.time(),status='queued',source=source,
                    language=language,skill=provenance,provider='deepseek')
        for name,content in guides.items():
            target_file=self.path(record['id']).parent/'skill'/name
            target_file.parent.mkdir(parents=True,exist_ok=True);target_file.write_bytes(content)
        write(self.path(record['id']),record)
        if self.start:threading.Thread(target=self.run,args=(record['id'],),daemon=True).start()
        return record
    def invoke(self,record):
        folder=self.path(record['id']).parent
        write(folder/'input.json',dict(**record['source'],language=record['language'],agentProvider='deepseek'))
        env={k:v for k,v in os.environ.items() if 'API_KEY' not in k}
        with (folder/'process.log').open('w',encoding='utf-8') as log:
            proc=subprocess.Popen(['node',str(APP/'agent/optimize-prompt.mjs'),str(folder/'input.json'),str(folder/'output.json')],
                                  cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:code=proc.wait(timeout=240)
            except subprocess.TimeoutExpired:
                import psutil
                try:
                    children=psutil.Process(proc.pid).children(recursive=True)
                    for child in children:
                        try:child.terminate()
                        except psutil.NoSuchProcess:pass
                finally:proc.kill();proc.wait()
                raise ValueError('DeepSeek 优化超时，原提示词未改动，可稍后重试')
        if code:raise ValueError('DeepSeek 优化失败，原提示词未改动；请检查 API 配置和优化记录 process.log')
        return read(folder/'output.json')
    def run(self,key):
        with self.slots:
            with LOCK:
                record=read(self.path(key));record['status']='running';write(self.path(key),record)
            try:
                result=self.invoke(record);parts=validate_candidate(result.get('prompt'),record['source'])
                before=record['source']['fields'];after=copy.deepcopy(before)
                if record['scope']=='project':after['prompt']=result['prompt'].strip()
                else:
                    after.update(parts);after['promptLanguage']=record['language']
                    after.setdefault('promptVariants',{})[record['language']]=copy.deepcopy(parts)
                if any(not isinstance(result.get(k),list) or any(not isinstance(x,str) for x in result[k]) for k in ('changes','warnings')):raise ValueError('优化说明格式无效')
                record.update(status='ready',candidate=after,changes=result['changes'],warnings=result['warnings'],
                              model=result.get('model'),usage=result.get('usage'),
                              diff=list(difflib.unified_diff(complete(before).splitlines(),complete(after).splitlines(),fromfile='优化前',tofile='优化后',lineterm='')))
            except Exception as e:record.update(status='failed',error=str(e))
            with LOCK:record['finishedAt']=time.time();write(self.path(key),record)
    def apply(self,key,rollback=False):
        record=read(self.path(key));source,p,item=self.source(record['scope'],record['owner'],record['target'])
        expected=record.get('candidate') if rollback else record['source']['fields']
        if record['status']!=('applied' if rollback else 'ready'):raise ValueError('当前优化记录不支持此操作')
        if source['fields']!=expected or source['context']!=record['source']['context']:
            raise ValueError('提示词、时长或参考素材已改变，未覆盖后续修改；请先比较历史内容')
        if record['scope']=='project' and not self.runner.can_edit(p['id'],'shot',item['id']):raise ValueError('当前流程正在使用此分镜，请完成后再采用或回退')
        fields=record['source']['fields'] if rollback else record['candidate']
        item.setdefault('promptOptimizationHistory',[]).append(dict(id=key,action='rollback' if rollback else 'apply',
                    at=time.time(),before=copy.deepcopy(source['fields']),after=copy.deepcopy(fields)))
        item.update(copy.deepcopy(fields))
        (self.runner.store.save if record['scope']=='project' else self.runner.lab.save)(p)
        record.update(status='rolled_back' if rollback else 'applied',changedAt=time.time());write(self.path(key),record)
        return record

def route(handler,parts,data=None):
    service=handler.server.runner.optimizer
    if data is None and len(parts)==5:return handler.respond(service.listing(*parts[2:]))
    if data is not None and len(parts)==2:return handler.respond(service.create(data),202)
    if data is not None and len(parts)==4 and parts[3] in ('apply','rollback'):
        return handler.respond(service.apply(parts[2],parts[3]=='rollback'))
    raise ValueError('优化接口不存在')
