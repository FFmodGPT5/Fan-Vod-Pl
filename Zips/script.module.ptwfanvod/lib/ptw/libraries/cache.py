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


import hashlib
import re
import time
import os

from ast import literal_eval

try:
    from sqlite3 import dbapi2 as db, OperationalError
except ImportError:
    from pysqlite2 import dbapi2 as db, OperationalError

from ptw.libraries import control, log_utils
from ptw.libraries.log_utils import log, fflog
from ptw.debug import log_exception, fflog_exc


data_path = control.dataPath


def create_cache_table():
    cursor = _get_connection_cursor()
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS cache (key TEXT, value TEXT, date INTEGER, UNIQUE(key))"
    )


def get(function, duration, *args, kwargs=None, output_type=None, callback=None):
    """
    :param function: Function to be executed
    :param duration: Duration of validity of cache in hours
    :param args: Optional arguments for the provided function
    :param kwargs: Optional named arguments for the provided function (must be as one dict)
    """
    # control.log(f'[FanVodPL]  [cache.py]  [get]  \n{function=}  \n{args=}  \n{duration=}  {output_type=}  {callback=}', 1)
    if kwargs is None:
        kwargs = {}
    try:
        key = _hash_function(function, args)
        # key = _hash_function(function, args, kwargs)  # nie wiem, czy jest taka potrzeba
        # fflog(f'{key=}\n',0,1)
        cache_result = cache_get(key)
        if cache_result:
            # fflog(f'jest taki rekord w bazie cache')
            try:
                result = literal_eval(cache_result['value'])
            except Exception:
                result = None
                # fflog(f'jakiś błąd danych tego rekordu',1,1)
                fflog_exc(0)
            if _is_cache_valid(cache_result['date'], duration) and result:  # zakłożenie, że jak puste, to można spróbowac ponownie
                # fflog(f"dane pobrane zostały z cache | {function} {args=}",1,1)
                if output_type == "tuple":
                    result = (result, True)
                return result
            else:
                # fflog(f"przeterminowany rekord, bo {duration=}  {cache_result.get('date')=}",1,1)
                pass
        else:
            # fflog('nie ma takiego pasującego rekordu w cache',1,1)
            pass

        # fflog(f'do wykonania: {function=}   {args=}',1,1)
        try:
            fresh_result = function(*args, **kwargs)  # may need a try-except block for server timeouts
        except Exception:
            fflog_exc(1)
            return
            pass
        try:
            if callback:
                fresh_result = eval("fresh_result" + callback)
            fresh_result = repr(fresh_result)
        except Exception:
            fflog_exc(1)
            return fresh_result
            pass
            # fresh_result = ""
        # fflog(f'{fresh_result=}',1,1)

        if True:  # dodałem
            # fflog(f'wstawienie każdego wyniku do bazy')
            cache_insert(key, fresh_result)  # wstawienie do bazy
            return literal_eval(fresh_result)  # i KONIEC
        """
        if cache_result and (result and len(result) == 1) and fresh_result == '[]': # fix for syncSeason mark unwatched season when it's the last item remaining
            fflog(f'tutaj 1 {result[0]=}')
            if result[0].isdigit():  # dlaczego taki warunek?
            # if True:
                remove(function, *args)  # usunięcie rekordu z bazy cache
                # remove(function, args)  # a nie powinno być tak ?
                # remove(key)  # a czemu nie tak?
                # remove("", "", key=key)  # albo tak (musi być nazwana zmienna, bo inaczej wciągnie to pod args)
                fflog('tutaj 2')
                return []

        invalid = False
        try:  # Sometimes None is returned as a string instead of None type for "fresh_result"
            if not fresh_result:
                invalid = True
            elif fresh_result == 'None' or fresh_result == '' or fresh_result == '[]' or fresh_result == '{}':  # tylko, że czasami chcemy, aby wynik był [] czy {}, czyli to, co zwraca rzeczywiście funkcja
                invalid = True
            elif len(fresh_result) == 0:
                invalid = True
        except:
            pass
        fflog(f'{invalid=}')
        if invalid:  # If the cache is old, but we didn't get "fresh_result", return the old cache  # no i mi to właśnie psuło!
            if cache_result:
                fflog(f'zwrócenie poprzedniego wyniku')
                return result
            else:
                return None  # do not cache_insert() None type, sometimes servers just down momentarily  - A NIŻEJ jest wstawiane None - to dlaczego? Może kiedyś tak było (w dawniejszych czasach)
        else:
            if '404:NOT FOUND' in fresh_result:
                fflog(f'wstawienie pustego wyniku do bazy')
                cache_insert(key, None)  # cache_insert() "404:NOT FOUND" cases only as None type
                return None
            else:
                fflog(f'wstawienie wyniku do bazy')
                cache_insert(key, fresh_result)  # wstawienie do bazy
            return literal_eval(fresh_result)
        """
    except Exception:
        from ptw.libraries import log_utils
        log_utils.log('Cache:', log_utils.LOGDEBUG)
        fflog_exc(1)
        return None


def timeout(function_, *args):
    try:
        key = _hash_function(function_, args)
        result = cache_get(key)
        time_out = int(result['date']) if result else 0
        # time_out = int(result["date"])
        # log_utils.fflog(f'{time_out=}',1,1)
        return time_out
    except Exception:
        return 0
        # return None


def calculate_key(function, *args):  # testowo
    control.log(f'{function=} {args=}',1)
    key = _hash_function(function, args)
    control.log(f'{key=}',1)
    return key


def cache_existing(function, *args):  # tu nieużywane (ale może jakaś funkcja z zewnątrz z tego korzysta)
    try:
        cache_result = cache_get( _hash_function(function, args) )
        if cache_result:
            return literal_eval(cache_result['value'])
        else:
            return None
    except:
        from ptw.libraries import log_utils
        log_utils.log('Cache:', log_utils.LOGDEBUG)
        return None


def cache_get(key, db_path=None, like=None):
    # type: (str, str) -> dict or None
    try:
        cursor = _get_connection_cursor()
        if like:
            cursor.execute('''SELECT * FROM cache WHERE key like ?''', (like,))
        else:
            cursor.execute('''SELECT * FROM cache WHERE key=?''', (key,))
        return cursor.fetchone()
    except OperationalError:
        # fflog_exc(1)
        return None


def cache_insert(key, value, db_path=None):
    # type: (str, str) -> None
    cursor = _get_connection_cursor()
    now = int(time.time())
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS cache (key TEXT, value TEXT, date INTEGER, UNIQUE(key))")

    update_result = cursor.execute(
        "UPDATE cache SET value=?,date=? WHERE key=?", (value, now, key)
    )

    if update_result.rowcount == 0:
        cursor.execute(
            "INSERT INTO cache Values (?, ?, ?)", (key, value, now)
        )

    cursor.connection.commit()


def remove(function, *args, like=None, key=None):  # aby nie wciągało do args, to like i key muszą być nazwane
    # control.log(f'[FanVodPL]  [cache.py]  [remove]  \n{function=}  \n{args=}  \n{like=}',0)
    try:
        if not key:
            key = _hash_function(function, args)
        fflog(f'{key=}',0,1)
        if like is True:
            like = key
        key_exists = cache_get(key, like=like)
        fflog(f'{key_exists=}',0,1)
        if key_exists:
            dbcon = _get_connection()
            dbcur = _get_connection_cursor(dbcon)
            if like:
                dbcur.execute('''DELETE FROM cache WHERE key like ?''', (like,))
            else:
                dbcur.execute('''DELETE FROM cache WHERE key=?''', (key,))
            dbcur.connection.commit()
        else:
            return False
    except:
        from ptw.libraries import log_utils
        log_utils.log('Cache:', log_utils.LOGDEBUG)
    try:
        dbcur.close()
        dbcon.close()
    except:
        pass


def cache_remove(key, like=None):
    try:
        dbcon = _get_connection()
        dbcur = _get_connection_cursor(dbcon)
        if like:
            dbcur.execute('''DELETE FROM cache WHERE key like ?''', (like,))
        else:
            dbcur.execute('''DELETE FROM cache WHERE key=?''', (key,))
        dbcur.connection.commit()
    except Exception:
        # from ptw.libraries import log_utils
        # log_utils.log('Cache:', log_utils.LOGDEBUG)
        # return False
        pass
    try:
        dbcur.close()
        dbcon.close()
    except:
        pass


def remove_partial_key(partial_key):
    ret = None
    try:
        create_cache_table()
        cursor = _get_connection_cursor()
        cursor.execute(f"DELETE FROM cache WHERE key LIKE '%{partial_key}%'")
        cursor.connection.commit()
        ret = True
    except OperationalError:
        pass
        ret = False
    try:
        dbcur.close()
        dbcon.close()
    except:
        pass
    return ret


def cache_clear_old():
    try:
        cursor = _get_connection_cursor()
        for t in [cache_table, "rel_list", "rel_lib"]:
            try:
                cursor.execute("DROP TABLE IF EXISTS %s" % t)
                cursor.execute("VACUUM")
                cursor.commit()
            except:
                pass
        cache_clear_meta()
    except:
        pass


def cache_clear(flush_only=False):
    cleared = False
    dbcon = None
    try:
        dbcon = _get_connection()
        dbcur = _get_connection_cursor(dbcon)
        if flush_only:
            dbcur.execute('''DELETE FROM cache''')
            dbcur.connection.commit() # added this for what looks like a 19 bug not found in 18, normal commit is at end
            dbcur.execute('''VACUUM''')
            cleared = True
        else:
            dbcur.execute('''DROP TABLE IF EXISTS cache''')
            dbcur.execute('''VACUUM''')
            dbcur.connection.commit()
            cleared = True
    except:
        from ptw.libraries import log_utils
        log_utils.log('Cache:', log_utils.LOGDEBUG)
        cleared = False
    finally:
        if dbcon is not None:
            dbcon.close()
    #return cleared


def cache_clear_meta():
    try:
        cursor = _get_connection_cursor_meta()

        for t in ["meta"]:
            try:
                cursor.execute("DROP TABLE IF EXISTS %s" % t)
                cursor.execute("VACUUM")
                cursor.commit()
            except:
                pass
    except:
        pass


def cache_clear_providers():
    try:
        cursor = _get_connection_cursor_providers()

        for t in ["rel_src", "rel_url"]:
            try:
                cursor.execute("DROP TABLE IF EXISTS %s" % t)
                cursor.execute("VACUUM")
                cursor.commit()
            except:
                pass
    except:
        pass


def cache_clear_search(content=None):
    try:
        cursor = _get_connection_cursor_search()
        allowed_content = ["tvshow", "movies", "persons", "multis", "collections"]
        if content == "all":
            content = allowed_content  # usunie wszystkie tabele jakie są w pliku
            pass
        elif content not in allowed_content:
            raise Exception(f"not allowed {content=}")
            pass
        else:
            content = [content]
        for t in content:
            try:
                cursor.execute("DROP TABLE IF EXISTS %s" % t)
                cursor.execute("VACUUM")
                cursor.commit()
            except:
                pass
        return True
    except Exception as e:
        log_utils.log(f"[cache_clear_search] Error: {e}")
        fflog_exc(1)


def cache_clear_search_by_term(term_value, content=None):
    try:
        cursor = _get_connection_cursor_search()
        allowed_content = ["tvshow", "movies", "persons", "multis", "collections"]
        if content not in allowed_content:
            # content = allowed_content
            raise Exception(f"not allowed {content=}")
            pass
        else:
            content = [content]
        for t in content:
            cursor.execute("DELETE FROM %s WHERE term = ?" % t, (term_value,))
            cursor.connection.commit()
        return True
    except Exception as e:
        log_utils.log(f"[cache_clear_search_by_term] Error: {e}")
        fflog_exc(1)


def cache_clear_all():
    cache_clear()
    cache_clear_meta()
    cache_clear_providers()


def _get_connection_cursor(conn=None):
    if conn is None:
        conn = _get_connection()
    return conn.cursor()


def _get_connection():
    if not control.existsPath(control.dataPath):
        control.makeFile(control.dataPath)
    dbcon = db.connect(control.cacheFile, timeout=60) # added timeout 3/23/21 for concurrency with threads
    dbcon.execute('''PRAGMA page_size = 32768''')
    dbcon.execute('''PRAGMA journal_mode = OFF''')
    dbcon.execute('''PRAGMA synchronous = OFF''')
    dbcon.execute('''PRAGMA temp_store = memory''')
    dbcon.execute('''PRAGMA mmap_size = 30000000000''')
    dbcon.row_factory = _dict_factory
    return dbcon


def _get_connection_cursor_meta():
    conn = _get_connection_meta()
    return conn.cursor()


def _get_connection_meta():
    control.makeFile(data_path)
    conn = db.connect(os.path.join(data_path, control.metacacheFile))
    conn.row_factory = _dict_factory
    return conn


def _get_connection_cursor_providers():
    conn = _get_connection_providers()
    return conn.cursor()


def _get_connection_providers():
    control.makeFile(data_path)
    conn = db.connect(os.path.join(data_path, control.providercacheFile))
    conn.row_factory = _dict_factory
    return conn


def _get_connection_cursor_search():
    conn = _get_connection_search()
    return conn.cursor()


def _get_connection_search():
    control.makeFile(data_path)
    conn = db.connect(os.path.join(data_path, control.searchFile))
    conn.row_factory = _dict_factory
    return conn


def _dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


def _hash_function(function_instance, *args):
    # control.log(f'\n {function_instance=} \n {args=}',1)
    # print(f'\n {function_instance=} \n {args=}')
    return _get_function_name(function_instance) + _generate_md5(args)


def _get_function_name(function_instance):
    if isinstance(function_instance, str):
        return function_instance
    return re.sub(r".+\smethod\s|.+function\s|\sat\s.+|\sof\s.+", "", repr(function_instance))


def _generate_md5(*args):
    # control.log(f'{args=}',1)
    md5_hash = hashlib.md5()
    try:
        [md5_hash.update(str(arg)) for arg in args]
    except Exception:
        # fflog_exc(1)
        [md5_hash.update(str(arg).encode('utf-8')) for arg in args]
    # control.log(f'{md5_hash=}',1)
    # control.log(f'{md5_hash.hexdigest()=}',1)
    return str(md5_hash.hexdigest())


def _is_cache_valid(cached_time, cache_timeout):
    now = int(time.time())
    diff = now - cached_time
    return (cache_timeout * 3600) > diff


def get_old(function_, duration, *args, **table):

    try:
        response = None

        f = repr(function_)
        f = re.sub(r".+\smethod\s|.+function\s|\sat\s.+|\sof\s.+", "", f)

        a = hashlib.md5()
        for i in args:
            try:
                a.update(str(i))
            except:
                a.update(str(i).encode('utf-8'))
        a = str(a.hexdigest())
    except Exception:
        pass

    try:
        table = table["table"]
    except Exception:
        table = "rel_list"

    try:
        control.makeFile(control.dataPath)
        dbcon = db.connect(control.cacheFile)
        dbcur = dbcon.cursor()
        dbcur.execute(
            "SELECT * FROM {tn} WHERE func = '{f}' AND args = '{a}'".format(
                tn=table, f=f, a=a
            )
        )
        match = dbcur.fetchone()

        try:
            response = literal_eval(match[2].encode("utf-8"))
        except AttributeError:
            response = literal_eval(match[2])

        t1 = int(match[3])
        t2 = int(time.time())
        update = (abs(t2 - t1) / 3600) >= int(duration)
        if not update:
            return response
    except Exception:
        pass

    try:
        r = function_(*args)
        if (r is None or r == []) and response is not None:
            return response
        elif r is None or r == []:
            return r
    except Exception:
        return

    try:
        r = repr(r)
        t = int(time.time())
        dbcur.execute(
            "CREATE TABLE IF NOT EXISTS {} ("
            "func TEXT, "
            "args TEXT, "
            "response TEXT, "
            "added TEXT, "
            "UNIQUE(func, args)"
            ");".format(table)
        )
        dbcur.execute(
            "DELETE FROM {0} WHERE func = '{1}' AND args = '{2}'".format(table, f, a)
        )
        dbcur.execute("INSERT INTO {} Values (?, ?, ?, ?)".format(table), (f, a, r, t))
        dbcon.commit()
    except Exception:
        pass

    try:
        return literal_eval(r.encode("utf-8"))
    except Exception:
        return literal_eval(r)


def _get_connection_old():
    control.makeFile(data_path)
    conn = db.connect(os.path.join(data_path, "cache.db"))
    conn.row_factory = _dict_factory
    return conn
