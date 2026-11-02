"""Each agent's access decision on GET /telemetry/agents (V5-access-agent-decision).

The list resolves every agent against the rule table read once, with evaluate()'s four precedence levels. These
tests pin the values, the "no decision yet" count, agreement with evaluate() on every level, and the single read.
"""
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import event

from app.models.enums import AccessPurpose, ActorType
from app.services import access_policy_service

GPTBOT_UA = "compatible; GPTBot/1.2; +https://openai.com/gptbot"
CLAUDEBOT_UA = "Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)"
CLAUDE_USER_UA = "Mozilla/5.0 (compatible; Claude-User/1.0; +Claude-User@anthropic.com)"
CLAUDE_SEARCH_UA = "Mozilla/5.0 (compatible; Claude-SearchBot/1.0)"
NOVEL_UA = "ZorpAnalyticsCrawler/2.3 (+https://zorp.invalid)"


def _see(client: TestClient, adapter_headers: dict, *uas: str) -> None:
    for ua in uas:   # an access-decision call registers the agent, as an adapter would
        assert client.get(f"/api/v1/telemetry/access-decision?user_agent={ua}", headers=adapter_headers).status_code == 200


def _agents(client: TestClient, headers: dict) -> dict:
    return client.get("/api/v1/telemetry/agents?limit=200", headers=headers).json()


def _policy(client: TestClient, headers: dict, **body) -> None:
    assert client.put("/api/v1/telemetry/access-policies", json=body, headers=headers).status_code == 200


def test_each_agent_carries_its_decision_and_no_rule_is_not_configured(client: TestClient, adapter_credential) -> None:
    org = adapter_credential["org"]
    _see(client, adapter_credential["headers"], GPTBOT_UA, NOVEL_UA)
    page = _agents(client, org["headers"])
    gptbot = next(a for a in page["items"] if a["signature"] == "GPTBot")
    _policy(client, org["headers"], agent_id=gptbot["id"], tier="forbidden")
    page = _agents(client, org["headers"])
    by_name = {a["signature"]: a["decision"] for a in page["items"]}
    assert by_name["GPTBot"] == "forbidden"
    zorp = next(a for a in page["items"] if "Zorp" in a["display_name"])
    assert zorp["decision"] == "unset"            # no rule: allowed, reported as Not configured, never "free"
    assert page["agents_without_decision"] == sum(1 for a in page["items"] if a["decision"] == "unset")
    assert page["agents_without_decision"] >= 1


def test_the_count_covers_every_agent_not_only_the_page(client: TestClient, adapter_credential) -> None:
    org = adapter_credential["org"]
    _see(client, adapter_credential["headers"], GPTBOT_UA, CLAUDEBOT_UA, NOVEL_UA)
    everyone = _agents(client, org["headers"])
    one = client.get("/api/v1/telemetry/agents?limit=1", headers=org["headers"]).json()
    assert len(one["items"]) == 1
    assert one["agents_without_decision"] == everyone["agents_without_decision"]


def test_the_list_agrees_with_evaluate_on_every_precedence_level(client: TestClient, adapter_credential, db_session) -> None:
    org = adapter_credential["org"]
    _see(client, adapter_credential["headers"], GPTBOT_UA, CLAUDEBOT_UA, CLAUDE_USER_UA, CLAUDE_SEARCH_UA, NOVEL_UA)
    items = _agents(client, org["headers"])["items"]
    pick = {a["signature"]: a for a in items}
    gpt, claude = pick["GPTBot"], pick["ClaudeBot"]
    # agent + purpose, agent any purpose, actor type + purpose, actor type any purpose, plus a rule that never applies
    _policy(client, org["headers"], agent_id=gpt["id"], purpose=gpt["declared_purpose"], tier="forbidden")
    _policy(client, org["headers"], agent_id=gpt["id"], tier="free")
    _policy(client, org["headers"], agent_id=claude["id"], tier="paid")
    _policy(client, org["headers"], actor_type="ai_user_agent", purpose="answering", tier="free")
    _policy(client, org["headers"], actor_type="ai_user_agent", tier="forbidden")
    _policy(client, org["headers"], actor_type="search_crawler", tier="paid")
    _policy(client, org["headers"], actor_type="ai_crawler", purpose="preview", tier="unset")
    org_id = uuid.UUID(client.get("/api/v1/auth/me", headers=org["headers"]).json()["organization"]["id"])
    listed = _agents(client, org["headers"])["items"]
    assert len(listed) >= 5
    for a in listed:
        expected = access_policy_service.evaluate(db_session, organization_id=org_id, agent_id=uuid.UUID(a["id"]),
                                                  actor_type=ActorType(a["actor_type"]),
                                                  purpose=AccessPurpose(a["declared_purpose"])).tier.value
        assert a["decision"] == expected, a["signature"]
    assert {pick_["signature"]: pick_["decision"] for pick_ in listed}["GPTBot"] == "forbidden"
    assert {pick_["signature"]: pick_["decision"] for pick_ in listed}["ClaudeBot"] == "paid"


def test_the_rule_table_is_read_once_for_the_whole_list(client: TestClient, adapter_credential, db_engine) -> None:
    org = adapter_credential["org"]
    _see(client, adapter_credential["headers"], GPTBOT_UA, CLAUDEBOT_UA, CLAUDE_USER_UA, NOVEL_UA)
    _policy(client, org["headers"], actor_type="ai_crawler", tier="forbidden")
    seen = []

    def count(conn, cursor, statement, *args):
        if "access_policies" in statement:
            seen.append(statement)

    event.listen(db_engine, "before_cursor_execute", count)
    try:
        assert len(_agents(client, org["headers"])["items"]) >= 4
    finally:
        event.remove(db_engine, "before_cursor_execute", count)
    assert len(seen) == 1
