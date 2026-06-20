"""Component-type -> KiCad symbol/footprint hints.

KiCad-specific knowledge (symbol lib_id, a sensible default land pattern) that does
not belong in verifier/config/component_registry.toml; keep the two in sync by type
key. An unknown type falls back to GENERIC so export never fails on a new component.

`footprint` is "" when there is no single canonical land pattern (power symbols,
ICs whose package is only known from `part`/the BOM). KiCad imports a footprint-less
component fine - the user assigns it on the board - so a blank is always safe.
"""

# type -> (lib_id, ref_prefix, default_footprint)
_MAP: dict[str, tuple[str, str, str]] = {
    "resistor":      ("Device:R", "R", "Resistor_SMD:R_0603_1608Metric"),
    "potentiometer": ("Device:R_Potentiometer", "RV", ""),
    "thermistor":    ("Device:Thermistor", "TH", ""),
    "varistor":      ("Device:R_Variable", "RV", ""),
    "capacitor":     ("Device:C", "C", "Capacitor_SMD:C_0603_1608Metric"),
    "inductor":      ("Device:L", "L", ""),
    "ferrite_bead":  ("Device:FerriteBead", "FB", ""),
    "diode":         ("Device:D", "D", ""),
    "led":           ("Device:LED", "D", "LED_SMD:LED_0603_1608Metric"),
    "led_rgb":       ("Device:LED_RGB", "D", ""),
    "zener_diode":   ("Device:D_Zener", "D", ""),
    "schottky_diode":("Device:D_Schottky", "D", ""),
    "tvs_diode":     ("Device:D_TVS", "D", ""),
    "photodiode":    ("Device:D_Photo", "D", ""),
    "diode_bridge":  ("Device:D_Bridge_+AA-", "D", ""),
    "transistor_npn":("Device:Q_NPN_BCE", "Q", ""),
    "transistor_pnp":("Device:Q_PNP_BCE", "Q", ""),
    "mosfet_n":      ("Device:Q_NMOS_GDS", "Q", ""),
    "mosfet_p":      ("Device:Q_PMOS_GDS", "Q", ""),
    "igbt":          ("Device:Q_IGBT_GCE", "Q", ""),
    "phototransistor":("Device:Q_Photo_NPN", "Q", ""),
    "fuse":          ("Device:Fuse", "F", ""),
    "relay":         ("Relay:Relay_SPDT", "K", ""),
    "transformer":   ("Device:Transformer_1P_1S", "T", ""),
    "crystal":       ("Device:Crystal", "Y", ""),
    "speaker":       ("Device:Speaker", "LS", ""),
    "microphone":    ("Device:Microphone", "MK", ""),
    "battery":       ("Device:Battery", "BT", ""),
    "button":        ("Switch:SW_Push", "SW", ""),
    "switch":        ("Switch:SW_SPST", "SW", ""),
    "antenna":       ("Device:Antenna", "AE", ""),
    "motor_dc":      ("Motor:Motor_DC", "M", ""),
    "power_vcc":     ("power:VCC", "#PWR", ""),
    "power_gnd":     ("power:GND", "#PWR", ""),
    "power_vee":     ("power:VEE", "#PWR", ""),
    "power_3v3":     ("power:+3V3", "#PWR", ""),
    "power_5v":      ("power:+5V", "#PWR", ""),
    "power_12v":     ("power:+12V", "#PWR", ""),
}

# Every ic_* / connector / sensor etc. that has no dedicated stock symbol renders as
# a generic box. It is still electrically correct (pins carry net labels); a nicer
# lib_id is a later cosmetic upgrade, tracked against this table.
GENERIC: tuple[str, str, str] = ("ohmatic:GENERIC", "U", "")


def lookup(ctype: str) -> tuple[str, str, str]:
    """(lib_id, ref_prefix, default_footprint) for a component type."""
    return _MAP.get(ctype, GENERIC)


def is_power(ctype: str) -> bool:
    return ctype.startswith("power_")
