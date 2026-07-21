import time
from opentrons import protocol_api

metadata = {
    'protocolName': 'C. elegans Bleach Sync — Variable Columns (96-channel) v1',
    'author': 'Tyler Kennedy + Claude',
    'description': (
        'Full 96-channel version of the 2-col v17 bleach sync: the exact single-column '
        'procedure, executed on all 96 nozzles at once. Load worms in any subset of the '
        'plate columns and matching reagent in the corresponding reservoir wells (cols 1-N). '
        'Nozzle columns over empty wells never touch liquid and stay dry for reuse — pluck '
        'the used tip columns by hand after the run and top the racks back up to 96. '
        'Timings identical to v17 (30 s bleach, 1 min initial settle, 3 min wash settles). '
        'Liquid waste collects in a Nalgene reservoir at D2; the robot pauses to have you empty '
        'it before it reaches 250 mL (0 pauses for 1-4 columns, up to 2 for 12). Pauses only ever '
        'land on post-bleach wash/M9 removals — never in the bleach window.'
    ),
    'apiLevel': '2.28'
}

requirements = {"robotType": "Flex"}


def add_parameters(parameters: protocol_api.Parameters):
    parameters.add_int(
        variable_name="num_columns",
        display_name="Number of Columns",
        description="Worm columns loaded (1-12). Drives waste-empty pauses + liquid display; motions always 96.",
        default=12, minimum=1, maximum=12
    )
    parameters.add_bool(
        variable_name="test_mode",
        display_name="Test Mode (fast dry run)",
        description="Shortens settle delays for dry runs. Tips always return to racks for hand-sorting.",
        default=False
    )


def run(protocol: protocol_api.ProtocolContext):

    # ── Parameters ──────────────────────────────────────────────────────────────
    num_columns = protocol.params.num_columns
    test_mode   = protocol.params.test_mode

    # Fixed settings (match v17) ─────────────────────────────────────────────────
    DEFAULT_FLOW        = 160.0
    SLOW_ASPIRATE       = 80.0    # 50% of 160 — gentle draw off settled worms/embryos
    BLEACH_EXPOSURE_SEC = 30.0    # 30 s target, identical to 2col v16/v17. It is a FLOOR, not a forced
                                  # soak: remaining = target - elapsed, so it only waits if the add->remove
                                  # arm swap finished in under 30 s. It never does (~40 s swap), so no delay
                                  # fires and the bleach contact = arm time (~55-67 s in the real runs).
    SRC_H               = 1.5     # fixed aspirate height for the untracked troughs (bleach, M9)

    # ── NEST 22 mL trough surface-tracking (anti-spill) ───────────────────────────
    # 8 tips plunged into a near-full trough push liquid over the rim. For high-fill troughs
    # (the water troughs, registered in _trough_vol below) aspirate just under the DESCENDING
    # surface, not at the bottom. Geometry (nest_12_reservoir_22ml): ~576.7 uL/mm in the main
    # body above a 2.02 mm bottom taper (~700 uL below the taper top); well depth 39.55 mm.
    TROUGH_AREA, TROUGH_TAPER_H, TROUGH_TAPER_V = 576.7, 2.02, 700.0
    SUBMERGE, MIN_SRC_H = 3.0, 1.0   # mm below the post-draw surface; floor above the bottom

    def _surface_h(v):
        if v <= TROUGH_TAPER_V:
            return max(TROUGH_TAPER_H * v / TROUGH_TAPER_V, 0.0)
        return TROUGH_TAPER_H + (v - TROUGH_TAPER_V) / TROUGH_AREA

    _trough_vol = {}   # id(A1 well) -> current uL/well; only set for surface-tracked troughs

    def src_h(well_a1, draw_per_nozzle):
        """Aspirate height keeping the tip ~SUBMERGE mm under the surface AFTER this draw
        (draw_per_nozzle x 8 leaves the well). Untracked troughs return the fixed SRC_H."""
        if id(well_a1) not in _trough_vol:
            return SRC_H
        _trough_vol[id(well_a1)] -= draw_per_nozzle * 8
        return max(_surface_h(_trough_vol[id(well_a1)]) - SUBMERGE, MIN_SRC_H)

    # Waste handling: liquid removals go to the Nalgene reservoir at D2 (300 mL capacity).
    # The robot pauses to have it emptied before the running total reaches WASTE_CAP_ML, which
    # keeps the level below ~31 mm (rim is ~37 mm) so the dry nozzle columns never meet the
    # rising surface. Per-removal liquid into the reservoir = added volume × 8 wells × N columns;
    # the media removal (R1) is treated as a full 900 µL/well draw (conservative).
    WASTE_CAP_ML     = 250.0
    WASTE_PER_COL_ML = 8 * 0.900 * 8   # conservative upper bound for the start-of-run estimate (57.6 mL)

    # ── Deck layout (full 96-channel — no single-column overhang) ─────────────────
    # The 8 usable slots are ALL in use; A1/A3/D1/D3 are taken by Bowie's fixed modules.
    #   A1 = Temperature Module Gen2  (installed — not used; do not load)
    #   A2 = worm plate     (Axygen 96-well 1100 µL; worms in cols 1-N)
    #   A3 = Absorbance Plate Reader  (installed — not used; leave clear)
    #   B1 = CLEAN rack     (dispense tips, on adapter — only ever touch reagents)
    #   B2 = Bleach NEST    (premixed bleach 8.5:1:0.5; load wells 1-N to ~10 mL each)
    #   B3 = Water NEST B   (water washes 3-5; load wells 1-N to ~19 mL each; surface-tracked)
    #   C1 = DIRTY rack     (removal tips, on adapter — touch worm-well contents)
    #   C2 = Water NEST A   (water washes 1-2; load wells 1-N to ~15 mL each; surface-tracked)
    #   C3 = M9 NEST        (final wash + resuspension; load wells 1-N to ~15 mL each)
    #   D1 = heater-shaker  (installed — not used; do not load)
    #   D2 = Nalgene waste reservoir (300 mL) — all liquid waste; emptied at pauses
    #   D3 = waste chute    (declared as the trash fixture; not used — tips return to racks)
    #
    # Every reservoir holds liquid ONLY in wells 1-N, so nozzle columns N+1..12 sit
    # over empty wells on every aspirate/dispense and never get wet.
    #
    # Per-worm-column reagent draws over the full run:
    #   Water  = 30.4 mL  (Water A: washes 1-2 @ 800 µL = 12.8 mL; Water B: washes 3 @ 800 + 4-5 @ 700 = 17.6 mL)
    #   Bleach = 1 × 900 µL/well × 8 = 7.2 mL
    #   M9     = (800 + 700) µL/well × 8 = 12 mL  (wash + resuspension, same well)

    worm_plate = protocol.load_labware('axygen_96_wellplate_1100ul', 'A2')

    water_a   = protocol.load_labware('nest_12_reservoir_22ml', 'C2')   # washes 1-2
    water_b   = protocol.load_labware('nest_12_reservoir_22ml', 'B3')   # washes 3-5
    bleach    = protocol.load_labware('nest_12_reservoir_22ml', 'B2')
    m9        = protocol.load_labware('nest_12_reservoir_22ml', 'C3')
    waste_res = protocol.load_labware('nalgene_1_reservoir_300ml', 'D2') # liquid waste (emptied at pauses)

    ad_clean   = protocol.load_adapter('opentrons_flex_96_tiprack_adapter', 'B1')
    clean_rack = ad_clean.load_labware('opentrons_flex_96_filtertiprack_1000ul')
    ad_dirty   = protocol.load_adapter('opentrons_flex_96_tiprack_adapter', 'C1')
    dirty_rack = ad_dirty.load_labware('opentrons_flex_96_filtertiprack_1000ul')

    waste_chute = protocol.load_waste_chute()

    # ── Pipette (full 96-channel, default ALL nozzle config) ──────────────────────
    p96 = protocol.load_instrument('flex_96channel_1000')

    # Anchor wells (ALL config maps the full 96 nozzles from the A1 corner) ────────
    plate_a1   = worm_plate.wells()[0]
    clean_a1   = clean_rack.wells()[0]
    dirty_a1   = dirty_rack.wells()[0]

    # ── Liquids (defined/loaded only in the columns you loaded) ───────────────────
    water_liq  = protocol.define_liquid('Water',                     'Molecular grade water',             '#06b6d4')
    bleach_liq = protocol.define_liquid('Premixed Bleach 8.5:1:0.5', '765:90:45 water:bleach:KOH',        '#f43f5e')
    m9_liq     = protocol.define_liquid('M9 Buffer',                 'M9 for final wash + resuspension',  '#22c55e')
    waste_liq  = protocol.define_liquid('Waste',                     'Collected liquid waste',            '#6b7280')

    for i in range(num_columns):
        water_a.wells()[i].load_liquid(liquid=water_liq,  volume=15000)  # ~15 mL — washes 1-2 use 12.8 mL
        water_b.wells()[i].load_liquid(liquid=water_liq,  volume=19000)  # ~19 mL — washes 3-5 use 17.6 mL
        bleach.wells()[i].load_liquid(liquid=bleach_liq, volume=10000)   # ~10 mL premix — 1 dose uses 7.2 mL
        m9.wells()[i].load_liquid(liquid=m9_liq,         volume=15000)   # ~15 mL — wash + resusp use 12 mL
    waste_res.wells()[0].load_liquid(liquid=waste_liq, volume=0)         # starts empty

    _trough_vol[id(water_a.wells()[0])] = 15000.0   # surface-track both water troughs (high-fill)
    _trough_vol[id(water_b.wells()[0])] = 19000.0

    # ── Helpers ───────────────────────────────────────────────────────────────────
    def use_clean():
        """Pick up all 96 dispense tips (re-picks the same set after a return)."""
        p96.pick_up_tip(clean_a1)

    def use_dirty():
        """Pick up all 96 removal tips."""
        p96.pick_up_tip(dirty_a1)

    def add(source_res, volume):
        """Aspirate reagent from a reservoir (cols 1-N) and dispense over the worm wells."""
        p96.flow_rate.aspirate = DEFAULT_FLOW
        p96.flow_rate.dispense = DEFAULT_FLOW
        p96.aspirate(volume, source_res.wells()[0].bottom(src_h(source_res.wells()[0], volume)))
        p96.dispense(volume, plate_a1.top(-1))
        p96.blow_out(plate_a1.top(-1))

    waste_top = waste_res.wells()[0].top()   # dispense at the rim — keeps dry tips above the waste surface

    def remove(height_mm=4):
        """Draw 900 µL/well off the worm plate (slow) and dump to the D2 waste reservoir (from the top)."""
        p96.flow_rate.aspirate = SLOW_ASPIRATE
        p96.aspirate(900, plate_a1.bottom(height_mm))
        p96.flow_rate.aspirate = DEFAULT_FLOW
        p96.dispense(900, waste_top)
        p96.blow_out(waste_top)

    # ── Waste tracking + auto-empty pause ─────────────────────────────────────────
    # waste_ml tracks the running volume in the D2 reservoir. Before a *pausable* removal,
    # if this removal would push it past the cap, pause for the user to empty (then reset).
    # The bleach removal (R3) is NEVER pausable — verified it can't reach the cap (<=249.6 mL
    # even at 12 columns), so the bleach exposure timing is never interrupted.
    waste_ml = [0.0]

    def do_removal(liquid_per_well_ul, label, allow_pause=True):
        incoming = liquid_per_well_ul * 8 * num_columns / 1000.0   # mL into the reservoir
        if allow_pause and (waste_ml[0] + incoming > WASTE_CAP_ML):
            protocol.pause(
                f"Empty the D2 waste reservoir now (~{waste_ml[0]:.0f} mL), then resume "
                f"(before {label})."
            )
            waste_ml[0] = 0.0
        use_dirty(); remove(); p96.return_tip()
        waste_ml[0] += incoming

    def settle(minutes, msg):
        if test_mode:
            protocol.delay(seconds=2, msg=f"[test] {msg}")
        else:
            protocol.delay(minutes=minutes, msg=msg)

    # ══════════════════════════════════════════════════════════════════════════════

    # Precompute the expected number of empty-the-reservoir pauses (mirrors do_removal volumes/logic below).
    _removal_ul = [900, 800, 900, 800, 800, 700, 700, 800]            # R1..R8 liquid per well
    _pausable   = [False, False, False, True, True, True, True, True]  # R3 (bleach) is never pausable
    _r = 0.0; _expected_pauses = 0
    for _ul, _can in zip(_removal_ul, _pausable):
        _inc = _ul * 8 * num_columns / 1000.0
        if _can and _r + _inc > WASTE_CAP_ML:
            _expected_pauses += 1; _r = 0.0
        _r += _inc

    est_waste = num_columns * WASTE_PER_COL_ML
    protocol.comment(
        f"var-col v1 | 96-channel | columns={num_columns} | test_mode={test_mode}"
    )
    protocol.comment(
        f"Liquid waste -> D2 Nalgene reservoir (cap {WASTE_CAP_ML:.0f} mL). "
        f"Up to ~{est_waste:.0f} mL total this run; expect {_expected_pauses} empty-the-reservoir pause(s)."
    )

    # STEP 1: Remove media → add 800 µL water (wash 1, Water A) → settle 1 min ──────
    protocol.comment("STEP 1: Remove worm media, add 800 µL water (wash 1), settle 1 min.")
    do_removal(900, "STEP 1 media removal", allow_pause=False)   # pre-bleach: never near the cap
    use_clean(); add(water_a, 800); p96.return_tip()
    settle(1, "Worms re-settling in water (wash 1).")

    # STEP 2: Remove wash 1 → bleach (30 s floor, absorbed by arm time) → remove → add water (wash 2) ──
    protocol.comment("STEP 2: Remove wash 1, add bleach, 30 s floor (arm time governs), remove, add 800 µL water (wash 2).")
    do_removal(800, "STEP 2 wash-1 removal", allow_pause=False)  # pre-bleach: never near the cap

    use_clean()
    add(bleach, 900)
    t_bleach = time.monotonic()
    protocol.comment("Bleach added to all columns. Timer started.")
    p96.return_tip()

    use_dirty()
    p96.move_to(plate_a1.top())
    # Identical to 2col v16/v17: 30 s is a FLOOR via `target - elapsed`, not a forced soak. The
    # ~40 s add->remove arm swap already exceeds 30 s, so this never delays and bleach contact =
    # arm time. Arm time is uncontrolled but reproducible (66-68 s logged across the v16/v17 runs).
    remaining = BLEACH_EXPOSURE_SEC - (time.monotonic() - t_bleach)
    if remaining > 0:
        protocol.delay(seconds=remaining, msg="Bleach incubating.")
    remove()   # bleach removal — NEVER preceded by a pause (timing-critical); just track the waste
    waste_ml[0] += 900 * 8 * num_columns / 1000.0
    protocol.comment(f"Bleach actual exposure: {time.monotonic() - t_bleach:.0f} s.")
    p96.return_tip()

    use_clean(); add(water_a, 800); p96.return_tip()   # post-bleach = wash 2 (Water A)

    # STEP 3: Post-bleach settle 3 min ─────────────────────────────────────────────
    protocol.comment("STEP 3: Post-bleach settle 3 min (after wash 2).")
    settle(3, "Embryos settling — wash 2.")

    # STEP 4: Wash 3 (Water B, 800 µL) ─────────────────────────────────────────────
    protocol.comment("STEP 4: Wash 3 — remove, add 800 µL water, settle 3 min.")
    do_removal(800, "STEP 4 wash-2 removal")
    use_clean(); add(water_b, 800); p96.return_tip()
    settle(3, "Embryos settling — wash 3.")

    # STEP 5: Wash 4 (Water B, 700 µL) ─────────────────────────────────────────────
    protocol.comment("STEP 5: Wash 4 — remove, add 700 µL water, settle 3 min.")
    do_removal(800, "STEP 5 wash-3 removal")
    use_clean(); add(water_b, 700); p96.return_tip()
    settle(3, "Embryos settling — wash 4.")

    # STEP 6: Wash 5 (Water B, 700 µL) ─────────────────────────────────────────────
    protocol.comment("STEP 6: Wash 5 — remove, add 700 µL water, settle 3 min.")
    do_removal(700, "STEP 6 wash-4 removal")
    use_clean(); add(water_b, 700); p96.return_tip()
    settle(3, "Embryos settling — wash 5.")

    # STEP 7: M9 wash ──────────────────────────────────────────────────────────────
    protocol.comment("STEP 7: M9 wash — remove, add 800 µL M9, settle 3 min.")
    do_removal(700, "STEP 7 wash-5 removal")
    use_clean(); add(m9, 800); p96.return_tip()
    settle(3, "Embryos settling — M9 wash.")

    # STEP 8: Remove M9 wash → add 700 µL M9 resuspension (stays) ───────────────────
    protocol.comment("STEP 8: Remove M9 wash, add 700 µL M9 resuspension.")
    do_removal(800, "STEP 8 M9-wash removal")
    use_clean(); add(m9, 700); p96.return_tip()

    protocol.comment(
        f"Complete. Columns 1-{num_columns} embryos are in 700 µL M9. "
        f"Pluck the used tip columns (1-{num_columns}) from both racks by hand; the rest stay dry for reuse."
    )
