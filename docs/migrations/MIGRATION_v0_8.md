# VisaForge v0.8 — Source Classification

This upgrade fixes the bug where visa policy pages from
`auswaertiges-amt.de` (and similar consular/foreign-office pages) were
being shown as scholarships in the user-facing Scholarships page.

## What changed

* **New deterministic source classifier**: every scraped or seeded
  scholarship row is now classified into one of five buckets:
  `actual_scholarship`, `scholarship_directory`, `visa_policy_page`,
  `generic_education_page`, or `invalid_or_noise`.
* **User view filters**: only `actual_scholarship` and
  `scholarship_directory` are shown to applicants. Everything else is
  kept in the database for admin review but hidden from results.
* **Admin view**: a new "🎓 Scholarships" tab in the admin panel shows
  all rows with their classification, lets you reclassify all rows
  with one click, and includes a sandbox for testing the classifier on
  arbitrary input.
* **No AI**: classification is rule-based with weighted keyword
  signals. Fully deterministic and explainable.

## Database migration

The bootstrap (`db/init_db.py → initialize()`) handles the migration
automatically when you next start the app — it adds the new
`source_type` column to `scholarship_entries` and classifies every
existing row.

You do **NOT** need to run any SQL by hand.

### If you want to run the migration manually anyway

For supervisor demo / audit purposes, here is the exact SQL the
bootstrap runs. From PowerShell, with the SQLite CLI installed:

```powershell
# Add the new column (idempotent — bootstrap also does this)
sqlite3 .\data\visaforge.db "ALTER TABLE scholarship_entries ADD COLUMN source_type VARCHAR(40);"

# Verify it was added
sqlite3 .\data\visaforge.db "PRAGMA table_info(scholarship_entries);"
```

If `sqlite3` is not on your PATH, you can install it with `scoop install sqlite` or download from https://www.sqlite.org/download.html.

After the column exists, **start the app once** so that
`initialize()` classifies every existing row:

```powershell
streamlit run app.py
```

The bootstrap log will show something like:
```
Seeded 0 demo scholarships; backfilled eligibility on 0, source_type on 47.
```

## Verifying the fix

1. Log in as admin → "🎓 Scholarships" tab
2. The table shows every row's `source_type` and a `user_visible` flag
3. Counts by type appear at the top:
   ```json
   {
     "actual_scholarship": 9,
     "scholarship_directory": 2,
     "visa_policy_page": 3,
     "generic_education_page": 1
   }
   ```
4. Visit the user-facing Scholarships page → only the
   `actual_scholarship` + `scholarship_directory` rows appear
5. The visa policy pages stay in the database (auditable) but are
   filtered from the user view

## Rolling back

If a real scholarship gets misclassified, click "🔁 Reclassify all" in
the admin tab after refining the classifier rules in
`services/source_classifier.py`. No DB reset needed.

To temporarily disable the filter (debug only), set
`include_hidden=True` in any `list_scholarships(...)` call.
