# -*- coding: utf-8 -*-
"""
SearchSourcesDialog – dialog postępu wyszukiwania źródeł FanVodPL.
PNG generowane w locie i zapisywane do special://temp/ przez xbmcvfs
– działa na PC, Android, LibreELEC, każdej platformie Kodi.
"""
import base64
import struct
import zlib
import os

import xbmc
import xbmcgui
import xbmcvfs

ACTION_PREVIOUS_MENU = 10
ACTION_NAV_BACK      = 92

_COL_WHITE = '0xFFFFFFFF'
_COL_LIGHT = '0xFFDDDDDD'
_COL_GREY  = '0xFFAAAAAA'
_COL_LBLUE = '0xFFB0D8FF'
_COL_LGRN  = '0xFF90EE90'
_W, _H     = 1280, 720
_CENTER    = 6
_RIGHT     = 2

def _get_screen_scale():
    """Zwraca współczynnik skalowania względem 1280x720."""
    try:
        w = xbmcgui.Window(10000).getWidth()
        h = xbmcgui.Window(10000).getHeight()
        if w > 0 and h > 0:
            return min(w / 1280.0, h / 720.0)
    except Exception:
        pass
    return 1.0

# ─── Generator PNG ────────────────────────────────────────────────

def _make_png(w, h, pixels_fn):
    def chunk(name, data):
        c = struct.pack('>I', len(data)) + name + data
        return c + struct.pack('>I', zlib.crc32(name + data) & 0xffffffff)
    sig  = b'\x89PNG\r\n\x1a\n'
    ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
    rows = b''
    for y in range(h):
        row = b'\x00'
        for x in range(w):
            row += bytes(pixels_fn(x, y))
        rows += row
    idat = chunk(b'IDAT', zlib.compress(rows, 6))
    iend = chunk(b'IEND', b'')
    return sig + ihdr + idat + iend

def _solid(w, h, r, g, b, a=255):
    return _make_png(w, h, lambda x, y: (r, g, b, a))

def _rounded(W, H, R, r, g, b, a=255):
    def px(x, y):
        cx = R if x < R else (W-1-R if x > W-1-R else x)
        cy = R if y < R else (H-1-R if y > H-1-R else y)
        d  = ((x-cx)**2 + (y-cy)**2) ** 0.5
        if d > R + 0.5: return (0, 0, 0, 0)
        if d > R - 0.5:
            aa = int(255 * (R + 0.5 - d))
            return (r, g, b, min(a, aa))
        return (r, g, b, a)
    return _make_png(W, H, px)

# ─── Zapis przez xbmcvfs do special://temp/ ────────────────────────

_CACHE = {}   # name -> special:// path

def _tex(name, data):
    """Zapisuje dane PNG do special://temp/ i zwraca ścieżkę."""
    if name in _CACHE:
        return _CACHE[name]
    special = 'special://temp/fanvod_%s' % name
    try:
        f = xbmcvfs.File(special, 'w')
        f.write(bytearray(data))
        f.close()
        _CACHE[name] = special
        xbmc.log('[SSD] zapisano: %s' % special, xbmc.LOGDEBUG)
    except Exception as e:
        xbmc.log('[SSD] blad zapisu %s: %s' % (name, e), xbmc.LOGWARNING)
    return special

def _init_textures(pw, ph, bw, bh):
    """Generuje i zapisuje wszystkie tekstury przy pierwszym użyciu."""
    _tex('overlay.png',   _solid(4, 4,   0,   0,   0, 175))
    _tex('panel.png',     _rounded(pw, ph, 24,  18,  18,  22, 230))
    _tex('blue.png',      _rounded(bw, bh, 10,  20,  70, 170, 255))
    _tex('blue_hdr.png',  _rounded(bw,  44, 10,  12,  45, 110, 255))
    _tex('green.png',     _rounded(bw, bh, 10,  25, 120,  50, 255))
    _tex('grn_hdr.png',   _rounded(bw,  44, 10,  15,  75,  30, 255))
    _tex('track.png',     _rounded(860,  16,  8,  35,  35,  42, 255))
    _tex('bar.png',       _solid(4, 12,  30, 130, 230, 255))
    _tex('sep.png',       _solid(4,  2,  70,  70,  80, 200))
    # poświata
    def glow(x, y):
        c = 14.0
        a = int(110 * max(0, 1 - (abs(y - c) / c) ** 1.5))
        return (60, 160, 255, a)
    _tex('glow.png', _make_png(4, 28, glow))
    # lewa końcówka paska
    R2 = 6
    def lcap(x, y):
        cx, cy = R2, R2
        if x >= R2: return (30, 130, 230, 255)
        d = ((x-cx)**2 + (y-cy)**2) ** 0.5
        if d > R2+0.5: return (0,0,0,0)
        if d > R2-0.5: return (30,130,230, int(255*(R2+0.5-d)))
        return (30, 130, 230, 255)
    _tex('bar_l.png', _make_png(12, 12, lcap))
    # prawa końcówka paska
    def rcap(x, y):
        cx, cy = R2-1, R2
        if x <= R2-1: return (30, 130, 230, 255)
        d = ((x-cx)**2 + (y-cy)**2) ** 0.5
        if d > R2+0.5: return (0,0,0,0)
        if d > R2-0.5: return (30,130,230, int(255*(R2+0.5-d)))
        return (30, 130, 230, 255)
    _tex('bar_r.png', _make_png(12, 12, rcap))


def _best_quality(q4k, q1440, q1080, q720, qsd):
    if q4k:   return '4K'
    if q1440: return '2K / 1440p'
    if q1080: return 'FullHD / 1080p'
    if q720:  return 'HD / 720p'
    if qsd:   return 'SD'
    return ''


# ─── Dialog ───────────────────────────────────────────────────────

class SearchSourcesDialog(xbmcgui.WindowDialog):

    def __init__(self, title='', meta='', poster='', rating='', white_png=''):
        super(SearchSourcesDialog, self).__init__()
        self._canceled = False
        self._poster   = poster

        # Dynamiczne skalowanie do rozdzielczości ekranu
        scale = _get_screen_scale()
        # Okno zajmuje ~89% szerokości i ~64% wysokości wirtualnej przestrzeni
        self._pw = int(_W * 0.89)
        self._ph = int(_H * 0.64)
        self._px = (_W - self._pw) // 2
        self._py = (_H - self._ph) // 2
        # Każdy przycisk zajmuje ~47% szerokości panelu
        self._bw = int((self._pw - 30) // 2)
        self._bh = int(self._ph * 0.43)
        self._scale = scale
        _init_textures(self._pw, self._ph, self._bw, self._bh)
        self._build_ui(title, meta, rating)

    def _img(self, x, y, w, h, name):
        path = _CACHE.get(name, '')
        if not path:
            return None
        ctrl = xbmcgui.ControlImage(x, y, w, h, path, aspectRatio=0)
        self.addControl(ctrl)
        return ctrl

    def _raw(self, x, y, w, h, path):
        if not path: return None
        ctrl = xbmcgui.ControlImage(x, y, w, h, path, aspectRatio=0)
        self.addControl(ctrl)
        return ctrl

    def _lbl(self, x, y, w, h, text, font='font13', color=_COL_WHITE, align=0):
        ctrl = xbmcgui.ControlLabel(x, y, w, h, text,
                                    font=font, textColor=color, alignment=align)
        self.addControl(ctrl)
        return ctrl

    def _build_ui(self, title, meta, rating):
        px, py = self._px, self._py
        pw, ph = self._pw, self._ph
        bw, bh = self._bw, self._bh

        # Poster jako tło
        if self._poster and os.path.isfile(self._poster):
            self._raw(0, 0, _W, _H, self._poster)

        # Ciemna nakładka
        self._img(0, 0, _W, _H, 'overlay.png')

        # Główny kontener
        self._img(px, py, pw, ph, 'panel.png')

        # Tytuł
        self._lbl(px, py + int(ph * 0.04), pw, int(ph * 0.09),
                  '[B]%s[/B]' % title,
                  font='font20', color=_COL_WHITE, align=_CENTER)

        # Meta / rating
        parts = []
        if rating:
            parts.append('[COLOR gold][B]* %s[/B][/COLOR]' % rating)
        if meta:
            parts.append(meta)
        if parts:
            self._lbl(px, py + int(ph * 0.16), pw, int(ph * 0.07),
                      '   |   '.join(parts),
                      font='font13', color=_COL_LIGHT, align=_CENTER)

        # Separator
        self._img(px + 20, py + int(ph * 0.25), pw - 40, 2, 'sep.png')

        # ── PREMIUM ──────────────────────────────────────────────
        panel_y = py + int(ph * 0.27)
        bx = px + 15

        self._img(bx, panel_y, bw, bh, 'blue.png')
        self._img(bx, panel_y, bw, 44, 'blue_hdr.png')

        self._lbl(bx + 10, panel_y + 9, bw - 20, 28,
                  '[B]  Premium: filtrowane[/B]',
                  font='font14', color=_COL_WHITE)

        self._lbl(bx + 10, panel_y + int(bh * 0.27), bw - 20, int(bh * 0.13),
                  '[B]Zaawansowane filtry jakości video i dźwięku.[/B]',
                  font='font13', color=_COL_LIGHT)
        self._lbl(bx + 10, panel_y + int(bh * 0.39), bw - 20, int(bh * 0.13),
                  '[B]Wyjątek: filmy 1950–2005 i seriale 1950–2015[/B]',
                  font='font13', color=_COL_LIGHT)
        self._lbl(bx + 10, panel_y + int(bh * 0.51), bw - 20, int(bh * 0.13),
                  '[B]— filtry pomijane, linki bez ograniczeń.[/B]',
                  font='font13', color=_COL_LIGHT)
        self._lbl(bx + 10, panel_y + int(bh * 0.66), bw - 20, int(bh * 0.13),
                  '[B]Działa na: tb7, xt7, nopremium,[/B]',
                  font='font13', color=_COL_LBLUE)
        self._lbl(bx + 10, panel_y + int(bh * 0.78), bw - 20, int(bh * 0.13),
                  '[B]rapideo, twojlimit, CDA Premium.[/B]',
                  font='font13', color=_COL_LBLUE)

        # ── DARMOWE ───────────────────────────────────────────────
        fx = bx + bw + 10

        self._img(fx, panel_y, bw, bh, 'green.png')
        self._img(fx, panel_y, bw, 44, 'grn_hdr.png')

        self._lbl(fx + 10, panel_y + 9, bw - 20, 28,
                  '[B]  Darmowe[/B]',
                  font='font14', color=_COL_WHITE)

        self._lbl(fx + 10, panel_y + int(bh * 0.29), bw - 20, int(bh * 0.13),
                  '[B]Bez filtra — przechodzi każda jakość.[/B]',
                  font='font13', color=_COL_LIGHT)
        self._lbl(fx + 10, panel_y + int(bh * 0.44), bw - 20, int(bh * 0.13),
                  '[B]Wszystkie dostępne źródła.[/B]',
                  font='font13', color=_COL_LGRN)

        # ── PASEK POSTĘPU ─────────────────────────────────────────
        prx = px + 20
        pry = py + ph - int(ph * 0.14)
        prw = pw - 40
        prh = 16
        bh2 = 12
        byo = (prh - bh2) // 2

        self._img(prx, pry, prw, prh, 'track.png')

        # Poświata
        gp = _CACHE.get('glow.png', '')
        self._prog_glow = xbmcgui.ControlImage(prx, pry - 6, 1, 28, gp, aspectRatio=0)
        self.addControl(self._prog_glow)

        # Lewa końcówka
        lp = _CACHE.get('bar_l.png', '')
        self._bar_lcap = xbmcgui.ControlImage(prx, pry + byo, 12, bh2, lp, aspectRatio=0)
        self.addControl(self._bar_lcap)

        # Wypełnienie
        bp = _CACHE.get('bar.png', '')
        self._prog_fill = xbmcgui.ControlImage(prx + 6, pry + byo, 1, bh2, bp, aspectRatio=0)
        self.addControl(self._prog_fill)

        # Prawa końcówka
        rp = _CACHE.get('bar_r.png', '')
        self._bar_rcap = xbmcgui.ControlImage(prx + 6, pry + byo, 12, bh2, rp, aspectRatio=0)
        self.addControl(self._bar_rcap)

        self._prog_max_w = prw - 12
        self._prx = prx
        self._pry_byo = pry + byo

        # Status
        self._lbl_status = self._lbl(
            px, pry + 22, pw, 28,
            'Trwa wyszukiwanie źródeł...',
            font='font13', color=_COL_LIGHT, align=_CENTER)

    # ── API ──────────────────────────────────────────────────────────
    def update_sources(self, premium_total=0, free_total=0, percent=0,
                       best_premium='', best_free='',
                       status='Trwa wyszukiwanie źródeł...'):
        try:
            pct   = max(0, min(100, int(percent)))
            bar_w = max(1, int(self._prog_max_w * pct / 100))
            self._update_bar(bar_w)
            if status is not None:
                self._lbl_status.setLabel(str(status))
        except Exception as e:
            xbmc.log('[SSD] update: %s' % str(e), xbmc.LOGWARNING)

    def _update_bar(self, bar_w):
        try:
            self._prog_fill.setWidth(max(1, bar_w))
            self._bar_rcap.setPosition(self._prx + 6 + max(1, bar_w), self._pry_byo)
            self._prog_glow.setWidth(max(1, bar_w + 6))
        except Exception:
            pass

    def update(self, percent=0, line=''):
        try:
            pct   = max(0, min(100, int(percent)))
            bar_w = max(1, int(self._prog_max_w * pct / 100))
            self._update_bar(bar_w)
            if line:
                self._lbl_status.setLabel(str(line))
        except Exception:
            pass

    def iscanceled(self):
        return self._canceled

    def onAction(self, action):
        if action.getId() in (ACTION_PREVIOUS_MENU, ACTION_NAV_BACK):
            self._canceled = True
            self.close()


def create_search_dialog(title='', meta='', poster='', rating='', white_png=''):
    dlg = SearchSourcesDialog(title=title, meta=meta, poster=poster, rating=rating)
    dlg.show()
    return dlg
