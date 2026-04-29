"""Advisor (end-to-end) accuracy eval — does the LLM get the answer right?

Retrieval eval (eval_retrieval.py) checks whether the right snippet is
fetched. This eval goes one step further: the LLM is given the plan and
the retrieved snippets, and we assert properties of its actual response.

Each scenario defines the inputs (plan + pet descriptions) and a set of
named CHECKS. A check is a labeled boolean function over the AdvisorReview.
The script reports pass/fail per check and an overall pass rate, so a
failure is debuggable to the specific behavior that broke.

Run from the project root:
    python evals/eval_advisor.py

Uses one LLM call per scenario (~5 calls total). Requires GEMINI_API_KEY
or GROQ_API_KEY.
"""
from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Tuple

# Quiet the noisy library logs so the eval table is readable.
for noisy in ("httpx", "google_genai", "tenacity", "urllib3", "chromadb"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from care_advisor import AdvisorReview, CareAdvisor  # noqa: E402


# ─── eval scenarios ──────────────────────────────────────────────────


@dataclass
class Scenario:
    name: str
    plan_lines: List[str]
    pet_descriptions: List[str]
    checks: List[Tuple[str, Callable[[AdvisorReview], bool]]] = field(default_factory=list)


def _no_temp_speculation(r: AdvisorReview) -> bool:
    """Rule 3 — model must not invent unstated facts. Issues should not
    reference 'hot weather' / 'in summer' / 'if temperature' when the
    plan doesn't include any temperature info."""
    flags = ("if it's hot", "in hot weather", "if the temperature",
             "during summer", "above 80", "above 90", "if it's a hot")
    haystack = " ".join((i.issue + " " + i.recommendation).lower()
                        for i in r.issues)
    return not any(f in haystack for f in flags)


def _all_changes_have_task_index(r: AdvisorReview) -> bool:
    """Schema rule — every proposed_change must include a 1-based task_index."""
    return all(c.task_index is not None and c.task_index >= 1
               for c in r.proposed_changes)


def _all_issues_cite_a_real_source(r: AdvisorReview) -> bool:
    """Rule 6 — every issue must include at least one snippet citation, and
    the citation must match a snippet that was actually retrieved."""
    retrieved = set(r.retrieved_sources)
    return all(
        i.citations and any(c in retrieved for c in i.citations)
        for i in r.issues
    )


def _summary_matches_emitted_actions(r: AdvisorReview) -> bool:
    """Rule 12 — if the summary uses past-tense action language, there must
    be at least one matching proposed_change. Simple keyword check."""
    action_words = ("has been shortened", "has been lengthened",
                    "has been removed", "has been rescheduled",
                    "was shortened", "was lengthened", "was removed",
                    "was rescheduled")
    summary = (r.summary or "").lower()
    if any(w in summary for w in action_words):
        return len(r.proposed_changes) > 0
    return True  # no action verbs claimed → vacuously true


SCENARIOS: List[Scenario] = [
    Scenario(
        name="In-range Toy Poodle (20 min, target 20–30)",
        plan_lines=["08:00-08:20: 'Morning walk' for Mochi, 20 min, HIGH priority, walk category"],
        pet_descriptions=["Mochi, dog, Toy Poodle, 1 years old"],
        checks=[
            ("no edits applied (in-range)", lambda r: len(r.proposed_changes) == 0),
            ("no issues raised at all",     lambda r: len(r.issues) == 0),
            ("dog_exercise_needs retrieved", lambda r: "dog_exercise_needs" in r.retrieved_sources),
            ("summary doesn't claim action",
                lambda r: _summary_matches_emitted_actions(r)),
        ],
    ),
    Scenario(
        name="Over-target Bulldog (70 min, target 20–30)",
        plan_lines=[
            "unscheduled: 'Morning walk' for Toby, 20 min, HIGH priority, walk category",
            "unscheduled: 'Morning walk' for Toby, 50 min, HIGH priority, walk category",
        ],
        pet_descriptions=["Toby, dog, Bulldog, 2 years old"],
        checks=[
            ("at least one issue raised",   lambda r: len(r.issues) >= 1),
            ("severity is medium or high",  lambda r: any(i.severity in ("medium", "high") for i in r.issues)),
            ("issue cites dog_exercise_needs",
                lambda r: any("dog_exercise_needs" in i.citations for i in r.issues)),
            ("no temperature speculation",  _no_temp_speculation),
            ("issues all cite a retrieved source",
                _all_issues_cite_a_real_source),
        ],
    ),
    Scenario(
        name="Under-target high-energy GSP (20 min, target 60–120)",
        plan_lines=["unscheduled: 'Morning walk' for Yogi, 20 min, HIGH priority, walk category"],
        pet_descriptions=["Yogi, dog, German Shorthaired Pointer, 1 years old"],
        checks=[
            ("flags as too short OR emits a lengthen",
                lambda r: len(r.issues) >= 1 or any(c.change_type == "lengthen" for c in r.proposed_changes)),
            ("any lengthen edit has new_duration ≥ 60",
                lambda r: all(
                    c.change_type != "lengthen" or (c.new_duration_min and c.new_duration_min >= 60)
                    for c in r.proposed_changes
                )),
            ("dog_exercise_needs retrieved", lambda r: "dog_exercise_needs" in r.retrieved_sources),
        ],
    ),
    Scenario(
        name="Multi-pet retrieval (puppy + senior)",
        plan_lines=[
            "07:00-07:15: 'Morning brush' for Whiskers, 15 min, HIGH priority, grooming category",
            "08:00-08:30: 'Morning walk' for Rex, 30 min, HIGH priority, walk category",
        ],
        pet_descriptions=[
            "Whiskers, cat, Persian, 14 years old",
            "Rex, dog, Border Collie, 8 months old",
        ],
        checks=[
            ("retrieved senior_pet_care for the senior cat",
                lambda r: "senior_pet_care" in r.retrieved_sources),
            ("retrieved puppy_kitten_care for the puppy",
                lambda r: "puppy_kitten_care" in r.retrieved_sources),
        ],
    ),
    Scenario(
        name="Schema integrity (any over-target case)",
        plan_lines=[
            "unscheduled: 'Morning walk' for Toby, 90 min, HIGH priority, walk category",
        ],
        pet_descriptions=["Toby, dog, Bulldog, 3 years old"],
        checks=[
            ("every proposed_change has a task_index",
                _all_changes_have_task_index),
            ("issues all cite a retrieved source",
                _all_issues_cite_a_real_source),
            ("summary doesn't claim un-emitted actions",
                _summary_matches_emitted_actions),
        ],
    ),
]


# ─── runner ──────────────────────────────────────────────────────────


def run_eval(advisor: CareAdvisor) -> None:
    if not advisor.is_available:
        print("✗ Advisor unavailable. Set GEMINI_API_KEY and try again.")
        sys.exit(1)

    n_scenarios = len(SCENARIOS)
    total_checks = 0
    total_passes = 0

    print()
    print("=" * 92)
    print(f"  Advisor end-to-end eval  ·  {n_scenarios} scenarios  ·  one LLM call per scenario")
    print("=" * 92)

    for i, sc in enumerate(SCENARIOS, start=1):
        print()
        print(f"  Scenario {i}: {sc.name}")
        review = advisor.review_plan(sc.plan_lines, sc.pet_descriptions)
        if not review.available:
            print(f"    ✗ advisor call failed: {review.error}")
            for label, _ in sc.checks:
                print(f"      ✗ {label}  (skipped — advisor unavailable)")
                total_checks += 1
            continue

        print(f"    [latency {review.latency_ms} ms · "
              f"issues {len(review.issues)} · "
              f"edits {len(review.proposed_changes)}]")
        for label, check in sc.checks:
            total_checks += 1
            try:
                ok = bool(check(review))
            except Exception as exc:
                ok = False
                label = f"{label}  (raised: {type(exc).__name__})"
            mark = "✓" if ok else "✗"
            print(f"      {mark} {label}")
            if ok:
                total_passes += 1

    pct = (total_passes / total_checks * 100) if total_checks else 0.0
    print()
    print("-" * 92)
    print(f"  Total: {total_passes}/{total_checks} checks passed across {n_scenarios} scenarios"
          f"  ({pct:.1f}%)")
    print("-" * 92)
    print()


def main() -> None:
    advisor = CareAdvisor()
    run_eval(advisor)


if __name__ == "__main__":
    main()
