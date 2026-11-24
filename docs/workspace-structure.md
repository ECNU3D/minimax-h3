# 工作区目录与维护约定

整理日期：2026-09-17。此工作区同时包含创作项目、本机模型运行环境和两个独立前端，目录按用途管理。

## 放在哪里

| 内容 | 位置 | 说明 |
|---|---|---|
| 当前 H3 导演台 | `h3_director/` | `backend/` 后端、`agent/` 审查、`web/` 前端、`tests/` 验证 |
| 另一个独立导演工具 | `director_board/` | 保留原 README 与启动方式，不并入 H3 导演台 |
| 创作项目 | `原创项目/`、`参赛项目/`、`行业项目/`、`其他项目/` | 用户项目路径原样保留 |
| 参考与音频创作资料 | `参考资料/`、`配音配乐/` | 与执行环境 `audio/` 分开理解 |
| 通用执行脚本 | `scripts/` | 保留稳定 CLI 路径及脚本间导入，避免打断现有工作流 |
| 制作输入 | `configs/`、`prompts/`、`workflows/` | 配置、提示词、编辑器/API 工作流 |
| 技能 | `skills/` | 唯一源；`.agents/skills`、`.trae/skills`、`.claude/skills` 为同步副本 |
| 当前文档 | `docs/` | 操作手册、模型清单、技术实测；JSON 模型清单也是运行依赖 |
| 旧资料 | `archive/` | 原目录迁移表见 [归档索引](../archive/README.md) |
| GPU 引擎 | `ComfyUI/` | 模型在 `models/`，引用图在 `input/`，视频在 `output/video/` |
| 运行环境 | `.venv-cu130/`、`audio/`、`tools/`、`数字人方案/.venv/` | 当前 CUDA13、独立音频与数字人环境及工具；根目录历史 CUDA12.8 `.venv` 已于 2026-10-17 按用户要求停用并核验目录已不存在；不直接搬动其余环境 |
| 生产证据 | `runs/`、`logs/`、`output/` | `runs/h3-budgets/` 为跨运行目录共享预算，不是可删除缓存 |
| 导演台数据 | `h3_director/data/` | 项目、任务、运行版本、审查附件与导出包 |

## 导演台内部

```text
h3_director/
├── backend/
│   ├── paths.py            APP / ROOT / DATA / PYTHON / HARNESS 路径定义
│   ├── project.py          原稿、资产、镜头、版本与 JSON 存储
│   ├── runner.py           队列、生成、审查与导出
│   └── server.py           本机 HTTP API、媒体流与静态站点
├── agent/harness.mjs       Codex SDK + DeepSeek 视觉审查
├── web/src/                React 页面与样式
├── tests/                  离线回归、隔离 HTTP 检查、已有产物验证
├── data/                   本地运行数据，位置不变
├── dist/、node_modules/    前端构建产物与 npm 依赖
├── server.py               原启动命令的兼容入口
├── harness.mjs             原审查 CLI 的兼容入口
├── start.ps1               Windows 启动脚本
├── README.md               使用、配置与开发说明
└── VALIDATION.md           2026-09-16 的真实生成与审查证据
```

两个兼容入口仅转发到对应实现；不要在入口里复制业务逻辑。Python 导入使用 `backend.project`、`backend.runner`、`backend.server`。路径从模块位置计算，不依赖终端当前目录。

## 备份与后续整理

生成记录引用了原始媒体的绝对路径。只备份项目 JSON 或 ZIP 不能完整恢复全部版本。完整备份应保留工作区相对布局，包含 `h3_director/data/`、`runs/`、`ComfyUI/input/`、`ComfyUI/output/`、原始创作项目和根 `.env`；模型可按固定官方清单恢复，密钥单独安全保存。

不要把预算、STOP 文件、已生成素材或审查证据当缓存清理。`node_modules/`、`dist/`、`__pycache__/` 属于可重建内容，但本次未批量删除。

本次代码整理前的备份与状态哈希在 `h3_director/data/maintenance/2026-09-17-structure/`。项目、队列、生产预算及已有媒体保持原路径；迁移后对这些状态文件复核 SHA256，并核验原视频及审查记录仍可读取。

## 2026-09-17 整理后的检查

通过 35 项离线回归、6 项隔离 HTTP 检查和前端构建；71 个本地文档链接有效。原启动入口从其他工作目录也能运行，审查 SDK 在新目录下可解析，H3 在线节点与模型预检正常。5 份项目、队列和预算文件 SHA256 未改变，已有视频、DeepSeek 审查及交接包核验通过。

本次没有重新提交视频或调用付费审查接口。检查报告：`h3_director/data/maintenance/2026-09-17-structure/validation.json`。导演台 README 已补全启动、制作步骤、配置、目录、测试与排障说明。
