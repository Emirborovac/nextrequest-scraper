import io, os, csv, time
try:
    from dotenv import load_dotenv
    load_dotenv()                      # read config from a .env file if present
except Exception:
    pass
from flask import Flask, render_template_string, send_file, abort
import store, nextrequest as nr
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

app = Flask(__name__)
store.init()

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>NextRequest Crash Monitor</title>
{% if refresh %}<meta http-equiv="refresh" content="{{ refresh }}">{% endif %}
<style>
:root{--navy:#0b3d91;--ink:#1c2b3a;--muted:#6b7c91;--line:#dfe7f0;--red:#b23b3b;--pale:#fdeaea;}
*{box-sizing:border-box}body{margin:0;font-family:-apple-system,"Segoe UI",Roboto,Arial,sans-serif;color:var(--ink);background:#fff;font-size:15px}
.page{max-width:1320px;margin:0 auto;padding:28px 36px 60px}
h1{color:var(--navy);font-size:1.5rem;margin:0 0 2px}h2{color:var(--navy);font-size:1.1rem;margin:26px 0 8px}
.sub{color:var(--muted);margin:0 0 18px;font-size:.9rem}
.cards{display:flex;gap:14px;flex-wrap:wrap;margin:10px 0 6px}
.card{border:1px solid var(--line);border-radius:8px;padding:14px 20px;min-width:130px}
.card .n{font-size:1.8rem;font-weight:700;color:var(--navy)}.card .l{color:var(--muted);font-size:.82rem}
.card.crash{border-color:var(--red)}.card.crash .n{color:var(--red)}
.meta{color:var(--muted);font-size:.82rem;margin:8px 0 14px}
a.btn{display:inline-block;background:var(--navy);color:#fff;text-decoration:none;padding:9px 16px;border-radius:6px;font-weight:600;font-size:.9rem}
a.btn:hover{background:#0a2f73}
table{width:100%;border-collapse:collapse;font-size:.84rem;margin-top:6px}
th{text-align:left;color:var(--navy);border-bottom:2px solid var(--navy);padding:7px 9px;white-space:nowrap;position:sticky;top:0;background:#fff}
td{padding:6px 9px;border-bottom:1px solid var(--line);vertical-align:top;overflow-wrap:anywhere}
tr.yes{background:var(--pale)}
.wrap{overflow-x:auto;border:1px solid var(--line);border-radius:8px;margin-top:6px}
.empty{color:var(--muted);text-align:center;padding:18px}
a{color:var(--navy)}
</style></head><body><div class="page">
<h1>NextRequest Crash-Report Monitor</h1>
<p class="sub">Source: {{ base }} &middot; monitoring stream: &ldquo;{{ term or 'all' }}&rdquo;{% if refresh %} &middot; auto-refreshes every {{ refresh }}s{% endif %}</p>
<div class="cards">
  <div class="card"><div class="n">{{ "{:,}".format(stats.total) }}</div><div class="l">docs scanned</div></div>
  <div class="card crash"><div class="n">{{ "{:,}".format(stats.crash) }}</div><div class="l">crash reports found</div></div>
  <div class="card"><div class="n">{{ "{:,}".format(stats.done) }}</div><div class="l">classified</div></div>
  <div class="card"><div class="n">{{ "{:,}".format(stats.pending) }}</div><div class="l">pending</div></div>
</div>
<p class="meta">Upload date range: <b>{{ dr[0] or '—' }} &rarr; {{ dr[1] or '—' }}</b>
  &middot; statuses: {% for k,v in by_status.items() %}{{ k }}={{ v }}{% if not loop.last %}, {% endif %}{% endfor %}</p>
<a class="btn" href="/export.xlsx">&#8595; Export crash reports (Excel)</a>

{% if ma %}
<h2>Massachusetts &mdash; daily CSV (Crash + Vehicle, VINs)</h2>
<p class="meta">{{ "{:,}".format(ma.rows) }} rows &middot; {{ ma.cols }} columns &middot; dates {{ ma.dmin }} &rarr; {{ ma.dmax }} &middot; updated {{ ma.updated }}</p>
<a class="btn" href="/ma.csv">&#8595; Download Massachusetts CSV (exact 52 columns)</a>
{% endif %}

<h2>Scraping operations</h2>
<div class="wrap"><table><thead><tr><th>#</th><th>Type</th><th>Started (UTC)</th><th>Finished (UTC)</th>
<th>New docs</th><th>Parsed</th><th>Crashes</th><th>Status</th></tr></thead><tbody>
{% for r in runs %}<tr class="{{ 'yes' if r.crashes and r.crashes>0 else '' }}">
<td>{{ r.id }}</td><td>{{ r.kind }}</td><td>{{ r.started_at }}</td>
<td>{{ r.finished_at if r.finished_at else 'running…' }}</td>
<td>{{ '' if r.new_docs is none else r.new_docs }}</td>
<td>{{ '' if r.classified is none else r.classified }}</td>
<td>{{ '' if r.crashes is none else r.crashes }}</td><td>{{ r.status }}</td></tr>{% endfor %}
{% if not runs %}<tr><td colspan="8" class="empty">No runs yet — start one with <code>run.py seed</code> or <code>run.py monitor</code>.</td></tr>{% endif %}
</tbody></table></div>

<h2>Crash reports ({{ crashes|length }})</h2>
<div class="wrap"><table><thead><tr><th>Uploaded</th><th>Document</th>
{% for f in fields %}<th>{{ labels[f] }}</th>{% endfor %}<th>Source</th></tr></thead><tbody>
{% for r in crashes %}<tr><td>{{ r.created_at }}</td><td>{{ r.title_file }}</td>
{% for f in fields %}<td>{{ r[f] or '' }}</td>{% endfor %}
<td><a href="{{ r.download_url }}" target="_blank" rel="noopener">PDF</a></td></tr>{% endfor %}
{% if not crashes %}<tr><td colspan="20" class="empty">No crash reports identified yet — the monitor will list them here as they are found.</td></tr>{% endif %}
</tbody></table></div>

<h2>Recent classifications &mdash; why each was / wasn't flagged</h2>
<div class="wrap"><table><thead><tr><th>Uploaded</th><th>Document</th><th>Crash?</th><th>Reason (why / why not a crash report)</th></tr></thead><tbody>
{% for r in recent %}<tr class="{{ 'yes' if r.is_crash=='yes' else '' }}"><td>{{ r.created_at }}</td>
<td>{{ r.title_file }}</td><td>{{ r.is_crash or '' }}</td><td>{{ r.ai_reason or '' }}</td></tr>{% endfor %}
{% if not recent %}<tr><td colspan="4" class="empty">Nothing classified yet — run a seed or wait for the poll.</td></tr>{% endif %}
</tbody></table></div>
</div></body></html>"""


@app.route("/")
def index():
    c = store.connect()
    stats = dict(store.counts())
    by_status = {r["status"]: r["n"] for r in
                 c.execute("SELECT status, COUNT(*) n FROM docs GROUP BY status").fetchall()}
    dr = c.execute("SELECT MIN(created_at), MAX(created_at) FROM docs").fetchone()
    crashes = c.execute("SELECT * FROM docs WHERE is_crash='yes' ORDER BY created_at DESC LIMIT 1000").fetchall()
    recent = c.execute("SELECT created_at,title_file,is_crash,ai_reason FROM docs WHERE status='done' "
                       "ORDER BY classified_at DESC LIMIT 100").fetchall()
    runs = c.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 25").fetchall()
    c.close()
    return render_template_string(PAGE, stats=stats, by_status=by_status, dr=dr,
                                  crashes=crashes, recent=recent, runs=runs, ma=ma_status(),
                                  fields=store.EXCEL_FIELDS, labels=store.EXCEL_LABELS,
                                  base=nr.BASE, term=nr.SEARCH_TERM,
                                  refresh=int(os.environ.get("REFRESH_SECS", "20")))


@app.route("/export.xlsx")
def export():
    c = store.connect()
    rows = c.execute("SELECT * FROM docs WHERE is_crash='yes' ORDER BY created_at DESC").fetchall()
    c.close()
    wb = Workbook(); ws = wb.active; ws.title = "Crash reports"
    headers = ["Document"] + [store.EXCEL_LABELS[f] for f in store.EXCEL_FIELDS] + ["Uploaded", "Source Link"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor="0B3D91")
    for r in rows:
        ws.append([r["title_file"]] + [r[f] for f in store.EXCEL_FIELDS] + [r["created_at"], r["download_url"]])
    bio = io.BytesIO(); wb.save(bio); bio.seek(0)
    return send_file(bio, as_attachment=True, download_name="crash_reports.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


MA_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ma_exports",
                      "massachusetts_crash_vehicle_latest.csv")


def ma_status():
    if not os.path.exists(MA_CSV):
        return None
    rows = 0; cols = 0; dmin = dmax = None
    with open(MA_CSV, newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        header = next(r, None)
        cols = len(header) if header else 0
        di = header.index("CRASH_DATE_TEXT") if header and "CRASH_DATE_TEXT" in header else None
        for row in r:
            rows += 1
            if di is not None and di < len(row) and row[di]:
                d = row[di]
                dmin = d if (dmin is None or d < dmin) else dmin
                dmax = d if (dmax is None or d > dmax) else dmax
    return {"rows": rows, "cols": cols, "dmin": dmin, "dmax": dmax,
            "updated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(os.path.getmtime(MA_CSV)))}


@app.route("/ma.csv")
def ma_download():
    if not os.path.exists(MA_CSV):
        abort(404)
    return send_file(MA_CSV, as_attachment=True,
                     download_name="massachusetts_crash_vehicle.csv", mimetype="text/csv")


if __name__ == "__main__":
    # Single entrypoint: `python app.py` runs the scraper (seed-if-empty + 2h poll)
    # in a background thread AND serves the dashboard. Set RUN_MONITOR=0 for UI-only.
    if os.environ.get("RUN_MONITOR", "1") != "0":
        import threading, run
        threading.Thread(target=run.monitor, daemon=True).start()
        print("[app] monitor thread started (seed if empty, then poll every 2h)")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), use_reloader=False)
