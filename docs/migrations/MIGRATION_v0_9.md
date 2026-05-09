# VisaForge v0.9 — Curated Source Refresh System (Part 1 of 2)

This upgrade lays the foundation for the controlled, trustworthy
scholarship refresh system described in the v0.9 spec. **Part 1**
(this release) ships the data model, registry, classifier extensions,
and admin/user gates. **Part 2** (next release) ships the crawl
orchestrator, structured extractor, and change detection.

## What's in part 1

### New / extended data model
* New **`curated_sources`** table — registry of approved crawl roots.
  Each row carries `start_urls`, `allowed_domains`, `follow_keywords`,
  `block_keywords`, `max_depth`, and `is_active` flags. JSON-list
  fields are stored as TEXT for SQLite portability.
* `scholarship_entries` extended with four new columns:
  * `review_status` — `pending_review` / `approved` / `rejected` /
    `needs_attention`. NULL is treated as approved for back-compat.
  * `extracted_payload_json` — full v0.9 structured extraction payload
    (populated by part 2).
  * `version` — bumps when part 2 detects changed fields.
  * `curated_source_id` — FK back to the curated source that
    produced this row.

### Page classifier extended
The v0.8 classifier knew 5 page types; v0.9 adds 4 more:
* `eligibility_page` — “Who can apply” / “Eligibility criteria” pages
* `application_process_page` — “How to apply” / process guides
* `deadline_page` — “Application deadline” / key-dates pages
* `country_specific_page` — “Scholarships for Pakistani students”
  country landing pages

These count as user-visible (per spec §3) — they're crawl by-products
*of* a real scholarship, not noise. A new sub-page override ensures a
title like “Eligibility criteria | Chevening” classifies as
`eligibility_page` rather than the generic `actual_scholarship`.

### User visibility filter (spec §7)
The Scholarships page now requires BOTH:
* `source_type` ∈ user-visible set (was already enforced in v0.8), AND
* `review_status` is `approved` (or NULL — back-compat)

Empty state shows the spec's exact copy:
> No approved scholarships are currently available. Please ask an
> admin to refresh and approve sources.

### Admin page (new tabs)
* **🗂️ Curated** — read-only registry inspector. List, filter by
  active, drill into a single source's URLs/keywords/depth, toggle
  active flag, re-seed from JSON.
* **🛡️ Review queue** — queue UI with counts by status, list view,
  per-row Approve / Reject / Needs Attention / Send-to-Pending
  buttons.

### Curated seed sources (spec §11)
The seed JSON ships **8 curated sources** across the three target
destinations:

* **UK** (3): Chevening, Commonwealth Scholarship Commission, GREAT
  Scholarships (British Council)
* **Canada** (2): EduCanada, Vanier Canada Graduate Scholarships
* **Germany** (3): DAAD Scholarship Database, DAAD Study Scholarships
  (Masters), Deutschlandstipendium

Six of eight have Pakistan/Pakistani in their `follow_keywords` per
the spec's Pakistan-first focus.

## What's NOT in part 1 (coming in part 2)

These are the bigger pieces of the spec that need their own
implementation + verification turn:

* **Crawl orchestrator** — controlled link following with
  depth/keyword filtering and per-source rate limits
* **Structured extraction** — produce `ExtractedScholarship` payloads
  from fetched HTML. The DTO shape is defined; the extractor isn't
  built yet.
* **Change detection** — diff old vs new extracted payloads, classify
  severity (`critical` / `informational`), surface in admin
* **Updated FetchLog schema** — new fields like `pages_fetched`,
  `pages_skipped`, `new_records`, `changed_records`
* **Curated source CREATE/UPDATE/DELETE UI** — currently the admin
  inspector is read-only with an active toggle; full CRUD comes with
  part 2

The "Refresh source" button in part 2 will tie these together.

## Database migration

The bootstrap (`db/init_db.py → initialize()`) handles everything
automatically — adds the new table, adds the 4 new columns, classifies
existing rows, and backfills `review_status` so legacy seed
scholarships stay visible to users.

You do **NOT** need to run any SQL by hand.

### If you want to run the migration manually

For audit/demo purposes, here is the exact SQL the bootstrap runs:

```powershell
# 1. Add the new columns to scholarship_entries
sqlite3 .\data\visaforge.db "ALTER TABLE scholarship_entries ADD COLUMN review_status VARCHAR(20);"
sqlite3 .\data\visaforge.db "ALTER TABLE scholarship_entries ADD COLUMN extracted_payload_json TEXT;"
sqlite3 .\data\visaforge.db "ALTER TABLE scholarship_entries ADD COLUMN version INTEGER DEFAULT 1;"
sqlite3 .\data\visaforge.db "ALTER TABLE scholarship_entries ADD COLUMN curated_source_id INTEGER;"

# 2. Verify
sqlite3 .\data\visaforge.db "PRAGMA table_info(scholarship_entries);"

# 3. The new curated_sources table is created automatically by SQLAlchemy
#    on first run (no manual DDL needed).
```

Then start the app once so `initialize()` seeds the curated sources
and backfills `review_status` on every row:

```powershell
streamlit run app.py
```

The bootstrap log will look like:

```
Migrating: adding scholarship_entries.review_status
Migrating: adding scholarship_entries.extracted_payload_json
Migrating: adding scholarship_entries.version
Migrating: adding scholarship_entries.curated_source_id
Seeded/updated 8 curated source(s).
Backfilled review_status on 11 legacy row(s).
```

## Verifying the upgrade

1. Sign in as admin → **🗂️ Curated** tab
   You should see 8 curated sources across UK / Canada / Germany.
2. Open a source — start URLs, follow_keywords, block_keywords, and
   max_depth should display.
3. Visit **🛡️ Review queue**:
   * The 4 status counters appear at top
   * Pending records have ✅ Approve / ❌ Reject / ⚠️ Needs Attention
     buttons
4. As a regular user, visit the Scholarships page:
   * If you have any seed scholarships visible, they'll be there
     (legacy rows backfilled to `approved`)
   * If an admin marks one as `rejected`, it disappears from the
     user view immediately

## Rollback

To temporarily disable the review-status filter (debug only):

```python
# in services/scholarship_service.py, list_scholarships(...)
# comment out the conds.append(or_(... review_status ...)) block
```

To clear all review statuses back to NULL (visible by default):

```powershell
sqlite3 .\data\visaforge.db "UPDATE scholarship_entries SET review_status = NULL;"
```
