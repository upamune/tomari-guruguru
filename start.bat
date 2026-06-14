@echo off
setlocal

pushd "%~dp0"
if errorlevel 1 (
  echo Failed to open the app folder.
  pause
  exit /b 1
)

rem Default page: Tomari Talk
set "PAGE=%%E3%%83%%88%%E3%%83%%9E%%E3%%83%%AA%%E3%%83%%88%%E3%%83%%BC%%E3%%82%%AF.html"

set "PYTHON_CMD=python"
python --version >nul 2>nul
if errorlevel 1 (
  set "PYTHON_CMD=py -3"
  py -3 --version >nul 2>nul
  if errorlevel 1 (
    echo Python 3 was not found.
    echo Please install Python 3, then run this file again.
    pause
    exit /b 1
  )
)

set "PORT=8000"
for /f %%P in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "$l=[Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,0);$l.Start();$p=$l.LocalEndpoint.Port;$l.Stop();$p" 2^>nul') do set "PORT=%%P"

set "URL=http://127.0.0.1:%PORT%/%PAGE%"

echo Starting Tomari local server...
echo Close the server window to stop the app.
echo %URL%

start "Tomari local server" /D "%~dp0" cmd /k "%PYTHON_CMD% -m http.server %PORT% --bind 127.0.0.1"
timeout /t 2 /nobreak >nul
start "" "%URL%"

popd
endlocal
