"""The web application: the JSON API under /api and, in production, the built PWA."""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from chronicle import __version__
from chronicle.api.deps import csrf_guard
from chronicle.api.routes import (
	admin,
	attendance,
	auth,
	calendar,
	devices,
	imports,
	me,
	people,
	reports,
	requests,
)
from chronicle.config import get_settings
from chronicle.i18n import DEFAULT_LANGUAGE, translate
from chronicle.services.errors import ChronicleError


def _language(request: Request) -> str:
	return getattr(request.state, "language", None) or DEFAULT_LANGUAGE


def create_app() -> FastAPI:
	app = FastAPI(title="Chronicle", version=__version__, dependencies=[Depends(csrf_guard)])

	@app.exception_handler(ChronicleError)
	async def chronicle_error(request: Request, exc: ChronicleError):
		return JSONResponse(
			{"message": exc.translated(_language(request)), "error": type(exc).__name__},
			status_code=exc.status_code,
		)

	@app.exception_handler(RequestValidationError)
	async def bad_input(request: Request, exc: RequestValidationError):
		return JSONResponse(
			{
				"message": translate("Some fields are missing or invalid", _language(request)),
				"detail": exc.errors(),
			},
			status_code=422,
		)

	@app.get("/api/health", tags=["system"])
	def health() -> dict:
		return {"ok": True, "version": __version__}

	# people before admin: its employee routes win over the generic /api/admin/{name}
	for module in (auth, me, requests, calendar, attendance, devices, reports, people, imports, admin):
		app.include_router(module.router)

	dist = get_settings().frontend_dist
	if dist and Path(dist).is_dir():
		_serve_pwa(app, Path(dist))
	return app


def _serve_pwa(app: FastAPI, dist: Path) -> None:
	"""Static assets as files; every other path gets index.html (client-side routing)."""
	app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
	index = dist / "index.html"

	@app.get("/{path:path}", include_in_schema=False)
	def spa(path: str):
		candidate = (dist / path).resolve()
		if path and candidate.is_file() and dist.resolve() in candidate.parents:
			return FileResponse(candidate)
		return FileResponse(index)
