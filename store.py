import sqlite3, os, time

DB_PATH = os.environ.get("OAKLAND_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "oakland.db"))

# The 15 fields from Example.xlsx (same schema as the main warehouse)
EXCEL_FIELDS = ["title", "county", "crash_id", "name", "ethnicity", "gender", "age",
                "crash_severity", "vin", "street", "phone", "vehicle_model",
                "vehicle_make", "vehicle_year", "report_link"]
EXCEL_LABELS = {"title": "Title", "county": "County", "crash_id": "Crash ID Number", "name": "Name",
                "ethnicity": "Ethnicity", "gender": "Gender Identity", "age": "AGE",
                "crash_severity": "Crash Severity", "vin": "VIN", "street": "Street",
                "phone": "Phone Number 1", "vehicle_model": "Vehicle Model",
                "vehicle_make": "Vehicle Make", "vehicle_year": "Vehicle Year",
                "report_link": "Report / Summary Link"}
META = ["title_file", "created_at", "doc_date", "folder_name", "file_extension", "redacted_at",
        "document_path", "download_url", "status", "is_crash", "ai_reason", "pages_used",
        "fetched_at", "classified_at"]


def connect():
    c = sqlite3.connect(DB_PATH, timeout=60)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init():
    c = connect()
    cols = META + EXCEL_FIELDS
    c.execute("CREATE TABLE IF NOT EXISTS docs (doc_id INTEGER PRIMARY KEY, "
              + ", ".join('"%s" TEXT' % x for x in cols) + ")")
    for ix in ("created_at", "status", "is_crash"):
        c.execute('CREATE INDEX IF NOT EXISTS ix_%s ON docs("%s")' % (ix, ix))
    c.execute("CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, "
              "started_at TEXT, finished_at TEXT, status TEXT, new_docs INTEGER, "
              "classified INTEGER, crashes INTEGER, note TEXT)")
    c.commit()
    c.close()


def add_doc(meta):
    """INSERT OR IGNORE so re-runs never overwrite an already-classified row. Returns True if newly added."""
    c = connect()
    keys = list(meta.keys())
    cur = c.execute("INSERT OR IGNORE INTO docs (%s) VALUES (%s)"
                    % (",".join('"%s"' % k for k in keys), ",".join("?" * len(keys))),
                    [meta[k] for k in keys])
    c.commit()
    n = cur.rowcount
    c.close()
    return n > 0


def pending(exts):
    c = connect()
    rows = c.execute("SELECT * FROM docs WHERE status='new' AND lower(file_extension) IN (%s)"
                     % (",".join("?" * len(exts))), [e.lower() for e in exts]).fetchall()
    c.close()
    return rows


def update(doc_id, **kw):
    c = connect()
    c.execute("UPDATE docs SET " + ", ".join('"%s"=?' % k for k in kw) + " WHERE doc_id=?",
              list(kw.values()) + [doc_id])
    c.commit()
    c.close()


def counts():
    c = connect()
    r = {"total": c.execute("SELECT COUNT(*) FROM docs").fetchone()[0],
         "crash": c.execute("SELECT COUNT(*) FROM docs WHERE is_crash='yes'").fetchone()[0],
         "pending": c.execute("SELECT COUNT(*) FROM docs WHERE status='new'").fetchone()[0],
         "done": c.execute("SELECT COUNT(*) FROM docs WHERE status='done'").fetchone()[0]}
    c.close()
    return r


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def start_run(kind):
    c = connect()
    cur = c.execute("INSERT INTO runs (kind, started_at, status) VALUES (?, ?, 'running')", (kind, _now()))
    c.commit(); rid = cur.lastrowid; c.close()
    return rid


def finish_run(rid, status="done", new_docs=0, classified=0, crashes=0, note=""):
    c = connect()
    c.execute("UPDATE runs SET finished_at=?, status=?, new_docs=?, classified=?, crashes=?, note=? WHERE id=?",
              (_now(), status, new_docs, classified, crashes, note[:300], rid))
    c.commit(); c.close()


def recent_runs(limit=25):
    c = connect()
    rows = c.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    c.close()
    return rows
