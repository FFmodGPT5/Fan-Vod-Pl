 
# -*- coding: utf-8 -*-

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

import datetime


# --- PREMIUM AUTOPLAY POST-END GUARD (playlist clear + dialog sweep) ---
try:
    import xbmc, xbmcgui, time as _t, threading as _th
    class _FF_PremiumGuard(xbmc.Player):
        def _sweep(self, secs=2.5):
            t_end = _t.time() + secs
            while _t.time() < t_end:
                try: xbmc.PlayList(xbmc.PLAYLIST_VIDEO).clear()
                except Exception: pass
                try: xbmc.executebuiltin('PlayerControl(RepeatOff)')
                except Exception: pass
                try: xbmc.executebuiltin('Dialog.Close(okdialog)')
                except Exception: pass
                try: xbmc.executebuiltin('Dialog.Close(notification)')
                except Exception: pass
                _t.sleep(0.12)  # ~120ms
        def onPlayBackEnded(self): _th.Thread(target=self._sweep, daemon=True).start()
        def onPlayBackStopped(self): _th.Thread(target=self._sweep, daemon=True).start()
    try:
        _FF__premium_guard_instance
    except NameError:
        _FF__premium_guard_instance = _FF_PremiumGuard()
except Exception:
    pass
# --- END PREMIUM AUTOPLAY GUARD ---



# --- HARD KILL OF POST-PLAYBACK POPUPS (premium stop/ended) ---
try:
    import time as _ff_time
    import xbmc as _ff_xbmc
    import xbmcgui as _ff_xbmcgui

    # Global "silence until" timestamp (list for mutability in closures)
    _FF_SILENCE_UNTIL = [0.0]

    # Patch Dialog.ok and Dialog.notification: swallow everything during silence window
    _ff_ok_orig = getattr(_ff_xbmcgui.Dialog, "ok", None)
    if callable(_ff_ok_orig):
        def _ff_ok_silenced(self, heading, message, *args, **kwargs):
            try:
                if _ff_time.time() < _FF_SILENCE_UNTIL[0]:
                    return  # swallow any OK dialog inside the window
            except Exception:
                pass
            return _ff_ok_orig(self, heading, message, *args, **kwargs)
        _ff_xbmcgui.Dialog.ok = _ff_ok_silenced

    _ff_notif_orig = getattr(_ff_xbmcgui.Dialog, "notification", None)
    if callable(_ff_notif_orig):
        def _ff_notif_silenced(self, heading, message, *args, **kwargs):
            try:
                if _ff_time.time() < _FF_SILENCE_UNTIL[0]:
                    return  # swallow any notification inside the window
            except Exception:
                pass
            return _ff_notif_orig(self, heading, message, *args, **kwargs)
        _ff_xbmcgui.Dialog.notification = _ff_notif_silenced

    # Player that opens 3s silence window on seek/stop/end and force-closes dialogs immediately
    class _FF_SilentPlayer(_ff_xbmc.Player):
        def _ff_silence(self, secs=3.0):
            _FF_SILENCE_UNTIL[0] = _ff_time.time() + secs  # 3s global silence
            try:
                _ff_xbmc.executebuiltin('Dialog.Close(okdialog)')
            except Exception:
                pass
            try:
                _ff_xbmc.executebuiltin('Dialog.Close(notification)')
            except Exception:
                pass
            try:
                _ff_xbmc.executebuiltin('Dialog.Close(all,true)')
            except Exception:
                pass
            # clear playlist to avoid 'unplayable index -1' chain popups
            try:
                pl = _ff_xbmc.PlayList(_ff_xbmc.PLAYLIST_VIDEO)
                pl.clear()
            except Exception:
                pass

        def onPlayBackStopped(self):
            self._ff_silence()

        def onPlayBackEnded(self):
            self._ff_silence()

        def onPlayBackSeek(self, time, seekOffset):
            # pre-empt komunikaty po agresywnym przewijaniu
            self._ff_silence()

        def onPlayBackSeekChapter(self, chapter):
            self._ff_silence()

    # Keep a global instance so callbacks stay alive
    try:
        _FF__silent_player_instance
    except NameError:
        _FF__silent_player_instance = _FF_SilentPlayer()
except Exception:
    pass
# --- END HARD KILL OF POST-PLAYBACK POPUPS ---


def _ff_safe_close_ui():
    try:
        # zamknij wszystkie możliwe okna, które mogą zasłaniać/psuć sterowanie
        control.execute('Dialog.Close(progressdialog,true)')
        control.execute('Dialog.Close(progressdialogbg,true)')
        control.execute('Dialog.Close(notification,true)')
        control.execute('Dialog.Close(busydialog,true)')
        control.execute('Dialog.Close(busydialognocancel,true)')
    except Exception:
        pass
    # czekaj max 3 sekundy aż player faktycznie zacznie grać i zamknij notyfikacje
    for _ in range(30):
        try:
            if control.condVisibility('Player.HasMedia') or control.condVisibility('Player.Playing'):
                control.execute('Dialog.Close(notification,true)')
                control.execute('Dialog.Close(progressdialog,true)')
                control.execute('Dialog.Close(progressdialogbg,true)')
                break
        except Exception:
            pass
        control.sleep(100)
import json
import random
import re
import sys
import time
import xbmc  # do aktorów potrzebne
import xbmcgui
import xbmcplugin  # do sortowania potrzebne
#import xbmcaddon
from functools import reduce
from urllib.parse import quote_plus, parse_qsl, unquote, urlencode
from html import unescape, escape
from ast import literal_eval

from ptw.libraries import trakt
from ptw.libraries import control
from ptw.libraries import cleantitle
from ptw.libraries import client
from ptw.libraries import debrid
from ptw.libraries import source_utils
from ptw.libraries import log_utils
from ptw.libraries import PTN
from ptw.libraries import cache
from ptw.libraries import views
from ptw.libraries.log_utils import log, fflog
# from ptw.debug import log, fflog
from ptw.debug import log_exception, fflog_exc

from sqlite3 import dbapi2 as database

try:
    import resolveurl
except Exception as e:
    print(e)
    pass



# ========== [BEGIN] BANNED PHRASES – GLOBAL ==========
# Helper for 'ai' exception and precompiled patterns for additional screening.
import re as _re  # alias to avoid shadowing elsewhere if re is already imported

# --- FORCE AUTOPLAY SAFETY SWITCH (działa nawet po „czystej” instalacji) ---
try:
    import xbmcaddon
    _ADDON = xbmcaddon.Addon()  # plugin id from addon.xml scope
    def _force_setting(key, val):
        try:
            if isinstance(val, bool):
                _ADDON.setSettingBool(key, val)
            else:
                _ADDON.setSetting(key, str(val))
        except Exception:
            pass
    _force_setting('cm.enable.autoplay', True)                 # autoodtwarzanie (menu kontekstowe)
    _force_setting('auto.select.next.item.to.play', True)      # próbuj kolejne linki
    _force_setting('hosts.mode', '2')                          # 2 = AUTOPLAY (zgodnie z Twoją logiką)
except Exception:
    pass
# --- END FORCE AUTOPLAY SAFETY SWITCH ---


# --- UI toggle: show/hide the "Odrzucone" pseudo-folder in GUI ---
SHOW_REJECTED_GUI = False  # False = ukryj; True = pokazuj




def _ff_return_to_last_sources(self, title, items, filtered_items, season, episode):
    # >>> PATCH: Harden return — stop playback, clear playlist, close dialogs
    try:
        handle = int(sys.argv[1])
        xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
    except Exception:
        pass
    try:
        xbmc.executebuiltin('PlayerControl(Stop)')
    except Exception:
        pass
    try:
        pl = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
        pl.clear()
    except Exception:
        pass
    try:
        cw = control.window
        for k in ['FanVodPL.autoplay','FanVodPL.autoplay_free','FanVodPL.autoplay_premium','FanVodPL.forceResolve','FanVodPL.pendingPlay','FanVodPL.resolve_in_progress']:
            cw.clearProperty(k)
    except Exception:
        pass
    try:
        control.execute('Dialog.Close(progressdialog,true)')
        control.execute('Dialog.Close(progressdialogbg,true)')
        control.execute('Dialog.Close(busydialog,true)')
        control.execute('Dialog.Close(busydialognocancel,true)')
        xbmc.executebuiltin('Dialog.Close(yesnoDialog)')
        xbmc.executebuiltin('Dialog.Close(okDialog)')
        control.execute('Dialog.Close(notification,true)')
    except Exception:
        pass
    # <<< PATCH END
    # 1) Twardo anuluj ewentualny resolve/play
    try:
        handle = int(sys.argv[1])
        xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
    except Exception:
        pass
    try:
        xbmc.executebuiltin('PlayerControl(Stop)')
    except Exception:
        pass

    # 2) Wyczyść właściwości, które mogą trzymać "wieczny" spinner
    try:
        cw = control.window
        for k in ['FanVodPL.autoplay','FanVodPL.autoplay_free','FanVodPL.autoplay_premium',
                  'FanVodPL.forceResolve','FanVodPL.pendingPlay','FanVodPL.resolve_in_progress']:
            cw.clearProperty(k)
        # Uwaga: nie czyścimy FanVodPL.forceCatalogThisSession – FREE ma zostać katalog-only do końca sesji
    except Exception:
        pass

    # 3) Zamknij tylko spinnery/progress – NIE zamykaj "all"
    try:
        control.execute('Dialog.Close(progressdialog,true)')
        control.execute('Dialog.Close(progressdialogbg,true)')
        control.execute('Dialog.Close(busydialog,true)')
        control.execute('Dialog.Close(busydialognocancel,true)')
        control.execute('Dialog.Close(notification,true)')
    except Exception:
        pass

    # 3.5) Jeśli to NIE jest autoplay — nie wymuszaj powrotu (Kodi wróci 1 poziom sam)
    try:
        _ap = control.window.getProperty('FanVodPL.autoplay') or ''
        _ap_free = control.window.getProperty('FanVodPL.autoplay_free') or ''
        if _ap != '2' and _ap_free != '2':
            return
    except Exception:
        pass

    # 4) Preferowany powrót: do zapamiętanego URL bez "replace" (stack zostaje)
    try:
        return_url = control.window.getProperty('FanVodPL.var.return_to_sources_url')
        if return_url:
            xbmc.executebuiltin(f'Container.Update({return_url})')  # bez ",replace"
            return
    except Exception:
        pass

    # 5) Fallback: przebuduj listę i pokaż showItems (zachowuje poziom)
    try:
        listing = filtered_items if filtered_items else items
        if listing:
            control.window.setProperty(self.itemProperty, json.dumps(listing))
            self.showItems(title, listing, None, season, episode)
            return
    except Exception:
        pass

    # 6) Ostateczność: pojedynczy Back
    try:
        control.execute('Action(Back)')
    except Exception:
        pass
    return


def has_standalone_ai(text: str) -> bool:
    t = (text or "").lower()
    return bool(
        _re.search(r'(^|[^a-z0-9])ai([^a-z0-9]|$)', t)
        or t.endswith('.ai')
        or '/ai/' in t
    )


def _ff_extract_release_year(year=None, premiered=None):
    """Wyciąga rok z year/premiered (np. '1994', '1994-03-10')."""
    for v in (premiered, year):
        if v is None:
            continue
        try:
            s = str(v).strip()
            if not s:
                continue
            m = _re.search(r'(19\d{2}|20\d{2})', s)
            if m:
                return int(m.group(1))
        except Exception:
            continue
    return None


def _ff_is_legacy_decades(release_year) -> bool:
    try:
        y = int(release_year)
        return 1950 <= y <= 2005
    except Exception:
        return False


def _ff_is_classic_series(release_year, is_episode: bool) -> bool:
    """Zwraca True gdy treść jest serialem (odcinkiem) z lat 1950–2015.
    Dla tych tytułów wszystkie bloki filtrowania fraz, limitów GB
    i innych ograniczeń są wyłączone – przepuszczamy każdy link.
    """
    if not is_episode:
        return False
    try:
        y = int(release_year)
        return 1950 <= y <= 2015
    except Exception:
        return False


def _ff_has_avi_token(text: str) -> bool:
    t = (text or "")
    return bool(_re.search(r'(?<![a-z0-9])avi(?![a-z0-9])|\.avi\b', t, _re.I))


def _ff_mask_avi_for_legacy(text: str) -> str:
    """Maskuje tylko token AVI, żeby nie wycinały go globalne blocklisty."""
    t = str(text or "")
    t = _re.sub(r'(?<![a-z0-9])avi(?![a-z0-9])', 'avilegacy', t, flags=_re.I)
    t = _re.sub(r'\.avi\b', '.avilegacy', t, flags=_re.I)
    return t


# --- LEGACY FULL MASK (tytuły 1950-2005) ---
# Stare filmy/seriale mają pliki tylko w starych formatach (DVDRip, XviD, AVI, TS itp.)
# Zastępujemy je neutralnymi tokenami żeby nie były blokowane przez globalną blacklistę.
_FF_LEGACY_MASK_PATTERNS = [
    (_re.compile(r'\bdvdrip\b',   _re.I), 'legacyrip1'),
    (_re.compile(r'\bdvdscr\b',   _re.I), 'legacyscr'),
    (_re.compile(r'\bbdrip\b',    _re.I), 'legacyrip2'),
    (_re.compile(r'\bhdrip\b',    _re.I), 'legacyrip3'),
    (_re.compile(r'\bwebrip\b',   _re.I), 'legacyrip4'),
    (_re.compile(r'\bweb-rip\b',  _re.I), 'legacyrip4'),
    (_re.compile(r'\bxvid\b',     _re.I), 'legacycodec1'),
    (_re.compile(r'\bdivx\b',     _re.I), 'legacycodec2'),
    # "avi" jest podciągiem w PATTERNS_SUBSTRING — zastępujemy na token bez "avi"
    (_re.compile(r'(?<![a-z0-9])avi(?![a-z0-9])', _re.I), 'legacycontainer1'),
    (_re.compile(r'\.avi\b',      _re.I), '.legacycontainer1'),
    (_re.compile(r'\bhdts\b',     _re.I), 'legacyformat1'),
    (_re.compile(r'\bhdcam\b',    _re.I), 'legacyformat2'),
    (_re.compile(r'\btelesync\b', _re.I), 'legacyformat3'),
    (_re.compile(r'\bvhsrip\b',   _re.I), 'legacyformat4'),
    (_re.compile(r'\bvhs\b',      _re.I), 'legacyformat5'),
    (_re.compile(r'\bhdtv\b',     _re.I), 'legacyformat8'),
    (_re.compile(r'\bpdtv\b',     _re.I), 'legacyformat9'),
    (_re.compile(r'\bdsrip\b',    _re.I), 'legacyformat10'),
    (_re.compile(r'\bsdtv\b',     _re.I), 'legacyformat11'),
    (_re.compile(r'\bcamrip\b',   _re.I), 'legacyrip5'),
    (_re.compile(r'\bts\b',       _re.I), 'legacyts'),
    (_re.compile(r'\bcam\b',      _re.I), 'legacycm'),
]


def _ff_mask_all_for_legacy(text: str) -> str:
    """Maskuje WSZYSTKIE frazy jakościowe/formatowe dla tytułów z lat 1950-2005."""
    t = str(text or "")
    for pattern, replacement in _FF_LEGACY_MASK_PATTERNS:
        t = pattern.sub(replacement, t)
    return t


def _ff_prepare_text_for_blocking(text: str, allow_legacy_avi: bool = False) -> str:
    t = (text or "")
    if allow_legacy_avi:
        # Pełna maska legacy (1950-2005) — wszystkie frazy jakościowe przepuszczone
        return _ff_mask_all_for_legacy(t).lower()
    return t.lower()


def _ff_src_has_avi(src: dict) -> bool:
    try:
        blob = " ".join([
            str(src.get("label", "")),
            str(src.get("info", "")),
            str(src.get("extrainfo", "")),
            str(src.get("url", "")),
            str(src.get("filename", "")),
        ])
    except Exception:
        blob = str(src or "")
    return _ff_has_avi_token(blob)

# Default hard block list (CSV string). Merged with GUI words.disallowed.
_FF_DEFAULT_BLOCK = (
    "cam,ts,tc,hdtc,hdts,workprint,wp,preair,screener,tsrip,hdcam,telecine,tele-sync,"
    "camrip,tc-rip,hd-cam,hd-camrip,hd-ts,hd-tc,hdtsrip,telesync,telesyn,telesync-rip,"
    "webrip,web-rip,hdrip,bdrip,dvdrip,avi,xvid,lq,low quality,sample only,"
    "vf,vfq,vfqf,vf2,vfweb,vfwebrip,vfbluray,vfhdrip,vfhd,vostfr,vostfrrip,french,fr,fr-ca,fr-be,fr-ch,français,francais,"
    "vost,mic,telesyncmic,line,lineaudio,camaudio,dubbedfr,frenchdub,frenchaudio,frdub,"
    "subforced,fansub,fansubs,subforcedfr,vostfrsub,vostfrsubs,vostfr-sub,vostfr-subs,"
    "xvidstage.com,streamango.com,rapidvideo.com,"
    "ai,pet,line-audio,line audio,mic-audio,mic audio,cam-audio,cam audio,ts-audio,ts audio,telesync audio,tsmic,ts-mic,line-mic,micline,hall audio,hall-audio,hallaudio,echo audio,echo-audio,echoaudio,rec audio,rec-audio,recaudio,md,m.d,micdub,mic-dub,mic dub,micdublado,mic dublado,dubbed mic,dub mic,dub-mic,line dub,line-dub,linedub,kino audio,kinoaudio,kino-audio,theater audio,theateraudio,theater-audio,truefrench"
)

# --- PATCH: allow x264/x265 ---
for _token in ("x264", "x265"):
    _FF_DEFAULT_BLOCK = _FF_DEFAULT_BLOCK.replace(f",{_token},", ",").replace(f",{_token}", "").replace(f"{_token},", "")
# --- END PATCH ---

PATTERNS_WHOLE_WORD = [
    _re.compile(r'\bwebrip\b', _re.I),
    _re.compile(r'\bhdrip\b', _re.I),
    _re.compile(r'\bbdrip\b', _re.I),
    _re.compile(r'\bdvdrip\b', _re.I),
    _re.compile(r'\bmic\b', _re.I),
    _re.compile(r'\bvf\b', _re.I),
    _re.compile(r'\bvostfr\b', _re.I),
    _re.compile(r'\bfr\b', _re.I),
    _re.compile(r'\bpet\b', _re.I),
    _re.compile(r'\bline\b', _re.I),
    _re.compile(r'\bcam\b', _re.I),
    _re.compile(r'\bts\b', _re.I),
    _re.compile(r'\btelesync\b', _re.I),
    _re.compile(r'\bmd\b', _re.I),
    _re.compile(r'\bm\.d\b', _re.I),
    _re.compile(r'\bmicrodub\b', _re.I),
    _re.compile(r'\bmicdub\b', _re.I),
    _re.compile(r'\btruefrench\b', _re.I),
    _re.compile(r'\bvff\b', _re.I),
    _re.compile(r'\bvfi\b', _re.I),
    _re.compile(r'\bfra\b', _re.I),
    _re.compile(r'\bfre\b', _re.I),
    _re.compile(r'\bavi\b', _re.I),
    _re.compile(r'\bxvid\b', _re.I),
    _re.compile(r'\baudio\b', _re.I),
    _re.compile(r'\bcamrip\b', _re.I),
    _re.compile(r'\bfr-be\b', _re.I),
    _re.compile(r'\bfr-ca\b', _re.I),
    _re.compile(r'\bfr-ch\b', _re.I),
    _re.compile(r'\bfrancais\b', _re.I),
    _re.compile(r'\bfrançais\b', _re.I),
    _re.compile(r'\bhdts\b', _re.I),
    _re.compile(r'\bivo\b', _re.I),
    _re.compile(r'\blq\b', _re.I),
    _re.compile(r'\bmixio\b', _re.I),
    _re.compile(r'\bnoaudio\b', _re.I),
    _re.compile(r'\bripcam\b', _re.I),
    _re.compile(r'\bvf2\b', _re.I),
    _re.compile(r'\bvfq\b', _re.I),
    _re.compile(r'\bvfqf\b', _re.I),

    _re.compile(r'\bdiy\b', _re.I),
    _re.compile(r'\bsupply\b', _re.I),
    _re.compile(r'\bkino\b', _re.I),
    _re.compile(r'\bkinowy\b', _re.I),
    _re.compile(r'\bkinowa\b', _re.I),
]

PATTERNS_SUBSTRING = [
    _re.compile(r'vfhdrip', _re.I),
    _re.compile(r'vfweb', _re.I),
    _re.compile(r'vfwebrip', _re.I),
    _re.compile(r'vfbluray', _re.I),
    _re.compile(r'french', _re.I),
    _re.compile(r'vost', _re.I),
    _re.compile(r"line[\s-]?audio", _re.I),
    _re.compile(r'avi', _re.I),
    _re.compile(r'xvid', _re.I),
    _re.compile(r'mic[\s-]?audio', _re.I),
    _re.compile(r'cam[\s-]?audio', _re.I),
    _re.compile(r'(?:ts|telesync)[\s-]?audio', _re.I),
    _re.compile(r'(?:ts)[\s-]?mic', _re.I),
    _re.compile(r'line[\s-]?mic', _re.I),
    _re.compile(r'micline', _re.I),
    _re.compile(r'hall[\s-]?audio', _re.I),
    _re.compile(r'echo[\s-]?audio', _re.I),
    _re.compile(r'(?:rec|record)[\s-]?audio', _re.I),
    _re.compile(r'mic[\s-]?dub', _re.I),
    _re.compile(r'mic[\s-]?dublado', _re.I),
    _re.compile(r'dub[\s-]?mic', _re.I),
    _re.compile(r'line[\s-]?dub', _re.I),
    _re.compile(r'kino[\s-]?audio', _re.I),
    _re.compile(r'theater[\s-]?audio', _re.I),
    _re.compile(r'vff(?:rip|webrip|bluray)?', _re.I),
    _re.compile(r'vfi(?:rip|webrip|bluray)?', _re.I),    _re.compile(r'vf2cam', _re.I),
    _re.compile(r'vfqcam', _re.I),
    _re.compile(r'vostfrrip', _re.I),
    _re.compile(r'webrip', _re.I),

    _re.compile(r'd[._\- ]?i[._\- ]?y', _re.I),
    _re.compile(r'su[._\- ]?p[._\- ]?p[._\- ]?l[._\- ]?y', _re.I),
    _re.compile(r'k[._\- ]?i[._\- ]?n[._\- ]?o', _re.I),
    _re.compile(r'k[._\- ]?i[._\- ]?n[._\- ]?o[._\- ]?w[._\- ]?y', _re.I),
    _re.compile(r'k[._\- ]?i[._\- ]?n[._\- ]?o[._\- ]?w[._\- ]?a', _re.I),
]

# --- AI SZTUCZNY LEKTOR (wykrywanie po labelu/etykiecie) ---
AI_LEKTOR_PATTERNS = (
    "ai lektor",
    "lektor ai",
    "lektorai",
    "ailektor",
    "ai-lektor",
    "ai_lektor",
    "lektor-ai",
    "lektor_ai",
    "sztuczny lektor",
    "ai sztuczny lektor",
    ".ai.",
    "pl.ai.",
    ".ai.pl",

    # --- Expressivo / PL.Expressivo → też do kubka AI ---
    "expressivo",
    ".expressivo.",
    "expressivo.",
    ".expressivo",
    "pl.expressivo",
    "pl expressivo",
    "expressivo pl",
    "expressivopl",
    "expressivo-pl",
    "pl-expressivo",
    "expressivo_pl",
    "pl_expressivo",
    "plexpressivo",
    "plexptessivo",
)



def _has_ai_lektor(item):
    """
    Wykrywa sztuczny lektor AI w dowolnym polu (label/info/extrainfo/url).
    Dzięki temu nie zależy już od tego, co provider wrzucił do labelu.
    """
    if not item:
        return False
    txt = " ".join([
        str(item.get("label","")),
        str(item.get("info","")),
        str(item.get("extrainfo","")),
        str(item.get("url",""))
    ]).lower()
    for p in AI_LEKTOR_PATTERNS:
        if p in txt:
            return True
    return False

def _has_any(rx_list, text: str) -> bool:
    if not text:
        return False
    for rx in rx_list:
        if rx.search(text):
            return True
    return False
# ========== [END] BANNED PHRASES – GLOBAL ==========

def _ff_detect_part(item):
    """
    Wykrywanie PART 1 / PART 2 – tylko po jawnych oznaczeniach w źródle (label/url/nazwa pliku):
      - part/pt, część/czesc/cz, 1of2/2of2, cd/disc
    Cel: nie łapać fałszywie nazw odcinków typu „Rozdział pierwszy / Chapter One”.
    """
    try:
        txt = " ".join([
            str(item.get("label", "")),
            str(item.get("name", "")),
            str(item.get("filename", "")),
            str(item.get("url", "")),
            str(item.get("info", "")),
            str(item.get("extrainfo", "")),
        ]).lower()
    except Exception:
        txt = ""

    # normalizacja separatorów (żeby złapać np. 'part1', 'cz.1', 'cd2' itp.)
    txt = txt.replace("_", " ").replace(".", " ").replace("-", " ").replace("/", " ")

    # kolejność: najpierw PART 2, potem PART 1
    if (re.search(r"\b(part|pt)\s*0?2\b", txt) or
        re.search(r"\b(cz|czesc|część)\s*0?2\b", txt) or
        re.search(r"\b2\s*of\s*2\b", txt) or
        re.search(r"\b(cd|disc)\s*0?2\b", txt) or
        re.search(r"\bfinale\s*2\b", txt)):
        return "PART 2 ✅"

    if (re.search(r"\b(part|pt)\s*0?1\b", txt) or
        re.search(r"\b(cz|czesc|część)\s*0?1\b", txt) or
        re.search(r"\b1\s*of\s*2\b", txt) or
        re.search(r"\b(cd|disc)\s*0?1\b", txt) or
        re.search(r"\bfinale\s*1\b", txt)):
        return "PART 1 ✅"

    return "NIEZNANE ?"



def _double_ep_notify(msg):
    try:
        import xbmcgui
        xbmcgui.Dialog().notification("DOUBLE EP", msg, xbmcgui.NOTIFICATION_WARNING, 10000)
    except Exception:
        pass
    try:
        import xbmcgui
        xbmcgui.Dialog().ok("DOUBLE EP", msg)
    except Exception:
        pass


class sources:


    def _ff_resolve_with_timeout(self, item, timeout_ms=12000):
        """Bezpieczne wywołanie sourcesResolve z limitem czasu.
        Jeśli provider/dialog wisi dłużej niż timeout_ms, przerywamy próbę i zwracamy None.
        Nie zabija wątku (Python nie pozwala), ale ignorujemy wynik spóźniony i czyścimy spinnery/flagę resolve."""
        try:
            import threading, time
        except Exception:
            return self.sourcesResolve(item)
        url_box = {'v': None}
        err_box = {'e': None}
        def _worker():
            try:
                url_box['v'] = self.sourcesResolve(item)
            except Exception as e:
                err_box['e'] = e
        t = threading.Thread(target=_worker, name='FFResolveWorker', daemon=True)
        try:
            t.start()
        except Exception:
            # fallback bez wątku
            try:
                return self.sourcesResolve(item)
            except Exception:
                return None
        start = time.time()
        # aktywnie czekamy maksymalnie timeout_ms
        while t.is_alive() and (time.time() - start) * 1000.0 < float(timeout_ms):
            try:
                if control.condVisibility('Dialog.IsVisible(busydialog)') or control.condVisibility('Dialog.IsVisible(busydialognocancel)'):
                    pass
            except Exception:
                pass
            control.sleep(100)
        if t.is_alive():
            # timeout – sprzątanie i rezygnacja z tej próby
            try:
                cw = control.window
                for k in ('FanVodPL.resolve_in_progress','FanVodPL.pendingPlay','FanVodPL.forceResolve'):
                    cw.clearProperty(k)
            except Exception:
                pass
            try:
                xbmc.executebuiltin('Dialog.Close(busydialog)')
                xbmc.executebuiltin('Dialog.Close(busydialognocancel)')
                xbmc.executebuiltin('Dialog.Close(yesnoDialog)')
                xbmc.executebuiltin('Dialog.Close(okDialog)')
            except Exception:
                pass
            return None
        # wątek zakończony – zwróć wynik lub None
        return url_box.get('v')

    # [EARLY_GETCONSTANTS_FIX] — kopia metody getConstants wstawiona na górze klasy
    def getConstants(self):
        # Właściwości kontenera (tak jak niżej)
        self.itemProperty = "plugin.video.fanvodpl.container.items"
        self.itemRejected = "plugin.video.fanvodpl.container.itemsRejected"
        self.metaProperty = "plugin.video.fanvodpl.container.meta"
        # Hosty dynamiczne (resolveurl) — opcjonalnie
        try:
            self.hostDict = resolveurl.relevant_resolvers(order_matters=True)
            self.hostDict = [i.domains for i in self.hostDict if "*" not in i.domains]
            from functools import reduce
            self.hostDict = [i.lower() for i in reduce(lambda x, y: x + y, self.hostDict)]
            self.hostDict = [x for y, x in enumerate(self.hostDict) if x not in self.hostDict[:y]]
        except Exception:
            self.hostDict = []
        # Hosty premium (statyczne)
        self.hostprDict = [
            "1fichier.com","oboom.com","rapidgator.net","rg.to","uploaded.net","uploaded.to","ul.to",
            "filefactory.com","nitroflare.com","turbobit.net","uploadrocket.net",
        ]
        # Hosty cap/low
        self.hostcapDict = [
            "hugefiles.net","kingfiles.net","openload","openload.io","openload.co","oload.tv",
            "thevideo.me","vidup.me","streamin.to","torba.se","flashx","flashx.tv",
        ]
        # Hosty HQ
        self.hosthqDict = [
            "gvideo","vidcloud.co","vidoza.net","vidoza.org","vidlox.tv","verystream.com","estream.to",
            "openload.co","openload.io","oload.tv","oload.stream","mail.ru","mailru","mixdrop.co",
            "mixdrop.to","mixdrop","streamtape.com","streamtape","yadi.sk","yandex","uptobox.com",
            "raptu.com","filez.tv","uptobox.com","uptobox.com","uptostream.com","xvidstage.com","streamango.com",
        ]
        self.hostblockDict = []
    def __init__(self):
        self.sourceFile = None
        self.url = None
        self.selectedSource = None
        self.itemProperty = None
        self.itemRejected = None
        self.metaProperty = None
        self.sourceDict = None
        self.hostDict = None
        self.hostprDict = None
        self.hostcapDict = None
        self.hosthqDict = None
        self.hostblockDict = None
        self.getConstants()
        self.sources = []
        self.blocked_sources_extend = None
        #self.test = {}
        #self.sources_thrown_out = []
        #control.setting = xbmcaddon.Addon().getSetting
        #control.setSetting = xbmcaddon.Addon().setSetting


    # ===== [AUTO JAKOŚĆ – HELPERS v3] =====
    def _is_premium_provider(self, item):
        prov = (item.get("provider") or item.get("source") or "").lower()
        url  = (item.get("url") or "").lower()
        info = (item.get("info") or "").lower()
        lab  = (item.get("label") or "").lower()
        txt  = " ".join([prov, url, info, lab])
        return any(p in txt for p in ("tb7", "xt7", "rapideo", "nopremium", "twojlimit", "cdapremium", "premiumsmart"))
    def _quality_of(self, item):
        q = (item.get("quality") or "").strip().lower()
        if q in {"4k", "2160p", "uhd"}: return "2160p"
        if q in {"1080p", "fhd", "fullhd"}: return "1080p"
        if q in {"720p"}: return "720p"
        txt = " ".join([str(item.get("info","")), str(item.get("extrainfo","")), str(item.get("label",""))]).lower()
        if "2160" in txt or "uhd" in txt or "4k" in txt: return "2160p"
        if "1080" in txt: return "1080p"
        if "720" in txt: return "720p"
        return "sd"

    def _has_container(self, item, container):  # "mkv" / "mp4"
        t = " ".join([str(item.get("info","")), str(item.get("extrainfo","")), str(item.get("label","")), str(item.get("url",""))]).lower()
        return container in t

    def _pick_best_premium_for(self, items, wanted_quality, container):
        out = []
        for it in items:  # items są już posortowane „najlepszy najpierw”
            if self._is_premium_provider(it) and self._quality_of(it) == wanted_quality and self._has_container(it, container):
                out.append(it)
        return out if out else None

    def _collect_best_pair_for_res(self, items, wanted_quality):
        best_mkv = self._pick_best_premium_for(items, wanted_quality, "mkv") or []
        best_mp4 = self._pick_best_premium_for(items, wanted_quality, "mp4") or []
        out = []
        out.extend(best_mkv)
        out.extend(best_mp4)
        return out  # max 2

    def _collect_free_links(self, items):
        return [it for it in items if not self._is_premium_provider(it)]




    def _collect_best_multi_pair(self, items):
        try:
            multi_items = [it for it in (items or []) if (str((it.get("language") or "")).lower() in ("multi", "mul")) and not _has_ai_lektor(it)]
            if not multi_items:
                return []
            # prefer highest resolution available among MULTI
            for wanted in ("2160p","1080p","720p","sd"):
                pair = self._collect_best_pair_for_res(multi_items, wanted)
                if pair:
                    return pair
            # fallback: pick any MKV/MP4 if quality unknown
            mkv = next((it for it in multi_items if self._has_container(it, "mkv")), None)
            mp4 = next((it for it in multi_items if self._has_container(it, "mp4")), None)
            out = []
            if mkv: out.append(mkv)
            if mp4 and mp4 is not mkv: out.append(mp4)
            return out
        except Exception:
            return []

        # ===== [AUTO JAKOŚĆ – LIMITY GB & SERWERY PL] =====
    def _extract_size_gb(self, item):
        # Wyciąga rozmiar (GB/MB/KB) z wielu pól (info/extrainfo/label/url/size) -> zwraca w GB (float) lub None
        try:
            parts = [
                str(item.get("info", "")),
                str(item.get("extrainfo", "")),
                str(item.get("extra_info", "")),
                str(item.get("info2", "")),
                str(item.get("label", "")),
                str(item.get("url", "")),
                str(item.get("size", "")),
                str(item.get("filesize", "")),
                str(item.get("file_size", "")),
            ]
            txt = " ".join([p for p in parts if p and p != "None"])
        except Exception:
            txt = ""
        # Obsługa: "1.4 GB", "900MB", "1024 KB", "1,5 GiB", "750 MiB"
        m = re.search(r'(\d+(?:[\.,]\d+)?)\s*(GiB|GB|MiB|MB|KiB|KB)\b', txt, flags=re.I)
        if not m:
            return None
        try:
            val = float(m.group(1).replace(",", ".").replace(" ", ""))
        except Exception:
            return None
        unit = m.group(2).upper()
        if unit in ("GB", "GIB"):
            return val
        if unit in ("MB", "MIB"):
            return val / 1024.0
        if unit in ("KB", "KIB"):
            return val / (1024.0 * 1024.0)
        return None
    def _is_tvshow_meta(self):
        # Sprawdza czy aktualnie wybrany element to serial (tvshow) na podstawie metaProperty
        try:
            meta = control.window.getProperty(self.metaProperty)
            if not meta:
                return False
            meta = json.loads(meta)
            return bool(meta.get("tvshowtitle") or (meta.get("season") is not None and meta.get("episode") is not None))
        except Exception:
            return False

    def _get_limit_values(self):
        # Stałe limity GB ustawione na sztywno (GUI wyłączone)
        return {
            "limit_4k_min": 10,
            "limit_4k_max": 20,
            "limit_multi_min": 12,
            "limit_multi_max": 25,
            "limit_fhd_min": 7,
            "limit_fhd_max": 17,
            "limit_720_min": 4,
            "limit_720_max": 10,
            "limit_tv_max": 12,
        }

    def _apply_size_limits(self, items):
        # Filtr rozmiaru wg limitów GB. Filmy: MIN/MAX per 2160p/1080p/720p. Seriale: jeden MAX.
        # CLASSIC SERIES BYPASS (1950–2015): jeśli to odcinek serialu z lat 1950–2015, nie stosuj limitów GB
        if getattr(self, '_ff_bypass_classic_series', False):
            return items
        # LEGACY MOVIE BYPASS (1950–2005): stare filmy mają małe pliki — wyłącz tylko dolny limit MIN
        _legacy_movie = getattr(self, '_ff_allow_legacy_avi', False)
        limits = self._get_limit_values()
        if not items or not isinstance(items, list):
            return items

        is_tv = self._is_tvshow_meta()


        def ok_movie(it):
            size = self._extract_size_gb(it)
            if size is None:
                # brak rozmiaru: odrzuć TYLKO premium
                return not self._is_premium_provider(it)

            # --- MULTI przed rozdzielczością ---
            is_multi = ((it.get("language") or "").lower() in ("multi", "mul") or
                        re.search(r'(?<![a-z0-9])multi(?![a-z0-9])',
                                  " ".join([str(it.get("label","")),
                                            str(it.get("info","")),
                                            str(it.get("extrainfo","")),
                                            str(it.get("url",""))]), re.I))

            if is_multi:
                mi, ma = limits["limit_multi_min"], limits["limit_multi_max"]
            else:
                res = self._quality_of(it)
                if res == "2160p":
                    mi, ma = limits["limit_4k_min"], limits["limit_4k_max"]
                elif res == "1080p":
                    mi, ma = limits["limit_fhd_min"], limits["limit_fhd_max"]
                elif res == "720p":
                    mi, ma = limits["limit_720_min"], limits["limit_720_max"]
                else:
                    mi, ma = None, None

            if mi is not None and size < mi and not _legacy_movie:
                return False
            if ma is not None and size > ma:
                return False
            return True
  # brak rozmiaru = nie odrzucaj
            if res == "2160p":
                mi, ma = limits["limit_4k_min"], limits["limit_4k_max"]
            elif res == "1080p":
                mi, ma = limits["limit_fhd_min"], limits["limit_fhd_max"]
            elif res == "720p":
                mi, ma = limits["limit_720_min"], limits["limit_720_max"]
            elif (it.get("language") or "").lower() in ("multi", "mul"):
                mi, ma = limits["limit_multi_min"], limits["limit_multi_max"]
            else:
                mi, ma = None, None
            if mi is not None and size < mi: return False
            if ma is not None and size > ma: return False
            return True

        def ok_tv(it):
            size = self._extract_size_gb(it)
            if size is None:
                # brak rozmiaru: odrzuć TYLKO premium
                return not self._is_premium_provider(it)
            ma = limits["limit_tv_max"]
            if ma is not None and size > ma:
                return False
            return True

        if is_tv:
            return [it for it in items if ok_tv(it)]
        else:
            return [it for it in items if ok_movie(it)]

    def _show_auto_quality_settings(self):
        # Menu główne ustawień: Limity GB / Serwery źródeł PL
        import xbmcgui, xbmcaddon
        addon = xbmcaddon.Addon()
        choices = ["Serwery źródeł PL"]
        idx = xbmcgui.Dialog().select("[FF] Ustawienia Auto Jakość", choices)
        if idx < 0:
            return False  # nic nie zapisano
        if idx == 0:
            return self._set_pl_servers(addon)
        return False

    def _set_pl_servers(self, addon):
        # Otwórz pełne GUI ustawień FanVodPL (loginy/hasła/hosty itd.) i po zamknięciu cofnij do tytułów
        import xbmcgui
        try:
            addon.openSettings()
            return True

        except Exception:
            xbmcgui.Dialog().notification("FanVodPL", "Nie udało się otworzyć ustawień dodatku", xbmcgui.NOTIFICATION_ERROR, 2000)
            return False

    def _collect_best_premium_from_rejected_nopl(self):
        """Zwraca najlepsze premium (MKV/MP4) z kubełka 'odrzucone', ale po ponownej filtracji zakazanych fraz.
        Dopuszcza wyjątki (ai+atvp / dv+hdr*). Priorytet: 2160p → 1080p → 720p."""
        import json, re
        try:
            rejected = json.loads(control.window.getProperty(self.itemRejected)) or []
        except Exception:
            rejected = []
        # premium z odrzuconych
        cand = [it for it in rejected if self._is_premium_provider(it)]
        if not cand:
            return []

        def _txt(it):
            return " ".join([str(it.get("info","")), str(it.get("extrainfo","")), str(it.get("label","")), str(it.get("url",""))]).lower()

        _allow_legacy_avi = _ff_is_legacy_decades(getattr(self, "_ff_release_year", None))

        def _whitelisted(t: str) -> bool:
            # Wyjątek 1: 'ai' + 'atvp/atpv' (Apple TV) → przepuść tylko wobec reguły 'ai'
            if 'ai' in t and ('atvp' in t or 'atpv' in t):
                return True
            return False


        def _banned(t: str) -> bool:
            t = _ff_prepare_text_for_blocking((t or ""), allow_legacy_avi=_allow_legacy_avi)
            if _whitelisted(t):
                return False
            # EXCEPTION: IMAX/MAX in safe, disc-quality MULTI contexts (4K/1080p)
            try:
                rx_imax = re.compile(r'(?<![a-z0-9])imax(?![a-z0-9])', re.I)
                rx_max  = re.compile(r'(?<![a-z0-9])max(?![a-z0-9])', re.I)
                is_imax = bool(rx_imax.search(t))
                is_max  = bool(rx_max.search(t)) and not is_imax  # don't double-count IMAX
                if is_imax:
                    # Always allow IMAX token (avoid false-positive on 'max')
                    return False
                if is_max:
                    is_4k  = re.search(r'(2160p|\b4k\b)', t, re.I)
                    is_fhd = re.search(r'(1080p|full\s*hd|fullhd)', t, re.I)
                    discq  = re.search(r'(bluray|uhd|remux)', t, re.I)
                    multi  = re.search(r'(?<![a-z0-9])multi(?![a-z0-9])|(?<![a-z0-9])mul(?![a-z0-9])', t, re.I)
                    if multi and discq and (is_4k or is_fhd):
                        return False
            except Exception:
                pass

            # EXCEPTION: allow 'hq' ONLY for 4K / FullHD MULTI disc-quality releases
            try:
                rx_hq = re.compile(r'(?<![a-z0-9])hq(?![a-z0-9])', re.I)
                rx_lq = re.compile(r'(?<![a-z0-9])lq(?![a-z0-9])', re.I)
                has_hq = bool(rx_hq.search(t))
                has_lq = bool(rx_lq.search(t))
                if has_hq and not has_lq:
                    is_4k   = re.search(r'(?:2160p|\b4k\b)', t, re.I)
                    is_fhd  = re.search(r'(?:1080p|full\s*hd|fullhd)', t, re.I)
                    discq   = re.search(r'(bluray|uhd|remux)', t, re.I)
                    multi   = re.search(r'(?<![a-z0-9])multi(?![a-z0-9])|(?<![a-z0-9])mul(?![a-z0-9])', t, re.I)
                    if multi and discq and (is_4k or is_fhd):
                        return False
            except Exception:
                pass
            if _has_any(PATTERNS_WHOLE_WORD, t) or _has_any(PATTERNS_SUBSTRING, t):
                return True
            for tok in _FF_DEFAULT_BLOCK.split(","):
                tok = tok.strip().lower()
                if not tok:
                    continue
                if tok == "ai" and ("atvp" in t or "atpv" in t):
                    continue
                if tok == "fr":
                    if re.search(r'\bfr\b', t):
                        return True
                    continue
                if tok in t:
                    return True
            return False

        cand = [it for it in cand if not _banned(_txt(it))]
        if not cand:
            return []

        out = []
        for res in ("2160p", "1080p", "720p"):
            pair = self._collect_best_pair_for_res(cand, res)
            if pair:
                out.extend(pair)
        return out if out else cand
        # wybierz najlepsze pary MKV/MP4 dla każdej rozdzielczości
        out = []
        for res in ("2160p", "1080p", "720p"):  # kolejność ważna
            pair = self._collect_best_pair_for_res(cand, res)
            if pair:
                out.extend(pair)
        # jeżeli nic nie wybrano parach (nietypowe etykiety), oddaj cokolwiek premium
        return out if out else cand
    def _collect_all_free_including_rejected(self, items):
            import json
            try:
                rejected = json.loads(control.window.getProperty(self.itemRejected)) or []
            except Exception:
                rejected = []
            free_now = [it for it in items if not self._is_premium_provider(it)]
            rejected_free = [it for it in rejected if not self._is_premium_provider(it)]
            seen = set()
            merged = []
            for it in free_now + rejected_free:
                key = ((it.get("url") or ""), (it.get("provider") or ""))
                if key in seen:
                    continue
                seen.add(key)
                merged.append(it)
            return merged

    
    def _auto_quality_dialog_and_filter(self, title, items):
            """
            Prosta logika:
            1) Po wyborze tytułu: okno z wyborem PREMIUM / DARMOWE.
            2) Po wyborze: szukamy JEDNEGO najlepszego źródła wg hierarchii
               (4K -> 1080p -> 720p, w pierwszej kolejności MULTI/MULTI PL/LEKTOR PL, potem NAPISY),
               pokazujemy informację o pliku + pytanie:
               OGLĄDAJ ONLINE / POBIERZ PLIK NA DYSK.
            Zwracamy:
                ("etykieta", [best_item]) – dla OGLĄDAJ
                ("__CANCEL__", None)      – dla POBIERZ lub anulowania.
            """
            try:
                import xbmcgui
                import xbmc
            except Exception:
                return ("__CANCEL__", None)

            # 0) Brak źródeł – nic nie robimy
            items_all = items or []
            if not items_all:
                return ("__CANCEL__", None)

            # --- SD policy: block SD globally, allow for legacy (<=2005) or classic series (<=2015) ---
            def _legacy_sd_allowed() -> bool:
                try:
                    y = getattr(self, "_ff_ctx_year", None)
                    y = int(y) if y not in (None, "", "None", "0") else None
                except Exception:
                    y = None
                if (y is not None) and (y <= 2005):
                    return True
                # CLASSIC SERIES BYPASS (1950-2015): dopuszczamy SD dla seriali z lat 1950-2015
                return bool(getattr(self, "_ff_bypass_classic_series", False))

            # 1) Podział: PREMIUM vs DARMOWE
            try:
                free_items_raw = self._collect_free_links(items_all)
            except Exception:
                free_items_raw = []

            try:
                prem_items_raw = [it for it in items_all if self._is_premium_provider(it)]
            except Exception:
                prem_items_raw = []

            # 2) Limity GB – tylko na premium
            try:
                prem_limited = self._apply_size_limits(prem_items_raw) if prem_items_raw else prem_items_raw
            except Exception:
                prem_limited = prem_items_raw

            # 3) HARD BLOCKERS (frazy z PDF + wyjątki) – tylko premium
            import re as _re

            def _txt(it):
                try:
                    return " ".join([
                        str(it.get("info", "")),
                        str(it.get("extrainfo", "")),
                        str(it.get("label", "")),
                        str(it.get("url", "")),
                    ]).lower()
                except Exception:
                    return (str(it) or "").lower()

            def _whitelisted(t: str) -> bool:
                t = (t or "").lower()
                # Wyjątek: "ai" + "atvp"/"atpv" (Apple TV) – nie blokujemy
                if "ai" in t and ("atvp" in t or "atpv" in t):
                    return True
                # Wyjątek: "dv" + HDR – nie blokujemy (Dolby Vision + HDR)
                if "dv" in t and any(h in t for h in (" hdr", " hdr10", " hdr10plus", " hdr10+", "hdr ", "hdr10 ", "hdr10plus ", "hdr10+ ")):
                    return True
                return False

            def _has_any(patterns, t: str) -> bool:
                if not patterns:
                    return False
                for rx in patterns:
                    try:
                        if rx.search(t):
                            return True
                    except Exception:
                        continue
                return False

            _allow_legacy_avi = _ff_is_legacy_decades(getattr(self, "_ff_release_year", None))

            def _banned(t: str) -> bool:
                t = _ff_prepare_text_for_blocking((t or ""), allow_legacy_avi=_allow_legacy_avi)
                if not t.strip():
                    return False
                if _whitelisted(t):
                    return False
                try:
                    from resources.lib.modules.constants import PATTERNS_WHOLE_WORD, PATTERNS_SUBSTRING, _FF_DEFAULT_BLOCK
                except Exception:
                    PATTERNS_WHOLE_WORD = []
                    PATTERNS_SUBSTRING = []
                    _FF_DEFAULT_BLOCK = ""
                if _has_any(PATTERNS_WHOLE_WORD, t) or _has_any(PATTERNS_SUBSTRING, t):
                    return True
                for tok in _FF_DEFAULT_BLOCK.split(","):
                    tok = tok.strip().lower()
                    if not tok:
                        continue
                    # szczególny przypadek FR – tylko całe słowo
                    if tok == "fr":
                        if _re.search(r"\bfr\b", t):
                            return True
                        continue
                    # wyjątek dla "ai" + atvp/atpv
                    if tok == "ai" and ("atvp" in t or "atpv" in t):
                        continue
                    if tok in t:
                        return True
                return False

            try:
                # CLASSIC SERIES BYPASS (1950-2015): nie filtruj zakazanych fraz dla premium w serialach klasycznych
                if getattr(self, "_ff_bypass_classic_series", False):
                    prem_limited = list(prem_limited or [])
                else:
                    prem_limited = [it for it in (prem_limited or []) if not _banned(_txt(it))]
            except Exception:
                pass

            prem_effective = prem_limited or []
            # 3b) HARD QUALITY FLOOR dla PREMIUM — WYŁĄCZONY (zostawiamy pełną listę; jakość filtrowana później na poziomie hosta)
            try:
                prem_effective = prem_effective or []
            except Exception:
                pass


            free_effective = free_items_raw or []


            # 4) FLOW → wymuś language=pl na źródłach FLOW (żeby traktować jak PL lektor)
            try:
                from resources.lib.modules import constants as _const
                FLOW_IDS = getattr(_const, "FLOW_SOURCE_IDS", ("flow", "flowcdn"))
            except Exception:
                FLOW_IDS = ("flow", "flowcdn")

            try:
                for it in prem_effective:
                    p = (it.get("provider") or it.get("source") or "").lower()
                    if any(fid in p for fid in FLOW_IDS):
                        it["language"] = "pl"
            except Exception:
                pass

            # 5) Detekcja języka / multi / napisy
            def _tmeta(_it):
                return " ".join([
                    str(_it.get("label", "")),
                    str(_it.get("info", "")),
                    str(_it.get("extrainfo", "")),
                ]).lower()

            import re as _rx
            _rx_lektor  = _rx.compile(r"(?<![a-z0-9])(lektor|lekt)(?![a-z0-9])", _rx.I)
            _rx_dubbing = _rx.compile(r"(?:(?<![a-z0-9])(dubbing|dubbingpl|dubbing-pl|dub|dubpl|dub-pl)(?![a-z0-9])|pldub|pl-dub)", _rx.I)
            _rx_pl_tok  = _rx.compile(r"(?<![a-z0-9])(pl|polish|polski)(?![a-z0-9])", _rx.I)
            _rx_multi   = _rx.compile(r"(?<![a-z0-9])(multi|mul)(?![a-z0-9])", _rx.I)
            _rx_subs    = _rx.compile(r"(?<![a-z0-9])(napisy|napis|subs?|subtitles?|pl\s*sub|sub\s*pl|plsub|subpl)(?![a-z0-9])", _rx.I)

            def _has_lang_tag_in_url(_it) -> bool:
                u = str(_it.get("url", "")).lower()
                if not u:
                    return False
                return (_rx_lektor.search(u) is not None) or (_rx_dubbing.search(u) is not None) or (_rx_subs.search(u) is not None) or (_rx_multi.search(u) is not None)

            def _is_subs_only(_it) -> bool:
                t = _tmeta(_it)
                lang = str(_it.get("language", "")).lower()
                if _rx_multi.search(t) or lang in ("multi", "mul"):
                    return False
                has_subs = _rx_subs.search(t) is not None
                has_voice_kw = (_rx_lektor.search(t) is not None) or (_rx_dubbing.search(t) is not None)
                if not has_subs:
                    return False
                if has_voice_kw:
                    return False
                return True

            def _is_multi_no_pl(_it) -> bool:
                t = _tmeta(_it)
                lang = str(_it.get("language", "")).lower()
                if _rx_multi.search(t) or lang in ("multi", "mul"):
                    return True
                return False

            def _is_voice_pl_strict(_it) -> bool:
                t = _tmeta(_it)
                lang = str(_it.get("language", "")).lower()
                has_pl = (_rx_pl_tok.search(t) is not None) or (lang in ("pl", "polish", "polski"))
                has_voice_kw = (_rx_lektor.search(t) is not None) or (_rx_dubbing.search(t) is not None)
                if not (has_pl and has_voice_kw):
                    return False
                return True

            # 6) Rankingi jakości / wielkości
            def _quality_rank(_it) -> int:
                try:
                    q = self._quality_of(_it)
                except Exception:
                    q = None
                if q == "2160p":
                    return 0
                if q == "1080p":
                    return 1
                if q == "720p":
                    return 2
                return 3

            def _size_gb_safe(_it) -> float:
                try:
                    s = self._extract_size_gb(_it)
                    return float(s) if s is not None else 0.0
                except Exception:
                    return 0.0

            def _voice_type_rank(_it) -> int:
                # MULTI / MULTI PL / LEKTOR PL traktujemy na szczycie
                if _is_multi_no_pl(_it):
                    return 0
                if _is_voice_pl_strict(_it):
                    return 1
                return 2

            def _best_source(seq):
                seq = list(seq or [])
                if not seq:
                    return None

                voice = [it for it in seq if (_is_multi_no_pl(it) or _is_voice_pl_strict(it))]
                subs  = [it for it in seq if _is_subs_only(it)]
                other = [it for it in seq if it not in voice and it not in subs]

                def _sort_voice(lst):
                    lst = list(lst or [])
                    lst.sort(key=lambda it: (_quality_rank(it), _voice_type_rank(it), -_size_gb_safe(it)))
                    return lst

                def _sort_basic(lst):
                    lst = list(lst or [])
                    lst.sort(key=lambda it: (_quality_rank(it), -_size_gb_safe(it)))
                    return lst

                if voice:
                    return _sort_voice(voice)[0]
                if subs:
                    return _sort_basic(subs)[0]
                if other:
                    return _sort_basic(other)[0]
                return None

            # 3c) HARD LANGUAGE TAG FLOOR dla PREMIUM — ukrywamy PREMIUM, jeśli brak bezpiecznych tagów językowych w URL
            # CLASSIC SERIES BYPASS (1950-2015): stare seriale nie mają polskich tagów w URL — przepuszczamy wszystko
            try:
                if getattr(self, "_ff_bypass_classic_series", False):
                    pass  # bypass: zostawiamy prem_effective bez filtrowania po języku URL
                else:
                    _prem_lang = []
                    for _it in (prem_effective or []):
                        if _has_lang_tag_in_url(_it):
                            _prem_lang.append(_it)
                    prem_effective = _prem_lang
            except Exception:
                pass

            # 7) Pierwsze okno: PREMIUM / DARMOWE
            options = []
            payloads = []

            if prem_effective:
                options.append("PREMIUM")
                payloads.append("premium")
            if free_effective:
                options.append("----------------\nDARMOWE")
                payloads.append("free")

            if not options:
                try:
                    from resources.lib.modules import control
                    control.infoDialog("Brak dostępnych źródeł.", "FanVodPL", time=3000)
                except Exception:
                    pass
                return ("__CANCEL__", None)

            try:
                idx = xbmcgui.Dialog().select("Wybierz źródła — %s" % title, options)
            except Exception:
                idx = -1

            if idx < 0 or idx >= len(payloads):
                return ("__CANCEL__", None)

            mode = payloads[idx]
            if mode == "premium":
                base_seq = prem_effective
            else:
                base_seq = free_effective

                        # WYBÓR HOSTA: PREMIUM z ręcznym wyborem providera + hierarchia MULTI/LEKTOR/NAPISY,
            # a dla DARMOWYCH dalej ręczny wybór hosta jak dotychczas
            if mode == "premium":
                # 7a) Wybór hosta PREMIUM (nopremium / xt7 / rapideo / itp.)
                try:
                    host_map = {}
                    for _it in (base_seq or []):
                        prov_raw = str(_it.get("provider") or _it.get("source") or "?")
                        prov_key = prov_raw.lower() or "?"
                        if prov_key not in host_map:
                            host_map[prov_key] = {"name": prov_raw, "items": []}
                        host_map[prov_key]["items"].append(_it)
                    host_keys = list(host_map.keys())
                except Exception:
                    host_map = {}
                    host_keys = []

                if not host_keys:
                    best = _best_source(base_seq)
                else:
                    chosen_items = None
                    chosen_host_name = "PREMIUM"

                    if len(host_keys) == 1:
                        # Tylko jeden host PREMIUM – nie ma sensu pytać użytkownika
                        info = host_map[host_keys[0]]
                        chosen_items = info.get("items") or []
                        chosen_host_name = info.get("name") or host_keys[0]
                    else:
                        # Lista aktywnych hostów PREMIUM (nopremium / xt7 / rapideo ...)
                        try:
                            options_hosts = []
                            payloads_hosts = []
                            for key in host_keys:
                                info = host_map.get(key) or {}
                                links = info.get("items") or []
                                prov_name = (info.get("name") or key).upper()
                                # --- DODATEK: opis hosta PREMIUM na podstawie URL/metadata (MULTI / lektor / napisy) ---
                                try:
                                    has_multi = False
                                    has_voice_pl = False
                                    has_ai = False
                                    has_subs = False
                                    for _cand in (links or []):
                                        try:
                                            if _is_multi_no_pl(_cand):
                                                has_multi = True
                                            if _is_voice_pl_strict(_cand):
                                                has_voice_pl = True
                                            if _has_ai_lektor(_cand):
                                                has_ai = True
                                            if _is_subs_only(_cand):
                                                has_subs = True
                                        except Exception:
                                            continue
                                    desc_parts = []
                                    if has_multi:
                                        desc_parts.append("multi")
                                    if has_ai:
                                        desc_parts.append("lektor AI")
                                    elif has_voice_pl:
                                        desc_parts.append("lektor PL")
                                    if has_subs:
                                        desc_parts.append("napisy PL")
                                    if desc_parts:
                                        prov_name = "%s — %s" % (prov_name, ", ".join(desc_parts))
                                except Exception:
                                    pass
                                try:
                                    _best_for_host = _best_source(links)
                                except Exception:
                                    _best_for_host = None
                                if _best_for_host is not None:
                                    try:
                                        qh = self._quality_of(_best_for_host)
                                    except Exception:
                                        qh = None
                                    if qh == "2160p":
                                        qh_str = "4K (2160p)"
                                    elif qh == "1080p":
                                        qh_str = "FULLHD (1080p)"
                                    elif qh == "720p":
                                        qh_str = "HD (720p)"
                                    else:
                                        qh_str = qh or "brak danych"
                                    size_gb = _size_gb_safe(_best_for_host)
                                    if size_gb > 0:
                                        size_str = "%.2f GB" % size_gb
                                    else:
                                        size_str = "brak danych"
                                else:
                                    qh_str = "brak danych"
                                    size_str = "brak danych"
                                # --- DODATEK: dopisz maksymalną rozdzielczość do etykiety hosta ---
                                try:
                                    _max_q = None
                                    for _q_cand in (links or []):
                                        try:
                                            _q_val = self._quality_of(_q_cand)
                                        except Exception:
                                            _q_val = None
                                        if _q_val == "2160p":
                                            _max_q = "4K"
                                            break
                                        elif _q_val == "1080p":
                                            if _max_q not in ("4K",):
                                                _max_q = "FULLHD"
                                        elif _q_val == "720p":
                                            if _max_q not in ("4K", "FULLHD"):
                                                _max_q = "HD"
                                    if _max_q:
                                        prov_name = "%s (Max %s)" % (prov_name, _max_q)
                                except Exception:
                                    pass
                                # --- on_account: złoty kolor jeśli jakikolwiek link hosta jest na koncie ---
                                if any(_it.get("on_account") for _it in links):
                                    prov_name = "[COLOR gold]%s[/COLOR]" % prov_name
                                options_hosts.append(prov_name)
                                payloads_hosts.append(key)
                            if options_hosts:
                                idx_host = xbmcgui.Dialog().select("Wybierz host PREMIUM — %s" % title, options_hosts)
                            else:
                                idx_host = -1
                        except Exception:
                            idx_host = -1

                        if idx_host < 0 or idx_host >= len(payloads_hosts):
                            return ("__CANCEL__", None)

                        chosen_key = payloads_hosts[idx_host]
                        info = host_map.get(chosen_key) or {}
                        chosen_items = info.get("items") or []
                        chosen_host_name = info.get("name") or chosen_key

                    base_seq = chosen_items or base_seq

                    # 7b) Lista WSZYSTKICH źródeł dla wybranego hosta: MULTI → LEKTOR/DUBBING → NAPISY (4K/FULLHD/HD, bez SD)
                    options_best = []
                    payloads_best = []
                    ai_flag = False

                    def _add_option_if_ok(_it, _prefix):
                        nonlocal ai_flag
                        if not _it:
                            return
                        if _it in payloads_best:
                            return
                        try:
                            q = self._quality_of(_it)
                        except Exception:
                            q = None
                        # filtr jakości: tylko 4K/FULLHD/HD — wyjątek: classic series (1950-2015) mogą mieć SD
                        _classic_bypass = getattr(self, "_ff_bypass_classic_series", False)
                        if q not in ("2160p", "1080p", "720p") and not _classic_bypass:
                            return
                        if q == "2160p":
                            q_str = "4K (2160p)"
                        elif q == "1080p":
                            q_str = "FULLHD (1080p)"
                        elif q == "720p":
                            q_str = "HD (720p)"
                        else:
                            q_str = q or "brak danych"
                        size_gb = _size_gb_safe(_it)
                        if size_gb > 0:
                            size_str = "%.2f GB" % size_gb
                        else:
                            size_str = "brak danych"
                        prov_name = (str(_it.get("provider") or _it.get("source") or "")).upper() or "?"
                        url_txt = (str(_it.get("url", "")) + " " + str(_it.get("label", ""))).lower()
                        inner_name = ""
                        if "wrzucaj" in url_txt:
                            inner_name = "WRZUCAJ"
                        elif "wrzuta" in url_txt:
                            inner_name = "WRZUTA"
                        elif "twojplik" in url_txt or "twoj-plik" in url_txt or "twoj_plik" in url_txt:
                            inner_name = "TWOJ PLIK"
                        elif "twoj" in url_txt and "plik" in url_txt:
                            inner_name = "TWOJ PLIK"
                        if inner_name:
                            host_str = "%s | %s" % (prov_name, inner_name)
                        else:
                            host_str = prov_name
                        is_ai_local = _has_ai_lektor(_it)
                        part_tag = _ff_detect_part(_it)
                        if is_ai_local:
                            ai_flag = True
                            label = "%s | %s | %s [AI LEKTOR] | %s | [%s]" % (_prefix, q_str, size_str, host_str, part_tag)
                        else:
                            label = "%s | %s | %s | %s | [%s]" % (_prefix, q_str, size_str, host_str, part_tag)
                        if _it.get("on_account"):
                            label = "[COLOR gold]%s[/COLOR]" % label
                        options_best.append(label)
                        payloads_best.append(_it)


                    # Sortowanie listy: PART 1 -> PART 2 -> NIEZNANE
                    try:
                        _combined = list(zip(options_best, payloads_best))
                        def _part_rank(lbl):
                            u = str(lbl).upper()
                            if "PART 1" in u:
                                return 0
                            if "PART 2" in u:
                                return 1
                            return 2
                        _combined.sort(key=lambda x: _part_rank(x[0]))
                        options_best = [x[0] for x in _combined]
                        payloads_best = [x[1] for x in _combined]
                    except Exception:
                        pass

                    # Zbieramy wszystkie linki z wybranego hosta
                    all_items = list(base_seq or [])
                   # MULTI (audio wielojęzyczne / multi)
                    try:
                        multi_candidates = [it for it in all_items if _is_multi_no_pl(it)]
                    except Exception:
                        multi_candidates = []
                    for it in multi_candidates:
                        _add_option_if_ok(it, "MULTI")

                    # Lektor / Dubbing PL (w tym AI)
                    try:
                        voice_candidates = [it for it in all_items if _is_voice_pl_strict(it) or _has_ai_lektor(it)]
                    except Exception:
                        voice_candidates = []
                    for it in voice_candidates:
                        _add_option_if_ok(it, "Lektor / Dubbing PL")

                    # Napisy PL
                    try:
                        subs_candidates = [it for it in all_items if _is_subs_only(it)]
                    except Exception:
                        subs_candidates = []
                    for it in subs_candidates:
                        _add_option_if_ok(it, "Napisy PL")

                    # CLASSIC SERIES (1950-2015): dodaj też linki bez PL (oryginał, angielski itp.)
                    try:
                        if getattr(self, '_ff_bypass_classic_series', False):
                            _already = set(id(x) for x in payloads_best)
                            for it in all_items:
                                if id(it) not in _already:
                                    _add_option_if_ok(it, "Oryginał")
                    except Exception:
                        pass

                    if options_best:
                        if ai_flag:
                            heading_best = "UWAGA: wykryto LEKTORA AI. Wybierz plik — %s" % (str(chosen_host_name) or "").upper()
                        else:
                            heading_best = "Wybierz plik — %s" % (str(chosen_host_name) or "").upper()
                        idx_best = xbmcgui.Dialog().select(heading_best, options_best)
                        if idx_best < 0 or idx_best >= len(payloads_best):
                            return ("__CANCEL__", None)
                        best = payloads_best[idx_best]
                    else:
                        # Jeśli po filtrach nic nie zostało, fallback do najlepszego dostępnego źródła
                        best = _best_source(base_seq)
                        # --- PATCH: obsługa SD w PREMIUM ---
                        allowed_qualities = ("2160p", "1080p", "720p")
                        try:
                            q_fallback = self._quality_of(best) if best else None
                        except Exception:
                            q_fallback = None
                        if q_fallback not in allowed_qualities:
                            # sprawdź, czy w ogóle istnieje jakakolwiek lepsza jakość
                            has_better = False
                            for item in (base_seq or []):
                                try:
                                    if self._quality_of(item) in allowed_qualities:
                                        has_better = True
                                        break
                                except Exception:
                                    pass
                            if has_better:
                                # były lepsze jakości, więc SD blokujemy
                                best = None
                            else:
                                # jest tylko SD → zapytaj użytkownika
                                dlg = xbmcgui.Dialog()
                                ok = dlg.yesno(
                                    "FanVodPL",
                                    "Nie znaleziono 4K / 1080p / 720p.",
                                    "Dostępne jest tylko SD.",
                                    "Oglądać mimo to?"
                                )
                                if not ok:
                                    best = None
                        # --- KONIEC PATCHA ---
            else:
                # Ręczny wybór spośród darmowych hostów
                try:
                    options_hosts = []
                    payloads_hosts = []
                    for _it in (base_seq or []):
                        prov = (str(_it.get("provider") or _it.get("source") or "?")).upper()
                        try:
                            q = self._quality_of(_it)
                        except Exception:
                            q = None
                        if q == "2160p":
                            q_str = "4K (2160p)"
                        elif q == "1080p":
                            q_str = "FULLHD (1080p)"
                        elif q == "720p":
                            q_str = "HD (720p)"
                        else:
                            q_str = q or "brak danych"
                        size_gb = _size_gb_safe(_it)
                        if size_gb > 0:
                            size_str = "%.2f GB" % size_gb
                        else:
                            size_str = "brak danych"
                        options_hosts.append("%s | %s | %s" % (prov, q_str, size_str))
                        payloads_hosts.append(_it)
                    if options_hosts:
                        idx_host = xbmcgui.Dialog().select("Wybierz darmowy host — %s" % title, options_hosts)
                    else:
                        idx_host = -1
                except Exception:
                    idx_host = -1

                if idx_host < 0 or idx_host >= len(payloads_hosts):
                    return ("__CANCEL__", None)
                best = payloads_hosts[idx_host]

            if not best:
                try:
                    from resources.lib.modules import control
                    control.infoDialog("Brak dopasowanych linków po filtrach.", "FanVodPL", time=3000)
                except Exception:
                    pass
                return ("__CANCEL__", None)

# Kandydat alternatywny: najlepszy plik z napisami PL (bez lektora)
            subs_best = None
            subs_q_str = None
            subs_size_str = None
            subs_summary = None
            try:
                subs_candidates = [it for it in (base_seq or []) if _is_subs_only(it)]
            except Exception:
                subs_candidates = []
            if subs_candidates:
                subs_candidates = list(subs_candidates)
                subs_candidates.sort(key=lambda it: (_quality_rank(it), -_size_gb_safe(it)))
                subs_best = subs_candidates[0]
                try:
                    q_sub = self._quality_of(subs_best)
                except Exception:
                    q_sub = None
                if q_sub == "2160p":
                    subs_q_str = "4K (2160p)"
                elif q_sub == "1080p":
                    subs_q_str = "FULLHD (1080p)"
                elif q_sub == "720p":
                    subs_q_str = "HD (720p)"
                else:
                    subs_q_str = q_sub or "brak danych"
                size_sub_gb = _size_gb_safe(subs_best)
                if size_sub_gb > 0:
                    subs_size_str = "%.2f GB" % size_sub_gb
                else:
                    subs_size_str = "brak danych"
                subs_summary = "%s | Napisy PL | %s" % (subs_q_str, subs_size_str)

            # 8) Informacja o najlepszym pliku
            try:
                q = self._quality_of(best)
            except Exception:
                q = None
            if q == "2160p":
                q_str = "4K (2160p)"
            elif q == "1080p":
                q_str = "FULLHD (1080p)"
            elif q == "720p":
                q_str = "HD (720p)"
            else:
                q_str = q or "brak danych"

            tmeta = _tmeta(best)
            lang = str(best.get("language", "")).lower()
            url_l = str(best.get("url", "")).lower()
            # Wykrywanie lektora AI – najpierw po labelu/infos, a jeśli brak, to po URL
            is_ai = _has_ai_lektor(best)
            # Jeśli wykryto AI, traktujemy to jak lektora (nie jako klasyczne MULTI),
            # żeby zawsze móc zaproponować wersję z napisami.
            if _is_multi_no_pl(best) and not is_ai:
                if (_rx_pl_tok.search(tmeta) is not None) or (lang in ("pl", "polish", "polski")):
                    tag_str = "MULTI PL"
                else:
                    tag_str = "MULTI"
            elif _is_voice_pl_strict(best):
                if is_ai:
                    tag_str = "Lektor AI / Dubbing PL"
                else:
                    tag_str = "Lektor / Dubbing PL"
            elif _is_subs_only(best):
                tag_str = "Napisy PL"
            else:
                tag_str = "Inny"

            size_gb = _size_gb_safe(best)
            if size_gb > 0:
                size_str = "%.2f GB" % size_gb
            else:
                size_str = "brak danych"

            heading = "Najlepsze źródło — %s" % ("PREMIUM" if mode == "premium" else "DARMOWE")
            line1 = "Rozdzielczość: %s" % q_str
            if "Lektor AI" in tag_str and subs_best is not None and subs_summary is not None:
                line2 = "Typ: %s" % tag_str
                line3 = "UWAGA: wykryto LEKTORA AI. Można wybrać wersję z napisami."
            elif "Lektor AI" in tag_str:
                line2 = "Typ: %s" % tag_str
                line3 = "UWAGA: wykryto LEKTORA AI (sztuczny lektor)."
            else:
                line2 = "Typ: %s" % tag_str
                line3 = "Rozmiar pliku: %s" % size_str

            # 9) Drugie okno: OGLĄDAJ / POBIERZ
            # Składamy krótki opis, żeby użytkownik widział, jaki plik będzie użyty.
            if "Lektor AI" in tag_str:
                summary = "%s | %s | %s | AI – sztuczny lektor" % (q_str, tag_str, size_str)
            else:
                summary = "%s | %s | %s" % (q_str, tag_str, size_str)
            if ("Lektor AI" in tag_str) and subs_best is not None and subs_summary is not None:
                heading_full = "UWAGA: wykryto LEKTORA AI. Można wybrać wersję z napisami."
            else:
                heading_full = "%s — %s" % ("PREMIUM" if mode == "premium" else "DARMOWE", summary )

            if mode == "premium":
                # PREMIUM – można oglądać online albo pobierać na dysk
                use_subs = False
                try:
                    res = xbmcgui.Dialog().yesno(
                        heading_full,
                        line1,
                        line2,
                        line3,
                        nolabel="POBRAĆ PLIK NA DYSK",
                        yeslabel="OGLĄDAĆ ONLINE"
                    )
                except Exception:
                    # Jeśli yesno() z jakiegoś powodu się wywali (skórka, wersja Kodi),
                    # robimy fallback na zwykłe okno select, żeby ZAWSZE pokazać wybór.
                    try:
                        options = [
                            "OGLĄDAĆ ONLINE — %s" % summary,
                            "POBRAĆ PLIK NA DYSK — %s" % summary,
                        ]
                        payloads = ["stream_ai", "download_ai"]
                        if ("Lektor AI" in tag_str) and subs_best is not None and subs_summary is not None:
                            options.append("OGLĄDAĆ ONLINE — %s [NAPISY PL]" % subs_summary)
                            payloads.append("stream_subs")
                            options.append("POBRAĆ PLIK NA DYSK — %s [NAPISY PL]" % subs_summary)
                            payloads.append("download_subs")
                        idx2 = xbmcgui.Dialog().select(
                            heading_full,
                            options
                        )
                    except Exception:
                        # Ostateczny fallback – traktuj jak OGLĄDAJ ONLINE
                        res = True
                    else:
                        if idx2 < 0 or idx2 >= len(payloads):
                            return ("__CANCEL__", None)
                        choice = payloads[idx2]
                        if choice == "stream_ai":
                            res = True
                            use_subs = False
                        elif choice == "download_ai":
                            res = False
                            use_subs = False
                        elif choice == "stream_subs":
                            res = True
                            use_subs = True
                        elif choice == "download_subs":
                            res = False
                            use_subs = True
                        else:
                            return ("__CANCEL__", None)

                # Jeśli użytkownik wybrał wersję z napisami, podmień najlepszy plik
                if use_subs and subs_best is not None:
                    best = subs_best
                    if subs_q_str is not None:
                        q_str = subs_q_str
                    tag_str = "Napisy PL"
                    if subs_size_str is not None:
                        summary = "%s | %s | %s" % (q_str, tag_str, subs_size_str)
                        heading_full = "%s — %s" % ("PREMIUM" if mode == "premium" else "DARMOWE", summary)

                # True -> OGLĄDAJ ONLINE
                if res:
                    chosen_label = "%s — %s, %s" % ("PREMIUM", q_str, tag_str)
                    return (chosen_label, [best])

                # False -> POBIERZ PLIK NA DYSK
                try:
                    from urllib.parse import quote_plus
                    import json as _json
                    plg = sys.argv[0]
                    source_param = quote_plus(_json.dumps([best]))
                    name_param = quote_plus(best.get("label", "download"))
                    image_param = quote_plus(best.get("thumbnail") or best.get("icon") or "")
                    extrainfo_param = quote_plus(best.get("info", "") or "")
                    cmd = f"{plg}?action=download&name={name_param}&image={image_param}&source={source_param}&extrainfo={extrainfo_param}"
                    xbmc.executebuiltin(f"RunPlugin({cmd})")
                except Exception:
                    try:
                        xbmc.log("[FanVodPL AutoQ] Błąd przy uruchamianiu pobierania.", xbmc.LOGNOTICE)
                    except Exception:
                        pass

                return ("__CANCEL__", None)

            else:
                # DARMOWE – tylko oglądanie online, bez opcji pobierania
                try:
                    res = xbmcgui.Dialog().yesno(
                        heading_full,
                        line1,
                        line2,
                        line3,
                        nolabel="ANULUJ",
                        yeslabel="OGLĄDAĆ ONLINE"
                    )
                except Exception:
                    # Fallback: select z jedną opcją oglądania
                    try:
                        idx2 = xbmcgui.Dialog().select(
                            heading_full,
                            [
                                "OGLĄDAĆ ONLINE — %s" % summary,
                                "ANULUJ",
                            ]
                        )
                    except Exception:
                        # Ostateczny fallback – traktuj jak OGLĄDAJ ONLINE
                        res = True
                    else:
                        if idx2 == 0:
                            res = True
                        else:
                            return ("__CANCEL__", None)

                if res:
                    chosen_label = "%s — %s, %s" % ("DARMOWE", q_str, tag_str)
                    return (chosen_label, [best])

                return ("__CANCEL__", None)

    def play(
            self,
            title,
            localtitle,
            year,
            imdb,
            tvdb,
            tmdb,
            season,
            episode,
            tvshowtitle,
            premiered,
            meta,
            select,
            customTitles=None,
            originalname="",
            epimdb="",
        ):
        fflog(f'[play] start', 0)
        # fflog(f'\n{title=} \n{localtitle=} \n{year=} \n{imdb=} \n{tvdb=} \n{tmdb=} \n{season=} \n{episode=} \n{tvshowtitle=} \n{premiered=} \n{meta=} \n{select=} \n{customTitles=} \n{originalname=}  \n{epimdb=}',1,1)

        meta1 = None

        if not originalname and meta:
            try:
                if isinstance(meta, str):
                    meta1 = json.loads(meta)
                originalname = meta1.get("originalname", "")
                #fflog(f'1A {originalname=}')
            except Exception:
                originalname = ""
                pass

        if not originalname:
            try:
                meta1 = cache.cache_get("superinfo" + f"_{tmdb or imdb}")  # zrobiłem to kiedyś dla odcinków głównie
                if meta1:
                    meta1 = meta1["value"]
                    meta1 = literal_eval(meta1)
                    #if imdb == meta1.get("imdb", "") or tmdb == meta1.get("tmdb", ""):  # tu chyba niepotrzebna ta weryfikacja, bo pobrany plik z cache musi pasować
                    originalname = meta1.get("originalname", "")
                    #fflog(f'1B {originalname=}')
                else:
                    if episode:
                        from resources.lib.indexers import episodes
                        meta1 = episodes.episodes().get_meta_for_tvshow(imdb=imdb, tmdb=tmdb)
                    else:
                        from resources.lib.indexers import movies
                        meta1 = movies.movies().get_meta_for_movie(imdb=imdb, tmdb=tmdb)
                    # fflog(f'meta1={json.dumps(meta1, indent=2)}',1,1)
                    originalname = meta1.get("originalname", "")
                    fflog(f'1C {originalname=}',1,1)
            except Exception:
                pass
            # meta = meta1 if not meta else meta  # tylko, że to jest trochę inna meta, bo po superinfo jest poprawianie

        # przydatne szczególnie dla krótkich linków
        if not tvshowtitle and episode and (tmdb or imdb):
            # czy brać jeszcze wariant pod uwagę, że jest przekazana meta jako argument funkcji ?
            """
            if meta:
                if isinstance(meta, str):
                    meta1 = json.loads(meta)
            else:
            """
            fflog(f'próba pobrania metadanych z bazy cache dla odcinka (bo brakuje) | {tvshowtitle=}  {season=} {episode=}  {tmdb=}  {imdb=}')
            if season or season == 0:
                meta1 = cache.cache_get("episodes" + f"_{tmdb or imdb}_s{season}")
            else:
                meta1 = cache.cache_get("episodes" + f"_{tmdb or imdb}")
            if not meta1:
                fflog("trzeba pobrać dane odcinka z serwisu tmdb.org")
                from resources.lib.indexers import episodes
                meta1 = episodes.episodes().tmdb_list(imdb=imdb, tmdb=tmdb, season=season)
            else:
                #from ast import literal_eval
                fflog(f'dane odcinka są w bazie')
                meta1 = meta1["value"]
                meta1 = literal_eval(meta1)
            meta1 = meta1[int(episode)-1]
            # uzupełniene brakujących danych
            tvshowtitle = meta1.get("tvshowtitle")
            title = meta1.get("title")  # tytuł odcinka ? Czy może być pusty ?
            localtitle = meta1.get("localtvshowtitle") or ""  # ? a może label? a może nie ważne jaki
            localtitle = meta1.get("label") if not localtitle else localtitle
            originalname = meta1.get("originaltvshowtitle", "") or originalname
            year = meta1.get("year")
            premiered = meta1.get("premiered")
            imdb = meta1.get("imdb") if not imdb or imdb=='None' or imdb=='0' else imdb
            tmdb = meta1.get("tmdb") if not tmdb or tmdb=='None' or tmdb=='0' else tmdb
            tvdb = meta1.get("tvdb") if not tvdb or tvdb=='None' or tvdb=='0' else tvdb
            # meta = meta1 if not meta else meta  # nie wszystko może pasować

        if not title and not episode and (tmdb or imdb):  # dla filmów
            fflog(f'próba pobrania metadanych z cache dla filmu (bo brakuje) | {title=}  {tmdb=}  {imdb=}')
            meta1 = cache.cache_get("superinfo" + f"_{tmdb or imdb}")  # sprawdzenie, czy nie ma już w cache
            if not meta1:
                fflog('potrzeba jednak pobrać informacje o filmie przez super_info.py')
                from resources.lib.indexers.super_info import SuperInfo
                media_list = [{'tmdb': tmdb, 'imdb': imdb}]
                import requests
                session = requests.Session()
                lang = control.apiLanguage()["tmdb"]
                super_info_obj = SuperInfo(media_list, session, lang)
                super_info_obj.get_info(0)
                meta1 = cache.cache_get("superinfo" + f"_{tmdb or imdb}")
            if meta1:
                meta1 = meta1["value"]
                meta1 = literal_eval(meta1)
            # uzupełniene brakujących danych
            title = meta1.get("originaltitle")
            localtitle = meta1.get("title")
            originalname = meta1.get("originalname", "") or originalname
            year = meta1.get("year")
            imdb = meta1.get("imdb") if not imdb or imdb=='None' or imdb=='0' else imdb
            tmdb = meta1.get("tmdb") if not tmdb or tmdb=='None' or tmdb=='0' else tmdb
            tvdb = meta1.get("tvdb") if not tvdb or tvdb=='None' or tvdb=='0' else tvdb
            # meta = meta1 if not meta else meta  # nie wszystko musi pasować
        # fflog(f'meta1={json.dumps(meta1, indent=2)}',1,1)

        if (not imdb or imdb=="0" or imdb=="None") and tmdb:
            fflog(f'brakuje {imdb=}, a może on być potrzebny',1,1)
            if tmdb and tmdb != "0" and tmdb != "None":
                if not meta1:
                    if meta:
                        meta1 = json.loads(meta)
                    else:
                        if not episode:  # czyli filmy
                            meta1 = cache.cache_get("superinfo" + f"_{tmdb or imdb}")
                            if meta1:
                                meta1 = meta1["value"]
                                meta1 = literal_eval(meta1)
                                # fflog(f'meta1={json.dumps(meta1, indent=2)}',1,1)
                            else:
                                # trzeba pobrać z neta
                                pass
                        else:
                            if season or season == 0:
                                meta1 = cache.cache_get("episodes" + f"_{tmdb or imdb}_s{season}")
                            else:
                                meta1 = cache.cache_get("episodes" + f"_{tmdb or imdb}")
                                if meta1:
                                    meta1 = meta1["value"]
                                    meta1 = literal_eval(meta1)
                                    meta1 = meta1[int(episode)-1]
                                    # fflog(f'meta1={json.dumps(meta1, indent=2)}',1,1)
                                else:
                                    # trzeba pobrać z neta
                                    pass
                imdb = meta1.get("imdb") if not imdb or imdb=='None' or imdb=='0' else imdb
                tvdb = meta1.get("tvdb") if not tvdb or tvdb=='None' or tvdb=='0' else tvdb
                fflog(f'{imdb=}',1,1)
            else:
                fflog(f'ale problem, bo {tmdb=}',1,1)
            if not imdb:
                fflog(f'nie udało się ustalić numeru imdb',1,1)
                # coś dać, aby nie szukało ponownie źródeł
                # wskazane, aby był to typ string, bo jest to potem wstawiane do pamięci
                # imdb = '-'
                # imdb = '0'
                imdb = 'None'
                pass
                fflog(f'{imdb=}',1,1)

        # fflog(f'\n{title=} \n{localtitle=} \n{year=} \n{imdb=} \n{tvdb=} \n{tmdb=} \n{season=} \n{episode=} \n{tvshowtitle=} \n{premiered=} \n{meta=} \n{select=} \n{customTitles=} \n{originalname=}  \n{epimdb=}',1,1)

        if not title and not tvshowtitle:
            fflog(f'Błąd - brak zmiennej {title=} lub {tvshowtitle=}')
            control.dialog.notification('FanVodPL', 'błąd: brak zmiennej "title" lub "tvshowtitle"', xbmcgui.NOTIFICATION_ERROR)
            return

        if not meta and meta1:
            # meta = json.dumps(meta1)  # tutaj lepiej nie (przynajmniej dla seriali, bo gubi rekordy np. tvshowtitle), bo to trochę inna meta, bo po superinfo jest przerabiane potem
            pass  # chyba, że zostały pobrane dane odcinka z serwisu tmdb.org (może sprawdzać obecność "tvshowtitle" dla seriali?)
        # meta1 = None

        # to z default.py
        FFlastpath = control.window.getProperty('FanVodPL.var.lastpath')  # z pamięci
        FFlastpath = eval(FFlastpath) if FFlastpath else {}  # tylko jak Kodi wczytuje folder z cachu, to ta zmienna się nie zmienia (bo plugin nie jest wywoływany)
        fflog(f'{FFlastpath=}', 0)

        folderpath = control.infoLabel('Container.FolderPath')  # może być też puste i nie zawsze okazuje się, że jest poprzednim, np. gdy odpalamy widżety
        # fflog(f'{folderpath=}')
        imdb_curr = ''

        params1 = dict(parse_qsl(folderpath.split('?')[-1]))
        fflog(f'{params1=}', 0)

        action1 = params1.get('action')  # może być też puste

        params2 = dict(parse_qsl(sys.argv[2][1:]))
        fflog(f'{params2=}', 0)
        if params2.get("r"):
            if (params1 := control.window.getProperty('FanVodPL.var.before_r')) or (params1 := dict(parse_qsl(folderpath.split('?')[-1]))) and not params1.get("r"):
                params1 = eval(params1) if isinstance(params1, str) else params1
                # fflog(f'{params1=}')
                params2.update(params1)
        fflog(f'{params2=}', 0)

        action2 = params2.get('action')

        # referer = folderpath if action1 != action2 else ''  # niepotrzebna ta zmienna
        # log(f'{referer=}')

        fflog(f'\n{params1=}  \n{params2=}', 0)
        fflog(f'{action1=}  {action2=}', 0)
        # if action1 not in ["play", "alterSources"]:
        # fflog(f'{control.setting("crefresh_always")=}')
        if action1 != action2 and action1 != "showItems" or control.setting("crefresh_always")=="true":
            if FFlastpath != params2:  # dodałem, ale nie wiem, czy nie będzie ujemnych skutków
                fflog(f'wymuszenie odświeżenia listy źródeł', 1)
                control.window.clearProperty('imdb_id')  # aby odświeżyć listę źródeł

        # params = None
        if (url := params2.get('url')):  # gdy z menu kontekstowego
            fflog(f'{url=}', 0)
            # params = params2  # nie wiem, czy to potrzebne
            params2 = dict(parse_qsl(url.split('?')[-1]))  # czy to nie zepsuje użycia params2 w dalszej części, już po zdecydowaniu, czy odświeżać czy nie?
            fflog(f'{params2=}', 0)

        items = None

        if control.setting("crefresh") != "true":

            # imdb_curr = params2.get('imdb', '')
            imdb_curr = params2.get('imdb', imdb)  # gdy krótkie ścieżki, to nie będzie takich danych w adresie
            # fflog(f'{imdb_curr=}')
            # imdb_curr = imdb_curr if imdb_curr else imdb if imdb else ''  # zastanowić się nad tym
            # fflog(f'{imdb_curr=}')
            if episode and imdb_curr is not None:
                # imdb_curr += "|" + params2.get('epimdb', '') + "|s" + params2.get('season', '') + "|e" + params2.get('episode', '')
                # imdb_curr += "|" + params2.get('epimdb', epimdb) + "|s" + params2.get('season', season) + "|e" + params2.get('episode', episode)
                imdb_curr += "|" + epimdb + "|s" + str(season) + "|e" + str(episode)  # ważne, jak modyfikowane do wyszukiwarki
            fflog(f'{imdb_curr=}', 0)

            imdb_last = control.window.getProperty('imdb_id')  # jeśli nie zostanie wyczyszczone
            fflog(f'{imdb_last=}', 0)
            #imdb_last = None if control.setting("crefresh") == "true" else imdb_last  # uwzględnienie ustawień wtyczki (ale czy to nie jest już zbędne?)
            if imdb_last:
                if (
                    imdb_curr == imdb_last  # to byłoby najlepsze, ale czasami coś gubił i mimo, że nie musiał, to odświeżał
                    # or customTitles is not None and imdb_curr.split("|")[0] == imdb_last.split("|")[0]
                    # or action1 == action2  # czy to nie będzie kolidowało, gdy kotś wyświetla w okienku?
                    # or params1 == params2  # or customTitles is not None  # dodałem ostatnio - tylko, że to coś koliduje, gdy odpala się z widżetu - nie odświeża źródeł, jak jest inny film
                    # or (params1 == params2 and params1 == FFlastpath)  # chyba nie zaszkodzi
                    or FFlastpath.get("action") == "playItem"  # nie odświeżamy po odtwarzaniu
                ):
                    fflog(f'{FFlastpath.get("action")=}', 0) if imdb_curr != imdb_last else ''
                    imdb_curr = imdb_last if imdb_curr != imdb_last else imdb_curr  # pomaga w przypadku modyfikowanych danych do wyszukiwarki
                    fflog(f'[play] próba pobrania wyników z poprzedniego wyszukiwania', 1)
                    items = control.window.getProperty(self.itemProperty)
                    if items:
                        # fflog(f'[play] coś odczytano', 1)
                        # fflog(f'[play] {items=}', 1)
                        items = json.loads(items)
                        fflog(f'[play] {len(items)=}', 1)
                    else:
                        fflog(f'[play] brak zapamiętanych', 1)
                else:
                    fflog(f'[play] nie zostaną wzięte wyniki z ostatniego wyszukiwania źródeł', 0)
                    fflog(f'{imdb_curr=}  !=  {imdb_last=}  |  {customTitles=}', 1)
                    # fflog(f'\n   {params1=}\n   {params2=}\n{FFlastpath=}', 1)
                    pass
            else:
                pass

        # params2 = params if params else params2  # nie wiem, czy to dobrze
        # params = None

        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}

        #if control.window.getProperty("TMDbHelper.ServiceStarted") == "True":
        if not meta:

            if meta1:
                meta = meta1  # jest ryzyko dla seriali, bo gubi rekordy np. tvshowtitle), bo to trochę inna meta, bo po superinfo jest przerabiane potem, chyba, że wcześniej zostały pobrane dane dla serialu
                pass  # ale i tak to jednak trochę lepszę niż nic (bo np. rok jest potrzebny w meta)

            props = ["title", "localtitle", "originaltitle", "year", "genre", "country", "rating", "votes", "mpaa", "director", "writer", "studio", "Tagline", "thumb", "Art(poster)", "poster", "trailer", "plot", "label", "duration"]
            #if "tmdb_type=tv" in folderpath:
            if tvshowtitle:
                # meta.update({'mediatype': 'episode'})
                props += ["season", "episode", "tvshowtitle", "localtvshowtitle", "premiered", "Art(season.poster)"]
            props = set(props)

            #can_get_from_tmdbhelper = False
            # if folderpath.startswith("plugin://plugin.video.themoviedb.helper/") and control.infoLabel("ListItem.Property(IMDb_ID)") in [imdb, epimdb]:
            if "plugin.video.fanvodpl" not in control.infoLabel("Container.PluginName") and control.infoLabel("ListItem.Property(IMDb_ID)") in [imdb, epimdb]:
                #can_get_from_tmdbhelper = True
                fflog('próba pobrania danych meta z ListItemu wybranej pozycji')
                for p in props:
                    if (val := control.infoLabel('ListItem.'+p.capitalize())) and val != 'ListItem.'+p.capitalize():
                        fflog(f'{p=} {val=}',0,1)
                        meta.update({p: val})
                        pass
                if (val := control.infoLabel("ListItem.Property(original_language)")):
                    meta.update({"original_language": val})
            else:
                fflog('próba pobrania danych meta z adresu wywołania url',1,1)
                """
                params2 = dict(parse_qsl(sys.argv[2][1:]))
                if params2.get("r"):
                    if (params1 := control.window.getProperty('FanVodPL.var.before_r')) or (params1 := dict(parse_qsl(folderpath.split('?')[-1]))) and not params1.get("r"):
                        params1 = eval(params1) if isinstance(params1, str) else params1
                        # fflog(f'{params1=}')
                        params2.update(params1)
                """
                for p in props:
                    if (val := params2.get(p, "")):
                        fflog(f'{p=} {val=}',0,1)
                        if val != "None" or "title" in p:  # dodatkowe sprawdzenie, ale okazało się, że jest film o o tytule "None"
                            meta.update({p: val})
                        else:
                            fflog(f' odrzucam {p=} bo {val=}',1,1)  # dla kontroli
                            pass
                # korekty na potrzeby FanVodPL
                if (val := meta.get("localtitle")):
                    meta.update({"title": val});  meta.pop('localtitle')
                if (val := meta.get("localtvshowtitle")):
                    meta.update({"tvshowtitle": val});  meta.pop('localtvshowtitle')

            # pozostałe korekty na potrzeby FanVodPL
            #fflog(f"{meta.get('thumb')=}")
            if not (thumb := meta.get('thumb')) or thumb == "None" or ".strm/" in thumb:
                meta.pop("thumb", None)
            if not (poster := meta.get('poster')) or poster == "ListItem.Poster" or ".strm/" in poster:
                meta.pop("poster", None)
                #if not (poster := control.infoLabel('ListItem.Icon')) or not can_get_from_tmdbhelper:
                if not (poster := control.infoLabel('ListItem.Icon')) or params2.get("poster"):
                    poster = params2.get("poster", "")
                if poster and ".strm/" not in poster:  # a co jak będzie ".mkv/" ?
                    # fflog(f'{poster=}')
                    meta.update({'poster': poster})
            if tvshowtitle:
                if (poster := meta.get("Art(season.poster)")):
                    meta.update({'poster': poster});  meta.pop("Art(season.poster)", None)
            else:
                if (poster := meta.get("Art(poster)")):
                    meta.update({'poster': poster});  meta.pop("Art(poster)", None)
            #fflog(f'{meta=}')
        # bo indexer z FF też daje angielski zamiast polskiego
        if (val := meta.get("localtvshowtitle")):
            meta.update({"tvshowtitle": val});  meta.pop('localtvshowtitle')
            pass

        # control.window.clearProperty(self.metaProperty)  # po co to ?
        control.window.setProperty(self.metaProperty, json.dumps(meta))

        # fflog(f'meta1={json.dumps(meta1, indent=2)}',1,1)
        # fflog(f' meta={json.dumps(meta,  indent=2)}',1,1)  # odchudzone (bo pop'y były po drodze)

        duration = meta.get("duration") or 0
        poster = meta.get("poster") or ""
        # fflog(f'{poster=}',1,1)


        if not items:
            # pobranie źródeł (wyszukiwanie)
            fflog(f'[play] potrzeba wyszukania źródeł', 1)

            control.window.clearProperty(self.itemProperty)  # wyczyszczenie poprzednich wyników

            fflog(f'[play] {title=} {localtitle=} {year=} {imdb=} {tvdb=} {tmdb=} {season=} {episode=} {tvshowtitle=} {premiered=} {originalname=} {customTitles=}', 1)

            if customTitles is not None:
                fflog(f'ustawienie znacznika do wyczyszczenia cache dla wszystkich serwisów, bo {customTitles=}',1,1)
                control.window.setProperty('clear_SourceCache_for', 'all')  # jak ktoś używa enableSourceCache

            # operacja szukania źródeł
            items = self.getSources(title, localtitle, year, imdb, tvdb, tmdb, season, episode, tvshowtitle, premiered, originalname, duration, poster)

            # === DOUBLE-EP PART 1/PART 2 SELECTION PATCH ===
            # Obsługuje dwa scenariusze:
            # A) items zawiera jednocześnie Part1 i Part2 (getSources zwróciło oba) → pytaj o wybór
            # B) items ma tylko Part1, brak Part2 → szukaj Part2 w paired episode (E+1) → pytaj
            try:
                _season_i = int(str(season)) if str(season).isdigit() else None
                _episode_i = int(str(episode)) if str(episode).isdigit() else None

                if _season_i is not None and _episode_i is not None and items:

                    def _items_have_part(item_list, part_num):
                        tag = "PART %d" % part_num
                        return any(_ff_detect_part(_it).upper().startswith(tag) for _it in (item_list or []))

                    def _items_with_part(item_list, part_num):
                        tag = "PART %d" % part_num
                        return [_it for _it in (item_list or []) if _ff_detect_part(_it).upper().startswith(tag)]

                    has_part1 = _items_have_part(items, 1)
                    has_part2 = _items_have_part(items, 2)

                    fflog(f"[DOUBLE-EP] {_episode_i=} {has_part1=} {has_part2=} items_count={len(items)}", 0)

                    part1_items = _items_with_part(items, 1)
                    part2_items = _items_with_part(items, 2)

                    if has_part1 and has_part2:
                        # === SCENARIUSZ A: oba Parts już w items — pytaj od razu ===
                        fflog(f"[DOUBLE-EP] Scenariusz A: oba Parts w items (p1={len(part1_items)}, p2={len(part2_items)})", 0)
                        try:
                            import xbmcgui as _xbmcgui_dep
                            _choice = _xbmcgui_dep.Dialog().select(
                                "Odcinek podzielony — wybierz część",
                                [
                                    "▶  Part 1  (pierwsza część odcinka)",
                                    "▶  Part 2  (druga część odcinka)",
                                ]
                            )
                            if _choice == 1:
                                items = part2_items
                                fflog("[DOUBLE-EP] Użytkownik wybrał Part 2", 0)
                            elif _choice == 0:
                                items = part1_items
                                fflog("[DOUBLE-EP] Użytkownik wybrał Part 1", 0)
                            else:
                                items = part1_items  # anuluj → domyślnie Part 1
                                fflog("[DOUBLE-EP] Dialog anulowany → domyślnie Part 1", 0)
                        except Exception:
                            fflog_exc(1)

                    elif has_part1 and not has_part2:
                        # === SCENARIUSZ B: tylko Part1 — szukaj Part2 w paired episode (E+1) ===
                        _pair_ep = str(_episode_i + 1)
                        fflog(f"[DOUBLE-EP] Scenariusz B: szukam Part2 w E{_pair_ep}", 0)
                        try:
                            extra_items = self.getSources(
                                title, localtitle, year, imdb, tvdb, tmdb, season, _pair_ep,
                                tvshowtitle, premiered, originalname, duration, poster
                            )
                        except Exception:
                            extra_items = []

                        extra_part2 = _items_with_part(extra_items, 2)
                        fflog(f"[DOUBLE-EP] Znaleziono Part2 z E{_pair_ep}: {len(extra_part2)}", 0)

                        if extra_part2:
                            try:
                                import xbmcgui as _xbmcgui_dep
                                _choice = _xbmcgui_dep.Dialog().select(
                                    "Odcinek podzielony — wybierz część",
                                    [
                                        "▶  Part 1  (pierwsza część odcinka)",
                                        "▶  Part 2  (druga część odcinka)",
                                    ]
                                )
                                if _choice == 1:
                                    items = extra_part2
                                    fflog("[DOUBLE-EP] Użytkownik wybrał Part 2", 0)
                                elif _choice == 0:
                                    fflog("[DOUBLE-EP] Użytkownik wybrał Part 1 (items bez zmian)", 0)
                                else:
                                    fflog("[DOUBLE-EP] Dialog anulowany → domyślnie Part 1", 0)
                            except Exception:
                                fflog_exc(1)

            except Exception:
                fflog_exc(1)
            # === END DOUBLE-EP PART 1/PART 2 SELECTION PATCH ===

            fflog(f'[play] otrzymano jakieś wyniki', 0)
            fflog(f'{len(items)=}')  # może być zero, ale mogą być "w koszu"
        else:
            fflog(f'[play] nie będzie procesu wyszukiwania źródeł', 0)
            pass
        # === [AUTO JAKOŚĆ – GLOBAL TRIGGER TUŻ PO ZEBRANIU ITEMS] ===
        try:
            if items and isinstance(items, list) and len(items) > 0:
                # --- SD policy context (legacy exception) ---
                try:
                    self._ff_ctx_year = int(year) if year not in (None, "", "None", "0") else None
                except Exception:
                    self._ff_ctx_year = None

                # WAŻNE: dla odcinków podzielonych (PART 1/2) zostawiamy bypass dialogu jakości,
                # bo pod rząd lecą dwa dialogi (wybór PART + AUTO JAKOŚĆ) i na Android/Kodi bywa ANULUJ=-1.
                _is_part = False
                try:
                    _is_part = any(_ff_detect_part(_it).upper().startswith("PART ") for _it in (items or []))
                except Exception:
                    _is_part = False

                _autoplay_mode = (control.setting("hosts.mode") == "2")

                if _is_part and _autoplay_mode:
                    # przy autoplay + PART pomijamy dialog jakości żeby nie było dwóch dialogów pod rząd
                    chosen_label, filtered_items = ("__SINGLE__", items)
                    fflog('[AUTO JAKOŚĆ] PART + autoplay -> bypass dialog jakości', 1, 1)
                elif len(items) == 1 and _is_part:
                    chosen_label, filtered_items = ("__SINGLE__", items)
                    fflog('[AUTO JAKOŚĆ] single source + PART -> bypass dialog', 1, 1)
                else:
                    chosen_label, filtered_items = self._auto_quality_dialog_and_filter(title, items)
            else:
                try:
                    control.infoDialog(
                        "Brak dostępnych źródeł dla tego tytułu.",
                        heading="FanVodPL",
                        icon="INFO",
                        time=2500,
                        sound=False,
                    )
                except Exception:
                    pass
                chosen_label, filtered_items = ("__CANCEL__", None)
        except Exception as e:
            fflog(f'[AUTO JAKOŚĆ] wyjątek: {e}', 1, 1)
            chosen_label, filtered_items = (None, None)

        # --- [ANULUJ] -> po anulowaniu AUTO JAKOŚCI wróć do listy źródeł (jak klasyczny FanFilm) ---

        if chosen_label == "__CANCEL__":

            fflog('[AUTO JAKOŚĆ] ANULUJ → powrót do listy źródeł', 1, 1)

            # Preferowany powrót: użyj wspólnego helpera, który sprząta play/resolve i pokazuje listę źródeł
            try:
                _ff_return_to_last_sources(self, title, items, filtered_items, season, episode)
            except Exception:
                # Fallback: minimalne sprzątanie jak wcześniej
                try:
                    handle = int(sys.argv[1])
                    xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
                except Exception:
                    pass
                try:
                    xbmc.executebuiltin('PlayerControl(Stop)')
                except Exception:
                    pass

            return

        if chosen_label and chosen_label != "__CANCEL__" and filtered_items:

            fflog(f'[AUTO JAKOŚĆ] wybrano: {chosen_label} | liczba pozycji: {len(filtered_items)}', 1, 1)
            # >>> FREE_BUCKET_FLAG
            try:
                _ff_lbl = str(chosen_label or '').strip().lower()
                import re as _re
                _ff_lbl = _re.sub(r'\s+\(\d+\)\s*(\|.*)?$', '', _ff_lbl)
            except Exception:
                _ff_lbl = ''
            if _ff_lbl.startswith('darmowe ') and _ff_lbl.split(' ',1)[1] in ('fullhd','hd','480p'):
                control.window.setProperty('FF.FREE_BUCKET_AUTOPLAY','1')
            else:
                control.window.clearProperty('FF.FREE_BUCKET_AUTOPLAY')
            # <<< FREE_BUCKET_FLAG

            control.window.setProperty(self.itemProperty, json.dumps(filtered_items))

            chosen = (chosen_label or "").strip().lower()
            # [FREE BUCKET → HARD OVERRIDE: ALWAYS CATALOG THIS SESSION]
            try:
                _chosen_low = (chosen_label or "").lower()
            except Exception:
                _chosen_low = chosen
            if (_chosen_low and ("darmowe" in _chosen_low or "free" in _chosen_low)):
                # FREE: show host list first (like premium), then continue to autoplay flow
                try:
                    def _ff_host(_it):
                        for k in ("source","provider","host"):
                            v = _it.get(k)
                            if v:
                                return str(v)
                        import re as _re
                        m = _re.search(r"https?://([^/]+)", str(_it.get("url","")))
                        return m.group(1) if m else ""
                    _hosts = sorted({h for h in (_ff_host(it) for it in (filtered_items or [])) if h})
                    # >>> FREE_AUTOPLAY via property
                    if control.setting('hosts.mode') == '2' and control.window.getProperty('FF.FREE_BUCKET_AUTOPLAY') == '1':
                        _hosts = _hosts[:1]
                        control.window.clearProperty('FF.FREE_BUCKET_AUTOPLAY')
                    # <<< FREE_AUTOPLAY via property

                    if len(_hosts) > 1:
                        import xbmcgui
                        _opts = ["Auto"] + _hosts
                        _hi = xbmcgui.Dialog().select("[FF] Host darmowe", _opts)
                        if _hi < 0:
                            # >>> PATCH: FREE_HOST_CANCEL – bezpieczny powrót bez spinnera
                            try:
                                fflog('[FREE HOSTS] Cancel → return to titles', 1, 1)
                            except Exception:
                                pass
                            try:
                                _ff_safe_close_ui()
                            except Exception:
                                pass
                            try:
                                _ff_return_to_last_sources(self, title, items, filtered_items, season, episode)
                            except Exception:
                                pass
                            return
                            # <<< PATCH END
                        if _hi > 0:
                            _sel = _hosts[_hi-1]
                            filtered_items = [it for it in filtered_items if _ff_host(it) == _sel]
                except Exception:
                    pass
            autoplay_enabled = (control.setting("hosts.mode") == "2")
            # Wymuś katalog dla darmowych w tej sesji
            if control.window.getProperty("FanVodPL.forceCatalogThisSession") == "true":
                autoplay_enabled = False


            if autoplay_enabled:

                # Autoplay dla KAŻDEGO kubełka (4K/FHD/720p/Darmowe/Wszystkie). Fallback -> katalog.

                handle = int(sys.argv[1])

                updateListing = True if ('params2' in globals() and isinstance(params2, dict) and params2.get("r")) or ('params2' in locals() and isinstance(params2, dict) and params2.get("r")) else False

                subs = []

                item = {}

                ret_item = True

                url = self.sourcesDirect(filtered_items, ret_item=ret_item)

                if isinstance(url, tuple):

                    url, subs = url

                if isinstance(url, list):

                    url, item = url

                if url and not str(url).startswith('close://'):

                    from ptw.libraries.player import player
                    _ff_safe_close_ui()
                    from ptw.libraries.player import player
                    control.window.clearProperty("FanVodPL.forceCatalogThisSession")
                    try:
                        fflog('[AUTO JAKOŚĆ] starting player.run', 1)# === FFGPT5: disable resolve-first to allow player().run (watched/history fix) ===
# [FFG-PAUSE] 
# [FFG-PAUSE]                         # FFRF: resolve-first (setResolvedUrl) for proper return to list
# [FFG-PAUSE]                         try:
# [FFG-PAUSE]                             import xbmcplugin, xbmcgui
# [FFG-PAUSE]                             _h = int(sys.argv[1])
# [FFG-PAUSE]                             if _h >= 0:
# [FFG-PAUSE]                                 _li = xbmcgui.ListItem(path=str(url))
# [FFG-PAUSE]                                 _li.setProperty('IsPlayable','true')
# [FFG-PAUSE]                                 xbmcplugin.setResolvedUrl(_h, True, _li)
# [FFG-PAUSE]                                 return
# [FFG-PAUSE]                         except Exception as _e:
# [FFG-PAUSE]                             pass
# [FFG-PAUSE] # === /FFGPT5 ===
                        player().run((title, localtitle, originalname, meta.get("tvshowtitle", "")), year, season, episode, imdb, tvdb, tmdb, url, subs, meta, handle, hosting=item.get("source"), customPlayer=item.get("customPlayer"))
                        try:
                            _ff_return_to_last_sources(self, title, items, filtered_items, season, episode)
                        except Exception:
                            pass
                        return
                    except Exception as e:
                        fflog(f'[AUTO JAKOŚĆ] player.run failed: {e}', 1, 1)
                        try:
                            fflog('[AUTO JAKOŚĆ] fallback: control.resolve -> próbuję uruchomić odtwarzanie przez Kodi', 1)
                            control.resolve(handle, True, control.item(path=str(url)))
                        except Exception as e2:
                            fflog(f'[AUTO JAKOŚĆ] control.resolve fallback failed: {e2}', 1, 1)
                            try:
                                self.showItems(title, filtered_items, None, season, episode)
                            except Exception:
                                pass

                    return

                # Fallback -> katalog

                try:

                    if control.window.getProperty("FanVodPL.skipResolveOnce") != "true":
                        control.resolve(handle, False, control.item(""))

                except Exception:

                    pass

                self.showItems(title, filtered_items, None, season, episode)

                return

            else:

                # Autoplay wyłączony globalnie -> katalog

                self.showItems(title, filtered_items, None, season, episode)

                return
        PluginName = control.infoLabel("Container.PluginName")
        fflog(f'{PluginName=}',1,1)

        select = control.setting("hosts.mode") if select is None else select
        fflog(f'{select=}',1,1)

        external_plugins = control.window.getProperty('external_plugins_from_FF').strip(',').split(',')
        allowed_plugins = ["plugin.video.fanvodpl"] + external_plugins
        yatse = control.setting("yatse") == "true"
        if not yatse:
            # if select == "1" and folderpath.startswith("plugin://plugin.video.themoviedb.helper/"):
            # if select == "1" and not control.infoLabel("Container.PluginName"):  # próba uniwersalności
            # if select == "1" and "plugin.video.fanvodpl" not in control.infoLabel("Container.PluginName"):  # próba uniwersalności
            # if select == "1" and control.infoLabel("Container.PluginName") not in ["plugin.video.fanvodpl", "plugin.video.tbseven", "plugin.video.mediafusion"]:  # próba uniwersalności (z wyjątkami)
            if select == "1" and control.infoLabel("Container.PluginName") not in allowed_plugins:  # próba uniwersalności (z wyjątkami)
                select = "0"
                fflog(f'zmieniono na {select=} (z 1)',1,1)
                fflog(f'bo {control.infoLabel("Container.PluginName")=}',1,1)
            #elif (select == "0" or select == "2") and int(sys.argv[1]) > 0 and not folderpath.startswith("plugin://plugin.video.themoviedb.helper/"):
            #elif select == "0" and int(sys.argv[1]) > 0 and control.infoLabel("Container.PluginName") and not control.infoLabel("ListItem.FolderPath"):  # nie mogą być przekierowania
            elif (select == "0" or select == "2") and int(sys.argv[1]) >= 0 and control.infoLabel("Container.PluginName") and not control.infoLabel("ListItem.FolderPath"):  # nie mogą być przekierowania
                select = "1"  # pomaga wyświetlać katalogi, gdy user ustawił okienko  # nie wiem jak przy 1 zrobić automatyczne odtwarzanie
                fflog(f'zmieniono na {select=} (z 0)',1,1)
                fflog(f'bo {control.infoLabel("Container.PluginName")=}',1,1)
                fflog(f' i {control.infoLabel("ListItem.FolderPath")=}',1,1)
                pass
            # fflog(f'{select=}',1,1)


        title = tvshowtitle if tvshowtitle is not None else title


        if control.window.getProperty("PseudoTVRunning") == "True":  # nie wiem co to jest
            # jakiś autoplay
            fflog("PseudoTVRunning",1,1)
            control.resolve( int(sys.argv[1]), True, control.item(path=str(self.sourcesDirect(items))) )  # xbmcplugin.setResolvedUrl
            return

        url = None
        subs = None

        if items or ( json.loads(control.window.getProperty(self.itemRejected)) and (select == "1" or select == "0") ):

            if params2.get("download"):
                def remove_some_sources_and_numbers(items):
                    #fflog(f'{items=}')
                    fflog(f'odrzucenie lokalnych źródeł, bo z nich nie można pobierać', 0)
                    items = [i for i in items if i.get('provider') not in['pobrane', 'library', 'biblioteka', 'plex', 'external']]
                    # można jeszce ewentualnie numery usunąć z labela (jak są) aby nie było ewentualnych dziur
                    # fflog(f'{items=}')
                    # if not re.search(r'\[LIGHT\]\[/LIGHT\]', items[0]["label"]):
                    if not items[0].get("without_number"):
                        # fflog(f'usunięcie numerów z labeli', 0)
                        # [i.update({'label': re.sub(r'\[LIGHT\]\d+\[/LIGHT\]\s*\|\s*', '', i.get('label'))}) for i in items]
                        [i.update({'label': re.sub(r'^(\D*)(\d+)(\D*?)[| ]\s*', r'\1\3', i.get('label'))}) for i in items]  # to też nie jest doskonałe
                        items[0]["without_number"] = True
                    return items
                items = remove_some_sources_and_numbers(items)
                itemRejected = json.loads(control.window.getProperty(self.itemRejected))
                if itemRejected:
                    itemRejected = remove_some_sources_and_numbers(itemRejected)
                    control.window.setProperty(self.itemRejected, json.dumps(itemRejected))

            #params2 = dict(parse_qsl(sys.argv[2][1:]))
            fflog(f'[play] {select=} {params2.get("r")=}', 0)

            wybieranie_zrodla = None

            # if select == "1" or params2.get("r"):  # directory
            if select == "1" and ("plugin" in control.infoLabel("Container.PluginName") or yatse) or params2.get("r"):  # directory
                control.window.setProperty('imdb_id', imdb_curr)

                # fflog(f'{len(items)=}')
                control.window.setProperty(self.itemProperty, json.dumps(items))

                #control.sleep(200)  # nie pamiętam do czego potrzebne
                if control.setting("hosts.mode") != "2":
                    fflog(f'[play] przygotowanie do wypisywania pozycji w katalogu', 0)
                    #sources().showItems(quote_plus(title), items)
                    # sources().showItems(title, items)
                    self.showItems(title, items, None, season, episode)
                    return  # dalej kod już nie idzie
                else:  # próba autoplay, gdy Kodi wymaga wyświetlienia katalogu
                    fflog(f'[play] próba autoplay, gdy Kodi wymaga wyświetlienia katalogu', 0)
                    handle = int(sys.argv[1])
                    updateListing = True if params2.get("r") else False  # True świadczy, że po drodze było odświeżanie
                    ret_item = True
                    url = self.sourcesDirect(items, ret_item=ret_item)
                    if isinstance(url, tuple):
                        url, subs = url
                    if isinstance(url, list):
                        url, item = url
                    else:
                        item = {}
                        pass
                    if url and not url.startswith('close://'):
                        fflog('akcja wstecz', 1)
                    control.execute('Action(Back)')
                    return

                if url.startswith('close://'):
                    fflog('[AUTO JAKOŚĆ] ANULUJ – bez nawigacji (zostaję w liście tytułów)', 1, 1)
                    try:
                        handle = int(sys.argv[1])
                        xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
                    except Exception:
                        pass
                    try:
                        xbmc.executebuiltin('PlayerControl(Stop)')
                    except Exception:
                        pass
                    try:
                        cw = control.window
                        for prop in ('FanVodPL.autoplay','FanVodPL.autoplay_free','FanVodPL.autoplay_premium','FanVodPL.forceResolve','FanVodPL.pendingPlay','FanVodPL.resolve_in_progress','FanVodPL.forceCatalogThisSession','FanVodPL.var.return_to_sources_url'):
                            cw.clearProperty(prop)
                        control.execute('Dialog.Close(progressdialog,true)')
                        control.execute('Dialog.Close(progressdialogbg,true)')
                        control.execute('Dialog.Close(busydialog,true)')
                        control.execute('Dialog.Close(busydialognocancel,true)')
                        control.execute('Dialog.Close(notification,true)')
                    except Exception:
                        pass
                    return
            elif select == "0" or select == "1":  # popup window (Dialog typu Select) lub pliki strm
                # czy to ma tu sens ? Bo chyba nigdy nie zajdzie taki przypadek
                # bo okno potem znika, i aby pojawiło się nowe, to trzeba zrobić wyszukiwanie, a te "wymusza" szukanie od nowa
                if control.setting("crefresh") != "true":
                    control.window.setProperty('imdb_id', imdb_curr)
                    control.window.clearProperty(self.itemProperty)
                    control.window.setProperty(self.itemProperty, json.dumps(items))

                ret_item = True
                # ret_item = True if params2.get("download") else False
                preselect = -1
                selected = -1
                trash = False
                def wybieranie_zrodla(preselect=preselect):
                    nonlocal selected
                    nonlocal url, trash, items
                    # fflog(f'sprawdzenie warunku  {url=}',1,1)
                    while not url or isinstance(url, str) and not url.startswith('close://') or isinstance(url, list) and not url[0]:
                        # fflog(f'warunek spełniony (czyli pytanie potrzebne)',1,1)
                        url = self.sourcesDialog(items=items, trash=trash, ret_item=ret_item, preselect=preselect)  # dialog aby wybrać źródło
                        # fflog(f'{url=}',1,1)
                        if isinstance(url, tuple):
                            # preselect = url[1]
                            # trash = url[2]
                            # url = url[0]  # musi być na końcu
                            url, selected, trash = url  # mix
                            if trash:
                                if True:  # wariant 1
                                    preselect = len(items)
                                    trash = False
                                else:  # wariant 2
                                    preselect = selected
                                    items = json.loads(control.window.getProperty(self.itemRejected))
                    else:
                        # fflog(f'warunek NIEspełniony (czyli ponowne pytanie niepotrzebne)',1,1)
                        pass
                    # fflog(f'zwrócenie odpowiedzi  {url=}',1,1)
                    return url  # w sumie mogłoby tego nie być bo url jest nonlocal
                # url = wybieranie_zrodla()
                wybieranie_zrodla()
            else:  # select ==2 (autoplay)
                ret_item = True
                # ret_item = True if params2.get("download") else False
                url = self.sourcesDirect(items, ret_item=ret_item)  # zwraca pierwszą pozycję z listy

        if select == "0":
            control.idle(2)
            pass

        fflog(f'{url=}', 0,1)

        if isinstance(url, list):
            url, item = url
        else:
            item = {}
            pass

        # fflog(f' {url=}', 1)

        if params2.get("download"):
            if url:
                if isinstance(url, tuple):
                    url = url[0]
                    # napisów nie pobieramy
                if not url.startswith('plugin://') and not url.startswith('close://'):

                    TvShowYear = control.infoLabel('ListItem.Property(TvShowYear)') or meta.get("tvshowyear")
                    localtvshowtitle = control.infoLabel('ListItem.Property(localTvShowTitle)') or meta.get("tvshowtitle") or title
                    #localtitle = control.infoLabel('ListItem.Property(localTitle)') or meta.get("title") or title
                    if "tvshowtitle" in meta and "season" in meta and "episode" in meta:
                        sysname = (localtvshowtitle)
                        if TvShowYear:
                            sysname += (" (%s)" % TvShowYear)  # to musi być rok serialu, nie odcinka
                        sysname += (" S%02dE%02d" % (int(meta["season"]), int(meta["episode"])))
                    elif "year" in meta:
                        sysname = (localtitle)
                        sysname += (" (%s)" % meta["year"])

                    allow_extrainfo_to_download = control.setting("download.extrainfo") == "true"
                    if allow_extrainfo_to_download:
                        extrainfo = (item.get("quality") or "") if item.get("quality") not in ["SD", ""] else ""
                        extrainfo += " " + item.get("extrainfo", "") or ""
                        extrainfo = extrainfo.replace(" | AVI", "")
                        extrainfo += " " + (item.get("info") or "")  # lektor, napisy, ale i rozmiar na końcu
                        extrainfo = re.sub(r"(?:^|\s*\|)\s*(\d+(?:[.,]\d+)?)\s*([GMK]B)\b\s*(?:\||$)", "", extrainfo, flags=re.I,)  # pozbycie się rozmmiaru
                        # extrainfo += " " + (item.get("language") or "").upper()
                        extrainfo += (" " + (item.get("language") or "").upper()) if not any(inf in extrainfo.lower() for inf in ["lektor", "napisy", "dubbing"]) else ""
                        extrainfo = extrainfo.replace(" | ", " ").replace(" / ", " ").strip()
                        extrainfo = re.sub(r"\s{2,}", " ", extrainfo).strip()  # nadmiarowe spacje
                        extrainfo = f"[{extrainfo}]" if extrainfo else ""
                    else:
                        extrainfo = ""

                    from ptw.libraries import downloader
                    download_ok = downloader.download(name=sysname, image="", url=url, extrainfo=extrainfo)

                    fflog(f'{download_ok=}',1,1)
                    if wybieranie_zrodla:  # przy autoplay funkcja wybieranie_zrodla nie jest aktywowana bo jest w warunku - pomyśleć jak to zmienić
                        while download_ok is False:
                            fflog(f'ponowne wyświetlenie zapytania o źródło pobierania',1,1)
                            # url = wybieranie_zrodla(selected)
                            wybieranie_zrodla(selected)

                            if isinstance(url, list):
                                url, item = url
                            else:
                                item = {}
                                pass

                            if isinstance(url, tuple):
                                url = url[0]
                                # napisów nie pobieramy

                            if not url.startswith('plugin://') and not url.startswith('close://'):
                                download_ok = downloader.download(name=sysname, image="", url=url, extrainfo=extrainfo)
                                fflog(f'{download_ok=}',1,1)
                            else:
                                fflog(f'opuszczenie procedury ponownego pytania o źródła pobierania',1,1)
                                download_ok = None
                                break
                    else:
                        fflog(f'{wybieranie_zrodla=}  więc nie można wybrać innego źródła  |  {select=}',1,1)
                        pass

            else:
                self.errorForSources()  # komunikat o błędzie
            return  # zakładam, że wywołanie tego będzie tylko z handle -1, czyli poprzez RunPlugin z context menu

        if url:  # only when popup window (dialog) or autoplay (select 0 or 2)
            if isinstance(url, tuple):
                url, subs = url

            if url.startswith('plugin://') and "plugin" in control.infoLabel("Container.PluginName"):  # to chyba dla źródeł external
                fflog(f'[play] obsługa adresu typu {url=}', 1)
                if item and item.get("isFolder"):
                    fflog('próba przejścia z polecenia PlayMedia na katalog',1,1)
                    handle = int(sys.argv[1])
                    if control.window.getProperty("FanVodPL.skipResolveOnce") != "true":
                        control.resolve(handle, False, control.item(path=''))  # próba odwołania polecenia "PlayMedia"
                    # niestety, ale pewnie i tak pojawi się pewnie komunikat "Nieudane odtwarzanie", a w logu "Playlist Player: skipping unplayable item"
                    # a z fejkowym video są problemy, a pusta lista m3u8 coś nie chce mi działać
                    control.sleep(100)
                    if control.condVisibility('Window.IsActive(okDialog)'):
                        fflog('zamknięcie komunikatu o nieudanym odtwarzaniu')
                        control.execute('Dialog.Close(okDialog,true)')
                    control.execute('Dialog.Close(okdialog,true)')
                    control.execute('Dialog.Close(notification,true)')
                    updateListing = True if params2.get("r") else False  # True świadczy, że po drodze było odświeżanie
                    control.directory(handle, updateListing=updateListing, cacheToDisc=False)
                    control.execute('Container.Update(' + url + ')')
                    return
                if item and item.get("customPlayer"):
                    pass  # nie wiem, jak to rozegrać
                from ptw.libraries.player import player
                # ciekawe, czy te 2 linijki mogą być fixem na zawieszanie Kodi
                # control.execute('Dialog.Close(notification,true)')
                # control.sleep0(500)
                # player().play(url)  # zawiesza mi Kodi (u innych niekoniecznie), ale i tak ma to minus, bo nie będzie oznaczenie materiału, że został obejrzany w FanVodPL
                try:
                    fflog('[AUTO JAKOŚĆ] starting player.run', 1)# === FFGPT5: disable resolve-first to allow player().run (watched/history fix) ===
# [FFG-PAUSE] 
# [FFG-PAUSE]                     # FFRF: resolve-first (setResolvedUrl) for proper return to list
# [FFG-PAUSE]                     try:
# [FFG-PAUSE]                         import xbmcplugin, xbmcgui
# [FFG-PAUSE]                         _h = int(sys.argv[1])
# [FFG-PAUSE]                         if _h >= 0:
# [FFG-PAUSE]                             _li = xbmcgui.ListItem(path=str(url))
# [FFG-PAUSE]                             _li.setProperty('IsPlayable','true')
# [FFG-PAUSE]                             xbmcplugin.setResolvedUrl(_h, True, _li)
# [FFG-PAUSE]                             return
# [FFG-PAUSE]                     except Exception as _e:
# [FFG-PAUSE]                         pass
# [FFG-PAUSE] # === /FFGPT5 ===
                    player().run( (title, localtitle, originalname, meta.get("tvshowtitle", "")), year, season, episode, imdb, tvdb, tmdb, url, subs, meta, hosting=item.get("source"), customPlayer=item.get("customPlayer") )
                    try:
                        _ff_return_to_last_sources(self, title, items, filtered_items, season, episode)
                    except Exception:
                        pass
                    return
                except Exception as e:
                    fflog(f'[AUTO JAKOŚĆ] player.run failed: {e}', 1, 1)
                    try:
                        fflog('[AUTO JAKOŚĆ] fallback: control.resolve -> próbuję uruchomić odtwarzanie przez Kodi', 1)
                        control.resolve(handle, True, control.item(path=str(url)))
                    except Exception as e2:
                        fflog(f'[AUTO JAKOŚĆ] control.resolve fallback failed: {e2}', 1, 1)
                        try:
                            self.showItems(title, filtered_items, None, season, episode)
                        except Exception:
                            pass
            elif not url.startswith('close://'):  # przeważnie jest to (nawet gdy wywołanie z biblioteki czy ulubionych)
                if item and item.get("isFolder"):
                    # fflog(f'z widżetu nie da się wyświetlić katalogu {url=}  {item.get("isFolder")=}', 1,1)
                    # fflog(f'{int(sys.argv[1])=}', 1,1)
                    # fflog(f"{control.infoLabel('ListItem.DBID')=}", 1,1)
                    # fflog(f"{control.infoLabel('ListItem.DBTYPE')=}", 1,1)
                    pass
                    fflog('próba przejścia na katalog',1,1)
                    handle = int(sys.argv[1])
                    if control.window.getProperty("FanVodPL.skipResolveOnce") != "true":
                        control.resolve(handle, False, control.item(path=''))  # próba odwołania polecenia "PlayMedia"
                    # niestety, ale pewnie i tak pojawi się pewnie komunikat "Nieudane odtwarzanie", a w logu "Playlist Player: skipping unplayable item"
                    # a z fejkowym video są problemy, a pusta lista m3u8 coś nie chce mi działać
                    control.sleep(100)
                    if control.condVisibility('Window.IsActive(okDialog)'):
                        fflog('zamknięcie komunikatu o nieudanym odtwarzaniu')
                        control.execute('Dialog.Close(okDialog,true)')
                    updateListing = True if params2.get("r") else False  # True świadczy, że po drodze było odświeżanie
                    control.directory(handle, updateListing=updateListing, cacheToDisc=False)
                    control.execute('Container.Update(' + url + ')')  # przejście na nowy adres
                    return  # koniec tego skryptu
                if item and item.get("customPlayer"):
                    pass  # nie wiem, jak to rozegrać
                from ptw.libraries.player import player
                _ff_safe_close_ui()
                from ptw.libraries.player import player
                control.window.clearProperty("FanVodPL.forceCatalogThisSession")
                try:
                    fflog('[AUTO JAKOŚĆ] starting player.run', 1)# === FFGPT5: disable resolve-first to allow player().run (watched/history fix) ===
# [FFG-PAUSE] 
# [FFG-PAUSE]                     # FFRF: resolve-first (setResolvedUrl) for proper return to list
# [FFG-PAUSE]                     try:
# [FFG-PAUSE]                         import xbmcplugin, xbmcgui
# [FFG-PAUSE]                         _h = int(sys.argv[1])
# [FFG-PAUSE]                         if _h >= 0:
# [FFG-PAUSE]                             _li = xbmcgui.ListItem(path=str(url))
# [FFG-PAUSE]                             _li.setProperty('IsPlayable','true')
# [FFG-PAUSE]                             xbmcplugin.setResolvedUrl(_h, True, _li)
# [FFG-PAUSE]                             return
# [FFG-PAUSE]                     except Exception as _e:
# [FFG-PAUSE]                         pass
# [FFG-PAUSE] # === /FFGPT5 ===
                    player().run( (title, localtitle, originalname, meta.get("tvshowtitle", "")), year, season, episode, imdb, tvdb, tmdb, url, subs, meta, hosting=item.get("source"), customPlayer=item.get("customPlayer") )
                    try:
                        _ff_return_to_last_sources(self, title, items, filtered_items, season, episode)
                    except Exception:
                        pass
                    return
                except Exception as e:
                    fflog(f'[AUTO JAKOŚĆ] player.run failed: {e}', 1, 1)
                    try:
                        fflog('[AUTO JAKOŚĆ] fallback: control.resolve -> próbuję uruchomić odtwarzanie przez Kodi', 1)
                        control.resolve(handle, True, control.item(path=str(url)))
                    except Exception as e2:
                        fflog(f'[AUTO JAKOŚĆ] control.resolve fallback failed: {e2}', 1, 1)
                        try:
                            self.showItems(title, filtered_items, None, season, episode)
                        except Exception:
                            pass

        self.errorForSources()  # komunikat o błędzie

        handle = int(sys.argv[1])

        if not url or url.startswith('close://'):
        # if url and url.startswith('close://'):  # tylko dla akcji Anuluj
            # fflog(f'nieudane odtwarzanie, bo {url=}  {handle=}  {control.infoLabel("Container.PluginName")=}')
            # próba odtwarzania jakiegoś fejkowego wideo, aby Kodi nie rzucał komunikatem o nieudanym odtwarzaniu
            # plik powinien być trochę dłuższy, bo trzeba przerwać odtwarzanie, aby Kodi nie zakwalifikował pozycji jako obejrzana, a przy wznowieniu powinien być jeszcze dłuższy
            # (nie wiem, czy ten komunikat nie pojawia się tylko w przypadku próby odtwarzanie plików z poza wtyczki FanVodPL)
            # if "plugin.video.fanvodpl" not in control.infoLabel("Container.PluginName") and url:  # tylko dla akcji Anuluj
            # if url:  # tylko, gdy są źródła (nie robimy, gdy nie ma źródeł)
            if True:  # zawsze
            #if False:  # bo odtworzenie powoduje zmianę długości w informacjach o filmie, także lepiej jednak nie
                if handle >= 0:
                    # control.resolve(handle, False, control.item())  # ale czy to w czymś pomaga? Bo komunikat i tak co jakiś czas się pojawia
                    pass
                    """
                    fflog('próba odtworzenia fragmenciku fejkowego wideo')  # ciekawe, czy playcount się zmienia
                    #url = ""
                    #from ptw.libraries.player import PlayerHacks
                    #PlayerHacks().resolve_to_dummy_hack(url)
                    # url = "special://home/addons/script.module.ptwfanvod/resources/dummy.mp4"
                    url = "special://home/addons/script.module.ptwfanvod/resources/empty.m3u8"  # nie działa mi (a szkoda) - w FF3 podobno działa
                    fflog(f'{url=}', 1)
                    control.resolve(handle, True, control.item(path=url, offscreen=True))  # start
                    # control.sleep(20)  # nie wiem, czy potrzebne
                    control.player.stop()  # stop
                    #control.sleep(20)  # extra time for callback can execute
                    fflog('koniec odtwarzenia fejkowego wideo', 1)
                    """

        control.sleep0(250)
        if handle > -1:
            #params2 = dict(parse_qsl(sys.argv[2][1:]))
            # ipdw = control.infoLabel("Container().NumItems")
            # fflog(f'{ipdw=}',1,1)
            fflog('dodanie pustego katalogu',1,1)
            updateListing = True if params2.get("r") else False  # True świadczy, że po drodze było odświeżanie
            control.directory(handle, updateListing=updateListing)
            # control.sleep(100)  # jak chcemy, aby poniższa zmienna się zaktualizowała
            # ipdw = control.infoLabel("Container().NumItems")
            ipdw = '0'
            # fflog(f'{ipdw=}',1,1)
            # fflog(f'zrobić akcję wstecz czy nie ? \n{select=} \n{control.infoLabel("Container.PluginName")=} \n{params2=} \n{params1=} \n{updateListing=} \n{ipdw=}',1,1)
            if select == "1" and "plugin" in control.infoLabel("Container.PluginName") and ipdw and int(ipdw) < 1:
                fflog('akcja wstecz',1,1)
                control.execute('Action(Back)')



    def showItems(self, title="", items=None, trash=None, season=None, episode=None):
        try:
            control.window.clearProperty("FanVodPL.skipResolveOnce")
            control.window.clearProperty("FanVodPL.forceCatalogThisSession")
        except Exception:
            pass



        # Proaktywne zamknięcie ewentualnego okDialog (błąd odtwarzania) zanim pokażemy listę Darmowe
        try:
            if control.condVisibility('Window.IsActive(okDialog)'):
                control.execute('Dialog.Close(okDialog,true)')
        except Exception:
            pass
        try:
            control.window.clearProperty("FanVodPL.skipResolveOnce")
        except Exception:
            pass


        try:
            if xbmc:
                control.window.setProperty('FanVodPL.var.return_to_sources_url', xbmc.getInfoLabel('Container.FolderPath'))
        except Exception:
            pass
        def sourcesDirMeta(metadata):
            if not metadata:
                return metadata
            allowed = [
                "icon",
                "poster",
                "fanart",
                "thumb",
                "clearlogo",
                "clearart",
                "discart",
                "banner",
                "title",
                "year",
                "tvshowtitle",
                "season",
                "episode",
                "rating",
                "plot",
                "trailer",
                "mediatype",
                "imdb",
                "tvdb",
                "tmdb",
                "votes",
                "originaltitle",
                "genre",
                "country",
                "director",
                "mpaa",  # kategoria wiekowa
                "duration",
                "castwiththumb",  # obsada
                "premiered",  # nie wiem czy potrzebny
            ]
            return {k: v for k, v in metadata.items() if k in allowed}

        control.playlist.clear()  # ciekawe, czy można to wykorzystać do zniwelowania informacji o błędzie odtwarzania, jak zrezygnujemy ("skip unplayable item")

        #if name == "odrzucone":
        if trash:
            items = control.window.getProperty(self.itemRejected)
            try:
                items = json.loads(items)
            except:
                control.dialog.notification('FanVodPL', 'wystąpił jakiś błąd', xbmcgui.NOTIFICATION_ERROR)
                fflog_exc()
                return
            #items = self.sortSources(items)
            #items = self.renumberSources(items)  # nie ma jeszcze takiej funkcji
        elif not items:
            items = control.window.getProperty(self.itemProperty)
            try:
                items = json.loads(items)
            except:
                control.dialog.notification('FanVodPL', 'wystąpił jakiś błąd', xbmcgui.NOTIFICATION_ERROR)
                fflog_exc()
                return

        meta = control.window.getProperty(self.metaProperty)
        try:
            meta = json.loads(meta)
        except Exception:
            fflog_exc(1)
            meta = {}
        # fflog(f'meta={json.dumps(meta, indent=2)}',1,1)

        if not title:
            title = meta.get("title", "")
        if not title:
            control.dialog.notification('FanVodPL', 'błędny parametr', xbmcgui.NOTIFICATION_ERROR)
            fflog(f"{title=}",1,1)
            return
        # fflog(f'{meta=}')

        originalname = meta.get("originalname", "")
        TvShowYear = control.infoLabel('ListItem.Property(TvShowYear)') or meta.get("tvshowyear")
        localtvshowtitle = control.infoLabel('ListItem.Property(localTvShowTitle)') or meta.get("tvshowtitle") or title
        localtitle = control.infoLabel('ListItem.Property(localTitle)') or meta.get("title") or title

        # ===== [AUTO JAKOŚĆ – LIMITY GB] (dla list PREMIUM w katalogach) =====
        # W trybie katalogów część ścieżek omija _auto_quality_dialog_and_filter(),
        # przez co limity rozmiaru (GB) nie były stosowane do list "Premium – wszystkie"
        # ani do pod-katalogów hostów. Tutaj stosujemy te same limity, ale wyłącznie
        # dla źródeł premium (darmowe pozostają bez filtra rozmiaru).
        try:
            if items and isinstance(items, list):
                _prem_flags = [bool(self._is_premium_provider(it)) for it in items]
                if any(_prem_flags):
                    _prem_only = all(_prem_flags)
                    if _prem_only:
                        items = self._apply_size_limits(items)
                    else:
                        _prem_items = [it for it in items if self._is_premium_provider(it)]
                        _prem_ok = self._apply_size_limits(_prem_items) if _prem_items else _prem_items
                        _prem_ok_keys = set(((it.get('url') or ''), (it.get('provider') or '')) for it in _prem_ok)
                        _merged = []
                        for it in items:
                            if self._is_premium_provider(it):
                                k = ((it.get('url') or ''), (it.get('provider') or ''))
                                if k in _prem_ok_keys:
                                    _merged.append(it)
                            else:
                                _merged.append(it)
                        items = _merged
        except Exception:
            pass

        meta = sourcesDirMeta(meta)  # usuwa niestandardowe rekordy
        # fflog(f'meta={json.dumps(meta, indent=2)}',1,1)

        # (Kodi bug?) [name,role] is incredibly slow on this directory,
        #             [name] is barely tolerable, so just nuke it for speed!
        #        if "cast" in meta:  # "cast" czy "castwiththumb" ?
        #            del meta["cast"]

        sysaddon = sys.argv[0]
        syshandle = int(sys.argv[1])
        # fflog(f'{sysaddon=} {syshandle=}')

        downloads = (
            control.setting("downloads") == "true"
            and not (
                control.setting("movie.download.path") == ""
                or control.setting("tv.download.path") == ""
            )
        )

        systitle = quote_plus(title)

        # potrzebne dla schematu nazywania pobranego pliku
        if "tvshowtitle" in meta and "season" in meta and "episode" in meta:
            sysname = quote_plus(localtvshowtitle)
            if TvShowYear:
                sysname += quote_plus(" (%s)" % TvShowYear)  # to musi być rok serialu, nie odcinka
            # SxxExx tylko gdy mamy komplet danych (sezon/odcinek)
            try:
                _s = meta.get("season")
                _e = meta.get("episode")
                if _s not in (None, "") and _e not in (None, ""):
                    sysname += quote_plus(" S%02dE%02d" % (int(_s), int(_e)))
            except Exception:
                pass
        elif "year" in meta:
            sysname = quote_plus(localtitle)
            sysname += quote_plus(" (%s)" % meta["year"])

        poster = meta["poster"] if "poster" in meta else "0"
        fanart = meta["fanart"] if "fanart" in meta else "0"
        thumb = meta["thumb"] if "thumb" in meta else "0"
        if thumb == "0":
            thumb = poster
        if thumb == "0":
            thumb = fanart
        banner = meta["banner"] if "banner" in meta else "0"
        if banner == "0":
            banner = poster
        if poster == "0":
            poster = control.addonPoster()
        if banner == "0":
            banner = control.addonBanner()
        if not control.setting("fanart") == "true":
            fanart = "0"
        if fanart == "0":
            fanart = control.addonFanart()
        if thumb == "0":
            thumb = control.addonFanart()

        sysimage = quote_plus(poster.encode("utf-8"))

        downloadMenu = control.lang(32403)

        list_of_items = []
        providers = []
        list_of_sources = []

        sysmeta = meta.copy()
        sysmeta.pop("rating", None)
        sysmeta.pop("votes", None)
        # sysmeta.pop("next", None)  # tego i tak nie ma w meta po jej przefiltrowaniu
        sysmeta = quote_plus(json.dumps(sysmeta))

        dont_use_setResolvedUrl = control.setting("player.dont_use_setResolvedUrl") == "true"

        generate_short_path = control.setting("generate_short_path") == "true"
        # generate_short_path = False  # bo taka pozycja dodana do ulubionych nie zadziała
        # tylko zmienianie raz tak raz tak będzie powodować, że Kodi nie będzie rozpoznawało czy dane źródło obejrzane, czy nie - dlatego dobrze byłoby się zdecydować na coś i trzymać się tego

        allow_extrainfo_to_download = control.setting("download.extrainfo") == "true"

        ia = control.setting("player.ia") == "true"

        if ia:
            disallowed_words = control.setting('player.ia_not_for')
            # fflog(f'{disallowed_words=}', 0)
            disallowed_words = disallowed_words.split(',')  # string into list
            disallowed_words = [w.strip().replace('"', '') for w in disallowed_words]  # clean a little
            disallowed_words = list(filter(None, disallowed_words))  # eliminate empty
            disallowed_words = list(dict.fromkeys(disallowed_words))  # eliminate duplicates
            fflog(f'{disallowed_words=}', 0)
        else:
            disallowed_words = []

        auto_select_next_item_to_play = control.setting("auto.select.next.item.to.play") == "true"

        yatse = control.setting("yatse") == "true"

        allow_delete_files = control.setting("allow_delete_files") == "true"

        cm_enable_autoplay = control.setting("cm.enable.autoplay") == "true"

        # fflog(f'{len(items)=}',1,1)
        for i in range(len(items)):
            try:
                # fflog(f'{i=} {items[i]=}')
                # fflog(f'{i=} items[{i}]={json.dumps(items[i], indent=2)}')
                label = items[i].get("label")
                if not label:
                    continue

                if downloads and allow_extrainfo_to_download:
                    extrainfo = (items[i].get("quality") or "") if items[i].get("quality") not in ["SD", ""] else ""
                    extrainfo += " " + items[i].get("extrainfo", "") or ""
                    extrainfo = extrainfo.replace(" | AVI", "")
                    extrainfo += " " + (items[i].get("info") or "")  # lektor, napisy, ale i rozmiar na końcu
                    extrainfo = re.sub(r"(?:^|\s*\|)\s*(\d+(?:[.,]\d+)?)\s*([GMK]B)\b\s*(?:\||$)", "", extrainfo, flags=re.I,)  # pozbycie się rozmmiaru
                    # extrainfo += " " + (item.get("language") or "").upper()
                    extrainfo += (" " + (items[i].get("language") or "").upper()) if not any(inf in extrainfo.lower() for inf in ["lektor", "napisy", "dubbing"]) else ""
                    extrainfo = extrainfo.replace(" | ", " ").replace(" / ", " ").strip()
                    extrainfo = re.sub(r"\s{2,}", " ", extrainfo).strip()  # nadmiarowe spacje
                    extrainfo = f"[{extrainfo}]" if extrainfo else ""
                else:
                    extrainfo = ""

                # próba wyeliminowanie zmiennych elementów, które przeszkadzają, aby Kodi precyzyjnie oznaczał status wznowienia i obejrzania
                # del items[i]["label"]  # bo m.in dużo znaczników formatujących
                items[i] = {k:v for k,v in items[i].items() if k not in ["label", "on_account", "on_account_link", "on_account_expires", "info2", "trash", "unsure", "extrainfo"]}

                syssource = quote_plus(json.dumps([items[i]]))  # czemu to idzię w listę ? chyba pod konstrukcję z autoplay next + prev

                sysurl = "%s?action=playItem&title=%s&source=%s&meta=%s" % (sysaddon, systitle, syssource, sysmeta)
                # sysurl = "%s?action=playItem&source=%s&meta=%s" % (sysaddon, syssource, sysmeta)  # wyeliminowałem title z adresu, bo jest on w meta
                # eksperyment
                if generate_short_path:
                    sysurl = "%s?action=playItem&title=%s&source=%s&imdb=%s&tmdb=%s" % (sysaddon, systitle, syssource, meta.get("imdb",""), meta.get("tmdb",""))
                    # sysurl = "%s?action=playItem&source=%s&imdb=%s&tmdb=%s" % (sysaddon, syssource, meta.get("imdb",""), meta.get("tmdb",""))
                    # if meta.get("mediatype") == "tvshow":  # nie zawsze działa np. nie działa dla źródeł odcinka
                    # problem ulubionych jest to, że nie są zapamiętywane dane obiektu ListItem, a tylko label, icon oraz path
                    # ale tu w sumie nie ma aż tak o co walczyć, bo to się nie wyświetla w oknie, choć w bazie MyVideos zapisują się długie ścieżki

                if "tvshowtitle" in meta and "season" in meta and "episode" in meta:  # to jest obowiązkowo potrzebne dla krótkich adresów, ale także przydaje się, gdy były modyfikowane parametry do wyszukiwarki
                    # sysurl = "%s?action=playItem&source=%s&imdb=%s&tmdb=%s&season=%s&episode=%s" % (sysaddon, syssource, meta.get("imdb",""), meta.get("tmdb",""), meta.get("season"), meta.get("episode"))
                    sysurl += "&season=%s&episode=%s" % ( season or meta.get("season"), episode or meta.get("episode") )
                # fflog(f'{sysurl=}')

                # context menu
                cm = []

                not_library_and_not_downloaded = items[i]["provider"]!='pobrane' and items[i]["provider"]!='library' and items[i]["provider"]!='biblioteka' and not items[i].get("isFolder")

                isa_no_sense = items[i]["provider"] in ["tb7", "xt7", "rapideo", "nopremium", "twojlimit", "external"]

                if downloads and not_library_and_not_downloaded:
                    cm.append(
                        (
                            downloadMenu,
                            "RunPlugin(%s?action=download&name=%s&image=%s&source=%s&extrainfo=%s)"
                            % (sysaddon, sysname, sysimage, syssource, quote_plus(extrainfo)  ),
                        )
                    )

                ia_per_item = ia
                if ia:
                    hosting = items[i].get("source")
                    if disallowed_words and hosting and hosting.lower() in disallowed_words:
                        ia_per_item = False

                if not isa_no_sense and not ia_per_item and not_library_and_not_downloaded:  # ponieważ rozwiązanie adresu odbywa się przeważnie dopiero przed samym odtwarzaniem, więc nie da się w tym miejscu wykrywać frazy m3u8 w adresie url źródła
                    cm.append(
                        (
                            "Odtwórz przez ISA",
                            "PlayMedia(%s&ia=1)"
                            % (sysurl),
                        )
                    )
                if not isa_no_sense and ia_per_item and not_library_and_not_downloaded:
                    cm.append(
                        (
                            "Nie odtwarzaj przez ISA",
                            "PlayMedia(%s&ia=0)"
                            % (sysurl),
                        )
                    )

                if items[i]["provider"]=='tb7' or items[i]["provider"]=='xt7':
                    cm.append(
                        (
                            "Ponownie wykorzystaj transfer",
                            "RunPlugin(%s?action=buyItemAgain&title=%s&source=%s)"
                            % (sysaddon, systitle, syssource),
                        )
                    )

                if items[i]["provider"]=='pobrane' and allow_delete_files:
                    # fflog(f'{items[i]=}',1,1)
                    cm.append(
                        (
                            "Usuń plik",
                            "RunPlugin(%s?action=deleteFile&file=%s)"
                            % ( sysaddon, quote_plus(items[i].get("url")) ),
                        )
                    )

                if cm_enable_autoplay:
                    if not auto_select_next_item_to_play:
                        cm.append(
                            (
                                "Autoodtwarzanie",
                                # "RunPlugin(%s&auto_select_next_item_to_play=1)"  # handle -1
                                "PlayMedia(%s&auto_select_next_item_to_play=1)"
                                % (sysurl),
                            )
                        )

                item = control.item(label=label, offscreen=True)  # create ListItem


                item.addContextMenuItems(cm)  # dodanie menu kontekstowego do pozycji

                item.setArt({"icon": thumb, "thumb": thumb, "poster": poster, "banner": banner})
                # if meta.get("mediatype") == "tvshow":  # nie zawsze działa np. nie działa dla źródeł odcinka
                if "tvshowtitle" in meta and "season" in meta and "episode" in meta:
                    item.setArt({"season.poster": poster})

                # item.setProperty("Fanart_Image", fanart)

                vtag = item.getVideoInfoTag()

                castwiththumb = meta.get("castwiththumb")
                if castwiththumb:
                    castwiththumb = [xbmc.Actor(**a) for a in castwiththumb]
                    vtag.setCast(castwiththumb)

                # vtag.addVideoStream(xbmc.VideoStreamDetail(codec="h264"))  # czy to potrzebne ? przecież nie każdy plik ma taki kodek

                # fflog(f'meta={json.dumps(meta, indent=2)}',1,1)
                # nie wiem do czego to było
                # meta.pop("imdb", None)
                # meta.pop("tmdb_id", None)
                # meta.pop("imdb_id", None)
                # meta.pop("poster", None)
                # meta.pop("clearlogo", None)
                # meta.pop("clearart", None)
                # meta.pop("fanart", None)
                # meta.pop("fanart2", None)
                # meta.pop("imdb", None)
                # meta.pop("tmdb", None)
                # meta.pop("metacache", None)
                # meta.pop("poster2", None)
                # meta.pop("poster3", None)
                # meta.pop("banner", None)
                # meta.pop("next", None)
                meta.pop("year", None)  if not meta.get("year") or meta.get("year") == "None"  else ""  # zabezpieczenie (TMDBHelper robił takie numery)

                if meta:
                    infoLabels = control.metadataClean(meta)
                else:
                    infoLabels = {}

                infoLabels.update({"OriginalTitle": originalname or title})  # oryginalny zamiast angielskiego tłumaczenia
                infoLabels.update({"title": label})  # musi być, gdy chcemy sortować w jakikolwiek sposób
                # infoLabels.update({"sorttitle": label})  # do przetestowania
                infoLabels.update({"count": i})  # potrzebne do powrotu do pierwotnej kolejności
                infoLabels.update({"size": source_utils.convert_size_to_bytes(items[i].get("size", ""))})
                # infoLabels.update({"country": items[i].get("language", "")})  # miało służyć do sortowania wg języka źródeł, ale koliduje z krajem produkcji

                duration_item = items[i].get("duration")
                # duration_meta = meta.get("duration")
                # fflog(f'{duration_item=} {duration_meta=}')
                if duration_item:
                    infoLabels.update({"duration": str(duration_item)})

                # fflog(f'infoLabels={json.dumps(infoLabels, indent=2)}',1,1)
                item.setInfo(type="Video", infoLabels=infoLabels)

                if generate_short_path:
                    item.setProperty("source", json.dumps([items[i]]))
                    item.setProperty("meta", json.dumps(meta))
                    # item.setProperty("mediatype", meta.get("mediatype",""))
                    # item.setProperty("url", items[i].get("url"))
                    pass

                # isFolder = True
                # if control.setting("player.dont_use_setResolvedUrl") != "true":
                if not dont_use_setResolvedUrl and not items[i]["url"].endswith(".strm") and not items[i].get("isFolder"):
                    item.setProperty('IsPlayable', 'true')  # ważne, gdy używamy metody xbmcplugin.setResolvedUrl (ma nadzieję, że nie powinno przeszkadzać, gdy używamy xbmc.Player().play)
                    isFolder = False
                    pass
                else:
                    isFolder = True
                    pass

                if isFolder:
                    sysurl = items[i].get("url")
                    external_plugin = re.sub("plugin://([^/]*).*", r"\1", sysurl)
                    external_plugins = control.window.getProperty('external_plugins_from_FF')
                    if external_plugin and external_plugin not in external_plugins.strip(',').split(','):
                        control.window.setProperty('external_plugins_from_FF', (external_plugins + f',{external_plugin}').lstrip(',') )

                if yatse:
                    vtag.setMediaType('video')  # yatse źle interpretuje element, gdy jest podany jako typ Movie, tzn. nie chce wyświetlać źródeł, jeśli mają być wyświetlone w katalogu (na fonie)

                #control.addItem(handle=syshandle, url=sysurl, listitem=item, isFolder=False)  # dodanie pojedynczego elementu przez Kodi do wirualnego folderu
                list_of_items.append((sysurl, item, isFolder,))  # dodanie elementu do listy, aby poźniej Kodi dodał je zbiorczo (lepsza wydajność w przypadku większej ilości pozyji)

                providers.append(items[i]["provider"])  # później do sprawdzenia, jakie wystąpiły (do wyjątku)

                # if auto_select_next_item_to_play:
                if True:  # potrzebuje zawsze, bo można wybrać autoplay z menu kontekstowego gdy są już wyświetlone źródła
                    list_of_sources.append(dict(items[i], label=label))
            except Exception:
                fflog_exc(1)
                continue

        # fflog(f'{len(list_of_items)=}',1,1)
        control.addItems(syshandle, list_of_items)  # dodanie zbiorcze

        # if control.setting("auto.select.next.item.to.play") == "true":
        # if auto_select_next_item_to_play:
        if True:  # potrzebuje zawsze, bo można wybrać autoplay z menu kontekstowego gdy są już wyświetlone źródła
            control.window.setProperty("plugin.video.fanvodpl.container.list_of_sources", json.dumps(list_of_sources))
            pass

        #control.content(syshandle, "videos")  # nie za bardzo się sprawdza, skórki nie mają chyba tego dobrze zaimplementowanego, poza tym, to raczej zarezerwowane dla różnych wideo, a tu są wszystkie takie same
        control.content(syshandle, "files")

        #if name != "odrzucone" and json.loads(control.window.getProperty(self.itemRejected)):
        if SHOW_REJECTED_GUI and (not trash) and json.loads(control.window.getProperty(self.itemRejected)):
            #name = "odrzucone"
            trash = True  # potrzebne niżej jako znacznik
            label = "[I]Zobacz odrzucone źródła (przez filtry)[/I]"
            item = control.item(label, offscreen=True)
            infoLabels = {}
            #infoLabels.update({"Title": label})  # musi być, gdy chcemy sortować w jakikolwiek sposób Uwaga: Title zarezerwowałem (patrz default.py)
            #infoLabels.update({"OriginalTitle": title})  # przekazuje parametr "title" do rekurencyjnego wywołania funkcji showItems (choć uniwersalniej byłoby wybrać item.setProperty)
            item.setProperty('title', title)
            infoLabels.update({"count": 1999})  # potrzebne do powrotu do pierwotnej kolejności
            item.setInfo("Video", infoLabels)
            icon = control.addonNext()
            addonFanart = control.addonFanart()
            addonLandscape = control.addonLandscape()
            item.setArt({"icon": icon, "thumb": icon, "poster": icon, "banner": icon, "fanart": addonFanart, "landscape": addonLandscape})
            if not control.setting("generate_short_path") == "true":
                sysurl = f"{sysaddon}?action=showItems&title={systitle}&trash=1"
            else:
                sysurl = f"{sysaddon}?action=showItems&trash=1"
            if "tvshowtitle" in meta and "season" in meta and "episode" in meta:
                sysurl += "&season=%s&episode=%s" % (season, episode)
            control.addItem(syshandle, sysurl, item, isFolder=True)


        # xbmcplugin.addSortMethod(syshandle, xbmcplugin.SORT_METHOD_UNSORTED)  # pokazuje napis "Domyślny", ale nie sortuje
        control.sortMethod(syshandle, xbmcplugin.SORT_METHOD_PLAYLIST_ORDER)
        control.sortMethod(syshandle, xbmcplugin.SORT_METHOD_SIZE)
        # control.sortMethod(syshandle, xbmcplugin.SORT_METHOD_COUNTRY)  # miało służyć do języka źródeł, ale koliduje z krajem produkcji (a nie wiem, jak zrobić SortByAudioLanguage)
        control.sortMethod(syshandle, xbmcplugin.SORT_METHOD_LASTPLAYED)
        control.sortMethod(syshandle, xbmcplugin.SORT_METHOD_PLAYCOUNT)
        # xbmcplugin.addSortMethod(syshandle, xbmcplugin.SORT_METHOD_BITRATE)  # to podobnie jak rozmiar - Kodi jakoś to sobie sam przelicza

        cacheToDisc = False  # mam większą kontrolę wówczas
        if control.setting("crefresh") != "true":  # można zrobić wyjątek
            pr_with_biblio = ['tb7', 'xt7', 'rapideo', 'nopremium', 'twojlimit']
            if not any(pr in pb for pr in providers for pb in pr_with_biblio):  # dla niektórych
                cacheToDisc = True  # tylko, że True czasami blokuje wymuszenie odświeżenia, gdy potrzeba, bo Kodi wczytuje sobie z cache i nie wiem, jak to zmienić (np. z Ulubionych przechodząc dalej)
        # fflog(f'{cacheToDisc=}')
        #if name:
        if trash:
            cacheToDisc = True

        # updateListing = False
        # params = dict(parse_qsl(sys.argv[2].replace("?", "")))
        params = dict(parse_qsl(sys.argv[2][1:]))
        # updateListing = False if params.get("trash") or params.get("item") else True  # True może świadczyć, że po drodze było odświeżanie
        updateListing = True if params.get("r") else False  # True świadczy, że po drodze było odświeżanie
        if updateListing:
            cacheToDisc = True  # nie wiem czy to potrzebne
            pass
        try:
            # fflog(f'{infoLabels=}',1,1)  # nie
            # fflog(f'{items[0]=}',1,1)  # nie
            # fflog(f'{meta=}',1,1)
            cat_label = ""
            if meta.get("episode"):
                # cat_label += meta.get("tvshowtitle") or ""
                cat_label += localtvshowtitle
                # dodanie roku serialu (choć to wydłuża labela)
                if meta.get('tvshowyear'):
                    # cat_label += f' ({meta["tvshowyear"]})'
                    pass
                elif TvShowYear:
                    # cat_label += f' ({TvShowYear})'
                    pass
                cat_label += f' / Sezon {meta.get("season", "")} / Odcinek {meta.get("episode")}'
                # cat_label += " / "
                # cat_label += meta["title"]  # tytuł odcinka  (jeszcze bardziej wydłuża labela)
            else:
                cat_label += meta["title"]
                if meta.get('year') and cat_label:
                    cat_label += f' ({meta["year"]})'
            cat_label = cat_label.strip(" /")
            control.pluginCategory(syshandle, cat_label)
        except Exception:
            fflog_exc(1)
            pass
        control.directory(syshandle, cacheToDisc=cacheToDisc, updateListing=updateListing)  # zamknięcie folderu
        # [FREE BUCKET] suppress Kodi playback-error dialog after listing update
        try:
            if control.window.getProperty('FanVodPL.freeBucket') == 'true' or control.window.getProperty('FanVodPL.forceCatalogThisSession') == 'true':
                control.sleep0(120)
                if control.condVisibility('Window.IsActive(okDialog)'):
                    control.execute('Dialog.Close(okDialog,true)')
        except Exception:
            pass

        fflog(f'[showItems] koniec wypisywania pozycji w katalogu', 0)

        views.setView("files")  # wymuszenie widoku (na w zależności od ustawień wtyczki)



    # def playItem(self, title, source, meta=None, **kwargs):
    def playItem(self, title="", source=None, meta=None, imdb=None, tmdb=None, season=None, episode=None, **kwargs):
        """ odtwarza źródła wyświetlone w katalogu """

        if not source:
            fflog(f'Błąd - brak ważnej zmiennej {source=}')
            control.dialog.notification('FanVodPL', 'błąd: brak zmiennej "source"', xbmcgui.NOTIFICATION_ERROR)
            return

        fflog("sprawdzanie linku do odtwarzania")
        #xbmcgui.Dialog().notification('', ('sprawdzam link ...'), sound=False)
        control.dialog.notification('', ('sprawdzam link ...'), sound=False)

        #try:
        if not meta:
            meta = control.window.getProperty(self.metaProperty)
            if meta:
                meta = json.loads(meta)
                if tmdb or imdb:
                    if not(imdb == meta.get("imdb", "") or tmdb == meta.get("tmdb", "")):
                        meta = {}
            if not meta and (tmdb or imdb):
                try:
                    if not episode:
                        fflog(f'próba pobrania metadanych z bazy dla filmu')
                        meta = cache.cache_get("superinfo" + f"_{tmdb or imdb}")
                        if not meta:
                            fflog('potrzeba pobrania informacji o filmie przez super_info.py')
                            from resources.lib.indexers.super_info import SuperInfo
                            media_list = [{'tmdb': tmdb, 'imdb': imdb}]
                            import requests
                            session = requests.Session()
                            lang = control.apiLanguage()["tmdb"]
                            super_info_obj = SuperInfo(media_list, session, lang)
                            super_info_obj.get_info(0)
                            meta = cache.cache_get("superinfo" + f"_{tmdb or imdb}")
                    else:
                        fflog(f'próba pobrania metadanych z bazy dla odcinka')
                        if season or season == 0:
                            meta = cache.cache_get("episodes" + f"_{tmdb or imdb}_s{season}")
                        else:
                            meta = cache.cache_get("episodes" + f"_{tmdb or imdb}")
                        if not meta:
                            fflog("trzeba pobrać dane odcinka z serwisu z internetu")
                            from resources.lib.indexers import episodes
                            meta = episodes.episodes().tmdb_list(imdb=imdb, tmdb=tmdb, season=season)
                            # meta = repr(meta)
                        else:
                            #from ast import literal_eval
                            fflog(f'dane odcinka powinny być w bazie cache')
                            #meta = meta["value"]
                            #meta = literal_eval(meta)
                    if meta:
                        if "value" in meta:
                            meta = meta["value"]
                            meta = literal_eval(meta)
                    else:
                        meta = {}
                except Exception:
                    meta = {}
                    fflog_exc(1)
            else:
                meta = {}
        else:
            if isinstance(meta, str):
                meta = json.loads(meta)

        if not title:
            title = meta.get("title", "")

        year = meta["year"] if "year" in meta else None

        if not season:
            season = meta["season"] if "season" in meta else None
        if not episode:
            episode = meta["episode"] if "episode" in meta else None

        imdb = meta["imdb"] if "imdb" in meta else None
        tvdb = meta["tvdb"] if "tvdb" in meta else None  # to chyba w przypadku traktu jest wykorzystywane
        tmdb = meta["tmdb"] if "tmdb" in meta else None  # dziwne, ale niewykorzystywane tu
        # self.test = {'Nazwa': title, 'Rok': year, 'Sezon': season, 'Odcinek': episode}

        progressDialog = None

        s = json.loads(source)[0]  # bo zostało przyszykowane w liście


        def _singleplay_playItem(i=0, info=True):
            """ trochę zrobiłem uniwersalną funkcję """
            if s["source"] == "pobrane" or s["provider"] == "pobrane":
                if progressDialog:
                    if progressDialog.iscanceled():
                        return True
                    try:
                        progressDialog.close()
                        pass
                    except Exception:
                        pass
                from ptw.libraries.player import player
                _ff_safe_close_ui()
                from ptw.libraries.player import player
                control.window.clearProperty("FanVodPL.forceCatalogThisSession")
                try:
                    fflog('[AUTO JAKOŚĆ] starting player.run', 1)# === FFGPT5: disable resolve-first to allow player().run (watched/history fix) ===
# [FFG-PAUSE] 
# [FFG-PAUSE]                     # FFRF: resolve-first (setResolvedUrl) for proper return to list
# [FFG-PAUSE]                     try:
# [FFG-PAUSE]                         import xbmcplugin, xbmcgui
# [FFG-PAUSE]                         _h = int(sys.argv[1])
# [FFG-PAUSE]                         if _h >= 0:
# [FFG-PAUSE]                             _li = xbmcgui.ListItem(path=str(url))
# [FFG-PAUSE]                             _li.setProperty('IsPlayable','true')
# [FFG-PAUSE]                             xbmcplugin.setResolvedUrl(_h, True, _li)
# [FFG-PAUSE]                             return
# [FFG-PAUSE]                     except Exception as _e:
# [FFG-PAUSE]                         pass
# [FFG-PAUSE] # === /FFGPT5 ===
                    player().run(title, year, season, episode, imdb, tvdb, tmdb, s["url"], meta=meta, hosting=s.get("source"), customPlayer=s.get("customPlayer"))
                except Exception as e:
                    fflog(f'[AUTO JAKOŚĆ] player.run failed: {e}', 1, 1)
                    try:
                        fflog('[AUTO JAKOŚĆ] fallback: control.resolve -> próbuję uruchomić odtwarzanie przez Kodi', 1)
                        control.resolve(handle, True, control.item(path=str(url)))
                    except Exception as e2:
                        fflog(f'[AUTO JAKOŚĆ] control.resolve fallback failed: {e2}', 1, 1)
                        try:
                            self.showItems(title, filtered_items, None, season, episode)
                        except Exception:
                            pass
                return True

            if i == 0:
                if s["provider"] in ['tb7', 'xt7']:
                    if not 'for_sourcesResolve' in kwargs:
                        kwargs['for_sourcesResolve'] = {'for_resolve': {}}
                    kwargs['for_sourcesResolve']['for_resolve'].update({'specific_source_data': s})

                if "for_resolve" in s:
                    if not 'for_sourcesResolve' in kwargs:
                        kwargs['for_sourcesResolve'] = {'for_resolve': {}}
                    kwargs['for_sourcesResolve']['for_resolve'].update(s['for_resolve'])

            if 'for_sourcesResolve' in kwargs and i == 0:
                url = self.sourcesResolve(s, **kwargs['for_sourcesResolve'])
            else:
                url = self.sourcesResolve(s)

            if url:
                if progressDialog:
                    if progressDialog.iscanceled():
                        return True
                    try:
                        progressDialog.close()
                        pass
                    except Exception:
                        pass
                from ptw.libraries.player import player
                _ff_safe_close_ui()
                from ptw.libraries.player import player
                control.window.clearProperty("FanVodPL.forceCatalogThisSession")
                try:
                    fflog('[AUTO JAKOŚĆ] starting player.run', 1)# === FFGPT5: disable resolve-first to allow player().run (watched/history fix) ===
# [FFG-PAUSE] 
# [FFG-PAUSE]                     # FFRF: resolve-first (setResolvedUrl) for proper return to list
# [FFG-PAUSE]                     try:
# [FFG-PAUSE]                         import xbmcplugin, xbmcgui
# [FFG-PAUSE]                         _h = int(sys.argv[1])
# [FFG-PAUSE]                         if _h >= 0:
# [FFG-PAUSE]                             _li = xbmcgui.ListItem(path=str(url))
# [FFG-PAUSE]                             _li.setProperty('IsPlayable','true')
# [FFG-PAUSE]                             xbmcplugin.setResolvedUrl(_h, True, _li)
# [FFG-PAUSE]                             return
# [FFG-PAUSE]                     except Exception as _e:
# [FFG-PAUSE]                         pass
# [FFG-PAUSE] # === /FFGPT5 ===
                    player().run(title, year, season, episode, imdb, tvdb, tmdb, url, meta=meta, hosting=s.get("source"), customPlayer=s.get("customPlayer"))
                except Exception as e:
                    fflog(f'[AUTO JAKOŚĆ] player.run failed: {e}', 1, 1)
                    try:
                        fflog('[AUTO JAKOŚĆ] fallback: control.resolve -> próbuję uruchomić odtwarzanie przez Kodi', 1)
                        control.resolve(handle, True, control.item(path=str(url)))
                    except Exception as e2:
                        fflog(f'[AUTO JAKOŚĆ] control.resolve fallback failed: {e2}', 1, 1)
                        try:
                            self.showItems(title, filtered_items, None, season, episode)
                        except Exception:
                            pass
                return True
            else:
                if url is not False:
                    c = 0
                    while control.condVisibility('Window.IsActive(notification)') and c < (5 * 2):
                        c += 1
                        control.sleep(200)
                    if info:
                        control.sleep(200)
                        # control.dialog.notification('', ('źródło nie działa'), xbmcgui.NOTIFICATION_WARNING)
                        control.infoDialog('źródło nie działa', '', "WARNING")
                        control.sleep(500)
                else:  # False coś miało oznaczać, nie pamiętam, może anulowanie przez użytkownika?
                    if control.condVisibility('Window.IsActive(notification)'):
                        control.execute('Dialog.Close(notification,true)')
                        pass

        auto_select_next_item_to_play = kwargs.get("auto_select_next_item_to_play")
        auto_select_next_item_to_play = control.setting("auto.select.next.item.to.play") == "true" if auto_select_next_item_to_play is None else auto_select_next_item_to_play
        # if control.setting("auto.select.next.item.to.play") != "true":
        if not auto_select_next_item_to_play:
            _singleplay_playItem()
        else:
            fflog(f'auto play',1,1)
            next = []
            prev = []
            total = []
            for i in range(1, 1000):
                try:
                    # następny od wybranego
                    u = control.infoLabel("ListItem(%s).FolderPath" % str(i))  # to teraz mi nie działa (przestało działać)
                    if u in total:
                        raise Exception()
                    total.append(u)
                    u = dict(parse_qsl(u.replace("?", "")))
                    u = json.loads(u["source"])[0]  # bo zostało przyszykowane w liście
                    u.update({"label": control.infoLabel("ListItem(%s).Label" % str(i))})
                    next.append(u)
                except Exception:
                    # fflog_exc(1)
                    break
            for i in range(-1000, 0)[::-1]:
                try:
                    # poprzedni od wybranego
                    u = control.infoLabel("ListItem(%s).FolderPath" % str(i))  # tu chyba może nie być labela
                    if u in total:
                        raise Exception()
                    total.append(u)
                    u = dict(parse_qsl(u.replace("?", "")))
                    u = json.loads(u["source"])[0]  # bo zostało przyszykowane w liście
                    u.update({"label": control.infoLabel("ListItem(%s).Label" % str(i))})
                    prev.append(u)
                except Exception:
                    # fflog_exc(1)
                    break
            total = list(filter(None, total))  # usunięcie pustych (ważne)
            # fflog(f'{total=}  {next=}  {prev=}',1,1)

            if not total:
                fflog(f'{total=}',1,1)
                # fflog(f'{control.infoLabel("Container().CurrentItem")=}')
                # fflog(f'{control.infoLabel("Container().NumItems")=}')
                CurrentItem = int(control.infoLabel("Container().CurrentItem"))
                # NumItems = int(control.infoLabel("Container().NumItems"))
                # wczytanie z pamięci
                list_of_sources = control.window.getProperty("plugin.video.fanvodpl.container.list_of_sources")
                list_of_sources = json.loads(list_of_sources)
                # fflog(f'{len(list_of_sources)=}')
                # fflog(f'{list_of_sources=}')
                # uzupełnienie reszty
                next = list_of_sources[CurrentItem:]
                prev = list_of_sources[:CurrentItem-1]
                # fflog(f'{len(next)=}  {len(prev)=}')
                # fflog(f'\n{next=} \n{prev=}')

            items = json.loads(source)  # wybrany  (uważam, że zmienna powinna się nazywać item)
            # fflog(f'wybrany {len(items)=}')  # powinno być 1
            # fflog(f'wybrany {items=}')
            items[0].update({"label": control.infoLabel("ListItem.Label")})  # items[0], bo zostało przyszykowane w liście
            # fflog(f'{control.infoLabel("ListItem.Label")=}')
            # fflog(f'wybrany {items=}')
            # items = [items]  # jakby nie było przyszykowanego w liście

            items = [i for i in items + next + prev][:40]
            # fflog(f'{len(items)=}')
            # fflog(f'{items=}')


            if len(items) == 1:
                # fflog(f'[playItem] {control.setting("auto.select.next.item.to.play")=} but {len(items)=} -> back to single play', 0)
                fflog(f'[playItem] {auto_select_next_item_to_play=} but {len(items)=} -> back to single play', 0)
                return _singleplay_playItem()

            header = control.addonInfo("name")
            header2 = header.upper()

            progressDialog = (
                control.progressDialog
                if control.setting("progress.dialog") == "0"
                else control.progressDialogBG
            )
            progressDialog.create(header, "")
            # progressDialog.update(0)
            control.sleep(100)

            focus_panel_id = control.getCurrentViewId()  # focus_panel_id
            # fflog(f"{focus_panel_id=}", 1,1)

            block = None
            monitor = control.monitor
            import threading

            fflog(f'{len(items)=}',1,1)
            # fflog(f'{json.dumps(items, indent=2)}')

            for i in range(len(items)):

                # fflog(f'{i=}  {items[i]=}',1,1)
                # fflog(f'{i=}  {items[i].get("label")=}',1,1)

                try:
                    # fflog(f'{i=}  {items[i].get("provider")=}  {items[i].get("source")=} ')
                    if items[i].get("source") == "pobrane" or items[i].get("provider") == "pobrane":
                        continue
                    else:
                        label = ""
                        try:
                            if progressDialog.iscanceled():
                                break
                            if len(items) == 1:
                                label = control.infoLabel("ListItem.Label")
                                # fflog(f'{i=}  {label=} (pojedynczy)')
                            else:
                                label = items[i].get("label") or items[i].get("filename") or ""
                                # fflog(f'{i=}  {label=}')
                            label = label.replace('   ', '')  # pomaga, jak jest stosowany fix na scrolowanie długich tytułów z 2-gą linią
                            # fflog(f'{i=}  {label=}')
                            progressDialog.update(int((100 / float(len(items))) * i),
                                str(label) + "\n" + str(" "),
                            )
                        except Exception:
                            fflog_exc(1)
                            label = label.replace('   ', '')
                            progressDialog.update(int((100 / float(len(items))) * i),
                                str(header2) + "\n" + str(label),
                            )

                        if False:  # testuje jeszcze
                            s = items[i]
                            if _singleplay_playItem(i, info=False):  # ten sam wątek
                                return
                            else:
                                if progressDialog.iscanceled():
                                    return progressDialog.close()
                                monitor.waitForAbort(0.5)
                                if monitor.abortRequested():
                                    return sys.exit()
                                if progressDialog.iscanceled():
                                    return progressDialog.close()
                                continue

                        # rozwiązywanie adresu jest w oddzielnym wątku, odtwarzanie już w tym samym, ale ogólnie jakby większa responsywność (można łatwiej przerwać)
                        if items[i].get("source") == block:
                            raise Exception()
                        if 'for_sourcesResolve' in kwargs and i == 0:  # tylko dla pierwszego wybranego
                            w = threading.Thread(
                                target=self.sourcesResolve, args=(items[i],), kwargs=kwargs['for_sourcesResolve']
                            )
                        else:
                            w = threading.Thread(
                                target=self.sourcesResolve, args=(items[i],)
                            )
                        w.start()

                        offset = (
                            60 * 2
                            if items[i].get("source") in self.hostcapDict
                            else 0
                        )

                        m = ""

                        for x in range(3600):
                            try:
                                if monitor.abortRequested():
                                    return sys.exit()
                                if progressDialog.iscanceled():
                                    return progressDialog.close()
                            except Exception:
                                pass

                            k = control.condVisibility("Window.IsActive(virtualkeyboard)")
                            if k:
                                m += "1"
                                m = m[-1]
                            if (not w.is_alive() or x > 30 + offset) and not k:
                                break
                            k = control.condVisibility("Window.IsActive(yesnoDialog)")
                            if k:
                                m += "1"
                                m = m[-1]
                            if (not w.is_alive() or x > 30 + offset) and not k:
                                break
                            # time.sleep(1.5)
                            control.sleep(1500)

                        for x in range(30):
                            try:
                                if monitor.abortRequested():
                                    return sys.exit()
                                if progressDialog.iscanceled():
                                    return progressDialog.close()
                            except Exception:
                                pass

                            if m == "":
                                break
                            if not w.is_alive():
                                break
                            time.sleep(0.5)

                        if w.is_alive():
                            block = items[i].get("source")

                        if self.url is None:
                            # raise Exception(f'{self.url=}')
                            raise Exception()

                        try:
                            progressDialog.close()
                        except Exception:
                            pass

                        control.sleep(200)
                        control.execute("Dialog.Close(virtualkeyboard)")
                        control.execute("Dialog.Close(yesnoDialog)")

                        # fflog(f'{items[i].get("url")=}',1,1)
                        # fflog(f'{self.url=}',1,1)  # po resolverze
                        # meta.update({"link1": items[i].get("url"), "link2": str(self.url)})  # do czego 2 linki? i do czego to w ogóle jest potrzebne ?

                        from ptw.libraries.player import player
                        _ff_safe_close_ui()
                        from ptw.libraries.player import player
                        control.window.clearProperty("FanVodPL.forceCatalogThisSession")
                        try:
                            fflog('[AUTO JAKOŚĆ] starting player.run', 1)# === FFGPT5: disable resolve-first to allow player().run (watched/history fix) ===
# [FFG-PAUSE] 
# [FFG-PAUSE]                             # FFRF: resolve-first (setResolvedUrl) for proper return to list
# [FFG-PAUSE]                             try:
# [FFG-PAUSE]                                 import xbmcplugin, xbmcgui
# [FFG-PAUSE]                                 _h = int(sys.argv[1])
# [FFG-PAUSE]                                 if _h >= 0:
# [FFG-PAUSE]                                     _li = xbmcgui.ListItem(path=str(url))
# [FFG-PAUSE]                                     _li.setProperty('IsPlayable','true')
# [FFG-PAUSE]                                     xbmcplugin.setResolvedUrl(_h, True, _li)
# [FFG-PAUSE]                                     return
# [FFG-PAUSE]                             except Exception as _e:
# [FFG-PAUSE]                                 pass
# [FFG-PAUSE] # === /FFGPT5 ===
                            player().run(title, year, season, episode, imdb, tvdb, tmdb, self.url, meta=meta, hosting=items[i].get("source"), customPlayer=items[i].get("customPlayer"))
                        except Exception as e:
                            fflog(f'[AUTO JAKOŚĆ] player.run failed: {e}', 1, 1)
                            try:
                                fflog('[AUTO JAKOŚĆ] fallback: control.resolve -> próbuję uruchomić odtwarzanie przez Kodi', 1)
                                control.resolve(handle, True, control.item(path=str(url)))
                            except Exception as e2:
                                fflog(f'[AUTO JAKOŚĆ] control.resolve fallback failed: {e2}', 1, 1)
                                try:
                                    self.showItems(title, filtered_items, None, season, episode)
                                except Exception:
                                    pass

                        return self.url
                except Exception as e:
                    print(e)
                    # fflog(f"{e=}  {str(e)=}",1,1)
                    if str(e):
                        fflog(f"{str(e)=}",1,1)
                        self.errorForSources(str(e))
                    pass

                    if not self.url:
                        if (i+1) < len(items):
                            # control.sleep(500)
                            # control.infoDialog(f"próbuję następne źródło ({i+2})", icon="INFO", sound=False)
                            fflog(f"próbuję następne źródło ({i+2}/{len(items)})",1,1)
                            # control.sleep(500)
                            if 1:
                                label = items[i+1].get("label") or ""
                                # fflog(f'następny {label=}',1,1)
                                numer_na_liscie = re.search(r'^(?:\[LIGHT])?(\d+)', label)
                                numer_na_liscie = int(numer_na_liscie[1]) if numer_na_liscie else ""
                                numer_na_liscie = ""  # bo nie chce to działać
                                if numer_na_liscie:
                                    fflog(f'{numer_na_liscie=}',1,1)
                                    control.execute(f'SetFocus({focus_panel_id},{numer_na_liscie},absolute)')  # nie działa - nie przesuwa się ramka
                                else:
                                    # control.execute('Action(Down)')  # to nie działa tu
                                    # control.execute(f'Control.Move({focus_panel_id},1)')  # to też nie
                                    control.execute(f'Control.Message({focus_panel_id},moveup)')
                                    control.sleep(100)  # musi być jakaś zwłoka
                                    new_focused_label = control.infoLabel('ListItem.Label')
                                    # fflog(f'{new_focused_label=}',1,1)
                                    if new_focused_label == ".." or "obacz odrzucone źródła" in new_focused_label:
                                        control.execute(f'Control.Message({focus_panel_id},moveup)')
                                        control.sleep(100)
                                        new_focused_label = control.infoLabel('ListItem.Label')
                                        # fflog(f'{new_focused_label=}',1,1)
                                        if new_focused_label == "..":
                                            control.execute(f'Control.Message({focus_panel_id},moveup)')
                                            # control.sleep(100)

            try:
                progressDialog.close()
            except Exception:
                pass

            self.errorForSources()  # to chyba jednak musi tu być
        """
        except Exception as e:
            print(e)
            if str(e):
                log(f'[playItem] {e!r}')
            xbmcgui.Dialog().notification('Problem', (f'Wystąpił jakiś błąd: \n{str(e)!r}'), xbmcgui.NOTIFICATION_ERROR)
            pass
        """



    def getSources(
            self,
            title,
            localtitle,
            year,
            imdb,
            tvdb,
            tmdb,
            season,
            episode,
            tvshowtitle,
            premiered,
            originalname='',
            duration='',
            poster='',
            quality="HD",
            timeout=30,
            progressDialogBG=None,
            sort=None,
        ):
        content = "movie" if tvshowtitle is None else "show"  # czy "episode" ?
        fflog(f'{content=}',1,1)
        ids = self.getIds(content, imdb, tmdb, tvdb)  # tu "movie" or "show" (nie "episode")
        trakt_id = ids.get("trakt") or ids.get("slug")
        fflog(f'{ids=}',1,1)
        localtvshowtitle = self.getLocalTitle(tvshowtitle, imdb, tvdb, "show", tmdb=tmdb) if tvshowtitle else ""
        fflog(f'{localtvshowtitle=}',1,1) if tvshowtitle else ""

        premiered = premiered if premiered else ""

        if control.player.isPlayingVideo():
            control.player.pause()

        # ---------------------------------------------------------------
        # NOWY DIALOG WYSZUKIWANIA (SearchSourcesDialog)
        # zastępuje standardowy progressDialog bardziej czytelnym oknem
        # ---------------------------------------------------------------
        try:
            from ptw.libraries.search_dialog import create_search_dialog, _best_quality as _bq
            _dlg_title = (localtvshowtitle or localtitle or title or '').strip()
            _dlg_meta  = ''
            if episode:
                _dlg_meta += 'S%02dE%02d' % (int(season or 1), int(episode))
            if year:
                _dlg_meta += ('  |  ' if _dlg_meta else '') + str(year)
            if duration:
                try:
                    _dur_sec = int(duration)
                    # duration w Kodi może być w minutach LUB sekundach
                    # jeśli > 300 zakładamy sekundy i przeliczamy
                    _dur_min = _dur_sec // 60 if _dur_sec > 300 else _dur_sec
                    _dlg_meta += ('  |  ' if _dlg_meta else '') + '%d min' % _dur_min
                except Exception:
                    pass
            _dlg_rating = ''
            try:
                _r = control.window.getProperty('VideoPlayer.Rating') or ''
                if _r: _dlg_rating = '%.1f/10' % float(_r)
            except Exception:
                pass
            searchDialog = create_search_dialog(
                title=_dlg_title, meta=_dlg_meta,
                poster=poster or '',
                rating=_dlg_rating,
            )
            progressDialog = searchDialog          # alias – nie zmienia reszty kodu
            _search_dialog_active = True
        except Exception:
            fflog_exc(1)
            _search_dialog_active = False
            if progressDialogBG is None:
                progressDialog = (
                    control.progressDialog
                    if control.setting("progress.dialog") == "0"
                    else control.progressDialogBG
                )
            elif not progressDialogBG:
                progressDialog = control.progressDialog
            else:
                progressDialog = control.progressDialogBG
            yatse = control.setting("yatse") == "true"
            if yatse:
                progressDialog = control.progressDialogBG
            progressDialog.create(localtvshowtitle or localtitle or 'Wyszukiwanie źródeł', '')

        # Pomocnik: aktualizuje nowy dialog z surowymi danymi liczbowymi
        def _sd_update(pct):
            """Aktualizuje SearchSourcesDialog; ignorowany gdy dialog nieaktywny."""
            if not _search_dialog_active:
                return
            try:
                # Liczymy bezpośrednio z self.sources (bez filtrów qmax/qmin)
                # HD/4K = źródła z jakością 4K, 1440p, 1080p, 1080i
                # SD/720p = źródła z jakością 720p, HD, SD i pozostałe
                _hd_q  = {'4K', '1440p', '1080p', '1080i'}
                _sd_q  = {'720p', 'HD', 'SD'}
                _hd_n  = sum(1 for e in self.sources if e.get('quality', '') in _hd_q and not e.get('debridonly'))
                _sd_n  = sum(1 for e in self.sources if e.get('quality', '') not in _hd_q and not e.get('debridonly'))
                searchDialog.update_sources(
                    premium_total=_hd_n,
                    free_total=_sd_n,
                    percent=pct,
                )
            except Exception:
                pass

        self.prepareSources()  # prepare database

        control.sleep(1200)  # czas na wycofanie się użytkownika z wyszukiwania źródeł

        try:
            if progressDialog.iscanceled():
                control.sleep(500)
                progressDialog.close()
                return self.sources
        except Exception:
            # fflog_exc(1)
            pass

        line2 = control.lang(32600)  # Przygotowywanie źródeł

        if _search_dialog_active:
            searchDialog.update_sources(percent=0, status=str(line2))
        else:
            progressDialog.update(0, line2)


        language = self.getLanguage()
        # fflog(f'{language=}')

        if not self.sourceDict:
            self.getScrapers('', language)
        sourceDict = self.sourceDict
        # fflog(f'{len(sourceDict)=}')
        # fflog(f'{len(sourceDict)=}  {sourceDict=}', 1)

        # start sources reduction
        # wartość -1 oznacza wyłączenie, więc out
        sourceDict = [i for i in sourceDict if i[1].priority != -1]
        # fflog(f'{len(sourceDict)=}')

        content = "movie" if tvshowtitle is None else "episode"  # a nie powinno być "show" ?
        if content == "movie":
            sourceDict = [(i[0], i[1], getattr(i[1], "movie",  None)) for i in sourceDict]
            # genres = trakt.getGenre("movie", "imdb", imdb)
            genres = trakt.getGenre("movie", "tmdb", tmdb)
        else:
            sourceDict = [(i[0], i[1], getattr(i[1], "tvshow", None)) for i in sourceDict]
            # genres = trakt.getGenre("show", "tvdb", tvdb)
            genres = trakt.getGenre("show", "tmdb", tmdb)
        # fflog(f'{genres=}')
        # fflog(f'{len(sourceDict)=} {sourceDict=}')
        sourceDict = [
            (i[0], i[1], i[2])
            for i in sourceDict
            if (not hasattr(i[1], "genre_filter")
                or not i[1].genre_filter
                or any(x in i[1].genre_filter for x in genres))
        ]
        # fflog(f'{len(sourceDict)=} {sourceDict=}')
        sourceDict = [(i[0], i[1]) for i in sourceDict if not i[2] is None]
        # fflog(f'{len(sourceDict)=} {sourceDict=}')

        sourceDict = [(i[0], i[1], i[1].language) for i in sourceDict]
        # fflog(f'{len(sourceDict)=} {sourceDict=}')
        sourceDict = [(i[0], i[1]) for i in sourceDict if any(x in i[2] for x in language)]
        # fflog(f'{len(sourceDict)=} {sourceDict=}')

        try:
            sourceDict = [(i[0], i[1], control.setting("provider." + i[0])) for i in sourceDict]
        except Exception:
            fflog_exc(1)
            sourceDict = [(i[0], i[1], "true") for i in sourceDict]
        # fflog(f'{len(sourceDict)=} {sourceDict=}')

        sourceDict = [(i[0], i[1]) for i in sourceDict if not i[2] == "false"]
        # fflog(f'{len(sourceDict)=} {sourceDict=}')

        sourceDict = [(i[0], i[1], i[1].priority) for i in sourceDict]
        # fflog(f'{len(sourceDict)=} {sourceDict=}')

        random.shuffle(sourceDict)
        sourceDict = sorted(sourceDict, key=lambda i: i[2])

        fflog(f'{len(sourceDict)=} {sourceDict=}', 0)

        self.sourceDict = sourceDict


        import threading

        threads = []

        control.window.clearProperty("blocked_sources_extend")
        self.blocked_sources_extend = False

        if content == "movie":
            # title = self.getTitle(title)  # niszczy polskie znaki diakrytyczne
            # localtitle = self.getTitle(localtitle)  # niszczy polskie znaki diakrytyczne
            # originalname = self.getTitle(originalname)  # niszczy polskie znaki diakrytyczne
            # aliases = self.getAliasTitles(imdb, localtitle, content)
            aliases = self.getAliasTitles(trakt_id, localtitle, content)
            if originalname:
                aliases.append({"originalname": originalname, 'country': 'original' })
            for i in sourceDict:
                threads.append(
                    threading.Thread(
                        target=self.getMovieSource,
                        args=(title, localtitle, aliases, year, imdb, i[0], i[1], False),
                        kwargs={"premiered": premiered, "tmdb": tmdb, "duration": duration, "poster": poster},
                    )
                )
        else:
            # tvshowtitle = self.getTitle(tvshowtitle)  # niszczy polskie znaki diakrytyczne
            # localtvshowtitle = self.getLocalTitle(tvshowtitle, imdb, tvdb, "show") if not localtvshowtitle else localtvshowtitle  # robię tę instrukcję na początku tej funkcji
            aliases = self.getAliasTitles(trakt_id, localtvshowtitle, "show")
            if originalname:
                aliases.append({"originalname": originalname, 'country': 'original' })
            # Disabled on 11/11/17 due to hang. Should be checked in the future and possible enabled again.
            # season, episode = thexem.get_scene_episode_number(tvdb, season, episode)
            # import threading  # to jest już wyżej
            for i in sourceDict:
                threads.append(
                    threading.Thread(
                        target=self.getEpisodeSource,
                        args=(
                            title,
                            year,
                            imdb,
                            tvdb,
                            season,
                            episode,
                            tvshowtitle,
                            localtvshowtitle,
                            aliases,
                            premiered,
                            i[0],
                            i[1],
                        ),
                        kwargs={"tmdb": tmdb, "duration": duration, "poster": poster},
                    )
                )

        s = [i[0] + (i[1],) for i in zip(sourceDict, threads)]
        s = [(i[3].getName(), i[0], i[2]) for i in s]

        mainsourceDict = [i[0] for i in s if i[2] == 0]
        sourcelabelDict = dict([(i[0], i[1].upper()) for i in s])

        [i.start() for i in threads]

        # string1 = control.lang(32404)  -- NOT USED
        # string2 = control.lang(32405)  -- NOT USED
        string3 = control.lang(32406)
        string4 = control.lang(32601)
        # string5 = control.lang(32602)  -- NOT USED
        string6 = control.lang(32606)
        string7 = control.lang(32607)
        info_static = "[COLOR white]Premium są filtrowane / Darmowe nie[/COLOR]\n[COLOR white]Zakazane frazy z złą jakość obrazu i dźwięku[/COLOR]\n[COLOR white]Jeśli jakaś nowa fraza przejdzie, można ją zablokować[/COLOR]"

        try:
            timeout = int(control.setting("scrapers.timeout.1"))
            #timeout = 3  # test
        except Exception:
            pass

        quality = control.setting("hosts.quality")
        if quality == "":
            quality = "0"
        qmax = int(quality)
        qmin = int(control.setting("hosts.quality.min"))
        #quality = "3"
        #qmax = 3  # test
        #qmin = 3  # test

        line1 = line2 = line3 = ""
        # debrid_only = control.setting("debrid.only")  -- NOT USED

        pre_emp = str(control.setting("preemptive.termination")) == 'true'
        pre_emp_limit = int(control.setting("preemptive.limit"))
        #pre_emp = True  # test
        #pre_emp_limit = 2  # test

        source_4k = d_source_4k = 0
        source_1440 = d_source_1440 = 0
        source_1080 = d_source_1080 = 0
        source_720 = d_source_720 = 0
        source_sd = d_source_sd = 0
        total = d_total = 0

        debrid_list = debrid.debrid_resolvers
        debrid_status = debrid.status()

        total_format = "[COLOR %s][B]%s[/B][/COLOR]"

        pdiag_tot_format = " %s: %s "
        pdiag_format = " 4K: %s | 2k: %s | FullHD: %s | HD: %s | SD: %s ".split("|")
        if debrid_status:
            pdiag_format = " 4K: %s | 1080p: %s | 720p: %s | SD: %s | %s: %s".split("|")

        pdiag_bg_tot_format = "T:%s(%s)"
        pdiag_bg_format = "4K:%s(%s)|2k:%s(%s)|FullHD:%s(%s)|HD:%s(%s)|SD:%s(%s)".split("|")
        if debrid_status:
            pdiag_bg_format = "4K:%s(%s)|1080p:%s(%s)|720p:%s(%s)|SD:%s(%s)|T:%s(%s)".split("|")

        monitor = control.monitor

        for i in range(0, 4 * timeout):

            if pre_emp:
                if (
                    source_4k
                    + d_source_4k
                    + source_1440
                    + d_source_1440
                    + source_1080
                    + d_source_1080
                    + source_720
                    + d_source_720
                    + source_sd
                    + d_source_sd
                ) >= pre_emp_limit:
                    line2 = f'Osiągnięto założony limit źródeł'
                    percent = int(100 * float(i) / (2 * timeout) + 0.5)
                    _sd_update(max(1, percent)) if _search_dialog_active else progressDialog.update(max(1, percent), info_static)
                    log(f'[getSources] {line2} ({pre_emp_limit})')
                    break

            try:
                if monitor.abortRequested():
                    return sys.exit()

                try:
                    if progressDialog.iscanceled():
                        break
                except Exception:
                    pass

                if len(self.sources) > 0:
                    #if quality in ["0"]:
                    if True:
                        source_4k = len(
                            [
                                e
                                for e in self.sources
                                if e["quality"] == "4K" and not e["debridonly"]
                            ]
                        ) if qmax == 0 else 0
                        source_1440 = len(
                            [
                                e
                                for e in self.sources
                                if e["quality"] in ["1440p"] and not e["debridonly"]
                            ]
                        ) if qmax <= 1 and qmin >=1 else 0
                        source_1080 = len(
                            [
                                e
                                for e in self.sources
                                if e["quality"] in ["1080p", "1080i"] and not e["debridonly"]
                            ]
                        ) if qmax <= 2 and qmin >=2 else 0
                        source_720 = len(
                            [
                                e
                                for e in self.sources
                                if e["quality"] in ["720p", "HD"] and not e["debridonly"]
                            ]
                        ) if qmax <= 3 and qmin >=3 else 0
                        source_sd = len(
                            [
                                e
                                for e in self.sources
                                if e["quality"] == "SD" and not e["debridonly"]
                            ]
                        ) if qmax <= 4 and qmin >=4 else 0
                    """
                    elif quality in ["1"]:
                        source_1080 = len(
                            [
                                e
                                for e in self.sources
                                if e["quality"] in ["1440p", "1080p", "1080i"] and not e["debridonly"]
                            ]
                        )
                        source_720 = len(
                            [
                                e
                                for e in self.sources
                                if e["quality"] in ["720p", "HD"] and not e["debridonly"]
                            ]
                        )
                        source_sd = len(
                            [
                                e
                                for e in self.sources
                                if e["quality"] == "SD" and not e["debridonly"]
                            ]
                        )
                    elif quality in ["2"]:
                        source_1080 = len(
                            [
                                e
                                for e in self.sources
                                if e["quality"] in ["1080p", "1080i"] and not e["debridonly"]
                            ]
                        )
                        source_720 = len(
                            [
                                e
                                for e in self.sources
                                if e["quality"] in ["720p", "HD"] and not e["debridonly"]
                            ]
                        )
                        source_sd = len(
                            [
                                e
                                for e in self.sources
                                if e["quality"] == "SD" and not e["debridonly"]
                            ]
                        )
                    elif quality in ["3"]:
                        source_720 = len(
                            [
                                e
                                for e in self.sources
                                if e["quality"] in ["720p", "HD"] and not e["debridonly"]
                            ]
                        )
                        source_sd = len(
                            [
                                e
                                for e in self.sources
                                if e["quality"] == "SD" and not e["debridonly"]
                            ]
                        )
                    else:
                        source_sd = len(
                            [
                                e
                                for e in self.sources
                                if e["quality"] == "SD" and not e["debridonly"]
                            ]
                        )
                    """
                    total = source_4k + source_1440 + source_1080 + source_720 + source_sd

                    if debrid_status:
                        if quality in ["0"]:
                            for d in debrid_list:
                                d_source_4k = len(
                                    [
                                        e
                                        for e in self.sources
                                        if e["quality"] == "4K" and d.valid_url("", e["source"])
                                    ]
                                )
                                d_source_1080 = len(
                                    [
                                        e
                                        for e in self.sources
                                        if e["quality"] in ["1440p", "1080p", "1080i"] and d.valid_url("", e["source"])
                                    ]
                                )
                                d_source_720 = len(
                                    [
                                        e
                                        for e in self.sources
                                        if e["quality"] in ["720p", "HD"] and d.valid_url("", e["source"])
                                    ]
                                )
                                d_source_sd = len(
                                    [
                                        e
                                        for e in self.sources
                                        if e["quality"] == "SD" and d.valid_url("", e["source"])
                                    ]
                                )
                        elif quality in ["1"]:
                            for d in debrid_list:
                                d_source_1080 = len(
                                    [
                                        e
                                        for e in self.sources
                                        if e["quality"] in ["1440p", "1080p", "1080i"] and d.valid_url("", e["source"])
                                    ]
                                )
                                d_source_720 = len(
                                    [
                                        e
                                        for e in self.sources
                                        if e["quality"] in ["720p", "HD"] and d.valid_url("", e["source"])
                                    ]
                                )
                                d_source_sd = len(
                                    [
                                        e
                                        for e in self.sources
                                        if e["quality"] == "SD" and d.valid_url("", e["source"])
                                    ]
                                )
                        elif quality in ["2"]:
                            for d in debrid_list:
                                d_source_1080 = len(
                                    [
                                        e
                                        for e in self.sources
                                        if e["quality"] in ["1080p", "1080i"] and d.valid_url("", e["source"])
                                    ]
                                )
                                d_source_720 = len(
                                    [
                                        e
                                        for e in self.sources
                                        if e["quality"] in ["720p", "HD"] and d.valid_url("", e["source"])
                                    ]
                                )
                                d_source_sd = len(
                                    [
                                        e
                                        for e in self.sources
                                        if e["quality"] == "SD" and d.valid_url("", e["source"])
                                    ]
                                )
                        elif quality in ["3"]:
                            for d in debrid_list:
                                d_source_720 = len(
                                    [
                                        e
                                        for e in self.sources
                                        if e["quality"] in ["720p", "HD"] and d.valid_url("", e["source"])
                                    ]
                                )
                                d_source_sd = len(
                                    [
                                        e
                                        for e in self.sources
                                        if e["quality"] == "SD" and d.valid_url("", e["source"])
                                    ]
                                )
                        else:
                            for d in debrid_list:
                                d_source_sd = len(
                                    [
                                        e
                                        for e in self.sources
                                        if e["quality"] == "SD" and d.valid_url("", e["source"])
                                    ]
                                )

                        d_total = d_source_4k + d_source_1080 + d_source_720 + d_source_sd

                if debrid_status:
                    d_4k_label = (
                        total_format % ("red", d_source_4k)
                        if d_source_4k == 0
                        else total_format % ("lime", d_source_4k)
                    )
                    d_1080_label = (
                        total_format % ("red", d_source_1080)
                        if d_source_1080 == 0
                        else total_format % ("lime", d_source_1080)
                    )
                    d_720_label = (
                        total_format % ("red", d_source_720)
                        if d_source_720 == 0
                        else total_format % ("lime", d_source_720)
                    )
                    d_sd_label = (
                        total_format % ("red", d_source_sd)
                        if d_source_sd == 0
                        else total_format % ("lime", d_source_sd)
                    )
                    d_total_label = (
                        total_format % ("red", d_total)
                        if d_total == 0
                        else total_format % ("lime", d_total)
                    )

                source_4k_label = (
                    total_format % ("red", source_4k)
                    if source_4k == 0
                    else total_format % ("lime", source_4k)
                )
                source_1440_label = (
                    total_format % ("red", source_1440)
                    if source_1440 == 0
                    else total_format % ("lime", source_1440)
                )
                source_1080_label = (
                    total_format % ("red", source_1080)
                    if source_1080 == 0
                    else total_format % ("lime", source_1080)
                )
                source_720_label = (
                    total_format % ("red", source_720)
                    if source_720 == 0
                    else total_format % ("lime", source_720)
                )
                source_sd_label = (
                    total_format % ("red", source_sd)
                    if source_sd == 0
                    else total_format % ("lime", source_sd)
                )
                source_total_label = (
                    total_format % ("red", total)
                    if total == 0
                    else total_format % ("lime", total)
                )

                if (i / 2) < timeout:
                    try:
                        mainleft = [
                            sourcelabelDict[x.getName()]
                            for x in threads
                            if x.is_alive() and x.getName() in mainsourceDict
                        ]
                        info = [
                            sourcelabelDict[x.getName()]
                            for x in threads
                            if x.is_alive()
                        ]
                        """ # nie pamiętam po co to
                        if (
                                # i >= timeout
                                and len(mainleft) == 0
                                and len(self.sources) >= 100 * len(info)
                        ):
                            break  # improve responsiveness
                        """
                        if debrid_status:
                            if quality in ["0"]:
                                if not progressDialog == control.progressDialogBG:
                                    line1 = ("%s:" + "|".join(pdiag_format)) % (
                                        string6,
                                        d_4k_label,
                                        d_1080_label,
                                        d_720_label,
                                        d_sd_label,
                                        str(string4),
                                        d_total_label,
                                    )
                                    line2 = ("%s:" + "|".join(pdiag_format)) % (
                                        string7,
                                        source_4k_label,
                                        source_1080_label,
                                        source_720_label,
                                        source_sd_label,
                                        str(string4),
                                        source_total_label,
                                    )
                                    print(line1, line2)
                                else:
                                    line1 = "|".join(pdiag_bg_format[:-1]) % (
                                        source_4k_label,
                                        d_4k_label,
                                        source_1080_label,
                                        d_1080_label,
                                        source_720_label,
                                        d_720_label,
                                        source_sd_label,
                                        d_sd_label,
                                    )
                            elif quality in ["1"]:
                                if not progressDialog == control.progressDialogBG:
                                    line1 = ("%s:" + "|".join(pdiag_format[1:])) % (
                                        string6,
                                        d_1080_label,
                                        d_720_label,
                                        d_sd_label,
                                        str(string4),
                                        d_total_label,
                                    )
                                    line2 = ("%s:" + "|".join(pdiag_format[1:])) % (
                                        string7,
                                        source_1080_label,
                                        source_720_label,
                                        source_sd_label,
                                        str(string4),
                                        source_total_label,
                                    )
                                else:
                                    line1 = "|".join(pdiag_bg_format[1:]) % (
                                        source_1080_label,
                                        d_1080_label,
                                        source_720_label,
                                        d_720_label,
                                        source_sd_label,
                                        d_sd_label,
                                        source_total_label,
                                        d_total_label,
                                    )
                            elif quality in ["2"]:
                                if not progressDialog == control.progressDialogBG:
                                    line1 = ("%s:" + "|".join(pdiag_format[1:])) % (
                                        string6,
                                        d_1080_label,
                                        d_720_label,
                                        d_sd_label,
                                        str(string4),
                                        d_total_label,
                                    )
                                    line2 = ("%s:" + "|".join(pdiag_format[1:])) % (
                                        string7,
                                        source_1080_label,
                                        source_720_label,
                                        source_sd_label,
                                        str(string4),
                                        source_total_label,
                                    )
                                else:
                                    line1 = "|".join(pdiag_bg_format[1:]) % (
                                        source_1080_label,
                                        d_1080_label,
                                        source_720_label,
                                        d_720_label,
                                        source_sd_label,
                                        d_sd_label,
                                        source_total_label,
                                        d_total_label,
                                    )
                            elif quality in ["3"]:
                                if not progressDialog == control.progressDialogBG:
                                    line1 = ("%s:" + "|".join(pdiag_format[2:])) % (
                                        string6,
                                        d_720_label,
                                        d_sd_label,
                                        str(string4),
                                        d_total_label,
                                    )
                                    line2 = ("%s:" + "|".join(pdiag_format[2:])) % (
                                        string7,
                                        source_720_label,
                                        source_sd_label,
                                        str(string4),
                                        source_total_label,
                                    )
                                else:
                                    line1 = "|".join(pdiag_bg_format[2:]) % (
                                        source_720_label,
                                        d_720_label,
                                        source_sd_label,
                                        d_sd_label,
                                        source_total_label,
                                        d_total_label,
                                    )
                            else:
                                if not progressDialog == control.progressDialogBG:
                                    line1 = ("%s:" + "|".join(pdiag_format[3:])) % (
                                        string6,
                                        d_sd_label,
                                        str(string4),
                                        d_total_label,
                                    )
                                    line2 = ("%s:" + "|".join(pdiag_format[3:])) % (
                                        string7,
                                        source_sd_label,
                                        str(string4),
                                        source_total_label,
                                    )
                                else:
                                    line1 = "|".join(pdiag_bg_format[3:]) % (
                                        source_sd_label,
                                        d_sd_label,
                                        source_total_label,
                                        d_total_label,
                                    )
                        else:
                            #if quality in ["0"]:
                            if True:
                                line1 = "|".join(pdiag_format[qmax:qmin+1]) % (
                                    source_4k_label,
                                    source_1440_label,
                                    source_1080_label,
                                    source_720_label,
                                    source_sd_label,
                                    #str(string4),
                                    #source_total_label,
                                )[qmax:qmin+1]
                            """
                            elif quality in ["1"]:
                                line1 = "|".join(pdiag_format[1:]) % (
                                    source_1080_label,
                                    source_720_label,
                                    source_sd_label,
                                    str(string4),
                                    source_total_label,
                                )
                            elif quality in ["2"]:
                                line1 = "|".join(pdiag_format[1:]) % (
                                    source_1080_label,
                                    source_720_label,
                                    source_sd_label,
                                    str(string4),
                                    source_total_label,
                                )
                            elif quality in ["3"]:
                                line1 = "|".join(pdiag_format[2:]) % (
                                    source_720_label,
                                    source_sd_label,
                                    str(string4),
                                    source_total_label,
                                )
                            else:
                                line1 = "|".join(pdiag_format[3:]) % (
                                    source_sd_label,
                                    str(string4),
                                    source_total_label,
                                )
                            """
                            if pre_emp:
                                line1 += "\n" + (pdiag_tot_format) % ( str(string4), source_total_label)  # TOTAL

                        if debrid_status:
                            if len(info) > 6:
                                line3 = string3 % (str(len(info)))
                            elif len(info) > 0:
                                line3 = string3 % (", ".join(info))
                            else:
                                break
                            percent = int(100 * float(i) / (2 * timeout) + 0.5)
                            if not progressDialog == control.progressDialogBG:
                                _sd_update(max(1, percent)) if _search_dialog_active else progressDialog.update(max(1, percent), info_static)
                            else:
                                _sd_update(max(1, percent)) if _search_dialog_active else progressDialog.update(max(1, percent), info_static)
                        else:
                            if len(info) > 16:
                                line2 = string3 % (str(len(info)))
                            elif len(info) > 0:
                                line2 = string3 % (", ".join(info))
                            else:
                                #break
                                line2 = ""
                            percent = int(100 * float(i) / (2 * timeout) + 0.5)
                            _sd_update(max(1, percent)) if _search_dialog_active else progressDialog.update(max(1, percent), info_static)
                            if len(info) == 0:
                                break
                    except Exception as e:
                        print("Exception Raised: %s" % str(e), log_utils.LOGERROR)
                        log("Exception Raised: %s" % str(e), log_utils.LOGERROR)
                else:
                    log(f'[getSources] przerwanie wyszukiwania - przekroczenie ustalonego czasu ({int(i/2)} s.)')
                    try:
                        mainleft = [
                            sourcelabelDict[x.getName()]
                            for x in threads
                            if x.is_alive() and x.getName() in mainsourceDict
                        ]
                        info = mainleft
                        if debrid_status:
                            if len(info) > 6:
                                line3 = "Waiting for: %s" % (str(len(info)))
                            elif len(info) > 0:
                                line3 = "Waiting for: %s" % (", ".join(info))
                            else:
                                break
                            percent = int(100 * float(i) / (2 * timeout) + 0.5)
                            if not progressDialog == control.progressDialogBG:
                                _sd_update(max(1, percent)) if _search_dialog_active else progressDialog.update(max(1, percent), info_static)
                            else:
                                _sd_update(max(1, percent)) if _search_dialog_active else progressDialog.update(max(1, percent), info_static)
                        else:
                            if len(info) > 6:
                                line2 = "Waiting for: %s" % (str(len(info)))
                            elif len(info) > 0:
                                line2 = "Waiting for: %s" % (", ".join(info))
                            else:
                                #break
                                line2 = 'Przerwanie wyszukiwania - przekroczenie czasu'
                            percent = int(100 * float(i) / (2 * timeout) + 0.5)
                            _sd_update(max(1, percent)) if _search_dialog_active else progressDialog.update(max(1, percent), info_static)
                            if len(info) == 0:
                                break
                    except Exception:
                        break

                time.sleep(0.5)  # potrzebne dla pętli for, aby prawidłowo odliczać czas

            except Exception:
                pass

        if line2:
        # if True:
            fflog(f'sygnał przerwania dalszej pracy scraperów')
            control.window.setProperty("blocked_sources_extend", "break")
            control.sleep(1000)

        # próba odzyskania choć części wyników dla wybranych serwisów, gdy minie czas
        # if int(i / 2) >= timeout  or  int(i / 2) > 10:
        if line2 and int(i / 2) > 20:
            # fflog(f'{s=}')
            ii = [s for s in sourceDict if s[0] in ['tb7', 'xt7'] and s[2]]  # s[2] to sprawdzenie, czy scraper włączony chyba
            # fflog(f'{len(ii)=} {ii=}')
            for i in ii:
                if not any(s for s in self.sources if s["provider"]==i[0]):  # sprawdzenie, czy nie ma w wynikach już jakiś źródeł od tb7 czy xt7
                    fflog(f'próba ewentualnego odzyskania wyników dla {i[0]}')
                    #xbmcgui.Dialog().notification('FanVodPL', (f'Próba ewentualnego odzyskania wyników dla {i[0]}'), xbmcgui.NOTIFICATION_INFO, 1500, sound=False)
                    if content == "movie":
                        self.getMovieSource(title, localtitle, aliases, year, imdb, i[0], i[1], True)
                    else:
                        self.getEpisodeSource(title, year, imdb, tvdb, season, episode, tvshowtitle, localtvshowtitle, aliases, premiered, i[0], i[1], True)
                    # log(f'[getSources] zakończono ratunkowy odczyt źródeł dla {i[0]}')
                    #if xbmc.getCondVisibility('Window.IsActive(notification)'):
                        #xbmc.executebuiltin('Dialog.Close(notification,true)')
                        #pass

        self.blocked_sources_extend = True

        if sort is None or sort:
            # self.sources = self.sortSources(self.sources)  # jakbym chciał, aby najpierw była biblioteka a potem pobrane
            self.sourcesFilter(year=year, premiered=premiered, duration=duration, episode=episode, tvshowtitle=tvshowtitle)  # filtrowanie wg różnych kryteriów

        if line2:
            control.sleep(1000-800)
        else:
            control.sleep(250)

        try:
            progressDialog.close()
            if _search_dialog_active:
                del searchDialog
            control.sleep0(100)
        except Exception:
            pass

        control.window.clearProperty('clear_SourceCache_for')

        if not self.sources:
            try:
                control.infoDialog(control.lang(32401), icon="ERROR", sound=False)
            except Exception:
                pass

        return self.sources


    def prepareSources(self):
        control.window.setProperty(self.itemRejected, json.dumps([]))
        try:
            control.makeFile(control.dataPath)

            if control.setting("enableSourceCache") == "true":
                self.sourceFile = control.providercacheFile

                dbcon = database.connect(self.sourceFile)
                dbcur = dbcon.cursor()
                dbcur.execute(
                    "CREATE TABLE IF NOT EXISTS rel_url ("
                    "source TEXT, "
                    "imdb_id TEXT, "
                    "season TEXT, "
                    "episode TEXT, "
                    "rel_url TEXT, "
                    "UNIQUE(source, imdb_id, season, episode)"
                    ");"
                )
                dbcur.execute(
                    "CREATE TABLE IF NOT EXISTS rel_src ("
                    "source TEXT, "
                    "imdb_id TEXT, "
                    "season TEXT, "
                    "episode TEXT, "
                    "hosts TEXT, "
                    "added TEXT, "
                    "UNIQUE(source, imdb_id, season, episode)"
                    ");"
                )

        except Exception:
            pass
        finally:
            if "dbcon" in locals():
                dbcon.close()


    def getMovieSource(self, title, localtitle, aliases, year, imdb, source, call, from_cache=False, **kwargs):
        try:
            dbcon = database.connect(self.sourceFile)
            dbcur = dbcon.cursor()
        except Exception:
            pass

        cSCf = ""
        # jak ktoś używa cache źródeł, to aby dla plików "wypożyczonych" na innych urządzeniach zawsze sprawdzał
        cSCf = control.window.getProperty('clear_SourceCache_for') + ',tb7,xt7,rapideo,nopremium,twojlimit,pobrane'  # string
        # cSCf += 'library,biblioteka'
        cSCf = cSCf.strip(',').split(',')  # na listę
        # cSCf = list(filter(None, cSCf))  # usunięcie pustych
        cSCf = set(cSCf)
        cSCf = ",".join(cSCf).strip(',')  # na string
        control.window.setProperty('clear_SourceCache_for', cSCf)  # do pamięci
        # chyba, ża dać jakiś krótki czas, np. tylko 5 minut (lub mniej, np. 1-2 minuty)

        """ Fix to stop items passed with a 0 IMDB id pulling old unrelated sources from the database. """
        # if not cSCf:  # czy jest sens pobierać, jak przed chwilą ta zmienna była na tacy?
        if 0:
            cSCf = control.window.getProperty('clear_SourceCache_for')  # string
            fflog(f'{cSCf=}',0,1)
        cSCf = cSCf.strip(',').split(',')  # na listę
        if imdb == "0" or source in cSCf or "all" in cSCf:
            # wyczyszczenie cache dla danego źródła
            fflog(f'wyczyszczenie cache dla {source=} {imdb=}',0,1)
            try:
                dbcur.execute(
                    "DELETE FROM rel_src WHERE source = '%s' AND imdb_id = '%s' AND season = '%s' AND episode = '%s'"
                    % (source, imdb, "", "")
                )
                dbcur.execute(
                    "DELETE FROM rel_url WHERE source = '%s' AND imdb_id = '%s' AND season = '%s' AND episode = '%s'"
                    % (source, imdb, "", "")
                )
                dbcon.commit()
                control.sleep(10)
            except Exception:
                # fflog_exc(1)
                pass
        """ END """

        sources = []
        update = True
        try:
            dbcur.execute(
                "SELECT * FROM rel_src WHERE source = '%s' AND imdb_id = '%s' AND season = '%s' AND episode = '%s'"
                % (source, imdb, "", "")
            )
            match = dbcur.fetchone()
            t1 = int(re.sub("[^0-9]", "", str(match[5])))
            t2 = int(datetime.datetime.now().strftime("%Y%m%d%H%M"))
            t1 = datetime.datetime.strptime(str(t1), "%Y%m%d%H%M").timestamp()
            t2 = datetime.datetime.strptime(str(t2), "%Y%m%d%H%M").timestamp()
            fflog(f'delta t: {int((t2-t1)/60)=} min',0,1)  # w minutach, jak dawno temu
            cache_timeout = int(control.setting("SourceCache_timeout"))  # w minutach
            fflog(f'{cache_timeout=} min',0,1)
            # expire_time = 30 if source not in ['tb7','xt7','rapideo','nopremium','twojlimit'] else 5  # albo mniej jeszcze
            update = int((t2-t1)/60) > cache_timeout
            fflog(f'{update=}',0,1)
            if not update:
                fflog(f'próba pobrania źródeł z cache  {source=}',1,1)
                sources = eval(match[4].encode("utf-8"))
                if sources:
                    dbcon.close()
                    if not self.blocked_sources_extend:
                        self.sources.extend(sources)
                    else:
                        fflog(f'{self.blocked_sources_extend=}',1,1)
                        pass
                    return  # przerwanie dalszej części tej funkcji
                else:
                    fflog(f'brak źródeł w cache  {source=}',1,1)
                    pass
            else:
                fflog(f'przeterminowany cache źródeł {source=}',1,1)
                pass
        except Exception:
            pass

        url = None
        try:
            # if not update:  # tylko, że jak cache jest ok, to tu może nie dochodzić (chyba, że dane są uszkodzone, ale to żadki przypadek będzie, jeśli będzie)
            if True:  # a może zawsze to sprawdzać? tylko wówczas to trochę oszukańcze, aczkolwiek, to i tak jest odświeżane po wyszukaniu źródeł, także chyba może być
                fflog(f'próba pobrania wcześniej znalezionych już pozycji (tytułów) do szukania ich źródeł z cache  {source=}',0,1)
                dbcur.execute(
                    "SELECT * FROM rel_url WHERE source = '%s' AND imdb_id = '%s' AND season = '%s' AND episode = '%s'"
                    % (source, imdb, "", "")
                )
                url = dbcur.fetchone()
                url = eval(url[4].encode("utf-8"))
        except Exception:
            fflog(f'nie udało się pobrać wcześniej znalezionych już pozycji  {source=}',0,1)
            pass

        try:
            if not url and not from_cache:
                if source in ["shinden", "external", "tb7", "xt7", "rapideo", "nopremium", "twojlimit", "filman", "filman_api", "pobrane", "ekinotv"]:
                    # fflog(f'{source=} {kwargs=}',1,1)
                    url = call.movie(imdb, title, localtitle, aliases, year, **kwargs)
                else:
                    url = call.movie(imdb, title, localtitle, aliases, year)
            # ===== [SAFE SEARCH RETRY] =====
            # 1 szybki retry gdy provider chwilowo nie zwróci URL (czasem timeout / ratelimit).
            if not url and not from_cache:
                try:
                    control.sleep(250)
                except Exception:
                    pass
                try:
                    if source in ["shinden", "external", "tb7", "xt7", "rapideo", "nopremium", "twojlimit", "filman", "filman_api", "pobrane", "ekinotv"]:
                        url = call.movie(imdb, title, localtitle, aliases, year, **kwargs)
                    else:
                        url = call.movie(imdb, title, localtitle, aliases, year)
                    if url:
                        fflog(f"SAFE_RETRY ok: {source} movie()", 0, 1)
                except Exception:
                    pass

            if not url and from_cache:
                results_cache = cache.cache_get(f'{source}_results')
                if results_cache and results_cache['value']:  # może w ogóle nie być
                    results_cache = literal_eval(results_cache['value'])
                    if results_cache:  # może być pusty
                        url = [results_cache[k] for k in results_cache][0]
                        fflog(f'dla {source} odczytano z cache rekordów: {len(url)}',1,1)
        except Exception as e:
            #if str(e):
                #fflog(f'Error: {e}',1,1)
            log_exception(1)

        try:
            if not url:
                raise Exception()
            dbcur.execute(
                "DELETE FROM rel_url WHERE source = '%s' AND imdb_id = '%s' AND season = '%s' AND episode = '%s'"
                % (source, imdb, "", "")
            )
            dbcur.execute(
                "INSERT INTO rel_url Values (?, ?, ?, ?, ?)",
                (source, imdb, "", "", repr(url)),
            )
            dbcon.commit()
        except Exception:
            pass

        sources = []
        try:
            if from_cache:
                sources = call.sources(url, self.hostDict, self.hostprDict, from_cache=from_cache)
            else:
                sources = call.sources(url, self.hostDict, self.hostprDict)
        except Exception:
            log_exception(1)
            sources = []

        # ===== [SAFE SEARCH RETRY] =====
        if not sources and not from_cache:
            try:
                control.sleep(350)
            except Exception:
                pass
            try:
                sources = call.sources(url, self.hostDict, self.hostprDict)
                if sources:
                    fflog(f"SAFE_RETRY ok: {source} sources()", 0, 1)
            except Exception:
                pass

        try:
            if not sources:
                raise Exception()

            # sources = [json.loads(t) for t in set(json.dumps(d, sort_keys=True) for d in sources)]  # miesza pierwotną kolejność

            for i in sources:
                provider = i.get("provider") or ""
                if provider:
                    if provider[0] == " ":
                        provider = source + provider
                else:
                    provider = source
                i.update({"provider": provider})
            if not self.blocked_sources_extend:
                self.sources.extend(sources)
            else:
                fflog(f'{self.blocked_sources_extend=}',1,1)
                pass

            dbcur.execute(
                "DELETE FROM rel_src WHERE source = '%s' AND imdb_id = '%s' AND season = '%s' AND episode = '%s'"
                % (source, imdb, "", "")
            )
            dbcur.execute(
                "INSERT INTO rel_src Values (?, ?, ?, ?, ?, ?)",
                (
                    source,
                    imdb,
                    "",
                    "",
                    repr(sources),
                    datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                ),
            )
            dbcon.commit()
        except Exception:
            pass

        if "dbcon" in locals():
            dbcon.close()


    def getEpisodeSource(
            self,
            title,
            year,
            imdb,
            tvdb,
            season,
            episode,
            tvshowtitle,
            localtvshowtitle,
            aliases,
            premiered,
            source,
            call,
            from_cache=False,
            **kwargs
    ):
        try:
            dbcon = database.connect(self.sourceFile)
            dbcur = dbcon.cursor()
        except Exception:
            # fflog_exc(1)
            pass

        cSCf = ""
        # jak ktoś używa cache źródeł, to aby dla plików "wypożyczonych" na innych urządzeniach zawsze sprawdzał
        cSCf = control.window.getProperty('clear_SourceCache_for') + ',tb7,xt7,rapideo,nopremium,twojlimit,pobrane'  # string
        # cSCf += 'library,biblioteka'
        cSCf = cSCf.strip(',').split(',')  # na listę
        # fflog(f'{cSCf=}',1,1)
        # cSCf = list(filter(None, cSCf))  # usunięcie pustych
        cSCf = set(cSCf)  # to samo co wyżej
        # fflog(f'{cSCf=}',1,1)
        cSCf = ",".join(cSCf).strip(',')  # na string
        # fflog(f'{cSCf=}',1,1)
        control.window.setProperty('clear_SourceCache_for', cSCf)  # do pamięci
        # chyba, ża dać jakiś krótki czas, np. tylko 5 minut (lub mniej, np. 1-2 minuty)

        """ Clear if needed """
        # if not cSCf:  # czy jest sens pobierać, jak przed chwilą ta zmienna była na tacy?
        if 0:
            cSCf = control.window.getProperty('clear_SourceCache_for')  # string
            fflog(f'{cSCf=}',0,1)
        cSCf = cSCf.strip(',').split(',')  # na listę
        if source in cSCf or "all" in cSCf:
            try:
                # fflog(f'wyczyszczenie cache dla {source=} {imdb=}',1,1)
                # dbcur.execute(
                    # "DELETE FROM rel_src WHERE source = '%s' AND imdb_id = '%s' AND season = '%s' AND episode = '%s'"
                    # % (source, imdb, "", "")
                # )
                # dbcur.execute(
                    # "DELETE FROM rel_url WHERE source = '%s' AND imdb_id = '%s' AND season = '%s' AND episode = '%s'"
                    # % (source, imdb, "", "")
                # )

                fflog(f'wyczyszczenie cache dla {source=} {imdb=} {season=} {episode=}',0,1)
                dbcur.execute(
                    "DELETE FROM rel_src WHERE source = '%s' AND imdb_id = '%s' AND season = '%s' AND episode = '%s'"
                    % (source, imdb, season, episode)
                )
                dbcur.execute(
                    "DELETE FROM rel_url WHERE source = '%s' AND imdb_id = '%s' AND season = '%s' AND episode = '%s'"
                    % (source, imdb, season, episode)
                )
                dbcon.commit()
                control.sleep(10)
            except Exception:
                # fflog_exc(1)
                pass

        sources = []
        update = True
        try:
            dbcur.execute(
                "SELECT * FROM rel_src WHERE source = '%s' AND imdb_id = '%s' AND season = '%s' AND episode = '%s'"
                % (source, imdb, season, episode)
            )
            match = dbcur.fetchone()
            # fflog(f'{match=}  |  {source=}',1,1)
            t1 = int(re.sub("[^0-9]", "", str(match[5])))
            t2 = int(datetime.datetime.now().strftime("%Y%m%d%H%M"))
            t1 = datetime.datetime.strptime(str(t1), "%Y%m%d%H%M").timestamp()
            t2 = datetime.datetime.strptime(str(t2), "%Y%m%d%H%M").timestamp()
            cache_timeout = int(control.setting("SourceCache_timeout"))
            # fflog(f'{cache_timeout=}',1,1)
            # expire_time = 30 if source not in ['tb7','xt7','rapideo','nopremium','twojlimit'] else 5  # albo mniej jeszcze
            update = int((t2-t1)/60) > cache_timeout
            if not update:
                fflog(f'próba pobrania źródeł z cache  {source=}',1,1)
                sources = eval(match[4].encode("utf-8"))
                if sources:
                    dbcon.close()
                    if not self.blocked_sources_extend:
                        self.sources.extend(sources)
                    else:
                        fflog(f'{self.blocked_sources_extend=}',1,1)
                        pass
                    return
                else:
                    fflog(f'brak źródeł w cache  {source=}',1,1)
                    pass
            else:
                fflog(f'przeterminowany cache źródeł {source=}',1,1)
                pass
        except Exception:
            # fflog_exc(1)
            pass

        url = None
        try:
            # if not update:
            if True:
                fflog(f'próba pobrania wcześniej znalezionych już pozycji (tytułów) do szukania ich źródeł z cache  {source=}',0,1)
                dbcur.execute(
                    "SELECT * FROM rel_url WHERE source = '%s' AND imdb_id = '%s' AND season = '%s' AND episode = '%s'"
                    % (source, imdb, "", "")
                )
                url = dbcur.fetchone()
                url = eval(url[4].encode("utf-8"))
        except Exception:
            # fflog_exc(1)
            fflog(f'nie udało się pobrać wcześniej znalezionych już pozycji  {source=}',0,1)
            pass

        try:
            if not url:
                if source in ["shinden", "external"]:
                    url = call.tvshow(imdb, tvdb, tvshowtitle, localtvshowtitle, aliases, year, **kwargs)
                else:
                    url = call.tvshow(imdb, tvdb, tvshowtitle, localtvshowtitle, aliases, year)
            # ===== [SAFE SEARCH RETRY] =====
            if not url:
                try:
                    control.sleep(250)
                except Exception:
                    pass
                try:
                    if source in ["shinden", "external"]:
                        url = call.tvshow(imdb, tvdb, tvshowtitle, localtvshowtitle, aliases, year, **kwargs)
                    else:
                        url = call.tvshow(imdb, tvdb, tvshowtitle, localtvshowtitle, aliases, year)
                    if url:
                        fflog(f"SAFE_RETRY ok: {source} tvshow()", 0, 1)
                except Exception:
                    pass

        except Exception:
            fflog_exc(1)
            pass

        try:
            if not url:
                raise Exception()
            dbcur.execute(
                "DELETE FROM rel_url WHERE source = '%s' AND imdb_id = '%s' AND season = '%s' AND episode = '%s'"
                % (source, imdb, "", "")
            )
            dbcur.execute(
                "INSERT INTO rel_url Values (?, ?, ?, ?, ?)",
                (source, imdb, "", "", repr(url)),
            )
            dbcon.commit()
        except Exception:
            # fflog_exc(1)
            pass

        ep_url = None
        # ep_url = url  # nie prościej? jeszcze tylko muszę sprawdzić
        try:
            if not ep_url:
                dbcur.execute(
                    "SELECT * FROM rel_url WHERE source = '%s' AND imdb_id = '%s' AND season = '%s' AND episode = '%s'"
                    % (source, imdb, season, episode)
                )
                ep_url = dbcur.fetchone()
                ep_url = eval(ep_url[4].encode("utf-8"))
        except Exception:
            # fflog_exc(1)
            pass

        try:
            if not ep_url and not from_cache and url:
                if source in ["shinden", "external"]:
                    season_s = "" if season is None else str(season)
                    episode_s = "" if episode is None else str(episode)
                    ep_url = call.episode(url, imdb, tvdb, title, premiered, season_s, episode_s, **kwargs)
                else:
                    season_s = "" if season is None else str(season)
                    episode_s = "" if episode is None else str(episode)
                    ep_url = call.episode(url, imdb, tvdb, title, premiered, season_s, episode_s)
            # ===== [SAFE SEARCH RETRY] =====
            if not ep_url:
                try:
                    control.sleep(250)
                except Exception:
                    pass
                try:
                    season_s = "" if season is None else str(season)
                    episode_s = "" if episode is None else str(episode)
                    if source in ["shinden", "external"]:
                        ep_url = call.episode(url, imdb, tvdb, title, premiered, season_s, episode_s, **kwargs)
                    else:
                        ep_url = call.episode(url, imdb, tvdb, title, premiered, season_s, episode_s)
                    if ep_url:
                        fflog(f"SAFE_RETRY ok: {source} episode()", 0, 1)
                except Exception:
                    pass

            if not ep_url and from_cache:
                results_cache = cache.cache_get(f'{source}_results')
                if results_cache and results_cache['value']:  # może w ogóle nie być
                    results_cache = literal_eval(results_cache['value'])
                    if results_cache:  # może być pusty
                        ep_url = [results_cache[k] for k in results_cache][0]
                        fflog(f'dla {source} odczytano z cache rekordów: {len(ep_url)}')
        except Exception:
            # log_exception(1)
            fflog_exc(1)
            pass

        try:
            if not ep_url:
                raise Exception()
            dbcur.execute(
                "DELETE FROM rel_url WHERE source = '%s' AND imdb_id = '%s' AND season = '%s' AND episode = '%s'"
                % (source, imdb, season, episode)
            )
            dbcur.execute(
                "INSERT INTO rel_url Values (?, ?, ?, ?, ?)",
                (source, imdb, season, episode, repr(ep_url)),
            )
            dbcon.commit()
        except Exception:
            # fflog_exc(1)
            pass

        sources = []
        try:
            if from_cache:
                sources = call.sources(ep_url, self.hostDict, self.hostprDict, from_cache=from_cache)
            else:
                sources = call.sources(ep_url, self.hostDict, self.hostprDict)
        except Exception:
            try:
                fflog_exc(1)
            except Exception:
                pass
            sources = []

        # ===== [SAFE SEARCH RETRY] =====
        if not sources and not from_cache:
            try:
                control.sleep(350)
            except Exception:
                pass
            try:
                sources = call.sources(ep_url, self.hostDict, self.hostprDict)
                if sources:
                    fflog(f"SAFE_RETRY ok: {source} sources()", 0, 1)
            except Exception:
                pass

        try:
            if not sources:
                raise Exception()
            # fflog(f'{len(sources)=} sources={json.dumps(sources, indent=2)}',1,1)
            # sources = [json.loads(t) for t in set(json.dumps(d, sort_keys=True) for d in sources)]  # miesza pierwotną kolejność
            # fflog(f'{len(sources)=} sources={json.dumps(sources, indent=2)}',1,1)
            for i in sources:
                provider = i.get("provider") or ""
                if provider:
                    if provider[0] == " ":
                        provider = source + provider
                else:
                    provider = source
                i.update({"provider": provider})
            if not self.blocked_sources_extend:
                self.sources.extend(sources)
            else:
                fflog(f'{self.blocked_sources_extend=}')
                pass

            dbcur.execute(
                "DELETE FROM rel_src WHERE source = '%s' AND imdb_id = '%s' AND season = '%s' AND episode = '%s'"
                % (source, imdb, season, episode)
            )
            dbcur.execute(
                "INSERT INTO rel_src Values (?, ?, ?, ?, ?, ?)",
                (
                    source,
                    imdb,
                    season,
                    episode,
                    repr(sources),
                    datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                ),
            )
            dbcon.commit()
        except Exception:
            # fflog_exc(1)
            pass

        if "dbcon" in locals():
            dbcon.close()


    def alterSources(self, url, meta=None):
        try:
            # log(f"{url=!r}")
            # log(f"{meta=!r}")
            # log(f"{sys.argv=!r}")

            if isinstance(url, str):
                url = url.split("?")
                q = dict(parse_qsl(url[-1]))
                # log(f"{q=!r}")
            else:
                q = url

            # aby nie pojawiały się drugi raz pytania
            # poprzedni url
            folderpath = control.infoLabel('Container.FolderPath')
            params1 = dict(parse_qsl(folderpath.split('?')[-1]))
            action1 = params1.get('action')
            # bieżący url
            params2 = dict(parse_qsl(sys.argv[2][1:]))
            action2 = params2.get('action')
            # jak polecenia były te same, to traktujemy to jako odświeżenie widoku
            referer = folderpath if action1 != action2 else ''
            fflog(f"{referer=} , bo {folderpath=} {action1=} {action2=}", 0)
            if not referer:  # odświeżenie
                # q.pop('customTitles', '')
                q.update({"customTitles": 0})
                pass

            if "customTitles" in q and q["customTitles"]:
                if (p := q.get('tvshowtitle')) and p != "None":
                    # seriale
                    if (s := xbmcgui.Dialog().input("Główny tytuł serialu [CR][LIGHT](anglojęzyczny lub oryginalny)[/LIGHT]", p)):
                        q.update({"tvshowtitle": s})
                    else:
                        return sys.exit()

                    if (p := q.get('season')) and p != "None":
                        while True:
                            s = xbmcgui.Dialog().input("Numer sezonu \n(maks 2 cyfry)", "", type=xbmcgui.INPUT_NUMERIC)
                            if s == "0" or s == "00":
                                s = "1"
                                break
                            if not s or re.match(r"^[\d]{1,2}$", s):
                                break
                            if not xbmcgui.Dialog().yesno('Niepoprawna wartość', (f"Wartość [B]{s}[/B] jest nieprawidłowa. \nCzy chcesz poprawić?")):
                                s = ''
                                break
                        if s:
                            q.update({"season": s})

                    if (p := q.get('episode')) and p != "None":
                        while True:
                            s = xbmcgui.Dialog().input("Numer odcinka \n(maks. 4 cyfry)", "", type=xbmcgui.INPUT_NUMERIC)
                            if s == "0" or s == "00" or s == "000" or s == "0000":
                                s = "1"
                                break
                            if not s or re.match(r"^[\d]{1,4}$", s):
                                break
                            if not xbmcgui.Dialog().yesno('Niepoprawna wartość', (f"Wartość [B]{s}[/B] jest nieprawidłowa. \nCzy chcesz poprawić?")):
                                s = ''
                                break
                        if s:
                            q.update({"episode": s})

                    if (p := q.get('year')) and p != "None":
                        while True:
                            s = xbmcgui.Dialog().input("Rok premiery", p, type=xbmcgui.INPUT_NUMERIC)
                            if not s or re.match(r"^(19|20)[\d]{2,2}$", s):
                                break
                            if not xbmcgui.Dialog().yesno('Niepoprawna wartość', (f"Wpisana wartość [B]{s}[/B] jest nieprawidłowa. \nCzy chcesz poprawić? \n[COLOR gray]dozwolony zakres to [1900-2099][/COLOR]")):
                                s = ''
                                break
                        if s:
                            q.update({"year": s})
                            q.update({"premiered": ""})  # bo źródła premium mogą odrzucić jak w nazwie będzie rok kolejnego sezonu inny niż rok premiery

                    xbmcgui.Dialog().notification(f"s{q.get('season').zfill(2)}e{q.get('episode').zfill(2)}", (f"{q.get('tvshowtitle')} ({q.get('year')})"))
                else:
                    # filmy
                    if (p := q.get('title')) and p != "None":
                        if (s := xbmcgui.Dialog().input("Główny tytuł [CR][LIGHT](anglojęzyczny lub oryginalny)[/LIGHT]", p)):
                            q.update({"title": s})
                        else:
                            return sys.exit()

                    if (p := q.get('localtitle')) and p != "None":
                        if (s := xbmcgui.Dialog().input("polskie tłumaczenie tytułu", p)):
                            q.update({"localtitle": s})

                    if (p := q.get('year')) and p != "None":
                        while True:
                            s = xbmcgui.Dialog().input("Rok premiery", p, type=xbmcgui.INPUT_NUMERIC)
                            if not s or re.match(r"^(19|20)[\d]{2,2}$", s):
                                break
                            if not xbmcgui.Dialog().yesno('Niepoprawna wartość', (f"Wpisana wartość [B]{s}[/B] jest nieprawidłowa. \nCzy chcesz poprawić? \n[COLOR gray]dozwolony zakres to [1900-2099][/COLOR]")):
                                s = ''
                                break
                        if s:
                            q.update({"year": s})

                    xbmcgui.Dialog().notification(f"{q.get('year')}", (f"{q.get('title')} \n{q.get('localtitle')}"))

            elif "customTitles" in q and not q["customTitles"]:  # np. gdy nie zadawał pytań
                q.update({"select": "1"})
                pass

            else:
                if control.setting("hosts.mode") == "2":  # autoplay
                    #url += "&select=1"  # directory
                    # q.update({"select": "1"})  # directory (to coś źle działa, bo chyba nie można wyświetlać katalogu, gdy element był ustawiony na IsPlayable, a tak jest ustawiane dla autoplay)
                    q.update({"select": "0"})  # dialog select
                    #url += "&select=0"  # dialog select
                else:
                    #url += "&select=2"
                    q.update({"select": "2"})  # autoplay

            q.pop('action', None)  # musi być ewentualnie "play"

            #self.play(**q)  # ale może niektórych zmiennych brakować
            #return

            """
            xbmcgui.Dialog().notification('', (f'czekaj ...'))
            url = url[0] + "?" + urlencode(q)
            control.execute("RunPlugin(%s)" % url + "&handle="+meta)  # gubi "handle"
            control.execute("Container.Update(%s)" % url)  # czemuś nie działa - nie wyszukuje źródeł
            control.directory(addon_handle, cacheToDisc=True)  # może tego brakowało? sprawdzić
            return
            """

            title = q.get('title')
            localtitle = q.get('localtitle')
            year = q.get('year')
            imdb = q.get('imdb')
            tvdb = q.get('tvdb')
            tmdb = q.get('tmdb')
            season = q.get('season')
            episode = q.get('episode')
            tvshowtitle = q.get('tvshowtitle')
            premiered = q.get('premiered')
            meta = q.get('meta') if meta is None else meta
            select = q.get('select')
            customTitles = q.get('customTitles', '')  # aby nie zadawał pytań ponownie
            originalname = q.get("originalname", "")
            epimdb = q.get("epimdb", "")
            # log(f'{title=!r} \n{localtitle=!r} \n{year=!r} \n{imdb=!r} \n{tvdb=!r} \n{tmdb=!r} \n{season=!r} \n{episode=!r} \n{tvshowtitle=!r} \n{premiered=!r} \n{meta=!r} \n{select=!r} ')
            if control.setting("generate_short_path") == "true":
                zmienne = { "title":title, "localtitle":localtitle, "year":year, "imdb":imdb, "tvdb":tvdb, "tmdb":tmdb,
                            "season":season, "episode":episode, "tvshowtitle":tvshowtitle, "premiered":premiered,
                            "meta":meta, "select":select,
                            "originalname":originalname, "epimdb":epimdb,
                            "customTitles":customTitles,
                            }
                control.window.setProperty('FanVodPL.var.curr_item_p', repr(zmienne))  # do pamięci
                self.play(**zmienne)
            else:
                self.play(title, localtitle, year, imdb, tvdb, tmdb, season, episode, tvshowtitle, premiered, meta, select, customTitles=customTitles)
                # self.play(title, localtitle, year, imdb, tvdb, tmdb, season, episode, tvshowtitle, premiered, meta, select, customTitles=customTitles, originalname=originalname, epimdb=epimdb)
                # może jednak to włączyć?
        except Exception:
            fflog_exc(1)
            pass


    def clearSources(self):
        try:
            #
            yes = control.yesnoDialog(control.lang(32407))
            if not yes:
                return

            control.makeFile(control.dataPath)
            dbcon = database.connect(control.providercacheFile)
            dbcur = dbcon.cursor()
            dbcur.execute("DROP TABLE IF EXISTS rel_src")
            dbcur.execute("DROP TABLE IF EXISTS rel_url")
            dbcur.execute("VACUUM")
            dbcon.commit()

            control.infoDialog(control.lang(32408), sound=True, icon="INFO")
        except Exception:
            pass


    def sortSources(self, sources, silent=False):
        # return sources  # brak sortowania - do testów
        # muszą być wszystkie pozycje, które zwraca source_utils.check_sd_url() i które zostały "zassane" przez zmienną filtered
        #my_quality_order = ["4K", "1440p", "1080p", "1080i", "720p", "SD", "SCR", "CAM"]
        my_quality_order = ["4K", "2160p", "2K", "1440p", "1080p", "1080i", "720p", "HD", "SD", "480p", "360p", "SCR", "CAM"]
        quality_order = {key: i for i, key in enumerate(my_quality_order)}

        # muszą być wszystkie możliwości wypisane jakie chcemy obsługiwać
        my_language_order = ["pl", "PL", "mul", "multi", "en", "eng", "de", "fr", "it", "es", "pt", "ko", "ru", "ja", '-', '']
        language_order = {key: i for i, key in enumerate(my_language_order)}

        # ustalenie kolejności dla nazw serwisów
        my_provider_order = ["cdapremium", "ekinotv premium",  "nopremium", "rapideo", "twojlimit", "tb7", "xt7", "0", "-"]
        my_provider_order = [str(i) for i in range(1,20+1)] + my_provider_order
        provider_order = {key: i for i, key in enumerate(my_provider_order)}
        provider_order[""] = 99
        # --- PART1/PART2 exception (prefer PART 2 when both present) ---
        def _ff_part_rank(item):
            """Return rank for PART markers: PART 2 first, then unknown, then PART 1 last."""
            try:
                s = (item.get("name") or item.get("info") or item.get("url") or "").lower()
            except Exception:
                s = ""
            # normalize Polish variants too
            if "part 2" in s or "czesc 2" in s or "część 2" in s:
                return 0
            if "part 1" in s or "czesc 1" in s or "część 1" in s:
                return 2
            return 1
        # --- END PART exception ---
        # fflog(f'{provider_order=}',1,1)

        # wybór wariantu sortowania
        sort_source = control.setting("hosts.sort")
        sort_source = str(sort_source)
        if sort_source == "0":  # by providers
            silent or fflog("Sortuję wg dostawców")  # serwisy internetowe www
            try:
                sources = sorted(
                    sources,
                    key=lambda d: (
                        not d["provider"].startswith("library"),
                        not d["provider"].startswith("biblioteka"),
                        not d["provider"].startswith("plex"),
                        not d["provider"].startswith("pobrane"),
                        not d["provider"].startswith("external"),
                        not d["on_account"] if "on_account" in d else 1,
                        # not d["provider"].startswith("cdapremium"),
                        # not d["provider"].startswith("nopremium") if not control.setting("nopremium.sort.order") else True,
                        # not d["provider"].startswith("rapideo") if not control.setting("rapideo.sort.order") else True,
                        # not d["provider"].startswith("twojlimit") if not control.setting("twojlimit.sort.order") else True,
                        # not d["provider"].startswith("tb7") if not control.setting("tb7.sort.order") else True,
                        # not d["provider"].startswith("xt7") if not control.setting("xt7.sort.order") else True,
                        # provider_order[(control.setting(d["provider"]+".sort.order") if control.setting(d["provider"]+".sort.order") and control.setting(d["provider"]+".sort.order") != "0" else d["provider"] if d["provider"] in my_provider_order else "")],
                        provider_order[(control.setting(d["provider"].split(" ")[0]+".sort.order") if control.setting(d["provider"].split(" ")[0]+".sort.order") and control.setting(d["provider"].split(" ")[0]+".sort.order") != "0" else d["provider"] if d["provider"] in my_provider_order else "")],
                        # provider_order[(control.setting(d["provider"].split(" ")[0]+".sort.order") if control.setting(d["provider"].split(" ")[0]+".sort.order") and control.setting(d["provider"].split(" ")[0]+".sort.order") != "0" else d["provider"] if any(d["provider"].startswith(p) for p in my_provider_order) else "")],  # eksperyment
                        language_order.get(d["language"]),
                        quality_order.get(d["quality"]),
                        d["provider"].replace("filman_api", "filma"),  # dostawca (serwis internetowy www) (dla filmana: aby filman_api było przed zwykłym filman)
                        source_utils.convert_size_to_bytes( d["size"] if "size" in d  else  d["info"].rsplit('|')[-1] if "info" in d and d["info"]  else '')*-1,
                        _ff_part_rank(d),
                    ),
                )
            except Exception:
                fflog_exc(1)
                fflog(f'sources={json.dumps(sources, indent=2)}', 0)
                pass

        if sort_source == "1":  # by sources (hosting, server)
            silent or fflog("Sortuję wg źródeł (hostingów/serwerów)")
            try:
                sources = sorted(
                    sources,
                    key=lambda d: (
                        not d["provider"].startswith("library"),
                        not d["provider"].startswith("biblioteka"),
                        not d["provider"].startswith("plex"),
                        not d["provider"].startswith("pobrane"),
                        not d["provider"].startswith("external"),
                        not d["on_account"] if "on_account" in d else 1,
                        # provider_order[(control.setting(d["provider"]+".sort.order") if control.setting(d["provider"]+".sort.order") and control.setting(d["provider"]+".sort.order") != "0" else d["provider"] if d["provider"] in my_provider_order else "")],
                        provider_order[(control.setting(d["provider"].split(" ")[0]+".sort.order") if control.setting(d["provider"].split(" ")[0]+".sort.order") and control.setting(d["provider"].split(" ")[0]+".sort.order") != "0" else d["provider"] if d["provider"] in my_provider_order else "")],
                        language_order.get(d["language"]),
                        quality_order.get(d["quality"]),
                        d["provider"].replace("filman_api", "filma"),  # dostawca (serwis internetowy www) (dla filmana: aby filman_api było przed zwykłym filman)
                        d["source"],  # source (serwer, hosting)
                        source_utils.convert_size_to_bytes( d["size"] if "size" in d  else  d["info"].rsplit('|')[-1] if "info" in d and d["info"]  else '')*-1,
                    ),
                )
            except Exception:
                fflog_exc(1)
                fflog(f'sources={json.dumps(sources, indent=2)}', 0)
                pass

        if sort_source == "2":  # by size
            silent or fflog("Sortuję wg rozmiaru")
            try:
                sources = sorted(
                    sources,
                    key=lambda d: (
                        not d["provider"].startswith("library"),
                        not d["provider"].startswith("biblioteka"),
                        not d["provider"].startswith("plex"),
                        not d["provider"].startswith("pobrane"),
                        not d["provider"].startswith("external"),
                        not d["on_account"] if "on_account" in d else 1,
                        # provider_order[(control.setting(d["provider"]+".sort.order") if control.setting(d["provider"]+".sort.order") and control.setting(d["provider"]+".sort.order") != "0" else d["provider"] if d["provider"] in my_provider_order else "")],
                        provider_order[(control.setting(d["provider"].split(" ")[0]+".sort.order") if control.setting(d["provider"].split(" ")[0]+".sort.order") and control.setting(d["provider"].split(" ")[0]+".sort.order") != "0" else d["provider"] if d["provider"] in my_provider_order else "")],
                        source_utils.convert_size_to_bytes( d["size"] if "size" in d  else  d["info"].rsplit('|')[-1] if "info" in d and d["info"]  else '')*-1,
                        language_order.get(d["language"]),
                        quality_order.get(d["quality"]),
                        d["provider"].replace("filman_api", "filma"),  # dostawca (serwis internetowy www) (dla filmana: aby filman_api było przed zwykłym filman)
                        d["source"],  # hosting (serwer, hosting)
                        _ff_part_rank(d),
                    ),
                )
            except Exception:
                fflog_exc(1)
                fflog(f'sources={json.dumps(sources, indent=2)}', 0)
                pass

        if sort_source == "3":
            custom_criterion = (control.setting("hosts.sort.elem1"), control.setting("hosts.sort.elem2"), control.setting("hosts.sort.elem3"), control.setting("hosts.sort.elem4"))
            silent or fflog(f'Sortuję wg ustawień użytkownika: {" -> ".join(custom_criterion)}')
            # funkcja pomocnicza
            def choose_criterium(d,x):
                crit = control.setting(f"hosts.sort.elem{x}")
                return (
                    # provider_order[(control.setting(d["provider"]+".sort.order") if control.setting(d["provider"]+".sort.order") and control.setting(d["provider"]+".sort.order") != "0" else d["provider"] if d["provider"] in my_provider_order else "")] if(crit.lower() in ("serwis", "provider"))
                    provider_order[(control.setting(d["provider"].split(" ")[0]+".sort.order") if control.setting(d["provider"].split(" ")[0]+".sort.order") and control.setting(d["provider"].split(" ")[0]+".sort.order") != "0" else d["provider"] if d["provider"] in my_provider_order else "")]  if(crit.lower() in ("serwis", "provider"))
                    else language_order.get(d["language"])  if(crit.lower() in ("język", "language"))
                    else quality_order.get(d["quality"])  if(crit.lower() in ("jakość", "quality"))
                    else source_utils.convert_size_to_bytes( d["size"] if "size" in d  else  d["info"].rsplit('|')[-1] if "info" in d and d["info"]  else '')*-1  if(crit.lower() in ("rozmiar", "size"))
                    else ''
                )
            # sortowanie
            try:
                sources = sorted(
                    sources,
                    key=lambda d: (
                        # zawsze na początku
                        not d["provider"].startswith("library"),
                        not d["provider"].startswith("biblioteka"),
                        not d["provider"].startswith("plex"),
                        not d["provider"].startswith("pobrane"),
                        not d["provider"].startswith("external"),
                        # czy na koncie online
                        not d["on_account"] if "on_account" in d else True,
                        # kryteria użytkownika
                        choose_criterium(d,0),  # 1 kryterium
                        choose_criterium(d,1),  # 2 kryterium
                        choose_criterium(d,2),  # 3 kryterium
                        choose_criterium(d,3),  # 4 kryterium
                        d["provider"].replace("filman_api", "filma"),  # dostawca (serwis internetowy www) (dla filmana: aby filman_api było przed zwykłym filman)
                        _ff_part_rank(d),
                    ),
                )
            except Exception:
                fflog_exc(1)
                fflog(f'sources={json.dumps(sources, indent=2)}', 0)
                pass

        return sources


    def sourcesFilter(self, **kwargs):
        fflog('Filtrowanie')
        # fflog(f'{kwargs=}')

        _release_year = _ff_extract_release_year(kwargs.get("year"), kwargs.get("premiered"))
        _allow_legacy_avi = _ff_is_legacy_decades(_release_year)
        _is_episode = bool(kwargs.get("episode")) and bool(kwargs.get("tvshowtitle"))
        _bypass_for_classic_series = _ff_is_classic_series(_release_year, _is_episode)
        try:
            self._ff_release_year = _release_year
            self._ff_allow_legacy_avi = _allow_legacy_avi
            self._ff_bypass_classic_series = _bypass_for_classic_series
        except Exception:
            pass

        # odrzucenie tych, które się nie mają adresu URL (może w wyniku jakiegoś błędu w scraperze)
        self.sources = [i for i in self.sources if i.get("url")]

        # fflog(f'{len(self.sources)=} self.sources={json.dumps(self.sources, indent=2)}',1,1)
        if control.setting("filter.duplicates") == "true":
            self.sources = self.filter_duplicates()  # usunięcie duplikatów
            pass
        # fflog(f'{len(self.sources)=} self.sources={json.dumps(self.sources, indent=2)}',1,1)
        debrid_only = control.setting("debrid.only")
        if debrid_only == "":
            debrid_only = "false"

        quality = control.setting("hosts.quality")
        if quality == "":
            quality = "0"
        #quality = "1"  # test
        # qmax = int(quality)  # niewykorzystywany
        qmin = int(control.setting("hosts.quality.min"))
        #qmin = 1  # test

        captcha = control.setting("hosts.captcha")
        if captcha == "":
            captcha = "true"

        numbering = ""
        numbering = control.setting("sources.numbering")
        if numbering == "":
            numbering = "true"
        numbering = False if numbering != "true" else True


        # ograniczenie maksymalnej ilości źródeł
        self.sources = self.sources[:1998]
        # fflog(f'{len(self.sources)=} self.sources={json.dumps(self.sources, indent=2)}',1,1)

        # random.shuffle(self.sources)  # po co to ?

        # [ s.update({"language": l.lower()})  for s in self.sources  if (l := s.get("language")) ]  # zmiana kodu języka na małe litery (nie wiem, czy potrzeba)

        sources_before_filtered = (self.sources).copy()  # kopia


        # coś z plikami lokalnymi (biblioteka Kodi może?)
        local = [i for i in self.sources if "local" in i and i["local"]]
        for i in local:
            # i.update({"language": self._getPrimaryLang() or "en"})  # aktualizacja języka dla plików lokalnych
            i.update({"language": i["language"] or "en"})  # aktualizacja języka dla plików lokalnych
            pass

        # oddzielenie internetowych od lokalnych
        self.sources = [i for i in self.sources if i not in local]  # tylko internetowe
        # --- DARMOWE LINKI (free) NIE SĄ FILTROWANE – WYCIĄGNIĘCIE NA BOK ---
        free_sources = [i for i in self.sources if not self._is_premium_provider(i)]
        self.sources = [i for i in self.sources if self._is_premium_provider(i)]

        # fflog(f'{len(self.sources)=} self.sources={json.dumps(self.sources, indent=2)}',1,1)


        # na początek listy źródła z linkami bezpośrednimi, czyli takimi, których nie trzeba dodatkowo wyszukiwać przez resolvera
        filtered = []
        filtered += [i for i in self.sources if i["direct"]]
        filtered += [i for i in self.sources if not i["direct"]]
        self.sources = filtered
        # fflog(f'{len(self.sources)=} self.sources={json.dumps(self.sources, indent=2)}',1,1)

        # coś ze źródłami debrid
        filtered = []
        for d in debrid.debrid_resolvers:
            fflog('coś ze źródłami debrid')
            valid_hoster = set([i["source"] for i in self.sources])  # set może zmienić pierwotną kolejność
            valid_hoster = [i for i in valid_hoster if d.valid_url("", i)]
            filtered += [
                dict(list(i.items()) + [("debrid", d.name)])
                for i in self.sources
                if i["source"] in valid_hoster
            ]
        if debrid_only == "false" or not debrid.status():
            filtered += [
                i
                for i in self.sources
                if not i["source"].lower() in self.hostprDict and not i["debridonly"]
            ]
        self.sources = filtered
        # fflog(f'{len(self.sources)=} self.sources={json.dumps(self.sources, indent=2)}',1,1)

        # kilkanaście linijek poniżej, to sprawdzanie jakości
        for i in self.sources:
            if "checkquality" in i and i["checkquality"]:
                if not i["source"].lower() in self.hosthqDict and i["quality"] not in ["SD", "SCR", "CAM"]:
                    i.update({"quality": "SD"})

        # ewentualne korekty oznaczeń jakości na stosowane tu przy przetwarzaniu
        for i in range(len(self.sources)):
            q = self.sources[i]["quality"]
            if q and (q[-1]=="P" or q[-1]=="I"):
                q = q.lower()
                self.sources[i].update({"quality": q})
            if q == "HD":
                self.sources[i].update({"quality": "720p"})
            elif q == "2K":
                self.sources[i].update({"quality": "1440p"})
            elif q == "2160p":
                self.sources[i].update({"quality": "4K"})
            elif q == "480p" or q == "360p":
                self.sources[i].update({"quality": "SD"})


        filtered = []
        filtered += local
        sources_before_filtered_quality = (self.sources).copy()

        if quality in ["0"]:
            filtered += [i for i in self.sources if i["quality"] == "4K" and "debrid" in i]
        if quality in ["0"]:
            filtered += [i for i in self.sources if i["quality"] == "4K" and "debrid" not in i and "memberonly" in i]
        if quality in ["0"]:
            filtered += [i for i in self.sources if i["quality"] == "4K" and "debrid" not in i and "memberonly" not in i]

        if quality in ["0", "1"]:
            filtered += [i for i in self.sources if i["quality"] == "1440p" and "debrid" in i]
        if quality in ["0", "1"] and qmin >= 1:
            filtered += [i for i in self.sources if i["quality"] == "1440p" and "debrid" not in i and "memberonly" in i]
        if quality in ["0", "1"] and qmin >= 1:
            filtered += [i for i in self.sources if i["quality"] == "1440p" and "debrid" not in i and "memberonly" not in i]

        if quality in ["0", "1", "2"]:
            filtered += [i for i in self.sources if (i["quality"] == "1080p" or i["quality"] == "1080i") and "debrid" in i]
        if quality in ["0", "1", "2"] and qmin >= 2:
            filtered += [i for i in self.sources if (i["quality"] == "1080p" or i["quality"] == "1080i") and "debrid" not in i and "memberonly" in i]
        if quality in ["0", "1", "2"] and qmin >= 2:
            filtered += [i for i in self.sources if (i["quality"] == "1080p" or i["quality"] == "1080i") and "debrid" not in i and "memberonly" not in i]

        if quality in ["0", "1", "2", "3"]:
            filtered += [i for i in self.sources if i["quality"] == "720p" and "debrid" in i]
        if quality in ["0", "1", "2", "3"] and qmin >= 3:
            filtered += [i for i in self.sources if i["quality"] == "720p" and "debrid" not in i and "memberonly" in i]
        if quality in ["0", "1", "2", "3"] and qmin >= 3:
            filtered += [i for i in self.sources if i["quality"] == "720p" and "debrid" not in i and "memberonly" not in i]

        #CAM_disallowed = control.setting("CAM.disallowed")  # później to filtruje
        CAM_disallowed = False
        if qmin >= 4:
            if CAM_disallowed == "true":
                filtered += [i for i in self.sources if i["quality"] in ["SD", "SCR"]]  # czy HDTS też zaliczać jako CAM ?
            else:
                filtered += [i for i in self.sources if i["quality"] in ["SD", "SCR", "CAM"]]

        self.sources = filtered

        # CLASSIC SERIES SD BYPASS (1950-2015):
        # Dla seriali z lat 1950-2015 SD zawsze przechodzi bez względu na qmin.
        try:
            if _bypass_for_classic_series:
                _sd_sources = [s for s in sources_before_filtered_quality if s.get("quality") in ["SD", "SCR", "CAM"]]
                if _sd_sources:
                    _seen = set()
                    for _x in self.sources:
                        try:
                            _seen.add((str(_x.get("provider", "")).lower(), str(_x.get("url", ""))))
                        except Exception:
                            pass
                    for _s in _sd_sources:
                        _k = (str(_s.get("provider", "")).lower(), str(_s.get("url", "")))
                        if _k not in _seen:
                            self.sources.append(_s)
                            _seen.add(_k)
        except Exception:
            pass

        # LEGACY AVI QUALITY BYPASS (1950-2005):
        # jeżeli AVI odpadło przez minimalną jakość (qmin), dołącz je z powrotem.
        try:
            if _allow_legacy_avi:
                _legacy_avi = [s for s in sources_before_filtered_quality if _ff_src_has_avi(s)]
                if _legacy_avi:
                    _seen = set()
                    for _x in self.sources:
                        try:
                            _seen.add((str(_x.get("provider", "")).lower(), str(_x.get("url", ""))))
                        except Exception:
                            pass
                    for _s in _legacy_avi:
                        _k = (str(_s.get("provider", "")).lower(), str(_s.get("url", "")))
                        if _k not in _seen:
                            self.sources.append(_s)
                            _seen.add(_k)
        except Exception:
            pass

        # aby móc potem zaznaczyć dlaczego poszło out
        for s in sources_before_filtered:
            if s in sources_before_filtered_quality:
                if s not in self.sources:
                    s["trash"] = s.get("quality")
        sources_before_filtered_quality = None

        # coś z captcha
        if not captcha == "true":
            filtered = [i for i in self.sources if i["source"].lower() in self.hostcapDict and "debrid" not in i]
            self.sources = [i for i in self.sources if i not in filtered]

        # coś z domenami, które chyba są z jakiegoś powodu wykluczone
        filtered = [i for i in self.sources if i["source"].lower() in self.hostblockDict and "debrid" not in i]
        self.sources = [i for i in self.sources if i not in filtered]

        # chyba angielskie źródła na koniec listy
        multi = [i["language"] for i in self.sources]
        multi = [x for y, x in enumerate(multi) if x not in multi[:y]]
        multi = True if len(multi) > 1 else False
        if multi:
            self.sources = [i for i in self.sources if not i["language"] == "en"] + [i for i in self.sources if i["language"] == "en"]


        EXTS = ("avi", "mkv", "mp4", ".ts", "mpg", "mov", "vob", "mts", "2ts")  # dozwolone rozszerzenia filmów ("2ts" to od "m2ts", ale tylko 3 znakowe rozszerzenie do tablicy ze względu na kompatybilność starszego kodu)
        extrainfo = control.setting("sources.extrainfo") == "true"
        filename_in_2nd_line = control.setting("sources.filename_in_2nd_line")
        remove_verticals_on_list = control.setting("sources.remove_verticals_on_list") == "true"
        fix_for_scroll_long_text_with_second_line = control.setting("fix_for_scroll_long_text_with_second_line") == "true"
        url2 = ""

        def _makeLabel(source, offset=None):
            url2 = ""
            if extrainfo:
                try:
                    if "filename" in source and source["filename"]:
                        url2 = source["filename"]
                    else:
                        url2 = source["url"].replace(' / ', ' ').replace('_/_', '_').rstrip("/").split("/")[-1]
                        url2 = url2.rstrip("\\").split("\\")[-1]  # dla plików z własnej biblioteki na dysku lokalnym
                        # fflog(f' {[i]} {url2=}')
                        url2 = re.sub(r"(\.(html?|php))+$", "", url2, flags=re.I)  # na przypadki typu "filmik.mkv.htm"
                        if url2.lower()[-3:] not in EXTS:
                            # próba pozyskanie nazwy z 2-giej linijki lub opisu
                            #if "info2" in source and source["info2"] and source["info2"].lower()[-3:] in EXTS:
                            # if source.get("info2", "").lower()[-3:] in EXTS:  # czasami są opisy "kamerdyner-cam-2018-pl"
                            if source.get("info2"):
                                url2 = source["info2"]
                            else:
                                """
                                # to raczej nie będzie już wykorzystywane, bo okazało się, że info może mieć juz swoje oznaczenia, więc mogą się dublować
                                url2 = source["info"] if source["info"] else ''
                                # próba odfiltrowania nazwy
                                url2 = url2.split("|")[-1].strip().lstrip("(").rstrip(")")
                                """
                                url2 = ""
                    # fflog(f' {[i]} {url2=}')
                    url2 = unquote(url2)  # zamiana takich tworów jak %nn (np. %21 to nawias)
                    url2 = unescape(url2)  # pozbycie się encji html-owych
                    # fflog(f' {url2=}')
                    if "year" in kwargs:
                        url3 = url2.partition( kwargs["year"] )[-1]
                        if not url3:
                            url3 = url2.partition( str(int(kwargs["year"])-1) )[-1]
                        url3 = url3 if url3 else url2
                    else:
                        url3 = url2
                    # fflog(f' {url3=}')
                    t = PTN.parse(url3)  # proces rozpoznawania
                    # fflog(f' {t=}')

                    t3d = t["3d"] if "3d" in t else ''  # zapamiętanie informacji pod inną zmienną czy wersja 3D
                    textended = t["extended"] if "extended" in t else ''  # informacja o wersji rozszerzonej
                    tremastered = t["remastered"] if "remastered" in t else ''  # informacja o wersji zremasterowanej

                    # poniżej korekty wizualne
                    if "audio" in t:
                        t["audio"] = re.sub(r"(?<!\d)([57]\.[124](?:\.[24])?)\.(ATMOS)\b", r"\1 \2", t["audio"], flags=re.I)
                        t["audio"] = re.sub(r"(?<=[DSPXAC3M])[.-]?([57261]\.[102])\b", r" \1", t["audio"], flags=re.I)
                        t["audio"] = re.sub(r"\b(DTS)[.-]?(HD|ES|EX|X(?!26))[. ]?(MA)?", r"\1-\2 \3", t["audio"], flags=re.I).rstrip()
                        t["audio"] = re.sub(r"(TRUEHD|DDP)\.(ATMOS)\b", r"\1 \2", t["audio"], flags=re.I)
                        t["audio"] = re.sub(r"(custom|dual)\.(audio)", r"\1 \2", t["audio"], flags=re.I)
                        t["audio"] = re.sub("ddp(?!l)", "DD+", t["audio"], flags=re.I)
                    if "codec" in t:
                        t["codec"] = re.sub(r"(\d{2,3})(fps)", r"\1 \2", t["codec"], flags=re.I)
                        t["codec"] = re.sub("plus", "+", t["codec"], flags=re.I)  # z myślą o HDR10Plus -> HDR10+
                        t["codec"] = re.sub(r"\bDoVi\b", "DV", t["codec"], flags=re.I)
                        if "DolbyVision".lower() in t["codec"].lower():  # DolbyVision -> DV
                            if "DV".lower() in t["codec"].lower():
                                t["codec"] = re.sub(r"\s*/\s*DolbyVision", "", t["codec"], flags=re.I)
                            else:
                                t["codec"] = re.sub("DolbyVision", "DV", t["codec"], flags=re.I)
                    if "quality" in t:
                        t["quality"] = re.sub(r"\b(\w+)\.(\w+)\b", r"\1-\2", t["quality"], flags=re.I)

                    t = [t[j] for j in t if "quality" in j or "codec" in j or "audio" in j]
                    t = " | ".join(t)
                    """
                    if not t:
                        log(f'fallback dla PTN.parse {url2=}')
                        t = source_utils.getFileType(url2)  # taki fallback dla PTN.parse()
                        t = t.strip()
                        log(f' {t=}')
                    """
                    """
                    # pozbycie się tych samych oznaczeń ze zmiennej info
                    if t:
                        source["info"] = re.sub(fr'(\b|[ ._|/]+)({"|".join(t.split(" / "))})\b', '', (source.get("info") or ""), flags=re.I)
                    """

                    # dodanie dodatkowych informacji (moim zdaniem ważnych)
                    if t3d:
                        if "3d" in url2.lower() and "3d" not in t.lower():
                            t = f"[3D] | {t}"
                        else:
                            t = t.replace("3D", "[3D]")

                    # dodatkowe oznaczenie pliku z wieloma sciezkami audio
                    if ( re.search(r"\bMULTI\b", url2, re.I)  # szukam w adresie, który powinien zawierać nazwę pliku
                         and "mul" not in source["language"].lower()
                         # and "PL" not in source["language"].upper()  # założenie, że jak wykryto język PL, to nie ma potrzeby o dodatkowym ozaczeniu
                         and "multi" not in (source.get("info") or "").lower()  # sprawdzenie, czy przypadkiem już nie zostało przekazane przez plik źródła
                         and "multi" not in t.lower()  # sprawdzenie, czy nie ma tej frazy już w opisie
                       ):
                        t += " | MULTI"

                    if ("multi" in t.lower() or "multi" in (source.get("info") or "").lower()) and source["language"] != "pl":
                        source["language"] = "multi"  # wymiana języka
                        t = re.sub(r'[/| ]*multi\b', '' , t, flags=re.I)  # wywalenie z opisu, aby nie było dubli
                        source["info"] = re.sub(r'[/| ]*multi\b', '' , (source.get("info") or ""), flags=re.I)  # wywalenie z opisu, aby nie było dubli

                    if textended:
                        if textended is True:
                            t += " | EXTENDED"
                        else:
                            textended = re.sub("(directors|alternat(?:iv)?e).(cut)", r"\1 \2", textended, flags=re.I)
                            t += f" | {textended}"

                    # długi napis i czy aż tak istotny?
                    if tremastered:
                        if tremastered is True:
                            t += " | REMASTERED"
                        else:
                            if "rekonstrukcja" not in t.lower():
                                tremastered = re.sub("(Rekonstrukcja).(cyfrowa)", r"\1 \2", tremastered, flags=re.I)
                                t += f" | {tremastered}"

                    if "imax" in url2.lower() and "imax" not in t.lower():  # sprawdzenie czy dodać info IMAX
                        t += " | [IMAX]"

                    if "avi" in url2.lower()[-3:] and "avi" not in t.lower():  # aby nie bylo zdublowań
                        t += " | AVI"  # oznaczenie tego typu pliku, bo nie zawsze dobrze odtwarza sie "w locie"

                    t = t.lstrip(" | ")  # przydaje się, jak ani PTN.parse() ani getFileType() nic nie znalazły
                    t += " " if t else ""
                    # t = t.strip()
                    # fflog(f'{t=}')

                except Exception:
                    fflog_exc(1)
                    t = None
            else:
                t = None
            #log(f' {t=} {url2=}')

            # u = source["url"]  -- NOT USED

            p = source["provider"]  # serwis internetowy, strona www

            lng = source["language"]

            s = source["source"]  # hosting (serwer hostujący źródło)
            source["source"] = source["source"].replace("*", "").replace("~", "")  # w tb7/xt7 dodaje * jak nie wiadomo jaki serwer konkretnie (dotyczy plików z bilbioteki)

            q = source["quality"]  # rozdzielczość pionowa

            # s = s.rsplit(".", 1)[0]  # wyrzucenie ostatniego człona domeny (np. ".pl", ".com")  # czy to tylko wizualnie, czy miało to jakiś cel?

            if p.lower() == "library":
                if control.setting("api.language") == "Polish":
                    p = "biblioteka"

            try:  # f to info (tu może być też rozmiar pliku na końcu)
                f = " | ".join(
                    [
                        "[I]%s [/I]" % info.strip()  # ta spacja chyba jest ważna
                        for info in source["info"].split("|")
                    ]
                )
            except Exception:
                f = ""

            try:
                d = source["debrid"]
            except Exception:
                d = source["debrid"] = ""

            if d.lower() == "real-debrid":
                d = "RD"

            # tworzenie LABELa
            if not d == "":  # debrid
                if numbering:
                    #label = "%02d | [B]%s | %s[/B] | " % (int(i + 1 + offset), d, p)
                    label = "{} |[B]%s[/B]| %s | " % (d, p)
                else:
                    label = "[B]%s[/B] | %s | " % (d, p)
            else:
                if numbering:
                    #label = "[LIGHT]%02d[/LIGHT] | [LIGHT][B]%s[/B][/LIGHT] | " % (int(i + 1 + offset), p)
                    if source.get("on_account"):
                        label = "[LIGHT]{}[/LIGHT] |[COLOR gold]%s[/COLOR]| " % (p)
                    else:
                        label = "[LIGHT]{}[/LIGHT] |%s| " % (p)
                else:
                    label = "%s | " % (p)

            if source.get("on_account") and numbering:
                #label = re.sub(r'(\d{2,})', r'[I]\1[/I]', label, 1)
                label = re.sub(r'(\{\})', r'[I]\1[/I]', label, 1)
                pass

            if numbering and offset is not None:
                label = label.format("%02d" % (i + 1 + offset))


            # oznaczenie języka
            if lng:
                if (
                    multi and lng != "en"  # nie rozumiem, kiedy ten warunek zachodzi
                    or not multi and lng != "en"  # dałem ten warunek
                   ):
                    if extrainfo:
                        label += "[B]%s[/B] | " % lng
                    else:
                        f = ("[B]%s[/B] | " % lng) + f  # inny wariant
                r"""
                else:
                    if "mul" in lng or re.search(r"\bMULTI\b", t, re.I):
                        label += "[B]multi[/B] | "
                        # usunięcie z opisu, aby nie było zdublowań
                        if re.search(r"\bMULTI\b", t, re.I):
                            t = re.sub(r"\s*\bMULTI\b(\s[/|])?", "", t, flags=re.I)
                            t = re.sub(r"(\s[/|])(?=\s*$)", "", t, flags=re.I)
                """


            # oznaczenie, czy źródło jest w tzw. bibliotece danego serwisu
            if "on_account" in source and source["on_account"]:
                if source.get("on_account_expires"):
                    label += f'[I][LIGHT]konto[/LIGHT] ({source["on_account_expires"]})[/I] | '
                else:
                    label += '[I]konto[/I] | '


            trash = source.get("trash")

            if t:  # extrainfo
                source["extrainfo"] = t  # potrzebne do downloadera
                if remove_verticals_on_list:
                    t = t.replace(" |", ",")
                    t = f"({t.strip()})"
                if q in ["4K", "1440p", "1080p", "1080i", "720p"] or trash == q:
                    label += "%s |[B][I]%s[/I][/B] |[I]%s[/I]| %s" % (s, q, t, f)
                elif q == "SD":
                    # label += "%s | %s | [I]%s[/I]" % (s, f, t)
                    # moja propozycja (wielkość pliku na końcu - dla spójności)
                    label += "%s |[I]%s[/I]| %s" % (s, t, f)
                else:
                    # label += "%s | %s | [I]%s [/I] | [I]%s[/I]" % (s, f, q, t)
                    # moja propozycja (wielkość pliku na końcu - dla spójności)
                    # label += "[LIGHT]%s | [B][I]%s [/I][/B] | [I]%s[/I] | %s[/LIGHT]" % (s, q, t, f)
                    label += "[LIGHT]%s |[I]%s[/I]| %s[/LIGHT]" % (s, t, f)
            else:
                if q in ["4K", "1440p", "1080p", "1080i", "720p"] or trash == q:
                    label += "%s |[B][I]%s[/I][/B] | %s" % (s, q, f)
                elif q == "SD":
                    label += "%s | %s" % (s, f)
                else:
                    # label += "%s | %s | [I]%s [/I]" % (s, f, q)
                    # moja propozycja (wielkość pliku na końcu - dla spójności)
                    # label += "[LIGHT]%s | [B][I]%s [/I][/B] | %s[/LIGHT]" % (s, q, f)
                    label += "[LIGHT]%s | %s[/LIGHT]" % (s, f)

            # korekty wizualne
            label = label.replace("| 0 |", "|").replace(" | [I]0 [/I]", "")
            label = re.sub(r"\[I\]\s+\[/I\]", " ", label)
            label = re.sub(r"\|\s+\|", "|", label)
            label = re.sub(r"\|\s+\|", "|", label)  # w pewnych okolicznościach ponowne wykonanie takiej samej linijki kodu jak wyżej pomaga
            label = re.sub(r"\|(?:\s+|)$", "", label)
            label = re.sub(r"\[I\](\d+(?:[.,]\d+)?\s*[GMK]B) ?\[/I\]", r"[B]\1[/B]", label, flags=re.I)  # wyróżnienie rozmiaru pliku
            label = re.sub(r"(?<=\d)\s+(?=[GMK]B\b)", "\u00A0", label, flags=re.I)  # aby nie rodzielal cyfr od jednostek
            label = re.sub("((?:1080|720|1440)[pi])", r"[LOWERCASE]\1[/LOWERCASE]", label, flags=re.I)  # aby np. 1080i było bardziej widoczne
            if (p.lower() == "external"
                # or p.lower() == "pobrane"
                or "quality" in (source.get("unsure") or "")
               ):
                label = re.sub("(4K|(?:1080|720|1440)[pi])", r"\1*", label, flags=re.I)  # dołączenie gwiazdki
            # log(f'{label=}')  # kontrola
            """
            if control.setting("sources.remove_spaces_on_list") == "true":
                # label = label.replace(" | ", "|")  # zmniejszenie odstępów
                label = label.replace(" |", "|").replace("| ", "|")  # zmniejszenie odstępów
            """
            if remove_verticals_on_list:
                label = label.replace("|", " ")
                label = label.replace("   ", "  ")
                # label = label.replace("  ", " ")
                label = label.replace(" [/I]  ", " [/I] ")
                pass

            label = label.upper()
            # fflog(f'{trash=} {label=}')  # na tym etapie nie ma jeszcze 2 linii
            if trash and isinstance(trash, str):
                label = re.sub(f"({re.escape(trash)})", r"[COLOR darkred]\1[/COLOR]", label, flags=re.I)

            # wdrożenie LABELa
            if (
                    d
                or  p.lower() == "pobrane"
                or  p.lower() == "external"
                or  p.lower() == "plex"
                or  p.lower() == "rapideo"
                or  p.lower() == "twojlimit"
                or  p.lower() == "nopremium"
                or  p.lower() == "tb7"
                or  p.lower() == "xt7"
                or  p.lower() == "cdapremium"
                or  p.lower() == "ekinotv premium"
                or  p.lower() == "library"
                or  p.lower() == "biblioteka"
                or (p.lower().startswith("filman_api")  if control.setting("filman_api.mark_as_premium") == "true"  else False)
            ):
                p = p.split(" ")[0]
                clib = control.setting(f"{p.lower()}.library.color.identify")
                clib = int(clib) if clib else 10
                if clib < 10 and source.get("on_account"):
                    color = source_utils.getPremColor(str(clib))
                    source["label"] = f'[COLOR {color}]{label}[/COLOR]'  # wdrożenie LABELa
                else:
                    prem_identify = source_utils.getPremColor()
                    cp = control.setting(f"{p.lower()}.color.identify")
                    cp = int(cp) if cp else 10
                    if cp < 10:
                        color = source_utils.getPremColor(str(cp))
                        source["label"] = f'[COLOR {color}]{label}[/COLOR]'  # wdrożenie LABELa
                    elif not prem_identify == "nocolor":
                        source["label"] = (("[COLOR %s]" % prem_identify) + label + "[/COLOR]")  # wdrożenie LABELa
                    else:
                        source["label"] = label  # wdrożenie LABELa
            else:
                source["label"] = label  # wdrożenie LABELa

            # dorzucenie ewentualnie drugiej linii
            # if (filename_in_2nd_line == "true" or source.get("trash")) and "info2" not in source:
            if (filename_in_2nd_line == "true" or source.get("trash")) and not source.get("info2"):
                # if url2 and url2.lower()[-3:] in EXTS:
                if url2:
                    source["info2"] = url2
                if source.get("filename"):
                    source["info2"] = source["filename"]
            if (
                source.get("info2")
                and (filename_in_2nd_line == "true" or source.get("trash"))  # zastanawiam się, czy info2 to tylko dla nazwy pliku
                ):
                source["info2"] = unescape(unquote(source["info2"]))
                if source.get("on_account"):
                    source["info2"] = '[I]' + source["info2"] + '[/I]'  # opcjonalnie, aby trochę bardziej odróżnić
                # sprawdzenie, czy wyróżnić jakiś fragment w tej 2 linii
                if trash and isinstance(trash, str):
                    source["info2"] = re.sub(f"({re.escape(trash)})", r"[COLOR darkred]\1[/COLOR]", source["info2"], flags=re.I)
                # dodanie do labela dodatkowych spacji, bo przy przesuwaniu tekstu Kodi ucina 2 linijkę, jeśli ta jest dłuższa od górnej
                if fix_for_scroll_long_text_with_second_line:
                    dlugosc1 = len(re.sub(r'\[.*?\]', '', source["label"]))
                    dlugosc2 = len(source["info2"])
                    roznica = dlugosc2 - dlugosc1
                    if roznica > 5:  # jakiś próg zadziałania
                        source["label"] += " " * int(roznica * 1.86)
                source["label"] += '[CR][LIGHT] ' + source["info2"] + '[/LIGHT]'  # dodanie 2 linii do labela

            return source


        # LABELOWANIE
        for i in range(len(self.sources)):
            #self.sources[i]["label"] = _makeLabel(self.sources[i])["label"]
            self.sources[i] = _makeLabel(self.sources[i])

        # odrzucenie tych, które się nie załapały czemuś (nie dostały labela)
        self.sources = [i for i in self.sources if "label" in i]

        # odrzucenie tych, które mają oznaczenie "kosza" (przeważnie to odrzucone przez filtr dopasowujący tytuły)
        for i in self.sources[:]:
            if i.get("trash"):
                if isinstance(i.get("trash"), bool):
                    i["label"] = i["label"].replace("[CR]", "[CR][COLOR brown]") + "[/COLOR]"
                self.sources.remove(i)
        """
        self.sources = [
            i
            for i in self.sources
            if not i.get("trash")
        ]
        """

        # odrzucenie, ze względu na rozmiar
        # fflog(f'{kwargs=}',1,1)
        duration = kwargs.get("duration") or 0 # w sekundach powinno być
        # ale może być też trafić się w formie 52:00 (52 minuty)
        if isinstance(duration, str) and ":" in duration:
            _ = duration.split(":")
            duration = 0
            for i,d in enumerate(reversed( _ )):
                duration += int(d) * 60**i
        else:
            try:
                duration = int(duration)
            except:
                duration = 0
        if duration > 300:  # raczej w sekundach
            duration = int(duration/60) if duration else 0  # na minuty
        else:
            pass  # może być już w minutach
        fflog(f'{duration=}',1,1)

        # tylko nie większe niż
        if (maxSourceSize := int(control.setting("maxSourceSize"))) > 0:

            if ( maxSourceSize_ranges := ( (control.setting("maxSourceSize.ranges")).strip(" ,") ) ) and duration:
                try:
                    maxSourceSize_ranges = maxSourceSize_ranges.split(",")
                    _ = {}
                    for o in maxSourceSize_ranges:
                        k,v = o.split(":")
                        _.update({int(k):int(v)})
                    maxSourceSize_ranges = _
                    for mss in maxSourceSize_ranges:
                        if duration <= mss:
                            maxSourceSize = maxSourceSize_ranges[mss]
                            break
                    fflog(f'{duration=} min.',1,1)
                    fflog(f'{maxSourceSize=} GB',1,1)
                except Exception:
                    fflog_exc(1)
                    pass
            fflog(f'{maxSourceSize=} GB',1,1)
            maxSourceSize = maxSourceSize * 1024 * 1024 * 1024 + 0
            for i in self.sources[:]:
                if i.get("provider") in ["pobrane", "biblioteka", "library", "plex"]:  # tych nie filtrujemy pod względem rozmiaru
                    continue
                    pass
                if source_utils.convert_size_to_bytes(i.get("size", "")) > maxSourceSize:
                    i["label"] = re.sub(r"\b(\d+([.,]\d+)?\s?[GMK]B)\b", r"[COLOR darkred]\1[/COLOR]", i["label"])
                    self.sources.remove(i)
            """
            self.sources = [
                i
                for i in self.sources
                if source_utils.convert_size_to_bytes(i.get("size", "")) < maxSourceSize
            ]
            """


        # i jeszcze odfiltrowania, które wykorzystują nadany już label

        # odrzucenie wersji 3D
        if control.setting("3D.disallowed") == "true":
            for i in self.sources[:]:
                if re.search(r"\b3D\b", i["label"], re.I):
                    i["label"] = re.sub(r"\b(3D)\b", r"[COLOR darkred]\1[/COLOR]", i["label"], flags=re.I)
                    self.sources.remove(i)

        # odrzucenie kodeka HEVC (przydatne dla starszych urządzeń)
        if not control.setting("HEVC") == "true":
            HEVC_pat = r"\b(HEVC|[xh]265)\b"
            for i in self.sources[:]:
                if re.search(HEVC_pat, i["label"], re.I):
                    i["label"] = re.sub(HEVC_pat, r"[COLOR darkred]\1[/COLOR]", i["label"], flags=re.I)
                    self.sources.remove(i)
            HEVC_pat = None
            """
            self.sources = [
                i
                for i in self.sources
                if "HEVC" not in i["label"] or "265" not in i["label"]
            ]
            """

        # odrzucenie nagrywanego kamerą
        CAM_disallowed = control.setting("CAM.disallowed")
        if CAM_disallowed == "true":
            CAM_format = ["camrip", "hdcam", "hqcam", "dvdcam", "cam"]
            if control.setting("telesync.disallowed") == "true":
                CAM_format += ["hdts", "hd-ts", "telesync", r"\bts\b", "tsrip", "dvdts"]
            CAM_format_re = re.compile(rf"\b({'|'.join(CAM_format)})(v[1-4])?\b", flags=re.I)
            for i in self.sources[:]:
                if CAM_format_re.search(i["label"]):
                    i["label"] = CAM_format_re.sub(r"[COLOR darkred]\1\2[/COLOR]", i["label"])
                    self.sources.remove(i)
            CAM_format_re = None
            """
            self.sources = [
                i
                for i in self.sources
                # if "CAM" not in i["label"]
                if not any(x in i["label"].lower().replace("]", " ").replace("[", " ") for x in CAM_format)
            ]
            """

        # odrzucenie dźwięku z kina
        if control.setting("MD.sound.disallowed") == "true":
            for i in self.sources[:]:
                """
                if re.search(r"\b(md|dubbing[ _.-]kino)\b", i["label"], re.I):
                    i["label"] = re.sub(r"\b(md|dubbing[ _.-]kino)\b", r"[COLOR darkred]\1[/COLOR]", i["label"], flags=re.I)
                """
                label = re.sub(r"\b(md|(dubbing|audio)[ _.-]kino)\b", r"[COLOR darkred]\1[/COLOR]", i["label"], flags=re.I)
                if label != i["label"]:
                    i["label"] = label
                    self.sources.remove(i)
            label = None
            """
            self.sources = [
                i
                for i in self.sources
                if not re.search(r"\b(md|dubbing[ _.-]kino)\b", i["label"], re.I)
            ]
            """

        # [GPT FIX] Early MULTI normalization BEFORE "only PL" filter
        try:
            _rx_multi = re.compile(r'\bmulti\b', re.I)
        except NameError:
            import re as _re
            _rx_multi = _re.compile(r'\bmulti\b', _re.I)
        try:
            _sources_iterable = self.sources if isinstance(self.sources, (list, tuple)) else []
            for _it in list(_sources_iterable):
                _lng = (_it.get("language") or "").lower()
                if _lng != "pl":
                    _blob = " ".join([str(_it.get("label","")), str(_it.get("info","")), str(_it.get("info2","")), str(_it.get("filename","")), str(_it.get("url",""))])
                    if _rx_multi.search(_blob):
                        _it["language"] = "multi"
        except Exception as _e:
            # fail-safe: do not break filtering if something goes wrong
            pass
        # tylko wersja z PL
        if control.setting("lang.onlyPL") == "true":
            #lang_allowed = ["pl"]
            # accept MULTI if any alias flag is true (fallback: default to TRUE per user preference)
            _multi_flags = [
                control.setting('MULTI.allowed'),
                control.setting('lang.allow_multi'),
                control.setting('lang.multi'),
                control.setting('lang.multi.allowed'),
            ]
            MULTI_allowed = any(str(x).lower() == 'true' for x in _multi_flags) or True
            for i in self.sources[:]:
                #fflog(f'{i.get("language")=}')
                if i.get("language") != "pl":
                    #fflog(f'{i.get("language")=}')
                    # if MULTI_allowed and MULTI_format_re.search(i["label"]):
                    if MULTI_allowed and (i.get("language") or "").lower() in ("multi", "mul"):
                        continue
                    else:
                        # fflog(f'{i["label"]=}',1,1)
                        #i["label"] = i["label"].replace(" | ", " | [COLOR darkred]brak PL[/COLOR] | ", 1)
                        #i["label"] = re.sub(r"(\|.*?\|)|$", r"\1 [COLOR darkred]brak PL[/COLOR] |", i["label"], 1).rstrip(" |")
                        i["label"] = re.sub(r"(\|.*?\|)|(\] )(\s{3,}\[CR\])|$", r"\1\2 [COLOR darkred]brak PL[/COLOR]\3 |", i["label"], 1).replace("[CR] |","[CR]").rstrip(" |")
                        i["label"] = re.sub(r" {4,9}", "", i["label"], 1)
                        self.sources.remove(i)
            """
            self.sources = [
                i
                for i in self.sources
                if i.get("language") == "pl"
            ]
            """

        subtitles_mode = control.setting("subtitles.mode")
        fflog(f'{subtitles_mode=}',1,1)
        # odrzucenie wersji tylko z napisami
        # if control.setting("subtitles.disallowed") == "true":
        if subtitles_mode == "bez napisów":
            for i in self.sources[:]:
                if re.search(r"\bnapisy\b", i["label"], re.I) and not re.search(r"\b(lektor|dubbing)\b", i["label"], re.I):  # dobrze, jak wynik jest z funkcji source_utils.get_lang_by_type
                    i["label"] = re.sub(r"\b(napisy)\b", r"[COLOR darkred]\1[/COLOR]", i["label"], flags=re.I)
                    self.sources.remove(i)
        # odrzucenie wersji, które nie mają napisów
        # if control.setting("subtitles.only") == "true":
        elif subtitles_mode == "tylko z napisami":
            for i in self.sources[:]:
                if not re.search(r"\bnapisy\b", i["label"], re.I) and re.search(r"\b(lektor|dubbing)\b", i["label"], re.I):  # dobrze, jak wynik jest z funkcji source_utils.get_lang_by_type
                    i["label"] = re.sub(r"\b(lektor|dubbing)\b", r"[COLOR darkred]\1[/COLOR]", i["label"], flags=re.I)
                    self.sources.remove(i)


        # do wykorzystania przez inne filtry
        def is_in_text(src, disallowed_rx, disallowed_rx1=None, color="darkred"):
            """ może być uniwersalną funkcją, trzeba tylko ustawić zmienną disallowed_rx """
            if not disallowed_rx:
                #return True
                return
            label, num = disallowed_rx.subn(rf"[COLOR {color}]\1[/COLOR]", src["label"])
            if num:
                if f"[COLOR {color}][/COLOR]" in label and disallowed_rx1:
                    is_in_text(src, disallowed_rx1, color=color)
                else:
                    src["label"] = label
            #return num == 0
            #return not num
            return bool(num)

        # odrzucenie DolbyVision (gdy nie ma dodatkowo HDR)
        DVonly_disallowed = control.setting("DVonly.disallowed") == "true"
        if DVonly_disallowed:
            # disallowed_words = ['DV', 'DoVi', 'DolbyVision', 'Dolby Vision']
            # disallowed_pat = "|".join(re.escape(w) for w in disallowed_words)
            # disallowed_pat = r"\bDV\b|\bDoVi\b|Dolby ?Vision"
            # disallowed_pat = r"\bD(?P<g1>o)?(?P<g2>lby)?(?(g2) ?)V(?(g1)i)(sion)?\b"
            disallowed_pat = r"\bD(?:V|oVi|olby ?Vision)\b"
            # disallowed_rx = re.compile(fr"\b({disallowed_pat})\b", flags=re.I)
            disallowed_rx = re.compile(fr"({disallowed_pat})", flags=re.I)
            hdrallowed_rx = re.compile("(hdr)", flags=re.I)
            self.sources = [src for src in self.sources if not is_in_text(src, disallowed_rx) or is_in_text(src, hdrallowed_rx, color="green")]

        # odrzucenie HDR
        HDR_disallowed = control.setting("HDR.disallowed") == "true"
        if HDR_disallowed:
            # disallowed_pat = "HDR"
            # disallowed_rx = re.compile(fr"\b({disallowed_pat})\b", flags=re.I)
            # disallowed_rx = re.compile(fr"({disallowed_pat})", flags=re.I)
            # self.sources = [src for src in self.sources if "hdr" not in src["label"].lower()]  # nie oznacza kolorem
            for i in self.sources[:]:
                # if "hdr" in i["label"].lower():
                i["label"], num = re.subn("(hdr)", r"[COLOR darkred]\1[/COLOR]", i["label"], flags=re.I)
                if num:
                    self.sources.remove(i)



        # zakazane słowa
        disallowed_words = control.setting('words.disallowed'); fflog(f'{disallowed_words=}', 0)
        def make_patterns(disallowed_words):
            if isinstance(disallowed_words, str):
                disallowed_words = disallowed_words.split(',')
                disallowed_words = [w.strip().replace('"', '') for w in disallowed_words]
                disallowed_words = list(filter(None, disallowed_words))
                disallowed_words = list(dict.fromkeys(disallowed_words))
            zwykla = [w for w in disallowed_words if not w.strip().startswith('!')]
            priorytetowa = [w.replace('!', '') for w in disallowed_words if w.strip().startswith('!')]
            zwykla  = [w for w in zwykla if len(w) > 0]
            priorytetowa = [w for w in priorytetowa if len(w) > 0]
            zwykla1 = [r'(^|[^a-z])' + _ + r'([^a-z]|$)' for _ in zwykla]
            priorytetowa1 = [r'(^|[^a-z])' + _ + r'([^a-z]|$)' for _ in priorytetowa]
            zwykla2 = [re.sub(r'\s+', r'.*', _) for _ in zwykla1]
            priorytetowa2 = [re.sub(r'\s+', r'.*', _) for _ in priorytetowa1]
            zwykla = zwykla1 + zwykla2
            priorytetowa = priorytetowa1 + priorytetowa2
            zwykla = [re.compile(_, flags=re.I) for _ in zwykla]
            priorytetowa = [re.compile(_, flags=re.I) for _ in priorytetowa]
            return zwykla, priorytetowa, zwykla1

        def rozdziel_na_priorytet(x):
            if isinstance(x, list):
                disallowed_words = [w.strip().replace('"', '') for w in x]
            else:
                disallowed_words = str(x or '').split(',')
                disallowed_words = [w.strip().replace('"', '') for w in disallowed_words]
            disallowed_words = list(filter(None, disallowed_words))
            disallowed_words = list(dict.fromkeys(disallowed_words))
            zwykla = [w for w in disallowed_words if not w.strip().startswith('!')]
            priorytetowa = [w.replace('!', '') for w in disallowed_words if w.strip().startswith('!')]
            return zwykla, priorytetowa

        def sprawdz_czy_jest(src, zwykla, zwykla2, zwykla1, color=None):
            wypisz = ''
            if zwykla:
                label = src.get('label', '')
                url = src.get('url', '')
                w = label + ' ' + url
                for pattern in zwykla:
                    if pattern.search(w):
                        if color:
                            wypisz += f"[B][COLOR {color}]ZAKAZANE[/COLOR][/B] "
                        return True
            return False

        # SCAL: GUI + _FF_DEFAULT_BLOCK
        try:
            gui_list = [w.strip() for w in (disallowed_words or "").split(',') if w.strip()]
        except Exception:
            gui_list = []
        merged_list = list(dict.fromkeys(gui_list + [w.strip() for w in _FF_DEFAULT_BLOCK.split(',') if w.strip()]))

        # Nonrejectable (whitelist) jak w GUI
        nonrejectable_phrases = control.setting('nonrejectable_phrases') or ""
        fflog(f'{nonrejectable_phrases=}', 0)

        # Rozdziel GUI+DEFAULT na zwykle/priorytetowe
        zwykla, priorytetowa = rozdziel_na_priorytet(merged_list)

        # Przygotuj wzorce
        disallowed_rx, disallowed2_rx, disallowed1_rx = make_patterns(zwykla)
        prio_rx, prio2_rx, prio1_rx = make_patterns(priorytetowa)
        nr_rx, nr2_rx, nr1_rx = make_patterns(nonrejectable_phrases)

        def _txt_from_src(src):
            return f"{src.get('label','')} || {src.get('url','')}".lower()

        def _is_blocked_by_main(src):
            # --- WHITELIST: AI + ATVP/ATPV (Apple TV) ---------------------  ### PATCH ###
            try:
                _txt_local = _txt_from_src(src)
                if _is_exception_ai_atvp(_txt_local):        # ai + atvp → NIE blokuj
                    return False                             # puść źródło dalej
            except Exception:
                pass
            # ----------------------------------------------------------------  ### END ###

            src_chk = src
            if _allow_legacy_avi:
                try:
                    src_chk = dict(src)
                    for _k in ("label", "url", "info", "extrainfo", "filename"):
                        if isinstance(src_chk.get(_k), str):
                            src_chk[_k] = _ff_prepare_text_for_blocking(src_chk.get(_k), allow_legacy_avi=True)
                except Exception:
                    src_chk = src

            if sprawdz_czy_jest(src_chk, prio_rx, prio2_rx, prio1_rx, color='ffcc0000'):
                return True
            if sprawdz_czy_jest(src_chk, disallowed_rx, disallowed2_rx, disallowed1_rx):
                if sprawdz_czy_jest(src_chk, nr_rx, nr2_rx, nr1_rx, color='green'):
                    return False
                return True
            return False





        def _is_exception_ai_atvp(txt: str) -> bool:
            # wyjątek: ai+atvp oraz AI-lektor (label) → NIE blokuj
            t = (txt or '').lower()
            if re.search(r'(?:ailektor|ai[\s\-_]*lektor|lektor[\s\-_]*ai)', t):
                return True
            return has_standalone_ai(txt) and ('atvp' in t or 'atpv' in t)

        def _is_exception_dv_hdr(txt: str) -> bool:
            # Wyjątek DV+HDR nie może przepuścić, jeśli występuje JAKAKOLWIEK fraza blokująca
            t = (txt or '').lower()
            if 'dv' not in t:
                return False
            # jeśli matchują frazy blokujące (whole/sub), nie stosuj wyjątku
            try:
                if _has_any(PATTERNS_WHOLE_WORD, t) or _has_any(PATTERNS_SUBSTRING, t):
                    return False
            except Exception:
                pass
            return any(k in t for k in ('hdr', 'hdr10', 'hdr10plus', 'hdr10+'))


        def _is_audio_20_exception(text: str) -> bool:
            t = (text or '').lower()
            if not re.search(r'\b2\.0\b', t):
                return False
            return bool(re.search(r'(?:\bddp\b|\bdd\+\b|\bac3\b)', t))

        _filtered = []
        if _bypass_for_classic_series:
            # CLASSIC SERIES BYPASS (1950–2015): wszystkie frazy blokujące wyłączone
            _filtered = list(self.sources)
        else:
            for _s in self.sources:
                _txt = _txt_from_src(_s)

                # Główna siatka – najpierw blokada, potem wyjątki
                if _is_blocked_by_main(_s):
                    continue

                # Wyjątki
                if _is_exception_ai_atvp(_txt) or _is_exception_dv_hdr(_txt) or _is_audio_20_exception(_txt):
                    _filtered.append(_s)
                    continue

                # Dodatkowe prekompilowane wzorce (honorują whitelistę)
                _txt_for_block = _ff_prepare_text_for_blocking(_txt, allow_legacy_avi=_allow_legacy_avi)
                if _has_any(PATTERNS_WHOLE_WORD, _txt_for_block) or _has_any(PATTERNS_SUBSTRING, _txt_for_block):
                    if sprawdz_czy_jest(_s, nr_rx, nr2_rx, nr1_rx, color='green'):
                        _filtered.append(_s); continue
                    else:
                        continue

                _filtered.append(_s)

        self.sources = _filtered
# SORTOWANIE
        self.sources = self.sortSources(self.sources)

        # numerowanie
        if numbering:
            for i in range(len(self.sources)):
                # fflog(f'{i=}  {self.sources[i]=}',1,1)
                self.sources[i]["label"] = self.sources[i]["label"].replace("{}", f"{i + 1:02d}", 1)
                # fflog(f'{i=}  {self.sources[i]=}',1,1)


        # na KONIEC lista ODRZUCONYCH
        # fflog(f'len:{len(sources_before_filtered)} {sources_before_filtered=}')
        # fflog(f'len:{len(self.sources)} {self.sources=}')
        s = [{s.get("provider"): s.get("url")} for s in self.sources]  # lista pomocnicza
        sources_thrown_out = [x for x in sources_before_filtered if {x.get("provider"): x.get("url")} not in s]
        # fflog(f'len:{len(sources_thrown_out)} {sources_thrown_out=}')

        sources_thrown_out = self.sortSources(sources_thrown_out, silent=True)  # sortowanie

        offset = len(self.sources)  # aby kontynuować numerację
        for i in range(len(sources_thrown_out)):
            if "label" not in sources_thrown_out[i]:
                # fflog(f'a {i=}  {sources_thrown_out[i]=}',1,1)
                sources_thrown_out[i] = _makeLabel(sources_thrown_out[i], offset)
                # fflog(f'b {i=}  {sources_thrown_out[i]=}',1,1)
            if numbering:
                # przenumerowanie
                # fflog(f'c {i=}  {sources_thrown_out[i]=}',1,1)
                if "{}" not in sources_thrown_out[i]["label"]:
                    sources_thrown_out[i]["label"] = re.sub(r'^([^|]*?)(\d{2,})(.*?\|)', r'\1{}\3', sources_thrown_out[i]["label"], 1)  # usunięcie starego numeru
                    # fflog(f'd {i=}  {sources_thrown_out[i]=}',1,1)
                sources_thrown_out[i]["label"] = sources_thrown_out[i]["label"].replace("{}", f"{offset + i + 1:02d}", 1)
                # fflog(f'e {i=}  {sources_thrown_out[i]=}',1,1)

        # wrzucenie do pamięci RAM
        control.window.setProperty(self.itemRejected, json.dumps(sources_thrown_out))


        # w tb7/xt7 dodaje * jak nie wiadomo jaki serwer konkretnie (dotyczy plików z bilbioteki)
        """ przeniosłem wyżej
        for i in range(len(self.sources)):
            if "source" in self.sources[i]:
                self.sources[i]["source"] = self.sources[i]["source"].replace("*", "").replace("~", "")
        """
        # --- FILTROWANIE MARTWYCH LINKÓW Z DARMOWYCH ŹRÓDEŁ (równoległe, nieblokujące) ---
        def _ff_is_url_alive(url, timeout=3):
            """Sprawdza czy URL odpowiada (HEAD request). Zwraca False dla 404/410/400."""
            try:
                import urllib.request
                clean_url = url.split('|')[0].split('$$')[0].strip()
                if not clean_url.startswith('http'):
                    return True
                req = urllib.request.Request(clean_url, method='HEAD')
                req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    if resp.status in (404, 410, 400):
                        fflog(f'[DEAD LINK] {resp.status} -> odrzucono: {clean_url}', 0, 1)
                        return False
                    return True
            except Exception as e:
                err = str(e)
                if '404' in err or '410' in err or '400' in err:
                    fflog(f'[DEAD LINK] blad HTTP -> odrzucono: {url[:60]} ({err})', 0, 1)
                    return False
                return True  # timeout/inny blad - nie odrzucamy

        try:
            import threading as _threading
            results = {}
            def _check(idx, fs):
                results[idx] = _ff_is_url_alive(fs.get('url', ''))
            threads_check = []
            for _idx, _fs in enumerate(free_sources):
                t = _threading.Thread(target=_check, args=(_idx, _fs))
                t.daemon = True
                t.start()
                threads_check.append(t)
            for t in threads_check:
                t.join(timeout=4)  # max 4s łącznie na wszystkie (równolegle)
            free_sources = [_fs for _idx, _fs in enumerate(free_sources) if results.get(_idx, True)]
        except Exception:
            pass

        # --- DOŁĄCZENIE NIEFILTROWANYCH DARMOWYCH ŹRÓDEŁ NA KONIEC LISTY ---
        # (poprawka: darmowe na końcu żeby premium miały priorytet przy autoplay)
        try:
            self.sources = self.sources + free_sources
        except Exception:
            pass

        # LEGACY AVI WARNING: lata 50/60/70/80/90
        try:
            if _allow_legacy_avi and self.sources:
                _avi = [s for s in self.sources if _ff_src_has_avi(s)]
                _non_avi = [s for s in self.sources if not _ff_src_has_avi(s)]
                if _avi and not _non_avi:
                    for _s in _avi:
                        _lbl = _s.get("label", "")
                        if "AVI-ONLY" not in _lbl:
                            _s["label"] = "[B][COLOR orange]⚠  AVI-ONLY (ARCHIWUM)[/COLOR][/B] " + _lbl
                    try:
                        xbmcgui.Dialog().notification("FanVodPL", "Znaleziono tylko źródła AVI (archiwalne).", xbmcgui.NOTIFICATION_WARNING, 3500)
                    except Exception:
                        pass
        except Exception:
            pass
        return self.sources


    def filter_duplicates(self):
        filtered = []
        append = filtered.append
        remove = filtered.remove
        for i in self.sources:
            # fflog(f'{i=}')
            if i.get("provider", "").lower() in ['tb7', 'xt7', 'rapideo', 'nopremium', 'twojlimit', 'library', 'biblioteka']:  # te serwisy same usuwają swoje duplikaty
                append(i)  # filtered.append
                # fflog(f'1) dodaję {i.get("provider")=}')
                continue
            larger = False
            if not isinstance(i["url"], str):
                append(i)
                continue
            a = i["url"].lower()
            for sublist in filtered:
                try:
                    # fflog(f'\nanaliza {i["provider"]=}        {i["source"]=} \n  {sublist["provider"]=}  {sublist["source"]=}')
                    if i["source"] == "cloud":
                    # if i["source"] == "cloud" or i["provider"] == "library" or i["provider"] == "biblioteka":  # czy to ok ?
                        # fflog(f'5) {i["provider"]=} {i["source"]=}')
                        break
                    b = sublist["url"].lower()
                    if "magnet:" in a:  # to dla torentów ?
                        if i["hash"].lower() in b:
                            # keep matching hash with longer name, possible more file info
                            if len(sublist["name"]) > len(i["name"]):
                                larger = True
                                break
                            remove(sublist)  # filtered.remove
                            # fflog(f'3) remove {sublist.get("provider")=}', 1)
                            break
                    elif a == b:
                        # fflog(f'\nA==B  {i.get("provider")=}  \n{sublist.get("provider")=}')
                        # fflog(f'\nA==B  {i.get("url")=}  \n{sublist.get("url")=}')
                        if sublist.get("provider") == "library" or sublist.get("provider") == "biblioteka":  # z biblioteki nie usuwamy (ok jak plik, a jak w pobranych jest plik a bibliotece strm ?) Pliki strm nie są uwzględniane, więc ok
                            pass
                            larger = True
                            break
                        remove(sublist)  # filtered.remove
                        # fflog(f'4) remove {sublist.get("provider")=}', 1)
                        break
                except Exception:
                    # fflog_exc(1)
                    pass
            if not larger:  # sublist['name'] len() was larger so do not append
                # fflog(f'2) dodaję {i.get("provider")=}')
                append(i)  # filtered.append

        # log_utils.log("Removed %s duplicate sources from list" % (len(self.sources) - len(filtered)), "module")
        fflog("Removed %s duplicate sources from list" % (len(self.sources) - len(filtered)))
        return filtered


    def sourcesResolve(self, item, info=False, for_resolve=None):
        # fflog(f'{item=}  {info=}  {for_resolve=}',1,1)
        try:
            self.url = url = sub = None
            u = url = item["url"]
            d = item["debrid"]
            direct = item["direct"]
            local = item.get("local", False)
            provider = item["provider"]
            try:
                is_free = not self._is_premium_provider(item)
            except Exception:
                is_free = False
            provider = provider.split(" ")[0]
            fflog(f'{provider=}', 0)

            if not self.sourceDict or not any(provider in p for p in self.sourceDict):
                fflog(f'muszę pobrać scraper dla {provider=}', 0)
                self.getScrapers(provider)
            fflog(f'{self.sourceDict=}', 0)

            call = [i[1] for i in self.sourceDict if i[0] == provider]
            # fflog(f'{call=}')
            if call:
                call = call[0]
            else:
                raise Exception(f'brak wymaganego {provider=}  |  {call=}')

            fflog(f'wywołanie funkcji resolve od scrapera {provider}', 0)
            if for_resolve:
                u = url = call.resolve(url, **for_resolve)
            else:
                u = url = call.resolve(url)

            if url is False:
                return False

            if url is None or (not "://" in str(url) and not local):
                # if provider == 'netflix':
                #    return url
                # if provider == 'external':
                #    return url
                return None
                #raise Exception()

            if not local:
                url = url[8:] if url.startswith("stack:") else url
                urls = []
                subs = []
                fflog(f'{url=}', 0)
                fflog(f'{url.split(" , ")=}', 0)
                for part in url.split(" , "):
                    u = part
                    if not d == "":
                        part = debrid.resolver(part, d)
                    elif not direct:
                        fflog(f'do rozwiązania {u=}', 1)
                        # ewentualne dodatkowe przekształcenie
                        if "|" in u and "$$" not in u and (referer:=dict(parse_qsl(u.rsplit("|", 1)[1])).get("Referer")):
                            u = f'{u.split("|")[0]}$${referer}'
                            fflog(f'link to resolve {u=}', 0)
                        # checking url
                        # subtitle = "$$subs" in u
                        # subtitle = True  # zawsze
                        # fflog(f'check for {subtitle=}', 0)
                        hmf = resolveurl.HostedMediaFile(url=u, include_disabled=True, include_universal=False, subs=True)
                        # fflog(f'{hmf=}', 1)
                        # result
                        if hmf.valid_url():
                            part = hmf.resolve()
                            fflog(f'{part=}', 0)  # może być False, jak resolver nie otworzy adresu
                            if isinstance(part, dict):
                                sub = part.get('subs')
                                fflog(f'    {sub=}', 0)
                                resolved = part.get('url')
                                fflog(f'    {resolved=}', 0)
                                part = resolved
                            else:
                                sub = ""
                            # part = None if part is False else part
                            if not part:
                                if is_free:
                                    # DARMOWE: fallback na bezpośredni URL, bez blokowania odtwarzania
                                    fflog("[FREE RESOLVE] brak wyniku z resolvera – używam URL bezpośredni", 0)
                                    part = u
                                    sub = ""
                                else:
                                    komunikat = f'Resolver nie otrzymał prawidłowego adresu docelowego'
                                    fflog(f'{komunikat}')
                                    komunikat = komunikat.replace("Resolver", "")
                                    control.infoDialog(komunikat, heading="Resolver", icon="WARNING", time=2900, sound=False)
                                    control.sleep(2700)
                                    return  # przydaje się szczególnie, gdy jest włączone autoodtwarzanie
                        else:
                            hosting = re.search(r"^https?://((\w+\.)*(\w+)(\.\w+))/", u)
                            if is_free:
                                # DARMOWE: łagodniejsza reakcja – log + próba bezpośredniego odtworzenia
                                komunikat = f'Resolver nie rozpoznał domeny "{hosting[1] if hosting else u}" (FREE, fallback na URL)'
                                fflog(f'{komunikat}')
                                part = u
                                sub = ""
                            else:
                                komunikat = f'Resolver nie rozpoznał domeny "{hosting[1] if hosting else u}"'
                                # fflog(f'{komunikat} (odtwarzanie może być niemożliwe)')
                                fflog(f'{komunikat}')
                                fflog('odtwarzanie tego źródła nie będzie realizowane')
                                komunikat = komunikat.replace("Resolver", "").replace("domeny ", "domeny \n")
                                control.infoDialog(komunikat, heading="Resolver", icon="WARNING", time=2900, sound=False)
                                control.sleep(2700)
                                return  # przydaje się szczególnie, gdy jest włączone autoodtwarzanie

                    urls.append(part)
                    subs.append(sub)

                url = "stack://" + " , ".join(urls) if len(urls) > 1 else urls[0]  # co to robi? jakaś kolejka?
                sub = "stack://" + " , ".join(subs) if len(subs) > 1 else subs[0] if subs else "" # co to robi? jakaś kolejka?
                fflog(f' {url=}', 0)
                fflog(f' {sub=}', 0)

            if not url:
                fflog(f'{url=}')
                raise Exception(f'{url=}')

            ext = (
                url.split("?")[0]
                .split("&")[0]
                .split("|")[0]
                .rsplit(".")[-1]
                .replace("/", "")
                .lower()
            )
            if ext == "rar":
                fflog(f'{ext=}')
                raise Exception(f'{ext=}')

            # to może być próba sprawdzenia, czy to jest stream hls?
            try:
                headers = url.rsplit("|", 1)[1]
            except Exception:
                headers = ""
            headers = quote_plus(headers).replace("%3D", "=") if " " in headers else headers
            headers = dict(parse_qsl(headers))
            if url.startswith("http") and ".m3u8" in url:  # nie wiem, po co to?
                # fflog(f'dodatkowy test, bo ".m3u8" w nazwie {url=}', 1)
                result = True
                # result = client.request(url.split("|")[0], headers=headers, output="geturl", timeout="20")  # test
                # fflog(f'{result=}', 1)
                if result is None:  # coś poszło nie tak
                    fflog(f'jakiś test dla ".m3u8" w nazwie negatywny')  # tylko co to ostatecznie oznacza?
                    # może to oznacza, że trzeba przez IA odtwarzać?
                    # raise Exception()  # na razie wyłączam to
                    pass
            elif url.startswith("http"):
                pass  # bo poniższe, to dubel
                # self.url = url
                # return url
            else:  # tak sobie dodałem
                pass

            if sub:
                url = (url, sub)

            self.url = url
            return url

        except Exception as e:
            # fflog_exc(1)  # nie włączać tego na produkcję, bo pokazuje błędy resolvera
            # fflog(f'{e=}')
            print(e)
            #err = str(repr(e))  # tak nie było - sam to wymyśliłem, ale to chyba nie wszędzie pasuje
            err = str(e)
            # fflog(f'{err=}')
            if info or err:
                if err:
                    # self.errorForSources(str(repr(e)))  # tak bylo
                    self.errorForSources(err)
                # log(f'[sourcesResolve] {e!r}')  # tak bylo
                # fflog(f'[sourcesResolve] {err}')
            control.sleep(500)
            url = None if url is False else url  # dalej są warunki na is None, a jak pojawia się False, to się coś psuje (szczególnie przy autoodtwarzaniu)
            if url is False:
                return False
            else:
                return
            # czy poniższe, to warunkowe zwrócenie adresu? A może to wywalić?
            """
            # if "ResolverError".lower() not in err.lower():  # tak bylo
            if(
                "ResolverError".lower() not in str(repr(e)).lower()
                and "HTTPError".lower() not in str(repr(e)).lower()
                # and False  # zastanowić się
               ):
                # self.url = url  # czy to może się przydać? czy przeszkodzić? bo jak kod trafił tu, to może oznaczać, że coś poszło nie tak, więc raczej tego nie powinno tu być
                return url  # ale z kolei to po co tu jest zwrócenie adresu zamiast False lub None ? Coś tu nie współgra ze sobą!
                # a co z napisami wówczas ?
            else:
                if err:
                    # control.infoDialog("[CR]" + err, heading="Resolver", icon="ERROR", time=2900, sound=False)
                    pass
            """


    def sourcesDialog(self, items, trash=None, ret_item=False, preselect=-1, auto_select_next_item_to_play=None):
        try:
            labels = [i["label"] for i in items]

            rejected_items = []
            if SHOW_REJECTED_GUI and (not trash):
                rejected_items = json.loads(control.window.getProperty(self.itemRejected)) or []
                if rejected_items:
                    labels += ["[COLOR darkorange][I] *   Źródła odrzucone (przez filtry)  --->[/I][/COLOR]"]

            control.sleep0(100)
            fflog('open select dialog')
            selected = control.selectDialog(labels, 'wybierz źródło', preselect=preselect)
            # selected = control.dialog.select('wybierz źródło', labels, preselect=preselect)
            fflog(f'{selected=} (number of position from list)')

            if selected == -1:
                fflog('anulowanie')
                return "close://"

            if SHOW_REJECTED_GUI and (not trash) and rejected_items:
                if selected == len(labels)-1:
                    url = self.sourcesDialog(rejected_items, trash=True, ret_item=ret_item, auto_select_next_item_to_play=auto_select_next_item_to_play)  # rekurencja
                    if url == "close://":
                        return self.sourcesDialog(items, ret_item=ret_item, auto_select_next_item_to_play=auto_select_next_item_to_play)
                    return url

            next = [y for x, y in enumerate(items) if x > selected]  # następne od wybranego
            prev = [y for x, y in enumerate(items) if x < selected][::-1]  # poprzednie od wybranego

            items = [items[selected]]  # jeden (wybrany)

            auto_select_next_item_to_play = control.setting("auto.select.next.item.to.play") == "true" if auto_select_next_item_to_play is None else auto_select_next_item_to_play
            # if control.setting("auto.select.next.item.to.play") == "true":
            if auto_select_next_item_to_play:
                items = [i for i in items + next + prev][:40]  # wybrany plus poprzednie i następne
                # fflog(f'{len(items)}  {items=}')
            else:
                return self.sourcesDirect(items, ret_item=ret_item) , selected , trash  # tylko wybrany

            header = control.addonInfo("name")
            header2 = header.upper()

            # progressDialog = None
            progressDialog = (
                control.progressDialog
                if control.setting("progress.dialog") == "0"
                else control.progressDialogBG
            )

            progressDialog.create(header, "")
            progressDialog.update(0)
            control.sleep(100)

            # focus_panel_id = control.getCurrentViewId()  # focus_panel_id
            # fflog(f"{focus_panel_id=}", 1,1)

            block = None
            import threading
            monitor = control.monitor

            for i in range(len(items)):
                try:
                    # fflog(f'{i=}  {items[i].get("label")=}',1,1)

                    if items[i]["source"] == block:
                        raise Exception()

                    w = threading.Thread(target=self.sourcesResolve, args=(items[i],))
                    w.start()

                    try:
                        if progressDialog.iscanceled():
                            break
                        progressDialog.update(int((100 / float(len(items))) * i),
                            str(items[i]["label"]) + "\n" + str(" "),
                        )
                    except Exception:
                        if progressDialog:
                            progressDialog.update(int((100 / float(len(items))) * i),
                                str(header2) + "\n" + str(items[i].get("label") or ""),
                            )

                    m = ""

                    for x in range(3600):
                        try:
                            if monitor.abortRequested():
                                return sys.exit()
                            if progressDialog.iscanceled():
                                return progressDialog.close()
                        except Exception:
                            pass

                        k = control.condVisibility("Window.IsActive(virtualkeyboard)")
                        if k:
                            m += "1"
                            m = m[-1]
                        if (not w.is_alive() or x > 60) and not k:
                            break
                        k = control.condVisibility("Window.IsActive(yesnoDialog)")
                        if k:
                            m += "1"
                            m = m[-1]
                        if (not w.is_alive() or x > 60) and not k:
                            break
                        time.sleep(0.5)

                    for x in range(10):
                        try:
                            if monitor.abortRequested():
                                return sys.exit()
                            if progressDialog.iscanceled():
                                return progressDialog.close()
                        except Exception:
                            pass

                        if m == "":
                            break
                        if not w.is_alive():
                            break
                        time.sleep(0.5)

                    if w.is_alive():
                        block = items[i]["source"]

                    if self.url is None:
                        raise Exception()

                    self.selectedSource = items[i]["label"]

                    try:
                        progressDialog.close()
                    except Exception:
                        pass

                    control.execute("Dialog.Close(virtualkeyboard)")
                    control.execute("Dialog.Close(yesnoDialog)")
                    # time.sleep(0.1)
                    control.sleep(100)
                    if not ret_item:
                        return self.url
                    else:
                        return [self.url, items[i]]

                except Exception:
                    pass

            try:
                progressDialog.close()
            except Exception:
                pass

        except Exception as e:
            fflog_exc(1)
            try:
                progressDialog.close()
            except Exception:
                pass
            print("Error %s" % str(e), log_utils.LOGINFO)
            return "close://"


    def sourcesDirect(self, items, ret_item=False):

        filtered = [i  for i in items  if i["source"].lower() in self.hostcapDict and i["debrid"] == ""]
        items = [i for i in items if i not in filtered]

        filtered = [i  for i in items  if i["source"].lower() in self.hostblockDict and i["debrid"] == ""]
        items = [i for i in items if i not in filtered]

        items = [i  for i in items  if ("autoplay" in i and i["autoplay"]) or "autoplay" not in i]

        if control.setting("autoplay.sd") == "true":
            items = [i  for i in items  if i["quality"] not in ["4K", "1440p", "1080p", "1080i", "HD", "720p"]]

        header = control.addonInfo("name")
        header2 = header.upper()

        progressDialog = None
        try:
            control.sleep(1000)
            progressDialog = (
                control.progressDialog
                if control.setting("progress.dialog") == "0"
                else control.progressDialogBG
            )

            progressDialog.create(header, "")
            progressDialog.update(0)
            control.sleep(100)
        except Exception:
            fflog_exc(1)
            pass

        monitor = control.monitor

        # focus_panel_id = control.getCurrentViewId()  # focus_panel_id
        # fflog(f"{focus_panel_id=}", 1,1)

        u = None

        for i in range(len(items)):

            # fflog(f'{i=}  {items[i].get("label")=}',1,1)

            try:
                if progressDialog.iscanceled():
                    break
                progressDialog.update(int((100 / float(len(items))) * i),
                    str(items[i]["label"]) + "\n" + str(" "),
                )
            except Exception:
                if progressDialog:
                    progressDialog.update(int((100 / float(len(items))) * i),
                        str(header2) + "\n" + str(items[i].get("label") or ""),
                    )

            try:
                if monitor.abortRequested():
                    return sys.exit()
                # fflog(f'{i=}  {items[i]=}',1,1)
                if items[i].get("provider") == "pobrane" or items[i].get("source") == "pobrane":
                    url = items[i].get("url") or None
                elif items[i].get("isFolder"):
                    url = None
                    url = items[i].get("url")  # test
                    # fflog(f'Na ten moment taka pozycja nie jest obsługiwana (wywołanie folderu, gdy w okienku wybieramy źródło do odtworzenia) |  {items[i]=}')
                    # control.infoDialog("Na ten moment taka pozycja nie jest obsługiwana", sound=False, icon="INFO")
                    # control.sleep(500)
                else:
                    url = self._ff_resolve_with_timeout(items[i], 20000)  # sprawdzenie adresu url z limitem czasu
                # Jeśli Anuluj -> close://, potraktuj jak brak URL i spróbuj następny
                if isinstance(url, str) and url.startswith('close://'):
                    url = None
                fflog(f'{u=} {url=}', 0)
                """ tak było, ale wówczas pobiera niepotrzebnie następne źródło
                if u is None:
                    u = url
                else:
                    break
                """
                # if url is None:  # a jeszcze może być False
                if not url:
                    if (i+1) < len(items):
                        control.sleep(500)
                        control.infoDialog(f"próbuję następne źródło ({i+2})", icon="INFO", sound=False)
                        fflog(f"próbuję następne źródło ({i+2}/{len(items)})",1,1)
                        control.sleep(500)
                    continue
                else:
                    u = url
                    break
            except Exception:
                pass

        try:
            progressDialog.close()
        except Exception:
            pass

        if not u:
            i = -1

        if not ret_item:
            return u  # adres url źródła
        else:
            if items:
                return [u, items[i]]
            else:  # taki problem powstał mi przy autoplay z contextmenu
                return None


    def errorForSources(self, err=""):
        # fflog(f'pojawił się jakiś problem przy wywołaniu elementu do odtwarzania (nie określono adresu url streamu, ale mogło też nastąpić anulowanie akcji) {err=}')
        err = "[CR]" + str(err) if err else ""
        c = 0
        while control.condVisibility('Window.IsActive(notification)') and c < (5 * 2):
            c += 1
            control.sleep(200)
        control.infoDialog(control.lang(32401) + err, sound=False, icon="INFO")  # Brak źródeł
        fflog(control.lang(32401) + err.replace("[CR]", " - "))
        control.sleep(2800)


    def getLanguage(self):
        langDict = {
            "English": ["en"],
            "German": ["de"],
            "German+English": ["de", "en"],
            "French": ["fr"],
            "French+English": ["fr", "en"],
            "Portuguese": ["pt"],
            "Portuguese+English": ["pt", "en"],
            "Polish": ["pl"],
            "Polish+English": ["pl", "en"],
            "Korean": ["ko"],
            "Korean+English": ["ko", "en"],
            "Russian": ["ru"],
            "Russian+English": ["ru", "en"],
            "Spanish": ["es"],
            "Spanish+English": ["es", "en"],
            "Greek": ["gr"],
            "Italian": ["it"],
            "Italian+English": ["it", "en"],
            "Greek+English": ["gr", "en"],
        }
        name = control.setting("providers.lang")
        return langDict.get(name, ["pl"])


    def getIds(self, content, imdb, tmdb=None, tvdb=None):
        if imdb and imdb not in ['None', '0']:
            type = 'imdb'
            type_id = imdb
        elif tmdb and tmdb not in ['None', '0']:
            type = 'tmdb'
            type_id = tmdb
        elif tvdb and tvdb not in ['None', '0']:
            type = 'tvdb'
            type_id = tvdb
        else:
            return
        ids = trakt.IdLookup(content, type, type_id)
        return ids


    def getLocalTitle(self, title, imdb, tvdb, content, ids=None, tmdb=None, trakt_id=None):
        lang = self._getPrimaryLang()
        if not lang:
            return title

        if not trakt_id:
            if not ids:
                imdb = None if imdb in ['None', '0'] else imdb
                tvdb = None if tvdb in ['None', '0'] else tvdb
                tmdb = None if tmdb in ['None', '0'] else tmdb
                id = imdb
            else:
                id = None

            if not id:
                if tmdb or tvdb:
                    ids = self.getIds(content, imdb, tmdb, tvdb)

            if ids:
                id = ids.get("trakt") or ids.get("slug")
        else:
            id = trakt_id

        if id:
            if content == "movie":
                t = trakt.getMovieTranslation(id, lang)
            else:
                t = trakt.getTVShowTranslation(id, lang)
        else:
            t = None

        return t or title


    def getAliasTitles(self, id, localtitle, content):
        lang = self._getPrimaryLang()
        try:
            t = trakt.getMovieAliases(id) if content == "movie" else trakt.getTVShowAliases(id)

            if not t:
                t = []
            else:
                t = [
                     i
                     for i in t
                     if (
                         # i.get("country", "").lower() in [lang, "", "us", "en", "uk", "gb", "au", "pl", "original"]
                         not self.czy_litery_krzaczki(i.get("title", ""))
                         and i.get("title", "").lower() != localtitle.lower()
                        )
                ]

            fflog("\nALIASY (z Trakt):\n "+("\n"+chr(32)).join(map(repr, t)), 0)
            return t
        except Exception:
            return []


    def _getPrimaryLang(self):
        langDict = {
            "English": "en",
            "German": "de",
            "German+English": "de",
            "French": "fr",
            "French+English": "fr",
            "Portuguese": "pt",
            "Portuguese+English": "pt",
            "Polish": "pl",
            "Polish+English": "pl",
            "Korean": "ko",
            "Korean+English": "ko",
            "Russian": "ru",
            "Russian+English": "ru",
            "Spanish": "es",
            "Spanish+English": "es",
            "Italian": "it",
            "Italian+English": "it",
            "Greek": "gr",
            "Greek+English": "gr",
        }
        name = control.setting("providers.lang")
        lang = langDict.get(name)
        return lang


    def getTitle(self, title):
        title = cleantitle.normalize(title)
        return title


    def getScrapers(self, provider="", language=None):
        if not provider:
            fflog(f'pobieranie listy dostępnych scraperów', 0)  # na podstawie plików na dysku (folder pl i en)
        else:
            fflog(f'wczytanie scrapera {provider}', 0)
        from resources.lib.sources import sources
        self.sourceDict = sources(provider, language)
        fflog(f'{len(self.sourceDict)=}', 0)


    def getConstants(self):
        self.itemProperty = "plugin.video.fanvodpl.container.items"
        self.itemRejected = "plugin.video.fanvodpl.container.itemsRejected"
        self.metaProperty = "plugin.video.fanvodpl.container.meta"

        try:
            self.hostDict = resolveurl.relevant_resolvers(order_matters=True)
            self.hostDict = [i.domains for i in self.hostDict if "*" not in i.domains]
            self.hostDict = [i.lower() for i in reduce(lambda x, y: x + y, self.hostDict)]
            self.hostDict = [x for y, x in enumerate(self.hostDict) if x not in self.hostDict[:y]]
        except Exception:
            self.hostDict = []

        self.hostprDict = [
            "1fichier.com",
            "oboom.com",
            "rapidgator.net",
            "rg.to",
            "uploaded.net",
            "uploaded.to",
            "ul.to",
            "filefactory.com",
            "nitroflare.com",
            "turbobit.net",
            "uploadrocket.net",
        ]

        self.hostcapDict = [
            "hugefiles.net",
            "kingfiles.net",
            "openload",
            "openload.io",
            "openload.co",
            "oload.tv",
            "thevideo.me",
            "vidup.me",
            "streamin.to",
            "torba.se",
            "flashx",
            "flashx.tv",
        ]

        self.hosthqDict = [
            "gvideo",
            "google.com",
            "openload.io",
            "openload.co",
            "oload.tv",
            "thevideo.me",
            "rapidvideo.com",
            "raptu.com",
            "filez.tv",
            "uptobox.com",
            "uptobox.com",
            "uptostream.com",
            "xvidstage.com",
            "streamango.com",
        ]

        self.hostblockDict = []


    def czy_litery_krzaczki(self, s, mode=0):
        from unicodedata import category

        def _czy_krzaczek(c):
            v = ord(c or ' ')
            # print(c, hex(v), v, (category(c)))  # debug
            if not (c and category(c)[0] == 'L'):  # if not a letter
                return ""
            if 0x20 <= v < 0x370:
                return False
            if 0x370 <= v <= 0x3ff:
                return 'gr'
            if 0x400 <= v <= 0x52f:
                return "rus"
            return True

        s = s.strip()
        if not len(s):
            return None

        if mode == 0:  # whole text (only letters)
            r = [_czy_krzaczek(l) for l in s if category(l)[0] == 'L']
        elif mode == 2:
            r = [_czy_krzaczek(s[i]) for i in [0, -1]]  # first and last letter
        if r.count("gr"):
            return "gr"
        if r.count("rus"):
            return "rus"
        return any(r)