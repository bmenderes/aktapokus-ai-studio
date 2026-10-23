@echo off
setlocal enableextensions
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo === Aktapokus kurulum ===
echo Bu betik: Python ve git'i kontrol eder, bu klasorde sanal ortam kurar, kurulumu dener.
echo Yonetici izni gerekmez. Baska hicbir yere dosya yazmaz ^(yalnizca bu klasore^).
echo.

set "PYCMD="
py -3 -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul
if not errorlevel 1 set "PYCMD=py -3"
if defined PYCMD goto :python_tamam
python -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul
if not errorlevel 1 set "PYCMD=python"
if defined PYCMD goto :python_tamam
echo [HATA] Python 3.10 veya ustu bulunamadi.
echo   Kurmak icin: https://www.python.org/downloads/
echo   Kurarken "Add python.exe to PATH" kutusunu isaretleyin, sonra bu dosyayi tekrar calistirin.
goto :bitir_hata
:python_tamam
echo [tamam] Python bulundu: %PYCMD%

git --version >nul 2>nul
if not errorlevel 1 goto :git_tamam
echo [HATA] git bulunamadi. Geri alma ozelligi git'e dayanir.
echo   Kurmak icin: https://git-scm.com/download/win
echo   Kurduktan sonra bu dosyayi tekrar calistirin.
goto :bitir_hata
:git_tamam
echo [tamam] git bulundu.

if exist ".venv\Scripts\python.exe" goto :venv_tamam
echo Sanal ortam olusturuluyor ^(.venv^)...
%PYCMD% -m venv .venv
if not errorlevel 1 goto :venv_tamam
echo [HATA] Sanal ortam olusturulamadi.
goto :bitir_hata
:venv_tamam
echo [tamam] Sanal ortam hazir: %~dp0.venv

set "CEVAP=H"
if defined AKTAPOKUS_KUR_SESSIZ (
  if defined AKTAPOKUS_KUR_QR set "CEVAP=%AKTAPOKUS_KUR_QR%"
) else (
  set /p CEVAP="Telegram eslestirmesi icin QR kod destegi kurulsun mu? ^(segno paketi, internetten indirilir^) [E/H]: "
)
if /i not "%CEVAP%"=="E" goto :qr_atla
echo segno kuruluyor...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --quiet segno
if errorlevel 1 echo [UYARI] segno kurulamadi; QR olmadan da calisir ^(baglanti yazdirilir^).
if not errorlevel 1 echo [tamam] QR kod destegi kuruldu.
goto :qr_bitti
:qr_atla
echo QR kod destegi atlandi ^(isteginize bagli; baglanti yine yazdirilir^).
:qr_bitti

echo.
echo --- Kurulum denetimi ---
".venv\Scripts\python.exe" -m aktapokus_ajan durum --arac
if errorlevel 1 goto :denetim_hata

echo.
echo === Kurulum tamam. Siradaki adimlar ===
echo 1^) OpenCode kurulu olmali ^(https://opencode.ai^) ve bir model ayarli olmali. Yukarida "OpenCode CLI: bulunamadi" yaziyorsa once onu kurun.
echo 2^) Telegram icin: BotFather'dan BU bilgisayara ozel yeni bir bot olusturun; token'i
echo    %USERPROFILE%\.aktapokus\telegram.token dosyasina tek satir olarak yazin ^(token'i kimseyle paylasmayin^).
echo    Ayni token iki bilgisayarda ayni anda calismaz; her bilgisayar icin ayri bot acin.
echo 3^) Proje klasorlerinizi bir kez tanitin ve botu baslatin:
echo    telegram-baslat.bat --kok C:\yol\projeler
echo 4^) Telefondan botunuza gelen baglantiyi acin ^(eslestirme^), sonra /projeler yazin.
echo Canli arayuz icin: arayuz-baslat.bat
echo Masaustu uygulamasi (kendi penceresi, kisayol) icin: kisayol-olustur.bat
echo.
if not defined AKTAPOKUS_KUR_SESSIZ pause
exit /b 0

:denetim_hata
echo [HATA] Kurulum denetimi basarisiz oldu; yukaridaki ciktiya bakin.
:bitir_hata
echo.
if not defined AKTAPOKUS_KUR_SESSIZ pause
exit /b 1
