@echo off
REM Load QGIS/OSGeo4W GDAL+Python env, then run the passed command.
REM Auto-pick the highest-versioned QGIS under "C:\Program Files" that has bin\o4w_env.bat.
set "QGISROOT="
for /f "delims=" %%D in ('dir /b /ad /o-n "C:\Program Files\QGIS *" 2^>nul') do (
  if not defined QGISROOT if exist "C:\Program Files\%%D\bin\o4w_env.bat" set "QGISROOT=C:\Program Files\%%D"
)
if not defined QGISROOT (
  echo [env.bat] No QGIS install with bin\o4w_env.bat found. Please install QGIS 3.x. 1>&2
  exit /b 1
)
call "%QGISROOT%\bin\o4w_env.bat" >nul 2>&1
%*
