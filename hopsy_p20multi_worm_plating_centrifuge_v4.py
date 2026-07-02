from opentrons import protocol_api

# ── Metadata ──────────────────────────────────────────────────────────────────
metadata = {
    'protocolName': 'Worm Plating (Centrifuge) v4',
    'author': 'Tyler Kennedy + Claude',
    'description': (
        'Transfers a small trace of worms from a deep 96-well plate to a flat 96-well '
        'agar plate using the P20 8-channel. Two source columns each map to user-specified '
        'destination columns. For each destination: aspirates 1.1 µL from the well bottom '
        '(0 mm), immediately dispenses 1.0 µL back into the source well (retaining 0.1 µL '
        'in the tip), then moves directly to the agar well and blows out the remaining '
        '0.1 µL at 4.8 mm below the rim. '
        'Uses NEST 96-well detachable 8-well plate (nest_96well_detachable_8well) — '
        'upload custom labware JSON to Opentrons App before running.'
    ),
    'apiLevel': '2.20'
}

# ── Fixed values ───────────────────────────────────────────────────────────────
ASPIRATE_VOLUME_UL = 1.1   # total volume drawn from source
RETURN_VOLUME_UL   = 1.0   # volume dispensed back — leaves 0.1 µL in tip
ASPIRATE_HEIGHT_MM = 0.0   # mm above well bottom — pulls from pellet surface
DISPENSE_HEIGHT_MM = 4.8   # mm below well top (calibrated for ~150 µL agar fill in NEST detachable plate)
DISPENSE_SPEED_PCT = 5     # % of default 7.56 µL/s → ~0.38 µL/s (gentle blowout)
SLOW_RETRACT_MM    = 2.0   # mm to retract slowly after blow-out at 1 mm/s

# ── Runtime Parameters ────────────────────────────────────────────────────────
def add_parameters(parameters: protocol_api.Parameters):
    parameters.add_int(
        variable_name="source_col_1",
        display_name="Source Column 1",
        description="Deep-well column with worm sample 1 (1-12).",
        default=1, minimum=1, maximum=12
    )
    parameters.add_str(
        variable_name="dest_cols_1",
        display_name="Dest Columns (Source 1)",
        description="Which agar plate columns receive worms from source 1.",
        default="1,3,5,7,9,11",
        choices=[
            {"display_name": "Odd  (1,3,5,7,9,11)",       "value": "1,3,5,7,9,11"},
            {"display_name": "Even (2,4,6,8,10,12)",       "value": "2,4,6,8,10,12"},
            {"display_name": "Left half  (1-6)",            "value": "1,2,3,4,5,6"},
            {"display_name": "Right half (7-12)",           "value": "7,8,9,10,11,12"},
            {"display_name": "All 12  (1-12)",              "value": "1,2,3,4,5,6,7,8,9,10,11,12"},
            {"display_name": "None (skip)",                 "value": ""},
        ]
    )
    parameters.add_int(
        variable_name="source_col_2",
        display_name="Source Column 2",
        description="Deep-well column with worm sample 2 (1-12).",
        default=2, minimum=1, maximum=12
    )
    parameters.add_str(
        variable_name="dest_cols_2",
        display_name="Dest Columns (Source 2)",
        description="Which agar plate columns receive worms from source 2.",
        default="2,4,6,8,10,12",
        choices=[
            {"display_name": "Even (2,4,6,8,10,12)",       "value": "2,4,6,8,10,12"},
            {"display_name": "Odd  (1,3,5,7,9,11)",        "value": "1,3,5,7,9,11"},
            {"display_name": "Left half  (1-6)",            "value": "1,2,3,4,5,6"},
            {"display_name": "Right half (7-12)",           "value": "7,8,9,10,11,12"},
            {"display_name": "All 12  (1-12)",              "value": "1,2,3,4,5,6,7,8,9,10,11,12"},
            {"display_name": "None (skip)",                 "value": ""},
        ]
    )
    parameters.add_bool(
        variable_name="pause_before",
        display_name="Pause Before Delivery",
        description="Pause before dispensing to each destination column.",
        default=False
    )
    parameters.add_bool(
        variable_name="pause_after",
        display_name="Pause After Delivery",
        description="Pause after dispensing to each destination column.",
        default=False
    )
    parameters.add_int(
        variable_name="tip_start_col",
        display_name="Tip Start Column",
        description="First tip rack column to use (1-11). Uses this col + next col.",
        default=1, minimum=1, maximum=11
    )
    parameters.add_bool(
        variable_name="test_mode",
        display_name="Test Mode",
        description="Returns tips to rack instead of trash for dry runs.",
        default=False
    )

# ── Run Function ──────────────────────────────────────────────────────────────
def run(protocol: protocol_api.ProtocolContext):

    source_col_1  = protocol.params.source_col_1
    dest_cols_1   = protocol.params.dest_cols_1
    source_col_2  = protocol.params.source_col_2
    dest_cols_2   = protocol.params.dest_cols_2
    pause_before  = protocol.params.pause_before
    pause_after   = protocol.params.pause_after
    tip_start_col = protocol.params.tip_start_col
    test_mode     = protocol.params.test_mode

    def parse_cols(s):
        cols = []
        for part in s.split(','):
            part = part.strip()
            if part.isdigit():
                c = int(part)
                if 1 <= c <= 12:
                    cols.append(c)
        return cols

    dest_list_1 = parse_cols(dest_cols_1)
    dest_list_2 = parse_cols(dest_cols_2)

    def handle_tip_drop(pipette):
        if test_mode:
            pipette.return_tip()
        else:
            pipette.drop_tip()

    tiprack    = protocol.load_labware('opentrons_96_filtertiprack_20ul',  3)
    deep_plate = protocol.load_labware('axygen_96_wellplate_1100ul',       1)
    # Custom labware — upload nest_96well_detachable_8well_504201.json to Opentrons App first
    agar_plate = protocol.load_labware('nest_96well_detachable_8well',     2)

    p20_multi = protocol.load_instrument('p20_multi_gen2', 'right', tip_racks=[tiprack])

    # ── Liquid definitions ────────────────────────────────────────────────────
    worm_liq_1 = protocol.define_liquid(
        name="Worms — Source 1",
        description="C. elegans worms/embryos in M9, source column 1",
        display_color="#f97316"   # orange
    )
    worm_liq_2 = protocol.define_liquid(
        name="Worms — Source 2",
        description="C. elegans worms/embryos in M9, source column 2",
        display_color="#8b5cf6"   # purple
    )

    vol_per_well_1 = max(ASPIRATE_VOLUME_UL * len(dest_list_1) + 10, 50)
    vol_per_well_2 = max(ASPIRATE_VOLUME_UL * len(dest_list_2) + 10, 50)
    for well in deep_plate.columns()[source_col_1 - 1]:
        well.load_liquid(liquid=worm_liq_1, volume=vol_per_well_1)
    for well in deep_plate.columns()[source_col_2 - 1]:
        well.load_liquid(liquid=worm_liq_2, volume=vol_per_well_2)

    default_dispense_rate = p20_multi.flow_rate.dispense
    slow_dispense_rate    = default_dispense_rate * (DISPENSE_SPEED_PCT / 100)

    # ── Delivery helper ───────────────────────────────────────────────────────
    def deliver_column(source_col, dest_cols, label, tip_well):
        if not dest_cols:
            protocol.comment(f"{label}: no destination columns specified — skipping.")
            return

        protocol.comment(
            f"{label}: picking up tips. "
            f"Delivering to destination columns: {dest_cols}."
        )
        p20_multi.pick_up_tip(tip_well)

        source_well = deep_plate.columns()[source_col - 1][0]
        aspirate_loc = source_well.bottom(ASPIRATE_HEIGHT_MM)

        for idx, dest_col in enumerate(dest_cols):
            dest_well = agar_plate.columns()[dest_col - 1][0]

            p20_multi.aspirate(ASPIRATE_VOLUME_UL, aspirate_loc)
            p20_multi.dispense(RETURN_VOLUME_UL, aspirate_loc)

            if pause_before:
                p20_multi.move_to(dest_well.top(20))
                protocol.pause(
                    f"{label} → dest col {dest_col}: ready to blowout. "
                    f"Inspect tips. Resume to deliver."
                )

            # Blowout at agar surface — deposits residual film gently
            p20_multi.flow_rate.dispense = slow_dispense_rate
            p20_multi.blow_out(dest_well.top(-DISPENSE_HEIGHT_MM))
            p20_multi.flow_rate.dispense = default_dispense_rate

            # Slow retract for first 2 mm, then fast (prevents trailing droplet)
            p20_multi.move_to(dest_well.top(-DISPENSE_HEIGHT_MM + SLOW_RETRACT_MM), speed=1)
            p20_multi.move_to(dest_well.top(20))

            if pause_after:
                if idx < len(dest_cols) - 1:
                    next_step = f"dest col {dest_cols[idx + 1]}"
                else:
                    next_step = "drop tips and finish source"
                protocol.pause(
                    f"{label} → dest col {dest_col}: done. "
                    f"Inspect. Resume to continue to {next_step}."
                )

        handle_tip_drop(p20_multi)

    # ── Log run settings ──────────────────────────────────────────────────────
    protocol.comment(
        f"Worm Plating (Centrifuge) v4 | "
        f"src1=col{source_col_1}→[{dest_cols_1}] | "
        f"src2=col{source_col_2}→[{dest_cols_2}] | "
        f"tip_cols={tip_start_col}&{tip_start_col+1} | "
        f"pause_before={pause_before} | pause_after={pause_after} | "
        f"test_mode={test_mode}"
    )

    # ── STEP 1: Deliver from source column 1 ─────────────────────────────────
    protocol.comment(
        f"STEP 1: Aspirate {ASPIRATE_VOLUME_UL} µL from deep-well col {source_col_1} "
        f"({ASPIRATE_HEIGHT_MM} mm above bottom), dispense {RETURN_VOLUME_UL} µL back (no blowout), "
        f"blowout remaining {ASPIRATE_VOLUME_UL - RETURN_VOLUME_UL:.1f} µL onto agar cols [{dest_cols_1}] "
        f"({DISPENSE_HEIGHT_MM} mm below top, {DISPENSE_SPEED_PCT}% speed)."
    )
    tip_well_1 = tiprack.columns()[tip_start_col - 1][0]
    tip_well_2 = tiprack.columns()[tip_start_col][0]
    deliver_column(source_col_1, dest_list_1, f"Src col {source_col_1}", tip_well_1)

    # ── STEP 2: Deliver from source column 2 ─────────────────────────────────
    protocol.comment(
        f"STEP 2: Aspirate {ASPIRATE_VOLUME_UL} µL from deep-well col {source_col_2} "
        f"({ASPIRATE_HEIGHT_MM} mm above bottom), dispense {RETURN_VOLUME_UL} µL back (no blowout), "
        f"blowout remaining {ASPIRATE_VOLUME_UL - RETURN_VOLUME_UL:.1f} µL onto agar cols [{dest_cols_2}] "
        f"({DISPENSE_HEIGHT_MM} mm below top, {DISPENSE_SPEED_PCT}% speed)."
    )
    deliver_column(source_col_2, dest_list_2, f"Src col {source_col_2}", tip_well_2)

    protocol.comment("Protocol complete.")
