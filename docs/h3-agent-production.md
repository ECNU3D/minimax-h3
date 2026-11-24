# 本地 H3：固定脚本、预算与停止协议

更新：2026-09-16。适用 Windows 本仓库、Trae/其他读取 SKILL.md 的 agent。当前任务是流程优化，**本次未运行新的 H3 生成，也未续做 EP3**。

## 1. 先读什么

- 运行入口：本文 → [三张独立参考](three-white-reference-workflow.md)。模型选择按 [image-model-selection.md](image-model-selection.md)。
- 音频：确有生成/混音需求时才读 [audio-local-workflow.md](audio-local-workflow.md)。
- 成片：[video-editing-workflow.md](video-editing-workflow.md)。
- `archive/docs-copy/`、早期四参考/首帧实验、平台 H3 技能中的视频/音频输入说明不覆盖当前本地能力。

## 2. 固定入口

视频生产统一走 `scripts/h3_batch.py`，禁止 agent 临时发 `/prompt`、直接跑 `generate.py` 或另写循环绕过预算。
`generate.graph()`、`workflow_client.run_job()` 作为其内部实现继续复用；源 ComfyUI/KJNodes 不修改。

镜头 spec 是 JSON 列表：

```json
[
  {
    "name": "ep01_s01",
    "prompt": "prompts/my-shot.txt",
    "refs": ["runs/my-refs/assets/character_front.png", "runs/my-refs/assets/scene.png", "runs/my-refs/assets/prop.png"],
    "seed": 20260916,
    "width": 1344,
    "height": 768,
    "seconds": 10
  }
]
```

路径从仓库根解析。name 代表逻辑镜头，修订不改名。默认恰好三图；预检验证标签集合/顺序对应数量、路径、尺寸和重复 name。它不能理解三张图是否真是人物/场景/道具，仍需目视检查。

2026-09-20 新增专用原生 768p 档位：在镜头 spec 中设置 `"profile": "ref2v-768p-8step"`，使用官方 Ref2V 768p 8-step v1.0 LoRA、Euler、shift 12/3，并保留编码前 PNG。模型固定记录、下载和使用说明见 [768p 工作流](h3-768p-workflow.md)。省略该字段继续使用原4步档位；预算、固定入口和 STOP 规则不变。

2026-10-13 增加显式可选的 [544p 快速预览档](h3-preview-workflow.md)：`ref2v-preview-4step` 与 `ref2v-preview-sol-4step`。用于用户选择的提示词预览，固定960×544、4步；后一档加内置Sol-Attn。保留三参考、原生音轨及全部预算规则，不修改768p生产默认。测试记录见链接文档。

2026-11-03 增加显式可选的 [Pika H3 Flex 768p 六步档](h3-flex-workflow.md)：`ref2v-flex-768p-6step`，采用单独 Flex LoRA、LCM 和固定 ManualSigmas；保留现有 INT8 底模与 FP16 视频 VAE。原 768p 八步默认不变，两个档位的同一逻辑镜头共用提交预算。

```powershell
$env:PYTHONUTF8 = '1'
# 默认仅离线预检，不接触服务，不提交任务。
.\.venv-cu130\Scripts\python.exe scripts/h3_batch.py --spec configs/my-shots.json --run-dir runs/my-film-v1
# 通过预检、确认属于当前用户请求后执行。campaign 在本次任务内固定。
.\.venv-cu130\Scripts\python.exe scripts/h3_batch.py --spec configs/my-shots.json --run-dir runs/my-film-v1 --campaign my-film --execute
# 中断后原目录、原参数恢复，不生成重复任务。
# 要改提示词时用 runs/my-film-v2，但仍用 --campaign my-film，name 仍为 ep01_s01。
```

只选部分镜头：`--only ep01_s01,ep01_s02`，必须是 spec 的完整名称。
历史 EP3 spec 有 1/2/3 张图，离线审计可显式加 `--allow-reference-override`。新制作默认不允许 agent 自行加此例外。

`scripts/47ky_run_shots.ps1` 现为兼容包装入口，默认也是预检；旧的每镜杀服务/四次重试循环已移除，原版保存在复盘 `before/`。

## 3. 预算由脚本执行

账本：`runs/h3-budgets/<campaign>/budget.json`；同 campaign 的所有输出目录共用。

| 条件 | 固定行为 |
|---|---|
| 同一逻辑镜头第 1 次 | 扣一次提交额度，提交前持久保存 |
| 修改 prompt/seed 后重做 | 仍扣该镜头额度，最多 2 次总提交 |
| 旧名 ep03_s07b/c/e | 合并为 ep03_s07 计数 |
| 某镜第 2 次执行仍失败 | 写 STOP，退出 20 |
| 整批累计 3 次 execution_error | 写 STOP，退出 20 |
| 申请第 3 次提交（含视觉重做） | 写 STOP，退出 20，不发任务 |
| 一次等待超过默认 900 秒 | 写 STOP，退出 20；服务端可能仍在运行，不自动杀/重提 |
| 提交结果不明、在途任务失联 | 写 STOP，退出 20，先对账 |
| 客户端中断，有原 prompt ID | 未触发 STOP 时原目录恢复；不重复扣额度 |
| 输出已成功 | 用记录路径 + SHA256 复用，不猜 `_00001_` |

失败计数只认保存的执行失败，画面质量失败通过“每镜总提交次数”限制。新预算不回填旧脚本的历史调用，历史统计另见审计 JSON。
预算和 STOP 不提供 agent 可调用的 reset/force 参数。原目录输入指纹改变会拒绝执行。进程锁防止同 campaign 同时启动多个客户端；崩溃留下锁时先查 PID 和队列，不能自动删锁。

### Goal 调用层必须遵守

```text
执行固定脚本并读取退出码及最后一条 JSON：
0  -> 读取 result.json；执行完成不代表视觉接受
20 -> goal_status=failed；结束当前 goal 循环；向用户报告原因和 STOP.json
10 -> 兼容 PENDING；结束本轮，原任务查询，不重复提交
1  -> 输入/环境/执行错误；先分类，只在账本允许时做一次有理由的修订
```

不能把 20 当作“继续尝试”的工具错误；不能换 campaign/name、删预算、修改脚本、另起 goal 绕过。用户新的明确指令才可调整预算/启动新批次。
**边界：** Python 退出码不会天然终止所有 Trae 自主循环。SKILL/项目规则是 agent 约束；真正强制需调用层配置“退出码 20 为终态，不重启”。本次没有访问/修改 Trae 的 goal 引擎。拥有任意 shell/写文件权限的 agent 能绕过普通脚本，若要不可绕过需在工具权限层只开放该入口。

本仓库已写入 `.trae/rules/h3-production.md`，设置 `alwaysApply: true`，并更新根 `AGENTS.md`；在下一轮 Trae 对话中加载。该规则格式依据 [Trae 官方规则说明](https://docs.trae.cn/ide_rules)。尚未在 Trae UI 内确认本机规则开关/goal 调度设置。

## 4. 服务与资源

先查 `http://127.0.0.1:8188/queue` 和相关 PID/父子关系；venv 的父/子 Python 进程不自动等于两个独立服务。
批量脚本不会启动、重启或杀服务；其他任务在队列里时拒绝新增本批次任务。

本机 9/16 对话使用过只禁 pinned memory 的缓解配置；现可明确表达为：

```powershell
.\start.ps1 -Cuda13 -SageAttention -KJNodes -VramHeadroom 8 -DisablePinnedMemory
```

`-DisablePinnedMemory` 只加 `--disable-pinned-memory`；旧 `-LowMemory` 同时禁 async offload 和 cuda malloc，二者不等价。
这是待继续观察的缓解配置，不是已证实的 VAE 卡死根治。9/16 已出现“每镜重启仍卡住”的反例。不固定每 4 镜/每镜重启；不凭低 GPU 或日志静止断言死锁；环境策略/模型重下/重装也不属于默认重试动作。

图像、H3、TTS、SFX、音乐 GPU 阶段串行。先固定可用资产，不每镜重生人物/场景。音频粗排与画面 EDL 尽早对齐；先做 1–2 个关键镜再批量，失败镜直接用预算约束。

## 5. 测试与实测边界

### 导演台提交边界补充（2026-09-16）

`--execute` 在新提交前只读查询 `/object_info`，核对节点与模型选项；运行条件缺失时不扣额度。`submission.json` 在 POST 前保存客户端 ID 和工作流哈希，随后保存接收或 HTTP 拒绝回执。ComfyUI HTTP 400 校验拒绝不等于排队执行失败：保留已扣提交次数并记录 `rejected`，不自动重发。网络中断、超时和无法对账的请求仍触发 STOP。新增回归：`scripts/test_h3_submission.py`。导演台实时验证记录单独存于 `h3_director/data/live-verification.json`，不改变下面历史测试的范围。

```powershell
.\.venv-cu130\Scripts\python.exe scripts/test_production_tools.py
.\.venv-cu130\Scripts\python.exe scripts/audit_h3_runs.py --output docs/reviews/47ky-20260916/jobs.json
```

新入口已通过离线预检和 10 项预算/复用/字幕回归测试（含模拟超时后禁止第二次提交、跨目录第二次执行失败锁定）；结果见 [validation.json](reviews/47ky-20260916/validation.json)。没有重新跑 GPU 端到端，不能承诺新的产片耗时或卡死消失。
`inputs.json` 保存提示词、seed、有序参考 SHA256、尺寸与固定模型清单；`job.json` 保存服务 history 和真实产物哈希；`result.json` 保存技术体检，视觉状态起始为 pending。
