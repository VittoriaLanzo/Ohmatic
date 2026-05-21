# Ohmatic Circuit Schema v0.1

## Overview

Ohmatic represents electronic circuits as structured JSON, enabling AI models to generate valid schematics programmatically.

## Schema Format

```json
{
  "metadata": {
    "title": "Circuit name",
    "description": "What the circuit does",
    "version": "0.1",
    "tags": ["tag1", "tag2"]
  },
  "components": [
    {
      "id": "unique_id",
      "type": "component_type",
      "part": "part_number",
      "value": "component_value",
      "pins": {"pin_name": "net_node", ...},
      "x": 0,
      "y": 0
    }
  ],
  "nets": [
    {
      "name": "net_name",
      "pins": ["component_id.pin_name", ...]
    }
  ]
}
```

## Metadata

- **title** (string): Short descriptive name
- **description** (string): What the circuit does, its purpose
- **version** (string): Schema version, must be "0.1"
- **tags** (array): Keywords like ["analog", "power", "signal-processing"]

## Components

### Fields

- **id** (string): Unique identifier, e.g., "R1", "U2", "LED1"
- **type** (string): Component class (see valid types below)
- **part** (string): Part number or description, e.g., "1N4148", "LM358"
- **value** (string): Component value, e.g., "10kΩ", "100µF", "2N2222"
- **pins** (object): Map of pin names to node identifiers
  - Key: pin identifier (e.g., "1", "2", "A", "B", "GND")
  - Value: unique node reference within circuit (e.g., "1", "2", "3")
- **x** (number): Horizontal position (0-300 range recommended)
- **y** (number): Vertical position (0-300 range recommended)

### Valid Component Types

#### Passive Components
- `resistor` - Resistor (R)
- `capacitor` - Capacitor (C)
- `inductor` - Inductor (L)

#### Semiconductors
- `diode` - Generic diode
- `led` - Light emitting diode
- `transistor_npn` - NPN BJT
- `transistor_pnp` - PNP BJT
- `mosfet_n` - N-channel MOSFET
- `mosfet_p` - P-channel MOSFET

#### Integrated Circuits (ICs)
- `ic_opamp` - Operational amplifier
- `ic_timer` - Timer IC (e.g., 555)
- `ic_regulator` - Voltage regulator
- `ic_logic` - Logic gate/buffer
- `ic_mcu` - Microcontroller
- `ic_driver` - Motor/LED driver

#### Other
- `power_vcc` - Positive supply
- `power_gnd` - Ground reference
- `connector` - External connector
- `crystal` - Crystal oscillator
- `button` - Push button switch
- `speaker` - Speaker/audio output
- `sensor` - Generic sensor

## Nets

Nets represent electrical connections between component pins.

### Fields

- **name** (string): Net identifier, e.g., "VCC", "GND", "Signal_A"
- **pins** (array): List of connected pins
  - Format: `"component_id.pin_name"`
  - Example: `["R1.2", "LED1.A", "GND1.1"]`

## Constraints

1. **Connectivity**
   - Every pin in a net must exist in a component
   - Every component pin must appear in exactly one net
   - Each net must have at least 2 pins

2. **Required Nets**
   - `"VCC"` net must exist (positive supply)
   - `"GND"` net must exist (ground reference)

3. **Validity**
   - All component IDs must be unique
   - All pin references must be valid
   - No isolated pins or components

## Example Circuit: Simple LED

```json
{
  "metadata": {
    "title": "Simple LED Circuit",
    "description": "LED with current limiting resistor",
    "version": "0.1",
    "tags": ["basic", "led"]
  },
  "components": [
    {
      "id": "VCC1",
      "type": "power_vcc",
      "part": "VCC",
      "value": "5V",
      "pins": {"1": "vcc_node"},
      "x": 10,
      "y": 10
    },
    {
      "id": "R1",
      "type": "resistor",
      "part": "1/4W",
      "value": "330Ω",
      "pins": {"1": "vcc_node", "2": "led_cathode"},
      "x": 50,
      "y": 10
    },
    {
      "id": "LED1",
      "type": "led",
      "part": "RED",
      "value": "",
      "pins": {"A": "led_cathode", "K": "gnd_node"},
      "x": 90,
      "y": 10
    },
    {
      "id": "GND1",
      "type": "power_gnd",
      "part": "GND",
      "value": "",
      "pins": {"1": "gnd_node"},
      "x": 130,
      "y": 10
    }
  ],
  "nets": [
    {"name": "VCC", "pins": ["VCC1.1", "R1.1"]},
    {"name": "Net1", "pins": ["R1.2", "LED1.A"]},
    {"name": "GND", "pins": ["LED1.K", "GND1.1"]}
  ]
}
```

## Validation Rules

A valid circuit must satisfy:

1. ✓ Contains metadata with all required fields
2. ✓ Components array is non-empty
3. ✓ Nets array is non-empty
4. ✓ All component IDs are unique
5. ✓ All component types are valid
6. ✓ All pins in nets exist in components
7. ✓ All component pins appear in exactly one net
8. ✓ VCC and GND nets exist
9. ✓ No net has fewer than 2 pins

## Tips for Generation

- Use meaningful component IDs (R1, R2, C1, etc.)
- Keep coordinates in 0-300 range for compact layouts
- Always include bypass capacitors for ICs
- Use realistic part numbers and values
- Include all power and ground connections explicitly
- Keep descriptions brief but descriptive
- Use appropriate tags for circuit category

## Version History

- **v0.1** (Initial): Basic component and net representation
