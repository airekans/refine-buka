@echo off
echo Building...
C:\Python33\Scripts\cxfreeze --target-dir=dist -OO --zip-include=dwebp.exe --icon=buka.ico buka.py
echo.
echo Done.
pause