# PawPal+ Project Reflection

## 1. System Design

**Core user actions:**

1. **Add a pet** — The user can register a pet by entering its name, species, and any relevant details (age, breed, special needs). This is the foundation of the app; everything revolves around a specific pet.
2. **Add and edit care tasks** — The user can create care tasks for their pet (e.g., walk, feeding, medication, grooming) with a duration and priority level. They can also update or remove tasks as their pet's needs change.
3. **Generate a daily care plan** — The user can request an automatically generated daily schedule that organizes their tasks based on available time and priority, so they know exactly what to do and when.

**Building blocks (classes):**

1. **Owner** — Represents the pet owner / app user.
   - *Attributes:* name, available_time (minutes per day)
   - *Methods:* add_pet(), remove_pet()

2. **Pet** — Represents a pet belonging to the owner.
   - *Attributes:* name, species, breed, age
   - *Methods:* add_task(), remove_task(), get_tasks()

3. **Task** — A single care activity for a pet.
   - *Attributes:* name, duration (minutes), priority (high/medium/low), category (walk, feeding, meds, grooming, enrichment)
   - *Methods:* mark_complete(), edit()

4. **Scheduler** — Generates a daily care plan from tasks and constraints.
   - *Attributes:* tasks (list), available_time (minutes)
   - *Methods:* generate_plan(), get_explanation()

**a. Initial design**

- Briefly describe your initial UML design.
- What classes did you include, and what responsibilities did you assign to each?

The initial UML design includes four classes:
- **Owner** — Stores the user's name and how many minutes they have per day. Responsible for managing a list of pets (add/remove).
- **Pet** — Stores pet details (name, species, breed, age) and holds a list of care tasks. Responsible for adding, removing, and retrieving tasks.
- **Task** — Represents a single care activity with a name, duration, priority, and category. Can be marked complete or edited.
- **Scheduler** — Takes in a list of tasks and the owner's available time, then generates a prioritized daily plan and an explanation of why tasks were ordered that way.

Relationships: Owner owns one-to-many Pets, each Pet has one-to-many Tasks, and the Scheduler operates on a collection of Tasks.

**b. Design changes**

- Did your design change during implementation?
- If yes, describe at least one change and why you made it.

Yes, two changes were made after reviewing the skeleton with AI:
1. **Priority changed from `str` to `IntEnum`** — The original design used plain strings ("high", "medium", "low") for priority, which is error-prone and harder to sort. Switching to an `IntEnum` (HIGH=1, MEDIUM=2, LOW=3) makes the scheduler's sorting logic cleaner and prevents typos.
2. **Added `pet_name` field to Task** — The original Task had no reference to which pet it belonged to. When an owner has multiple pets and tasks are combined into one plan, the schedule needs to show which pet each task is for.

---

## 2. Scheduling Logic and Tradeoffs

**a. Constraints and priorities**

- What constraints does your scheduler consider (for example: time, priority, preferences)?
- How did you decide which constraints mattered most?

The scheduler considers three constraints, in order of importance:

1. **Scheduled time** — Tasks with a specific time slot (e.g., 07:00) are placed first and sorted chronologically. A vet appointment at 9 AM can't be moved, so fixed-time tasks always take priority in ordering.
2. **Priority level** (HIGH > MEDIUM > LOW) — Among tasks without a fixed time, high-priority tasks are scheduled before lower ones. This ensures critical care (medication, feeding) happens before optional activities (enrichment, grooming).
3. **Available time budget** — The scheduler only includes tasks that fit within the owner's daily available minutes. It greedily fills the schedule by trying shorter tasks first within each priority tier, maximizing the number of tasks that fit.

These constraints were ranked by real-world urgency: you can't miss a timed appointment, you shouldn't skip medication, and you work within the hours you actually have.

**b. Tradeoffs**

- Describe one tradeoff your scheduler makes.
- Why is that tradeoff reasonable for this scenario?

**Tradeoff: Conflict detection warns but does not resolve.**

The `_detect_conflicts()` method identifies overlapping time windows and labels them as SAME-PET or CROSS-PET warnings, but it does not automatically move or remove conflicting tasks. The schedule still includes both overlapping tasks.

*Why this is reasonable:* A pet care app should inform the owner, not make decisions for them. A CROSS-PET conflict (walking the dog while feeding the cat) might actually be fine if another family member helps. A SAME-PET conflict (two tasks for Buddy at 07:00) is more serious but the owner might want to choose which one to reschedule. Automatically dropping or rearranging tasks could hide important care activities. The warning-based approach keeps the owner in control.

*Alternative considered:* Using `itertools.combinations` to check all pairs would be more "Pythonic" (one line instead of a nested loop), but it loses the early-break optimization. Since the task list is sorted by start time, once task A's end time doesn't reach task B's start, no later task can overlap with A either. This makes the average case faster than O(n^2). For a small pet care app the difference is negligible, but the explicit loop is also easier to read and debug, so we kept it.

---

## 3. AI Collaboration

**a. How you used AI**

- How did you use AI tools during this project (for example: design brainstorming, debugging, refactoring)?
- What kinds of prompts or questions were most helpful?

I used AI (Claude Code) across every phase of the project:

- **Phase 1 (Design):** Asked AI to review my UML class diagram and suggest missing attributes. This is how `pet_name` was added to Task and `Priority` was changed from a string to an IntEnum — both suggestions that I validated before accepting.
- **Phase 2 (Implementation):** Used AI to scaffold class stubs from the UML, then iteratively build out methods like `generate_plan()` and `get_explanation()`. I gave step-by-step instructions rather than asking for everything at once.
- **Phase 3 (Algorithms):** Asked AI to implement sorting, filtering, conflict detection, and recurring tasks. The most helpful prompt was asking it to *plan* the features first (listing what each one needed) before writing code, so I could review the approach.
- **Phase 4 (Testing):** Asked AI for a test plan targeting happy paths and edge cases, then had it implement 18 tests. I reviewed each test to make sure it was actually testing meaningful behavior, not just confirming trivial things.
- **Phase 5 (Polish):** Used AI to wire the Scheduler methods into the Streamlit UI, update the UML diagram to match the final code, and draft the README.

The most helpful prompts were specific and scoped — for example, "What are the most important edge cases to test for a pet scheduler with sorting and recurring tasks?" produced better results than vague requests like "write tests."

**b. Judgment and verification**

- Describe one moment where you did not accept an AI suggestion as-is.
- How did you evaluate or verify what the AI suggested?

When evaluating the `_detect_conflicts()` method, AI considered replacing the nested loop with `itertools.combinations` for a more "Pythonic" one-liner. I rejected this because:

1. The current sorted-list approach has an **early break** — once task A no longer overlaps task B, it skips ahead. `itertools.combinations` would check every pair regardless, making it always O(n^2).
2. The explicit loop is **easier to read and debug** for someone learning Python. You can follow the logic step by step.
3. For a pet care app with a small number of tasks, the performance difference is negligible, but the readability difference matters for maintainability.

I verified by running the test suite after the refactor (extracting `_fmt_time()` and switching to `enumerate`) to confirm all 18 tests still passed. The algorithm stayed the same; only the formatting was cleaned up.

**c. AI strategy reflection**

- Which AI features were most effective for building your scheduler?
- Give one example of an AI suggestion you rejected or modified to keep your system design clean.
- How did using separate chat sessions for different phases help you stay organized?
- What did you learn about being the "lead architect" when collaborating with AI tools?

**Most effective AI features:** The ability to ask AI to *plan before coding* was the most valuable pattern. Before implementing sorting, filtering, conflict detection, and recurrence, I had AI produce a table of what each feature needed (where it goes, what logic it uses). This let me review and approve the design before any code was written, catching issues early.

**Suggestion I rejected:** AI initially handled recurring tasks by simply resetting the `completed` flag to `False` inside `_collect_eligible_tasks()`. This was a shortcut — it mutated the task in place with no date tracking, so there was no way to know *when* the next occurrence was due. I had this replaced with proper `due_date` + `timedelta` logic so that completing a daily task creates a genuinely new Task instance due tomorrow. This was more complex but gave the system real date awareness.

**Separate sessions for organization:** Working on different phases in focused sessions prevented context from getting muddled. The design session stayed clean (UML, class responsibilities), the algorithm session focused on sorting/filtering/conflicts without UI distractions, and the testing session could approach the code as a "fresh reviewer." Each session had a clear goal and deliverable.

**Being the lead architect:** The most important lesson was that AI is a powerful *implementer* but a mediocre *decision-maker*. It will confidently produce code for whatever approach you describe, even if that approach has flaws. My job was to:
1. Define the requirements and constraints before asking for code
2. Review every suggestion against the overall system design
3. Say "no" to clever shortcuts that would make the system harder to understand or extend
4. Verify with tests, not trust

AI accelerated every phase, but the quality of the final system depended on my judgment about *what to build* and *what to keep*.

---

## 4. Testing and Verification

**a. What you tested**

- What behaviors did you test?
- Why were these tests important?

The test suite covers five categories with 18 tests total:

1. **Schedule generation (2 tests):** Verified that tasks are sorted by scheduled time first, then by priority/duration, and that only tasks fitting within the available time budget are included. These are important because sorting and time-budgeting are the core logic of the scheduler — if these break, the entire app produces wrong plans.

2. **Recurring tasks (3 tests):** Confirmed that completing a daily task creates a new one due tomorrow (+1 day via timedelta), a weekly task creates one due in 7 days, and a non-recurring task returns None. These matter because incorrect recurrence logic could cause tasks to disappear, duplicate endlessly, or show up on the wrong day.

3. **Conflict detection (3 tests):** Verified that same-pet overlaps produce SAME-PET warnings, cross-pet overlaps produce CROSS-PET warnings, and non-overlapping tasks produce zero conflicts. Without these, the owner could unknowingly schedule impossible overlaps.

4. **Filtering (3 tests):** Tested filtering by pet name, by completion status, and both combined. Filtering is used throughout the UI — broken filters would show the wrong tasks everywhere.

5. **Edge cases (7 tests):** Covered no pets, no tasks, zero available time, a task longer than available time, future-dated recurring tasks, all tasks completed, and two tasks at the exact same time. These prevent crashes and incorrect behavior at boundary conditions that are easy to miss during manual testing.

**b. Confidence**

- How confident are you that your scheduler works correctly?
- What edge cases would you test next if you had more time?

**Confidence: 4 out of 5 stars.** All 18 tests pass and cover the core scheduling logic, recurrence, conflicts, filtering, and key edge cases. The scheduler produces correct plans in every scenario I've tested.

If I had more time, I would test:
- **Multi-day recurrence chains:** Complete a daily task 5 days in a row and verify each new instance has the correct due date.
- **Large task lists:** 50+ tasks to check performance and verify the greedy algorithm still makes sensible choices.
- **Streamlit UI integration:** Automated browser tests (e.g., with Selenium) to verify that button clicks, dropdowns, and session state work correctly end-to-end.
- **Concurrent recurring + conflict:** A recurring task that conflicts with another task every time it regenerates.

---

## 5. Reflection

**a. What went well**

- What part of this project are you most satisfied with?

I'm most satisfied with the **conflict detection system**. It evolved from a simple adjacent-pair check to a comprehensive algorithm that compares all pairs with an early-break optimization, labels conflicts as SAME-PET or CROSS-PET, and displays them as clear warnings in the UI. It's the feature that makes PawPal+ feel like a real scheduling tool rather than just a to-do list — it actively helps the owner avoid mistakes.

**b. What you would improve**

- If you had another iteration, what would you improve or redesign?

I would add **conflict resolution suggestions**, not just detection. When the scheduler finds a SAME-PET conflict, it could suggest moving one task to the nearest open time slot. For CROSS-PET conflicts, it could ask whether another family member can help, or offer to stagger the tasks. This would close the loop from "here's the problem" to "here's a solution."

I would also redesign the **task completion flow in the UI** to support bulk actions — marking multiple tasks as done at once rather than one at a time through a dropdown.

**c. Key takeaway**

- What is one important thing you learned about designing systems or working with AI on this project?

**Design first, code second.** The phases where I planned before implementing (UML before classes, feature tables before algorithms, test plans before tests) produced cleaner, more intentional code. The phases where I jumped straight into coding required more rework. AI makes it tempting to skip planning because it can generate code so fast — but fast code that solves the wrong problem is worse than slow code that solves the right one. The human's job is to define *what right looks like* before letting AI help build it.
