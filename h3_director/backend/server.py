"""Loopback-only API and static server. No arbitrary path or command endpoints."""
import argparse
import base64
import copy
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import time
from urllib.parse import urlparse,unquote
from .project import ROOT,LOCK,Store,uid,read,write,digest,selected,make_asset,parse_storyboard,validate_shot,current
from .runner import Runner,budget,queue,owns_item,shot_clear_targets
from .paths import APP,DATA
from .agent import provider as agent_provider,selection as agent_selection,catalog as agent_catalog

SAMPLE=ROOT/'原创项目/对面/对面-Seedance分镜脚本(信息修订版).md'
DEMO_MANIFEST=ROOT/'runs/white_reference_demo/manifest.json'

def library():
    paths=sorted(set((ROOT/'原创项目/候选剧本').glob('*.md'))|{p for p in (ROOT/'原创项目').rglob('*.md') if 'seedance' in p.name.lower() or '参考图' in p.name})
    return [{'id':str(i),'name':p.name,'path':p,'role':'references' if '参考图' in p.name else 'storyboard'} for i,p in enumerate(paths) if p.is_file()]

def read_documents(documents):
    if not 1<=len(documents)<=2:raise ValueError('请选择参考图和分镜两个文档')
    docs=[]
    for entry in documents:
        role=entry['role']
        if role not in ('references','storyboard'):raise ValueError('文档用途无效')
        if any(s['role']==role for s in docs):raise ValueError('同一用途只能选择一份文档')
        if entry.get('libraryId') is not None:
            src=next(x for x in library() if x['id']==entry['libraryId']); text=src['path'].read_text(encoding='utf-8-sig');name=src['name']
        else:text=str(entry.get('text',''));name=Path(entry.get('filename','文档.md')).name
        if not text.strip():raise ValueError('文档为空')
        docs.append(dict(id=uid(),name=name,text=text,role=role))
    return docs


def public_project(p):
    p=copy.deepcopy(p)
    p.setdefault('agentProvider','deepseek')
    from .production import VIDEO_PROFILE,selected_profile
    p['defaultVideoProfile']=VIDEO_PROFILE
    p['videoProfile']=selected_profile(p)
    for k,v in agent_selection(p).items():p.setdefault(k,v)
    for category in ('assets','shots'):
        for item in p[category]:
            if category=='assets':
                for f in item.get('inputs',[]): f['url']=f'/api/inputs/{p["id"]}/{item["id"]}/{f["id"]}'
            item['stale']=bool(selected(item)) and not current(p,category,item)
            for v in item['versions']:
                for i,f in enumerate(v['files']): f['url']=f'/api/media/{p["id"]}/{category}/{item["id"]}/{v["id"]}/{i}'
                if category=='assets':
                    for i,f in enumerate(v.get('inputReferences',[])):f['url']=f'/api/reference-input/{p["id"]}/{item["id"]}/{v["id"]}/{i}'
                    if v.get('editMaskReference'):v['editMaskReference']['url']=f'/api/edit-mask/{p["id"]}/{item["id"]}/{v["id"]}'
            if category=='shots': item['errors']=validate_shot(p,item)
    p['budget']=budget(p)
    from .production import reference_readiness
    p['referenceReadiness']=reference_readiness(p,[s for s in p['shots'] if not selected(s)])
    for shot in p['shots']:shot['referenceReadiness']=reference_readiness(p,[shot])
    for e in p['exports']: e['url']=f'/api/exports/{p["id"]}/{e["id"]}'
    return p

def demo(store,reuse=False):
    reuse=reuse and DEMO_MANIFEST.is_file()
    p=store.create('温室 · 最小路径验证' if not reuse else '温室 · 已有素材体验')
    cfg=read(ROOT/'configs/three-white-references.json')
    for st in cfg['stages']:
        kind='character' if st['name']=='character_front' else st['name']
        a=make_asset({'character':'温室研究员','scene':'清晨温室','prop':'黄铜提灯'}[kind],kind,st['name'])
        a['prompt']=(ROOT/st['prompt_file']).read_text(encoding='utf-8-sig'); a['seed']=st['seed']; p['assets'].append(a)
    source=(ROOT/cfg['video']['prompt_file']).read_text(encoding='utf-8-sig')
    p['shots']=[dict(id='s001',name='提起灯，稍停，放回',scene='清晨温室',seconds=10,seed=20260922,width=1344,height=768,
                    originalPrompt=source,prompt=source,refs=[a['id'] for a in p['assets']],info='研究员提起黄铜灯后放回桌面',warnings=[],versions=[],selected=None,history=[])]
    p['sources']=[dict(id=uid(),name='温室-验证分镜.md',text='# 温室最小路径\n\n'+source)]
    if reuse:
        m=read(DEMO_MANIFEST)
        for a in p['assets']:
            f=m['assets'][a['id']]; version=dict(id=uid(),created=time.time(),files=[dict(label=a['id'],**f)],prompt=a['prompt'],seed=a['seed'],review=None,humanAccepted=False,record=str(DEMO_MANIFEST),imported=True)
            a['versions'].append(version); a['selected']=version['id']
        s=p['shots'][0]; v=dict(id=uid(),created=time.time(),files=[dict(label='video',**m['video'])],prompt=source,seed=s['seed'],review=None,humanAccepted=False,
                              references=[dict(path=m['assets'][a['id']]['path'],sha256=m['assets'][a['id']]['sha256']) for a in p['assets']],imported=True)
        s['versions'].append(v); s['selected']=v['id']
    store.save(p); return p

class Handler(BaseHTTPRequestHandler):
    server_version='H3Director/0.1'
    def log_message(self,*args): pass
    def respond(self,value,status=200):
        data=json.dumps(value,ensure_ascii=False).encode(); self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(data)
    def do_GET(self): self.handle_request(False)
    def do_POST(self): self.handle_request(True)
    def handle_request(self,post):
        try:
            host=self.headers.get('Host','').split(':')[0]
            if host not in ('127.0.0.1','localhost'): return self.respond({'error':'仅允许本机访问'},403)
            parts=unquote(urlparse(self.path).path).strip('/').split('/')
            if post:
                origin=self.headers.get('Origin')
                if origin and origin not in (f'http://{self.headers.get("Host")}', 'http://127.0.0.1:5178','http://localhost:5178'):
                    return self.respond({'error':'跨站请求被拒绝'},403)
                if self.headers.get('Content-Type','').split(';')[0]!='application/json': return self.respond({'error':'需 application/json'},415)
                size=int(self.headers.get('Content-Length','0'))
                if size>160*1024*1024: return self.respond({'error':'文件过大'},413)
                data=json.loads(self.rfile.read(size) or '{}')
                with LOCK: return self.mutate(parts,data)
            if parts[:2]==['api','lab']:
                from .lab import get
                with LOCK:return get(self,parts)
            if parts[:2]==['api','prompt-optimizations']:
                from .prompt_optimizer import route
                with LOCK:return route(self,parts)
            if parts==['api','codex','usage']:
                from .codex_bridge import usage
                return self.respond(usage())
            if parts==['api','codex','models']:
                return self.respond({'models':agent_catalog()})
            if len(parts)==5 and parts[:2]==['api','inputs']:
                p=self.server.store.get(parts[2]); a=next(a for a in p['assets'] if a['id']==parts[3])
                f=next(f for f in a.get('inputs',[]) if f['id']==parts[4]); return self.send_file(Path(f['path']))
            if parts[:2]==['api','health']:
                try: q=queue(); state='busy' if q['queue_running'] or q['queue_pending'] else 'online'
                except Exception: state='offline'
                try: q=queue('http://127.0.0.1:8190'); image_state='busy' if q['queue_running'] or q['queue_pending'] else 'online'
                except Exception:image_state='offline'
                keys={}
                env=ROOT/'.env'
                if env.exists():
                    for line in env.read_text(encoding='utf-8-sig').splitlines():
                        if '=' in line:
                            k,v=line.split('=',1)
                            if k.strip() in ('DEEPSEEK_MODEL','LLM_PROVIDER'): keys[k.strip()]=v.strip().strip('\"\'')
                            if k.strip()=='DEEPSEEK_API_KEY': keys['configured']=bool(v.strip())
                return self.respond(dict(comfy=state,qwen=image_state,defaultImageModel='qwen21',agent=keys,referenceLimit=9))
            if parts==['api','library']: return self.respond([{k:v for k,v in x.items() if k!='path'} for x in library()])
            if parts==['api','projects']:
                with LOCK: return self.respond([dict(id=p['id'],name=p['name'],shots=len(p['shots']),assets=len(p['assets']),updated=p['updated']) for p in self.server.store.list()])
            if parts==['api','projects','trash']:
                with LOCK: return self.respond([dict(id=p['id'],name=p['name'],deletedAt=p['deletedAt']) for p in self.server.store.list(deleted=True)])
            if len(parts)==3 and parts[:2]==['api','projects']:
                with LOCK: return self.respond(public_project(self.server.store.get(parts[2])))
            if parts==['api','jobs']:
                with LOCK: return self.respond([{**{k:v for k,v in j.items() if k!='snapshot'},
                    'ownedTargets':[a['id'] for a in j['snapshot']['assets'] if owns_item(j,a['id'])] if j['kind']=='shot_auto' else [j.get('target')],
                    'clearBlockedShotIds':shot_clear_targets(j),
                    'inFlight':any(t['status']=='running' for t in j.get('shotTasks',[]))}
                    for j in reversed(self.server.runner.jobs) if not j.get('archivedByReset')])
            if len(parts)==5 and parts[:2]==['api','edit-mask']:
                _,_,pid,iid,vid=parts
                p=self.server.store.get(pid);item=next(a for a in p['assets'] if a['id']==iid);v=next(v for v in item['versions'] if v['id']==vid)
                f=v['editMaskReference']
                if digest(Path(f['path']))!=f['sha256']:raise ValueError('编辑蒙版已改变')
                return self.send_file(Path(f['path']))
            if len(parts)==6 and parts[:2]==['api','reference-input']:
                _,_,pid,iid,vid,index=parts
                p=self.server.store.get(pid);item=next(a for a in p['assets'] if a['id']==iid);v=next(v for v in item['versions'] if v['id']==vid)
                f=v['inputReferences'][int(index)]
                if digest(Path(f['path']))!=f['sha256']:raise ValueError('实际输入参考图已改变')
                return self.send_file(Path(f['path']))
            if len(parts)==7 and parts[:2]==['api','media']:
                _,_,pid,category,iid,vid,index=parts
                if category not in ('assets','shots'): raise ValueError('非法素材类型')
                p=self.server.store.get(pid); item=next(x for x in p[category] if x['id']==iid); v=next(v for v in item['versions'] if v['id']==vid)
                return self.send_file(Path(v['files'][int(index)]['path']))
            if len(parts)==4 and parts[:2]==['api','exports']:
                p=self.server.store.get(parts[2]); e=next(x for x in p['exports'] if x['id']==parts[3]); return self.send_file(Path(e['path']),download=True)
            if parts and parts[0]=='api': return self.respond({'error':'接口不存在'},404)
            dist=APP/'dist'; path=(dist/unquote(urlparse(self.path).path).lstrip('/')).resolve()
            if not path.is_relative_to(dist.resolve()): return self.respond({'error':'非法路径'},403)
            if not path.is_file(): path=dist/'index.html'
            return self.send_file(path)
        except (ValueError,KeyError,StopIteration,IndexError) as e: self.respond({'error':str(e) or '未找到指定对象'},400)
        except FileNotFoundError: self.respond({'error':'文件不存在'},404)
        except (BrokenPipeError,ConnectionResetError): pass
        except Exception as e: self.respond({'error':str(e)},500)
    def mutate(self,parts,d):
        st=self.server.store; runner=self.server.runner
        if parts[:2]==['api','prompt-optimizations']:
            from .prompt_optimizer import route
            return route(self,parts,d)
        if parts[:2]==['api','lab']:
            from .lab import mutate
            return mutate(self,parts,d)
        if parts==['api','projects']:
            chosen_agent=agent_provider(d)
            chosen_options=agent_selection(d)
            if d.get('documents'):
                docs=read_documents(d['documents'])
                p=st.create(d.get('name','未命名项目'));p['sources']=docs;p['agentProvider']=chosen_agent;p.update(chosen_options);st.save(p)
                runner.enqueue(p['id'],'parse',None,False)
                return self.respond(public_project(p),201)
            text=d.get('text',''); filename=d.get('filename','分镜脚本.md')
            if d.get('libraryId') is not None:
                src=next(x for x in library() if x['id']==d['libraryId']); text=src['path'].read_text(encoding='utf-8-sig'); filename=src['name']
            p=st.create(d.get('name') or filename.rsplit('.',1)[0],text,filename)
            p['agentProvider']=chosen_agent;p.update(chosen_options);st.save(p)
            if text and d.get('parserMode')=='ai': runner.enqueue(p['id'],'parse',p['sources'][-1]['id'],False)
            return self.respond(public_project(p),201)
        if parts==['api','demo']: return self.respond(public_project(demo(st,d.get('reuse',True))),201)
        if parts==['api','jobs']:
            j=runner.enqueue(d['projectId'],d['kind'],d.get('target'),d.get('autoReview',True),d.get('options'),d.get('revision')); return self.respond({'id':j['id'],'status':j['status']},202)
        if len(parts)==4 and parts[:2]==['api','jobs']: return self.respond({k:v for k,v in runner.control(parts[2],parts[3]).items() if k!='snapshot'})
        if len(parts)==4 and parts[:2]==['api','projects']:
            pid,action=parts[2:]
            if action=='restore': return self.respond(public_project(st.restore(pid)))
            p=st.get(pid)
            if not runner.can_edit(pid,action,d.get('id')):
                if action=='clear-shot':raise ValueError('此镜头有未完成的生成或审核任务，请完成或取消该镜头的任务后再清空；其他镜头可直接清空。')
                raise ValueError('此操作影响待执行任务使用的素材，请完成相关任务后再操作；独立图片和单镜任务可编辑并继续排队。')
            if 'revision' in d and int(d['revision'])!=p['revision']: raise ValueError('项目已更新，请刷新后保存，避免覆盖其他修改')
            if action=='delete':
                if runner.busy(pid): raise ValueError('请先完成或取消此工作空间的待执行任务')
                st.trash(pid); return self.respond({'id':pid,'deleted':True})
            if action=='settings':
                if 'agentProvider' in d:p['agentProvider']=agent_provider(d)
                if 'agentModel' in d or 'agentThinking' in d:p.update(agent_selection({**p,**d}))
                if 'name' in d: p['name']=str(d['name'])[:100]
                if 'autoReview' in d: p['autoReview']=bool(d['autoReview'])
            elif action=='video-mode':
                from .production import set_video_profile
                set_video_profile(p,d.get('videoProfile'))
            elif action=='new-round':
                state=budget(p)
                if not state['stop']:raise ValueError('当前批次未停止，无需开启新一轮')
                if d.get('revision')!=p['revision']:raise ValueError('项目已更新，请刷新后开启新一轮')
                previous=p['campaign'];p['campaign']='director_'+p['id']+'_'+uid()
                p.setdefault('campaignHistory',[]).append(dict(campaign=previous,nextCampaign=p['campaign'],
                    at=time.time(),reason='user_started_new_round_after_stop',stop=copy.deepcopy(state['stop'])))
            elif action=='documents':
                if any(x['versions'] for x in p['assets']+p['shots']): raise ValueError('已有制作版本，请新建项目成对导入，保留现有素材')
                p['sources'].extend(read_documents(d['documents']));st.save(p)
                runner.enqueue(pid,'parse',None,False)
                return self.respond(public_project(p))
            elif action=='source':
                role=d.get('role','storyboard')
                if role not in ('references','storyboard'):raise ValueError('文档用途无效')
                text=str(d['text']); p['sources'].append(dict(id=uid(),name=Path(d['filename']).name,text=text,role=role))
                if d.get('parse'):
                    if p['shots']: raise ValueError('项目已有分镜，请新建项目导入修订脚本以保留原版本')
                    p['assets'],p['shots']=parse_storyboard(text)
            elif action=='asset':
                if not d.get('id'): p['assets'].append(make_asset(str(d['name'])[:100],d['kind']))
                else:
                    item=next(a for a in p['assets'] if a['id']==d['id']); self.edit(item,d,('name','prompt','sidePrompt','backPrompt','seed','provider','imageMode','imageVariant','generationRefs','editMask'))
                    from .assets import references
                    if item.get('imageMode')=='text' or item.get('generationRefs'): references(p,item,allow_pending=True)
                    from .assets import ordered_assets
                    ordered_assets(p)
            elif action in ('clear-asset','restore-asset'):
                from .project import clear_asset,restore_asset
                item=next(a for a in p['assets'] if a['id']==d['id'])
                (clear_asset if action=='clear-asset' else restore_asset)(item)
            elif action in ('clear-shot','restore-shot'):
                from .project import clear_shot,restore_shot
                item=next(s for s in p['shots'] if s['id']==d['id'])
                if action=='clear-shot':
                    state=budget(p)
                    # Archive only this shot. Existing jobs keep their frozen campaign
                    # and files; unrelated ComfyUI activity does not affect this edit.
                    clear_shot(p,item,state['ledger'],bool(state['stop']))
                else:restore_shot(item)
            elif action=='shot':
                from .production import RESOLUTIONS
                if 'videoResolution' in d and d['videoResolution'] not in tuple(RESOLUTIONS):
                    raise ValueError('不支持的分镜画幅')
                item=next(s for s in p['shots'] if s['id']==d['id']); self.edit(item,d,('name','prompt','seconds','seed','refs','info','videoResolution'))
            elif action in ('select','accept'):
                if d['category'] not in ('assets','shots'): raise ValueError('非法类型')
                item=next(x for x in p[d['category']] if x['id']==d['id']); v=next(v for v in item['versions'] if v['id']==d['version'])
                if action=='select':
                    from .project import select_version
                    select_version(item,v,d['category'])
                else: v['humanAccepted']=bool(d.get('accepted',True))
            elif action in ('upload','input'):
                category='assets' if action=='input' else d['category']
                if category not in ('assets','shots'): raise ValueError('非法类型')
                item=next(x for x in p[category] if x['id']==d['id']); ext=Path(d['filename']).suffix.lower()
                if ext not in (('.png','.jpg','.jpeg','.webp') if category=='assets' else ('.mp4',)): raise ValueError('不支持此格式')
                payload=base64.b64decode(d['content'],validate=True)
                vid=uid(); folder=st.folder/'projects'/pid/'uploads'; folder.mkdir(parents=True,exist_ok=True); file=folder/(vid+ext)
                if category=='assets':
                    from PIL import Image
                    import io
                    Image.open(io.BytesIO(payload)).verify()
                file.write_bytes(payload)
                if action=='input':
                    item.setdefault('inputs',[]).append(dict(id=vid,label=Path(d['filename']).name,path=str(file),sha256=digest(file)))
                    st.save(p); return self.respond(public_project(p))
                v=dict(id=vid,created=time.time(),files=[dict(label='uploaded',path=str(file),sha256=digest(file))],prompt=item['prompt'],seed=item['seed'],review=None,humanAccepted=False,imported=True)
                if category=='shots':
                    byid={a['id']:a for a in p['assets']}
                    v['references']=[selected(byid[key])['files'][0] for key in item['refs'] if key in byid and selected(byid[key])]
                    v['seconds']=item['seconds']
                item['versions'].append(v); item['selected']=vid
            else: raise ValueError('未知操作')
            st.save(p); return self.respond(public_project(p))
        return self.respond({'error':'接口不存在'},404)
    def edit(self,item,d,fields):
        item['history'].append(dict(at=time.time(),values={k:item.get(k) for k in fields}))
        for k in fields:
            if k in d: item[k]=d[k]
        if 'seed' in d: item['seed']=int(d['seed'])
        if 'seconds' in d: item['seconds']=float(d['seconds'])
    def send_file(self,path,download=False):
        size=path.stat().st_size; start=0; end=size-1; status=200
        value=self.headers.get('Range','')
        if value:
            m=re.fullmatch(r'bytes=(\d+)-(\d*)',value)
            if not m: self.send_error(416); return
            start=int(m[1]); end=min(int(m[2]) if m[2] else size-1,size-1)
            if start>end: self.send_error(416); return
            status=206
        self.send_response(status); self.send_header('Content-Type',mimetypes.guess_type(path)[0] or 'application/octet-stream')
        self.send_header('Content-Length',str(end-start+1)); self.send_header('Accept-Ranges','bytes'); self.send_header('X-Content-Type-Options','nosniff')
        if download: self.send_header('Content-Disposition','attachment; filename="trae-edit-package.zip"')
        if status==206: self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        self.end_headers()
        with path.open('rb') as f:
            f.seek(start); remaining=end-start+1
            while remaining>0:
                data=f.read(min(1024*1024,remaining))
                if not data: break
                self.wfile.write(data); remaining-=len(data)

def main():
    arg=argparse.ArgumentParser(); arg.add_argument('--port',type=int,default=8321); arg.add_argument('--data',type=Path,default=DATA); args=arg.parse_args()
    st=Store(args.data)
    # A second server must never own the same queue and campaign jobs.
    import msvcrt
    lock=(st.folder/'server.lock').open('a+b'); lock.seek(0); lock.write(b'0'); lock.flush(); lock.seek(0)
    try: msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError: raise SystemExit('此数据目录已有导演台服务运行')
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler); server.store=st; server.runner=Runner(st)
    print(f'H3 Director http://127.0.0.1:{args.port}',flush=True); server.serve_forever()

if __name__=='__main__': main()
