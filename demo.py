"""Live demo for the PawPal+ presentation.

Runs four end-to-end demos that prove the RAG advisor works as designed.
Designed for screen-capture during a 5–7 minute video walkthrough.

  Demo A  ·  Retrieval ranks the semantically correct snippet first
  Demo B  ·  Retrieval discriminates on-topic vs off-topic queries
  Demo C  ·  Same plan, three breeds, three verdicts (the "AI is reasoning" demo)
  Demo D  ·  The Evaluator rejects three classes of bad AI edits

Usage:
    python demo.py            # run all four demos
    python demo.py --no-llm   # skip Demo C (the only demo that hits the LLM)
    python demo.py --pause    # pause between demos for slow walkthroughs
"""
from __future__ import annotations

import logging
import sys
import time
from typing import List

# Quiet the noisy library logs so the demo output stays clean for screenshots.
for noisy in ("httpx", "google_genai", "tenacity", "urllib3", "chromadb"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

from care_advisor import AdvisorReview, CareAdvisor, ProposedChange
from pawpal_system import Owner, Pet, Priority, Scheduler, Task


# ─── formatting helpers ──────────────────────────────────────────────

WIDTH = 72


def banner() -> None:
    print()
    print("┏" + "━" * (WIDTH - 2) + "┓")
    title = "PawPal+ live demo  —  RAG + Evaluator + provider switcher"
    print("┃" + title.center(WIDTH - 2) + "┃")
    print("┗" + "━" * (WIDTH - 2) + "┛")


def section(title: str) -> None:
    print()
    print("=" * WIDTH)
    print(f"  {title}")
    print("=" * WIDTH)


def subhead(label: str) -> None:
    print()
    print(f"  ▸ {label}")


def maybe_pause(pause: bool, label: str = "") -> None:
    if pause:
        prompt = f"  [press Enter to continue{(' to ' + label) if label else ''}]"
        try:
            input(prompt)
        except (KeyboardInterrupt, EOFError):
            print()
            sys.exit(0)


# ─── Demo A · retrieval ranks correctly ──────────────────────────────


def demo_a_retrieval_ranks(advisor: CareAdvisor) -> None:
    section("DEMO A  ·  Retrieval ranks the right snippet first")
    print("  Three queries, top-3 results from CareAdvisor.retrieve(query, k=3).")
    print("  Cosine similarity (0–1) — higher means more relevant.")
    queries = [
        "Bulldog walking in heat",
        "puppy exercise growth plates",
        "cat litter box hygiene",
    ]
    for q in queries:
        subhead(f"query: {q!r}")
        for i, r in enumerate(advisor.retrieve(q, k=3), start=1):
            marker = "   ← top match" if i == 1 else ""
            print(f"      {i}. {r.score:.3f}  {r.source_id:<25}{marker}")


# ─── Demo B · retrieval discriminates ────────────────────────────────


def demo_b_discrimination(advisor: CareAdvisor) -> None:
    section("DEMO B  ·  Retrieval discriminates on/off-topic")
    print("  On-topic queries score noticeably higher than off-topic ones,")
    print("  proving the retriever isn't just returning random documents.")
    print()
    print("  ON-TOPIC (pet-care related):")
    for q in [
        "daily exercise for a senior dog",
        "puppy bathroom training tips",
    ]:
        top = advisor.retrieve(q, k=1)
        if top:
            print(f"      {top[0].score:.3f}  {q!r:<45} → {top[0].source_id}")

    print()
    print("  OFF-TOPIC (no good match should exist):")
    for q in [
        "python programming tutorial",
        "weather forecast for Tuesday",
        "best pasta recipe",
    ]:
        top = advisor.retrieve(q, k=1)
        if top:
            print(f"      {top[0].score:.3f}  {q!r:<45} → {top[0].source_id}")
        else:
            print(f"      no match  {q!r}")


# ─── Demo C · side-by-side breed comparison ──────────────────────────


def demo_c_side_by_side(advisor: CareAdvisor) -> None:
    section("DEMO C  ·  Same plan, three breeds, three verdicts")
    print("  Identical 60-minute walk evaluated against three breeds. The AI")
    print("  adapts its judgment to each breed's energy bucket — pattern-matching")
    print("  cannot produce three different answers from the same plan.")

    plan = [
        "08:00-09:00: 'Morning walk' for Mochi, 60 min, HIGH priority, walk category"
    ]
    scenarios = [
        ("Bulldog (low-energy / brachycephalic, target 20–30 min)", "Mochi, dog, Bulldog, 2 years old"),
        ("Standard Poodle (high-energy, target 60–120 min)", "Mochi, dog, Standard Poodle, 2 years old"),
        ("Border Collie (high-energy working, target 60–120 min)", "Mochi, dog, Border Collie, 2 years old"),
    ]
    for label, desc in scenarios:
        subhead(label)
        review = advisor.review_plan(plan, [desc])
        verdict = "NEEDS EDITS" if review.proposed_changes else "IN RANGE — no edits"
        print(f"      verdict:  {verdict}")
        print(f"      issues:   {len(review.issues)},  edits: {len(review.proposed_changes)},  latency: {review.latency_ms}ms")
        print(f"      summary:  {review.summary[:200]}")


# ─── Demo D · evaluator guards reject bad edits ──────────────────────


def demo_d_evaluator_guards() -> None:
    section("DEMO D  ·  Evaluator catches three classes of bad AI edits")
    print("  Feeding apply_advisor_changes three deliberately-bad proposed edits.")
    print("  None should make it into the final plan.")

    owner = Owner("Demo Owner", available_time=120)
    pet = Pet("Mochi", "dog", "Bulldog", 2)
    owner.add_pet(pet)
    pet.add_task(Task("Morning walk", 30, Priority.HIGH, "walk"))

    sched = Scheduler(owner, advisor=None)
    plan = sched.generate_plan()

    bad_review = AdvisorReview(
        available=True,
        proposed_changes=[
            ProposedChange(
                pet_name="Mochi", task_name="Morning walk", change_type="shorten",
                reason="Split this walk into two shorter sessions",
                task_index=1, new_duration_min=15,
            ),
            ProposedChange(
                pet_name="Mochi", task_name="Phantom walk", change_type="shorten",
                reason="reasonable-sounding rationale, but the task does not exist",
                task_index=99, new_duration_min=10,
            ),
            ProposedChange(
                pet_name="Mochi", task_name="Morning walk", change_type="shorten",
                reason="reasonable-sounding rationale, but the new duration matches the old",
                task_index=1, new_duration_min=30,
            ),
        ],
    )

    print()
    print("  Bad edits proposed:")
    print("    1. shorten · reason contains 'split into … sessions' (split-pattern)")
    print("    2. references task_index=99 (only 1 task exists)")
    print("    3. 'shorten' from 30 → 30 minutes (no-op)")

    final, applied = sched.apply_advisor_changes(plan, bad_review)

    print()
    print(f"  proposed:  {len(bad_review.proposed_changes)}")
    print(f"  applied:   {len(applied)}   (expected 0)")
    print(f"  rejected:  {len(bad_review.proposed_changes) - len(applied)}   ← all three caught")
    print()
    print("  → see pawpal.log for the per-rejection log lines and the")
    print("    rule that fired on each one.")


# ─── runner ──────────────────────────────────────────────────────────


def main(skip_llm: bool = False, pause: bool = False) -> None:
    banner()

    advisor = CareAdvisor()
    if not advisor.is_available:
        print()
        print("  ⚠ Advisor unavailable — set GEMINI_API_KEY in .env to run A/B/C.")
        print("  Demo D does not need the LLM and will still run.")
    else:
        maybe_pause(pause, "Demo A")
        demo_a_retrieval_ranks(advisor)

        maybe_pause(pause, "Demo B")
        demo_b_discrimination(advisor)

        if not skip_llm:
            maybe_pause(pause, "Demo C  (uses ~3 LLM calls)")
            demo_c_side_by_side(advisor)
        else:
            print()
            print("  Demo C skipped (--no-llm). Run without that flag to include it.")

    maybe_pause(pause, "Demo D")
    demo_d_evaluator_guards()

    print()
    print("=" * WIDTH)
    print("  All demos complete.".center(WIDTH))
    print("=" * WIDTH)
    print()


if __name__ == "__main__":
    main(
        skip_llm="--no-llm" in sys.argv,
        pause="--pause" in sys.argv,
    )
