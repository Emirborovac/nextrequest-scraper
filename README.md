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
```

## Run
```bash
python3 run.py seed 15      # first run: last 15 days -> classify -> extract
python3 run.py poll         # incremental: last 2 days (schedule every 2h)
python3 export.py out.xlsx  # Excel dump of crash rows (fast, indexed query)
```

## Schedule (every 2 hours)
```cron
0 */2 * * *  cd /opt/nextrequest && OPENAI_API_KEY=sk-... python3 run.py poll >> poll.log 2>&1
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
