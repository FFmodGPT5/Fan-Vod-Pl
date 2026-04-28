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

import base64
import codecs
import gzip
import json
import os
import re
import sys
from urllib.parse import quote_plus, unquote_plus, parse_qsl, urlencode

import six
import xbmc

import xbmcaddon
import threading
import time
try:
    import xbmcvfs  # Kodi VFS helpers
except Exception:
    xbmcvfs = None

from ptw.libraries import bookmarks

try:
    from ptw.libraries import trace_log as _tlog
except Exception:
    _tlog = None

def _tr(event, **kw):
    try:
        if _tlog: _tlog.player_event('player.py', event, **kw)
    except Exception:
        pass
from ptw.libraries import cleantitle
from ptw.libraries import control
from ptw.libraries import playcount
from ptw.libraries import trakt
from ptw.libraries.source_utils import get_kodi_version

from ptw.libraries.log_utils import log, fflog
from ptw.debug import log_exception, fflog_exc


def _ff_should_skip_foreign_audio_guard(content, year) -> bool:
    """Wyłącza foreign-audio STOP/cache dla starych tytułów.
    - odcinki seriali: 1950–2015
    - filmy: 1950–2005
    """
    try:
        y = int(year)
    except Exception:
        return False
    if content == 'episode':
        return 1950 <= y <= 2015
    return 1950 <= y <= 2005


def _ff_is_ai_lektor_audio_label(label) -> bool:
    if label is None:
        return False
    try:
        raw = six.ensure_str(label).strip().lower()
    except Exception:
        raw = str(label).strip().lower()
    if not raw:
        return False
    compact = re.sub(r'[^a-z0-9ąćęłńóśźż]+', '', raw, flags=re.IGNORECASE)
    if 'lektorai' in compact or 'ailektor' in compact:
        return True
    normalized = re.sub(r'[^a-z0-9ąćęłńóśźż]+', ' ', raw, flags=re.IGNORECASE)
    tokens = {tok for tok in normalized.split() if tok}
    return 'lektor' in tokens and 'ai' in tokens


# ZMIANA (2026-04) [PATCH]: lista hostów dla których pomijamy cały mechanizm foreign-audio guard.
# POWOD: hosty premium/nopremium/rapideo/twojlimit/xt7/tb7 mogą zwracać pliki z inną ścieżką audio
# niż PL/EN (np. oryginalną) mimo że lektor polski jest nałożony osobno — blokada fałszywie zatrzymywała odtwarzanie.
# NIE ZMIENIAC: lista dotyczy wyłącznie pre-play i post-play audio guard; nie wyłącza innych zabezpieczeń (lowres, dead, TwojPlik antyshare).
_FF_NO_AUDIO_BLOCK_HOSTS = {'premium', 'nopremium', 'rapideo', 'twojlimit', 'xt7', 'tb7'}

# ZMIANA (2026-04) [PATCH]: wykrywanie AI lektora w opisie linku / źródła działa osobno od nazw ścieżek audio z Kodi.
# POWOD: część plików z „PL.Ai / Lektor AI” zwraca w getAvailableAudioStreams() tylko techniczne etykiety typu „ac3 5.1(side)”, więc sam odczyt ścieżek audio nie wystarcza do bezpiecznego bypassu.
# NIE ZMIENIAC: ten helper ma służyć wyłącznie do wyciszenia okna foreign-audio dla źródeł AI lektora; nie wolno rozszerzać go na zwykłe linki bez wyraźnych wzorców AI.
def _ff_has_ai_lektor_source_context(*values) -> bool:
    patterns = (
        'lektor ai', 'ai lektor', 'lektor-ai', 'ai-lektor',
        'lektor_ai', 'ai_lektor', 'lektorai', 'ailektor',
        '.pl.ai', ' pl ai', '.plai', 'pl-ai', 'pl_ai',
    )
    for value in values:
        if value is None:
            continue
        try:
            raw = six.ensure_str(value)
        except Exception:
            raw = str(value)
        raw = raw.strip().lower()
        if not raw:
            continue
        compact = re.sub(r'[^a-z0-9ąćęłńóśźż]+', '', raw, flags=re.IGNORECASE)
        if 'lektorai' in compact or 'ailektor' in compact or 'plai' in compact:
            return True
        normalized = raw.replace('%20', ' ')
        if any(pat in normalized for pat in patterns):
            return True
    return False


# ZMIANA (2026-04) [PATCH]: helpery TwojPlik do fallbacku naglowkow URL na retry (all devices).
# POWOD: stare linki konta TwojPlik potrafia nie przejsc demux i wymagaja ponownej proby z bezpiecznymi naglowkami.
# NIE ZMIENIAC: fallback ma byc ograniczony do kontekstu TwojPlik, aby nie ruszac innych hostow.
_FF_ANDROID_WEB_UA = (
    "Mozilla/5.0 (Linux; Android 13; SM-S911B) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Mobile Safari/537.36"
)
_FF_DESKTOP_WEB_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


def _ff_is_android_runtime() -> bool:
    try:
        if xbmc.getCondVisibility('System.Platform.Android'):
            return True
    except Exception:
        pass
    try:
        return 'android' in six.ensure_str(sys.platform).lower()
    except Exception:
        return False


def _ff_pick_twojplik_retry_ua() -> str:
    if _ff_is_android_runtime():
        return _FF_ANDROID_WEB_UA
    return _FF_DESKTOP_WEB_UA

def _ff_is_twojplik_context(hosting, source_url=None) -> bool:
    host = str(hosting or '').strip().lower()
    if host in ('twojplik', 'twojplik.to', 'plik.to', 'plikto'):
        return True
    src = str(source_url or '').strip().lower()
    return 'twojplik.to/' in src or 'plik.to/' in src


def _ff_build_android_twojplik_fallback(url, cookie_header='', user_agent=None):
    if not url:
        return None
    raw_url = str(url).strip()
    if not raw_url:
        return None
    if '|' in raw_url:
        stream_url, raw_headers = raw_url.split('|', 1)
    else:
        stream_url, raw_headers = raw_url, ''
    if not stream_url.startswith('http'):
        return None
    try:
        pairs = parse_qsl(raw_headers, keep_blank_values=True) if raw_headers else []
    except Exception:
        pairs = []
    fallback_ua = str(user_agent or _ff_pick_twojplik_retry_ua()).strip() or _ff_pick_twojplik_retry_ua()

    out = []
    changed = False
    has_ua = False
    has_referer = False
    has_origin = False
    has_cookie = False
    has_cache_control = False
    has_pragma = False

    for key, value in pairs:
        lkey = (key or '').strip().lower()
        v = value or ''
        if lkey == 'user-agent':
            has_ua = True
            _suspicious = any(x in v.lower() for x in ('sosnf-', 'python-urllib', 'curl/', 'okhttp/', 'dalvik'))
            if _suspicious or v.strip() != fallback_ua:
                v = fallback_ua
                changed = True
        elif lkey == 'referer':
            has_referer = True
            if 'twojplik.to' not in v.lower():
                v = 'https://twojplik.to/'
                changed = True
        elif lkey == 'origin':
            has_origin = True
            if 'twojplik.to' not in v.lower():
                v = 'https://twojplik.to'
                changed = True
        elif lkey == 'cookie':
            has_cookie = True
            if cookie_header and v.strip() != cookie_header.strip():
                v = cookie_header
                changed = True
        elif lkey == 'cache-control':
            has_cache_control = True
            if 'no-cache' not in v.lower():
                v = 'no-cache'
                changed = True
        elif lkey == 'pragma':
            has_pragma = True
            if 'no-cache' not in v.lower():
                v = 'no-cache'
                changed = True
        out.append((key, v))

    if not has_ua:
        out.append(('User-Agent', fallback_ua))
        changed = True
    if not has_referer:
        out.append(('Referer', 'https://twojplik.to/'))
        changed = True
    if not has_origin:
        out.append(('Origin', 'https://twojplik.to'))
        changed = True
    if not has_cache_control:
        out.append(('Cache-Control', 'no-cache'))
        changed = True
    if not has_pragma:
        out.append(('Pragma', 'no-cache'))
        changed = True
    # ZMIANA (2026-04) [PATCH]: fallback moze dopiac Cookie sesyjne do URL odtwarzania.
    # POWOD: na czesci telefonow TwojPlik zwraca strone antyshare bez ciasteczka sesji.
    # NIE ZMIENIAC: Cookie dodawac tylko gdy mamy wartosc z warmup, bez twardego hardcodu.
    if cookie_header and not has_cookie:
        out.append(('Cookie', cookie_header))
        changed = True

    if not changed:
        return None
    return f'{stream_url}|{urlencode(out, doseq=True)}'


def _ff_try_warmup_twojplik_cookie(source_url, stream_url=None, user_agent=None):
    try:
        import http.cookiejar as _cookiejar
        import urllib.request as _urlreq
    except Exception:
        return ''

    source_url = str(source_url or '').strip()
    if not source_url.startswith('http'):
        return ''

    ua = str(user_agent or _ff_pick_twojplik_retry_ua()).strip() or _ff_pick_twojplik_retry_ua()
    cookiejar = _cookiejar.CookieJar()
    opener = _urlreq.build_opener(_urlreq.HTTPCookieProcessor(cookiejar))
    targets = [source_url]
    stream_url = str(stream_url or '').strip()
    if stream_url.startswith('http'):
        targets.append(stream_url)

    # ZMIANA (2026-04) [PATCH]: warmup cookie sesji TwojPlik przed retry odtwarzania.
    # POWOD: czesc urzadzen Android dostaje HTML antyshare bez cookie sesyjnego i demuxer nie rozpoznaje formatu.
    # NIE ZMIENIAC: to tylko best-effort; blad sieciowy nie moze przerywac odtwarzania ani crashowac playera.
    base_headers = [
        ('User-Agent', ua),
        ('Accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'),
        ('Accept-Language', 'pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7'),
        ('Referer', 'https://twojplik.to/'),
    ]
    for target in targets:
        try:
            req = _urlreq.Request(target, headers=dict(base_headers))
            with opener.open(req, timeout=6) as _resp:
                _resp.read(0)
        except Exception:
            pass

    cookies = []
    for ck in cookiejar:
        try:
            domain = (ck.domain or '').lower()
            if 'twojplik.to' in domain or 'plik.to' in domain:
                cookies.append(f'{ck.name}={ck.value}')
        except Exception:
            continue
    if not cookies:
        return ''
    # dict.fromkeys zachowuje kolejnosc i usuwa duplikaty.
    return '; '.join(dict.fromkeys(cookies))



def _ff_parse_kodi_play_url(play_url):
    raw_url = str(play_url or '').strip()
    if not raw_url:
        return '', {}
    if '|' in raw_url:
        stream_url, raw_headers = raw_url.split('|', 1)
    else:
        stream_url, raw_headers = raw_url, ''
    headers = {}
    if raw_headers:
        try:
            for key, value in parse_qsl(raw_headers, keep_blank_values=True):
                if key:
                    headers[key] = value
        except Exception:
            pass
    return stream_url, headers


def _ff_probe_twojplik_antyshare(play_url, timeout=6):
    try:
        import urllib.request as _urlreq
    except Exception:
        return False

    stream_url, headers = _ff_parse_kodi_play_url(play_url)
    stream_url = str(stream_url or '').strip()
    if not stream_url.startswith('http'):
        return False
    low_stream_url = stream_url.lower()
    if 'twojplik.to' not in low_stream_url and 'plik.to' not in low_stream_url:
        return False

    def _pick_header(*names):
        lowered = {str(k).lower(): v for k, v in headers.items()}
        for name in names:
            val = lowered.get(str(name).lower())
            if val:
                return str(val).strip()
        return ''

    req_headers = {
        'User-Agent': _pick_header('User-Agent') or _ff_pick_twojplik_retry_ua(),
        'Referer': _pick_header('Referer') or 'https://twojplik.to/',
        'Origin': _pick_header('Origin') or 'https://twojplik.to',
        'Accept': _pick_header('Accept') or 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': _pick_header('Accept-Language') or 'pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7',
        'Range': 'bytes=0-4095',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
    }
    cookie = _pick_header('Cookie')
    if cookie:
        req_headers['Cookie'] = cookie

    try:
        req = _urlreq.Request(stream_url, headers=req_headers)
        with _urlreq.urlopen(req, timeout=timeout) as resp:
            ctype = six.ensure_str(resp.headers.get('Content-Type') or '', errors='ignore').lower()
            body = resp.read(8192) or b''
    except Exception:
        return False

    try:
        text_body = six.ensure_str(body, errors='ignore').lower()
    except Exception:
        text_body = str(body).lower()

    anti_patterns = (
        'antyshare',
        'ochrona antyshare',
        'nie mozesz korzystac z directlinka',
        'nie mo?esz korzysta? z directlinka',
        'operatora sieci',
        'operator sieci',
    )
    if any(pattern in text_body for pattern in anti_patterns):
        return True

    is_html = ('text/html' in ctype) or ('<html' in text_body) or ('<!doctype html' in text_body)
    if is_html and ('twojplik' in text_body or 'plik.to' in text_body):
        if 'directlink' in text_body or 'ochrona' in text_body or 'operator' in text_body:
            return True
    return False


def _ff_get_source_item_from_argv():
    # 1) Prefer source from argv (when available in folder sources flow).
    try:
        params2 = dict(parse_qsl(sys.argv[2][1:]))
        source = params2.get('source')
        if source:
            parsed = json.loads(source)
            if isinstance(parsed, list):
                parsed = parsed[0] if parsed else None
            if isinstance(parsed, dict):
                return parsed
    except Exception:
        pass

    # 2) Fallback: source item stored by sources.py in window property.
    try:
        import xbmcgui as _xgui_si
        raw = _xgui_si.Window(10000).getProperty('FanVodPL.source_item_json') or ''
        if raw:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                parsed = parsed[0] if parsed else None
            if isinstance(parsed, dict):
                return parsed
    except Exception:
        pass
    return None


def _ff_try_refresh_twojplik_url_from_source(source_item, source_orig_url=None):
    if not isinstance(source_item, dict):
        return None
    try:
        source_copy = dict(source_item)
    except Exception:
        return None

    try:
        host_hint = source_copy.get('source') or source_copy.get('provider') or ''
    except Exception:
        host_hint = ''
    if not _ff_is_twojplik_context(host_hint, source_orig_url or source_copy.get('url')):
        return None

    kwargs = {}
    try:
        provider = str(source_copy.get('provider') or '').strip().lower()
    except Exception:
        provider = ''
    if provider in ('tb7', 'xt7'):
        kwargs.setdefault('for_resolve', {}).update({'specific_source_data': source_copy})
    if isinstance(source_copy.get('for_resolve'), dict):
        kwargs.setdefault('for_resolve', {}).update(source_copy['for_resolve'])

    try:
        from ptw.libraries.sources import sources as _ff_sources_class
        resolver = _ff_sources_class()
        if kwargs:
            refreshed = resolver.sourcesResolve(source_copy, **kwargs)
        else:
            refreshed = resolver.sourcesResolve(source_copy)
    except Exception:
        fflog_exc(1)
        return None

    if isinstance(refreshed, (list, tuple)) and refreshed:
        refreshed = refreshed[0]

    refreshed = str(refreshed or '').strip()
    if not refreshed or not refreshed.startswith('http'):
        return None
    return refreshed


class player(xbmc.Player):
    def __init__(self):
        super().__init__()
        self.currentTime = None
        self.totalTime = None
        self.runtime = None  # traktowy totaltime
        self.content = None
        self.title = None
        self.localtitle = None
        self.englishtitle = None
        self.originaltitle = None
        self.tvshowtitle = None
        self.year = None
        self.name = None
        self.season = None
        self.episode = None
        self.DBID = None
        self.imdb = None
        self.tvdb = None
        self.tmdb = None
        self.ids = None
        self.offset = None
        self.is_active = True
        self.playback_started = None
        self.offsetSource = None
        self.watched_before = None
        self.addRating_in_progress = None


        # --- MAX SAFE MODE (stability-first) ---
        # On some devices (notably Android/Exynos) certain xbmc.Player methods can cause native crashes.
        # In MAX_SAFE_MODE we keep callbacks extremely lightweight and avoid risky calls.
        self._max_safe_mode = True
        self._ended = False
        self._error = False
        self._stop_in_progress = False
        self._stop_cleanup_done = False
        self._last_stop_ts = 0.0
        self._audio_renderer_failed = False
        self._bookmark_touch_done = False
        self._last_local_progress_save = 0.0
        self._source_group = None
        self._source_quality = ""
        self._from_rejected_folder = False
        self._av_started = False
        # ZMIANA (2026-04) [PATCH]: pole na alternatywny URL dla drugiej proby odtwarzania.
        # POWOD: retry na Androidzie moze wymagac innego zestawu naglowkow niz pierwsza proba.
        # NIE ZMIENIAC: pierwsza proba ma dalej uzywac oryginalnego URL, fallback tylko dla retry.
        self._retry_play_url = None
        self._source_item_for_refresh = None
        self._twojplik_antyshare_detected = False
        self._twojplik_same_stream_after_refresh = False

    def _refresh_rejected_folder_flag(self):
        try:
            found = False
            candidates = []
            try:
                candidates.append(six.ensure_str(sys.argv[2]))
            except Exception:
                pass
            try:
                candidates.append(six.ensure_str(control.infoLabel('Container.FolderPath') or ''))
            except Exception:
                pass
            try:
                candidates.append(six.ensure_str(xbmc.getInfoLabel('Container.FolderPath') or ''))
            except Exception:
                pass

            for candidate in candidates:
                if candidate and 'trash=1' in candidate:
                    found = True
                    fflog(f'[REJECTED_BYPASS] trash=1 detected: {candidate}', 1)
                    break
            self._from_rejected_folder = found
            return found
        except Exception:
            fflog_exc(1)
        return False

    # większość wywowałań tej funkcji wstawia zamiast tmdb "tvdb"
    def run(self, title, year, season, episode, imdb, tvdb, tmdb, url, subs=None, meta=None, handle=None, hosting=None, customPlayer=None):

        if customPlayer is None:
            params2 = dict(parse_qsl(sys.argv[2][1:]))
            # fflog(f'{params2=}', 1)
            source = params2.get("source")
            try:
                source = json.loads(source)  # to się tylko sprawdzi, gdy źródła w folderze (nie w okienku)
                source = source[0]  # tak dziwnie to jest stworzone (źródło w liście)
                customPlayer = source.get("customPlayer")
            except Exception:
                # fflog_exc(1)  # bo będzie alert w logu, gdy zmienna nieustawiona i źródła w okienku
                pass
        fflog(f'{customPlayer=}', 1)
        # customPlayer = True  # test only

        try:
            # te 2 linijki muszą być, bo inaczej Kodi potrafi się zawiesić
            control.execute('Dialog.Close(notification,true)')
            control.sleep0(200)
            # Reset transient flags per-run. Player object can be reused across plays.
            # ZMIANA (2026-04) [PATCH]: zapis aktualnego hosta do self._hosting na potrzeby bypasów audio guard.
            # POWOD: _check_audio_langs_after_start() jest metodą asynchroniczną i nie ma dostępu do lokalnej zmiennej hosting z run(); self._hosting przenosi tę informację.
            # NIE ZMIENIAC: musi być resetowane na początku każdego run() żeby nie przenosić hosta z poprzedniego odtworzenia.
            self._hosting = str(hosting or '').strip().lower()
            self._from_rejected_folder = False
            self._av_started = False
            self._stop_in_progress = False
            # ZMIANA (2026-04) [PATCH]: reset fallback URL na poczatku kazdego run().
            # POWOD: obiekt player bywa reused miedzy odtworzeniami i nie moze przenosic fallbacku.
            # NIE ZMIENIAC: fallback URL ma dotyczyc tylko biezacego odtworzenia.
            self._retry_play_url = None
            self._source_item_for_refresh = _ff_get_source_item_from_argv()
            self._twojplik_antyshare_detected = False
            self._twojplik_same_stream_after_refresh = False
            try:
                if self._source_item_for_refresh:
                    fflog('[TWOJPLIK][HARD_REFRESH] source item ready (argv/window)', 1)
                else:
                    fflog('[TWOJPLIK][HARD_REFRESH] source item missing (argv/window)', 1)
            except Exception:
                pass
            self._refresh_rejected_folder_flag()

            if not customPlayer:
                fflog("przygotowywanie do odtwarzania")
                control.dialog.notification('FanVodPL', 'uruchamianie odtwarzania ...', time=1500, sound=False)
                control.sleep(400)

                self.currentTime = 0
                self.totalTime = 0
                self.runtime = 0
                self.playback_started = None

                self.content = "movie" if not season or not episode else "episode"

                localtitle = originalname = tvshowtitle = ""
                if isinstance(title, tuple):
                    title, localtitle, originalname, tvshowtitle = title
                self.englishtitle = title  # angielski
                self.localtitle = localtitle
                self.originaltitle = originalname
                self.tvshowtitle = tvshowtitle
                self.title = title = localtitle or title
                self.year = year
                self.name = (
                    quote_plus(title) + quote_plus(" (%s)" % year)
                    if self.content == "movie"
                    else quote_plus(title) + quote_plus(" S%01dE%01d" % (int(season), int(episode)))
                )
                self.name = unquote_plus(self.name)  # to jakieś awaryjne do wyszukania informacji z bilioteki, ale jak tytuł jest w meta, to do playera idzie z meta

                self.season = "%01d" % int(season) if self.content == "episode" else None
                self.episode = "%01d" % int(episode) if self.content == "episode" else None

                self.DBID = None  # jakiś reset zmiennej chyba

                self.imdb = imdb if not imdb is None else "0"
                self.tmdb = tmdb if not tmdb is None else "0"
                self.tvdb = tvdb if not tvdb is None else "0"

                #self.ids = {"imdb": self.imdb, "tmdb": self.tmdb}  # brak tvdb
                self.ids = {"imdb": self.imdb, "tvdb": self.tvdb, "tmdb": self.tmdb}
                self.ids = dict((k, v) for k, v in self.ids.items() if not v == "0")  # znacznik dla wtyczki script.trakt, aby mogła rozpoznawać filmy

                self.offset, self.runtime, self.offsetSource = bookmarks.get(self.content, imdb, season, episode)

                #fflog(f"{self.imdb=} {self.tmdb=} {self.ids=} {self.offset=}", 1)
                fflog(f"{self.ids=}   {self.offset=}   {self.offsetSource=}   {self.content=}  {imdb=}  {season=}  {episode=}", 1)

                # --- RESUME DIALOG ---
                self._resume_from = 0
                if self.offset and float(self.offset) > 5:
                    try:
                        import xbmcgui as _xgui
                        _sec = int(float(self.offset))
                        _h, _rem = divmod(_sec, 3600)
                        _m, _s = divmod(_rem, 60)
                        _time_str = '%d:%02d:%02d' % (_h, _m, _s) if _h else '%d:%02d' % (_m, _s)
                        _res = _xgui.Dialog().yesno(
                            'FanVodPL',
                            'Kontynuować od [B]%s[/B]?' % _time_str,
                            nolabel='Od początku',
                            yeslabel='Kontynuuj',
                        )
                        self._resume_from = float(self.offset) if _res else 0
                        fflog(f'resume_dialog: {_res=}  {self._resume_from=}', 1)
                    except Exception:
                        fflog_exc(1)
                # --- END RESUME DIALOG ---

                poster, thumb, fanart, clearlogo, clearart, discart, keyart, landscape, banner, icon, characterart, meta = self.getMeta(meta)
                # fflog(f'\n   {poster=} \n    {thumb=} \n   {fanart=} \n{clearlogo=} \n {clearart=} \n  {discart=} \n   {keyart=} \n{landscape=} \n   {banner=} \n     {icon=} \n{characterart=} \n{meta=}', 1)

                if isinstance(url, tuple):
                    url, subs = url

                fflog(f'{control.setting("player.strip_headers_from_link")=}', 0)  # to jakby też (patrz komentarz poniżej)
                if control.setting("player.strip_headers_from_link") == "true":
                    url = url.split("|")[0]

                # URL_CACHE: odczytaj oryginalny URL i jakosc zrodla z window property
                try:
                    import xbmcgui as _xgui_uc
                    self._source_orig_url = _xgui_uc.Window(10000).getProperty('FanVodPL.source_orig_url') or None
                    self._source_quality = _xgui_uc.Window(10000).getProperty('FanVodPL.source_quality') or ''
                    fflog(f'[URL_CACHE] source_orig_url={str(self._source_orig_url or "")[:80]!r} quality={self._source_quality!r}', 1)
                except Exception:
                    self._source_orig_url = None
                    self._source_quality = ''

                fflog(f'{url=}', 0)  # dziwne, ale to pomaga uzwględnić zmianę powyższego ustawienia bez konieczności ponownego szukania źródeł (tylko musi być chyba zmienna w logu)

                # Create a playable item with a path to play.
                item = control.item(path=url, offscreen=True)  # offscreen=True means that the item is not meant for displaying (only to pass info to the Kodi player)

                if subs:
                    fflog(f'{subs.keys()=}', 1)
                    fflog(f'{subs=}', 0)
                    item.setSubtitles(list(subs.values()))

                if self.content == "movie":
                    item.setArt(
                        {
                            "icon": icon,
                            "thumb": thumb,
                            "poster": poster,
                            "fanart": fanart,
                            "clearlogo": clearlogo,
                            "clearart": clearart,
                            "discart": discart,
                            "keyart": keyart,
                            "landscape": landscape,
                            "banner": banner,
                        }
                    )
                else:
                    poster1 = poster2 = poster
                    if isinstance(poster, tuple):
                        poster1, poster2 = poster
                        poster = poster2

                    banner1 = banner2 = banner
                    if isinstance(banner, tuple):
                        banner1, banner2 = banner
                        # banner = banner2 if banner1 == banner2 else banner1
                        banner = banner2

                    landscape1 = landscape2 = landscape
                    if isinstance(landscape, tuple):
                        landscape1, landscape2 = landscape
                        # landscape = landscape2 if landscape1 == landscape2 else landscape1
                        landscape = landscape2

                    fanart1 = fanart2 = fanart
                    if isinstance(fanart, tuple):
                        fanart1, fanart2 = fanart
                        # fanart = fanart2 if fanart1 == fanart2 else fanart1
                        fanart = fanart2

                    # fflog(f'\n   {icon=} \n    {thumb=} \n  {poster1=} \n  {poster2=} \n   {fanart=} \n  {fanart1=} \n  {fanart2=} \n{clearlogo=} \n {clearart=} \n   {keyart=} \n{landscape=} \n{landscape1=} \n{landscape2=} \n   {banner=} \n  {banner1=} \n  {banner2=} \n     {icon=} \n{characterart=}', 1)
                    item.setArt(
                        {
                            "icon": icon,
                            "thumb": thumb,
                            "tvshow.poster": poster1,
                            "season.poster": poster2,
                            "fanart": fanart,
                            "clearlogo": clearlogo,
                            # "tvshow.clearlogo": clearlogo,  # opcjonalnie (jak nie będzie poprzednie wystarczało)
                            "clearart": clearart,
                            "keyart": keyart,
                            "landscape": landscape,
                            "banner": banner,
                            # nie wiem, czy podział tu (w odtwarzaczu) na season i tvshow ma sens
                            "season.banner": banner2,
                            "season.landscape": landscape2,
                            "season.fanart": fanart2,
                            "tvshow.banner": banner1,
                            "tvshow.landscape": landscape1,
                            "tvshow.fanart": fanart1,
                        }
                    )
                    # fflog(f'{characterart=}')  # z ciekawości
                    if characterart:
                        if isinstance(characterart, list):
                            for an in range(0, len(characterart)):
                                item.setArt({f"characterart{an+1}": characterart[an]})
                                item.setArt({f"tvshow.characterart{an+1}": characterart[an]})  # nie wiem, czy to działa i czy to w ogóle potrzebne
                                pass
                        else:
                            item.setArt({"characterart": characterart})
                            item.setArt({"tvshow.characterart": characterart})  # nie wiem, czy to działa i czy to w ogóle potrzebne
                            pass

                try:
                    if ":" in str(meta.get("duration") or ""):
                        meta["duration"] = time_to_seconds(meta["duration"])
                    item.setInfo(type="video", infoLabels=control.metadataClean(meta))
                except Exception:
                    fflog_exc(1)
                    fflog(f'{control.metadataClean(meta)=}')
                    pass

                vtag = item.getVideoInfoTag()
                castwiththumb = meta.get("castwiththumb")
                if castwiththumb:
                    try:
                        castwiththumb = [xbmc.Actor(**a) for a in castwiththumb]
                        vtag.setCast(castwiththumb)
                    except Exception:
                        pass

                if hosting is None:
                    params2 = dict(parse_qsl(sys.argv[2][1:]))
                    # fflog(f'{params2=}', 1)
                    source = params2.get("source")
                    try:
                        source = json.loads(source)  # to się tylko sprawdzi, gdy źródła w folderze (nie w okienku)
                        source = source[0]  # tak dziwnie to jest stworzone (źródło w liście)
                        # provider = source.get("provider")
                        hosting = source.get("source")
                    except Exception:
                        fflog_exc(1)
                        # provider = ""
                        hosting = ""
                # fflog(f'{provider=} {hosting=}', 1)
                fflog(f'{hosting=}', 1)

                # ZMIANA (2026-04) [PATCH]: przygotowanie fallback URL z UA + Referer/Origin dla TwojPlik (all devices).
                # POWOD: legacy linki z konta czesto zawieraja wymuszony lub niestandardowy UA i wpadaja w fast-fail demuxera.
                # NIE ZMIENIAC: przygotowujemy tylko fallback dla retry; nie podmieniamy URL przed pierwsza proba.
                try:
                    if _ff_is_twojplik_context(hosting, getattr(self, '_source_orig_url', None)):
                        _retry_ua = _ff_pick_twojplik_retry_ua()
                        _stream_url_only = str(url).split('|', 1)[0] if '|' in str(url) else str(url)
                        _cookie_header = _ff_try_warmup_twojplik_cookie(
                            getattr(self, '_source_orig_url', None),
                            _stream_url_only,
                            _retry_ua
                        )
                        if _cookie_header:
                            fflog('[TWOJPLIK][RETRY_URL] warmup cookie OK - dodaje Cookie do fallback URL', 1)
                        _android_retry_url = _ff_build_android_twojplik_fallback(
                            url,
                            cookie_header=_cookie_header,
                            user_agent=_retry_ua
                        )
                        if _android_retry_url and _android_retry_url != url:
                            self._retry_play_url = _android_retry_url
                            fflog('[TWOJPLIK][RETRY_URL] przygotowano fallback URL dla retry (UA + Referer/Origin + opcjonalnie Cookie + no-cache)', 1)
                except Exception:
                    fflog_exc(1)

                ia = False
                # if params2.get("ia"):  # źródła z okienka tego nie ma
                if "&ia=1" in sys.argv[2]:
                    ia = True
                fflog(f'{url=}', 0)
                if url.startswith('ia://'):
                    ia = True
                    url = url[5:]
                if not ia and control.setting("player.ia") == "true":
                    if url.startswith("http") and ".m3u8" in url:  # czy nie dodać także ".m3u" ?
                        ia = True
                    else:
                        fflog('IA nie będzie, bo brak ".m3u8" w adresie {url=}', 0)
                        pass
                if "&ia=0" in sys.argv[2]:
                    ia = False

                # CDA HLS FIX: wymusz inputstream.adaptive dla linków CDA .m3u8
                if not ia and ".m3u8" in url and "cda.pl" in url:
                    ia = True
                    fflog('CDA HLS: wymuszam inputstream.adaptive (url zawiera cda.pl + .m3u8)', 1)

                if ia:
                    disallowed_words = control.setting('player.ia_not_for')
                    # fflog(f'{disallowed_words=}', 0)
                    disallowed_words = disallowed_words.split(',')  # string into list
                    disallowed_words = [w.strip().replace('"', '') for w in disallowed_words]  # clean a little
                    disallowed_words = list(filter(None, disallowed_words))  # eliminate empty
                    disallowed_words = list(dict.fromkeys(disallowed_words))  # eliminate duplicates
                    fflog(f'{disallowed_words=}', 0)
                    if disallowed_words and hosting and hosting.lower() in disallowed_words:
                        if "&ia=1" in sys.argv[2]:
                            fflog(f'nie zostanie zastosowany wyjątek dla {hosting=}')
                        else:
                            ia = False
                            fflog(f'IA nie zostanie użyte, bo {hosting=} jest na liście wyjątków  {disallowed_words}', 1)

                if ia:
                    fflog('using Inputstream Adaptive to play stream')
                    kodiver = get_kodi_version().major
                    # fflog(f'{kodiver=}')
                    listitem = item
                    stream_url = url
                    ia = True
                    if kodiver > 16 and ('.mpd' in stream_url or ia):
                        if kodiver < 19:
                            listitem.setProperty('inputstreamaddon', 'inputstream.adaptive')
                        else:
                            listitem.setProperty('inputstream', 'inputstream.adaptive')
                        if '.mpd' in stream_url:
                            if kodiver < 21:
                                listitem.setProperty('inputstream.adaptive.manifest_type', 'mpd')
                            listitem.setMimeType('application/dash+xml')
                        else:
                            if kodiver < 21:
                                listitem.setProperty('inputstream.adaptive.manifest_type', 'hls')
                            listitem.setMimeType('application/x-mpegURL')
                        listitem.setContentLookup(False)
                        if '|' in stream_url:
                            stream_url, strhdr = stream_url.split('|')
                            listitem.setProperty('inputstream.adaptive.stream_headers', strhdr)
                            if kodiver > 19:
                                listitem.setProperty('inputstream.adaptive.manifest_headers', strhdr)
                            listitem.setPath(stream_url)
                        # item = listitem  # nie wiem, czy potrzeba
            else:
                item = control.item(path=url, offscreen=True)

            if not customPlayer:
                fflog("trying to start playback")
            else:
                fflog("trying to run custom playback")

            handle = int(sys.argv[1]) if not handle else handle
            handle = handle if isinstance(handle, int) else -1

            # URL_CACHE LOOKUP: sprawdz url + fingerprint przed odtworzeniem
            try:
                if self._refresh_rejected_folder_flag():
                    fflog('[URL_CACHE] bypass blacklist/cache for rejected folder (trash=1)', 1)
                elif _ff_should_skip_foreign_audio_guard(self.content, self.year):
                    fflog(f'[URL_CACHE] bypass foreign-audio guard for legacy/classic title: {self.content=} {self.year=}', 1)
                # ZMIANA (2026-04) [PATCH]: bypass blokady pre-play (URL_CACHE) dla whitelistowanych hostów.
                # POWOD: linki z tych hostów były fałszywie blokowane gdy cache zawierał wpis 'foreign' z poprzedniego odtworzenia innego tytułu na tym samym hoście.
                # NIE ZMIENIAC: bypass działa tylko gdy self._hosting jest w _FF_NO_AUDIO_BLOCK_HOSTS; dla pozostałych hostów blokada pre-play działa normalnie.
                elif self._hosting in _FF_NO_AUDIO_BLOCK_HOSTS:
                    fflog(f'[URL_CACHE] bypass foreign-audio guard for whitelisted host: {self._hosting!r}', 1)
                else:
                    import hashlib as _hl_uc
                    import xbmcgui as _xgui_lk
                    _blocked = False
                    _uc_url = getattr(self, '_source_orig_url', None)
                    if _uc_url:
                        _uc_key = _hl_uc.md5(_uc_url.split('?')[0].encode('utf-8', errors='replace')).hexdigest()
                        if bookmarks.group_cache_lookup(_uc_key) == 'foreign':
                            fflog(f'[URL_CACHE] BLOKADA url', 1)
                            _blocked = True
                    if not _blocked:
                        _fp_key = _xgui_lk.Window(10000).getProperty('FanVodPL.source_fp_key') or ''
                        if _fp_key and bookmarks.group_cache_lookup(_fp_key) == 'foreign':
                            fflog(f'[URL_CACHE] BLOKADA fingerprint', 1)
                            _blocked = True
                    if _blocked:
                        self.is_active = False
                        try:
                            import xbmcgui as _xgui_dlg2
                            _xgui_dlg2.Dialog().ok(
                                'FanVodPL – Link zablokowany',
                                (
                                    'Ten link został wcześniej zablokowany.\n\n'
                                    'Wykryto obce audio przy poprzednim odtwarzaniu.\n'
                                    'Link jest na czarnej liście.\n\n'
                                    'Wciśnij [B]OK[/B] aby wrócić do listy źródeł.'
                                )
                            )
                        except Exception:
                            fflog_exc(0)
                        return
            except Exception:
                fflog_exc(0)

            #if "plugin" in control.infoLabel("Container.PluginName") and control.setting("hosts.mode") != "1" or int(sys.argv[1]) < 0:
            if handle < 0 or control.setting("player.dont_use_setResolvedUrl") == "true" or url.endswith(".strm"):
                fflog(f'{handle=}')
                if url.endswith(".strm"):
                    fflog(f'case for strm file')
                    if control.condVisibility('Window.IsActive(busydialog)'):
                        if handle > -1:
                            fflog('dodanie pustego katalogu przed odtwarzaniem',1,1)
                            control.directory(handle)
                            pass
                    control.player.play(url)
                else:
                    fflog(f'not setResolved method')
                    control.player.play(url, item)
            else:
                fflog(f'setResolvedUrl method')
                control.resolve(handle, True, item)


            if customPlayer:
                self.is_active = False
                control.sleep(1000)
                fflog(f'exit from FF player script because {customPlayer=}')
                return


            # control.sleep(100)
            control.busy()
            control.sleep(100)
            fflog(f'waiting for player to start')
            try:
                import xbmcgui
                control.dialog.notification('FanVodPL', 'Łączenie z serwerem...', time=15000, sound=False)
            except Exception:
                pass

            # fflog(f'{dir(self)=}',1,1)

            monitor = control.monitor
            _had_playback_start = False
            for i in (r := list(range(0, 10*90))):  # 90 sekund na rozpoczęcie odtwarzania
                if monitor.abortRequested():
                    fflog('Kodi exit signal appeared')
                    return sys.exit()
                if self.isPlayingVideo() or not self.is_active:
                    fflog(f'{self.isPlayingVideo()=}  {self.is_active=}')
                    break
                control.sleep(100)  # delay if loop
                if self.playback_started:
                    _had_playback_start = True
                    self.playback_started = None
                    if i > 0:
                        fflog(f'{i=}')
                        # fflog(f'{r=}')
                        pass
                    r += range(r[-1]+1, r[-1]+1+i)
                    if i > 0:
                        # fflog(f'{r=}')
                        pass
                    # control.busy()
                #fflog(f'waiting ... {i=}')
            # fflog(f'{i=}' + (f' (waited {round((i+1)/10,1)} sec.)' if i else ''))
            fflog(f'{i=}')
            control.idle(2)
            control.sleep(100)
            # zamknij notification "Łączenie z serwerem" gdy film już gra
            try:
                control.execute('Dialog.Close(notification,true)')
            except Exception:
                pass


            # HOST SPEED: zapisz czas startu jesli odtwarzanie wystartowalo
            if self.isPlayingVideo():
                try:
                    _start_ms = i * 100
                    _speed_host = str(hosting or '').strip().lower()
                    _speed_quality = str(getattr(self, '_source_quality', '') or '').strip()
                    fflog(f'[HOST_SPEED] host={_speed_host!r} quality={_speed_quality!r} start_ms={_start_ms}', 1)
                    if _speed_host:
                        bookmarks.host_speed_record(_speed_host, _speed_quality, _start_ms)
                except Exception:
                    fflog_exc(1)
            if not self.isPlayingVideo():
                # Rozróżnienie: user stop (małe i) vs timeout serwera (duże i).
                # Gdy FFmpeg sam się poddaje (np. plik.to po 30s), Kodi odpala onPlayBackStopped
                # -> _stop_in_progress=True, ale to NIE jest akcja usera.
                # Próg: i < 30 (3 sekundy) = user nacisnął STOP ręcznie.
                # i >= 30 = serwer nie odpowiedział / FFmpeg timeout -> traktuj jako dead link.
                _quick_stop = getattr(self, '_stop_in_progress', False) and i < 30
                _server_fast_fail = _quick_stop and (_had_playback_start or getattr(self, '_av_started', False))
                if _quick_stop and not _server_fast_fail:
                    if self._refresh_rejected_folder_flag():
                        fflog(
                            f'[RETRY] szybki fail przed startem w folderze odrzucone (i={i}, {i*100}ms) – wymuszam retry zamiast user-stop',
                            1
                        )
                    else:
                        self.is_active = False
                        fflog(f'odtwarzanie przerwane przez użytkownika przed startem (i={i}, {i*100}ms) – pomijam dead-link')
                        return
                if getattr(self, '_stop_in_progress', False):
                    if _server_fast_fail:
                        fflog(
                            f'[RETRY] fast-fail dekodera/kontenera przed onAVStarted (i={i}, {i*100}ms) – probuje retry zamiast user-stop',
                            1
                        )
                    fflog(f'[TIMEOUT] serwer nie odpowiedział po {i*100}ms (i={i}) – traktuję jako failed link', 1)

                # RETRY: hosty premium (xt7, tb7, plik.to itp.) czasem potrzebują drugiej próby (session warmup).
                # setResolvedUrl można wywołać tylko raz – retry zawsze przez play(), bez drugiego resolve.
                fflog(f'[RETRY] pierwsza próba nie powiodła się – retry za 2s', 1)
                self._stop_in_progress = False  # reset przed retry
                self.is_active = True           # onPlayBackStopped ustawia is_active=False, bez tego retry nigdy nie startuje
                control.sleep(2000)
                if not getattr(self, '_stop_in_progress', False) and self.is_active:
                    try:
                        if _ff_is_twojplik_context(hosting, getattr(self, '_source_orig_url', None)):
                            _probe_retry_url = getattr(self, '_retry_play_url', None) or url
                            if _ff_probe_twojplik_antyshare(_probe_retry_url):
                                self._twojplik_antyshare_detected = True
                                fflog('[TWOJPLIK][HARD_REFRESH] wykryto antyshare przed retry', 1)
                            else:
                                fflog('[TWOJPLIK][HARD_REFRESH] probe nie potwierdzil antyshare, ale wymuszam odswiezenie URL', 1)

                            _refreshed_url = _ff_try_refresh_twojplik_url_from_source(
                                getattr(self, '_source_item_for_refresh', None),
                                getattr(self, '_source_orig_url', None)
                            )
                            if _refreshed_url:
                                _retry_ua = _ff_pick_twojplik_retry_ua()
                                _stream_url_only = str(_refreshed_url).split('|', 1)[0] if '|' in str(_refreshed_url) else str(_refreshed_url)
                                _cookie_header = _ff_try_warmup_twojplik_cookie(
                                    getattr(self, '_source_orig_url', None),
                                    _stream_url_only,
                                    _retry_ua
                                )
                                _hard_retry_url = _ff_build_android_twojplik_fallback(
                                    _refreshed_url,
                                    cookie_header=_cookie_header,
                                    user_agent=_retry_ua
                                )
                                _old_retry_stream = str((getattr(self, '_retry_play_url', None) or url)).split('|', 1)[0]
                                _new_retry_stream = str(_refreshed_url).split('|', 1)[0]
                                self._retry_play_url = _hard_retry_url or _refreshed_url
                                if _new_retry_stream != _old_retry_stream:
                                    fflog('[TWOJPLIK][HARD_REFRESH] odswiezono URL do retry (nowy stream)', 1)
                                else:
                                    # ZMIANA (2026-04) [PATCH]: zapisujemy przypadek stalego linku z konta.
                                    # POWOD: gdy sourcesResolve zwraca ten sam stream URL, drugi retry nic juz nie zmieni.
                                    # NIE ZMIENIAC: ta flaga ma sluzyc tylko do pokazania realnego komunikatu po finalnym failu.
                                    self._twojplik_same_stream_after_refresh = True
                                    fflog('[TWOJPLIK][HARD_REFRESH] sourcesResolve zwrocil ten sam stream URL', 1)
                            else:
                                # ZMIANA (2026-04) [PATCH]: brak nowego URL traktujemy jak nieodswiezalny stary wpis.
                                # POWOD: dla uzytkownika efekt jest ten sam - retry idzie starym linkiem i nie ma szans ruszyc.
                                # NIE ZMIENIAC: flaga ma tylko wywolac czytelny komunikat po finalnym failu.
                                self._twojplik_same_stream_after_refresh = True
                                fflog('[TWOJPLIK][HARD_REFRESH] brak nowego URL po sourcesResolve', 1)
                    except Exception:
                        fflog_exc(1)
                    try:
                        control.dialog.notification('FanVodPL', 'Ponawianie połączenia...', time=8000, sound=False)
                    except Exception:
                        pass
                    # ZMIANA (2026-04) [PATCH]: retry przywraca to samo zachowanie startu i oczekiwania co pierwsza proba
                    # POWOD: po poprzedniej poprawce druga proba uzywala innego wywolania play i krotszej petli bez
                    # wydluzenia po playback_started, przez co retry konczylo sie przedwczesnie mimo realnego startu OpenFile.
                    # NIE ZMIENIAC: retry ma omijac drugi setResolvedUrl, ale ma zachowac taki sam sposob startu jak
                    # pierwsza proba (control.player.play / .strm) oraz to samo wydluzanie okna po callbacku playback_started.
                    try:
                        # ZMIANA (2026-04) [PATCH]: retry moze uzyc fallback URL przygotowanego dla TwojPlik.
                        # POWOD: druga proba z alternatywnymi naglowkami zwieksza szanse poprawnego demux dla starych linkow.
                        # NIE ZMIENIAC: gdy fallback nie istnieje, retry musi isc dokladnie tym samym URL co pierwsza proba.
                        _retry_play_url = getattr(self, '_retry_play_url', None) or url
                        if _retry_play_url != url:
                            fflog('[RETRY] TWOJPLIK: retry z fallback headerami', 1)
                        self._av_started = False
                        self.playback_started = None
                        if _retry_play_url.endswith(".strm"):
                            control.player.play(_retry_play_url)
                        else:
                            control.player.play(_retry_play_url, item)
                    except Exception:
                        fflog_exc(1)
                    _ri = 0
                    _retry_had_playback_start = False
                    for _ri in (_rr := list(range(0, 10 * 30))):  # max 30s na retry + wydluzenie po playback_started
                        if monitor.abortRequested() or not self.is_active:
                            break
                        if self.isPlayingVideo():
                            break
                        control.sleep(100)
                        if self.playback_started:
                            _retry_had_playback_start = True
                            self.playback_started = None
                            if _ri > 0:
                                _rr += range(_rr[-1] + 1, _rr[-1] + 1 + _ri)
                        if getattr(self, '_stop_in_progress', False):
                            break
                    try:
                        control.execute('Dialog.Close(notification,true)')
                    except Exception:
                        pass
                    fflog(f'[RETRY] {self.isPlayingVideo()=}  {self.is_active=}', 1)
                    if self.isPlayingVideo():
                        fflog('[RETRY] udało się za drugą próbą – kontynuuję', 1)
                    else:
                        _retry_quick_stop = getattr(self, '_stop_in_progress', False) and _ri < 30
                        _retry_server_fast_fail = _retry_quick_stop and (
                            _retry_had_playback_start or getattr(self, '_av_started', False)
                        )
                        if _retry_quick_stop and not _retry_server_fast_fail:
                            self.is_active = False
                            fflog('[RETRY] user zatrzymał podczas retry – pomijam dead-link')
                            return
                        if _retry_server_fast_fail:
                            fflog(
                                f'[RETRY] fast-fail dekodera/kontenera podczas retry (i={_ri}, {_ri*100}ms) – traktuję jako failed link',
                                1
                            )
                elif getattr(self, '_stop_in_progress', False) and i < 30 and not _server_fast_fail:
                    self.is_active = False
                    fflog('[RETRY] user zatrzymał przed retry – pomijam dead-link')
                    return

            # ZMIANA (2026-04) [PATCH]: usunieto blok DEAD_LINK (zapis do cache + Dialog().ok)
            # POWOD: na zyczenie uzytkownika — po nieudanym retry player ma zakonczyc cicho,
            #   bez wpisu do czarnej listy (bookmarks.group_cache_record z flaga 'dead')
            #   i bez komunikatu 'Serwer nie odpowiedzial / Link zapisany na czarnej liscie'.
            #   Zachowujemy tylko log + is_active=False + return (taki sam exit jak przy user-stop).
            # NIE ZMIENIAC: nie przywracac group_cache_record z flaga 'dead' bez wyraznego zlecenia.
            #   Lowres-blacklist (RES_CHECK, linie ~1692-1703) i foreign-audio guard to OSOBNE mechanizmy
            #   i NIE sa objete tym usunieciem — dotycza innych flag cache ('lowres', audio).
            if not self.isPlayingVideo():
                try:
                    if _ff_is_twojplik_context(hosting, getattr(self, '_source_orig_url', None)):
                        _final_probe_url = getattr(self, '_retry_play_url', None) or url
                        if _ff_probe_twojplik_antyshare(_final_probe_url):
                            self._twojplik_antyshare_detected = True
                            fflog('[TWOJPLIK][HARD_REFRESH] antyshare potwierdzony po retry', 1)
                except Exception:
                    fflog_exc(1)
                if getattr(self, '_twojplik_same_stream_after_refresh', False):
                    try:
                        import xbmcgui as _xgui_tp
                        control.execute('Dialog.Close(notification,true)')
                        _xgui_tp.Dialog().ok(
                            'FanVodPL - TwojPlik',
                            (
                                'Ten plik jest juz wczesniej pobrany na Twoje konto/host, ale serwer zwraca ten sam stary link odtwarzania.\n\n'
                                'Po drugim retry nadal wraca strona antyshare zamiast pliku video.\n\n'
                                'Tego wpisu nie da sie naprawic sama ponowna proba w odtwarzaczu.\n\n'
                                'Pobierz ten odcinek jeszcze raz na swiezo na swoj host i uruchom go ponownie.'
                            )
                        )
                    except Exception:
                        pass
                elif getattr(self, '_twojplik_antyshare_detected', False):
                    try:
                        import xbmcgui as _xgui_tp
                        control.execute('Dialog.Close(notification,true)')
                        _xgui_tp.Dialog().ok(
                            'FanVodPL - TwojPlik',
                            (
                                'TwojPlik zablokowal ten link i zamiast pliku video zwrocil strone antyshare.\n\n'
                                'Otworz zrodlo ponownie na tym samym urzadzeniu i tej samej sieci.\n\n'
                                'Jesli to starszy plik juz wczesniej pobrany na konto, pobierz go ponownie na swiezo na swoj host.'
                            )
                        )
                    except Exception:
                        pass
                fflog(f'nie udało się rozpocząć odtwarzania (po retry)')
                self.is_active = False
                fflog(f'exit from player script')
                return

            # fflog(f'odtwarzanie')
            """
            if url.endswith(".strm"):
                c = 3
                while control.condVisibility('Window.IsActive(busydialog)') and c > 0:
                    control.sleep0(100)
                    c -= 1
                if control.condVisibility('Window.IsActive(busydialog)'):
                    # fflog('wymuszenie zamknięcia BusyDialog')
                    # control.execute('Dialog.Close(busydialog,true)')
                    pass
            """
            # if control.condVisibility('System.AddonIsEnabled(script.trakt)'):
            # --- SEEK DO POZYCJI RESUME ---
            if getattr(self, '_resume_from', 0) > 0:
                # Wznów od zapisanej pozycji
                try:
                    import xbmcgui as _xgui2
                    _xgui2.Window(10000).setProperty('FanVodPL.seek_resume_in_progress', 'true')
                    control.sleep(800)
                    if self.isPlayingVideo():
                        self.seekTime(float(self._resume_from))
                        fflog(f'seekTime({self._resume_from})', 1)
                    control.sleep(500)
                except Exception:
                    fflog_exc(1)
                finally:
                    try:
                        import xbmcgui as _xgui2
                        _xgui2.Window(10000).clearProperty('FanVodPL.seek_resume_in_progress')
                    except Exception:
                        pass
            elif getattr(self, 'offset', 0) and float(self.offset or 0) > 5:
                # User wybrał "Od początku" ale Kodi może mieć własny resume –
                # jawnie seekuj do 0 żeby go nadpisać
                try:
                    control.sleep(800)
                    if self.isPlayingVideo():
                        self.seekTime(0)
                        fflog('seekTime(0) – od początku, override Kodi native resume', 1)
                except Exception:
                    fflog_exc(1)
            # --- END SEEK ---
            control.window.setProperty("script.trakt.ids", json.dumps(self.ids))  # znacznik dla wtyczki script.trakt, aby mogła rozpoznawać filmy

            # FIX Exynos: try/finally gwarantuje clearProperty nawet przy crashu
            # Brak tego powodował crash przy ponownym wejściu w kategorię po STOP
            try:
                self.keepPlaybackAlive()  # podtrzymywanie, aby skrypt się nie zakończył
            finally:
                control.sleep(100)
                control.window.clearProperty("script.trakt.ids")

            # Dialog po wykryciu obcego audio jest wywoływany w _check_audio_langs_after_start przed stop()

            if self.is_active:
                self.onPlayBackStopped()  # bo czasami się nie odpala (jak się za szybko klika), a ważne gdy trakt

            fflog(f'end of player script')

        except Exception:
            control.infoDialog('wystąpił jakiś błąd', heading="FanVodPL Player", icon="ERROR", time=2900)
            # log("player_fail", "module")
            # fflog("player fail")
            #from ptw.debug import log_exception, fflog_exc
            fflog_exc(1)
            #return


    def getMeta(self, meta):

        if control.infoLabel('ListItem.DBID'):

            if self.content == "movie":
                meta1 = meta
                try:
                    fflog(f'[getMeta] case 2f', 1)

                    meta = control.jsonrpc(
                        '{"jsonrpc": "2.0", "method": "VideoLibrary.GetMovies", "params": {"filter":{"or": [{"field": "year", "operator": "is", "value": "%s"}, {"field": "year", "operator": "is", "value": "%s"}, {"field": "year", "operator": "is", "value": "%s"}]}, "properties" : ["title", "originaltitle", "year", "genre", "studio", "country", "runtime", "rating", "votes", "mpaa", "director", "writer", "plot", "plotoutline", "tagline", "thumbnail", "art", "file"]}, "id": 1}'
                        % (self.year, str(int(self.year) + 1), str(int(self.year) - 1))
                    )
                    # fflog(f'{meta=}')
                    meta = six.ensure_text(meta, errors="ignore")
                    meta = json.loads(meta)["result"]["movies"]
                    # fflog(f'{meta=}')
                    t1 = cleantitle.get(self.title)
                    t2 = cleantitle.get(self.originaltitle)
                    t3 = cleantitle.get(self.englishtitle)
                    # fflog(f'{t1=} {t2=} {t3=}')
                    meta = [
                        i
                        for i in meta
                        if self.year == str(i["year"])
                        and (
                            cleantitle.get(i["title"]) in [t1, t2, t3]
                            or cleantitle.get(i["originaltitle"]) in [t1, t2, t3]
                            )
                    ]
                    meta = meta[0] if meta else {}

                    for k, v in meta.items():
                        if type(v) == list:
                            try:
                                meta[k] = str(" / ".join([six.ensure_str(i) for i in v]))
                            except:
                                meta[k] = ""
                        else:
                            try:
                                meta[k] = str(six.ensure_str(v))
                            except:
                                meta[k] = str(v)

                    if not "plugin" in control.infoLabel("Container.PluginName"):
                        self.DBID = meta["movieid"]

                    #poster = thumb = meta["thumbnail"]
                    #poster = thumb = eval(meta["art"])["poster"]
                    poster = eval(meta["art"]).get("poster", "")
                    thumb = eval(meta["art"]).get("thumb", "") or poster  # or meta["thumbnail"]
                    fanart = eval(meta["art"]).get("fanart", "")
                    clearlogo = eval(meta["art"]).get("clearlogo", "")
                    clearart = eval(meta["art"]).get("clearart", "")
                    discart = eval(meta["art"]).get("discart", "")
                    keyart = eval(meta["art"]).get("keyart", "")
                    landscape = eval(meta["art"]).get("landscape", "")
                    banner = eval(meta["art"]).get("banner", "")
                    icon = eval(meta["art"]).get("icon", "") or poster

                    #return poster, thumb, "", "", "", "", "", "", "", meta
                    return poster, thumb, fanart, clearlogo, clearart, discart, keyart, landscape, banner, icon, "", meta
                except Exception:
                    fflog_exc(1)
                    meta = meta1
                    pass

            elif self.content == "episode":
                meta1 = meta
                try:
                    fflog(f'[getMeta] case 2s', 1)

                    meta = control.jsonrpc(
                        '{"jsonrpc": "2.0", "method": "VideoLibrary.GetTVShows", "params": {"filter":{"or": [{"field": "year", "operator": "is", "value": "%s"}, {"field": "year", "operator": "is", "value": "%s"}, {"field": "year", "operator": "is", "value": "%s"}]}, "properties" : ["title", "year", "thumbnail", "art", "file"]}, "id": 1}'
                        % (self.year, str(int(self.year) + 1), str(int(self.year) - 1))
                    )
                    meta = six.ensure_text(meta, errors="ignore")
                    meta = json.loads(meta)["result"]["tvshows"]
                    # fflog(f'{meta=}')
                    t = cleantitle.get(self.title)
                    # fflog(f'{t=}')
                    t1 = cleantitle.get(self.title)
                    t2 = cleantitle.get(self.originaltitle)
                    t3 = cleantitle.get(self.englishtitle)
                    t4 = cleantitle.get(self.tvshowtitle)
                    # fflog(f'{t1=} {t2=} {t3=} {t4=}')
                    meta = [
                        i
                        for i in meta
                        if( self.year == str(i["year"])
                            and t == cleantitle.get(i["title"])
                            or cleantitle.get(i["title"]) in [t1, t2, t3, t4]
                            #or cleantitle.get(i["originaltitle"]) in [t1, t2, t3, t4]
                        )
                    ][0]

                    # fflog(f'{meta=}')
                    tvshowid = meta["tvshowid"]
                    #poster = meta["thumbnail"]  # nie wiem, czy to dobrze
                    #poster = meta["art"].get("tvshow.poster", "")
                    poster1 = meta["art"].get("poster", "")
                    fanart1 = meta["art"].get("fanart", "")
                    clearlogo1 = meta["art"].get("clearlogo", "")
                    clearart1 = meta["art"].get("clearart", "")
                    keyart1 = meta["art"].get("keyart", "")
                    landscape1 = meta["art"].get("landscape", "")
                    banner1 = meta["art"].get("banner", "")
                    icon1 = meta["art"].get("icon", "") or poster1
                    characterart1 = meta["art"].get("characterart", "")

                    meta = control.jsonrpc(
                        '{"jsonrpc": "2.0", "method": "VideoLibrary.GetEpisodes", "params":{ "tvshowid": %d, "filter":{"and": [{"field": "season", "operator": "is", "value": "%s"}, {"field": "episode", "operator": "is", "value": "%s"}]}, "properties": ["title", "season", "episode", "showtitle", "firstaired", "runtime", "rating", "director", "writer", "plot", "thumbnail", "art", "file"]}, "id": 1}'
                        % (tvshowid, self.season, self.episode)
                    )
                    meta = six.ensure_text(meta, errors="ignore")
                    meta = json.loads(meta)["result"]["episodes"][0]
                    # fflog(f'{meta=}')
                    for k, v in meta.items():
                        if type(v) == list:
                            try:
                                meta[k] = str(" / ".join([six.ensure_str(i) for i in v]))
                            except:
                                meta[k] = ""
                        else:
                            try:
                                meta[k] = str(six.ensure_str(v))
                            except:
                                meta[k] = str(v)

                    if not "plugin" in control.infoLabel("Container.PluginName"):
                        self.DBID = meta["episodeid"]
                    # fflog(f'{meta=}')
                    # fflog(f'{eval(meta["art"])=}')
                    #thumb = meta["thumbnail"]
                    poster = eval(meta["art"]).get("season.poster", "") or poster1
                    thumb = eval(meta["art"]).get("thumb", "") or poster
                    fanart = eval(meta["art"]).get("season.fanart", "") or fanart1
                    clearlogo = eval(meta["art"]).get("season.clearlogo", "") or clearlogo1
                    clearart = eval(meta["art"]).get("season.clearart", "") or clearart1
                    keyart = eval(meta["art"]).get("season.keyart", "") or keyart1
                    landscape = eval(meta["art"]).get("season.landscape", "") or landscape1
                    banner = eval(meta["art"]).get("season.banner", "") or banner1
                    icon = eval(meta["art"]).get("season.icon", "") or icon1
                    characterart = eval(meta["art"]).get("season.characterart", "") or characterart1

                    #return poster, thumb, "", "", "", "", "", "", "", meta
                    # return (poster1, poster), thumb, fanart, clearlogo, clearart, "", keyart, landscape, banner, icon, characterart, meta
                    return (poster1,poster), thumb, (fanart1,fanart), clearlogo, clearart, "", keyart, (landscape1,landscape), (banner1,banner), icon, characterart, meta
                except Exception:
                    fflog_exc(1)
                    meta = meta1
                    pass

        if meta:
            try:
                fflog(f'[getMeta] case 1', 1)
                poster = meta["poster"] if "poster" in meta.keys() else ""
                poster1 = meta["tvshow.poster"] if "tvshow.poster" in meta.keys() else ""
                poster2 = meta["season.poster"] if "season.poster" in meta.keys() else ""
                thumb = meta["thumb"] if "thumb" in meta.keys() else "" or poster
                fanart = meta["fanart"] if "fanart" in meta.keys() else ""
                clearlogo = meta["clearlogo"] if "clearlogo" in meta.keys() else ""
                clearart = meta["clearart"] if "clearart" in meta.keys() else ""
                discart = meta["discart"] if "discart" in meta.keys() else ""
                keyart = meta["keyart"] if "keyart" in meta.keys() else ""
                landscape = meta["landscape"] if "landscape" in meta.keys() else ""
                banner = meta["banner"] if "banner" in meta.keys() else ""
                icon = meta["icon"] if "icon" in meta.keys() else "" or thumb
                characterart = meta["characterart"] if "characterart" in meta.keys() else ""
                if not "plugin" in control.infoLabel("Container.PluginName"):  # tylko dla zewnętrznych ?
                    # pomaga, bo jak są źle ustawione, to FF sobie je jakoś sam dobiera (pytanie, czy to tylko tak w Kodi 21 ?)
                    meta.pop("poster", None);  meta.pop("thumb", None);
                    poster = thumb = ""  # a może wszystkie czyścić ?
                if poster2:
                    poster = (poster1 or poster, poster2)
                # fflog(f'\n   {poster=} \n    {thumb=} \n   {fanart=} \n{clearlogo=} \n {clearart=} \n  {discart=} \n   {keyart=} \n{landscape=} \n   {banner=} \n     {icon=} \n{meta=}', 1)
                return poster, thumb, fanart, clearlogo, clearart, discart, keyart, landscape, banner, icon, characterart, meta
            except Exception:
                fflog_exc(1)
                meta = {}
                pass

        # fallback
        fflog(f'[getMeta] case 3', 1)
        poster, thumb, fanart, clearlogo, clearart, discart, keyart, landscape, banner, icon, characterart = (
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            #{"title": self.name},
        )
        if not meta:
            meta = {}
        if not meta.get("title"):
            meta.update({"title": self.name})

        return poster, thumb, fanart, clearlogo, clearart, discart, keyart, landscape, banner, icon, characterart, meta


    def _save_local_progress(self, current_time, total_time):
        try:
            current_time = float(current_time or 0.0)
            total_time = float(total_time or 0.0)
        except Exception:
            return

        if total_time <= 0 or current_time <= 0:
            return

        try:
            progress = current_time / total_time
        except Exception:
            return

        watched = progress >= 0.92
        # Stary próg 120s powodował brak paska po pierwszym STOP.
        # Schodzimy tylko do bezpiecznego minimum, żeby zapisać realnie rozpoczęty odcinek,
        # ale nadal nie tworzyć progresu po przypadkowym 1-2 sekundowym kliknięciu.
        min_progress_save_sec = 15
        if not watched and current_time < min_progress_save_sec:
            return

        try:
            if watched:
                bookmarks.reset(current_time, total_time, self.content, self.imdb, self.season, self.episode)
            else:
                if not getattr(self, '_bookmark_touch_done', False):
                    bookmarks._delete_record(self.content, self.imdb, self.season, self.episode)
                    self._bookmark_touch_done = True
                    control.sleep(100)
                bookmarks.reset(current_time, total_time, self.content, self.imdb, self.season, self.episode)
            self._last_local_progress_save = current_time
        except Exception:
            try:
                fflog_exc(1)
            except Exception:
                pass



    def keepPlaybackAlive(self):
        fflog('start keepPlaybackAlive method')
        _monitor = xbmc.Monitor()

        # Czekaj az film wystartuje (max 15 sek) - fix podwojnego klikniecia
        for _i in range(150):
            if _monitor.abortRequested() or not self.is_active:
                fflog('keepPlaybackAlive: przerwano przed startem')
                return
            if self.isPlayingVideo():
                fflog(f'keepPlaybackAlive: film uruchomiony po {_i*100}ms')
                break
            # Exynos fix: waitForAbort zamiast xbmc.sleep - bezpieczniejszy na Android podczas flush dekodera
            _monitor.waitForAbort(0.1)

        # Detekcja braku audio renderera (np. po crashu audio engine w poprzedniej sesji)
        # Sprawdzamy po 3s od startu - dajemy czas na inicjalizacje audio
        _audio_check_done = False
        _audio_check_ticks = 0
        _AUDIO_CHECK_AFTER = 30  # 30 * 100ms = 3 sekundy

        # Czekaj az film sie skonczy
        # Przywracamy lokalny zapis progresu w bezpieczny sposób: tylko w tej pętli, nigdy w callbackach STOP.
        _progress_ticks = 0
        _progress_every = 50  # 50 * 100ms = 5 sekund - zapis do bazy
        _snapshot_ticks = 0
        _snapshot_every = 10  # 10 * 100ms = 1 sekunda - odświeżenie pamięci pozycji
        while self.isPlayingVideo() and not _monitor.abortRequested():
            # Exynos fix: waitForAbort zamiast xbmc.sleep - nie blokuje native threadu podczas flush dekodera
            _monitor.waitForAbort(0.1)
            if not _audio_check_done:
                _audio_check_ticks += 1
                if _audio_check_ticks >= _AUDIO_CHECK_AFTER:
                    _audio_check_done = True
                    try:
                        # Exynos fix: podwójne sprawdzenie isPlayingVideo() tuż przed getAudioStreamCount()
                        if self.isPlayingVideo() and not getattr(self, '_stop_in_progress', False):
                            if self.getAudioStreamCount() == 0:
                                self._audio_renderer_failed = True
                                fflog('keepPlaybackAlive: brak strumienia audio po 3s - audio engine uszkodzony', 1)
                    except Exception:
                        pass

            _snapshot_ticks += 1
            if _snapshot_ticks >= _snapshot_every:
                _snapshot_ticks = 0
                try:
                    # Tylko lekki snapshot pozycji do pamięci procesu.
                    # Nie dotykamy STOP callbacka, więc nie cofamy crash-fixa.
                    if self.isPlayingVideo() and not getattr(self, '_stop_in_progress', False):
                        current_time = float(self.getTime() or 0.0)
                        total_time = float(self.getTotalTime() or self.runtime or 0.0)
                        if total_time <= 0 and self.runtime:
                            total_time = float(self.runtime or 0.0)
                        self.currentTime = current_time
                        self.totalTime = total_time
                except Exception:
                    pass

            _progress_ticks += 1
            if _progress_ticks >= _progress_every:
                _progress_ticks = 0
                try:
                    if self.currentTime and self.totalTime:
                        self._save_local_progress(self.currentTime, self.totalTime)
                except Exception:
                    pass

        try:
            if self.currentTime and self.totalTime:
                self._save_local_progress(self.currentTime, self.totalTime)
        except Exception:
            pass

        fflog('end of keepPlaybackAlive method')
    def libForPlayback(self):
        """ oznacza w Bibliotece, że obejrzany """
        try:
            if self.DBID is not None:

                if self.content == "movie":
                    rpc = (
                        '{"jsonrpc": "2.0", "method": "VideoLibrary.SetMovieDetails", "params": {"movieid" : %s, "playcount" : 1 }, "id": 1 }'
                        % str(self.DBID)
                    )
                elif self.content == "episode":
                    rpc = (
                        '{"jsonrpc": "2.0", "method": "VideoLibrary.SetEpisodeDetails", "params": {"episodeid" : %s, "playcount" : 1 }, "id": 1 }'
                        % str(self.DBID)
                    )
                else:
                    return

                control.jsonrpc(rpc)

                if control.setting("crefresh") == "true":
                    control.refresh()
        except Exception:
            fflog_exc(1)
            pass


    # -------------------------
    # MAX SAFE helpers
    # -------------------------
    def _translate_path(self, path):
        try:
            if xbmcvfs and hasattr(xbmcvfs, "translatePath"):
                return xbmcvfs.translatePath(path)
        except Exception:
            pass
        try:
            return xbmc.translatePath(path)
        except Exception:
            return path

    def _notify(self, msg, ms=2500):
        # Use a notification that is safe even if called from a worker thread.
        try:
            # control.dialog.notification is used elsewhere in this file.
            control.dialog.notification("FanVodPL", msg, time=ms, sound=False)
            return
        except Exception:
            pass
        try:
            xbmc.executebuiltin("Notification(FanVodPL,{0},{1})".format(msg, int(ms)))
        except Exception:
            pass

    def _run_async(self, fn, delay_s=0.35):
        def _worker():
            try:
                mon = xbmc.Monitor()
                if delay_s and delay_s > 0:
                    mon.waitForAbort(float(delay_s))
            except Exception:
                try:
                    time.sleep(float(delay_s))
                except Exception:
                    pass
            try:
                fn()
            except Exception:
                try:
                    fflog_exc(1)
                except Exception:
                    pass

        try:
            t = threading.Thread(target=_worker, daemon=True)
            t.start()
        except Exception:
            # Fallback: run inline (still protected)
            _worker()

    def _cleanup_plugin_cache_dirs(self):
        # Only clears this addon's cache/temp/cookies. Does NOT touch global Kodi cache.
        try:
            addon_id = xbmcaddon.Addon().getAddonInfo("id")
        except Exception:
            addon_id = None
        if not addon_id:
            return (0, 0)

        base = self._translate_path("special://profile/addon_data/{0}".format(addon_id))
        targets = ["cache", "temp", "tmp"]

        files_deleted = 0
        dirs_deleted = 0

        for sub in targets:
            d = os.path.join(base, sub)
            if not os.path.exists(d):
                continue

            for root, dirs, files in os.walk(d, topdown=False):
                for fn in files:
                    fp = os.path.join(root, fn)
                    try:
                        os.remove(fp)
                        files_deleted += 1
                    except Exception:
                        pass
                for dn in dirs:
                    dp = os.path.join(root, dn)
                    try:
                        os.rmdir(dp)
                        dirs_deleted += 1
                    except Exception:
                        pass

        return (files_deleted, dirs_deleted)

    def onPlayBackStarted(self):
        # MAX SAFE: keep this callback minimal (no getPlayingFile/getTime).
        try:
            fflog('playback started')
        except Exception:
            pass
        _tr('onPlayBackStarted', content=getattr(self,'content','?'), imdb=getattr(self,'imdb','?'), season=getattr(self,'season','?'), episode=getattr(self,'episode','?'))
        self.playback_started = True
        self.is_active = True
        self._ended = False
        self._error = False
        self._av_started = False
        self._stop_in_progress = False
        self._stop_cleanup_done = False
        self._audio_renderer_failed = False
        self._bookmark_touch_done = False
        self._last_local_progress_save = 0.0

    def onAVStarted(self):  # czasami dopiero po ponad 1 sekundzie odpala
        # MAX SAFE: do not use getTime/getTotalTime/pause/seek/resume dialogs here.
        try:
            fflog('player has video and audiostream')
        except Exception:
            pass
        self._av_started = True
        # URL_CACHE: sprawdz sciezki audio w tle po 3s
        try:
            self._run_async(self._check_audio_langs_after_start, delay_s=3.0)
        except Exception:
            pass
        # URL_CACHE LOWRES: sprawdz faktyczna rozdzielczosc vs zadeklarowana po 5s
        # (po audio check zeby nie nakladac dialogow jesli player zostal juz zatrzymany)
        try:
            self._run_async(self._check_resolution_after_start, delay_s=5.0)
        except Exception:
            pass
        return

    def onPlayBackStopped(self):
        # MAX SAFE: keep STOP callback extremely lightweight to avoid native crashes on some devices.
        try:
            if getattr(self, "_stop_in_progress", False):
                return
            if self.is_active == False:
                return
        except Exception:
            pass

        self._stop_in_progress = True
        self._last_stop_ts = time.time()
        try:
            fflog('player has been stopped')
        except Exception:
            pass
        _tr('onPlayBackStopped', content=getattr(self,'content','?'), imdb=getattr(self,'imdb','?'), currentTime=getattr(self,'currentTime',0), totalTime=getattr(self,'totalTime',0))

        # Mark inactive early (prevents duplicate execution paths)
        self.is_active = False

        if getattr(self, "_max_safe_mode", True):
            # Decide about cleanup a bit later, so if Kodi fires ENDED/ERROR after STOP, we don't misclassify.
            def _maybe_cleanup():
                try:
                    if getattr(self, "_stop_cleanup_done", False):
                        return
                    if getattr(self, "_ended", False) or getattr(self, "_error", False):
                        return

                    self._stop_cleanup_done = True

                    # Komunikat o uszkodzonym audio engine
                    if getattr(self, "_audio_renderer_failed", False):
                        self._notify(
                            "Brak dźwięku? Audio engine Kodi jest uszkodzony. Zrestartuj Kodi.",
                            ms=8000,
                        )

                    files_deleted, dirs_deleted = self._cleanup_plugin_cache_dirs()

                    if files_deleted or dirs_deleted:
                        self._notify(
                            "STOP: wyczyszczono cache (pliki: {0}, foldery: {1})".format(files_deleted, dirs_deleted)
                        )
                    else:
                        self._notify("STOP: cache już był pusty")
                except Exception:
                    try:
                        fflog_exc(1)
                    except Exception:
                        pass

            self._run_async(_maybe_cleanup, delay_s=0.55)
            return

        # Non-safe mode fallback: keep original behavior (not used by default).
        try:
            fflog('MAX_SAFE_MODE disabled: original STOP logic skipped in this build', 1)
        except Exception:
            pass

    def onPlayBackEnded(self):  # materiał doszedł do końca
        # MAX SAFE: mark as ended and reuse STOP handler (which will NOT run cleanup when _ended==True).
        try:
            fflog('playback Ended')
        except Exception:
            pass
        self._ended = True
        try:
            self.onPlayBackStopped()
        except Exception:
            pass
        try:
            if control.setting("crefresh") == "true":
                control.refresh()
        except Exception:
            pass

    def onPlayBackError(self):  # Will be called when playback stops due to an error.
        try:
            fflog('playback ERROR')
        except Exception:
            pass
        self._error = True
        # Ensure STOP handler runs once, but it will skip cleanup because _error==True.
        try:
            self.onPlayBackStopped()
        except Exception:
            pass

    def onPlayBackSeek(self, time, offset):
        fflog('playback Seek')
        if self.isPlayingVideo():
            if (
                trakt.getTraktCredentialsInfo()
                #and control.setting("trakt.scrobble") == "true"
                and trakt.getTraktIndicatorsInfo()
                and self.external_scrobble_is_disabled()
            ):
                #self.currentTime = self.getTime()  # ewentualnie (time / 1000)
                self.currentTime = time / 1000
                #self.totalTime = self.getTotalTime()
                #fflog(f'{time=} {offset=}')
                #fflog(f'{self.totalTime=} {self.currentTime=}')
                #fflog(f'bookmarks set_scrobble (trakt)')
                bookmarks.set_scrobble(
                    self.currentTime,
                    #self.totalTime,
                    self.runtime or self.totalTime,
                    self.content,
                    self.imdb,
                    None,
                    self.season,
                    self.episode,
                    self.offset,
                    action="start",
                )


    def onPlayBackResumed(self):
        # MAX SAFE: do nothing (avoids trakt/bookmarks scrobble calls in callback).
        try:
            fflog('playback Resumed')
        except Exception:
            pass
        return

    def onPlayBackPaused(self):
        # MAX SAFE: do nothing (avoids trakt/bookmarks scrobble calls in callback).
        try:
            fflog('playback Paused')
        except Exception:
            pass
        return

    def external_scrobble_is_disabled(self):
        external_scrobble_is_disabled = not(trakt.getTraktAddonMovieInfo() if self.content == "movie" else trakt.getTraktAddonEpisodeInfo())
        """ bo okazało się, że już taka funkcja jest
        external_script_trakt_id = "script.trakt"
        #fflog(f'sprawdzam, cz zewnętrzna wtyczka "{external_script_trakt_id}" jest aktywna')
        #control.sleep(100)
        #external_script_trakt_exists = control.condVisibility(f"System.HasAddon({external_script_trakt_id})")
        #if external_script_trakt_exists:
        external_script_trakt_enabled = control.condVisibility(f"System.AddonIsEnabled({external_script_trakt_id})")
        if external_script_trakt_enabled:
            external_scrobble_movie = control.addon(external_script_trakt_id).getSetting("scrobble_movie")
            external_scrobble_episode = control.addon(external_script_trakt_id).getSetting("scrobble_episode")

        external_scrobble_is_disabled = (
                #not (external_script_trakt_exists and external_script_trakt_enabled)
                not external_script_trakt_enabled
                or (
                    external_scrobble_movie != "true" if self.content == "movie"
                    else external_scrobble_episode != "true"
                   )
            )
        """
        #fflog(f'{external_scrobble_is_disabled=}')
        return external_scrobble_is_disabled


    # def get_host_name(self, url):
        # """ chyba jednak nie będę używał """
        # m = re.search('https?://([A-Za-z_0-9.-]+).*', url)
        # if m:
            # return m.group(1).split('.')[-2]
        # else:
            # return ""


    def _check_audio_langs_after_start(self):
        """
        Sprawdza faktyczne sciezki audio po 3s od startu.
        Klucz cache = MD5 oryginalnego URL zrodla (z window property).
        Jesli obce audio: zatrzymuje + zapisuje do cache.
        """
        _ALLOWED = {
            'polish', 'polski', 'pol', 'pl',
            'english', 'eng', 'en',
            'und', 'undefined', 'unknown', '',
        }
        try:
            if not self.isPlayingVideo() or getattr(self, '_stop_in_progress', False):
                return

            if self._refresh_rejected_folder_flag():
                fflog('[AUDIO_CHECK] bypass blacklist/cache for rejected folder (trash=1)', 1)
                return

            if _ff_should_skip_foreign_audio_guard(getattr(self, 'content', None), getattr(self, 'year', None)):
                fflog(f'[AUDIO_CHECK] bypass foreign-audio guard for legacy/classic title: {getattr(self, "content", None)=} {getattr(self, "year", None)=}', 1)
                return

            # ZMIANA (2026-04) [PATCH]: bypass post-play audio check dla whitelistowanych hostów.
            # POWOD: mechanizm _check_audio_langs_after_start() wywoływany 3s po starcie zatrzymywał odtwarzanie i pokazywał dialog blokujący gdy plik miał ścieżkę audio inną niż PL/EN; dla tych hostów jest to błędna detekcja.
            # NIE ZMIENIAC: getattr z fallbackiem '' jest konieczny bo metoda jest wywoływana asynchronicznie i self._hosting może teoretycznie nie istnieć; nie skracać do self._hosting (AttributeError risk).
            if str(getattr(self, '_hosting', '') or '').strip().lower() in _FF_NO_AUDIO_BLOCK_HOSTS:
                fflog(f'[AUDIO_CHECK] bypass foreign-audio guard for whitelisted host: {getattr(self, "_hosting", "")!r}', 1)
                return

            streams = self.getAvailableAudioStreams()
            if not streams:
                fflog('[AUDIO_CHECK] brak strumieni – pomijam', 0)
                return

            langs = {str(s).strip().lower() for s in streams if s is not None}
            try:
                import xbmcgui as _xgui_ai_ctx
                _src_url_ai = _xgui_ai_ctx.Window(10000).getProperty('FanVodPL.source_orig_url') or ''
                _src_quality_ai = _xgui_ai_ctx.Window(10000).getProperty('FanVodPL.source_quality') or ''
            except Exception:
                _src_url_ai = getattr(self, '_source_orig_url', None) or ''
                _src_quality_ai = getattr(self, '_source_quality', '') or ''
            _ai_context = _ff_has_ai_lektor_source_context(_src_url_ai, _src_quality_ai, getattr(self, 'title', None), getattr(self, 'name', None), sys.argv[2] if len(sys.argv) > 2 else '')
            # ZMIANA (2026-04) [PATCH]: jeśli opis linku / źródła wskazuje na AI lektora, cały dialog foreign-audio jest pomijany.
            # POWOD: użytkownik chce prosty bypass po wzorcach „Lektor AI / PL.Ai”; Kodi potrafi zwrócić techniczne nazwy ścieżek audio bez „pl”, więc wcześniejsze filtrowanie po samych streamach nadal pokazywało okno.
            # NIE ZMIENIAC: bypass ma działać tylko dla wyraźnego kontekstu AI lektora z opisu linku lub źródła; zwykłe obce audio bez takich wzorców nadal mają wywoływać obecną blokadę i zapis foreign.
            if _ai_context:
                fflog(f'[AUDIO_CHECK] bypass foreign-audio dialog for AI lektor source: sciezki={langs}', 1)
                return
            ai_lektor_labels = {lang for lang in langs if _ff_is_ai_lektor_audio_label(lang)}
            foreign = {lang for lang in langs if lang not in _ALLOWED and lang not in ai_lektor_labels}
            fflog(f'[AUDIO_CHECK] sciezki={langs}  ai_context={_ai_context}  ai_lektor={ai_lektor_labels}  obce={foreign}', 1)

            # Klucze cache: MD5(url) + fingerprint z window property
            cache_key_url = None
            cache_key_fp  = None
            try:
                import xbmcgui as _xgui_ac
                import hashlib as _hl_ac
                src_url = _xgui_ac.Window(10000).getProperty('FanVodPL.source_orig_url') or ''
                if src_url:
                    cache_key_url = _hl_ac.md5(src_url.split('?')[0].encode('utf-8', errors='replace')).hexdigest()
                cache_key_fp = _xgui_ac.Window(10000).getProperty('FanVodPL.source_fp_key') or None
                if cache_key_fp == '': cache_key_fp = None
                fflog(f'[AUDIO_CHECK] key_url={cache_key_url!r} key_fp={cache_key_fp!r}', 1)
            except Exception:
                fflog_exc(1)

            # Zapisz oba klucze do cache
            try:
                bookmarks.group_cache_record(cache_key_url, langs, foreign)
            except Exception:
                fflog_exc(1)
            try:
                if cache_key_fp:
                    bookmarks.group_cache_record(cache_key_fp, langs, foreign)
            except Exception:
                fflog_exc(1)

            if not foreign:
                fflog('[AUDIO_CHECK] audio OK (PL/EN)', 1)
                return

            # Obce audio – pokaż dialog PRZED zatrzymaniem (player jeszcze aktywny)
            # Musi być PRZED stop() bo po nawigacji powrotnej Dialog().ok() nie ma kontekstu
            langs_str = ', '.join(sorted(foreign)).upper()
            fflog(f'[AUDIO_CHECK] STOP – obce={foreign}', 1)
            try:
                import xbmcgui as _xgui_dlg_fg
                # Poczekaj aż sweep (_FF_PremiumGuard) z poprzedniego odtwarzania się skończy
                # ale tylko jeśli jesteśmy bardzo blisko startu (sweep trwa 2.5s od poprzedniego STOP)
                # Tutaj: player właśnie gra, sweep z TEGO stopu jeszcze nie wystartował
                _xgui_dlg_fg.Dialog().ok(
                    'FanVodPL – Odtwarzanie przerwane',
                    (
                        f'Wykryto obce ścieżki audio: [B]{langs_str}[/B]\n\n'
                        f'Brak języka polskiego lub angielskiego.\n\n'
                        f'Struktura techniczna tego pliku (jakość, platforma, grupa)\n'
                        f'została automatycznie dodana do czarnej listy.\n'
                        f'Wszystkie linki z identyczną strukturą – na innych hostach\n'
                        f'i w innych tytułach – będą blokowane od razu.\n\n'
                        f'Wciśnij [B]OK[/B] aby wrócić do listy źródeł.'
                    )
                )
            except Exception:
                fflog_exc(1)
            # Zatrzymaj odtwarzanie DOPIERO PO kliknięciu OK
            try:
                import xbmc as _xbmc2
                if self.isPlayingVideo() and not getattr(self, '_stop_in_progress', False):
                    self.stop()
            except Exception:
                fflog_exc(1)
        except Exception:
            fflog_exc(1)


    def _check_resolution_after_start(self):
        """
        Sprawdza faktyczna rozdzielczosc po 5s od startu i porownuje
        z zadeklarowana jakoscia ze zrodla. Jesli faktyczna jest
        istotnie nizsza (np. zrodlo twierdzi '4K' a gra SD) –
        zapisuje grupe do czarnej listy jako 'lowres' i zatrzymuje.

        Progi (margines ~15% zeby nie blokowac anamorficznego kadru):
          4K/2160p  -> min 1800 px wysokosci
          1080p/FHD -> min 900  px
          720p/HD   -> min 600  px
          SD / inne -> nie sprawdzamy (nie ma co porownywac)

        Downgrade tylko w jedna strone: jesli zrodlo deklaruje 720p
        a gra 1080p – to bonus, NIE blokujemy.

        Wyjatek 1:1 z _check_audio_langs_after_start: stare tytuly
        (seriale 1950-2015, filmy 1950-2005) nie sa sprawdzane.
        """
        # Progi minimalnej akceptowalnej wysokosci px per zadeklarowana jakosc.
        _LOWRES_THRESHOLDS = [
            # (lista tokenow do matchowania, minimalna wysokosc px)
            (('2160p', '4k', 'uhd'),      1800),
            (('1080p', '1080i', 'fhd'),    900),
            (('720p',  'hd'),              600),
        ]
        try:
            # Audio check mogl juz zatrzymac player – nie nachodz na dialog.
            if not self.isPlayingVideo() or getattr(self, '_stop_in_progress', False):
                fflog('[RES_CHECK] pominieto – player nie gra lub stop w toku', 0)
                return

            if self._refresh_rejected_folder_flag():
                fflog('[RES_CHECK] bypass blacklist/cache for rejected folder (trash=1)', 1)
                return

            # Ten sam bypass co dla foreign-audio – seriale 1950-2015, filmy 1950-2005.
            if _ff_should_skip_foreign_audio_guard(getattr(self, 'content', None), getattr(self, 'year', None)):
                fflog(f'[RES_CHECK] bypass dla legacy/classic: content={getattr(self,"content",None)!r} year={getattr(self,"year",None)!r}', 1)
                return

            declared_raw = str(getattr(self, '_source_quality', '') or '').strip()
            if not declared_raw:
                fflog('[RES_CHECK] brak zadeklarowanej jakosci w source_quality – pomijam', 0)
                return
            declared = declared_raw.lower()

            # Znajdz prog dla zadeklarowanej jakosci.
            min_required = None
            declared_bucket = None
            for tokens, thr in _LOWRES_THRESHOLDS:
                if any(tok in declared for tok in tokens):
                    min_required = thr
                    declared_bucket = tokens[0]
                    break
            if min_required is None:
                fflog(f'[RES_CHECK] declared={declared_raw!r} nie podlega kontroli (SD lub nieznane) – pomijam', 0)
                return

            # Odczytaj faktyczna wysokosc. Priorytet: Player.Process(VideoHeight) – dziala w callbacku.
            # Fallback: getVideoInfoTag().getHeight() – nie na kazdej platformie bezpieczny w callbacku.
            actual_h = 0
            try:
                import xbmc as _xbmc_rc
                _vh = _xbmc_rc.getInfoLabel('Player.Process(VideoHeight)') or ''
                try:
                    actual_h = int(str(_vh).strip())
                except Exception:
                    actual_h = 0
            except Exception:
                fflog_exc(1)

            if actual_h <= 0:
                # Fallback – ostroznie, tylko jesli player nadal gra.
                try:
                    if self.isPlayingVideo() and not getattr(self, '_stop_in_progress', False):
                        tag = self.getVideoInfoTag()
                        try:
                            actual_h = int(tag.getHeight() or 0)
                        except Exception:
                            actual_h = 0
                except Exception:
                    fflog_exc(1)

            if actual_h <= 0:
                fflog('[RES_CHECK] nie udalo sie odczytac faktycznej wysokosci – pomijam', 0)
                return

            fflog(f'[RES_CHECK] declared={declared_raw!r} bucket={declared_bucket!r} min_required={min_required}px actual={actual_h}px', 1)

            # Downgrade tylko w jedna strone – actual >= min_required znaczy OK.
            if actual_h >= min_required:
                fflog('[RES_CHECK] rozdzielczosc OK', 1)
                return

            # LOWRES – zapytaj usera czy dopisac do czarnej listy, potem zatrzymaj.
            cache_key_url = None
            cache_key_fp  = None
            try:
                import xbmcgui as _xgui_rc
                import hashlib as _hl_rc
                src_url = _xgui_rc.Window(10000).getProperty('FanVodPL.source_orig_url') or ''
                if src_url:
                    cache_key_url = _hl_rc.md5(src_url.split('?')[0].encode('utf-8', errors='replace')).hexdigest()
                cache_key_fp = _xgui_rc.Window(10000).getProperty('FanVodPL.source_fp_key') or None
                if cache_key_fp == '':
                    cache_key_fp = None
                fflog(f'[RES_CHECK] key_url={cache_key_url!r} key_fp={cache_key_fp!r}', 1)
            except Exception:
                fflog_exc(1)

            fflog(f'[RES_CHECK] STOP - lowres declared={declared_raw!r} actual={actual_h}px (min={min_required}px)', 1)
            # ZMIANA (2026-04) [PATCH]: REVERT poprzedniej proby self.stop()+sleep PRZED Dialog().yesno()
            # POWOD: Poprzednia proba (self.stop() przed dialogiem) powodowala ze DialogConfirm.xml
            #   nie ladowal sie poprawnie — Kodi zglaszal "Window Translator: Can't find window
            #   dialogconfirm", yesno() zwracal False (NIE) jako default BEZ kliknięcia usera.
            #   Dodatkowo: self.stop() triggerowalo auto-retry action=play przez Kodi (handle=-1).
            #   Potwierdzone logiem 2026-04-19 13:45 (film zatrzymywal sie sam, auto-retry HostSelect).
            # POWRACAM do oryginalnego zachowania: dialog podczas playback, stop dopiero po TAK.
            # NIE ZMIENIAC: nie dodawac ponownie self.stop() / sleep / setProperty PRZED Dialog().yesno().
            #   Jesli DestroyWindow nadal jest problemem — rozwiazac inna metoda (nie przez stop-before).
            _add_to_blacklist = True  # fallback: stare zachowanie, gdy dialog nie pojawi sie
            try:
                import xbmcgui as _xgui_dlg_rc
                _add_to_blacklist = _xgui_dlg_rc.Dialog().yesno(
                    'FanVodPL - Odtwarzanie przerwane',
                    (
                        f'Zadeklarowana jakosc: [B]{declared_raw}[/B]\n'
                        f'Faktyczna rozdzielczosc: [B]{actual_h}px[/B] (minimum: {min_required}px)\n\n'
                        f'Plik ma nizsza rozdzielczosc niz deklaruje zrodlo.\n\n'
                        f'Czy dodac strukture techniczna tego pliku (jakosc, platforma, grupa)\n'
                        f'do czarnej listy?\n\n'
                        f'[B]TAK[/B] - dodaj do czarnej listy i blokuj podobne linki.\n'
                        f'[B]NIE[/B] - nie dodawaj, tylko zatrzymaj odtwarzanie.'
                    ),
                    nolabel='NIE',
                    yeslabel='TAK'
                )
            except Exception:
                fflog_exc(1)

            if _add_to_blacklist:
                fflog('[RES_CHECK] user decision: TAK -> zapis do czarnej listy', 1)
                try:
                    if cache_key_url:
                        bookmarks.group_cache_record_lowres(cache_key_url, declared_raw, actual_h, min_required)
                except Exception:
                    fflog_exc(1)
                try:
                    if cache_key_fp:
                        bookmarks.group_cache_record_lowres(cache_key_fp, declared_raw, actual_h, min_required)
                except Exception:
                    fflog_exc(1)
            else:
                fflog('[RES_CHECK] user decision: NIE -> bez zapisu do czarnej listy, kontynuuje odtwarzanie', 1)
                return

            # ZMIANA (2026-04) [PATCH]: REVERT — przywrocono oryginalne self.stop() po TAK
            # POWOD: Poprzednia proba usunela ten stop zakladajac ze film jest juz zatrzymany
            #   przez stop-before-dialog. Po revercie stop-before-dialog, ten stop znow jest
            #   potrzebny (film gra az do tego momentu w TAK-path).
            # NIE ZMIENIAC: nie usuwac self.stop() bez cofniecia revertu wyzej.
            try:
                if self.isPlayingVideo() and not getattr(self, '_stop_in_progress', False):
                    self.stop()
            except Exception:
                fflog_exc(1)
        except Exception:
            fflog_exc(1)


def time_to_seconds(time_str):
    if ':' in str(time_str):
        time_parts = time_str.split(':')
        if len(time_parts) == 3:
            hours, minutes, seconds = map(int, time_parts)
            return hours * 3600 + minutes * 60 + seconds
        elif len(time_parts) == 2:
            minutes, seconds = map(int, time_parts)
            return minutes * 60 + seconds
        else:
            raise ValueError("Nieprawidłowy format czasu.")
    else:
        # raise ValueError("Czas musi zawierać dwukropek.")
        return time_str
