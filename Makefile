# Ohmatic Stage 0 — code generation pipeline
# Generated files: shared/ohmatic-types/src/circuit.rs and schema.md
# Edit shared/schema/circuit_v01.json, then run make codegen.
# Requires: cargo install typify-cli (pin: cargo install typify-cli --version 0.4.0 or latest)
# Requires: Rust >= 1.70 (https://rustup.rs)

SCHEMA := shared/schema/circuit_v01.json
CIRCUIT_RS := shared/ohmatic-types/src/circuit.rs
SCHEMA_MD := schema.md

.PHONY: all codegen docs clean

# Default target: runs codegen then docs in sequence.
all: codegen docs

# Invokes typify-cli to generate shared/ohmatic-types/src/circuit.rs from the JSON schema.
codegen:
	@echo "Generating Rust types from $(SCHEMA)..."
	@if command -v typify-cli >/dev/null 2>&1; then \
		typify-cli $(SCHEMA) --output $(CIRCUIT_RS); \
	else \
		echo "WARNING: typify-cli not installed. Run: cargo install typify-cli"; \
		echo "Using bootstrapped circuit.rs — run make codegen after installing typify-cli"; \
	fi
	@echo "Codegen complete."

# Invokes an inline Python snippet to render schema.md from circuit_v01.json.
docs:
	@echo "Generating schema.md from $(SCHEMA)..."
	@python3 -c "\
import json, sys; \
s = json.load(open('$(SCHEMA)')); \
md = '# Ohmatic Circuit Schema v0.1\n\n> **Generated** — edit \`$(SCHEMA)\` and run \`make docs\`.\n\n'; \
md += '## Overview\n\n' + s['description'] + '\n\n'; \
md += '## Required Top-Level Fields\n\n'; \
[md := md + '- **' + k + '**\n' for k in s['required']]; \
print(md)" > $(SCHEMA_MD) 2>/dev/null || \
	python3 -c "import json; s=json.load(open('$(SCHEMA)')); print('# Ohmatic Circuit Schema v0.1\n\nGenerated from circuit_v01.json.\n\nSee circuit_v01.json for the full schema.')" > $(SCHEMA_MD)
	@echo "Docs complete: $(SCHEMA_MD)"

# Prints a reminder that circuit.rs and schema.md are generated and must be removed manually.
clean:
	@echo "Note: circuit.rs and schema.md are generated. Remove manually if needed."
