import sys, os, time
import store, nextrequest as nr, classify

NO_AI = os.environ.get("NO_AI") == "1" or not os.environ.get("OPENAI_API_KEY")


def meta_of(doc):
    did = doc.get("id")
    return {"doc_id": did, "title_file": doc.get("title"), "created_at": doc.get("created_at"),
            "doc_date": doc.get("doc_date"), "folder_name": doc.get("folder_name"),
            "file_extension": (doc.get("file_extension") or "").lower(),
            "redacted_at": doc.get("redacted_at"), "document_path": doc.get("document_path"),
            "download_url": nr.BASE + "/documents/%s/download" % did, "status": "new",
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def harvest(days):
    store.init()
    n = 0
    for doc in nr.iter_recent(days=days):
        if store.add_doc(meta_of(doc)):
            n += 1
    print("[harvest] new docs added:", n)
    return n


def process(limit=None):
    rows = store.pending(nr.CLASSIFIABLE)
    if limit:
        rows = rows[:limit]
    print("[process] classifiable PDFs pending:", len(rows), "| NO_AI =", NO_AI)
    for r in rows:
        did = r["doc_id"]
        try:
            pdf = nr.download(did)
        except Exception as e:
            store.update(did, status="error", ai_reason=("dl:" + str(e))[:200]); continue
        if not pdf:
            store.update(did, status="skipped", ai_reason="too large / no file"); continue
        if NO_AI:
            store.update(did, status="fetched"); continue
        v, reason, page = classify.classify(pdf)
        upd = {"status": "done", "is_crash": v, "ai_reason": reason[:300], "pages_used": str(page),
               "classified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        if v == "yes":
            try:
                fields = classify.extract(pdf)
                for k in store.EXCEL_FIELDS:
                    val = fields.get(k)
                    upd[k] = (str(val) if val not in (None, "") else None)
            except Exception as e:
                upd["ai_reason"] = (reason + " | extract_err:" + str(e))[:300]
        store.update(did, **upd)
    print("[process] done:", dict(store.counts()))


def monitor():
    """Turnkey: seed the backfill window once (if DB empty), then poll forever."""
    store.init()
    if store.counts()["total"] == 0:
        days = int(os.environ.get("SEED_DAYS", "15"))
        print("[monitor] empty DB -> seeding last %d days of the '%s' stream" % (days, nr.SEARCH_TERM))
        harvest(days); process()
    interval = int(os.environ.get("POLL_SECONDS", "7200"))   # default every 2 hours
    print("[monitor] poll loop every %d s (Ctrl-C to stop)" % interval)
    while True:
        try:
            harvest(2); process()
        except Exception as e:
            print("[monitor] cycle error:", str(e)[:200])
        time.sleep(interval)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "seed"
    if cmd == "seed":
        harvest(int(sys.argv[2]) if len(sys.argv) > 2 else 15); process()
    elif cmd == "poll":
        harvest(2); process()
    elif cmd == "monitor":
        monitor()
    elif cmd == "harvest":
        harvest(int(sys.argv[2]) if len(sys.argv) > 2 else 15)
    elif cmd == "process":
        store.init(); process(int(sys.argv[2]) if len(sys.argv) > 2 else None)
    else:
        print("usage: run.py monitor | seed [days] | poll | harvest [days] | process [limit]")


if __name__ == "__main__":
    main()
