@echo off
setlocal
python -m pip install -r requirements-dev.txt
if errorlevel 1 exit /b 1
python -m PyInstaller --clean --noconfirm --onefile --windowed --uac-admin --name BrowserCacheTool --hidden-import win32security --hidden-import win32api --hidden-import pywintypes main.py
if errorlevel 1 exit /b 1
endlocal