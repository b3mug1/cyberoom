# Cyberoom

Cyberoom is a booking platform foundation for discovering fictional computer clubs, comparing gaming PCs, and reserving a time slot. The repository contains a Python API and a TypeScript Next.js application, with PostgreSQL-backed booking conflict protection.

## Current Scope

Implemented in this phase:

- FastAPI with async SQLAlchemy 2, Pydantic v2, and a versioned `/api/v1` API.
- Argon2 password hashes, short-lived JWT access tokens, rotated refresh tokens in scoped HttpOnly cookies, and user reload from the database for protected requests.
- Club search with server-side pagination, city/name/hardware filters, club detail data, and sample club listings.
- Structured club price menus displayed alongside bookable hourly tariffs; demo BRO menu includes Standard and Bootcamp weekday/weekend prices.
- Weekday-aware tariffs with independent prices and time windows, plus owner reports by local date, start hour, and computer.
- Backend tariff pricing, booking validation, ownership-checked booking reads/cancellation/rescheduling, and valid booking status transitions.
- Verified post-visit reviews with separate club and computer ratings; one review per completed online booking and a live club-rating average.
- Owner-managed promo codes with date windows, per-user and global usage limits, fixed/percentage discounts, and booking price snapshots.
- Owner-managed prepaid hour packs; paid memberships add a balance that can cover full booking intervals and is restored when a booking is cancelled or expires.
- Payment records, checkout/status/refund API boundaries, idempotency keys, and a provider-neutral payment adapter contract. Checkout and refunds return `503` until an adapter is configured; the app never simulates a successful payment.
- Club cancellation refund cutoffs, with eligible paid cancellations routed through the configured payment adapter.
- Rescheduling of upcoming bookings between computers in the same club, with server-side repricing and overlap protection.
- In-app booking confirmations, one-hour reminders, cancellation/session-completion updates, and a waitlist alert when a matching slot opens.
- Redis-backed API rate limits with stricter limits for authentication routes.
- Owner and admin audit history for booking, session, staff, club, computer, tariff, and account changes.
- Owner-managed staff shifts with overlap protection and staff-visible rosters.
- A background worker that starts confirmed sessions at their booked start time, completes active sessions at their booked end time, and expires bookings that pass without starting.
- Unified online and staff-created walk-in reservations, actual session start/end records, conflict-checked extensions, and a club availability API.
- PostgreSQL GiST exclusion constraint plus row locking for overlapping-booking protection.
- Owner, staff, and admin API workflows protected by database-loaded roles. Owner resources and staff assignments are scoped to club ownership; staff reads/actions are scoped to explicit club assignments.
- Owner club/computer/tariff management, staff booking/QR/check-in/completion and computer maintenance workflows, and admin user/club/booking/computer controls with global analytics.
- Responsive Next.js discovery, club, login/register, role dashboards, booking history, and QR confirmation screens.
- Alembic configuration, fictional sample data, focused pricing/state tests, Docker Compose services, and Nginx routing.

External email/SMS/messenger delivery and Redis-backed WebSocket distribution are not connected yet. The in-app inbox and provider-neutral notification adapter contract are available. Online payment and refund flows also require a concrete implementation of the payment adapter before they can be used; Redis currently backs rate limits.

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
$env:DATABASE_URL = "postgresql+asyncpg://cyberoom:cyberoom-dev-only@localhost:5432/cyberoom"
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

Run scheduled session automation from another backend terminal when testing outside Docker:

```powershell
Set-Location backend
python -m app.worker
```

The frontend runs at `http://localhost:6006`. Set `NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1` in the frontend environment when running outside Nginx.

## Database and Seed Data

Apply the current schema with:

```powershell
Set-Location backend
alembic upgrade head
```

Seed five fictional clubs, the BRO sample club and demo pricing menu, plus 50 computers with test roles and time-based tariffs:

```powershell
python -m app.seed
```

The seed command is idempotent for a non-empty clubs table. Seed accounts use the reserved `example.com` domain and the development-only password `Cyberoom!2026`; change or remove these accounts outside local development.

| Role | Email | Username |
| --- | --- | --- |
| USER | `player@example.com` | `playerone` |
| STAFF | `staff@example.com` | `clubstaff` |
| OWNER | `owner@example.com` | `clubowner` |
| ADMIN | `admin@example.com` | `platformadmin` |

The password for these local demo accounts is `Cyberoom!2026`. OWNER can assign STAFF accounts to clubs from `/dashboard`; STAFF only sees assigned clubs. Sign in as OWNER, STAFF, or ADMIN to open the matching role dashboard.

BRO is seeded in Astana with its price menu from the supplied reference. Its address and computer lineup are placeholders, and menu prices are informational; online booking quotes continue to use the club's hourly tariffs.

## API Overview

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `GET /api/v1/clubs?page=1&page_size=12&search=RTX&city=Astana`
- `GET /api/v1/clubs/{club_id}`
- `GET /api/v1/clubs/{club_id}/reviews`
- `GET /api/v1/clubs/{club_id}/membership-plans`
- `GET /api/v1/clubs/{club_id}/availability?start_time=...&end_time=...` (timezone-aware, up to seven days)
- `POST /api/v1/bookings/quote`
- `POST /api/v1/bookings`
- `POST /api/v1/bookings/{booking_id}/payment`, `GET /api/v1/payments/{payment_id}`
- `POST /api/v1/membership-plans/{plan_id}/checkout`, `GET /api/v1/memberships`
- `GET /api/v1/bookings`
- `GET /api/v1/bookings/{booking_id}`
- `PATCH /api/v1/bookings/{booking_id}/reschedule`
- `GET/POST /api/v1/bookings/{booking_id}/review`
- `POST /api/v1/bookings/{booking_id}/cancel`
- `GET /api/v1/notifications`, `PATCH /api/v1/notifications/{notification_id}/read`
- `GET/POST /api/v1/waitlist`, `DELETE /api/v1/waitlist/{entry_id}`
- `GET /api/v1/owner/dashboard`, `GET/POST /api/v1/owner/clubs`
- `GET /api/v1/owner/reports?start_date=2026-10-01&end_date=2026-10-26` (up to 90 days; grouped in each club's time zone)
- `GET /api/v1/owner/audit?limit=100`, `GET /api/v1/admin/audit?limit=100`
- `GET /api/v1/owner/promo-codes`, `POST /api/v1/owner/clubs/{club_id}/promo-codes`
- `GET /api/v1/owner/membership-plans`, `POST /api/v1/owner/clubs/{club_id}/membership-plans`
- `GET /api/v1/owner/shifts`, `POST /api/v1/owner/clubs/{club_id}/shifts`, `DELETE /api/v1/owner/shifts/{shift_id}`, `GET /api/v1/staff/shifts`
- `POST /api/v1/owner/clubs/{club_id}/computers`, `POST /api/v1/owner/clubs/{club_id}/tariffs`
- `POST /api/v1/owner/clubs/{club_id}/staff`, `GET /api/v1/owner/bookings`
- `GET /api/v1/staff/dashboard`, `GET /api/v1/staff/bookings`, `GET /api/v1/staff/computers`
- `POST /api/v1/staff/bookings/verify-qr`, `POST /api/v1/staff/bookings/{booking_id}/check-in`, `POST /api/v1/staff/bookings/{booking_id}/complete`
- `POST /api/v1/staff/walk-ins` (guest name, computer, end time; starts the session immediately)
- `POST /api/v1/staff/bookings/{booking_id}/start`, `POST /api/v1/staff/bookings/{booking_id}/extend`, `POST /api/v1/staff/bookings/{booking_id}/end`
- `GET /api/v1/admin/dashboard`, `GET /api/v1/admin/users`, `GET /api/v1/admin/clubs`, `GET /api/v1/admin/bookings`

Interactive API documentation is served by FastAPI at `/docs`.

## Booking Rules

The server ignores client prices and calculates cost from active club tariffs by the minute. Bookings require timezone-aware whole-minute timestamps and must be between 15 minutes and 8 hours. A booking cannot start in the past, and maintenance/disabled computers cannot be booked. Users can only view, cancel, and reschedule their own bookings; cancellation and rescheduling are limited to upcoming pending or confirmed bookings. Reviews are limited to completed online bookings and one review per booking.

Promo codes are validated and usage is reserved atomically when a booking is created. Hour packs cover a complete booking interval; the balance is debited at reservation and restored when an upcoming booking is cancelled or expires. Paid booking cancellations issue a full refund only when made at least the club's configured cutoff hours before the start. A payment provider adapter must be configured to create checkout sessions, confirm status, cancel pending checkout, and process refunds.

Tariffs use the club's IANA time zone and selected weekdays, regardless of the offset in the client's request. Overnight tariff windows apply to the weekday on which they start. Existing clubs receive `Asia/Almaty` when migration `0004` runs; owners should check each club's time zone in the dashboard and correct it before accepting new reservations. Changing the time zone is blocked while the club has active or upcoming bookings. New bookings keep the 15-minute minimum; an active session may be extended by a shorter whole-minute interval if its total duration remains within eight hours.

The service checks for overlap to return a useful conflict error. PostgreSQL is the final concurrency guard: a GiST exclusion constraint rejects intersecting `[start, end)` ranges for the same computer while a row lock serializes competing requests.

Walk-in bookings use the same interval check and database constraint as online bookings. Staff must be assigned to the computer's club. A walk-in starts an `ACTIVE` session immediately; online bookings start automatically at the reserved time and finish at the reserved end time. Staff can check in or end a session manually, and can extend an active session only if the new end does not overlap another booking. A session that remains overdue while the worker is offline blocks new bookings until staff resolves it. The availability endpoint lists reserved intervals without customer details. Scheduled automation records reservation times; it does not detect physical occupancy on gaming PCs.

## Tests

Run the unit tests:

```powershell
Set-Location backend
pytest -q
```

The PostgreSQL concurrency test is skipped unless `TEST_DATABASE_URL` points to a dedicated disposable test database. It creates its required tables and `btree_gist` extension, sends two overlapping booking operations concurrently, and asserts exactly one succeeds. For example:

```powershell
$env:TEST_DATABASE_URL = "postgresql+asyncpg://cyberoom:cyberoom-dev-only@localhost:5432/cyberoom_test"
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

Refresh and logout requests carrying a refresh cookie require a trusted `Origin` matching the configured `CORS_ORIGINS` or the API's own origin. Redis enforces per-IP request windows; in production, requests fail closed if Redis is unavailable. This is an early project phase, not a complete production service. Audit logging, monitoring, provider connections, and the other unimplemented features listed above remain necessary before public deployment.
