"""sms.ir (api.sms.ir, version 1): one text per recipient with `likeToLike`, the key in the
`X-API-KEY` header.

Note: the request and response shapes below follow sms.ir's public SDKs
(lineNumber, messageTexts, mobiles, sendDateTime; answer {status, message, data{packId,
messageIds, cost}}). They were not run against a live account when this was written: the first
thing to do with a real key is "Test connection" and one real message in the PWA. The address
can be changed with the option ``base_url`` should sms.ir move it.
"""

from __future__ import annotations

import httpx

from chronicle.sms.base import (
	SmsConfig,
	SmsError,
	SmsGateway,
	SmsHealth,
	SmsMessage,
	SmsResult,
	_,
	register,
)

BASE_URL = "https://api.sms.ir"
OK_STATUS = 1


def _error_text(response: httpx.Response) -> str:
	try:
		data = response.json()
		return str(data.get("message") or "")[:300]
	except Exception:
		return ""


@register
class SmsIrGateway(SmsGateway):
	code = "smsir"
	label = "sms.ir"
	batch_size = 100

	def __init__(self, config: SmsConfig, client: httpx.Client | None = None):
		super().__init__(config)
		self._client = client  # tests pass one with a mock transport

	def _request(self, method: str, path: str, body: dict | None = None) -> dict:
		base = (self.config.options.get("base_url") or BASE_URL).rstrip("/")
		headers = {"X-API-KEY": self.config.api_key, "Accept": "application/json"}
		client = self._client or httpx.Client(timeout=self.config.timeout)
		try:
			response = client.request(method, f"{base}{path}", json=body, headers=headers)
		except httpx.HTTPError as e:
			raise SmsError(_("Could not reach sms.ir: {0}"), type(e).__name__) from None
		finally:
			if self._client is None:
				client.close()
		if response.status_code in (401, 403):
			raise SmsError(_("sms.ir refused the API key"))
		try:
			data = response.json()
		except ValueError:
			data = {}
		if response.status_code >= 400 or data.get("status") != OK_STATUS:
			detail = _error_text(response) or str(response.status_code)
			raise SmsError(_("sms.ir answered: {0}"), detail)
		return data

	def send(self, messages: list[SmsMessage]) -> list[SmsResult]:
		if not messages:
			return []
		if len(messages) > self.batch_size:
			raise SmsError(_("At most {0} messages can be sent in one request"), self.batch_size)
		try:
			line = int(self.config.line_number)
		except ValueError:
			raise SmsError(_("The sender line number must be a number")) from None
		data = self._request(
			"POST",
			"/v1/send/likeToLike",
			{
				"lineNumber": line,
				"messageTexts": [m.text for m in messages],
				"mobiles": [m.mobile for m in messages],
				"sendDateTime": None,
			},
		)
		ids = (data.get("data") or {}).get("messageIds") or []
		same = len(ids) == len(messages)
		return [
			SmsResult(m.mobile, True, str(ids[i]) if same and ids[i] is not None else None)
			for i, m in enumerate(messages)
		]

	def health(self) -> SmsHealth:
		data = self._request("GET", "/v1/credit")
		credit = data.get("data")
		return SmsHealth(True, "", float(credit) if isinstance(credit, int | float) else None)
