import os
import shutil

for d in ('build', 'dist'):
    if os.path.exists(d) and os.path.isdir(d):
        shutil.rmtree(d)

os.system('pyinstaller --clean --onefile --icon=sei_icon-32x32.ico wave_integration.py')

if os.path.exists('dist') and os.path.isdir('dist'):
    os.system('copy config.yml dist')
    os.system('copy scenarios.yml dist')
    os.system('xcopy data dist\\data\\ /E')
    os.system('xcopy locale dist\\locale\\ /E')
