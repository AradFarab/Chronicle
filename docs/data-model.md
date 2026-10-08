# Data model (PostgreSQL)

The schema is the contract of the app (CLAUDE.md rule 10). Every change is an Alembic migration
in `backend/hozur/db/migrations/` and is reflected here. Constraints live in the database.

## Conventions

| Topic | Rule |
| --- | --- |
| Keys | `id bigint GENERATED ALWAYS AS IDENTITY`; natural keys (employee code, names) are `UNIQUE` columns, never primary keys |
| Names | `snake_case`, singular table names (`employee`, `holiday`) |
| Business dates | domain `jdate` = `char(10)` checked by `^1[34][0-9]{2}/(0[1-9]\|1[0-2])/(0[1-9]\|[12][0-9]\|3[01])$`; full validity (e.g. 1404/12/30) is checked in Python with jdatetime |
| Grouping | `jyear`, `jmonth` are `GENERATED ALWAYS AS (...) STORED` from the `jdate` column, so they can never drift |
| Times of day | `time(0)`; minutes as `integer` |
| System instants | `timestamptz` (`created_at`, `updated_at`, audit time, session expiry); shown to people only as Jalali |
| Enumerations | `text` + `CHECK (col IN (...))` with lower-case codes (`'pending'`); labels are translated in the app |
| Booleans | `boolean NOT NULL DEFAULT false` |
| Money | none: payroll is out of scope |
| Append-only | trigger `forbid_change()` rejects UPDATE/DELETE on `raw_punch`, `audit_entry`, `leave_ledger_entry` |
| Deletes | FKs are `ON DELETE RESTRICT` unless a child row is part of its parent (`ON DELETE CASCADE`: steps, items, details) |
| Files | uploads live on disk under the data directory; `stored_file` holds the metadata and a SHA-256 |

## Tables by area

### Access

| Table | Purpose | Key invariants |
| --- | --- | --- |
| `app_user` | people who log in | `username` unique (lower-case); `password_hash` Argon2; `language` default `fa` |
| `user_role` | roles of a user | PK (`user_id`, `role`); role ∈ `admin, operator, ceo, manager, employee` |
| `user_session` | server-side sessions | PK is the SHA-256 of the cookie token; `expires_at` |

### Organization

| Table | Purpose | Key invariants |
| --- | --- | --- |
| `organization` | the company (one row) | `id = 1` CHECK; CEO is an employee |
| `province` | 31 provinces (seeded) | name unique |
| `branch` | branches; province for provincial holidays | name unique |
| `department` | department tree (adjacency list, read with recursive CTEs) | name unique; `parent_id` self-FK; manager, default approver, deputy with Jalali validity |
| `designation` | job titles; hard-and-harmful flag | name unique |
| `employee` | personnel | `code` unique; `national_id` unique when set; `user_id` unique when set; `full_name` generated; `status ∈ active, suspended, left`; `contract_type ∈ full_time, part_time, hourly` |

### Calendar

| Table | Purpose | Key invariants |
| --- | --- | --- |
| `holiday` | every day off: official solar/lunar/occasional, office closure, company internal | `status ∈ confirmed, predicted`; `scope ∈ country, province, branch, company` with the matching FK set (CHECK); `source ∈ bundled, time_ir, file, manual`; `closure_pay_mode` only for office closures |
| `calendar_year` | one row per Jalali year: where its holidays came from and when the operator refreshed it | PK `jyear`; `status ∈ predicted, confirmed` |

Weekdays and month lengths are computed with jdatetime; there is no per-day table.

### Labor rules

| Table | Purpose | Key invariants |
| --- | --- | --- |
| `labor_rule_set` | legal parameters with a Jalali effective date | name unique; `parameters jsonb` validated against the engine's parameter list and the legal baseline; at most one `is_legal_baseline` row (partial unique index); `effective_from` unique |

Parameters are JSONB so that a new legal parameter does not need a schema change; the engine
(`engine/rules.py`) is the single list of parameter names, units and legal floors.

### Schedules

| Table | Purpose | Key invariants |
| --- | --- | --- |
| `shift` | one working day's hours | name unique; `shift_type ∈ fixed, flexible`; break inside the shift (checked in Python) |
| `work_pattern` | weekly or rotating pattern | name unique; `pattern_type ∈ weekly, rotating`; rotating needs `cycle_start_date` |
| `work_pattern_day` | a day of the pattern | weekly: `weekday` 0–6 (0 = Saturday) unique per pattern; rotating: `cycle_day` 1..n unique per pattern; `shift_id` NULL = rest day |
| `work_pattern_assignment` | who follows which pattern, from–to | `target_type ∈ employee, designation, department, company` and exactly the matching FK (CHECK); `valid_to ≥ valid_from` |
| `shift_override` | one-day change for one person | unique (`employee_id`, `jdate`); `shift_id` NULL = day off |

Resolution order for a person and day: override → employee → designation → department (walking up) → company.

### Devices and punches

| Table | Purpose | Key invariants |
| --- | --- | --- |
| `attendance_device` | a configured device (rule 5) | name unique; `adapter_type` registered in code; `comm_key` encrypted with the app secret; health and sync status columns |
| `device_user_map` | device user id → employee, with Jalali validity | unique (`device_id`, `device_user_id`, `valid_from`) |
| `raw_punch` | every punch as received (append-only) | `dedup_key` unique; `jdate` + `time` set once at ingestion; `device_timestamp` raw device clock; `source ∈ device, file_import` |
| `punch_import_template` | how to read a USB/Excel/CSV file | name unique |
| `punch_import` | one imported file and its counts | FK to device, template, file |
| `stored_file` | uploaded files | SHA-256, size, content type |

### Requests and approvals ("forms and processes")

All four request kinds share one `request` row (class-table inheritance), so numbering, status,
the approval chain, the inbox and the audit trail are the same for every kind. A correction
needs no detail table: its day is the request's `start_jdate`, its lines are `correction_item`.
The request number (`LV-00012`, `MS-…`, `OT-…`, `COR-…`) is a generated column.

| Table | Purpose | Key invariants |
| --- | --- | --- |
| `request` | the common part of every request | `kind ∈ leave, mission, overtime, correction`; `request_type ∈ daily_leave, hourly_leave, mission, overtime, attendance_correction` (selects the approval process); `status ∈ pending, approved, rejected, cancelled`; `start_jdate ≤ end_jdate`; `pending_*` columns mirror the current step for a fast inbox |
| `leave_request` | 1:1 detail | daily: from/to dates; hourly: one date and from/to time (CHECK per unit) |
| `mission_request` | 1:1 detail | same shape as leave |
| `overtime_request` | 1:1 detail | `overtime_kind ∈ normal, exceptional, emergency`; `minutes > 0`; `assigned_by_manager` |
| `correction_item` | lines of a correction | `action ∈ add_punch, ignore_punch`; add needs `time`, ignore needs `raw_punch_id` (CHECK) |
| `request_approval` | the approval chain of one request | unique (`request_id`, `step`); `status ∈ pending, approved, rejected, skipped` |
| `approval_process` | named process | name unique |
| `approval_process_step` | ordered steps | unique (`process_id`, `position`); `approver_type ∈ direct_manager, parent_department_manager, ceo, specific_person` (person needs the FK) |
| `approval_default` | default process per request type (and for operator entries) | PK `request_type` |
| `approval_override` | per-employee exception | unique (`employee_id`, `request_type`) |

### Leave

| Table | Purpose | Key invariants |
| --- | --- | --- |
| `leave_type` | earned, sick, unpaid, … | name unique; `category` enumerated |
| `leave_ledger_entry` | the leave ledger (append-only); a balance is always a SUM | `entry_type ∈ allocation, usage, reversal, carry_over, expiry, adjustment`; optional `request_id` |

### Attendance

| Table | Purpose | Key invariants |
| --- | --- | --- |
| `daily_attendance` | engine output, one row per person and Jalali day | unique (`employee_id`, `jdate`); snapshot of department/branch/designation/pattern/shift/rule set used; `warnings text[]` of engine codes |
| `daily_attendance_leave` | leave minutes/days per type in that day | PK (`attendance_id`, `leave_type_id`) |
| `attendance_period` | Jalali month open/closed (rule 9) | unique (`jyear`, `jmonth`) |

### Reports, settings, audit, jobs

| Table | Purpose | Key invariants |
| --- | --- | --- |
| `report_template` | saved report definition | name unique; `columns jsonb` (catalog keys only, validated in Python); `shared_roles text[]` |
| `app_setting` | key → JSON value (dedup window, warnings, calendar source) | PK `key` |
| `audit_entry` | who changed what, when, why (append-only) | `entity`, `entity_id`, `action`, `before`/`after` JSONB |
| `job` | background work queue | `status ∈ queued, running, done, failed`; picked with `FOR UPDATE SKIP LOCKED` |
