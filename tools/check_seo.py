"""Checks the website against the on-page SEO list; exits non-zero on any failure.

    python3 -I tools/check_seo.py website

Breadcrumbs (visible + structured, same trail) · robots.txt · domain consistency · structured data (valid JSON-LD)
· canonical · meta description · custom 404 (+ hosting rules) · organization / local business · sitemap.xml
· favicon · internal links (none broken) · unique titles · one unique H1 per page, no duplicate headings ·
JS size · llms.txt · alt text · share image present.
"""
import glob, html, json, os, re, sys
from collections import Counter

root = sys.argv[1]
fails, notes = [], []


def fail(msg):
    fails.append(msg)


pages = sorted(glob.glob("**/*.html", root_dir=root, recursive=True))
index = open(os.path.join(root, "index.html"), encoding="utf-8").read()
ORIGIN = re.search(r'<link rel="canonical" href="(https?://[^/"]+)/', index).group(1)
SPECIAL = {"offline.html"}                      # service-worker fallback: never indexed, never linked
ERR = {"404.html", "fa/404.html"}
titles, descs, h1s = Counter(), Counter(), Counter()

for p in pages:
    s = open(os.path.join(root, p), encoding="utf-8").read()
    if p in SPECIAL:
        continue
    t = re.search(r"<title>(.*?)</title>", s, re.S)
    d = re.search(r'<meta name="description" content="([^"]+)"', s)
    c = re.search(r'<link rel="canonical" href="([^"]+)"', s)
    if not t: fail(f"{p}: no <title>")
    else: titles[t.group(1).strip()] += 1
    if not d: fail(f"{p}: no meta description")
    else: descs[d.group(1)] += 1
    if not c or not c.group(1).startswith(ORIGIN): fail(f"{p}: canonical missing or on another origin")
    h1 = [re.sub(r"<[^>]+>", "", x).strip() for x in re.findall(r"<h1[^>]*>(.*?)</h1>", s, re.S)]
    if len(h1) != 1: fail(f"{p}: {len(h1)} <h1> elements")
    for x in h1: h1s[x] += 1
    main = s.split("<footer")[0]
    hs = [re.sub(r"<[^>]+>", "", x).strip() for x in re.findall(r"<h[2-4][^>]*>(.*?)</h[2-4]>", main, re.S)]
    dup = [k for k, v in Counter(hs).items() if v > 1]
    if dup: fail(f"{p}: duplicate headings {dup}")
    for img in re.findall(r"<img\b[^>]*>", s):
        if "alt=" not in img: fail(f"{p}: <img> without alt: {img[:80]}")
    if not re.search(r'<link rel="icon"', s): fail(f"{p}: no favicon link")
    og = re.search(r'<meta property="og:image" content="([^"]+)"', s)
    if not og: fail(f"{p}: no og:image")
    elif not os.path.exists(os.path.join(root, og.group(1)[len(ORIGIN) + 1:])): fail(f"{p}: og:image file missing")
    if 'og:image:alt' not in s: fail(f"{p}: no og:image:alt")
    for blk in re.findall(r'<script type="application/ld\+json">(.*?)</script>', s, re.S):
        try:
            json.loads(blk)
        except ValueError:
            fail(f"{p}: invalid JSON-LD")
    # breadcrumbs: visible trail on inner pages, equal to the structured one
    if p not in ("index.html", "fa/index.html"):
        nav = re.search(r'<nav class="crumbs"[^>]*><ol>(.*?)</ol></nav>', s, re.S)
        if not nav: fail(f"{p}: no visible breadcrumb")
        elif p not in ERR:
            seen = [html.unescape(re.sub(r"<[^>]+>", "", x)).strip() for x in re.findall(r"<li>(.*?)</li>", nav.group(1))]
            m = re.search(r'"BreadcrumbList", "itemListElement": (\[.*?\])\}', s)
            data = [i["name"] for i in json.loads(m.group(1))] if m else []
            if seen != data: fail(f"{p}: visible breadcrumb {seen} != structured {data}")
    # internal links resolve
    for href in re.findall(r'<a [^>]*href="([^"#?]+)', s):
        if re.match(r"(https?:|mailto:|tel:|/dashboard/)", href): continue
        target = os.path.normpath(os.path.join(os.path.dirname(os.path.join(root, p)), href.lstrip("/") if not href.startswith("/") else os.path.join(os.path.relpath(root, os.path.dirname(os.path.join(root, p))), href.lstrip("/"))))
        if href.startswith("/"):
            target = os.path.join(root, href.lstrip("/"))
        if href.endswith("/"): target = os.path.join(target, "index.html")
        if not os.path.exists(target): fail(f"{p}: broken internal link {href}")
    if p in ERR and "noindex" not in s: fail(f"{p}: error page is indexable")

for name, ctr in (("title", titles), ("description", descs), ("h1", h1s)):
    d = [k for k, v in ctr.items() if v > 1]
    if d: fail(f"duplicate {name}: {d}")

robots = open(os.path.join(root, "robots.txt"), encoding="utf-8").read()
if f"Sitemap: {ORIGIN}/sitemap.xml" not in robots: fail("robots.txt: Sitemap line missing or on another origin")
sm = open(os.path.join(root, "sitemap.xml"), encoding="utf-8").read()
locs = set(re.findall(r"<loc>([^<]+)</loc>", sm))
indexable = {f"{ORIGIN}/" + ("" if p == "index.html" else "fa/" if p == "fa/index.html" else p)
             for p in pages if p not in SPECIAL | ERR}
if locs != indexable: fail(f"sitemap.xml differs from indexable pages: missing {sorted(indexable - locs)}, extra {sorted(locs - indexable)}")
for f in ("llms.txt", "llms-full.txt", "favicon.ico", "_redirects", ".htaccess", "_headers"):
    if not os.path.exists(os.path.join(root, f)): fail(f"{f} missing")
llms = open(os.path.join(root, "llms.txt"), encoding="utf-8").read()
if not llms.startswith("# ") or "\n> " not in llms: fail("llms.txt: not in llmstxt.org form (H1 + summary)")
js = os.path.getsize(os.path.join(root, "assets/js/site.min.js"))
if js > 120_000: fail(f"site.min.js is {js:,} bytes")
if 'site.min.js' not in index: fail("pages do not load the minified script")
other = [p for p in pages if ORIGIN not in open(os.path.join(root, p), encoding="utf-8").read() and p not in SPECIAL]
if other: fail(f"pages without the site origin: {other}")
if ORIGIN.endswith(".example"): notes.append(f"domain is still the placeholder {ORIGIN} — run tools/configure_site.py --domain")
if '"#localbusiness"' not in index and "#localbusiness" not in index: notes.append("no LocalBusiness data yet — run tools/configure_site.py --business (needs the real address and phone)")

print(f"checked {len(pages)} pages, {len(locs)} sitemap URLs, site.min.js {js:,} B")
for n in notes: print("NOTE:", n)
for f in fails: print("FAIL:", f)
print("RESULT:", "PASS" if not fails else f"{len(fails)} failure(s)")
sys.exit(1 if fails else 0)
