"""Massachusetts daily CSV exporter — Crash+Vehicle (VINs) merged, exact client column set/order.
Writes ma_exports/massachusetts_crash_vehicle_latest.csv (+ a dated copy). Run daily via cron."""
import urllib.request, urllib.parse, json, ssl, csv, os, time

CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
SVC = os.environ.get("MA_SVC", "https://gis.crashdata.dot.mass.gov/arcgis/rest/services/MassDOT/MASSDOT_ODP_OPEN_2026/FeatureServer")
MA_FROM = os.environ.get("MA_FROM", "2026-05-30")              # cumulative window start (configurable)
WHERE = "CRASH_DATETIME >= DATE '%s'" % MA_FROM
OUTDIR = os.environ.get("MA_OUTDIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ma_exports"))

# Exact columns + order requested by the client — do not change.
COLUMNS = ["CRASH_NUMB", "CITY_TOWN_NAME", "CRASH_DATE_TEXT", "CRASH_SEVERITY_DESCR", "MAX_INJR_SVRTY_CL",
           "NUMB_VEHC", "NUMB_NONFATAL_INJR", "NUMB_FATAL_INJR", "MANR_COLL_DESCR", "VEHC_MNVR_ACTN_CL",
           "VEHC_SEQ_EVENTS_CL", "WEATH_COND_DESCR", "MOST_HRMFL_EVT_CL", "VEHC_CONFIG_CL", "STREET_NUMB",
           "RDWY", "TRAF_CNTRL_DEVC_TYPE_DESCR", "TRAFY_DESCR_DESCR", "FIRST_HRMF_EVENT_LOC_DESCR",
           "NON_MTRST_TYPE_CL", "NON_MTRST_ACTN_CL", "NON_MTRST_LOC_CL", "CRASH_RPT_IDS", "DRVR_DISTRACTED_CL",
           "VEHC_TOWED_FROM_SCENE_CL", "CNTY_NAME", "FMCSA_RPTBL_CL", "FMCSA_RPTBL", "HIT_RUN_DESCR",
           "SCHL_BUS_RELD_DESCR", "SPEED_LIMIT", "SPEED_LIM", "STREETNAME", "FROMSTREETNAME", "TOSTREETNAME",
           "CITY", "ALC_SUSPD_TYPE_DESCR", "DRIVER_AGE", "DRVR_CNTRB_CIRC_DESCR", "DRUG_SUSPD_TYPE_DESCR",
           "EMERGENCY_USE_DESC", "MAX_INJR_SVRTY_VL", "MOST_HRMF_EVENT", "TOTAL_OCCPT_IN_VEHC",
           "VEHC_MANR_ACT_DESCR", "VEHC_CONFG_DESCR", "VEHC_MOST_DMGD_AREA", "VEHC_TOWED_FROM_SCENE",
           "VEHICLE_MAKE_DESCR", "VEHICLE_MODEL_DESCR", "VEHICLE_VIN", "DRIVER_VIOLATION_CL"]

LATEST = "massachusetts_crash_vehicle_latest.csv"


def _g(u):
    r = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=120, context=CTX).read())


def _fetch(layer):
    base = SVC + "/" + str(layer); rows = []; off = 0
    while True:
        d = _g(base + "/query?" + urllib.parse.urlencode(
            {"where": WHERE, "outFields": "*", "f": "json", "resultOffset": off,
             "resultRecordCount": 2000, "returnGeometry": "false", "orderByFields": "CRASH_DATETIME DESC"}))
        fe = d.get("features", [])
        if not fe:
            break
        rows += [f.get("attributes", {}) for f in fe]; off += len(fe)
        if len(fe) < 2000 and not d.get("exceededTransferLimit"):
            break
    return rows


def export():
    crash = _fetch(0)
    veh = _fetch(1)
    cmap = {r.get("CRASH_NUMB"): r for r in crash}
    merged = [{**cmap.get(v.get("CRASH_NUMB"), {}), **v} for v in veh]   # one row per vehicle, VIN included
    os.makedirs(OUTDIR, exist_ok=True)
    latest = os.path.join(OUTDIR, LATEST)
    dated = os.path.join(OUTDIR, "massachusetts_crash_vehicle_%s.csv" % time.strftime("%Y%m%d", time.gmtime()))
    for path in (latest, dated):
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(COLUMNS)
            for m in merged:
                w.writerow([m.get(c) for c in COLUMNS])
    print("[ma_csv] from=%s crashes=%d rows=%d -> %s" % (MA_FROM, len(crash), len(merged), latest))
    return len(merged)


if __name__ == "__main__":
    export()
