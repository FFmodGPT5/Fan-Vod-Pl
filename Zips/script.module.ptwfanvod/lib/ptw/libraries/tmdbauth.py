# -*- coding: utf-8 -*-


import requests
from ptw.libraries import control
from ptw.libraries import apis
from ptw.libraries import log_utils



class cached_property:
    """
    A property that is only computed once per instance and then replaces itself
    with an ordinary attribute. Deleting the attribute resets the property.
    Source: https://github.com/bottlepy/bottle/commit/fa7733e075da0d790d809aa3d2f53071897e6f76
    """  # noqa

    def __init__(self, func):
        self.__doc__ = getattr(func, "__doc__")
        self.func = func

    def __get__(self, obj, cls):
        if obj is None:
            return self

        value = obj.__dict__[self.func.__name__] = self.func(obj)
        return value



class Auth:

    def __init__(self):
        self.auth_base_link = 'https://api.themoviedb.org/3/authentication'
        # self.auth_base_link_v4 = '"https://api.themoviedb.org/4/auth'
        self.tm_user = control.setting("tm.user") or apis.tmdb_API
        # control.log(f'{self.tm_user=}',1)  # ten z api zgłasza pod nazwą Home Movie Library 
        self.bearer = control.setting("tm.user_bearer") or apis.tmdb_bearer  # read access token


    def generate_access_token(self):  # v4
        # https://developer.themoviedb.org/v4/docs/authentication-user
        # 1. Generate a new request token
        # 2. Send the user to TMDB asking the user to approve the token
        # 3. With an approved request token, generate a fresh access token


        # if control.setting('tmdb.username') != '' and control.setting('tmdb.password') != '' and control.setting("tmdb.version") == '0':
        if control.setting("tmdb.version") == '0':
            # log_utils.fflog(f'przejście do wersji v3, bo podano nazwę użytkownika i HASŁO',1,1)
            log_utils.fflog(f'przejście do wersji v3',1,1)
            self.create_session_id()  # przejście do starej metody
            return
            pass

        log_utils.fflog(f'będzie zastosowana wersja v4',1,1)

        if not self.bearer:
            log_utils.fflog(f'wystąpił jakiś błąd  {self.bearer=}',1,1)
            control.infoDialog("Wystąpił jakiś błąd - powiadom dewelopera", 'Autoryzacja v4 TMDB', 'ERROR')
            return            

        msg = "Proces polega na zatwierdzeniu w serwisie internetowym TMDB żadania autoryzacji.\nCzy chcesz kontynuować?"
        if not control.yesnoDialog(msg, heading='Autoryzacja TMDB v4'):
            log_utils.fflog('użytkownik zrezygnował z procedury zewnętrznego uwierzytelniania (v4)',1,1)
            return
            pass


        # 1. Generate a new request token  https://developer.themoviedb.org/v4/reference/auth-create-request-token
        url = "https://api.themoviedb.org/4/auth/request_token"
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "Authorization": f"Bearer {self.bearer}"
        }
        response = requests.post(url, headers=headers)
        # log_utils.fflog(f'{response=}',1,1)
        if not response:
            # log_utils.fflog(f'wystąpił jakiś błąd  {response=}  {url=}  {headers=}',1,1)
            log_utils.fflog(f'wystąpił jakiś błąd  {response=}  {url=}',1,1)
            control.infoDialog("Wystąpił jakiś błąd", 'Autoryzacja v4 TMDB', 'ERROR')
            return
        # log_utils.fflog(f'{response.text=}',1,1)
        # log_utils.fflog(f'{response.json()=}',1,1)
        response = response.json()
        request_token = response.get('request_token')
        if not request_token:
            log_utils.fflog(f'wystąpił jakiś błąd  {request_token=}  {response=}  {url=}',1,1)
            control.infoDialog("Wystąpił jakiś błąd", 'Autoryzacja v4 TMDB', 'ERROR')
            return
            pass
        else:
            log_utils.fflog(f'zaczyna być liczony czas ważności tymczasowego tokena (15 minut)',1,1) 
            pass


        # 2. Send the user to TMDB asking the user to approve the token
        url2 = f'https://www.themoviedb.org/auth/access?request_token={request_token}'

        # otwiera domyślną przeglądarkę internetową systemu operacyjnego (nie działa na Androidach)
        import webbrowser
        webbrowser.open(url2, new=0, autoraise=True)

        from ptw.libraries import segno
        qrcode = segno.make(url2)  # generacja qrkodu

        data_path = control.dataPath
        import os
        qrcode_file = os.path.join(data_path, "qrcode.png")
        qrcode.save(qrcode_file, scale=8)  # zapis obrazka na dysk

        self.request_token_qrcode = qrcode_file  # przekazanie do wyświetlenia na ekranie
        self.dialog_progress_create()

        if False:
            wait_for_approve = None
            control.sleep(3000)
            msg = "Po zakończeniu czynności na stronie\n wybierz TAK, aby kontynuować"
            if control.yesnoDialog(msg, heading='Autoryzacja TMDB v4'):
                # wait_for_approve = False
                self.dialog_progress.update(99)
                # self.dialog_qrcode_close()
                pass
            else:
                log_utils.fflog('użytkownik zrezygnował z kontynuacji procedury zewnętrznego uwierzytelniania (v4)',1,1)
                wait_for_approve = False
                self.dialog_qrcode_close()
                return
                pass
            self.dialog_qrcode_close()
        else:
            pass
            wait_for_approve = True
            # można sprawdzać odpowiedź i jeśli będzie 422, to znaczy, że jeszcze użytkownik nie zatwierdził na stronie
            # dla url = "https://api.themoviedb.org/4/auth/access_token"


        # 3. With an approved request token, generate a fresh access token  https://developer.themoviedb.org/v4/reference/auth-create-access-token
        response = url = payload = headers = None
        monitor = control.monitor
        max_counter = counter = 15 * 60  # minut

        url = "https://api.themoviedb.org/4/auth/access_token"
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "Authorization": f"Bearer {self.bearer}"
        }
        payload = {"request_token": request_token}

        while wait_for_approve is None or wait_for_approve and counter > 0:
        # if True:
            response = requests.post(url, json=payload, headers=headers)
            # log_utils.fflog(f'{response.status_code=}  {counter=}',1,1)
            if response.status_code == 422:
                pass
                wait_for_approve = bool(wait_for_approve)  # aby None zlikwidować
            else:
                wait_for_approve = False
                pass
            if self.dialog_progress.iscanceled():
                wait_for_approve = False
                log_utils.fflog('nastąpiło anulowanie czekania',1,1)
                return
            if wait_for_approve:
                control.sleep(5000)  # 5 sekund
                if monitor.abortRequested():
                    return
                counter -= 5  # 5 sekund
                progress = 100 - ((counter * 100) / max_counter)
                self.dialog_progress.update(int(progress))
                # log_utils.fflog(f'{counter=}  {int(progress)=}',1,1)
        # if control.condVisibility('Window.IsActive(DialogConfirm)'):  # nie jestem pewien, ale i tak trzeba odczepić obrazek od okienka typu progress
        try:
            self.dialog_progress_close()
            pass
        except:
            pass

        if not response:
            log_utils.fflog(f'wystąpił jakiś błąd  {response=}  {url=}  {payload=}  {headers=}',1,1)
            control.infoDialog("Wystąpił jakiś błąd", 'Autoryzacja v4 TMDB', 'ERROR')
            log_utils.fflog(f'wystąpił jakiś błąd  {response.status_code=}  {response.text=}',1,1) if response is not None else ''
            return
        # log_utils.fflog(f'{response.text=}',1,1)
        response = response.json()
        if response.get('success') is True:
            access_token = response.get('access_token')
            msg = "Wsztko w porządku. Czy zapisać autoryzację?"
            if control.yesnoDialog(msg, heading='Autoryzacja TMDB v4'):
                control.setSetting('tmdb.access_token', access_token)  # zapisanie dostępowego tokenu sesji w Ustawieniach
                control.setSetting('tmdb.account_id', response.get('account_id'))
                log_utils.fflog('zapisano dane autoryzacyjne (v4) w Ustawieniach',1,1)

                log_utils.fflog('jeszcze przekonwertowanie access tokena (v4) do session_id (v3)',1,1)
                url = "https://api.themoviedb.org/3/authentication/session/convert/4"
                headers = {
                    "accept": "application/json",
                    "content-type": "application/json",
                    "Authorization": f"Bearer {self.bearer}"
                }
                payload = {"access_token": access_token}
                # control.sleep(1000)  # bo po drodze jest jeszcze komunikat potwierdzający
                response = requests.post(url, json=payload, headers=headers)
                if response:
                    response = response.json()
                    if response.get('success') is True:
                        session_id = response.get('session_id')
                        control.setSetting('tmdb.sessionid', session_id)  # zapisanie identyfikatora sesji w Ustawieniach (dla v3)
                        # control.setSetting('tmdb.session_id', session_id)
                    else:
                        log_utils.fflog(f'wystąpił problem przy konwertowaniu access tokena (v4) do session_id (v3)',1,1)
                        log_utils.fflog(f'  {response=}  {url=}',1,1)
                        pass
                else:
                    log_utils.fflog(f'{response=}  {url=}',1,1)
                    log_utils.fflog(f'{response.text=}  {url=}',1,1)
                    pass

                control.infoDialog("Autoryzacja zapisana", 'Autoryzacja v4 TMDB', 'default')
            else:
                control.infoDialog("Zrezygnowano", 'Autoryzacja v4 TMDB', 'WARNING')
        else:
            log_utils.fflog(f'wystąpił jakiś błąd  {response=}  {url=}',1,1)
            control.infoDialog("Wystąpił jakiś błąd", 'Autoryzacja v4 TMDB', 'ERROR')



    def create_session_id(self):  # v3
        """ uzyskanie identyfikatora sesji i zapisanie go w Ustawieniach """
        # https://developer.themoviedb.org/reference/authentication-how-do-i-generate-a-session-id
        # 1. Create a new request token
        # 2. Get the user to authorize the request token (Ask the user for permission or do it automatically with username and password)
        # 3. Create a new session id with the athorized request token

        log_utils.fflog(f'będzie zastosowana wersja v3',1,1)

        if control.setting('tmdb.username') == '' or control.setting('tmdb.password') == '':
            # return control.notification(title='default', message=32683, icon='ERROR')  # bo można to zrobić za pomocą serwisu tmdb (tam będzie logowanie)
            pass


        url = self.auth_base_link + '/token/new?api_key=%s' % self.tm_user
        result = requests.get(url)  # 1-wsze zapytanie do serwera (na podstawie klucza API) o tymczasowy token potrzebny tylko na czas procesu autoryzacji 
        if not result:
            log_utils.fflog(f'wystąpił jakiś błąd  {result=}  {url=}',1,1)
            control.infoDialog("Wystąpił jakiś błąd", 'Autoryzacja v3 TMDB', 'ERROR')
            return
            pass
        result = result.json()

        token = result.get('request_token')  # otrzymanie tokenu (będzie dołączany do każdego kolejengo polecenia do serwera w tym procesie)
        if not token:
            log_utils.fflog(f'wystąpił jakiś błąd  {token=}  {result=}',1,1)
            control.infoDialog("Wystąpił jakiś błąd", 'Autoryzacja v3 TMDB', 'ERROR')
            return
            pass
        else:
            pass
            # ważność tokena to 60 minut (wg dokumentacji TMDb)


        if control.setting('tmdb.username') == '' or control.setting('tmdb.password') == '':
        # if True:  # na testy
            log_utils.fflog(f'rozpoczęcie procedury zewnętrznego uwierzytelnienia (v3)',1,1)
            # return control.notification(title='default', message=32683, icon='ERROR')
            pass
            url2 = f'https://www.themoviedb.org/authenticate/{token}'
            # log_utils.fflog(f'{url2=}',1,1)

            # msg = f"[LIGHT]Przejdź na stronę \n[B]{url2}[/B]\ni zatwierdź autoryzację (ważne przez 60 min)\nNastępnie wybierz czy kontynuować[/LIGHT]"
            # msg = "[LIGHT]Proces polega na zatwierdzeniu w serwisie internetowym TMDB żadania autoryzacji.\nCzy chcesz kontynuować? [I](Zostanie otwarta twoja domyślna przeglądarka internetowa)[/I][/LIGHT]"
            msg = "Proces polega na zatwierdzeniu w serwisie internetowym TMDB żadania autoryzacji.\nCzy chcesz kontynuować?"
            if control.yesnoDialog(msg, heading='Autoryzacja TMDB'):

                # otwiera domyślną przeglądarkę internetową systemu operacyjnego (nie działa na Androidach)
                import webbrowser
                webbrowser.open(url2, new=0, autoraise=True)

                from ptw.libraries import segno
                qrcode = segno.make(url2)  # generacja qrkodu

                data_path = control.dataPath
                import os
                qrcode_file = os.path.join(data_path, "qrcode.png")
                qrcode.save(qrcode_file, scale=8)  # zapis obrazka na dysk

                self.request_token_qrcode = qrcode_file  # przekazanie do wyświetlenia na ekranie
                self.dialog_progress_create()

                control.sleep(3000)

                # self.dialog_progress.update(50)
                
                # tu nie wiem, czy da się wykryć zatwierdzenie na stronie, bo status jest zawsze 401 (choć może to nie przeszkadza)
                # ale czas ważności tymczasowego tokena (60 minut) biegnie już wcześniej, bo od pierwszego requestu

                msg = "Po zakończeniu czynności na stronie\n wybierz TAK, aby kontynuować"
                if control.yesnoDialog(msg, heading='Autoryzacja TMDB'):
                    pass
                    # self.dialog_qrcode_close()
                    self.dialog_progress.update(99)
                else:
                    log_utils.fflog('użytkownik zrezygnował z kontynuacji procedury zewnętrznego uwierzytelniania (v3)',1,1)
                    self.dialog_qrcode_close()
                    return
                    pass

                self.dialog_qrcode_close()
                try:
                    # self.dialog_progress_close()
                    pass
                except:
                    pass

            else:
                log_utils.fflog('użytkownik zrezygnował z procedury zewnętrznego uwierzytelniania (v3)',1,1)
                return
                pass
        else:
            log_utils.fflog(f'uwierzytelnie za pomocą nazwy i hasła',1,1)
            url2 = self.auth_base_link + '/token/validate_with_login?api_key=%s' % self.tm_user
            if control.setting('tmdb.username') == '' or control.setting('tmdb.password') == '':
                masg = 'brak albo nazwy użytkownika albo hasła'
                log_utils.fflog(msg,1,1)
                control.infoDialog(msg, 'Autoryzacja v3 TMDB', 'WARNING')
                control.sleep(3000)
                return
                pass
            username = control.setting('tmdb.username')
            password = control.setting('tmdb.password')
            post2 = {"username": "%s" % username,
                     "password": "%s" % password,
                     "request_token": "%s" % token}
            control.sleep(1000)
            result2 = requests.post(url2, data=post2)  # 2-gie polecenie do serwera (wysłanie danych logowania i tokenu z 1 kroku)
            # powyższe nic nie zwraca do wykorzystania, ale pewnie serwer coś u siebie tworzy na podstawie tokenu z 1 kroku
            if not result2:
                log_utils.fflog(f'wystąpił jakiś błąd  {result2=}  {url2=}',1,1)
                control.infoDialog("Wystąpił jakiś błąd", 'Autoryzacja v3 TMDB', 'ERROR')
                return
                pass
            result2 = result2.json()


        url3 = self.auth_base_link + '/session/new?api_key=%s' % self.tm_user
        post3 = {"request_token": "%s" % token}
        control.sleep(1000)
        result3 = requests.post(url3, data=post3)  # 3-cie polecenie do serwera o session_id
        if not result3:
            log_utils.fflog(f'wystąpił jakiś błąd  {result3=}  {url3=}  {post3=}',1,1)
            control.infoDialog("Wystąpił jakiś błąd", 'Autoryzacja v3 TMDB', 'ERROR')
            log_utils.fflog(f'wystąpił jakiś błąd  {result3.status_code=}  {result3.text=}',1,1)
            return
            pass
        result3 = result3.json()

        if result3.get('success') is True:
            # otrzymano identyfikator sesji
            session_id = result3.get('session_id')  # otrzymanie session_id

            # msg = '%s' % ('login =' + username + '[CR]hasło =' + password + '[CR]token = ' + token + '[CR]Zatwierdzasz?')
            # msg = '%s' % ('login =' + username + '[CR]hasło =' + (len(password) * "*") + '[CR]token = ' + token + '[CR]Zatwierdzasz?')
            # msg = '%s' % ('[LIGHT]login:[/LIGHT]  ' + username + '[CR][LIGHT]hasło:[/LIGHT]  ' + (len(password) * "*") + '[CR][CR]Zatwierdzasz ?')
            # msg = "Czy chesz zatwierdzić autoryzacje?"
            msg = "Wsztko w porządku. Czy zapisać autoryzację?"
            if control.yesnoDialog(msg, heading='Autoryzacja TMDB'):
                control.setSetting('tmdb.sessionid', session_id)  # zapisanie identyfikatora sesji w Ustawieniach
                # control.setSetting('tmdb.session_id', session_id)  # zapisanie identyfikatora sesji w Ustawieniach
                log_utils.fflog('zapisano dane autoryzacyjne (v3) w Ustawieniach',1,1)
                # usunięcie danych związanych z v4
                log_utils.fflog('usunięcie danych związanych z v4 z Ustawień',0,1)
                control.setSetting('tmdb.access_token', '')
                control.setSetting('tmdb.account_id', '')

                control.infoDialog("Autoryzacja zapisana", 'Autoryzacja v3 TMDB', 'default')
            else:
                control.infoDialog("Zrezygnowano", 'Autoryzacja v3 TMDB', 'WARNING')

        else:
            control.infoDialog("Wystąpił jakiś błąd", 'Autoryzacja v3 TMDB', 'ERROR')
            log_utils.fflog(f'wystąpił jakiś błąd  {result3=}  {url3=}  {post3=}',1,1)
        # aby odczepić obrazek, bo inaczej będzie się on pojawiał przy każdym okienku typu progress
        try:
            # self.dialog_qrcode_close()  # wcześniej odczepiam
            pass
        except:
            pass



    def revoke_session_id(self):
        """ unieważnienie sesji """
        if control.setting('tmdb.sessionid') == '' and control.setting('tmdb.access_token') == '':  # czyli, gdy nie ma takiej potrzeby
            log_utils.fflog('nie ma takiej potrzeby, bo nie ma w Ustawieniach wartości tmdb.sessionid ani tmdb.access_token',1,1)
            return

        if control.yesnoDialog("Potwierdzasz chęć usunięcia danych autoryzacyjnych z FanVodPL?", heading='Autoryzacja TMDB'):

            # if control.setting("tmdb.version") != '0':
            if access_token := control.setting('tmdb.access_token'):
                # v4
                log_utils.fflog('v4',1,1)
                url = "https://api.themoviedb.org/4/auth/access_token"
                headers = {
                    "accept": "application/json",
                    "content-type": "application/json",
                    "Authorization": f"Bearer {self.bearer}"
                }
                payload = {"access_token": access_token,
                           # "session_id": control.setting('tmdb.sessionid'),  # to nie zadziałało
                }
                response = requests.delete(url, json=payload, headers=headers)
                if not response:
                    pass
                    log_utils.fflog(f'wystąpił jakiś błąd  {response=}  {url=}',1,1)
                    control.infoDialog("Wystąpił błąd", 'Unieważnienie autoryzacji v4 TMDB', 'ERROR')
                else:
                    # log_utils.fflog(f'{response.text=}  {url=}  {payload=}',1,1)
                    response = response.json()
                    if response.get('success') is True:
                        control.setSetting('tmdb.access_token', '')
                        control.setSetting('tmdb.account_id', '')
                        # control.setSetting('tmdb.sessionid', '')  # bo nie wycofuje z serwisu TMDb
                        control.setting = control.addon().getSetting  # odświeżenie cachu Pythona
                        log_utils.fflog(f'wycofano autoryzacje (v4)',1,1)
                        control.infoDialog("Usunięto dane", 'Unieważnienie autoryzacji v4 TMDB', 'default')
                        control.sleep(1000)
                    else:
                        log_utils.fflog(f'wystąpił jakiś błąd  {response=}  {url=}',1,1)
                        control.infoDialog("Wystąpił błąd", 'Unieważnienie autoryzacji v4 TMDB', 'ERROR')
                        pass
                control.sleep(1000)
            else:
                if control.setting("tmdb.version") == '1':  # != '0':
                    msg = 'nie ma takiej potrzeby, bo nie ma w Ustawieniach wartości tmdb.access_token'
                    log_utils.fflog(msg,1,1)
                    control.infoDialog(msg, 'Unieważnienie autoryzacji v4 TMDB', 'WARNING')
                    control.sleep(3000)
                    pass

            # log_utils.fflog(f"{control.setting('tmdb.sessionid')=}",1,1)
            # log_utils.fflog(f"{control.addon().getSetting('tmdb.sessionid')=}",1,1)
            if control.setting("tmdb.version") == '0' or control.setting('tmdb.sessionid'):
            # if control.setting("tmdb.version") == '0':
                # v3
                if control.setting("tmdb.version") == '0':
                    log_utils.fflog('v3',1,1)
                url3 = self.auth_base_link + '/session?api_key=%s' % self.tm_user
                data3 = {"session_id": "%s" % control.setting('tmdb.sessionid')}
                result3 = requests.delete(url3, data=data3)  # żądanie do serwera
                if not result3:
                    log_utils.fflog(f'wystąpił jakiś błąd  {result3=}  {url3=}  {data3=}',1,1)
                    control.infoDialog("Wystąpił błąd", 'Unieważnienie autoryzacji v3 TMDB', 'ERROR')
                    pass
                else:
                    result3 = result3.json()
                    if result3.get('success') is True:
                        # wykasowanie z Ustawień
                        # control.setSetting('tmdb.session_id', '')
                        control.setSetting('tmdb.sessionid', '')
                        control.setSetting('tmdb.access_token', '')
                        control.setSetting('tmdb.account_id', '')
                        # control.setSetting('tmdb.username', '')  # nie wiem, czy też warto
                        # control.setSetting('tmdb.password', '')  # nie wiem, czy też warto
                        log_utils.fflog(f'wycofano autoryzacje (v3)',1,1)
                        control.infoDialog("Usunięto dane", 'Unieważnienie autoryzacji v3 TMDB', 'default')
                    else:
                        control.infoDialog("Wystąpił błąd", 'Unieważnienie autoryzacji v3 TMDB', 'ERROR')
                        log_utils.fflog(f'wystąpił jakiś błąd  {result3=}  {url3=}  {data3=}',1,1)
            else:
                if control.setting("tmdb.version") == '0':
                    msg = 'nie ma takiej potrzeby, bo nie ma w Ustawieniach wartości tmdb.sessionid'
                    log_utils.fflog(msg,1,1)
                    control.infoDialog(msg, 'Unieważnienie autoryzacji v3 TMDB', 'WARNING')
                    control.sleep(3000)
                    pass

        else:
            pass
            log_utils.fflog('Zrezygnowano z procedury unieważnienia autoryzacji TMDB',1,1)



    def dialog_progress_create(self):
        head = 'Autoryzacja TMDB'
        data = 'Możesz użyć wyświetlonego QR kodu'
        self.dialog_progress.create(head, data)
        self.dialog_qrcode_create()

    @cached_property
    def dialog_progress(self):
        from xbmcgui import DialogProgress
        return DialogProgress()

    @cached_property
    def current_window_id(self):
        from xbmcgui import getCurrentWindowDialogId
        return getCurrentWindowDialogId()

    @cached_property
    def dialog_qrcode_window(self):
        try:
            from xbmcgui import Window
            return Window(self.current_window_id)
        except RuntimeError:
            return

    def dialog_qrcode_create(self):
        if not self.current_window_id:
            return
        if not self.dialog_qrcode_image:
            return
        if not self.dialog_qrcode_window:
            return
        try:
            self.dialog_qrcode_window.addControl(self.dialog_qrcode_image)
        except RuntimeError:
            return

    def dialog_progress_close(self):
        self.dialog_qrcode_close()
        self.dialog_progress.close()

    def dialog_qrcode_close(self):
        if not self.current_window_id:
            return
        if not self.dialog_qrcode_image:
            return
        if not self.dialog_qrcode_window:
            return
        # odczepienie obrazka, bo inaczej będzie się on pojawiał przy każdym okienku typu progress
        try:
            self.dialog_qrcode_window.removeControl(self.dialog_qrcode_image)
        except RuntimeError:
            return

    @cached_property
    def dialog_qrcode_image(self):
        if not self.request_token_qrcode:
            return
        try:
            from xbmcgui import ControlImage
            return ControlImage(0, 0, 324, 324, self.request_token_qrcode)
        except RuntimeError:
            return



