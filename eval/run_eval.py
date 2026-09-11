"""
Phase 7 (started early, on purpose): runs classify_email against the labelled
fixture set and reports per-category accuracy + urgency recall, per the
project plan's eval table. This only depends on Phase 2 tools, so it's
useful right now for judging classifier prompt quality before the full
agent loop (Phase 3) exists.

Usage:
    python -m eval.run_eval                 # uses real Claude (needs ANTHROPIC_API_KEY in .env)
    python -m eval.run_eval --fake           # uses FakeLLMClient (no API key, sanity check only)

Escalation precision/recall and draft-quality scoring get added once
Phase 3/4 exist, since those depend on the full loop's confidence-threshold
logic, not just the raw classifier.
"""
from __future__ import annotations

import argparse
from collections import defaultdict

from dotenv import load_dotenv

from agent.llm_client import AnthropicLLMClient, FakeLLMClient
from agent.schemas import ClassifyInput
from agent.tools.classify import classify_email
from ingest.fixture_loader import load_fixtures_with_labels


def run(llm) -> None:
    pairs = load_fixtures_with_labels()

    per_category_total = defaultdict(int)
    per_category_correct = defaultdict(int)
    urgency_total = defaultdict(int)
    urgency_correct = defaultdict(int)
    errors = []

    for email, expected in pairs:
        result = classify_email(ClassifyInput(subject=email.subject, body=email.body), llm=llm)

        exp_cat = expected["category"]
        exp_urg = expected["urgency"]
        per_category_total[exp_cat] += 1
        urgency_total[exp_urg] += 1

        if hasattr(result, "category"):  # ClassifyOutput, not ToolError
            if result.category == exp_cat:
                per_category_correct[exp_cat] += 1
            if result.urgency == exp_urg:
                urgency_correct[exp_urg] += 1
        else:
            errors.append((email.id, result))

    print("\n=== Classification accuracy by category ===")
    total_correct, total_n = 0, 0
    for cat in sorted(per_category_total):
        n = per_category_total[cat]
        correct = per_category_correct[cat]
        total_correct += correct
        total_n += n
        print(f"  {cat:<12} {correct:>2}/{n:<2}  ({correct/n:.0%})")
    print(f"  {'OVERALL':<12} {total_correct:>2}/{total_n:<2}  ({total_correct/total_n:.0%})")

    print("\n=== Urgency accuracy (watch 'high' recall especially) ===")
    for urg in ["high", "medium", "low"]:
        n = urgency_total.get(urg, 0)
        if n == 0:
            continue
        correct = urgency_correct.get(urg, 0)
        print(f"  {urg:<8} {correct:>2}/{n:<2}  ({correct/n:.0%})")

    if errors:
        print(f"\n=== {len(errors)} tool errors (not scored above) ===")
        for email_id, err in errors:
            print(f"  {email_id}: {err.message}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fake", action="store_true", help="use FakeLLMClient instead of real Claude")
    args = parser.parse_args()

    load_dotenv()

    if args.fake:
        print("Using FakeLLMClient (keyword heuristic) — sanity check only, not real accuracy.\n")
        llm = FakeLLMClient()
    else:
        try:
            llm = AnthropicLLMClient()
        except RuntimeError as e:
            print(f"Couldn't set up AnthropicLLMClient ({e})")
            print("Falling back to --fake mode.\n")
            llm = FakeLLMClient()

    run(llm)


if __name__ == "__main__":
    main()
