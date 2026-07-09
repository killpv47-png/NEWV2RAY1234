# Changes made

## Fixed
- Switched panel HTTP server from single-threaded `HTTPServer` to `ThreadingHTTPServer` to reduce panel/API blocking and intermittent UI disconnects.
- Added DB restore fallback from embedded Xray config backup when `panel_db.json` is missing/corrupted.
- Kept periodic DB/subscription flushing so state is less likely to disappear on rerun/cancel.
- Added automatic private-tunnel host regeneration on startup and ensured regenerated host is saved back to DB.
- Applied `push_subs_to_github()` immediately after saving system settings so repo path/token changes are applied without waiting.
- Added Xray Stats API configuration (`stats`, `api`, routing, user stats flags) and real-traffic refresh logic.
- Stopped log-sniffer from incrementing usage for `real_traffic=True` users, so real-traffic users are driven by Xray Stats API instead of fake/log-based estimates.
- Kept fallback log-based estimation only for non-real-traffic users.
- Added testability guard `if __name__ == "__main__": main()` so the module can be imported safely in tests.
- Changed workflow concurrency to `cancel-in-progress: false` to reduce abrupt run replacement and state loss.
- Added checkout `fetch-depth: 0` for more reliable git history/push behavior.

## Added
- `login_template.html`
- `panel_template.html`
- `test_killpv2.py`
- `README_SECRETS.md`
