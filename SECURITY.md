# Security Policy

Report vulnerabilities through a [private security advisory](https://github.com/DuggeeChen/wechat-wingman/security/advisories/new) or **duggeechen518@gmail.com**. Avoid posting private chat or credentials publicly. This personal project may take a few days to respond.

## Scope

- Uploads to unconfigured endpoints, secret leaks or private files in the repository/releases.
- Sending WeChat messages, modifying its client or accessing its database.
- Cross-contact context reuse, stale request acceptance or bypassing intended identity guards.
- Cleanup deleting configurations, profiles, backups or anything outside its three disposable filenames.

Recognition, generation, draft checks and manual profile imports upload documented data. See [Privacy](docs/PRIVACY.md). The default workflow does not call Jev or automatically build/inject profiles; separately invoked legacy modules can use their configured endpoints.

New setup uses Windows Credential Manager; legacy source configurations may use env/private `.env`. Profile quotes and snapshots are plaintext. Startup passwords are convenience locks, not encryption. Provider storage policies and screen recordings are outside this application's control.

Visual checks can fail. User corrections and guards reduce errors but do not guarantee accuracy. Chat/background are untrusted prompt data; instructions and parsing do not fully prevent model prompt injection.

There is no automatic send path. Stream previews require complete candidates. Failed/inconsistent final output removes them and prompts review of already copied text. Cancellation blocks late UI results without claiming to stop remote computation.

CI uses synthetic regression tests, a tracked-file secret guard, isolated smoke checks and portable packaging. These do not establish accuracy for every WeChat layout or guarantee provider availability.
