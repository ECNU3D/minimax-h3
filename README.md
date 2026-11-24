# 映场导演台 · MiniMax H3 本地创作工作台

**简体中文** · [English](README.en.md)

映场把剧本、参考图、镜头生成、审查和剪辑交接放在同一个本地工作区。可以在网页里逐镜制作，也可以由 Codex 等 Agent 直接调用仓库里的脚本。参考图、镜头和后期声音都可以用本地模型完成。

## 工作方式

| 方式 | 适合怎么用 |
| --- | --- |
| **纯本地制作** | 在「分镜测试」里直接编辑提示词、上传参考和试镜。本地 Qwen 或 FLUX 生成参考图，ComfyUI 运行 H3，后期声音由本地音频脚本生成。素材、版本和任务记录都存放在本机。 |
| **Codex 驱动** | 在导演台按项目选择 Codex 作为导演 Agent，复用本机已登录的 ChatGPT 账户来解析剧本、校对原文、审查参考图和视频抽帧。参考资产也可单独选择 Codex Image Gen，用来生图或基于实际参考图改图。 |
| **DeepSeek 导演 Agent** | 按项目选用 DeepSeek 进行解析和审查。在根目录 `.env` 填好自己的 `DEEPSEEK_API_KEY` 即可配置。 |

Codex 和 DeepSeek 按所选任务处理文档、提示词或送审图片，H3 视频生成仍由本机 ComfyUI 执行。也可以让 Codex 这类 Agent 在仓库中直接运行 `scripts/h3_batch.py` 和 `scripts/audio_film_pipeline.py`，用同一套预检、运行记录与恢复机制。视频生产沿用每个逻辑镜头的提交预算和 STOP 机制。详见[导演台手册](h3_director/README.md)和[批量生成协议](docs/h3-agent-production.md)。

## 图片、视频与声音模型

| 制作环节 | 模型或入口 | 用途 |
| --- | --- | --- |
| 本地参考图 | **Qwen Image 2.1** | 导演台默认图片模型。支持文生图、有序参考图生图，以及画笔或套索蒙版改图。可用来制作人物三视图、场景、道具和关键帧。见 [Qwen 图片工作流](docs/h3-qwen21-images.md)。 |
| 本地参考图 | **FLUX.2 Klein 4B Distilled / Base** | 通过 ComfyUI 生成或编辑参考图。Distilled 支持 4 步快速生成，Base 提供 20 步选项。见[图像模型说明](docs/image-model-selection.md)。 |
| 本地视频与原生声音 | **MiniMax H3 Ref2VA INT8** | 默认 768p、24 fps、8 步，支持横屏和竖屏。可用人物、场景和道具参考生成镜头及原生音轨。「分镜测试」可加音频参考，对照同一次生成的 FLAC 和 MP4 音轨。见[分镜测试手册](docs/h3-shot-lab.md)。 |
| 本地对白和旁白 | **Qwen3-TTS VoiceDesign + Base** | 用 VoiceDesign 设计角色声线，再用 Base 复用已选定的声音样本，逐句生成对白或旁白。 |
| 本地音效 | **MOSS-SoundEffect v2** | 生成环境声、物件接触声和动作音效，可作为独立音轨交给后期。 |
| 本地器乐配乐 | **ACE-Step 1.5 SFT** | 按场景情绪和时长生成器乐候选，供选择、剪辑和混音。 |

导演台的剪辑交接包包含选中的镜头、源文档、音频配置模板和制作说明。对白、音效、配乐由交接后的本地音频流程分阶段生成，可以交付分轨和混音。见[本地音频配置与运行](docs/audio-local-workflow.md)和[音频制作技能](skills/local-film-audio/SKILL.md)。

## Windows 快速开始

1. 安装 Git、Node.js（20.19+ 的 20.x 版本，或 22.12+）和 uv。克隆仓库并将 uv 官方发行版的 `uv.exe` 放到 `tools/uv.exe`，然后在仓库根目录运行 `./repair-environment.ps1` 创建 `.venv-cu130`。本地 GPU 生成需要兼容 CUDA 13 的 NVIDIA 驱动。
2. 运行 `./h3_director/start.ps1` 构建并启动导演台，打开 <http://127.0.0.1:8321/>。可以先打开「温室示例」查看资产和分镜，或从「分镜测试」开始。选用 DeepSeek 时将 `.env.example` 复制为 `.env` 并填入自己的密钥。选用 Codex 时使用本机已登录的 Codex，图片生成还需要账号支持 Image Gen。
3. 要在本地生成视频，在仓库根目录安装固定版本的 ComfyUI 和 KJNodes。

   ```powershell
   git clone https://github.com/Comfy-Org/ComfyUI.git ComfyUI
   git -C ComfyUI checkout --detach (Get-Content docs/comfy-commit.txt -TotalCount 1)
   git clone https://github.com/kijai/ComfyUI-KJNodes.git ComfyUI/custom_nodes/ComfyUI-KJNodes
   git -C ComfyUI/custom_nodes/ComfyUI-KJNodes checkout --detach 57105374f47d0fbb49c9c3926fb981702e0a4b5c
   ```

4. 按下列清单的 `revision` 和 `source_path` 从 Hugging Face 下载权重，缺省时用 `path` 作为源路径。保存到 `ComfyUI/models/` 下对应的 `path`，对照 `sha256` 校验。

   | 默认 768p 八步档所需权重 | 清单 |
   | --- | --- |
   | Ref2VA INT8 扩散模型 | [INT8 清单](docs/int8-reference-manifest.json) |
   | 768p Turbo 八步 LoRA | [768p 清单](docs/h3-768p-models-manifest.json) |
   | 文本编码器、视频 VAE、音频 VAE | [H3 清单](docs/models-manifest.json)中的 `text_encoders/` 与 `vae/` 条目 |

5. 启动 ComfyUI，再从导演台提交镜头。可上传现成参考图，也可以按 [Qwen 图片服务](docs/qwen-image-21-local.md)或 [FLUX 模型清单](docs/image-models-manifest.json)配置本地生图。

   ```powershell
   ./start.ps1 -Cuda13 -SageAttention -KJNodes -VramHeadroom 8 -DisablePinnedMemory
   ```

   ComfyUI 监听 <http://127.0.0.1:8188/>。Qwen 图片服务使用独立环境，监听 `8190`。

## 工作流与文档

- 从白底人物、完整场景和白底道具开始，按顺序把三张图交给 H3。[三张独立参考工作流](docs/three-white-reference-workflow.md)
- 管理镜头版本、审核结果与剪辑交接。[导演台使用手册](h3_director/README.md) · [剪辑与字幕工作流](docs/video-editing-workflow.md)
- 查看本机部署记录、音频配置和可复用的 Agent 技能。[文档索引](docs/README.md) · [技能目录](skills/)

权重、运行环境和第三方工具需单独安装。`.env`、账号会话、项目素材和生成记录保存在各自的本机工作区。

源码采用 [MIT 许可](LICENSE)，附带的第三方内容遵循各自的许可证。
