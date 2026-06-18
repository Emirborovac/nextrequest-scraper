"""Iowa State Patrol crash reports -> iowa.db (one row per involved person).

Source: https://accidentreports.iowa.gov/  (Iowa State Patrol "Minimal Crash Reports").
Unlike the MA/CA tabs (de-identified open data), these public ISP reports are
NAME-BEARING: each involved person's NAME, AGE and CITY & STATE of residence, the
vehicle year/make, the crash county/date/severity and a free-text fault narrative.
NOT present: street address, phone, VIN, vehicle model, DOB (the site's FAQ withholds
DOB / home phone / SSN; "full reports" have been offline since 2015-01-01).

Coverage = Iowa State Patrol only (highway / serious crashes) -> a small rolling set
(~a dozen reports in the 15-day window the portal exposes). Powers the Iowa tab:
date filter, per-day counts, named reports table, CSV export.

Compliance note: this is public-record data, but using crash-victim name/address for
attorney solicitation is governed by the federal DPPA + Maracich v. Spears and Iowa
rules of professional conduct. Retrieval is not permission to market. Run daily via cron.
"""
import urllib.request, ssl, sqlite3, os, re, html, http.cookiejar

CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
BASE = os.environ.get("IOWA_BASE", "https://accidentreports.iowa.gov")
DB = os.environ.get("IOWA_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "iowa.db"))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
BOUNDARY = "----iowaformboundary7e3a1c9d"

# clean output columns (in order) for the CSV / table
COLUMNS = ["case_no", "crash_type", "county_name", "county_code", "crash_date", "crash_time",
           "location", "role", "name", "age", "city_state", "vehicle_year", "vehicle_make",
           "injury_type", "seatbelt", "transported_to", "transported_by",
           "carrier_name", "carrier_city", "hazmat", "officer", "summary", "report_link"]


def _opener():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj),
                                     urllib.request.HTTPSHandler(context=CTX))
    op.addheaders = [("User-Agent", UA), ("Accept", "text/html")]
    return op


def _get(op, url, to=45):
    return op.open(url, timeout=to).read().decode("utf-8", "replace")


def _post_search(op, date="", typ="", county="", to=45):
    """The search form is a multipart POST to index.php?; results come back after a
    302 redirect (urllib follows it) and reference each report as ?pgname=minimal_ar&caseno=."""
    parts = []
    for k, v in (("date", date), ("type", typ), ("countypulldown", county), ("submit", "Search")):
        parts.append("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (BOUNDARY, k, v))
    body = ("".join(parts) + "--%s--\r\n" % BOUNDARY).encode("utf-8")
    req = urllib.request.Request(BASE + "/index.php?", data=body,
                                 headers={"Content-Type": "multipart/form-data; boundary=%s" % BOUNDARY})
    return op.open(req, timeout=to).read().decode("utf-8", "replace")


def _clean(s):
    s = re.sub(r"<[^>]+>", " ", s)
    s = s.replace("&nbsp;", " ")
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _pairs(rpt):
    """Ordered (label, value) pairs from the report's fieldname/fielddata table cells."""
    out = []
    for lab, val in re.findall(
            r'class="fieldname"[^>]*>(.*?)</td>\s*<td[^>]*class="fielddata"[^>]*>(.*?)</td>',
            rpt, re.I | re.S):
        out.append((_clean(lab).rstrip(":").strip(), _clean(val)))
    return out


def _parse(caseno, rpt, cmap):
    pairs = _pairs(rpt)
    text = _clean(rpt)

    def first(label):
        for l, v in pairs:
            if l.lower() == label.lower():
                return v
        return ""

    # header -------------------------------------------------------------
    case_no, crash_type = "", ""
    for i, (l, v) in enumerate(pairs):
        if l.lower() == "case number":
            case_no = v
            if i + 1 < len(pairs) and pairs[i + 1][0].lower() == "type":
                crash_type = pairs[i + 1][1]
            break
    county_code = re.sub(r"\D", "", first("County"))
    county_code = county_code.zfill(2) if county_code else ""
    county_name = cmap.get(county_code, "")
    crash_date, crash_iso = "", ""
    m = re.match(r"(\d{2})(\d{2})(\d{4})", first("Crash Date"))
    if m:
        mm, dd, yy = m.groups()
        crash_date = "%s/%s/%s" % (mm, dd, yy)
        crash_iso = "%s-%s-%s" % (yy, mm, dd)
    crash_time = first("Time")
    location = first("Location")
    carrier_name = first("Name of Carrier")
    carrier_city = first("City & State of Carrier")
    hazmat = first("Hazmat Involved?")
    sm = re.search(r"Summary:\s*(.*?)\s*(?:Officer Name:|Any questions about this report)", text, re.I)
    summary = sm.group(1).strip() if sm else ""
    om = re.search(r"Officer Name:\s*(.*?)\s*(?:Post:|Assisted By:|Any questions)", text, re.I)
    officer = om.group(1).strip() if om else ""

    # vehicle + injury segments (anchored on the unique "Vehicle N Year" / "Injury N Type") ---
    vehicles, injuries, seg = [], [], None
    for l, v in pairs:
        mv = re.match(r"Vehicle (\d+) Year", l, re.I)
        mi = re.match(r"Injury (\d+) Type", l, re.I)
        if mv:
            seg = {"_n": mv.group(1), "Year": v}; vehicles.append(seg); continue
        if mi:
            seg = {"_n": mi.group(1), "Type": v}; injuries.append(seg); continue
        if seg is not None:
            seg[l] = v

    people, order = {}, []

    def person(nm):
        k = re.sub(r"\s+", " ", nm).strip().upper()
        if k not in people:
            people[k] = {"name": nm.strip()}; order.append(k)
        return people[k]

    for veh in vehicles:
        nm = (veh.get("Driver Name") or "").strip()
        if not nm:
            continue
        p = person(nm)
        p.setdefault("role", "Driver %s" % veh["_n"])
        p["age"] = p.get("age") or veh.get("Age", "")
        p["city_state"] = p.get("city_state") or veh.get("City & State of Residence", "")
        p["vehicle_year"] = veh.get("Year", "")
        p["vehicle_make"] = veh.get("Make", "")
    for inj in injuries:
        nm = (inj.get("Name") or "").strip()
        if not nm:
            continue
        p = person(nm)
        p.setdefault("role", "Injured")
        p["injury_type"] = inj.get("Type", "")
        p["age"] = p.get("age") or inj.get("Age", "")
        p["city_state"] = p.get("city_state") or inj.get("City & State of Residence", "")
        p["seatbelt"] = inj.get("Seatbelt Use", "")
        p["transported_to"] = inj.get("Transported To", "")
        p["transported_by"] = inj.get("Transported By", "")

    link = "%s/index.php?pgname=minimal_ar&caseno=%s" % (BASE, caseno)
    base = {"case_no": case_no or caseno, "crash_type": crash_type, "county_name": county_name,
            "county_code": county_code, "crash_date": crash_date, "crash_time": crash_time,
            "location": location, "carrier_name": carrier_name, "carrier_city": carrier_city,
            "hazmat": hazmat, "officer": officer, "summary": summary, "report_link": link}
    person_cols = ("role", "name", "age", "city_state", "vehicle_year", "vehicle_make",
                   "injury_type", "seatbelt", "transported_to", "transported_by")
    rows = []
    if not order:                                  # keep the crash even if no named people
        r = dict(base); r.update({c: "" for c in person_cols}); rows.append((crash_iso, r))
    for k in order:
        r = dict(base)
        for c in person_cols:
            r[c] = people[k].get(c, "")
        rows.append((crash_iso, r))
    return rows


def _county_map_and_dates(op):
    home = _get(op, BASE + "/")
    cmap = {}
    for code, name in re.findall(r'<option value="(\d{2})">([^<]*?County)', home):
        cmap[code] = re.sub(r"\s+", " ", html.unescape(name)).strip()
    dates = re.findall(r'<option value="(\d{4}-\d{2}-\d{2})">', home)
    return cmap, dates


def _enumerate(op, dates):
    """Union of the all-reports search and each per-day search (cheap; tiny data set)."""
    seen = set()
    try:
        seen.update(re.findall(r"caseno=(\d+)", _post_search(op)))
    except Exception as e:
        print("[iowa] all-search ERR", str(e)[:80])
    for d in dates:
        try:
            seen.update(re.findall(r"caseno=(\d+)", _post_search(op, date=d)))
        except Exception as e:
            print("[iowa] date %s ERR %s" % (d, str(e)[:60]))
    return sorted(seen)


def build():
    op = _opener()
    cmap, dates = _county_map_and_dates(op)
    casenos = _enumerate(op, dates)
    allrows = []
    for cn in casenos:
        try:
            rpt = _get(op, BASE + "/index.php?pgname=minimal_ar&caseno=%s" % cn)
            allrows += _parse(cn, rpt, cmap)
        except Exception as e:
            print("[iowa] report %s ERR %s" % (cn, str(e)[:60]))

    conn = sqlite3.connect(DB, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("DROP TABLE IF EXISTS iowa")
    conn.execute("CREATE TABLE iowa (crash_date_iso TEXT, %s)" % ", ".join('"%s" TEXT' % c for c in COLUMNS))
    conn.execute("CREATE INDEX ix_iso ON iowa(crash_date_iso)")
    batch = [[di] + [r.get(c, "") for c in COLUMNS] for di, r in allrows]
    conn.executemany("INSERT INTO iowa VALUES (%s)" % ",".join("?" * (len(COLUMNS) + 1)), batch)
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM iowa").fetchone()[0]
    nd = conn.execute("SELECT COUNT(DISTINCT case_no) FROM iowa").fetchone()[0]
    named = conn.execute("SELECT COUNT(*) FROM iowa WHERE name<>''").fetchone()[0]
    rng = conn.execute("SELECT MIN(NULLIF(crash_date_iso,'')), MAX(NULLIF(crash_date_iso,'')) FROM iowa").fetchone()
    conn.close()
    print("[iowa_csv] reports=%d person_rows=%d named=%d range=%s..%s" % (nd, n, named, rng[0], rng[1]))
    return n


if __name__ == "__main__":
    build()
