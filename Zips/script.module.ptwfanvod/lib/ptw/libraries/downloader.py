"""
    Simple XBMC Download Script
    Copyright (C) 2013 Sean Poyser (seanpoyser@gmail.com)

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

import json
import hashlib
import os
import re
import threading
import time

from sqlite3 import dbapi2 as database, OperationalError
from urllib.parse import parse_qsl, urlparse, unquote

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import pyxbmct
import requests
# import xbmc
import xbmcgui
# import xbmcvfs  # w control jest dużo z tych funkcji

from ptw.libraries import control, cleantitle, source_utils
from ptw.libraries.log_utils import log, fflog
from ptw.debug import log_exception, fflog_exc


# fflog(f'{__name__=}',1,1)  # to nic nie daje
# można sprawdzić, kto próbuje skorzystać z tego modułu (poprzez import)
# fflog(f"{control.addon().getAddonInfo('name')=}",1,1)
# fflog(f'{control.addonInfo("name")=}',1,1)
fflog(f'{control.addonInfo("id")=}',0,1)


def download(name, image, url, extrainfo="", season_name=""):
    """ przygotowanie folderów tylko """
    # fflog(f'{url=}')
    if not url:
        fflog(f'{url=}',1,1)
        return

    if not isinstance(url, str):  # list or tuple
        url = url[0]

    try:
        headers = dict(parse_qsl(url.rsplit("|", 1)[1]))
    except:
        headers = dict("")

    url = url.split("|")[0]  # pozbycie się headerów z adresu url

    folder = ""

    name = unquote(name)
    # fflog(f'{name=}',1,1)
    if "/" in name:
        folder, _, name = name.rpartition("/")
        fflog(f'{folder=}',1,1)
        fflog(f'{name=}',1,1)
    else:
        fflog(f'{name=}',1,1)

    # content = re.compile(r"(.+?)\sS(\d*)E\d*$").findall(name)  # szukanie np. S01E01 na końcu
    content = re.compile(r"^(.+?)\sS(\d+)E\d+\s?(?!.*\.[a-z2438]{2,4}$)(.*)", re.I).findall(name)  # na koncu nie może być rozszerzenia
    # fflog(f'{content=}',1,1)
    
    def makeLegalFilename(name):
        # fflog(f'trans{name=}',1,1)
        transname = name.translate(str.maketrans("", "", r'\/:*?"<>|'))
        # fflog(f'{transname=}',1,1)
        # transname = control.makeLegalFilename(transname)  # część znaków jest zamieniana na _ np. : oraz dodaje mi / na końcu (może jak nie znajdzie kropki, to stwierdza, że to folder?)
        # fflog(f'{transname=}',1,1)
        # transname = transname.rstrip("/")  # ewentualny fix na slash na końcu
        if control.setting("download.diacritics") != "true":
            transname = cleantitle.normalize(transname)  # usuwa polskie znaki diakrytyczne
            # fflog(f'{transname=}',1,1)
        # transname = re.sub(r"/|:|\*|\?|\"|<|>|\+|,|\.|", "", cleantitle.normalize(name))  # znaku plusa bym nie wycinał
        return transname

    transname = makeLegalFilename(name)
    # fflog(f'{transname=}',1,1)
    
    transfolder = makeLegalFilename(folder)
    # fflog(f'{transfolder=}',1,1)

    # levels = ["../../../../../..", "../../../../..", "../../../..", "../../..", "../..", ".."]

    if len(content) == 0:  # movie
        # if control.addonInfo("id") != 'plugin.video.fanvodpl':  # ale to i tak nic nie, bo w Kodi każda inna wtyczka może zmienić ustawienia dla innej
            # dest = control.addon("plugin.video.fanvodpl").getSetting("movie.download.path")
        # else:
        dest = control.setting("movie.download.path")
        fflog(f'movie  {dest=}',1,1)
        if not dest:
            dest = control.addon("plugin.video.fanvodpl").getSetting("movie.download.path")
            fflog(f'movie  {dest=}',1,1)
            pass
        if not dest:
            try:
                control.infoDialog("Pobieranie nie działa. Skonfiguruj folder pobierania w ustawieniach FanVodPL.", icon="ERROR", sound=True)
            except Exception:
                pass
            return
        dest = control.transPath(dest)  # e.g. Converts 'special://home' -> '/home/[username]/.kodi' on Linux
        # fflog(f'{dest=}',1,1)
        # dest = control.validPath(dest)  # Only useful for fixing slash problems beetween operating systems (e.g. Corrects 'Z://something' -> 'Z:\something').
        # fflog(f'{dest=}',1,1)
        """
        for level in levels:  # teraz jest funkcja xbmcvfs.mkdirs(path) zamiast xbmcvfs.mkdir
            try:
                fflog(f'{os.path.abspath(os.path.join(dest, level))=}',1,1)
                control.makeFile(os.path.abspath(os.path.join(dest, level)))  # xbmcvfs.mkdir
            except Exception:
                fflog_exc(1)
                pass
        control.makeFile(dest)  # xbmcvfs.mkdir
        """
        ok = None
        try:
            fflog(f'sprawdzenie folderu {dest=}',0,1)
            # ok = xbmcvfs.mkdirs(dest)
            ok = control.makeDirs(dest)  # xbmcvfs.mkdirs
        except Exception:
            fflog(f'nie udało się przygotować folderu',1,1)
            fflog_exc(1)
            pass
        fflog(f'{ok=}',0,1)
        if not ok:
            fflog(f'nie udało się przygotować folderu {dest=}',1,1)
            xbmcgui.Dialog().ok("Błąd tworzenia folderu", f"{dest}\n\nMoże problem z prawami do zapisu?")
            return

        # dobrze byłoby, aby to tworzyło się dopiero po potwierdzeniu chęci albo możności pobrania pliku
        if folder:
            dest = os.path.join(dest, transfolder)
        elif control.setting("movie.download.in_folder") == "true":
            dest = os.path.join(dest, transname)
            # fflog(f'{dest=}',1,1)
            #control.makeFile(dest)  # przeniosłem do "doDownload"
        season = None

    else:  # tvshow
        dest = control.setting("tv.download.path")
        fflog(f'tvshow  {dest=}',1,1)
        if not dest:
            dest = control.addon("plugin.video.fanvodpl").getSetting("tv.download.path")
            fflog(f'tvshow  {dest=}',1,1)
            pass
        if not dest:
            try:
                control.infoDialog("Pobieranie nie działa. Skonfiguruj folder pobierania w ustawieniach FanVodPL.", icon="ERROR", sound=True)
            except Exception:
                pass
            return
        dest = control.transPath(dest)  # e.g. Converts 'special://home' -> '/home/[username]/.kodi' on Linux
        # fflog(f'{dest=}',1,1)
        # dest = control.validPath(dest)  # Only useful for fixing slash problems beetween operating systems (e.g. Corrects 'Z://something' -> 'Z:\something').
        # fflog(f'{dest=}',1,1)
        """
        for level in levels:
            try:
                control.makeFile(os.path.abspath(os.path.join(dest, level)))
            except Exception:
                fflog_exc(1)
                pass
        control.makeFile(dest)
        """
        ok = None
        try:
            fflog(f'sprawdzenie folderu {dest=}',0,1)
            ok = control.makeDirs(dest)
        except Exception:
            fflog(f'nie udało się przygotować folderu',1,1)
            fflog_exc(1)
            pass
        fflog(f'{ok=}',0,1)
        if not ok:
            fflog(f'nie udało się przygotować folderu {dest=}',1,1)
            xbmcgui.Dialog().ok("Błąd tworzenia folderu", f"{dest}\n\nMoże problem z prawami do zapisu?")
            return
        r"""
        transtvshowtitle = content[0][0].translate(str.maketrans("", "", r'\/:*?"<>|.'))
        transtvshowtitle = cleantitle.normalize(transtvshowtitle)  # polskie znaki diakrytyczne
        # transtvshowtitle = re.sub(
        #     r"/|:|\*|\?|\"|<|>|",
        #     "",
        #     cleantitle.normalize(content[0][0].encode().decode("utf-8")),
        # )
        """
        transtvshowtitle = makeLegalFilename(content[0][0])
        season = content[0][1]
        # dobrze byłoby, aby to tworzyło się dopiero po potwierdzeniu chęci albo możności pobrania pliku
        # folder z nazwą serialu
        dest = os.path.join(dest, transtvshowtitle)
        #control.makeFile(dest)  # można by przenieść do "doDownload"
        # subfolder for season
        #dest = os.path.join(dest, "Season %01d" % int(content[0][1]))
        #control.makeFile(dest)

    ext = os.path.splitext(urlparse(url).path)[1][1:]
    #fflog(f'{ext=}')
    if not ext in ["mp4", "mkv", "flv", "avi", "mpg", "mov", "webm", "ts", "wmv", "vob", "m2ts", "mts"]:  # a co gdy będzie "m3u8" ("m3u")
        # ext = "mp4"
        ext = "unknow"  # później koryguję
        #fflog(f'{ext=}')

    # dodanie informacji np. o kodekach do nazwy pliku
    # extrainfo = extrainfo.replace(f"({ext})", "").replace("  ", " ")  # czasami typ pliku w informacjach
    extrainfo = re.sub(rf"\(?({ext}|mp4|m3u8)\)?", "", extrainfo).replace("  ", " ")  # czasami typ pliku w informacjach
    transname += f" {makeLegalFilename(extrainfo)}" if extrainfo and control.setting("download.extrainfo") == "true" else ""
    if not transname.endswith(ext):
        transname = transname + "." + ext
    # poniższą można by przenieść do "doDownload"
    #dest = os.path.join(dest, transname)  # new path - with filename
    # fflog(f'{name=}  {transname=}  {dest=}  {ext=}')
    #doDownload(url, dest, name, image, json.dumps(headers))
    return doDownload(url, dest, name, image, json.dumps(headers), transname, season, ext, season_name)


def getResponse(url, headers, size, requests_test_only=False):
    # fflog(f'{headers=}',0,1)
    try:
        if size > 0:
            size = int(size)
            headers["Range"] = "bytes=%d-" % size  # aby zacząć od miejsca, w którym zostało przerwane
        def do_req():
            if requests_test_only:
                r = requests.head(url, headers=headers, verify=False, allow_redirects=True)
            else:
                r = requests.get(url, headers=headers, verify=False, stream=True)
            fflog(f'{r=}',0,1)
            return r
        r = do_req()
        """
        if not r:
            if not headers.get("User-Agent"):
            # if "kodi" not in (headers.get("User-Agent") or "").lower():
                headers["User-Agent"] = 'kodi-agent/1.1'
                # fflog('replay',1,1)
                r = do_req()
        """
        return r
    except Exception:
        fflog_exc(1)
        return None


def done(title, dest, downloaded, text=""):
    #fflog(f'{title=} {dest=} {downloaded=}')

    # playing = xbmc.Player().isPlaying()
    playing = control.player.isPlaying()
    #fflog(f'{playing=}', 1)

    if not text:
        text = xbmcgui.Window(10000).getProperty("GEN-DOWNLOADED")  # do czego to służy ?
    #fflog(f'{text=}')

    if downloaded:
        head = "[COLOR forestgreen]Pobieranie zakończone[/COLOR]"
        message = title + "\n" + text
        icon = "INFO"
    else:
        head = "[COLOR red]Błąd pobierania[/COLOR]"
        message = title + "\n" + text
        icon = "ERROR"

    xbmcgui.Window(10000).setProperty("GEN-DOWNLOADED", text)  # do czego to służy ?

    fflog(f"{head}  {text}", 1)
    if not playing:
        if control.condVisibility('Window.IsActive(notification)'):
            control.infoDialog('', time=1, sound=False)
            control.sleep0(200)
        c = 3
        while control.condVisibility('Window.IsActive(notification)') and c > 0:
            control.sleep0(100)
            c -= 1

        xbmcgui.Dialog().ok(head, message)

        xbmcgui.Window(10000).clearProperty("GEN-DOWNLOADED")  # do czego to służy ?


def doDownload(url, dest, title, image="", headers="", transname="", season=None, ext="", season_name="", total=0, display_manager=True):
    fflog(f'{url=}\n {dest=}\n {title=}\n {transname=}\n {image=}\n {headers=}\n {total=}\n {ext=}\n {season=}\n {season_name=}',0,1)
    if total:
        fflog(f'próba wznowienia pobierania  {title=}  {total=}  {dest=}')
        pass
    try:
        try:
            headers = json.loads(headers)
        except Exception:
            fflog_exc(1)
            headers = {}

        #fflog(f'{url=} {headers=}')
        requests_test_only = True
        #resp = getResponse(url, headers, 0)  # zapytanie do serwera (pobieranie zacznie się dopiero jak wywołamy resp.text albo resp.iter_content() )
        #resp = getResponse(url, headers, 0, requests_test_only=True)  # zapytanie testujące do serwera
        resp = getResponse(url, headers, total, requests_test_only=requests_test_only)
        fflog(f'{resp=}',0,1)

        # print "Download Header"
        # print resp.headers
        fflog(f'{resp.headers=}',0,1) if resp is not None else ""

        # fflog(f'{resp.request=}')

        if not resp:
            fflog(f'{resp=}',1,1)
            xbmcgui.Dialog().ok("Niestety", f"Brak poprawnej odpowiedzi z serwera.\n\n{title.replace('.unknow', '', 1)}\n\nPobieranie niemożliwe.")
            return

        fflog(f'{resp.headers["Content-Type"]=}')

        # if resp.headers["Content-Type"] in ["text/html"] or "text/html" in resp.headers["Content-Type"] or "text/" in resp.headers["Content-Type"]:
        if any(x in resp.headers["Content-Type"] for x in ["text/html", "text/"]):
            resp.close()  # na wszelki wypadek
            fflog(f'najprawdopodobniej to jest strona html o jakimś komunikacie błędu')
            xbmcgui.Dialog().ok("Pobieranie nie będzie realizowane", "To nie jest plik wideo" + f'\n\n[I]{resp.headers["Content-Type"]}[/I]')
            return

        if resp.headers["Content-Type"] in ["application/vnd.apple.mpegurl", "application/x-mpegURL"]:
        # if "application/" in resp.headers["Content-Type"]:  # 'application/octet-stream' może być
            resp.close()  # na wszelki wypadek
            fflog(f'pobieranie takich typów (m3u8) nie jest obecnie zaimplementowane')
            xbmcgui.Dialog().ok("Pobieranie nie będzie realizowane", "Nieobsługiwany typ źródła" + f'\n\n[I]{resp.headers["Content-Type"]}[/I]')
            return False

        # test, jak poprzedni warunek zmienię
        if resp.headers["Content-Type"] in ["application/vnd.apple.mpegurl", "application/x-mpegURL"]:
            ext = "m3u8"
            transname = transname.replace(".mp4", f".{ext}", 1)
            title = title.replace(".mp4", f".{ext}", 1)
            transname = transname.replace(".unknow", f".{ext}", 1)
            title = title.replace(".unknow", f".{ext}", 1)

        if transname.endswith(".unknow"):
            ext = resp.headers["Content-Type"]
            ext = ext.rsplit("/", 1)[-1] if "video/" in ext else ""
            fflog(f'{ext=}')
            if ext:
                if ext == "mp4":
                    pass
                elif ext == "mpeg":
                    ext = "mpg"
                elif ext == "quicktime":
                    ext = "qt"
                elif ext == "x-ms-wmv":
                    ext = "wmv"
                elif ext == "x-msvideo":
                    ext = "avi"
                elif ext == "x-flv":
                    ext = "flv"
                elif ext == "x-webm":
                    ext = "webm"
                else:
                    ext = ""  # i co wtedy?
                    ext = "mp4"
            if ext:
                transname = transname.replace(".unknow", f".{ext}", 1)  # tylko co z identyfikatorem pobierania ?
                title = title.replace(".unknow", f".{ext}", 1)  # tylko co z identyfikatorem pobierania ?
            else:
                pass
            transname = transname.rstrip(".")
            title = title.rstrip(".")
            #id_downloading = transname or title
            #id_downloading = "FanVodPL-downloading-" + hashlib.md5(id_downloading.encode()).hexdigest()

    except Exception:
        fflog_exc(1)
        control.idle(2)
        xbmcgui.Dialog().ok("Niestety", "Wystąpił jakiś błąd\n\nSprawdź log")
        return
        pass

    # A CO JAK ROZSZERZENIE BĘDZIE DO KOREKCJI ?
    title = transname if transname else title
    # id_downloading = os.path.join(dest, transname)  # takie przybliżenie, bo url się może niestety zmieniać
    id_downloading = transname or title  # bo potrzebne mi w managerze, abym mógł sobie obliczyć i przerwać ewentualnie proces pobierania
    #fflog(f'{id_downloading=}')
    id_downloading = "FanVodPL-downloading-" + hashlib.md5(id_downloading.encode()).hexdigest()
    #fflog(f'{id_downloading=}')
    #fflog(f'{xbmcgui.Window(10000).getProperty(id_downloading)=}')
    if xbmcgui.Window(10000).getProperty(id_downloading):
        fflog(f'{xbmcgui.Window(10000).getProperty(id_downloading)=}')
        #fflog('wykryto trwające pobieranie z tego adresu url')
        fflog(f'wykryto trwające pobieranie pliku {title}')
        control.idle(2)
        control.sleep(100)
        """
        xbmcgui.Dialog().ok(
            title, "\nBłąd" + "\nPobieranie z tego źródła już trwa"
        )
        return
        """
        if (
            ans := xbmcgui.Dialog().yesnocustom(
            # not xbmcgui.Dialog().yesno(
                #title + "\n - Potwierdź pobieranie",
                #"UWAGA - Pobieranie z tego źródła już trwa",
                "UWAGA - Pobieranie takiego pliku już trwa",
                "Czy chcesz przerwać to pobieranie ?",
                yeslabel="Przerwij",  # 1
                nolabel="Kontynuuj",  # 0
                customlabel="Pokaż Menadżera",  # 2
            )
            # == 1
        ) == 0:
            fflog('zdecydowano o kontynuowaniu pobierania')
            return
        elif ans == 2:
            fflog('wybrano wyświetlenie Menadżera pobierania')
            threading.Thread(target=downloadManager, ).start()
            return
        else:
            # fflog(f'{ans=}')
            # przerwanie pobierania
            fflog('wysłanie sygnału do przerwania pobierania')
            xbmcgui.Window(10000).setProperty(id_downloading, 'break')
            control.sleep(500)
            c = 9
            while xbmcgui.Window(10000).getProperty(id_downloading) == 'break' and c:
                c -= 1
                control.sleep(500)
            if not c:
                fflog(f'awaryjne odblokowanie identyfikatora pobierania')
                xbmcgui.Window(10000).clearProperty(id_downloading)
            return

    # naprawa stanu w sytuacji, gdy np. podczas przerzucania zanikł prąd
    dest2 = dest + ".part"  # plik kopii awaryjnego kontynuowania
    if control.existsPath(dest2):
        fflog(f'wykryto plik tymczasowy {dest2=}')
        control.deleteFile(dest)  # bo może remove nie zadziałać
        ok = control.renameF(dest2, dest)  # przywrócenie pierwotnego stanu
        if not ok:
            fflog(f'nie udało się przywrócić pierwotnego pliku {dest=} | Może problem z prawami do zapisu?',1,1)
            # xbmcgui.Dialog().ok("Błąd przywracania pierwotnego pliku", f"{dest}\n\nMoże problem z prawami do zapisu?")
            # return

    # if total and not xbmcvfs.exists(dest):
    if total and not control.existsPath(dest):
        update(title, state="broken",)
        fflog("Kontynuowanie niemożliwe - Brak pliku z poprzedniego pobierania" + "" + title)
        xbmcgui.Dialog().ok("Kontynuowanie niemożliwe", "Brak pliku z poprzedniego pobierania" + "\n\n" + title)
        return

    if total:
        # st = xbmcvfs.Stat(dest)  # chyba to samo co os.stat(file_name with path)
        st = control.fileStat(dest)
        fsize = st.st_size()
        """
        with xbmcvfs.File(dest) as f:
            fsize = f.size()
        """
        fflog(f'\n {fsize=} \n {total=}',0,1)

        if fsize != total:
            resp.close()  # na wszelki wypadek
            update(title, downloaded=total, state="broken",)
            fflog("Kontynuowanie niemożliwe - Rozmiar pliku z poprzedniego pobierania nie pasuje" + "" + title)
            xbmcgui.Dialog().ok("Kontynuowanie niemożliwe", "Rozmiar pliku z poprzedniego pobierania nie pasuje" + "\n\n" + title)
            return

    try:
        control.idle(2)
        control.sleep(100)

        try:
            content = int(resp.headers["Content-Length"])  # ile bajtów do pobrania (jak od początku, to sumaryczna wielkość pliku, a jak kontynuacja, to pozostała reszta do pobrania)
        except:
            content = 0
            content = -1

        if content < 1:
            # xbmcgui.Dialog().ok("Pobieranie niemożliwe", "Nieznany rozmiar do pobrania" + "\n\n" + title)
            # xbmcgui.Dialog().ok("UWAGA", "Nieznany rozmiar do pobrania" + "\n\n" + title)
            if (
                not xbmcgui.Dialog().yesno(
                    #title + "\n - Potwierdź pobieranie",
                    #"UWAGA - Pobieranie z tego źródła już trwa",
                    "UWAGA - Nieznany rozmiar do pobrania",
                    title + "\nCzy mimo to, chcesz kontynuować?",
                    yeslabel="Kontynuuj",
                    nolabel="Zrezygnuj",
                )
                == 1
            ):
                fflog(f'uzytkownik zrezygnował z powodu nieznanego rozmiaru do pobrania',1,1)
                resp.close()  # na wszelki wypadek
                return

            fflog(f'{resp=}',1,1)
            fflog(f'{resp.headers=}',1,1)
            # resp.close()  # na wszelki wypadek
            # return

        size = content + total  # sumaryczny rozmiar pliku (w bajtach)

        try:
            resumable = "bytes" in (resp.headers.get("Accept-Ranges") or "").lower() or "bytes" in (resp.headers.get("Content-Range") or "").lower()
        except Exception:
            fflog_exc(1)
            resumable = False

        if resumable:
            fflog("Download is resumable")
        else:
            fflog("Download is not resumable")
            pass

        if transname:
            file = transname
        elif title:
            file = title
        else:
            if "/" in dest:
                file = dest.rsplit("/", 1)[-1]
            else:
                file = dest.rsplit(os.sep, 1)[-1]
        # fflog(f'{title=}  {transname=}   {file=}  {os.sep=}',1,1)
        title = file  # wstawiany jest do bazy managera pobierania

        mb = content / (1024 * 1024)  # do pobrania w MB

        """
        size = 1024 * 1024  # = 1 MB  # do czego to miało służyć ?
        if content < size:
            size = content
        size = source_utils.convert_size(content)
        """

        if (
            not xbmcgui.Dialog().yesno(
                f"Potwierdź {'pobieranie' if not total else 'kontynuację pobierania'}",
                #file + "\n" + "Rozmiar: %d MB" % mb + "\nKontynuować pobieranie?",
                #file + "\n" + "do pobrania pozostało: %.2f MB" % mb,
                # file + "\n" + f"do pobrania{' pozostało' if total else ''}: " + source_utils.convert_size(content, True),
                file + "\n\n" + (f"do pobrania{' pozostało' if total else ''}: " + source_utils.convert_size(content, True) if content > 0 else ""),
                yeslabel="Pobieraj",
                nolabel="Anuluj",
            )
            == 1  # po co to ?
        ):
            resp.close()  # bo stream=True, więc może dalej trwać pobieranie danych z serwera
            #del window_manager
            return

        if total:
            content += total
            mb = content / (1024 * 1024)

        if transname:
            ok = None
            if not season:
                if control.setting("movie.download.in_folder") == "true" or not control.existsPath(dest):
                    ok = control.makeFile(dest)  # folder z nazwą pliku
                else:
                    # ok = True
                    pass
            else:
                ok = control.makeFile(dest)  # folder z nazwą serialu
                if ok:
                    # subfolder for season
                    if not season_name:
                        # season_name = "S"  # ale wóczas lepiej byłoby "s01"
                        # season_name = "Season"
                        country = control.infoLabel('ListItem.Country')
                        fflog(f'{country=}',1,1)
                        # season_name = "Season" if control.setting("library.localtitles_for_filenames") != "true" else "Sezon"
                        season_name = "Sezon" if country.lower() in ["poland", "pl", "polska"] else "Season"
                    dest = os.path.join(dest, season_name + " %01d" % int(season))
                    ok = control.makeFile(dest)
                else:
                    if not ok:
                        fflog(f'nie udało się przygotować folderu {dest=}',1,1)
                        xbmcgui.Dialog().ok("Błąd tworzenia folderu", f"{dest}\n\nMoże problem z prawami do zapisu?")
                        return
            fflog(f'{ok=}',0,1)
            if ok is not None and not ok:
                fflog(f'nie udało się przygotować folderu {dest=}',1,1)
                xbmcgui.Dialog().ok("Błąd tworzenia folderu", f"{dest}\n\nMoże problem z prawami do zapisu?")
                return
            # fflog(f'{dest=}',1,1)
            dest = os.path.join(dest, transname)  # new path - with filename
            # fflog(f'{dest=}',1,1)
            dest = control.validPath(dest)  # przydaje się
            # fflog(f'{dest=}',1,1)

        if control.existsPath(dest) and not total:
            fflog(f'wykryto, że plik już istnieje {dest=}')

            # st = xbmcvfs.Stat(dest)  # chyba to samo co os.stat(file_name with path)
            st = control.fileStat(dest)
            fsize = st.st_size()

            # dobrze byłoby zrobić jeszcze jakieś sprawdzenie, czy plik na dysku pochodzi ze źródła o takim samym rozmiarze jak wcześniej pobierany, bo są różne jakości mimo takiego samego opisu
            # albo nazwę tymczasową na czas ściągania, albo jakiś dodatkowy plik info, w którym byłby przechowywany rozmiar pobieranego źródła

            control.sleep(100)
            # fflog(f'{resumable=} {fsize=} {content=}')
            if resumable and fsize < content:
                ans = xbmcgui.Dialog().yesnocustom(
                    "UWAGA - Wykryto istniejący plik",
                    f" o takiej samej nazwie (na dysku: {source_utils.convert_size(fsize, True)}, na\u00A0serwerze: {source_utils.convert_size(content, True)})." + 
                        "\n\nCzy chcesz go zastąpić, czy może spróbować kontynuować poprzednie pobieranie ?",
                    customlabel="Kontynuuj",
                    yeslabel="Zastąp",
                    nolabel="Anuluj",
                )
                if ans < 1:
                    fflog(f'pobieranie nie będzie realizowane')
                    # xbmcgui.Dialog().ok(title, "\nBłąd" + "\npobieranie nie będzie realizowane")
                    xbmcgui.Dialog().notification(title, "\npobieranie nie będzie realizowane", "WARNING")
                    resp.close()
                    #del window_manager
                    return
                elif ans == 2:
                    resp.close()
                    control.sleep(100)
                    total = fsize
                    resp = getResponse(url, headers, total, requests_test_only=requests_test_only)
                    if not resp:
                        xbmcgui.Dialog().ok("Wystąpił błąd", f"Brak poprawnej odpowiedzi z serwera.\n\n{title}\n\nPobieranie niemożliwe.")
                        fflog(f'{resp=}',1,1)
                        return
            else:
                if (
                    not xbmcgui.Dialog().yesno(
                        "UWAGA - Wykryto istniejący plik",
                        " o takiej samej nazwie. \n\nCzy chcesz go zastąpić ?",
                        yeslabel="Zastąp",
                        nolabel="Anuluj",
                    )
                ):
                    fflog(f'pobieranie nie będzie realizowane')
                    # xbmcgui.Dialog().ok(title, "\nBłąd" + "\npobieranie nie będzie realizowane")
                    xbmcgui.Dialog().notification(title, "\npobieranie nie będzie realizowane", "WARNING")
                    resp.close()
                    #del window_manager
                    return

        try:
            progressDialog = None
            if total:
                # f = xbmcvfs.File(dest, "a")  # wg dokumentacji nie ma a (a szkoda)  https://forum.kodi.tv/showthread.php?tid=307996&pid=3232014
                dest1 = dest
                # fflog(f' {dest=}',1,1)
                if dest.startswith("smb://"):  # może trzeba by też dla innych jak np. "nfs"
                    # fixy, które zadziałały na Windowsie
                    # dest1 = dest1.replace("smb:", "")  # to pomogło tylko dla Kodi na  w niektórych przypadkach (gdy nie było hasła do udziału sieciowego)
                    dest1 = re.sub("^smb://([^@]*@)?", "//", dest1)  # to co wyżej, ale wycina hasło - jest szansa, że się połączy
                    dest1 = control.validPath(dest1)
                    dest1 = control.transPath(dest1)  # nie wiem, czy to potrzebne tu
                    fflog(f'{dest1=}',0,1)
                elif dest.startswith("nfs://"):  # nie testowałem
                    # fflog('przetestować trzeba',1,1)
                    pass
                # dest1 = "dupa"+dest1  # for TEST only
                try:
                    f = open(dest1, "ab")  # append binary mode
                except (OSError, UnicodeEncodeError):
                    fflog_exc(1)  # dla ciekawości
                    fflog('procedura obejściowa')
                    # dest2 = dest + ".part"  # teraz wcześniej to definiuje
                    control.renameF(dest, dest2)
                    ok = control.existsPath(dest2)  # kontrola, czy mam prawa do zapisu
                    if ok:
                        update(title, state="preparing")
                        f = control.openFile(dest, "w")
                        with control.openFile(dest2) as f2:
                            s = f2.size()
                            chunk_size = 1024*1024*2  # 2 MB
                            msg = 'kopiowanie zawartości poprzedniego pliku pobierania' + f' | ({source_utils.convert_size(total, True)})' 
                            fflog(msg + f'  chunk_size: {source_utils.convert_size(chunk_size, True)}')
                            progressDialog = control.progressDialogBG
                            progressDialog.create(msg)
                            t = 0
                            speed = ""
                            speed_update_interval = 0
                            prevt = t
                            old_time1 = time.time()
                            monitor = control.monitor
                            while not monitor.abortRequested() and (chunk := f2.readBytes(chunk_size)):  # nie wiem, jaki bufor najlepiej wybrać
                                if not monitor.abortRequested():  # bo czytanie też trochę trwa przy sieciowym dysku
                                    f.write(chunk)  # zapis na sieciowy może trochę trwać
                                    # t = f.tell()  # tylko przy ostatnim kroku będzie różnica
                                    t += chunk_size
                                    perc = min(int(t / s * 100), 100)
                                    new_time1 = time.time()
                                    delta_time1 = new_time1 - old_time1
                                    # fflog(f'\n\n{old_time1=} \n{new_time1=} \n{delta_time1=}')
                                    old_time1 = new_time1
                                    if speed_update_interval >= 1:  # co 1 sekundę
                                        speed = (t - prevt) / speed_update_interval  # dynamicznie
                                        speed = " ~" + source_utils.convert_size(speed, True) + "/s"
                                        # fflog(f'{speed_update_interval=}\n{prevt=} \n    {t=} \ndelta={t - prevt} \n{speed=}')
                                        prevt = t
                                        speed_update_interval = 0
                                        progressDialog.update(perc, message=speed)
                                    else:
                                        progressDialog.update(perc)
                                    speed_update_interval += delta_time1
                                else:
                                    break
                            if monitor.abortRequested():
                                fflog("sygnał zamknięcia Kodi się pojawił",1,1)
                                update(title, state="stopped")
                                f2.close()
                                if True or f.tell() < s:  # bo w sumie, to powinno być bez różnicy, bo i tak dalej nie będzie pobierania
                                    f.close()
                                    control.deleteFile(dest)
                                    control.renameF(dest2, dest)  # przywrócenie
                                else:
                                    fflog('skopiowano')
                                    f.close()  # plik będzie miał inną datę
                                    control.deleteFile(dest2)
                                # return sys.exit()  # import sys trzeba by jeszcze
                                return
                        fflog('skopiowano')
                        chunk = None  # nie wiem, czy potrzebne, bo za chwilę pod tą nazwę będzie przyporządkowany inny chunk
                        if progressDialog:
                            progressDialog.close()
                        control.deleteFile(dest2)
                    else:
                        msg = 'nie udało się utworzyć kopii pliku poprzedniego pobierania'
                        fflog(msg)
                        xbmcgui.Dialog().ok(f"Problem stworzenia kopii pliku pobierania", f"{dest2}\n\nWięcej informacji w logu")
                        return
            else:
                # f = xbmcvfs.File(dest, "w")  # utworzenie pustego pliku
                f = control.openFile(dest, "w")  # utworzenie pustego pliku
                # f = open(dest1, "wb")  # prawie (gdy nie ma takich jak "smb://") równoważna komenda (i robi Exception OSError, gdy niepowodzenie, a te Kodiowskie nie)
        except Exception:
            fflog_exc(1)
            update(title, state="stopped")  # a może "broken" dać?
            xbmcgui.Dialog().ok(f"Błąd {'otwarcia' if total else 'tworzenia'} pliku", f"{dest}\n\nWięcej informacji w logu")
            if progressDialog:
                progressDialog.close()
            return
        # kontrola
        ok = None
        control.sleep0(100)
        # fflog(f'{f=}',1,1)  # to nic nie daje
        ok = control.existsPath(dest)  # or control.existsPath(dest2) if total
        fflog(f'{ok}',0,1)
        if not ok:
            fflog(f'nie udało się utworzyć pliku {dest=}',1,1)
            xbmcgui.Dialog().ok("Błąd tworzenia pliku", f"{dest}\n\nMoże problem z prawami do zapisu?")
            return
        # fflog(f'{dir(f)=}')
        # s = f.size()  # kontrola rozmiaru (nie ma, gdy plik otwarty standardowym poleceniem pythona)
        s = t = f.tell()  # jest i przy xbmcvfs i przy standardowym open()
        # fflog(f'\n    {s=}  \n{total=} \n    {t=}',1,1)
        if s != total:
            fflog(f'plik {dest=} \n ma nieprawidłowy rozmiar {s=} | powinien mieć {total=}',1,1)
            xbmcgui.Dialog().ok("Błąd tworzenia pliku", f"{dest}\n\nMoże problem z prawami do zapisu?")
            return

        fflog("Start Downloadinf File  %s  (Size: %.2f MB)" % (dest, mb))

        # ustawienie znacznika, że pobieranie tego pliku już trwa
        xbmcgui.Window(10000).setProperty(id_downloading, file)
        control.sleep0(100)

        #total = 0  # ilość bajtów zapisanych do pliku ? definiuję zmienną jako parametr tej funkcji
        notify = 0
        increment = int(control.setting("download.percentage.info")) if control.setting("download.percentage.info") else 5
        errors = 0
        count = 0
        resume = 0
        sleep = 0
        manager = 0
        speed_update_interval = 0
        check_canceled = 0

        chunks = []  # taki bufor
        canceled = False
        percent = min( int(total / content  * 100), 100 )  if total  else 0
        #percent = 0
        downloaded = prevt = total
        state = "initializing"
        speed = 0

        prepareDatabase()
        """
        if not total:
            #files = insertIntoDb(title, "%.2f MB" % mb, "0%", "0 MB", total, resumable, state, "", url, json.dumps(headers), dest, id_downloading)
            files = insertIntoDb(title, content, "0%", total, resumable, state, "", url, json.dumps(headers), dest, id_downloading)
        else:
            files = 0
        """
        # files = insertIntoDb(title, content, "0%", total, resumable, state, "", url, json.dumps(headers), dest, id_downloading)
        files = insertIntoDb(title, content, f"{percent}%", total, resumable, state, "", url, json.dumps(headers), dest, id_downloading)

        if display_manager:
            # wyświetlenie Managera
            #threading.Thread(target=downloadManager, args=(window_manager,)).start()  # ale nie działają przyciski
            threading.Thread(target=downloadManager, kwargs={"files":files}).start()

        #fflog(f'{requests_test_only=}')
        # fflog(f'{("HEAD" in str(resp.request))=}')
        if requests_test_only:
            resp = getResponse(url, headers, 0)  # rozpoczęcie pobierania danych z serwera
            #fflog(f'{resp.request=}')

        # monitor = xbmc.Monitor()
        monitor = control.monitor
        state = "running"
        chunk_size=1024*10
        #chunk_size=1250*10  # (0,01 Mb)
        old_time1 = time.time()
        #counter = 0
        try:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                #fflog(f'pętla początek')
                #counter += 1
                new_time1 = time.time()
                delta_time1 = new_time1 - old_time1
                #fflog(f'\n\n{old_time1=} \n{new_time1=} \n{delta_time1=}')
                old_time1 = new_time1

                # przerwanie pobieranie
                #if percent > check_canceled:
                if total > check_canceled:
                    # fflog('sprawdzam, czy przerwać pobieranie')
                    # fflog(f'{xbmcgui.Window(10000).getProperty(id_downloading)=}')
                    if xbmcgui.Window(10000).getProperty(id_downloading) == 'break' or monitor.abortRequested():
                        resp.close()  # aby nie wczytywać danych, bo stream=True
                        #chunk = None  # nie wiem, czy trzeba
                        canceled = True
                        if monitor.abortRequested():
                            state = "stopped"
                        else:
                            state = "canceled"
                        fflog(f'download canceled by the user')
                        print( "download canceled by the user  %s" % dest)
                        try:
                            if True:  # nie wiem, jak lepiej
                                while len(chunks) > 0:  # aż do opróżnienia bufora
                                    c = chunks.pop(0)
                                    f.write(c)
                                    total += len(c)
                                    del c                        
                            f.close()
                        except Exception:
                            pass
                        # break  # a może dać później, aby zaktualizowało jeszcze ilość pobranych danych ?
                    #check_canceled += 1
                    check_canceled = total

                downloaded = total
                #fflog(f'1\n{downloaded=}\n     {total=} ')
                for c in chunks:
                    downloaded += len(c)  # nie za bardzo rozumiem tego (pobrane, ale nie zapisane jeszcze ? (mogą być w buforze)
                    pass
                #fflog(f'2\n{downloaded=}\n     {total=} ')

                #percent = min(100 * downloaded / content, 100)
                percent = min(100 * total / content, 100) if content else 0
                #fflog(f'{percent=}')

                if speed_update_interval >= 2:
                    #delta = total - prevt  # to rozmiar chunka, czyli chunk_size
                    speed = (total - prevt) * ( 8 / 1048576 ) / speed_update_interval
                    #fflog(f'{speed_update_interval=}\n{prevt=} \n{total=} \ndelta={total - prevt} \n{speed=}')
                    prevt = total
                    speed_update_interval = 0
                speed_update_interval += delta_time1

                #if percent >= manager or canceled:
                #if downloaded > manager or canceled:
                if manager >= 0.5 or canceled:
                    #fflog(f'raportuje do bazy {manager=}')
                    update(
                        title,  # nazwa pliku docelowego
                        str(int(percent)) + "%",  # procent pobrania
                        downloaded,  # pobranych i zapisanych bajtów
                        state=state,
                        speed="{:.2f}".format(speed),
                    )
                    #manager += 0.25
                    #manager = downloaded
                    manager = 0
                manager += delta_time1

                if canceled:  # nie jestem tego pewien
                    break
                    pass

                if percent >= notify and not canceled:
                    if not control.condVisibility('Window.IsActive(notification)'):
                    # if not xbmc.getCondVisibility('Window.IsActive(notification)'):  # bardzo się przydaje tu, jak pobieranie bardzo szybko idzie
                        xbmcgui.Dialog().notification(
                            title,  # heading
                            "\n - Postęp pobierania - " + str(round(percent)) + "%",  # message (2 linijka)
                            image,  # icon (default xbmcgui.NOTIFICATION_INFO)
                            1,  # jak długo ma pokazywać się informacja (w milisekundach) [danie 1 może pomóc w niewyświetlaniu przeterminowanych notyfikacji]
                            False  # sound
                        )
                    printer = (
                        "Download percent: %s   %s   %.2f MB   downloaded: %s MB  (Total File Size: %s MB)"
                        % (
                            # str(int(percent)) + "%",
                            str(round(percent)) + "%",
                            dest,
                            mb,
                            downloaded / 1048576,
                            content / (1024 * 1024),
                        )
                    )
                    # print(printer)
                    fflog(printer, 0)
                    notify += increment

                error = False

                try:
                    if not chunk:
                        fflog(f'2 {percent=}')
                        if percent < 99:  # a może lepiej sprawdzić stosunek pobranych danych do zadanych? Bo procenty mogą się nie zdążyć odświeżyć przy końcówce
                            error = True
                        else:
                            while len(chunks) > 0:  # aż do opróżnienia bufora
                                c = chunks.pop(0)
                                f.write(c)
                                total += len(c)
                                del c
                            f.close()
                            downloaded = total  # dla formalności
                            state = "finished"
                            fflog(f'w środku pętli pętli \n   {content=}\n     {total=}\n{downloaded=}\n{state=}')
                            update(
                                title,
                                "100%",
                                downloaded,
                                state=state,
                            )
                            fflog("download complete  %s" % dest)  # jeśli total == content
                            xbmcgui.Window(10000).clearProperty(id_downloading)
                            return done(title, dest, True)
                    else:
                        #fflog('jest chunk (1)')
                        pass

                except Exception as e:
                    fflog(str(e))
                    print(str(e))
                    error = True
                    sleep = 10
                    errno = 0

                    if hasattr(e, "errno"):
                        errno = e.errno
                    fflog(f'{errno=}')

                    if errno == 10035:  # 'A non-blocking socket operation could not be completed immediately'
                        pass
                    elif errno == 10054:  # 'An existing connection was forcibly closed by the remote host'
                        errors = 10  # force resume
                        sleep = 30
                    elif errno == 11001:  # 'getaddrinfo failed'
                        errors = 10  # force resume
                        sleep = 30

                if chunk:  # tu jest chyba cykliczne zapisywanie danych do pliku
                    #fflog('jest chunk (2)')
                    errors = 0
                    chunks.append(chunk)  # doładowanie do bufora (tylko nie wiem po co taki zabieg) - a może jak by było mniej niż 5 elementów (5*1024)?
                    if len(chunks) > 0:  # bufor nie zostanie cały rozładowany  (pierwotnie była wartość 5)
                        c = chunks.pop(0)  # pobranie tylko najwcześniejszej porcji
                        f.write(c)  # zapisanie do pliku tylko 1 chunka (reszta czeka w buforze)
                        total += len(c)
                        del c
                        # fflog(f'{f.tell()=}  {total=}',1,1)  # size() nie ma, gdy nie otwarty plik przez xbmcvfs
                        if True and f.tell() != total:
                        # if f.tell() != total and f.size() != total:  # nie wiem, czy aż tak potrzeba
                            fflog(f'{f.tell()=}  {total=}',1,1)
                            # total = f.tell()  # potrzebne, gdy używa się następnej linijki
                            total = ""  # bo to nie koresponduje z tym, ile faktycznie zostało zapisane do pliku
                            # raise Exception(f'{f.tell()=}  {total=}')
                            xbmcgui.Window(10000).clearProperty(id_downloading)
                            done(title, dest, False, text="\nPojawił się problem z zapisem do pliku")
                            # update(title, state="stopped")  # z może jednak lepiej broken ?
                            update(title, state="broken")  # na sieciowym zasobie uzyskiwałem dziwne wyniki
                            # update(title, f"{round(percent)}%", total, state="broken",)
                            return
                else:
                    fflog('brak chunka')

                if canceled:
                    break

                # fflog(f'{error=} {errors=} {resumable=} {resume=}')
                if error:
                    errors += 1
                    count += 1
                    fflog(f'Error(s) whilst downloading')
                    fflog("%d Error(s) whilst downloading %s" % (count, dest))
                    # xbmc.sleep(sleep * 1000)
                    control.sleep0(sleep * 1000)

                if (resumable and errors > 0) or errors >= 10:
                    if (not resumable and resume >= 50) or resume >= 500:
                        # Give up!
                        fflog(f'download canceled - too many error')
                        fflog("download canceled - too many error while downloading  %s" % dest)
                        resp.close()  # na wszelki wypadek
                        if monitor.abortRequested():
                            state = "stopped"
                        else:
                            state = "canceled"
                        update(title, "100%", total, state=state,)
                        xbmcgui.Window(10000).clearProperty(id_downloading)
                        return done(title, dest, False)

                    resume += 1
                    errors = 0
                    if resumable:
                        chunks = []
                        resp.close()  # czy to tu potrzebne ?
                        control.sleep(200)
                        # create new response
                        fflog(f'Download resumed, but new response will be create')
                        fflog("Download resumed (%d) %s" % (resume, dest))
                        resp = getResponse(url, headers, total)
                    else:
                        # use existing response
                        fflog(f'Download resumed')
                        pass

            # fflog('koniec pętli pobierania - ale nie znam wyniku')
            downloaded = total
            for c in chunks:
                downloaded += len(c)
            #fflog(f'{len(chunks)=}')
            while len(chunks) > 0:  # aż do opróżnienia bufora
                #fflog(f'opróżnianie bufora  {len(chunks)=}')
                c = chunks.pop(0)
                f.write(c)
                total += len(c)
                del c
            f.close()
            state = "finished" if state == "running" else state
            percent = 100 if state == "finished" else percent
            update(title, f"{round(percent)}%", total, state=state,)
            xbmcgui.Window(10000).clearProperty(id_downloading)
            # fflog(f'koniec pętli \n   {content=}\n     {total=}\n{downloaded=}\n{state=}')
            if canceled:
                fflog("download canceled  %s" % dest)
                done(title, dest, False)
            else:
                fflog("download finished  (with error=%s)  %s" % (error, dest,))
                done(title, dest, not error)
            control.sleep(200)

            if canceled and state != "stopped":
                if (
                    xbmcgui.Dialog().yesno(
                        "Czy chcesz skasować ",
                        " nie do końca pobrany plik ?",
                        yeslabel="Skasuj",
                        nolabel="Zostaw",
                    )
                ):
                    fflog(f'plik zostanie skasowany')
                    try:
                        successed = control.deleteFile(dest)
                        update(title, state="broken",)
                        if not successed:
                            fflog(f'nie udało się skasować pliku')
                    except Exception:
                        fflog(f'wystąpił błąd podczas kasowania pliku')
                        pass
                    control.sleep(100)

        except Exception as e:
            xbmcgui.Window(10000).clearProperty(id_downloading)
            #update(title, state="broken",)
            #update(title, percentage=f"{round(percent)}%", downloaded="%.2f" % (total / 1048576) + " MB", filesize="%.2f MB" % mb, bytesdownloaded=total, state="broken",)
            update(title, f"{round(percent)}%", total, state="broken",)
            #update(title, f"{round(percent)}%", "%.2f" % (downloaded / 1048576) + " MB", "%.2f MB" % mb, downloaded, state="canceled",)  # downloaded nie musi być równe total (dla awarii, bo nie wiemy gdzie ona nastąpiła)
            fflog(f'AWARIA \n   {content=}\n     {total=}\n{downloaded=}\n{state=}')
            fflog_exc(1)
            f.close()
            xbmcgui.Dialog().ok("AWARIA", f"{e}\n\n{title}")
            pass

    except Exception:
        control.idle(2)
        fflog_exc(1)


def downloadManager(window=None, files=0):
    if xbmcgui.Window(10000).getProperty("FanVodPL-downloadManager-active"):
        fflog("istnieje okienko downloadManager'a")
        #return
    if not files:
        #files = 5
        files = count_records()
        files = files if files else 5
    xbmcgui.Window(10000).setProperty("FanVodPL-downloadManager-active", "true")
    fflog('przytowanie okienka menadzera pobierania')
    if not window:
        #window = MyAddon("Download Manager")  # nazwę można chyba zmienić
        window = MyAddon('"Menadżer" pobierania', files=files)  # nazwę można chyba zmienić
    else:
        fflog('menadzer został wcześniej przygotowany')
    fflog('wyświetlenie Menadżera')
    window.doModal()  # otwarcie okienka
    # po zamknięciu okienka:
    fflog('Menadżer został zamknięty')
    xbmcgui.Window(10000).clearProperty("FanVodPL-downloadManager-active")
    try:
        window.cancelThread = True
        del window
    except Exception:
        # fflog_exc()
        pass


def prepareDatabase():
    control.makeFile(control.dataPath)
    dbcon = database.connect(
        control.downloadsFile,
        detect_types=database.PARSE_DECLTYPES,
        cached_statements=20000,
    )
    dbcur = dbcon.cursor()
    dbcur.execute(
        "CREATE TABLE IF NOT EXISTS download_manager ("
            "filename TEXT, "
            "filesize TEXT, "
            "percentage TEXT, "
            "downloaded TEXT, "
            "resumable INTEGER, "
            "state TEXT, "
            "speed TEXT, "
            "url TEXT, "
            "headers TEXT, "
            "dest TEXT, "
            "id_downloading TEXT "
            ");"
    )


def insertIntoDb(fileName, filesize, percentage, downloaded, resumable="", state="running", speed="", url="", headers="", dest="", id_downloading=""):
    # fflog(f'insert into database {fileName=} {percentage=} {state=}')
    dbcon = database.connect(control.downloadsFile)
    dbcur = dbcon.cursor()
    if isinstance(resumable, bool):
        resumable = int(resumable)
    #record = dbcur.execute("SELECT filename FROM download_manager WHERE filename=? AND filesize=?", (fileName, filesize) ).fetchone()
    record = dbcur.execute("SELECT filename FROM download_manager WHERE filename=?", (fileName, ) ).fetchone()
    if record:
        dbcur.execute(
            #"UPDATE download_manager SET percentage=?, downloaded=?, bytesdownloaded=?, resumable=?, state=?, url=?, headers=?, dest=? WHERE filename=? AND filesize=?",
            "UPDATE download_manager SET filesize=?, percentage=?, downloaded=?, resumable=?, state=?, speed=?, url=?, headers=?, dest=?, id_downloading=? WHERE filename=?",
            #(percentage, downloaded, bytesdownloaded, resumable, state, url, headers, dest, fileName, filesize),
            (filesize, percentage, downloaded, resumable, state, speed, url, headers, dest, id_downloading, fileName),
        )
    else:
        dbcur.execute(
            "INSERT INTO download_manager Values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (fileName, filesize, percentage, downloaded, resumable, state, speed, url, headers, dest, id_downloading),
        )
    dbcon.commit()
    control.sleep(100)
    rows = dbcur.execute("select count(*) from download_manager").fetchone()
    rows = rows[0] if rows else 0
    fflog(f'rekordów w bazie {rows=}')
    return rows


def update(fileName, percentage="", downloaded="", state="running", speed=""):
    # fflog(f'update database {fileName=} {filesize=} {percentage=} {state=}')
    dbcon = database.connect(control.downloadsFile)
    dbcur = dbcon.cursor()
    dbcur.execute(
        #"UPDATE download_manager SET percentage=?, downloaded=?, bytesdownloaded=?, state=? WHERE filename=? AND filesize=?",
        "UPDATE download_manager SET percentage=?, downloaded=?, state=?, speed=? WHERE filename=?",
        #(percentage, downloaded, bytesdownloaded, state, fileName, filesize),
        (percentage, downloaded, state, speed, fileName),
    )
    dbcon.commit()


def remove(fileName, filesize):
    fflog(f'usunięcie z bazy rekordu {fileName=} {filesize=}')
    dbcon = database.connect(control.downloadsFile)
    dbcur = dbcon.cursor()
    dbcur.execute(
        #"DELETE FROM download_manager WHERE filename=? AND filesize=?",
        "DELETE FROM download_manager WHERE filename=?",
        #(fileName, filesize),
        (fileName, ),
    )
    dbcon.commit()
    dbcur.execute("VACUUM")


def count_records():
    dbcon = database.connect(control.downloadsFile)
    dbcur = dbcon.cursor()
    rows = dbcur.execute("select count(*) from download_manager").fetchone()
    rows = rows[0] if rows else 0
    fflog(f'rekordów w bazie {rows=}')
    return rows


class MyAddon(pyxbmct.AddonDialogWindow):
    def __init__(self, title="", files=5, start_list_update=True):
        super(MyAddon, self).__init__(title)  # Call the base class' constructor
        """
        self.close_button = None
        self.button_show_list = None
        self.items_fileName = None
        self.items_percent = None
        self.items_downloaded = None
        self.items_fileSize = None
        self.items_action = None
        """
        fflog(f'przygotowuje okno dla {files=} plik(u/ów)')
        self.max_rows_files = files
        #self.max_rows_files = max(2, files)  # minimum 2 linijki
        self.window_rows = max(4, self.max_rows_files + 3)
        self.setGeometry(1024, 60 * (self.window_rows), self.window_rows, 9)  # Set width, height and the grid parameters
        self.set_active_controls()  # Call set controls method
        self.set_navigation()  # Call set navigation method
        # self.connect(pyxbmct.ACTION_NAV_BACK, self.close)  # Connect a key action (Backspace) to close the window
        self.connect(pyxbmct.ACTION_NAV_BACK, self.confirm_close)  # Connect a key action (Backspace) to function that close the window
        # dla klawisza ESC nie da się tego zrobić https://romanvm.github.io/script.module.pyxbmct/connection.html na samym dole wyjaśnienie
        #self.connect(pyxbmct.ACTION_MOVE_DOWN, self.navi_update)
        #self.connect(pyxbmct.ACTION_MOVE_UP, self.navi_update)
        self.abort = False
        self.cancelThread = False
        self.worker_active = False
        if start_list_update:
            self.list_update()
        # self.setFocus(self.button_show_list)  # Set initial focus
        self.setFocus(self.close_button)  # Set initial focus 

    def set_active_controls(self):
        # elementy (tabelka) (nagłówki)
        int_label = pyxbmct.Label("[B]Nazwa Pliku[/B]", alignment=pyxbmct.ALIGN_CENTER)
        self.placeControl(int_label, 0, 0, 1, 3)
        int_label = pyxbmct.Label("[B]Procent[/B]", alignment=pyxbmct.ALIGN_CENTER)
        self.placeControl(int_label, 0, 3, 1, 1)
        int_label = pyxbmct.Label("[B]Pobrano[/B]", alignment=pyxbmct.ALIGN_CENTER)
        self.placeControl(int_label, 0, 4, 1, 1)
        int_label = pyxbmct.Label("[B]Rozmiar[/B]", alignment=pyxbmct.ALIGN_CENTER)
        self.placeControl(int_label, 0, 5, 1, 1)
        int_label = pyxbmct.Label("[B]Mb/s[/B]", alignment=pyxbmct.ALIGN_CENTER)
        self.placeControl(int_label, 0, 6, 1, 1)
        int_label = pyxbmct.Label("[B]Czas[/B]", alignment=pyxbmct.ALIGN_CENTER)
        self.placeControl(int_label, 0, 7, 1, 1)
        int_label = pyxbmct.Label("[B]Akcja[/B]", alignment=pyxbmct.ALIGN_CENTER)
        self.placeControl(int_label, 0, 8, 1, 1)
        int_label = None

        # Przycisk pobierania listy
        self.button_show_list = pyxbmct.Button("Pobierz listę")
        self.placeControl(self.button_show_list, self.window_rows - 1, 1, 1, 2)
        self.connect(self.button_show_list, self.list_update)
        # Close button
        self.close_button = pyxbmct.Button('Zamknij okno')
        self.placeControl(self.close_button, self.window_rows - 1, 4, 1, 2)
        # self.connect(self.close_button, self.close)  # Connect close button
        self.connect(self.close_button, self.confirm_close)  # Connect close button

        # tworzenie elementów przez klonowanie ich (będą to pola (dane/wartości) tabeli)
        self.items_fileName = [pyxbmct.FadeLabel(_alignment=pyxbmct.ALIGN_CENTER) for x in range(0, self.max_rows_files)]  # 4 pliki na liście (4 linijki)
        self.items_fileName2 = [pyxbmct.Label(f"a {x}") for x in range(0, self.max_rows_files)]  # 4 pliki na liście (4 linijki)
        self.items_fileSize = [pyxbmct.Label(f"", alignment=pyxbmct.ALIGN_CENTER) for x in range(0, self.max_rows_files)]
        self.items_percent = [pyxbmct.Label(f"", alignment=pyxbmct.ALIGN_CENTER) for x in range(0, self.max_rows_files)]  # j.w.
        self.items_downloaded = [pyxbmct.Label(f"", alignment=pyxbmct.ALIGN_CENTER) for x in range(0, self.max_rows_files)]
        self.items_speed = [pyxbmct.Label(f"", alignment=pyxbmct.ALIGN_CENTER) for x in range(0, self.max_rows_files)]
        self.items_time = [pyxbmct.Label(f"", alignment=pyxbmct.ALIGN_CENTER) for x in range(0, self.max_rows_files)]
        self.items_action = [pyxbmct.Button("-", alignment=pyxbmct.ALIGN_CENTER) for x in range(0, self.max_rows_files)]
        self.items_state = [pyxbmct.Label("", ) for x in range(0, self.max_rows_files)]
        self.items_resumable = [pyxbmct.Label("", ) for x in range(0, self.max_rows_files)]
        self.items_data = [pyxbmct.Label(f"", alignment=pyxbmct.ALIGN_CENTER) for x in range(0, self.max_rows_files)]  # jest jeszcze parametr hasPath=False, ale nie wiem czy jest on tu potrzebny
        self.items_bytesdownloaded = [pyxbmct.Label("") for x in range(0, self.max_rows_files)]

        self.all_items = (
                self.items_fileName,  # zawiera po 4 elementy
                self.items_percent,  # jw.
                self.items_downloaded,
                self.items_fileSize,
                self.items_speed,
                self.items_time,
                self.items_action,

                self.items_fileName2,
                self.items_state,
                self.items_resumable,
                self.items_data,  # url, headers, dest
                self.items_bytesdownloaded,
            )

        for c, items in enumerate(self.all_items):
            for i, item in enumerate(items):
                self.placeControl(items[i], i + 1, (2 if c else 0) + (c * 1), 1, (1 if c else 3))
                if c == 6:  # akcja
                    self.connect(item, eval(f"lambda: self.do_action({i})", {"self":self}) )  # chyba mniej eleganckie rowzwiązanie
                    #self.connect(item, self.do_action1(i) )  # elegantsze rozwiązania
                    #item.setEnableCondition(f'Control.IsEnabled({self.button_show_list.getId()})')
                    #item.setEnableCondition(f'String.IsEqual(Control.GetLabel(3011),)')
                    item.setVisibleCondition(f'[!String.IsEqual(Control.GetLabel({self.items_fileSize[i].getId()}),)  ]', False)
                if c >= 7:  # pomocnicze
                    item.setVisible(False)
                    pass

        self.connectEventList(
            [xbmcgui.ACTION_CONTEXT_MENU],
            self.change_action,
        )

    def set_navigation(self):
        """Set up keyboard/remote navigation between controls."""
        self.button_show_list.controlRight(self.close_button)
        #self.button_show_list.setNavigation(self.button_show_list, self.button_show_list, self.button_show_list, self.close_button)

        self.close_button.controlLeft(self.button_show_list)
        self.close_button.controlUp(self.items_action[self.max_rows_files - 1])
        #self.close_button.setNavigation(self.close_button, self.close_button, self.button_show_list, self.close_button)

        if self.max_rows_files > 1:
            for i, item in enumerate(self.items_action):
                if i == 0:
                    # item.controlUp(self.close_button)
                    item.controlDown(self.items_action[i+1])
                elif i == self.max_rows_files - 1:
                    item.controlUp(self.items_action[i-1])
                    item.controlDown(self.close_button)
                    pass
                else:
                    item.controlDown(self.items_action[i+1])
                    item.controlUp(self.items_action[i-1])
                    pass
        else:
            self.items_action[0].controlDown(self.close_button)

    def change_action(self):
        try:
            focused_button = self.getFocus()
        except:
            #fflog('nic nie miało focusa (żadna kontrolka)')
            return
        for i, item in enumerate(self.items_action):
            if focused_button == item:
                #fflog(f'{i=}')
                pass
                break
        cur_action = new_action = focused_button.getLabel()
        #fflog(f'{cur_action=}')
        if cur_action == "pobierz":
            new_action = "ukryj"
        elif cur_action == "wznów":
            new_action = "ukryj"
        elif cur_action == "ukryj":
            new_action = "-"
        if new_action != cur_action:
            focused_button.setLabel(new_action)

    def set_button_label(self, r):
        #fflog(f'z linii nr {r=}')
        color = ""
        italic = ""
        state = self.items_state[r].getLabel()
        #fflog(f'{state=}')
        cur_action = new_action = self.items_action[r].getLabel()
        if state == "running":
            new_action = "stop"
            color = "none"
            italic = "I"
        elif state in ["canceled", "stopped"] and cur_action != "ukryj":
            resumable = self.items_resumable[r].getLabel() == "1"
            if resumable:
                new_action = "wznów"
                color = "orange"
            else:
                #new_action = "ukryj"
                new_action = "pobierz"
                color = "red"
        elif state == "broken" and cur_action != "ukryj":
            new_action = "pobierz"
            color = "deeppink"
        elif state == "finished":
            new_action = "ukryj"
            color = "limegreen"
            # self.items_percent[r].setLabel("100%")
        elif cur_action != "ukryj":
            new_action = "-"
            color = "darkgray"
        #fflog(f'{new_action=}  {self.items_action[r].getLabel()=} {r=}')
        if new_action != cur_action:
            #fflog(f'wymieniam labela')
            self.items_action[r].setLabel(new_action)
            if color:
                label = self.items_fileName2[r].getLabel()
                self.items_fileName[r].reset()
                label = f'[COLOR {color}]{label}[/COLOR]'
                if italic:
                    label = f'[{italic}]{label}[/{italic}]'
                self.items_fileName[r].reset()
                self.items_fileName[r].addLabel(label)
            control.sleep(100)

    def do_action(self, r):
        #fflog(f'dla linii nr {r=}')
        self.items_action[r].setEnabled(False)
        fileName = self.items_fileName2[r].getLabel()
        fileSize = self.items_fileSize[r].getLabel()
        action = self.items_action[r].getLabel()
        #fflog(f'{action=}')
        if action == "stop":
            data = self.items_data[r].getLabel()
            data = json.loads(data)
            id_downloading = data["id_downloading"]
            """
            if not id_downloading:
                id_downloading = fileName
                id_downloading = "FanVodPL-downloading-" + hashlib.md5(id_downloading.encode()).hexdigest()
            """
            xbmcgui.Window(10000).setProperty(id_downloading, 'break')
            control.sleep(500)
        elif action == "wznów" or action == "pobierz":
            data = self.items_data[r].getLabel()
            #fflog(f'{data=}')
            data = json.loads(data)
            #data = dict(parse_qsl(data))
            #fflog(f'{data=}')
            url = data["url"]
            headers = data["headers"]
            #headers = json.dumps(headers)
            title = fileName
            total = self.items_bytesdownloaded[r].getLabel()
            total = int(total) if total else 0
            if action != "wznów":
                total = 0
                id_downloading = data["id_downloading"]
                """
                if not id_downloading:
                    id_downloading = fileName
                    id_downloading = "FanVodPL-downloading-" + hashlib.md5(id_downloading.encode()).hexdigest()
                """
                xbmcgui.Window(10000).clearProperty(id_downloading)
            dest = data["dest"]
            image = ""
            #self.items_action[r].setEnabled(True)
            threading.Thread(target=doDownload, args=(url, dest, title, image, headers), kwargs={"total":total, "display_manager":False}).start()  # asynchronicznie, aby nie blokowało zakończenia tej funkcji, bo inaczej nowa akcja nie działa
        elif action == "ukryj":
            remove(fileName, fileSize)
            #self.pause_worker = True
            #control.sleep(550)
            for c, items in enumerate(self.all_items):
                for i, item in enumerate(items):
                    if i < r:
                        continue
                    #fflog(f'{type(item)=}')
                    if "FadeLabel" in str(type(item)):
                        item.reset()
                        item.addLabel("")
                    elif "Button" in str(type(item)):
                        item.setLabel(" ")
                    else:
                        item.setLabel("")
            #control.sleep(100)
            #self.one_update = False
            #self.pause_worker = False
            pass
        control.sleep(100)
        self.items_action[r].setEnabled(True)

    def do_action1(self, r=""):
        fflog(f'funkcja action1 {r=}')
        def do_action2():  # inner callable
            fflog(f'ver2: z linii nr {r=} (numeracja od 0)')
            filename = self.items_fileName2[r].getLabel()
            fflog(f'{filename=}')
            pass
        return do_action2  # zwrócenie samej funkcji, aby potem mogła być wykonana

    def worker(self):
        if self.worker_active:
            fflog(f"jest już uruchomiana inna instancja worker'a")
            return
        fflog(f"worker")
        dbcon = database.connect(control.downloadsFile)
        dbcur = dbcon.cursor()
        #self.one_update = False
        self.pause_worker = False
        kodi_exit = False
        # monitor = xbmc.Monitor()
        monitor = control.monitor
        # można zrobić jeszcze sprawdzenie, czy tabela download_manager istnieje w bazie
        table = dbcur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='download_manager'").fetchone()
        #fflog(f'{table=}')
        if not table :
            fflog(f'brak tabeli o nazwie "download_manager" - brak pobierań')
            control.infoDialog('brak pobierań w bazie', time=1, icon="WARNING")
            fflog(f"worker nie będzie kontynuował pracy")
            return
        counter_speed = True
        while not self.cancelThread and not (kodi_exit := monitor.abortRequested()):
            try:
                fflog(f'worker działa',0)
                self.worker_active = True
                counter_speed = not counter_speed
                if not self.pause_worker:
                    dbcur.execute("SELECT * FROM download_manager")
                    match = dbcur.fetchall()
                    #fflog(f'{match=}', 1)
                    for row, item in enumerate(match[:self.max_rows_files]):
                        #fflog(f'{row=} {item=}')  # row (r) to nr pobieranego pliku
                        #fflog(f'{row=}')

                        """
                        #speed = self.items_percent[row].getLabel()
                        state = self.items_state[row].getLabel()
                        if state == "running":
                            if counter_speed:
                                try:
                                    #speed = ( float(item[3].replace(" MB","")) - float(self.items_downloaded[row].getLabel().replace(" MB", "")) ) * 8 / 0.5
                                    speed = ((item[4] - int(self.items_downloaded[row].getLabel())) / (1024 * 1024)) * 8
                                    speed = str(round(speed, 2))
                                    # fflog(f'{speed=}  {item[3]=}\n           {self.items_downloaded[row].getLabel()=}')
                                except Exception:
                                    speed = "-"
                                    # fflog_exc(1)
                                    pass
                                self.items_speed[row].setLabel(speed)
                        else:
                            if self.items_speed[row].getLabel():
                                self.items_speed[row].setLabel("")
                        """

                        if type(item[2]) == str:
                            if type(item[1])==str and "-" not in item[1] and "0 B" not in item[1] or item[2]=="100%":
                                self.items_percent[row].setLabel(item[2])

                        if type(item[3]) == str and item[3]:
                            self.items_downloaded[row].setLabel(source_utils.convert_size(item[3], True))
                            self.items_bytesdownloaded[row].setLabel(item[3])

                        if type(item[5]) == str:
                            self.items_state[row].setLabel(item[5])

                        if type(item[6]) == str:
                            if type(item[1])==str and "-" not in item[1] and "0 B" not in item[1]:
                                self.items_speed[row].setLabel(item[6])
                                if counter_speed:
                                    if item[6] and float(item[6]):
                                        #time = (float(item[1].replace(" MB","")) - float(item[3].replace(" MB",""))) * 8 / float(item[7])
                                        time = ((int(item[1]) - int(item[3])) / (1024 * 1024)) * 8 / float(item[6])
                                        time = 1 if 0.7 < time < 1 else int(time)
                                        #time = int(time)
                                        m, s = divmod(time, 60)
                                        h, m = divmod(m, 60)
                                        h = f"{h}:" if h else ""
                                        time = f'{h}{m:02d}:{s:02d}'
                                        time = time[1:] if time[0] == "0" else time
                                    else:
                                        time = ""
                                    self.items_time[row].setLabel(time)

                        #if not self.one_update or item[0] != self.items_fileName2[row].getLabel():
                        if item[0] != self.items_fileName2[row].getLabel():
                            fflog(f'{row} {item[0]=} {self.items_fileName2[row].getLabel()=}',0)
                            if type(item[0]) == str:
                                #fflog(f'dodaje/zmieniam tekst do fadelabel {row=}')
                                self.items_fileName[row].reset()
                                self.items_fileName[row].addLabel(item[0])
                                self.items_fileName2[row].setLabel(item[0])

                            if type(item[1]) == str and "-" not in item[1] and "0 B" not in item[1]:
                                self.items_fileSize[row].setLabel(source_utils.convert_size(int(item[1]), True))
                            else:
                                self.items_fileSize[row].setLabel("-")
                                pass

                            if type(item[4]) == int:
                                self.items_resumable[row].setLabel(str(item[4]))

                            if type(item[7]) == str:
                                data = {}
                                data["url"] = item[7]
                                data["headers"] = item[8]
                                data["dest"] = item[9]
                                data["id_downloading"] = item[10]
                                self.items_data[row].setLabel( json.dumps(data) )

                        #if self.items_action[row].getLabel() == "-":
                        self.set_button_label(row)

                    #if not self.one_update:
                        #self.one_update = True
                else:
                     fflog('pauza workera',0)
                     pass

                control.sleep(500)
            except Exception:
                fflog_exc(1)
                self.cancelThread = True
                pass
        fflog(f"koniec worker'a  |  {self.cancelThread=}  {kodi_exit=}",0)
        if kodi_exit:
            self.cancelThread = True
            self.close()
            pass

    def list_update(self):
        fflog(f'start funkcji(metody) do pobrania listy pobierań | {self.abort=}')
        #but_id = self.button_show_list.getId()
        #fflog(f'{but_id=}')
        self.button_show_list.setEnabled(False)
        self.button_show_list.setVisible(False)
        #self.button_show_list.setLabel("[COLOR red]dupa1[/COLOR]")
        #self.button_show_list.setLabel2("pojazd")
        # self.button.setVisibleCondition('[Control.IsVisible(41) + !Control.IsVisible(12)]', False)
        # self.button.setEnableCondition('System.InternetState')
        #self.close_button.setEnableCondition('Control.IsEnabled(3011)')
        #self.close_button.setEnableCondition(f'Control.IsEnabled({but_id})')
        if not self.abort:
            fflog("uruchomienie worker'a")
            thread = threading.Thread(target=self.worker)
            thread.start()
            self.abort = False

    def setAnimation(self, control):
        # Set fade animation for all add-on window controls
        control.setAnimations(
            [
                (
                    "WindowOpen",
                    "effect=fade start=0 end=100 time=200",
                ),
                (
                    "WindowClose",
                    "effect=fade start=100 end=0 time=100",
                ),
            ]
        )

    def confirm_close(self):
        if check_active_downloads():
            if not xbmcgui.Dialog().yesno(
                    "Czy chcesz zamknąć menadzera ?",
                    "Pobieranie będzie kontynuowane w tle",
                    # yeslabel="Zamknij",
                    # nolabel="Anuluj",
            ):
                return
        self.close()


def clear_db0():  # cała baza
    if False:  # w celach deweloperskich
        fflog('czyszczenie bazy pobieranych plików wyłączone')
        return
    try:
        dbcon = database.connect(control.downloadsFile)
        dbcur = dbcon.cursor()
        dbcur.execute("DROP TABLE IF EXISTS download_manager")
        dbcon.commit()
        dbcur.execute("VACUUM")
        dbcon.close()
        fflog('wyczyszczono historię pobierania')
    except Exception:
        fflog_exc(0)
        pass


def clear_db():
    if False:  # w celach deweloperskich
        fflog('czyszczenie pobieranych plików wyłączone')
        return
    try:
        dbcon = database.connect(control.downloadsFile)
        dbcur = dbcon.cursor()
        dbcur.execute("UPDATE download_manager SET state='stopped' WHERE state='running'")
        dbcur.execute("DELETE FROM download_manager WHERE state!='stopped' and state!='running'")
        dbcon.commit()
        dbcur.execute("VACUUM")
        dbcon.close()
        fflog('usunięto zakończone pobierania z historii')
    except Exception:
        fflog_exc(0)
        pass


def check_active_downloads():
    try:
        dbcon = database.connect(control.downloadsFile)
        dbcur = dbcon.cursor()
        dbcur.execute("SELECT filename FROM download_manager WHERE state='running'")
        rows = dbcur.fetchall()
        # fflog(f'{rows=}',1,1)
        dbcon.close()
        fflog(f'trwających pobierań: {len(rows)=}',1,1)
        return len(rows)
    except Exception:
        fflog_exc(0)
        pass