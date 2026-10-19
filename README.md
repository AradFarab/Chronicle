# Chronicle (کرونیکل) — حضور و غیاب

Open-source attendance for Iranian companies: punches come from attendance devices (ZKTeco
first), the Iranian Labor Law (قانون کار ۱۳۶۹) is applied as configurable data, and everything
is Jalali, Persian and RTL. An independent Python server (FastAPI) on PostgreSQL plus one
installable PWA for every role.

Status: phase 1 (MVP), version 0.3.0 (see [CHANGELOG.md](CHANGELOG.md)). Until 0.3.0 the project was called
«حضور» / `hozur`; the database is still named `hozur` and `HOZUR_*` variables are still read.

- **Employees** see their day and month, their leave balance, and file leave, mission,
  overtime and manual time entries.
- **Managers** (anyone with people below their designation) approve, see those people and run reports for them; they can delegate their approvals for a while.
- **The system admin** (مدیر سیستم) manages the organization (employees are users too, designations
  form the chart), work patterns, devices (IP, port, comm key — no code changes), punch-file
  imports, the yearly holiday refresh (time.ir) and the monthly period lock, all from the PWA.
  Every create form also has an Excel sample to download and an Excel import.
- **SMS**: a section for every message the app sends: panels (sms.ir; a primary and a fallback), templates
  (a full text or a panel pattern), a send window, opt-outs and a history with what was sent and what the
  panel answered. Triggers (leave decisions, shift reminders, missed punches, birthdays, ...) send only
  when a template is active.
- **Payslips** (فیش حقوقی): the system admin uploads the payroll software's PDF, each page is matched
  to an employee by the personnel code printed on it, and a private link is sent to every employee by
  SMS. The link opens with the last four digits of the national id and shows the payslip with a watermark.
  Set up a panel and a template for the event «payslip link» in the SMS section first.

| Document | |
| --- | --- |
| [`CLAUDE.md`](CLAUDE.md) | Rules for contributors and coding agents — read first |
| [`docs/data-model.md`](docs/data-model.md) | The PostgreSQL schema (the contract of the app) |
| [`docs/design-doc.md`](docs/design-doc.md) | Design: scope, architecture, roadmap (Persian) |
| [`docs/decisions.md`](docs/decisions.md) | Decisions with the product owner (Persian) |

## Development

```bash
docker compose -f docker/dev.yml up -d          # PostgreSQL 17 (databases hozur, hozur_test)
cd backend
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/chronicle db install                      # schema + reference data + holidays 1400-1410
.venv/bin/chronicle create-user admin --name "مدیر سیستم" --role admin
.venv/bin/chronicle serve --reload                  # API on http://localhost:8000/api
.venv/bin/chronicle worker                          # devices, job queue, nightly work (second terminal)
.venv/bin/pytest -q

cd ../frontend && yarn && yarn dev              # PWA on http://localhost:8080
```

## Production (one company, its own server)

```bash
cp docker/.env.example docker/.env               # set POSTGRES_PASSWORD and CHRONICLE_SECRET_KEY
docker compose -f docker/compose.yml --env-file docker/.env up -d --build
docker compose -f docker/compose.yml --env-file docker/.env exec app chronicle create-user admin --role admin
```

The app listens on port 8000; serve it over HTTPS (the company's reverse proxy) so the PWA can
be installed on phones.

Backups: the worker takes one every night (Manage → Backups sets the hour and how many to keep)
into `/data/backups` of the `files` volume; download copies from the same page and keep them
somewhere else. To restore, stop the worker and run
`docker compose -f docker/compose.yml --env-file docker/.env exec app chronicle backup restore <name>`.

## Contributing

`pre-commit install` once (ruff). Every user-facing string is English in code and Persian in
`backend/chronicle/locale/fa.po`: run `python3 tools/i18n.py` after adding strings.

## License

GPLv3 — see [LICENSE](LICENSE). Code ported from [Frappe HR](https://github.com/frappe/hrms)
(GPLv3) keeps its attribution comments.
