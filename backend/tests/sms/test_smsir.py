"""The sms.ir gateway against a mock server: the request it makes and the answers it handles."""

from __future__ import annotations

import json

import httpx
import pytest

from chronicle.sms.base import SmsConfig, SmsError, SmsMessage
from chronicle.sms.smsir import SmsIrGateway


def gateway(handler, line="30007732") -> SmsIrGateway:
	client = httpx.Client(transport=httpx.MockTransport(handler))
	return SmsIrGateway(SmsConfig(api_key="secret-key", line_number=line), client=client)


def test_send_posts_one_text_per_recipient_with_the_api_key():
	seen = {}

	def handler(request: httpx.Request) -> httpx.Response:
		seen["url"], seen["key"] = str(request.url), request.headers["x-api-key"]
		seen["body"] = json.loads(request.content)
		data = {"messageIds": [11, 12], "cost": 2}
		return httpx.Response(200, json={"status": 1, "message": "ok", "data": data})

	results = gateway(handler).send([SmsMessage("09121111111", "a"), SmsMessage("09122222222", "b")])
	assert seen["url"] == "https://api.sms.ir/v1/send/likeToLike"
	assert seen["key"] == "secret-key"
	assert seen["body"]["lineNumber"] == 30007732
	assert seen["body"]["mobiles"] == ["09121111111", "09122222222"]
	assert seen["body"]["messageTexts"] == ["a", "b"]
	assert [(r.mobile, r.ok, r.provider_id) for r in results] == [
		("09121111111", True, "11"),
		("09122222222", True, "12"),
	]


def test_a_refused_key_is_an_error():
	with pytest.raises(SmsError) as error:
		gateway(lambda r: httpx.Response(401, json={"message": "no"})).send([SmsMessage("09121111111", "a")])
	assert "key" in str(error.value)


def test_a_status_other_than_one_is_an_error_with_the_providers_words():
	def handler(request):
		return httpx.Response(200, json={"status": 105, "message": "not enough credit"})

	with pytest.raises(SmsError) as error:
		gateway(handler).send([SmsMessage("09121111111", "a")])
	assert "not enough credit" in str(error.value)


def test_a_network_failure_is_an_error():
	def handler(request):
		raise httpx.ConnectError("down")

	with pytest.raises(SmsError):
		gateway(handler).send([SmsMessage("09121111111", "a")])


def test_one_request_carries_at_most_a_batch():
	too_many = [SmsMessage("09121111111", "a")] * (SmsIrGateway.batch_size + 1)
	with pytest.raises(SmsError):
		gateway(lambda r: httpx.Response(200, json={"status": 1})).send(too_many)


def test_the_line_number_must_be_a_number():
	broken = gateway(lambda r: httpx.Response(200, json={"status": 1}), line="abc")
	with pytest.raises(SmsError):
		broken.send([SmsMessage("09121111111", "a")])


def test_health_reports_the_credit():
	health = gateway(lambda r: httpx.Response(200, json={"status": 1, "data": 12500})).health()
	assert health.ok and health.credit == 12500
