"""Command line: `hozur db install`, `hozur create-user`, `hozur serve`, `hozur worker`."""

from __future__ import annotations

import argparse
import getpass
import sys


def _db_upgrade(args) -> None:
	from hozur.db.migrate import upgrade

	upgrade()
	print("database schema is up to date")


def _db_install(args) -> None:
	from hozur.db.migrate import upgrade
	from hozur.db.session import session_scope
	from hozur.setup import install

	upgrade()
	with session_scope() as session:
		install.run(session)
	print("database schema and reference data are ready")


def _create_user(args) -> None:
	from hozur.db.session import session_scope
	from hozur.services import users

	password = args.password or getpass.getpass("password: ")
	with session_scope() as session:
		user = users.create_user(
			session,
			username=args.username,
			full_name=args.name or args.username,
			password=password,
			roles=args.role,
		)
		print(f"user {user.username} created with roles {', '.join(sorted(user.role_names))}")


def _serve(args) -> None:
	import uvicorn

	uvicorn.run("hozur.api.app:create_app", factory=True, host=args.host, port=args.port, reload=args.reload)


def _worker(args) -> None:
	from hozur.worker import run

	run()


def main(argv: list[str] | None = None) -> None:
	parser = argparse.ArgumentParser(prog="hozur", description="Hozur attendance server")
	sub = parser.add_subparsers(dest="command", required=True)

	db = sub.add_parser("db", help="database schema")
	db_sub = db.add_subparsers(dest="db_command", required=True)
	db_sub.add_parser("upgrade", help="apply migrations").set_defaults(func=_db_upgrade)
	db_sub.add_parser("install", help="apply migrations and seed reference data").set_defaults(
		func=_db_install
	)

	user = sub.add_parser("create-user", help="create a user (e.g. the first admin)")
	user.add_argument("username")
	user.add_argument("--name")
	user.add_argument("--password", help="prompted when omitted")
	user.add_argument("--role", action="append", default=[], help="admin, operator, ceo, manager, employee")
	user.set_defaults(func=_create_user)

	serve = sub.add_parser("serve", help="run the web server")
	serve.add_argument("--host", default="127.0.0.1")
	serve.add_argument("--port", type=int, default=8000)
	serve.add_argument("--reload", action="store_true")
	serve.set_defaults(func=_serve)

	sub.add_parser("worker", help="run the scheduler and job queue").set_defaults(func=_worker)

	args = parser.parse_args(argv)
	args.func(args)


if __name__ == "__main__":
	sys.exit(main())
