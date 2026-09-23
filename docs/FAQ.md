# FAQ

### Does it send messages for me?
No. It only copies a candidate to your clipboard when you click it. You paste it yourself. There is no code path that sends a WeChat message.

### Does it modify or inject into WeChat?
No. It reads pixels from the screen (Win32 capture of the focused WeChat window). No injection, no hooks, no DB access, no keyboard/mouse automation.

### Does it watch me constantly?
No. It does nothing until you press the hotkey or click a button. There is no background monitoring loop.

### I chat with many people and switch windows — does it get confused?
It re-locates and re-captures the window fresh on every trigger, and identifies the current contact from the screenshot. After you switch to a different chat, press the trigger again to re-read. "Rebatch" and "refine" always target the contact shown at the top, not whatever WeChat happens to be showing later.

### Can I add my own tone / persona?
Yes. Open the persona manager (style library) from the UI or `python wx_helper.py --styles`. Add, rename, edit, or delete personas. The last one can't be deleted.

### How do I bind a tone to a specific person?
Edit `contact_personas` in `config.json` (e.g. `"周总": "上级"`). When that contact is recognized, a second text-only call regenerates the candidates in that tone.

### Which models work?
Any OpenAI-compatible chat-completions endpoint that accepts image input. Cloud or self-hosted (vLLM, Ollama, …). Set `api_base`, `model`, and `api_key_env` in `config.json`.

### Where does my API key go?
Either the environment variable named by `api_key_env`, or a `.env` file next to the script. It is never written into the repo. If you see "启动失败: 缺少 API key", the env var isn't set and no `.env` was found.

### The hotkey doesn't fire. What now?
- Don't use `Ctrl+Alt+W` — that's WeChat's own show/hide shortcut.
- If `Ctrl+Alt+Q` is taken by another app, the tool auto-tries alternates and shows the active one in the status bar.
- Or just use the on-screen "读取当前聊天" button (and `Ctrl+Enter` inside the window).

### Why no screenshot preview / confirmation before upload?
Clicking "read" is treated as consent to upload the current screen to your configured API. See [docs/PRIVACY.md](PRIVACY.md) for exactly what is sent. If you want a confirmation step, that's a reasonable feature request — open an issue.

The profile flow is the exception to that rule: it has an explicit paste-and-click, because there is nothing to capture — **nothing is uploaded until you paste text and press 生成 / 更新画像.**

### What is a "person profile" and where does it live?
A per-contact memory built from chat text *you* paste in — 50–100 messages is the sweet spot. Every observation it keeps must come with a verbatim quote from your paste; anything the model can't back with a real line is discarded. It's stored as plain JSON under `profiles/`, one file per contact, and `profiles/` is git-ignored.

### How do I delete a profile?
Delete its file in `profiles/` (`profiles/周总.json`). That's the whole thing — there's no server copy. `profiles/.history/` holds one snapshot per update if you want to undo an import instead; delete that directory too if you want it gone entirely. Merging two profiles renames the source to `<name>.json.merged` rather than deleting it, so check for `.merged` files as well.

### Does my profile get sent to the model for other people?
No. A profile is only ever in a request when it's *that* contact's profile and you are building, updating, or merging it — or when you read *that* contact's chat, where only the background block rides along in the text-only pass. Reading 张三's chat never sends 李四's profile, not even as a hint. If the app sees a similar-looking name it *asks you* whether it's the same person; the guessed name is shown in the UI and never uploaded.

### Isn't pasting my chat into a box a privacy risk?
Yes, and it's worth being clear-eyed about it: **the paste is uploaded verbatim, in full.** A regex scrubber removes ID numbers, bank-card numbers, phone numbers, emails, and `密码：xxx`, but it does not understand context — names, addresses, salaries, and secrets written any other way go out untouched. If you wouldn't paste it into a form on your provider's website, don't paste it here.

### Does the screenshot get sent more than once?
Only if you configure `fallback_models`. The first call of a trigger carries the image; the second pass, "rebatch", and "refine" are all text-only. But a *failed* attempt is retried against each fallback with the same payload — image included — so with two fallbacks the image can go out three times, all to the same `api_base`. Leave `fallback_models` empty if you want it sent exactly once.

### It misread a message. How do I fix it?
Use "查看 / 纠正" to expand and correct the recognized messages, then "同内容换一批" to regenerate from the corrected text (no new screenshot).

### Does it read messages that are off-screen?
No. It reads only what's visible in the current window. Scrolling history isn't read automatically. The one way older messages get in is if *you* copy them out of WeChat and paste them into the profile window.

### Is it Windows-only?
Yes. It relies on Win32 screen capture and `RegisterHotKey`.

### What's `--selftest`?
`python wx_helper.py --selftest` checks local config and window state only. It does not screenshot and does not call the network, so it's safe to run anywhere.

### Can I run it on a company / managed device?
The safe-by-construction design (read-only, no injection, no auto-send) is intended to be defensible, but always follow your org's policies and the platform's terms.
