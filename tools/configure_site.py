"""Point the website at its real domain and (optionally) publish LocalBusiness structured data.

    python3 -I tools/configure_site.py website --domain https://www.your-domain.com
    python3 -I tools/configure_site.py website --business tools/business.json
    python3 -I tools/configure_site.py website --domain https://www.your-domain.com --business tools/business.json

--domain    Replaces the current origin everywhere it is written: canonical and hreflang links, Open Graph and
            Twitter tags, JSON-LD, sitemap.xml, robots.txt, llms.txt / llms-full.txt. Pages themselves use
            relative links, so nothing else changes. Connecting the domain (DNS + TLS) is done at the host;
            see "Connect a custom domain" in website/README.md.
--business  Adds a LocalBusiness node (or a subtype such as ProfessionalService) to the home and contact pages in
            both languages, linked to the one Organization. Every required field must be real: the script refuses
            the placeholder values of business.example.json, because structured data that describes a business
            that does not exist at that address is a false statement to search engines.

Always (idempotent): the English and Persian pages describe ONE organization (@id <origin>/#org), and its
address carries what the site already states publicly — the city and country in the footer.
"""
import argparse, glob, json, os, re, sys
from urllib.parse import urlparse

ap = argparse.ArgumentParser()
ap.add_argument("root")
ap.add_argument("--domain")
ap.add_argument("--business")
ap.add_argument("--email", help="public contact address; default hello@<your domain without www>")
a = ap.parse_args()
root = a.root
LD = re.compile(r'(<script type="application/ld\+json">)(.*?)(</script>)', re.S)


def origin_now() -> str:
    s = open(os.path.join(root, "index.html"), encoding="utf-8").read()
    return re.search(r'<link rel="canonical" href="(https?://[^/"]+)/', s).group(1)


def text_files():
    pats = ["**/*.html", "sitemap.xml", "robots.txt", "llms.txt", "llms-full.txt", "manifest.webmanifest",
            "assets/js/site.js", "assets/js/site.min.js"]
    for p in pats:
        yield from glob.glob(os.path.join(root, p), recursive=True)


# ------------------------------------------------------------------------------------------------ domain
if a.domain:
    u = urlparse(a.domain.strip())
    if u.scheme != "https" or not u.hostname or u.path not in ("", "/") or u.query or u.fragment:
        sys.exit("--domain must be an https origin with no path, e.g. https://www.example.com")
    if u.hostname.endswith(".example") or u.hostname in ("example.com", "www.example.com"):
        sys.exit("--domain is still an example domain")
    new = f"https://{u.netloc}"
    old = origin_now()
    old_host = urlparse(old).hostname
    apex = u.hostname[4:] if u.hostname.startswith("www.") else u.hostname
    email = a.email or f"hello@{apex}"
    if not re.fullmatch(r"[^@\s<>]+@[^@\s<>]+\.[a-z]{2,}", email, re.I):
        sys.exit("--email is not a valid address")
    n = 0
    for f in text_files():
        s = open(f, encoding="utf-8").read()
        # the contact address on the old domain first (mailto links, the newsletter fallback), then the origin
        t = re.sub(r"[A-Za-z0-9._%+-]+@" + re.escape(old_host) + r"\b", email, s).replace(old, new)
        if t != s:
            open(f, "w", encoding="utf-8").write(t)
            n += 1
    print(f"domain: {old} -> {new}, contact {email}, in {n} files")

ORIGIN = origin_now()
ORG_ID = f"{ORIGIN}/#org"
CITY = {"addressLocality": "Mashhad", "addressCountry": "IR"}     # as stated in the footer of every page


def edit_jsonld(path, fn):
    s = open(path, encoding="utf-8").read()

    def repl(m):
        data = json.loads(m.group(2))
        data = fn(data)
        return m.group(1) + json.dumps(data, ensure_ascii=False) + m.group(3)

    t = LD.sub(repl, s)
    if t != s:
        open(path, "w", encoding="utf-8").write(t)


# --------------------------------------------------------------------------------- one organization entity
def unify(data):
    nodes = data.get("@graph") if isinstance(data, dict) and "@graph" in data else None
    if nodes is None:
        return data
    old_ids = set()
    for n in nodes:
        if n.get("@type") == "Organization":
            old_ids.add(n.get("@id"))
            n["@id"], n["url"] = ORG_ID, f"{ORIGIN}/"
            addr = n.get("address") or {"@type": "PostalAddress"}
            for k, v in CITY.items():
                addr.setdefault(k, v)
            n["address"] = addr

    def relink(o):
        if isinstance(o, dict):
            if set(o) == {"@id"} and o["@id"] in old_ids:
                o["@id"] = ORG_ID
            for v in o.values():
                relink(v)
        elif isinstance(o, list):
            for v in o:
                relink(v)

    relink(nodes)
    return data


for f in glob.glob(os.path.join(root, "**/*.html"), recursive=True):
    edit_jsonld(f, unify)
print(f"organization: one entity {ORG_ID}, address {CITY['addressLocality']}, {CITY['addressCountry']}")

# ------------------------------------------------------------------------------------------- local business
if a.business:
    b = json.load(open(a.business, encoding="utf-8"))
    need = ["name", "telephone", ("address", "streetAddress"), ("address", "addressLocality"), ("address", "addressCountry")]
    missing, fake = [], []
    for k in need:
        v = b.get(k) if isinstance(k, str) else (b.get(k[0]) or {}).get(k[1])
        if not v:
            missing.append(k if isinstance(k, str) else ".".join(k))
        elif re.search(r"<|>|example|placeholder|000-0000|xxx", str(v), re.I):
            fake.append(k if isinstance(k, str) else ".".join(k))
    if missing or fake:
        sys.exit(f"business.json not usable — missing: {missing or 'none'}; placeholder values: {fake or 'none'}")
    lb = {"@type": b.get("type", "LocalBusiness"), "@id": f"{ORIGIN}/#localbusiness", "name": b["name"],
          "url": f"{ORIGIN}/", "telephone": b["telephone"], "parentOrganization": {"@id": ORG_ID},
          "image": f"{ORIGIN}/assets/icons/og-image.jpg", "logo": f"{ORIGIN}/assets/icons/icon-512.png",
          "address": {"@type": "PostalAddress", **b["address"]}}
    for k in ("email", "priceRange", "areaServed", "sameAs", "description"):
        if b.get(k):
            lb[k] = b[k]
    if b.get("geo"):
        lb["geo"] = {"@type": "GeoCoordinates", "latitude": b["geo"]["latitude"], "longitude": b["geo"]["longitude"]}
    if b.get("openingHours"):
        lb["openingHoursSpecification"] = [
            {"@type": "OpeningHoursSpecification", "dayOfWeek": h["days"], "opens": h["opens"], "closes": h["closes"]}
            for h in b["openingHours"]]
    block = '<script type="application/ld+json">' + json.dumps({"@context": "https://schema.org", **lb},
                                                                ensure_ascii=False) + "</script>"
    n = 0
    for page in ("index.html", "fa/index.html", "contact.html", "fa/contact.html"):
        p = os.path.join(root, page)
        s = open(p, encoding="utf-8").read()
        s = re.sub(r'<script type="application/ld\+json">\{"@context": "https://schema.org", "@type": "[A-Za-z]+", '
                   r'"@id": "[^"]*#localbusiness".*?</script>\n?', "", s, flags=re.S)        # replace, never duplicate
        s = s.replace("</head>", block + "\n</head>", 1)
        open(p, "w", encoding="utf-8").write(s)
        n += 1
    print(f"local business: {lb['@type']} '{lb['name']}' added to {n} pages")

# ------------------------------------------------------------------------------------------- rebuild
# The domain and contact address are also inside the scripts and llms.txt, so the derived files and the cache
# version are rebuilt here; without it returning visitors could keep the old files from their service worker.
import subprocess

subprocess.run([sys.executable, "-I", os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_site.py"), root],
               check=True, stdout=subprocess.DEVNULL)
print("rebuilt: breadcrumbs, llms.txt, site.min.js (when Node is available), asset version")
