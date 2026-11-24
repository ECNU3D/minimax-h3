# 配置与批量

## 单条

将新任务写为 UTF-8 JSON。所有参考图路径、promptFile 和输出路径相对于 JSON 文件所在目录，不是 shell 当前目录。

```json
{
  "shotId": "campaign-shot-01",
  "settings": {
    "site": "cn",
    "mode": "全能参考",
    "resolution": "768p",
    "aspectRatio": "16:9",
    "durationSec": 4,
    "maxCredits": 28
  },
  "prompt": "以图片1锁定机器人，以图片2锁定温室，以图片3锁定浇水壶。机器人拿起浇水壶给小苗浇水。",
  "references": ["../assets/robot.png", "../assets/greenhouse.png", "../assets/can.png"],
  "outputDir": "../runs/campaign/shot-01"
}
```

支持 1–12 张 PNG/JPEG/WebP，提示词必须引用每张图且不能引用越界编号。可用 `promptFile` 替代 `prompt`，内容为 UTF-8。按用户的参考图数量和顺序执行；本项目默认角色白底、完整场景、道具白底三张独立图。

### 音频参考（音色参考，2026-11-22 加入）

```json
{
  "references": ["../ref/girl.png", "../ref/room.png"],
  "audioReferences": ["../voice/girl.wav"],
  "prompt": "图片1锁定女孩，图片2锚定房间。女孩说话的音色参考音频1，只参考音色，不照搬音频里的内容。……"
}
```

- 网页全能参考的同一个上传框接收图片和音频，@ 菜单里音频单独编号为“音频1、音频2”，内部名 `asset-音频N`。CLI 先按顺序上传全部图片，再上传音频，并把提示词里的“音频N”绑定成原生引用；预检要求每个“音频N”都是原生节点，参考计数等于图片数加音频数。
- 目前只接受 WAV，本地读取时长：最多 3 段，每段 2–15 秒，合计不超过 15 秒，图片和音频合计不超过 12 个文件。音频必须和图片一起传。
- 音频卡片一出现就带一张 https 背景图，CLI 以 `<audio>` 拿到 https 地址作为上传完成的依据。
- 有音频时，音频哈希计入任务指纹；没有音频的旧配置指纹不变。
- 同日实测：2674×1024（约 2.6:1）的拼图在网页上传失败，2048×1024（2:1）可以。宽图请控制在 2:1 以内。

`settings.resolution` 可省略，默认 `768p`；当前可选值为 `"768p"` 和 `"2K"`，最高 2K。同一批量的各镜头可分别选择分辨率，积分上限按各自实际报价核对。

当前支持 MiniMax H3、国内站、全能参考，768p 或 2K，4–15 秒。`settings.aspectRatio` 默认 `16:9`；竖屏明确填写 `9:16`。网页参数配置和付费前检查都核对该比例，上传参考图后会再次应用参数，避免自动构图改变比例。其他配置允许的比例仍以网页是否实际提供为准，不可用时付费前报错。

以上 28 贝壳是本账号在 2026-10-05 的 768p/4s 实测报价示例，2K/4s 的不付费页面检查报价为 48。2026-11-09 修复后已在真实网页完成 2K/8s/9:16 预检，报价 96；生成和下载结果单独记录，预检不能算成片验证。命令仍以网页报价核对上限，不同参数或价格变动会在付费前拦截。实测 768p 的 4 秒选项文件时长为约 4.46 秒。

`settings.downloadWatermark` 默认 `"none"`，通过网页下载菜单去除 AI 及品牌两类可见水印；`"ai"` 保留 AI 标识、去除品牌；`"all"` 保留两类。命令行 `--watermark` 可覆盖配置，重新下载不重新生成。首次去 AI 标识须用户本人在 `hailuo watermark-consent --id existing-shot-id` 打开的规则窗口点击同意；agent 不得接受协议或伪造本机确认记录。

付费端到端实测覆盖 768p/4s/三图参考；其他参数虽有配置和页面检查支持，不应表述为已完成付费实测。

`shotId` 为最多 121 个英文、数字、下划线或连字符，首字符须英文或数字。一个已尝试任务保留同 ID；用户明确追加生成新镜头时使用独立逻辑 ID。

## 逻辑分镜补拍上限

正式制作的每条配置同时填写以下元数据；默认初拍一次、最多两次补拍。所有批次共用同一 campaign 和逻辑镜号。

```json
{
  "shotId": "mama-school-ep001-20261007-s01-pickup-01",
  "production": {
    "campaignId": "mama-school-ep001-20261007",
    "logicalShotId": "s01",
    "takeIndex": 1,
    "maxRetakes": 2
  }
}
```

这是元数据片段，仍须保留上述单条配置的 settings、prompt/promptFile、references 与 outputDir。初拍 ID 必须为 `campaignId-logicalShotId`；补拍为同一基础 ID 加 `-pickup-01` 或 `-pickup-02`。`takeIndex` 只允许 0–2，不能改名制造第三次补拍。`maxRetakes` 可以更小，不能超过 2。

累计检查读取持续总账，包括同一基础 ID 的历史记录，即使旧记录没有 production 字段或输出在其他目录。生成前预检未点击不计数；已点击且未知、失败或被拒的尝试保守占用次数。修改提示词或种子不能重置累计数。status、resume 和 download 不付费、不增加次数。元数据不能替代单条/批量积分上限或已有更小的明确授权。

## 批量

```json
{
  "batchId": "campaign-batch-01",
  "maxTotalCredits": 168,
  "shots": ["shot-01.json", "shot-02.json", "shot-03.json", "shot-04.json", "shot-05.json", "shot-06.json"],
  "outputDir": "../runs/campaign/batch-01"
}
```

`shots` 为 1–6 个单条配置文件路径，相对于批量文件。ID、生成输入及输出目录均不能重复，每条积分上限之和不能超过 `maxTotalCredits`。批量先完成所有预检查，再每条间隔约三秒发送提交；服务端接受后按账号配额同时运行和排队。单条失败或超时不自动重投。

续查保持原配置及镜头 ID：`hailuo batch --config batch.json --resume --wait 900`。结束后读 `batch.json.jobs` 的回执、状态及成片路径。`batch.json.status=incomplete` 时逐条查询现有任务，不能重跑不带 `--resume` 的提交命令。

仅当回执明确返回资源忙拒绝（`2400003`），没有 task/batchID/cardId/videoIDs，且用户范围允许继续测试时，显式执行 `hailuo batch --config batch.json --retry-busy --wait 900`。它只重新准备这些拒绝项，已接受或完成的其他项只查询；每条最多三次请求，历史回执留存 `submission-response-attempt-N.json`。不能与查询命令 `--resume` 合并，也不能用于超时/未知状态。没有盲目自动重投或新增积分预算。

## 状态与异常

- `preparing/preflight_error`：没有成功完成付费点击；先核对是否存在 `submittedAt` 或回执，修正检查问题后仍用原 ID。上传时出现本地缩略图、参考数量增加，都不表示上传完成；CLI 等到 `aria-busy=false`、无加载图标且图片成为 HTTPS 素材后才开始绑定原生引用。上传超时保留错误，不能跳过检查提交。
- `attempted/uncertain`：点击已尝试，回执不确定；只查原任务。
- `accepted`：保存了服务端 batchID 或唯一匹配任务卡，等待结果。
- `done`：已下载并记录哈希。
- `failed/rejected`：平台失败或明确拒绝，保存错误；不会自动重投。

CLI 不根据“余额没变化”认定未知提交可重投。若排他锁残留，确认记录中的进程已结束并检查原任务，处理该具体中断状态；不要删除任务记录或直接再次付费。后台网页结构或登录失效可能使检查失败，先保留诊断截图再修复。
