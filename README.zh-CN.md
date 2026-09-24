<p align="center">
  <img src="assets/wingman.png" alt="微信回复军师" width="104">
</p>

<h1 align="center">微信回复军师 · WeChat Wingman</h1>

<p align="center"><b>只读你的屏幕，给出回复建议。不碰微信本体，不替你发送任何消息。</b></p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/平台-Windows-0078D6?logo=windows&logoColor=white" alt="平台：Windows"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.9+-3776AB?logo=python&logoColor=white" alt="Python 3.9+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/许可-MIT-2ea44f" alt="许可：MIT"></a>
  <a href="#-自带模型"><img src="https://img.shields.io/badge/模型-任意%20OpenAI%20兼容视觉接口-8A2BE2" alt="模型无关"></a>
  <a href="#-为什么不是机器人"><img src="https://img.shields.io/badge/方式-只读屏幕-00C7B7" alt="只读屏幕"></a>
  <a href="https://github.com/DuggeeChen/wechat-wingman/actions/workflows/ci.yml"><img src="https://github.com/DuggeeChen/wechat-wingman/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
</p>

<p align="center"><a href="README.md">English</a> · <b>中文</b></p>

微信回复军师盯着你面前的**屏幕**，为当前正在看的聊天草拟回复——**按需、在你本机、用你自己的模型。** 按一下热键（或点一下按钮），它读取当前对话、认出你在跟谁聊，用贴合的语气给出几条候选回复。你点一下复制，然后自己粘贴发送。

它**不**注入、不 Hook、不改微信客户端；**不**读本地数据库；**不**替你发消息。它是「军师」，不是「自动驾驶」。

<p align="center">
  <img src="assets/ui.png" alt="微信回复军师 — 带策略标签的回复候选" width="440">
</p>

---

## 为什么不是机器人？

市面上大多数「微信 AI 回复」项目都是自动发送机器人或进程 Hook 工具。演示很酷，实战很险——注入别的程序进程脆弱、常常违反平台条款，还可能导致账号被风控。

这个项目走的是「笨但安全」的路子，而这正是重点：

| | 常见机器人 / Hook 工具 | 微信回复军师 |
|---|---|---|
| 碰微信客户端 | Hook / 注入进程 | **从不** —— 只读屏幕 |
| 发送消息 | 自动发送 | **从不** —— 你复制粘贴 |
| 读聊天记录 | 扒本地数据库 | **从不碰微信的数据** —— 只看当下屏幕，加上**你自己粘贴**进画像窗口的聊天文本 |
| 上传聊天 | 常传远程服务器 | **只**传给你配置的 API —— 当前屏幕，以及你粘贴的聊天文本 |
| 日志 | 通常记聊天内容 | **不记** —— 只记启动/热键/风格改动，无正文无姓名 |
| 模型 | 绑死一家 | **任意** OpenAI 兼容视觉接口 |

想要回复被*替你*草拟好、同时又想保持掌控、让聊天内容留在自己手里——就是它。

---

## 工作原理

```
┌───────────────┐   Ctrl+Alt+Q    ┌───────────────────────────────┐
│  微信窗口       │◄────────────────│  wx_helper.py（核心）          │
│  （屏幕上的）    │   Win32 截图     │  热键 · 窗口定位               │
└───────────────┘                 │  侧栏裁剪 · JPEG 编码          │
                                  └───────────────┬───────────────┘
                                                  │ base64 图片 + 提示词
                                                  ▼
                                  ┌───────────────────────────────┐
                                  │  你的模型（OpenAI 兼容视觉接口， │
                                  │  base_url 可配置）              │
                                  └───────────────┬───────────────┘
                                                  │ 对象 + 消息 + 候选
                                                  ▼
                                  ┌───────────────────────────────┐
                                  │  wx_ui.py（界面）              │
                                  │  候选卡片 · 复制               │
                                  │  风格切换 · 微调               │
                                  └───────────────┬───────────────┘
                                                  │ 点一下复制
                                                  ▼
                                          你自己粘贴发送（不代发）

  profile_ui.py（独立窗口）── 粘贴文本 / 选择 .md 文件 ──► profile.py ──► profiles/<名字>.json
                                                       │
                                                       └── 背景块 ──► 上面那一轮纯文字请求
```

1. **触发** —— 按 `Ctrl+Alt+Q`（或点「读取当前聊天」）。你不按，它绝不动。
2. **抓图** —— 找到微信窗口，按真实侧栏分界线裁掉左侧列表，**保留完整高度**不漏最新消息。
3. **理解** —— 截图发给你的模型，返回**聊天对象**、**最近消息**、**3 条候选**，每条带一个**策略标签**（说明为什么这么回）。
4. **贴合语气** —— 若识别出的联系人有绑定风格（如老板 → 上级）**或**已有可用画像，会额外发一次**只含文字**的轻量请求重生成候选。你的联系人名单永远不会发给模型。
5. **带上记忆** —— 如果你给这个人建过**人物画像**，它的背景块会随那次纯文字请求一起发出去，让回复能考虑到你已经知道的关于他的事（做什么的、在意什么、以前说过什么）。
6. **选择** —— 点候选复制正文（不含策略标签），用**编辑 / 短一点 / 自然点 / 换个说法**微调，或**同内容换一批**。然后自己粘贴。

---

## 人物画像 —— 越用越懂他

回复流程只能看到当下这一屏，所以它自己不可能知道周总是做建材的、或者他讨厌一次被问两件事。画像功能就是把这些背景放进去的通道 —— 而且它是**刻意做成手动的**。

打开画像窗口，选一个联系人。可以把聊天文本粘贴进去，也可以点「选择 .md 文件」导入聊天导出的 Markdown（日期标题 + `**时间 | 昵称：** 消息`格式；程序从不碰微信数据库）。长文件会按完整消息分段处理，再归纳为整体画像；取消或中途失败不会保存半成品画像。然后：

- 它**在本地、确定性地**按说话人切分粘贴内容，所以「谁说的」这件事根本不需要模型猜。
- 分段提取少量有原话支持的事实与沟通线索，再跨段归纳为表达方式、思考与决策、互动习惯等**整体画像**，而不是把每句话都当成一条要回喂的记忆。
- 「查看画像」默认展示核心特征和回复建议；点「显示证据层」可查看依据。旧画像未重新导入前仍能按原来的观察列表使用。上一次导入可以一键撤销；点「删除画像…」确认后，可把当前联系人的整份画像移出可用列表，本窗口还可立即恢复。
- 下次读取这个人的聊天时，军师会从整体画像中挑选与当前对话相关的简短参考卡，用于生成回复；不会把整份聊天记录再次发送。

**画像是你的，只留在本机。** 它存在 `profiles/`（已 gitignore），是你能直接读、直接删的纯 JSON，而且**永远不会发给其他联系人**。它只有两种情况会到模型那里：你主动建/更新画像时（粘贴或导入的聊天先在本机脱敏；Markdown 长文件按段发送给模型分析），以及读**这个人**聊天时（只发 ≤600 字的摘要，不含原话）。具体发了什么见 [docs/PRIVACY.md](docs/PRIVACY.md)。

「删除画像…」会将当前画像移动到 `profiles/.deleted/`，不会永久擦除历史快照；后续新生成的回复不再使用它（已经生成的旧候选不会自动撤回）。误删可在当前画像窗口点「恢复刚删除的画像」；关闭窗口后仍可从归档目录手动恢复。

---

## 特性

- 🖥️ **只读屏幕** —— 不注入、不 Hook、不扒数据库，微信保持原样。
- ✋ **按需触发** —— 只有按热键或点按钮才分析。
- 👥 **多会话感知** —— 认出当前跟谁聊，切换会话自动换语气。
- 🎭 **按人设风格** —— `contact_personas` 绑定表（如 `"周总": "上级"`），风格库可自由增删。
- 🧠 **人物画像** —— 粘贴一段聊天，得到这个人的长期记忆：他是谁、在意什么，每条都有原话可查。存在本机，越攒越准。详见[下文](#人物画像--越用越懂他)。
- 🏷️ **策略标签** —— 每条候选都说明策略，让你**有意识地**选，不是随机挑。
- 🔁 **就地微调** —— 编辑、变短、变自然、换说法，或整批重生成，不重复发图。
- 🛡️ **防注入** —— 聊天内容被当作不可信数据，永远无法覆盖指令。
- 🔒 **代码无密钥** —— API key 只存在环境变量或已 gitignore 的 `.env`，绝不进仓库。
- 🧪 **`--selftest`** —— 纯本地自检（配置 + 窗口状态），不截图、不联网。
- 🪟 **Windows 原生** —— 全局热键、置顶、单实例、静默 `.vbs` 启动、日志轮转。

---

## 环境要求

- **Windows**（使用 Win32 截图与热键）
- **Python 3.9+**（含 Tkinter，官方安装包自带）
- `pip install -r requirements.txt` → `pillow`、`requests`
- 任意 OpenAI 兼容视觉接口的 **API key**

---

## 快速开始

```bash
git clone https://github.com/DuggeeChen/wechat-wingman.git
cd wechat-wingman
pip install -r requirements.txt
```

1. 复制模板：`copy config.example.json config.json`（或直接运行一次，首次启动会自动复制）。
2. 配置 key —— 二选一：
   - 环境变量：`setx WECHAT_WINGMAN_API_KEY "sk-..."`，或
   - 脚本同目录的 `.env` 文件：
     ```
     WECHAT_WINGMAN_API_KEY=sk-...
     ```
3. 编辑 `config.json`：把 `api_base` / `model` 指向你的接口（见下）。
4. 打开微信、打开一个聊天，双击 **`launch.vbs`**（想看到日志就用 `launch.bat`）。
5. 按 **`Ctrl+Alt+Q`** → 挑一条候选 → 粘贴。

> ⚠️ 别用 `Ctrl+Alt+W` —— 那是微信自己的显示/隐藏快捷键。默认的 `Ctrl+Alt+Q` 避开了它。若热键被占用，程序会自动回退到备用组合并在状态栏显示实际生效的键。

---

## 自带模型

默认配置指向 `https://api.openai.com/v1`、模型 `gpt-4o-mini`（占位）。想换别的，改 `config.json` 三行即可：

```jsonc
{
  "api_base": "https://你的接口.example.com/v1",   // 任意 OpenAI 兼容 base
  "model": "你的视觉模型ID",
  "api_key_env": "WECHAT_WINGMAN_API_KEY",        // 从哪里读 key
  "fallback_models": ["备用模型A", "备用模型B"]     // 主模型失败时依次尝试
}
```

任何走 OpenAI chat-completions 协议、支持图片输入的接口都能用——云端或自建（vLLM、Ollama 等）。它只需要能读一张截图并返回 JSON。

---

## 配置项

| 键 | 默认 | 作用 |
|---|---|---|
| `api_base` | `https://api.openai.com/v1` | OpenAI 兼容接口地址 |
| `model` | `gpt-4o-mini` | 视觉模型 ID |
| `api_key_env` | `WECHAT_WINGMAN_API_KEY` | 存放 key 的环境变量 / `.env` 名 |
| `env_files` | `[".env"]` | 找 key 的文件（相对脚本目录） |
| `fallback_models` | `[]` | 主模型报错时依次尝试 |
| `hotkey` | `ctrl+alt+q` | 按需触发热键 |
| `candidates` | `3` | 每批候选条数 |
| `personas` | *（5 个默认）* | 可编辑的风格定义 |
| `default_persona` | `默认` | 联系人未绑定时的风格 |
| `contact_personas` | `{}` | `"联系人名": "风格"` 绑定表 |
| `always_on_top` | `true` | 窗口置顶 |
| `save_debug` | `false` | 保存最近一次截图用于调试 |
| `capture_sidebar_max_px` | `320` | 裁侧栏时考虑的最大像素 |

---

## 隐私

- 你的聊天**只**发给你配置的 API。回复流程发的是**你触发时正在看的那个屏幕**；画像流程发的是**你自己粘贴进去的聊天文本**。
- **人物画像留在你本机** —— `profiles/` 是已 gitignore 的纯 JSON，永远不会发给其他联系人，删文件即删除。
- **日志不含聊天正文、不含联系人姓名** —— 只记启动、热键注册、风格增删和模型报错。连消息条数、耗时、风格名都不记。
- 无遥测、无统计、无第三方调用。

不点进详情也该知道的两件事：粘贴的聊天文本是**原样、全量**上传的（正则只屏蔽证件号/卡号/手机号/邮箱和 `密码：xxx`，别的都不管）；另外若你配了 `fallback_models`，首次失败会用**同一份 payload（含截图）**重试。

详见 [docs/PRIVACY.md](docs/PRIVACY.md) · 安全策略：[SECURITY.md](SECURITY.md)

> 本工具用于帮你草拟自己的回复。请负责任地使用，并遵守所用平台的条款。

---

## 项目结构

```
wechat-wingman/
├── wx_helper.py            # 核心：热键、抓图、裁剪、模型调用、配置
├── wx_ui.py                # Tkinter 卡片界面：复制、微调、风格、换批
├── profile.py              # 人物画像：说话人切分、提取、合并、存储
├── profile_ui.py           # 画像窗口：粘贴、逐条过目、拒绝、并入
├── ui_theme.py             # 两个窗口共用的卡片/面板绘制
├── launch.bat / launch.vbs # 启动器（vbs = 静默无控制台）
├── config.example.json     # 模板 → 首次运行复制成 config.json
├── requirements.txt
├── profiles/               # 你的画像（已 gitignore，永不入库）
├── docs/
│   ├── ARCHITECTURE.md     # 数据流与设计取舍
│   ├── PRIVACY.md          # 到底发什么、存什么
│   └── FAQ.md
├── scripts/
│   ├── check_no_secrets.py # 提交前密钥守卫（CI 里也会跑）
│   ├── test_profile.py     # 画像存储回归测试（不联网）
│   └── test_ui.py          # 界面回归测试（不联网）
└── .github/workflows/ci.yml
```

---

## 许可证

[MIT](LICENSE) © 2026 [DuggeeChen](https://github.com/DuggeeChen)
