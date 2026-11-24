# 参考图生成视频：Mario / 480p / 5 秒

本机已用项目内的 `Mario.jpg` 完成 H3 首帧图生视频。复用现有 FP8 FL2VA 权重和 Turbo 8 步 LoRA，无需下载 Ref2VA 或安装自定义节点。

## 查看与复用

- [测试视频](../ComfyUI/output/video/h3_mario_i2v_00001_.mp4)
- [可视化工作流：H3-5080-I2V-480p-5s.json](../workflows/H3-5080-I2V-480p-5s.json)
- [API 工作流](../workflows/h3_mario_i2v_api.json)
- [动作及音效提示词](../prompts/mario-i2v.txt)

启动 `start.cmd`，打开 http://127.0.0.1:8188 。在左侧“工作流”中双击 **H3-5080-I2V-480p-5s**；也可以将上面的可视化 JSON 文件拖入 ComfyUI。不要把 API JSON 当作带布局的编辑器工作流。

1. 在 **Load Reference Image** 节点上传或选择新图片。
2. 在 H3 节点修改动作提示词。此次是从跳跃姿势落地，站起后挥手。
3. 保持 864×480、duration=5、turbo_mode=true、turbo_steps=8，点击“运行”。
4. 视频保存在 `ComfyUI/output/video/`，界面工作流前缀为 `H3_Mario_I2V`，自动递增编号。

工作流也保存在 `ComfyUI/user/default/workflows/H3-5080-I2V-480p-5s.json`。参考图片副本保存在 `ComfyUI/input/h3_reference_b9c784b5b507.jpg`；原始 `Mario.jpg` 未修改。迁移到另一台机器时，除工作流和权重外，还需复制这个输入图片，或者重新上传并选择图片。

## 命令行

在项目目录运行：

```powershell
& .\.venv\Scripts\python.exe .\scripts\generate.py --image .\Mario.jpg --prompt-file .\prompts\mario-i2v.txt --width 864 --height 480 --seconds 5 --name h3_mario_i2v
```

`--image` 接受本地图片路径，按文件内容哈希生成输入副本名称；该功能配合本项目的 ComfyUI 使用。换图时同时换提示词中的角色描述。每次提交的实际 API 图与结果保存在 `workflows/` 和 `logs/`。

## 画幅与首帧

流程为 **LoadImage → ResizeAndPadImage → H3 first_frame → 采样 → 视频/音频解码 → SaveVideo**。

Mario 原图为 275×362 的竖图，输出采用此前实测过的 864×480 横屏。补边节点使用 lanczos 等比例缩放和白色补边，保留完整角色比例。H3 的 first_frame 入口内部会直接拉伸到目标画布，所以不能省略补边步骤后直接把竖图接到横屏画布。

本工作流将参考图作为第一帧约束，不是单纯提取角色身份；开头会保留参考图姿势。白色背景与本图匹配，更换其他背景图片时可调整补边方式或选用相近画幅。若改分辨率，必须同时调整补边节点与 H3 节点的宽高，并保持 H3 宽高为 32 的倍数。

## 首次实测

| 项目 | 结果 |
|---|---|
| 输出 | 864×480、124 帧、24fps、实际 5.1667 秒 |
| 生成时间 | 服务端 103.64 秒；客户端 106.51 秒 |
| 模型 | FP8 FL2VA + NVFP4 文本编码器 + Turbo LoRA，8 步 |
| 采样器 / 调度 / 种子 | res_multistep / simple / 20260910 |
| 编码与文件大小 | H.264 + AAC，453,899 字节 |
| 音轨 | 32kHz 双声道，165,888 个解码样本 |
| 整卡显存最高采样值 | 15,503 MiB |
| 系统可用内存最低采样值 | 2.752 GiB |
| GPU 最高采样温度 | 68°C |
| 结果 | success，全部视频帧和音轨可解码，无 OOM |

资源为约 5 秒间隔的整机/整卡采样，非精确模型分配峰值。逐秒画面显示开头保留跳跃姿势，约 2 秒落地，之后站起并抬手挥动；角色比例、红帽和蓝色背带裤等主要特征保持。动作过程中线条和身体形状会有生成变化，不能保证逐像素保持原画。

音频信号有限且非静音，RMS 0.019864，解码峰值 1.01381 略超过 1。未进行人耳音质评分；需要正式发布的音轨可后期检查峰值并限幅，不能仅凭“解码成功”判断音质完美。

[任务记录](../logs/h3_mario_i2v_9f9c9330-49aa-4e94-b824-65f500ab1a55.json) · [资源采样](../logs/h3_mario_i2v_9f9c9330-49aa-4e94-b824-65f500ab1a55.resources.jsonl) · [逐秒画面](../ComfyUI/output/video/h3_mario_i2v_00001_.contact.jpg) · [解码检查](../ComfyUI/output/video/h3_mario_i2v_00001_.inspection.json)

如工作流提示图片不存在，重新上传并选择即可；如提示模型缺失，核对本机模型文件名，不要下载另一套模型来替代。通用维护和 OOM 排查见 [部署手册](../README.md)。

## 可视化工作流验证

已在 ComfyUI 界面打开保存的工作流，确认 Mario 图片预览、白色补边、first_frame 连线、864×480 和 Turbo 8 步参数，并点击“运行”完成第二次验证。任务成功，耗时 99.031 秒（复用了部分缓存，不作为冷启动性能）。[界面验证视频](../ComfyUI/output/video/H3_Mario_I2V_00002_.mp4) 为 124 帧、864×480、5.1667 秒，视频和音轨均完整解码通过。

[界面提交的完整工作流和结果](i2v-ui-validation.json) · [服务日志](i2v-server.log)。可视化 JSON 已通过前端加载并重新保存，包含当前前端实际序列化的节点参数。
