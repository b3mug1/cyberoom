# CyberBook

CyberBook is a booking platform foundation for discovering fictional computer clubs, comparing gaming PCs, and reserving a time slot. The repository contains a Python API and a TypeScript Next.js application, with PostgreSQL-backed booking conflict protection.

## Current Scope

Implemented in this phase:

- FastAPI with async SQLAlchemy 2, Pydantic v2, and a versioned `/api/v1` API.
- Argon2 password hashes, short-lived JWT access tokens, rotated refresh tokens in scoped HttpOnly cookies, and user reload from the database for protected requests.
- Club search with server-side pagination, city/name/hardware filters, club detail data, and sample club listings.
- Backend tariff pricing, booking validation, ownership-checked booking reads/cancellation, and valid booking status transitions.
- Unified online and staff-created walk-in reservations, actual session start/end records, conflict-checked extensions, and a club availability API.
- PostgreSQL GiST exclusion constraint plus row locking for overlapping-booking protection.
- Owner, staff, and admin API workflows protected by database-loaded roles. Owner resources and staff assignments are scoped to club ownership; staff reads/actions are scoped to explicit club assignments.
- Owner club/computer/tariff management, staff booking/QR/check-in/completion and computer maintenance workflows, and admin user/club/booking/computer controls with global analytics.
- Responsive Next.js discovery, club, login/register, role dashboards, booking history, and QR confirmation screens.
- Alembic configuration, fictional sample data, focused pricing/state tests, Docker Compose services, and Nginx routing.

Not implemented yet: reviews, payments, notifications, Redis-backed WebSocket distribution, background jobs, API rate limiting, and audit logging. Redis is provisioned but not yet used by application logic. These remain follow-on production hardening/features.

## Stack

- Backend: Python 3.12+, FastAPI, SQLAlchemy 2.x async, Pydantic v2, Alembic, PostgreSQL, Redis.
- Frontend: Next.js App Router, React, TypeScript strict mode, Tailwind CSS 4, TanStack Query, React Hook Form, Zod, Lucide.
- Infrastructure: Docker Compose and Nginx.

## Run With Docker

1. Copy `.env.example` to `.env` and replace `POSTGRES_PASSWORD` and `JWT_SECRET` with local values.
2. Start the stack:

   ```powershell
   docker compose up --build
   ```

3. Open `http://localhost:6006`. The API is available at `http://localhost:6006/api/v1`, health at `http://localhost:6006/health`, and OpenAPI docs at `http://localhost:6006/docs`.

The backend waits for PostgreSQL and Redis health, applies Alembic migrations, inserts fictional seed data when the database is empty, and then starts Uvicorn. Compose defaults are for local development only. Do not use them for a public deployment.

## Local Development

Start PostgreSQL and Redis first (Docker is convenient):

```powershell
docker compose up -d postgres redis
```

From the repository root, create and activate a Python environment, then install the API requirements:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
```

Set the database URL for the local processes, then run the API from `backend`:

```powershell
$env:DATABASE_URL = "postgresql+asyncpg://cyberbook:cyberbook-dev-only@localhost:5432/cyberbook"
$env:JWT_SECRET = "local-development-secret-change-this-value"
Set-Location backend
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload
```

In another terminal, start the frontend:

```powershell
Set-Location frontend
npm ci
npm run dev
```

The frontend runs at `http://localhost:6006`. Set `NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1` in the frontend environment when running outside Nginx.

## Database and Seed Data

Apply the current schema with:

```powershell
Set-Location backend
alembic upgrade head
```

Seed five fictional clubs and 50 computers with test roles and time-based tariffs:

```powershell
python -m app.seed
```

The seed command is idempotent for a non-empty clubs table. Seed accounts use the reserved `example.com` domain and the development-only password `CyberBook!2026`; change or remove these accounts outside local development.

| Role | Email | Username |
| --- | --- | --- |
| USER | `player@example.com` | `playerone` |
| STAFF | `staff@example.com` | `clubstaff` |
| OWNER | `owner@example.com` | `clubowner` |
| ADMIN | `admin@example.com` | `platformadmin` |

The password for these local demo accounts is `CyberBook!2026`. OWNER can assign STAFF accounts to clubs from `/dashboard`; STAFF only sees assigned clubs. Sign in as OWNER, STAFF, or ADMIN to open the matching role dashboard.

## API Overview

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `GET /api/v1/clubs?page=1&page_size=12&search=RTX&city=Astana`
- `GET /api/v1/clubs/{club_id}`
- `GET /api/v1/clubs/{club_id}/availability?start_time=...&end_time=...` (timezone-aware, up to seven days)
- `POST /api/v1/bookings/quote`
- `POST /api/v1/bookings`
- `GET /api/v1/bookings`
- `GET /api/v1/bookings/{booking_id}`
- `POST /api/v1/bookings/{booking_id}/cancel`
- `GET /api/v1/owner/dashboard`, `GET/POST /api/v1/owner/clubs`
- `POST /api/v1/owner/clubs/{club_id}/computers`, `POST /api/v1/owner/clubs/{club_id}/tariffs`
- `POST /api/v1/owner/clubs/{club_id}/staff`, `GET /api/v1/owner/bookings`
- `GET /api/v1/staff/dashboard`, `GET /api/v1/staff/bookings`, `GET /api/v1/staff/computers`
- `POST /api/v1/staff/bookings/verify-qr`, `POST /api/v1/staff/bookings/{booking_id}/check-in`, `POST /api/v1/staff/bookings/{booking_id}/complete`
- `POST /api/v1/staff/walk-ins` (guest name, computer, end time; starts the session immediately)
- `POST /api/v1/staff/bookings/{booking_id}/start`, `POST /api/v1/staff/bookings/{booking_id}/extend`, `POST /api/v1/staff/bookings/{booking_id}/end`
- `GET /api/v1/admin/dashboard`, `GET /api/v1/admin/users`, `GET /api/v1/admin/clubs`, `GET /api/v1/admin/bookings`

Interactive API documentation is served by FastAPI at `/docs`.

## Booking Rules

The server ignores client prices and calculates cost from active club tariffs by the minute. Bookings require timezone-aware whole-minute timestamps and must be between 15 minutes and 8 hours. A booking cannot start in the past, and maintenance/disabled computers cannot be booked. Users can only view and cancel their own bookings; cancellation is limited to pending or confirmed bookings.

The service checks for overlap to return a useful conflict error. PostgreSQL is the final concurrency guard: a GiST exclusion constraint rejects intersecting `[start, end)` ranges for the same computer while a row lock serializes competing requests.

Walk-in bookings use the same interval check and database constraint as online bookings. Staff must be assigned to the computer's club. A walk-in starts an `ACTIVE` session immediately; online bookings become active when staff checks the customer in during the reserved interval. Staff can extend an active session only if the new end does not overlap another booking, or end it to release the computer. An overdue active session blocks new bookings until staff resolves it. The availability endpoint lists reserved intervals without customer details. Physical occupancy still depends on staff recording arrivals and departures; there is no software agent on gaming PCs.

## Tests

Run the unit tests:

```powershell
Set-Location backend
pytest -q
```

The PostgreSQL concurrency test is skipped unless `TEST_DATABASE_URL` points to a dedicated disposable test database. It creates its required tables and `btree_gist` extension, sends two overlapping booking operations concurrently, and asserts exactly one succeeds. For example:

```powershell
$env:TEST_DATABASE_URL = "postgresql+asyncpg://cyberbook:cyberbook-dev-only@localhost:5432/cyberbook_test"
pytest tests\test_booking_concurrency.py -q
```

Do not point this integration test at a database containing data you need.

`tests/test_booking_management_concurrency.py` additionally races online vs walk-in creation and session extension vs a new online booking, and checks overdue-session handling. Run it with the same disposable `TEST_DATABASE_URL`.

Frontend checks:

```powershell
Set-Location frontend
npm run lint
npm run build
```

## Security Notes

Passwords are Argon2-hashed. Access tokens are short-lived. Refresh tokens are random, stored server-side only as SHA-256 hashes, rotated on refresh, and sent to the browser in a path-scoped HttpOnly cookie. The frontend stores only the access token in session storage. Configure a strong `JWT_SECRET`, HTTPS, production CORS origins, and secure database credentials before deployment.

This is an early project phase, not a complete production service. Staff/owner/admin authorization, CSRF defenses for cookie-backed operations, rate limiting, audit logging, monitoring, and the unimplemented features listed above are required before public deployment.
