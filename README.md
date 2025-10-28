# GCal→Sheet Agent

Cross-platform, low-footprint agent to sync Google Calendar events to a Google Sheet with weekly tabs and optional 2‑way sync back to Calendar, plus one‑way posting to a Slack To‑do channel.

- Weekly sheet name format: `Oct 27 - Oct 31`
- New sheet tab auto-created every Monday (configurable week start)
- 2‑way sync (optional): edit the sheet, push changes back to Calendar
- 1‑way Slack: post upcoming events to your to‑do channel
- Works on Windows, macOS, Linux

## Install

Prereqs: Python 3.9+.

```bash
# Clone and set up virtualenv
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install --upgrade pip
pip install -e .
```

Option B (isolated, system-wide install via pipx):

```bash
pip install pipx
pipx install .
gcalsheet-agent --help
```

Option C using `requirements.txt`:

```bash
pip install -r requirements.txt
pip install -e .
```

## Configure

1) Create state dir and default config:

```bash
gcalsheet-agent init
```

This creates `.gcalsheet-agent/config.json`. Edit fields as needed:

- `google.credentials_path`: Path to your `client_secret.json` (OAuth client) copied into `.gcalsheet-agent/`.
- `google.calendar_id`: Typically `primary`.
- `google.spreadsheet_title`: Title of spreadsheet to create/use.
- `slack.bot_token`: Slack bot token (optional, for 1‑way posting).
- `slack.todo_channel`: Channel ID or name where to post todos.
- `sync.two_way`: Enable 2‑way sync.
- `sync.week_start`: 0=Monday. New tab created when a new ISO week starts.
- `sync.week_span_days`: Title shows start to `start+week_span_days` (default Mon‑Fri).

2) Google auth:

- Place your OAuth client file at the configured `google.credentials_path` (default: `.gcalsheet-agent/client_secret.json`).
- Run:

```bash
gcalsheet-agent auth-google
```

This opens a browser for consent and saves a token at `.gcalsheet-agent/token.json`.

3) Slack (optional):

- Create a Slack app, add `chat:write` scope, install to workspace.
- Set `slack.bot_token` and `slack.todo_channel` in config.

## Usage

- Sync current week to sheet and post Slack todos:

```bash
gcalsheet-agent run
```

- Sync a specific week (Monday date recommended):

```bash
gcalsheet-agent run --now 2025-10-27
```

- Apply 2‑way updates (push sheet edits back to Calendar):

```bash
gcalsheet-agent run --apply-updates
```

Columns used in each weekly sheet:

1. Event ID
2. Title
3. Start (YYYY-MM-DD HH:MM or YYYY-MM-DD for all-day)
4. End (YYYY-MM-DD HH:MM or YYYY-MM-DD for all-day)
5. All Day (TRUE/FALSE)
6. Location
7. Description
8. Attendees (comma emails)
9. Calendar Link

## Packaging (optional)

- Single-file binaries via PyInstaller:

```bash
pip install pyinstaller
pyinstaller -F -n gcalsheet-agent -c -s -i NONE - \
  --paths .venv/lib/python*/site-packages \
  --collect-all googleapiclient --collect-all google_auth_oauthlib --collect-all google.auth \
  --collect-all slack_sdk \
  --hidden-import dateutil.tz \
  --hidden-import googleapiclient.discovery \
  --hidden-import googleapiclient.http \
  --hidden-import httplib2 \
  - <<'PY'
from gcalsheet_agent.cli import main
if __name__ == '__main__':
    main()
PY

# Output in dist/gcalsheet-agent (exe on Windows)
```

- Zipapp (requires deps available on target, not fully self-contained):

```bash
python -m zipapp gcalsheet_agent -m 'gcalsheet_agent.cli:main' -o gcalsheet-agent.pyz
python gcalsheet-agent.pyz run
```

- Or build a wheel:

```bash
pip install build
python -m build
```

## Notes

- The agent stores config and tokens in `.gcalsheet-agent/` in your current working directory.
- It queries Calendar in your calendar's timezone.
- Slack posting is deduplicated per weekly tab.
- Low resource use: single-shot CLI; you can cron/schedule it weekly or daily.
