"""Local audio/editing contract and source-matched context for Trae exports."""
import copy
import re
import shutil
from datetime import datetime
from pathlib import Path
from .paths import ROOT
from .project import digest, read, write

WORKFLOW_FILES = (
    'skills/local-film-audio/SKILL.md',
    'skills/narrative-video-editor/SKILL.md',
    'skills/subtitle-layout-qa/SKILL.md',
    'skills/release-gate/SKILL.md',
    'docs/audio-local-workflow.md',
    'docs/video-editing-workflow.md',
)


def folder_name(name):
    """A readable Windows path component, never a user-supplied relative path."""
    name=re.sub(r'[<>:"/\\|?*`\x00-\x1f]', '-', str(name))
    name=re.sub(r'\s+', ' ', name).strip(' .-')[:48].rstrip(' .') or '未命名项目'
    if re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\..*)?',name,re.I):name='项目-'+name
    return name


def export_paths(base, project, job, root=ROOT):
    """Reserve a human-readable package path; persist this choice on the job for resume."""
    if job.get('exportPaths'):return job['exportPaths']
    name=folder_name(project['name'])
    stamp=datetime.fromtimestamp(job['created']).strftime('%Y-%m-%d_%H-%M-%S')
    parent=Path(base)/name;parent.mkdir(parents=True,exist_ok=True)
    for suffix in range(1,10000):
        label=stamp+(f'-{suffix}' if suffix>1 else '')
        folder=parent/label;archive=parent/f'{name}-剪辑素材包-{label}.zip'
        delivery=root/'成片'/name/label
        if archive.exists() or delivery.exists():continue
        if folder.exists():
            owner=folder/'.export-owner.json'
            if not owner.is_file() or read(owner).get('jobId')!=job['id']:continue
        else:folder.mkdir()
        write(folder/'.export-owner.json',dict(jobId=job['id'],projectId=project['id']))
        paths=dict(folder=str(folder.resolve()),archive=str(archive.resolve()),deliveryRoot=str(delivery.resolve()))
        job['exportPaths']=paths
        return paths
    raise ValueError('同名导出目录过多，请检查导出位置')


def delivery_contract(folder,project,root=ROOT,delivery_root=None):
    name=folder_name(project['name'])
    label=folder.name if re.fullmatch(r'\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}(?:-\d+)?',folder.name) else datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    target=Path(delivery_root) if delivery_root else root/'成片'/name/label
    target=target.resolve()
    return dict(root=str(target),videoDirectory=str(target/'视频'),
                finalVideo=str(target/'视频'/f'{name}-成片-v001.mp4'),
                audioDirectory=str(target/'声音'),subtitleDirectory=str(target/'字幕'),
                editingDirectory=str(target/'剪辑工程'),reviewDirectory=str(target/'验收'),
                pathPolicy='project_name_and_export_date',overwriteExisting=False)


def collect_context(sources, folder, root=ROOT):
    """Match both name and full imported text before including version siblings."""
    records, warnings, parents = [], [], set()
    library = root/'原创项目'
    for source in sources:
        name = source.get('name', '')
        if not name or Path(name).name != name:
            continue
        matches = [p for p in library.rglob('*') if p.is_file() and p.name == name
                   and p.read_text(encoding='utf-8-sig') == source['text'].lstrip('\ufeff').replace('\r\n', '\n')]
        if len(matches) == 1:
            parents.add(matches[0].parent)
        elif len(matches) > 1:
            warnings.append(f'{name} 有多份完全相同的本地副本，未猜测装配规范所在版本；请从 source 原文核对后补齐。')
    source_names = {s.get('name') for s in sources}
    for index, parent in enumerate(sorted(parents), 1):
        # Only numbered editorial documents and the known production-plan schema;
        # never bundle old API scripts, credentials, rendered media or other versions.
        candidates = [p for p in parent.iterdir() if p.is_file() and re.match(r'^\d+[-_]', p.name)
                      and p.suffix.lower() in ('.md', '.srt') and p.name not in source_names]
        plan = parent/'_制作数据/production-plan.json'
        if plan.is_file():
            candidates.append(plan)
        for source in sorted(candidates):
            dest = folder/'context'/f'{index:02d}'/source.relative_to(parent)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            records.append(dict(file=dest.relative_to(folder).as_posix(), source=str(source), sha256=digest(dest)))
    return records, warnings


def write_handoff(folder, project, rows, missing, root=ROOT,delivery_root=None):
    delivery=delivery_contract(folder,project,root,delivery_root)
    sources = []
    for i, source in enumerate(project['sources'], 1):
        dest = folder/f'source-{i}.md'
        dest.write_text(source['text'], encoding='utf-8', newline='')
        sources.append(dict(file=dest.name, name=source['name'], role=source.get('role'), sha256=digest(dest)))
    context, warnings = collect_context(project['sources'], folder, root)
    workflow = []
    for relative in WORKFLOW_FILES:
        dest = folder/'workflow'/relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root/relative, dest)
        workflow.append(dict(file=dest.relative_to(folder).as_posix(), sha256=digest(dest)))
    template = copy.deepcopy(read(root/'configs/audio-film-test.json'))
    template['source_video'] = str((folder/rows[0]['media']).resolve()) if rows else ''
    template['source_video_sha256'] = rows[0]['sha256'] if rows else ''
    for stage in ('design', 'clone', 'sfx', 'music'):
        template[stage]['jobs'] = []
    template['design']['text'] = ''
    template['clone']['reference_id'] = ''
    template['_instructions'] = '待填模板，不可直接执行。每个角色另存一份完整配置和独立run；只运行design/clone/sfx/music，禁止直接套用温室mix。见本地音频技能。'
    write(folder/'audio-config.template.json', template)
    models = {stage: template[stage]['model'] for stage in ('design', 'clone', 'sfx', 'music')}
    audio = dict(status='pending', localOnly=True, requiredTracks=['dialogue', 'sfx', 'music'],
                 models=models, configTemplate='audio-config.template.json',
                 skill='workflow/skills/local-film-audio/SKILL.md',
                 pipeline=str(root/'scripts/audio_film_pipeline.py'),
                 generationStages=['design', 'clone', 'sfx', 'music'],
                 mixMode='project_edl_not_greenhouse_demo',
                 subtitleAlignment='actual_generated_speech',
                 environmentFilesPresent={name:(root/f'audio/env-{name}/Scripts/python.exe').is_file() for name in ('tts','sfx','music')},
                 modelManifestFilesPresent={stage:(root/path/'snapshot-verified.json').is_file() for stage,path in models.items()})
    manifest = dict(schemaVersion=3, project=project['name'], shots=rows, missing=missing, status='draft',delivery=delivery,
                    audioReview='pending', subtitleReview='pending', workspaceRoot=str(root),
                    sources=sources, context=context, workflow=workflow, warnings=warnings, audioProduction=audio)
    write(folder/'edit-manifest.json', manifest)
    context_links = '\n'.join(f'- [{r["file"]}]({r["file"]})' for r in context) or '未找到与导入原文唯一匹配的本地配套文档；从 source 原文提取台词/声音/时间线，不臆造缺失信息。'
    brief = f'''# {project['name']} · 剪辑、配音与配乐任务

请完成这份交接包的剪辑和本地声音制作：**逐句中文配音 + 环境/动作音效 + 背景音乐 + 实际语音对齐字幕 + 最终混音成片**。缺少声音文件时，直接用下面指定的本地模型生成，不停在“待后录”的无对白粗剪。

## 工作位置与资料

- 仓库工作目录：`{root}`。脚本从此目录运行；包内 media/source/context 路径相对本任务文件。
- 采用版本和哈希见 [edit-manifest.json](edit-manifest.json)，完整导入原文见 source-*.md。按清单顺序剪辑，不按镜号重新排序。
- 先读仓库 `skills/local-film-audio/SKILL.md`、`skills/narrative-video-editor/SKILL.md`、`skills/subtitle-layout-qa/SKILL.md` 和 `skills/release-gate/SKILL.md`；包内 workflow 保存了本次导出的技能/规范快照。
- 下列 context 文件由“文件名 + 完整导入文本”匹配到同版本目录后复制，保留其原始状态说明。旧的“未生成/后录/文本验收通过”等描述不是当前素材或声音验收结论。

{context_links}

## 固定交付位置

本次交付根目录：`{delivery['root']}`。开始剪辑前创建这些子目录；不要从交接包的编号或任务 ID 推导输出路径。

- 成片 MP4：`{delivery['finalVideo']}`。片名可以按剧本改成实际片名，所有最终 MP4 必须保存在 `视频` 子目录。
- 对白、音效、音乐、master 分轨和角色母版：`{delivery['audioDirectory']}`。
- 校准后的 SRT / ASS：`{delivery['subtitleDirectory']}`。
- EDL、audio-plan.json、audio-cues.json、配置、生成 run、日志与可重放脚本：`{delivery['editingDirectory']}`。
- 验收报告、抽帧和试听材料：`{delivery['reviewDirectory']}`。

`edit-manifest.json` 的 `delivery` 字段是本次输出路径约定。源素材继续从本包 media 读取，工程中的路径指向实际文件；不要移动源文件来适配新目录。成片不得只留在 `runs/<任务ID>/_edit/out` 或其他纯编号目录。已有同名文件时使用 v002、v003 等新版本，保留旧版，不覆盖。完成后在交付根目录写 `交付清单.md`，列出实际成片及分轨路径、验收状态，并向用户提供可点击的成片绝对路径。

## 必须执行的声音工序

1. 读剧本、装配规范和声音行，建立 audio-plan.json：逐字台词、说话人、镜头、计划窗口、复用母版、音效动作点、音乐段落和静默区间。原文“后期录制”由你用本地 TTS 完成；H3 的“无人声/无配乐”只约束源视频，不约束后期。配音不得摘要改词。
2. 使用 **Qwen3-TTS VoiceDesign + Base** 为不同角色建立固定母版并逐句生成；同一角色复用声线。要求同一录音的重复台词复用同一 WAV/hash，不重复生成。使用 **MOSS-SoundEffect v2** 生成音效，**ACE-Step 1.5 SFT** 生成纯器乐配乐。不要调用 MiniMax/其他云音频 API，也不要复用来源不明的旧云音轨代替本次本地制作。
3. 从 audio-config.template.json 填写本片配置，每个角色独立配置/run。通过仓库 scripts/audio_film_pipeline.py 的 --only design / clone / sfx / music 分阶段运行；先检查 ComfyUI 队列，模型串行使用 GPU。**不要跑默认全流程或 --only mix：现有默认混音/验证脚本写死了温室样片，不适用于本片。** 具体字段、命令和恢复方法见本地音频技能。
4. 配音生成后测真实语音起止和停顿、核对尾字并校准字幕；草稿 SRT 不能直接标为已对齐。超窗调整留白/EDL或同文重录，不截断、删词、机械压缩。按本片全局时间线制作音效/音乐分轨，对白期间压低音乐，严格保留原规范的撤音乐与静默窗口。
5. 保留源视频/旧成片/原始音轨，新建本次交付目录。输出对白、音效、音乐三类分轨及 master；仅换声音可复制压缩视频流并核对流哈希，改字幕从干净画面重建。不得因字幕、配音或混音问题重新生成 H3。

## 交付与完成标准

交付成片 MP4、对白/音效/音乐/master WAV、角色母版与逐句 WAV/文本、EDL、校准后的 SRT/ASS、audio-plan.json、audio-cues.json、配置/种子/模型版本/hash/生成日志、可重放剪辑与混音命令、验收报告。

必听台词逐条核对覆盖；检查音乐和音效真实存在且已混入、撤音乐区间、全片解码、削波/LUFS/真峰值、字幕真实中文边界、跨镜字幕与声音同步。Agent 视觉初筛只看抽帧，不代表动作/口型/声音/文字验收；技术通过、实际听音和人工接受分别记录。不能用字幕替代必要人声，也不能只做计划就宣称完成。生成失败时保存已完成部分和日志，报告具体阻塞；没有实际实听能力就交付试听材料并标记待听审。

缺少镜头：{', '.join(missing) or '无'}。
当前包是制作输入，配音/音乐/音效尚未由本次导出执行，最终验收仍待完成。
'''
    (folder/'TRAE-剪辑任务.md').write_text(brief, encoding='utf-8')
    return manifest
