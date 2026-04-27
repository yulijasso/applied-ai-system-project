from datetime import date
import streamlit as st
from pawpal_system import Owner, Pet, Task, Priority, Scheduler

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")

if "owner" not in st.session_state:
    st.session_state.owner = Owner("Jordan", available_time=120)

owner = st.session_state.owner
scheduler = Scheduler(owner)

st.title("🐾 PawPal+")

# ── Owner Setup ──────────────────────────────────────────────
st.subheader("Owner")
owner_name = st.text_input("Owner name", value=owner.name)
available_time = st.number_input(
    "Available time (minutes per day)", min_value=1, max_value=480, value=owner.available_time
)
owner.name = owner_name
owner.available_time = available_time

# ── Add a Pet ────────────────────────────────────────────────
st.divider()
st.subheader("Add a Pet")

col_p1, col_p2 = st.columns(2)
with col_p1:
    pet_name = st.text_input("Pet name", value="Mochi")
with col_p2:
    species = st.selectbox("Species", ["dog", "cat", "other"])

pet_breed = st.text_input("Breed (optional)", value="")
pet_age = st.number_input("Age (years)", min_value=0, max_value=30, value=1)

if st.button("Add pet"):
    new_pet = Pet(name=pet_name, species=species, breed=pet_breed, age=pet_age)
    owner.add_pet(new_pet)
    st.success(f"Added {pet_name} the {species}!")

if owner.pets:
    st.write("Current pets:")
    st.table([{"Name": p.name, "Species": p.species, "Breed": p.breed, "Age": p.age} for p in owner.pets])
else:
    st.info("No pets yet. Add one above.")

# ── Add a Task to a Pet ──────────────────────────────────────
st.divider()
st.subheader("Add a Task")

if owner.pets:
    pet_choice = st.selectbox("Assign to pet", [p.name for p in owner.pets])

    col1, col2 = st.columns(2)
    with col1:
        task_title = st.text_input("Task title", value="Morning walk")
        duration = st.number_input("Duration (minutes)", min_value=1, max_value=240, value=20)
        recurrence = st.selectbox("Recurrence", ["None", "daily", "weekly"], index=0)
    with col2:
        category = st.selectbox("Category", ["walk", "feeding", "meds", "grooming", "enrichment"])
        priority = st.selectbox("Priority", ["HIGH", "MEDIUM", "LOW"], index=0)
        use_scheduled_time = st.checkbox("Set a scheduled time")

    scheduled_time = None
    if use_scheduled_time:
        sched_hour = st.number_input("Hour (0-23)", min_value=0, max_value=23, value=8)
        sched_min = st.number_input("Minute (0-59)", min_value=0, max_value=59, value=0)
        scheduled_time = int(sched_hour) * 60 + int(sched_min)

    if st.button("Add task"):
        selected_pet = next(p for p in owner.pets if p.name == pet_choice)
        new_task = Task(
            name=task_title,
            duration=int(duration),
            priority=Priority[priority],
            category=category,
            recurrence=None if recurrence == "None" else recurrence,
            scheduled_time=scheduled_time,
            due_date=date.today(),
        )
        selected_pet.add_task(new_task)
        st.success(f"Added '{task_title}' for {pet_choice}!")

    # ── Filter & Sort Task List ──────────────────────────────
    all_tasks = owner.get_all_tasks()
    if all_tasks:
        st.markdown("### Task List")
        filter_col1, filter_col2 = st.columns(2)
        with filter_col1:
            filter_pet = st.selectbox(
                "Filter by pet", ["All"] + [p.name for p in owner.pets], key="filter_pet"
            )
        with filter_col2:
            filter_status = st.selectbox(
                "Filter by status", ["All", "Incomplete", "Completed"], key="filter_status"
            )

        # Use Scheduler.filter_tasks() for filtering
        pet_filter = None if filter_pet == "All" else filter_pet
        status_filter = None
        if filter_status == "Incomplete":
            status_filter = False
        elif filter_status == "Completed":
            status_filter = True

        display_tasks = scheduler.filter_tasks(pet_name=pet_filter, completed=status_filter)

        # Use Scheduler.sort_by_time() for sorting
        display_tasks = scheduler.sort_by_time(display_tasks)

        if display_tasks:
            st.table([
                {
                    "Pet": t.pet_name,
                    "Task": t.name,
                    "Duration (min)": t.duration,
                    "Priority": t.priority.name,
                    "Category": t.category,
                    "Scheduled": Scheduler._fmt_time(t.scheduled_time) if t.scheduled_time is not None else "-",
                    "Recurrence": t.recurrence or "-",
                    "Status": "Done" if t.completed else "Pending",
                }
                for t in display_tasks
            ])
        else:
            st.info("No tasks match the current filters.")

    # ── Mark Tasks Complete ──────────────────────────────────
    incomplete = scheduler.filter_tasks(completed=False)
    if incomplete:
        st.markdown("### Complete a Task")
        task_labels = [f"{t.name} ({t.pet_name})" for t in incomplete]
        chosen_label = st.selectbox("Select task to complete", task_labels, key="complete_task")
        if st.button("Mark complete"):
            chosen_idx = task_labels.index(chosen_label)
            chosen_task = incomplete[chosen_idx]
            target_pet = next(p for p in owner.pets if p.name == chosen_task.pet_name)
            next_task = target_pet.complete_task(chosen_task)
            st.success(f"'{chosen_task.name}' marked as done!")
            if next_task is not None:
                st.info(
                    f"Recurring task: next '{next_task.name}' scheduled for "
                    f"{next_task.due_date.strftime('%B %d, %Y')}."
                )

else:
    st.info("Add a pet first, then you can assign tasks.")

# ── Generate Schedule ────────────────────────────────────────
st.divider()
st.subheader("Build Schedule")

if st.button("Generate schedule"):
    if not owner.get_all_tasks():
        st.warning("Add at least one task before generating a schedule.")
    else:
        plan = scheduler.generate_plan()

        if not plan:
            st.warning("No tasks could be scheduled. Check your available time or add tasks.")
        else:
            # Show conflict warnings first so the owner sees them immediately
            if scheduler.conflicts:
                for conflict in scheduler.conflicts:
                    st.warning(conflict)
                st.error(
                    f"{len(scheduler.conflicts)} time conflict(s) detected! "
                    "Consider rescheduling the tasks above to avoid overlaps."
                )

            # Display the sorted plan as a clean table
            total_time = sum(t.duration for t in plan)
            st.success(
                f"Daily plan for {owner.name} — "
                f"{total_time}/{owner.available_time} minutes used"
            )

            st.table([
                {
                    "#": i,
                    "Time": Scheduler._fmt_time(t.scheduled_time) if t.scheduled_time is not None else "-",
                    "Task": t.name,
                    "Pet": t.pet_name,
                    "Duration (min)": t.duration,
                    "Priority": t.priority.name,
                    "Recurrence": t.recurrence or "-",
                }
                for i, t in enumerate(plan, start=1)
            ])

            # Show skipped tasks
            eligible = scheduler._collect_eligible_tasks()
            skipped = [t for t in eligible if t not in plan]
            if skipped:
                st.warning("The following tasks did not fit in today's schedule:")
                st.table([
                    {
                        "Task": t.name,
                        "Pet": t.pet_name,
                        "Duration (min)": t.duration,
                        "Priority": t.priority.name,
                    }
                    for t in skipped
                ])
