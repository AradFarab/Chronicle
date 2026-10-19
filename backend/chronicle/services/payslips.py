"""Payslips (فیش حقوقی): store the pages of the finance software's PDF, send each employee a
private link by SMS, and serve the page to its owner after a second factor.

The app never computes pay. A payslip is one PDF page per employee and Jalali month, found by
the personnel code printed on it. The link is a random token (only its SHA-256 is stored), limited
in time and views, and the page opens only with the last four digits of the employee's national
id. The SMS itself is the SMS module's (services/sms_dispatch.py): the link goes out as a short
``l/<code>`` path inside the admin's approved pattern. The national id printed on the page must be
the employee's, or no link is made: nobody's slip may reach somebody else. Every file served
carries the viewer's name and the time as a watermark.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import re
import secrets
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
	SmsMessage,
	StoredFile,
)
from chronicle.db.models.org import ACTIVE, LEFT
from chronicle.db.models.payslips import MATCH, MISMATCH, TOO_MANY_ATTEMPTS, UNKNOWN, VOIDED
from chronicle.db.models.sms import DELIVERED, FAILED, QUEUED, SENDING, SENT, SKIPPED
from chronicle.db.models.sms import UNKNOWN as UNKNOWN_STATUS
from chronicle.i18n import DEFAULT_LANGUAGE, _, translate
from chronicle.jalali.dates import MONTH_NAMES, from_gregorian, to_ascii_digits
from chronicle.payslips import pdf
from chronicle.payslips.watermark import watermark_pdf
from chronicle.services import audit, files, settings, sms_dispatch
from chronicle.services.access import Actor, require_admin
from chronicle.services.errors import ChronicleError, NotFound, ValidationError

SETTING = "payslips"
DEFAULTS: dict[str, Any] = {"link_expiry_days": 14, "link_max_views": 5, "max_failed_attempts": 5}
LINK_PATH = "/p/"  # the PWA's public payslip page
MOBILE_RE = re.compile(r"^09\d{9}$")
IN_FLIGHT = (QUEUED, SENDING)
MODES = ("unsent", "all")  # who gets an SMS: people without a working link, or everyone ready


class LinkInvalid(NotFound):
	"""One answer for every reason a link does not work, so a guesser learns nothing."""


class WrongSecret(ChronicleError):
	status_code = 403


# settings ---------------------------------------------------------------------------------------


def get_settings(session: Session) -> dict[str, Any]:
	return {**DEFAULTS, **(settings.get(session, SETTING) or {})}


def save_settings(session: Session, actor: Actor, values: dict[str, Any]) -> dict[str, Any]:
	require_admin(actor)
	current = get_settings(session)
	new = dict(current)
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
	require_admin(actor)
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
	require_admin(actor)
	year, month = _period(jyear, jmonth)
	at = now()
	payslips = {
		p.employee_id: p
		for p in session.scalars(select(Payslip).where(Payslip.jyear == year, Payslip.jmonth == month))
	}
	links = _links_of(session, [p.id for p in payslips.values()])
	messages = _messages_of(session, links)
	rows = []
	for employee in session.scalars(select(Employee).order_by(Employee.code)):
		payslip = payslips.get(employee.id)
		if payslip is None and employee.status == LEFT:
			continue
		link = links.get(payslip.id) if payslip else None
		message = messages.get(link.sms_message_id) if link and link.sms_message_id else None
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
						"sms_message_id": link.sms_message_id,
						"sms_status": message.status if message else None,
						"sms_error": message.error if message else None,
						"sms_sent_at": message.sent_at if message else None,
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
			"sent": sum(1 for link in with_link if link["sms_status"] in (SENT, DELIVERED)),
			"pending": sum(1 for link in with_link if link["sms_status"] in IN_FLIGHT),
			"failed": sum(1 for link in with_link if link["sms_status"] in (FAILED, SKIPPED)),
			"unknown": sum(1 for link in with_link if link["sms_status"] == UNKNOWN_STATUS),
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
	require_admin(actor)
	row = _payslip(session, payslip_id)
	file_row = session.get(StoredFile, row.file_id)
	before = {"employee_id": row.employee_id, "jyear": row.jyear, "jmonth": row.jmonth}
	session.delete(row)
	session.flush()
	if file_row is not None:
		files.delete(session, file_row)
	audit.log(session, "payslip", payslip_id, "delete", actor.user_id, "deleted", before)


def clear_rejections(session: Session, actor: Actor, jyear: Any, jmonth: Any) -> None:
	require_admin(actor)
	year, month = _period(jyear, jmonth)
	for row in session.scalars(
		select(PayslipRejection).where(PayslipRejection.jyear == year, PayslipRejection.jmonth == month)
	):
		session.delete(row)


def void_link(session: Session, actor: Actor, link_id: int) -> None:
	"""Stop a link from working (it was sent to the wrong number, say)."""
	require_admin(actor)
	link = session.get(PayslipLink, link_id)
	if link is None:
		raise NotFound(_("Not found"))
	if not link.locked:
		link.locked, link.lock_reason = True, VOIDED
		audit.log(session, "payslip_link", link.id, "update", actor.user_id, "link voided")


def payslip_file(session: Session, actor: Actor, payslip_id: int) -> bytes:
	"""The stored page for the system admin to check (no watermark)."""
	require_admin(actor)
	row = _payslip(session, payslip_id)
	return files.read(session.get(StoredFile, row.file_id))


# sending ----------------------------------------------------------------------------------------

EVENT = "payslip_link"  # the SMS event (chronicle/sms/events.py): its template is made in the SMS section


def _expires_label(expires_at) -> str:
	return from_gregorian(expires_at.astimezone(now().tzinfo).date())


def _messages_of(session: Session, links: dict[int, PayslipLink]) -> dict[int, SmsMessage]:
	ids = [link.sms_message_id for link in links.values() if link.sms_message_id]
	if not ids:
		return {}
	return {m.id: m for m in session.scalars(select(SmsMessage).where(SmsMessage.id.in_(ids)))}


def _targets(
	session: Session, year: int, month: int, mode: str, payslip_ids: list[int] | None
) -> tuple[list[tuple[Payslip, Employee, PayslipLink | None]], list[dict[str, Any]]]:
	"""(ready to send, blocked) for the month. «unsent» takes everyone whose SMS has not gone out
	and is not on its way (no link yet, or the SMS failed or was skipped); a message whose outcome
	is unknown is left alone until the admin has checked the panel. «all» takes everyone who can
	be sent a link, replacing their link; only messages still on their way are left alone."""
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
	messages = _messages_of(session, links)
	ready, blocked = [], []
	for payslip, employee in pairs:
		link = links.get(payslip.id)
		active = link if link is not None and not link.locked else None
		status = (
			messages[active.sms_message_id].status if active and active.sms_message_id in messages else None
		)
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
		elif status in IN_FLIGHT:
			continue  # its SMS is already on its way
		elif mode == "all" or active is None or status in (FAILED, SKIPPED):
			ready.append((payslip, employee, active))
	return ready, blocked


def _context(employee: Employee, payslip: Payslip, expires_at, link: str) -> dict[str, str]:
	return {
		"name": employee.full_name,
		"month": month_label(payslip.jyear, payslip.jmonth),
		"expires": _expires_label(expires_at),
		"link": link,
	}


def preview(
	session: Session,
	actor: Actor,
	jyear: Any,
	jmonth: Any,
	mode: str = "unsent",
	payslip_ids: list[int] | None = None,
) -> dict[str, Any]:
	"""What sending would do, before anything is sent: how many, who is left out and why, and
	what the first message would send (the text, or the pattern code and parameters exactly as the
	panel gets them)."""
	require_admin(actor)
	year, month = _period(jyear, jmonth)
	cfg = get_settings(session)
	ready, blocked = _targets(session, year, month, mode, payslip_ids)
	sample = None
	if ready:
		payslip, employee, _old = ready[0]
		context = _context(employee, payslip, now() + timedelta(days=cfg["link_expiry_days"]), "")
		context["link_path"] = "l/xxxxxxxx"  # what dispatch makes of the link
		del context["link"]
		sample = sms_dispatch.preview_event(session, EVENT, context)
	problem_text = sms_dispatch.readiness(session, EVENT)
	messages = _messages_of(session, _links_of(session, [p.id for p, _e, _l in ready]))
	return {
		"count": len(ready),
		"replacing": sum(
			1
			for _p, _e, link in ready
			if link is not None
			and link.sms_message_id in messages
			and messages[link.sms_message_id].status in (SENT, DELIVERED)
		),
		"blocked": blocked,
		"sample": sample,
		"unavailable": translate(problem_text, actor.language) if problem_text else None,
	}


def queue_send(
	session: Session,
	actor: Actor,
	jyear: Any,
	jmonth: Any,
	mode: str = "unsent",
	payslip_ids: list[int] | None = None,
) -> dict[str, Any]:
	"""Make a fresh link for each person and dispatch its SMS (the worker sends it). A link that
	was sent before is voided: sending again replaces it."""
	require_admin(actor)
	year, month = _period(jyear, jmonth)
	problem_text = sms_dispatch.readiness(session, EVENT)
	if problem_text:
		raise ValidationError(problem_text)
	cfg = get_settings(session)
	ready, _blocked = _targets(session, year, month, mode, payslip_ids)
	if not ready:
		raise ValidationError(_("There is nobody to send to"))
	at = now()
	queued = 0
	for payslip, employee, old in ready:
		if old is not None:
			old.locked, old.lock_reason = True, VOIDED
			session.flush()  # only one active link per payslip may exist
		token = secrets.token_urlsafe(32)
		expires_at = at + timedelta(days=cfg["link_expiry_days"])
		link = PayslipLink(
			payslip_id=payslip.id,
			token_hash=_hash(token),
			expires_at=expires_at,
			max_views=cfg["link_max_views"],
			view_count=0,
			failed_attempts=0,
			locked=False,
			created_by_id=actor.user_id,
		)
		session.add(link)
		session.flush()
		message = sms_dispatch.dispatch(
			session,
			EVENT,
			employee.mobile,
			_context(employee, payslip, expires_at, f"{LINK_PATH}{token}"),
			entity_key=f"payslip_link:{link.id}",
		)
		link.sms_message_id = message.id
		queued += 1
		audit.log(
			session,
			"payslip_link",
			link.id,
			"insert",
			actor.user_id,
			"SMS queued",
			after={
				"payslip_id": payslip.id,
				"replaced": old.id if old else None,
				"sms_message_id": message.id,
			},
		)
	return {"queued": queued}


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
