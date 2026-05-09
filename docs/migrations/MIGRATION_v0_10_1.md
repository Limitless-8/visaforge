# VisaForge v0.10.1 — Route Plan Dependency Unlock Fix

## Bug

After marking Step 1 (`check_scholarship_eligibility`) as complete, Step 2
remained locked with a stale "Waiting for: check_scholarship_eligibility"
message. Dependent steps did not recompute when their dependencies became
satisfied.

## Root cause

Three interlocking bugs in `services/route_plan_service.py`:

1. **Wrong overlay order in `generate_plan`.** The user-completion overlay
   (which marks user-acknowledged steps as `completed`) ran *after* the
   dependency resolver. The resolver therefore saw the freshly completed
   step as still `available` and locked all dependents with stale "Waiting
   for: X" messages. Then the overlay marked X as completed — but the
   resolver never ran again, so dependents stayed locked.

2. **`get_persisted_plan` never re-resolved.** It read raw rows from the
   database with whatever stale status / status_reason was last persisted
   and returned them as-is. Any state change since the last save (a step
   marked complete elsewhere, a document uploaded, an eligibility re-run)
   never cascaded to dependents on read.

3. **`mark_step_complete` did not write back sibling state.** It updated
   the one row the user clicked on, but the persisted DB rows for
   downstream steps kept their stale "locked" status. Display via
   `get_persisted_plan` would re-resolve in memory (after fix 2), but
   the persisted data drifted further from truth on every write.

There was also a 4th sub-bug inside `_resolve_dependencies`: when a
step's dependencies were now satisfied, the resolver kept the step's
existing `status_reason` even if it was a stale "Waiting for: X."
message. The visible effect was a step that had upgraded to `available`
but still showed the old waiting text.

## Fix

### `services/route_plan_service.py`

* **`_resolve_dependencies`** (existing function — bug fix):
  - `completed` status now propagates as-is alongside `blocked`. The
    resolver no longer demotes a completed step. Spec compliance:
    "Completed steps must stay completed."
  - When a step's deps are now satisfied AND its prior status was
    `locked` with a "Waiting for:" reason, upgrade to `available` and
    clear the reason.
  - When a step's deps are satisfied AND its prior reason starts with
    "Waiting for:" but the step was already `available`/`pending`,
    clear the stale reason while preserving the intrinsic status.
  - Waiting messages now use dependency *titles*, not raw keys, for
    friendlier UX.

* **`generate_plan`** (existing function — order fix):
  - The evidence overlay and user-completion overlay now run BEFORE
    `_resolve_dependencies`, not after. This means any completion
    correctly cascades to dependents in a single pass.

* **`get_persisted_plan`** (existing function — bug fix):
  - Now runs `_resolve_dependencies` on every read. Persisted
    `status='completed'` rows are sticky and propagate through the
    resolver, unlocking dependents and clearing stale messages on
    every page load.

* **`mark_step_complete`** (existing function — write-back):
  - After marking a step complete, calls
    `recompute_states_for_plan(profile_id, country)` to bring all
    sibling rows back into sync with the new truth.

* **`recompute_states_for_plan`** (NEW public function):
  - Recomputes every persisted RouteStep's status + status_reason
    against current truth (intrinsic from profile/eligibility/docs,
    sticky from `completed_at`, then dependency resolution). Persists
    any drift back to the DB. Sticky completed steps are never
    demoted. Idempotent — safe to call on every page load.

### `pages/3_Route_Plan.py`

* Imports `recompute_states_for_plan` and calls it on every page
  load, before `get_persisted_plan`. Out-of-band updates (a document
  uploaded on the Documents page, an eligibility re-run, etc.) now
  cascade to dependents on the next view.

### What did NOT change

* Status enum (locked/available/pending/completed/blocked) — unchanged.
* Manual status dropdown — still absent. Still no manual override.
* Document verification logic — unchanged.
* Pakistan policy steps — unchanged.
* Scholarship selection — unchanged.
* AI explain buttons — unchanged.
* ORM columns / migrations — none needed.

## Verification

11 individual checks pass against `_resolve_dependencies` alone:

1. ✅ Completed step propagates: dependent unlocks `locked → available`
2. ✅ Stale "Waiting for: X" message cleared when X is now completed
3. ✅ "Waiting for" message names ONLY the unmet deps (not completed ones)
4. ✅ Completed status is sticky (never demoted, even with unmet deps)
5. ✅ Blocked status is sticky (propagates as-is)
6. ✅ Pending status preserved when deps satisfied
7. ✅ Stale messages on already-`available` steps also cleared
8. ✅ Unknown dependency keys correctly lock the step
9. ✅ All 4 deps of step 1 correctly locked initially (step 1 is `available`,
       not `completed`)
10. ✅ Waiting messages use dependency *titles*, not raw keys
11. ✅ NOT_ELIGIBLE blocked status still works (no regression)

End-to-end regression run against v0.10 part-1 scenarios (UK fresh,
UK advanced, NOT_ELIGIBLE) confirmed no break.

All 63 Python files compile. All cross-file imports resolve.

## Deployment

Drop the two updated files into your existing v0.10 install:

```
services/route_plan_service.py
pages/3_Route_Plan.py
```

Restart Streamlit:

```powershell
streamlit run app.py
```

No DB migration. No data reset. The first page load after the upgrade
will run `recompute_states_for_plan` automatically and bring any
already-drifted persisted rows back into sync.

## Manual smoke test

1. Open Route Plan as a user with a selected scholarship.
2. Step 1 (`check_scholarship_eligibility`) should be **available**.
3. The four steps that depend on it should be **locked** with reason
   "Waiting for: Check scholarship eligibility."
4. Click "Mark step complete" on Step 1.
5. The page reloads. Step 1 should now be **completed** (✅).
6. **The four dependent steps should now be `available`** with no
   "Waiting for:" message.
7. Mark essays + references + gather complete.
8. `submit_scholarship_application` should unlock to `available`.
9. Mark submit complete → `track_scholarship_decision` unlocks.
10. Mark track complete → CAS / LOA / Zulassung step in the visa phase
    unlocks (provided your offer status reflects an unconditional offer).
