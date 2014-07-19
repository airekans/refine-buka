@echo off
echo Building...
C:\Python33\python.exe C:\Python33\Scripts\cxfreeze --target-dir=dist -OO --exclude-modules=PIL,PIL.Image,Image --icon=buka.ico buka.py
C:\Python33\python.exe C:\Python33\Scripts\cxfreeze --target-dir=dist -OO png2jpg.py
echo.
echo Done.
pause
