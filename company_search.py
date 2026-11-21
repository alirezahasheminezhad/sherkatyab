"""Company search on Rasmio (via rasmio-mcp) with a persistent cache in db/ (kept on the `db` branch).

usage: python company_search.py <keyword> [--pages N] [--refresh]
db/companies.json  {national_id: {hit fields, "profile": {...}|absent, "kw": [keywords]}}
db/searches.json   {slug: {"keyword", "at", "total", "ids": [ranked national ids]}}
A repeated keyword is served from the cache (no network) unless --refresh or the cache is older than TTL_DAYS.
"""
import asyncio, json, os, re, sys, time

DB = "db"
TTL_DAYS = 7
PROFILES_PER_RUN = 5  # Rasmio allows ~5 anonymous profile views per IP per ~4 days; the cache fills up across runs
PAGE = 60


def load(name):
    try:
        return json.load(open(f"{DB}/{name}.json", encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(name, obj):
    os.makedirs(DB, exist_ok=True)
    json.dump(obj, open(f"{DB}/{name}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0, sort_keys=True)


_DIGITS = str.maketrans("".join(chr(0x6F0 + i) for i in range(10)) + "".join(chr(0x660 + i) for i in range(10)), "0123456789" * 2)


def slug(kw):
    kw = kw.translate(_DIGITS).replace("\u200c", " ").replace("ي", "ی").replace("ك", "ک")
    return re.sub(r"\s+", " ", kw).strip()


def queries(kw):
    """Rasmio matches loosely (an extra word like «قلم» pulls in unrelated companies), so search the core product
    word(s) without grade modifiers, plus each Persian synonym from synonyms.json (max 4 searches)."""
    try:
        syn = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "synonyms.json"), encoding="utf-8"))
    except (OSError, ValueError):
        syn = {}
    mods = {slug(m) for m in syn.get("modifiers", [])}
    toks = kw.split()
    core = " ".join(t for t in toks if t not in mods) or kw
    out = [core]
    for g in syn.get("groups", []):
        g = [slug(x) for x in g]
        if core in g or (len(toks) == 1 and kw in g):
            out += [x for x in g if x not in out and re.search("[\u0600-\u06ff]", x)]  # Rasmio is Persian-only
    return out[:4]


def score(c, rank, n):
    """Bigger = bigger/more official. Base is Rasmio's own highest-capital order; verified + licenses add to it."""
    return round((n - rank) / max(n, 1) * 60 + (20 if c.get("verified_by_company") else 0)
                 + min(c.get("license_count") or 0, 10) * 2 + (10 if c.get("profile") else 0), 1)


async def run(kw, pages, refresh, search, company, now=None):
    now = now or time.time()
    kw = slug(kw)
    companies, searches = load("companies"), load("searches")
    s = searches.get(kw)
    fresh = s and now - s["at"] < TTL_DAYS * 86400 and not refresh
    if not fresh:
        ids, total, qs = [], 0, queries(kw)
        for q in qs:
            for p in range(1, pages + 1):
                r = await search(query=q, status="active", sort="highest_capital", page=p, page_size=PAGE)
                total += r.get("total", 0) if p == 1 else 0
                for h in r.get("results", []):
                    cid = str(h["company_id"])
                    old = companies.get(cid, {})
                    companies[cid] = {**old, **h, "kw": sorted(set(old.get("kw", [])) | {kw})}
                    if cid not in ids:
                        ids.append(cid)
                if p >= r.get("pages", 0):
                    break
        if not ids:
            raise SystemExit(f"no result for {kw!r}; nothing saved")
        searches[kw] = {"keyword": kw, "at": now, "total": total, "ids": ids, "queries": qs}
    ids = searches[kw]["ids"]
    # profiles (address, capital, board, shareholders, ...) for the best-ranked companies we do not have yet.
    # rs_company parses the whole page in one fetch, so sections=None keeps every section at no extra request cost.
    pos = {cid: i for i, cid in enumerate(ids)}
    ranked = sorted(ids, key=lambda i: -score(companies[i], pos[i], len(ids)))
    got = 0
    for cid in [i for i in ranked if "profile" not in companies[i]][:PROFILES_PER_RUN]:
        try:
            companies[cid]["profile"] = await company(company_id=cid, sections=None, max_rows=8)
            got += 1
        except Exception as e:  # limit reached or site error: keep what we have, fill the rest next run
            print(f"profile stopped at {cid}: {e}")
            break
    searches[kw]["ranked"] = sorted(ids, key=lambda i: -score(companies[i], pos[i], len(ids)))
    save("companies", companies)
    save("searches", searches)
    print(f"{kw}: {len(ids)} companies, {got} new profiles, cached={'yes' if fresh else 'no'}")
    return searches[kw]


if __name__ == "__main__":
    from rasmio_mcp.company import rs_company
    from rasmio_mcp.search import rs_search_companies
    a = sys.argv[1:]
    if not a or not a[0].strip():
        raise SystemExit("keyword required")
    pg = int(a[a.index("--pages") + 1]) if "--pages" in a else 3
    asyncio.run(run(a[0], max(1, min(pg, 10)), "--refresh" in a, rs_search_companies, rs_company))
