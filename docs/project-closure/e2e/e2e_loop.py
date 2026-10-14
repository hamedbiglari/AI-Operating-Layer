"""E2E part 3 — Core truth after the real WooCommerce sync, recommendation, AI-facing ask, merchant page, cart, order."""
import json, re, sys, httpx
S = json.load(open("/home/claude/wp/state.json")); WID = int(open("/home/claude/wp/woo_id.txt").read())
B = "http://127.0.0.1:8000/api/v1"; WP = "http://127.0.0.1:8081"; T = S["owner_token"]; A = S["adapter_token"]
c = httpx.Client(timeout=30); out = {}
H = lambda t: {"Authorization": f"Bearer {t}"}
def j(r):
    try: return r.json()
    except Exception: return r.text[:300]
# Core state produced by the plugin
offers = j(c.get(f"{B}/products/{S['product_id']}/offers", headers=H(T)))
out["core_offer"] = [{k: o.get(k) for k in ("id", "price", "currency", "availability", "stock_quantity", "url", "external_id")} for o in (offers.get("items", offers) if isinstance(offers, dict) else offers)]
maps = j(c.get(f"{B}/mappings", headers=H(T)))
out["core_mapping"] = [{k: m.get(k) for k in ("object_type", "object_id", "wordpress_post_id", "wordpress_url")} for m in maps.get("items", [])]
cm = j(c.get(f"{B}/commerce-mappings", headers=H(T)))
out["core_commerce_mapping"] = [{k: m.get(k) for k in ("id", "product_id", "woo_product_id", "sku")} for m in cm.get("items", [])]
# recommendation (owner, merchant dashboard path)
r = c.post(f"{B}/recommendations", headers=H(T), json={"response_mode": "recommend", "query_id": S["query_id"], "knowledge_object_id": S["ko_id"], "persist": True})
rec = j(r); out["recommendation_http"] = r.status_code
out["recommendation"] = {k: rec.get(k) for k in ("status", "explanation")} if isinstance(rec, dict) else rec
items = rec.get("recommendations", []) if isinstance(rec, dict) else []
out["recommended"] = [{"product_id": i.get("product_id"), "status": i.get("status"), "offer_id": i.get("offer_id"), "final_score": i.get("final_score"), "caveats": i.get("caveats"), "keys": sorted(i.keys())} for i in items]
out["rejected"] = rec.get("rejected") if isinstance(rec, dict) else None
# AI-facing path with the machine credential (what an AI agent would call)
r = c.post(f"{B}/ai/ask", headers=H(A), json={"topic": "toranjebin", "knowledge_object_id": S["ko_id"], "purchase_intent": True, "limit": 3})
ask = j(r); out["ai_ask_http"] = r.status_code
out["ai_ask"] = json.dumps(ask)[:900]
urls = re.findall(r'https?://127\.0\.0\.1:8081[^"\s]*', json.dumps(ask) + json.dumps(rec) + json.dumps(offers) + json.dumps(maps))
out["merchant_urls_seen_in_core_responses"] = sorted(set(urls))
json.dump(out, open("/home/claude/wp/e2e_core_out.json", "w"), indent=1)
print(json.dumps(out, indent=1)[:6000])
