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

import os
import re
import sys

try:
    import urllib.parse as urllib
except:
    pass

# from kover import autoinstall  # noqa: F401
import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs

integer = 1000

lang = xbmcaddon.Addon().getLocalizedString

lang2 = xbmc.getLocalizedString

setting = xbmcaddon.Addon().getSetting

setSetting = xbmcaddon.Addon().setSetting

addon = xbmcaddon.Addon

addItem = xbmcplugin.addDirectoryItem

addItems = xbmcplugin.addDirectoryItems

item = xbmcgui.ListItem

directory = xbmcplugin.endOfDirectory

content = xbmcplugin.setContent

pluginCategory = xbmcplugin.setPluginCategory

property = xbmcplugin.setProperty

sortMethod = xbmcplugin.addSortMethod

addonInfo = xbmcaddon.Addon().getAddonInfo

infoLabel = xbmc.getInfoLabel

condVisibility = xbmc.getCondVisibility

jsonrpc = xbmc.executeJSONRPC

window = xbmcgui.Window(10000)

dialog = xbmcgui.Dialog()

progressDialog = xbmcgui.DialogProgress()

progressDialogBG = xbmcgui.DialogProgressBG()

windowDialog = xbmcgui.WindowDialog()

button = xbmcgui.ControlButton

image = xbmcgui.ControlImage

getCurrentDialogId = xbmcgui.getCurrentWindowDialogId()
currentDialogId =    xbmcgui.getCurrentWindowDialogId

currentWindowId = xbmcgui.getCurrentWindowId()

keyboard = xbmc.Keyboard

log = xbmc.log

monitor = xbmc.Monitor()

# Modified `sleep` command that honors a user exit request  # ale jest przecież funkcja do tego o nazwie "waitForAbort()" - czas w sekundach
def sleep(time):
    monitor = xbmc.Monitor()
    monitor.waitForAbort(time/1000)
    """
    while time > 0 and not monitor.abortRequested():
        xbmc.sleep( min(50, time) )  # zawsze nie dłużej niż 50ms (może być krócej)
        time = time - 50
    """

sleep0 = xbmc.sleep  # msec

execute = xbmc.executebuiltin

skin = xbmc.getSkinDir()

player = xbmc.Player()

playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)

resolve = xbmcplugin.setResolvedUrl

fileStat = xbmcvfs.Stat

makeLegalFilename = xbmcvfs.makeLegalFilename

openFile = xbmcvfs.File  # z parametrem "w" utworzony zostanie pusty plik

makeFile = xbmcvfs.mkdir  # nie rozumiem, dlaczego ktoś tak nazwał alias funkcji tworzącej folder
makeDir = xbmcvfs.mkdir  # nazwa adekwatniejsza niż ta powyżej

makeDirs = xbmcvfs.mkdirs

deleteFile = xbmcvfs.delete

deleteDir = xbmcvfs.rmdir

listDir = xbmcvfs.listdir

renameF = xbmcvfs.rename

existsPath = xbmcvfs.exists

validPath = xbmcvfs.validatePath

transPath = xbmcvfs.translatePath

skinPath = xbmcvfs.translatePath("special://skin/")

addonPath = xbmcvfs.translatePath(addonInfo("path"))

dataPath = xbmcvfs.translatePath(addonInfo("profile"))

settingsFile = os.path.join(dataPath, "settings.xml")

viewsFile = os.path.join(dataPath, "views.db")

bookmarksFile = os.path.join(dataPath, "bookmarks.db")

providercacheFile = os.path.join(dataPath, "providers.13.db")

episodesFile = os.path.join(dataPath, "episodes.json")

metacacheFile = os.path.join(dataPath, "meta.5.db")

sourcescacheFile = os.path.join(dataPath, "sources.db")

searchFile = os.path.join(dataPath, "search.1.db")

libcacheFile = os.path.join(dataPath, "library.db")

cacheFile = os.path.join(dataPath, "cache.db")

downloadsFile = os.path.join(dataPath, "downloads.db")

key = "RgUkXp2s5v8x/A?D(G+KbPeShVmYq3t6"

iv = "p2s5v8y/B?E(H+Mb"


def autoTraktSubscription(tvshowtitle, year, imdb, tmdb):
    from . import libtools

    libtools.libtvshows().add(tvshowtitle, year, imdb, tmdb)


def addonIcon():
    theme = appearance()
    art = artPath()
    if not (art is None and theme in ["-", ""]):
        return os.path.join(art, "icon.png")
    return addonInfo("icon")


def addonThumb():
    theme = appearance()
    art = artPath()
    if not (art is None and theme in ["-", ""]):
        return os.path.join(art, "poster.png")
    elif theme == "-":
        return "poster.png"
    return addonInfo("icon")


def addonPoster():
    theme = appearance()
    art = artPath()
    if not (art is None and theme in ["-", ""]):
        return os.path.join(art, "poster.png")
    return "poster.png"


def addonBanner():
    theme = appearance()
    art = artPath()
    if not (art is None and theme in ["-", ""]):
        return os.path.join(art, "banner.png")
    return "banner.png"


def addonFanart():
    theme = appearance()
    art = artPath()
    if not (art is None and theme in ["-", ""]):
        return os.path.join(art, "fanart.jpg")
    return addonInfo("fanart.jpg")


def addonLandscape():
    theme = appearance()
    art = artPath()
    if art is None and theme in ["-", ""]:
        path = "landscape.jpg"
    else:
        path = os.path.join(art, "landscape.jpg")
    return path if os.path.exists(path) else addonFanart()


def addonNext():
    theme = appearance()
    art = artPath()
    if not (art is None and theme in ["-", ""]):
        return os.path.join(art, "next.png")
    return "next.png"


def addonId():
    return addonInfo("id")


def addonName():
    return addonInfo("name")


def get_plugin_url(queries):
    try:
        query = urllib.urlencode(queries)
    except UnicodeEncodeError:
        for k in queries:
            if isinstance(queries[k], str):
                queries[k] = queries[k].encode("utf-8")
        query = urllib.urlencode(queries)
    addon_id = sys.argv[0]
    if not addon_id:
        addon_id = addonId()
    return addon_id + "?" + query


def artPath():
    # theme = appearance()
    theme = "incursion"
    if theme in ["-", ""]:
        return
    path_old = ""
    # najpierw spróbuj znaleźć grafiki w FanVodPL
    path_new = ""
    try:
        path_new = os.path.join(
            xbmcaddon.Addon("plugin.video.fanvodpl").getAddonInfo("path"),
            "resources",
            "media",
            theme,
        )
    except RuntimeError:
        path_new = ""
    return path_new if path_new and os.path.exists(path_new) else path_old


def appearance():
    try:
        appearance = setting("appearance.1").lower()
    except Exception:
        appearance = setting("appearance.alt").lower()
    return appearance


def artwork():
    return


def infoDialog(message, *args, **kwargs):
    """Uniwersalne powiadomienie (toast na dole ekranu)."""
    try:
        heading = kwargs.get("heading", addonInfo("name"))
    except Exception:
        heading = addonInfo("name")
    icon = kwargs.get("icon", "")
    try:
        time_ms = int(kwargs.get("time", 3000))
    except Exception:
        time_ms = 3000
    sound = bool(kwargs.get("sound", False))
    if len(args) >= 1:
        heading = args[0]
    if len(args) >= 2:
        third = args[1]
        if isinstance(third, (int, float)):
            time_ms = int(third)
        elif isinstance(third, str):
            icon = third
    if len(args) >= 3:
        fourth = args[2]
        if isinstance(fourth, (int, float)):
            time_ms = int(fourth)
    try:
        icon_key = (icon or "").upper()
    except Exception:
        icon_key = ""
    if icon_key == "ERROR":
        icon_id = xbmcgui.NOTIFICATION_ERROR
    elif icon_key in ("WARNING", "WARN"):
        icon_id = xbmcgui.NOTIFICATION_WARNING
    else:
        icon_id = xbmcgui.NOTIFICATION_INFO
    try:
        dialog.notification(heading, message, icon_id, time_ms, sound)
    except TypeError:
        dialog.notification(heading, message, icon_id, time_ms)


def yesnoDialog(
    line1="", line2="", line3="", heading=addonInfo("name"), nolabel="", yeslabel=""
):
    return dialog.yesno(heading, line1 + "\n" + line2 + "\n" + line3, nolabel, yeslabel)


def selectDialog(list, heading=addonInfo("name"), autoclose=0, preselect=-1, useDetails=False):
    return dialog.select(heading, list, autoclose=autoclose, preselect=preselect, useDetails=useDetails)


def metaFile():
    return None


def apiLanguage(ret_name=None):
    langDict = {
        "Albanian": "sq",
        "Arabic": "ar",
        "Bulgarian": "bg",
        "Catalan": "ca",
        "Chinese": "zh",
        "Croatian": "hr",
        "Czech": "cs",
        "Danish": "da",
        "Dutch": "nl",
        "English": "en",
        "Estonian": "et",
        "Finnish": "fi",
        "French": "fr",
        "German": "de",
        "Greek": "el",
        "Hebrew": "he",
        "Hungarian": "hu",
        "Italian": "it",
        "Japanese": "ja",
        "Korean": "ko",
        "Latvian": "lv",
        "Lithuanian": "lt",
        "Norwegian": "no",
        "Polish": "pl",
        "Portuguese": "pt",
        "Romanian": "ro",
        "Russian": "ru",
        "Serbian": "sr",
        "Slovak": "sk",
        "Slovenian": "sl",
        "Spanish": "es",
        "Swedish": "sv",
        "Thai": "th",
        "Turkish": "tr",
        "Ukrainian": "uk",
        "Vietnamese": "vi",
    }
    try:
        kodi_lang = xbmc.getLanguage(xbmc.ENGLISH_NAME)
    except Exception:
        kodi_lang = "English"
    code = langDict.get(kodi_lang, "en")
    if ret_name:
        # zwróć nazwę jeśli ktoś chce debugować
        return kodi_lang
    return {"tmdb": code, "trakt": code, "tvdb": code}


def version():
    num = ""
    try:
        version = addon("xbmc.addon").getAddonInfo("version")
    except:
        version = "999"
    for i in version:
        if i.isdigit():
            num += i
        else:
            break
    return int(num)


def cdnImport(uri, name):
    import imp
    from ptw.libraries import client

    path = os.path.join(dataPath, "py" + name)
    path = path.decode("utf-8")

    deleteDir(os.path.join(path, ""), force=True)
    makeFile(dataPath)
    makeFile(path)

    r = client.request(uri)
    p = os.path.join(path, name + ".py")
    f = openFile(p, "w")
    f.write(r)
    f.close()
    m = imp.load_source(name, p)

    deleteDir(os.path.join(path, ""), force=True)
    return m


def openSettings(query=None, id=addonInfo("id")):
    try:
        idle()
        execute("Addon.OpenSettings(%s)" % id)
        if query is None:
            raise Exception()
        c, f = query.split(".")
        execute("SetFocus(%i)" % (int(c) + 100))
        execute("SetFocus(%i)" % (int(f) + 200))
    except:
        return


def getCurrentViewId():
    win = xbmcgui.Window(xbmcgui.getCurrentWindowId())
    return str(win.getFocusId())


def refresh():
    return execute("Container.Refresh")


def update(url, replace=None):
    if replace:
        return execute("Container.Update(%s, replace)" % url)
    else:
        return execute("Container.Update(%s)" % url)


def busy():
    Kodi = xbmc.getInfoLabel("System.BuildVersion")[:2]
    try:
        Kodi = int(Kodi)
        if Kodi > 17:
            if not condVisibility("Window.IsActive(busydialognocancel)") and not condVisibility("Window.IsActive(busydialog)"):
                execute("ActivateWindow(busydialognocancel)")  # Kodi 18
        else:
            if not condVisibility("Window.IsActive(busydialog)"):
                execute("ActivateWindow(busydialog)")  # Kodi 17
    except Exception:
        pass


def idle(mode=0):
    if mode != 2 and condVisibility("Window.IsActive(busydialog)"):
        execute("Dialog.Close(busydialog)")  # Kodi 17
    if mode != 1 and condVisibility("Window.IsActive(busydialognocancel)"):
        execute("Dialog.Close(busydialognocancel)")  # Kodi 18


def queueItem():
    return execute("Action(Queue)")


def metadataClean(
    metadata,
):  # Filter out non-existing/custom keys. Otherise there are tons of errors in Kodi 18 log.
    if metadata is None:
        return metadata
    allowed = [
        "genre",
        "country",
        "year",
        "episode",
        "season",
        "sortepisode",
        "sortseason",
        "episodeguide",
        "showlink",
        "top250",
        "setid",
        "tracknumber",
        "rating",
        "userrating",
        "watched",
        "playcount",
        "overlay",
        "cast",
        "castandrole",
        "director",
        "mpaa",
        "plot",
        "plotoutline",
        "title",
        "originaltitle",
        "sorttitle",
        "duration",
        "studio",
        "tagline",
        "writer",
        "tvshowtitle",
        "premiered",
        "status",
        "set",
        "setoverview",
        "tag",
        "imdbnumber",
        "code",
        "aired",
        "credits",
        "lastplayed",
        "album",
        "artist",
        "votes",
        "path",
        "trailer",
        "dateadded",
        "mediatype",
        "dbid",
    ]
    return {k: v for k, v in metadata.items() if k in allowed}


class settings:
    def getInt(id):
        try:
            n = int(setting(id))
        except:
            n = 0
        return n
    
    def getBool(id):
        return True if setting(id) == "true" else False

    def getString(id):
        return str(setting(id))

def _strip_kodi_markup(text):
    text = '' if text is None else str(text)
    text = re.sub(r'\[COLOR[^\]]*\]', '', text, flags=re.I)
    text = re.sub(r'\[/COLOR\]|\[/?(?:B|I|LIGHT|UPPERCASE|LOWERCASE|CAPITALIZE)\]', '', text, flags=re.I)
    return text.strip()


def _extract_media_details(filename):
    filename = _strip_kodi_markup(filename)
    upper = filename.upper()

    resolution = 'brak danych'
    for token, label in (('2160', '4K (2160p)'), ('1080', 'Full HD (1080p)'), ('720', 'HD (720p)'), ('480', 'SD (480p)')):
        if token in upper:
            resolution = label
            break

    audio_bits = []
    if 'ATMOS' in upper:
        audio_bits.append('Dolby Atmos')
    if 'TRUEHD' in upper:
        audio_bits.append('TrueHD')
    if 'DDP5.1' in upper or 'DDP 5.1' in upper:
        audio_bits.append('DDP5.1')
    elif 'DD5.1' in upper or 'DD 5.1' in upper:
        audio_bits.append('DD5.1')
    elif 'AAC' in upper:
        audio_bits.append('AAC')
    elif 'DTS' in upper:
        audio_bits.append('DTS')
    if 'MULTI' in upper:
        audio_bits.append('MULTI')
    elif re.search(r'\bPL\b', upper):
        audio_bits.append('PL')
    audio = ' / '.join(dict.fromkeys(audio_bits)) if audio_bits else 'brak danych'

    file_format = 'brak danych'
    ext_match = re.search(r'\.([a-z0-9]{2,5})$', filename, flags=re.I)
    if ext_match:
        file_format = ext_match.group(1).upper()
    else:
        for token in ('MKV', 'MP4', 'AVI', 'M2TS', 'TS'):
            if token in upper:
                file_format = token
                break

    return resolution, audio, file_format


def _build_rich_confirm_fallback(title, fields):
    lines = []
    for label, value in fields:
        label = _strip_kodi_markup(label)
        value = _strip_kodi_markup(value)
        if value:
            lines.append('%s: %s' % (label, value))
    return '\n'.join(lines)


def show_rich_confirm_dialog(title, filename='', size='', transfer='', remaining='', host='', info='', operation='Czy chcesz odtworzyć tę pozycję?', yeslabel='Odtwórz', nolabel='Anuluj'):
    filename = filename or ''
    resolution, audio, file_format = _extract_media_details(filename)
    size = _strip_kodi_markup(size) or 'brak danych'
    transfer = _strip_kodi_markup(transfer) or size
    remaining = _strip_kodi_markup(remaining) or 'brak danych'
    host = _strip_kodi_markup(host) or 'brak danych'
    info = _strip_kodi_markup(info) or 'Potwierdzenie uruchomienia źródła.'
    operation = _strip_kodi_markup(operation) or 'Czy chcesz kontynuować?'

    fields = [
        ('Operacja', operation),
        ('Plik', filename or 'brak danych'),
        ('Rozdzielczość', resolution),
        ('Audio', audio),
        ('Format', file_format),
        ('Rozmiar', size),
        ('Transfer', transfer),
        ('Stan konta', remaining),
        ('Host', host),
        ('Informacja', info),
    ]

    try:
        import pyxbmct.addonwindow as pyxbmct

        class _RichConfirmDialog(pyxbmct.AddonDialogWindow):
            def __init__(self, dlg_title, dlg_fields, dlg_yes, dlg_no):
                super(_RichConfirmDialog, self).__init__(dlg_title)
                self._result = False
                wrapped = []
                for label, value in dlg_fields:
                    text_value = _strip_kodi_markup(value)
                    chunks = [text_value[i:i + 56] for i in range(0, max(len(text_value), 1), 56)] or ['']
                    wrapped.append((_strip_kodi_markup(label), chunks[:3]))

                total_rows = min(max(14, sum(len(lines) for _, lines in wrapped) + 4), 22)
                self.setGeometry(1180, 760, total_rows, 8)

                row = 0
                header = pyxbmct.Label('[B]%s[/B]' % _strip_kodi_markup(dlg_title), alignment=pyxbmct.ALIGN_CENTER)
                self.placeControl(header, row, 0, 1, 8)
                row += 1

                for label, lines in wrapped:
                    label_ctrl = pyxbmct.Label('[B]%s[/B]' % label)
                    self.placeControl(label_ctrl, row, 0, 1, 2)
                    value_ctrl = pyxbmct.Label(lines[0])
                    self.placeControl(value_ctrl, row, 2, 1, 6)
                    row += 1
                    for extra_line in lines[1:]:
                        extra_ctrl = pyxbmct.Label(extra_line)
                        self.placeControl(extra_ctrl, row, 2, 1, 6)
                        row += 1

                row += 1
                self.btn_yes = pyxbmct.Button(dlg_yes)
                self.btn_no = pyxbmct.Button(dlg_no)
                self.placeControl(self.btn_yes, row, 1, 1, 3)
                self.placeControl(self.btn_no, row, 4, 1, 3)
                self.connect(self.btn_yes, self._on_yes)
                self.connect(self.btn_no, self._on_no)
                self.connect(pyxbmct.ACTION_NAV_BACK, self._on_no)
                self.setFocus(self.btn_yes)
                try:
                    self.btn_yes.controlRight(self.btn_no)
                    self.btn_no.controlLeft(self.btn_yes)
                except Exception:
                    pass

            def _on_yes(self):
                self._result = True
                self.close()

            def _on_no(self):
                self._result = False
                self.close()

        dialog_window = _RichConfirmDialog(title, fields, yeslabel, nolabel)
        dialog_window.doModal()
        result = dialog_window._result
        del dialog_window
        return result
    except Exception:
        return dialog.yesno(title, _build_rich_confirm_fallback(title, fields), yeslabel=yeslabel, nolabel=nolabel)
