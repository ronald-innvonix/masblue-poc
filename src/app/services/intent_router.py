from typing import Literal

Intent = Literal["field_help", "policy_qa", "handoff"]

FIELD_TERMS = {"field", "form", "deductible", "limit", "coverage amount"}
POLICY_TERMS = {"covered", "coverage", "policy", "claim", "exclusion", "water damage", "damage"}
HANDOFF_TERMS = {
    "speak to someone",
    "talk to someone",
    "real person",
    "human",
    "speak to a human",
    "talk to a human",
    "human agent",
    "representative",
    "approve my claim",
    "deny my claim",
    "claim decision",
    "claim status",
    "decide whether",
    "will my claim be paid",
    "will this claim be paid",
    "is my claim going to be paid",
    "is my claim approved",
    "has my claim been approved",
    "will my claim be covered",
    "should i file a claim",
    "file a claim for me",
    "another user's policy",
    "someone else's policy",
    "another person's policy",
    "other user's policy",
    "neighbor's policy",
    "friend's policy",
    "coworker's policy",
    "spouse's policy",
    "wife's policy",
    "husband's policy",
    "partner's policy",
}


def route_intent(message: str) -> Intent:
    normalized = message.lower().replace("’", "'")
    if any(term in normalized for term in HANDOFF_TERMS):
        return "handoff"
    asks_definition = any(
        phrase in normalized for phrase in ("what does", "meaning", "mean", "define", "explain")
    )
    mentions_field = any(term in normalized for term in FIELD_TERMS)
    mentions_form_field = "field" in normalized or "form" in normalized
    deductible_definition = (
        "what is" in normalized
        and "deductible" in normalized
        and not any(term in normalized for term in POLICY_TERMS)
    )
    if mentions_form_field or (mentions_field and asks_definition) or deductible_definition:
        return "field_help"
    if any(term in normalized for term in POLICY_TERMS):
        return "policy_qa"
    return "handoff"
