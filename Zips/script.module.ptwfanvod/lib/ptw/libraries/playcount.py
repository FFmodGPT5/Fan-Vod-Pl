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

from ptw.libraries import bookmarks
from ptw.libraries import control
from ptw.libraries import log_utils
from ptw.libraries import trakt

from ptw.libraries.log_utils import log, fflog
from ptw.debug import log_exception, fflog_exc



def getMovieIndicators(refresh=False):
    #    try:
    #        if trakt.getTraktIndicatorsInfo():
    #            raise Exception()
    #        from metahandler import metahandlers
    #
    #        indicators = metahandlers.MetaData(preparezip=False)
    #        return indicators
    #    except:
    #        pass

    try:
        if not trakt.getTraktIndicatorsInfo():
            indicators_ = bookmarks._indicators()
            # fflog(f'{indicators_=}',1,1)
            return indicators_
    except Exception:
        fflog_exc(1)
        pass

    try:
        # if not trakt.getTraktIndicatorsInfo():
            # raise Exception()
        if trakt.getTraktIndicatorsInfo():
            if not refresh:
                timeout = 720
            else:
                timeout = 0
            indicators = trakt.cachesyncMovies(timeout=timeout)
            # fflog(f'{indicators}',1,1)
            return indicators
    except Exception:
        fflog_exc(1)
        pass


def getTVShowIndicators(refresh=False):
    try:
        if not trakt.getTraktIndicatorsInfo():
            indicators_ = bookmarks._indicators()
            # fflog(f'{indicators_=}',1,1)
            return indicators_
    except Exception:
        fflog_exc(1)
        pass

    try:
        if trakt.getTraktIndicatorsInfo():
            if not refresh:
                timeout = 720
            # elif trakt.getWatchedActivity() < trakt.timeoutsyncTVShows():
                # timeout = 720
            else:
                timeout = 0
            indicators = trakt.cachesyncTVShows(timeout=timeout)
            # fflog(f'{indicators=}',1,1)
            return indicators
    except Exception:
        fflog_exc(1)
        pass


def getSeasonIndicators(imdb, ret_tuple=False):
    try:
        if not trakt.getTraktIndicatorsInfo():  # czyli lokalnie
            indicators_ = bookmarks._indicators('episode')
            # fflog(f'{indicators_=}',1,1)
            return indicators_
    except Exception:
        fflog_exc(1)
        pass

    try:
        if trakt.getTraktIndicatorsInfo():  # traktowo
        # if not trakt.getTraktIndicatorsInfo():
            # raise Exception()
            indicators = trakt.syncSeason(imdb, ret_tuple=ret_tuple)
            return indicators
    except Exception:
        fflog_exc(1)
        pass


def getEpisodeIndicators(imdb):
    # może trzeba stworzyć ? A może nie jest to potrzebne wcale
    pass
    try:  # na razie to tylko kopiuj-wklej zrobiłem
        if not trakt.getTraktIndicatorsInfo():
            indicators_ = bookmarks._indicators()
            # fflog(f'{indicators_=}',1,1)
            return indicators_
    except Exception:
        fflog_exc(1)
        pass



def getMovieOverlay(indicators, imdb):
    # fflog(f'{imdb=}  {indicators=}',1,1)
    try:
        if trakt.getTraktIndicatorsInfo():
            # if indicators:
            if True:  # tak, aby błąd wyrzucił jak coś
                playcount = [i for i in indicators if i == imdb]
                # fflog(f'{playcount=}')
                overlay = 7 if len(playcount) > 0 else 6
            else:
                overlay = 6
            return str(overlay)
        else:
            overlay = playcount = bookmarks._get_watched("movie", imdb, "", "")  # to może być lokalne
            # fflog(f'{overlay=}')
            return str(overlay)
    except Exception:
        fflog_exc(1)
        return "6"


def getTVShowOverlay(indicators, imdb, tmdb, episodes=0, ret_tuple=False):
    # fflog(f'{imdb=}  {tmdb=}  {episodes=}  {indicators=}',1,1)
    try:
        if trakt.getTraktIndicatorsInfo():
            # fflog(f'{indicators=}',1,1)
            # playcount = [ i[0] for i in indicators if i[0] == tmdb and len(i[2]) >= int(i[1]) ]  # wersja dla trakt
            playcount = [ (i[1], len(i[2])) for i in indicators if i[0] == tmdb ]
            # fflog(f'{playcount=}',1,1)
            if playcount:
                episodes, watched = playcount[0]
            else:
                watched = 0
            # overlay = 7 if playcount else 6
            overlay = 7 if watched and watched >= episodes else 6
        else:  # lokalnie
            # fflog(f'{indicators=}',1,1)
            playcount = [i for i in indicators if i == imdb]  # wersja dla lokalnego
            # fflog(f'{playcount=}',1,1)
            overlay = 7 if playcount and len(playcount) >= episodes else 6
            watched = len(playcount)
        # fflog(f'{overlay=}',1,1)
        # fflog(f'{overlay=}  {watched=}  {episodes=}',1,1)
        if ret_tuple:
            return str(overlay), watched, episodes
        else:
            return str(overlay)
    except Exception:
        fflog_exc(1)
        return "6"


def getSeasonOverlay(indicators, imdb, season, episodes=0, ret_tuple=False):
    # fflog(f'{imdb=}  {season=}  {episodes=}  {indicators=}',1,1)
    try:
        if trakt.getTraktIndicatorsInfo():
            # fflog(f'{indicators=}',1,1)
            if ret_tuple:
                playcount = [i for i in indicators if int(season) == int(i[0])]
                if playcount:
                    _, episodes, watched = playcount[0]
                else:
                    watched = 0
                overlay = 7 if watched and watched >= episodes else 6
                return str(overlay), watched, episodes
            else:
                # stary fragment
                playcount = [i for i in indicators if int(season) == int(i)]
                # fflog(f'{playcount=}',1,1)
                overlay = 7 if len(playcount) > 0 else 6
                # fflog(f'{overlay=}',1,1)
                return str(overlay)

        else:  # lokalnie
            # playcount = bookmarks._get_watched('season', imdb, season, '')  # nie pamiętam, czemu to zakomentowałem, ale być może to chyba dla filmów i odcinków lepiej się sprawdza
            # fflog(f'{indicators=}',1,1)
            playcount = [i for i in indicators if i[0] == imdb and i[1] == str(season)]
            # fflog(f'{playcount=}',1,1)
            overlay = 7 if playcount and len(playcount) >= episodes else 6
            watched = len(playcount)
            # fflog(f'{overlay=}',1,1)
            # fflog(f'{overlay=}  {watched=}  {episodes=}',1,1)
            if ret_tuple:
                return str(overlay), watched, episodes
            else:
                return str(overlay)
    except Exception:
        fflog_exc(1)
        return "6"


def getEpisodeOverlay(indicators, imdb, tmdb, season, episode):
    try:
        if not trakt.getTraktIndicatorsInfo():
            overlay = bookmarks._get_watched("episode", imdb, season, episode)
            # fflog(f'{overlay=}',1,1)
            return str(overlay)
        else:  # lokalnie
            playcount = [i[2] for i in indicators if i[0] == tmdb]
            # fflog(f'{playcount=}',1,1)
            playcount = playcount[0] if len(playcount) > 0 else []
            # fflog(f'{playcount=}',1,1)
            playcount = [
                i
                for i in playcount
                if int(season) == int(i[0]) and int(episode) == int(i[1])
            ]
            # fflog(f'{playcount=}',1,1)
            overlay = 7 if len(playcount) > 0 else 6
            # fflog(f'{overlay=}',1,1)
            return str(overlay)
    except Exception:
        fflog_exc(1)
        return "6"



def markMovieDuringPlayback(imdb, watched, current_time=1, total_time=1, also_locally=False):
    try:
        # if not trakt.getTraktIndicatorsInfo():
            # raise Exception()
        if trakt.getTraktIndicatorsInfo():
            if int(watched) == 7:
                trakt.markMovieAsWatched(imdb)
            else:
                trakt.markMovieAsNotWatched(imdb)

            trakt.cachesyncMovies()

            if trakt.getTraktAddonMovieInfo():
                trakt.markMovieAsNotWatched(imdb)  # dlaczego tu jest 2 raz komenda, która była wcześniej ?
                pass
            if not also_locally:
                return
    except Exception:
        pass

    try:
        if not trakt.getTraktIndicatorsInfo() or also_locally:
            if int(watched) == 7:
                bookmarks.reset(current_time, total_time, "movie", imdb)
            else:
                ok = (int(current_time) > 120  # to ważne
                      and (current_time / total_time) < 0.92  # pomyśleć, czy trzeba
                     )
                if ok:
                    bookmarks._delete_record("movie", imdb)  # przydaje się, aby osatnio oglądany pojawiał się na końcu w tabeli
                    control.sleep(100)
                bookmarks.reset(current_time, total_time, "movie", imdb)
            return
    except Exception:
        fflog_exc(1)
        pass

    try:  # to przestało działać
        from metahandler import metahandlers  # jakiś dodatkowy moduł
        metaget = metahandlers.MetaData(preparezip=False)  # tu jest jakiś błąd (może wersja tego modułu się zmieniła?)
        metaget.get_meta("movie", name="", imdb_id=imdb)
        metaget.change_watched("movie", name="", imdb_id=imdb, watched=int(watched))
    except Exception:
        pass


def markEpisodeDuringPlayback(imdb, tvdb, season, episode, watched, current_time=1, total_time=1, also_locally=False):
    try:
        if trakt.getTraktIndicatorsInfo():
        # if not trakt.getTraktIndicatorsInfo():
            # raise Exception()

            if int(watched) == 7:
                trakt.markEpisodeAsWatched(imdb, season, episode)
            else:
                trakt.markEpisodeAsNotWatched(imdb, season, episode)

            trakt.cachesyncTVShows()

            if trakt.getTraktAddonEpisodeInfo():
                trakt.markEpisodeAsNotWatched(imdb, season, episode)
            if not also_locally:
                return
    except Exception:
        pass

    try:
        if not trakt.getTraktIndicatorsInfo() or also_locally:
            if int(watched) == 7:
                bookmarks.reset(current_time, total_time, "episode", imdb, season, episode)
            else:
                ok = (int(current_time) > 120  # to ważne
                      and (current_time / total_time) < 0.92  # pomyśleć, czy trzeba
                     )
                if ok:
                    bookmarks._delete_record("episode", imdb, season, episode)  # przydaje się, aby osatnio oglądany pojawiał się na końcu w tabeli
                    control.sleep(100)
                bookmarks.reset(current_time, total_time, "episode", imdb, season, episode)
            return
    except Exception:
        fflog_exc(1)
        pass

    try:  # tak jak opis przy filmach - przestało działać
        from metahandler import metahandlers
        metaget = metahandlers.MetaData(preparezip=False)
        metaget.get_meta("tvshow", name="", imdb_id=imdb)
        metaget.get_episode_meta("", imdb_id=imdb, season=season, episode=episode)
        metaget.change_watched(
            "episode",
            "",
            imdb_id=imdb,
            season=season,
            episode=episode,
            watched=int(watched),
        )
    except Exception:
        pass



def movies(imdb, watched):
    # brak tmdb 
    try:
        # if not trakt.getTraktIndicatorsInfo():  # czyli to tylko dla trakt
            # raise Exception("not trakt.getTraktIndicatorsInfo")
        if trakt.getTraktIndicatorsInfo():
            if int(watched) == 7:
                trakt.markMovieAsWatched(imdb)
            else:
                trakt.markMovieAsNotWatched(imdb)
            trakt.cachesyncMovies()  # czy to tu potrzebne?
            control.refresh()
            return
    except Exception:
        # fflog_exc(1)
        pass

    try:
        # if not trakt.getTraktIndicatorsInfo():
        if int(watched) == 7:
            bookmarks.reset(1, 1, "movie", imdb)
        else:
            bookmarks._delete_record("movie", imdb)
        if not trakt.getTraktIndicatorsInfo():
            control.refresh()
            return
    except Exception:
        fflog_exc(1)
        pass

    try:  # to chyba służyło do lokalnego oznaczania statusu za pomocą jakiegoś dodatkowego modułu metahandler
        from metahandler import metahandlers
        metaget = metahandlers.MetaData(preparezip=False)  # coś się zmieniło, bo wyrzuca błąd: TypeError: __init__() got an unexpected keyword argument 'preparezip'
        metaget.get_meta("movie", name="", imdb_id=imdb)
        metaget.change_watched("movie", name="", imdb_id=imdb, watched=int(watched))
        if not trakt.getTraktIndicatorsInfo():
            control.refresh()
    except Exception:
        fflog_exc(1)
        pass


def episodes(imdb, tmdb, season, episode, watched):
    # tmdb nie używany
    try:
        if trakt.getTraktIndicatorsInfo():
            if int(watched) == 7:
                trakt.markEpisodeAsWatched(imdb, season, episode)
            else:
                trakt.markEpisodeAsNotWatched(imdb, season, episode)
            trakt.cachesyncTVShows()  # czy to tu potrzebne?
            control.refresh()
            return
    #        
    except Exception:
        # fflog_exc(1)
        pass

    try:
        if int(watched) == 7:
            bookmarks.reset(1, 1, "episode", imdb, season, episode)
        else:
            bookmarks._delete_record("episode", imdb, season, episode)
        if not trakt.getTraktIndicatorsInfo():
            control.refresh()
            return
    #        
    except Exception:
        fflog_exc(1)
        pass


def tvshows(tvshowtitle, imdb, tmdb, season, watched):
    season = None if season == "None" else season
    imdb = None if imdb == "None" else imdb

    traktIndicatorsInfo = trakt.getTraktIndicatorsInfo()
    # fflog(f'{traktIndicatorsInfo=}')
    
    if traktIndicatorsInfo == False:  # lokalnie
        try:
            import sys, xbmc

            # if not trakt.getTraktIndicatorsInfo() == False:
                # raise Exception()

            # fflog(f'status lokalny (FanVodPL)',1,1)

            from resources.lib.indexers import episodes

            name = control.addonInfo("name")

            dialog = control.progressDialogBG
            dialog.create(str(name), str(tvshowtitle))
            dialog.update(0, str(name), str(tvshowtitle))

            # log_utils.log('playcount_season: ' + str(season))
            items = []
            if season:
                items = episodes.episodes().get(
                    tvshowtitle, "0", imdb, tmdb, meta=None, season=season, idx=False
                )
                items = [
                    i
                    for i in items
                    if int("%01d" % int(season)) == int("%01d" % int(i["season"]))
                ]
                items = [
                    {
                        "label": "%s S%02dE%02d"
                        % (tvshowtitle, int(i["season"]), int(i["episode"])),
                        "season": int("%01d" % int(i["season"])),
                        "episode": int("%01d" % int(i["episode"])),
                        "unaired": i["unaired"],
                    }
                    for i in items
                ]

                for i in range(len(items)):
                    if control.monitor.abortRequested():
                        return sys.exit()

                    dialog.update(
                        int((100 / float(len(items))) * i),
                        str(name),
                        str(items[i]["label"]),
                    )

                    _season, _episode, unaired = (
                        items[i]["season"],
                        items[i]["episode"],
                        items[i]["unaired"],
                    )
                    if int(watched) == 7:
                        if not unaired == "true":
                            bookmarks.reset(1, 1, "episode", imdb, _season, _episode)
                        else:
                            pass
                    else:
                        bookmarks._delete_record("episode", imdb, _season, _episode)

            else:
                seasons = episodes.seasons().get(
                    tvshowtitle, "0", imdb, tmdb, meta=None, idx=False
                )
                seasons = [i["season"] for i in seasons]
                # log_utils.log('playcount_seasons: ' + str(seasons))
                for s in seasons:
                    items = episodes.episodes().get(
                        tvshowtitle, "0", imdb, tmdb, meta=None, season=s, idx=False
                    )
                    items = [
                        {
                            "label": "%s S%02dE%02d"
                            % (tvshowtitle, int(i["season"]), int(i["episode"])),
                            "season": int("%01d" % int(i["season"])),
                            "episode": int("%01d" % int(i["episode"])),
                            "unaired": i["unaired"],
                        }
                        for i in items
                    ]
                    # log_utils.log('playcount_items2: ' + str(items))

                    for i in range(len(items)):
                        if control.monitor.abortRequested():
                            return sys.exit()

                        dialog.update(
                            int((100 / float(len(items))) * i),
                            str(name),
                            str(items[i]["label"]),
                        )

                        _season, _episode, unaired = (
                            items[i]["season"],
                            items[i]["episode"],
                            items[i]["unaired"],
                        )
                        if int(watched) == 7:
                            if not unaired == "true":
                                bookmarks.reset(1, 1, "episode", imdb, _season, _episode)
                            else:
                                pass
                        else:
                            bookmarks._delete_record("episode", imdb, _season, _episode)

            try:
                dialog.close()
            except Exception:
                fflog_exc(1)
                pass
        except Exception:
            log_utils.log("playcount_local_shows", "module")
            fflog_exc(1)
            pass
            try:
                dialog.close()
            except Exception:
                fflog_exc(1)
                pass

    else:
        try:
            if not trakt.getTraktIndicatorsInfo():  # to już się i tak nie wykona
                fflog(f'not trakt.getTraktIndicatorsInfo (2)')
                raise Exception()

            # fflog(f'status Trakt',1,1)

            # log_utils.log('playcount_season: ' + str(season))
            if season:
                from resources.lib.indexers import episodes

                items = episodes.episodes().get(
                    tvshowtitle, "0", imdb, tmdb, meta=None, season=season, idx=False
                )
                items = [(int(i["season"]), int(i["episode"])) for i in items]
                items = [
                    i[1] for i in items if int("%01d" % int(season)) == int("%01d" % i[0])
                ]
                for i in items:
                    if int(watched) == 7:
                        trakt.markEpisodeAsWatched(imdb, season, i)
                    else:
                        trakt.markEpisodeAsNotWatched(imdb, season, i)
            else:
                if int(watched) == 7:
                    trakt.markTVShowAsWatched(imdb)
                else:
                    trakt.markTVShowAsNotWatched(imdb)
            trakt.cachesyncTVShows()  # czy to tu potrzebne?
        except Exception:
            log_utils.log("playcount_trakt_shows", "module")
            fflog_exc(1)
            pass

    control.refresh()
#    
