@echo off
echo Building...
C:\Python34\python.exe C:\Python34\Scripts\cxfreeze --target-dir=dist -OO --icon=buka.ico buka.py
C:\Python34\python.exe C:\Python34\Scripts\cxfreeze --target-dir=dist -OO png2jpg.py
copy dwebp_32.exe dist/dwebp_32.exe
copy dwebp_64.exe dist/dwebp_64.exe
echo.
echo Done.
pause
