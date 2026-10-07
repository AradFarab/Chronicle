#!/usr/bin/env python3
"""Phase-0 spike: read users and attendance logs from a ZKTeco device (pyzk).

Prints device info, the user list and the latest punches with the Jalali day and
time derived from the raw device timestamp. Read-only: the connection is wrapped so
that only read commands can be sent; the device log is never cleared.

    python spikes/zkteco/read_device.py --ip 192.168.1.201
    python spikes/zkteco/read_device.py --ip 192.168.1.201 --password 1234 --since 1405/07/01 --csv punches.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime

import jdatetime
from zk import ZK

# Only these pyzk methods may be called. Anything that writes to the device
# (clear_attendance, clear_data, set_user, delete_user, set_time, restart, ...)
# raises instead of reaching the device.
READ_ONLY_METHODS = frozenset(
	{
		"disconnect",
		"disable_device",
		"enable_device",
		"get_firmware_version",
		"get_serialnumber",
		"get_platform",
		"get_device_name",
		"get_mac",
		"get_face_version",
		"get_fp_version",
		"get_network_params",
		"get_time",
		"read_sizes",
		"get_users",
		"get_attendance",
	}
)


class ReadOnlyConnection:
	def __init__(self, conn):
		self._conn = conn

	def __getattr__(self, name):
		value = getattr(self._conn, name)
		if callable(value) and name not in READ_ONLY_METHODS:
			raise PermissionError(f"spike is read-only; refusing to call {name}()")
		return value


def to_jalali(ts: datetime) -> tuple[str, str]:
	"""Device wall-clock datetime -> ('1405/07/14', '08:02:11'), ASCII digits."""
	j = jdatetime.datetime.fromgregorian(datetime=ts)
	return j.strftime("%Y/%m/%d"), j.strftime("%H:%M:%S")


def parse_args() -> argparse.Namespace:
	p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	p.add_argument("--ip", required=True, help="device IP address")
	p.add_argument("--port", type=int, default=4370)
	p.add_argument("--password", type=int, default=0, help="device comm key (default 0)")
	p.add_argument("--timeout", type=int, default=10, help="socket timeout in seconds")
	p.add_argument("--udp", action="store_true", help="force UDP (older firmware)")
	p.add_argument("--no-ping", action="store_true", help="skip ICMP ping before connecting")
	p.add_argument(
		"--disable-device",
		action="store_true",
		help="lock the device screen while reading (consistent read, but nobody can punch meanwhile)",
	)
	p.add_argument("--since", help="only show punches on/after this Jalali day, e.g. 1405/07/01")
	p.add_argument("--last", type=int, default=20, help="how many punches to print (default 20)")
	p.add_argument("--csv", help="write all (filtered) punches to this CSV file")
	p.add_argument("--users-csv", help="write the device user list to this CSV file")
	return p.parse_args()


def main() -> int:
	args = parse_args()
	zk = ZK(
		args.ip,
		port=args.port,
		timeout=args.timeout,
		password=args.password,
		force_udp=args.udp,
		ommit_ping=args.no_ping,
	)

	print(f"Connecting to {args.ip}:{args.port} ({'UDP' if args.udp else 'TCP'}) ...")
	conn = ReadOnlyConnection(zk.connect())
	try:
		if args.disable_device:
			conn.disable_device()

		server_now = datetime.now()
		device_now = conn.get_time()
		drift = (device_now - server_now).total_seconds()

		conn.read_sizes()
		print("\n== Device")
		print(f"  name / platform : {conn.get_device_name()} / {conn.get_platform()}")
		print(f"  serial number   : {conn.get_serialnumber()}")
		print(f"  firmware        : {conn.get_firmware_version()}")
		print(f"  MAC             : {conn.get_mac()}")
		print(f"  users           : {conn.users} / {conn.users_cap}")
		print(f"  fingerprints    : {conn.fingers} / {conn.fingers_cap}")
		print(f"  faces           : {getattr(conn, 'faces', '?')} / {getattr(conn, 'faces_cap', '?')}")
		print(f"  log records     : {conn.records} / {conn.rec_cap}")
		jd, jt = to_jalali(device_now)
		print(f"  device clock    : {device_now:%Y-%m-%d %H:%M:%S}  (Jalali {jd} {jt})")
		print(f"  drift vs. this machine: {drift:+.0f} s")

		users = conn.get_users()
		print(f"\n== Users ({len(users)})")
		print(f"  {'uid':>5}  {'user_id':<10} {'priv':>4}  {'card':>10}  name")
		for u in users:
			print(f"  {u.uid:>5}  {u.user_id:<10} {u.privilege:>4}  {u.card:>10}  {u.name}")

		punches = conn.get_attendance()
	finally:
		if args.disable_device:
			conn.enable_device()
		conn.disconnect()

	names = {u.user_id: u.name for u in users}
	rows = []
	for a in sorted(punches, key=lambda a: a.timestamp):
		jday, jtime = to_jalali(a.timestamp)
		if args.since and jday < args.since:
			continue
		rows.append(
			{
				"device_timestamp": a.timestamp.isoformat(sep=" "),
				"jalali_day": jday,
				"time": jtime,
				"user_id": a.user_id,
				"name": names.get(a.user_id, ""),
				"verify_type": a.status,
				"punch_state": a.punch,
			}
		)

	print(
		f"\n== Punches: {len(punches)} on device, {len(rows)} after filter; last {min(args.last, len(rows))}"
	)
	print(
		f"  {'device timestamp':<19}  {'jalali day':<10}  {'time':<8}  {'user_id':<10} {'verify':>6} {'state':>5}  name"
	)
	for r in rows[-args.last :]:
		print(
			f"  {r['device_timestamp']:<19}  {r['jalali_day']:<10}  {r['time']:<8}  {r['user_id']:<10}"
			f" {r['verify_type']:>6} {r['punch_state']:>5}  {r['name']}"
		)

	unknown = sorted({r["user_id"] for r in rows} - set(names))
	if unknown:
		print(f"\n  punches from user_ids not in the device user list: {', '.join(unknown)}")

	if args.csv:
		with open(args.csv, "w", newline="", encoding="utf-8") as f:  # nosemgrep
			w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["device_timestamp"])
			w.writeheader()
			w.writerows(rows)
		print(f"\nWrote {len(rows)} punches to {args.csv}")

	if args.users_csv:
		with open(args.users_csv, "w", newline="", encoding="utf-8") as f:  # nosemgrep
			w = csv.writer(f)
			w.writerow(["uid", "user_id", "name", "privilege", "card"])
			for u in users:
				w.writerow([u.uid, u.user_id, u.name, u.privilege, u.card])
		print(f"Wrote {len(users)} users to {args.users_csv}")

	return 0


if __name__ == "__main__":
	sys.exit(main())
