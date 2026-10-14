"""
THE canonical actor signature table (Phase 13, ADR-076).

ONE TABLE, TWO RUNTIMES

`AIOL_Actors::$signatures` (PHP) and this module (Python) must agree, or
the same crawler gets classified one way at the edge and another way in
the report, and the merchant's access policy silently stops matching.

The rule is therefore: **this file is canonical, the plugin mirrors it,
and a conformance test asserts the two lists are identical.** The plugin
keeps a local copy rather than calling Core on every request because the
classification runs in `template_redirect` on every page load and a
network round trip there is not acceptable — but a copy that can drift is
a bug waiting to happen, so the drift is made a test failure instead of a
code review responsibility.

See `cloud-core/tests/test_phase13_signature_parity.py` and
`wordpress-plugin/tests/test-signature-parity.php`.

PURPOSE IS ASSIGNED, NOT GUESSED

Each signature carries the purpose its operator has publicly documented.
Where an operator documents more than one use for one agent, or documents
none, the purpose is `UNKNOWN` — and `UNKNOWN` is a perfectly usable
policy subject, so nothing is lost by refusing to guess. Notably
`GPTBot`/`ClaudeBot`/`CCBot` are TRAINING and `ChatGPT-User`/`Claude-User`/
`Perplexity-User` are ANSWERING; that split is the entire reason the
owner can say "no to training, yes to answering" and have it mean
something.

This list is a seed, not a boundary. Anything not in it still gets an
`AiAgent` row on first sight (`AgentRegistrationOrigin.DISCOVERED`).
"""

from dataclasses import dataclass

from app.models.enums import AccessPurpose, ActorType


@dataclass(frozen=True)
class Signature:
    needle: str
    display_name: str
    vendor: str | None
    actor_type: ActorType
    purpose: AccessPurpose


# Ordered: matching is first-hit, so a more specific needle must precede a
# less specific one that would also match it. `Claude-SearchBot` before
# `ClaudeBot` is not cosmetic - `stripos` would otherwise classify a
# user-driven fetch as a training crawler and the merchant's "block
# training" rule would block their own customers' questions.
SIGNATURES: tuple[Signature, ...] = (
    # --- user-driven: a person asked something right now -------------------
    Signature("Claude-SearchBot", "Claude-SearchBot", "Anthropic", ActorType.AI_USER_AGENT, AccessPurpose.ANSWERING),
    Signature("Claude-User", "Claude-User", "Anthropic", ActorType.AI_USER_AGENT, AccessPurpose.ANSWERING),
    Signature("ChatGPT-User", "ChatGPT-User", "OpenAI", ActorType.AI_USER_AGENT, AccessPurpose.ANSWERING),
    Signature("Perplexity-User", "Perplexity-User", "Perplexity", ActorType.AI_USER_AGENT, AccessPurpose.ANSWERING),
    Signature("MistralAI-User", "MistralAI-User", "Mistral", ActorType.AI_USER_AGENT, AccessPurpose.ANSWERING),
    Signature("DuckAssistBot", "DuckAssistBot", "DuckDuckGo", ActorType.AI_USER_AGENT, AccessPurpose.ANSWERING),

    # --- AI crawlers: collecting for later ---------------------------------
    Signature("OAI-SearchBot", "OAI-SearchBot", "OpenAI", ActorType.AI_CRAWLER, AccessPurpose.SEARCH_INDEXING),
    Signature("GPTBot", "GPTBot", "OpenAI", ActorType.AI_CRAWLER, AccessPurpose.TRAINING),
    Signature("ClaudeBot", "ClaudeBot", "Anthropic", ActorType.AI_CRAWLER, AccessPurpose.TRAINING),
    Signature("anthropic-ai", "anthropic-ai", "Anthropic", ActorType.AI_CRAWLER, AccessPurpose.TRAINING),
    Signature("PerplexityBot", "PerplexityBot", "Perplexity", ActorType.AI_CRAWLER, AccessPurpose.SEARCH_INDEXING),
    Signature("Google-Extended", "Google-Extended", "Google", ActorType.AI_CRAWLER, AccessPurpose.TRAINING),
    Signature("Applebot-Extended", "Applebot-Extended", "Apple", ActorType.AI_CRAWLER, AccessPurpose.TRAINING),
    Signature("Bytespider", "Bytespider", "ByteDance", ActorType.AI_CRAWLER, AccessPurpose.TRAINING),
    Signature("CCBot", "CCBot", "Common Crawl", ActorType.AI_CRAWLER, AccessPurpose.TRAINING),
    Signature("Amazonbot", "Amazonbot", "Amazon", ActorType.AI_CRAWLER, AccessPurpose.UNKNOWN),
    Signature("meta-externalagent", "meta-externalagent", "Meta", ActorType.AI_CRAWLER, AccessPurpose.TRAINING),
    Signature("FacebookBot", "FacebookBot", "Meta", ActorType.AI_CRAWLER, AccessPurpose.TRAINING),
    Signature("Diffbot", "Diffbot", "Diffbot", ActorType.AI_CRAWLER, AccessPurpose.UNKNOWN),
    Signature("YouBot", "YouBot", "You.com", ActorType.AI_CRAWLER, AccessPurpose.SEARCH_INDEXING),
    Signature("cohere-ai", "cohere-ai", "Cohere", ActorType.AI_CRAWLER, AccessPurpose.TRAINING),
    Signature("Timpibot", "Timpibot", "Timpi", ActorType.AI_CRAWLER, AccessPurpose.TRAINING),
    Signature("omgili", "omgili", "Webz.io", ActorType.AI_CRAWLER, AccessPurpose.TRAINING),
    Signature("ImagesiftBot", "ImagesiftBot", "Hive", ActorType.AI_CRAWLER, AccessPurpose.TRAINING),

    # --- agents acting for a person ----------------------------------------
    Signature("OpenAI-Operator", "OpenAI Operator", "OpenAI", ActorType.AGENT_TOOL, AccessPurpose.AGENT_ACTION),
    Signature("Claude-Agent", "Claude Agent", "Anthropic", ActorType.AGENT_TOOL, AccessPurpose.AGENT_ACTION),

    # --- conventional search -----------------------------------------------
    Signature("Googlebot", "Googlebot", "Google", ActorType.SEARCH_CRAWLER, AccessPurpose.SEARCH_INDEXING),
    Signature("bingbot", "Bingbot", "Microsoft", ActorType.SEARCH_CRAWLER, AccessPurpose.SEARCH_INDEXING),
    Signature("DuckDuckBot", "DuckDuckBot", "DuckDuckGo", ActorType.SEARCH_CRAWLER, AccessPurpose.SEARCH_INDEXING),
    Signature("Slurp", "Yahoo Slurp", "Yahoo", ActorType.SEARCH_CRAWLER, AccessPurpose.SEARCH_INDEXING),
    Signature("YandexBot", "YandexBot", "Yandex", ActorType.SEARCH_CRAWLER, AccessPurpose.SEARCH_INDEXING),
    Signature("Baiduspider", "Baiduspider", "Baidu", ActorType.SEARCH_CRAWLER, AccessPurpose.SEARCH_INDEXING),

    # --- link preview -------------------------------------------------------
    Signature("Twitterbot", "Twitterbot", "X", ActorType.SEARCH_CRAWLER, AccessPurpose.PREVIEW),
    Signature("Slackbot", "Slackbot", "Slack", ActorType.SEARCH_CRAWLER, AccessPurpose.PREVIEW),
    Signature("WhatsApp", "WhatsApp", "Meta", ActorType.SEARCH_CRAWLER, AccessPurpose.PREVIEW),
    Signature("TelegramBot", "TelegramBot", "Telegram", ActorType.SEARCH_CRAWLER, AccessPurpose.PREVIEW),
)


def match(user_agent: str) -> Signature | None:
    """First-hit, case-insensitive substring match. Returns None for
    anything unrecognised — which is a normal outcome, not an error."""
    ua = user_agent.strip()
    if not ua:
        return None
    lowered = ua.lower()
    for sig in SIGNATURES:
        if sig.needle.lower() in lowered:
            return sig
    return None


def needles() -> list[str]:
    """Used by the parity test against the plugin's copy."""
    return [s.needle for s in SIGNATURES]
