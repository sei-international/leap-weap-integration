import re
import os #os.path, os.system
from winreg import *

# function that retrieve path where julia is installed
def get_julia_path(shell):
    juliapath = None
    
    # First check the PATH environment variable
    r = re.compile('julia', re.IGNORECASE)
    path_array = os.environ['PATH'].split(';')
    for p in path_array:
        if r.search(p) is not None:
            juliapath = os.path.join(p, 'julia.exe')
            break
    
	# Then check in C:\USER\AppData\Local\Programs
    if juliapath is None:
        for p in os.scandir(os.path.join(os.environ['localappdata'],'Programs')):
            if p.is_dir() and r.search(p.name) is not None:
                juliapath = os.path.join(p.path, 'bin', 'julia.exe')
                break

    # Then check registry
    hklm = ConnectRegistry(None, HKEY_LOCAL_MACHINE)
    hkcu = ConnectRegistry(None, HKEY_CURRENT_USER)
    common_prefix = r"SOFTWARE"
    common_path = r"Microsoft\Windows\CurrentVersion\Uninstall"
    # NEMO key
    if juliapath is None:
        try:
            key = OpenKey(hklm, os.path.join(common_prefix, common_path, '{4EEC991C-8D33-4773-84D3-7FE4162EEF82}'))
            juliapath = QueryValueEx(key, 'JuliaPath')[0]
        except:
            pass
    # Julia keys
    if juliapath is None:
        # HKEY_LOCAL_MACHINE
        try:
            key = OpenKey(hklm, os.path.join(common_prefix, common_path, 'Julia-1.7.2_is1'))
            juliapath = QueryValueEx(key, 'DisplayIcon')[0]
        except:
            pass
    if juliapath is None:
        try:
            key = OpenKey(hklm, os.path.join(common_prefix, common_path, '{054B4BC6-BD30-45C8-A623-8F5BA6EBD55D}_is1'))
            juliapath = QueryValueEx(key, 'DisplayIcon')[0]
        except:
            pass
    if juliapath is None:
        try:
            key = OpenKey(hklm, os.path.join(common_prefix, 'WOW6432Node', common_path, 'Julia-1.7.2_is1'))
            juliapath = QueryValueEx(key, 'DisplayIcon')[0]
        except:
            pass
    if juliapath is None:
        try:
            key = OpenKey(hklm, os.path.join(common_prefix, 'WOW6432Node', common_path, '{054B4BC6-BD30-45C8-A623-8F5BA6EBD55D}_is1'))
            juliapath = QueryValueEx(key, 'DisplayIcon')[0]
        except:
            pass
        # HKEY_CURRENT_USER
    if juliapath is None:
        try:
            key = OpenKey(hkcu, os.path.join(common_prefix, common_path, 'Julia-1.7.2_is1'))
            juliapath = QueryValueEx(key, 'DisplayIcon')[0]
        except:
            pass
    if juliapath is None:
        try:
            key = OpenKey(hkcu, os.path.join(common_prefix, common_path, '{054B4BC6-BD30-45C8-A623-8F5BA6EBD55D}_is1'))
            juliapath = QueryValueEx(key, 'DisplayIcon')[0]
        except:
            pass
    if juliapath is None:
        try:
            key = OpenKey(hkcu, os.path.join(common_prefix, 'WOW6432Node', common_path, 'Julia-1.7.2_is1'))
            juliapath = QueryValueEx(key, 'DisplayIcon')[0]
        except:
            pass
    if juliapath is None:
        try:
            key = OpenKey(hkcu, os.path.join(common_prefix, 'WOW6432Node', common_path, '{054B4BC6-BD30-45C8-A623-8F5BA6EBD55D}_is1'))
            juliapath = QueryValueEx(key, 'DisplayIcon')[0]
        except:
            pass        
    return juliapath
