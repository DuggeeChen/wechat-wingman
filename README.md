# WeChat Wingman · 微信回复军师

> **Reads your screen. Suggests replies. Never touches WeChat. Never sends anything.**

[![Windows](https://img.shields.io/badge/platform-Windows-0078D6?logo=windows&logoColor=white)](https://www.python.org/downloads/)
[![Python](https://img.shields.io/badge/python-3.9+-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-2ea44f)](LICENSE)
[![Model-agnostic](https://img.shields.io/badge/model-any%20OpenAI%20compatible%20vision%20API-8A2BE2)](#-bring-your-own-model)
[![Zero-injection](https://img.shields.io/badge/approach-screen--read%20only-00C7B7)](#-why-not-a-bot)
[![CI](https://github.com/DuggeeChen/wechat-wingman/actions/workflows/ci.yml/badge.svg)](https://github.com/DuggeeChen/wechat-wingman/actions/workflows/ci.yml)

**English** · [中文](README.zh-CN.md)

WeChat Wingman watches the **screen** in front of you and drafts replies for the chat you are looking at — **on demand, on your own machine, with your own model.** Press a hotkey (or click a button), and it reads the current conversation, figures out who you are talking to, and offers a few reply candidates in a matching tone. You click one to copy it, then paste it yourself.

It does **not** hook, inject, or modify the WeChat client. It does **not** read its local database. It does **not** send messages for you. It is a *wingman*, not an autopilot.

<p align="center">
  <img src="assets/ui.png" alt="WeChat Wingman — reply candidates with strategy tags" width="440">
</p>

---

## Why not a bot?

Most "AI WeChat reply" projects are auto-send bots or process-hooking tools. They look great in a demo and are risky in practice — injecting into another app's process is fragile, often against the platform's terms, and can get your account flagged.

This project takes the boring-but-safe route, and that's the point:

| | Typical bot / hook tool | WeChat Wingman |
|---|---|---|
| Touches the WeChat client | Hooks / injects the process | **Never** — reads the screen only |
| Sends messages | Automatically | **Never** — you copy & paste |
| Reads chat history | Scrapes the local DB | **Never** — only what's on screen right now |
| Uploads your chats | Often a remote server | **Only** to the API you configure, and only the current screen |
| Keeps logs of chats | Usually yes | **No** — logs record counts and timing, not content or names |
| Model choice | Locked to one vendor | **Any** OpenAI-compatible vision API |

If you want your replies drafted *for* you — but still want to stay in control and keep your chats yours — this is the tool.

---

## How it works

```
┌───────────────┐   Ctrl+Alt+Q    ┌───────────────────────────────┐
│  WeChat window │◄────────────────│  wx_helper.py (core)          │
│  (on screen)   │   Win32 capture │  hotkey · window locate        │
└───────────────┘                 │  sidebar crop · JPEG encode    │
                                  └───────────────┬───────────────┘
                                                  │ base64 image + prompt
                                                  ▼
                                  ┌───────────────────────────────┐
                                  │  Your model (OpenAI-compatible │
                                  │  vision API — base_url config) │
                                  └───────────────┬───────────────┘
                                                  │ contact + messages + candidates
                                                  ▼
                                  ┌───────────────────────────────┐
                                  │  wx_ui.py (UI)                │
                                  │  candidate cards · copy        │
                                  │  tone switch · refine          │
                                  └───────────────┬───────────────┘
                                                  │ click to copy
                                                  ▼
                                        you paste it yourself
```

1. **Trigger** — press `Ctrl+Alt+Q` (or the "读取当前聊天" button). Nothing happens until *you* ask.
2. **Capture** — it finds the WeChat window, crops the sidebar away using the real divider line, and keeps the full height so no latest message is missed.
3. **Understand** — the screenshot goes to your model, which returns the **contact**, the **recent messages**, and **3 reply candidates**, each tagged with a *why* (the strategy behind it).
4. **Match tone** — if the recognized contact has a bound persona (e.g. your boss → 上级), a lightweight text-only second call regenerates the candidates in that tone. Your contact list is never sent to the model.
5. **Choose** — click a candidate to copy the text (without the strategy tag), refine it with **edit / shorter / more natural / rephrase**, or ask for **a fresh batch**. Then paste it yourself.

---

## Features

- 🖥️ **Screen-read only** — no injection, no hooks, no DB scraping. WeChat stays untouched.
- ✋ **On-demand** — it analyzes only when you press the hotkey or click the button.
- 👥 **Multi-chat aware** — recognizes who you're talking to and switches tone automatically as you switch chats.
- 🎭 **Per-person tone** — a `contact_personas` map (e.g. `"王总": "上级"`) plus editable personas, add/delete freely in the UI.
- 🏷️ **Why-tags** — every candidate explains its strategy so you pick *deliberately*, not randomly.
- 🔁 **Refine in place** — edit, shorten, naturalize, rephrase, or regenerate a whole batch without re-sending the image.
- 🛡️ **Injection-aware** — chat content is treated as untrusted data and can never override instructions.
- 🔒 **No secret in code** — your API key lives in an environment variable or a git-ignored `.env`, never in the repo.
- 🧪 **`--selftest`** — a local-only check (config + window state) that never screenshots or uploads.
- 🪟 **Windows-native** — global hotkey, topmost UI, single-instance, silent `.vbs` launcher, log rotation.

---

## Requirements

- **Windows** (uses Win32 screen capture and hotkeys)
- **Python 3.9+** (with Tkinter — included in the official installer)
- `pip install -r requirements.txt` → `pillow`, `requests`
- An **API key** for any OpenAI-compatible vision endpoint

---

## Quick start

```bash
git clone https://github.com/DuggeeChen/wechat-wingman.git
cd wechat-wingman
pip install -r requirements.txt
```

1. Copy the template: `copy config.example.json config.json` (or just run once — it's copied automatically on first launch).
2. Set your key — either:
   - an environment variable: `setx WECHAT_WINGMAN_API_KEY "sk-..."`, or
   - a `.env` file next to the script:
     ```
     WECHAT_WINGMAN_API_KEY=sk-...
     ```
3. Edit `config.json`: point `api_base` / `model` at your endpoint (see below).
4. Open WeChat, open a chat, then double-click **`launch.vbs`** (or `launch.bat` to see logs).
5. Press **`Ctrl+Alt+Q`** → pick a candidate → paste.

> ⚠️ Don't use `Ctrl+Alt+W` — that's WeChat's own show/hide shortcut. The default `Ctrl+Alt+Q` avoids it. If the hotkey is taken, the app auto-falls back to alternates and shows the active one in the status bar.

---

## Bring your own model

The default config points at `https://api.openai.com/v1` with `gpt-4o-mini` as a placeholder. Change three lines in `config.json` to use whatever you like:

```jsonc
{
  "api_base": "https://your-endpoint.example.com/v1",  // any OpenAI-compatible base
  "model": "your-vision-model-id",
  "api_key_env": "WECHAT_WINGMAN_API_KEY",             // where to read the key from
  "fallback_models": ["backup-model-a", "backup-model-b"] // tried in order if the main one fails
}
```

Works with any provider that speaks the OpenAI chat-completions protocol with image input — cloud or self-hosted (vLLM, Ollama, etc.). It just needs to read a screenshot and return JSON.

---

## Configuration

| Key | Default | Meaning |
|---|---|---|
| `api_base` | `https://api.openai.com/v1` | OpenAI-compatible endpoint |
| `model` | `gpt-4o-mini` | Vision model id |
| `api_key_env` | `WECHAT_WINGMAN_API_KEY` | Env-var / `.env` name holding the key |
| `env_files` | `[".env"]` | Files to look for the key in (relative to script) |
| `fallback_models` | `[]` | Tried in order if the main model errors |
| `hotkey` | `ctrl+alt+q` | On-demand trigger |
| `candidates` | `3` | Replies per batch |
| `personas` | *(5 defaults)* | Editable tone definitions |
| `default_persona` | `默认` | Tone when the contact isn't mapped |
| `contact_personas` | `{}` | `"contact name": "persona"` map |
| `always_on_top` | `true` | Keep the UI above other windows |
| `save_debug` | `false` | Save the last screenshot for debugging |
| `capture_sidebar_max_px` | `320` | Max sidebar width considered when cropping |

---

## Privacy

- Your chats are sent **only** to the API you configure, and **only the screen you're looking at** when you trigger it.
- **Logs contain no chat content and no contact names** — they record only app lifecycle events (startup, hotkey registration, persona edits) and model errors. Not even message counts, timing, or persona names.
- No telemetry, no analytics, no third-party calls.

Full details: [docs/PRIVACY.md](docs/PRIVACY.md)

> This tool is for drafting your own replies. Use it responsibly and respect the terms of any platform you use it with.

---

## Project layout

```
wechat-wingman/
├── wx_helper.py            # core: hotkey, capture, crop, model call, config
├── wx_ui.py                # Tkinter card UI: copy, refine, tone, batch
├── launch.bat / launch.vbs # launchers (vbs = silent, no console)
├── config.example.json     # template → copied to config.json on first run
├── requirements.txt
├── docs/
│   ├── ARCHITECTURE.md     # data flow & design decisions
│   ├── PRIVACY.md          # exactly what is sent / stored
│   └── FAQ.md
├── scripts/
│   └── check_no_secrets.py # pre-commit secret guard (runs in CI)
└── .github/workflows/ci.yml
```

---

## License

[MIT](LICENSE) © 2026 [DuggeeChen](https://github.com/DuggeeChen)
