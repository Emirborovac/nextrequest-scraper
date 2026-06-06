# NextRequest crash-report pipeline

Standalone scraper for a [NextRequest](https://nextrequest.com) public-records portal
(default: Oakland, CA). It harvests recently-uploaded documents, uses an LLM to decide
whether each PDF is a **motor-vehicle traffic crash / collision report**, extracts the
15 target fields when it is, and exports them to Excel.

> **Reality note:** documents on these portals are released **redacted**. This pipeline
> tells you *which* recent docs are crash reports and pulls whatever fields survive
> redaction — it does not un-redact anything. Whether the result contains usable
> name/address PII is exactly what the first run reveals.

## Install
```bash
sudo apt-get -y install poppler-utils python3-pip
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...          # set on the host, never commit it
export OPENAI_MODEL=gpt-4o-mini       # any vision-capable model your key supports
# optional — point at any NextRequest agency:
# export NR_BASE=https://<agency>.nextrequest.com
# optional — which result stream to monitor (default "redacted"; "" = all docs):
# export NR_SEARCH=redacted
```

## Run (one command)
```bash
pip install -r requirements.txt
cp .env.example .env              # then edit .env: OPENAI_API_KEY, OPENAI_MODEL, SEED_DAYS...
python app.py                    # reads .env, runs the scraper (seed + 2h poll) AND the dashboard, with logging
```
Config is loaded from `.env` automatically (or set the same vars with `export …` — both work).
`.env` is gitignored, so your key never gets committed.
Then open **http://&lt;host&gt;:8080** — stat cards, the **Scraping operations** log
(start / finish / new / parsed / crashes), the crash-report table (15 fields),
recent classifications, and an Excel export button.

### Advanced / manual
```bash
python3 run.py monitor       # scraper loop only, no UI
python3 run.py seed 15       # one backfill pass
python3 run.py poll          # one incremental pass
python3 export.py out.xlsx   # Excel dump
RUN_MONITOR=0 python app.py  # UI only (no scraping)
```

## Run as a service (systemd)
`/etc/systemd/system/nrmonitor.service`:
```ini
[Service]
WorkingDirectory=/opt/nextrequest-scraper
Environment=OPENAI_API_KEY=sk-...
Environment=OPENAI_MODEL=gpt-5-mini
Environment=SEED_DAYS=2
ExecStart=/usr/bin/python3 run.py monitor
Restart=always
[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl enable --now nrmonitor          # monitor loop
PORT=8080 nohup python3 app.py &               # UI (or a second unit)
```

## Old-style cron (alternative to `monitor`)
```cron
0 */2 * * *  cd /opt/nextrequest-scraper && OPENAI_API_KEY=sk-... python3 run.py poll >> poll.log 2>&1
```

## Files
| File | Role |
|---|---|
| `nextrequest.py` | NextRequest JSON API client (list newest-first, download, size guard) |
| `store.py` | SQLite store; 15 Example.xlsx fields + document metadata |
| `classify.py` | LLM classify (crash y/n) + field extraction |
| `run.py` | orchestrator: `seed` / `poll` / `harvest` / `process` |
| `export.py` | Excel dump of confirmed crash reports |

## Cost controls (built in)
- only **PDFs** are classified (video/audio/office skipped); files >30 MB skipped
- **page 1 first**; PDFs with a text layer use cheap **text** (no vision); scans fall back to a **low-detail** image
- escalates to **page 2** only when page 1 is `uncertain`
- field extraction runs **only** on docs already classified as crash reports
