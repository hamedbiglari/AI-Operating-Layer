"""One command after any website change:  python3 -I tools/build_site.py website

  1. breadcrumbs   visible trail on every inner page, generated from its BreadcrumbList JSON-LD
  2. llms          website/llms.txt and llms-full.txt rebuilt from the pages
  3. minify        assets/js/site.js (readable source) -> assets/js/site.min.js, which the pages load
                   (needs Node:  npx --yes terser@5.36.0 ...; skipped with a warning when Node is absent)
  4. stamp         one content hash for all CSS/JS, written into every ?v= and the service-worker cache name,
                   so returning visitors never get a stale mix of old and new files
"""
import glob, hashlib, os, re, shutil, subprocess, sys

root = os.path.abspath(sys.argv[1])
here = os.path.dirname(os.path.abspath(__file__))


def run_py(script):
    subprocess.run([sys.executable, "-I", os.path.join(here, script), root], check=True)


run_py("crumbs.py")
run_py("build_llms.py")

src, out = os.path.join(root, "assets/js/site.js"), os.path.join(root, "assets/js/site.min.js")
terser = shutil.which("terser") or os.environ.get("TERSER")
cmd = [terser] if terser else (["npx", "--yes", "terser@5.36.0"] if shutil.which("npx") else None)
if cmd:
    subprocess.run(cmd + [src, "--ecma", "2020", "--compress", "passes=2", "--mangle", "--comments", "false", "-o", out], check=True)
    print(f"minify: site.js {os.path.getsize(src):,} B -> site.min.js {os.path.getsize(out):,} B")
else:
    print("minify: Node not found — site.min.js NOT rebuilt; run this again where Node is installed", file=sys.stderr)

files = [os.path.join(root, f) for f in ("assets/css/base.css", "assets/css/layout.css", "assets/css/landing.css",
                                         "assets/js/site.min.js", "assets/js/site-config.js")]
h = hashlib.sha256()
for f in files:
    h.update(open(f, "rb").read())
v = h.hexdigest()[:10]
n = 0
for f in glob.glob(os.path.join(root, "**/*.html"), recursive=True) + [os.path.join(root, "sw.js")]:
    s = open(f, encoding="utf-8").read()
    t = re.sub(r"assets/js/site\.js\?v=", "assets/js/site.min.js?v=", s)          # pages load the minified file
    t = re.sub(r"(\.(?:css|js)\?v=)[0-9a-f]{10}", lambda m: m.group(1) + v, t)
    t = re.sub(r"aiol-site-[0-9a-f]{10}", "aiol-site-" + v, t)
    if t != s:
        n += 1
        open(f, "w", encoding="utf-8").write(t)
print(f"stamp: v={v} written to {n} files")
