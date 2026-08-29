@echo off
REM Arranca Futbol Analytics en Windows. Doble clic sobre este fichero.
REM La primera vez crea el entorno virtual e instala las dependencias (unos minutos);
REM las siguientes arranca directamente.

cd /d "%~dp0"

if not exist ".venv" (
    echo Creando el entorno virtual...
    python -m venv .venv || goto :error
    echo Instalando dependencias, esto tarda unos minutos...
    call .venv\Scripts\python.exe -m pip install --upgrade pip || goto :error
    call .venv\Scripts\python.exe -m pip install -r requirements.txt || goto :error
    call .venv\Scripts\python.exe -m pip install --no-deps -e . || goto :error
)

echo Arrancando la app; se abrira en el navegador...
call .venv\Scripts\python.exe -m streamlit run streamlit_app.py
goto :eof

:error
echo.
echo Algo fallo. Comprueba que Python 3.11 o superior esta instalado
echo y accesible desde la linea de comandos ("python --version").
pause
