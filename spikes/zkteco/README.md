# Spike: read the ZKTeco device (phase 0, item 1)

Goal: prove we can read users and logs from the company's ZKTeco (likely VF600) over
TCP 4370 with `pyzk`, and turn each raw device timestamp into a Jalali day + time.

The script is **read-only**: the pyzk connection is wrapped so only read commands can be
sent. It never clears the device log, never changes users, never sets the clock.

## Run (on a machine inside the company network)

```bash
python3 -m venv .venv-spike
.venv-spike/bin/pip install -r spikes/zkteco/requirements.txt

# basic read: device info, users, last 20 punches
.venv-spike/bin/python spikes/zkteco/read_device.py --ip <DEVICE_IP>

# with comm key, only this month, and save samples for test fixtures
.venv-spike/bin/python spikes/zkteco/read_device.py --ip <DEVICE_IP> --password <COMM_KEY> \
    --since 1405/07/01 --csv punches.csv --users-csv users.csv
```

`*.csv` files hold employee names and punch times: keep them local, do not commit them
(they are git-ignored).

## Troubleshooting

| Symptom | Try |
| --- | --- |
| `can't reach device (ping ...)` | `--no-ping` (ICMP is often blocked) |
| timeout / `Can't connect` | Paliz may be polling at that moment: retry; or `--udp` for older firmware |
| `Unauthenticated` | the device has a comm key: `--password <key>` (Menu → Comm. → Comm Key) |
| empty / partial log | `--disable-device` locks the screen during the read (people cannot punch for those seconds) |

## Pass criteria

- [ ] device model, serial and firmware printed
- [ ] user list matches the people enrolled on the device
- [ ] latest punches match what the device / Paliz shows, with the correct Jalali day
- [ ] clock drift vs. a correct clock noted (Iran has no DST since 1401; check the device has DST off)
- [ ] `verify_type` / `punch_state` values noted (face, finger, card; in/out if used)
