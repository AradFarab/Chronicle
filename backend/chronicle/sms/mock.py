"""A driver that sends nothing: for development, the test button and the tests. Its `behavior`
setting makes the next sends succeed or fail in a chosen way."""

from __future__ import annotations

from typing import Any, ClassVar

from chronicle.sms.base import (
	BULK,
	NAMED,
	PATTERN,
	AmbiguousResult,
	Health,
	ProviderError,
	SendResult,
	SmsDriver,
	_,
	register,
)


@register
class MockDriver(SmsDriver):
	code = "mock"
	label = "آزمایشی (mock)"
	config_schema: ClassVar[dict[str, dict[str, Any]]] = {
		"behavior": {
			"type": "string",
			"label": _("Behavior: ok, retryable, fatal or timeout"),
			"required": False,
		},
	}
	capabilities = frozenset({BULK, PATTERN})
	pattern_schema: ClassVar[dict[str, Any]] = {
		"requires_line_number": False,
		"param_style": NAMED,
		"max_params": 10,
	}
	sent: ClassVar[list[dict[str, Any]]] = []  # what a test can look at

	def test_connection(self) -> Health:
		return Health(True, "", 1000.0)

	def get_credit(self) -> float | None:
		return 1000.0

	def _go(self, request: dict[str, Any]) -> SendResult:
		behavior = (self.config.get("behavior") or "ok").strip()
		if behavior == "retryable":
			raise ProviderError(_("The mock panel is busy"), retryable=True, raw={"status": 503})
		if behavior == "fatal":
			raise ProviderError(_("The mock panel refused the request"), retryable=False, raw={"status": 400})
		if behavior == "timeout":
			raise AmbiguousResult(_("The mock panel did not answer in time"))
		self.sent.append(request)
		return SendResult(
			provider_message_id=f"mock-{len(self.sent)}",
			cost=1.0,
			raw_request=request,
			raw_response={"ok": True},
		)

	def send_bulk(self, to: str, text: str, line_number: str | None = None) -> SendResult:
		return self._go({"to": to, "text": text, "line_number": line_number})

	def send_pattern(
		self, to: str, pattern_code: str, params: dict[str, str] | list[str], line_number: str | None = None
	) -> SendResult:
		return self._go({"to": to, "pattern": pattern_code, "params": self.prepare_params(params)})
