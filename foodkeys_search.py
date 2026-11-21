"""foodkeys.com collector (Persian food-industry directory): search a bank, read company pages, match against Rasmio.

usage: python foodkeys_search.py <keyword> [--banks a,b] [--pages N] [--details N] [--refresh] | --delete | --match
db/foodkeys.json          {"<bank>:<id>": {name, bank, id, url, summary, views, rating, detail?{fields,phones,emails,sites,products,about}, kw[]}}
db/foodkeys_searches.json {kw: {keyword, at, total, ids: [ranked keys], banks}}
db/matches.json           {"rasmio": {national_id: {key, conf, why[]}}, "known": {"r:<id>"|"f:<key>": known name}}
Politeness: robots.txt is read first, one request per DELAY seconds, identified User-Agent, only public pages. The
"click to see" contact data is already in the page HTML (the button only un-hides it); fields marked «محفوظ» are withheld by the site.
"""
import difflib, html as H, http.cookiejar, json, os, re, sys, time, urllib.parse, urllib.request, urllib.robotparser

DB, BASE, DELAY, TTL_DAYS = "db", "https://www.foodkeys.com", 2.0, 14
UA = "sherkatyab-research/1.0 (+https://github.com/alirezahasheminezhad/sherkatyab)"
BANKS = {"food_importers": "واردکنندگان و صادرکنندگان", "wholesale_trade": "پخش و عمده‌فروشان", "raw_materials": "مواد اولیه",
         "additives": "افزودنی‌ها و مواد اولیه", "producers": "تولیدکنندگان"}
GRID = "ctl00$MainContentPlaceHolder$GridView1"
_D = str.maketrans("".join(chr(0x6F0 + i) for i in range(10)) + "".join(chr(0x660 + i) for i in range(10)), "0123456789" * 2)


def load(name, d=None):
    try:
        return json.load(open(f"{DB}/{name}.json", encoding="utf-8"))
    except (OSError, ValueError):
        return {} if d is None else d


def save(name, obj):
    os.makedirs(DB, exist_ok=True)
    json.dump(obj, open(f"{DB}/{name}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0, sort_keys=True)


def norm(s):
    return re.sub(r"\s+", " ", (s or "").translate(_D).replace("‌", " ").replace("ي", "ی").replace("ك", "ک")).strip()


def text(frag):
    frag = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", frag)
    frag = re.sub(r"(?i)<(br|/p|/div|/tr|/li|/h\d|hr|/label|/td)[^>]*>", "\n", frag)
    return "\n".join(norm(H.unescape(re.sub(r"<[^>]+>", " ", l))) for l in frag.split("\n") if norm(H.unescape(re.sub(r"<[^>]+>", " ", l))))


# ───────── network (robots-aware, slow, cookie session for WebForms) ─────────
class Site:
    def __init__(self):
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.rp, self.last = urllib.robotparser.RobotFileParser(), 0.0
        try:
            self.rp.parse(self._raw(BASE + "/robots.txt").splitlines())
        except Exception:
            self.rp.disallow_all = True  # robots.txt unreadable: stay out

    def _raw(self, url, data=None):
        time.sleep(max(0, self.last + DELAY - time.time()))
        req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, "Accept-Language": "fa"})
        with self.op.open(req, timeout=45) as r:
            self.last = time.time()
            return r.read().decode("utf-8", "replace")

    def fetch(self, url, fields=None):
        if not self.rp.can_fetch(UA, url):
            raise PermissionError(f"robots.txt disallows {url}")
        for i in range(3):
            try:
                return self._raw(url, urllib.parse.urlencode(fields).encode() if fields else None)
            except Exception as e:
                if i == 2:
                    raise
                print(f"retry {url}: {e}")
                time.sleep(5 * (i + 1))


# ───────── parsing ─────────
def hidden(html):
    return {n: H.unescape(v) for n, v in re.findall(r'<input type="hidden" name="([^"]+)"[^>]*?value="([^"]*)"', html)}


def rows(html, bank):
    """Listing rows -> [{id, name, summary, views, rating}] (one per company card)."""
    out = []
    for blk in html.split('<div class="col-md-2 text-center"')[1:]:
        m = re.search(r'href="details\?id=(\d+)[^"]*"', blk)
        n = re.search(r"<h2>.*?<span[^>]*>(.*?)</span>", blk, re.S)
        if not m or not n:
            continue
        s = re.search(r'<span class="title" data-content="([^"]*)"', blk)
        v = re.search(r"(\d+)\s*بازدید", blk.translate(_D))
        r = re.search(r"rating_(\d)", blk)
        out.append({"id": m.group(1), "bank": bank, "name": norm(H.unescape(re.sub(r"<[^>]+>", "", n.group(1)))),
                    "summary": norm(H.unescape(s.group(1))) if s else "", "views": int(v.group(1)) if v else 0,
                    "rating": int(r.group(1)) if r else 0})
    return out


PH = re.compile(r"(?<!\d)(?:\+98|0098|98|0)?(9\d{9}|[1-8]\d{9,10})(?!\d)")


def detail(html):
    """Company page -> label/value fields from every tab + phones/emails/sites/products/about."""
    secs = {k: html[a:b] for k, a, b in _panes(html)}
    fields, withheld = {}, 0
    for k in ("nav-home", "nav-address", "nav-employee", "nav-Information"):
        for ln in text(secs.get(k, "")).split("\n"):
            m = re.match(r"^([^:：]{2,40}?)\s*[:：]\s*(.+)$", ln)
            if m:
                v = m.group(2).strip()
                if v == "محفوظ":
                    withheld += 1
                elif v:
                    fields.setdefault(m.group(1).strip(), v)
    body = text(re.sub(r"(?is)<head.*?</head>", "", html)).translate(_D)
    phones = sorted({("0" + x if x[0] != "0" else x) for x in PH.findall(" ".join(v for v in fields.values()).replace("-", "").replace(" ", ""))})
    emails = sorted(set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", body)))
    sites = sorted({u.lower().rstrip("/") for u in re.findall(r"(?:https?://)?(?:www\.)?[a-z0-9-]+\.(?:com|ir|org|net|co)\b(?:/[\w./-]*)?", body, re.I)
                    if "foodkeys" not in u.lower() and "enamad" not in u.lower()})
    hist = text(secs.get("nav-history", ""))
    return {"fields": fields, "phones": phones, "emails": emails, "sites": sites[:5], "withheld": withheld,
            "products": fields.get("عنوان محصولات", ""), "about": hist[:1200]}


def _panes(html):
    pos = [(m.group(1), m.start()) for m in re.finditer(r'id="(nav-[A-Za-z]+)"', html)]
    return [(k, a, pos[i + 1][1] if i + 1 < len(pos) else a + 40000) for i, (k, a) in enumerate(pos)]


# ───────── search one bank ─────────
def search_bank(site, bank, kw, pages):
    url = f"{BASE}/view/{bank}/"
    html = site.fetch(url)
    f = {**hidden(html), "ctl00$MainContentPlaceHolder$TextBox_Search": kw, "ctl00$MainContentPlaceHolder$Button_Search": "جستجو"}
    html, got = site.fetch(url, f), []
    for p in range(1, pages + 1):
        rs = rows(html, bank)
        got += rs
        if not rs or f"Page${p + 1}'" not in html or p == pages:
            break
        f = {**hidden(html), "ctl00$MainContentPlaceHolder$TextBox_Search": kw, "__EVENTTARGET": GRID, "__EVENTARGUMENT": f"Page${p + 1}"}
        html = site.fetch(url, f)
    return got


def run(kw, banks, pages, ndetails, refresh, site=None, now=None):
    now, kw = now or time.time(), norm(kw)
    db, ss = load("foodkeys"), load("foodkeys_searches")
    s = ss.get(kw)
    if not (s and now - s["at"] < TTL_DAYS * 86400 and not refresh and set(banks) <= set(s.get("banks", []))):
        site = site or Site()
        ids = []
        for b in banks:
            for r in search_bank(site, b, kw, pages):
                k = f"{b}:{r['id']}"
                old = db.get(k, {})
                db[k] = {**old, **r, "url": f"{BASE}/view/{b}/details?id={r['id']}", "kw": sorted(set(old.get("kw", [])) | {kw})}
                if k not in ids:
                    ids.append(k)
        if not ids:
            raise SystemExit(f"foodkeys: no result for {kw!r}; nothing saved")
        ss[kw] = {"keyword": kw, "at": now, "total": len(ids), "ids": ids, "banks": banks}
    site = site or Site()
    got = 0
    for k in [k for k in ss[kw]["ids"] if "detail" not in db[k]][:ndetails]:  # most-viewed first would need a sort; listing order is the site's own
        try:
            db[k]["detail"] = detail(site.fetch(db[k]["url"]))
            got += 1
        except Exception as e:
            print(f"detail stopped at {k}: {e}")
            break
    save("foodkeys", db)
    save("foodkeys_searches", ss)
    save("matches", match_all())
    print(f"{kw}: {len(ss[kw]['ids'])} companies, {got} new detail pages")
    for k in ss[kw]["ids"][:3]:
        print("sample", k, json.dumps(db[k], ensure_ascii=False)[:700])


def delete(kw):
    kw = norm(kw)
    ss = load("foodkeys_searches")
    if ss.pop(kw, None) is None:
        return False
    keep = {i for s in ss.values() for i in s["ids"]}
    save("foodkeys", {k: {**c, "kw": [x for x in c.get("kw", []) if x != kw]} for k, c in load("foodkeys").items() if k in keep})
    save("foodkeys_searches", ss)
    save("matches", match_all())
    return True


# ───────── Rasmio ↔ foodkeys matching ─────────
GENERIC = set("شرکت گروه بازرگانی تولیدی صنعتی صنایع سهامی خاص عام مسئولیت محدود تجارت تجاری تولید کارخانه کارخانجات توسعه و".split())


def core(name):
    return " ".join(t for t in norm(name).split() if t not in GENERIC and not re.fullmatch(r"[(){}\[\]\-–]+", t))


def name_sim(a, b):
    a, b = core(a), core(b)
    if not a or not b:
        return 0.0
    ta, tb = set(a.split()), set(b.split())
    jac = len(ta & tb) / len(ta | tb)
    return max(jac, difflib.SequenceMatcher(None, a, b).ratio() * 0.95)


def score_pair(r, f):
    """Confidence 0-99 that Rasmio company r and foodkeys company f are the same legal/trading entity, plus the reasons."""
    p, d = r.get("profile") or {}, f.get("detail") or {}
    sim, why = name_sim(r.get("name", ""), f.get("name", "")), []
    conf = sim * 70
    if sim >= 0.5:
        why.append(f"شباهت نام {round(sim * 100)}٪")
    elif sim < 0.34:
        return 0, []  # without any name resemblance, other weak hints are not enough
    ftxt = norm(" ".join([*(d.get("fields") or {}).values(), f.get("summary", "")]))
    ceo = norm(r.get("ceo") or p.get("ceo") or "")
    if ceo and len(ceo) > 5 and all(t in ftxt for t in ceo.split()[-2:]):
        conf += 20
        why.append("نام مدیرعامل در فوودکیز")
    ph = {x[-10:] for x in d.get("phones", [])} & {x[-10:] for x in PH.findall(norm(json.dumps(p, ensure_ascii=False)).replace("-", "").replace(" ", ""))}
    if ph:
        conf += 15
        why.append("تلفن مشترک")
    city = norm(p.get("address") or "").split("،")[0:2]
    if any(len(c.strip()) > 2 and c.strip() in ftxt for c in city if c.strip()):
        conf += 5
        why.append("شهر/نشانی همسو")
    return min(round(conf), 99), why


def match_all():
    rs, fk = load("companies"), load("foodkeys")
    out, known = {}, {}
    names = load_known()
    for cid, r in rs.items():
        best = max(((score_pair(r, f), k) for k, f in fk.items()), default=((0, []), None), key=lambda x: x[0][0])
        if best[0][0] >= 45:
            out[cid] = {"key": best[1], "conf": best[0][0], "why": best[0][1]}
        for n in names:
            if name_sim(n, r.get("name", "")) >= 0.8:
                known[f"r:{cid}"] = n
    for k, f in fk.items():
        for n in names:
            if name_sim(n, f.get("name", "")) >= 0.8:
                known[f"f:{k}"] = n
    return {"rasmio": out, "known": known}


def load_known():
    try:
        return json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "known.json"), encoding="utf-8"))["names"]
    except (OSError, ValueError, KeyError):
        return []


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--match" in a:
        save("matches", match_all())
        raise SystemExit(print("matches updated"))
    if not a or not a[0].strip():
        raise SystemExit("keyword required")
    if "--delete" in a:
        raise SystemExit(print(f"{a[0]}: deleted={delete(a[0])}"))
    opt = lambda n, d: int(a[a.index(n) + 1]) if n in a else d
    banks = [b for b in (a[a.index("--banks") + 1].split(",") if "--banks" in a else list(BANKS)) if b in BANKS]
    run(a[0], banks, max(1, min(opt("--pages", 2), 6)), max(0, min(opt("--details", 30), 80)), "--refresh" in a)
