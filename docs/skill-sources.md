# 剪辑 skill 来源与选择

核查/加入日期：2026-09-16。以项目 `skills/` 为规范来源，同步到 `.trae/skills`、`.agents/skills`、`.claude/skills` 供新一轮 agent 发现。

## 引入：ffmpeg-skill

- 上游：[kajisho5/ffmpeg-skill](https://github.com/kajisho5/ffmpeg-skill)。
- 固定 commit：`cecf37ca8194a83bacf5a564700112f73656c26d`；代码版本 `1.17.3`，MIT 许可，保留 LICENSE。
- 安装路径：`skills/ffmpeg-skill`。使用 skill-installer 的 GitHub 下载脚本，指定 commit，没有运行上游安装脚本或 npm 钩子。
- 文件哈希：[skill-vendor-lock.json](skill-vendor-lock.json)。上游目录保持原样，本地兼容入口放在 `scripts/run_ffmpeg_skill.ps1`。
- 选择原因：本地 FFmpeg/Python、无需云 API；含实际裁切、字幕、拼接、响度、抽帧与 project.json 工具；能输出结构化测量结果。比仅提供命令菜谱更适合约束 agent 执行。
- 本次检查了入口、工具路由、公共 subprocess 执行层及实际使用的工具；不是对全部工具的安全/正确性完整审计。
- 已在本机跑通 doctor、实际成片 probe、已有 H3 素材的 3 秒精确裁切、中文 SRT 烧录与抽帧；没有把全部 42 个工具称为本机验证。

### 本地使用覆盖规则

通用技能会给一些短视频默认策略（变速凑时长、自动缩字、自动切长字幕）。本项目叙事剪辑遵守用户指定时长与原话：这些行为只在请求明确需要时采用；默认先由本地叙事/字幕技能做 EDL 和分句。
字体指定 Microsoft YaHei；caption.py 的字号是 288p ASS 单位，不是像素。Windows 参数通过 `-ToolArgs @(...)` 传递。渲染修改文件留新版本。

## 保留：Remotion 官方技能

仓库原有 `remotion-best-practices` 已含字幕、时序、测字宽、视频、音频规则。本次保留现有版本，未覆盖/升级，也不虚称已经核实其安装 commit。
其官方维护来源为 [remotion-dev/skills](https://github.com/remotion-dev/skills)，功能介绍见 [Remotion Agent Skills](https://www.remotion.dev/docs/ai/skills)。适用于图形包装、动画字幕与 React 视频组件；此次普通叙事剪辑不需要额外建立 React 工程。

## 比较但未加入

- [bryanwhl/ffmpeg-video-editor](https://github.com/bryanwhl/ffmpeg-video-editor)：本次读取固定 commit `d5c3ee6e9896fdabccd4e8b5d68149252bbb682c` 的 SKILL.md/LICENSE。命令示例覆盖面不错，但提供 bash 辅助入口，和已选工具重合；不再安装第二套同类命令路由。
- [n0an/ffmpeg-skill](https://github.com/n0an/ffmpeg-skill)：可作 FFmpeg 配方参考；没有在本机做工具执行验证，不据此评价整体质量。

## 本地补齐的技能

- `h3-production-runner`：固定脚本、持久预算、STOP/goal 退出规则、执行与视觉状态分离。
- `narrative-video-editor`：有效动作选段、反应与声画衔接、可重放 EDL、成片审查；沿用现有 `release-gate` 发布验收。
- `subtitle-layout-qa`：中文分句、安全区、bbox、遮挡、时间轴与实听同步区分。

这几个技能承担项目决策，外部 FFmpeg 技能承担工具执行。不会把所有导演技能重新串成每次必跑的大流程。

## 同步方法

```powershell
.\.venv-cu130\Scripts\python.exe scripts/sync_skills.py --names h3-production-runner narrative-video-editor subtitle-layout-qa ffmpeg-skill h3-storyboard release-gate
# 确认差异后应用（本次已应用）
.\.venv-cu130\Scripts\python.exe scripts/sync_skills.py --names h3-production-runner narrative-video-editor subtitle-layout-qa ffmpeg-skill h3-storyboard release-gate --apply
```

新文件直接复制；修改已有文件前保存到 `.cache/skill-sync-backups/<timestamp>`；不删除其他技能。下一轮对话或刷新技能列表后可发现，当前已加载上下文不会自动改写。
