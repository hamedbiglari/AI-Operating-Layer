"""Visible breadcrumbs generated from each page's BreadcrumbList JSON-LD, so the two can never disagree.
Usage: python3 -I crumbs.py <website-root>"""
import glob, html, json, os, re, sys

root = sys.argv[1]
# The site's origin is read from the home page's canonical link, so this keeps working after configure_site.py
# has moved the site to its real domain.
SITE = re.search(r'<link rel="canonical" href="(https?://[^/"]+/)',
                 open(os.path.join(root, "index.html"), encoding="utf-8").read()).group(1)
NOT_FOUND = {"en": "Page not found", "fa": "صفحه پیدا نشد"}
HOME = {"en": ("Home", "index.html"), "fa": ("خانه", "index.html")}
LABEL = {"en": "Breadcrumb", "fa": "مسیر صفحه"}


def rel(url: str, page: str) -> str:
    path = url[len(SITE):] if url.startswith(SITE) else url
    if path in ("", "fa/"):
        path += "index.html"
    return os.path.relpath(path, os.path.dirname(page) or ".").replace(os.sep, "/")


def nav(items, lang):
    lis = []
    for i, (name, href) in enumerate(items):
        last = i == len(items) - 1
        inner = (f'<span aria-current="page">{html.escape(name)}</span>' if last
                 else f'<a href="{html.escape(href)}">{html.escape(name)}</a>')
        lis.append(f"<li>{inner}</li>")
    return f'<nav class="crumbs" aria-label="{LABEL[lang]}"><ol>{"".join(lis)}</ol></nav>'


done = []
for page in sorted(glob.glob("**/*.html", root_dir=root, recursive=True)):
    if page in ("index.html", "fa/index.html", "offline.html"):
        continue                                   # home pages are the root of every trail
    p = os.path.join(root, page)
    s = open(p, encoding="utf-8").read()
    lang = "fa" if page.startswith("fa/") else "en"
    is404 = page.endswith("404.html")
    m = re.search(r'<script type="application/ld\+json">(\{[^<]*"BreadcrumbList".*?)</script>', s, re.S)
    if is404:
        # A noindex error page gets a visible trail but no breadcrumb structured data.
        if m:
            s = s.replace(m.group(0) + "\n", "").replace(m.group(0), "")
        items = [(HOME[lang][0], os.path.relpath(("fa/" if lang == "fa" else "") + "index.html",
                                                 os.path.dirname(page) or ".").replace(os.sep, "/")),
                 (NOT_FOUND[lang], "")]
    else:
        data = json.loads(m.group(1))
        items = [(it["name"], rel(it["item"], page)) for it in data["itemListElement"]]
    trail = nav(items, lang)
    s = re.sub(r'<nav class="crumbs"[^>]*>.*?</nav>\s*', "", s, flags=re.S)        # replace any older trail
    anchor = (re.search(r'(<(?:section|header) class="page-hero">\s*<div class="shell[^"]*">\s*)', s)
              or re.search(r'(<main id="main">\s*<section class="section"><div class="shell[^>]*>\s*)', s))
    if not anchor:
        print("NO ANCHOR", page); continue
    s = s[:anchor.end()] + trail + s[anchor.end():]
    open(p, "w", encoding="utf-8").write(s)
    done.append((page, " › ".join(n for n, _ in items)))
for d in done:
    print(*d)
