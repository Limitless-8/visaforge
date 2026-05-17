# ✈️ VisaForge

> **Deterministic study-abroad workflow guidance with AI-assisted explanations.**

VisaForge is a Streamlit-based academic MVP that helps students prepare for study abroad, scholarship applications, and visa-related documentation. It combines deterministic eligibility evaluation, scholarship matching, route planning, OCR-supported document review, trusted source management, admin monitoring, and explanation-only AI guidance.

The core principle is simple:

> **Deterministic engines make decisions. AI explains only.**

VisaForge is a guidance-support platform. It is **not legal or immigration advice**. Applicants should always verify important information through official government, university, or scholarship sources.

---

## 🌐 Live Demo

**Live App:**  
https://visaforge.streamlit.app/

**Source Code:**  
https://github.com/Limitless-8/visaforge

---

## ✅ Final MVP Stack

The submitted MVP is implemented using:

- **Streamlit** — applicant UI, admin dashboard, and super admin interface
- **streamlit-keyup** — live search behaviour in admin tables
- **Python service modules** — application logic and deterministic engines
- **SQLite** — MVP database persistence
- **SQLAlchemy** — ORM and structured database access
- **bcrypt** — password hashing
- **Role-Based Access Control** — applicant, admin, and super admin permissions
- **Tesseract OCR** — OCR text extraction
- **PyMuPDF** — PDF processing
- **Groq** — LLM provider for explanation-only AI guidance
- **GitHub** — version control and deployment source
- **Streamlit Cloud** — hosted MVP deployment

Future production options include:

- FastAPI API layer
- PostgreSQL database
- pgvector / vector retrieval
- Alembic migrations
- object storage for documents
- token/JWT-based API authentication

These future tools are **not the active MVP runtime**.

---

## 🧠 Key Design Principles

1. **Deterministic first**  
   Eligibility, scholarship fit, route planning, workflow progression, document status, and account-management decisions are handled by deterministic logic.

2. **AI explains only**  
   AI guidance is used to explain deterministic outputs and provide contextual support. It cannot override system decisions.

3. **Transparent workflows**  
   Applicants move through a structured journey: profile → eligibility → scholarship selection → route plan → documents → AI guidance.

4. **Role-based governance**  
   The system separates applicant, admin, and super admin permissions.

5. **Auditability**  
   Privileged admin actions are recorded in audit logs.

6. **Trusted source awareness**  
   The admin dashboard supports trusted source management for scholarship and policy guidance.

7. **Safe account deletion**  
   User and admin account deletion uses anonymisation/deactivation safeguards rather than unsafe raw deletion.

---

## 🏗️ Architecture at a Glance

```text
┌─────────────────────────────────────────────────────────────────────┐
│                         Streamlit MVP Layer                         │
│  app.py + pages/                                                    │
│  Landing · Login · Register · Profile · Eligibility · Scholarships  │
│  Route Plan · Documents · AI Assistant · Dashboard · Admin           │
├─────────────────────────────────────────────────────────────────────┤
│                         Python Service Layer                        │
│  auth · profile · eligibility · scholarship · route · documents      │
│  OCR · AI guidance · trusted sources · notifications · admin audit   │
├──────────────────────────┬──────────────────────────────────────────┤
│        AI Guidance        │              Data Layer                  │
│        Groq LLM           │              SQLite MVP DB               │
│        Explanations only  │              SQLAlchemy ORM              │
├──────────────────────────┴──────────────────────────────────────────┤
│                         Deployment Layer                            │
│                 GitHub → Streamlit Cloud                            │
└─────────────────────────────────────────────────────────────────────┘
```

### Current MVP

- Streamlit app calls Python service modules directly.
- SQLite stores MVP data through SQLAlchemy.
- Groq provides explanation-only AI responses.
- Tesseract OCR and PyMuPDF support document processing.
- Super admin controls manage privileged account actions.

### Future Production Path

VisaForge is structured so that the service layer can later be migrated to:

- FastAPI backend API
- PostgreSQL production database
- pgvector/vector retrieval
- Alembic migrations
- object storage for uploaded documents

---

## 📁 Project Structure

```text
visaforge/
├── app.py
├── requirements.txt
├── packages.txt
├── README.md
├── .env.example
├── .streamlit/
│   ├── config.toml
│   └── secrets.toml.example
├── config/
│   └── settings.py
├── db/
│   ├── database.py
│   └── init_db.py
├── models/
│   ├── orm.py
│   ├── schemas.py
│   └── user.py
├── services/
│   ├── auth_service.py
│   ├── profile_service.py
│   ├── eligibility_service.py
│   ├── scholarship_service.py
│   ├── route_plan_service.py
│   ├── document_service.py
│   ├── document_extraction_service.py
│   ├── document_verification_service.py
│   ├── ai_service.py
│   ├── notification_service.py
│   ├── source_registry_service.py
│   ├── ingestion_service.py
│   └── journey_service.py
├── llm/
│   ├── __init__.py
│   ├── base.py
│   ├── factory.py
│   ├── groq_provider.py
│   └── openai_provider.py
├── ingestion/
│   ├── __init__.py
│   ├── base.py
│   ├── factory.py
│   ├── firecrawl_provider.py
│   ├── parser.py
│   ├── crawlee_provider.py
│   ├── playwright_provider.py
│   └── tinyfish_provider.py
├── components/
│   ├── ui.py
│   └── badges.py
├── utils/
│   ├── helpers.py
│   ├── logger.py
│   ├── reference_data.py
│   └── text_cleaning.py
├── data/
│   ├── visaforge.db
│   └── seeds/
│       ├── visa_rules.json
│       ├── route_templates.json
│       ├── document_checklists.json
│       ├── source_registry.json
│       ├── scholarship_sources.json
│       └── seed_scholarships.json
└── pages/
    ├── 0_Login.py
    ├── 0_Register.py
    ├── 1_Profile.py
    ├── 2_Eligibility.py
    ├── 3_Route_Plan.py
    ├── 4_Scholarships.py
    ├── 5_Documents.py
    ├── 6_AI_Assistant.py
    ├── 7_Dashboard.py
    ├── 8_Admin.py
    └── 9_Reset_Password.py
```

---

## 🚀 Local Setup

### 1. Clone the Repository

```bash
git clone https://github.com/Limitless-8/visaforge.git
cd visaforge
```

### 2. Create and Activate Virtual Environment

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

macOS/Linux:

```bash
source .venv/bin/activate
```

### 3. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Add your API keys if required:

```env
LLM_PROVIDER=groq
GROQ_API_KEY=your_groq_key
GROQ_MODEL=llama-3.3-70b-versatile

DATABASE_URL=sqlite:///data/visaforge.db
APP_ENV=development
```

### 5. Run the App

```bash
streamlit run app.py
```

The app will initialise the SQLite database and seed required demo/source data on first run.

---

## ☁️ Streamlit Cloud Deployment

VisaForge is deployed through **Streamlit Cloud** from the GitHub repository.

### Streamlit Cloud setup

1. Push the repository to GitHub.
2. Open Streamlit Cloud.
3. Create a new app.
4. Select the GitHub repository.
5. Set the main file as:

```text
app.py
```

6. Add required secrets in Streamlit Cloud settings.

Example secrets:

```toml
LLM_PROVIDER = "groq"
GROQ_API_KEY = "your_groq_key"
GROQ_MODEL = "llama-3.3-70b-versatile"

DATABASE_URL = "sqlite:///data/visaforge.db"
APP_ENV = "production"
```

### System packages

`packages.txt` contains system-level dependencies such as Tesseract OCR:

```text
tesseract-ocr
tesseract-ocr-eng
poppler-utils
```

Python packages such as `streamlit-keyup` belong in `requirements.txt`, not `packages.txt`.

---

## 👤 Applicant Features

Applicants can:

- Register and log in
- Create and update their study-abroad profile
- Add passport, academic, destination, language, and finance details
- Run deterministic eligibility evaluation
- View eligibility results, risk flags, and readiness indicators
- Browse scholarship matches
- View scholarship fit scores and criteria
- Select a scholarship
- Generate a route plan
- Track workflow progress
- Upload documents
- Review OCR extraction results
- Ask the AI assistant for explanations
- Reset journey progress
- Delete/anonymise their own account after confirmation

---

## ⚙️ Admin Features

Admins can:

- View applicant analytics
- Search applicant progress records
- Review scholarship records
- Approve/reject scholarship entries
- Monitor official sources
- Manage trusted sources
- View scholarship library records
- Send applicant notifications
- Review notification delivery reports
- Monitor logs

---

## 👑 Super Admin Features

Super admins can:

- Access all normal admin features
- Create admin accounts
- Create or promote super admin accounts only when permitted by root super admin safeguards
- Change user roles
- Activate or deactivate accounts
- Delete/anonymise permitted accounts
- View account-management audit logs
- Review privileged actions

### Root Super Admin Protection

The root super admin account is protected from being:

- demoted
- deactivated
- deleted

by another account.

This prevents accidental or malicious administrative lockout.

---

## 🛡️ Account Deletion and Anonymisation

VisaForge supports safe deletion/anonymisation.

### Applicant self-delete

Applicants can delete/anonymise their own account from the dashboard after:

1. entering their exact email,
2. reviewing a confirmation dialog,
3. confirming the action.

The system removes or anonymises applicant-owned records where safely identifiable, anonymises the user account, disables sign-in, and records an audit event.

### Super admin account deletion

Super admins can safely delete/anonymise permitted accounts through Account Management.

The system:

- disables sign-in,
- anonymises account identity,
- resets role to user,
- replaces the password hash,
- records the action in admin audit logs,
- prevents deletion of the protected root super admin account.

Deleted accounts are hidden by default in account management, with an option to include them for accountability.

---

## 🧮 Deterministic Eligibility Engine

Eligibility rules are stored as structured definitions and evaluated deterministically.

The engine uses applicant profile data such as:

- nationality
- destination country
- academic level
- English language readiness
- financial readiness
- document availability

Outputs include:

- eligibility/readiness status
- confidence/readiness score
- risk flags
- missing requirements
- improvement suggestions

The same input produces the same output.

The AI assistant receives deterministic results as context, but it cannot change or override them.

---

## 🎓 Scholarship Matching

The scholarship matching module compares applicant profiles with scholarship records and criteria.

It produces:

- fit score
- matched criteria
- missing criteria
- unknown criteria
- improvement guidance
- selected scholarship state

Applicants must select a scholarship before generating a route plan so that the workflow reflects the chosen opportunity.

---

## 🗺️ Route Planning and Workflow

VisaForge generates route plans based on:

- applicant profile
- eligibility result
- selected scholarship
- destination country
- preparation requirements

The workflow includes:

- scholarship preparation
- Pakistan-side documentation
- visa preparation
- final submission tasks

Workflow steps can be:

- locked
- available
- pending
- completed
- requiring document evidence
- requiring manual review

This helps applicants follow a structured preparation path instead of treating the process as a random checklist.

---

## 📄 OCR and Document Processing

VisaForge supports document upload and OCR-assisted review.

Document processing uses:

- **PyMuPDF** for PDF processing
- **Tesseract OCR** for text extraction

The system can show:

- extracted text previews
- extracted fields
- warnings
- OCR quality issues
- manual review prompts
- reprocessing options

OCR results are not treated as automatically correct. Users are shown warnings and review controls where extraction is uncertain.

---

## 🤖 AI Guidance

VisaForge uses Groq for AI-assisted explanations.

The AI assistant can explain:

- eligibility results
- risk flags
- scholarship fit
- route plan steps
- document requirements
- next actions

The AI assistant cannot:

- decide eligibility
- calculate scholarship scores
- generate route decisions independently
- unlock workflow steps
- verify documents
- change roles
- delete accounts

> **AI explains only. Deterministic modules decide.**

---

## 🌐 Trusted Source Management

The admin dashboard includes a trusted source registry.

Trusted sources support:

- scholarship source management
- official-source tracking
- trusted context for guidance
- source refresh monitoring
- admin review of curated sources

Examples include:

- UK Government
- Government of Canada / EduCanada
- DAAD Germany
- Chevening
- British Council
- University and scholarship portals

The MVP uses trusted-source guidance at application level. A full vector-based RAG pipeline is a future production enhancement.

---

## 📢 Notifications and Delivery Reports

Admins can send applicant notifications and reminders.

Delivery reporting includes:

- targeted recipients
- sent recipients
- failed recipients
- skipped recipients
- recipient-level status
- CSV download of delivery report

This supports administrative visibility over communication outcomes.

---

## 🔐 Security and Governance

VisaForge includes:

- bcrypt password hashing
- session-based login handling
- role-based access control
- protected navigation
- applicant/admin/super admin separation
- root super admin protection
- root super admin cannot be demoted, deactivated, or deleted through the application UI
- account deletion/anonymisation safeguards
- admin audit logs
- explanation-only AI constraints
- disclaimers on guidance-only use

The app is an academic MVP, not a production immigration advisory system.

---

## 📊 Testing Summary

Core tested areas include:

- authentication
- invalid login handling
- deterministic eligibility
- scholarship matching
- locked workflow steps
- OCR processing
- poor-quality OCR warnings
- AI guidance
- unsupported file validation
- protected page access
- frontend/dashboard layout
- end-to-end applicant workflow
- notification delivery reporting
- super admin account creation
- root super admin protection
- user account deletion/anonymisation

---

## 🔁 Future Work

Future improvements could include:

| MVP Area | Future Production Direction |
|---|---|
| Streamlit-only MVP | FastAPI backend + separate frontend |
| SQLite | PostgreSQL production database |
| Streamlit session auth | Token/JWT-based API authentication |
| Local/document metadata storage | Object storage for uploaded documents |
| Trusted-source guidance | Full vector-based RAG with pgvector |
| Manual source monitoring | Automated source versioning and policy monitoring |
| Basic OCR | Layout-aware OCR and structured extraction |
| Web-only interface | Mobile-friendly or dedicated mobile app |
| English-only focus | Urdu / Roman Urdu support |
| Manual testing | Larger-scale user testing |

---

## 🧪 Troubleshooting

| Issue | Fix |
|---|---|
| App does not start | Run `pip install -r requirements.txt` and check Python version. |
| Tesseract not found | Install system packages from `packages.txt` or configure Tesseract path. |
| AI assistant unavailable | Check `GROQ_API_KEY` and `LLM_PROVIDER` settings. |
| Database missing | Restart app; `db/init_db.py` initializes the SQLite database. |
| Admin account missing | Check `ADMIN_EMAIL` and `ADMIN_PASSWORD` secrets/environment variables. |
| OCR is weak | Upload clearer scans or text-based PDFs. |
| Streamlit Cloud deployment fails | Check `requirements.txt`, `packages.txt`, and secrets. |
| Deleted account is visible | Toggle “Include deleted accounts” in Account Management. Deleted accounts are hidden by default. |

---

## ⚖️ Responsible Use

VisaForge is a final year academic project and MVP demonstration.

It provides:

- structured guidance,
- eligibility preparation support,
- scholarship matching support,
- document review support,
- explanation-only AI guidance.

It does **not** provide:

- legal advice,
- official immigration decisions,
- guaranteed visa outcomes,
- guaranteed scholarship outcomes.

Always verify important information through official government, institutional, or scholarship sources.

---

## 📜 License and Attribution

VisaForge links to and attributes official source content where applicable. It does not claim ownership of government, university, or scholarship source material.

Automated source access should respect each website’s terms of use and robots.txt policies.

---

## 👨‍🎓 Academic Context

VisaForge was built as a final year research project MVP for COM6001 Research Project.

Project title:

**VisaForge: An Explainable Deterministic Workflow Orchestration Platform for AI-Assisted Immigration Guidance**

Built by **Shehryar Khan** as an academic software engineering artefact.

---

## ✅ Current Status

VisaForge is a working MVP with:

- applicant workflow
- deterministic eligibility
- scholarship matching
- route planning
- document upload/OCR
- AI explanations
- admin dashboard
- trusted source management
- notification delivery reports
- logs
- super admin account management
- account deletion/anonymisation safeguards
- Streamlit Cloud deployment

The project is demo-ready and suitable for further development into a production architecture.
