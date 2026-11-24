---
name: dreamina-cli
description: 在本项目使用官方即梦 Dreamina CLI，复用登录、提交授权范围内的云端图片或 Seedance 视频任务、续查异步结果并记录积分与验收。适用于用户选择即梦 CLI 的生成任务；纯分镜写作沿用 seedance-storyboard，本地 H3 制作沿用 h3-production-runner。
---

# 即梦官方 CLI 项目接入

本技能接入已安装的官方 `dreamina`，用于用户选择的即梦云端工作。保留原素材和本地 H3 的生产流程。读取项目根目录的 `AGENTS.md` 作为入口规则。本技能中的 `AGENTS.md`、`runs/` 等项目路径均从项目根目录解析，避免同步到不同 Agent 的技能目录后相对路径偏移。

## 当前入口与官方依据

- Windows 可执行文件：`C:/Users/shang/bin/dreamina.exe`。PATH 尚未刷新时，在 PowerShell 用 `& "C:/Users/shang/bin/dreamina.exe"` 调用。
- 每次任务先读 `dreamina -h`；使用具体命令前读 `dreamina <subcommand> -h`。模型、分辨率、时长、输入数量和参数组合以当前帮助及服务端返回为准。
- 官方说明随安装保存在 `~/.dreamina_cli/dreamina/SKILL.md`；本机为 [官方 SKILL.md](C:/Users/shang/.dreamina_cli/dreamina/SKILL.md)。需要登录流程或复杂模式的补充说明时阅读它。官方更新入口为 [jimeng.jianying.com/cli](https://jimeng.jianying.com/cli)。
- 复用现有登录。用户要求自行登录时，给出命令并由用户完成；不要代为执行 `login`、`relogin` 或 `logout`。登录确属任务需要且已获授权时，按官方 Device Flow 执行并明确报告最终状态。不要把凭证文件复制到项目。

## 选择生成模式

- 文生图、图生图、图片超清：分别查看 `text2image`、`image2image`、`image_upscale`。
- 文生视频、单图动画、首尾帧：分别查看 `text2video`、`image2video`、`frames2video`。
- 全能参考（图片、视频、音频参考）：查看 `multimodal2video`。智能多帧：查看 `multiframe2video`；两者的参数和模型选择能力不相同。
- 保留用户指定模型、参考职能、顺序、时长和画幅。未指定模型时沿用当前命令默认值；不能将一次 mini 测试变成所有任务的固定模型。
- 用户要求低成本时，先检查指定模型的可用参数，选择满足任务的低费用规格。CLI 返回的 `credit_count` 与余额变化用于核实实际费用；没有报价接口时，不把估计费用写成已确认报价。
- 参考图已存在则复用并检查。用户选择内置 imagegen 时使用该工具，将最终参考图复制到项目输出目录；其他素材来源按用户请求选择。

## 付费任务记录与续查

1. 用 `user_credit` 检查当前账号和余额。说明提交会消耗积分，执行范围遵循用户已有授权；缺少必要预算或重试范围时，只澄清缺少的部分。
2. 在 `runs/<唯一任务目录>/` 保存 `manifest.json`、完整提示词、有序参考文件及 SHA256、CLI 命令和参数、请求模型与规格、CLI 构建信息、提交前积分。命令未暴露 seed 时记录 `null` 和原因。
3. 首次提交前持久记录状态 `submitting` 及本任务提交次数。任务目录已处于 `submitting` 或持有 `submit_id` 时，先对账，避免重复提交。一次视频测试默认只提交一次；批量与重做次数遵循本次用户授权。
4. 保存原始提交回执及 `submit_id`。`gen_status=querying` 表示已受理；之后只用 `query_result --submit_id=<id>` 续查，可加 `--download_dir=<输出目录>` 下载。`list_task` 用于查看已有任务历史，先读帮助。
5. 轮询超时、网络中断或进度静止不构成重提理由。保留任务 ID；提交结果不明时查本地任务记录或报告待对账。服务端仍可能继续运行。
6. `gen_status=fail` 时记录 `fail_reason` 并报告。若返回 `AigcComplianceConfirmationRequired`，告知用户按网页要求完成首次授权/生成；不要擅自增加付费网页任务来解锁。
7. `gen_status=success` 后从实际回执定位下载文件，记录 SHA256、实际时长、尺寸、帧率和音轨；比较前后余额与回执费用。解码并查看关键帧，核对主体、场景和动作。未听取声音或未验证的动作要求需明确标记。

保留生成原片。需要剪辑、字幕或混音时遵循项目已有后期工作流，避免为后期问题重新提交生成。项目文档目前不提供云端运行时预算锁，也没有把 CLI 接入导演台按钮；本技能不宣称这些能力已实现。

## 已完成的项目测试

2026-10-05 的一次测试使用内置 imagegen 参考图、`multimodal2video`、`seedance2.0mini`、5 秒、720p、16:9。只提交一次，回执费用与余额差额均为 30 积分，下载视频为 1280×720，容器时长 5.088 秒；画面保留机器人和场景，但挥手换了另一只手。

可查证记录：从项目根目录读取 `runs/jimeng-mini-omni-5s-20261005-6c3659cf/manifest.json`。这是一条已完成样例，参数和价格不构成未来任务的固定承诺。
