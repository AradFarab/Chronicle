# hozur — حضور و غیاب

Open-source attendance for Iranian companies: punches come from attendance devices (ZKTeco
first), the Iranian Labor Law (قانون کار ۱۳۶۹) is applied as configurable data, and everything
is Jalali, Persian and RTL. An independent Python server (FastAPI) on PostgreSQL plus one
installable PWA for every role.

Status: phase 1 (MVP) in progress. Working name `hozur`; the final name is still open.

- **Employees** see their day and month, their leave balance, and file leave, mission,
  overtime and manual time entries.
- **Managers** (anyone with people below their designation) approve, see those people and run reports for them; they can delegate their approvals for a while.
- **The system admin** (مدیر سیستم) manages the organization (employees are users too, designations
  form the chart), work patterns, devices (IP, port, comm key — no code changes), punch-file
  imports, the yearly holiday refresh (time.ir) and the monthly period lock, all from the PWA.
  Every create form also has an Excel sample to download and an Excel import.

| Document | |
| --- | --- |
| [`CLAUDE.md`](CLAUDE.md) | Rules for contributors and coding agents — read first |
| [`docs/data-model.md`](docs/data-model.md) | The PostgreSQL schema (the contract of the app) |
| [`docs/design-doc.md`](docs/design-doc.md) | Design: scope, architecture, roadmap (Persian) |
| [`docs/decisions.md`](docs/decisions.md) | Decisions with the product owner (Persian) |

## Development

```bash
docker compose -f docker/dev.yml up -d          # PostgreSQL 17 (hozur, hozur_test)
cd backend
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/hozur db install                      # schema + reference data + holidays 1400-1410
.venv/bin/hozur create-user admin --name "مدیر سیستم" --role admin
.venv/bin/hozur serve --reload                  # API on http://localhost:8000/api
.venv/bin/hozur worker                          # devices, job queue, nightly work (second terminal)
.venv/bin/pytest -q

cd ../frontend && yarn && yarn dev              # PWA on http://localhost:8080
```

## Production (one company, its own server)

```bash
cp docker/.env.example docker/.env               # set POSTGRES_PASSWORD and HOZUR_SECRET_KEY
docker compose -f docker/compose.yml --env-file docker/.env up -d --build
docker compose -f docker/compose.yml --env-file docker/.env exec app hozur create-user admin --role admin
```

The app listens on port 8000; serve it over HTTPS (the company's reverse proxy) so the PWA can
be installed on phones.

Backups: the worker takes one every night (Manage → Backups sets the hour and how many to keep)
into `/data/backups` of the `files` volume; download copies from the same page and keep them
somewhere else. To restore, stop the worker and run
`docker compose -f docker/compose.yml --env-file docker/.env exec app hozur backup restore <name>`.

## Contributing

`pre-commit install` once (ruff). Every user-facing string is English in code and Persian in
`backend/hozur/locale/fa.po`: run `python3 tools/i18n.py` after adding strings.

## License

GPLv3 — see [LICENSE](LICENSE). Code ported from [Frappe HR](https://github.com/frappe/hrms)
(GPLv3) keeps its attribution comments.
