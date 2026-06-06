import urllib.request, urllib.parse, json, ssl, datetime, os, sys

BASE = os.environ.get("NR_BASE", "https://oaklandca.nextrequest.com")
SEARCH_TERM = os.environ.get("NR_SEARCH", "redacted")          # monitor the 'redacted' stream (set "" for all docs)
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
CLASSIFIABLE = {"pdf"}                                          # only classify PDFs (skip video/audio/office)
MAX_DL = int(os.environ.get("NR_MAX_BYTES", str(30 * 1024 * 1024)))   # skip files > 30MB (videos)


def _get(url, accept="application/json", to=90):
    r = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": accept,
                                             "X-Requested-With": "XMLHttpRequest"})
    return urllib.request.urlopen(r, timeout=to, context=CTX)


def _date(s):
    try:
        return datetime.datetime.strptime(s, "%m/%d/%Y").date()
    except Exception:
        return None


def list_page(page, term=None):
    params = {"page": page, "sort_field": "created_at", "sort_order": "desc"}
    t = SEARCH_TERM if term is None else term
    if t:
        params["search_term"] = t                              # monitor the 'redacted' result stream
    u = BASE + "/client/documents?" + urllib.parse.urlencode(params)
    return json.loads(_get(u).read())


def iter_recent(days=15, hard_max_pages=4000):
    """Yield documents uploaded within the last `days`, newest first."""
    cutoff = datetime.date.today() - datetime.timedelta(days=days)
    page = 1
    while page <= hard_max_pages:
        docs = list_page(page).get("documents", [])
        if not docs:
            break
        for doc in docs:
            dt = _date(doc.get("created_at"))
            if dt and dt < cutoff:
                return
            yield doc
        page += 1
    if page > hard_max_pages:
        sys.stderr.write("[nextrequest] WARNING: hit %d-page cap (~%d docs) before reaching the %d-day "
                         "cutoff; window truncated. Raise hard_max_pages.\n"
                         % (hard_max_pages, hard_max_pages * 50, days))


def download(doc_id):
    resp = _get(BASE + "/documents/%s/download" % doc_id, accept="*/*", to=180)
    cl = resp.headers.get("content-length")
    if cl and int(cl) > MAX_DL:
        return None
    data = resp.read(MAX_DL + 1)
    return None if len(data) > MAX_DL else data
