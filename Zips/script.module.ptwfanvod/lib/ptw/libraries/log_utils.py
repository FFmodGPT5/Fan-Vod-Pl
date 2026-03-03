"""
    FanVodPL Add-on

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
import cProfile
import json
import pstats
import time
import re
from io import StringIO
import sys

import xbmc
from xbmc import LOGDEBUG, LOGINFO, LOGWARNING, LOGERROR, LOGFATAL  # noqa: F401

from past.builtins import basestring

from ptw.libraries import control


# loglevel == -1 (NONE, nothing at all is logged to the log)
# loglevel == 0 (NORMAL, shows LOGINFO, LOGWARNING, LOGERROR and LOGFATAL) - Default kodi behaviour
# loglevel == 1 (DEBUG, shows all) - Behaviour if you toggle debug log in the GUI


name = control.addonInfo("name")


logsilent = control.setting("logsilent") == "true"
logexceptionsilent = control.setting("logexceptionsilent") == "true"


#: Custom log level names.
custom_log_levels = {
    "sources": LOGDEBUG,
    "indexer": LOGDEBUG,
    "module": LOGDEBUG,
    }


def log(msg, level=LOGINFO):
    """Nicer logging (with addon name)."""
    # override message level to force logging when addon logging turned on
    # Przyszla opcja ?
    #    if control.setting("addon_debug") == "true" and level == LOGDEBUG:
    #        level = LOGINFO
    level = custom_log_levels.get(level, level)
    # xbmc_log(f'{level=}',1)
    if "EXCEPTION Thrown:" not in msg:
        level = 0 if logsilent else level
    else:
        level = 0 if logsilent and logexceptionsilent else level
        pass
    msg = log.format.sub(3*'\052', str(msg))
    msg = re.sub("(?<=session_id=)[^&]*", 3*'\052', msg)
    try:
        xbmc_log(f"[{name}]  {msg}", level)
    except Exception as exc:
        try:
            if not isinstance(level, int):
                level = LOGINFO
            xbmc_log(f"Logging Failure: {exc}", level)
        except Exception:
            pass  # just give up


def fflog(msg, level=LOGINFO, fn=False, deep=1):
    file = sys._getframe(deep).f_code.co_filename
    file = file.rpartition('/')[-1]
    file = file.rpartition('\\')[-1]  # Windows
    caller = sys._getframe(deep).f_code.co_name
    level = custom_log_levels.get(level, level)
    if level == LOGDEBUG or _is_debugging() or fn:
        log(f"[{file}]  [{caller}]  {msg}", level)
    else:
        log(f"[{file}]  {msg}", level)


def _flog():
    subn = ['%ss' % n for n in ('librarie', 'api')]
    subm = __import__(f'ptw.{subn[0]}.{subn[-1]}')
    while subn:
        subm = getattr(subm, subn.pop(0))
        # kkk = [k for k in dir(subm) if k[:1] != '_' and len(k) > 1 for v in (getattr(subm, k),) if isinstance(v, str)]
        # control.log(f'{subm=} {kkk=}',1)
    fmt = [getattr(subm, k) for k in dir(subm) if k[:1] != '_' and len(k) > 1
                   for v in (getattr(subm, k),) if isinstance(v, str)]
    # fmt = [getattr(subm, k) for k in kkk]  # nie jestem tego pewien
    # fmt = [re.escape(f) for f in fmt]  # czy to by się nie przydało ?
    fmt = '|'.join(fmt)
    # control.log(f'{fmt=}',1)
    oth  = [control.setting("tm.user"), control.setting('tm.user_bearer'), ]
    oth += [control.setting("fanart.tv.user"), control.setting('fanart.tv.dev'), ]
    oth += [control.setting("TVDb_ApiKey"), control.setting('TVDb_UserKey'), ]
    oth = list(filter(None, oth))  # empty
    oth = list(dict.fromkeys(oth))  # duplicates
    if oth:
        # control.log(f'{oth=}',1)
        # oth = [re.escape(f) for f in oth]  # czy to by się nie przydało ?
        fmt += '|' + '|'.join(oth)
        pass
    # a czy to nie jest potrzebne?
    # fmt = fmt.split('|')
    # fmt = [re.escape(f) for f in fmt]  # o to chodzi
    # fmt = '|'.join(fmt)
    return re.compile(fr'({fmt})', re.IGNORECASE)


class Profiler(object):
    def __init__(self, file_path, sort_by="time", builtins=False):
        self._profiler = cProfile.Profile(builtins=builtins)
        self.file_path = file_path
        self.sort_by = sort_by

    def profile(self, f):
        def method_profile_on(*args, **kwargs):
            try:
                self._profiler.enable()
                result = self._profiler.runcall(f, *args, **kwargs)
                self._profiler.disable()
                return result
            except Exception as e:
                log("Profiler Error: %s" % e, LOGWARNING)
                return f(*args, **kwargs)

        def method_profile_off(*args, **kwargs):
            return f(*args, **kwargs)

        if _is_debugging():
            return method_profile_on
        else:
            return method_profile_off

    def __del__(self):
        self.dump_stats()

    def dump_stats(self):
        if self._profiler is not None:
            s = StringIO()
            params = (
                (self.sort_by,)
                if isinstance(self.sort_by, basestring)
                else self.sort_by
            )
            ps = pstats.Stats(self._profiler, stream=s).sort_stats(*params)
            ps.print_stats()
            if self.file_path is not None:
                with open(self.file_path, "w") as f:
                    f.write(s.getvalue())


def trace(method):
    def method_trace_on(*args, **kwargs):
        start = time.time()
        result = method(*args, **kwargs)
        end = time.time()
        log(
            "{name!r} time: {time:2.4f}s args: |{args!r}| kwargs: |{kwargs!r}|".format(
                name=method.__name__, time=end - start, args=args, kwargs=kwargs
            ),
            LOGDEBUG,
        )
        return result

    def method_trace_off(*args, **kwargs):
        return method(*args, **kwargs)

    if _is_debugging():
        return method_trace_on
    else:
        return method_trace_off


# based on forum.kodi.tv/showthread.php?tid=218843&pid=2448420#pid2448420
def _is_debugging():
    command = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "Settings.getSettings",
        "params": {"filter": {"section": "system", "category": "logging"}},
    }
    js_data = execute_jsonrpc(command)
    for item in js_data.get("result", {}).get("settings", {}):
        if item["id"] == "debug.showloginfo":
            return item["value"]

    return False


def execute_jsonrpc(command):
    if not isinstance(command, basestring):
        command = json.dumps(command)
    response = control.jsonrpc(command)
    return json.loads(response)


log.format = _flog()
xbmc_log = xbmc.log
xbmc.log = log  # to nadpisuje funkcję Kodi
