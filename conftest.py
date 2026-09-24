"""Put the repo root on sys.path so tests import `capture` and `subagent_config`.

pytest already inserts the rootdir (this dir, which holds this conftest) at the
front of sys.path, but we do it explicitly so the suite runs the same way from
any cwd or invocation style.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
