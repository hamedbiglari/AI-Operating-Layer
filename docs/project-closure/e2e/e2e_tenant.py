import json, httpx
S = json.load(open("/home/claude/wp/state.json")); B = "http://127.0.0.1:8000/api/v1"; c = httpx.Client(timeout=20)
H = lambda t: {"Authorization": f"Bearer {t}"}
reg = c.post(f"{B}/auth/register-organization", json={"organization_name": "Tenant B", "owner_email": "b-owner@example.com", "owner_name": "B", "owner_password": "tenant-b-pass-123"}).json()
TB = reg["token"]["access_token"]
site = c.post(f"{B}/sites", headers=H(TB), json={"name": "B", "domain": "b.example"}).json()
inst = c.post(f"{B}/installations", headers=H(TB), json={"name": "B agent", "adapter_type": "mcp", "site_id": site["id"]}).json()
AB = c.post(f"{B}/installations/{inst['id']}/credentials", headers=H(TB), json={"scopes": ["ai:query", "knowledge:read", "catalog:read", "mappings:read", "commerce:read"]}).json()["token"]
checks = {
 "B user -> A product": c.get(f"{B}/products/{S['product_id']}", headers=H(TB)).status_code,
 "B user -> A offers": c.get(f"{B}/products/{S['product_id']}/offers", headers=H(TB)).status_code,
 "B user -> A knowledge object": c.get(f"{B}/knowledge/{S['ko_id']}", headers=H(TB)).status_code,
 "B user -> A evidence": c.get(f"{B}/evidence/{S['evidence_id']}", headers=H(TB)).status_code,
 "B user -> A trust record": c.get(f"{B}/trust-records/{S['trust_id']}", headers=H(TB)).status_code,
 "B user -> A query": c.get(f"{B}/queries/{S['query_id']}", headers=H(TB)).status_code,
 "B machine -> A catalog product": c.get(f"{B}/adapter/catalog/{S['product_id']}", headers=H(AB)).status_code,
 "B machine -> A knowledge (AI)": c.get(f"{B}/ai/knowledge/{S['ko_id']}", headers=H(AB)).status_code,
 "B machine -> A product trust (AI)": c.get(f"{B}/ai/products/{S['product_id']}/trust", headers=H(AB)).status_code,
}
lists = {
 "B products": c.get(f"{B}/products", headers=H(TB)).json().get("total"),
 "B mappings": c.get(f"{B}/mappings", headers=H(TB)).json().get("total"),
 "B commerce-mappings": c.get(f"{B}/commerce-mappings", headers=H(TB)).json().get("total"),
 "B recommendations": c.get(f"{B}/recommendations", headers=H(TB)).json().get("total"),
}
ask = c.post(f"{B}/ai/ask", headers=H(AB), json={"purchase_intent": "ready"}).text
print(json.dumps({"direct_access": checks, "list_totals": lists, "B ai/ask leaks A product/url": ("Toranjebin" in ask or "8081" in ask)}, indent=1))
