---
name: hailuo-cli
description: 使用海螺国内站的订阅贝壳，通过已安装的 CLI 生成 MiniMax H3 全能参考视频，支持原生图片引用、最多六条批量提交、原任务续查和自动下载。用于海螺消费者网页生成；本地 ComfyUI H3 和即梦使用各自入口。
---

# 海螺 H3 CLI

本机入口是 `C:/Users/shang/bin/hailuo.cmd`，项目位于 `C:/Users/shang/zheyu/minimax h3`。它通过独立 Chrome 登录目录操作 `https://hailuoai.com`，消费当前账号的订阅贝壳。无需 LuoFlow 插件或 MiniMax API key。源码在项目 `tools/hailuo-cli/`。

## 使用

先运行 `hailuo help` 查看当前命令。创建任务配置时读 [references/config.md](references/config.md)，使用稳定的逻辑 `shotId`、有序参考图、明确的每条积分上限；批量任务还需要总上限。保留用户已授权的任务和花费范围，无需重复确认已有授权。

用户默认限制（2026-10-07）：每个逻辑分镜初拍后最多两次补拍，跨批次和输出目录累计。正式制作配置必须带 `production` 元数据，初拍 `takeIndex=0`，两次补拍为 1、2，`maxRetakes=2`；更小的明确授权仍优先。CLI 总账在付费点击前检查累计次数，含已接收、不确定、失败及拒绝的点击尝试，不含未付费预检错误。达到上限仍不合格就停止该镜并记录缺口，不改镜号、campaign 或删总账继续。原任务查询和重新下载不消耗补拍次数。

分辨率默认 `768p`，当前最高可选 `2K`。用户未指定时使用默认值；指定 2K 时设置 `settings.resolution="2K"`，并按该分辨率的网页报价配置积分上限。批量可为每条镜头分别指定分辨率。

画面比例默认 `16:9`；竖屏任务必须在配置中明确设置 `settings.aspectRatio="9:16"`。CLI 等待每张参考图真正完成上传后才打开原生引用菜单，不能把即时出现的本地缩略图当成上传成功。2026-11-09 已修复这项竞态，并在上传结束后重新应用、核对比例。

```powershell
& 'C:/Users/shang/bin/hailuo.cmd' generate --config 'C:/absolute/path/shot.json' --wait 900
& 'C:/Users/shang/bin/hailuo.cmd' batch --config 'C:/absolute/path/batch.json' --wait 900
```

命令默认在后台完成参数设置、上传、原生 @ 图片绑定、付费提交、等待和下载。`prepare --config ...` 只做上传及完整预检查，不付费。配置中的“图片1”等标记会转成真实图片节点；不要自行把纯文本编号当作已绑定图片。配置可加 `audioReferences`（WAV，最多 3 段，每段 2–15 秒、合计 ≤15 秒），提示词用“音频1”等引用，作为音色参考；写法见 config.md 的音频参考一节。

仅在 CLI 报未登录时让用户运行 `hailuo login`，在其独立窗口完成登录。若首次功能协议出现，用 `prepare --headed` 让用户阅读并确认，随后继续。已保存的登录可以直接复用；不要操作扩展页面、复制普通浏览器 Cookie 或导出凭据。

## 原任务续查

```powershell
& 'C:/Users/shang/bin/hailuo.cmd' status --id 'original-shot-id' --wait 900
& 'C:/Users/shang/bin/hailuo.cmd' batch --config 'C:/absolute/path/batch.json' --resume --wait 900
& 'C:/Users/shang/bin/hailuo.cmd' status --id 'original-shot-id' --offline
& 'C:/Users/shang/bin/hailuo.cmd' download --id 'original-shot-id'
& 'C:/Users/shang/bin/hailuo.cmd' batch --config 'C:/absolute/path/batch.json' --resume --download --wait 0
```

超时、失联、已有回执或平台生成失败后，保留原 ID 并查询已有任务。`--resume` 只查询已尝试的任务，缺少记录也不会补提交。CLI 在唯一付费点击前写入总账，并拦截同 ID 或相同输入的重投；不要删总账、改名或改预算来绕过保护。旧测试 `luoflow-h3-omni-20261005-three-references` 仍是用户报告的未知提交，不能重投。

一次 `batch` 最多提交六个独立的单条任务，共用一个 Chrome 进程。服务端实际运行数量由账号决定，可能排队；不要并行启动多个 CLI 进程争用登录目录。可用 `inspect --output <account.json>` 查看当前账号的会员页面。2026-10-05 本账号标准会员页面标示同时运行 2、排队 8，这不是所有账号的固定上限。

批量会间隔发送提交，避免同一瞬间的请求被平台拒绝。若回执明确是 `2400003 / 当前资源较忙，请重试`，且没有任何任务 ID，授权范围内可显式用 `batch --config ... --retry-busy` 重试这些拒绝项；其他项只查询。CLI 保存尝试历史，每条最多三次请求；不会自动重试，未知或已接受的请求永远不能走此分支。

## 交付与判断

输出目录保存 `preflight.json/png`、原生引用检查结果、精确提示词与参考图哈希、服务端 `submission-response.json`、`job.json`，完成后保存 `video.mp4` 和 SHA256。批量还保存 `batch.json`。总账位于 `%LOCALAPPDATA%/HailuoH3Cli/jobs/`，登录数据不进入项目或 skill。

默认通过原任务的网页下载菜单取得正式 MP4，开启“去除AI生成水印”和“去除品牌水印”，并核对文件名中的 videoID。首次去除 AI 标识需用户本人阅读并确认海螺《去水印规则》：运行 `hailuo watermark-consent --id <已完成任务ID>`，CLI 打开规则窗口，等待本人点击“同意”，再自动下载；不得代点或伪造确认记录。已有确认后后台命令可复用。

`download --id` 可重新下载已有结果，不付费。下载选项 `--watermark none|ai|all` 分别表示去除两类可见水印、保留 AI 标识但去除品牌、保留两类；配置可用 `settings.downloadWatermark`，默认 `none`。这些选项不改变生成输入或解除提交保护。默认去除水印失败时命令报错，不会悄悄交付带标识预览；其他模式的预览退路会记录 `downloadWarning` 和 `downloadMethod=preview-media-url`，不能称作正式下载成功。旧文件按哈希保存在 `video-before-watermark-*.mp4`，旧预览保存在 `preview-video.mp4`。平台规则说明去除可见标识后可能仍保留元数据中的隐式标识，不声称已删除它们。

本账号于 2026-10-06 完成七条原任务的 `none` 下载实测：首次本人确认后，其余六条后台下载成功，完整解码及逐条四帧水印检查通过，旧文件哈希复核通过，下载没有扣费。报告在项目 `runs/hailuo-cli-e2e-20261005/report.md`。2K/4s 只验证了参数及 48 贝壳页面报价，没有付费生成。

检查退出状态和 `job.status`；`pending/accepted/uncertain` 均不代表下载完成。只有 `done` 且文件存在才可交付。比较整个批次前后的余额，单条 `balanceAfter` 可能已包含其他并发任务的扣费。使用 ffprobe 核对成片，再抽帧检查参考角色、场景、道具和动作；执行成功与视觉验收分开记录。网页不暴露 seed、模型权重版本或精确时长保证，不编造这些信息。

安装损坏时，在项目 `tools/hailuo-cli/` 运行 `npm ci --ignore-scripts --no-fund --no-audit`、`npm run build`、`npm test`。普通生成不需要重建或重载插件。
