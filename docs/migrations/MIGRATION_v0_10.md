# VisaForge v0.10 — Phase 4: Scholarship-Driven Route Plan (Part 1 of 2)

This release lays the deterministic foundation for the Phase-4
scholarship-driven route plan: the data model, the Pakistan-policy
catalogue, and the generator. **Part 2** (next release) ships the UI
rewrite (`pages/3_Route_Plan.py`), the AI-assistant context wiring,
and Dashboard updates.

## What's in part 1

### New services
* **`services/pakistan_policy_service.py`** — read-only access to the
  Pakistan-specific process catalogue. Provides `get_process()`,
  `list_processes_for_country()`, `required_for_destination()`, and
  `explain_for_ai()` (a stable AI-grounding subset).
* **`services/route_plan_service.py`** — destination-aware deterministic
  generator. Produces a `DynamicRoutePlanDTO` with three sections
  (Scholarship Application Phase / Pakistan Preparation Phase /
  Visa Application Phase). Status of every step is derived from
  profile + eligibility + document data; users never set it manually.

### New seed data
* **`data/seeds/pakistan_processes.json`** — 7 Pakistan processes
  (HEC attestation, IBCC equivalence, MOFA attestation, PCC, passport,
  TB test, NADRA documents) with full structured fields per spec §8.

### Extended data model
* `models/orm.py` — `RoutePlan` gains `scholarship_id` + `user_id`
  (both nullable, FK with `SET NULL`). `RouteStep` gains 8 new columns
  per spec §4: `section_id`, `source`, `priority`,
  `required_documents_json`, `action_label`, `action_target`,
  `help_text`, `pakistan_process_id`.
* `models/schemas.py` — `DynamicRouteStepDTO`, `RouteSectionDTO`,
  `DynamicRoutePlanDTO` (kept distinct from the legacy v0.1 DTOs so
  the old `route_service` keeps working until part 2 retires it).

### Tighter selection + journey rules
* `services/scholarship_service.py` — `set_selected_scholarship()`
  now refuses non-approved or non-user-visible scholarships per
  spec §14.
* `services/journey_service.py` — `route_plan_generated` is now
  `True` only when ALL of: profile complete, eligibility completed,
  scholarship selected, AND a `RoutePlan` row exists. Per spec §13.

### Verified end-to-end (9 scenarios, 32 individual checks)
* UK Chevening fresh profile → scholarship phase available, visa
  phase locked
* UK advanced profile → CAS, funds, doc-driven steps all completed
* NOT_ELIGIBLE → all 5 visa steps blocked, scholarship phase still
  available, `plan.blocked_reason` set
* Canada Vanier route → uses `ca_default_v0_10` template
* Germany DAAD route → uses `de_default_v0_10`, includes MOFA
* Visa app step locks when `passport_issuance` / `tb_test` not done;
  unlocks when both are completed
* Progress percentages are computed correctly per section and overall
* No scholarship selected → `generate_plan()` returns None
* Unsupported destination country → returns None

## What's NOT in part 1 (coming in part 2)

These are the user-visible / AI-side pieces:

1. **`pages/3_Route_Plan.py`** — full UI rewrite. Three grouped
   sections, no manual-status dropdowns, status badges, action buttons
   ("Go to Profile", "Go to Documents", "Go to Scholarships",
   "Ask AI about this step"), per spec §10.
2. **`pages/6_AI_Assistant.py` + `services/ai_service.py`** — accept
   structured route step + Pakistan policy context per spec §11–§12.
   New system instruction: "You are an immigration guidance assistant
   for Pakistani students. You explain only from provided structured
   data..."
3. **`pages/7_Dashboard.py`** — Surface "Generate route plan" as the
   next-step recommendation when a scholarship is selected but no
   plan exists.

The route plan generator can already run and persist plans; it just
isn't yet rendered in the UI. The legacy `pages/3_Route_Plan.py`
keeps showing the v0.1 generic route until part 2.

## Database migration

The bootstrap (`db/init_db.py → initialize()`) handles everything
automatically. Every additive migration is idempotent and safe.

You do **NOT** need to run any SQL by hand.

### If you want to run the migration manually

```powershell
# v0.10 columns on route_plans
sqlite3 .\data\visaforge.db "ALTER TABLE route_plans ADD COLUMN scholarship_id INTEGER;"
sqlite3 .\data\visaforge.db "ALTER TABLE route_plans ADD COLUMN user_id INTEGER;"

# v0.10 columns on route_steps
sqlite3 .\data\visaforge.db "ALTER TABLE route_steps ADD COLUMN section_id VARCHAR(40);"
sqlite3 .\data\visaforge.db "ALTER TABLE route_steps ADD COLUMN source VARCHAR(40);"
sqlite3 .\data\visaforge.db "ALTER TABLE route_steps ADD COLUMN priority VARCHAR(20);"
sqlite3 .\data\visaforge.db "ALTER TABLE route_steps ADD COLUMN required_documents_json TEXT DEFAULT '[]';"
sqlite3 .\data\visaforge.db "ALTER TABLE route_steps ADD COLUMN action_label VARCHAR(80);"
sqlite3 .\data\visaforge.db "ALTER TABLE route_steps ADD COLUMN action_target VARCHAR(120);"
sqlite3 .\data\visaforge.db "ALTER TABLE route_steps ADD COLUMN help_text TEXT;"
sqlite3 .\data\visaforge.db "ALTER TABLE route_steps ADD COLUMN pakistan_process_id VARCHAR(60);"

# Verify
sqlite3 .\data\visaforge.db "PRAGMA table_info(route_plans);"
sqlite3 .\data\visaforge.db "PRAGMA table_info(route_steps);"
```

Then start the app:

```powershell
streamlit run app.py
```

## Smoke-test the new generator from a Python REPL

```powershell
python -c "
from services.route_plan_service import generate_plan
plan = generate_plan(profile_id=1)  # use your profile id
print('Plan:', plan.template_key, plan.destination_country)
for s in plan.sections:
    print(f'  {s.title} — {s.progress_pct}%')
    for step in s.steps:
        print(f'    [{step.status:10s}] {step.title}')
"
```

## Rollback

The new columns are all nullable / default-able. To revert to v0.9:

* Stop using `services/route_plan_service.py`.
* The legacy `services/route_service.py` (v0.1 generic templates) is
  unchanged and continues to drive the existing
  `pages/3_Route_Plan.py`.
