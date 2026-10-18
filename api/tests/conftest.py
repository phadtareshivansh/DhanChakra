"""Pytest bootstrap: make the `app` package importable no matter how the
suite is invoked (from /app inside the container, or from the api/ dir on a
host). Tests import application modules as `app.*` to match runtime packaging.
"""

import os
import sys

API_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if API_ROOT not in sys.path:
    sys.path.insert(0, API_ROOT)
