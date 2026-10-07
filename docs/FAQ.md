# FAQ — v2.6.3

### Does it send messages or watch continuously?
No. Each read is user-triggered; you copy and paste yourself. No client injection, database access or automatic scrolling.

### How do I change providers?
More → 模型与 API 设置. Set an OpenAI-compatible Chat Completions endpoint, an image-capable model and key; use the list/test buttons. Native Messages/Responses URLs are not supported directly.

### Where is the key?
New setup uses Windows Credential Manager with endpoint-isolated targets. Blank input only reuses an existing key for that endpoint. Legacy source configurations may use env/private `.env`; do not commit them.

### How can I add missing earlier context?
Use 前情 / 纠正 for background or pasted messages, or capture an older screen. Reliable overlaps join automatically; contact changes and gaps require confirmation.

### It swapped my words with someone else's.
Click the speaker button to choose 我 / 对方 / 待确认; undo the last correction if needed. Checks use positions, not meaning, but can still miss clear-looking errors.

### It says I've already replied.
A last self-message stops automatic generation to avoid answering as the other person. Explicitly choose a target when you want to add a follow-up.

### Must I fill in a goal and boundary?
No. 特殊要求 is optional. Blank fields generate from context without a form-filling step.

### Does clicking a direction generate again?
In v2.6.3 it instantly shows that direction's current reply. Returning to it reuses the latest generated or edited version. Click the separate 换一条 button when you want new content; it uses existing text context, preserving alternatives. Failure/cancellation restores originals, and restoring a previous version affects only that card. Context or voice changes invalidate old replies. Restart a running source installation to load the fix.

### Does the voice library really affect wording?
The selected name and definition now enter explicit system writing instructions, separately from quoted chats. Built-in guides specify vocabulary, rhythm, familiarity and emoji use. Edited/custom definitions are retained; only exact original defaults migrate in memory. A fictional same-context comparison showed differences between default, business and familiar voices; see [examples](VOICE.md). Voice changes expression, while facts, identity and commitments remain grounded. Actual quality still depends on your provider and the conversation.

### Why can replies still be slow?
Fresh captures require recognition followed by generation. Compatible streams show complete candidates early, but API latency remains. Stage logs distinguish waits; generation retry is text-only.

### It repeatedly reports incomplete model output.
An HTTP 200 response may still contain no final answer or output cut off at its token limit. v2.6.1 preserves finish reasons and distinguishes these errors. Supported official DeepSeek models use JSON output, and screenshot recognition disables thinking explicitly. Recognition can recover once using the same screenshot within the original 60-second budget. Normal success adds no requests; custom endpoints keep their existing parameters. Complete JSON with a BOM, code fence or short explanatory wrapper is accepted, but missing text, duplicate fields and ambiguous objects are not repaired. Restart an existing source installation after upgrading to load the fix.

### Why doesn't early display always work?
It needs content SSE, a complete candidate and the question field. Ordinary JSON, reordered fields or a delayed first response may show only the final result.

### Will screenshots fill the disk?
Main workflow does not save screenshots. Cache is one fingerprint in RAM; logs rotate around 1 MB. More → 清理截图与临时数据 removes old debug images/logs and resets that fingerprint, keeping context/settings. The next capture is recognized again.

### What survives exit?
Current chat and background do not. Config, window state and legacy manual profiles do. Source data is beside the code; portable data is in `%LOCALAPPDATA%\微信军师`.

### Are profiles or Jev used automatically?
No, not by the default workflow. Manual profile import remains available and calls your configured model on request.

### Which hotkey?
Default `Ctrl+Alt+Q` reads only. The main button reads and generates. Existing `Ctrl+Enter` read behavior remains; avoid WeChat's `Ctrl+Alt+W` shortcut.

### Can I test without uploading?
`python wx_helper.py --selftest` reads local configuration/window state, without capture or remote requests. Regressions use fictional data, mocked keys, isolated directories and loopback HTTP.
