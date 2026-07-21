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

## Custom labware

All three scripts require custom labware definitions, included in `labware/`:

| File | Defines | Required by |
|---|---|---|
| `axygen_96_wellplate_1100ul.json` | Axygen 96-well plate, 1100 µL | `bowie_celegans_bleach_sync_var-col_v1.py` (worm plate), `hopsy_p20multi_worm_plating_centrifuge_v4.py` (deep plate) |
| `nalgene_1_reservoir_300ml.json` | Nalgene 1-well reservoir, 300 mL | `bowie_celegans_bleach_sync_var-col_v1.py` (liquid waste) |
| `nest_96well_detachable_8well_504201.json` | NEST 96-well ELISA plate, 8-well, detachable (catalog #504201) | `hopsy_p20multi_worm_plating_centrifuge_v4.py`, `hopsy_p20multi_op50_agar_spotting_centrifuge_v4.py` |

Before running any script, upload all three JSON files to the Opentrons App under **Labware → Add labware**. They'll appear under the "custom beta" namespace in your labware library. All other labware called out in these scripts (NEST reservoirs, tip racks, tip rack adapters) is part of the standard Opentrons labware library and needs no separate upload.

## Usage

1. Install dependencies: `pip install -r requirements.txt`.
2. Upload all three custom labware JSON files to the Opentrons App first (see above).
3. Open the script in the Opentrons App or upload it directly to the robot.
4. Set runtime parameters (source/destination columns, test mode, pause options, and so on — each script exposes its own set via `add_parameters`).
5. Run.

Each script includes in-code comments describing deck layout, timing logic, and volume calculations in detail — see the `metadata['description']` field and inline comments in each file for protocol-specific notes.

## Notes

- `test_mode` in each script shortens delays and/or returns tips to the rack instead of the trash, for dry runs.
- The bleach sync script tracks liquid waste volume and pauses for manual emptying before the reservoir approaches capacity; it never pauses during the bleach exposure window.
