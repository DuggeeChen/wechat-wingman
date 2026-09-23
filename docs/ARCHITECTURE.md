# Architecture

Two modules, one responsibility each, no shared mutable global state beyond a config dict and a few thread-safe queues.

```
wx_helper.py (core / headless)          wx_ui.py (Tkinter, UI thread)
─────────────────────────────           ─────────────────────────────
• config load & first-run bootstrap     • candidate cards + why-tags
• hotkey registration (RegisterHotKey)  • copy (text only, no tag)
• Win32 window locate (FindWindow)       • edit / shorter / natural / rephrase
• screen capture + sidebar crop          • fresh-batch / cancel / retry
• model call (chat completions)          • persona manager (add/del/rename)
• single-instance mutex                  • topmost + window-state persist
• logging + rotation                     • Ctrl+Enter in-window trigger
```

## Data flow

```
[1] trigger ──► [2] locate window ──► [3] capture ──► [4] crop ──► [5] encode ──► [6] model
      ▲                                                                                  │
      │ hotkey OR button OR Ctrl+Enter                                                    ▼
      │                                                                        [7] parse (contact, messages, candidates)
      │                                                                                  │
      └────────────────── [10] refine / rebatch (text-only) ◄──── [9] bind persona? ────┘
                                        │                                  │
                                        │                              yes (non-default)
                                        │                                  │
                                        └──► [11] render cards ──► [12] copy on click ──► user pastes
```

## Key design decisions

### 1. Two-pass persona, not one big prompt
Instead of embedding the whole `contact_personas` map into the system prompt (which fixes a "first analysis uses the wrong tone" bug but leaks your contact list to the model), we do **two calls**:

1. **Pass 1 (image + prompt)** — return contact, messages, and candidates using the *default* persona.
2. **Pass 2 (text-only)** — if the recognized contact has a bound persona that isn't the default, re-generate candidates in that persona, sending only the already-extracted text.

Same correctness, better privacy. "Rebatch" and single-card "refine" also go text-only — the image is only ever sent once per trigger.

### 2. Screen-read only, by construction
The only input is a screenshot of the *currently focused* WeChat window. No process injection, no DB access, no UI automation. This bounds both risk and surface area: the worst thing a bad crop does is a bad suggestion.

### 3. Cropping that keeps the last message
- The window is located fresh on every trigger (position + size are re-read).
- The sidebar divider is detected and used to crop the left chat list, capped by `capture_sidebar_max_px`.
- **Full height is kept** (no fixed bottom ratio) so the newest message isn't cut off.
- The title area keeps extra left margin to avoid clipping long nicknames.

### 4. Cancellation is real
A `epoch` counter + `cancel_event` mean a late result from a cancelled request is discarded instead of overwriting the current UI. Cancelling can't un-send an already-submitted request (or stop its billing), but it won't pollute the UI.

### 5. Chat text is untrusted input
The system prompt treats the chat content as data, not instructions: content inside the screenshot can never override the model's task ("ignore previous instructions" in a chat won't work).

### 6. No secrets in the process image
The API key is read at startup from an environment variable or a git-ignored `.env` file, then held in memory. `config.json` stores only the *name* of the env var (`api_key_env`), never the value. `DEFAULT_CFG` is fully generic.

## Threading model

- **UI thread** — Tkinter event loop (`wx_ui.py`).
- **Worker thread** — capture + model call + parse, so the UI never freezes mid-request.
- **Hotkey thread** — a message loop that receives `WM_HOTKEY` and posts a trigger into the worker queue.
- **Single instance** — a named Win32 mutex; a second launch exits immediately instead of spawning a second floating window.

## Logging

`wx_helper.log`, rotated at 1 MB → `wx_helper.log.1`. Log lines record: timestamp, event, message count, candidate count, elapsed time, model id, persona — **no chat content, no contact names, no API response bodies.** (Note: log files from pre-refactor versions may still contain contact names; the current format does not.)
