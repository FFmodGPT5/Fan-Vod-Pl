# -*- coding: utf-8 -*-

"""
    FanVodPL Add-on
    Copyright (C) 2015 lambda

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

try:
    from sqlite3 import dbapi2 as database
except:
    from pysqlite2 import dbapi2 as database

from ptw.libraries import control
from ptw.libraries import log_utils
from ptw.libraries.log_utils import log, fflog
from ptw.debug import log_exception, fflog_exc
from ptw.libraries import trakt

# niektóre nie mają imdb
# imdb = imdb or tmdb

def get(media_type, imdb, season=None, episode=None, local=False, tmdb=None):  # tmdb nie dorobione jeszcze
    # fflog(f'{media_type=} {imdb=} {local=} {season=} {episode=} {tmdb=}',1,1)
    offset = 0
    runtime = 0
    # imdb = imdb or tmdb
    source = None
    if (
        local == False
        #and control.setting('resume.source') == '1'  # nie ma takiego settingsu
        and trakt.getTraktIndicatorsInfo()
        and trakt.getTraktCredentialsInfo() == True
        ):
        try:
            fflog(f'from trakt', 0)
            source = 'trakt'
            #control.sleep(500)
            if media_type == 'episode':
                # Looking for a Episode progress
                traktInfo = trakt.getTraktAsJson('https://api.trakt.tv/sync/playback/episodes?extended=full')
                fflog(f'{traktInfo=}') if not traktInfo else ""
                for i in traktInfo:
                    if imdb == i['show']['ids']['imdb']:  # or tmdb == i['show']['ids']['tmdb']
                        # Checking Episode Number
                        if int(season) == i['episode']['season'] and int(episode) == i['episode']['number']:
                            runtime = int(i['episode']['runtime']) * 60
                            fflog(f"{i['progress']=}",0)
                            seekable = 1 < i['progress'] < 92
                            fflog(f'{seekable=}',0)
                            if seekable:
                                # Calculating Offset to seconds
                                offset = float(i['progress'] / 100) * int(i['episode']['runtime']) * 60
                            else:
                                offset = 0
            else:
                # Looking for a Movie Progress
                traktInfo = trakt.getTraktAsJson('https://api.trakt.tv/sync/playback/movies?extended=full')  # full aby mieć runtime, tylko czemu szuka wszystkich filmów, a nie tylko jednego ?
                fflog(f'{traktInfo=}') if not traktInfo else ""
                for i in traktInfo:
                    if imdb == i['movie']['ids']['imdb']:  # or tmdb == i['movie']['ids']['tmdb']
                        runtime = int(i['movie']['runtime']) * 60
                        fflog(f"{i['progress']=}",0)
                        seekable = 1 < i['progress'] < 92
                        fflog(f'{seekable=}',0)
                        if seekable:
                            # Calculating Offset to seconds
                            offset = float(i['progress'] / 100) * int(i['movie']['runtime']) * 60
                        else:
                            offset = 0
            fflog(f'{offset=}  {runtime=}', 0)
            if offset > 0:  # chociaż ten warunek też jest dalej sprawdzany
                return offset, runtime, source  # więc może tego tu nie być
                pass
        except Exception:
            fflog_exc(1)
            offset = 0

    # else:
    if True:
        if offset == 0:  # ten warunek jest ważny
            fflog(f'from local machine', 0)
            source = 'local'
            # runtime = 0  # pomyśleć nad tym
            # imdb = imdb or tmdb
            try:
                sql_select = "SELECT * FROM bookmarks WHERE imdb = '%s'" % imdb
                if media_type == "episode":
                    sql_select += " AND season = '%s' AND episode = '%s'" % (season, episode)
                control.makeFile(control.dataPath)
                dbcon = database.connect(control.bookmarksFile)
                dbcur = dbcon.cursor()
                dbcur.execute(sql_select)
                match = dbcur.fetchone()
                if match:
                    offset = match[0]
                    offset = float(offset)
                else:
                    offset = 0
                fflog(f'{offset=}', 0)
                dbcon.commit()
            except Exception as e:
                log_utils.log("bookmarks_get %s" % e, "module")
                fflog_exc(0)
                offset = 0

    #return offset
    # return offset, runtime
    return offset, runtime, source


def reset(current_time, total_time, media_type, imdb, season="", episode=""):
    #fflog(f'[reset] {current_time=} {total_time=} {imdb=} {season=} {episode=}')
    try:
        _playcount = 0
        overlay = 6
        timeInSeconds = str(current_time)
        ok = int(current_time) > 120 and (current_time / total_time) < 0.92
        watched = (current_time / total_time) >= 0.92

        sql_select = "SELECT * FROM bookmarks WHERE imdb = '%s'" % imdb
        if media_type == "episode":
            sql_select += " AND season = '%s' AND episode = '%s'" % (season, episode)

        sql_update = "UPDATE bookmarks SET timeInSeconds = '%s' WHERE imdb = '%s'" % (timeInSeconds, imdb,)
        if media_type == "episode":
            sql_update += " AND season = '%s' AND episode = '%s'" % (season, episode)

        if media_type == "movie":
            sql_update_watched = (
                # "UPDATE bookmarks SET timeInSeconds = '0', playcount = %s, overlay = %s WHERE imdb = '%s'" % ("%s", "%s", imdb)
                "UPDATE bookmarks SET timeInSeconds = '%s', playcount = %s, overlay = %s WHERE imdb = '%s'" % (timeInSeconds, "%s", "%s", imdb)
            )
        elif media_type == "episode":
            sql_update_watched = (
                # "UPDATE bookmarks SET timeInSeconds = '0', playcount = %s, overlay = %s WHERE imdb = '%s' AND season = '%s' AND episode = '%s'" % ("%s", "%s", imdb, season, episode)
                "UPDATE bookmarks SET timeInSeconds = '%s', playcount = %s, overlay = %s WHERE imdb = '%s' AND season = '%s' AND episode = '%s'" % (timeInSeconds, "%s", "%s", imdb, season, episode)
            )

        if media_type == "movie":
            sql_insert = (
                "INSERT INTO bookmarks Values ('%s', '%s', '%s', '', '', '%s', '%s')"
                % (timeInSeconds, media_type, imdb, _playcount, overlay)
            )
        elif media_type == "episode":
            sql_insert = (
                "INSERT INTO bookmarks Values ('%s', '%s', '%s', '%s', '%s', '%s', '%s')"
                % (
                    timeInSeconds,
                    media_type,
                    imdb,
                    season,
                    episode,
                    _playcount,
                    overlay,
                )
            )

        if media_type == "movie":
            sql_insert_watched = (
                "INSERT INTO bookmarks Values ('%s', '%s', '%s', '', '', '%s', '%s')"
                % (timeInSeconds, media_type, imdb, "%s", "%s")
            )
        elif media_type == "episode":
            sql_insert_watched = (
                "INSERT INTO bookmarks Values ('%s', '%s', '%s', '%s', '%s', '%s', '%s')"
                % (timeInSeconds, media_type, imdb, season, episode, "%s", "%s")
            )

        control.makeFile(control.dataPath)
        dbcon = database.connect(control.bookmarksFile)
        dbcur = dbcon.cursor()
        """ przeniosełem do def _indicators
        dbcur.execute(
            "CREATE TABLE IF NOT EXISTS bookmarks ("
            "timeInSeconds TEXT, "
            "type TEXT, "
            "imdb TEXT, "  # czasami może być numer tmdb, ale dla kompatybilności w kolumnie o nazwie imdb
            "season TEXT, "
            "episode TEXT, "
            "playcount INTEGER, "
            "overlay INTEGER, "
            "UNIQUE(imdb, season, episode)"
            ");"
        )
        """
        dbcur.execute(sql_select)
        match = dbcur.fetchone()
        # fflog(f'{match=} {imdb=}',1,1)
        fflog(f'{match=}  {ok=}  {current_time=}  {total_time=}  {imdb=}',1,1)
        if match:
            if ok:
                dbcur.execute(sql_update)
            elif watched:
                _playcount = match[5] + 1
                overlay = 7
                dbcur.execute(sql_update_watched % (_playcount, overlay))
        else:
            if ok:
                # fflog(f'{sql_insert=}',1,1)
                dbcur.execute(sql_insert)
            elif watched:
                _playcount = 1
                overlay = 7
                dbcur.execute(sql_insert_watched % (_playcount, overlay))
        dbcon.commit()
    except Exception:
        log_utils.log("bookmarks_reset", "module")
        fflog_exc(0)
        pass


def set_scrobble(current_time, total_time, _content, _imdb="", _tvdb="", _season="", _episode="", last_time=0, action=""):
    #fflog(f'[set_scrobble] {current_time=} {total_time=} {_imdb=} {_season=} {_episode=}')
    try:
        if current_time <= 120 and last_time:
            current_time = last_time
        if not (current_time == 0 or total_time == 0):
            percent = float((current_time / total_time)) * 100
        else:
            percent = 0
        #fflog(f'{percent=}')

        if action == "start" and percent < 99:
            trakt.scrobbleMovie(
                _imdb, percent, action="start"
            ) if _content == "movie" else trakt.scrobbleEpisode(
                _imdb, _season, _episode, percent, action="start"
            )
            #if control.setting("trakt.scrobble.notify") == "true":  # nie ma takiego ustawienia
            if True:
                #control.sleep(1000)
                control.infoDialog("Trakt: Scrobble Start", time=1)
                fflog("Trakt: Scrobble Start")
            return

        #if int(current_time) > 120 and 2 < percent < 92:
        if percent < 92:  # zatrzymanie wideo powinno także zatrzymać progress w dashboardzie, niezależnie od procentu (poniżej granicy finish)
            trakt.scrobbleMovie(
                _imdb, percent, action="pause"
            ) if _content == "movie" else trakt.scrobbleEpisode(
                _imdb, _season, _episode, percent, action="pause"
            )
            #if control.setting("trakt.scrobble.notify") == "true":  # nie ma takiego ustawienia
            if True:
                #control.sleep(1000)
                control.infoDialog("Trakt: Scrobble Paused", time=1)
                fflog("Trakt: Scrobble Paused")
        elif percent >= 92:
            trakt.scrobbleMovie(
                _imdb, percent, action="stop"
            ) if _content == "movie" else trakt.scrobbleEpisode(
                _imdb, _season, _episode, percent, action="stop"
            )
            #if control.setting("trakt.scrobble.notify") == "true":  # nie ma takiego ustawienia
            if True:
                #control.sleep(1000)
                control.infoDialog("Trakt: Scrobbled (finish)", time=1)
                fflog("Trakt: Scrobbled (finish)")
    except Exception:
        fflog_exc(1)
        log_utils.log("Scrobble - Exception", "module")
        control.infoDialog("Scrobble Failed")


def get_scrobble( _content, imdb, season="", episode=""):
    if _content == "movie":
        percent = trakt.getMovieProgress(imdb)
        return percent
    else:
        percent = trakt.getEpisodeProgress(imdb, season, episode)
        return percent


def _indicators(out=None, media_type=None):
    control.makeFile(control.dataPath)
    dbcon = database.connect(control.bookmarksFile)
    dbcur = dbcon.cursor()
    dbcur.execute(
        "CREATE TABLE IF NOT EXISTS bookmarks ("
        "timeInSeconds TEXT, "
        "type TEXT, "
        "imdb TEXT, "  # czasami może być numer tmdb, ale dla kompatybilności w kolumnie o nazwie imdb
        "season TEXT, "
        "episode TEXT, "
        "playcount INTEGER, "
        "overlay INTEGER, "
        "UNIQUE(imdb, season, episode)"
        ");"
    )
    sql_select = "SELECT * FROM bookmarks WHERE overlay = 7"
    if media_type:
        sql_select += " AND type = '%s'" % media_type
    dbcur.execute(sql_select)
    match = dbcur.fetchall()
    dbcon.commit()
    if match:
        # fflog(f'{match=}',1,1)
        if not out:
            return [i[2] for i in match]
        else:
            if out == 'all':
                return [i for i in match]
            elif 'episode' in out or media_type == 'episode':
                # return [(i[2], (i[3],i[4])) for i in match]
                return [(i[2], i[3], i[4]) for i in match]
    else: return []  # czy lepiej None?


def _get_watched(media_type, imdb, season=None, episode=None):
    sql_select = "SELECT * FROM bookmarks WHERE imdb = '%s' AND overlay = 7" % imdb
    # sql_select = "SELECT * FROM bookmarks WHERE imdb = '%s'" % imdb
    if media_type == "episode":
        # sql_select += " AND season = '%s' AND episode = '%s'" % (season, episode)
        if season:
            sql_select += " AND season = '%s'" % season
        if episode:
            sql_select += " AND episode = '%s'" % episode
    control.makeFile(control.dataPath)
    dbcon = database.connect(control.bookmarksFile)
    dbcur = dbcon.cursor()
    dbcur.execute(sql_select)
    match = dbcur.fetchone()
    dbcon.commit()
    # fflog(f'{match=}',1,1)
    if match:
        # if match[6] == 7:
            # return 7
        # else
            # return 6
        return 7  # tu typ liczbowy (a nie string)
    else:
        return 6
        # return 0


def _update_watched(media_type, new_value, imdb, season=None, episode=None):
    sql_update = "UPDATE bookmarks SET overlay = %s WHERE imdb = '%s'" % (new_value, imdb,)
    if media_type == "episode":
        # sql_update += " AND season = '%s' AND episode = '%s'" % (season, episode)
        if season:
            sql_select += " AND season = '%s'" % season
        if episode:
            sql_select += " AND episode = '%s'" % episode
    dbcon = database.connect(control.bookmarksFile)
    dbcur = dbcon.cursor()
    dbcur.execute(sql_update)
    dbcon.commit()


def _delete_record(media_type, imdb, season=None, episode=None):
    fflog(f'{imdb=}  {media_type=}  {season=}  {episode=}',1,1)
    sql_delete = "DELETE FROM bookmarks WHERE imdb = '%s'" % imdb
    if media_type == "episode":
        sql_delete += " AND season = '%s' AND episode = '%s'" % (season, episode)
    dbcon = database.connect(control.bookmarksFile)
    dbcur = dbcon.cursor()
    dbcur.execute(sql_delete)
    dbcon.commit()


def last_position():
    # from local database
    sql_select = "SELECT type, imdb, season, episode FROM bookmarks WHERE rowid = (SELECT MAX(rowid) FROM bookmarks);"
    control.makeFile(control.dataPath)
    dbcon = database.connect(control.bookmarksFile)
    dbcur = dbcon.cursor()
    dbcur.execute(sql_select)
    match = dbcur.fetchone()
    dbcon.commit()
    return match


def last_positions(limit=10):
    # from local database
    # sql_select = "SELECT type, imdb, season, episode FROM bookmarks"
    sql_select = "SELECT type, imdb, season, episode FROM bookmarks ORDER BY rowid DESC LIMIT %s" % limit
    control.makeFile(control.dataPath)
    dbcon = database.connect(control.bookmarksFile)
    dbcur = dbcon.cursor()
    dbcur.execute(sql_select)
    match = dbcur.fetchall()
    dbcon.commit()
    # fflog(f'{len(match)=}  {match=}',1,1)
    # match = match[::-1][:limit]
    # fflog(f'{len(match)=}  {match=}',1,1)
    return match
