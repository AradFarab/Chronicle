# Data model (PostgreSQL)

The schema is the contract of the app (CLAUDE.md rule 10). Every change is an Alembic migration
in `backend/chronicle/db/migrations/` and is reflected here. Constraints live in the database.

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
| `user_role` | roles of a user | PK (`user_id`, `role`); role ∈ `admin` (system admin, مدیر سیستم), `employee`. Who is the CEO or a manager is not a role: it follows from the designation tree |
| `user_session` | server-side sessions | PK is the SHA-256 of the cookie token; `expires_at` |

### Organization

The organization is the tree of designations (سمت). A person's **parent** is whoever holds the nearest filled designation above theirs; their **subordinates** are everyone holding a designation below one they hold. Departments are only tags for reports.

| Table | Purpose | Key invariants |
| --- | --- | --- |
| `organization` | the company (one row) | `id = 1` CHECK. The CEO is not stored here: it is the holder of the designation flagged `is_ceo` |
| `province` | 31 provinces (seeded) | name unique |
| `work_location` | the physical place people work (محل کار); its province decides which provincial holidays apply | name unique |
| `department` | a flat tag put on people (one per employee) so reports can be grouped | name unique; no parent, no manager |
| `designation` | a position in the organization chart; a tree (`parent_id`) | name unique; `parent_id <> id`; at most one `is_ceo` (partial unique index) and it must be a root (CHECK); `hard_and_harmful` flag with the committee ruling |
| `designation_assignment` | a person holds a designation from one Jalali day to another; giving adds a row, taking away sets `valid_to` (history stays). Several people may hold one designation, one person several | `valid_to ≥ valid_from` |
| `employee` | personnel | `code` unique; `detail_code` (کد تفصیلی, accounting detail code) unique when set; `national_id` unique when set; **`user_id` NOT NULL unique: every employee is also a user**; `full_name` generated; `status ∈ active, suspended, left` (a person who left or is suspended cannot log in); `contract_type ∈ full_time, part_time, hourly` |
| `approval_delegation` | a manager hands their approval authority to another person for a period | `delegator_id <> delegate_id`; `valid_to ≥ valid_from` |

### Calendar

| Table | Purpose | Key invariants |
| --- | --- | --- |
| `holiday` | every day off: official solar/lunar/occasional, office closure, company internal | `status ∈ confirmed, predicted`; `scope ∈ country, province, work_location, company` with the matching FK set (CHECK); `source ∈ bundled, time_ir, file, manual`; `closure_pay_mode` only for office closures |
| `calendar_year` | one row per Jalali year: where its holidays came from and when the system admin refreshed it | PK `jyear`; `status ∈ predicted, confirmed` |

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
| `shift` | one working day's hours | name unique; `shift_type ∈ fixed, flexible`; `grace_late_minutes` / `grace_early_minutes`: up to this late or early is forgiven, beyond it the whole time counts; `overtime_after_minutes`: staying up to this long after the end is ignored, beyond it all of it is extra work |
| `shift_segment` | timed parts of a shift drawn in the PWA: breaks (never working time, Article 51; several per shift) and overtime windows (only extra work inside them can become overtime, still with request and approval) | `kind ∈ break, overtime`; `start_minute`/`end_minute` from the shift day's 00:00, `0 ≤ start < end ≤ 2880` (CHECK); breaks inside the shift, windows outside a fixed shift, no overlap within a kind (checked in Python) |
| `work_pattern` | weekly or rotating pattern | name unique; `pattern_type ∈ weekly, rotating`; rotating needs `cycle_start_date` |
| `work_pattern_day` | a day of the pattern | weekly: `weekday` 0–6 (0 = Saturday) unique per pattern; rotating: `cycle_day` 1..n unique per pattern; `shift_id` NULL = rest day |
| `work_pattern_assignment` | who follows which pattern, from–to | `target_type ∈ employee, designation, department, company` and exactly the matching FK (CHECK); `valid_to ≥ valid_from`; `cycle_offset_days ≥ 0` moves a group along a rotating pattern's cycle, so two groups of guards can follow one pattern half a cycle apart |
| `shift_override` | one-day change for one person | unique (`employee_id`, `jdate`); `shift_id` NULL = day off |

Resolution order for a person and day: override → employee → a designation they hold that day → department → company.

### Devices and punches

| Table | Purpose | Key invariants |
| --- | --- | --- |
| `attendance_device` | a configured device (rule 5); `work_location_id` says where it hangs | name unique; `adapter_type` registered in code; `comm_key` encrypted with the app secret; health and sync status columns |
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
| `request` | the common part of every request | `kind ∈ leave, mission, overtime, correction`; `request_type ∈ daily_leave, hourly_leave, mission, overtime, attendance_correction` (selects the approval process); `status ∈ pending, approved, rejected, cancelled`; `start_jdate ≤ end_jdate`; `entered_by_admin` when the system admin filed it for someone |
| `leave_request` | 1:1 detail | daily: from/to dates; hourly: one date and from/to time (CHECK per unit) |
| `mission_request` | 1:1 detail | same shape as leave |
| `overtime_request` | 1:1 detail | `overtime_kind ∈ normal, exceptional, emergency`; `minutes > 0`; `assigned_by_manager` |
| `request_suggestion` | a request the calculation proposes from a day's punches and pattern: overtime (extra work in an overtime window), hourly leave (late / early), correction (missing punch) | `request_type ∈ overtime, hourly_leave, attendance_correction`; `status ∈ open, sent, dismissed`; unique (`employee_id`, `jdate`, `key`) so a dismissed or sent one is never proposed again; open ones are replaced on every recalculation; the employee sends (their consent, Article 59) or dismisses, nothing is submitted for them |
| `correction_item` | lines of a correction | `action ∈ add_punch, ignore_punch`; add needs `time`, ignore needs `raw_punch_id` (CHECK) |
| `request_approval` | one step of the approval chain of a request | unique (`request_id`, `step`); `status ∈ pending, approved, rejected, skipped`; `approver_type ∈ parent, ceo, specific_person, employee_acceptance`; `acted_by_id` is who really decided |
| `request_approval_approver` | who may decide a step: the holders of the designation it resolved to (any one of them, or someone they delegated to) | PK (`approval_id`, `employee_id`); the inbox is a join on this table |
| `approval_process` | named process | name unique |
| `approval_process_step` | ordered steps | unique (`process_id`, `position`); `approver_type ∈ parent, ceo, specific_person` (a person needs the FK) |
| `approval_default` | default process per request type (and for requests the system admin files for someone: `admin_entry`) | PK `request_type` |
| `approval_override` | per-employee exception | unique (`employee_id`, `request_type`) |

### Leave

| Table | Purpose | Key invariants |
| --- | --- | --- |
| `leave_type` | earned, sick, unpaid, … | name unique; `category` enumerated |
| `leave_ledger_entry` | the leave ledger (append-only); a balance is always a SUM | `entry_type ∈ allocation, usage, reversal, carry_over, expiry, adjustment`; optional `request_id` |

### Attendance

| Table | Purpose | Key invariants |
| --- | --- | --- |
| `daily_attendance` | engine output, one row per person and Jalali day | unique (`employee_id`, `jdate`); snapshot of department/work location/designation/pattern/shift/rule set used; `warnings text[]` of engine codes |
| `daily_attendance_leave` | leave minutes/days per type in that day | PK (`attendance_id`, `leave_type_id`) |
| `attendance_period` | Jalali month open/closed (rule 9) | unique (`jyear`, `jmonth`) |

### Reports, settings, audit, jobs

| Table | Purpose | Key invariants |
| --- | --- | --- |
| `report_template` | saved report definition | name unique; `columns jsonb` (catalog keys only, validated in Python); `shared_roles text[]` |
| `app_setting` | key → JSON value (dedup window, warnings, calendar source) | PK `key` |
| `audit_entry` | who changed what, when, why (append-only) | `entity`, `entity_id`, `action`, `before`/`after` JSONB |
| `job` | background work queue | `status ∈ queued, running, done, failed`; picked with `FOR UPDATE SKIP LOCKED` |
