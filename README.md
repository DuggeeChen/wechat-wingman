<p align="center"><img src="assets/wingman.png" alt="Desk Buddy" width="104"></p>

# Desk Buddy · WeChat Wingman

Read a WeChat conversation on demand and get editable reply suggestions using your own model API. Keep context for this session, choose a reply, copy it and send it yourself.

[中文](README.zh-CN.md) · [Windows download](https://github.com/DuggeeChen/wechat-wingman/releases/latest) · [Changelog](CHANGELOG.md) · [Privacy](docs/PRIVACY.md)

![Windows](https://img.shields.io/badge/platform-Windows-blue)
![Version](https://img.shields.io/badge/version-2.6.0-green)
![CI](https://github.com/DuggeeChen/wechat-wingman/actions/workflows/ci.yml/badge.svg)

<p align="center"><img src="assets/ui.png" alt="Fictional conversation: reply-first cards and speaker correction" width="440"></p>

## Features

- One-click capture and generation, with speaker identification before reply generation. Read-only capture and manual text import are available too.
- Session context, older screenshots and user background. Only reliable overlaps are joined automatically; changed contacts and gaps need confirmation.
- Speaker correction, original-text editing, group nicknames and undo. Uncertain recent identities block generation.
- One prominent reply card, alternative directions, inline editing and explicit copy. Goals and boundaries are optional special requirements.
- Early display of complete candidates on compatible streams while alternatives and evidence continue in the same request. Half a reply is never presented as finished.
- UI provider settings, model-list retrieval and synthetic connection tests. Keys are isolated by endpoint in Windows Credential Manager.
- Cleanup of a legacy debug screenshot and rotated logs, plus recognition-fingerprint reset without deleting chat or API settings.

No automatic sending, WeChat database access, client modification, injection, automatic scrolling or continuous monitoring. Visual recognition can still be wrong; review identity and wording before sending.

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
