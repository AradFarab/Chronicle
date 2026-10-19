"""Keep the panel's secrets out of the message history."""

from __future__ import annotations

from typing import Any

MASK = "••••••••"


def mask_text(value: Any, secrets: list[str]) -> Any:
	"""Replace every known secret inside a request or answer (any JSON shape) by a mask."""
	known = [s for s in secrets if s and len(s) >= 4]
	if isinstance(value, str):
		for secret in known:
			value = value.replace(secret, MASK)
		return value
	if isinstance(value, dict):
		return {k: mask_text(v, known) for k, v in value.items()}
	if isinstance(value, list):
		return [mask_text(v, known) for v in value]
	return value
