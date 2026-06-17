"""California CCRS store -> ca.db. Joins Crashes_<year> + Parties_<year> (one row per party) with a
sortable date + explicit at-fault flag. Powers the California tab: date filter, per-day accident counts,
at-fault filter, and CSV export. De-identified (no names/addresses/plates/VIN). Run daily via cron."""
import urllib.request, urllib.parse, json, ssl, sqlite3, os

CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
API = "https://data.ca.gov/api/3/action"
PKG = os.environ.get("CA_PKG", "ccrs")
YEAR = os.environ.get("CA_YEAR", "2026")
DB = os.environ.get("CA_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ca.db"))

CRASH_SEL = ["Collision Id", "Report Number", "Crash Date Time", "City Name", "County Code",
             "Collision Type Description", "HitRun", "NumberInjured", "NumberKilled", "Latitude", "Longitude",
             "PrimaryRoad", "SecondaryRoad", "Primary Collision Factor Violation", "LightingDescription",
             "Weather 1", "Road Condition 1"]
PARTY_SEL = ["CollisionId", "PartyNumber", "PartyType", "IsAtFault", "IsHitAndRun", "GenderDescription",
             "StatedAge", "RaceDesc", "Vehicle1Make", "Vehicle1Model", "Vehicle1Year",
             "MovementPrecCollDescription", "SpeedLimit"]

# clean output columns (in order) for the CSV/table
COLUMNS = ["collision_id", "report_number", "crash_date", "city", "county_code", "collision_type", "hit_run",
           "num_injured", "num_killed", "latitude", "longitude", "primary_road", "secondary_road",
           "primary_factor", "lighting", "weather", "road_condition",
           "party_number", "party_type", "is_at_fault", "party_hit_run", "gender", "age", "race",
           "vehicle_make", "vehicle_model", "vehicle_year", "movement_before_crash", "speed_limit"]


def _g(u, to=120):
    r = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=to, context=CTX).read())


def _resources():
    d = _g(API + "/package_show?id=" + PKG)
    return {r["name"]: r["id"] for r in d["result"]["resources"] if r.get("datastore_active")}


def _fetch(rid, fields):
    recs = []; off = 0; lim = 20000
    fsel = ",".join(fields)
    while True:
        u = API + "/datastore_search?" + urllib.parse.urlencode(
            {"resource_id": rid, "limit": lim, "offset": off, "fields": fsel})
        res = _g(u)["result"]
        rows = res.get("records", [])
        if not rows:
            break
        recs += rows; off += len(rows)
        if off >= res.get("total", 0):
            break
    return recs


def _iso(v):
    s = str(v) if v is not None else ""
    return s[:10] if (len(s) >= 10 and s[4] == "-" and s[7] == "-") else None


def _yn(v):
    s = str(v).strip().lower()
    if s in ("true", "t", "y", "yes", "1"):
        return "Y"
    if s in ("false", "f", "n", "no", "0"):
        return "N"
    return v


def build():
    res = _resources()
    crid = res.get("Crashes_%s" % YEAR)
    prid = res.get("Parties_%s" % YEAR)
    crashes = _fetch(crid, CRASH_SEL)
    parties = _fetch(prid, PARTY_SEL)
    cmap = {c.get("Collision Id"): c for c in crashes}
    conn = sqlite3.connect(DB, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("DROP TABLE IF EXISTS ca")
    conn.execute("CREATE TABLE ca (crash_date_iso TEXT, %s)" % ", ".join('"%s" TEXT' % c for c in COLUMNS))
    conn.execute("CREATE INDEX ix_iso ON ca(crash_date_iso)")
    conn.execute("CREATE INDEX ix_fault ON ca(is_at_fault)")
    batch = []
    for p in parties:
        c = cmap.get(p.get("CollisionId"), {})
        di = _iso(c.get("Crash Date Time"))
        row = {"collision_id": p.get("CollisionId"), "report_number": c.get("Report Number"), "crash_date": di,
               "city": c.get("City Name"), "county_code": c.get("County Code"),
               "collision_type": c.get("Collision Type Description"), "hit_run": c.get("HitRun"),
               "num_injured": c.get("NumberInjured"), "num_killed": c.get("NumberKilled"),
               "latitude": c.get("Latitude"), "longitude": c.get("Longitude"),
               "primary_road": c.get("PrimaryRoad"), "secondary_road": c.get("SecondaryRoad"),
               "primary_factor": c.get("Primary Collision Factor Violation"),
               "lighting": c.get("LightingDescription"), "weather": c.get("Weather 1"),
               "road_condition": c.get("Road Condition 1"), "party_number": p.get("PartyNumber"),
               "party_type": p.get("PartyType"), "is_at_fault": _yn(p.get("IsAtFault")),
               "party_hit_run": _yn(p.get("IsHitAndRun")), "gender": p.get("GenderDescription"),
               "age": p.get("StatedAge"), "race": p.get("RaceDesc"), "vehicle_make": p.get("Vehicle1Make"),
               "vehicle_model": p.get("Vehicle1Model"), "vehicle_year": p.get("Vehicle1Year"),
               "movement_before_crash": p.get("MovementPrecCollDescription"), "speed_limit": p.get("SpeedLimit")}
        batch.append([di] + [None if row[k] is None else str(row[k]) for k in COLUMNS])
    conn.executemany("INSERT INTO ca VALUES (%s)" % ",".join("?" * (len(COLUMNS) + 1)), batch)
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM ca").fetchone()[0]
    nd = conn.execute("SELECT COUNT(DISTINCT collision_id) FROM ca").fetchone()[0]
    rng = conn.execute("SELECT MIN(crash_date_iso), MAX(crash_date_iso) FROM ca").fetchone()
    fault = dict(conn.execute("SELECT is_at_fault, COUNT(*) FROM ca GROUP BY is_at_fault").fetchall())
    conn.close()
    print("[ca_csv] parties=%d accidents=%d range=%s..%s fault=%s" % (n, nd, rng[0], rng[1], fault))
    return n


if __name__ == "__main__":
    build()
