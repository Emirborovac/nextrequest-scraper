"""Iowa tab (Blueprint) for the crash-data console. Reads iowa.db (built by iowa_csv.py)
and serves /iowa (date filter + per-day counts + named reports table) and /iowa.csv.

Iowa is the one name-bearing source: each row is an involved person (name, age,
city/state, role, vehicle) with the crash county/date/severity and fault narrative.
Source = Iowa State Patrol minimal crash reports (accidentreports.iowa.gov)."""
import io, csv, os, sqlite3, datetime, time
from flask import Blueprint, render_template_string, send_file, abort, request
import iowa_csv

bp = Blueprint("iowa", __name__)
IOWA_DB = os.environ.get("IOWA_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "iowa.db"))


def iowa_meta():
    if not os.path.exists(IOWA_DB):
        return None
    c = sqlite3.connect(IOWA_DB)
    try:
        row = c.execute("SELECT MIN(NULLIF(crash_date_iso,'')), MAX(NULLIF(crash_date_iso,'')), "
                        "COUNT(*), COUNT(DISTINCT case_no), "
                        "SUM(CASE WHEN name<>'' THEN 1 ELSE 0 END) FROM iowa").fetchone()
    except Exception:
        c.close(); return None
    c.close()
    if not row or row[3] in (None, 0):
        return None
    return {"dmin": row[0], "dmax": row[1], "people": row[2], "reports": row[3], "named": row[4] or 0,
            "updated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(os.path.getmtime(IOWA_DB)))}


@bp.route("/iowa.csv")
def iowa_download():
    meta = iowa_meta()
    if not meta:
        abort(404)
    frm = request.args.get("from") or meta["dmin"] or "0000-00-00"
    to = request.args.get("to") or meta["dmax"] or "9999-99-99"
    cols = iowa_csv.COLUMNS
    c = sqlite3.connect(IOWA_DB)
    rows = c.execute('SELECT %s FROM iowa WHERE crash_date_iso BETWEEN ? AND ? '
                     'ORDER BY crash_date_iso DESC, case_no DESC'
                     % ",".join('"%s"' % x for x in cols), (frm, to)).fetchall()
    c.close()
    sio = io.StringIO()
    w = csv.writer(sio); w.writerow(cols); w.writerows(rows)
    data = io.BytesIO(sio.getvalue().encode("utf-8")); data.seek(0)
    return send_file(data, as_attachment=True,
                     download_name="iowa_isp_%s_to_%s.csv" % (frm, to), mimetype="text/csv")


IOWA_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Iowa — State Patrol Crash Reports</title>
<style>
:root{--navy:#0b3d91;--ink:#1c2b3a;--muted:#6b7c91;--line:#dfe7f0;--soft:#f5f9ff;--pale:#fdeaea;--red:#b23b3b;}
*{box-sizing:border-box}body{margin:0;font-family:-apple-system,"Segoe UI",Roboto,Arial,sans-serif;color:var(--ink);background:#fafbfd;font-size:15px}
.page{max-width:1180px;margin:0 auto;padding:28px 32px 60px;background:#fff}
h1{color:var(--navy);font-size:1.5rem;margin:0 0 2px}
.sub{color:var(--muted);margin:0 0 14px;font-size:.88rem}
.nav{display:flex;gap:6px;margin:4px 0 20px;border-bottom:2px solid var(--line)}
.nav a{padding:8px 16px;text-decoration:none;color:var(--muted);font-weight:600;border-bottom:3px solid transparent;margin-bottom:-2px}
.nav a.on{color:var(--navy);border-bottom-color:var(--navy)}
.controls{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap;background:var(--soft);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin-bottom:16px}
.filter{display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap}
.filter label{font-size:.72rem;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.03em;display:flex;flex-direction:column;gap:4px}
.filter input{border:1px solid var(--line);border-radius:6px;padding:8px 10px;font-size:.9rem;color:var(--ink)}
.filter button{background:var(--navy);color:#fff;border:0;border-radius:6px;padding:9px 18px;font-weight:600;cursor:pointer;font-size:.9rem}
a.btn{display:inline-block;background:var(--navy);color:#fff;text-decoration:none;padding:10px 18px;border-radius:6px;font-weight:700;font-size:.9rem;white-space:nowrap}
a.btn:hover{background:#0a2f73}
.cards{display:flex;gap:14px;flex-wrap:wrap;margin:0 0 8px}
.card{flex:1;min-width:140px;border:1px solid var(--line);border-radius:10px;padding:14px 18px;text-align:center}
.card .n{font-size:1.8rem;font-weight:700;color:var(--navy)}.card .l{color:var(--muted);font-size:.8rem;margin-top:2px}
.card.name{border-color:var(--red)}.card.name .n{color:var(--red)}
.meta{color:var(--muted);font-size:.8rem;margin:10px 0 16px}
.note{background:#fff8e6;border:1px solid #f0e2bd;color:#6b5a1f;border-radius:8px;padding:9px 13px;font-size:.78rem;margin:0 0 16px}
.panel{border:1px solid var(--line);border-radius:10px;overflow:hidden;margin-bottom:18px}
.panel-h{padding:10px 16px;border-bottom:1px solid var(--line);background:var(--soft);font-weight:600;color:var(--navy);font-size:.95rem}
.scroll{max-height:300px;overflow:auto}
.scroll.tall{max-height:560px}
table{border-collapse:collapse;font-size:.84rem;width:100%}
th{text-align:left;color:var(--muted);font-size:.72rem;text-transform:uppercase;letter-spacing:.03em;border-bottom:1px solid var(--line);padding:8px 14px;position:sticky;top:0;background:#fff;white-space:nowrap}
td{padding:7px 14px;border-bottom:1px solid var(--line);vertical-align:top}
tr:last-child td{border-bottom:0}
td.num{text-align:right;font-weight:600;width:90px}
.barcell{width:45%}
.bar{display:block;height:12px;background:var(--navy);border-radius:3px;min-width:2px}
.sev-Fatality{color:var(--red);font-weight:700}.sev-Injury{color:#b9770a;font-weight:600}
.empty{color:var(--muted);padding:22px;text-align:center}
a{color:var(--navy)}
</style></head><body><div class="page">
<h1>Crash Data Console</h1>
<div class="nav"><a href="/">Oakland &middot; NextRequest</a><a href="/massachusetts">Massachusetts</a><a href="/california">California</a><a href="/iowa" class="on">Iowa</a></div>
<p class="sub">Iowa State Patrol minimal crash reports (accidentreports.iowa.gov) &middot; <b>name-bearing</b> &middot; one row per involved person &middot; refreshed daily</p>
{% if meta %}
<div class="note">Public ISP records. Fields exposed: name, age, <b>city &amp; state</b> of residence (no street address), vehicle year/make, county, date, severity, fault narrative. No phone/VIN/DOB. Coverage = Iowa State Patrol only (≈15-day rolling window). Marketing use is governed by the DPPA + state rules — retrieval is not permission to solicit.</div>
<div class="controls">
  <form class="filter" method="get" action="/iowa">
    <label>From<input type="date" name="from" value="{{ frm }}" min="{{ meta.dmin }}" max="{{ meta.dmax }}"></label>
    <label>To<input type="date" name="to" value="{{ to }}" min="{{ meta.dmin }}" max="{{ meta.dmax }}"></label>
    <button type="submit">Apply</button>
  </form>
  <a class="btn" href="/iowa.csv?from={{ frm }}&amp;to={{ to }}">&#8595; Download CSV ({{ "{:,}".format(tot_people) }} rows)</a>
</div>
<div class="cards">
  <div class="card"><div class="n">{{ "{:,}".format(tot_reports) }}</div><div class="l">crash reports in range</div></div>
  <div class="card"><div class="n">{{ "{:,}".format(tot_people) }}</div><div class="l">involved-person rows</div></div>
  <div class="card name"><div class="n">{{ "{:,}".format(tot_named) }}</div><div class="l">with a name</div></div>
</div>
<p class="meta">Range <b>{{ frm }} &rarr; {{ to }}</b> &middot; data available {{ meta.dmin }} &rarr; {{ meta.dmax }} &middot; updated {{ meta.updated }}</p>
<div class="panel">
  <div class="panel-h">Reports per day</div>
  <div class="scroll"><table><thead><tr><th>Date</th><th class="num">Reports</th><th class="barcell"></th></tr></thead><tbody>
  {% for d, n in perday %}<tr><td>{{ d }}</td><td class="num">{{ n }}</td><td class="barcell"><span class="bar" style="width:{{ (n * 100 // maxc) if maxc else 0 }}%"></span></td></tr>{% endfor %}
  {% if not perday %}<tr><td colspan="3" class="empty">No reports in this range.</td></tr>{% endif %}
  </tbody></table></div>
</div>
<div class="panel">
  <div class="panel-h">Involved people ({{ rows|length }}{% if rows|length >= cap %}, first {{ cap }}{% endif %})</div>
  <div class="scroll tall"><table><thead><tr>
    <th>Date</th><th>County</th><th>Severity</th><th>Role</th><th>Name</th><th>Age</th>
    <th>City &amp; State</th><th>Vehicle</th><th>Location</th><th>Report</th></tr></thead><tbody>
  {% for r in rows %}<tr>
    <td>{{ r.crash_date or r.crash_date_iso }}</td><td>{{ r.county_name or r.county_code }}</td>
    <td class="sev-{{ r.crash_type }}">{{ r.crash_type }}</td><td>{{ r.role }}</td>
    <td>{{ r.name }}</td><td>{{ r.age }}</td><td>{{ r.city_state }}</td>
    <td>{{ (r.vehicle_year ~ ' ' ~ r.vehicle_make)|trim }}</td><td>{{ r.location }}</td>
    <td><a href="{{ r.report_link }}" target="_blank" rel="noopener">view</a></td></tr>{% endfor %}
  {% if not rows %}<tr><td colspan="10" class="empty">No people in this range.</td></tr>{% endif %}
  </tbody></table></div>
</div>
{% else %}
<p class="empty">No data yet &mdash; the Iowa cache builds automatically each morning (or run <code>python iowa_csv.py</code>).</p>
{% endif %}
</div></body></html>"""


@bp.route("/iowa")
def iowa():
    meta = iowa_meta()
    if not meta:
        return render_template_string(IOWA_PAGE, meta=None)
    frm = request.args.get("from") or meta["dmin"]
    to = request.args.get("to") or meta["dmax"]
    cap = 500
    c = sqlite3.connect(IOWA_DB); c.row_factory = sqlite3.Row
    perday = c.execute("SELECT crash_date_iso, COUNT(DISTINCT case_no) FROM iowa "
                       "WHERE crash_date_iso BETWEEN ? AND ? AND crash_date_iso<>'' "
                       "GROUP BY crash_date_iso ORDER BY crash_date_iso DESC", (frm, to)).fetchall()
    tot = c.execute("SELECT COUNT(DISTINCT case_no), COUNT(*), "
                    "SUM(CASE WHEN name<>'' THEN 1 ELSE 0 END) FROM iowa "
                    "WHERE crash_date_iso BETWEEN ? AND ?", (frm, to)).fetchone()
    rows = c.execute("SELECT * FROM iowa WHERE crash_date_iso BETWEEN ? AND ? "
                     "ORDER BY crash_date_iso DESC, case_no DESC LIMIT ?", (frm, to, cap)).fetchall()
    c.close()
    maxc = max([p[1] for p in perday], default=1)
    return render_template_string(IOWA_PAGE, meta=meta, frm=frm, to=to, perday=perday, rows=rows, cap=cap,
                                  tot_reports=tot[0] or 0, tot_people=tot[1] or 0, tot_named=tot[2] or 0, maxc=maxc)
