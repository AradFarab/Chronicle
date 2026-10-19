"""The SMS drivers against a mock panel, and the pure helpers (numbers, parameters, masking)."""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from chronicle.services.sms_dispatch import next_send_time
from chronicle.sms.base import ZWNJ, AmbiguousResult, ConfigurationError, ProviderError, clean_param
from chronicle.sms.masking import MASK, mask_text
from chronicle.sms.mock import MockDriver
from chronicle.sms.numbers import normalize_number
from chronicle.sms.smsir import SmsIrDriver


def driver(handler, **config) -> SmsIrDriver:
	client = httpx.Client(transport=httpx.MockTransport(handler))
	return SmsIrDriver({"api_key": "secret-key", **config}, client=client)


def ok(data=None):
	return httpx.Response(
		200, json={"status": 1, "message": "ok", "data": data or {"messageId": 77, "cost": 1.5}}
	)


# sms.ir ----------------------------------------------------------------------------------------------


def test_a_pattern_is_sent_with_named_parameters_and_the_key():
	seen = {}

	def handler(request: httpx.Request) -> httpx.Response:
		seen["url"], seen["key"] = str(request.url), request.headers["x-api-key"]
		seen["body"] = json.loads(request.content)
		return ok()

	result = driver(handler).send_pattern(
		"09121234567", "123456", {"#NAME#": "علی رضایی", "LINK": "l/AbC12345"}
	)
	assert seen["url"] == "https://api.sms.ir/v1/send/verify" and seen["key"] == "secret-key"
	assert seen["body"] == {
		"mobile": "09121234567",
		"templateId": 123456,
		"parameters": [
			{"name": "NAME", "value": f"علی{ZWNJ}رضایی"},  # no plain space; the # is dropped
			{"name": "LINK", "value": "l/AbC12345"},
		],
	}
	assert (result.ok, result.provider_message_id, result.cost) == (True, "77", 1.5)
	assert result.raw_request["json"]["templateId"] == 123456 and result.raw_response["status"] == 1
	assert "secret-key" not in json.dumps(result.raw_request)  # the key is a header, not in the record


def test_a_full_text_goes_through_bulk_with_the_line_number():
	seen = {}

	def handler(request):
		seen["url"], seen["body"] = str(request.url), json.loads(request.content)
		return ok()

	driver(handler, sender="30007732").send_bulk("09121234567", "hello")
	assert seen["url"] == "https://api.sms.ir/v1/send/bulk"
	assert seen["body"] == {"lineNumber": 30007732, "messageText": "hello", "mobiles": ["09121234567"]}
	driver(handler).send_bulk("09121234567", "hello", line_number="3000")
	assert seen["body"]["lineNumber"] == 3000  # the template's own line wins over none


def test_bulk_needs_a_numeric_line():
	with pytest.raises(ConfigurationError):
		driver(lambda r: ok()).send_bulk("09121234567", "hello")


@pytest.mark.parametrize("status", [408, 425, 429, 500, 502, 503, 504])
def test_these_answers_are_worth_trying_again(status):
	with pytest.raises(ProviderError) as e:
		driver(lambda r: httpx.Response(status, json={"message": "busy"})).send_pattern(
			"0912", "1", {"A": "b"}
		)
	assert e.value.retryable and e.value.raw == {"message": "busy"}


def test_a_revoked_key_or_a_refusal_is_final():
	for response in (
		httpx.Response(401, json={"message": "no"}),
		httpx.Response(400, json={"status": 105, "message": "bad parameter"}),
		httpx.Response(200, json={"status": 105, "message": "no credit"}),
		httpx.Response(200, text="not json"),
	):
		with pytest.raises(ProviderError) as e:
			driver(lambda r, response=response: response).send_pattern("0912", "1", {"A": "b"})
		assert not e.value.retryable


def test_not_connecting_is_retryable_but_a_lost_answer_is_unknown():
	def cannot_connect(request):
		raise httpx.ConnectError("down")

	def times_out(request):
		raise httpx.ReadTimeout("slow")

	with pytest.raises(ProviderError) as e:
		driver(cannot_connect).send_pattern("0912", "1", {"A": "b"})
	assert e.value.retryable  # nothing reached the panel
	with pytest.raises(AmbiguousResult):  # it may have been sent: never retry
		driver(times_out).send_pattern("0912", "1", {"A": "b"})


def test_an_empty_key_is_found_before_any_network_call():
	def never(request):
		raise AssertionError("no request should be made")

	with pytest.raises(ConfigurationError):
		SmsIrDriver(
			{"api_key": " "}, client=httpx.Client(transport=httpx.MockTransport(never))
		).validate_config()


def test_the_pattern_code_is_a_number_and_credit_is_read():
	assert driver(lambda r: ok()).validate_pattern_code("123") is None
	assert driver(lambda r: ok()).validate_pattern_code("abc")
	health = driver(lambda r: httpx.Response(200, json={"status": 1, "data": 12500})).test_connection()
	assert health.ok and health.credit == 12500


def test_sms_ir_cannot_take_positional_parameters():
	with pytest.raises(ConfigurationError):
		driver(lambda r: ok()).send_pattern("0912", "1", ["a", "b"])


# the mock ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
	("behavior", "error"),
	[("retryable", ProviderError), ("fatal", ProviderError), ("timeout", AmbiguousResult)],
)
def test_the_mock_fails_the_way_it_is_told(behavior, error):
	with pytest.raises(error):
		MockDriver({"behavior": behavior}).send_bulk("0912", "x")


# numbers, parameters, masking ---------------------------------------------------------------------------


@pytest.mark.parametrize(
	"value",
	["09121234567", "+98 912 123 4567", "00989121234567", "989121234567", "9121234567", "۰۹۱۲۱۲۳۴۵۶۷"],
)
def test_every_way_of_writing_a_mobile_number_gives_one_form(value):
	assert normalize_number(value) == "09121234567"


@pytest.mark.parametrize("value", ["", None, "0212345", "09121", "abc", "0912123456789"])
def test_what_is_not_a_mobile_number_is_refused(value):
	assert normalize_number(value) is None


def test_whitespace_in_a_parameter_becomes_a_half_space():
	assert clean_param("دکتر  پونه\tیزدانی") == f"دکتر{ZWNJ}پونه{ZWNJ}یزدانی"
	assert clean_param(15) == "15" and clean_param(None) == ""


def test_secrets_are_masked_wherever_they_appear():
	data = {"url": "https://x/?key=abc12345", "list": ["abc12345", {"k": "v abc12345"}], "n": 3}
	masked = mask_text(data, ["abc12345", "", "xy"])
	dumped = json.dumps(masked, ensure_ascii=False)
	assert "abc12345" not in dumped and MASK in dumped and masked["n"] == 3


# the send window --------------------------------------------------------------------------------------


TEHRAN = ZoneInfo("Asia/Tehran")
WINDOW = {"window_enabled": True, "window_start_hour": 9, "window_end_hour": 21}


def at(hour, minute=0, day=19):
	return datetime(2026, 10, day, hour, minute, tzinfo=TEHRAN)


def test_a_message_inside_the_window_goes_at_once():
	assert next_send_time(at(9), WINDOW) == at(9)
	assert next_send_time(at(20, 59), WINDOW) == at(20, 59)


def test_a_message_outside_the_window_waits_for_the_next_opening():
	assert next_send_time(at(21), WINDOW) == at(9, day=20)  # evening: tomorrow morning
	assert next_send_time(at(23, 30), WINDOW) == at(9, day=20)
	assert next_send_time(at(3), WINDOW) == at(9)  # night: this morning


def test_a_one_time_code_or_a_switched_off_window_never_waits():
	assert next_send_time(at(23), WINDOW, bypass=True) == at(23)
	assert next_send_time(at(23), {**WINDOW, "window_enabled": False}) == at(23)
