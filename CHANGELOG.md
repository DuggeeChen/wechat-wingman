# 版本记录 / Changelog

## v2.6.0

本次公开发布汇总本地 2.0–2.6 迭代，将默认入口升级为以聊天上下文和身份校验为基础的桌面搭子。此前 GitHub 公开发行版为 v1.0.0；下面的 2.x 小版本是开发迭代记录，并非每项都有独立 GitHub Release。

| 迭代 | 简要变化 |
|---|---|
| 2.0 | 上下文会话、补读片段与前情、说话人位置校验、人工纠正、草稿检查；主流程退出自动画像与 Jev。 |
| 2.1 | 模型与 API 设置、模型列表、连接测试和按接口隔离的凭据。 |
| 2.2 | 目标与底线改为可选特殊要求，默认直接生成；候选方向可直接切换。 |
| 2.3 | 一键读取并生成、精确画面指纹复用、HTTP 连接复用；保留原快捷键。 |
| 2.4 | 回复优先布局、卡片内编辑与复制、快速身份纠正及撤销。 |
| 2.5 | 第一条完整候选提前可复制；识别、生成和首条可用回复分别记录耗时。 |
| 2.6 | 「更多」内新增临时数据清理，限定处理遗留截图、日志和识别指纹。 |

升级保留原配置和凭据。便携版数据目录继续使用 `%LOCALAPPDATA%\微信军师`，源码版使用程序目录。当前会话关闭后清空；旧版手动画像仍保留在磁盘，但不进入主回复流程。

提前显示取决于接口流式支持及输出顺序，不保证固定响应秒数。视觉识别仍需核对。程序不自动发送消息。

**Release summary:** context-aware conversations and speaker correction replace the old default flow. Provider settings, optional requirements, exact-frame recognition reuse, pooled connections, inline editing, early complete replies, stage timing and scoped cleanup are included. Legacy profiles remain manual; the main workflow does not call Jev or send messages automatically.

## v1.0.0

首次公开发行：Windows 屏幕读取、可配置模型接口、回复候选与手动复制。后续主分支增加图标和手动画像管理；v2.6.0 保留兼容模块并重建默认回复流程。
