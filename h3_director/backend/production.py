"""Automatic-production selections supported by the existing bounded executors."""
from .agent import provider,selection
from pathlib import Path
from .project import current,selected,digest
from scripts.generate import NATIVE_LANDSCAPE,NATIVE_PORTRAIT

IMAGE_MODELS=('inherit','qwen21','distilled','base','codex')
VIDEO_MODEL='h3_ref2va_int8_turbo_768p_8step'
LEGACY_VIDEO_MODEL='h3_ref2va_int8_turbo'
VIDEO_PROFILE='ref2v-768p-8step'
PREVIEW_MODEL='h3_ref2va_int8_turbo_544p_4step'
PREVIEW_PROFILE='ref2v-preview-4step'
FLEX_MODEL='h3_ref2va_int8_flex_768p_6step'
FLEX_PROFILE='ref2v-flex-768p-6step'
VIDEO_PROFILES={VIDEO_MODEL:VIDEO_PROFILE,PREVIEW_MODEL:PREVIEW_PROFILE,FLEX_MODEL:FLEX_PROFILE,LEGACY_VIDEO_MODEL:'legacy-ref2v-4step'}
PROFILE_DIMENSIONS={VIDEO_PROFILE:NATIVE_LANDSCAPE,PREVIEW_PROFILE:(960,544),FLEX_PROFILE:NATIVE_LANDSCAPE}
RESOLUTIONS={'landscape':NATIVE_LANDSCAPE,'portrait':NATIVE_PORTRAIT}

def shot_dimensions(profile,shot):
    stored=(shot.get('width',NATIVE_LANDSCAPE[0]),shot.get('height',NATIVE_LANDSCAPE[1]))
    if profile==VIDEO_PROFILE:
        orientation=shot.get('videoResolution','portrait' if stored==NATIVE_PORTRAIT else 'landscape')
        return RESOLUTIONS[orientation]
    return PROFILE_DIMENSIONS.get(profile,stored)

def selected_profile(project):
    # Old projects keep the established 768p default for new submissions.
    value=project.get('videoProfile')
    return value if isinstance(value,str) and value in PROFILE_DIMENSIONS else VIDEO_PROFILE

def set_video_profile(project,value):
    if not isinstance(value,str) or value not in PROFILE_DIMENSIONS:raise ValueError('不支持的视频生成模式')
    project['videoProfile']=value

def retry_limit(value):
    if isinstance(value,bool) or not isinstance(value,int) or not 0<=value<=10:
        raise ValueError('最大重试次数必须是 0–10 的整数（不含首次生成）')
    return value

def reference_readiness(project,shots=None,verify_hashes=False):
    """Only selected, current, approved versions can feed the video-only batch."""
    required={};byid={a['id']:a for a in project['assets']}
    for shot in project['shots'] if shots is None else shots:
        for key in shot['refs']:required.setdefault(key,[]).append(shot['id'])
    problems=[]
    for key,shot_ids in required.items():
        a=byid.get(key);v=selected(a) if a else None;reason=''
        if not a or not v:reason='尚未生成或未选择参考图版本'
        elif not current(project,'assets',a):reason='参考图已过期，需重新生成并审批'
        elif not v.get('files') or any(not Path(f.get('path','')).is_file() for f in v['files']):reason='参考图文件缺失，需重新生成或上传'
        elif not (v.get('humanAccepted') or (v.get('review') or {}).get('verdict')=='pass'):reason='尚未审批通过，请完成 Agent 初筛或人工采用'
        elif verify_hashes:
            try:
                if any(digest(Path(f['path']))!=f.get('sha256') for f in v['files']):reason='参考图文件已改变，需重新导入并审批'
            except OSError:reason='参考图文件无法读取，请检查后重新审批'
        if reason:problems.append(dict(id=key,name=a['name'] if a else key,shots=shot_ids,reason=reason))
    return dict(ready=not problems,requiredCount=len(required),problems=problems)

def require_references(project,shots=None):
    report=reference_readiness(project,shots,verify_hashes=True)
    if not report['ready']:
        raise ValueError('请先到参考图页面生成并审批所需参考图，再制作分镜：\n'+'\n'.join(f'{p["name"]}（{p["id"]}）：{p["reason"]}' for p in report['problems']))

def configure(project,options,scope='all'):
    if not isinstance(options,dict):raise ValueError('自动制作设置无效')
    allowed={'imageModel','videoModel','videoResolution','videoSeconds','agentProvider','agentModel','agentThinking','autoReview','maxRetries','regenerateAssets'}
    if set(options)-allowed:raise ValueError('包含不支持的自动制作设置')
    image=options.get('imageModel','inherit');video=options.get('videoModel',{PREVIEW_PROFILE:PREVIEW_MODEL,FLEX_PROFILE:FLEX_MODEL}.get(selected_profile(project),VIDEO_MODEL))
    resolution=options.get('videoResolution','inherit');seconds=options.get('videoSeconds','inherit')
    if image not in IMAGE_MODELS or video not in VIDEO_PROFILES or resolution not in ('inherit',*RESOLUTIONS):raise ValueError('不支持的图片/视频模型或分辨率')
    profile=VIDEO_PROFILES[video]
    dimensions=PROFILE_DIMENSIONS.get(profile)
    fixed_landscape=profile in (PREVIEW_PROFILE,FLEX_PROFILE)
    if scope!='assets' and fixed_landscape and resolution=='portrait':raise ValueError('当前视频模式仅支持横屏 '+ ' × '.join(map(str,dimensions)))
    if seconds!='inherit' and (isinstance(seconds,bool) or not isinstance(seconds,(int,float)) or not 0<seconds<=15):raise ValueError('视频时长需大于 0 且不超过 15 秒')
    if 'autoReview' in options and not isinstance(options['autoReview'],bool):raise ValueError('自动初筛设置无效')
    if scope not in ('all','assets','shots'):raise ValueError('自动制作范围无效')
    regenerate=options.get('regenerateAssets',False)
    if not isinstance(regenerate,bool) or (regenerate and scope!='assets'):raise ValueError('全部重做仅支持参考图批量任务')
    if scope=='assets' and (resolution!='inherit' or seconds!='inherit'):raise ValueError('参考图批量任务不能修改视频参数')
    if scope=='shots' and image!='inherit':raise ValueError('分镜批量任务不能修改参考图模型')
    chosen={**project,**options}
    retries=retry_limit(options.get('maxRetries',1))
    settings=dict(scope=scope,imageModel=image,videoModel=video,videoResolution=resolution,videoSeconds=seconds,
                  maxRetries=retries,agentProvider=provider(chosen),**selection(chosen),autoReview=options.get('autoReview',project.get('autoReview',True)))
    settings['regenerateAssets']=regenerate
    # Current usable versions keep their original generation settings and are reused.
    for asset in project['assets'] if scope!='shots' else []:
        if image!='inherit' and (regenerate or not selected(asset)):
            asset['provider']='codex' if image=='codex' else 'local'
            if image!='codex':asset['imageVariant']=image
    for shot in project['shots'] if scope!='assets' else []:
        if not selected(shot):
            if resolution!='inherit' and not fixed_landscape:
                if profile==VIDEO_PROFILE:shot['videoResolution']=resolution
                else:shot['width'],shot['height']=RESOLUTIONS[resolution]
            if seconds!='inherit':shot['seconds']=float(seconds)
            shot['width'],shot['height']=shot_dimensions(profile,shot)
    if scope!='assets':
        project['videoProfile']=profile
        if fixed_landscape:settings['videoResolution']='landscape'
    for key in ('agentProvider','agentModel','agentThinking','autoReview'):project[key]=settings[key]
    project['productionSettings']=settings
    project.setdefault('productionSettingsByScope',{})[scope]=dict(settings)
    return settings
