# -*- mode: python -*-
# _*_ coding:utf-8 _*_
import os
block_cipher = None

anaconda_sloth=os.path.abspath('..')
a = Analysis(['sloth'],
             pathex=[os.path.join(anaconda_sloth,'bin')],
             binaries=[(os.path.join(anaconda_sloth,'api-ms-win-downlevel-shlwapi-l1-1-0.dll'), '.'),
                       (os.path.join(anaconda_sloth,'IEShims.dll'), '.')],
             datas=[(os.path.join(anaconda_sloth,r'gui\labeltool.ui'),'sloth\\gui\\'),
                    (os.path.join(anaconda_sloth,r'gui\icons.qrc'),'sloth\\gui\\'),
                    (os.path.join(anaconda_sloth,r'gui\icons\*'),'sloth\\gui\\icons\\'),
                    (os.path.join(anaconda_sloth,r'conf\config.json'),'sloth\\conf\\')],
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=['PyQt5'],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          [],
          exclude_binaries=True,
          name='sloth',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=False )
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               name='sloth')
