"""Errors the API turns into translated messages. Messages are English templates with
{0}-style parameters (marked with _()), translated for the user at the edge."""

from __future__ import annotations

from hozur.i18n import translate


class Message:
	"""A translatable message that is not an error (warnings, notices)."""

	def __init__(self, template: str, *params: object):
		self.template, self.params = template, params

	def translated(self, language: str) -> str:
		return translate(self.template, language).format(*self.params)

	def __str__(self) -> str:
		return self.template.format(*self.params)


class HozurError(Exception):
	status_code = 400

	def __init__(self, message: str, *params: object):
		super().__init__(message.format(*params) if params else message)
		self.template = message
		self.params = params

	def translated(self, language: str) -> str:
		return translate(self.template, language).format(*self.params)


class ValidationError(HozurError):
	status_code = 422


class NotFound(HozurError):
	status_code = 404


class PermissionDenied(HozurError):
	status_code = 403


class Conflict(HozurError):
	status_code = 409
