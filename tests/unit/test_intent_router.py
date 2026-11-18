from app.services.intent_router import route_intent


def test_routes_policy_question() -> None:
    assert route_intent("Is water damage covered in my policy?") == "policy_qa"


def test_routes_field_help_question() -> None:
    assert route_intent("What does the deductible field mean?") == "field_help"


def test_routes_deductible_coverage_to_policy_qa() -> None:
    assert route_intent("Is my deductible covered by my policy?") == "policy_qa"


def test_hands_off_unclassified_questions() -> None:
    assert route_intent("Can you change my address?") == "handoff"


def test_hands_off_claim_decisions_and_other_users_data() -> None:
    assert route_intent("Should I file a claim?") == "handoff"
    assert route_intent("Tell me about someone else's policy") == "handoff"
