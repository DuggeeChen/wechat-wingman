<p align="center"><img src="assets/wingman.png" alt="Desk Buddy" width="104"></p>

# Desk Buddy · The next reply, at your pace

**Keep up with the conversation. Keep your own voice.**

Sometimes you know what you mean. Finding the right words takes a little longer.

Desk Buddy is a Windows companion for WeChat conversations. Read the current chat on demand, bring earlier context into view, and explore different ways to respond. Follow the thread, find a new angle, or say something more clearly—the choice is yours.

Visual recognition reads the messages. Session context connects them. Editable voice instructions shape the wording. Choose a direction, adjust a sentence, then copy the reply that sounds like you and send it yourself.

[中文](README.md) · [Windows download](https://github.com/DuggeeChen/wechat-wingman/releases/latest) · [Changelog](CHANGELOG.md) · [Privacy](docs/PRIVACY.md)

![Windows](https://img.shields.io/badge/platform-Windows-blue)
![Version](https://img.shields.io/badge/version-2.6.5-green)
![CI](https://github.com/DuggeeChen/wechat-wingman/actions/workflows/ci.yml/badge.svg)

<p align="center"><img src="assets/ui.png" alt="Fictional conversation: reply suggestions, inline editing and sender correction" width="440"></p>

## Understand this turn. Choose the next one.

- **Give the reply somewhere to start.** Read and generate in one click, read first, or import text. Add earlier messages and background so suggestions can use the context. Only reliable overlaps are joined automatically; you confirm gaps.
- **Know who said what.** Correct senders, edit recognized text and group nicknames, or undo a correction. Uncertain identities show a reason, and important unresolved identities pause generation. Reading again can retry unconfirmed screenshot identities.
- **One message can invite several responses.** Explore reply directions and return to their latest wording instantly. Use a card's rewrite button for a new version, or edit it yourself without starting over.
- **Let the wording carry your voice.** Built-in voices cover everyday, business, close, supervisor and polite conversations. Create your own with explicit writing instructions for vocabulary, sentence rhythm and familiarity. See [voice behavior and sampled outputs](docs/VOICE.md).
- **Less moving text around. Fewer interruptions.** Compatible streams can show the first complete candidate while the same request finishes the remaining suggestions. Goals and boundaries are optional; everyday replies need no preliminary form.
- **Choose your model. Change it in the UI.** Bring your own OpenAI-compatible Chat Completions API. Provider settings include model-list retrieval and connection tests; keys are isolated by endpoint in Windows Credential Manager.

> Keep the context in view, the words considered, and the next reply yours.

## Your conversation, your call

Reading starts when you click. You review, choose and send. There is no automatic sending, continuous monitoring, WeChat database access or client injection.

Current messages and background stay in memory for this run. The main workflow does not save screenshots; logs rotate by size, and cleanup handles legacy screenshots and temporary data. Recognition, generation and draft checks send relevant content to your configured model service. Review recognized identities and suggested wording before sending. See [Privacy](docs/PRIVACY.md).

## Getting started

Download and fully extract the ZIP from [Releases](https://github.com/DuggeeChen/wechat-wingman/releases/latest), then run `WeChatStrategist.exe`. The first-run wizard asks for an OpenAI-compatible Chat Completions endpoint and an image-capable model. Open a specific WeChat chat and click the main read-and-generate button.

No Python installation is required. Personal data lives in `%LOCALAPPDATA%\微信军师`; this existing folder name is retained for upgrades. Change providers under More → 模型与 API 设置. `重新配置.bat` opens the first-run wizard again.

### Source

Windows and Python 3.9+ are required. CI uses Python 3.13.

```powershell
git clone https://github.com/DuggeeChen/wechat-wingman.git
cd wechat-wingman
python -m pip install -r requirements.txt
python wx_helper.py
```

`launch.bat` / `launch.vbs` are alternative launchers. Private source-run data lives next to the code; preserve existing configuration and credentials when upgrading.

## Providers, latency and privacy

The protocol is `/chat/completions` with image input for recognition. Native Messages and Responses endpoints are not interchangeable. Use the built-in test to check compatibility.

A fresh capture normally needs image recognition followed by text generation. Exact unchanged frames can reuse accepted recognition; generation retries are text-only. Pooled connections and early complete-candidate display reduce waiting but cannot eliminate provider or network latency. Non-streaming JSON still works without early display.

Selecting a direction or expanding alternatives makes no request. The separate rewrite action uses existing context for new text without another screenshot. Returning to a direction keeps its latest generated or edited wording.

For official DeepSeek `deepseek-flash` / `deepseek-v4-pro`, v2.6.1 requests JSON output and explicitly disables thinking for screenshot recognition. Empty, truncated or malformed recognition output can recover once within the same 60-second stage budget; successful calls do not add requests. Custom endpoints retain their existing parameters, and reply-generation thinking preferences are preserved.

Stage timings are logged without chat text or keys. Session messages/background stay in RAM for one run. The main workflow does not save screenshots; its cache stores only the last frame's fingerprint. Logs rotate at about 1 MB. Resetting recognition cache causes the next capture to be recognized again.

Recognition, generation and draft checks send relevant data to your configured service. This is not offline-only. [Privacy](docs/PRIVACY.md) details each action and storage location.

Legacy profiles remain manually managed in `profiles/`. The main workflow does not build or inject them or invoke Jev. Explicit manual profile imports still call the configured model.

## Development

```powershell
python -m unittest discover -s scripts -p "test_*.py" -v
python scripts/check_no_secrets.py
python wx_helper.py --selftest
python -m pip install pyinstaller
.\build_portable.ps1
```

Tests use fictional conversations, isolated directories, mocked credentials and loopback HTTP, with no remote model requests. Windows CI also checks setup, model settings, packaging and private-file isolation.

[Architecture](docs/ARCHITECTURE.md) · [FAQ](docs/FAQ.md) · [Security](SECURITY.md) · [MIT license](LICENSE)
