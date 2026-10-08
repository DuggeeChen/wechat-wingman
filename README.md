<p align="center"><img src="assets/wingman.png" alt="桌面搭子" width="104"></p>

# 桌面搭子 · 下一句，按你的节奏

**接得住话，也拿得定主意。**

有些话，心里已经想明白了，落到聊天框里却总差一点。

桌面搭子是一款面向 Windows 的微信聊天辅助工具。按需读取当前对话，衔接本次聊天的前情，把不同回应方向摆到你面前。顺着聊、换个切口，或者把话说得更明确——你来选。

以视觉识别读取消息，以会话上下文组织信息，以可编辑的语气指令塑造表达。选一个方向，调整措辞，复制最像自己的那一句，再由你粘贴发送。

[English](README.en.md) · [下载 Windows 便携版](https://github.com/DuggeeChen/wechat-wingman/releases/latest) · [版本记录](CHANGELOG.md) · [隐私说明](docs/PRIVACY.md)

![Windows](https://img.shields.io/badge/platform-Windows-blue)
![Version](https://img.shields.io/badge/version-2.6.5-green)
![CI](https://github.com/DuggeeChen/wechat-wingman/actions/workflows/ci.yml/badge.svg)

<p align="center"><img src="assets/ui.png" alt="虚构对话演示：回复建议、卡片编辑与发送者纠正" width="440"></p>

## 看清这一轮，再决定下一句

- **前情接得上，回应才有着落。** 一键读取并生成，也可以先只读取或导入文字。补读更早的消息、补充背景，让建议参考前因后果；只有可靠重叠的片段才自动衔接，缺口由你确认。
- **谁说了什么，先弄清楚。** 支持发送者纠正、原文编辑、群聊昵称和撤销。身份待确认时会说明原因，关键身份不明时暂停生成；再次读取可重新识别尚未确认的截图消息。
- **同一句来话，可以有不同接法。** 查看不同回复方向，切回来仍保留最新文字。想换一种说法，就在那张卡片上点「换一条」；也可以直接编辑，不用每次重新开始。
- **语气有选择，表达有自己的气质。** 内置默认、商务、亲密、上级、客套，也支持自定义风格。名称与说明作为明确的写作指令传给模型，约束用词、句式、节奏与分寸。见 [语气说明与实测样例](docs/VOICE.md)。
- **少一点搬运，少一点打断。** 兼容流式接口时，第一条完整候选可提前复制，其余建议在同一次请求中继续补齐。「特殊要求」按需填写，日常接话无需先设目标或底线。
- **模型由你选，连接在界面里改。** 使用自己的 OpenAI 兼容 Chat Completions API；在「更多 → 模型与 API 设置」切换供应商、获取模型列表和测试连接。密钥按接口隔离保存在 Windows 凭据管理器。

> 让上下文留在场，让表达有分寸，让下一句仍然属于你。

## 使用的分寸

只在你点击时读取窗口，由你核对、选择和发送。工具不自动发送、不持续监控，也不读取微信数据库或注入客户端。

当前聊天与前情保留在本次运行内存中；主流程不保存截图，日志按大小轮换，支持清理遗留截图与临时数据。识别、生成和草稿检查会把相关内容发给你配置的模型服务。视觉识别和回复建议仍需核对，详见 [隐私说明](docs/PRIVACY.md)。

## 开始使用

### 便携版

1. 从 [Releases](https://github.com/DuggeeChen/wechat-wingman/releases/latest) 下载 Windows ZIP，完整解压。
2. 双击 `WeChatStrategist.exe`，首次向导中填写支持图片输入的 OpenAI 兼容 Chat Completions 接口、模型和 API Key。
3. 打开具体微信聊天，点击「一键读取并生成」，选择、编辑、复制，然后自己粘贴发送。
4. 后续修改连接使用「更多 → 模型与 API 设置」；`重新配置.bat` 可重开首次向导。

无需安装 Python。便携版个人数据保存在 `%LOCALAPPDATA%\微信军师`；目录名保留以兼容旧版。

### 从源码运行

需要 Windows、Python 3.9+；CI 使用 Python 3.13。

```powershell
git clone https://github.com/DuggeeChen/wechat-wingman.git
cd wechat-wingman
python -m pip install -r requirements.txt
python wx_helper.py
```

也可双击 `launch.bat` / `launch.vbs`。首次运行会生成私有 `config.json` 并打开向导。源码版个人数据在程序目录；升级时保留自己的配置和凭据，不用示例配置覆盖它们。

## 模型与速度

支持 OpenAI 兼容 `/chat/completions`；截图识别模型须支持图片。原生 Messages 或 Responses 接口不能直接替换此地址，兼容性以连接测试为准。

新截图的一键流程通常有两次串行请求：**识别图片 → 生成文字回复**。完全未变化的画面可复用已接受的识别结果；纯文字重试无需重新截图。连接复用和提前显示完整候选改善等待体验，但不能消除供应商排队、处理和网络延迟。

方向切换和展开其他方案不请求模型；「换一条」使用已读上下文生成所选方向的新回复，无需重新识别截图。切回该方向会复用换写或手动编辑后的最新版本。

日志分别记录识别、生成及首条可用回复的耗时，不记录聊天正文或密钥。非流式 JSON 或字段顺序不同的接口仍可显示最终结果，但可能无法提前显示。

v2.6.1 为 DeepSeek 官方 `deepseek-flash` / `deepseek-v4-pro` 启用 JSON 输出，截图识别明确关闭思考。空正文、截断或无效 JSON 最多自动恢复一次，仍共用识别阶段的 60 秒上限；正常成功不增加请求。自定义接口不附加这些供应商专用参数，回复生成的思考设置保持原样。

## 数据与兼容性

当前聊天和前情只保留在本次运行内存中，关闭后清空。主流程不保存截图，识别缓存只有上一张画面的指纹；日志约 1 MB 轮换。清理缓存后，下次读取会重新识别。

识别、生成和草稿检查会把相关内容发给你配置的模型，不是完全离线工具。详见 [隐私说明](docs/PRIVACY.md)。

旧版人物画像保留为手动管理入口，数据在本地 `profiles/`。当前主流程不自动建立画像、不注入旧画像、不调用 Jev；主动导入画像仍会调用模型，旧模块仅作兼容保留。

## 开发与打包

```powershell
python -m unittest discover -s scripts -p "test_*.py" -v
python scripts/check_no_secrets.py
python wx_helper.py --selftest
python -m pip install pyinstaller
.\build_portable.ps1
```

测试使用虚构对话、隔离目录、模拟凭据和本机 HTTP 服务，无真实聊天或远程模型请求。Windows CI 检查回归、首次配置、模型设置、打包和私有文件隔离。

[架构](docs/ARCHITECTURE.md) · [常见问题](docs/FAQ.md) · [安全政策](SECURITY.md) · [MIT 许可](LICENSE)
