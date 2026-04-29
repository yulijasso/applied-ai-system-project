import os
from datetime import date
import streamlit as st

# Mirror Streamlit Cloud secrets into os.environ BEFORE CareAdvisor reads
# them via os.getenv. Streamlit Cloud exposes secrets through st.secrets,
# but the env-var injection isn't guaranteed to happen before module-load
# code in dependent files runs. Copying explicitly here is safe and idempotent.
try:
    for _key in (
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
        "GEMINI_MODEL",
        "GROQ_MODEL",
        "GEMINI_EMBEDDING_MODEL",
        "PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION",
    ):
        if _key in st.secrets:
            os.environ.setdefault(_key, str(st.secrets[_key]))
except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
    # No secrets.toml locally — fall through to .env loaded by dotenv inside care_advisor.
    pass

from pawpal_system import Owner, Pet, Task, Priority, Scheduler
from care_advisor import CareAdvisor

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")

if "owner" not in st.session_state:
    st.session_state.owner = Owner("Jordan", available_time=120)

if "advisor" not in st.session_state:
    st.session_state.advisor = CareAdvisor()

owner = st.session_state.owner
advisor = st.session_state.advisor
scheduler = Scheduler(owner, advisor=advisor)

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
st.subheader("Build schedule")

def _format_change(c, draft_lookup):
    """One-line summary of an applied advisor change for the edits table."""
    old = draft_lookup.get((c.task_name, c.pet_name))
    if c.change_type == "remove":
        if old and old.is_recurring:
            return "Removed from today (recurring template kept)"
        return "Deleted from task list"
    if c.change_type in ("shorten", "lengthen") and old:
        return f"{old.duration} min → {c.new_duration_min} min"
    if c.change_type == "reschedule" and old:
        old_t = (
            Scheduler._fmt_time(old.scheduled_time)
            if old.scheduled_time is not None
            else "—"
        )
        return f"{old_t} → {c.new_start_hhmm}"
    if c.change_type == "change_recurrence" and old:
        old_rec = old.recurrence or "none"
        new_rec = (c.new_recurrence or "none").lower()
        return f"recurrence: {old_rec} → {new_rec}"
    return c.change_type


_total_tasks = len(owner.get_all_tasks())
_open_tasks = len(owner.get_tasks_by_status(completed=False))
_n_pets = len(owner.pets)

if _total_tasks == 0:
    st.caption("Add at least one task above to generate a plan.")
else:
    st.caption(
        f"Ready to schedule **{_open_tasks}** open task(s) across "
        f"**{_n_pets}** pet(s), within **{owner.available_time} min** today."
    )

ctrl_left, ctrl_right = st.columns([2, 1], vertical_alignment="center")
with ctrl_left:
    use_advisor = st.checkbox(
        "Use AI care advisor",
        value=advisor.is_available,
        disabled=not advisor.is_available,
        help=(
            "Retrieves curated pet-care knowledge via embeddings, then asks "
            "the chosen LLM to flag risks and edit the plan (shorten / "
            "reschedule / remove) when a snippet supports it. Edits are "
            "applied before the plan is shown."
        ),
    )

    # Provider switcher — only shown when both providers are available and
    # the advisor is on. Embeddings always use Gemini regardless of choice.
    if advisor.is_available and use_advisor:
        providers = advisor.available_providers
        if len(providers) > 1:
            label_for = {"gemini": "Gemini", "groq": "Groq"}
            selected = st.radio(
                "Chat model provider",
                options=providers,
                index=providers.index(advisor.chat_provider or providers[0]),
                format_func=lambda p: label_for.get(p, p),
                horizontal=True,
                help=(
                    "Switch which LLM handles the chat call. Useful when "
                    "one provider's daily quota is exhausted. Embeddings "
                    "always go through Gemini."
                ),
            )
            if selected != advisor.chat_provider:
                advisor.set_chat_provider(selected)

    if not advisor.is_available:
        st.warning(
            "Offline — set `GEMINI_API_KEY` in `.env` to enable",
            icon=":material/key_off:",
        )
    elif use_advisor:
        provider_label = {"gemini": "Gemini", "groq": "Groq"}.get(
            advisor.chat_provider, advisor.chat_provider or "—"
        )
        st.success(
            f"Connected — {provider_label} · {len(advisor.snippets)}-doc knowledge base",
            icon=":material/check_circle:",
        )
with ctrl_right:
    generate_clicked = st.button(
        "Generate schedule",
        type="primary",
        use_container_width=True,
        disabled=_total_tasks == 0,
    )

if generate_clicked:
    if not (draft_plan := scheduler.generate_plan()):
        st.warning("No tasks could be scheduled. Check available time or add tasks.")
    else:
        review = None
        if use_advisor and advisor.is_available:
            with st.spinner("Consulting AI care advisor..."):
                review = scheduler.run_advisor_review(draft_plan)

        eligible = scheduler._collect_eligible_tasks()
        skipped = [t for t in eligible if t not in draft_plan]
        final_plan, applied_changes = scheduler.apply_advisor_changes(
            draft_plan, review
        )
        draft_lookup = {(t.name, t.pet_name): t for t in draft_plan}
        # Use object identity so the 🤖 badge only attaches to tasks that
        # were actually replaced (shorten/lengthen/reschedule produce new
        # Task instances; unchanged tasks are still the draft references).
        # Keying by (name, pet) misfires when the user has duplicate-named
        # tasks and only one of them was modified.
        draft_ids = {id(t) for t in draft_plan}
        modified_task_ids = {id(t) for t in final_plan if id(t) not in draft_ids}
        modified_keys = {(c.task_name, c.pet_name) for c in applied_changes}

        # ── Plan headline + table ─────────────────────────────────
        total_time = sum(t.duration for t in final_plan)
        ai_badge = (
            f"  ·  🤖 {len(applied_changes)} AI edit(s)" if applied_changes else ""
        )
        st.success(
            f"Daily plan for {owner.name} — "
            f"{total_time}/{owner.available_time} min used{ai_badge}"
        )

        if review is not None and review.available:
            high = [i for i in review.issues if i.severity == "high"]
            if high:
                st.error(
                    f"🚨 {len(high)} high-severity concern(s) — see the AI "
                    "section below before following the plan."
                )

        if scheduler.conflicts:
            st.error(
                f"{len(scheduler.conflicts)} time conflict(s) detected — "
                "consider rescheduling the overlapping tasks."
            )
            for conflict in scheduler.conflicts:
                st.caption(f"• {conflict}")

        st.table([
            {
                "#": i,
                "Time": (
                    Scheduler._fmt_time(t.scheduled_time)
                    if t.scheduled_time is not None
                    else "—"
                ),
                "Task": ("🤖 " if id(t) in modified_task_ids else "") + t.name,
                "Pet": t.pet_name,
                "Min": t.duration,
                "Priority": t.priority.name,
                "Recurrence": t.recurrence or "—",
            }
            for i, t in enumerate(final_plan, start=1)
        ])

        if skipped:
            with st.expander(f"⏭️ Tasks that didn't fit ({len(skipped)})"):
                st.table([
                    {
                        "Task": t.name,
                        "Pet": t.pet_name,
                        "Min": t.duration,
                        "Priority": t.priority.name,
                    }
                    for t in skipped
                ])

        # ── AI advisor section ────────────────────────────────────
        if review is not None:
            st.divider()
            st.subheader("🤖 AI care advisor")

            if not review.available:
                st.info(f"Advisor unavailable: {review.error}")
            else:
                if review.summary:
                    st.markdown(review.summary)

                if applied_changes:
                    st.markdown("**Edits applied to the plan**")
                    st.table([
                        {
                            "Task": f"{c.task_name} ({c.pet_name})",
                            "Change": _format_change(c, draft_lookup),
                            "Reason": c.reason,
                            "Sources": ", ".join(c.citations) or "—",
                        }
                        for c in applied_changes
                    ])
                    permanent = [
                        c for c in applied_changes
                        if c.change_type == "remove"
                        and (old := draft_lookup.get((c.task_name, c.pet_name)))
                        and not old.is_recurring
                    ]
                    if permanent:
                        st.warning(
                            f"🗑️ {len(permanent)} non-recurring task(s) "
                            "were deleted from your task list permanently."
                        )
                    # Persist enough state for the Save-to-task-list button
                    # rendered below (a button click triggers a fresh rerun
                    # where generate_clicked is False, so the in-block button
                    # would be unreachable).
                    st.session_state["pending_save"] = {
                        "draft_plan": list(draft_plan),
                        "applied_changes": list(applied_changes),
                    }
                else:
                    st.session_state.pop("pending_save", None)

                other_issues = [
                    i for i in review.issues
                    if (i.task_name, i.pet_name) not in modified_keys
                ]
                if other_issues:
                    st.markdown("**Other concerns**")
                    for item in other_issues:
                        sources = (
                            ", ".join(f"`{c}`" for c in item.citations) or "—"
                        )
                        st.markdown(
                            f"**{item.task_name} — {item.pet_name}**  \n"
                            f"{item.issue}  \n"
                            f"_Recommendation:_ {item.recommendation}  \n"
                            f"_Sources:_ {sources}"
                        )

                if not applied_changes and not review.issues:
                    st.success("Plan looks fine against retrieved guidance.")

                if review.retrieved_sources:
                    st.caption(
                        "Retrieved: "
                        + ", ".join(f"`{s}`" for s in review.retrieved_sources)
                        + f"  ·  {review.latency_ms} ms"
                    )


# ── Persist AI edits to the underlying task list ─────────────
# Lives outside `if generate_clicked:` so the click survives the rerun
# (Streamlit reruns the script on each interaction; without session_state
# the applied_changes would be unavailable in the rerun the Save click
# triggers).
_pending = st.session_state.get("pending_save")
if _pending:
    if st.button(
        f"Save {len(_pending['applied_changes'])} AI edit(s) to your task list",
        icon=":material/save:",
        help=(
            "Updates the underlying tasks (durations, scheduled times, "
            "and recurring-task removals) so future plans reflect the "
            "advisor's edits. Non-recurring removals are already applied."
        ),
    ):
        saved = 0
        for c in _pending["applied_changes"]:
            target = Scheduler._resolve_target(_pending["draft_plan"], c)
            if target is None:
                continue
            if c.change_type in ("shorten", "lengthen") and c.new_duration_min:
                target.duration = c.new_duration_min
                saved += 1
            elif c.change_type == "reschedule":
                new_start = Scheduler._parse_hhmm(c.new_start_hhmm)
                if new_start is not None:
                    target.scheduled_time = new_start
                    saved += 1
            elif c.change_type == "remove" and target.is_recurring:
                # Non-recurring removes already deleted at apply time;
                # recurring ones are kept by default and removed here only
                # when the owner explicitly clicks Save.
                for pet in owner.pets:
                    if target in pet.tasks:
                        pet.tasks.remove(target)
                        saved += 1
                        break
        del st.session_state["pending_save"]
        st.success(
            f"Saved {saved} edit(s) to your task list. "
            "Re-generate to see the updated plan."
        )
        st.rerun()
