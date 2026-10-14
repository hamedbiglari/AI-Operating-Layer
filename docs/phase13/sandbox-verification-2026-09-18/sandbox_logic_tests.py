"""
Real, executed logic tests run in a network-isolated sandbox with NO
fastapi / sqlalchemy / pytest / postgres available.

This script does NOT mock the database or the web framework - it does
not touch any code that needs them. It only loads the two production
files that have zero framework dependency (app/models/enums.py and
app/services/actor_signatures.py) by bypassing the `app` package's
__init__ chain (which does import sqlalchemy-dependent siblings), and
then calls the real, unmodified `match()` function from
actor_signatures.py against real User-Agent strings, plus a static
parity check against the PHP mirror.

Every assertion below either passed or the script exits non-zero and
prints which one failed. Nothing here is simulated output.
"""
import importlib.util
import re
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "phase13_prev" / "cloud-core"


def load_standalone(mod_name: str, file_path: Path, pkg_name: str):
    spec = importlib.util.spec_from_file_location(mod_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


# --- bypass the `app` / `app.models` / `app.services` package __init__
# files (which import sqlalchemy) by registering empty stand-in packages,
# then loading the two target files directly from disk. No behaviour of
# either target file is altered.
for pkg in ("app", "app.models", "app.services"):
    if pkg not in sys.modules:
        m = types.ModuleType(pkg)
        m.__path__ = []  # mark as a package
        sys.modules[pkg] = m

enums = load_standalone("app.models.enums", ROOT / "app/models/enums.py", "app.models")
sys.modules["app.models"].enums = enums
actor_signatures = load_standalone(
    "app.services.actor_signatures", ROOT / "app/services/actor_signatures.py", "app.services"
)

match = actor_signatures.match
ActorType = enums.ActorType
AccessPurpose = enums.AccessPurpose

results = []


def check(label, cond):
    results.append((label, bool(cond)))
    print(("PASS " if cond else "FAIL "), label)


# 1) Real bot / agent classification against the production SIGNATURES table
ua_googlebot = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
ua_gptbot = "Mozilla/5.0 (compatible; GPTBot/1.2; +https://openai.com/gptbot)"
ua_chatgpt_user = "Mozilla/5.0 (compatible; ChatGPT-User/1.0; +https://openai.com/bot)"
ua_claude_user = "Mozilla/5.0 (compatible; Claude-User/1.0; +https://www.anthropic.com/claude-user)"
ua_claudebot = "Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)"
ua_claude_searchbot = "Mozilla/5.0 (compatible; Claude-SearchBot/1.0)"
ua_chrome_human = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
ua_unknown_bot = "SomeRandomResearchCrawler/3.1 (+http://example.com/bot)"

s = match(ua_googlebot)
check("Googlebot -> SEARCH_CRAWLER/SEARCH_INDEXING", s and s.actor_type == ActorType.SEARCH_CRAWLER and s.purpose == AccessPurpose.SEARCH_INDEXING)

s = match(ua_gptbot)
check("GPTBot -> AI_CRAWLER/TRAINING", s and s.actor_type == ActorType.AI_CRAWLER and s.purpose == AccessPurpose.TRAINING)

s = match(ua_chatgpt_user)
check("ChatGPT-User -> AI_USER_AGENT/ANSWERING", s and s.actor_type == ActorType.AI_USER_AGENT and s.purpose == AccessPurpose.ANSWERING)

s = match(ua_claude_user)
check("Claude-User -> AI_USER_AGENT/ANSWERING", s and s.actor_type == ActorType.AI_USER_AGENT and s.purpose == AccessPurpose.ANSWERING)

s = match(ua_claudebot)
check("ClaudeBot -> AI_CRAWLER/TRAINING", s and s.actor_type == ActorType.AI_CRAWLER and s.purpose == AccessPurpose.TRAINING)

# 2) The ordering-sensitive case the module's own docstring calls out:
# Claude-SearchBot / Claude-User must NOT be misclassified as ClaudeBot
# because "ClaudeBot" is a substring-adjacent needle checked later.
s = match(ua_claude_searchbot)
check("Claude-SearchBot NOT classified as ClaudeBot (order-sensitive)", s and s.needle == "Claude-SearchBot" and s.purpose == AccessPurpose.ANSWERING)

# 3) A plain human browser must not match anything
s = match(ua_chrome_human)
check("Ordinary Chrome UA -> no signature match (None)", s is None)

# 4) An unrecognised crawler must not match anything (no guessing)
s = match(ua_unknown_bot)
check("Unrecognised crawler -> no signature match (None)", s is None)

# 5) Empty / whitespace UA -> None, not an exception
check("Empty UA -> None, no exception", match("") is None and match("   ") is None)

# 6) needles() returns the same count/order used for the parity test
ns = actor_signatures.needles()
check("needles() returns 36 canonical entries", len(ns) == 36)

# --- 7) Static parity against the PHP mirror (wordpress-plugin/includes/class-aiol-actors.php)
# No PHP interpreter is available in this sandbox, so this is a text-level
# extraction of the PHP array's keys and order, compared against the
# Python list actually returned by needles(). It proves textual parity of
# the two lists as they exist in these files; it does NOT execute the PHP
# code (PHP itself could not be run here).
php_path = Path(__file__).resolve().parents[1] / "phase13_prev" / "wordpress-plugin" / "includes" / "class-aiol-actors.php"
php_src = php_path.read_text(encoding="utf-8")
m = re.search(r"private static array \$signatures = \[(.*?)\n    \];", php_src, re.S)
php_keys = re.findall(r"'([^']+)' => \[", m.group(1)) if m else []
check(f"PHP mirror has same signature count ({len(php_keys)} vs {len(ns)})", len(php_keys) == len(ns))
check("PHP mirror keys match Python needles() exactly, in order", php_keys == ns)

print()
n_pass = sum(1 for _, ok in results if ok)
print(f"{n_pass}/{len(results)} passed")
if n_pass != len(results):
    sys.exit(1)
