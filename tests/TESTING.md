# Testing ZWO-to-iGPSPORT

The project uses Python's built-in `unittest`; no additional packages are needed.

Run from the repository root:

```bash
python -m unittest discover -s tests -v
```

The tests cover FTP scaling, fixed-power intervals, warm-up and cool-down ramps, reverse ramps, non-multiple ramp durations, FreeRide, several ZWO spelling variants, ignored annotations, errors for unsupported elements and invalid durations, and FIT container header/CRC correctness.

Fixture files are in `tests/fixtures/` and can also be converted manually:

```bash
python zwo_to_igpsport_fit.py tests/fixtures/lactate_low_1.zwo --ftp 200
```

These tests verify encoding and known examples, **not** physical BSC300 or trainer behaviour. After changing FIT layout or open-step handling, repeat a short BSC300 hardware test.

When a new Zwift ZWO file fails, add a minimal example (or a suitably licensed fixture) and regression test before extending the parser.
