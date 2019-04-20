# -*- mode: python -*-

block_cipher = None


a = Analysis(['sloth'],
             pathex=['E:\\sloth\\bin'],
             binaries=[('D:\\api-ms-win-downlevel-shlwapi-l1-1-0.dll', '.'),
                       ('D:\\IEShims.dll', '.')],
             datas=[('E:\\sloth\\gui\\labeltool.ui','sloth\\gui\\'),
                    ('E:\\sloth\\gui\\icons.qrc','sloth\\gui\\'),
                    ('E:\\sloth\\gui\\icons\\*','sloth\\gui\\icons\\'),
                    ('E:\\sloth\\conf\\config.json','sloth\\conf\\')],
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
          console=True )
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               name='sloth')
