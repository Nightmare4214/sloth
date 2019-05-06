set sloth="E:\sloth"
set anaconda_sloth="D:\Anaconda3\Lib\site-packages\sloth"
set destination="E:\sloth_test"

if exist %sloth%\bin\build (
  rmdir /S /Q  %sloth%\bin\build
)
if exist %sloth%\bin\dist (
  rmdir /S /Q %sloth%\bin\dist
)

xcopy %sloth%\. %anaconda_sloth% /S /E /Y
rmdir /S /Q  %anaconda_sloth%\.idea
rmdir /S /Q  %anaconda_sloth%\__pycache__
rmdir /S /Q  %anaconda_sloth%\bin
rmdir /S /Q  %anaconda_sloth%\gui\__pycache__
rmdir /S /Q  %anaconda_sloth%\gui\icons
del %anaconda_sloth%\gui\icons.qrc
del %anaconda_sloth%\gui\labeltool.ui
cd %sloth%\bin
pyinstaller sloth.spec
rmdir /S /Q build
if not exist %destination%\sloth (
  mkdir %destination%\sloth
)
xcopy dist\sloth\. %destination%\sloth /S /E /Y
rmdir /S /Q dist
cd %destination%
7z a sloth.7z sloth