---
name: local-film-audio
description: 为已有短片或导演台剪辑包，用本仓库实测的 Qwen3-TTS、MOSS-SoundEffect v2 和 ACE-Step 1.5 SFT 制作中文配音、音效、背景音乐并交付分轨、真实语音对齐字幕和混音。用于本地后期声音制作，不调用云音频 API、不重新生成视频。
---

# 本地短片声音制作

所有路径以仓库根目录为基准；优先阅读根目录 `docs/audio-local-workflow.md`、`docs/video-editing-workflow.md`、`configs/audio-film-test.json` 和目标音频 run 的 manifest（若存在）。该配置是已测温室示例，**不能原样用于新片**。

## 任务与声音清单

读取交接包的 `TRAE-剪辑任务.md`、`edit-manifest.json`、原始脚本、装配规范和音轨表。脚本里的“后录／后期录制”表示要生成配音，不表示等待真人录音；H3 提示词中的“无人声／无配乐”只约束源视频生成，不取消后期配音配乐任务。

任务要求本地配音配乐时，直接执行声音设计与生成。不要因包里没有 WAV 就只报告缺失；也不要转用 MiniMax 或其他云 API。必要台词生成失败时保留进度、指出具体阻塞，不把无声粗剪当最终交付。

先写 `audio-plan.json`：逐句 ID、逐字台词、说话人、所属镜头、计划窗口、母版 ID、复用关系；另列音效事件、配乐段落和必须保持安静的区间。台词以原文为准，不能用摘要改写。重复呼唤若要求同一录音，用同一个 WAV/hash，不重新抽卡；字幕草稿窗口尚未经过真实语音校准。

## 固定本地模型与分阶段执行

| 内容 | 模型目录 | 独立环境 |
|---|---|---|
| 声音设计 | `audio/models/qwen-design`（Qwen3-TTS VoiceDesign） | `audio/env-tts` |
| 同角色逐句配音 | `audio/models/qwen-base`（Qwen3-TTS Base） | `audio/env-tts` |
| 环境声／动作音效 | `audio/models/moss-sfx`（MOSS-SoundEffect v2） | `audio/env-sfx` |
| 纯器乐背景音乐 | `audio/models/ace`，`acestep-v15-sft`，`acestep-5Hz-lm-1.7B` | `audio/env-music` |

检查环境和各模型的 `snapshot-verified.json`。一次一个 GPU 阶段，用已有入口检查 ComfyUI 队列，不抢占别的生成任务。不要升级环境、自动下载其他模型或调用云接口作为回退。

复制交接包的 `audio-config.template.json`（或已测配置）到新的工作目录，填本片内容并删除所有温室示例任务。`source_video` 使用现有画面母版或包内一个已校验源片段的绝对路径，填真实 SHA256；它在单独音频阶段仅作为受保护的来源锚点，不决定音乐/台词长度。项目说明与配音台词默认中文，模型提示词记录原文和实际发送版本。

当前 worker 的一个 clone 配置只支持一个 `reference_id`。**每个角色用独立配置和 run 目录**，同一角色的所有台词放在该配置的 `clone.jobs` 中；每条有稳定 id、seed、text。`design.text` 是母版准确朗读文本，`design.jobs` 配置 id、seed、instruct，`clone.reference_id` 对应该角色设计声音的 id。不同角色不能共用一个母版。已有合适母版可复用，但须保留 WAV、准确 transcript、hash 和来源；不要只复制一段声线描述就声称一致。

在仓库根目录，配置路径和 run 路径换成实际绝对路径：

```powershell
.venv-cu130/Scripts/python.exe scripts/audio_film_pipeline.py --config "<角色配置.json>" --run-dir "<角色音频目录>" --only design
.venv-cu130/Scripts/python.exe scripts/audio_film_pipeline.py --config "<同一角色配置.json>" --run-dir "<同一角色音频目录>" --only clone
.venv-cu130/Scripts/python.exe scripts/audio_film_pipeline.py --config "<音效配乐配置.json>" --run-dir "<音效配乐目录>" --only sfx
.venv-cu130/Scripts/python.exe scripts/audio_film_pipeline.py --config "<同一音效配乐配置.json>" --run-dir "<同一音效配乐目录>" --only music
```

先填完整配置再开始，不在同一 run 中修改配置。相同配置续跑校验输出哈希；改文本、种子或模型需新版本目录。技术失败或听审不合格默认最多重试 2 次，保留日志与旧版，仍失败就报告具体条目，不能无限抽卡。

MOSS 使用已测100步/CFG4/sigma_shift5；ACE 使用已测 SFT、50步/CFG7/30秒器乐段，按情绪段落生成后剪接，不假设120秒一次生成已验证。音乐 jobs 有 id、seed、bpm、keyscale、caption；音效 jobs 有 id、seed、seconds、prompt。Qwen 采用现有 BF16/SDPA 路径。喊声与特殊表演需实听验证，Base 不支持假定的逐句 instruct 控制；必要时单独设计表演版本并检查声线衔接。

## 对齐与混音

**不要直接跑无 `--only` 的全流程或 `--only mix`。** 现有 `audio_mix.py`、`audio_review.py`、`audio_validate.py` 的默认逻辑是10秒温室专用，含固定素材名和时间，不能用于新片验收。只复用上述四个生成阶段，再根据本片 EDL/cue 用 FFmpeg 或项目专用混音脚本制作，保存可重放命令。

逐句检查 WAV 实际时长与起止，填写 `audio-cues.json`（源路径/hash、原文、角色、源入出点、全局入出点、校准方法与实听状态）。保留尾字、气口和跨镜声尾；超窗先调整留白/EDL或以同文重录，不能删改台词、硬截尾字或无说明加速。字幕从真实语音定时，不能把字数均分、非静音检测或草稿 SRT 当成已听审对齐；本仓库未验证通用强制对齐器，不要冒称已自动逐字对齐。

按画面定位动作音效；持续环境声跨镜连贯。配乐在对白时压低，尊重撤音乐/静默区间。H3 原音另存，按实际听审决定保留环境声或替换，避免双重人声/音乐。

输出48kHz/24-bit的 `dialogue.wav`、`sfx.wav`、`music.wav`、`master.wav` 和AAC成片；保留模型原始 float WAV、配置、模型版本、stage日志和哈希。只换声音时复制压缩视频流并验证前后流 hash；改字幕从干净画面母版/原镜头重建，不能二次覆盖硬字幕。

## 验收和交付

用 `narrative-video-editor`、`subtitle-layout-qa` 和 `release-gate` 完成既有剪辑/发布验收。交付成片、分轨、母版与逐句文本、EDL、校准后 SRT/ASS、audio-plan/cues、复现命令和验收报告。逐条核对必要对白覆盖与重复录音哈希；查全片解码、音频缺失、削波、LUFS/真峰值、对白可懂性、音乐人声污染、动作同步、中文字幕边界。

生成成功、数值检查、实听、用户接受分别记状态。没有实际听音能力就如实标注待听审并交付试听材料，仍完成可执行的生成和混音；不要伪报听过或把未完项藏在“完成”结论里。
