from datetime import date
from pawpal_system import Owner, Pet, Task, Priority, Scheduler

today = date.today()

# Create owner
owner = Owner("Yuli", available_time=120)

# Create pets
dog = Pet("Buddy", "Dog", "Golden Retriever", 3)
cat = Pet("Mimi", "Cat", "Siamese", 2)

owner.add_pet(dog)
owner.add_pet(cat)

# ── Scenario 1: Same-pet conflict ────────────────────────────
# Both tasks for Buddy at 07:00
dog.add_task(Task("Morning walk", 30, Priority.HIGH, "walk",
                  scheduled_time=420, due_date=today))            # 07:00-07:30
dog.add_task(Task("Give heartworm med", 10, Priority.HIGH, "meds",
                  scheduled_time=420, due_date=today))            # 07:00-07:10  CONFLICT!

# ── Scenario 2: Cross-pet conflict ──────────────────────────
# Buddy's walk (07:00-07:30) overlaps with Mimi's feeding at 07:15
cat.add_task(Task("Feed breakfast", 10, Priority.HIGH, "feeding",
                  scheduled_time=435, due_date=today))            # 07:15-07:25  CONFLICT!

# ── Non-conflicting tasks ───────────────────────────────────
dog.add_task(Task("Brush coat", 15, Priority.LOW, "grooming",
                  scheduled_time=600, due_date=today))            # 10:00 — no conflict
cat.add_task(Task("Play with feather toy", 20, Priority.MEDIUM, "enrichment",
                  due_date=today))                                 # unscheduled — no conflict
cat.add_task(Task("Clean litter box", 10, Priority.MEDIUM, "grooming",
                  recurrence="daily", due_date=today))

# ── Generate the schedule ────────────────────────────────────
scheduler = Scheduler(owner)

print("=" * 60)
print(f"  PawPal+ — Conflict Detection Demo ({today})")
print("=" * 60)
print()
print(scheduler.get_explanation())

# ── Print conflict summary ───────────────────────────────────
print()
if scheduler.conflicts:
    print("=" * 60)
    print(f"  {len(scheduler.conflicts)} conflict(s) found!")
    print("=" * 60)
    for c in scheduler.conflicts:
        print(f"  {c}")
else:
    print("No conflicts detected.")
