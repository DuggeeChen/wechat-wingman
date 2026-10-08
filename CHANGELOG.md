# 版本记录 / Changelog

## v2.6.4

修复反复提示「没有识别到聊天对象」的一种已复现原因：窗口选择误选不可见的大尺寸微信窗口，PrintWindow 返回成功但图片全黑。

- 窗口选择排除不可见及被系统隐藏的窗口，正确识别已最小化的微信；有多个可用微信窗口时优先当前前台窗口。
- 上传前检查黑屏、空白及纯色截图。正常后台截图不切前台、不增加模型请求。
- 后台抓图失效时将微信切到前台，等待短暂绘制后只截取该窗口；检查前台归属、屏幕边界、遮挡和位置变化。仍无效则停止，不发送黑图。
- 截图故障、聊天类型未确认与确实没打开会话分别提示；识别提示词明确顶栏与裁剪留白的含义。
- 新增 19 项隐藏窗口、黑图回退、遮挡、变化及无效截图不调用模型的检查。原有 158 项回归通过；本机验证恢复微信后能捕获清晰标题及消息，不上传真实聊天进行验证。

**Patch summary:** ignore hidden/cloaked windows, detect invalid captures before upload, and use a guarded foreground fallback only when background rendering fails. Correct minimized-window detection prevents hidden auxiliary windows from being sent to the model.

## v2.6.3

修正 v2.6.2 将方向切换与换写绑定的交互，并加强语气风格和方向差异。

- 方向按钮即时显示该方向现有回复；切回来复用最新生成或编辑的文字，不请求模型。卡片上的「换一条」单独触发该方向的文字生成。
- 换写继续保留其他卡片；恢复上一版只还原这一条，不覆盖其他卡片的手工修改。
- 风格名称和说明作为明确的写作指令传给模型，落实到用词、句式、节奏、语气词和表情；修改当前风格后旧建议失效。
- 五种原版内置风格升级为具体描述，原样的旧默认说明在读取时升级到内存，个人配置不自动写回；自定义名称、修改过的说明和空说明保留。
- 要求不同方向改变沟通行动或立场，并携带具体用意。重复初始候选合并；换写拦截原样及高度相近的文本，不仅检查标点。相似度是文字检查，不是完整的语义判断。
- 主流程 158 项检查通过。另用同一虚构情景、同一方向实测默认/商务/亲密，输出呈现了口语、专业与熟络表达的差异；示例见 [语气说明](docs/VOICE.md)。

**Patch summary:** selecting a direction reuses its current reply; an explicit rewrite action generates new content. Voice definitions become system-level writing instructions, original built-ins get concrete descriptions while custom edits survive, and strategy intents plus duplicate checks reduce interchangeable candidates. Voice effects were sampled with fictional text, without uploading real chats.

## v2.6.2

修复点击回复方向只调换已有卡片顺序、不产生新内容的问题。

- 点击方向现在按该方向换写一条新回复，只更新所选卡片，保留其他方案；再次点击同一方向也会换写。
- 使用现有已读上下文，单次换写只发起一次文字生成请求，不重新识别截图。流式接口返回第一条完整新回复后仍可提前复制。
- 界面改为「按方向换写 · 点击生成新回复」，等待时显示所选方向并防止连点发起重复请求。
- 原样复用已有内容、仅改变标点或空格的结果不会当作新回复。失败、取消和备用模型切换会恢复原方案，完成后可恢复换写前的建议。
- 新增 15 项回归检查，主流程共 141 项通过，覆盖三种方向及重复点击、编辑保留、复制、文本请求、取消、重复输出和迟到事件。

**Patch summary:** direction buttons now generate one fresh reply using the selected direction instead of merely sorting existing cards. Other cards remain available; complete streamed replies can be copied early. Replayed output is rejected, cancellation/failure restores the original cards, and a completed rewrite can be reverted without a request.

## v2.6.1

修复读取截图时反复出现「模型返回格式不完整」的问题。

- 对 DeepSeek 官方 `deepseek-flash` / `deepseek-v4-pro` 的主流程启用 JSON 输出；截图识别明确关闭思考，回复生成保留原有思考设置。
- HTTP 200 不再等同于有效结果：保留流式结束原因，区分空正文、输出上限截断和服务端中断。
- 官方 DeepSeek 截图识别遇到空正文、截断或无效 JSON 时，最多恢复一次，复用原截图并共用原 60 秒上限；正常成功不增加请求。
- 读取结果兼容 BOM、大小写代码围栏和 JSON 前后说明；重复字段、多个对象和真正截断仍拒绝，身份与上下文校验保持有效。
- 新增 16 项回归测试，主流程共 126 项通过。当前配置接口另用完全虚构画面实测，首次返回约 1.2 秒，双方身份及消息正确；该结果不代表真实画面的固定耗时。

**Patch summary:** structured output and explicit non-thinking screenshot recognition for supported official DeepSeek models; preserve finish reasons, reject empty/truncated output, recover recognition once within its original deadline, and accept harmless JSON wrappers without guessing missing content. Custom endpoints keep their existing request parameters.

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
