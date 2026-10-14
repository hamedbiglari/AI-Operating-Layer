"""Website management (ADR-118): blog posts, revisions, sections, newsletter."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import exc, text

W = "/api/v1/website"


def _slug(org):
    return org["organization"]["slug"]


def _post(client, org, **kw):
    body = {"lang": "en", "slug": "why-indirect-stays-indirect", "title": "Why indirect stays indirect",
            "body": "A study of a compound is evidence about that compound.", "author_name": "AIOL team"}
    body.update(kw)
    r = client.post(f"{W}/posts", headers=org["headers"], json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_a_post_is_drafted_edited_with_history_and_published(client: TestClient, register_org) -> None:
    org = register_org()
    p = _post(client, org, references=[{"title": "Citing Medicine", "publisher": "NLM"}])
    assert p["status"] == "draft" and p["version"] == 1
    r = client.patch(f"{W}/posts/{p['id']}", headers=org["headers"], json={"title": "Why indirect evidence stays indirect", "note": "Sharper title"})
    assert r.json()["version"] == 2
    hist = client.get(f"{W}/posts/{p['id']}/revisions", headers=org["headers"]).json()
    assert [h["version"] for h in hist] == [2, 1] and hist[0]["note"] == "Sharper title"
    pub = client.post(f"{W}/posts/{p['id']}/publish", headers=org["headers"]).json()
    assert pub["status"] == "published" and pub["published_at"]
    listed = client.get(f"/api/v1/public/website/{_slug(org)}/posts?lang=en").json()
    assert [x["slug"] for x in listed] == ["why-indirect-stays-indirect"] and "body" not in listed[0]
    one = client.get(f"/api/v1/public/website/{_slug(org)}/posts/why-indirect-stays-indirect").json()
    assert one["references"][0]["title"] == "Citing Medicine" and len(one["history"]) == 2


def test_a_draft_is_not_public_and_publishing_needs_an_author_and_a_body(client: TestClient, register_org) -> None:
    org = register_org()
    p = _post(client, org, author_name=None)
    assert client.get(f"/api/v1/public/website/{_slug(org)}/posts").json() == []
    assert client.get(f"/api/v1/public/website/{_slug(org)}/posts/{p['slug']}").status_code == 404
    r = client.post(f"{W}/posts/{p['id']}/publish", headers=org["headers"])
    assert r.status_code == 422 and "author" in r.text


def test_the_database_refuses_a_published_post_without_a_date(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    p = _post(client, org)
    with pytest.raises(exc.IntegrityError, match="published_needs_date_and_author"):
        db_session.execute(text("UPDATE site_posts SET status='published', published_at=NULL WHERE id=:i"), {"i": p["id"]})
        db_session.flush()
    db_session.rollback()


def test_translations_are_linked_and_exposed_as_alternates(client: TestClient, register_org) -> None:
    org = register_org()
    en = _post(client, org)
    fa = _post(client, org, lang="fa", slug="why-indirect-stays-indirect", title="چرا شواهد غیرمستقیم غیرمستقیم می‌ماند",
               translation_of=en["id"])
    assert fa["translation_group"] == en["id"]
    for x in (en, fa):
        client.post(f"{W}/posts/{x['id']}/publish", headers=org["headers"])
    one = client.get(f"/api/v1/public/website/{_slug(org)}/posts/{en['slug']}?lang=en").json()
    assert one["alternate"] == {"lang": "fa", "slug": "why-indirect-stays-indirect"}
    r = client.post(f"{W}/posts", headers=org["headers"], json={"lang": "en", "slug": "x-two", "title": "Same language",
                    "body": "b", "translation_of": en["id"]})
    assert r.status_code == 422


def test_sections_are_seeded_from_the_real_page_and_the_hero_cannot_be_hidden(client: TestClient, register_org) -> None:
    org = register_org()
    secs = client.get(f"{W}/sections?page=home&lang=en", headers=org["headers"]).json()
    assert secs[0]["section_key"] == "hero" and len(secs) == 17 and not {"platform", "capabilities"} & {x["section_key"] for x in secs} and all(s["enabled"] for s in secs)
    hero, faq = secs[0], next(s for s in secs if s["section_key"] == "faq")
    assert client.patch(f"{W}/sections/{hero['id']}", headers=org["headers"], json={"enabled": False}).status_code == 422
    r = client.patch(f"{W}/sections/{faq['id']}", headers=org["headers"], json={"enabled": False, "heading": "Common questions"})
    assert r.json()["enabled"] is False and r.json()["heading"] == "Common questions"
    pub = client.get(f"/api/v1/public/website/{_slug(org)}/sections?page=home&lang=en").json()
    assert next(s for s in pub if s["section_key"] == "faq")["enabled"] is False


def test_subscribe_needs_consent_cannot_be_probed_and_ignores_bots(client: TestClient, register_org) -> None:
    org = register_org()
    url = f"/api/v1/public/website/{_slug(org)}/subscribe"
    base = {"email": "Reader@Example.com", "consent_text": "I agree to receive the monthly newsletter.", "source": "/"}
    assert client.post(url, json={**base, "consent": False}).status_code == 422
    a = client.post(url, json={**base, "consent": True})
    b = client.post(url, json={**base, "consent": True})            # the same address again
    assert a.status_code == b.status_code == 202 and a.json() == b.json()
    client.post(url, json={**base, "email": "bot@example.com", "consent": True, "website": "spam"})
    subs = client.get(f"{W}/subscribers", headers=org["headers"]).json()
    assert subs["total"] == 1 and subs["items"][0]["email"] == "reader@example.com"


def test_unsubscribe_by_token_export_and_erasure(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    client.post(f"/api/v1/public/website/{_slug(org)}/subscribe",
                json={"email": "=cmd@example.com", "consent": True, "consent_text": "I agree to the newsletter."})
    token = db_session.execute(text("SELECT unsubscribe_token FROM newsletter_subscribers")).scalar_one()
    client.get(f"/api/v1/public/website/{_slug(org)}/unsubscribe?token={token}")
    sub = client.get(f"{W}/subscribers", headers=org["headers"]).json()["items"][0]
    assert sub["status"] == "unsubscribed" and sub["unsubscribed_at"]
    csv = client.get(f"{W}/subscribers/export.csv", headers=org["headers"]).text
    assert "'=cmd@example.com" in csv and "consented_at" in csv            # formula injection neutralised
    assert client.delete(f"{W}/subscribers/{sub['id']}", headers=org["headers"]).status_code == 204
    assert client.get(f"{W}/subscribers", headers=org["headers"]).json()["total"] == 0


def test_website_management_is_admin_only_and_tenant_isolated(client: TestClient, register_org) -> None:
    x, y = register_org(), register_org()
    p = _post(client, x)
    assert client.get(f"{W}/posts/{p['id']}", headers=y["headers"]).status_code == 404
    assert client.get(f"{W}/posts", headers=y["headers"]).json()["total"] == 0
    assert client.get(f"/api/v1/public/website/{_slug(y)}/posts").json() == []
    assert client.get(f"{W}/posts").status_code in (401, 403)


def test_website_lists_sort_like_every_other_list(client: TestClient, register_org) -> None:
    org = register_org()
    for slug, title in (("b-post", "Beta"), ("a-post", "Alpha"), ("c-post", "Gamma")):
        _post(client, org, slug=slug, title=title)
    asc = client.get(f"{W}/posts?sort_by=title&sort_dir=asc", headers=org["headers"]).json()["items"]
    assert [x["title"] for x in asc] == ["Alpha", "Beta", "Gamma"]
    assert client.get(f"{W}/posts?sort_by=bogus", headers=org["headers"]).status_code == 422
    assert client.get(f"{W}/subscribers?sort_by=email&sort_dir=asc", headers=org["headers"]).status_code == 200
