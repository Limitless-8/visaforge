# VisaForge v0.10 — Phase 4 Part 2 (UI + AI Grounding Layer)

This release adds the user-visible Route Plan UI and AI assistant
context wiring on top of the deterministic Phase-4 backend shipped in
v0.10 part 1. No backend logic changed.

## What's in part 2

### Updated files

| File | What changed |
|---|---|
| `services/ai_service.py` | New `RouteStepContext` dataclass · new `ask_about_step()` helper · `build_context()` accepts `focused_step_key` and adds `current_step` + `pakistan_process` blocks · `ask()` accepts `focused_step_key` and switches to a step-focused system prompt with the spec §12 wording. |
| `pages/3_Route_Plan.py` | Full rewrite. Reads from `route_plan_service`. Three sections (A/B/C) with status pills, priority badges, dependency rendering, required documents per step. Action buttons: Go to Profile / Documents / Scholarships, Explain this step, How to complete this in Pakistan, Ask AI about this step. Shows selected scholarship at top. Re-generate button calls `generate_and_save()`. **No manual status dropdowns anywhere.** |
| `pages/6_AI_Assistant.py` | Reads `st.session_state['ai_step_context']` on arrival from a Route Plan action. Auto-runs the composed question and stays in step-focused mode for follow-up turns. Clear-focus button to return to general chat. |
| `pages/7_Dashboard.py` | Prominent next-action card driven by `JourneyStatus.current_step()` with friendly headlines per stage (Complete profile / Run eligibility / Select scholarship / Generate route plan / Continue with documents). Route plan card now reads from `route_plan_service.get_persisted_plan()` to show overall + per-section progress. |

### Verification

* All 61 Python files compile.
* All cross-file imports resolve.
* 47 wiring checks pass:
  - `ai_service`: `RouteStepContext`, `ask_about_step`, `focused_step_key` kwarg, both system prompts present, spec §12 wording verbatim, `current_step` + `pakistan_process` blocks built into context, imports `route_plan_service` + `pakistan_policy_service`.
  - `3_Route_Plan.py`: imports `get_persisted_plan` + `generate_and_save`, does NOT import the legacy `route_service` or `update_step_status`, no status dropdowns, all 3 sections rendered, all 5 status pills, all 6 spec-required action buttons, hands `RouteStepContext` to AI Assistant via `session_state` + `switch_page`.
  - `6_AI_Assistant.py`: pops `ai_step_context` on arrival, auto-runs composed question, passes `focused_step_key` on follow-up turns, has Clear-focus button.
  - `7_Dashboard.py`: uses `current_step()`, headline cards for all 5 spec §13 stages, reads persisted plan for route card.

### What did NOT change

* `services/route_plan_service.py` — untouched.
* `services/pakistan_policy_service.py` — untouched.
* `services/scholarship_service.py` — untouched.
* `services/journey_service.py` — untouched.
* `models/orm.py`, `models/schemas.py`, `db/init_db.py` — untouched.
* No new tables, no new columns, no migrations needed.

## Deployment

Drop the four files into your existing v0.10 part 1 install:

```
services/ai_service.py
pages/3_Route_Plan.py
pages/6_AI_Assistant.py
pages/7_Dashboard.py
```

Restart Streamlit:

```powershell
streamlit run app.py
```

That's it. The deterministic backend from part 1 is unchanged, so no
DB migration runs.

## End-to-end smoke test (manual)

1. Sign in. Dashboard now shows a prominent next-action card.
2. If a profile + eligibility + scholarship selection are all in place,
   click **Generate your route plan** → lands on the new Route Plan
   page.
3. Click **Generate plan** (or **Re-generate plan**) → three sections
   appear with status pills.
4. On any step, expand **Actions**, click **Explain this step** → the
   AI Assistant opens, auto-runs a composed question, and answers
   grounded in that specific step's structured context.
5. On a Pakistan-section step (e.g. HEC Attestation), click **🇵🇰 How
   to complete this in Pakistan** → the assistant uses the structured
   `pakistan_process` block (requirements, steps, official source URL)
   and refuses to invent rules outside it.
6. Try following up with a free-form question while in step-focused
   mode — the focus banner stays visible until you click **Clear
   focus**.
