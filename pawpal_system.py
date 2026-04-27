from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import IntEnum
from typing import List, Optional


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
    def __init__(self, owner: Owner):
        self.owner = owner
        self.conflicts: List[str] = []

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
        return plan

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
