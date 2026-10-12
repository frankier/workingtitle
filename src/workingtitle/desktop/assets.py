"""Compatibility alias for the shared devserver asset builder.

The default cache is now .workingtitle-build; pass cache_dir=".desktop-build"
to retain an existing cache.
"""

import sys
from ..devserver import assets as _assets

sys.modules[__name__] = _assets
