# CLAUDE.md — Chronicle (کرونیکل), an Iranian attendance app (package and command `chronicle`)

Guidance for Claude Code (and any contributor) working in this repository. Read this file fully before writing code.

## What we are building

An open-source attendance (حضور و غیاب) application for Iranian companies: an **independent** Python
backend on PostgreSQL plus one Vue PWA. It reads punches from attendance devices, applies the Iranian
Labor Law (قانون کار ۱۳۶۹), and produces working-time reports. It is **Persian-first**: Jalali (شمسی)
calendar, RTL, Persian UI copy.

The app was called «حضور» / `hozur` until 1405/07/20, when the product owner renamed it Chronicle (see `docs/decisions.md`); the English name is the one shown. The PostgreSQL database and role are still named `hozur`, so existing installations keep their data, and `HOZUR_*` environment variables are still read. Until 1405/07/15 the app was a Frappe app; the product owner decided to leave Frappe (see
`docs/decisions.md`, «استقلال از Frappe»). The last Frappe version is commit `b7a596f` on `main`.

Source-of-truth documents (read before designing anything):

| File | What it holds |
| --- | --- |
| `docs/design-doc.md` | Full design: scope, architecture, data model, approval flow, report builder, roadmap |
| `docs/decisions.md` | Decisions made with the product owner (Arad), with dates |
| `docs/data-model.md` | The PostgreSQL schema: every table, why it exists, its invariants |
| `attendance-software-iran-labor-law-rules.md` | Labor-law rules, articles, legal floors, 1405 holiday list |

If code and these documents disagree, stop and ask. Do not silently pick one.

## Scope

In scope: Jalali calendar with editable holidays refreshed yearly by the system admin; org structure (work location, department tags, the designation tree, employee = user); work patterns (fixed, flexible, rotating) assigned with Jalali validity dates; device ingestion; labor-law calculation engine; leave, mission, overtime and punch-correction requests with configurable approval; report builder with Excel / text / PDF export; an SMS section (panels, templates, history, events with triggers) and payslip distribution (the payroll software's PDF pages sent to each employee as a private SMS link, no pay computation); one PWA for all roles, including every admin screen.

Out of scope — do not build: payroll, insurance or tax amounts; Bale or any messenger bot; punching from the PWA or phone (punches come **only** from devices); native mobile apps; multi-tenant cloud; employee monthly sign-off.

## Stack

| Layer | Choice |
| --- | --- |
| Backend | Python 3.13+, **FastAPI**, Pydantic v2, in `backend/` (package `chronicle`) |
| Database | **PostgreSQL 17**, SQLAlchemy 2.0 (typed ORM), **Alembic** migrations, psycopg 3 |
| Background work | a `chronicle worker` process: scheduler (device polling, nightly jobs) + a job table in PostgreSQL (`FOR UPDATE SKIP LOCKED`). No Redis |
| Auth | own users table, Argon2 password hashes, server-side sessions in PostgreSQL, httpOnly cookie |
| Frontend | Vue 3 + TypeScript + Tailwind (frappe-ui components for now: a standalone MIT UI kit, no Frappe server), in `frontend/`, installable PWA |
| Font / direction | Vazirmatn, RTL everywhere, light + dark mode |
| PDF | WeasyPrint |
| Excel | openpyxl |
| Device protocol | `pyzk` for ZKTeco (TCP 4370) |
| SMS | driver adapters in `chronicle/sms/` (sms.ir and a mock), panels and templates configured in the PWA, sent by the worker; payslip PDFs are read with `pypdf` + `pdfplumber` and watermarked with `reportlab` |
| Jalali math | `jdatetime` (Python), `jalaali-js` (frontend) |
| Holidays | time.ir (official calendar) fetched on the system admin's yearly refresh; bundled offline seed as fallback |
| Translations | English source strings in code, Persian in `backend/chronicle/locale/fa.po` (gettext) |
| Deploy | Docker Compose on each company's own server |
| License | GPLv3 |

We never depend on Frappe, ERPNext or Frappe HR. Code ported from Frappe HR (GPLv3) keeps its attribution comments.

## Non-negotiable rules

1. **Jalali everywhere, no Gregorian business dates.**
   - Business dates (attendance day, leave from/to, holiday, assignment validity, period) are stored in the PostgreSQL domain `jdate` (`char(10)`, `1405/07/14`, ASCII digits, zero-padded, checked by regex). `jyear` / `jmonth` are generated columns where grouping is needed.
   - Weekday and month lengths come from `jdatetime`; holidays come from the `holiday` table. No pre-generated day table.
   - Gregorian values allowed: (a) the raw device timestamp, kept untouched as evidence and converted to Jalali day + time **once, at ingestion**; (b) system instants (`timestamptz`: created_at, audit time, session expiry), which are shown to people only as Jalali.
   - Display Persian digits in the UI; store ASCII digits.
2. **Labor law is data, not code.** Every legal number (8 h/day, 44 h/week, 4 h overtime cap, 26 leave days, 9 carry-over days, 7 h 20 min = one leave day, night window 22–06, etc.) lives in a `labor_rule_set` with a Jalali effective date. Validation must reject settings that are worse for the worker than the legal floor; more generous values are allowed. No legal constant may be hard-coded in the engine.
3. **The calculation engine is pure Python.** `backend/chronicle/engine/` must not import the database, FastAPI or SQLAlchemy. Inputs: punches, the day's resolved shift, the day type, approved requests, the rule set. Output: a daily attendance record. Every labor-law article gets at least one pytest case named after the article (e.g. `test_madde_59_overtime_cap`).
4. **Raw punches are append-only.** A database trigger rejects UPDATE and DELETE on `raw_punch` (and on `audit_entry` and `leave_ledger_entry`). Corrections are separate requests that go through approval. Every change to a calculated or configured record writes an `audit_entry` (who, when, why, before/after).
5. **Devices are configured, not coded.** IP, port, comm key, work location, polling interval and direction mode are columns of `attendance_device`, edited in the PWA. Adapters implement one interface (`fetch_since`, `list_users`, `sync_time`, `health`) and register themselves; adding a device of a supported type must never require a code change. The app must never clear device logs.
6. **Approval is data-driven and follows the designation tree.** A person's parent is whoever holds the nearest filled designation above theirs; the CEO holds the designation flagged `is_ceo` and has no parent. `approval_process` steps are `parent`, `ceo` or a specific person; the standard processes are parent only, parent then CEO (just the CEO when the parent is the CEO), and CEO only; the CEO's own requests need no approval. Chosen per request type, with per-employee `approval_override`. A manager can delegate approval authority to someone for a period (both can then approve). No numeric conditions. Overtime assigned by a manager needs employee acceptance (Article 59).
7. **No automatic dismissal logic.** Absence only produces configurable disciplinary warnings.
8. **Permissions:** the system admin and the CEO see everyone; a manager (anyone holding a designation with people below it) sees only the people below their designations, including in reports. Roles are just `admin` (system admin, مدیر سیستم) and `employee`. Every employee is also a user. Enforced in the service layer, never only in the UI.
9. **Locked periods:** once an `attendance_period` (Jalali month) is closed, nothing inside it changes without formally reopening it.
10. **The schema is the contract.** Every schema change is an Alembic migration, reviewed like code and described in `docs/data-model.md`. Constraints (FKs, CHECKs, uniques) live in the database, not only in Python.

## Repository layout

```
backend/
  pyproject.toml
  alembic.ini
  chronicle/
    config.py              # settings from environment
    db/                    # engine/session, types (jdate), models/, migrations/ (Alembic)
    engine/                # pure-Python labor-law engine
    jalali/                # date helpers, bundled holiday seed
    calendar/              # holiday sources (time.ir, bundled, file) and the yearly refresh
    devices/               # adapter interface + adapters (zkteco.py, file_import.py)
    services/              # business logic: resources (config tables), devices (ingestion), attendance,
                           # requests, approvals, suggestions, leave, periods, reports, users, audit,
                           # jobs, excel + cleaning (Excel import with column mapping), backup,
                           # sms (admin), sms_dispatch (the one gate + sender), sms_triggers, payslips
    worker.py              # `chronicle worker`: device polling, job queue, nightly work
    payslips/              # PDF page splitting and the viewer watermark
    sms/                   # SMS driver interface + adapters (smsir.py, mock.py), events, number and masking helpers
    reports/               # field catalog and exporters (xlsx, csv/txt, pdf); the builder is services/reports.py
    api/                   # FastAPI routers used by the PWA
    locale/                # fa.po
  tests/
frontend/                  # Vue 3 + TS PWA (all roles, all admin screens)
docker/                    # dev.yml (PostgreSQL for development), compose.yml (production)
docs/
```

## Development environment

- `docker compose -f docker/dev.yml up -d` starts PostgreSQL 17 with the databases `hozur` and `hozur_test` (user/password `hozur`).
- Backend: `cd backend && python -m venv .venv && .venv/bin/pip install -e '.[dev]'`, then `chronicle db install` (migrations + reference data), `chronicle create-user admin --role admin`, `chronicle serve --reload` (API on :8000) and `chronicle worker` (devices, jobs, nightly work and the nightly backup). Backups: `chronicle backup create|list|restore`.
- Frontend: `cd frontend && yarn && yarn dev` (PWA on :8080, `/api` proxied to :8000).
- Tests: `pytest` in `backend/` (DB tests use `hozur_test`; engine and jalali tests run without it). Frontend: `yarn typecheck && yarn test`. Translations: `python3 tools/i18n.py --check`.
- Production: `Dockerfile` + `docker/compose.yml` (PostgreSQL, app, worker) on the company's own server.

## Working style

- Small, reviewable commits; one feature per branch; conventional commit messages in English.
- Code, identifiers and comments in English. All user-facing strings are Persian and go through translations (`_()` in Python, `__()` in the PWA).
- When a legal rule is unclear or marked † in the labor-law file, implement it as a configurable parameter and leave a `# LEGAL-CHECK:` comment with the article number.
- Ask the product owner before changing scope, data model or any rule above.

## Glossary

| Persian | English / code name |
| --- | --- |
| تردد خام | Raw Punch (`raw_punch`) |
| کارکرد روزانه | Daily Attendance (`daily_attendance`) |
| الگوی کاری / شیفت | Work Pattern / Shift |
| مرخصی استحقاقی / ساعتی / استعلاجی | Earned / Hourly / Sick leave |
| مأموریت | Mission |
| اضافه‌کار | Overtime |
| شب‌کاری / نوبت‌کاری / جمعه‌کاری | Night work / Rotating shift work / Friday work |
| اصلاح تردد | Attendance Correction |
| درخواست | Request (`request` + one detail table per kind) |
| فرایند تأیید | Approval Process |
| قفل دوره | Period lock |
| مجموعه قواعد | Labor Rule Set |
| تعطیلی | Holiday (`holiday`) |
| سمت | Designation (`designation`): a node of the organization chart, held by people with Jalali validity |
| محل کار | Work location (`work_location`): the physical place of work |
| واحد | Department (`department`): a flat tag on people for reports |
| کد تفصیلی | Detail code (`employee.detail_code`): the accounting detail code |
| مدیر سیستم | System admin (role `admin`; there is no separate operator) |
| استراحت / بازهٔ مجاز اضافه‌کار | Break / overtime window (`shift_segment.kind` = `break` / `overtime`) |
| درخواست پیشنهادی | Suggested request (`request_suggestion`): proposed by the calculation, sent or dismissed by the employee |
| پشتیبان | Backup (`chronicle backup`, `services/backup.py`) |
| فیش حقوقی | Payslip (`payslip`): one PDF page of the payroll software per employee and month, sent as a private SMS link (`payslip_link`) |
