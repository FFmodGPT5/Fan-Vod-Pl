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

try:
    from sqlite3 import dbapi2 as database
except:
    from pysqlite2 import dbapi2 as database

from ptw.libraries import control
# from ptw.libraries.log_utils import log, fflog
from ptw.debug import log_exception, fflog_exc

def addView(content):
    try:
        # import pydevd
        # pydevd.settrace('localhost', port=5678, stdoutToServer=True, stderrToServer=True)
        skin = control.skin
        record = ( skin, content, str(control.getCurrentViewId()) )

        control.makeFile(control.dataPath)
        dbcon = database.connect(control.viewsFile)
        dbcur = dbcon.cursor()
        dbcur.execute(
            "CREATE TABLE IF NOT EXISTS views ("
            "skin TEXT, "
            "view_type TEXT, "
            "view_id TEXT, "
            "UNIQUE(skin, view_type)"
            ");"
        )
        dbcur.execute(
            "DELETE FROM views WHERE skin = '%s' AND view_type = '%s'"
            % (record[0], record[1])
        )
        dbcur.execute("INSERT INTO views Values (?, ?, ?)", record)
        dbcon.commit()

        viewName = control.infoLabel("Container.Viewmode")
        skinName = control.addon(skin).getAddonInfo("name")
        skinIcon = control.addon(skin).getAddonInfo("icon")
        control.infoDialog(f"{content} \n{viewName}", heading=skinName, sound=True, icon=skinIcon)  # informacja
        control.execute('Action(Back)')
    except Exception:
        fflog_exc(1)
        return


def setView(content, viewDict=None):
    # control.log(f'[views.py] start', 1)
    for i in range(0, int(1000/50) * 2):  # 2 sek.
        if control.condVisibility("Container.Content(%s)" % content):
            # control.log(f'[views.py] in', 1)
            skin = control.skin
            # control.log(f'[views.py] {skin=}', 1)
            try:
                record = (skin, content)
                dbcon = database.connect(control.viewsFile)
                dbcur = dbcon.cursor()
                dbcur.execute(
                    "SELECT * FROM views WHERE skin = '%s' AND view_type = '%s'"
                    % (record[0], record[1])
                )
                view = dbcur.fetchone()
                # control.log(f'[views.py] {view=}', 1)  # example view=('skin.quartz', 'movies', '52')
                if view:
                    view = view[2]
                if view is None:
                    if not viewDict:
                        return  # dostawiłem
                        pass
                    raise Exception(f'{view=}')
                control.sleep(100)  # można ewentualnie poeksperymentować z czasem
                control.execute("Container.SetViewMode(%s)" % str(view))
                # control.sleep(100)  # to raczej niepotrzebne
                # control.log(f'[views.py] done', 1)
                break
            except Exception:
                fflog_exc(0)
                try:
                    # nie wiem, kiedy jest taki przypadek
                    # control.log(f'[views.py] to ten inny przypadek', 0)
                    control.log(f'[views.py] {viewDict=}', 0)
                    control.log(f'[views.py] {skin=}', 0)
                    control.sleep(100)
                    if viewDict:
                        control.execute("Container.SetViewMode(%s)" % str(viewDict[skin]))
                    break
                except Exception:
                    fflog_exc(0)
                    # control.log(f'[views.py] give up', 1)
                    return
        # control.log(f'[views.py] waiting {i=}', 1)
        control.sleep(50)
    # control.log(f'[views.py] end', 1)
