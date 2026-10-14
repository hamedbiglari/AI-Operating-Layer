"""E2E part 3b — AI-facing answer with merchant URL -> real merchant page -> real WooCommerce cart -> real order (cheque, unpaid)."""
import json, re, httpx
S = json.load(open("/home/claude/wp/state.json")); WID = int(open("/home/claude/wp/woo_id.txt").read())
B = "http://127.0.0.1:8000/api/v1"; WP = "http://127.0.0.1:8081"; T = S["owner_token"]
H = lambda t: {"Authorization": f"Bearer {t}"}; c = httpx.Client(timeout=30); out = {}
# an AI agent's own installation + credential (separate from the WordPress adapter)
inst = c.post(f"{B}/installations", headers=H(T), json={"name": "AI agent", "adapter_type": "mcp", "site_id": S["site_id"]}).json()
agent = c.post(f"{B}/installations/{inst['id']}/credentials", headers=H(T), json={"scopes": ["ai:query", "knowledge:read"]}).json()["token"]
r = c.post(f"{B}/ai/ask", headers=H(agent), json={"topic": "where to buy authentic toranjebin", "knowledge_object_id": S["ko_id"], "purchase_intent": "ready", "limit": 3})
ask = r.json(); out["ai_ask_http"] = r.status_code
out["ai_answer"] = {"answerable": ask.get("answerable"), "reason": ask.get("reason"), "products": ask.get("products")}
url = (ask.get("products") or [{}])[0].get("merchant_url"); out["merchant_url"] = url
# merchant website: the real WooCommerce product page
page = c.get(url, follow_redirects=True); html = page.text
out["product_page"] = {"http": page.status_code, "title_present": "Toranjebin Grade A" in html,
                       "woo_price_12_90": "12.90" in html}
ld = [json.loads(b) for b in re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S) if '"Product"' in b or "Product" in b]
aiol = [x for x in ld if isinstance(x, dict) and (x.get("sku") == "TRJ-A-100" or "offers" in x)]
out["json_ld_product_blocks"] = len(ld)
out["json_ld_blocks"] = [{k: x.get(k) for k in ("@id", "sku", "identifier", "offers", "url")} for x in ld][:3]
# real WooCommerce cart via the Store API
w = httpx.Client(timeout=30)
cart0 = w.get(f"{WP}/?rest_route=/wc/store/v1/cart"); nonce = cart0.headers.get("Nonce")
add = w.post(f"{WP}/?rest_route=/wc/store/v1/cart/add-item", headers={"Nonce": nonce}, json={"id": WID, "quantity": 2})
cart = add.json()
out["cart"] = {"http": add.status_code, "items": [{"id": i["id"], "name": i["name"], "quantity": i["quantity"], "line_total": i["totals"]["line_total"]} for i in cart.get("items", [])],
               "total": cart.get("totals", {}).get("total_price"), "currency": cart.get("totals", {}).get("currency_code")}
# purchase intent -> real order (cheque = no money moves)
addr = {"first_name": "E2E", "last_name": "Buyer", "address_1": "1 Test St", "city": "San Jose", "postcode": "95112", "country": "US", "state": "CA", "email": "buyer@example.com", "phone": "0"}
co = w.post(f"{WP}/?rest_route=/wc/store/v1/checkout", headers={"Nonce": add.headers.get("Nonce", nonce)},
            json={"billing_address": addr, "shipping_address": {k: v for k, v in addr.items() if k not in ("email",)}, "payment_method": "cheque"})
cj = co.json()
out["checkout"] = {"http": co.status_code, "order_id": cj.get("order_id"), "status": cj.get("status"),
                   "payment_status": (cj.get("payment_result") or {}).get("payment_status"), "error": cj.get("message") if co.status_code >= 400 else None}
json.dump(out, open("/home/claude/wp/e2e_purchase_out.json", "w"), indent=1)
print(json.dumps(out, indent=1, ensure_ascii=False))
