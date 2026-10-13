@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo  ============================================================
echo    AutoClicker Studio Pro   v1.0.0 "Studio"
echo    Compilando AutoClicker_Studio.exe
echo  ============================================================
echo.

rem --- Comprobaciones previas ------------------------------------
if not exist "launcher\Launcher.cs" (
    echo  [ERROR] No se encontro launcher\Launcher.cs
    echo  Ejecuta este .bat desde la raiz del proyecto.
    pause
    exit /b 1
)
if not exist "launcher\launcher.manifest" (
    echo  [ERROR] No se encontro launcher\launcher.manifest
    pause
    exit /b 1
)

rem --- Localizar csc.exe (.NET Framework 4) ----------------------
set "CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if not exist "%CSC%" set "CSC=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe"
if not exist "%CSC%" (
    echo  [ERROR] No se encontro csc.exe ^(.NET Framework 4^).
    echo  Instala .NET Framework 4 o superior desde:
    echo     https://dotnet.microsoft.com/download/dotnet-framework
    pause
    exit /b 1
)

rem --- Icono (opcional) ------------------------------------------
set "ICON="
if exist "assets\app\app_icon.ico" set "ICON=/win32icon:assets\app\app_icon.ico"

rem --- Limpiar el .exe anterior ----------------------------------
if exist "AutoClicker_Studio.exe" del /q "AutoClicker_Studio.exe"

rem --- Compilar --------------------------------------------------
"%CSC%" /nologo /target:winexe /optimize+ /codepage:65001 ^
    /out:AutoClicker_Studio.exe ^
    /win32manifest:launcher\launcher.manifest %ICON% ^
    /reference:System.Windows.Forms.dll ^
    launcher\Launcher.cs

if errorlevel 1 (
    echo.
    echo  Fallo la compilacion.
    pause
    exit /b 1
)

if not exist "AutoClicker_Studio.exe" (
    echo.
    echo  [ERROR] El compilador no genero AutoClicker_Studio.exe.
    pause
    exit /b 1
)

echo.
echo  ============================================================
echo    Listo: AutoClicker_Studio.exe  ^(en esta carpeta^)
echo  ============================================================
for %%F in (AutoClicker_Studio.exe) do echo  Tamano: %%~zF bytes
echo.
echo  Este .exe inicia AutoClicker Studio Pro con:
echo    - Permisos de administrador ^(UAC^)
echo    - Consola oculta ^(salida en autoclicker.log^)
echo.
echo  Distribuye solo el .exe, NO el .pdb ni el .cs.
echo.
pause