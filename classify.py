import os, json, base64, subprocess, tempfile, urllib.request
import store

OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")           # cheap vision-capable; override via env
API = os.environ.get("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions")


def _tmp(pdf):
    f = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    f.write(pdf); f.close()
    return f.name


def page_text(pdf, page):
    p = _tmp(pdf)
    try:
        out = subprocess.run(["pdftotext", "-f", str(page), "-l", str(page), p, "-"],
                             capture_output=True, timeout=60)
        return out.stdout.decode("utf-8", "replace")
    finally:
        try: os.unlink(p)
        except Exception: pass


def page_png(pdf, page, dpi=150):
    p = _tmp(pdf); base = p[:-4]
    try:
        subprocess.run(["pdftoppm", "-png", "-f", str(page), "-l", str(page), "-r", str(dpi),
                        "-singlefile", p, base], timeout=120, check=True)
        with open(base + ".png", "rb") as g:
            return g.read()
    finally:
        for x in (p, base + ".png"):
            try: os.unlink(x)
            except Exception: pass


def _call(content, schema=None, to=180):
    # strict Structured Outputs when a schema is given (guarantees the keys); else plain json_object.
    # No temperature set -> compatible with both standard and reasoning models.
    rf = ({"type": "json_schema", "json_schema": {"name": "out", "strict": True, "schema": schema}}
          if schema else {"type": "json_object"})
    body = json.dumps({"model": MODEL, "response_format": rf,
                       "messages": [{"role": "user", "content": content}]}).encode()
    r = urllib.request.Request(API, data=body,
                               headers={"Authorization": "Bearer " + (OPENAI_KEY or ""),
                                        "Content-Type": "application/json"})
    raw = json.loads(urllib.request.urlopen(r, timeout=to).read())
    return json.loads(raw["choices"][0]["message"]["content"])


def _content(prompt, pdf, page):
    txt = page_text(pdf, page)
    if len(txt.strip()) > 200:                                 # has text layer -> cheap TEXT classify
        return [{"type": "text", "text": prompt + "\n\n--- PAGE %d TEXT ---\n" % page + txt[:6000]}]
    b64 = base64.b64encode(page_png(pdf, page)).decode()       # scanned/flattened -> low-detail IMAGE
    return [{"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64, "detail": "low"}}]


CLS = ('Screening a redacted public-records PDF page. Is it a MOTOR-VEHICLE TRAFFIC CRASH / COLLISION '
       'report (police traffic collision report / CHP 555 / crash report)? '
       'Reply ONLY JSON: {"is_crash":"yes|no|uncertain","reason":"<=12 words"}.')


def classify(pdf):
    """Page 1 first; escalate to page 2 only if undecided."""
    for page in (1, 2):
        try:
            res = _call(_content(CLS, pdf, page))
        except Exception as e:
            return "error", str(e)[:150], page
        v = str(res.get("is_crash", "")).lower().strip()
        if v in ("yes", "no"):
            return v, res.get("reason", "")[:200], page
    return "uncertain", "undecided after pages 1-2", 2


EXTRACT_SCHEMA = {"type": "object", "additionalProperties": False,
                  "properties": {f: {"type": ["string", "null"]} for f in store.EXCEL_FIELDS},
                  "required": list(store.EXCEL_FIELDS)}


def _xprompt():
    lines = ["Extract these fields from this traffic-crash report page. "
             "Use null when redacted or absent. Keys:"]
    for f in store.EXCEL_FIELDS:
        lines.append('  "%s"  (%s)' % (f, store.EXCEL_LABELS[f]))
    return "\n".join(lines)


def extract(pdf):
    return _call(_content(_xprompt(), pdf, 1), schema=EXTRACT_SCHEMA)
