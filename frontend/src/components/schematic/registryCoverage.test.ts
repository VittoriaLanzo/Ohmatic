import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { KNOWN_COMPONENT_TYPES, type KnownComponentType } from "../../types/circuit";
import { renderSchematicSymbol, SCHEMATIC_SYMBOL_PROVENANCE, SCHEMATIC_SYMBOLS, UNKNOWN_SYMBOL_TYPE } from "./symbols";
import { SCHEMATIC_SYMBOL_SVGS } from "./symbolDataset";

const REGISTRY_TOML = readFileSync(resolve(process.cwd(), "../verifier/config/component_registry.toml"), "utf8");
const REGISTRY_TYPES = Array.from(REGISTRY_TOML.matchAll(/^\[([a-z0-9_]+)\]$/gm))
  .map((match) => match[1])
  .filter((type) => type !== "defaults") as KnownComponentType[];

function geometryOnly(markup: string) {
  return markup
    .replace(/\sdata-symbol-kind="[^"]+"/g, "")
    .replace(/\sdata-symbol-mode="[^"]+"/g, "");
}

describe("schematic registry coverage", () => {
  it("declares local CC0 provenance for the inline symbol geometry", () => {
    expect(SCHEMATIC_SYMBOL_PROVENANCE).toEqual({
      source: "self-authored-inline-svg-dataset",
      license: "CC0-1.0",
      externalAssets: false,
    });
  });

  it("has a CC0 ANSI and IEC SVG dataset entry for every registry type", () => {
    expect(Object.keys(SCHEMATIC_SYMBOL_SVGS).sort()).toEqual([...REGISTRY_TYPES].sort());

    for (const type of REGISTRY_TYPES) {
      expect(SCHEMATIC_SYMBOL_SVGS[type], type).toBeDefined();
      expect(SCHEMATIC_SYMBOL_SVGS[type].ansi.trim(), `${type} ansi svg`).toMatch(/^</);
      expect(SCHEMATIC_SYMBOL_SVGS[type].iec.trim(), `${type} iec svg`).toMatch(/^</);
      expect(SCHEMATIC_SYMBOL_SVGS[type].ansi, `${type} ansi/iec dataset`).not.toBe(SCHEMATIC_SYMBOL_SVGS[type].iec);
    }
  });

  it("keeps frontend known component types aligned with the read-only registry", () => {
    expect([...KNOWN_COMPONENT_TYPES].sort()).toEqual([...REGISTRY_TYPES].sort());
  });

  it("has explicit ANSI and IEC symbol coverage for every known registry type", () => {
    for (const type of REGISTRY_TYPES) {
      expect(SCHEMATIC_SYMBOLS[type], type).toBeDefined();
      expect(SCHEMATIC_SYMBOLS[type].ansi.kind, `${type} ansi`).not.toBe(UNKNOWN_SYMBOL_TYPE);
      expect(SCHEMATIC_SYMBOLS[type].iec.kind, `${type} iec`).not.toBe(UNKNOWN_SYMBOL_TYPE);
      expect(SCHEMATIC_SYMBOLS[type].ansi.kind, `${type} mode-specific kind`).not.toBe(SCHEMATIC_SYMBOLS[type].iec.kind);
      expect(Object.keys(SCHEMATIC_SYMBOLS[type].anchors).length, `${type} anchors`).toBeGreaterThan(0);
    }
  });

  it("renders distinct ANSI and IEC geometry for every registry type", () => {
    for (const type of REGISTRY_TYPES) {
      expect(geometryOnly(renderToStaticMarkup(renderSchematicSymbol(type, "ansi"))), `${type} ansi/iec visual`).not.toBe(
        geometryOnly(renderToStaticMarkup(renderSchematicSymbol(type, "iec")))
      );
    }
  });

  it("keeps symbols inline and free of external asset references", () => {
    for (const type of REGISTRY_TYPES) {
      for (const mode of ["ansi", "iec"] as const) {
        const markup = renderToStaticMarkup(renderSchematicSymbol(type, mode));

        expect(markup, `${type} ${mode}`).not.toMatch(/<image\b|<use\b|\bhref=|\bxlink:href=|url\(/);
      }
    }
  });
});
