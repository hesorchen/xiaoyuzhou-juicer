# 🥤 xiaoyuzhou-juicer

> Turn a Xiaoyuzhou (小宇宙 FM) podcast episode link into a readable transcript + official chapters + guest background + a structured, decision-ready summary.

[中文 README](README.md)（更完整，含真实样例截图）

A bring-your-own-token tool to fetch & structure transcripts of your own Xiaoyuzhou podcast episodes for personal, offline study. Ships code only — never bundles credentials or any podcast content.

**Pure Python stdlib, zero dependencies** — Python 3.8+ is all you need.

## ⚠️ Disclaimer

- Uses Xiaoyuzhou's private APIs. **For personal archiving / study / accessibility of content your own account can access only.**
- **No credentials bundled** — bring your own login token (BYO-token).
- **No audio or transcript content is distributed** — code only; do not republish generated files.
- No bulk-crawling capability; respect the platform ToS and content copyright.
- APIs are reverse-engineered and may break when the platform changes. Use at your own risk.

## What it does

| Capability | Token? |
|------|:---:|
| Episode metadata (title / duration / date / audio URL) | ❌ |
| Engagement stats (plays / favorites / comments + show subscribers) | ❌ |
| Official chapters (timestamped, from shownotes) | ❌ |
| Top comments (~20, SSR, by popularity) | ❌ |
| Full transcript (readable markdown + raw JSON) | ✅ |
| Discovery feed (charts + editor picks + for-you) | ✅ |
| Keyword search (episodes / podcasts) | ✅ |
| Subscriptions + latest-episode inbox | ✅ |
| Speaker labeling, guest background enrichment, structured summary (TL;DR / decision card / chapter timeline / must-listen rating / quotes / references / takeaways) | done by AI (Claude Code skill) |

## Quick start

```bash
# Metadata + chapters only (no token)
python3 scripts/xyz_fetch.py "https://www.xiaoyuzhoufm.com/episode/<EID>" --meta-only

# With transcript (token required; see below)
python3 scripts/xyz_fetch.py "https://www.xiaoyuzhoufm.com/episode/<EID>" --token-file config/token.txt

# Top comments (no token)
python3 scripts/xyz_fetch.py "<EID>" --meta-only --comments

# Account-level: discovery / search / subscriptions / inbox (token required)
python3 scripts/xyz_fetch.py --discover --token-file config/token.txt
python3 scripts/xyz_fetch.py --search "AI agents" --token-file config/token.txt
python3 scripts/xyz_fetch.py --subscriptions --token-file config/token.txt
python3 scripts/xyz_fetch.py --inbox --token-file config/token.txt

# Reuse one access token for multiple account-level actions
python3 scripts/xyz_fetch.py --discover --subscriptions --inbox --token-file config/token.txt

# Deterministic summary scaffold: quick / full / transcript / deep
python3 scripts/xyz_render.py <EID> --mode full
```

Fetched files are cached under `~/.cache/xiaoyuzhou-juicer/<EID>/` (XDG-compliant, override with `--out`).

## Getting a token

The `x-jike-access-token` lives ~2 hours; the paired `x-jike-refresh-token` is long-lived. This tool stores the **refresh token**, auto-renews the access token on every run, and writes the rotated refresh token back — configure once.

1. Log in at https://www.xiaoyuzhoufm.com (scan QR with the app).
2. DevTools (F12) → Network → reload → click any **200** request to `web-api.xiaoyuzhoufm.com`.
3. Copy the value of the **`x-jike-refresh-token`** request header.
4. Save to `config/token.txt` (gitignored), or `export XYZ_REFRESH_TOKEN="..."`.

## As a Claude Code skill

```bash
git clone https://github.com/hesorchen/xiaoyuzhou-juicer ~/.claude/skills/xiaoyuzhou-juicer
```

Then paste an episode link in a conversation. The skill first asks you to choose `quick`, `full`, `transcript`, or `deep`, then follows a deterministic workflow: fetch → scaffold → enrich and summarize → archive → validate.

Use `scripts/xyz_validate.py` to check the exact title, section order, source engagement numbers, timestamps, transcript quotes, and comment authors. Archive defaults can be stored in `config/archive.ini` using the included example.

For local development, change the source repository first and then run `scripts/install_skill.py --target <skill-dir>`; it synchronizes runtime files without overwriting tokens or private archive configuration. Add `--check` in CI or release checks to detect drift.

## Known limitations

- Transcripts come from the platform's auto ASR: no speaker labels; English names / jargon may be mis-transcribed.
- The transcript CDN enforces a User-Agent allowlist; the script ships a working app UA (`UA_APP`) and handles gzip/deflate responses, but platform changes may still require updates.
- Refresh-token rotation is guarded by a process lock and atomic writes; short-lived access tokens are cached locally to make concurrent account-level commands safe.
- Charts expose only Top 3 per list by platform design; use `--search` for specific topics.

## License

MIT — see [LICENSE](LICENSE). See also [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).
