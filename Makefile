# Ohmatic Stage 0 — code generation pipeline
# make docs generates schema.md from the schema; make codegen regenerates circuit.rs (currently bootstrapped by hand).
# Edit shared/schema/circuit_v01.json, then run make codegen.
# Requires: cargo install typify-cli --version 0.4.0
# Requires: Rust >= 1.70 (https://rustup.rs)
# Requires: Python >= 3.8 (https://python.org) — make docs uses walrus operator

SCHEMA := shared/schema/circuit_v01.json
CIRCUIT_RS := shared/ohmatic-types/src/circuit.rs
SCHEMA_MD := schema.md

.PHONY: all codegen docs clean

# Default target: docs only. codegen is NOT in the default target — circuit.rs is hand-authored.
all: docs

# !! DANGER: do NOT run this target. circuit.rs is hand-authored (transparent ComponentType
# newtype + component_types constants). Running typify-cli overwrites it with a hard enum,
# destroying the data-driven registry design. See shared/ohmatic-types/src/circuit.rs header.
# This target is retained for historical reference only.
codegen:
	@echo "ERROR: codegen is disabled. circuit.rs is hand-authored — see its header comment."
	@echo "To add a new component type, edit verifier/config/component_registry.toml instead."
	@exit 1

# Invokes an inline Python 3.8+ snippet (uses walrus operator) to render schema.md.
docs:
	@echo "Generating schema.md from $(SCHEMA)..."
	@python3 -c "import sys; sys.exit(0) if sys.version_info >= (3,8) else sys.exit('ERROR: Python 3.8+ required for make docs (found ' + sys.version + ')')"
	@python3 -c "\
import json, sys; \
s = json.load(open('$(SCHEMA)')); \
md = '# Ohmatic Circuit Schema v0.1\n\n> **Generated** — edit \`$(SCHEMA)\` and run \`make docs\`.\n\n'; \
md += '## Overview\n\n' + s['description'] + '\n\n'; \
md += '## Required Top-Level Fields\n\n'; \
[md := md + '- **' + k + '**\n' for k in s['required']]; \
print(md)" > $(SCHEMA_MD)
	@echo "Docs complete: $(SCHEMA_MD)"

# Removes only the generated schema.md. circuit.rs is hand-maintained and is not deleted.
clean:
	@rm -f $(SCHEMA_MD)
	@echo "Cleaned: $(SCHEMA_MD)"
