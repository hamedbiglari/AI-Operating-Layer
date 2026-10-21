"""Builds website/llms.txt and website/llms-full.txt from the pages themselves (llmstxt.org format).

llms.txt      — what the site is, then every public page as  - [Title](URL): description
llms-full.txt — the same pages with their main text, for tools that want the content in one fetch.
Titles, descriptions and text are read from the HTML, so the files never drift from the site.
Usage:  python3 -I tools/build_llms.py website
"""
import glob, html, os, re, sys

root = sys.argv[1]
SITE = re.search(r'<link rel="canonical" href="(https?://[^/"]+/)', open(os.path.join(root, "index.html"), encoding="utf-8").read()).group(1)
SKIP = {"404.html", "fa/404.html", "offline.html"}
GROUPS = [("Product", ["index.html", "product.html", "pricing.html", "security.html"]),
          ("Articles", sorted(os.path.relpath(p, root) for p in glob.glob(os.path.join(root, "blog", "*.html"))) + ["blog.html"]),
          ("Company", ["about.html", "contact.html"]),
          ("Optional", ["privacy.html", "terms.html"])]


def meta(page):
    s = open(os.path.join(root, page), encoding="utf-8").read()
    title = html.unescape(re.search(r"<title>(.*?)</title>", s, re.S).group(1).strip())
    title = re.sub(r"\s*[|—]\s*AI Operating Layer$", "", title) or title
    desc = html.unescape(re.search(r'<meta name="description" content="([^"]*)"', s).group(1))
    canon = re.search(r'<link rel="canonical" href="([^"]*)"', s).group(1)
    main = re.search(r'<main id="main">(.*?)</main>', s, re.S).group(1)
    main = re.sub(r"<(script|style|svg|template|canvas|form|nav)\b.*?</\1>", " ", main, flags=re.S)
    main = re.sub(r"<(h[1-4])[^>]*>(.*?)</\1>", lambda m: "\n\n" + "#" * (int(m.group(1)[1]) + 1) + " " + m.group(2) + "\n", main, flags=re.S)
    main = re.sub(r"<li[^>]*>", "\n- ", main)
    main = re.sub(r"</(p|li|div|section|article|header|tr|dd|dt)>", "\n", main)
    text = html.unescape(re.sub(r"<[^>]+>", " ", main))
    text = "\n".join(re.sub(r"[ \t ]+", " ", ln).strip() for ln in text.splitlines())
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return title, desc, canon, text


def section(prefix, lang_note=None):
    out = []
    for name, pages in GROUPS:
        rows = []
        for pg in pages:
            pg = prefix + pg
            if pg in SKIP or not os.path.exists(os.path.join(root, pg)):
                continue
            t, d, c, _ = meta(pg)
            rows.append(f"- [{t}]({c}): {d}")
        if rows:
            out.append(f"## {name if not lang_note else lang_note + ' — ' + name}\n\n" + "\n".join(rows))
    return out


_, home_desc, _, _ = meta("index.html")
head = [
    "# AI Operating Layer",
    "",
    f"> {home_desc}",
    "",
    "AI Operating Layer turns a website's content, research and product data into structured, evidence-linked "
    "knowledge. Every claim stays linked to the source it came from, and the strength of that evidence is stated "
    "(direct, indirect, abstract-only, contradicted). Nothing on this site is a guarantee of ranking or AI visibility.",
    "",
    "The site is bilingual: English pages are at the root, Persian (fa-IR) translations under /fa/. Each page "
    "links to its translation with hreflang. Machine-readable data: sitemap.xml, JSON-LD on every page.",
    "",
]
body = section("") + section("fa/", "Persian (فارسی)")
open(os.path.join(root, "llms.txt"), "w", encoding="utf-8").write("\n".join(head) + "\n" + "\n\n".join(body) + "\n")

full = head[:]
for pg in [p for _, ps in GROUPS for p in ps] + ["fa/" + p for _, ps in GROUPS for p in ps]:
    if pg in SKIP or not os.path.exists(os.path.join(root, pg)):
        continue
    t, d, c, text = meta(pg)
    full += [f"\n---\n\n# {t}\n\nURL: {c}\n\n> {d}\n", text]
open(os.path.join(root, "llms-full.txt"), "w", encoding="utf-8").write("\n".join(full).strip() + "\n")
print("llms.txt", sum(1 for ln in open(os.path.join(root, "llms.txt"), encoding="utf-8") if ln.startswith("- [")), "links;",
      "llms-full.txt", os.path.getsize(os.path.join(root, "llms-full.txt")), "bytes")
