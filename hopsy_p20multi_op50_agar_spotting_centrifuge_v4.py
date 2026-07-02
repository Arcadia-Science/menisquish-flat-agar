from opentrons import protocol_api

# ── Metadata ──────────────────────────────────────────────────────────────────
metadata = {
    'protocolName': 'OP50 Agar Plate Spotting (Centrifuge) v4',
    'author': 'Tyler Kennedy + Claude',
    'description': (
        'Dispenses 1 uL of OP50 per column using the P20 8-channel. '
        'Fixed at 4.8 mm below well top, 5% dispense speed, 2 mm slow retract after blow out. '
        'Primes tips before first column. Optional inspect pauses before and after each dispense. '
        'Uses NEST 96-well detachable 8-well plate (nest_96well_detachable_8well) — '
        'upload custom labware JSON to Opentrons App before running.'
    ),
    'apiLevel': '2.20'
}

# ── Fixed values (not exposed as parameters) ──────────────────────────────────
DISPENSE_VOLUME_UL  = 1.0
DISPENSE_HEIGHT_MM  = 4.8   # mm below well top (calibrated for ~150 uL agar fill in NEST detachable plate)
DISPENSE_SPEED_PCT  = 5     # % of default 7.56 uL/s → 0.38 uL/s
SLOW_RETRACT_MM     = 2.0   # mm to retract slowly after blow out at 1 mm/s

# ── Runtime Parameters ────────────────────────────────────────────────────────
def add_parameters(parameters: protocol_api.Parameters):
    parameters.add_bool(
        variable_name="test_mode",
        display_name="Test Mode",
        description="Returns tips to rack instead of trash for dry runs.",
        default=False
    )
    parameters.add_int(
        variable_name="start_col",
        display_name="Starting Column",
        description="First column to spot (1-12).",
        default=1,
        minimum=1,
        maximum=12
    )
    parameters.add_int(
        variable_name="num_cols",
        display_name="Number of Columns",
        description="Number of columns to spot.",
        default=12,
        minimum=1,
        maximum=12
    )
    parameters.add_int(
        variable_name="start_tip_col",
        display_name="Starting Tip Column",
        description="Tip rack column to pick up from (1-12).",
        default=1,
        minimum=1,
        maximum=12
    )
    parameters.add_bool(
        variable_name="inspect_mode",
        display_name="Inspect Mode",
        description="Pause before and after each dispense to inspect tips.",
        default=False
    )

# ── Run Function ──────────────────────────────────────────────────────────────
def run(protocol: protocol_api.ProtocolContext):

    test_mode     = protocol.params.test_mode
    start_col     = protocol.params.start_col
    num_cols      = protocol.params.num_cols
    start_tip_col = protocol.params.start_tip_col
    inspect_mode  = protocol.params.inspect_mode

    # Clamp columns to plate bounds
    num_cols = min(num_cols, 12 - start_col + 1)

    def handle_tip_drop(pipette):
        if test_mode:
            pipette.return_tip()
        else:
            pipette.drop_tip()

    # Tip calculation: one set of 8 tips reused for all columns (single shared reagent)
    tiprack = protocol.load_labware('opentrons_96_filtertiprack_20ul', 3)

    reservoir = protocol.load_labware('nest_12_reservoir_15ml', 1)
    # Custom labware — upload nest_96well_detachable_8well_504201.json to Opentrons App first
    plate     = protocol.load_labware('nest_96well_detachable_8well', 2)

    p20_multi = protocol.load_instrument('p20_multi_gen2', 'right', tip_racks=[tiprack])

    op50_liquid = protocol.define_liquid(
        name="OP50",
        description="OP50 bacterial suspension for agar spotting",
        display_color="#22c55e"
    )
    # Volume: 1 uL × 8 wells × num_cols + 100 uL dead volume + 1 uL for prime
    reservoir_volume = (DISPENSE_VOLUME_UL * 8 * num_cols) + 101
    reservoir['A1'].load_liquid(liquid=op50_liquid, volume=reservoir_volume)

    default_dispense_rate = p20_multi.flow_rate.dispense
    slow_dispense_rate    = default_dispense_rate * (DISPENSE_SPEED_PCT / 100)

    # ── STEP 1: Pick up tips and prime ──────────────────────────────────────
    protocol.comment(f"STEP 1: Pick up tips from column {start_tip_col} and prime — aspirate 1 uL then dispense back to reservoir.")
    p20_multi.pick_up_tip(tiprack.columns()[start_tip_col - 1][0])
    p20_multi.aspirate(DISPENSE_VOLUME_UL, reservoir['A1'])
    p20_multi.dispense(DISPENSE_VOLUME_UL, reservoir['A1'])

    # ── STEP 2: Spot each column ─────────────────────────────────────────────
    protocol.comment(
        f"STEP 2: Spotting {num_cols} column(s) starting at column {start_col}, "
        f"{DISPENSE_HEIGHT_MM} mm below well top, {DISPENSE_SPEED_PCT}% dispense speed."
    )

    for i in range(num_cols):
        col_num   = start_col + i
        dest_well = plate.columns()[col_num - 1][0]

        p20_multi.aspirate(DISPENSE_VOLUME_UL, reservoir['A1'])

        if inspect_mode:
            p20_multi.move_to(dest_well.top(20))
            protocol.pause(f"Column {col_num} ready. Inspect tips. Resume to dispense.")

        p20_multi.flow_rate.dispense = slow_dispense_rate
        p20_multi.dispense(DISPENSE_VOLUME_UL, dest_well.top(-DISPENSE_HEIGHT_MM))
        p20_multi.blow_out(dest_well.top(-DISPENSE_HEIGHT_MM))
        p20_multi.flow_rate.dispense = default_dispense_rate

        # Slow retract for first 2 mm, then fast
        p20_multi.move_to(dest_well.top(-DISPENSE_HEIGHT_MM + SLOW_RETRACT_MM), speed=1)
        p20_multi.move_to(dest_well.top(20))

        if inspect_mode:
            if i < num_cols - 1:
                protocol.pause(f"Column {col_num} done. Inspect tips. Resume to continue to column {col_num + 1}.")
            else:
                protocol.pause(f"Column {col_num} done. Inspect tips. Resume to drop tips and end.")

    # ── STEP 3: Drop tips ────────────────────────────────────────────────────
    protocol.comment("STEP 3: Drop tips.")
    handle_tip_drop(p20_multi)

    protocol.comment("Protocol complete.")
