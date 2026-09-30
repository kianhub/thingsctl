"""Isolated launcher for the packaged standard-library runtime."""
import os
import sys
from pathlib import Path

if sys.version_info < (3, 9):
    raise SystemExit("ThingsCTL requires Python 3.9 or later")
plugin_root = Path(__file__).resolve().parent.parent
os.environ.setdefault("THINGSCTL_PLUGIN_ROOT", str(plugin_root))
sys.path.insert(0, str(plugin_root / "runtime"))
from thingsctl_pkg.cli import main
raise SystemExit(main())
