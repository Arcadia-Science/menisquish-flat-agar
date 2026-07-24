# C. elegans liquid-handling protocols

Opentrons protocols used for bleach synchronization, OP50 agar spotting, and worm plating. These scripts run on Opentrons Flex and OT-2 robots and are provided here for reproducibility alongside the associated pub.

## Contents

| Script | Robot | API level | Purpose |
|---|---|---|---|
| `bowie_celegans_bleach_sync_var-col_v1.py` | Flex (96-channel) | 2.28 | Bleach synchronization across a variable number of worm columns |
| `hopsy_p20multi_op50_agar_spotting_centrifuge_v4.py` | OT-2 (P20 8-channel) | 2.20 | Spots OP50 bacterial suspension onto agar plate columns |
| `hopsy_p20multi_worm_plating_centrifuge_v4.py` | OT-2 (P20 8-channel) | 2.20 | Transfers a small trace of worms from a deep-well plate to an agar plate |

"Bowie" and "Hopsy" are internal nicknames for the two robots used to develop and run these protocols (a Flex and an OT-2, respectively) — they carry no functional meaning beyond identifying which physical robot a script was written for.

## Requirements

- Python 3.10+ with `opentrons>=9.0.0` installed (see `requirements.txt`). A single install of this version covers both API levels used in this repo — `opentrons` releases support a backward-compatible range of `apiLevel`s, not a strict one-to-one mapping. If you're running on an OT-2 or Flex robot directly (rather than simulating locally), robot software 9.0.0 or later is required for `apiLevel` 2.28.
- Opentrons App (for uploading custom labware and running protocols on the robot)

## Labware

Every piece of labware loaded across the three protocols is listed below. **Custom** items are included in this repo under `labware/` and must be uploaded to the Opentrons App before running; **standard** items ship with the Opentrons labware library and need no separate upload.

| Labware (`loadName`) | Description | Source | Used by |
|---|---|---|---|
| `axygen_96_wellplate_1100ul` | Axygen 96-well plate, 1100 µL | **Custom** — `labware/axygen_96_wellplate_1100ul.json` | Bleach sync (worm plate), worm plating (deep-well source) |
| `nalgene_1_reservoir_300ml` | Nalgene 1-well reservoir, 300 mL | **Custom** — `labware/nalgene_1_reservoir_300ml.json` | Bleach sync (liquid waste) |
| `nest_96well_detachable_8well` | NEST 96-well ELISA plate, 8-well, detachable (catalog #504201) | **Custom** — `labware/nest_96well_detachable_8well_504201.json` | OP50 spotting (agar plate), worm plating (agar plate) |
| `nest_12_reservoir_22ml` | NEST 12-well reservoir, 22 mL | Standard | Bleach sync (water ×2, bleach, M9 troughs) |
| `nest_12_reservoir_15ml` | NEST 12-well reservoir, 15 mL | Standard | OP50 spotting (OP50 source) |
| `opentrons_flex_96_filtertiprack_1000ul` | Opentrons Flex 96 filter tip rack, 1000 µL | Standard | Bleach sync (clean + dirty racks) |
| `opentrons_flex_96_tiprack_adapter` | Opentrons Flex 96 tip-rack adapter | Standard | Bleach sync (×2, one per rack) |
| `opentrons_96_filtertiprack_20ul` | Opentrons 96 filter tip rack, 20 µL | Standard | OP50 spotting, worm plating |

The bleach sync protocol also declares the Flex waste chute via `load_waste_chute()` — a built-in deck fixture, not labware, and not used at runtime (tips return to their racks).

### Uploading the custom labware

Upload the three JSON files in `labware/` to the Opentrons App under **Labware → Add labware** before running any script. They'll appear under the "custom beta" namespace in your labware library. Each script needs only a subset — bleach sync uses the Axygen plate and Nalgene reservoir; OP50 spotting uses the NEST detachable plate; worm plating uses the Axygen plate and NEST detachable plate — but uploading all three once covers every protocol.

## Usage

1. Install dependencies: `pip install -r requirements.txt`.
2. Upload all three custom labware JSON files to the Opentrons App first (see above).
3. Open the script in the Opentrons App or upload it directly to the robot.
4. Set runtime parameters (source/destination columns, test mode, pause options, and so on — each script exposes its own set via `add_parameters`).
5. Run.

Each script includes in-code comments describing deck layout, timing logic, and volume calculations in detail — see the `metadata['description']` field and inline comments in each file for protocol-specific notes.

## Verifying without hardware

If you don't have access to a Flex or OT-2, you can still check that a protocol is well-formed using the [`opentrons_simulate`](https://docs.opentrons.com/v2/new_advanced_running.html#simulate) CLI (installed alongside the `opentrons` package). Point it at the bundled custom labware directory so the simulator can resolve the custom `loadName`s:

```bash
opentrons_simulate -L labware bowie_celegans_bleach_sync_var-col_v1.py
```

Run the same command against the other two scripts to simulate the full protocol run without a robot attached.

## Notes

- `test_mode` in each script shortens delays and/or returns tips to the rack instead of the trash, for dry runs.
- The bleach sync script tracks liquid waste volume and pauses for manual emptying before the reservoir approaches capacity; it never pauses during the bleach exposure window.
