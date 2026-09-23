# Security Policy

## Reporting a vulnerability

Use a [private security advisory](https://github.com/DuggeeChen/wechat-wingman/security/advisories/new),
or email **duggeechen518@gmail.com**. Please don't open a public issue for a
vulnerability. This is a personal project rather than a funded one, so expect a
first reply within a few days, not minutes.

## In scope

- The app sends data anywhere other than the `api_base` you configured.
- The app sends a WeChat message, or writes to WeChat in any way.
- The app leaks your `config.json`, `.env`, `ui_state.json`, or the screenshot it captured.
- The app reads something other than the screen you were looking at when you triggered it.
- A secret or private file accidentally committed to this repository.

## Out of scope

- The app reads your screen. That is the entire point — see [docs/PRIVACY.md](docs/PRIVACY.md).
- What your API provider does with the data you send it. That is your provider's policy.
- WeChat's own security posture, or using this tool against WeChat's terms of service.

## Design commitments

These hold by construction. A patch that breaks one is a bug, not a trade-off.

- **No injection, no hooks, no database access, no keyboard or mouse automation.**
  The app reads pixels from a window handle and posts them to an HTTP endpoint.
  There is no covert channel, because there is no other channel.
- **No auto-send path.** No code in this repository sends a WeChat message. The
  only output is the clipboard, and only on your click.
- **No secrets in the repo.** The API key lives in the environment or in a
  git-ignored `.env`. `config.json` stores only the env-var *name*.
- **`scripts/check_no_secrets.py` runs in CI** and fails the build if a private
  file or a key-shaped string is ever committed.
- **No telemetry.** There is no second endpoint, no analytics host, no phone-home.
