# kill_pv2 - Secrets & Setup

## Secrets required in GitHub Actions

### 1) `GH_PAT`
Used for re-triggering the workflow at the end of each cycle.
Recommended scopes:
- `repo`
- `workflow`

### 2) `GH_PAT2`
Used as `SUB_REPO_TOKEN` inside `analytics_worker.py` to push generated subscription files to the subscription repository.
Recommended scopes:
- `repo`

If the subscription repo is private, this token must have access to that repo.

### 3) `TELEGRAM_BOT_TOKEN`
Telegram bot token.

### 4) `TELEGRAM_ADMIN_ID`
Telegram numeric chat ID of the admin.

### 5) `TELEGRAM_CHANNEL_ID`
Telegram channel ID or channel username.
Examples:
- `@your_channel_username`
- `-1001234567890`

---

## Important notes
- The panel now persists system settings in `system_config.json` and reloads them on restart.
- Private tunnel hosts are regenerated automatically after restart because `trycloudflare` hosts are ephemeral.
- Real traffic mode now uses Xray Stats API, so each VLESS user must have an `email` set in the Xray client entry. This patch already keeps the username as email in the generated Xray config.
- Current implementation does **not** require any extra Cloudflare secret because the selected strategy is automatic private-tunnel rebuild after rerun.

---

## Files changed
- `analytics_worker.py`
- `data-sync.yml`
- `panel_template.html`
- `login_template.html`
- `test_killpv2.py`
