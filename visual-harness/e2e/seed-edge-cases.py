"""Seed one fresh organization with knowledge objects in the edge-case states
the live Knowledge list must handle, then check GET /knowledge/overview
against them.

API only: POST /knowledge creates every object as a draft and
PATCH /knowledge/{id} sets the other statuses. No claims, gaps or evidence
are added, so every count is 0 and only the status decides what is shown:

  clean-published  published, nothing open -> finished: hidden by default,
                   shown with include_finished=true
  archived         archived -> never shown, not even with include_finished
  draft            draft -> always shown
  in-review        in_review -> always shown
  region           draft, object_type "region" (no approved label) -> the
                   list shows it in English inside <bdi>; found by search

Prints JSON with the organization name, its access token, the object ids and
each check (query, expected, got). Exit 1 if any check fails.

Needs a running Cloud Core:
  cd cloud-core
  .venv/Scripts/python.exe ../visual-harness/e2e/seed-edge-cases.py [http://127.0.0.1:8000] > seed-edge.json

The organization is left in place for the browser; delete it afterwards
(organizations cascade to their users and knowledge objects).
"""

import json
import sys
import time

import httpx

API = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/") + "/api/v1"
client = httpx.Client(base_url=API, timeout=30)


def ok(response: httpx.Response) -> dict:
    assert response.status_code in (200, 201), (str(response.request.url), response.status_code, response.text[:300])
    return response.json()


stamp = int(time.time())
name = f"E2E Knowledge edge cases {stamp}"
org = ok(client.post("/auth/register-organization", json={
    "organization_name": name, "owner_email": f"e2e-edge-{stamp}@example.dev",
    "owner_name": "E2E Owner", "owner_password": "supersecret123"}))
token = org["token"]["access_token"]
client.headers["Authorization"] = "Bearer " + token

# (key, canonical_name, object_type, status set by PATCH or None to stay a draft).
# Only the region object has "region" in its name, so search=region finds one.
PLAN = [
    ("clean-published", "Clean published", "plant", "published"),
    ("archived", "Legacy note", "plant", "archived"),
    ("draft", "Draft object", "plant", None),
    ("in-review", "In review object", "concept", "in_review"),
    ("region", "Khorasan region", "region", None),
]
ids = {}
for key, canonical_name, object_type, status in PLAN:
    obj = ok(client.post("/knowledge", json={"canonical_name": canonical_name, "object_type": object_type}))
    assert obj["status"] == "draft", (key, obj["status"])
    if status:
        obj = ok(client.patch(f"/knowledge/{obj['id']}", json={"status": status}))
        assert obj["status"] == status, (key, obj["status"])
    ids[key] = obj["id"]
by_id = {v: k for k, v in ids.items()}


def shown(**params) -> list[str]:
    page = ok(client.get("/knowledge/overview", params={"limit": 100, **params}))
    assert page["total"] == len(page["items"]), page["total"]
    return sorted(by_id[item["id"]] for item in page["items"])


CHECKS = [
    ("default", {}, ["draft", "in-review", "region"]),
    ("include_finished=true", {"include_finished": "true"}, ["clean-published", "draft", "in-review", "region"]),
    ("status=archived", {"status": "archived", "include_finished": "true"}, []),
    ("object_type=region", {"object_type": "region"}, ["region"]),
    ("search=region", {"search": "region"}, ["region"]),
]
results = []
for label, params, expected in CHECKS:
    got = shown(**params)
    results.append({"query": label, "expected": expected, "got": got, "count": len(got), "pass": got == expected})

print(json.dumps({"organization": name, "token": token, "objects": ids, "checks": results}, indent=1))
sys.exit(0 if all(r["pass"] for r in results) else 1)
