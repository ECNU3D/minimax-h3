"""Validate semantic imports, retaining exact source ranges and original prompts."""
import hashlib
import re
from .project import make_asset

def import_source(sources):
    """Bundle the latest document per explicit role, with reversible line offsets."""
    chosen={}
    for s in sources: chosen[s.get('role','storyboard')]=s
    docs=list(chosen.values())
    if len(docs)==1: return docs[0]
    lines=[]; mapping=[]
    for s in docs:
        lines.append(f'# 导入文件：{s["name"]}（{s.get("role","storyboard")}）')
        start=len(lines)+1; lines.extend(s['text'].splitlines())
        mapping.append(dict(id=s['id'],name=s['name'],role=s.get('role','storyboard'),startLine=start,endLine=len(lines)))
        lines.append('')
    text='\n'.join(lines)
    return dict(id='bundle_'+hashlib.sha256(text.encode()).hexdigest()[:12],name=' + '.join(s['name'] for s in docs),text=text,documents=mapping)

def source_location(source,start,end):
    for d in source.get('documents',[]):
        if d['startLine']<=start<=end<=d['endLine']:
            return dict(sourceId=d['id'],filename=d['name'],lines=[start-d['startLine']+1,end-d['startLine']+1])
    if source.get('documents'): raise ValueError('提示词范围跨越两个源文件')
    return dict(sourceId=source['id'],filename=source.get('name','原稿'),lines=[start,end])

def apply_parse(project,source,result):
    text=source['text']; lines=text.splitlines()
    if result.get('sourceSha256')!=hashlib.sha256(text.encode()).hexdigest(): raise ValueError('智能解析与原始文档哈希不一致')
    if result.get('audit') and result['audit']['verdict']!='pass': raise ValueError('Agent 原文核对未通过：'+'；'.join(result['audit']['issues']))
    assets=[]; shots=[]; ids=set(); ranges=[]
    style=result.get('style','')
    for item in result['assets']:
        key=item['id']
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,49}',key) or key in ids: raise ValueError('资产 ID 重复或无效')
        ids.add(key)
        a=make_asset(item['name'],item['kind'],key,item.get('generationPrompt') or item['description'])
        a['description']=item['description']
        a['aliases']=[name.lstrip('@') for name in item.get('aliases',[])]
        a['promptOrigin']='agent'; a['referencePrompts']=[]
        for variant in item.get('promptVariants',[]):
            start,end=variant['startLine'],variant['endLine']
            if not isinstance(start,int) or not isinstance(end,int) or not 1<=start<=end<=len(lines): raise ValueError(f'资产 {key} / {variant["role"]}：参考图提示词原文行号越界 {start}–{end}')
            raw='\n'.join(lines[start-1:end]).strip()
            if not raw or '```' in raw: raise ValueError(f'资产 {key} / {variant["role"]}：参考图提示词原文为空或包含代码围栏（第 {start}–{end} 行）')
            a['referencePrompts'].append(dict(label=variant['label'],role=variant['role'],text=raw,**source_location(source,start,end)))
        primary=next((v for v in a['referencePrompts'] if v['role']=='main'),None)
        if primary:
            a['prompt']=primary['text']; a['originalPrompt']=primary['text']; a['promptOrigin']='source';a['promptSource']=primary
        elif style: a['prompt']=style+'。'+a['prompt']
        for role,field in [('side','sidePrompt'),('back','backPrompt')]:
            v=next((v for v in a['referencePrompts'] if v['role']==role),None)
            if v:a[field]=v['text']
        assets.append(a)
    from .assets import apply_dependencies
    apply_dependencies({'assets':assets},[dict(id=row['id'],referenceAssetIds=row.get('referenceAssetIds',[])) for row in result['assets']])
    shot_text='\n'.join('\n'.join(lines[d['startLine']-1:d['endLine']]) for d in source['documents'] if d['role']!='references') if source.get('documents') else ('' if source.get('role')=='references' else text)
    expected=[int(m[1]) for m in re.finditer(r'^(?:#{1,6}\s*)?【?(?:分镜|镜头)\s*0*(\d+)',shot_text,re.M)]
    declared=[row['number'] for row in result['shots']]
    if expected and expected!=declared: raise ValueError('镜头覆盖检查失败：原文编号顺序或数量与解析结果不一致')
    repeated=len(set(declared))!=len(declared)
    if repeated and not expected:raise ValueError('镜头序号重复或无效')
    for index,row in enumerate(result['shots']):
        number=row['number']; start=row['promptStartLine']; end=row['promptEndLine']
        if not isinstance(number,int) or number<=0: raise ValueError('镜头序号重复或无效')
        if not isinstance(start,int) or not isinstance(end,int) or not 1<=start<=end<=len(lines): raise ValueError('原文行号越界')
        if result.get('sourceType')!='script' and any(start<=b and end>=a for a,b in ranges): raise ValueError('镜头原文区间重叠，需重新检查解析结果')
        ranges.append((start,end)); original='\n'.join(lines[start-1:end]).strip()
        if not original or '```' in original: raise ValueError(f'镜头 {number}：提示词行号包含围栏或为空（第 {start}–{end} 行）；保留原稿，未应用解析')
        refs=row['refs']
        if len(refs)!=len(set(refs)) or any(k not in ids for k in refs): raise ValueError('镜头引用未定义或重复资产')
        converted=row.get('generationPrompt') if result.get('sourceType')=='script' else original
        if not converted: raise ValueError('原始剧本拆镜缺少生成提示词')
        aliases=[(name,a['id']) for a in assets for name in [a['name']]+a.get('aliases',[])]
        for name,key in sorted(aliases,key=lambda x:len(x[0]),reverse=True):
            if key in refs: converted=converted.replace('@'+name,f'<Picture {refs.index(key)+1}>')
        declarations='\n'.join(f'<Picture {i+1}> 是{next(a["name"] for a in assets if a["id"]==key)}的外观参考。' for i,key in enumerate(refs))
        warnings=list(row.get('warnings',[]))
        if re.search(r'首帧|尾帧|文字保持',original): warnings.append('H3 参考图不锁定首尾帧或文字，生成前需确认适配。')
        headings=re.findall(r'^#{1,2}\s+([^\n]+)', '\n'.join(lines[:start-1]),re.M)
        section=row.get('section') or (headings[-1] if repeated and headings else '')
        shots.append(dict(id=f's{index+1 if repeated else number:03}',name=(section+' · ' if section else '')+row['name'],sourceNumber=number,section=section,scene=row['scene'],seconds=float(row['seconds']),seed=20260916+index,width=1344,height=768,
            originalPrompt=original,prompt=declarations+'\n\n'+converted,refs=refs,info=row['info'],warnings=warnings,versions=[],selected=None,history=[],sourceRange=[start,end],sourceLocation=source_location(source,start,end)))
    project['assets']=assets; project['shots']=shots
    project['importReport']={k:v for k,v in result.items() if k not in ('assets','shots')}
    project['importReport'].update(sourceId=source['id'],documents=source.get('documents',[]),assetCount=len(assets),shotCount=len(shots),coverageChecked=bool(expected),sourceRanges=ranges)
