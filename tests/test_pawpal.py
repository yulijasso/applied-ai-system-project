from datetime import date, timedelta
from pawpal_system import Task, Pet, Owner, Priority, Scheduler


# ── 1. Schedule Generation (Happy Path) ─────────────────────

def test_plan_sorted_by_time_then_priority():
    """Tasks with scheduled_time come first (chronologically),
    then unscheduled tasks sorted by priority and duration."""
    owner = Owner("Test", available_time=120)
    pet = Pet("Buddy", "Dog")
    owner.add_pet(pet)

    pet.add_task(Task("Grooming", 15, Priority.LOW, "grooming"))                  # unscheduled
    pet.add_task(Task("Walk", 30, Priority.HIGH, "walk", scheduled_time=480))     # 08:00
    pet.add_task(Task("Meds", 5, Priority.HIGH, "meds", scheduled_time=420))      # 07:00

    plan = Scheduler(owner).generate_plan()
    names = [t.name for t in plan]
    assert names == ["Meds", "Walk", "Grooming"]


def test_plan_respects_available_time():
    """Only tasks that fit within available_time are included."""
    owner = Owner("Test", available_time=25)
    pet = Pet("Buddy", "Dog")
    owner.add_pet(pet)

    pet.add_task(Task("Walk", 20, Priority.HIGH, "walk"))
    pet.add_task(Task("Meds", 5, Priority.HIGH, "meds"))
    pet.add_task(Task("Groom", 15, Priority.LOW, "grooming"))  # won't fit

    plan = Scheduler(owner).generate_plan()
    names = [t.name for t in plan]
    assert "Walk" in names
    assert "Meds" in names
    assert "Groom" not in names


# ── 2. Recurring Task Completion (Happy Path) ───────────────

def test_daily_recurrence_creates_next_day():
    """Completing a daily task creates a new one due tomorrow."""
    today = date.today()
    pet = Pet("Buddy", "Dog")
    task = Task("Walk", 30, Priority.HIGH, "walk", recurrence="daily", due_date=today)
    pet.add_task(task)

    next_task = pet.complete_task(task)

    assert task.completed is True
    assert next_task is not None
    assert next_task.due_date == today + timedelta(days=1)
    assert next_task.completed is False
    assert len(pet.tasks) == 2  # original + new


def test_weekly_recurrence_creates_next_week():
    """Completing a weekly task creates a new one due in 7 days."""
    today = date.today()
    task = Task("Litter", 10, Priority.MEDIUM, "grooming", recurrence="weekly", due_date=today)
    pet = Pet("Mimi", "Cat")
    pet.add_task(task)

    next_task = pet.complete_task(task)

    assert next_task.due_date == today + timedelta(days=7)


def test_non_recurring_returns_none():
    """Completing a non-recurring task returns None (no next occurrence)."""
    task = Task("Bath", 20, Priority.LOW, "grooming")
    pet = Pet("Buddy", "Dog")
    pet.add_task(task)

    next_task = pet.complete_task(task)

    assert task.completed is True
    assert next_task is None
    assert len(pet.tasks) == 1  # no new task added


# ── 3. Conflict Detection (Happy Path) ──────────────────────

def test_same_pet_conflict():
    """Two tasks for the same pet at the same time produce a SAME-PET warning."""
    owner = Owner("Test", available_time=60)
    pet = Pet("Buddy", "Dog")
    owner.add_pet(pet)

    pet.add_task(Task("Walk", 30, Priority.HIGH, "walk", scheduled_time=420))
    pet.add_task(Task("Meds", 10, Priority.HIGH, "meds", scheduled_time=420))

    scheduler = Scheduler(owner)
    scheduler.generate_plan()

    assert len(scheduler.conflicts) == 1
    assert "SAME-PET" in scheduler.conflicts[0]


def test_cross_pet_conflict():
    """Overlapping tasks for different pets produce a CROSS-PET warning."""
    owner = Owner("Test", available_time=60)
    dog = Pet("Buddy", "Dog")
    cat = Pet("Mimi", "Cat")
    owner.add_pet(dog)
    owner.add_pet(cat)

    dog.add_task(Task("Walk", 30, Priority.HIGH, "walk", scheduled_time=420))     # 07:00-07:30
    cat.add_task(Task("Feed", 10, Priority.HIGH, "feeding", scheduled_time=435))  # 07:15-07:25

    scheduler = Scheduler(owner)
    scheduler.generate_plan()

    assert len(scheduler.conflicts) == 1
    assert "CROSS-PET" in scheduler.conflicts[0]


def test_no_conflict_when_no_overlap():
    """Non-overlapping tasks produce zero conflicts."""
    owner = Owner("Test", available_time=120)
    pet = Pet("Buddy", "Dog")
    owner.add_pet(pet)

    pet.add_task(Task("Walk", 30, Priority.HIGH, "walk", scheduled_time=420))     # 07:00-07:30
    pet.add_task(Task("Groom", 15, Priority.LOW, "grooming", scheduled_time=480)) # 08:00-08:15

    scheduler = Scheduler(owner)
    scheduler.generate_plan()

    assert len(scheduler.conflicts) == 0


# ── 4. Filtering (Happy Path) ───────────────────────────────

def test_filter_by_pet_name():
    """filter_tasks returns only the specified pet's tasks."""
    owner = Owner("Test", available_time=120)
    dog = Pet("Buddy", "Dog")
    cat = Pet("Mimi", "Cat")
    owner.add_pet(dog)
    owner.add_pet(cat)

    dog.add_task(Task("Walk", 30, Priority.HIGH, "walk"))
    cat.add_task(Task("Feed", 10, Priority.HIGH, "feeding"))
    cat.add_task(Task("Play", 20, Priority.MEDIUM, "enrichment"))

    scheduler = Scheduler(owner)
    buddy_tasks = scheduler.filter_tasks(pet_name="Buddy")
    mimi_tasks = scheduler.filter_tasks(pet_name="Mimi")

    assert len(buddy_tasks) == 1
    assert buddy_tasks[0].name == "Walk"
    assert len(mimi_tasks) == 2


def test_filter_by_status():
    """filter_tasks returns only tasks matching the completion status."""
    owner = Owner("Test", available_time=120)
    pet = Pet("Buddy", "Dog")
    owner.add_pet(pet)

    t1 = Task("Walk", 30, Priority.HIGH, "walk")
    t2 = Task("Meds", 5, Priority.HIGH, "meds")
    pet.add_task(t1)
    pet.add_task(t2)
    t1.mark_complete()

    scheduler = Scheduler(owner)
    done = scheduler.filter_tasks(completed=True)
    pending = scheduler.filter_tasks(completed=False)

    assert len(done) == 1
    assert done[0].name == "Walk"
    assert len(pending) == 1
    assert pending[0].name == "Meds"


def test_filter_combined():
    """filter_tasks with both pet_name and completed works together."""
    owner = Owner("Test", available_time=120)
    dog = Pet("Buddy", "Dog")
    cat = Pet("Mimi", "Cat")
    owner.add_pet(dog)
    owner.add_pet(cat)

    t1 = Task("Walk", 30, Priority.HIGH, "walk")
    t2 = Task("Meds", 5, Priority.HIGH, "meds")
    dog.add_task(t1)
    dog.add_task(t2)
    cat.add_task(Task("Feed", 10, Priority.HIGH, "feeding"))
    t1.mark_complete()

    scheduler = Scheduler(owner)
    result = scheduler.filter_tasks(pet_name="Buddy", completed=False)

    assert len(result) == 1
    assert result[0].name == "Meds"


# ── 5. Edge Cases ───────────────────────────────────────────

def test_empty_owner_no_pets():
    """Owner with no pets generates an empty plan without crashing."""
    owner = Owner("Test", available_time=120)
    scheduler = Scheduler(owner)
    plan = scheduler.generate_plan()

    assert plan == []
    assert scheduler.conflicts == []


def test_pet_with_no_tasks():
    """Pet exists but has zero tasks — schedule still works."""
    owner = Owner("Test", available_time=120)
    owner.add_pet(Pet("Buddy", "Dog"))

    plan = Scheduler(owner).generate_plan()
    assert plan == []


def test_zero_available_time():
    """available_time=0 means all tasks are skipped."""
    owner = Owner("Test", available_time=0)
    pet = Pet("Buddy", "Dog")
    owner.add_pet(pet)
    pet.add_task(Task("Walk", 30, Priority.HIGH, "walk"))

    plan = Scheduler(owner).generate_plan()
    assert plan == []


def test_task_longer_than_available_time():
    """A task that exceeds available_time is skipped; shorter ones still fit."""
    owner = Owner("Test", available_time=15)
    pet = Pet("Buddy", "Dog")
    owner.add_pet(pet)

    pet.add_task(Task("Long walk", 60, Priority.HIGH, "walk"))     # too long
    pet.add_task(Task("Quick meds", 5, Priority.HIGH, "meds"))     # fits

    plan = Scheduler(owner).generate_plan()
    names = [t.name for t in plan]

    assert "Long walk" not in names
    assert "Quick meds" in names


def test_future_dated_task_excluded():
    """A recurring task with due_date in the future does not appear in today's plan."""
    owner = Owner("Test", available_time=120)
    pet = Pet("Buddy", "Dog")
    owner.add_pet(pet)

    tomorrow = date.today() + timedelta(days=1)
    pet.add_task(Task("Walk", 30, Priority.HIGH, "walk", recurrence="daily", due_date=tomorrow))

    plan = Scheduler(owner).generate_plan()
    assert plan == []


def test_all_tasks_completed():
    """When every task is done and non-recurring, the plan is empty."""
    owner = Owner("Test", available_time=120)
    pet = Pet("Buddy", "Dog")
    owner.add_pet(pet)

    t1 = Task("Walk", 30, Priority.HIGH, "walk")
    t2 = Task("Meds", 5, Priority.HIGH, "meds")
    pet.add_task(t1)
    pet.add_task(t2)
    t1.mark_complete()
    t2.mark_complete()

    plan = Scheduler(owner).generate_plan()
    assert plan == []


def test_exact_same_time_and_duration():
    """Two identical-time tasks for same pet are both included but flagged."""
    owner = Owner("Test", available_time=60)
    pet = Pet("Buddy", "Dog")
    owner.add_pet(pet)

    pet.add_task(Task("Walk", 20, Priority.HIGH, "walk", scheduled_time=420))
    pet.add_task(Task("Meds", 20, Priority.HIGH, "meds", scheduled_time=420))

    scheduler = Scheduler(owner)
    plan = scheduler.generate_plan()

    assert len(plan) == 2  # both fit
    assert len(scheduler.conflicts) == 1
    assert "SAME-PET" in scheduler.conflicts[0]
