"""Set a per-executable writable matplotlib cache before application imports."""

import os
from pathlib import Path
import sys
import tempfile


if getattr(sys, "frozen", False) and not os.environ.get("MPLCONFIGDIR"):
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    config_dir = base / Path(sys.executable).stem / "matplotlib"
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    else:
        os.environ["MPLCONFIGDIR"] = str(config_dir)
