::修改为你的anaconda下的sloth的位置
set anaconda_sloth="D:\Anaconda3\Lib\site-packages\sloth"
if exist %anaconda_sloth%\bin\build (
  rmdir /S /Q %anaconda_sloth%\bin\build
)
if exist %anaconda_sloth%\bin\dist (
  rmdir /S /Q %anaconda_sloth%\bin\dist
)
::修改为最后压缩的位置
set destination="E:\sloth_test"
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
::请保证7z加入了环境变量
7z a %destination%\sloth.7z %destination%\sloth
explorer %destination%
