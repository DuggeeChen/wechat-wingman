# Architecture

Four modules, one responsibility each, no shared mutable global state beyond a config dict and a few thread-safe queues.

```
wx_helper.py (core / headless)          wx_ui.py (Tkinter, UI thread)
─────────────────────────────           ─────────────────────────────
• config load & first-run bootstrap     • candidate cards + why-tags
• hotkey registration (RegisterHotKey)  • copy (text only, no tag)
• Win32 window locate (FindWindow)      • edit / shorter / natural / rephrase
• screen capture + sidebar crop         • fresh-batch / cancel / retry
• model call (chat completions)         • persona manager (add/del/rename)
• single-instance mutex                 • topmost + window-state persist
• logging + rotation                    • Ctrl+Enter in-window trigger

profile.py (store, no UI)               profile_ui.py (Tkinter, profile window)
─────────────────────────────           ─────────────────────────────
• speaker attribution (deterministic)   • paste box → 生成 / 更新画像
• extraction + quote verification       • observation list, 接受 / 拒绝
• merge & contradiction tracking        • 撤销上次导入 / 并入另一个画像
• local store + .history snapshots      • similar-name confirmation
• alias table, background-block build   • 查看 / 纠正 联系人名
```

`wx_helper.py` and `profile.py` are importable without Tkinter; the two UI modules are the only ones that touch a widget. `profile_ui.py` gets the same `core` object `wx_ui.py` uses, so it inherits the config, the API key, and the model-call helper rather than re-deriving them.

## Data flow

```
[1] trigger ──► [2] locate window ──► [3] capture ──► [4] crop ──► [5] encode ──► [6] model
      ▲                                                                                  │
      │ hotkey OR button OR Ctrl+Enter                                                    ▼
      │                                                                        [7] parse (contact, messages, candidates)
      │                                                                                  │
      └────────────────── [10] refine / rebatch (text-only) ◄──── [9] bind persona? ────┘
                                        │                          or a usable profile?
                                        │                                  │
                                        │                              yes (either)
                                        │                                  │
                                        └──► [11] render cards ──► [12] copy on click ──► user pastes
```

The profile path is a separate loop that feeds the one above but is never entered by it:

```
[P1] you paste chat text ──► [P2] split speakers (local, deterministic)
                                      │
                                      ▼
                             [P3] model: extract observations  ◄── text only, no image
                                      │
                                      ▼
                             [P4] verify each quote against the pasted text
                                      │        (no match → dropped, with a reason)
                                      ▼
                             [P5] merge into the stored profile  ◄── model: re-summarize
                                      │
                                      ▼
                             [P6] profiles/<name>.json  (+ .history snapshot)
                                      │
                                      ▼
                             [P7] background block ──► [9] above, on the next read
```

## Key design decisions

### 1. Two-pass persona, not one big prompt
Instead of embedding the whole `contact_personas` map into the system prompt (which fixes a "first analysis uses the wrong tone" bug but leaks your contact list to the model), we do **two calls**:

1. **Pass 1 (image + prompt)** — return contact, messages, and candidates using the *default* persona.
2. **Pass 2 (text-only)** — re-generate the candidates, sending only the already-extracted text. This runs when *either* the recognized contact has a bound persona that isn't the default, *or* a usable profile background block exists for them. Either reason alone is enough.

Same correctness, better privacy. "Rebatch" and single-card "refine" also go text-only. The image is attached only to the first call of a trigger — with one honest exception: a failed attempt is retried against each configured `fallback_models` entry with the same payload, image included, so the image can go out up to `1 + len(fallback_models)` times. All to the same `api_base`.

**Pass 2 is an extra, and extras are not allowed to break the main feature.** If it fails — network, timeout, a model that returns nothing usable — the pass-1 candidates are shown anyway, with the status bar saying so. The one thing that must *not* happen is resetting the contact's bound style to the default on the way out: the style name is persistent state that feeds the dropdown, and the dropdown is written back into `contact_personas`. Resetting it on a network blip would make the style flicker between batches for no visible reason.

### 2. Screen-read only, by construction
The only *screen* input is a screenshot of the *currently focused* WeChat window. No process injection, no DB access, no UI automation. This bounds both risk and surface area: the worst thing a bad crop does is a bad suggestion.

There is exactly one other input, and it is a different kind: the **chat text you paste** into the profile window. It never comes from WeChat — the app has no code that reads the WeChat database, the clipboard, or any file. If you don't paste it, no profile can be built. See [PRIVACY.md](PRIVACY.md) for what that paste uploads.

### 3. Cropping that keeps the last message
- The window is located fresh on every trigger (position + size are re-read).
- The sidebar divider is detected and used to crop the left chat list, capped by `capture_sidebar_max_px`.
- **Full height is kept** (no fixed bottom ratio) so the newest message isn't cut off.
- The title area keeps extra left margin to avoid clipping long nicknames.

### 4. Cancellation is real
A `epoch` counter + `cancel_event` mean a late result from a cancelled request is discarded instead of overwriting the current UI. Cancelling can't un-send an already-submitted request (or stop its billing), but it won't pollute the UI.

### 5. Chat text is untrusted input
The system prompt treats the chat content as data, not instructions: content inside the screenshot can never override the model's task ("ignore previous instructions" in a chat won't work). The same rule is stated in the profile-extraction system prompt, where the pasted text is likewise framed as untrusted data.

### 6. No secrets in the process image
The API key is read at startup from an environment variable or a git-ignored `.env` file, then held in memory. `config.json` stores only the *name* of the env var (`api_key_env`), never the value. `DEFAULT_CFG` is fully generic.

### 7. A profile is a claim with a receipt, or it is discarded
The person profile is the one feature whose output is *remembered*, so it is the one feature where a hallucination would compound. The design answer is that the model is never asked to be trustworthy — it is asked to produce something that can be **checked**, and everything uncheckable is thrown away.

- **Speaker attribution is deterministic, not model-reported.** `parse_speakers()` splits the pasted text on the `昵称: ` prefix that WeChat's own "copy" produces, and decides who said what by string comparison. The model is never asked "who said this?" — so it cannot get that wrong.
- **Every observation carries a verbatim quote.** An observation survives only if its quote string-matches the pasted text *and* falls inside a continuous block attributed to the other party. No quote, or a quote that can't be found → the observation is dropped, and the drop is counted by reason (`bad_kind / too_long / other_speaker / no_quote`) and shown to you.
- **The model never names the contact.** The extraction template's placeholders are the category list, a length cap, and the text — there is no contact field to fill in, so a misread name can't be baked into an observation.
- **Merging is model-assisted, not model-decided.** New observations are absorbed into existing ones by evidence, and contradictions are recorded as contradictions rather than overwriting. The count of *new evidence* is tracked separately from the count of *merges*, because "merged" does not mean "learned something".
- **The background block is sanitized before it goes back into a prompt.** Profile text containing `【】` would be read by the reply parser as its own output format and could be echoed back as a card; those characters are stripped first.

The limit of this design is worth stating plainly: **the receipt proves the quote is real, not that the inference from it is sound.** "他说他在建材行业" with a matching quote is verifiable; "所以他不信任合伙人" is a judgment the model made and you are expected to overrule. That is why observations are shown to you individually, with their quotes, and why you can reject one.

## Threading model

- **UI thread** — Tkinter event loop (`wx_ui.py`, and `profile_ui.py` when the profile window is open).
- **Worker thread** — capture + model call + parse, so the UI never freezes mid-request.
- **Hotkey thread** — a message loop that receives `WM_HOTKEY` and posts a trigger into the worker queue.
- **Single instance** — a named Win32 mutex; a second launch exits immediately instead of spawning a second floating window.

Both UI modules use the same cancellation shape: an `epoch` counter plus a `threading.Event`, and the worker pushes events into a `queue.Queue` that the UI drains on a timer. A result whose epoch is stale is discarded rather than rendered, so a cancelled request can't overwrite newer state. The profile window's `epoch` is separate from the reply window's — cancelling one does not cancel the other.

## Logging

`wx_helper.log`, rotated at 1 MB → `wx_helper.log.1`. Log lines record: timestamp and event — config load/save, hotkey registration, persona add/rename/delete, the model id in use, an HTTP status code, and the *class name* of an exception. **No chat content, no contact names, no persona names, no message counts, no timing, no API response bodies.** (Note: log files from pre-refactor versions may still contain contact names; the current format does not.)

That last point is load-bearing, so it is worth being precise about what "no counts, no timing" costs us: when a model call fails you get `模型请求失败: HTTP 502 模型=xxx` and nothing else — no payload size, no latency, no message count. Debugging a bad response therefore means reproducing it, not reading the log. The trade was deliberate.
