<div align="center">

# 💰 Track My Money

**Upload bank statement PDFs. Get every transaction in one database.**

[![Python](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.143-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.8-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Vite](https://img.shields.io/badge/Vite-7-646CFF?logo=vite&logoColor=white)](https://vite.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![Jev](https://img.shields.io/badge/AI-Jev%20by%20TypeSafe-7B3FE4)](https://docs.typesafe.ai)
[![uv](https://img.shields.io/badge/uv-package%20manager-DE5FE9?logo=uv&logoColor=white)](https://docs.astral.sh/uv/)
[![pnpm](https://img.shields.io/badge/pnpm-11-F69220?logo=pnpm&logoColor=white)](https://pnpm.io/)
[![Tests](https://img.shields.io/badge/tests-31%20passed-2EA44F?logo=pytest&logoColor=white)](#-run-the-tests)
[![Pyright](https://img.shields.io/badge/types-pyright%20clean-2EA44F)](#-run-the-tests)

</div>

---

## 📖 Contents

- [What the app does](#-what-the-app-does)
- [Features](#-features)
- [Architecture](#%EF%B8%8F-architecture)
- [Requirements](#-requirements)
- [Run the app](#-run-the-app)
- [Use the app](#%EF%B8%8F-use-the-app)
- [Categories and the local model](#%EF%B8%8F-categories-and-the-local-model)
- [Run the tests](#-run-the-tests)
- [Configuration](#%EF%B8%8F-configuration)
- [API](#-api)
- [Database](#%EF%B8%8F-database)
- [Project structure](#-project-structure)
- [Privacy](#-privacy)
- [Troubleshooting](#%EF%B8%8F-troubleshooting)

---

## 🎯 What the app does

Track My Money reads bank statement PDFs and keeps the transactions in a PostgreSQL database.

The app does not use one fixed layout for each bank. It finds the transaction table in the PDF. Then it asks **Jev**, the AI model from TypeSafe, what each column contains. Jev sees only the column names and masked sample values. If Jev is not available, keyword rules find the columns.

Some banks draw the column names as images. SBI is an example. For these statements, the app sends images of the column names to Jev.

The app checks each statement after it reads it. Each balance must be equal to the previous balance, minus the debit, plus the credit.

---

## ✨ Features

| | Feature |
|---|---|
| 📤 | Upload one PDF or many PDFs at the same time. |
| 🏦 | Read statements from any bank. The app does not need a layout for each bank. |
| 🔒 | Open locked PDFs. The app asks for the password of each locked file. |
| 🤖 | Find the column roles with Jev. Keyword rules are the fallback. |
| 🖼️ | Read column names that are images (for example, SBI statements). |
| 🔑 | Enter your own Jev API key in the browser. The server does not keep it. |
| ✅ | Check the running balance of each statement. |
| 🚫 | Stop duplicates. The app does not import the same file two times. |
| 🗄️ | Keep statements and transactions in PostgreSQL for analysis. |
| 🏷️ | Put each transaction into a category (32 categories) with a fine-tuned Laya model that runs on your computer. You can correct any category. |
| 📊 | See money in vs out per month, spending and income by category, and the trend of one category. |

---

## 🏗️ Architecture

### Components

```mermaid
flowchart LR
    user(["👤 User"])

    subgraph browser["🌐 Browser"]
        ui["⚛️ React UI<br/>upload · password · statements · transactions"]
        key[("🔑 localStorage<br/>Jev API key")]
    end

    subgraph backend["🐍 Backend · FastAPI"]
        api["🚪 API<br/>/api/statements"]
        parser["📄 Statement parser<br/>pdfplumber"]
        classifier["🧭 Header classifier<br/>mask · images · cache"]
        orm["🧱 SQLAlchemy + Alembic"]
    end

    jev["🤖 Jev<br/>api.typesafe.ai"]
    db[("🐘 PostgreSQL 17<br/>Docker")]

    user --> ui
    ui <--> key
    ui -- "PDF + password + key<br/>(Vite proxy /api)" --> api
    api --> parser
    parser --> classifier
    classifier -- "headers + masked samples<br/>or header images" --> jev
    jev -- "column roles" --> classifier
    api --> orm --> db
```

### Upload of one file

```mermaid
sequenceDiagram
    autonumber
    actor U as 👤 User
    participant UI as ⚛️ React UI
    participant API as 🚪 FastAPI
    participant P as 📄 Parser
    participant J as 🤖 Jev
    participant DB as 🐘 PostgreSQL

    U->>UI: Select PDF files
    UI->>API: POST /api/statements (file, key)
    API->>DB: Same file imported before?
    alt File is locked and has no password
        API-->>UI: 422 password_required
        UI->>U: Show a password field
        U->>UI: Enter the password
        UI->>API: POST /api/statements (file, password, key)
    end
    API->>P: Parse the PDF
    P->>J: Column names + masked samples (or header images)
    J-->>P: Role of each column
    P-->>API: Statement + transactions
    API->>DB: Insert statement and transactions
    API-->>UI: 201 Created (statement summary)
    UI->>U: Show "Imported N transactions"
```

### How the parser finds the columns

```mermaid
flowchart TD
    start(["Table row"]) --> key{"Jev key<br/>available?"}
    key -- No --> rules["Keyword rules"]
    key -- Yes --> dated{"Dated rows<br/>below the row?"}
    dated -- No --> rules
    dated -- Yes --> text{"Row looks like<br/>a text header?"}
    text -- Yes --> jevtext["🤖 Jev: names + masked samples"]
    text -- No --> image{"Header cells empty<br/>(names are images)?"}
    image -- Yes --> jevimage["🤖 Jev: images of header cells"]
    image -- No --> rules
    jevtext --> ok{"Usable header?<br/>date + amounts"}
    jevimage --> ok
    ok -- Yes --> done(["Column map"])
    ok -- No --> rules
    rules --> done
```

---

## 🧰 Requirements

| Tool | Version | Use |
|---|---|---|
| 🐳 [Docker Desktop](https://www.docker.com/products/docker-desktop/) | 4.x or later | Runs PostgreSQL |
| ⚡ [uv](https://docs.astral.sh/uv/) | 0.11 or later | Installs Python 3.14 and the backend packages |
| 🟢 [Node.js](https://nodejs.org/) | 24 or later | Runs the frontend tools |
| 📦 [pnpm](https://pnpm.io/) | 11 or later | Installs the frontend packages |
| 🔑 Jev API key | optional | Reads column names with AI. Get a key in the [TypeSafe console](https://docs.typesafe.ai). |

---

## 🚀 Run the app

> [!WARNING]
> The database uses port **5433**, not 5432. Port 5432 is often used by a local PostgreSQL installation. Do not change the port to 5432 if a local PostgreSQL runs on your computer.

### 1. Start the database

1. Start Docker Desktop.
2. Open a terminal in the project folder.
3. Start PostgreSQL:
   ```bash
   docker compose up -d
   ```
4. Make sure that the database is healthy:
   ```bash
   docker compose ps
   ```
   The `STATUS` column must show `healthy`.

### 2. Start the backend

> [!CAUTION]
> The `backend/.env` file can contain your Jev API key. Do not commit this file. The `.gitignore` file excludes it.

1. Go to the backend folder:
   ```bash
   cd backend
   ```
2. Make a copy of the example settings:
   ```bash
   cp .env.example .env
   ```
3. Optional: add your Jev API key to `backend/.env`:
   ```ini
   TYPESAFE_API_KEY=your-key
   ```
4. Create the database tables:
   ```bash
   uv run alembic upgrade head
   ```
5. Start the API:
   ```bash
   uv run uvicorn app.main:app --reload
   ```
6. Open http://127.0.0.1:8000/docs to see the API documentation.

### 3. Start the frontend

1. Open a second terminal in the project folder.
2. Go to the frontend folder:
   ```bash
   cd frontend
   ```
3. Install the packages:
   ```bash
   pnpm install
   ```
4. Start the development server:
   ```bash
   pnpm dev
   ```
5. Open http://localhost:5173 in your browser.

---

## 🖱️ Use the app

1. Optional: enter your Jev API key in the **Jev API key** field.
   - The browser keeps the key. The app sends it with each upload.
   - If you do not enter a key, the app uses the server key. If the server has no key, the app uses keyword rules.
2. Drop PDF files on the upload area, or click **Choose files**.
3. Look at the status of each file:

   | Status | Meaning | Action |
   |---|---|---|
   | ⏳ Reading… | The server reads the file. | Wait. |
   | 🔒 Locked | The PDF has a password. | Enter the password, then click **Unlock**. |
   | ❌ Wrong password | The password is not correct. | Enter the correct password. |
   | ✅ Imported | The transactions are in the database. | No action. |
   | ↩️ Already imported | The same file is in the database. | No action. |

4. Click a statement in the **Statements** list to see its transactions.
5. To delete a statement, click **Delete…**, then click **Delete**.

> [!WARNING]
> **Delete** removes the statement and all of its transactions. You cannot undo this. To get the data again, upload the PDF again.

> [!NOTE]
> SBI statements draw the column names as images. To read these statements, you must enter a Jev API key.

---

## 🏷️ Categories and the local model

The app puts each transaction into one of 32 categories (`backend/app/categorising/categories.py`).
**Laya**, an open-source decision model, makes the choice. It runs in Docker on your computer, so
narrations do not leave your machine.

Base Laya does not know Indian merchants (it got 7–10 of 18 test narrations right). We fine-tune it
on **synthetic** narrations on a free Kaggle GPU, then run the result locally.

- 📘 Step-by-step guide: [`backend/training/README.md`](backend/training/README.md)
- 📝 Why we did it this way: [`docs/case-study-laya-fine-tuning.md`](docs/case-study-laya-fine-tuning.md)

To start the model after you add the checkpoint to `models/laya-finance/`:

```bash
docker compose --profile laya up -d laya
```

If Laya is not running, uploads still work. The transactions stay uncategorised until you click
**Categorise** on the statement.

---

## 🧪 Run the tests

> [!NOTE]
> The API tests use the `trackmymoney_test` database. Start the database before you run the tests.

1. Go to the backend folder:
   ```bash
   cd backend
   ```
2. Run the tests:
   ```bash
   uv run pytest
   ```
3. Run the type check:
   ```bash
   uv run pyright
   ```
4. Do the frontend checks:
   ```bash
   cd ../frontend
   pnpm run build
   pnpm run lint
   ```

The tests do not call Jev. They use fake classifiers.

---

## ⚙️ Configuration

The backend reads these settings from `backend/.env`.

| Setting | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://trackmymoney:trackmymoney@127.0.0.1:5433/trackmymoney` | The application database. |
| `TEST_DATABASE_URL` | `…/trackmymoney_test` | The database for the API tests. |
| `TYPESAFE_API_KEY` | *(empty)* | The server Jev key. The app uses it when the browser sends no key. |
| `CORS_ORIGINS` | *(empty)* | Comma-separated origins that can call the API. Use it when the frontend is on a different host. |

The frontend reads one setting at build time:

| Setting | Default | Description |
|---|---|---|
| `VITE_API_BASE` | *(empty)* | The API address. Leave it empty when the API and the UI use the same host. |

> [!TIP]
> Use `127.0.0.1`, not `localhost`, in the database address. On Windows, `localhost` tries IPv6 first, and each connection waits for approximately 8 seconds.

---

## 🔌 API

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Shows the database status and if the server has a Jev key. |
| `POST` | `/api/statements` | Reads one PDF and keeps its transactions. Fields: `file`, `password` (optional). Header: `X-TypeSafe-Key` (optional). |
| `GET` | `/api/statements` | Lists the statements. The newest statement is first. |
| `GET` | `/api/statements/{id}/transactions` | Lists the transactions of one statement. |
| `DELETE` | `/api/statements/{id}` | Deletes one statement and its transactions. |

Upload errors have a `code`:

| HTTP | `code` | Meaning |
|---|---|---|
| 409 | `duplicate` | The same file is already in the database. |
| 413 | `too_large` | The file is larger than 20 MB. |
| 422 | `password_required` | The PDF is locked. Send it again with the password. |
| 422 | `wrong_password` | The password does not open the PDF. |
| 422 | `not_a_pdf` | The file is not a PDF, or it is damaged. |
| 422 | `no_text_layer` | The PDF is a scan. It has no text. |
| 422 | `no_transactions` | The app did not find a transaction table. |

---

## 🗄️ Database

```mermaid
erDiagram
    statements ||--o{ transactions : "has"
    statements {
        bigint id PK
        text filename
        text file_sha256 UK "stops duplicates"
        text bank
        text account_number
        text period
        text header_mapping "jev · jev (image) · rules · rules (no Jev key) · rules (fallback)"
        text balance_check
        jsonb metadata
        timestamptz uploaded_at
    }
    transactions {
        bigint id PK
        bigint statement_id FK "ON DELETE CASCADE"
        int row_index
        date date
        text particulars
        numeric debit "numeric(14,2), >= 0"
        numeric credit "numeric(14,2), >= 0"
        numeric balance "numeric(14,2)"
        jsonb extra
    }
```

- Money uses `numeric(14,2)`. This type keeps exact values.
- Indexes are on `transactions.statement_id` and `transactions.date`.
- Alembic manages the schema. The migrations are in `backend/alembic/versions/`.

---

## 📁 Project structure

```text
track-my-money/
├── 🐳 docker-compose.yml          PostgreSQL 17 on port 5433
├── 🐳 docker/initdb/              Creates the test database
├── 🐍 backend/
│   ├── app/
│   │   ├── main.py                FastAPI application
│   │   ├── config.py              Settings from .env
│   │   ├── db.py                  Database engine and sessions
│   │   ├── models.py              Tables: statements, transactions
│   │   ├── schemas.py             API response models
│   │   ├── api/statements.py      API endpoints
│   │   └── parsing/
│   │       ├── statement_parser.py    Finds tables, rows and amounts
│   │       └── header_classifier.py   Masking, Jev calls, header images
│   ├── alembic/                   Database migrations
│   └── tests/                     Parser tests and API tests
├── ⚛️ frontend/
│   └── src/
│       ├── App.tsx                Page layout and state
│       ├── api.ts                 Typed API client
│       └── components/            Upload, key field, statements, transactions
├── 🧪 playground/                 First command-line version of the parser
└── 📄 sample_statements/          Your PDFs for local tests (not committed)
```

---

## 🔐 Privacy

- 🚫 The server does not keep PDF files.
- 🚫 The server does not keep PDF passwords.
- 🚫 The server does not keep or log Jev API keys.
- 🎭 Jev gets only column names and **masked** sample values. Digits change to `9` and letters change to `X` or `x`:

  | Original | Sent to Jev |
  |---|---|
  | `UPI/412345/SWIGGY` | `UPI/999999/XXXXXX` |
  | `1,234.50 Dr` | `9,999.99 Dr` |
  | `Rahul Sharma` | `Xxxxx Xxxxxx` |

- 🖼️ For column names that are images, Jev gets images of the header cells only. It does not get images of transactions.

### Categorising: Laya (local) or Jev (cloud, masked)

Nothing is categorised automatically. You choose **Laya** or **Jev** in the **Categorise with** switch, then
click **Categorise with …** on a statement.

- **Laya** runs on your computer. The original narration never leaves it.
- **Jev** gets only the **masked narration**, the direction (money in or out) and an **amount range**
  (for example `₹10k–50k`), never the exact amount.

The app masks every narration when you upload it and stores the result in its own column
(`particulars_masked`). Turn on **Show what Jev sees** in the transaction table to check it before you
use Jev. The masking (`backend/app/masking/`) keeps what tells the category and replaces the rest:

| Original | Stored and sent to Jev |
|---|---|
| `UPI/P2A/412345678901/RAHUL SHARMA/rahul.12@okaxis/rent oct` | `UPI/P2A/[REF]/[PERSON_6C46]/[UPI_ID]@okaxis/rent oct` |
| `POS 458024 SRI LAKSHMI ENTERPRISES NASHIK` | `POS [REF] SRI [NAME_3264] ENTERPRISES [CITY]` |
| `NEFT Dr-UTIB0281200-ARJUN IYER-HOUSE RENT JUL` | `NEFT Dr-[IFSC:UTIB]-[PERSON_B05B]-HOUSE RENT JUL` |
| `UPI/P2M/998877665544/SWIGGY/swiggy@icici/Payment` | `UPI/P2M/[REF]/SWIGGY/swiggy@icici/Payment` |

- Known brands, payment keywords, business words and common English words are kept. Names, UPI IDs,
  numbers, PAN, Aadhaar, phone numbers, emails, dates and cities are replaced.
- The same person always gets the same token, so patterns stay visible. A secret key in
  `backend/.env` (`MASKING_SECRET`, created on first use) makes the tokens impossible to reverse.
  **Keep this key.** A new key gives every name a new token.
- After the masking rules change, run `uv run python -m app.masking.backfill` in `backend/` to
  mask the stored rows again.
- `uv run python training/check_masking.py` in `backend/` checks the rules on synthetic narrations.
  The current result is 0 leaks and 0 masked brands in 5,000 narrations.

> [!IMPORTANT]
> All users share one workspace in this version. Add user accounts and HTTPS before other people use a hosted copy.

---

## 🛠️ Troubleshooting

| Problem | Cause | Solution |
|---|---|---|
| "No transaction table was recognised" for an SBI statement | No Jev key. The column names are images. | Enter a Jev API key, then upload the file again. |
| **Columns by** shows `rules (no Jev key)` | The upload had no Jev key. The UI field was empty and the server has no key. | Enter a Jev API key. Delete the statement, then upload the file again. |
| **Columns by** shows `rules (fallback)` | Jev was not available, or its answer was not usable. | Make sure that the key is correct. Delete the statement, then upload the file again. |
| Each request takes approximately 8 seconds | The database address uses `localhost`. | Use `127.0.0.1` in `DATABASE_URL`. |
| `docker compose up` fails | Docker Desktop is not running. | Start Docker Desktop, then try again. |
| `Can't reach the server` in the UI | The backend is not running. | Start the backend (step 2). |
| `ERR_PNPM_IGNORED_BUILDS` | pnpm blocks build scripts. | The project allows esbuild in `frontend/pnpm-workspace.yaml`. Run `pnpm install` again. |
| "Already imported" for a new statement | The same file is in the database. | Delete the old statement first, if you want to import it again. |
