# Privacy

The short version: **your chats go only to the API you configure. The reply flow sends the screen you're looking at when you trigger it; the person-profile flow sends the chat text you paste in. Logs never store chat content or contact names. No telemetry.**

Here is the exact, per-action accounting.

## What is sent to your model API

| Action | What is uploaded | Sent every time? |
|---|---|---|
| **读取当前聊天** (initial read) | A JPEG of the current WeChat window (cropped), plus the instruction prompt | Yes — image + prompt |
| **同内容换一批** (rebatch) | The already-extracted message text, your extra instruction, and the chosen persona | Text only — **no image** |
| **短一点 / 自然点 / 换个说法** (refine one) | That one candidate's text, the message text, and the instruction — **plus the background block**, if this contact has a usable profile | Text only — **no image** |
| **第二次请求** (the read's second call) | The already-extracted message text, **plus whichever of these applies**: the bound persona's definition, and/or the profile's background block. Runs when *either* a non-default persona is bound *or* a usable profile exists | Text only — **no image** |
| **人物画像** (profile extract) | **The chat text you pasted**, plus the extraction prompt | Text only — **no image**, only when you click 生成 / 更新画像 |
| **画像更新** (updating a profile from a new paste) | The observations just extracted — **including their verbatim quotes** — plus a one-line summary of each stored observation (id, category, text, count, last-seen date — **no quotes** for the stored ones) | Text only — **no image**, only if that contact already has a profile |

> Two different things are called "merge" in the UI. **「并入另一个画像…」** — combining two stored profiles for the same person — is **purely local file work**: no model call, nothing uploaded. The table's 画像更新 row is the other one: the model-assisted re-summarize that happens when you *update* a profile from a new paste.

The image is sent **only on the first call of a trigger** — every follow-up (second pass, rebatch, refine) is text-only, and the profile flow never sends an image at all.

**One caveat on "once":** if you configure `fallback_models`, a failed first attempt is retried against each fallback in order, and the retry re-posts the *same* payload — **including the image**. So the image can go out more than once per trigger: up to `1 + len(fallback_models)` times. All of them go to the same `api_base`; only the `model` field changes. If you want the strict once-per-trigger guarantee, leave `fallback_models` empty.

**"Text only" does not mean "a little text."** The profile-extraction call uploads the paste **in full** — no length cap, no chunking, no sampling. Paste 100 messages and 100 messages go out. The reply side is the opposite for the *profile*: that always arrives as a ≤600-character digest. (The message text in a rebatch or refine call is whatever was on screen, so it can be as long as the visible conversation.)

**What the background block leaves behind.** The stored profile keeps verbatim quotes; the block that goes into a reply prompt does not. `hint_stats()` renders one line per category, capped at 600 characters, keeps only `active`/`disputed` entries, drops anything older than 180 days unless it's a stable fact (关系事实), and appends an instruction telling the model not to bring these things up unless the current conversation already has. So a long history is summarized down before it is ever re-uploaded.

## What is *not* sent, ever

- Your `contact_personas` map (the full contact list) is **never** embedded in any prompt. Only the persona of the *single* recognized contact is used, and only as a text definition.
- **No profile is ever sent for a contact it doesn't belong to.** When you read screen for 张三, 李四's profile is not in the request — not as context, not as a "similar contacts" hint. The only profile that can appear in a request is the recognized contact's own: as the **600-character digest** in the text-only reply pass, or as the full observation set when *you* build, update, or merge it.
- **The verbatim quotes in a stored profile are never re-uploaded by a read.** They leave the machine again only when you update that profile from a new paste, which sends the newly extracted observations (quotes included) back for re-summarizing. A read sends the digest, which has no quotes in it.
- No message history beyond what's visible in the current screenshot — **except** the chat text you yourself paste into the profile box, which is uploaded in full at that moment. The paste itself is not retained; what persists is the observations and their quotes (see below).
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
| `profiles/*.json` | Yes, **on disk and permanent** | The person profiles: every observation **with the verbatim quote it was extracted from**, plus counters (batches, lines seen). One file per contact. **Git-ignored.** The raw chat you pasted is *not* kept — but the quotes inside the observations are real lines from it, so treat the file as containing chat content. |
| `profiles/.history/` | Yes | One timestamped snapshot per profile write, so a bad update can be undone. Same content as above. **Git-ignored.** |
| `profiles/.aliases.json` | Yes | Maps an OCR-misread name to the name its profile was built under. Names only. **Git-ignored.** |
| `profiles/.rejected.json` | Yes | The observation texts you rejected with 「不准」, so they aren't re-suggested. **Global, not per-contact** — one shared list. Contains observation text, which is chat-derived. **Git-ignored.** |
| `profiles/*.merged` | Only after 「并入另一个画像」 | The source profile file, **renamed rather than deleted — its observations are still in it.** A merge is local file surgery: no model call, nothing uploaded. **Git-ignored.** |

**Deleting a profile is deleting the file.** There is no server copy and no undo beyond `profiles/.history/`, which you can also delete. A stored profile leaves your machine again in exactly two ways: the **digest** goes out on a read of that contact's chat, and the **observations with their quotes** go out when you update that profile from a new paste. Nothing uploads on its own.

**What the file name is, and isn't.** A profile is stored under a sanitized form of the contact's name (zero-width characters and all whitespace stripped, path-illegal characters replaced, truncated to 60 chars). So **contact names are visible in `profiles/` as file names** — that directory listing is a contact list. It is git-ignored and local-only, but it is not encrypted and not hidden.

## What is *not* stored

- No chat logs and no message history. **The one exception is the profile store**, which keeps observations with verbatim quotes from the pastes you chose to import — see the table above.
- No contact list is sent anywhere, and none is stored as a list — but note that `profiles/` **is** effectively a list of contact names, in its file names. Nothing aggregates it, and nothing uploads it.
- No screenshots (unless you opt into `save_debug`).
- **No profile is ever written for a contact you didn't explicitly build one for**, and no profile is written automatically from a screen read — building one always requires a paste and a click. (Reading a profile only *heals* it in memory; it does not write.)

## Assurances that hold by construction

- **Screen-read only** — no process injection, no DB scraping, no keyboard/mouse automation, so there's no covert channel for data.
- **No auto-send** — the app has no code path that sends a WeChat message. Copying to the clipboard is the only "output" and it requires your click.
- **No secrets in the repo** — the key is read from env / `.env`; `config.json` keeps only the env-var *name*.
- **The profile store is not in the repo.** `profiles/` is git-ignored, and `scripts/check_no_secrets.py` fails the build if any file under it is ever staged.
- **A stored profile cannot reach the model without you.** It travels on exactly one path: the update call, fired when you press 生成 / 更新画像 for a contact that already has a profile. A read sends only the digest, and only for the contact you just read.

## Threat model caveats (honest limits)

- The screenshot may include the draft in your input box or a sliver of the sidebar if cropping is imperfect. Read the "capture range" notes in the README before relying on it for sensitive chats.
- **Pasted chat text goes to your API provider verbatim.** The profile feature's only privacy control is a regex scrubber (ID numbers, card numbers, phone numbers, emails, `密码：xxx`). It does not understand context: a name, an address, a salary, a medical detail, or a secret written any other way goes out untouched. If you would not paste it into a web form on that provider's site, don't paste it here.
- Cancelling can't un-send a request already submitted to your API provider, nor stop its billing.
- This is not an encryption layer: your API provider sees the screenshot and text you submit, per their own terms. Choose a provider you trust.
- The profile store is plain JSON on your disk, readable by anything running as you. It is not encrypted.
