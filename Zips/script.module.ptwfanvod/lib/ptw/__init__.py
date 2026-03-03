# AUTO-CLEAR __pycache__ po aktualizacji
# Rozwiazuje problem: Kodi zostawia stare .pyc po update, co powoduje crash
import os as _os
import shutil as _shutil

def _clear_pycache():
    try:
        _base = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
        for root, dirs, files in _os.walk(_base):
            for d in dirs:
                if d == "__pycache__":
                    _shutil.rmtree(_os.path.join(root, d), ignore_errors=True)
    except Exception:
        pass

_clear_pycache()

# Force patching Kodi API
# Basic logging.
from .libraries.log_utils import log  # noqa: F401

import sys
PY2 = sys.version_info < (3, 0)


# Monkey-patching datetime.strptime
# see: https://forum.kodi.tv/showthread.php?tid=112916&pid=2953239
# see: https://bugs.python.org/issue27400
import datetime as datetime_module            # noqa: E402
from datetime import datetime as _datetime    # noqa: E402

if not getattr(datetime_module, '_datetime_is_patched', False):
    class datetime(_datetime):
        @classmethod
        def strptime(cls, date_string: str, format: str) -> _datetime:
            # log(f"Monkey-patching datetime.strptime  {date_string=}", 1)
            try:
                return _dt_strptime(date_string, format)
            except TypeError:
                import time
                return datetime(*(time.strptime(date_string, format)[0:6]))

    _dt_strptime = _datetime.strptime
    datetime_module.datetime = datetime
    datetime_module._datetime = _datetime
    datetime_module._datetime_is_patched = True

