# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, unicode_literals, print_function

import functools
import traceback
import sys

import xbmc

# import xbmcaddon

# logsilent = xbmcaddon.Addon().getSetting("logsilent") == "true"
# # xbmc.log(f'[exc.py]  {logsilent=}', 1)

# name = xbmcaddon.Addon().getAddonInfo("name")


# try:
#    from future import standard_library
#    from future.builtins import *
#    standard_library.install_aliases()
# except ImportError:
#    print('WARNING: no furure module')

INDENT = 44 * " "


def _get_backtrace(skip=2, prefix=None):
    """
    Get backtrace lines.

    Parameters
    ----------
    skip : int
        Number of entries to skip. To avoid debug functions in backtrace.
    prefix : str or None
        Text to prefix every line.

    Returns
    -------
    str
        Backtrace string lines. All lines separated by EOL not by backtrace entry.
    """
    callstack = traceback.format_stack()
    if skip > 0:
        callstack = callstack[:-skip]
    callstack = ((prefix or "") + ln for e in callstack for ln in e.splitlines())
    return list(callstack)


def log_exception(level=None, deep=1):
    """
    Log exception.

    Parameters
    ----------
    e : Exception
        Exception to log.
    level : int or None
        Kodi log level or None for default level (DEBUG).
    """
    if level is None:
        level = xbmc.LOGDEBUG
    msg = "EXCEPTION Thrown: -->Python callback/script returned the following error<--\n"
    msg += traceback.format_exc()
    msg += "-->End of Python script error report<--"
    file = sys._getframe(deep).f_code.co_filename
    file = file.rpartition('/')[-1]
    file = file.rpartition('\\')[-1]  # Windows
    caller = sys._getframe(deep).f_code.co_name
    msg = f"[{file}]  [{caller}]  " + msg
    xbmc.log(msg, level)
    # xbmc_log(f"[{name}]  {msg}", level)


def fflog_exc(level=None):
    log_exception(level, 2)


def log(msg, level=None):
    msg = str(msg)
    if level is None:
        level = xbmc.LOGINFO
    # level = 0 if logsilent else level
    xbmc.log(msg, level)
    # xbmc_log(f"[{name}]  {msg}", level)


def fflog(msg, level=None, fn=True, deep=1):
    file = sys._getframe(deep).f_code.co_filename
    file = file.rpartition('/')[-1]
    file = file.rpartition('\\')[-1]  # Windows
    caller = sys._getframe(deep).f_code.co_name
    # level = 0 if logsilent else level
    log(f"[{file}]  [{caller}]  {msg}", level)


def stacktrace(func):
    """Decorator for trace function enter.

    See: https://stackoverflow.com/a/48653175
    """

    @functools.wraps(func)
    def wrapped(*args, **kwds):
        # Get all but last line returned by traceback.format_stack()
        # which is the line below.
        prefix = "[XXX] "
        callstack = "\n".join(
            prefix + e.rstrip() for e in traceback.format_stack()[:-1]
        )
        callstack = "\n".join(">{}<".format(e) for e in traceback.format_stack()[:-1])
        print("{}() called:".format(func.__name__))
        print(callstack)
        return func(*args, **kwds)

    return wrapped


# xbmc_log = xbmc.log
