"""Immutable, project-owned image inputs and generation settings."""
from pathlib import Path
from .project import digest,selected

def settings(asset):
    result=dict(provider=asset.get('provider','local'),imageMode=asset.get('imageMode','text'),
        imageVariant=asset.get('imageVariant','qwen21'),generationRefs=asset.get('generationRefs',[]))
    if result['imageMode']=='inpaint':result['editMask']=asset.get('editMask')
    return result

def mask_reference(project,asset,refs=None):
    if asset.get('imageMode')!='inpaint':return None
    if asset.get('provider','local')!='local' or asset.get('imageVariant','qwen21')!='qwen21':
        raise ValueError('选区编辑需要本地 Qwen 2.1')
    key=asset.get('editMask')
    available={'input:'+a['id']+':'+f['id']:f for a in project['assets'] for f in a.get('inputs',[])}
    if key not in available:raise ValueError('请先绘制并保存选区')
    f=available[key]
    if digest(Path(f['path']))!=f['sha256']:raise ValueError('选区蒙版已被修改')
    from PIL import Image
    with Image.open(f['path']) as mask:
        if mask.convert('L').getextrema()[1]==0:raise ValueError('编辑选区不能为空')
        if refs:
            with Image.open(refs[0]['path']) as base:
                if mask.size!=base.size:raise ValueError('选区尺寸必须与原图一致，请重新绘制')
    return dict(path=f['path'],sha256=f['sha256'],key=key)

def references(project,asset,allow_pending=False):
    cfg=settings(asset)
    if cfg['provider'] not in ('local','codex'): raise ValueError('未知参考图生成方式')
    if cfg['imageVariant'] not in ('qwen21','distilled','base'): raise ValueError('未知本地模型')
    if cfg['imageMode'] not in ('text','reference','inpaint'): raise ValueError('未知图像生成模式')
    if cfg['imageMode']=='inpaint' and (cfg['provider']!='local' or cfg['imageVariant']!='qwen21'):
        raise ValueError('选区编辑需要本地 Qwen 2.1')
    if cfg['imageMode']=='text': return []
    available={}
    for a in project['assets']:
        for f in a.get('inputs',[]): available['input:'+a['id']+':'+f['id']]=f
        for v in a['versions']:
            for i,f in enumerate(v['files']): available[f'version:{a["id"]}:{v["id"]}:{i}']=f
    keys=cfg['generationRefs']
    if cfg['imageMode']=='inpaint' and any(k.startswith('asset:') for k in keys):
        raise ValueError('选区编辑请选择固定版本或上传原图，不能使用随生成更新的上游主图')
    limit=1 if cfg['imageMode']=='inpaint' else 9
    if not 1<=len(keys)<=limit or len(set(keys))!=len(keys): raise ValueError(f'此模式需选择 1–{limit} 张不重复的输入图')
    result=[]
    for key in keys:
        if key.startswith('asset:'):
            parts=key.split(':')
            source=next((a for a in project['assets'] if len(parts)==3 and a['id']==parts[1]),None)
            if not source or source['id']==asset['id'] or parts[2] not in ('0','1','2') or (source['kind']!='character' and parts[2]!='0'):
                raise ValueError('上游参考资产或视角无效：'+key)
            v=selected(source);index=int(parts[2])
            if allow_pending:continue
            if not v or index>=len(v['files']):raise ValueError('请先生成上游参考图：'+source['name'])
            available[key]=v['files'][index]
        if key not in available: raise ValueError('输入参考图不存在：'+key)
        f=available[key]
        if digest(Path(f['path']))!=f['sha256']: raise ValueError('输入参考图已被修改')
        result.append(dict(path=f['path'],sha256=f['sha256'],key=key))
    if cfg['imageMode']=='inpaint' and not allow_pending:mask_reference(project,asset,result)
    return result

def ordered_assets(project,items=None):
    byid={a['id']:a for a in project['assets']};done=set();visiting=set();result=[]
    def visit(a):
        if a['id'] in visiting:raise ValueError('参考图依赖形成循环：'+a['name'])
        if a['id'] in done:return
        visiting.add(a['id'])
        if a.get('imageMode') in ('reference','inpaint'):
            for key in a.get('generationRefs',[]):
                if key.startswith('asset:'):
                    parts=key.split(':')
                    if len(parts)!=3 or parts[1] not in byid:raise ValueError('上游资产不存在：'+key)
                    visit(byid[parts[1]])
        visiting.remove(a['id']);done.add(a['id']);result.append(a)
    for a in project['assets'] if items is None else items:visit(a)
    return result

def apply_dependencies(project,rows):
    byid={a['id']:a for a in project['assets']}
    if len(rows)!=len(byid) or {r['id'] for r in rows}!=set(byid):raise ValueError('依赖识别未完整覆盖资产')
    for row in rows:
        a=byid[row['id']];refs=row['referenceAssetIds']
        if not isinstance(refs,list) or len(refs)>9 or len(set(refs))!=len(refs) or any(k not in byid or k==a['id'] for k in refs):raise ValueError('参考依赖无效：'+a['name'])
        # Preserve manually configured inputs; fill missing imported connections.
        if refs and not a.get('generationRefs'):
            a.update(imageMode='reference',generationRefs=['asset:'+key+':0' for key in refs])
        a['referenceAssetIds']=refs
    ordered_assets(project)
