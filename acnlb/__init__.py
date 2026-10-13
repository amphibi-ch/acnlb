"""acnlb — alpha CN Legal Bench.

A work-product-and-rubric benchmark harness for Chinese-law tasks, implementing
the item schema, rubric format, CN negative-point taxonomy, and scoring loop
specified in the design doc (CN-Legal-Benchmark-Design.md, sections 3.3-3.8).

The public surface is the CLI: ``python -m acnlb``. Everything else is
implementation detail. The scoring layer is pure; model access is
OpenAI-compatible HTTP only.
"""

__version__ = "0.1.0"

PROTOCOL_VERSION = "acnlb-protocol-1"
SCHEMA_VERSION = "acnlb-item-1"
