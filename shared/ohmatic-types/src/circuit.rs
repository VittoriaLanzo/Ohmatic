// GENERATED — do not hand-edit. Run: make codegen
// Source: shared/schema/circuit_v01.json

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct OhmaticCircuitV01 {
    pub metadata: CircuitMetadata,
    pub components: Vec<Component>,
    pub nets: Vec<Net>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CircuitMetadata {
    pub title: String,
    pub description: String,
    pub version: String,
    pub tags: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Component {
    pub id: String,
    #[serde(rename = "type")]
    pub component_type: ComponentType,
    pub value: String,
    pub part: String,
    pub x: f64,
    pub y: f64,
    pub pins: std::collections::HashMap<String, String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum ComponentType {
    Resistor,
    Capacitor,
    Led,
    Diode,
    TransistorNpn,
    TransistorPnp,
    MosfetN,
    MosfetP,
    IcTimer,
    IcOpamp,
    IcRegulator,
    IcLogic,
    IcMcu,
    IcDriver,
    PowerVcc,
    PowerGnd,
    Connector,
    Crystal,
    Inductor,
    Button,
    Speaker,
    Sensor,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Net {
    pub name: String,
    pub pins: Vec<String>,
}
