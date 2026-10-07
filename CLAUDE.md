# CLAUDE.md — Iranian Attendance App on Frappe (working name: `hozur`)

Guidance for Claude Code (and any contributor) working in this repository. Read this file fully before writing code.

## What we are building

An open-source attendance (حضور و غیاب) application for Iranian companies, built as **one Frappe app**.
It reads punches from attendance devices, applies the Iranian Labor Law (قانون کار ۱۳۶۹), and produces
working-time reports. It is **Persian-first**: Jalali (شمسی) calendar, RTL, Persian UI copy.

Source-of-truth documents (read before designing anything):

| File | What it holds |
| --- | --- |
| `docs/design-doc.md` | Full design: scope, architecture, data model, approval flow, report builder, roadmap |
| `docs/decisions.md` | Decisions made with the product owner (Arad), with dates |
| `attendance-software-iran-labor-law-rules.md` | Labor-law rules, articles, legal floors, 1405 holiday list |

If code and these documents disagree, stop and ask. Do not silently pick one.

## Scope

In scope: Jalali calendar 1400–1410 with editable holidays; org structure (branch, department tree, designation, employee); work patterns (fixed, flexible, rotating) assigned with Jalali validity dates; device ingestion; labor-law calculation engine; leave, mission, overtime and punch-correction requests with configurable approval; report builder with Excel / text / PDF export; one PWA for all roles.

Out of scope — do not build: payroll, insurance or tax amounts; Bale or any messenger bot; punching from the PWA or phone (punches come **only** from devices); native mobile apps; multi-tenant cloud; employee monthly sign-off.

## Stack

| Layer | Choice |
| --- | --- |
| Framework | Frappe Framework **v16** (Python 3.14, Node 24, MariaDB, Redis) |
| App | single app `hozur` — do **not** fork Frappe, do **not** depend on ERPNext or Frappe HR |
| Frontend | Vue 3 + TypeScript + frappe-ui + Tailwind, in `frontend/`, built into `hozur/public/frontend`, served at `/hozur`, installable PWA |
| Font / direction | Vazirmatn, RTL everywhere, light + dark mode |
| PDF | WeasyPrint (must render Persian correctly — verify in phase 0) |
| Device protocol | `pyzk` for ZKTeco (TCP 4370) |
| Jalali math | `jdatetime` (Python), `jalaali-js` (frontend) |
| Deploy | Docker Compose on each company's own server |
| License | GPLv3 |

Frappe HR (`frappe/hrms`) requires ERPNext, so we never install it. We may **port** code from it (shift, checkin, attendance, leave ledger logic). It is GPLv3, so keep attribution comments on ported code.

## Non-negotiable rules

1. **Jalali everywhere, no Gregorian business dates.**
   - Business dates (attendance day, leave from/to, holiday, assignment validity, period) are stored as `Data` fields in the form `1405/07/14` (ASCII digits, zero-padded), plus `Int` fields `jyear` and `jmonth` when grouping is needed. Never use Frappe `Date` fields for business dates.
   - A pre-generated `Calendar Day` table (one row per Jalali day, 1400–1410) provides the weekday, day type and holiday. The engine reads it instead of converting dates.
   - The only Gregorian values allowed are (a) the raw device timestamp, kept untouched as evidence, and converted to Jalali day + time **once, at ingestion**; and (b) Frappe's own `creation`/`modified` columns, which are never shown or used in calculations.
   - Display Persian digits in the UI; store ASCII digits.
2. **Labor law is data, not code.** Every legal number (8 h/day, 44 h/week, 4 h overtime cap, 26 leave days, 9 carry-over days, 7 h 20 min = one leave day, night window 22–06, etc.) lives in a `Labor Rule Set` with a Jalali effective date. Validation must reject settings that are worse for the worker than the legal floor; more generous values are allowed. No legal constant may be hard-coded in the engine.
3. **The calculation engine is pure Python.** `hozur/engine/` must not import `frappe`. Inputs: punches, the day's resolved shift, the Calendar Day, approved requests, the rule set. Output: a daily attendance record. Every labor-law article gets at least one pytest case named after the article (e.g. `test_madde_59_overtime_cap`).
4. **Raw punches are append-only.** Never update or delete a `Raw Punch`. Corrections are separate `Attendance Correction` documents that go through approval. Every change to a calculated or configured record writes an `Audit Entry` (who, when, why, before/after).
5. **Devices are configured, not coded.** IP, port, comm key, branch, polling interval and direction mode are fields on `Attendance Device`, edited in the PWA. Adapters implement one interface (`fetch_since`, `list_users`, `sync_time`, `health`) and register themselves; adding a device of a supported type must never require a code change. The app must never clear device logs.
6. **Approval is data-driven.** `Approval Process` (no approval / direct manager / manager then CEO / CEO only / custom steps), chosen per request type, with per-employee `Approval Override`. No numeric conditions. Overtime assigned by a manager needs employee acceptance (Article 59).
7. **No automatic dismissal logic.** Absence only produces configurable disciplinary warnings.
8. **Permissions:** role plus department subtree. A manager sees only their department and its children, including in reports.
9. **Locked periods:** once an `Attendance Period` (Jalali month) is closed, nothing inside it changes without formally reopening it.

## Repository layout (target)

```
hozur/                     # Frappe app (Python)
  hooks.py
  hozur/                   # module: doctypes
    doctype/...
  engine/                  # pure-Python labor-law engine (no frappe import)
  jalali/                  # calendar helpers, Calendar Day generator, holiday seed data
  devices/                 # adapter interface + adapters (zkteco.py, file_import.py, ...)
  reports/                 # report builder, exporters (xlsx, csv/txt, pdf)
  api/                     # whitelisted endpoints used by the PWA
  public/frontend/         # built PWA (generated)
frontend/                  # Vue 3 + TS + frappe-ui source
tests/                     # pytest for engine and jalali; Frappe tests for doctypes
docs/                      # design-doc.md, decisions.md
docker/                    # compose files for dev and production
```

## Development environment

- Prefer the official `frappe_docker` dev container (MariaDB + Redis + bench) over a hand-built Mac setup.
- Create the bench on Frappe `version-16`, then `bench new-app hozur` and `bench --site <site> install-app hozur`.
- Keep read-only reference clones **outside** the app, e.g. `../reference/frappe` (version-16), `../reference/hrms` (version-16), `../reference/frappe-ui`. Read them to follow Frappe conventions; never import from `hrms`.
- Run `pytest tests/engine tests/jalali` after every engine change, and `bench --site <site> run-tests --app hozur` for doctype tests.

## Build order (phase 0, then phase 1)

Phase 0 — foundation, each item must pass before moving on:
1. Spike: read users and logs from the company's ZKTeco (likely VF600) with `pyzk`; print Jalali day + time. Never clear logs.
2. Jalali core: helpers, `Calendar Day` generator 1400–1410, 1405 holidays seeded from the labor-law file, lunar holidays for later years marked "پیش‌بینی".
3. Frontend shell: Vue + frappe-ui PWA at `/hozur`, RTL, Vazirmatn, Jalali date picker, design tokens. Must install on a phone.
4. PDF spike: a Persian table rendered correctly through WeasyPrint.
5. Org doctypes: Organization, Branch, Department (tree), Designation, Employee.

Phase 1 — MVP: work patterns and assignment resolution; device adapter + scheduler + Paliz Excel import; engine with tests per article; requests + approval processes; report builder + exports; period lock. Gate: one full month run in parallel with Paliz, every difference explained.

## Working style

- Small, reviewable commits; one feature per branch; conventional commit messages in English.
- Code, identifiers and comments in English. All user-facing strings are Persian and go through Frappe translations (`_()` / `__()`).
- When a legal rule is unclear or marked † in the labor-law file, implement it as a configurable parameter and leave a `# LEGAL-CHECK:` comment with the article number.
- Ask the product owner before changing scope, data model or any rule above.

## Glossary

| Persian | English / code name |
| --- | --- |
| تردد خام | Raw Punch |
| کارکرد روزانه | Daily Attendance |
| الگوی کاری / شیفت | Work Pattern / Shift |
| مرخصی استحقاقی / ساعتی / استعلاجی | Earned / Hourly / Sick leave |
| مأموریت | Mission |
| اضافه‌کار | Overtime |
| شب‌کاری / نوبت‌کاری / جمعه‌کاری | Night work / Rotating shift work / Friday work |
| اصلاح تردد | Attendance Correction |
| فرایند تأیید | Approval Process |
| قفل دوره | Period lock |
| مجموعه قواعد | Labor Rule Set |
| روز تقویم | Calendar Day |
