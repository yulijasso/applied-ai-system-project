"""RAG retrieval accuracy eval — gold-standard query → source_id pairs.

For each query, retrieve the top-k snippets and check whether the
hand-labeled "right answer" appears at rank 1, in the top 3, or at all.
Reports the three canonical RAG metrics: Hit@1, Hit@3, and MRR
(Mean Reciprocal Rank). A per-query table makes failures easy to debug.

Run from the project root:
    python evals/eval_retrieval.py

Requires GEMINI_API_KEY (used to embed the queries; snippet embeddings
are reused from the existing ChromaDB cache).
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import List, Tuple

# Quiet the noisy library logs so the eval table is readable.
for noisy in ("httpx", "google_genai", "tenacity", "urllib3", "chromadb"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

# Make sure the project root is on the path so `from care_advisor import …`
# works whether the script is run from the root or from inside evals/.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from care_advisor import CareAdvisor  # noqa: E402


# ─── Hand-labeled gold set ───────────────────────────────────────────
# Each entry is (query, expected_source_id). Queries deliberately span
# every snippet in `knowledge/` and include paraphrases / synonyms to
# stress-test semantic recall (not just exact-keyword matching).

GOLD: List[Tuple[str, str]] = [
    # heat_safety_walking
    ("Bulldog walking in summer heat",                      "heat_safety_walking"),
    ("is it safe to walk a dog in 90 degree weather",       "heat_safety_walking"),
    ("hot pavement test for dog paws",                      "heat_safety_walking"),

    # dog_exercise_needs
    ("how much exercise does a Border Collie need",         "dog_exercise_needs"),
    ("daily walk minutes for a Bulldog",                    "dog_exercise_needs"),
    ("Toy Poodle exercise requirements",                    "dog_exercise_needs"),

    # puppy_kitten_care
    ("when can a puppy meet other dogs after vaccines",     "puppy_kitten_care"),
    ("kitten socialization sensitive period",               "puppy_kitten_care"),

    # litter_box_hygiene
    ("how often to scoop the litter box",                   "litter_box_hygiene"),
    ("how many litter boxes for two cats",                  "litter_box_hygiene"),

    # dental_care
    ("how often should I brush my dog's teeth",             "dental_care"),

    # grooming_frequency
    ("anal gland expression frequency",                     "grooming_frequency"),

    # senior_pet_care
    ("senior dog joint pain low impact exercise",           "senior_pet_care"),

    # feeding_schedule
    ("feeding schedule for a diabetic cat",                 "feeding_schedule"),

    # bloat_risk_post_meal
    ("walking a deep-chested dog after a meal",             "bloat_risk_post_meal"),

    # cat_enrichment
    ("indoor cat enrichment ideas play sessions",           "cat_enrichment"),

    # preventive_medications
    ("monthly heartworm prevention dog",                    "preventive_medications"),

    # medication_timing
    ("doxycycline esophageal stricture in cats",            "medication_timing"),
]


# ─── eval runner ─────────────────────────────────────────────────────


def run_eval(advisor: CareAdvisor, k: int = 5) -> None:
    if not advisor.is_available:
        print("✗ Advisor unavailable. Set GEMINI_API_KEY and try again.")
        sys.exit(1)

    n = len(GOLD)
    hit_at_1 = 0
    hit_at_3 = 0
    rr_sum = 0.0  # sum of reciprocal ranks; MRR = rr_sum / n

    # Header
    print()
    print("=" * 96)
    print(f"  RAG retrieval eval  ·  {n} labeled queries  ·  top-{k} retrieval depth")
    print("=" * 96)
    print()
    print(f"  {'#':>2}  {'query':<48}  {'expected':<22}  {'top match':<22}  rank")
    print(f"  {'--':>2}  {'-' * 48}  {'-' * 22}  {'-' * 22}  ----")

    rows: List[Tuple[int, str, str, str, int]] = []
    for i, (query, expected) in enumerate(GOLD, start=1):
        results = advisor.retrieve(query, k=k)
        ranked_ids = [r.source_id for r in results]
        rank = ranked_ids.index(expected) + 1 if expected in ranked_ids else 0
        rr_sum += (1.0 / rank) if rank else 0.0
        if rank == 1:
            hit_at_1 += 1
        if 1 <= rank <= 3:
            hit_at_3 += 1
        top = ranked_ids[0] if ranked_ids else "—"
        rank_str = f"@{rank}" if rank else "MISS"
        rows.append((i, query, expected, top, rank))
        print(f"  {i:>2}  {query[:48]:<48}  {expected:<22}  {top:<22}  {rank_str}")

    # Summary
    mrr = rr_sum / n
    print()
    print("-" * 96)
    print(f"  Hit@1  (top-1 correct):     {hit_at_1:>2}/{n}    ({hit_at_1 / n * 100:5.1f}%)")
    print(f"  Hit@3  (correct in top-3):  {hit_at_3:>2}/{n}    ({hit_at_3 / n * 100:5.1f}%)")
    print(f"  MRR    (mean reciprocal):   {mrr:.3f}     (1.000 = always rank 1)")
    print("-" * 96)

    # Failures
    misses = [(i, q, e, t, r) for (i, q, e, t, r) in rows if r != 1]
    if misses:
        print()
        print(f"  {len(misses)} queries did not rank the expected snippet at #1:")
        for i, q, e, t, r in misses:
            tag = f"@{r}" if r else "MISS"
            print(f"    #{i:<2} {tag:<5}  query={q!r}  expected={e}  got={t}")
    else:
        print()
        print("  ✓ Every query ranked the expected snippet at #1.")
    print()


def main() -> None:
    advisor = CareAdvisor()
    run_eval(advisor)


if __name__ == "__main__":
    main()
