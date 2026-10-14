"""E2E part 1 — Cloud Core tenant, knowledge, evidence, product, trust, query (real API, real DB)."""
import json, sys, httpx
B = "http://127.0.0.1:8000/api/v1"; S = {}
c = httpx.Client(timeout=20)
def call(m, path, tok=None, **kw):
    r = c.request(m, B + path, headers={"Authorization": f"Bearer {tok}"} if tok else {}, **kw)
    if r.status_code >= 400:
        print("FAIL", m, path, r.status_code, r.text[:400]); sys.exit(1)
    return r.json()
reg = call("POST", "/auth/register-organization", json={"organization_name": "Toranjebin Merchant", "owner_email": "owner@toranjebin.example", "owner_name": "Owner", "owner_password": "e2e-owner-pass-123"})
T = reg["token"]["access_token"]; S["org_id"] = reg["organization"]["id"]; S["owner_token"] = T
S["site_id"] = call("POST", "/sites", T, json={"name": "Toranjebin Shop", "domain": "127.0.0.1:8081", "platform": "wordpress", "wordpress_url": "http://127.0.0.1:8081", "woo_enabled": True})["id"]
inst = call("POST", "/installations", T, json={"name": "WP e2e", "adapter_type": "wordpress", "site_id": S["site_id"], "external_url": "http://127.0.0.1:8081"})
S["installation_id"] = inst["id"]
cred = call("POST", f"/installations/{inst['id']}/credentials", T, json={"scopes": ["catalog:read", "mappings:read", "mappings:write", "commerce:read", "commerce:write", "recommendations:read"]})
S["adapter_token"] = cred.get("token") or cred.get("plaintext_token") or cred.get("secret")
print("credential keys:", [k for k in cred.keys()])
ko = call("POST", "/knowledge", T, json={"canonical_name": "Toranjebin (Persian manna)", "object_type": "ingredient", "description": "Traditional Persian manna collected from Alhagi maurorum."})
S["ko_id"] = ko["id"]
ent = call("POST", "/entities", T, json={"knowledge_object_id": ko["id"], "entity_type": "ingredient", "canonical_name": "Toranjebin"})
S["entity_id"] = ent["id"]
src = call("POST", "/sources", T, json={"source_type": "url", "title": "Supplier lab certificate — Toranjebin batch 2026-07", "url": "http://127.0.0.1:8081/lab-certificate", "reliability_score": 0.8})
S["source_id"] = src["id"]
ev = call("POST", "/evidence", T, json={"source_id": src["id"], "summary": "Lab certificate: batch contains mannitol; no adulterants detected.", "directness": "direct", "evidence_strength": "moderate"})
S["evidence_id"] = ev["id"]
def transition(path, field, steps):
    last = None
    for s in steps:
        r = c.post(B + path, headers={"Authorization": f"Bearer {T}"}, json={field: s, "note": "e2e review"})
        if r.status_code >= 400:
            print("  transition", path, s, "->", r.status_code, r.json().get("error", {}).get("message", "")[:160]); continue
        last = r.json()
    return last
S["evidence_status"] = transition(f"/evidence/{ev['id']}/review", "status", ["pending_review", "verified"])["status"]
cl = call("POST", "/claims", T, json={"knowledge_object_id": ko["id"], "subject_entity_id": ent["id"], "predicate": "contains", "object_value": "mannitol", "claim_type": "composition"})
S["claim_id"] = cl["id"]
S["claim_status"] = transition(f"/claims/{cl['id']}/review", "status", ["pending_review", "approved"])["status"]
S["claim_evidence_id"] = call("POST", "/claim-evidence", T, json={"claim_id": cl["id"], "evidence_id": ev["id"], "relation": "supports"})["id"]
prod = call("POST", "/products", T, json={"name": "Toranjebin Grade A — 100 g", "slug": "toranjebin-grade-a-100g", "site_id": S["site_id"], "sku": "TRJ-A-100", "brand": "Toranjebin Co", "category": "herbal", "origin": "IR", "knowledge_object_id": ko["id"]})
S["product_id"] = prod["id"]
pe = call("POST", f"/products/{prod['id']}/evidence", T, json={"evidence_id": ev["id"], "claim": "Batch lab-tested: contains mannitol, no adulterants detected."})
S["product_evidence_id"] = pe["id"]
S["product_evidence_status"] = transition(f"/product-evidence/{pe['id']}/verify", "verification_status", ["verified"])["verification_status"]
tr = call("POST", "/trust-records", T, json={"subject_type": "product", "subject_id": prod["id"], "trust_type": "testing", "claim": "Independent lab test of this batch", "evidence_id": ev["id"]})
S["trust_id"] = tr["id"]
S["trust_verified"] = call("POST", f"/trust-records/{tr['id']}/verify", T, json={"verification_status": "verified", "note": "Certificate checked by owner"})["verification_status"]
S["product_status"] = transition(f"/products/{prod['id']}/status", "status", ["in_review", "published"])["status"]
imp = call("POST", "/queries/import", T, data={"source": "manual", "rows_json": json.dumps([{"query": "where to buy authentic toranjebin online"}])})
q = call("GET", "/queries?limit=5", T)["items"][0]; S["query_id"] = q["id"]
S["intent"] = call("POST", f"/queries/{q['id']}/intents", T, json={"intent_type": "transactional", "entity_id": ent["id"], "is_primary": True})["intent_type"]
json.dump(S, open("/home/claude/wp/state.json", "w"), indent=1)
print(json.dumps({k: v for k, v in S.items() if "token" not in k}, indent=1))
print("adapter token present:", bool(S["adapter_token"]))
