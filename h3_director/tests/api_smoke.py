"""HTTP acceptance and optional single live campaign. Never creates another live campaign on rerun."""
import base64
import json
from pathlib import Path
import sys
import urllib.request
import urllib.error
import argparse
import atexit
import tempfile
import threading

APP=Path(__file__).resolve().parents[1]; BASE='http://127.0.0.1:8321/api/'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--isolated',action='store_true',help='Use temporary project data and an ephemeral local HTTP port; no production edits')
parser.add_argument('--live',action='store_true',help='Explicitly start the guarded production campaign')
options=parser.parse_args()
if options.isolated and options.live: parser.error('--isolated cannot start live production')
if options.isolated:
    sys.path.insert(0,str(APP))
    from http.server import ThreadingHTTPServer
    from backend.server import Handler
    from backend.project import Store
    from backend.runner import Runner
    temporary=tempfile.TemporaryDirectory(prefix='h3-director-api-')
    service=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    service.store=Store(temporary.name); service.runner=Runner(service.store,start=False)
    threading.Thread(target=service.serve_forever,daemon=True).start()
    BASE=f'http://127.0.0.1:{service.server_port}/api/'
    def cleanup():
        service.shutdown(); service.server_close(); temporary.cleanup()
    atexit.register(cleanup)
def api(route,data=None,headers=None):
    req=urllib.request.Request(BASE+route,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json',**(headers or {})})
    with urllib.request.urlopen(req,timeout=15) as r:return json.load(r)

if options.live:
    state=APP/'data/live-validation.json'
    if state.exists():
        print(state.read_text());raise SystemExit('Live campaign already recorded. Inspect its job; never auto-start another.')
    p=api('demo',{'reuse':False})
    record={'projectId':p['id'],'campaign':p['campaign'],'status':'created'}
    state.write_text(json.dumps(record,indent=2),encoding='utf-8')
    j=api('jobs',{'projectId':p['id'],'kind':'auto','autoReview':True})
    record.update(jobId=j['id'],status='queued');state.write_text(json.dumps(record,indent=2),encoding='utf-8')
    print(json.dumps(record));raise SystemExit()

# Reversible workspace deletion, including guards and restored history.
trash_test=api('projects',{'name':'回收站验收'})
j=api('jobs',{'projectId':trash_test['id'],'kind':'parse'})
try:api(f'projects/{trash_test["id"]}/delete',{});raise AssertionError('queued workspace deleted')
except urllib.error.HTTPError as e:assert e.code==400
api(f'jobs/{j["id"]}/cancel',{})
api(f'projects/{trash_test["id"]}/delete',{})
assert not any(p['id']==trash_test['id'] for p in api('projects'))
assert any(p['id']==trash_test['id'] for p in api('projects/trash'))
try:api('projects/'+trash_test['id']);raise AssertionError('deleted workspace readable')
except urllib.error.HTTPError as e:assert e.code==404
restored=api(f'projects/{trash_test["id"]}/restore',{})
assert restored['campaign']==trash_test['campaign']
assert any(p['id']==trash_test['id'] for p in api('projects'))

checks=['workspace deletion blocked while queued; trash, 404, restore and campaign verified']
health=api('health'); assert health['referenceLimit']==9;assert 'DEEPSEEK_API_KEY' not in json.dumps(health);checks.append('health omits credentials')
library=api('library');src=next((x for x in library if '信息修订版' in x['name']),None)
if src:
    p=api('projects',{'name':'对面 · 导演台导入验证','libraryId':src['id']})
    assert len(p['shots'])==27 and len(p['assets'])==12;assert len(p['shots'][2]['refs'])==4
    checks.append('27 shots / 12 assets / four references preserved')
else:
    storyboard='''| 杯子 | P01 | 道具 |
| 工作台 | S01 | 场景 |

## 分镜 1 · 5 秒
```text
@杯子 放在 @工作台 中央。
```
'''
    p=api('projects',{'name':'导演台导入验证','filename':'示例.md','text':storyboard})
    assert p['sources'][0]['text']==storyboard
    assert len(p['shots'])==1 and p['shots'][0]['refs']==['P01','S01']
    checks.append('inline storyboard import preserves original text and ordered references')
s=p['shots'][0];original=s['originalPrompt']
p=api(f'projects/{p["id"]}/shot',{'id':s['id'],'prompt':s['prompt']+'\n固定机位。','revision':p['revision']})
assert p['shots'][0]['originalPrompt']==original; assert len(p['shots'][0]['history'])==1;checks.append('prompt revision preserves source')
try:api(f'projects/{p["id"]}/settings',{'name':'bad','revision':0});raise AssertionError('stale edit allowed')
except urllib.error.HTTPError as e:assert e.code==400
checks.append('stale writes rejected')
try:api('projects',{'name':'cross-site'},headers={'Origin':'https://evil.example'});raise AssertionError('foreign origin allowed')
except urllib.error.HTTPError as e:assert e.code==403
checks.append('foreign Origin rejected')
try:api('projects/../../.env');raise AssertionError('path traversal allowed')
except urllib.error.HTTPError:pass
checks.append('arbitrary path rejected')
if options.isolated:
    from PIL import Image
    import io
    image=io.BytesIO();Image.new('RGB',(32,32),'blue').save(image,format='PNG')
    a=p['assets'][0]
    p=api(f'projects/{p["id"]}/input',dict(id=a['id'],filename='reference.png',content=base64.b64encode(image.getvalue()).decode(),revision=p['revision']))
    a=p['assets'][0];assert not a['versions'];assert len(a['inputs'])==1
    with urllib.request.urlopen(BASE.removesuffix('api/')+a['inputs'][0]['url'].lstrip('/')) as response:assert response.read()==image.getvalue()
    checks.append('input image upload and media delivery preserve bytes and versions')
    key='input:'+a['id']+':'+a['inputs'][0]['id']
    p=api(f'projects/{p["id"]}/asset',dict(id=a['id'],provider='codex',imageMode='reference',generationRefs=[key],revision=p['revision']))
    assert p['assets'][0]['provider']=='codex' and p['assets'][0]['generationRefs']==[key]
    checks.append('provider and ordered image inputs roundtrip')
    try:api(f'projects/{p["id"]}/asset',dict(id=a['id'],generationRefs=['C:/private.png'],revision=p['revision']));raise AssertionError('arbitrary image input allowed')
    except urllib.error.HTTPError as e:assert e.code==400
    assert api('projects/'+p['id'])['assets'][0]['generationRefs']==[key]
    checks.append('unowned image references rejected without mutation')
    j=api('jobs',dict(projectId=p['id'],kind='shot_auto',target=p['shots'][0]['id']))
    assert j['status']=='queued';assert service.runner.jobs[-1]['kind']=='shot_auto'
    checks.append('single-shot auto accepts missing assets for staged preparation')
    docs=[dict(role='references',filename='参考.md',text='蓝色杯子，灰色背景。'),dict(role='storyboard',filename='分镜.md',text='镜头1：杯子放在桌上。')]
    paired=api('projects',dict(name='双文档导入验证',documents=docs))
    assert {s['role'] for s in paired['sources']}=={'references','storyboard'}
    parse_job=next(j for j in service.runner.jobs if j['projectId']==paired['id'])
    assert parse_job['kind']=='parse' and len(parse_job['snapshot']['sources'])==2
    checks.append('paired document import retains both roles and queues DeepSeek parsing')
    parse_job['status']='cancelled'
    paired=api(f'projects/{paired["id"]}/documents',dict(documents=[dict(role='references',filename='新版参考.md',text='红色杯子。')],revision=paired['revision']))
    assert paired['sources'][-1]['name']=='新版参考.md'
    assert len([j for j in service.runner.jobs if j['projectId']==paired['id']])==2
    checks.append('supplemental reference document queues paired reparse')
    images=api('projects',dict(name='多图片排队验证'))
    for name in ['甲','乙']:
        images=api(f'projects/{images["id"]}/asset',dict(name=name,kind='prop',revision=images['revision']))
    first=api('jobs',dict(projectId=images['id'],kind='asset',target=images['assets'][0]['id']))
    next(j for j in service.runner.jobs if j['id']==first['id'])['status']='running'
    second=api('jobs',dict(projectId=images['id'],kind='asset',target=images['assets'][1]['id']))
    assert second['status']=='queued'
    images=api(f'projects/{images["id"]}/asset',dict(id=images['assets'][0]['id'],prompt='修改后的中文杯子提示词',revision=images['revision']))
    third=api('jobs',dict(projectId=images['id'],kind='asset',target=images['assets'][0]['id']))
    assert third['status']=='queued'
    checks.append('HTTP permits queued images and freezes changed prompts during generation')
    agents=api('projects',dict(name='导演 Agent 切换验证'))
    assert agents['agentProvider']=='deepseek'
    assert agents['agentModel']=='gpt-5.6-sol' and agents['agentThinking']=='high'
    agents=api(f'projects/{agents["id"]}/settings',dict(agentProvider='codex',revision=agents['revision']))
    assert api('projects/'+agents['id'])['agentProvider']=='codex'
    try:api(f'projects/{agents["id"]}/settings',dict(agentProvider='invalid',revision=agents['revision']));raise AssertionError('invalid agent allowed')
    except urllib.error.HTTPError as e:assert e.code==400
    agents=api(f'projects/{agents["id"]}/asset',dict(name='杯子',kind='prop',revision=agents['revision']))
    job=api('jobs',dict(projectId=agents['id'],kind='asset',target=agents['assets'][0]['id']))
    assert next(j for j in service.runner.jobs if j['id']==job['id'])['snapshot']['agentProvider']=='codex'
    checks.append('agent defaults, persistent switching, validation and queued provider snapshot')
    paired=api('projects',dict(name='Codex 订阅导入',documents=docs,agentProvider='codex'))
    assert next(j for j in service.runner.jobs if j['projectId']==paired['id'])['snapshot']['agentProvider']=='codex'
    checks.append('new-project import freezes selected subscription provider before parsing')
    custom=api('projects',dict(name='模型与推理等级',agentProvider='codex',agentModel='gpt-5.6-luna',agentThinking='medium'))
    custom=api(f'projects/{custom["id"]}/settings',dict(agentThinking='xhigh',revision=custom['revision']))
    saved=api('projects/'+custom['id'])
    assert saved['agentModel']=='gpt-5.6-luna' and saved['agentThinking']=='xhigh'
    checks.append('model and thinking settings persist with Sol/High defaults')
if options.isolated:
    automatic=api('demo',{'reuse':False})
    choices=dict(imageModel='base',videoModel='h3_ref2va_int8_turbo',videoResolution='portrait',videoSeconds=8,agentProvider='deepseek',autoReview=False)
    configured=api('jobs',dict(projectId=automatic['id'],kind='auto',options=choices,revision=automatic['revision']))
    frozen=next(j for j in service.runner.jobs if j['id']==configured['id'])
    live=api('projects/'+automatic['id'])
    assert frozen['snapshot']['assets'][0]['imageVariant']=='base'
    assert live['shots'][0]['width']==768 and live['shots'][0]['height']==1344 and live['shots'][0]['seconds']==8
    assert not frozen['autoReview'] and frozen['productionSettings']['imageModel']=='base'
    assert frozen['snapshot']['campaign']==automatic['campaign']
    assert next(j for j in api('jobs') if j['id']==configured['id'])['productionSettings']['videoSeconds']==8
    api(f'jobs/{configured["id"]}/cancel',{})
    try:api('jobs',dict(projectId=automatic['id'],kind='auto',options={'videoModel':'unsupported'}));raise AssertionError('unsupported model accepted')
    except urllib.error.HTTPError as e:assert e.code==400
    checks.append('automatic production options persist, reach immutable task snapshot, and reject unsupported models')
    stage_images=api('projects',dict(name='仅参考图批量验证'))
    stage_images=api(f'projects/{stage_images["id"]}/asset',dict(name='参考杯子',kind='prop',revision=stage_images['revision']))
    image_job=api('jobs',dict(projectId=stage_images['id'],kind='assets_auto',options={'imageModel':'base','maxRetries':3},revision=stage_images['revision']))
    assert next(j for j in api('jobs') if j['id']==image_job['id'])['productionSettings']['scope']=='assets' and not stage_images['shots']
    assert next(j for j in api('jobs') if j['id']==image_job['id'])['productionSettings']['maxRetries']==3
    assert api('projects/'+stage_images['id'])['productionSettingsByScope']['assets']['maxRetries']==3
    api(f'jobs/{image_job["id"]}/cancel',{})
    checks.append('image-only batch accepts a workspace without storyboards and records its scope')
    assert not live['referenceReadiness']['ready'] and live['referenceReadiness']['problems']
    before=api('projects/'+automatic['id']);job_count=len(api('jobs'))
    try:api('jobs',dict(projectId=automatic['id'],kind='shots_auto',options={'autoReview':False,'videoSeconds':10}));raise AssertionError('missing references allowed')
    except urllib.error.HTTPError as e:
        assert e.code==400 and '请先到参考图页面' in json.load(e)['error']
    assert api('projects/'+automatic['id'])==before and len(api('jobs'))==job_count
    checks.append('video-only batch reports missing references and rejects without changing settings or queue')
    for asset in before['assets']:
        live=api(f'projects/{automatic["id"]}/upload',dict(category='assets',id=asset['id'],filename='reference.png',content=base64.b64encode(image.getvalue()).decode()))
    assert not live['referenceReadiness']['ready']
    try:api('jobs',dict(projectId=automatic['id'],kind='shots_auto',options={'autoReview':False}));raise AssertionError('unapproved references allowed')
    except urllib.error.HTTPError as e:assert e.code==400 and '尚未审批通过' in json.load(e)['error']
    for asset in live['assets']:
        live=api(f'projects/{automatic["id"]}/accept',dict(category='assets',id=asset['id'],version=asset['selected'],accepted=True))
    assert live['referenceReadiness']['ready']
    shot_job=api('jobs',dict(projectId=automatic['id'],kind='shots_auto',options={'videoSeconds':10,'autoReview':False},revision=live['revision']))
    frozen=next(j for j in service.runner.jobs if j['id']==shot_job['id'])
    assert next(j for j in api('jobs') if j['id']==shot_job['id'])['productionSettings']['scope']=='shots' and frozen['snapshot']['assets']==service.store.get(automatic['id'])['assets']
    api(f'jobs/{shot_job["id"]}/cancel',{})
    checks.append('uploaded references still require approval; manual approval unlocks video-only queue')
    lifecycle=api('projects/'+stage_images['id']);aid=lifecycle['assets'][0]['id'];pid=lifecycle['id']
    lifecycle=api(f'projects/{pid}/upload',dict(category='assets',id=aid,filename='v1.png',content=base64.b64encode(image.getvalue()).decode()))
    v1=lifecycle['assets'][0]['selected'];original_prompt=lifecycle['assets'][0]['prompt']
    lifecycle=api(f'projects/{pid}/asset',dict(id=aid,prompt='Agent 修订版中文提示词',revision=lifecycle['revision']))
    lifecycle=api(f'projects/{pid}/upload',dict(category='assets',id=aid,filename='v2.png',content=base64.b64encode(image.getvalue()).decode()))
    v2=lifecycle['assets'][0]['selected']
    lifecycle=api(f'projects/{pid}/select',dict(category='assets',id=aid,version=v1));assert lifecycle['assets'][0]['prompt']==original_prompt
    lifecycle=api(f'projects/{pid}/select',dict(category='assets',id=aid,version=v2));assert lifecycle['assets'][0]['prompt']=='Agent 修订版中文提示词'
    lifecycle=api(f'projects/{pid}/clear-asset',dict(id=aid));assert not lifecycle['assets'][0]['versions'] and lifecycle['assets'][0]['selected'] is None
    lifecycle=api(f'projects/{pid}/restore-asset',dict(id=aid));assert lifecycle['assets'][0]['selected']==v2 and len(lifecycle['assets'][0]['versions'])==2
    checks.append('clear/restore retain versions; selecting v1 or v2 restores its exact generation prompt')
    from unittest.mock import patch
    video_project=api('projects/'+automatic['id']);sid=video_project['shots'][0]['id'];vpid=video_project['id']
    video_project=api(f'projects/{vpid}/upload',dict(category='shots',id=sid,filename='test.mp4',content=base64.b64encode(b'offline test video').decode()))
    vid=video_project['shots'][0]['selected'];file=Path(video_project['shots'][0]['versions'][-1]['files'][0]['path']);old_campaign=video_project['campaign']
    with patch('backend.local_service.probe',side_effect=AssertionError('archival must not inspect the GPU queue')),patch('backend.server.budget',return_value={'ledger':{'attempts':{sid:['first','second']}},'stop':None}):
        cleared=api(f'projects/{vpid}/clear-shot',dict(id=sid,revision=video_project['revision']))
    assert cleared['campaign']!=old_campaign and not cleared['shots'][0]['versions'] and cleared['shots'][0]['selected'] is None
    assert file.read_bytes()==b'offline test video' and cleared['shots'][0]['clearedBatches'][-1]['selected']==vid
    restored=api(f'projects/{vpid}/restore-shot',dict(id=sid,revision=cleared['revision']))
    assert restored['shots'][0]['selected']==vid and file.exists()
    pending_review=api('jobs',dict(projectId=vpid,kind='review',target=sid))
    try:api(f'projects/{vpid}/clear-shot',dict(id=sid));raise AssertionError('same-shot clear accepted during pending review')
    except urllib.error.HTTPError as e:assert e.code==400
    assert api('projects/'+vpid)['shots'][0]['selected']==vid
    api('jobs/'+pending_review['id']+'/cancel',{})
    round_before=api('projects/'+vpid)
    stopped_state={'ledger':{'attempts':{sid:['first','second']}},'stop':{'status':'STOP','reason':sid+': submission budget exhausted (2)'}}
    with patch('backend.server.budget',return_value=stopped_state):
        fresh_round=api(f'projects/{vpid}/new-round',dict(revision=round_before['revision']))
    assert fresh_round['campaign']!=round_before['campaign']
    assert fresh_round['shots']==round_before['shots'] and fresh_round['assets']==round_before['assets']
    assert fresh_round['campaignHistory'][-1]['stop']==stopped_state['stop']
    assert stopped_state['ledger']['attempts'][sid]==['first','second']
    try:api(f'projects/{vpid}/new-round',dict(revision=fresh_round['revision']));raise AssertionError('new round allowed without STOP')
    except urllib.error.HTTPError as e:assert e.code==400
    checks.append('explicit new-round action preserves media and STOP history; no automatic retry or budget deletion')
    checks.append('shot clear/restore archives video, preserves old budget, ignores unrelated GPU activity and blocks same-shot work')
    lifecycle=api(f'projects/{pid}/asset',dict(name='待生成的上游',kind='prop'));upstream=lifecycle['assets'][-1]['id']
    lifecycle=api(f'projects/{pid}/asset',dict(id=aid,imageMode='reference',generationRefs=[f'asset:{upstream}:0']))
    assert lifecycle['assets'][0]['generationRefs']==[f'asset:{upstream}:0']
    try:api(f'projects/{pid}/asset',dict(id=upstream,imageMode='reference',generationRefs=[f'asset:{aid}:0']));raise AssertionError('cycle allowed')
    except urllib.error.HTTPError as e:assert e.code==400
    stored=service.store.get(pid);v=stored['assets'][0]['versions'][-1];v['inputReferences']=[dict(v['files'][0],key='test-owned-snapshot')];service.store.save(stored)
    lifecycle=api('projects/'+pid);url=lifecycle['assets'][0]['versions'][-1]['inputReferences'][0]['url']
    with urllib.request.urlopen(BASE.removesuffix('api/')+url.lstrip('/')) as response:assert response.read()==image.getvalue()
    checks.append('pending upstream selection is supported, cycles rejected, actual version input thumbnails serve verified bytes')
report={'checks':checks,'projectId':p['id'],'status':'passed'}
if not options.isolated:
    (APP/'data/api-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
