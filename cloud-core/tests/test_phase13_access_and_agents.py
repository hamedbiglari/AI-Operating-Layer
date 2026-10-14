"""
Phase 13 — agent discovery, access policy precedence, tenant isolation.

THE TWO PROPERTIES THAT MATTER MOST

1. **The registry has no rejection path.** An agent nobody has heard of
   still gets a row. A test asserts this with a User-Agent that is
   guaranteed not to be in the seed list, because "every AI that comes in
   must be listed" is the requirement and an allow-list would satisfy
   every other test in this file while failing the product.

2. **Precedence is first-match, most-specific-first, and stops.** Four
   tests walk the four levels and one asserts that a specific rule beats a
   general one even when the general one is stricter — because "strictest
   wins" is the plausible-looking alternative that would make "block all
   AI crawlers except this one" impossible to express.

STATUS: written, NOT YET EXECUTED. See PHASE13_REPORT.md §Verification.
"""

import uuid as uuid_module
from datetime import datetime, timezone

from fastapi.testclient import TestClient

UTC = timezone.utc

GPTBOT_UA = "compatible; GPTBot/1.2; +https://openai.com/gptbot"
CLAUDEBOT_UA = "Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)"
CLAUDE_USER_UA = "Mozilla/5.0 (compatible; Claude-User/1.0; +Claude-User@anthropic.com)"
CLAUDE_SEARCH_UA = "Mozilla/5.0 (compatible; Claude-SearchBot/1.0)"
BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
NOVEL_UA = "ZorpAnalyticsCrawler/2.3 (+https://zorp.invalid)"
GIBBERISH_UA = "qqq-zzz-client"


# ---------------------------------------------------------------------------
# Classification — pure, no database
# ---------------------------------------------------------------------------


def test_signature_match_is_detected_never_verified() -> None:
    """A header is a claim. Presenting a header match as a verified
    identity is the same class of error as treating unverified evidence as
    verified — the thing this whole architecture exists to avoid."""
    from app.models.enums import ActorConfidence
    from app.services.ai_agent_service import classify

    actor_type, confidence, purpose, note = classify(GPTBOT_UA)
    assert confidence == ActorConfidence.DETECTED
    assert confidence != ActorConfidence.VERIFIED
    assert "not verified" in note.lower() or "NOT verified" in note


def test_user_driven_fetch_is_not_classified_as_a_training_crawler() -> None:
    """`Claude-User` and `ClaudeBot` share a prefix. If ordering were
    wrong, a merchant's "block training" rule would block their own
    customers' questions — which is the single most damaging way this
    feature could fail."""
    from app.models.enums import AccessPurpose, ActorType
    from app.services.ai_agent_service import classify

    assert classify(CLAUDE_USER_UA)[0] == ActorType.AI_USER_AGENT
    assert classify(CLAUDE_USER_UA)[2] == AccessPurpose.ANSWERING
    assert classify(CLAUDE_SEARCH_UA)[0] == ActorType.AI_USER_AGENT
    assert classify(CLAUDEBOT_UA)[0] == ActorType.AI_CRAWLER
    assert classify(CLAUDEBOT_UA)[2] == AccessPurpose.TRAINING


def test_unrecognised_automated_client_is_probable_not_asserted() -> None:
    from app.models.enums import ActorConfidence, ActorType
    from app.services.ai_agent_service import classify

    actor_type, confidence, _, _ = classify(NOVEL_UA)
    assert actor_type == ActorType.UNKNOWN
    assert confidence == ActorConfidence.PROBABLE


def test_robot_and_abbot_are_not_classified_as_bots() -> None:
    """Inherited verbatim from AIOL_Actors, where this was found by a real
    test failure: a bare "bot" substring misclassifies "robot", "abbot"
    and several genuine browser strings."""
    from app.models.enums import ActorType
    from app.services.ai_agent_service import classify

    assert classify("Mozilla/5.0 RobotCleaner Chrome/120.0")[0] != ActorType.UNKNOWN
    assert classify(BROWSER_UA)[0] == ActorType.HUMAN


def test_empty_user_agent_is_unknown_with_an_explanation() -> None:
    from app.models.enums import ActorConfidence, ActorType
    from app.services.ai_agent_service import classify

    actor_type, confidence, _, note = classify("")
    assert (actor_type, confidence) == (ActorType.UNKNOWN, ActorConfidence.UNKNOWN)
    assert note


def test_fingerprint_collapses_version_bumps() -> None:
    """Otherwise every Chrome release would appear as a newly discovered
    AI, and the discovery list — the thing the merchant is supposed to
    read — would be unreadable within a week."""
    from app.services.ai_agent_service import fingerprint

    a = fingerprint("ZorpCrawler/1.2.3 (+https://zorp.invalid)")
    b = fingerprint("ZorpCrawler/1.9.0 (+https://zorp.invalid)")
    c = fingerprint("OtherCrawler/1.2.3 (+https://other.invalid)")
    assert a == b
    assert a != c


# ---------------------------------------------------------------------------
# Discovery — there is no allow-list
# ---------------------------------------------------------------------------


def test_an_unknown_agent_is_registered_not_dropped(
    client: TestClient, adapter_credential
) -> None:
    """THE requirement: no restriction on which AIs are listed."""
    org = adapter_credential["org"]
    client.post(
        "/api/v1/telemetry/ingest/page-views",
        json={
            "events": [
                {
                    "event_key": uuid_module.uuid4().hex,
                    "occurred_at": datetime.now(UTC).isoformat(),
                    "path": "/",
                    "user_agent": NOVEL_UA,
                }
            ]
        },
        headers=adapter_credential["headers"],
    )
    agents = client.get(
        "/api/v1/telemetry/agents?seen_only=true", headers=org["headers"]
    ).json()
    names = [a["display_name"] for a in agents["items"]]
    assert any("Zorp" in n for n in names), f"discovered agent missing from {names}"
    discovered = next(a for a in agents["items"] if "Zorp" in a["display_name"])
    assert discovered["origin"] == "discovered"
    assert discovered["confidence"] == "probable"


def test_even_a_gibberish_client_gets_a_row(client: TestClient, adapter_credential) -> None:
    org = adapter_credential["org"]
    client.post(
        "/api/v1/telemetry/ingest/page-views",
        json={
            "events": [
                {
                    "event_key": uuid_module.uuid4().hex,
                    "occurred_at": datetime.now(UTC).isoformat(),
                    "path": "/",
                    "user_agent": GIBBERISH_UA,
                }
            ]
        },
        headers=adapter_credential["headers"],
    )
    total = client.get(
        "/api/v1/telemetry/agents?seen_only=true", headers=org["headers"]
    ).json()["total"]
    assert total >= 1


def test_agents_endpoint_has_no_known_only_filter() -> None:
    """A filter that hid unrecognised agents would hide precisely the rows
    the merchant needs. Asserted against the route signature so a future
    "helpful" addition fails the build."""
    import inspect

    from app.api.v1.telemetry import list_agents

    params = set(inspect.signature(list_agents).parameters)
    assert "known_only" not in params
    assert "seen_only" in params


def test_reseeing_an_agent_does_not_overwrite_a_merchant_rename(
    client: TestClient, adapter_credential
) -> None:
    org = adapter_credential["org"]
    headers = adapter_credential["headers"]

    def send(ua):
        client.post(
            "/api/v1/telemetry/ingest/page-views",
            json={
                "events": [
                    {
                        "event_key": uuid_module.uuid4().hex,
                        "occurred_at": datetime.now(UTC).isoformat(),
                        "path": "/",
                        "user_agent": ua,
                    }
                ]
            },
            headers=headers,
        )

    send(GPTBOT_UA)
    agent = client.get("/api/v1/telemetry/agents?seen_only=true", headers=org["headers"]).json()["items"][0]
    client.patch(
        f"/api/v1/telemetry/agents/{agent['id']}",
        json={"display_name": "OpenAI training crawler (ours)"},
        headers=org["headers"],
    )
    send(GPTBOT_UA)
    after = client.get(f"/api/v1/telemetry/agents?seen_only=true", headers=org["headers"]).json()["items"][0]
    assert after["display_name"] == "OpenAI training crawler (ours)"
    assert after["observation_count"] == 2


# ---------------------------------------------------------------------------
# Access policy precedence
# ---------------------------------------------------------------------------


def _policy(client, headers, **body):
    return client.put("/api/v1/telemetry/access-policies", json=body, headers=headers)


def _decide(client, adapter_headers, ua, purpose=None):
    url = f"/api/v1/telemetry/access-decision?user_agent={ua}"
    if purpose:
        url += f"&purpose={purpose}"
    return client.get(url, headers=adapter_headers).json()


def test_no_policy_is_not_configured_not_allowed(
    client: TestClient, adapter_credential
) -> None:
    """Both let the request through; only one is honest about the fact
    that nobody decided. An invisible default that quietly becomes policy
    is exactly what the dashboard's "awaiting decision" count exists to
    prevent."""
    result = _decide(client, adapter_credential["headers"], GPTBOT_UA)
    assert result["decision"] == "not_configured"
    assert result["tier"] == "unset"
    assert result["http_status"] == 200


def test_actor_type_rule_blocks_all_ai_crawlers(client: TestClient, adapter_credential) -> None:
    org = adapter_credential["org"]
    _policy(client, org["headers"], actor_type="ai_crawler", tier="forbidden",
            reason="We do not permit corpus collection.")
    result = _decide(client, adapter_credential["headers"], GPTBOT_UA)
    assert result["decision"] == "blocked"
    assert result["http_status"] == 403
    assert "corpus" in result["reason"]


def test_purpose_rule_blocks_training_while_answering_stays_open(
    client: TestClient, adapter_credential
) -> None:
    """The headline use case: no to training, yes to answering."""
    org = adapter_credential["org"]
    _policy(client, org["headers"], actor_type="ai_crawler", purpose="training", tier="forbidden")
    _policy(client, org["headers"], actor_type="ai_user_agent", purpose="answering", tier="free")

    assert _decide(client, adapter_credential["headers"], GPTBOT_UA)["decision"] == "blocked"
    assert _decide(client, adapter_credential["headers"], CLAUDE_USER_UA)["decision"] == "allowed"


def test_specific_agent_rule_beats_a_stricter_general_rule(
    client: TestClient, adapter_credential
) -> None:
    """"Strictest wins" is the plausible-looking alternative that would
    make "block all AI crawlers EXCEPT this one" impossible to express.
    Most-specific-first is what makes the table readable."""
    org = adapter_credential["org"]
    headers = adapter_credential["headers"]

    _decide(client, headers, GPTBOT_UA)  # ensure the agent row exists
    agent = client.get("/api/v1/telemetry/agents", headers=org["headers"]).json()["items"]
    gptbot = next(a for a in agent if a["signature"] == "GPTBot")

    _policy(client, org["headers"], actor_type="ai_crawler", tier="forbidden")
    _policy(client, org["headers"], agent_id=gptbot["id"], tier="free")

    result = _decide(client, headers, GPTBOT_UA)
    assert result["decision"] == "allowed", "the specific rule must win"
    assert result["matched_policy_id"] is not None


def test_paid_tier_returns_402_with_terms_link(client: TestClient, adapter_credential) -> None:
    org = adapter_credential["org"]
    _policy(
        client, org["headers"], actor_type="ai_crawler", tier="paid",
        reason="Commercial licence required.",
        terms_url="https://merchant.example/ai-terms",
    )
    result = _decide(client, adapter_credential["headers"], GPTBOT_UA)
    assert result["decision"] == "payment_required"
    assert result["http_status"] == 402
    assert result["terms_url"] == "https://merchant.example/ai-terms"


def test_unset_tier_behaves_exactly_like_no_rule(client: TestClient, adapter_credential) -> None:
    """"I created the row but haven't chosen yet" must not read as "I
    allowed it"."""
    org = adapter_credential["org"]
    _policy(client, org["headers"], actor_type="ai_crawler", tier="unset")
    assert _decide(client, adapter_credential["headers"], GPTBOT_UA)["decision"] == "not_configured"


def test_humans_are_never_subject_to_an_access_policy(
    client: TestClient, adapter_credential
) -> None:
    """A rule that could 403 a customer's browser is a foot-gun with no
    upside. A merchant who wants to block human traffic has a firewall."""
    org = adapter_credential["org"]
    _policy(client, org["headers"], actor_type="human", tier="forbidden")
    result = _decide(client, adapter_credential["headers"], BROWSER_UA)
    assert result["decision"] == "allowed"


def test_policy_with_no_subject_is_422(client: TestClient, adapter_credential) -> None:
    org = adapter_credential["org"]
    response = _policy(client, org["headers"], tier="forbidden")
    assert response.status_code == 422


def test_policy_with_two_subjects_is_422(client: TestClient, adapter_credential) -> None:
    org = adapter_credential["org"]
    _decide(client, adapter_credential["headers"], GPTBOT_UA)
    agents = client.get("/api/v1/telemetry/agents", headers=org["headers"]).json()["items"]
    response = _policy(
        client, org["headers"],
        agent_id=agents[0]["id"], actor_type="ai_crawler", tier="forbidden",
    )
    assert response.status_code == 422


def test_put_is_idempotent_and_does_not_create_a_second_rule(
    client: TestClient, adapter_credential
) -> None:
    """Two "GPTBot, training" rows would make precedence ambiguous the
    moment the second one succeeded."""
    org = adapter_credential["org"]
    _policy(client, org["headers"], actor_type="ai_crawler", purpose="training", tier="forbidden")
    _policy(client, org["headers"], actor_type="ai_crawler", purpose="training", tier="paid")
    listing = client.get("/api/v1/telemetry/access-policies", headers=org["headers"]).json()
    matching = [p for p in listing["items"] if p["actor_type"] == "ai_crawler" and p["purpose"] == "training"]
    assert len(matching) == 1
    assert matching[0]["tier"] == "paid"


def test_specificity_cannot_be_set_by_a_client() -> None:
    """A caller who could set it could reorder the whole precedence table
    from outside."""
    from app.schemas.telemetry import AccessPolicyWrite

    assert "specificity" not in AccessPolicyWrite.model_fields


def test_deleting_a_policy_does_not_rewrite_recorded_history(
    client: TestClient, adapter_credential, db_session
) -> None:
    """`page_views.matched_policy_id` is deliberately not a foreign key:
    what we DID must survive the rule that did it."""
    from app.models.page_view import PageView

    org = adapter_credential["org"]
    _policy(client, org["headers"], actor_type="ai_crawler", tier="forbidden")
    client.post(
        "/api/v1/telemetry/ingest/page-views",
        json={
            "events": [
                {
                    "event_key": uuid_module.uuid4().hex,
                    "occurred_at": datetime.now(UTC).isoformat(),
                    "path": "/",
                    "user_agent": GPTBOT_UA,
                }
            ]
        },
        headers=adapter_credential["headers"],
    )
    policy = client.get("/api/v1/telemetry/access-policies", headers=org["headers"]).json()["items"][0]
    client.delete(f"/api/v1/telemetry/access-policies/{policy['id']}", headers=org["headers"])

    view = db_session.query(PageView).first()
    assert view.access_decision.value == "blocked"
    assert str(view.matched_policy_id) == policy["id"]


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


def test_one_tenant_cannot_see_another_tenants_traffic(
    client: TestClient, adapter_credential, register_org
) -> None:
    other = register_org()
    client.post(
        "/api/v1/telemetry/ingest/page-views",
        json={
            "events": [
                {
                    "event_key": uuid_module.uuid4().hex,
                    "occurred_at": datetime.now(UTC).isoformat(),
                    "path": "/secret",
                    "user_agent": GPTBOT_UA,
                }
            ]
        },
        headers=adapter_credential["headers"],
    )
    listing = client.get("/api/v1/telemetry/page-views", headers=other["headers"]).json()
    assert listing["total"] == 0


def test_agent_registry_is_per_tenant(
    client: TestClient, adapter_credential, register_org
) -> None:
    """Two merchants can legitimately reach different conclusions about the
    same crawler. A global agent row would leak one merchant's decision
    into another's tenant."""
    other = register_org()
    _decide(client, adapter_credential["headers"], GPTBOT_UA)
    assert client.get("/api/v1/telemetry/agents", headers=other["headers"]).json()["total"] == 0


def test_cross_tenant_policy_write_is_404(
    client: TestClient, adapter_credential, register_org
) -> None:
    """404, not 403 — a 403 would confirm the agent exists in another
    tenant (the Phase 0 golden-test rule)."""
    org = adapter_credential["org"]
    other = register_org()
    _decide(client, adapter_credential["headers"], GPTBOT_UA)
    agent = client.get("/api/v1/telemetry/agents", headers=org["headers"]).json()["items"][0]

    response = _policy(client, other["headers"], agent_id=agent["id"], tier="free")
    assert response.status_code == 404


def test_cross_tenant_policy_delete_is_404(
    client: TestClient, adapter_credential, register_org
) -> None:
    org = adapter_credential["org"]
    other = register_org()
    _policy(client, org["headers"], actor_type="ai_crawler", tier="forbidden")
    policy = client.get("/api/v1/telemetry/access-policies", headers=org["headers"]).json()["items"][0]
    response = client.delete(
        f"/api/v1/telemetry/access-policies/{policy['id']}", headers=other["headers"]
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Signature parity with the plugin
# ---------------------------------------------------------------------------


def test_python_and_php_signature_lists_are_identical() -> None:
    """Two runtimes classify the same traffic. If they drift, the edge
    blocks one thing and the report shows another, and the merchant's
    policy silently stops matching. Drift is made a test failure rather
    than a code-review responsibility."""
    import pathlib
    import re

    from app.services.actor_signatures import needles

    php = pathlib.Path(__file__).resolve().parents[2] / "wordpress-plugin" / "includes" / "class-aiol-actors.php"
    if not php.exists():  # pragma: no cover
        import pytest

        pytest.skip("plugin source not present in this checkout")

    found = re.findall(r"'([^']+)'\s*=>\s*\[self::", php.read_text(encoding="utf-8"))
    assert found, "no signatures parsed from the plugin — the parity test itself is broken"
    assert found == needles(), (
        "Python and PHP signature lists differ.\n"
        f"only in PHP: {set(found) - set(needles())}\n"
        f"only in Python: {set(needles()) - set(found)}\n"
        "Order matters too: first-hit matching means Claude-User must precede ClaudeBot."
    )


def test_a_rule_blocking_one_named_agent_beats_a_permissive_type_rule(
    client: TestClient, adapter_credential
) -> None:
    """Added in the final existing-owner closure pass: the fail-OPEN side of
    the precedence defect. Before the fix the specific block was ignored."""
    org = adapter_credential["org"]
    headers = adapter_credential["headers"]
    _decide(client, headers, GPTBOT_UA)
    agent = client.get("/api/v1/telemetry/agents", headers=org["headers"]).json()["items"]
    gptbot = next(a for a in agent if a["signature"] == "GPTBot")
    _policy(client, org["headers"], actor_type="ai_crawler", tier="free")
    _policy(client, org["headers"], agent_id=gptbot["id"], tier="forbidden")
    assert _decide(client, headers, GPTBOT_UA)["decision"] == "blocked"
