# Privacy — v2.6.1

Recognition, generation and draft checks send requested data to your configured model service. There is no telemetry, continuous capture or automatic sending. This is not an offline-only app.

## Per-action uploads

| Action | Data sent |
|---|---|
| Read / older capture | Cropped JPEG and recognition instructions. Exact accepted-frame reuse avoids recognition. |
| One-click read and generate | Recognition, then text-only generation after identity/context guards pass. |
| Generate / another batch / retry | Session messages, roles and evidence IDs, user background, optional goal/boundary, selected style and relevant previous candidates. No new image. |
| Draft check | Draft and selected session context/requirements. |
| Connection test / model list | Synthetic blue image and test prompt, or no chat for the model-list request. |
| Inline edits, correction, undo, copy, cleanup | Local only. Cache reset means the next capture requires recognition again. |

Message context is limited to 100 messages and approximately 24,000 text characters, with omission disclosure and explicit-target retention. Background and previous candidates are separate fields. Chat and screenshots are not automatically anonymized. Cropping does not guarantee redaction of contacts, group nicknames, quotes or other window contents.

Fallbacks retry the same payload at the same endpoint, including images for recognition. A screenshot can therefore be submitted more than once. Cancellation discards stale UI output but cannot guarantee remote processing has stopped.

## Local data

| Item | Storage |
|---|---|
| Configuration / endpoint metadata | Private `config.json`; UI writes credential lookup names, not API keys. Startup lock may be plaintext or a hash; it is not encryption. |
| API keys | New setup/settings use Windows Credential Manager. Legacy source config can use env/private `.env`. Managed connections do not silently reuse another endpoint's key. |
| Window geometry | Private `ui_state.json`. |
| Sessions, background, corrections, replies | RAM for this run; grow with use and are released on current-chat clearing or exit. |
| Recognition cache | One exact frame fingerprint and session ID in RAM, not screenshot pixels. |
| Capture/request images | Temporary worker memory; current main workflow does not save screenshots. |
| Logs | Approximately 1 MB rotation into one `.1` file. Lifecycle, safe error types/statuses, model names and stage/request timings; no main-workflow message text, reply bodies, keys or contact names. |
| Legacy debug image | `debug_last.png` may remain from the old debug path; cleanup removes it. Main workflow does not save captures via `save_debug`. |
| Legacy profiles | Plaintext `profiles/`, including quotes, nicknames, history and deletion archives; retained across runs. |

Source data lives beside the program. Frozen builds use `%LOCALAPPDATA%\微信军师`. Test-only `WX_HELPER_DATA_DIR` isolates smoke checks from real files.

## Legacy modules

Manual profile imports/updates call the configured model with imported segments and relevant profile material. Regex scrubbing is incomplete; names, addresses and contextual secrets may remain. Profile quotes and history stay on disk, including deletion archives.

Current `BuddyApp` generation does not automatically build profiles, inject their digest or invoke Jev, even if old config has `jev_enabled`. Separately invoked legacy modules can use their configured Jev endpoint; this is outside the default pipeline.

## Cleanup and publication

Cleanup deletes only `debug_last.png`, `wx_helper.log` and `wx_helper.log.1` in the writable data directory, and resets the recognition fingerprint. No directory traversal or recursive deletion. Config, keys, conversations, profiles and upgrade backups are preserved. A fresh log can be created afterward.

Git excludes personal config, env files, screenshots, profiles, logs and build output. Releases contain code/resources and a fictional configuration template, never personal runtime files. CI scans tracked files for private artifacts; packaging checks filenames too.

The application does not encrypt local profiles or control providers' retention policies.
