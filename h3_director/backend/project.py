"""Local project documents. Original scripts and every generated take are immutable."""
import hashlib
import json
from pathlib import Path
import re
import threading
import time
import uuid

from .paths import ROOT
LOCK = threading.RLock()

def uid():
    return uuid.uuid4().hex[:12]

def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    try:
        for attempt in range(8):
            try:tmp.replace(path);break
            except PermissionError:
                if attempt==7:raise
                time.sleep(min(.05*2**attempt,.4))
    finally:
        if tmp.exists():tmp.unlink()

def select_version(item,version,category):
    item['selected']=version['id']
    for key in ('prompt','seed'):item[key]=version[key]
    if category=='assets':
        if version.get('viewPrompts'):item['sidePrompt'],item['backPrompt']=version['viewPrompts']
        if version.get('generation'):item.update(version['generation'])
    else:
        for key in ('seconds','width','height'):
            if key in version:item[key]=version[key]

def clear_asset(item):
    if item['versions']:item.setdefault('clearedBatches',[]).append(dict(at=time.time(),versions=item['versions'],selected=item['selected']))
    item['versions']=[];item['selected']=None

def restore_asset(item):
    if item['versions']:raise ValueError('已有新素材，请先清空再恢复历史批次')
    if not item.get('clearedBatches'):raise ValueError('没有可恢复的清空记录')
    batch=item['clearedBatches'].pop();item['versions']=batch['versions'];item['selected']=batch['selected']
    if selected(item):select_version(item,selected(item),'assets')

def clear_shot(project,item,ledger,stopped=False):
    if not item['versions']:return
    # A deliberate per-shot clear authorizes a fresh round. Never reset/delete a ledger.
    # Consecutive clears before generation share this campaign, since its ledger is empty.
    if stopped or ledger.get('attempts',{}).get(item['id']):
        previous=project['campaign']
        project['campaign']='director_'+project['id']+'_'+uid()
        project.setdefault('campaignHistory',[]).append(dict(campaign=previous,nextCampaign=project['campaign'],
            at=time.time(),reason='user_cleared_shot_for_regeneration',shot=item['id']))
    item.setdefault('clearedBatches',[]).append(dict(at=time.time(),versions=item['versions'],selected=item['selected']))
    item['versions']=[];item['selected']=None

def restore_shot(item):
    if item['versions']:raise ValueError('已有新视频，请先清空再恢复历史批次')
    if not item.get('clearedBatches'):raise ValueError('没有可恢复的清空记录')
    batch=item['clearedBatches'].pop();item['versions']=batch['versions'];item['selected']=batch['selected']
    if selected(item):select_version(item,selected(item),'shots')

def selected(item):
    return next((v for v in item['versions'] if v['id'] == item.get('selected')), None)

def current(p,category,item):
    v=selected(item)
    if not v: return False
    if v['prompt']!=item['prompt'] or v['seed']!=item['seed']: return False
    if category=='assets':
        from .assets import settings
        if v.get('generation') and v['generation']!=settings(item): return False
        if v.get('viewPrompts') and v['viewPrompts']!=[item['sidePrompt'],item['backPrompt']]: return False
        if item.get('imageMode') in ('reference','inpaint') and 'inputReferences' in v:
            from .assets import references
            try:refs=references(p,item)
            except (ValueError,OSError):return False
            if [(f.get('key'),f['sha256']) for f in refs]!=[(f.get('key'),f['sha256']) for f in v['inputReferences']]:return False
    else:
        refs=[]
        for key in item['refs']:
            a=next((a for a in p['assets'] if a['id']==key),None)
            if not a or not selected(a): return False
            refs.append(selected(a)['files'][0]['sha256'])
        if refs!=[f['sha256'] for f in v.get('references',[])]: return False
        if v.get('seconds',item['seconds'])!=item['seconds']: return False
        if any(v.get(key,item[key])!=item[key] for key in ('width','height')):return False
        if item.get('videoResolution'):
            from .production import VIDEO_PROFILE,shot_dimensions
            version_size=(v.get('width',item['width']),v.get('height',item['height']))
            if v.get('profile')==VIDEO_PROFILE and version_size!=shot_dimensions(VIDEO_PROFILE,item):return False
    return True

def make_asset(name, kind, key=None, description=''):
    suffix = {'character':'单个人物，全身，纯白背景，无文字，无拼图。',
              'scene':'完整空场景，无人物，电影感光影。',
              'keyframe':'保留关键帧中的主体、构图和光影。',
              'prop':'单个道具，纯白背景，外形完整，无人物。'}[kind]
    return dict(id=key or uid(), name=name, kind=kind, prompt=(description or name)+'。'+suffix,
                sidePrompt='以图 1 为人物身份母版，生成严格 90 度侧面全身图，鼻尖朝画面右侧。保持同一人物、脸型、发型、服装、鞋履、背景与画风。仅一人。',
                backPrompt='以图 1 为人物身份母版，生成背面全身图，不露面部。保持同一人物、发型、服装、鞋履、背景与画风。仅一人。',
                seed=20260916, versions=[], selected=None, history=[],provider='local',imageMode='text',imageVariant='qwen21',generationRefs=[],inputs=[])

def parse_storyboard(text):
    """Parse the user's Seedance format without dropping the untouched source."""
    assets=[]
    for line in text.splitlines():
        cols=[v.strip() for v in line.strip().strip('|').split('|')]
        if len(cols)>=3 and re.fullmatch(r'[CSP E]\d+',cols[1].replace(' ','')):
            key=cols[1]; kind='character' if key.startswith('C') else 'scene' if key.startswith('S') else 'prop'
            if not any(a['id']==key for a in assets): assets.append(make_asset(cols[0],kind,key))
    headings=list(re.finditer(r'^#{2,4}\s*【?分镜\s*(\d+)([^\n]*)',text,re.M))
    shots=[]
    for index,h in enumerate(headings):
        block=text[h.end():headings[index+1].start() if index+1<len(headings) else len(text)]
        prompt=re.search(r'```[^\n]*\n([\s\S]*?)```',block)
        if not prompt: continue
        source=prompt.group(1).strip()
        scene=re.search(r'\*\*场景\*\*[:：]\s*([^|\n]+)',block)
        seconds=re.search(r'(?:时长[:：]\s*)?(\d+(?:\.\d+)?)\s*秒',h.group(2))
        declared=re.search(r'\*\*上传素材\*\*[:：]\s*([^\n]+)',block)
        refids=[]
        if declared:
            for key in re.findall(r'\(([A-Z]\d+)\)', declared.group(1)):
                if any(a['id']==key for a in assets) and key not in refids: refids.append(key)
        if not refids: refids=[a['id'] for a in assets if '@'+a['name'] in source]
        mapping={a['name']:f'<Picture {refids.index(a["id"])+1}>' for a in assets if a['id'] in refids}
        converted=source
        for name in sorted(mapping,key=len,reverse=True): converted=converted.replace('@'+name,mapping[name])
        declarations='\n'.join(f'<Picture {i+1}> 是{next(a["name"] for a in assets if a["id"]==key)}的外观参考。' for i,key in enumerate(refids))
        info=re.search(r'📌\s*本镜信息增量[:：]\s*([^\n]+)',block)
        warnings=[]
        if re.search(r'首[尾帧]|首帧|文字保持',block): warnings.append('原脚本包含首帧或文字要求；Ref2VA 参考图不等于锁定首帧，需审查适配。')
        shots.append(dict(id=f's{int(h.group(1)):03}', name=f'分镜 {h.group(1)}',scene=scene.group(1).strip() if scene else '',
            seconds=float(seconds.group(1)) if seconds else 10, seed=20260916+index, width=1344,height=768,
            originalPrompt=source,prompt=declarations+'\n\n'+converted, refs=refids,
            info=info.group(1).strip() if info else '',warnings=warnings,versions=[],selected=None,history=[]))
    # Resolve character descriptions from the actual script, not invented biographies.
    for asset in assets:
        if asset['kind']=='character':
            match=re.search(re.escape(asset['name'])+r'（([^）]{15,400})）',text)
            if match:
                desc=re.sub(r'人物形象参考@[^，]+[，,]?','',match.group(1))
                asset['prompt']=asset['name']+'，'+desc+'。单个人物全身，正面站立，纯白背景，无文字。'
    return assets,shots

class Store:
    def __init__(self, folder):
        self.folder=Path(folder).resolve(); self.folder.mkdir(parents=True,exist_ok=True)
    def path(self,pid):
        if not re.fullmatch(r'[a-f0-9]{12}',pid): raise ValueError('项目 ID 无效')
        return self.folder/'projects'/pid/'project.json'
    def get(self,pid,deleted=False):
        p=read(self.path(pid))
        if p.get('deletedAt') and not deleted: raise FileNotFoundError('工作空间已删除')
        return p
    def trash(self,pid):
        p=self.get(pid); p['deletedAt']=time.time(); self.save(p); return p
    def restore(self,pid):
        p=self.get(pid,deleted=True); p.pop('deletedAt',None); self.save(p); return p
    def save(self,p):
        p['revision']=p.get('revision',0)+1; p['updated']=time.time(); write(self.path(p['id']),p)
    def list(self,deleted=False):
        projects=[read(p) for p in (self.folder/'projects').glob('*/project.json')]
        return sorted([p for p in projects if bool(p.get('deletedAt'))==deleted],key=lambda p:p['updated'],reverse=True)
    def create(self,name,text='',filename='分镜脚本.md'):
        assets,shots=parse_storyboard(text)
        p=dict(id=uid(),name=name or '未命名项目',created=time.time(),revision=0,assets=assets,shots=shots,
               sources=[dict(id=uid(),name=Path(filename).name,text=text)] if text else [],exports=[],autoReview=True,agentProvider='deepseek',agentModel='gpt-5.6-sol',agentThinking='high')
        p['campaign']='director_'+p['id']; self.save(p); return p

def validate_shot(p,shot,require_media=True):
    errors=[]
    if not 1<=len(shot['refs'])<=9: errors.append('每镜需 1–9 张参考图')
    if len(set(shot['refs']))!=len(shot['refs']): errors.append('同一资产不可重复引用')
    tags={int(n) for n in re.findall(r'<Picture\s+(\d+)>',shot['prompt'])}
    if tags!=set(range(1,len(shot['refs'])+1)): errors.append('Picture 标签必须与参考图顺序连续对应')
    if re.search(r'@[\w\u4e00-\u9fff]+',shot['prompt']): errors.append('仍有未转换的 @ 素材引用')
    if not 0<float(shot['seconds'])<=15: errors.append('当前执行器时长范围为大于 0 且不超过 15 秒')
    for key in shot['refs']:
        a=next((a for a in p['assets'] if a['id']==key),None)
        if a is None: errors.append('参考资产不存在：'+key)
        elif require_media and not selected(a): errors.append('缺少参考图：'+a['name'])
    return errors
