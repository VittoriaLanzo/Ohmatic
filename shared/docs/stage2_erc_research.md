# Stage 2 ERC Research - Component Taxonomy & Rule Expansion

**Status:** Research spike - not yet implemented  
**Date:** 2026-05-24  
**Author:** Vittoria Lanzo  
**Purpose:** Define the expanded component vocabulary and rule set for Stage 2. All content is derived from electrical engineering first principles; no code or rule text is copied from any external codebase. (Copyright: AGPL-3.0, same as the project.)

---

## 1. Copyright & Sources Policy

All component types and rule descriptions in this document are derived from:
- Electrical engineering fundamentals (Kirchhoff's laws, semiconductor physics)
- Manufacturer datasheets (public domain application guidance)
- Standard reference designator conventions (IEEE 315-1975, IEC 60617 - categories only, not the paywalled text)

**Not used as a source for any content herein:**
- KiCad source code (GPL-3 - cannot be incorporated into an AGPL-3 project without full copyleft compliance)
- LibrePCB, Horizon EDA, or any other GPL tool's source code
- KiCad symbol library files (CC-BY-SA 4.0 - incompatible without explicit relicensing)

The *fact* that "an LED needs a current-limiting resistor" is physics and is not copyrightable. Our implementation in Rust is written from scratch.

---

## 2. Current State (Stage 1 baseline)

### Component types: 22
`resistor`, `capacitor`, `inductor`, `diode`, `led`, `transistor_npn`, `transistor_pnp`, `mosfet_n`, `mosfet_p`, `ic_timer`, `ic_opamp`, `ic_regulator`, `ic_logic`, `ic_mcu`, `ic_driver`, `power_vcc`, `power_gnd`, `connector`, `crystal`, `button`, `speaker`, `sensor`

### Rules: 17
- T1: 7 schema/structural rules (`run_tier1`, delegates to `OhmaticCircuitV01::validate()`)
- T2: 2 geometry rules (T2-01 normalise, T2-02 collision)
- T3: 8 electrical rules (T3-01 through T3-08)

---

## 3. Expanded Component Taxonomy (Stage 2 target: ~50 types)

### 3.1 Protection & Switching

| Snake_case name | Description | Key pins | Notes |
|-----------------|-------------|----------|-------|
| `relay` | Electromechanical switch. Coil energises to close contacts. | `A1`, `A2` (coil), `NO`, `NC`, `COM` (contacts) | Needs flyback diode across coil (T3-09). Stage 1 has no `relay` type - circuits using relays must currently use `connector` as a workaround. |
| `fuse` | Overcurrent protection element. Breaks circuit above rated current. | `1`, `2` | Passive series element. No DRC rule needed beyond T1/T2. |
| `tvs_diode` | Transient voltage suppressor. Clamps overvoltage spikes. | `A`, `K` (unidirectional) or `A1`, `A2` (bidirectional) | Usually placed across a power net. |
| `zener_diode` | Voltage reference / clamp. Reverse-biased in normal operation. | `A`, `K` | Distinct from `diode` - operates in breakdown region intentionally. |
| `schottky_diode` | Low forward-voltage drop diode. Used in rectifiers, protection. | `A`, `K` | Common in power supply catch circuits and reverse-polarity protection. |
| `thyristor_scr` | Silicon controlled rectifier. Latching switch - ON until current interrupted. | `A`, `K`, `G` | Gate triggers turn-on only. |
| `triac` | Bidirectional thyristor. Used in AC power control. | `MT1`, `MT2`, `G` | Phase-control circuits (dimmers, motor speed). |
| `igbt` | Insulated gate bipolar transistor. High-voltage, high-current switching. | `G`, `C`, `E` | Used in motor drives, inverters. Gate drive similar to MOSFET. |

### 3.2 Optoelectronics

| Snake_case name | Description | Key pins | Notes |
|-----------------|-------------|----------|-------|
| `optocoupler` | Galvanic isolation via light. LED input, phototransistor output. | `A`, `K` (LED), `C`, `E` (transistor), `VCC`, `GND` optional | Input and output sides must be on electrically isolated nets. |
| `photodiode` | Light-sensitive diode. Reverse-biased for photocurrent mode. | `A`, `K` | Low-light current sensing. |
| `phototransistor` | Light-sensitive transistor. No physical base pin. | `C`, `E` | Base is effectively "light". Base pin may be absent or NC. |
| `led_rgb` | RGB LED (common anode or common cathode). | `R`, `G`, `B`, `COM` | Each colour channel needs its own current-limiting resistor. |
| `seven_segment` | 7-segment numeric display. | `A`-`G`, `DP`, `COM` | Each segment pin needs a current-limiting resistor. |

### 3.3 Analog ICs

| Snake_case name | Description | Key pins | Notes |
|-----------------|-------------|----------|-------|
| `ic_comparator` | Voltage comparator. Non-inverting/inverting inputs, single output. | `IN+`, `IN-`, `OUT`, `VCC`, `GND` | Output is often open-collector/drain - needs pull-up resistor (T3-14). |
| `ic_adc` | Analog-to-digital converter. | `VIN`, `VREF`, `SDA`/`SCK` or parallel bus, `VCC`, `GND` | Bypass cap required (same as IcMcu - T3-04 scope). |
| `ic_dac` | Digital-to-analog converter. | `VOUT`, `SDA`/`SCK`, `VREF`, `VCC`, `GND` | Requires voltage reference or VCC as reference. |
| `ic_voltage_ref` | Precision voltage reference IC. | `IN`, `OUT`, `GND` | Distinct from `ic_regulator` - no load regulation, only precision output. |
| `ic_pll` | Phase-locked loop. | `VCO_IN`, `CLK_IN`, `CLK_OUT`, `VCC`, `GND` | Loop filter caps needed. |
| `ic_instrumentation_amp` | High-CMRR differential amplifier. | `IN+`, `IN-`, `OUT`, `REF`, `VCC`, `VEE`, `GND`, `RG` (gain set) | Needs symmetric supply for bipolar signals. |

### 3.4 Power

| Snake_case name | Description | Key pins | Notes |
|-----------------|-------------|----------|-------|
| `power_vee` | Negative supply rail (e.g. −15V). | `1` | Listed in ARCH-02. Enables T3-04/T3-06 multi-rail checks. |
| `power_3v3` | Named 3.3V supply symbol. | `1` | Allows tools to distinguish multi-rail circuits. |
| `power_5v` | Named 5V supply symbol. | `1` | |
| `power_12v` | Named 12V supply symbol. | `1` | |

### 3.5 Magnetics & Transformers

| Snake_case name | Description | Key pins | Notes |
|-----------------|-------------|----------|-------|
| `transformer` | Magnetic coupling with galvanic isolation. Primary + secondary windings. | `P1`, `P2` (primary), `S1`, `S2` (secondary); `S3`, `S4` for centre-tap | Primary and secondary nets must be electrically isolated (T3-12). |

### 3.6 Motion & Actuators

| Snake_case name | Description | Key pins | Notes |
|-----------------|-------------|----------|-------|
| `motor_dc` | DC brush motor. | `1`, `2` | Back-EMF requires flyback diode or H-bridge freewheeling (T3-15). |
| `motor_stepper` | Stepper motor. 4-wire (bipolar) or 6-wire (unipolar). | `A+`, `A-`, `B+`, `B-` (bipolar) | Requires dedicated stepper driver IC. |
| `servo` | RC servo with PWM control. | `VCC`, `GND`, `SIG` | 5V power, ~50Hz PWM signal. |

### 3.7 Passive Variants

| Snake_case name | Description | Key pins | Notes |
|-----------------|-------------|----------|-------|
| `potentiometer` | 3-terminal variable resistor. | `A`, `W` (wiper), `B` | Wiper unconnected is a common error (T3-17). |
| `thermistor` | Temperature-sensitive resistor. NTC or PTC. | `1`, `2` | Usually part of a voltage divider. Treated as passive for DRC. |
| `varistor` | Voltage-dependent resistor (MOV). Overvoltage clamp. | `1`, `2` | Protection across mains or signal lines. |

### 3.8 Memory & Communication ICs

| Snake_case name | Description | Key pins | Notes |
|-----------------|-------------|----------|-------|
| `ic_memory` | EEPROM, Flash, SRAM. | `VCC`, `GND`, `SDA`/`SCK`, `CS`, `WP`, address pins | Bypass cap required. |

### 3.9 Displays

| Snake_case name | Description | Key pins | Notes |
|-----------------|-------------|----------|-------|
| `lcd` | LCD display module (character or graphic). | `VCC`, `GND`, `RS`, `E`, `D0`-`D7` (parallel) or `SDA`, `SCK` (I2C) | Backlight LED usually needs current limiting. |

---

**Total Stage 2 component count: 22 (current) + 28 (new) = 50 types**

---

## 4. Pin Type System

Each component type will have a pin-type annotation map. Pin types determine which connections are valid.

### 4.1 Pin Type Enum

| Type | Meaning | Direction |
|------|---------|-----------|
| `power_in` | Draws from a supply rail | Sink |
| `power_out` | Sources a supply rail | Source |
| `passive` | No direction - resistor, capacitor pins | Bidirectional |
| `input` | Signal input - gate, base, non-inverting | Sink |
| `output` | Signal output - drain (load), op-amp out | Source |
| `bidirectional` | Can be input or output - MCU GPIO, I2C | Both |
| `open_drain` | Can only pull low; needs external pull-up | Source (weak) |
| `no_connect` | Intentionally unconnected | - |

### 4.2 Pin Conflict Matrix

When two pins connect on the same net, the following conflicts apply:

| Pin A | Pin B | Result |
|-------|-------|--------|
| `output` | `output` | **ERROR** - two drivers fighting (bus contention) |
| `power_out` | `power_out` | **ERROR** - two power sources short |
| `output` | `power_out` | **ERROR** - signal driver vs power rail |
| `open_drain` | `open_drain` | **OK** - wire-OR is valid |
| `input` | nothing | **WARNING** - floating input |
| `power_in` | nothing | **WARNING** - IC without power |
| `passive` | `passive` | **OK** - always valid |
| `passive` | any | **OK** - always valid |
| `input` | `output` | **OK** - normal signal connection |
| `input` | `power_out` | **OK** - signal input driven by power rail |
| `bidirectional` | `bidirectional` | **OK** - shared bus |
| `bidirectional` | `output` | **WARNING** - possible contention if both drive simultaneously |

---

## 5. Expanded Rule Set (Stage 2 target: ~45 rules)

### 5.1 New T3 Rules (continuing from T3-08)

| Rule ID | Level | Trigger condition |
|---------|-------|-------------------|
| T3-09 | Violation | Relay coil (component type `relay`) has no flyback diode (`diode`, `schottky_diode`, or `tvs_diode`) on its coil net |
| T3-10 | Violation | Optocoupler: input side (A/K) and output side (C/E) share any net (defeats galvanic isolation) |
| T3-11 | Warning | Transformer: primary net (P1/P2) and secondary net (S1/S2) share any net |
| T3-12 | Violation | IGBT gate on a net with no driver or bias resistor (mirrors T3-03) |
| T3-13 | Warning | Comparator output (`open_drain` type) has no pull-up resistor on its output net |
| T3-14 | Warning | DC motor has no freewheeling diode on the supply net |
| T3-15 | Warning | Crystal without at least two load capacitors, one on each pin |
| T3-16 | Warning | Potentiometer wiper pin W has no net connection |
| T3-17 | Warning | RGB LED - any of R/G/B pins without a series resistor on that pin's net |
| T3-18 | Warning | Power rail naming mismatch: `power_vcc` component on a net not named VCC / VCC_x (configurable) |
| T3-INFO-02 | Info | Relay detected - flyback diode check may be insufficient for inductive loads above 500mA |

### 5.2 Pin-Type Conflict Rules (T4 tier - new tier)

For Stage 2, introduce **Tier 4** (pin-type conflict checks), operating on the pin-type annotation map:

| Rule ID | Level | Trigger |
|---------|-------|---------|
| T4-01 | Violation | output + output on same net (bus contention) |
| T4-02 | Violation | power_out + power_out on same net (supply short) |
| T4-03 | Violation | output + power_out on same net |
| T4-04 | Warning | input pin not connected to any net |
| T4-05 | Warning | power_in pin not connected to any net |
| T4-06 | Warning | bidirectional + output on same net (possible contention) |
| T4-07 | Info | open_drain output on net with no pull-up resistor |

---

## 6. Implementation Plan

### Step 1 - Schema expansion (before any code)
1. Add new types to `circuit_v01.json` enum (§9 of contracts.md process)
2. Add new variants to `ComponentType` in `shared/ohmatic-types/src/circuit.rs`
3. Add entries to `verifier/config/component_registry.toml` for new types (bbox, ref_prefix, description)
4. Add ≥1 example circuit using each new type to `dataset/examples.json`
5. Update `contracts.md` §9 with new types and new T3/T4 rules

### Step 2 - Pin type annotation system
1. Create `shared/ohmatic-types/src/pin_types.rs` with `PinType` enum and `fn pin_type_for(ct: &ComponentType, pin_name: &str) -> PinType`
2. This is a lookup table, no external data source needed

### Step 3 - Rule implementation
1. Add T3-09 through T3-18 to `verifier/src/drc/electrical_rules.rs`
2. Create `verifier/src/drc/pin_conflict.rs` with Tier 4 rules
3. Create `run_tier4` in `verifier/src/lib.rs` and call it from the HTTP handler alongside `run_tier3`

### Step 4 - Test expansion
1. Unit tests for each new rule (pass + violation)
2. Seed circuit test: all new example circuits pass all tiers without Violation-level findings

---

## 7. What Still Needs Research (before implementation)

- **Relay rated current threshold**: at what current does the flyback diode rule upgrade from Warning to Violation? (EE judgment call - suggest always Violation for Stage 2)
- **Crystal load capacitance values**: rules involving component values require parsing the `value` field string. Define a value-parsing utility.
- **Power rail naming conventions**: should we enforce VCC / VCC_3V3 / VCC_5V naming or leave it configurable?
- **T4 tier sequencing**: does a T4 failure block Tier 3? (Suggest: no - run T3 and T4 in parallel, both → warnings, never 422)

---

## 8. Files to Change in Stage 2

| File | Change |
|------|--------|
| `shared/schema/circuit_v01.json` | Add 28 new type strings to `components[].type.enum` |
| `shared/ohmatic-types/src/circuit.rs` | Add 28 new `ComponentType` variants |
| `shared/ohmatic-types/src/pin_types.rs` | NEW - PinType enum + lookup table |
| `shared/ohmatic-types/src/lib.rs` | Export `pin_types` module |
| `verifier/config/component_registry.toml` | Add 28 entries (bbox, ref_prefix, description) |
| `verifier/src/drc/electrical_rules.rs` | Add T3-09 through T3-18 |
| `verifier/src/drc/pin_conflict.rs` | NEW - T4-01 through T4-07 |
| `verifier/src/drc/mod.rs` | Export `pin_conflict` |
| `verifier/src/lib.rs` | Wire `run_tier4` into handler |
| `dataset/examples.json` | Add ≥28 example circuits (one per new type) |
| `shared/docs/contracts.md` | Document new types and rules in §7 and §9 |
| `verifier/BACKLOG.md` | Close ARCH-02, ARCH-03; add new backlog items |
