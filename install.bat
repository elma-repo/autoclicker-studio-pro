@echo off
REM ============================================================
REM  AutoClicker Studio Pro  ·  v1.0.0 "Studio"
REM  Instalador de dependencias
REM ============================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0"

title AutoClicker Studio Pro - Instalacion

echo.
echo  ============================================================
echo    AutoClicker Studio Pro   v1.0.0 "Studio"
echo    Instalacion de dependencias
echo  ============================================================
echo.

REM --- 1. Comprobar que Python esta disponible --------------------
where python >nul 2>nul
if errorlevel 1 (
    echo  [ERROR] No se encontro Python en el PATH.
    echo.
    echo  Instala Python 3.10 o superior desde:
    echo     https://www.python.org/downloads/
    echo.
    echo  IMPORTANTE: al instalar, marca la casilla
    echo     "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

REM --- 2. Mostrar version de Python ------------------------------
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo  Python detectado: !PYVER!

REM --- 3. Comprobar que pip esta disponible ----------------------
python -m pip --version >nul 2>nul
if errorlevel 1 (
    echo.
    echo  [ERROR] pip no esta disponible. Intentando instalarlo...
    python -m ensurepip --upgrade
    if errorlevel 1 (
        echo.
        echo  [ERROR] No se pudo instalar pip. Revisa tu instalacion de Python.
        pause
        exit /b 1
    )
)

REM --- 4. Comprobar que requirements.txt existe ------------------
if not exist "requirements.txt" (
    echo.
    echo  [ERROR] No se encontro requirements.txt en esta carpeta.
    echo  Ejecuta este instalador desde la raiz del proyecto.
    echo.
    pause
    exit /b 1
)

REM --- 5. Actualizar pip ----------------------------------------
echo.
echo  Actualizando pip...
python -m pip install --upgrade pip
if errorlevel 1 (
    echo  [AVISO] No se pudo actualizar pip. Se continua con la version actual.
)

REM --- 6. Instalar dependencias ---------------------------------
echo.
echo  ============================================================
echo    Instalando dependencias de requirements.txt
echo  ============================================================
echo.
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo  [ERROR] Fallo la instalacion de dependencias.
    echo  Revisa los mensajes anteriores para mas detalle.
    echo.
    pause
    exit /b 1
)

REM --- 7. Comprobar que los imports basicos funcionan -----------
echo.
echo  Verificando imports principales...
python -c "import customtkinter, PIL, pynput, pystray, pyautogui, win32gui, cv2" 2>nul
if errorlevel 1 (
    echo  [AVISO] Algunos modulos no se pudieron importar.
    echo  La instalacion termino, pero revisa los errores de arriba.
) else (
    echo  Todos los modulos principales estan disponibles.
)

REM --- 8. Listo ------------------------------------------------
echo.
echo  ============================================================
echo    AutoClicker Studio Pro   v1.0.0 "Studio"
echo    Instalacion completada
echo  ============================================================
echo.
echo  Para ejecutar la aplicacion tienes dos opciones:
echo.
echo    1) Directamente con Python:
echo         python main.py
echo.
echo    2) Con el lanzador ligero (consola oculta + permisos de admin):
echo         build_launcher.bat   ^<- compila AutoClicker_Studio.exe
echo         AutoClicker_Studio.exe
echo.
echo  Recuerda: para simular clics sobre ventanas elevadas
echo  es recomendable ejecutar como administrador.
echo.
pause
endlocal