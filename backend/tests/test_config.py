"""Settings: the CHRONICLE_ variables, and the HOZUR_ ones of installations from before 0.3.0."""

from __future__ import annotations

from chronicle import config


def test_old_hozur_variables_are_still_read(monkeypatch):
	monkeypatch.setenv("HOZUR_TIMEZONE", "Asia/Kabul")
	monkeypatch.delenv("CHRONICLE_TIMEZONE", raising=False)
	config.get_settings.cache_clear()
	try:
		assert config.get_settings().timezone == "Asia/Kabul"
	finally:
		monkeypatch.delenv("CHRONICLE_TIMEZONE", raising=False)
		config.get_settings.cache_clear()


def test_the_new_name_wins(monkeypatch):
	monkeypatch.setenv("HOZUR_TIMEZONE", "Asia/Kabul")
	monkeypatch.setenv("CHRONICLE_TIMEZONE", "Asia/Tehran")
	config.get_settings.cache_clear()
	try:
		assert config.get_settings().timezone == "Asia/Tehran"
	finally:
		config.get_settings.cache_clear()
