# Ohmatic - schema docs generation
# make docs generates schema.md from shared/schema/circuit_v01.json.
# Requires: Python >= 3.8 (make docs uses the walrus operator).

SCHEMA := shared/schema/circuit_v01.json
SCHEMA_MD := schema.md

.PHONY: all docs clean

all: docs

# Invokes an inline Python 3.8+ snippet (uses walrus operator) to render schema.md.
docs:
	@echo "Generating schema.md from $(SCHEMA)..."
	@python3 -c "import sys; sys.exit(0) if sys.version_info >= (3,8) else sys.exit('ERROR: Python 3.8+ required for make docs (found ' + sys.version + ')')"
	@python3 -c "\
import json, sys; \
s = json.load(open('$(SCHEMA)')); \
md = '# Ohmatic Circuit Schema v0.1\n\n> **Generated** - edit \`$(SCHEMA)\` and run \`make docs\`.\n\n'; \
md += '## Overview\n\n' + s['description'] + '\n\n'; \
md += '## Required Top-Level Fields\n\n'; \
[md := md + '- **' + k + '**\n' for k in s['required']]; \
print(md)" > $(SCHEMA_MD)
	@echo "Docs complete: $(SCHEMA_MD)"

# Removes only the generated schema.md.
clean:
	@rm -f $(SCHEMA_MD)
	@echo "Cleaned: $(SCHEMA_MD)"
