# TMRP - Tutor Matching and Rating Platform

A full-stack web application for connecting parents with private tutors. Parents search for tutors, communicate through in-app messaging, send match invitations, and track their child's learning progress. Tutors manage lesson notes, exam records, and earnings. Both sides exchange structured ratings after a tutoring relationship ends.

Built as the final group project for a university SQL (MS Access) course.

---

## Table of Contents

- [TMRP - Tutor Matching and Rating Platform](#tmrp---tutor-matching-and-rating-platform)
  - [Table of Contents](#table-of-contents)
  - [Project Background](#project-background)
  - [Core Features](#core-features)
    - [For Parents](#for-parents)
    - [For Tutors](#for-tutors)
    - [For Admins](#for-admins)
    - [Shared](#shared)
  - [System Architecture](#system-architecture)
  - [Technology Stack](#technology-stack)
  - [Getting Started](#getting-started)
  - [Project Structure](#project-structure)
  - [Database Design](#database-design)
    - [Tables by functional group](#tables-by-functional-group)
    - [Key constraints](#key-constraints)
  - [API Overview](#api-overview)
    - [Endpoint groups](#endpoint-groups)
    - [Authentication](#authentication)
    - [Notable design decisions](#notable-design-decisions)
  - [Match Status Machine](#match-status-machine)
  - [Background Tasks](#background-tasks)
  - [Team and Roles](#team-and-roles)
  - [Known Limitations](#known-limitations)

---

## Project Background

This project simulates a tutoring marketplace -- similar in concept to a job board, but scoped entirely to private tutoring. The idea came from a common real-world problem: parents looking for qualified tutors have no good centralized platform for finding, evaluating, and maintaining a tutoring relationship.

**Course requirement:** The database must be implemented in MS Access. At the end of the semester, the team presents the system live and demonstrates its features in class.

**Design goals:**

| Goal | Description |
|------|-------------|
| Meet course requirements | MS Access as the database; tables and relationships viewable directly in Access |
| Apply industry practices | Three-tier architecture, RESTful API, JWT authentication, repository pattern |
| Run locally | Everything runs on a single Windows machine; no cloud deployment |

---

## Core Features

**Three user roles:** Parent, Tutor, and Admin.

### For Parents
- Search for tutors by subject, hourly rate range, star rating, and school
- View detailed tutor profiles (bio, availability, subjects, rates, past reviews)
- Message tutors directly through in-app conversations
- Send match invitations with contract terms (hourly rate, sessions per week, optional trial period)
- Track children's lesson notes and exam scores (subject to tutor's visibility settings)
- View monthly tutoring expense breakdowns

### For Tutors
- Manage a searchable profile with granular visibility controls (can hide university, major, rates, etc.)
- Receive and respond to match invitations
- Record lesson session notes (date, hours, content, homework, performance observations)
- Log exam scores for students
- Rate students and parents after a match ends
- View monthly income breakdowns by student and subject

### For Admins
- View all registered users
- Export and import table data as CSV (runs asynchronously)
- Generate seed data for testing
- Reset the database

### Shared
- Three-way rating system: parents rate tutors; tutors rate both students and parents
- 7-day review edit window; reviews lock automatically after that
- In-app one-on-one messaging between parents and tutors
- Session edit history: every change to a lesson record is logged with old/new values

---

## System Architecture

The system uses a standard three-tier architecture running locally on Windows:

```
Browser (Vue 3)
    |
    | HTTP / JSON (Axios)
    |
FastAPI (Python) -- JWT auth, business logic, repository layer
    |
    | ODBC / pyodbc
    |
MS Access (.accdb) <---- huey Worker (background tasks, same DB)
```

A separate background worker process (huey) handles long-running operations such as CSV import/export, statistics calculation, and scheduled review locking. This keeps the main API responsive during admin operations.

---

## Technology Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Frontend framework | Vue 3 | 3.5.13 |
| Build tool | Vite | 6.0.5 |
| State management | Pinia | 2.3.0 |
| Client-side routing | Vue Router | 4.5.0 |
| HTTP client | Axios | 1.7.9 |
| Charts | Chart.js + vue-chartjs | 4.5.1 / 5.3.3 |
| CSS framework | Tailwind CSS | 4.2.2 |
| Backend framework | FastAPI | 0.115.6 |
| Data validation | Pydantic | 2.10.4 |
| Database driver | pyodbc | 5.2.0 |
| Password hashing | bcrypt | 4.2.1 |
| JWT | python-jose | 3.3.0 |
| Task queue | huey | 2.5.2 |
| Database | MS Access (.accdb) | - |

---

## Getting Started

**Requirements:**
- Windows (ODBC driver for MS Access is Windows-only)
- Python 3.10+
- Node.js 18+
- Microsoft Access Database Engine (or Office with Access installed)

**Steps:**

1. Clone this repository.

2. Set up the backend environment:
   ```bash
   cd tutor-platform-api
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and fill in the required values:
   ```
   ACCESS_DB_PATH=./data/tutoring.accdb
   JWT_SECRET_KEY=your-secret-key-here
   JWT_EXPIRE_MINUTES=60
   ADMIN_USERNAME=admin
   ADMIN_PASSWORD=your-admin-password
   ```

4. Install frontend dependencies:
   ```bash
   cd ../tutor-platform-web
   npm install
   ```

5. Launch everything with the provided script:
   ```bash
   cd ../tutor-platform-api
   start.bat
   ```
   This starts three processes: the huey worker, the FastAPI server, and the Vite dev server.

**Default URLs once running:**

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5273 |
| API | http://localhost:8000 |
| Swagger UI | http://localhost:8000/docs |

---

## Project Structure

```
project-root/
|
+-- docs/
|   +-- project-spec.md          # Full system specification (v5.1)
|
+-- tutor-platform-api/          # Python backend
|   +-- app/
|   |   +-- main.py              # FastAPI application setup, startup events
|   |   +-- config.py            # Environment variable loading
|   |   +-- database.py          # ODBC connection management, retry logic
|   |   +-- dependencies.py      # FastAPI dependency injection (auth, DB)
|   |   +-- exceptions.py        # Custom exception classes
|   |   +-- models/              # Pydantic request/response schemas (10 files)
|   |   +-- repositories/        # Data access layer (11 files)
|   |   +-- routers/             # API endpoints (11 route modules)
|   |   +-- tasks/               # huey background tasks (4 files)
|   |   +-- utils/               # Helpers: security, logging, CSV, Access BIT handling
|   |   +-- worker.py            # huey instance configuration
|   +-- seed/                    # Fake data generator
|   +-- data/
|   |   +-- tutoring.accdb       # MS Access database file
|   |   +-- huey.db              # SQLite task queue state
|   +-- logs/                    # Rotating log files
|   +-- requirements.txt
|   +-- start.bat                # One-click launcher
|
+-- tutor-platform-web/          # Vue 3 frontend
    +-- src/
    |   +-- main.js              # App entry point
    |   +-- router/index.js      # Route definitions with role guards
    |   +-- stores/              # Pinia stores: auth, tutor, match, message
    |   +-- api/                 # Axios service layer (12 files, one per resource)
    |   +-- views/               # Page-level Vue components (15 files)
    |   +-- components/          # Reusable UI components (19+ files)
    +-- package.json
    +-- vite.config.js
```

---

## Database Design

The database contains 13 tables in MS Access (.accdb format).

### Tables by functional group

**Users and roles**

| Table | Purpose |
|-------|---------|
| Users | Core account: username, password hash, role (parent/tutor/admin), display name, contact |
| Tutors | Tutor-specific profile: university, department, grade year, bio, visibility settings |
| Students | Children managed by a parent account: name, school, notes |

**Subjects and availability**

| Table | Purpose |
|-------|---------|
| Subjects | Subject catalog: name, category |
| Tutor_Subjects | Many-to-many: which tutors teach which subjects, at what hourly rate |
| Tutor_Availability | Tutor's weekly availability slots (day of week + time range) |

**Communication**

| Table | Purpose |
|-------|---------|
| Conversations | One conversation record per unique user pair |
| Messages | Individual messages within a conversation |

**Matching and contracts**

| Table | Purpose |
|-------|---------|
| Matches | The core matching record: tutor, student, subject, contract terms, current status |

**Teaching records**

| Table | Purpose |
|-------|---------|
| Sessions | Individual lesson records: date, hours, content, homework, performance notes |
| Session_Edit_Logs | Audit trail: every field edit to a session record (field name, old value, new value) |
| Exams | Exam score records: date, type, score, visibility flag |

**Ratings**

| Table | Purpose |
|-------|---------|
| Reviews | Post-match reviews: supports three directions (parent-to-tutor, tutor-to-student, tutor-to-parent) |

### Key constraints

- All primary keys are AutoNumber (MS Access equivalent of auto-increment integer)
- Tutor_Subjects and Tutor_Availability use composite unique constraints
- Conversations enforces a unique pair constraint to prevent duplicate threads
- Reviews enforces one review per reviewer per match per review type
- MS Access stores BIT fields as -1 (true) and 0 (false); the backend normalizes these to Python booleans

---

## API Overview

All endpoints return a unified response envelope:

```json
{
  "success": true,
  "data": { ... },
  "message": "optional status message"
}
```

HTTP status codes follow standard REST conventions: 200 OK, 201 Created, 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found, 409 Conflict.

### Endpoint groups

| Prefix | Module | Responsibility |
|--------|--------|---------------|
| `/api/auth` | auth.py | Register, login, current user |
| `/api/tutors` | tutors.py | Search, profiles, availability, visibility |
| `/api/students` | students.py | Parent's children management |
| `/api/subjects` | subjects.py | Subject catalog |
| `/api/matches` | matches.py | Invitations, status transitions, contract details |
| `/api/sessions` | sessions.py | Lesson notes CRUD, edit history |
| `/api/exams` | exams.py | Exam score records |
| `/api/reviews` | reviews.py | Post-match ratings (three directions) |
| `/api/messages` | messages.py | Conversations and messages |
| `/api/stats` | stats.py | Income (tutor) and expense (parent) breakdowns |
| `/api/admin` | admin.py | User management, CSV ops, seed data, task status |

### Authentication

All protected endpoints require a JWT bearer token in the `Authorization` header:

```
Authorization: Bearer <token>
```

Tokens are issued on login and expire after a configurable TTL (default 60 minutes). Role enforcement uses a `@require_role()` decorator that returns 403 if the authenticated user's role does not match.

### Notable design decisions

**Tutor search** supports multi-parameter filtering (subject, rate range, star rating, school/university) with server-side pagination. Because MS Access does not support SQL `LIMIT`/`OFFSET`, pagination is applied in Python after fetching results.

**Session editing** automatically creates a `Session_Edit_Logs` entry for every changed field, recording the field name, old value, new value, and edit timestamp. This provides parents with an audit trail of post-hoc changes.

**Review locking** is enforced by a scheduled background task (runs daily at 3 AM) that marks reviews older than 7 days as immutable. The `PATCH /api/reviews/{id}` endpoint also checks this flag before allowing edits.

**Tutor capacity** is validated when a parent sends a match invitation. The backend checks whether the tutor already has the maximum number of active or trial students before creating the pending match record.

---

## Match Status Machine

A match progresses through a defined set of states. Only specific roles can trigger each transition.

```
                        [Parent sends invitation]
                                  |
                               pending
                              /        \
              [Tutor accepts,        [Tutor rejects]
               no trial]              /
                  |            rejected
               active
                              /
              [Tutor accepts,
               with trial]
                  |
                trial
              /        \
   [Trial ok]       [Trial rejected]
       |                  |
    active             rejected
       |
   [Paused by either party]
       |
    paused
       |
   [Resume]
       |
    active
       |
   [Either party initiates termination]
       |
  terminating
       |
   [Other party confirms]
       |
    ended
```

Additional states: `cancelled` (parent withdraws a pending invitation before tutor responds).

Each `(current_status, action)` pair maps to a new status and a set of roles permitted to perform that action. The backend validates both the current status and the requesting user's role before applying any transition.

---

## Background Tasks

The huey worker runs as a separate process backed by a SQLite queue (`data/huey.db`). It shares the same MS Access database connection as the main API.

| Task | Trigger | Description |
|------|---------|-------------|
| `import_csv_task` | Admin action | Bulk import CSV data into a table (upsert or overwrite) |
| `export_csv_task` | Admin action | Export a table to CSV format |
| `generate_seed_data` | Admin action | Populate the database with realistic fake data for testing |
| `calculate_income_stats` | Admin / scheduled | Aggregate tutor earnings by month, student, and subject |
| `calculate_expense_stats` | Admin / scheduled | Aggregate parent spending by month and subject |
| `lock_expired_reviews` | Scheduled (3 AM daily) | Mark reviews older than 7 days as immutable |

Admin-triggered tasks return a `task_id` immediately. The frontend polls `GET /api/admin/tasks/{task_id}` for status and completion.

---

## Team and Roles

| Member | Role |
|--------|------|
| A (Tech Lead) | Full-stack architecture, core backend, complex frontend, code review |
| B | Frontend: login, dashboard, search, messaging pages |
| C | Frontend: tutor pages, session/exam pages, integration testing |
| D | MS Access database design, presentation slides |
| E | MS Access database design, written documentation |

---

## Known Limitations

- **Windows-only.** The pyodbc ODBC driver for MS Access is not available on macOS or Linux.
- **No real-time messaging.** The message system is polling-based, not WebSocket-based.
- **Concurrent access.** MS Access is not designed for high concurrency; the backend uses retry logic (3 attempts, 0.5 s backoff) to handle transient locking errors.
- **Local deployment only.** The system is designed to run on a single machine for demonstration purposes and is not hardened for production use.
- **Pagination in Python.** Because MS Access does not support `LIMIT`/`OFFSET` in SQL, all pagination is done in the application layer after fetching results from the database.
