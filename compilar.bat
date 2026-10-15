@echo off
rem Genera dist\Munay Cotizador.exe a partir de app.py y la carpeta ui
cd /d "%~dp0"
if not exist .venv (
  "%USERPROFILE%\anaconda3\python.exe" -m venv .venv
  .venv\Scripts\python.exe -m pip install pywebview pyinstaller
)
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name "Munay Cotizador" --icon icono.ico --add-data "ui;ui" app.py
echo.
echo Listo: dist\Munay Cotizador.exe
