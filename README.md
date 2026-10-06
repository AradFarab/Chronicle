# hozur — حضور و غیاب

Open-source attendance for Iranian companies, built as a single [Frappe](https://frappe.io/framework)
v16 app: punches come from attendance devices (ZKTeco first), the Iranian Labor Law (قانون کار ۱۳۶۹)
is applied as configurable data, and everything is Jalali, Persian and RTL.

Status: phase 0 (foundation). Working name `hozur`; the final name is still open.

| Document | |
| --- | --- |
| [`CLAUDE.md`](CLAUDE.md) | Rules for contributors and coding agents — read first |
| [`docs/design-doc.md`](docs/design-doc.md) | Design: scope, architecture, data model, roadmap (Persian) |
| [`docs/decisions.md`](docs/decisions.md) | Decisions with the product owner (Persian) |
| [`docker/dev/README.md`](docker/dev/README.md) | Development environment (frappe_docker based) |

## Quick start (development)

```bash
docker compose -f docker/dev/compose.yml up -d
docker compose -f docker/dev/compose.yml exec frappe bash /workspace/hozur/docker/dev/bootstrap.sh
docker compose -f docker/dev/compose.yml exec frappe bench start
# http://hozur.localhost:8000  —  Administrator / admin
```

## Contributing

This app uses `pre-commit` (ruff, eslint, prettier). Install it and run `pre-commit install`
in the repository.

## License

GPLv3 — see [LICENSE](LICENSE). Code ported from [Frappe HR](https://github.com/frappe/hrms)
(GPLv3) keeps its attribution comments.
