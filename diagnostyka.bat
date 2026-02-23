@echo off
title GPW Analyst V2 - Diagnostyka Sieci
echo ========================================
echo   DIAGNOSTYKA POLACZENIA MOBILNEGO
echo ========================================
echo.
echo KROK 1: Odblokowywanie portu 5173 w Zaporze Windows...
echo (Moze wyskoczyc okienko z prosba o dostep administratora)
echo.
powershell -Command "Start-Process cmd -ArgumentList '/c netsh advfirewall firewall add rule name=\"AppGPW_V2_Port_5173\" dir=in action=allow protocol=TCP localport=5173' -Verb RunAs"

echo.
echo KROK 2: Szukanie Twojego adresu Wi-Fi...
echo ----------------------------------------
ipconfig | findstr /R /C:"IPv4 Address" /C:"Wireless LAN adapter" /C:"Wi-Fi"
echo ----------------------------------------
echo.
echo INSTRUKCJA:
echo 1. Znajdz powyzej sekcje "Wireless LAN adapter Wi-Fi".
echo 2. Spisz numer IPv4 (zazwyczaj 192.168.x.x).
echo 3. Na telefonie wpisz: http://TEN_NUMER:5173
echo.
echo UWAGA: Jesli nadal nie dziala, a masz wlaczony PROFIL PRYWATNY, 
echo to Twoj router moze blokowac polaczenia miedzy urzadzeniami.
echo.
pause
