"""Evaluate responses from a running service using tests/eval/questions.yaml."""

import asyncio
import os
from pathlib import Path
from typing import TypedDict

import httpx
import yaml


class EvalCase(TypedDict):
    question: str
    expected_facts: list[str]
    should_refuse: bool


def _is_refusal(answer: str, intent: str) -> bool:
    lowered = answer.casefold()
    markers = (
        "couldn't find",
        "cannot make",
        "can't make",
        "only provide information for policies associated with your account",
        "contact your insurer",
    )
    return intent == "handoff" or any(marker in lowered for marker in markers)


async def run() -> int:
    user_id = os.environ.get("EVAL_USER_ID")
    if not user_id:
        raise RuntimeError("Set EVAL_USER_ID to run evaluations")
    base_url = os.environ.get("EVAL_API_URL", "http://127.0.0.1:8000").rstrip("/")
    api_key = os.environ.get("INTERNAL_API_KEY")
    if not api_key:
        raise RuntimeError("Set INTERNAL_API_KEY to run evaluations")
    policy_id = os.environ.get("EVAL_POLICY_ID")
    contents = yaml.safe_load(
        Path(__file__).with_name("questions.yaml").read_text(encoding="utf-8")
    )
    cases: list[EvalCase] = contents["questions"]
    accuracy_count = citation_count = refusal_count = 0
    async with httpx.AsyncClient(timeout=60) as client:
        for case in cases:
            request_data: dict[str, object] = {
                "user_id": user_id,
                "message": case["question"],
            }
            if policy_id:
                request_data["policy_id"] = policy_id
            response = await client.post(
                f"{base_url}/v1/chat",
                headers={"X-Internal-Key": api_key},
                json=request_data,
            )
            response.raise_for_status()
            result = response.json()
            answer = str(result["answer"])
            intent = str(result["intent"])
            expected_facts = case["expected_facts"]
            accuracy_count += int(
                all(fact.casefold() in answer.casefold() for fact in expected_facts)
            )
            citation_count += int(bool(result.get("sources")) or "Sources:" in answer)
            refusal_count += int(_is_refusal(answer, intent) == case["should_refuse"])
    total = len(cases)
    if total == 0:
        raise RuntimeError("Evaluation file contains no questions")
    print(f"Accuracy: {accuracy_count / total:.1%} ({accuracy_count}/{total})")
    print(f"Citation rate: {citation_count / total:.1%} ({citation_count}/{total})")
    print(f"Refusal correctness: {refusal_count / total:.1%} ({refusal_count}/{total})")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
