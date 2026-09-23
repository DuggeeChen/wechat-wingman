# Privacy

The short version: **your chats go only to the API you configure, and only the screen you're looking at when you trigger it. Logs never store chat content or contact names. No telemetry.**

Here is the exact, per-action accounting.

## What is sent to your model API

| Action | What is uploaded | Sent every time? |
|---|---|---|
| **读取当前聊天** (initial read) | A JPEG of the current WeChat window (cropped), plus the instruction prompt | Yes — image + prompt |
| **同内容换一批** (rebatch) | The already-extracted message text, your extra instruction, and the chosen persona | Text only — **no image** |
| **短一点 / 自然点 / 换个说法** (refine one) | That one candidate's text, the message text, and the instruction | Text only — **no image** |
| **绑定风格生成** (bound-persona pass) | The already-extracted message text + the persona definition | Text only — **no image** |

The image is sent **at most once per trigger**. Every follow-up is text-only.

## What is *not* sent, ever

- Your `contact_personas` map (the full contact list) is **never** embedded in any prompt. Only the persona of the *single* recognized contact is used, and only as a text definition.
- No message history beyond what's visible in the current screenshot.
- No data goes anywhere except `api_base` in your `config.json`. There is no second endpoint, no analytics host, no telemetry.

## What is stored locally

| Item | Stored? | Notes |
|---|---|---|
| `config.json` | Yes | Your personas and contact bindings. **Git-ignored** — this is your private file. |
| `.env` | Yes | Your API key. **Git-ignored.** |
| `ui_state.json` | Yes | Window size / position / topmost. **Git-ignored.** |
| `wx_helper.log` | Yes, rotated at 1 MB | App lifecycle only — startup, hotkey registration, persona add/rename/delete — plus model errors. **No chat content, no contact names, no persona names, no message counts, no timing, no response bodies.** |
| `debug_last.png` | Only if `save_debug: true` | The last screenshot. **Off by default; git-ignored.** Delete it if you turn it on. |
| Read messages / candidates | In memory only | Cleared when the app exits. |

## What is *not* stored

- No chat logs, no message history, no contact list (beyond the bindings you explicitly configured).
- No screenshots (unless you opt into `save_debug`).

## Assurances that hold by construction

- **Screen-read only** — no process injection, no DB scraping, no keyboard/mouse automation, so there's no covert channel for data.
- **No auto-send** — the app has no code path that sends a WeChat message. Copying to the clipboard is the only "output" and it requires your click.
- **No secrets in the repo** — the key is read from env / `.env`; `config.json` keeps only the env-var *name*.

## Threat model caveats (honest limits)

- The screenshot may include the draft in your input box or a sliver of the sidebar if cropping is imperfect. Read the "capture range" notes in the README before relying on it for sensitive chats.
- Cancelling can't un-send a request already submitted to your API provider, nor stop its billing.
- This is not an encryption layer: your API provider sees the screenshot and text you submit, per their own terms. Choose a provider you trust.
