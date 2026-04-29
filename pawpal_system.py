import dataclasses
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import IntEnum
from typing import List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from care_advisor import AdvisorReview, CareAdvisor, ProposedChange

logger = logging.getLogger("pawpal.scheduler")


class Priority(IntEnum):
    HIGH = 1
    MEDIUM = 2
    LOW = 3


@dataclass
class Task:
    name: str
    duration: int  # minutes
    priority: Priority
    category: str  # "walk", "feeding", "meds", "grooming", "enrichment"
    pet_name: str = ""
    completed: bool = False
    scheduled_time: Optional[int] = None  # start minute of the day (0-1439)
    recurrence: Optional[str] = None  # "daily", "weekly", or None
    due_date: Optional[date] = None  # when this task is due

    def mark_complete(self) -> Optional["Task"]:
        """Mark this task as completed.

        If the task is recurring, a new Task instance is created with
        the next due_date (today + 1 day for daily, today + 7 days for weekly)
        using Python's timedelta. The new task is returned so the caller
        can add it to the pet's task list.
        """
        self.completed = True

        if not self.is_recurring:
            return None

        days = 1 if self.recurrence == "daily" else 7
        next_due = (self.due_date or date.today()) + timedelta(days=days)

        next_task = Task(
            name=self.name,
            duration=self.duration,
            priority=self.priority,
            category=self.category,
            pet_name=self.pet_name,
            scheduled_time=self.scheduled_time,
            recurrence=self.recurrence,
            due_date=next_due,
        )
        return next_task

    def edit(
        self,
        name: Optional[str] = None,
        duration: Optional[int] = None,
        priority: Optional[Priority] = None,
        category: Optional[str] = None,
    ):
        """Update one or more task fields."""
        if name is not None:
            self.name = name
        if duration is not None:
            self.duration = duration
        if priority is not None:
            self.priority = priority
        if category is not None:
            self.category = category

    @property
    def end_time(self) -> Optional[int]:
        """Return the end minute if a scheduled_time is set."""
        if self.scheduled_time is not None:
            return self.scheduled_time + self.duration
        return None

    @property
    def is_recurring(self) -> bool:
        """Return True if this task repeats on a daily or weekly cycle."""
        return self.recurrence is not None


@dataclass
class Pet:
    name: str
    species: str
    breed: str = ""
    age: int = 0
    tasks: List[Task] = field(default_factory=list)

    def add_task(self, task: Task):
        """Add a task to this pet and stamp it with the pet's name."""
        task.pet_name = self.name
        self.tasks.append(task)

    def remove_task(self, task: Task):
        """Remove a task from this pet's task list."""
        self.tasks.remove(task)

    def complete_task(self, task: Task) -> Optional[Task]:
        """Mark a task complete. If recurring, add the next occurrence automatically."""
        next_task = task.mark_complete()
        if next_task is not None:
            self.tasks.append(next_task)
        return next_task

    def get_tasks(self) -> List[Task]:
        """Return a copy of this pet's task list."""
        return list(self.tasks)


@dataclass
class Owner:
    name: str
    available_time: int  # minutes per day
    pets: List[Pet] = field(default_factory=list)

    def add_pet(self, pet: Pet):
        """Add a pet to this owner's pet list."""
        self.pets.append(pet)

    def remove_pet(self, pet: Pet):
        """Remove a pet from this owner's pet list."""
        self.pets.remove(pet)

    def get_all_tasks(self) -> List[Task]:
        """Collect and return all tasks from all pets."""
        all_tasks = []
        for pet in self.pets:
            all_tasks.extend(pet.get_tasks())
        return all_tasks

    def get_tasks_by_pet(self, pet_name: str) -> List[Task]:
        """Return tasks belonging to a specific pet."""
        return [t for t in self.get_all_tasks() if t.pet_name == pet_name]

    def get_tasks_by_status(self, completed: bool) -> List[Task]:
        """Return tasks filtered by completion status."""
        return [t for t in self.get_all_tasks() if t.completed == completed]


class Scheduler:
    def __init__(self, owner: Owner, advisor: Optional["CareAdvisor"] = None):
        self.owner = owner
        self.conflicts: List[str] = []
        self.advisor = advisor
        self.review: Optional["AdvisorReview"] = None

    def _collect_eligible_tasks(self) -> List[Task]:
        """Gather incomplete tasks that are due today or have no due date."""
        today = date.today()
        tasks = []
        for task in self.owner.get_all_tasks():
            if task.completed:
                continue
            if task.due_date is not None and task.due_date > today:
                continue
            tasks.append(task)
        return tasks

    @staticmethod
    def _fmt_time(minutes: int) -> str:
        """Convert a minute-of-day integer to HH:MM string."""
        return f"{minutes // 60:02d}:{minutes % 60:02d}"

    def _detect_conflicts(self, plan: List[Task]) -> List[str]:
        """Check every pair of scheduled tasks for time overlaps.

        Compares all pairs (not just adjacent) so conflicts are caught
        even when tasks are assigned to different pets. Labels each
        warning as SAME-PET or CROSS-PET so the owner knows the severity.

        Uses a sorted list + early break: once task A's end_time no longer
        reaches task B's start, no later task can overlap A either, so we
        skip ahead. This keeps average performance well below O(n**2).
        """
        scheduled = sorted(
            (t for t in plan if t.scheduled_time is not None),
            key=lambda t: t.scheduled_time,
        )
        conflicts = []

        for i, a in enumerate(scheduled):
            for b in scheduled[i + 1:]:
                if a.end_time <= b.scheduled_time:
                    break  # sorted — no later task can overlap with a
                kind = "SAME-PET" if a.pet_name == b.pet_name else "CROSS-PET"
                conflicts.append(
                    f"WARNING [{kind}]: '{a.name}' ({a.pet_name}, "
                    f"{self._fmt_time(a.scheduled_time)}-{self._fmt_time(a.end_time)}) "
                    f"overlaps with '{b.name}' ({b.pet_name}, "
                    f"starts {self._fmt_time(b.scheduled_time)})"
                )

        return conflicts

    def sort_by_time(self, tasks: List[Task]) -> List[Task]:
        """Sort tasks by scheduled time (earliest first), then by priority and duration.

        Uses a lambda key so that:
        - Tasks WITH a scheduled_time come first, ordered by that time
        - Tasks WITHOUT a scheduled_time come after, ordered by priority then duration
        """
        return sorted(
            tasks,
            key=lambda t: (
                (0, t.scheduled_time, t.priority, t.duration)
                if t.scheduled_time is not None
                else (1, 0, t.priority, t.duration)
            ),
        )

    def filter_tasks(
        self,
        pet_name: Optional[str] = None,
        completed: Optional[bool] = None,
    ) -> List[Task]:
        """Filter all owner tasks by pet name and/or completion status."""
        tasks = self.owner.get_all_tasks()
        if pet_name is not None:
            tasks = [t for t in tasks if t.pet_name == pet_name]
        if completed is not None:
            tasks = [t for t in tasks if t.completed == completed]
        return tasks

    def generate_plan(self) -> List[Task]:
        """Build a daily plan sorted by scheduled time then priority."""
        tasks = self._collect_eligible_tasks()
        tasks = self.sort_by_time(tasks)

        plan = []
        remaining_time = self.owner.available_time
        for task in tasks:
            if task.duration <= remaining_time:
                plan.append(task)
                remaining_time -= task.duration

        self.conflicts = self._detect_conflicts(plan)
        self.review = None
        return plan

    def _describe_pets(self) -> List[str]:
        descs = []
        for pet in self.owner.pets:
            parts = [pet.name, f"{pet.species}"]
            if pet.breed:
                parts.append(pet.breed)
            if pet.age:
                parts.append(f"{pet.age} years old")
            descs.append(", ".join(parts))
        return descs

    def _describe_plan(self, plan: List[Task]) -> List[str]:
        # Render recurrence in a way the LLM can't misread. The earlier wording
        # "weekly recurring" was being parsed by the model as scheduling
        # metadata instead of meaning "this task fires once per week" — so a
        # cat scheduled to Feed weekly was getting only a low-severity nudge.
        lines = []
        for task in plan:
            time_str = (
                f"{self._fmt_time(task.scheduled_time)}-"
                f"{self._fmt_time(task.end_time)}"
                if task.scheduled_time is not None
                else "unscheduled"
            )
            if task.recurrence == "daily":
                recur = ", recurs DAILY"
            elif task.recurrence == "weekly":
                recur = ", recurs ONCE EVERY 7 DAYS (not daily)"
            elif task.recurrence:
                recur = f", recurs {task.recurrence}"
            else:
                recur = ", no recurrence"
            lines.append(
                f"{time_str}: '{task.name}' for {task.pet_name}, "
                f"{task.duration} min, {task.priority.name} priority, "
                f"{task.category} category{recur}"
            )
        return lines

    def run_advisor_review(self, plan: List[Task]) -> Optional["AdvisorReview"]:
        """Ask the AI advisor to critique the generated plan via RAG."""
        if self.advisor is None or not plan:
            return None
        plan_lines = self._describe_plan(plan)
        pet_descriptions = self._describe_pets()
        self.review = self.advisor.review_plan(plan_lines, pet_descriptions)
        return self.review

    def apply_advisor_changes(
        self,
        plan: List[Task],
        review: Optional["AdvisorReview"],
    ) -> Tuple[List[Task], List["ProposedChange"]]:
        """Mutate a copy of the plan according to the advisor's structured
        proposed_changes so the plan the owner sees actually reflects the
        retrieved guidance. Returns (modified_plan, applied_changes).

        Tasks are copied via dataclasses.replace before edits so the owner's
        underlying Pet.tasks lists are never mutated.
        """
        if review is None or not review.available:
            return plan, []

        proposed_changes = list(review.proposed_changes)

        # Safety net: if the advisor raised an issue about a feeding task with
        # a non-daily cadence but failed to emit the matching `change_recurrence`
        # (rule 11 in the system prompt — models sometimes skip it), synthesize
        # one here so the plan the owner sees actually reflects the guidance.
        # Only fires when an issue cites the snippet, so it remains RAG-grounded.
        from care_advisor import ProposedChange as _PC  # local import avoids cycle
        already_changed = {
            (c.task_name, c.pet_name)
            for c in proposed_changes
            if c.change_type == "change_recurrence"
        }
        for issue in review.issues:
            key = (issue.task_name, issue.pet_name)
            if key in already_changed:
                continue
            target = next(
                (
                    t for t in plan
                    if t.name == issue.task_name
                    and t.pet_name == issue.pet_name
                    and (t.category or "").lower() == "feeding"
                    and (t.recurrence or "").lower() != "daily"
                ),
                None,
            )
            if target is None:
                continue
            task_idx = next(
                (i + 1 for i, t in enumerate(plan) if t is target), None
            )
            proposed_changes.append(_PC(
                pet_name=issue.pet_name,
                task_name=issue.task_name,
                change_type="change_recurrence",
                reason=f"Synthesized from advisor issue: {issue.recommendation}",
                task_index=task_idx,
                new_recurrence="daily",
                citations=list(issue.citations),
            ))
            already_changed.add(key)
            logger.info(
                "Synthesized change_recurrence=daily for %s/%s (advisor "
                "raised issue but emitted no fix)",
                issue.task_name, issue.pet_name,
            )

        if not proposed_changes:
            return plan, []

        new_plan = list(plan)
        applied: List["ProposedChange"] = []

        plan_has_feeding = any(
            (t.category or "").lower() == "feeding" for t in plan
        )

        for change in proposed_changes:
            # Reject changes whose reason describes a split / new session.
            # Our scheduler has no add-task operation; the model has
            # repeatedly tried to fake one by emitting a shorten with
            # "split into two sessions" rationale, which leaves a single
            # too-short task instead of two sessions. Catch that here so
            # the in-range plan isn't silently mutilated.
            if self._reason_describes_split(change.reason):
                logger.info(
                    "Advisor change skipped (split/add-session pattern in "
                    "reason — system cannot add tasks): %s for %s — %r",
                    change.task_name,
                    change.pet_name,
                    change.reason,
                )
                continue

            # Reject reschedule edits that try to align a medication with
            # an unstated meal time. If the plan has no feeding task, the
            # model has no basis for picking a "with food" time; surfacing
            # the warning in the issue text is fine but mutating the plan
            # to a fabricated mealtime is a hallucination.
            if (
                change.change_type == "reschedule"
                and not plan_has_feeding
                and self._reason_describes_meal_alignment(change.reason)
            ):
                logger.info(
                    "Advisor change skipped (reschedule references meal but "
                    "plan has no feeding task): %s for %s — %r",
                    change.task_name,
                    change.pet_name,
                    change.reason,
                )
                continue

            target = self._resolve_target(plan, change)
            if target is None:
                logger.info(
                    "Advisor change skipped (no matching task): %s for %s "
                    "(task_index=%s)",
                    change.task_name,
                    change.pet_name,
                    change.task_index,
                )
                continue

            # Locate target in new_plan, which may have shifted after prior
            # pops or been replaced (in-place) by an earlier shorten/lengthen/
            # reschedule on the same task. Identity match first; fall back to
            # name+pet — the replacement copy preserves both fields.
            idx = next(
                (i for i, t in enumerate(new_plan) if t is target), None
            )
            if idx is None:
                idx = next(
                    (
                        i
                        for i, t in enumerate(new_plan)
                        if t.name == target.name and t.pet_name == target.pet_name
                    ),
                    None,
                )
            if idx is None:
                logger.info(
                    "Advisor change skipped (target already removed): %s for %s",
                    change.task_name,
                    change.pet_name,
                )
                continue
            task = new_plan[idx]

            if change.change_type == "remove":
                new_plan.pop(idx)
                applied.append(change)
                # For non-recurring tasks, also delete from the owner's task
                # list so the task doesn't reappear in future plans. Recurring
                # tasks keep their template — the advisor only meant to skip
                # today's instance, not kill the daily/weekly cadence.
                if not task.is_recurring:
                    for pet in self.owner.pets:
                        if task in pet.tasks:
                            pet.tasks.remove(task)
                            logger.info(
                                "Deleted non-recurring task '%s' from %s.tasks per advisor",
                                task.name,
                                pet.name,
                            )
                            break
            elif change.change_type == "shorten":
                new_dur = change.new_duration_min
                if new_dur and 0 < new_dur < task.duration:
                    new_plan[idx] = dataclasses.replace(task, duration=new_dur)
                    applied.append(change)
            elif change.change_type == "lengthen":
                new_dur = change.new_duration_min
                if new_dur and new_dur > task.duration:
                    new_plan[idx] = dataclasses.replace(task, duration=new_dur)
                    applied.append(change)
            elif change.change_type == "reschedule":
                new_start = self._parse_hhmm(change.new_start_hhmm)
                if new_start is not None:
                    new_plan[idx] = dataclasses.replace(
                        task, scheduled_time=new_start
                    )
                    applied.append(change)
            elif change.change_type == "change_recurrence":
                new_rec = self._normalize_recurrence(change.new_recurrence)
                if new_rec != task.recurrence:
                    new_plan[idx] = dataclasses.replace(task, recurrence=new_rec)
                    applied.append(change)
                else:
                    logger.info(
                        "Advisor change skipped (recurrence already %r): %s for %s",
                        new_rec, change.task_name, change.pet_name,
                    )
            else:
                logger.warning(
                    "Unknown advisor change_type '%s' — skipped",
                    change.change_type,
                )

        if applied:
            logger.info(
                "Applied %d advisor change(s) to plan: %s",
                len(applied),
                [(c.change_type, c.task_name, c.pet_name) for c in applied],
            )
        return new_plan, applied

    _SPLIT_REASON_PHRASES = (
        "split into",
        "two sessions",
        "two shorter sessions",
        "two walks",
        "second walk",
        "second session",
        "add a walk",
        "add a session",
        "add a second",
        "additional walk",
        "additional session",
        "more frequent walks",
        "more frequent sessions",
        "shorter sessions",
    )

    @classmethod
    def _reason_describes_split(cls, reason: Optional[str]) -> bool:
        """True when the advisor's reason text is trying to describe adding
        a session or splitting a task — patterns the scheduler can't honor
        because there's no add-task operation."""
        if not reason:
            return False
        lowered = reason.lower()
        return any(phrase in lowered for phrase in cls._SPLIT_REASON_PHRASES)

    _MEAL_ALIGNMENT_PHRASES = (
        "with food",
        "with a meal",
        "with meal",
        "at mealtime",
        "with breakfast",
        "with dinner",
        "alongside meal",
        "alongside food",
        "after eating",
        "during breakfast",
        "during dinner",
        "align with mealtime",
        "align with a meal",
        "align with the meal",
        "given with food",
        "taken with food",
    )

    @classmethod
    def _reason_describes_meal_alignment(cls, reason: Optional[str]) -> bool:
        if not reason:
            return False
        lowered = reason.lower()
        return any(phrase in lowered for phrase in cls._MEAL_ALIGNMENT_PHRASES)

    @staticmethod
    def _resolve_target(
        plan: List[Task], change: "ProposedChange"
    ) -> Optional[Task]:
        """Resolve a ProposedChange to the specific Task in the original plan
        it targets. Prefers `task_index` (1-based, validated against name+pet)
        and falls back to (task_name, pet_name) match if the index is missing
        or doesn't validate. Returns None if no match."""
        if change.task_index is not None:
            idx = change.task_index - 1
            if 0 <= idx < len(plan):
                candidate = plan[idx]
                if (
                    candidate.name == change.task_name
                    and candidate.pet_name == change.pet_name
                ):
                    return candidate
                logger.warning(
                    "task_index=%d points at '%s' for %s but change names "
                    "'%s' for %s — falling back to name+pet match",
                    change.task_index,
                    candidate.name,
                    candidate.pet_name,
                    change.task_name,
                    change.pet_name,
                )
        return next(
            (
                t
                for t in plan
                if t.name == change.task_name and t.pet_name == change.pet_name
            ),
            None,
        )

    @staticmethod
    def _normalize_recurrence(value: Optional[str]) -> Optional[str]:
        """Map a model-emitted recurrence string to the value the Task field
        expects. 'none', empty string, and None all map to None (no recurrence).
        Unknown values are dropped (returned as the original task's value)."""
        if value is None:
            return None
        v = str(value).strip().lower()
        if v in ("daily", "weekly"):
            return v
        if v in ("none", "no", ""):
            return None
        return None

    @staticmethod
    def _parse_hhmm(hhmm: Optional[str]) -> Optional[int]:
        if not hhmm:
            return None
        try:
            hh, mm = hhmm.split(":")
            minutes = int(hh) * 60 + int(mm)
        except (ValueError, AttributeError):
            return None
        if 0 <= minutes < 24 * 60:
            return minutes
        return None

    def get_explanation(self) -> str:
        """Return a human-readable summary of the daily plan with reasoning."""
        plan = self.generate_plan()
        if not plan:
            return "No tasks could be scheduled. Check your available time or add tasks."

        total_time = sum(t.duration for t in plan)
        lines = [
            f"Daily plan for {self.owner.name} "
            f"({total_time}/{self.owner.available_time} minutes used):",
            "",
        ]

        for i, task in enumerate(plan, start=1):
            time_str = ""
            if task.scheduled_time is not None:
                time_str = f" @ {self._fmt_time(task.scheduled_time)}"
            recur_str = f" [{task.recurrence}]" if task.is_recurring else ""
            lines.append(
                f"  {i}. [{task.priority.name}] {task.name} "
                f"({task.pet_name}) - {task.duration} min{time_str}{recur_str}"
            )

        if self.conflicts:
            lines.append("")
            lines.append("Conflicts detected:")
            for c in self.conflicts:
                lines.append(f"  ! {c}")

        skipped = [t for t in self._collect_eligible_tasks()
                    if t not in plan]
        if skipped:
            lines.append("")
            lines.append("Skipped (not enough time):")
            for task in skipped:
                lines.append(
                    f"  - {task.name} ({task.pet_name}) - {task.duration} min"
                )

        lines.append("")
        lines.append(
            "Tasks with a scheduled time are placed first, "
            "then remaining tasks by priority (high first) "
            "and duration (shorter first)."
        )
        return "\n".join(lines)
