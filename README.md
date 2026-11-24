# MiniMax H3 本地创作工具

用「映场」导演台导入剧本或分镜，准备参考图，用 ComfyUI 生成 MiniMax H3 镜头，再审查、选取并导出剪辑交接。

## Windows 快速开始

1. 安装 Git、Node.js（满足前端的 Vite 版本要求）和 uv。将 uv 官方发行版的 `uv.exe` 放到 `tools/uv.exe`，运行 `./repair-environment.ps1` 创建 `.venv-cu130`。运行本地生成还需要兼容 CUDA 13 的 NVIDIA 驱动。
2. 运行 `./h3_director/start.ps1`，打开 <http://127.0.0.1:8321/>。脚本安装和构建前端。需要 DeepSeek 智能解析或审查时，将 `.env.example` 复制为根目录的 `.env`，填写自己的凭据。使用 Codex 作为导演 Agent 时，使用本机的 Codex 登录。
3. 要在本机生成视频，在仓库根目录安装固定版本的 ComfyUI 和 KJNodes：

   ```powershell
   git clone https://github.com/Comfy-Org/ComfyUI.git ComfyUI
   git -C ComfyUI checkout --detach (Get-Content docs/comfy-commit.txt -TotalCount 1)
   git clone https://github.com/kijai/ComfyUI-KJNodes.git ComfyUI/custom_nodes/ComfyUI-KJNodes
   git -C ComfyUI/custom_nodes/ComfyUI-KJNodes checkout --detach 57105374f47d0fbb49c9c3926fb981702e0a4b5c
   ```

4. 配置默认的 H3 Ref2VA INT8 768p 八步模型。按清单内的固定 revision 和 `source_path`（缺省时用 `path`）从 Hugging Face 下载，将文件按 `path` 放进 `ComfyUI/models/`，对照 `sha256` 校验。

   | 所需权重 | 清单 |
   | --- | --- |
   | Ref2VA INT8 扩散模型 | [INT8 清单](docs/int8-reference-manifest.json) |
   | 768p Turbo 八步 LoRA | [768p 清单](docs/h3-768p-models-manifest.json) |
   | 文本编码器、视频 VAE、音频 VAE | [H3 清单](docs/models-manifest.json)中的 `text_encoders/` 与 `vae/` 条目 |

5. 运行 `./start.ps1 -Cuda13 -SageAttention -KJNodes -VramHeadroom 8 -DisablePinnedMemory`。ComfyUI 监听 <http://127.0.0.1:8188/>。参考图可直接上传，独立 Qwen 图像服务的配置见[操作说明](docs/h3-qwen21-images.md)。

## 仓库内容

| 内容 | 入口 |
| --- | --- |
| 映场导演台 | [使用说明](h3_director/README.md) |
| H3 批量生成 | [运行方式、重试预算与停止协议](docs/h3-agent-production.md) |
| 三张独立参考图 | [参考图工作流](docs/three-white-reference-workflow.md) |
| 自动化技能 | [技能目录](skills/) · [来源与同步方式](docs/skill-sources.md) |
| 部署、剪辑与音频 | [操作文档索引](docs/README.md) |

模型、运行环境、ComfyUI 和第三方工具需单独安装。`.env`、账号会话、生成输出、日志和个人制作项目保存在各自的本机工作区。历史文档里的本机素材路径用于说明当时的目录结构。

源码采用 [MIT 许可](LICENSE)，仓库中附带的第三方内容遵循各自许可证。
