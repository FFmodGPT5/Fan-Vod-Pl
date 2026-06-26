Pliki:
- aktualizacja_repo_z_zipow_v2.bat
- aktualizacja_repo_z_zipow_v2.ps1

Jak uruchomic:
1. Wrzuc oba pliki do glownego folderu repo.
2. W tym samym folderze musi byc katalog Zips.
3. Uruchom BAT.

Co robi:
- bierze tylko najnowszy ZIP z kazdego folderu dodatku w Zips,
- nie korzysta z rozpakowanego folderu roboczego jako bazy,
- podbija tylko wersje w addon.xml,
- tworzy nowy ZIP,
- liczy ZIP.md5,
- regeneruje addons.xml i addons.xml.md5.
