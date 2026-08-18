"""Make the helper Workflow modules in this directory importable by name.

Workflows must live in their own module -- the sandbox re-imports the module a
Workflow is defined in, and defining one inside a test module would drag pytest
into the sandbox. Those helpers are then imported as top-level modules
(``_unwrapped_import_workflow``), which only resolves if this directory is on
``sys.path``. Pytest's rootdir insertion does not reliably provide that, so make
it explicit.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
