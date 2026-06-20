"""KiCad emitters for OhmaticCircuitV01.

Pure-stdlib serializers over KiCad's open, documented S-expression file formats.
No KiCad code is imported, linked, or bundled - so nothing copyleft (GPL `pcbnew`,
`kicad-cli`) ever touches this process, and the output is unencumbered. The LICENSE
already declares outputs unrestricted; this keeps the *generator* clean too.

If we ever want KiCad-grade output (Gerbers, autoroute, 3D), shell out to
`kicad-cli` (GPLv3) as a separate, user-installed executable - never bundle it.
That arm's-length call is mere aggregation, and the exporter process is the license
firewall that keeps it from reaching the rest of Ohmatic.
"""
from .export import FORMATS, SCHEMA_VERSIONS, build_export, capabilities

__all__ = ["FORMATS", "SCHEMA_VERSIONS", "build_export", "capabilities"]
