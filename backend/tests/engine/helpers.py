"""Shared helpers for engine tests."""

from chronicle.engine.model import Day, Punch, Shift


def hm(value: str) -> int:
	"""'08:30' -> minutes."""
	h, m = value.split(":")
	return int(h) * 60 + int(m)


def punches(*times: str, directions: str | None = None) -> list[Punch]:
	"""punches('08:00', '16:00:30') -> seconds; a leading '+' means the next day."""
	out = []
	for i, t in enumerate(times):
		day = 86400 if t.startswith("+") else 0
		parts = [int(x) for x in t.lstrip("+").split(":")]
		seconds = parts[0] * 3600 + parts[1] * 60 + (parts[2] if len(parts) > 2 else 0)
		direction = {"I": "in", "O": "out"}.get(directions[i], "unknown") if directions else "unknown"
		out.append(Punch(day + seconds, direction))
	return out


def workday(jdate="1405/07/14", weekday=3, **kw):
	return Day(jdate=jdate, weekday=weekday, day_type=kw.pop("day_type", "workday"), **kw)


# 08:00-16:30 with a 12:30-13:10 break: 7 h 50 min of work, 5 minutes grace
OFFICE = Shift(
	"Office",
	start=hm("08:00"),
	end=hm("16:30"),
	breaks=((hm("12:30"), hm("13:10")),),
	grace_late=5,
	grace_early=5,
)
# no break: 08:00-15:20 = 440 minutes (7 h 20 min)
SHORT = Shift("Short", start=hm("08:00"), end=hm("15:20"))
