# ZWO to iGPSPORT FIT

A small, standalone command-line tool for converting **Zwift `.zwo` cycling workouts** into **iGPSPORT-style `.fit` workouts**, intended for devices such as the **iGPSPORT BSC300**.

Zwift workouts normally express power as a fraction of FTP. This converter uses your FTP to write **absolute watt targets** into the FIT file. It also approximates progressive ramps with a sequence of short, fixed-power steps.

The FIT structure was based on a workout exported from iGPSPORT, because a generic, standards-compliant FIT workout is not necessarily interpreted correctly by every head unit.

This is an independent project: **Wattzap and the FTMS-to-ANT+ bridge are not required to convert workout files**.

## Requirements

- Python **3.10 or newer** (Python 3.12 tested)
- No third-party Python packages
- A cycling workout in Zwift `.zwo` format
- Your FTP, in watts

## Usage

Put `zwo_to_igpsport_fit_v2.py` somewhere convenient and run:

```bash
python zwo_to_igpsport_fit_v2.py workout.zwo --ftp 200
```

The converter writes `workout.fit` next to `workout.zwo` and prints a summary of the converted steps.

Choose a different filename with `--output` (or `-o`):

```bash
python zwo_to_igpsport_fit_v2.py workout.zwo --ftp 240 --output my_workout.fit
```

Control the length of the fixed-power steps used to approximate ramps:

```bash
python zwo_to_igpsport_fit_v2.py workout.zwo --ftp 200 --ramp-step 15
```

The default ramp interval is **30 seconds**. Shorter intervals more closely approximate the original curve, but create more workout steps and more frequent trainer target changes.

For full command-line help:

```bash
python zwo_to_igpsport_fit_v2.py --help
```

### Options

| Option | Description |
| --- | --- |
| `zwo` | Input `.zwo` workout file (required) |
| `--ftp WATTS` | FTP used to convert relative power to watts (required) |
| `--ramp-step SECONDS` | Duration of each ramp segment; default `30` |
| `--output FILE`, `-o FILE` | Destination `.fit` filename; defaults to input filename with `.fit` extension |

Both FTP and ramp-step must be positive. Power calculated from a ZWO step must be between 0 and 1000 W, or the converter exits with an error.

## How power conversion works

A ZWO target of `Power="0.80"` means 80% of FTP. With FTP = 200 W, the converter writes an absolute **160 W** target.

For instance:

```xml
<SteadyState Duration="600" Power="0.80" />
```

becomes a 10-minute step targeting 160 W.

A five-minute ramp from 50% to 75% FTP becomes ten 30-second steps with gradually increasing watt targets. The ramp is **approximated**, rather than preserved as a native ramp instruction, because the iGPSPORT workout structure examined does not provide an established ramp mechanism.

The converter uses the **FTP supplied when converting**. If your FTP changes, regenerate the FIT file to update the targets.

## Supported ZWO workout elements

| ZWO element | FIT conversion |
| --- | --- |
| `Warmup` | Increasing or specified power ramp divided into short steps |
| `Cooldown` | Descending power ramp divided into short steps |
| `Ramp` | Ramp divided into short steps; respects the supplied endpoints |
| `SteadyState`, `SolidState` | Constant watt target |
| `IntervalsT` | Repeated work and recovery steps |
| `FreeRide`, `Freeride` | Timed step without a prescribed power target |
| `MaxEffort` | Timed step without a prescribed power target |
| `textevent`, `TextEvent`, `TextNotification`, `gameplayevent` | Ignored as workout annotations, not timed steps |

Unsupported workout elements raise an error rather than being silently skipped. `RestDay` is explicitly rejected because it is not a timed cycling workout step.

**Not everything in a ZWO file is transferred.** Coaching text, cadence instructions, and advanced workout metadata are not represented in the generated FIT workout. In particular, `IntervalsT` is expanded into individual steps, and warm-up/cool-down ramps can substantially increase the step count.

## Loading and testing

1. Generate a `.fit` file using the converter.
2. Transfer it to the BSC300 using the workout import or transfer method you normally use with iGPSPORT.
3. Confirm that the workout appears with the expected number and durations of steps.

**Compatibility status:** the generated file structure is modelled on an iGPSPORT export, and a converted ramp has been reported to work well on a BSC300 with a Van Rysel D100 trainer. This is not a guarantee of compatibility with all iGPSPORT models, firmware versions, or every ZWO workout. Long workouts with large numbers of steps have not been comprehensively tested.

## Limitations

- **Cycling only:** `sportType` must be `bike` (or omitted).
- **Absolute power targets:** percentage-of-FTP intent is not retained in the FIT output.
- **Ramps are stepped:** not smooth native ramp instructions; use `--ramp-step` to choose granularity.
- **Power range:** output targets must fall between 0 and 1000 W.
- **Limited ZWO coverage:** some unusual or advanced workout elements may be unsupported.
- **No trainer communications:** conversion is offline and independent of any BLE or ANT+ bridge.
- **No conversion of coaching prompts or cadence targets** into equivalent device instructions.

## Example: testing an ERG → FreeRide → ERG transition

The following minimal ZWO workout is useful for verifying that a trainer correctly changes modes:

```xml
<workout_file>
  <name>ERG FreeRide ERG Test</name>
  <sportType>bike</sportType>
  <workout>
    <SteadyState Duration="60" Power="0.75" />
    <FreeRide Duration="60" />
    <SteadyState Duration="60" Power="0.75" />
  </workout>
</workout_file>
```

With `--ftp 200`, it produces **150 W for one minute → one minute untargeted → 150 W for one minute**.