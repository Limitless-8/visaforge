# ✈️ VisaForge

> **AI-assisted immigration & scholarship guidance for students** targeting the UK, Canada, and Germany.

VisaForge combines a **deterministic rule engine** for visa eligibility with **grounded AI guidance** and **live scholarship discovery** from curated, credible sources. Built as a serious academic MVP — modular, explainable, and demo-ready.

---

## 🏗️ Architecture at a glance

```
┌─────────────────────────────────────────────────────────────────┐
│                      Streamlit UI layer                         │
│   app.py + pages/   (landing, profile, eligibility, route,      │
│                      scholarships, docs, AI, dashboard, admin)  │
├─────────────────────────────────────────────────────────────────┤
│                       Services layer                            │
│   profile · eligibility · route · document · policy             │
│   scholarship · ingestion · ai                                  │
├────────────────┬────────────────┬─────────────────┬─────────────┤
│   LLM layer    │ Ingestion layer│  Data layer     │  Config     │
│  (factory →    │  (factory →    │  SQLAlchemy ORM │  settings   │
│   Groq ✓       │   Firecrawl ✓  │  + Pydantic     │  + secrets  │
│   OpenAI ·)    │   TinyFish ·   │  + JSON seeds   │             │
│                │   Playwright · │  + SQLite       │             │
│                │   Crawlee ·)   │                 │             │
└────────────────┴────────────────┴─────────────────┴─────────────┘
                       ✓ = active   · = placeholder
```

**Key design principles**

1. **Deterministic first.** Rule-based engine decides eligibility. AI only *explains*.
2. **Provider abstraction.** LLM and ingestion vendors are swappable via config.
3. **Grounded AI.** LLM context packet is built from your deterministic outputs; the system prompt forbids hallucination and overriding rules.
4. **Never fabricate.** Missing scholarship deadlines stay `None`. Unparseable pages become attributed fallback entries, not made-up content.
5. **Graceful degradation.** Firecrawl outage? Falls back to polite HTTP + BeautifulSoup. LLM key missing? Deterministic pages still work.
6. **Migration ready.** SQLite↔Postgres via `DATABASE_URL`. Streamlit→FastAPI by lifting `services/`. Groq→OpenAI by editing one line.

---

## 📁 Project structure

```
visaforge/
├── app.py                     # Landing page
├── requirements.txt
├── README.md
├── .env.example
├── .streamlit/
│   ├── config.toml            # Theme
│   └── secrets.toml.example
├── config/
│   └── settings.py            # Single source of truth for config
├── db/
│   ├── database.py            # Engine + session_scope()
│   └── init_db.py             # Schema + seed loader (idempotent)
├── models/
│   ├── orm.py                 # SQLAlchemy 2.0 entities
│   └── schemas.py             # Pydantic DTOs
├── services/                  # Orchestration layer — UI never calls ORM directly
│   ├── profile_service.py
│   ├── eligibility_service.py # ★ Deterministic engine
│   ├── route_service.py       # ★ Template-driven workflows
│   ├── document_service.py
│   ├── policy_service.py
│   ├── scholarship_service.py
│   ├── ingestion_service.py   # ★ Orchestrates provider → parser → DB → log
│   ├── ai_service.py          # ★ Grounded context builder
│   ├── document_extraction_service.py  # Extension point
│   └── ocr_service.py         # Placeholder
├── llm/
│   ├── base.py                # LLMProvider interface
│   ├── groq_provider.py       # ★ Active
│   ├── openai_provider.py     # Placeholder (scaffolded)
│   └── factory.py
├── ingestion/
│   ├── base.py                # IngestionProvider interface
│   ├── firecrawl_provider.py  # ★ Active (+ HTTP fallback)
│   ├── tinyfish_provider.py   # Placeholder
│   ├── playwright_provider.py # Placeholder
│   ├── crawlee_provider.py    # Placeholder
│   ├── parser.py              # Scholarship extraction heuristics
│   └── factory.py
├── components/
│   ├── ui.py                  # Shared UI helpers (sidebar, disclaimer, …)
│   └── badges.py              # Colored status pills
├── utils/
│   ├── logger.py
│   └── helpers.py             # iso_now, truncate, deadline parser, …
├── data/
│   └── seeds/
│       ├── visa_rules.json           # ★ Deterministic rule definitions
│       ├── route_templates.json      # ★ Country workflows
│       ├── document_checklists.json
│       ├── source_registry.json      # ★ Curated ingestion sources
│       └── seed_scholarships.json    # Offline-safe demo data
└── pages/
    ├── 1_👤_Profile.py
    ├── 2_✅_Eligibility.py
    ├── 3_🗺️_Route_Plan.py
    ├── 4_🎓_Scholarships.py
    ├── 5_📄_Documents.py
    ├── 6_🤖_AI_Assistant.py
    ├── 7_📊_Dashboard.py
    └── 8_⚙️_Admin.py
```

---

## 🚀 Local setup

### 1. Clone & create a virtualenv

```bash
git clone <your-repo-url> visaforge
cd visaforge
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure secrets

Copy `.env.example` to `.env` and fill in keys:

```bash
cp .env.example .env
```

Required for full functionality:

- `GROQ_API_KEY` — get one free at https://console.groq.com/keys
- `FIRECRAWL_API_KEY` — get one at https://firecrawl.dev (optional: the app falls back to polite HTTP fetching if missing)

### 3. Run

```bash
streamlit run app.py
```

The first run auto-creates `data/visaforge.db` (SQLite) and seeds the source registry and demo scholarships.

### 4. First-use flow

1. Go to **👤 Profile**, create a profile.
2. **✅ Eligibility** — run the deterministic check.
3. **🗺️ Route Plan** — see your workflow; steps tied to failing rules are auto-marked `pending_evidence`.
4. **🎓 Scholarships** — browse seeded entries; bookmark some.
5. **⚙️ Admin → 🌐 Sources → Refresh ALL** — fetch live scholarships (requires Firecrawl key, or falls back to HTTP).
6. **📄 Documents** — track your checklist.
7. **🤖 AI Assistant** — ask grounded questions.
8. **📊 Dashboard** — single-pane overview.

---

## ☁️ Streamlit Cloud deployment

1. Push the repo to GitHub.
2. On [share.streamlit.io](https://share.streamlit.io), create a new app pointing to `app.py`.
3. In **Settings → Secrets**, paste the content of `.streamlit/secrets.toml.example` and fill in real keys:

   ```toml
   LLM_PROVIDER = "groq"
   GROQ_API_KEY = "gsk_…"
   GROQ_MODEL = "llama-3.3-70b-versatile"

   INGESTION_PROVIDER = "firecrawl"
   FIRECRAWL_API_KEY = "fc_…"

   DATABASE_URL = "sqlite:///data/visaforge.db"
   APP_ENV = "production"
   ```

4. Deploy. The app bootstraps its DB on first launch.

> **Note on SQLite on Streamlit Cloud:** the filesystem is ephemeral — user profiles persist only within a single container lifetime. For production, set `DATABASE_URL` to a Postgres URL (see "Future migrations" below).

---

## 🧠 How the deterministic engine works

Rules live in `data/seeds/visa_rules.json` and have this shape:

```json
{
  "id": "uk_proof_of_funds",
  "description": "Proof of funds covering course fees and living costs.",
  "field": "has_proof_of_funds",
  "check": "is_true",
  "weight": 1.0,
  "evidence_required": ["Bank statements showing required maintenance funds"]
}
```

Supported `check` primitives: `non_empty_date`, `is_true`, `numeric_min`, `numeric_min_or_na`, `non_empty_string`.

Each evaluation produces an `EligibilityReport` with:
- `status` — `eligible` / `partial` / `not_eligible`
- `confidence` — weighted score
- `trace` — per-rule `RuleEvaluation` with outcome, detail, and required evidence
- `missing_evidence` — deduplicated list

The LLM in `services/ai_service.py` receives this report as **authoritative grounding context** and is explicitly instructed not to contradict it.

---

## 🌐 Live ingestion

`ingestion/firecrawl_provider.py` is the active provider:

1. Calls Firecrawl's `scrape_url` for markdown output.
2. If Firecrawl fails or is unconfigured → falls back to `requests` + BeautifulSoup with a polite User-Agent.
3. `ingestion/parser.py` extracts scholarship-like entries from the text:
   - Markdown-link heuristic (anchor contains *scholarship/bursary/fellowship/grant/award*)
   - Heading heuristic
   - Fallback: one attributed page-level entry
4. `services/ingestion_service.py` upserts entries, updates source timestamps, and writes a `FetchLog`.

### Adding a source

Either via the **Admin → Sources → ➕ Add** form, or by editing `data/seeds/source_registry.json` and restarting (the seed loader is idempotent).

### Polite crawling

- Distinct User-Agent: `VisaForgeBot/0.1 (academic research prototype; …)`.
- HTTP timeout: 20s.
- No concurrent floods — refreshes are sequential.
- **Always** respect each target's `robots.txt` and terms of use before enabling a source.

---

## 🔁 Future migrations

| From (MVP)              | To (production)                   | How                                                                              |
| ----------------------- | --------------------------------- | -------------------------------------------------------------------------------- |
| Streamlit               | FastAPI + separate frontend       | Services are framework-free. Wrap `services/*` in FastAPI routers.               |
| SQLite                  | PostgreSQL                        | Change `DATABASE_URL`, `pip install psycopg2-binary`, run Alembic migrations.    |
| Groq                    | OpenAI                            | Uncomment scaffold in `llm/openai_provider.py`, set `LLM_PROVIDER=openai`.       |
| No Docker               | Docker + Compose                  | Add `Dockerfile` with `streamlit run app.py`; volumes for `/data`.               |
| Firecrawl               | TinyFish / Playwright / Crawlee   | Implement the provider scaffold; set `INGESTION_PROVIDER=…`.                     |
| Static rule JSON        | Dynamic policy ingestion          | Persist rules to DB; admin UI for editing; versioning.                           |
| In-session file uploads | Object store + OCR                | Implement `services/ocr_service.py` and `document_extraction_service.py`.        |

No code outside the relevant module needs to change for any of these swaps.

---

## 🛡️ Responsible design

- **Disclaimer** shown on every page: VisaForge is guidance support, **not legal advice**.
- **No hallucinated deadlines.** The deadline parser in `utils/helpers.py` only returns dates that literally appear in source text.
- **Source attribution** stored on every scholarship record (URL, source name, credibility level, fetch timestamp).
- **Confidence scores** exposed on the eligibility verdict — users see when the system is not sure.
- **Redacted secrets** in the admin Config tab (never expose raw keys).
- **Minimal PII.** Only what's needed for the eligibility engine; no passwords, no IDs stored.

---

## 📜 License & attribution

- Official source content linked to and attributed at all times; VisaForge does not redistribute copyrighted content.
- Respects each source's `robots.txt` and terms of use — disable sources that disallow automated access.

---

## 🧪 Troubleshooting

| Symptom                                                      | Fix                                                                             |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------- |
| `AI provider is not configured`                              | Set `GROQ_API_KEY` in `.env` or Streamlit secrets.                             |
| Scholarships page shows only seed entries                    | Go to **Admin → Sources → Refresh ALL**. Check fetch logs for errors.          |
| `groq` package missing                                       | `pip install -r requirements.txt`.                                             |
| Firecrawl errors                                             | App auto-falls back to HTTP. Check the **Fetch logs** tab for details.         |
| Need to edit rules                                           | Edit `data/seeds/visa_rules.json`, then **Admin → Config → Reload visa rules**. |
| DB reset needed                                              | Delete `data/visaforge.db` and restart.                                         |

---

Built with ❤️ as a research MVP. PRs and supervisor feedback welcome.
