标注软件  
最好使用anaconda来配置 
下载之后直接放在Anaconda的Lib\site-packages里面
如果是另开的环境就是anaconda里envs\对应环境\Lib\site-packages    
pyqt4 https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyqt4  
根据自己的py版本来下载wheel 通过pip install 对应的wheel  
更新源  
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple  
必要的库:  
pip install opencv-python json5 simplejson pillow  
打包exe必要的  
pip install pyinstaller  
pip install --upgrade setuptools  
打包exe脚本在bin目录里  
打包前修改pack_sloth_to_exe_script.cmd里的路径    
conda activate 你的环境(默认是base)   
比如 conda activate pyqt4only  
然后执行pack_sloth_to_exe_script.cmd