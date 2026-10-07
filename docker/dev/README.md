# Development environment

Based on [frappe_docker](https://github.com/frappe/frappe_docker)'s `devcontainer-example`:
MariaDB 11.8 + two Redis containers + the official `frappe/bench` image
(Debian trixie, Python 3.14, Node 24, bench, WeasyPrint system libraries).

| Where | What |
| --- | --- |
| this repository | bind-mounted at `/workspace/hozur`, soft-linked into the bench as `apps/hozur` |
| `bench` volume | the bench itself, `/home/frappe/frappe-bench` (Frappe `version-16`) |
| `mariadb-data` volume | the database (root password `123`, dev only) |
| site | `hozur.localhost`, user `Administrator`, password `admin` |

## First run

Requires Docker Desktop (or Docker Engine + compose plugin) with at least 4 GB RAM.

```bash
docker compose -f docker/dev/compose.yml up -d
docker compose -f docker/dev/compose.yml exec frappe bash /workspace/hozur/docker/dev/bootstrap.sh
```

The bootstrap takes 5–10 minutes the first time (clones Frappe, installs Python and Node
dependencies, builds assets, creates the site). It is idempotent: re-run it any time.

With VS Code, "Dev Containers: Reopen in Container" does the same using `.devcontainer/`.

## Daily use

```bash
docker compose -f docker/dev/compose.yml up -d
docker compose -f docker/dev/compose.yml exec frappe bash   # shell in the bench
bench start                                                  # web + workers + scheduler
```

Open http://hozur.localhost:8000 (browsers resolve `*.localhost` to 127.0.0.1; plain
http://localhost:8000 also works because the site is the bench default).

Useful commands inside the container (from `/home/frappe/frappe-bench`):

```bash
bench --site hozur.localhost migrate                 # after changing doctypes / hooks
bench --site hozur.localhost console                 # IPython with frappe loaded
bench build --app hozur                              # rebuild desk assets and the PWA
```

Tests run on a separate, empty site so they never meet your own data:

```bash
bench new-site test.localhost --db-root-username root --db-root-password 123 \
	--admin-password admin --install-app hozur          # once
bench --site test.localhost set-config allow_tests 1   # once
bench --site test.localhost run-tests --app hozur      # Frappe (doctype + API) tests
```

### The PWA (`/hozur`)

The app for employees, managers and operators is a Vue 3 + frappe-ui PWA in `frontend/`.
`bench build --app hozur` builds it into `hozur/public/frontend` and `hozur/www/hozur.html`
(both generated, not committed); open http://hozur.localhost:8000/hozur.

While working on it, run the Vite dev server instead (hot reload, API calls are proxied
to the bench on port 8000):

```bash
cd apps/hozur/frontend
yarn dev            # http://hozur.localhost:8080/hozur
yarn typecheck      # vue-tsc
yarn test           # vitest
```

User-facing strings are English source text wrapped in `__()`; the Persian comes from
`hozur/locale/fa.po` like the rest of the app.

Stop with `docker compose -f docker/dev/compose.yml down`. Add `-v` to also delete the
bench and the database (next bootstrap starts from scratch).

## Notes

- Linux hosts: the container runs as uid 1000 (`frappe`). If your user has another uid,
  give uid 1000 write access to the checkout, or the bench cannot write `*.egg-info`,
  build output and new doctype files into the repository.
- Read-only reference clones (Frappe, Frappe HR, frappe-ui) belong **outside** this
  repository, e.g. `../reference/`. Never import from `hrms`.
- Device spikes that must reach the company network (ZKTeco on TCP 4370) can run inside
  the container too: Docker Desktop routes container traffic to the host's LAN.
