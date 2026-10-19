"""Payslips (فیش حقوقی): store the pages of the finance software's PDF, send each employee a
private link by SMS, and serve the page to its owner after a second factor.

The app never computes pay. A payslip is one PDF page per employee and Jalali month, found by
the personnel code printed on it. The link is a random token (only its SHA-256 is stored for
lookup; the token waits encrypted until the SMS has gone out), limited in time and views, and
the page opens only with the last four digits of the employee's national id. The national id
printed on the page must be the employee's, or no link is made: nobody's slip may reach somebody
else. Every file served carries the viewer's name and the time as a watermark.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import re
import secrets
import string
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from chronicle.clock import now, now_jalali
from chronicle.db.models import (
	Employee,
	Organization,
	Payslip,
	PayslipLink,
	PayslipRejection,
	PayslipView,
	StoredFile,
)
from chronicle.db.models.org import ACTIVE, LEFT
from chronicle.db.models.payslips import (
	FAILED,
	MATCH,
	MISMATCH,
	PENDING,
	SENT,
	TOO_MANY_ATTEMPTS,
	UNKNOWN,
	VOIDED,
)
from chronicle.i18n import DEFAULT_LANGUAGE, _, translate
from chronicle.jalali.dates import MONTH_NAMES, from_gregorian, to_ascii_digits
from chronicle.payslips import pdf
from chronicle.payslips.watermark import watermark_pdf
from chronicle.secrets import decrypt, encrypt
from chronicle.services import audit, files, jobs, settings
from chronicle.services import sms as sms_service
from chronicle.services.access import Actor
from chronicle.services.errors import ChronicleError, NotFound, PermissionDenied, ValidationError
from chronicle.sms.base import SmsError, SmsMessage

SETTING = "payslips"
DEFAULT_MESSAGE = "{name} عزیز، فیش حقوقی {month} شما آماده است:\n{link}\nاعتبار تا {expires}"
PLACEHOLDERS = frozenset({"name", "month", "link", "expires"})
DEFAULTS: dict[str, Any] = {
	"base_url": "",  # the public address of this server, e.g. https://chronicle.example.ir
	"link_expiry_days": 14,
	"link_max_views": 5,
	"max_failed_attempts": 5,
	"message": DEFAULT_MESSAGE,
}
LINK_PATH = "/p/"  # the PWA's public payslip page
MOBILE_RE = re.compile(r"^09\d{9}$")
MODES = ("unsent", "all")  # who gets an SMS: people without a working link, or everyone ready


class LinkInvalid(NotFound):
	"""One answer for every reason a link does not work, so a guesser learns nothing."""


class WrongSecret(ChronicleError):
	status_code = 403


def _require_admin(actor: Actor) -> None:
	if not actor.is_admin:
		raise PermissionDenied(_("Not permitted"))


# settings ---------------------------------------------------------------------------------------


def get_settings(session: Session) -> dict[str, Any]:
	return {**DEFAULTS, **(settings.get(session, SETTING) or {})}


def _check_message(message: str) -> None:
	try:
		names = {f for _t, f, _s, _c in string.Formatter().parse(message) if f is not None}
	except ValueError:
		names = set()
		message = ""
	if "link" not in names or names - PLACEHOLDERS or not message.strip():
		raise ValidationError(
			_("The message must contain {0} and may only use {1}"),
			"{link}",
			"{name} {month} {link} {expires}",
		)


def save_settings(session: Session, actor: Actor, values: dict[str, Any]) -> dict[str, Any]:
	_require_admin(actor)
	current = get_settings(session)
	new = dict(current)
	if "base_url" in values:
		url = str(values["base_url"] or "").strip().rstrip("/")
		if url and not re.match(r"^https?://[^\s/]+\S*$", url):
			raise ValidationError(_("The site address must start with http:// or https://"))
		new["base_url"] = url
	for key, low, high, label in (
		("link_expiry_days", 1, 365, _("Days a link works")),
		("link_max_views", 1, 100, _("Times a link can be opened")),
		("max_failed_attempts", 1, 50, _("Wrong answers before a link locks")),
	):
		if key in values:
			try:
				number = int(to_ascii_digits(str(values[key])))
			except ValueError:
				raise ValidationError(_("{0} must be a number"), label) from None
			if not low <= number <= high:
				raise ValidationError(_("{0} must be between {1} and {2}"), label, low, high)
			new[key] = number
	if "message" in values:
		message = str(values["message"] or "")
		_check_message(message)
		new["message"] = message
	settings.set_value(session, SETTING, new, actor.user_id)
	audit.log(session, "app_setting", SETTING, "update", actor.user_id, None, current, new)
	return new


# helpers ----------------------------------------------------------------------------------------


def month_label(jyear: int, jmonth: int) -> str:
	return f"{MONTH_NAMES[jmonth - 1]} {jyear}"


def _period(jyear: Any, jmonth: Any) -> tuple[int, int]:
	try:
		year, month = int(jyear), int(jmonth)
	except (TypeError, ValueError):
		raise ValidationError(_("Choose a valid year and month")) from None
	if not (1300 <= year <= 1499 and 1 <= month <= 12):
		raise ValidationError(_("Choose a valid year and month"))
	return year, month


def _code_key(code: str | None) -> str | None:
	"""The number at the end of a personnel code, without leading zeros: «EMP042» and «42»
	both give «42», the way the finance software prints it."""
	match = re.search(r"(\d+)$", to_ascii_digits(code or "").strip())
	if not match:
		return None
	return match.group(1).lstrip("0") or None


def _mobile(employee: Employee) -> str | None:
	value = to_ascii_digits(employee.mobile or "").strip().replace(" ", "")
	return value if MOBILE_RE.match(value) else None


def _hash(token: str) -> str:
	return hashlib.sha256(token.encode()).hexdigest()


def _text(error: tuple) -> str:
	"""A reason (English template and arguments) in the company language, for storing."""
	template, *params = error
	return translate(template, DEFAULT_LANGUAGE).format(*params)


def _national_status(printed: str | None, employee: Employee) -> str:
	if not printed or not employee.national_id:
		return UNKNOWN
	return MATCH if to_ascii_digits(printed) == to_ascii_digits(employee.national_id) else MISMATCH


def problem(employee: Employee, payslip: Payslip | None) -> str | None:
	"""Why this person cannot be sent a link now (a code the PWA translates), or None."""
	if payslip is None:
		return "no_payslip"
	if employee.status != ACTIVE:
		return "not_active"
	if payslip.national_status == MISMATCH:
		return "national_mismatch"
	if not employee.national_id:
		return "no_national_id"
	if _mobile(employee) is None:
		return "bad_mobile"
	return None


def link_state(link: PayslipLink, at) -> str:
	if link.locked:
		return link.lock_reason or VOIDED
	if link.expires_at <= at:
		return "expired"
	if link.view_count >= link.max_views:
		return "exhausted"
	return "active"


# uploading --------------------------------------------------------------------------------------


def upload(
	session: Session, actor: Actor, jyear: Any, jmonth: Any, uploads: list[tuple[str, bytes]]
) -> dict[str, int]:
	"""Split the uploaded PDFs, match each page to an employee by the personnel code printed on it
	and store it. Pages that cannot be matched are listed with the reason; nothing is guessed."""
	_require_admin(actor)
	year, month = _period(jyear, jmonth)
	index: dict[str, list[Employee]] = {}
	for employee in session.scalars(select(Employee)):
		key = _code_key(employee.code)
		if key:
			index.setdefault(key, []).append(employee)
	existing = {
		p.employee_id: p
		for p in session.scalars(select(Payslip).where(Payslip.jyear == year, Payslip.jmonth == month))
	}
	seen: dict[int, str] = {}
	counts = {"created": 0, "replaced": 0, "rejected": 0, "mismatch": 0}

	def reject(source: str, page: int | None, error: tuple) -> None:
		session.add(
			PayslipRejection(jyear=year, jmonth=month, source_name=source, page_no=page, reason=_text(error))
		)
		counts["rejected"] += 1

	for filename, content in uploads:
		name = Path(filename or "").name[:255] or "payslips.pdf"
		try:
			pages = pdf.split_pdf(io.BytesIO(content))
		except ValueError as e:
			reject(name, None, (str(e),))
			continue
		for page in pages:
			if page.error:
				reject(name, page.page_no, page.error)
				continue
			matches = index.get(page.code or "", [])
			if not matches:
				reject(name, page.page_no, (_("No employee has the personnel code {0}"), page.code))
				continue
			if len(matches) > 1:
				reject(name, page.page_no, (_("Several employees match the personnel code {0}"), page.code))
				continue
			employee = matches[0]
			if employee.id in seen:
				reject(
					name,
					page.page_no,
					(_("The personnel code {0} is repeated (already on {1})"), page.code, seen[employee.id]),
				)
				continue
			seen[employee.id] = f"{name} / {page.page_no}"
			status = _national_status(page.national, employee)
			counts["mismatch"] += status == MISMATCH
			stored = files.save(session, page.pdf_bytes, "payslip.pdf", "application/pdf", actor.user_id)
			row = existing.get(employee.id)
			if row is None:
				row = Payslip(
					employee_id=employee.id,
					jyear=year,
					jmonth=month,
					file_id=stored.id,
					source_name=name,
					source_page=page.page_no,
					national_status=status,
					uploaded_by_id=actor.user_id,
				)
				session.add(row)
				session.flush()
				existing[employee.id] = row
				counts["created"] += 1
				audit.log(session, "payslip", row.id, "insert", actor.user_id, "uploaded")
				continue
			old_file = row.file_id
			row.file_id, row.source_name, row.source_page = stored.id, name, page.page_no
			row.national_status, row.uploaded_by_id = status, actor.user_id
			session.flush()
			old = session.get(StoredFile, old_file)
			if old is not None:
				files.delete(session, old)
			counts["replaced"] += 1
			audit.log(session, "payslip", row.id, "update", actor.user_id, "replaced by a new upload")
	session.flush()
	return counts


# the month ---------------------------------------------------------------------------------------


def _links_of(session: Session, payslip_ids: list[int]) -> dict[int, PayslipLink]:
	"""The active link of each payslip, else its latest one."""
	if not payslip_ids:
		return {}
	chosen: dict[int, PayslipLink] = {}
	for link in session.scalars(
		select(PayslipLink).where(PayslipLink.payslip_id.in_(payslip_ids)).order_by(PayslipLink.id)
	):
		current = chosen.get(link.payslip_id)
		if current is None or not link.locked or current.locked:
			chosen[link.payslip_id] = link
	return chosen


def overview(session: Session, actor: Actor, jyear: Any, jmonth: Any) -> dict[str, Any]:
	_require_admin(actor)
	year, month = _period(jyear, jmonth)
	at = now()
	payslips = {
		p.employee_id: p
		for p in session.scalars(select(Payslip).where(Payslip.jyear == year, Payslip.jmonth == month))
	}
	links = _links_of(session, [p.id for p in payslips.values()])
	rows = []
	for employee in session.scalars(select(Employee).order_by(Employee.code)):
		payslip = payslips.get(employee.id)
		if payslip is None and employee.status == LEFT:
			continue
		link = links.get(payslip.id) if payslip else None
		rows.append(
			{
				"employee_id": employee.id,
				"code": employee.code,
				"full_name": employee.full_name,
				"mobile": employee.mobile,
				"payslip": (
					{
						"id": payslip.id,
						"national_status": payslip.national_status,
						"source_name": payslip.source_name,
						"source_page": payslip.source_page,
					}
					if payslip
					else None
				),
				"problem": problem(employee, payslip),
				"link": (
					{
						"id": link.id,
						"state": link_state(link, at),
						"sms_status": link.sms_status,
						"sms_error": link.sms_error,
						"sms_sent_at": link.sms_sent_at,
						"expires_at": link.expires_at,
						"view_count": link.view_count,
						"max_views": link.max_views,
					}
					if link
					else None
				),
			}
		)
	rejections = [
		{
			"id": r.id,
			"source_name": r.source_name,
			"page_no": r.page_no,
			"reason": r.reason,
			"created_at": r.created_at,
		}
		for r in session.scalars(
			select(PayslipRejection)
			.where(PayslipRejection.jyear == year, PayslipRejection.jmonth == month)
			.order_by(PayslipRejection.id.desc())
		)
	]
	with_link = [r["link"] for r in rows if r["link"]]
	return {
		"jyear": year,
		"jmonth": month,
		"month_label": month_label(year, month),
		"rows": rows,
		"rejections": rejections,
		"counts": {
			"employees": len(rows),
			"payslips": len(payslips),
			"missing": sum(1 for r in rows if r["problem"] == "no_payslip"),
			"blocked": sum(1 for r in rows if r["problem"] not in (None, "no_payslip")),
			"sent": sum(1 for link in with_link if link["sms_status"] == SENT),
			"failed": sum(1 for link in with_link if link["sms_status"] == FAILED),
			"viewed": sum(1 for link in with_link if link["view_count"] > 0),
			"rejected": len(rejections),
		},
	}


def _payslip(session: Session, payslip_id: int) -> Payslip:
	row = session.get(Payslip, payslip_id)
	if row is None:
		raise NotFound(_("Not found"))
	return row


def delete_payslip(session: Session, actor: Actor, payslip_id: int) -> None:
	"""Remove a payslip, its links and its file (a wrong upload)."""
	_require_admin(actor)
	row = _payslip(session, payslip_id)
	file_row = session.get(StoredFile, row.file_id)
	before = {"employee_id": row.employee_id, "jyear": row.jyear, "jmonth": row.jmonth}
	session.delete(row)
	session.flush()
	if file_row is not None:
		files.delete(session, file_row)
	audit.log(session, "payslip", payslip_id, "delete", actor.user_id, "deleted", before)


def clear_rejections(session: Session, actor: Actor, jyear: Any, jmonth: Any) -> None:
	_require_admin(actor)
	year, month = _period(jyear, jmonth)
	for row in session.scalars(
		select(PayslipRejection).where(PayslipRejection.jyear == year, PayslipRejection.jmonth == month)
	):
		session.delete(row)


def void_link(session: Session, actor: Actor, link_id: int) -> None:
	"""Stop a link from working (it was sent to the wrong number, say)."""
	_require_admin(actor)
	link = session.get(PayslipLink, link_id)
	if link is None:
		raise NotFound(_("Not found"))
	if not link.locked:
		link.locked, link.lock_reason, link.token_encrypted = True, VOIDED, None
		audit.log(session, "payslip_link", link.id, "update", actor.user_id, "link voided")


def payslip_file(session: Session, actor: Actor, payslip_id: int) -> bytes:
	"""The stored page for the system admin to check (no watermark)."""
	_require_admin(actor)
	row = _payslip(session, payslip_id)
	return files.read(session.get(StoredFile, row.file_id))


# sending ----------------------------------------------------------------------------------------


def _render(cfg: dict[str, Any], name: str, label: str, link: str, expires: str) -> str:
	return cfg["message"].format(name=name, month=label, link=link, expires=expires)


def _expires_label(expires_at) -> str:
	return from_gregorian(expires_at.astimezone(now().tzinfo).date())


def _targets(
	session: Session, year: int, month: int, mode: str, payslip_ids: list[int] | None
) -> tuple[list[tuple[Payslip, Employee, PayslipLink | None]], list[dict[str, Any]]]:
	"""(ready to send, blocked) for the month. «unsent» takes everyone without a link that works
	(none yet, or the SMS failed); «all» everyone who can be sent one, replacing their link."""
	if mode not in MODES:
		raise ValidationError(_("Unknown way of choosing the people"))
	query = (
		select(Payslip, Employee)
		.join(Employee, Employee.id == Payslip.employee_id)
		.where(Payslip.jyear == year, Payslip.jmonth == month)
		.order_by(Employee.code)
	)
	if payslip_ids:
		query = query.where(Payslip.id.in_(payslip_ids))
	pairs = list(session.execute(query).all())
	links = _links_of(session, [p.id for p, _e in pairs])
	ready, blocked = [], []
	for payslip, employee in pairs:
		link = links.get(payslip.id)
		active = link if link is not None and not link.locked else None
		reason = problem(employee, payslip)
		if reason:
			blocked.append(
				{
					"employee_id": employee.id,
					"code": employee.code,
					"full_name": employee.full_name,
					"problem": reason,
				}
			)
		elif active is not None and active.sms_status == PENDING:
			continue  # its SMS is already on its way
		elif mode == "all" or active is None or active.sms_status == FAILED:
			ready.append((payslip, employee, active))
	return ready, blocked


def _not_ready(session: Session) -> ValidationError | None:
	if not get_settings(session)["base_url"]:
		return ValidationError(_("Enter the site address in the payslip settings first"))
	try:
		sms_service.gateway(session)
	except ValidationError as e:
		return e
	return None


def preview(
	session: Session,
	actor: Actor,
	jyear: Any,
	jmonth: Any,
	mode: str = "unsent",
	payslip_ids: list[int] | None = None,
) -> dict[str, Any]:
	"""What sending would do, before anything is sent: how many, who is left out and why, and
	the text of the first message."""
	_require_admin(actor)
	year, month = _period(jyear, jmonth)
	cfg = get_settings(session)
	ready, blocked = _targets(session, year, month, mode, payslip_ids)
	sample = None
	if ready:
		_p, employee, _l = ready[0]
		base = cfg["base_url"] or "https://…"
		expires = _expires_label(now() + timedelta(days=cfg["link_expiry_days"]))
		link = f"{base}{LINK_PATH}{'x' * 20}"
		sample = _render(cfg, employee.full_name, month_label(year, month), link, expires)
	error = _not_ready(session)
	return {
		"count": len(ready),
		"replacing": sum(1 for _p, _e, link in ready if link is not None and link.sms_status == SENT),
		"blocked": blocked,
		"sample": sample,
		"unavailable": error.translated(actor.language) if error else None,
	}


def queue_send(
	session: Session,
	actor: Actor,
	jyear: Any,
	jmonth: Any,
	mode: str = "unsent",
	payslip_ids: list[int] | None = None,
) -> dict[str, Any]:
	"""Make a fresh link for each person and queue the SMS for the worker. A link that was sent
	before is voided: sending again replaces it."""
	_require_admin(actor)
	year, month = _period(jyear, jmonth)
	error = _not_ready(session)
	if error:
		raise error
	cfg = get_settings(session)
	ready, _blocked = _targets(session, year, month, mode, payslip_ids)
	if not ready:
		raise ValidationError(_("There is nobody to send to"))
	at = now()
	link_ids = []
	for payslip, _employee, old in ready:
		if old is not None:
			old.locked, old.lock_reason, old.token_encrypted = True, VOIDED, None
			session.flush()  # only one active link per payslip may exist
		token = secrets.token_urlsafe(32)
		link = PayslipLink(
			payslip_id=payslip.id,
			token_hash=_hash(token),
			token_encrypted=encrypt(token),
			expires_at=at + timedelta(days=cfg["link_expiry_days"]),
			max_views=cfg["link_max_views"],
			view_count=0,
			failed_attempts=0,
			locked=False,
			sms_status=PENDING,
			created_by_id=actor.user_id,
		)
		session.add(link)
		session.flush()
		link_ids.append(link.id)
		audit.log(
			session,
			"payslip_link",
			link.id,
			"insert",
			actor.user_id,
			"SMS queued",
			after={"payslip_id": payslip.id, "replaced": old.id if old else None},
		)
	job = jobs.enqueue(session, jobs.PAYSLIP_SEND, {"link_ids": link_ids})
	return {"queued": len(link_ids), "job_id": job.id}


def send_pending(session: Session, link_ids: list[int] | None = None) -> dict[str, int]:
	"""The worker's job: send the SMS of the pending links in batches and record the outcome of
	each. A failure is recorded on the links, not retried by itself: nobody is texted twice, and
	«send to those without a working link» picks the failed ones up again."""
	query = select(PayslipLink).where(PayslipLink.sms_status == PENDING, PayslipLink.locked.is_(False))
	if link_ids:
		query = query.where(PayslipLink.id.in_(link_ids))
	links = list(session.scalars(query.order_by(PayslipLink.id)))
	result = {"sent": 0, "failed": 0}
	if not links:
		return result

	def fail(chosen: list[PayslipLink], why: str) -> None:
		for link in chosen:
			link.sms_status, link.sms_error, link.token_encrypted = FAILED, why[:1000], None
		result["failed"] += len(chosen)

	cfg = get_settings(session)
	try:
		gateway = sms_service.gateway(session)
	except ValidationError as e:
		fail(links, e.translated(DEFAULT_LANGUAGE))
		return result
	if not cfg["base_url"]:
		fail(links, translate(_("Enter the site address in the payslip settings first"), DEFAULT_LANGUAGE))
		return result
	info = {
		p.id: (p, e)
		for p, e in session.execute(
			select(Payslip, Employee)
			.join(Employee, Employee.id == Payslip.employee_id)
			.where(Payslip.id.in_([link.payslip_id for link in links]))
		)
	}
	size = max(1, gateway.batch_size)
	for start in range(0, len(links), size):
		chunk = links[start : start + size]
		messages, sendable = [], []
		for link in chunk:
			payslip, employee = info[link.payslip_id]
			token = decrypt(link.token_encrypted)
			mobile = _mobile(employee)
			if not token or not mobile:
				fail([link], translate(_("The link or the mobile number is not usable"), DEFAULT_LANGUAGE))
				continue
			text = _render(
				cfg,
				employee.full_name,
				month_label(payslip.jyear, payslip.jmonth),
				f"{cfg['base_url']}{LINK_PATH}{token}",
				_expires_label(link.expires_at),
			)
			messages.append(SmsMessage(mobile, text))
			sendable.append(link)
		if messages:
			try:
				outcomes = gateway.send(messages)
			except SmsError as e:
				fail(sendable, sms_service.admin_text(e))
			else:
				stamp = now()
				for link, outcome in zip(sendable, outcomes, strict=True):
					if outcome.ok:
						link.sms_status, link.sms_sent_at = SENT, stamp
						link.sms_provider_id = outcome.provider_id
						link.sms_error, link.token_encrypted = None, None
						result["sent"] += 1
					else:
						fail([link], outcome.error or translate(_("The SMS was refused"), DEFAULT_LANGUAGE))
		session.commit()  # progress survives a crash: what was sent is never sent again
	return result


# the employee's side (no login) -----------------------------------------------------------------


def _live_link(session: Session, token: str | None) -> tuple[PayslipLink, Payslip, Employee]:
	invalid = _("This link is invalid or has expired")
	if not token or len(token) > 128:
		raise LinkInvalid(invalid)
	link = session.scalar(select(PayslipLink).where(PayslipLink.token_hash == _hash(token)).with_for_update())
	if link is None or link_state(link, now()) != "active":
		raise LinkInvalid(invalid)
	payslip = session.get(Payslip, link.payslip_id)
	employee = session.get(Employee, payslip.employee_id)
	if employee.status != ACTIVE or payslip.national_status == MISMATCH:
		raise LinkInvalid(invalid)
	return link, payslip, employee


def link_info(session: Session, token: str) -> dict[str, str]:
	"""What the link page shows before the question: which month, whose company."""
	_link, payslip, _employee = _live_link(session, token)
	return {
		"month_label": month_label(payslip.jyear, payslip.jmonth),
		"organization": session.scalar(select(Organization.name).where(Organization.id == 1)) or "",
	}


def open_payslip(session: Session, token: str, secret: str, ip: str | None) -> tuple[bytes, str]:
	"""The employee's payslip as a watermarked PDF, after the last four digits of their national
	id. A wrong answer is counted (and kept although the request fails); too many lock the link."""
	link, payslip, employee = _live_link(session, token)
	expected = (employee.national_id or "")[-4:]
	given = to_ascii_digits(secret or "").strip()
	if not expected or not hmac.compare_digest(given.encode(), expected.encode()):
		link.failed_attempts += 1
		locked = link.failed_attempts >= get_settings(session)["max_failed_attempts"]
		if locked:
			link.locked, link.lock_reason = True, TOO_MANY_ATTEMPTS
		session.commit()  # the count must survive the error answer below
		if locked:
			raise LinkInvalid(_("This link is invalid or has expired"))
		raise WrongSecret(_("The information entered is not correct"))
	content = files.read(session.get(StoredFile, payslip.file_id))
	jdate, clock = now_jalali()
	marked = watermark_pdf(
		content,
		employee.full_name,
		employee.code,
		f"{jdate} - {clock[:5]}",
		translate(_("Confidential"), DEFAULT_LANGUAGE),
	)
	link.view_count += 1
	link.failed_attempts = 0
	session.add(PayslipView(link_id=link.id, ip=(ip or "")[:64] or None))
	return marked, f"payslip-{payslip.jyear}-{payslip.jmonth:02d}.pdf"
