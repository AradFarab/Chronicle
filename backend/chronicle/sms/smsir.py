"""sms.ir (api.sms.ir, version 1): `send/bulk` for a full text and `send/verify` for a pattern.

Pattern variables are **named**: the panel replaces a variable only when the name is exactly the
one in the approved text (case-sensitive, without the surrounding ``#``). For a name it does not
know it gives no error and sends the text with ``#NAME#`` left in it, so the template check and
reading the message that arrives are the only protection. The pattern code is a number."""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from chronicle.sms.base import (
	BULK,
	NAMED,
	PATTERN,
	AmbiguousResult,
	ConfigurationError,
	Health,
	ProviderError,
	SendResult,
	SmsDriver,
	_,
	register,
)

BASE_URL = "https://api.sms.ir/v1"
RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}
OK_STATUS = 1


@register
class SmsIrDriver(SmsDriver):
	code = "smsir"
	label = "sms.ir"
	config_schema: ClassVar[dict[str, dict[str, Any]]] = {
		"api_key": {"type": "secret", "label": _("API key"), "required": True},
		"sender": {"type": "string", "label": _("Sender line number"), "required": False},
	}
	capabilities = frozenset({BULK, PATTERN})
	pattern_schema: ClassVar[dict[str, Any]] = {
		"requires_line_number": False,
		"param_style": NAMED,
		"max_params": 10,
	}

	def __init__(self, config: dict[str, Any], client: httpx.Client | None = None):
		super().__init__(config)
		self._client = client  # tests pass one with a mock transport

	def validate_pattern_code(self, code: str) -> str | None:
		return None if str(code).strip().isdigit() else _("The sms.ir pattern code must be a number")

	def _call(self, method: str, path: str, body: dict | None = None) -> tuple[dict, Any]:
		"""(the request as kept in the history, the decoded answer)."""
		self.validate_config()
		base = (self.config.get("base_url") or BASE_URL).rstrip("/")
		request = {"method": method, "url": f"{base}/{path}", "json": body}
		headers = {"X-API-KEY": str(self.config["api_key"]), "Accept": "application/json"}
		client = self._client or httpx.Client(timeout=20)
		try:
			response = client.request(method, request["url"], json=body, headers=headers)
		except (httpx.ConnectError, httpx.ConnectTimeout):
			raise ProviderError(_("Could not connect to sms.ir"), retryable=True) from None
		except httpx.HTTPError:
			# the request may have been delivered: do not send it again
			raise AmbiguousResult(_("sms.ir did not answer in time")) from None
		finally:
			if self._client is None:
				client.close()
		try:
			data = response.json()
		except ValueError:
			data = None
		raw = data if data is not None else response.text[:500]
		if response.status_code in (401, 403):
			raise ProviderError(_("sms.ir refused the API key"), retryable=False, raw=raw)
		message = str((data or {}).get("message") or "")[:300] if isinstance(data, dict) else ""
		if response.status_code in RETRYABLE_STATUS:
			raise ProviderError(
				_("sms.ir answered: {0}"), message or response.status_code, retryable=True, raw=raw
			)
		if response.status_code >= 400 or not isinstance(data, dict) or data.get("status") != OK_STATUS:
			raise ProviderError(
				_("sms.ir answered: {0}"), message or response.status_code, retryable=False, raw=raw
			)
		return request, data

	def _result(self, request: dict, data: dict) -> SendResult:
		info = data.get("data") or {}
		message_id = info.get("messageId")
		cost = info.get("cost")
		return SendResult(
			provider_message_id=str(message_id) if message_id is not None else None,
			cost=float(cost) if isinstance(cost, int | float) else None,
			raw_request=request,
			raw_response=data,
		)

	def _line(self, line_number: str | None) -> int:
		value = str(line_number or self.config.get("sender") or "").strip()
		if not value.isdigit():
			raise ConfigurationError(_("The sender line number must be a number"))
		return int(value)

	def send_bulk(self, to: str, text: str, line_number: str | None = None) -> SendResult:
		body = {"lineNumber": self._line(line_number), "messageText": text, "mobiles": [to]}
		request, data = self._call("POST", "send/bulk", body)
		return self._result(request, data)

	def send_pattern(
		self, to: str, pattern_code: str, params: dict[str, str] | list[str], line_number: str | None = None
	) -> SendResult:
		if not isinstance(params, dict):
			raise ConfigurationError(_("sms.ir patterns need named variables"))
		body = {
			"mobile": to,
			"templateId": int(str(pattern_code).strip()),
			"parameters": [{"name": k, "value": v} for k, v in self.prepare_params(params).items()],
		}
		request, data = self._call("POST", "send/verify", body)
		return self._result(request, data)

	def get_credit(self) -> float | None:
		_request, data = self._call("GET", "credit")
		credit = data.get("data")
		return float(credit) if isinstance(credit, int | float) else None

	def test_connection(self) -> Health:
		return Health(True, "", self.get_credit())
