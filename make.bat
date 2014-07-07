@echo off
echo Building...
start C:\Python33\Scripts\cxfreeze --target-dir=dist -OO png2jpg.py
C:\Python33\Scripts\cxfreeze --target-dir=dist -OO --icon=buka.ico buka.py
echo.
echo Done.
pause
