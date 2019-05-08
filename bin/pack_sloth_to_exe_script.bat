set anaconda_sloth="D:\Anaconda3\Lib\site-packages\sloth"
::set destination="D:\sloth_test"
if exist %anaconda_sloth%\bin\build (
  rmdir /S /Q %anaconda_sloth%\bin\build
)
if exist %anaconda_sloth%\bin\dist (
  rmdir /S /Q %anaconda_sloth%\bin\dist
)
set destination="D:\sloth_test"
pyinstaller sloth.spec
rmdir /S /Q build
if not exist %destination% (
  mkdir %destination%
)
if not exist %destination%\sloth (
  mkdir %destination%\sloth
)
xcopy /S /E /Y dist\sloth\. %destination%\sloth
rmdir /S /Q dist
7z a %destination%\sloth.7z %destination%\sloth
explorer %destination%
