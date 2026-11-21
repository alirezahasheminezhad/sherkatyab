"""One-off probe: look at foodkeys.com public pages (robots.txt respected, slow, identified) and print their structure to the log.
    python foodkeys_probe.py / /some/path ...      (paths relative to https://www.foodkeys.com)
"""
import collections, re, sys, time, urllib.request
from urllib.robotparser import RobotFileParser

BASE = "https://www.foodkeys.com"
UA = "sherkatyab-research/1.0 (+https://github.com/alirezahasheminezhad/sherkatyab)"


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"}), timeout=40) as r:
        return r.status, r.geturl(), r.read().decode("utf-8", "replace")


def main(paths):
    rp = RobotFileParser()
    try:
        _, _, robots = get(BASE + "/robots.txt")
        rp.parse(robots.splitlines())
        print("=== robots.txt ===\n" + robots[:2500])
    except Exception as e:  # no robots.txt readable: stay conservative, fetch nothing
        sys.exit(f"robots.txt unreadable ({e}); not fetching anything")
    delay = rp.crawl_delay(UA) or 2
    for path in paths:
        url = BASE + path
        print(f"\n=== {url} ===")
        if not rp.can_fetch(UA, url):
            print("DISALLOWED by robots.txt, skipped")
            continue
        time.sleep(max(delay, 2))
        try:
            st, final, html = get(url)
        except Exception as e:
            print("fetch failed:", e)
            continue
        print(f"status {st}, final {final}, {len(html)} chars")
        print("title:", re.findall(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)[:1])
        print("forms:", [f[:300] for f in re.findall(r"<form\b[^>]*>", html, re.I)][:5])
        hrefs = re.findall(r'href="([^"#]+)"', html)
        groups = collections.defaultdict(list)
        for h in hrefs:
            if h.startswith("/") or "foodkeys.com" in h:
                groups[re.sub(r"https?://[^/]+", "", h).strip("/").split("/")[0][:30]].append(h)
        print("link groups:", {k: (len(v), v[:8]) for k, v in sorted(groups.items(), key=lambda x: -len(x[1]))[:25]})
        seen = {}
        for h, t in re.findall(r'<a [^>]*href="([^"#]+)"[^>]*>(.*?)</a>', html, re.S | re.I):
            if h.startswith("/view") or h.startswith("/food") or h.startswith("/agri"):
                seen.setdefault(h, re.sub(r"<[^>]+>|\s+", " ", t).strip()[:60])
        print("links:", [f"{h} = {t}" for h, t in list(seen.items())[:160]])
        print("headings:", [re.sub(r"<[^>]+>|\s+", " ", h).strip()[:80] for h in re.findall(r"<h[1-3][^>]*>(.*?)</h[1-3]>", html, re.S | re.I)][:25])
        print("json-ld:", [j[:600] for j in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)][:2])
        body = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S | re.I)
        print("text:", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))[:1800])
        print("html head (body part):", re.sub(r"\s+", " ", body[body.lower().find("<body"):][:2500]))


if __name__ == "__main__":
    main(sys.argv[1:] or ["/"])
