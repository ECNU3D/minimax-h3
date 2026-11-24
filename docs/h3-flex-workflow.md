# Pika H3 Flex：可选 768p 六步档

2026-11-03。本项目的生产默认仍为 `ref2v-768p-8step`（LightX2V 8 步）；Flex 只有显式选择后才生效。

## 使用位置

- 导演台「分镜制作」上方的「视频生成模式」。
- 「自动制作」的视频模型选项。
- 「分镜测试」右侧的「测试视频生成模式」。

选择 **Pika H3 Flex · 768p（可选）**。在分镜测试中六步采样参数锁定，切回原有 768p 后恢复保存的高级参数。新项目默认、已生成版本和已排队快照不受切换影响。

## 固定配方

| 项目 | 值 |
|---|---|
| profile | `ref2v-flex-768p-6step` |
| 分辨率 | 1344×768，24fps |
| 底模 | 现有 `minimax_h3_ref2va_pruned_int8_convrot.safetensors` |
| 文本编码器 | 现有 Qwen3-VL 32B NVFP4 AWQ |
| 适配器 | `pika_h3_flex_ref2va_v1_bf16.safetensors`，强度 1 |
| 采样器 / 引导 | `lcm` / `BasicGuider` |
| ManualSigmas | `1.0, 0.972973, 0.923077, 0.8, 0.571429, 0.333333, 0.0` |
| 视频 / 音频 shift | 12 / 3 |
| VAE | 现有视频 FP16、音频 FP32 |
| 内存补丁 | 与基线相同：SageAttention、head chunks 4、FFN chunks 8 |
| 输出 | 原生 MP4、独立混合音轨 FLAC、编码前诊断 PNG |

Flex 替换当前加速 LoRA，不叠加 LightX2V/PDD。不能把 Euler 步数改成 6 当作 Flex。官方 Comfy 模板的视频 VAE 为 INT8；本轮保留本项目 FP16 VAE，以避免 A/B 同时改变解码器。能否生成及画质结论以本轮结果为准。

本地输出仍是原生 768p 和混合立体声音轨。FLAC 是同一混合音轨的无损导出，不是对白、音乐、音效分轨。官方云端 4K 与五分轨扩展不属于本地档位。

## 下载与版本

固定模型清单：`docs/h3-flex-models-manifest.json`；安装验证：`docs/h3-flex-model-verification.json`。

- 官方源：Comfy-Org/MiniMax-H3。
- revision：`8118df0eaf5e96acc56eed5daf5229ca81cc05cf`。
- 文件：1,956,172,304 字节。
- SHA256：`de3745ceb7d8d5c20898dd8fa3a05f1c0b00089ccd55297b2a8bab95c766b0e0`。
- 模型许可：MiniMax H3 Community License Agreement。

```powershell
.\.venv-cu130\Scripts\python.exe scripts/download_h3_flex.py
```

只下载此 Ref2VA 适配器，复用已有底模与编码器。该下载器支持续传，安装前验证大小和 SHA256。

## 生产入口和预算

镜头 spec 写入 `"profile": "ref2v-flex-768p-6step"`，其他字段沿用现有格式。默认三张有序参考，`<Picture n>` 与顺序一致。

```powershell
.\.venv-cu130\Scripts\python.exe scripts/h3_batch.py --spec configs/my-shots.json --run-dir runs/my-flex
.\.venv-cu130\Scripts\python.exe scripts/h3_batch.py --spec configs/my-shots.json --run-dir runs/my-flex --campaign my-film --execute
```

继续遵守 [固定入口与 STOP 协议](h3-agent-production.md)。同一逻辑镜头的基线和 Flex 各占一次提交，两者共用 campaign/name，不因模型不同重置额度。

## 本轮比较范围

数据目录：`runs/pika-flex-eval-20261102`。比较表情文戏 5 秒、跑跳开合伞 10 秒、双人打斗争伞 10 秒。原始成对 spec、提示词、参考哈希和回执均保留。

之前一次表情基线在 VAE 加载时崩溃，已对账为失败并保留次数。表情仅剩一次 Flex 提交，基线复用 2026-10-12 相同输入的历史片，因此不计算该组速度优势。

新片沿用已恢复的保守显存服务（关闭动态显存、pinned memory、async offload、cuda malloc，reserve VRAM 4GiB）；两种模型采用相同服务配置。该配置与历史速度不同，不将本轮结果解释为默认服务模式下的普遍速度。

交付目录：`output/pika-flex-eval-20261103`。`comparison.json` 记录实际服务器耗时、缓存节点、输入哈希、输出哈希和技术检查；`index.html` 提供原片并排播放；最终视觉结论另见该目录的 `review.md`。生成成功与视觉通过分别记录。

## 本机实测结果（2026-11-03）

三条 Flex 原片全部完成，已验证 INT8 底模 + Flex LoRA + FP16 视频 VAE 的实际生成链。对应三组共六条对照片；表情基线为历史片。

| 同一保守服务下的 10 秒片 | 原方案总耗时 | Flex 总耗时 | 耗时减少 |
|---|---:|---:|---:|
| 跑跳与开合伞 | 651.41 秒 | 504.60 秒 | 22.5% |
| 双人打斗与争伞 | 648.09 秒 | 505.32 秒 | 22.0% |

这两组的纯采样耗时分别从 546 / 543 秒降为 406 / 402 秒。表情 Flex 用时 280.08 秒，不能与服务设置不同的历史 207.51 秒基线直接比较速度。

画面表现有取舍：Flex 表情末段的笑意较轻，单人开伞的伞体更合理；双人争伞时却出现长伞缩成短黑块的问题。两版都未准确完成跨凳和指定低踢。维持原有默认，Flex 作为可选加速档；不宣称整体质量胜出。详细证据见 `output/pika-flex-eval-20261103/review.md`。

相关 35 项回归测试与前端构建通过；隔离界面验证了保存、重开和切回原方案。原片音频已做技术检查，主观听感与声画同步尚未验收。

## 来源

### 可选参考图尺寸（2026-11-05）

`h3_batch.py` 镜头 spec 可显式设置 `"ref_image_size": "max"`，保留视频输出 1344×768，同时改用原生节点的较高参考图尺寸上限。默认仍为 `match`；旧配置的输入指纹和工作流保持兼容。`max` 被记录进输入指纹，不与旧任务混用。该选项尚未增加到导演台界面。

`max` 不会将小图自动放大；节点按短边 2048 上限缩小及 32 对齐。高参考分辨率增加计算与内存压力，不代表已经证明六人远景脸部改善。2026-11-05 s01 单变量实验记录在 `原创项目/汇丰APP/s01_768p参考max测试_20261105`。参考数量、唯一提交入口、预算与 STOP 规则不变。

- [官方 Comfy 适配器及固定采样配方](https://huggingface.co/Comfy-Org/MiniMax-H3/commit/8118df0eaf5e96acc56eed5daf5229ca81cc05cf)
- [官方 Ref2VA 模板](https://github.com/Comfy-Org/workflow_templates/blob/main/templates/video_pika_h3_flex_ref2va.json)
- [Pika 模型卡](https://huggingface.co/Pika-Labs/Pika-H3-Flex)
