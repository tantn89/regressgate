"""A toy support bot with the failure modes real LLM apps have, and no API key needed.

- most answers are stable;
- one answer is flaky: it sometimes leaves out the refund window, like a model that
  phrases things differently from run to run;
- setting SUPPORT_BOT_VARIANT=broken simulates a bad prompt change that breaks one
  answer for good, so you can watch the gate catch it.
"""

from __future__ import annotations

import os
import random

KNOWLEDGE = {
    "hours": "We are open 9am to 6pm, Monday to Friday.",
    "shipping": "Standard shipping takes 3 to 5 business days and costs $4.99.",
    "warranty": "Every device has a 2-year warranty covering manufacturing defects.",
    "password": "Use 'Forgot password' on the sign-in page to get a reset link by email.",
    "cancel": "You can cancel a subscription any time under Settings, then Billing.",
}
SOURCES = {topic: {"doc": f"help/{topic}.md"} for topic in KNOWLEDGE}


def answer(question: str) -> dict[str, object]:
    q = question.lower()
    broken = os.environ.get("SUPPORT_BOT_VARIANT") == "broken"
    if "refund" in q:
        # Flaky by design: one phrasing omits the 30-day window.
        text = random.choice([
            "Refunds are available within 30 days of purchase.",
            "Refunds are available within 30 days of purchase if the item is unused.",
            "You can request a refund from your order page.",
        ])
        return {"output": text, "citations": [{"doc": "help/refunds.md"}], "cost_usd": 0.0004}
    for topic, text in KNOWLEDGE.items():
        if topic in q:
            if broken and topic == "warranty":
                text = "Devices are covered by our standard warranty."
            return {"output": text, "citations": [SOURCES[topic]], "cost_usd": 0.0004}
    return {"output": "I don't have information about that in the help center.",
            "cost_usd": 0.0002}
