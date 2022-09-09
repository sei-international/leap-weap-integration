
# installed packages: os, pywin32, pywingui, Tkinter, tkMessageBox, winreg, calendar, time, yaml, psutil, numpy, calendar
# ultimate environment will need to contain these

from ntpath import altsep
import win32com.client as win32
import win32gui
from tkinter import Tk, Label, Button, Radiobutton, IntVar
from tkinter import messagebox as tkmessagebox
import yaml
import time
from winreg import *
from calendar import monthrange
import os #os.path, os.system
import csv
import psutil
import numpy
import re

#in julia: using LEAPMacro
#using YAML
#using ArgParse need to be installed)
#==================================================================================================#
# Script for integrating WAVE WEAP and LEAP models.
#
# Copyright © 2022: Stockholm Environment Institute U.S.
#==================================================================================================#
tst= time.time()
# List of functions to be defined
# function that enumerates windows
def windowEnumerationHandler(hwnd, top_windows):
    top_windows.append((hwnd, win32gui.GetWindowText(hwnd)))

def get_list_separator():
    aReg = ConnectRegistry(None, HKEY_CURRENT_USER)
    aKey = OpenKey(aReg, r"Control Panel\International")
    val = QueryValueEx(aKey, "sList")[0]
    return val

# function that brings leap to front
def BringToFront(app_name, shell):
    top_windows = []
    win32gui.EnumWindows(windowEnumerationHandler, top_windows)
    for i in top_windows:
        if app_name in i[1]: # needs to be kept up to date, but is not version sensitive
            shell.AppActivate(i[1])
            break

# function that sleeps sleep_app while wait_app.ProgramStarted <> true. wait_app and sleep_app should be LEAP/WEAP application objects.
def wait_apps(wait_app, sleep_app):
    while not wait_app.ProgramStarted:
        sleep_app.Sleep(1000)

# Message box that asks multiple choice question
def ask_multiple_choice_question(prompt, options):
    root = Tk()
    if prompt:
        Label(root, text=prompt).pack()
    v = IntVar()
    for i, option in enumerate(options):
        Radiobutton(root, text=option, variable=v, value=i).pack(anchor="w")
    Button(text="Submit", command=root.destroy).pack()
    root.mainloop()
    if v.get() == 0: return None
    return options[v.get()]

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

# function that checks branch-variable-unit combination exists in app (WEAP or LEAP)
def check_branch_var(app, branch_path, variable, unit) :
    check_passed = False
    app_name = repr(app)[11:15]
    if app_name == 'LEAP' :
        if app.Branches.Exists(branch_path) :
            if app.Branches(branch_path).VariableExists(variable) :
                if app.Branches(branch_path).Variable(variable).DataUnitText == unit :
                    check_passed = True
    if app_name == 'WEAP' :
        if app.BranchExists(branch_path) :
            if app.Branch(branch_path).VariableExists(variable) :
                if app.Branch(branch_path).Variable(variable).ScaleUnit == unit :
                    check_passed = True
    if not check_passed :
        msg= [" The active ", app_name, " area does not contain the required variable ", branch_path ,":" ,variable," with unit " , unit, ". Please check the area and try again. Exiting..."]
        tkmessagebox.showerror("WAVE integration", " ".join(msg))
        exit()

# function that hecks whether region (this argument should be a region name) exists in the active LEAP area. If it does, enables calculations for region.
def check_region(leap, region) :
    check_passed = False
    if leap.Regions.Exists(region) :
        leap.Regions(region).ResultsShown = True
        check_passed = True
    if not check_passed :
        msg = [ "WAVE integration", "Could not enable calculations for region " , region , " in the active LEAP area. Please check the area and try again. Exiting..."]
        tkmessagebox.showerror("WAVE integration", " ".join(msg))

# function that disables all scenarios in current area in app (which should be a LEAP or WEAP application object).
def disable_all_scenario_calcs(app):
    for s in app.Scenarios :
        s.ResultsShown = False

# function that returns an array of years calculated in LEAP.
def get_leap_calc_years(app) :
    leap_calculated_years=[]
    last_index = -1
    for y in range(app.FirstScenarioYear, app.EndYear+1) :
        if y%app.resultsEvery == 0:
            leap_calculated_years.append(y)
            last_index += 1
    return leap_calculated_years

# Splits the Interp expression exp into two parts: before startyear and after endyear (years from startyear to endyear are omitted). Returns an array with the two parts. listseparator is the currently active Windows list separator character (e.g., ",").
def split_interp_ex(exp, startyear, endyear, listseparator):
    return_val=[]
    return_val.append("Interp(")
    return_val.append("")
    interp_termination = exp[-(len(exp) - exp.find(")") ):len(exp)]  # Closing ) and any subsequent content in Interp expression
    exp=exp.lower().replace("interp(", "")
    exp=exp[0:exp.find(")")]
    exp_split = exp.split(listseparator)
    for i in range(0, len(exp_split),2):
        if i==len(exp_split)-1:
            # exp_split[i] is final, optional growth rate parameter for Interp
            return_val[1] = "".join([return_val[1], exp_split[-1].strip()])
            break
        if int(exp_split[i].strip())<startyear :
            return_val[0] = "".join([return_val[0], exp_split[i].strip(), listseparator, exp_split[i+1].strip(), listseparator])
        if int(exp_split[i].strip())>endyear :
            return_val[1] = "".join([return_val[1], exp_split[i].strip(), listseparator, exp_split[i+1].strip(), listseparator])
    # Trim extra list separators
    if return_val[0][-1]==listseparator: return_val[0]=return_val[0][0:-1]
    if len(return_val[1])>0:
        if return_val[1][-1]==listseparator:
            return_val[1]=return_val[1][0:-1]
            return_val[1] = "".join([return_val[1], interp_termination])
        else:
            return_val[1] = "".join([return_val[1], interp_termination])
    else:
        return_val[1] = "".join([return_val[1], interp_termination])
    return return_val

# function that inserts LEAP data from leap_branch, leap_variable, and leap_region into the WEAP Interp expression for weap_branch and weap_variable. weap and leap are WEAP and LEAP application objects, respectively; weap_scenarios and leap_scenarios are arrays of the names of the WEAP and LEAP scenarios being calculated. The procedure assumes that the units of the LEAP and WEAP variables are compatible if LEAP values are multiplied by data_multiplier. listseparator is the currently active Windows list separator character (e.g., ",").
def add_leap_data_to_weap_interp(weap, leap, weap_scenarios, leap_scenarios, weap_branch, weap_variable, leap_branch, leap_variable, leap_region, data_multiplier, listseparator, procedure_title):
    # This procedure doesn't validate branches, variables, and regions. This is assumed to happen via check_branch_var() and check_region() before the procedure is called.
    # Add Current Accounts to local copies of weap_scenarios and leap_scenarios.
    # Scenarios in weap_scenarios and leap_scenarios should exclude Current Accounts; add it here to ensure Current Accounts values are transcribed to WEAP
    leap_scenarios_local=leap_scenarios.copy()
    weap_scenarios_local=weap_scenarios.copy()
    leap_scenarios_local.append('Current Accounts')
    weap_scenarios_local.append('Current Accounts')
    # Loop over scenarios and add LEAP data to WEAP expressions.
    for i in range(0, len(leap_scenarios_local)):
        print('Current scenario:', leap_scenarios_local[i])
        weap.ActiveScenario = weap_scenarios_local[i]
        print(weap.Branches(weap_branch).Variables(weap_variable).Name)
        weap_expression = weap.Branches(weap_branch).Variables(weap_variable).Expression # ' Target expression in WEAP; must be an Interp expression
        print(weap_expression)
        if not weap_expression[0:6]=='Interp':
            msg = ["Cannot update the expression for ", weap_branch , ":" , weap_variable , " with data from LEAP. The expression must be an Interp() expression. Exiting..."]
            tkmessagebox.showerror(procedure_title,msg)
            exit()
        startyear = leap.baseyear # Starting year for LEAP data transcribed to WEAP
        endyear = leap.endyear # Ending year for LEAP data transcribed to WEAP
        split_weap_expression = split_interp_ex(weap_expression, startyear, endyear, listseparator)
        new_data = "" #New data to be inserted into target WEAP expression
        for y in range(startyear, endyear+1):
            new_data="".join([new_data, str(y), listseparator, str(leap.Branches(leap_branch).Variables(leap_variable).ValueRS(leap.regions(leap_region).id, leap_scenarios_local[i], y) * data_multiplier), listseparator])
        new_weap_expression = split_weap_expression[0]
        if new_weap_expression[-1]=="(":
            new_weap_expression = "".join([new_weap_expression, new_data])
        else:
            new_weap_expression = "".join([new_weap_expression, listseparator, new_data])
        if split_weap_expression[1][0]==")":
            new_weap_expression = "".join([new_weap_expression[0:-1], split_weap_expression[1]])
        else:
            new_weap_expression = "".join([new_weap_expression, split_weap_expression[1]])
        weap.Branches(weap_branch).Variables(weap_variable).Expression = new_weap_expression
        print('Updated expression: ', weap.Branches(weap_branch).Variables(weap_variable).Expression)

# function that returns the month number associated with the month named month_name.
def get_month_num(month_name, procedure_title):
    months_in_year = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
    if month_name in months_in_year:
        month_num= months_in_year.index(month_name)+1
    else:
        msg= ["Unrecognized month (", month_name, ") in month_num function. Exiting..."]
        tkmessagebox.showerror(procedure_title, "".join(msg))
    return month_num
    
# function to clear out any running instances of Excel (no return value)
def kill_excel():
    ps_re = re.compile(r'excel', flags=re.IGNORECASE)
    for proc in psutil.process_iter():
        if ps_re.search(proc.name()) is not None:
            proc.kill()

# function that returns an array whose length is length argument; allows creating an array based on an expression for the length.
#==================================================================================================#
#                                         MAIN ROUTINE                                             #
#==================================================================================================#
def main_integration(user_interface, tolerance, max_iterations): # add tolerance, max_iterations as inputs
# takes binary value for leap macro and whether user interface including message boxes is required

    # load user configured parameters
    with open(r'config.yml') as file:
        config_params = yaml.full_load(file)

    with open(r'scenarios.yml') as file:
        scenarios = yaml.full_load(file)

    # Ensure both LEAP and WEAP are open
    leap = win32.Dispatch('LEAP.LEAPApplication') # will open Freedonia
    runfrom_app = "LEAP"
    leap.Visible = True
    weap = win32.Dispatch('WEAP.WEAPApplication') # will open last area
    weap.Visible = True
    other_app = "WEAP"
    wait_apps(weap, leap)

    if not leap or not weap:
        print("WAVE integration", "Cannot start LEAP and WEAP. Exiting...")
        exit()
        
    leap.Verbose = 1

    if runfrom_app == "LEAP" :
        runfrom_app_obj = leap
        other_app_obj = weap
    elif runfrom_app == "WEAP" :
        runfrom_app_obj = weap
        other_app_obj = leap


    # Bring LEAP to front to enable showing progress bar to increase chances of showing progress bar
    shell = win32.Dispatch("WScript.Shell")
    shell.AppActivate("LEAP: ")

    # Initiate parameters
    completed_iterations = 0
    results_converged = False
    lang = None
    leap_macro=False
    if 'LEAP-Macro' in config_params.keys():
        leap_macro=True

    # Set run time language
    if user_interface :
        lines=["Would you like Russian language prompts? / Хотите подсказки на русском языке?", "Select Language / Выберите язык"]
        msg="\n".join(lines)
        result = ask_multiple_choice_question(
            msg,
            [
                "English/Английский язык",
                "Russian/Русский"
            ]
        )
        if result == 'Russian/Русский' :
            lang = "RUS"

    if lang == "RUS" :
        procedure_title = "Процедура интеграции WEAP-LEAP"
        msg = "Инициирование процедуры интеграции."
    else :
        procedure_title = "WEAP-LEAP Integration Procedure"
        msg = "Initiating integration procedure."

    shell.AppActivate("LEAP: ")
    leap.ShowProgressBar(procedure_title, msg)

    # get Julia install location path
    if leap_macro:
        juliapath=get_julia_path(shell)
        if juliapath==None:
            msg="Could not locate the Julia executable. Try adding the path to the executable to the Windows environment variable named 'Path'."
            leap.ShowProgressBar(procedure_title, msg)
            exit()

    # open correct leap and weap areas
    if  user_interface :
        root=Tk()
        root.withdraw()
        if lang == "RUS" :
            msg = "Пожалуйста, откройте модель WAVE (область) в WEAP."
            title = "Открытая область WEAP"
        else :
            title = "Open WEAP Area"
            msg = "Please open the WAVE model (area) in WEAP."
        messagebox=tkmessagebox.askokcancel(title, msg)
        if messagebox != True :
            exit()
        else :
            wait_apps(weap,leap)
        if lang == "RUS" :
            msg = "Пожалуйста, откройте модель WAVE (область) в LEAP."
            title = "Открытая область LEAP"
        else :
            title = "Open LEAP Area"
            msg = "Please open the WAVE model (area) in LEAP."
        messagebox=tkmessagebox.askokcancel(title, msg)
        if messagebox != True :
            exit()
        else :
            wait_apps(leap, weap)
    else :
        weap.ActiveArea = config_params['WEAP']['Area'] # needs to be  put in a yaml file
        wait_apps(weap, leap)
        leap.ActiveArea = config_params['LEAP']['Area']
        wait_apps(leap, weap)

    # Validate leap and weap areas
    if lang == "RUS" : msg = "Валидирование областей WEAP и LEAP."
    else : msg = "Validating WEAP and LEAP areas."
    leap.ShowProgressBar(procedure_title, msg)
    leap.SetProgressBar(5)


    #validate branches
    for aep in config_params:
        if (aep == 'WEAP' or aep=="LEAP"):
            for key in config_params[aep]['Branches']:
                if aep== 'WEAP' :
                    check_branch_var(weap, config_params[aep]['Branches'][key]['path'], config_params[aep]['Branches'][key]['variable'], config_params[aep]['Branches'][key]['unit'])
                elif aep== 'LEAP' :
                    check_branch_var(leap, config_params[aep]['Branches'][key]['path'], config_params[aep]['Branches'][key]['variable'], config_params[aep]['Branches'][key]['unit'])
            if aep == "WEAP" :
                for r in config_params[aep]['Agricultural regions']:
                    for key in config_params[aep]['Agricultural regions'][r]:
                        check_branch_var(weap, config_params[aep]['Agricultural regions'][r][key]['weap_path'], config_params[aep]['Agricultural regions'][r][key]['variable'], config_params[aep]['Agricultural regions'][r][key]['unit'])
                        print('Does this path exist?', config_params[aep]['Agricultural regions'][r][key]['weap_path'])
                for r in config_params[aep]['Industrial and domestic regions']:
                    for key in config_params[aep]['Industrial and domestic regions'][r]:
                        check_branch_var(weap, config_params[aep]['Industrial and domestic regions'][r][key]['weap_path'], config_params[aep]['Industrial and domestic regions'][r][key]['variable'], config_params[aep]['Industrial and domestic regions'][r][key]['unit'])
                        print('Does this path exist?', config_params[aep]['Industrial and domestic regions'][r][key]['weap_path'])

    # validate hydropower plants in leap
    for b in config_params['LEAP']['Hydropower_plants'] :
        check_branch_var(leap, config_params['LEAP']['Hydropower_plants'][b]['leap_path'], "Maximum Availability", "Percent")

    # validate regions
    calculated_leap_regions = config_params['LEAP']['Regions']
    for r in calculated_leap_regions :
        check_region(leap, r)

    # validate hydropower reservoirs in weap
    for b in config_params['WEAP']['Hydropower_plants'] :
        check_branch_var(weap, config_params['WEAP']['Hydropower_plants'][b]['weap_path'], "Hydropower Generation", "GJ")


    # set up target results for convergence checks during iterative calculations
    value = []
    list_leap_keys = list(config_params['LEAP']['Hydropower_plants'].keys())
    target_leap_results  = {list_leap_keys[i]: value for i in range(len(list_leap_keys))} # did not

    list_weap_keys = list(config_params['WEAP']['Hydropower_plants'].keys())
    target_weap_results  = {list_weap_keys[i]: value for i in range(len(list_weap_keys))}

    if leap_macro:
        list_leapmacro_keys=(config_params['LEAP-Macro']['target_variables'])
        target_leapmacro_results = {list_leapmacro_keys[i]: value for i in range(len(list_leapmacro_keys))}

    # BEGIN: Determine which scenarios are calculated.
    # Logic in this section: 1) look at all scenarios in runfrom_app for which results are shown; 2) try to find corresponding scenarios in other_app, looking for exact name matches and checking predefined_mappings; 3) calculate a) scenarios from 1 with a corresponding scenario from 2; and b) corresponding scenarios from 2. Disable calculations for all other scenarios.
    if lang=="RUS": msg = "Определение сценариев для расчета."
    else : msg = "Identifying scenarios to calculate."
    leap.ShowProgressBar(procedure_title, msg)
    leap.SetProgressBar(10)

    scenarios_map=dict()
    # Disable all scenario calculations in other app - calculations will be turned on for scenarios corresponding to calculated scenarios in runform_app
    disable_all_scenario_calcs(other_app_obj)

    #Map scenarios by name first, then look in predefined_mappings if an exact name match isn't found
    at_least_1_calculated = False  # Indicates whether results are shown for at least one scenario in runfrom_app
    for s in runfrom_app_obj.Scenarios :
        if s.name != "Current Accounts" and s.ResultsShown == True :
            at_least_1_calculated = True

            if other_app_obj.Scenarios.Exists(s.Name) :
                scenarios_map.update({s.name : s.name})
            else: #look for scenario name in predefined mapping
                if runfrom_app=="LEAP":
                    if s.Name in scenarios['predefined scenarios'].keys():
                        scenarios_map.update({s.name: scenarios['predefined scenarios'][s.Name]})
                elif runfrom_app == "WEAP":
                    corr_leap_scenario_predef = [i for i in scenarios['predefined scenarios'] if scenarios['predefined scenarios'][i]==s.name]
                    if corr_leap_scenario_predef:
                        scenarios_map.update({corr_leap_scenario_predef[0] : s.name})

                if runfrom_app == "LEAP" :
                    if s.Name in scenarios_map.keys():
                        other_app_obj.Scenarios(scenarios_map[s.Name]).ResultsShown = True
                elif runfrom_app == "WEAP" :
                    corr_leap_scenario = [i for i in scenarios_map if scenarios_map[i]==s.Name]
                    if corr_leap_scenario:
                        other_app_obj.Scenarios(corr_leap_scenario[0]).ResultsShown = True


    if not at_least_1_calculated :
        if lang=="RUS": msg = ["Хотя бы один сценарий должен быть рассчитан в активной области", runfrom_app, ". Выход..."]
        else : msg = ["At least one scenario must be calculated in the active " ,runfrom_app, " area. Exiting..."]
        tkmessagebox.showerror(procedure_title, " ".join(msg))
        exit()
    elif len(scenarios_map)== 0:
        if lang == "RUS": msg= ["Не удалось найти сценарии в активной области", other_app, "соответствующие сценариям, рассчитанным в активной области", runfrom_app, ". Выход..."]
        else : msg = ["Could not find scenarios in the active ", other_app, " area corresponding to the scenarios calculated in the active ", runfrom_app , " area. Exiting..."]
        tkmessagebox.showerror(procedure_title, " ".join(msg))
        exit()

    #Populate leap_scenarios and weap_scenarios
    if runfrom_app == "LEAP" or runfrom_app=="WEAP":
        leap_scenarios = list(scenarios_map.keys())
        weap_scenarios = list(scenarios_map.values())
    else :
        if lang == "RUS" : tkmessagebox.showerror(procedure_title, "Неподдерживаемый runfrom_app в интеграционной модели.")
        else : tkmessagebox.showerror(procedure_title, "Unsupported runfrom_app in run_wave_model().")

    if lang == "RUS" : msg1 = "Расчет следующих сценариев:"
    else:  msg1 = "Calculating the following scenarios:"

    for k in scenarios_map.keys():
        msg = [msg1, k,  "(LEAP) <-> ", scenarios_map[k], "(WEAP)"]
        leap.ShowProgressBar(procedure_title, " ".join(msg))

    # get calculated years in leap
    leap_calc_years=get_leap_calc_years(leap)

    # run initial LEAP-Macro run, to retrieve macro-economic variables for LEAP
    if leap_macro:
        kill_excel()
        for s in leap_scenarios:
            print('Running LEAP-Macro for scenario: ', s)
            for r, rinfo in config_params['LEAP-Macro']['regions'].items():
                print('Region:', r, flush = True)
                macrodir = os.path.join(leap.ActiveArea.Directory,  rinfo['directory_name'], rinfo['script'])
                exec_string = juliapath + " \"" + macrodir + "\" \"" +  s + "\" -y " + str(leap_calc_years[-1])
                print("Executing: '", exec_string, "'", flush = True)
                errorcode= os.system(exec_string)
                if errorcode != 0:
                    raise RuntimeError("LEAP-Macro exited with an error")

    # start iterative calculations
    last_iteration_leap_results=[]
    last_iteration_weap_results=[]
    if leap_macro:
        last_iteration_leapmacro_results=[]

    fs_obj = win32.Dispatch('Scripting.FileSystemObject') # ' Instance of scripting.FileSystemObject; used to manipulate CSV files in following loop
    excel = win32.Dispatch('Excel.Application') # Excel Application object used to create data files and query Windows list separator
    excel.ScreenUpdating = False

    listseparator = get_list_separator() # Windows list separator character (e.g., ",")
    if not len(listseparator) == 1 :
        if lang == "RUS" : tkmessagebox.showerror(procedure_title, "Разделитель списка Windows длиннее 1 символа, что несовместимо с процедурой интеграции WEAP-LEAP. Выход...")
        else : tkmessagebox.showerror(procedure_title,  "The Windows list separator is longer than 1 character, which is incompatible with the WEAP-LEAP integration procedure. Exiting...")
        exit()


    while completed_iterations < max_iterations :
        print(completed_iterations)
        if lang == "RUS":
            msg = ["Перемещение демографических и макроэкономических предположений из LEAP в WEAP (итерация ", str(completed_iterations+1), ")." ]
        else :
            msg = ["Moving demographic and macroeconomic assumptions from LEAP to WEAP (iteration ", str(completed_iterations+1), ")."]
        leap.ShowProgressBar(procedure_title, "".join(msg))
        leap.SetProgressBar(20)

        #Push demographic and macroeconomic key assumptions from LEAP to WEAP.
        #Values from LEAP base year to end year are embedded in WEAP Interp expressions
        count=0
        for k in config_params['WEAP']['Branches'].keys():
            print(k)
            leap_path=config_params['LEAP']['Branches'][config_params['WEAP']['Branches'][k]['leap_branch']]['path']
            leap_variable=config_params['LEAP']['Branches'][config_params['WEAP']['Branches'][k]['leap_branch']]['variable']
            leap_region = config_params['WEAP']['Branches'][k]['leap_region']
            if config_params['WEAP']['Branches'][k]['leap_branch']=='Population':
                unit_multiplier=1
            elif config_params['WEAP']['Branches'][k]['leap_branch']=='GDP':
                unit_multiplier =1e-9
            elif config_params['WEAP']['Branches'][k]['leap_branch']=='Industrial_VA_fraction':
                unit_multiplier =100
            else:
                msg='Unit multiplier for this variable is unknown. Exiting....'
                tkmessagebox.showerror("WAVE integration", msg)
                exit()
            add_leap_data_to_weap_interp(weap, leap, weap_scenarios, leap_scenarios, config_params['WEAP']['Branches'][k]['path'], config_params['WEAP']['Branches'][k]['variable'],  leap_path, leap_variable, leap_region, unit_multiplier, listseparator,procedure_title)

            count+=1
            print('Pushed ', count, ' variable(s) to WEAP')


        # Calculate WEAP
        if lang == "RUS":
            msg = ["Расчет (итерация ", str(completed_iterations+1), ")." ]
        else :
            msg = ["Calculating WEAP (iteration ", str(completed_iterations+1), ")."]
        leap.ShowProgressBar(procedure_title, "".join(msg))
        leap.SetProgressBar(30)

        print('Calculating WEAP...', flush = True)
        weap.Calculate()
        while weap.IsCalculating :
           leap.Sleep(1000)

        print('DONE: calculating WEAP. Moving Hydropower Maximum Availabilities from WEAP to LEAP....', flush = True)

        # Move hydropower availability information from WEAP to LEAP.
        # Availability information saved to Excel files specific to WEAP branches and LEAP scenarios. Excel pathway used since LEAP's performance is extremely poor when reading from text files.
        if lang == "RUS" : msg = ["Перемещение доступности гидроэнергетики из WEAP в LEAP (итерация ", str(completed_iterations+1), ")."]
        else : msg = ["Moving hydropower availability from WEAP to LEAP (iteration ", str(completed_iterations+1), ")."]
        leap.ShowProgressBar(procedure_title, " ".join(msg))
        leap.SetProgressBar(40)

        weap_hydro_branches = config_params['WEAP']['Hydropower_plants'].keys()
        for i in range(0, len(weap_scenarios)):
            for wb in weap_hydro_branches:
                print('weap hydro reservoir:', wb, flush = True)
                xlsx_file = "".join(["hydro_availability_wbranch", str(weap.Branches(config_params['WEAP']['Hydropower_plants'][wb]['weap_path']).Id), "_lscenario", str(leap.Scenarios(leap_scenarios[i]).Id), ".xlsx" ]) # Name of XLSX file being written
                xlsx_path = "".join([leap.ActiveArea.Directory, xlsx_file])  # Full path to XLSX file being written
                xlsx_path=fr"{xlsx_path}"
                csv_path = "".join([leap.ActiveArea.Directory, "temp.csv"])  # Temporary CSV file used to expedite creation of XLSX files

                if os.path.isfile(xlsx_path): os.remove(xlsx_path)
                if os.path.isfile(csv_path): os.remove(csv_path)

                #ts= open(csv_path, 'w', newline='')
                #writer = csv.writer(ts)
                #ts_table=list()
                ts=fs_obj.CreateTextFile(csv_path, True, False)

                num_lines_written = 0 # Number of lines written to csv_path

                print('Writing csv...', flush = True)
                st = time.time()

                # check unit
                weap_unit= weap.Branches(config_params['WEAP']['Hydropower_plants'][wb]['weap_path']).Variables('Hydropower Generation').Unit
                if not weap_unit=='GJ':
                    if lang=='RUS':
                        msg="Выработка энергии в WEAP должна быть в гигаджоулях. Выход..."
                    else:
                        msg="Energy Generation in WEAP has to be in Gigajoules. Exiting..."
                    tkmessagebox.showerror("WAVE integration", msg)
                    exit()
                # if correct unit pull weap values from weap baseyear to endyear, remove first item, convert to GJ, and round)
                weap_hpp_gen = weap.Branches(config_params['WEAP']['Hydropower_plants'][wb]['weap_path']).Variables('Hydropower Generation').ResultValues(weap.BaseYear, weap.EndYear, weap_scenarios[i])[1:]

                # check that there are values for every month
                if not len(weap_hpp_gen)%12==0:
                    if lang=='RUS':
                        msg="Выработка энергии в WEAP не является ежемесячной или не доступна для каждого месяца моделирования. Выход...."
                    else:
                        msg="Energy generation in WEAP is not monthly or not available for every simulation month. Exiting..."
                    tkmessagebox.showerror("WAVE integration", msg)
                    exit()
                y_range=range(weap.BaseYear, weap.EndYear+1)
                
                for y in range(weap.BaseYear, weap.EndYear):
                    leap_capacity_year = y
                    if leap.BaseYear > y :
                        leap_capacity_year = leap.BaseYear
                    if leap.EndYear < y :
                        leap_capacity_year = leap.EndYear
                    weap_branch_capacity = 0  # Exogenous capacity in LEAP corresponding to WEAP branch [MW]
                    leap_hpps = config_params['WEAP']['Hydropower_plants'][wb]['leap_hpps']
                    for lb in leap_hpps:
                        leap_path = config_params['LEAP']['Hydropower_plants'][lb]['leap_path']
                        leap_region = config_params['LEAP']['Hydropower_plants'][lb]['leap_region']
                        weap_branch_capacity = weap_branch_capacity + leap.Branches(leap_path).Variable("Exogenous Capacity").ValueRS(leap.Regions(leap_region).Id, leap.Scenarios(leap_scenarios[i]).Id, leap_capacity_year)  # Can't specify unit when querying data variables, but unit for Exogenous Capacity is MW

                    # Don't bother writing values for years where capacity = 0
                    if weap_branch_capacity > 0 :
                       month_vals = dict()
                       for tsl in leap.timeslices :
                            m_num=get_month_num(tsl.Name[:tsl.Name.index(":")],procedure_title) # Number of month of current time slice
                            if m_num in month_vals:
                                val=month_vals[m_num]
                            else:
                                val = round(weap_hpp_gen[y_range.index(y)*12+m_num-1] / 3.6/ (weap_branch_capacity * monthrange(y, m_num)[1] * 24) * 100, 1)  # Percentage availability value to be written to csv_path (GJ > GW)
                                if val > 100 : val = 100
                                month_vals[m_num] = val

                            ts.WriteLine("".join([str(y), listseparator, tsl.Name, listseparator, str(val)]))
                            #ts_table.append([str(y), tsl.Name, str(val)])
                            num_lines_written = num_lines_written + 1

                #writer.writerows(ts_table)
                #ts.close()
                ts.Close()
                et = time.time()
                elapsed_time = et - st
                print('Elapsed time: ', elapsed_time, ' seconds', flush = True)

                if num_lines_written>0 :
                    # Convert csv_path into an XLSX file
                    st = time.time()
                    print('saving as Excel with filename "' + xlsx_file + '"')
                    try:
                        excel.Workbooks.OpenText(csv_path, 2, 1, 1, -4142, False, False, False, True)
                        excel.ActiveWorkbook.SaveAs(xlsx_path, 51)
                        excel.ActiveWorkbook.Close()
                    except Exception as e:
                        print('could not save to Excel: ', e)
                    finally:
                        excel.Application.Quit()
                    print('xls file exists:', os.path.isfile(xlsx_path))
                    et = time.time()
                    elapsed_time = et - st
                    print('Elapsed time: ', elapsed_time, ' seconds', flush = True)

                    # Update LEAP Maximum Availability
                    leap_hpps = config_params['WEAP']['Hydropower_plants'][wb]['leap_hpps']
                    for lhpp in leap_hpps:
                        print('leap hpp:', lhpp)
                        lhpp_path = config_params['LEAP']['Hydropower_plants'][lhpp]['leap_path']
                        lhpp_region = config_params['LEAP']['Hydropower_plants'][lhpp]['leap_region']
                        leap.ActiveRegion=lhpp_region
                        leap.ActiveScenario=leap_scenarios[i]
                        leap.Branches(lhpp_path).Variable("Maximum Availability").Expression = "".join(["ReadFromExcel(" , xlsx_file , ", A1:C", str(num_lines_written), ")"])

        if excel:
            del excel
            # END: Move hydropower availability information from WEAP to LEAP.

		# BEGIN: Move Syr Darya agricultural water requirements from WEAP to LEAP.
        if lang == "RUS":
            msg = ["Перемещение информации о перекачке воды из WEAP в LEAP (итерация ", str(completed_iterations+1), ", сельское хозяйство)." ]
        else :
            msg = ["Moving water pumping information from WEAP to LEAP (iteration ", str(completed_iterations+1), ", agricultural use)."]
        leap.ShowProgressBar(procedure_title, "".join(msg))
        leap.SetProgressBar(50)

        region_ag_demand_map = config_params['WEAP']['Agricultural regions']
        for i in range(0, len(weap_scenarios)):
            for r in region_ag_demand_map:
                expr = "Interp("  # Expression that will be set for Demand\Agriculture\Syr Darya\Water demand:Activity Level in LEAP

                for y in range(weap.BaseYear, weap.EndYear+1):
                    val = 0  # Value that will be written into expr for y
                    for wb in region_ag_demand_map[r]:
                        val = val + weap.ResultValue("".join([region_ag_demand_map[r][wb]['weap_path'], ":Supply Requirement[m^3]"]), y, 1, weap_scenarios[i], y, 12, 'Total')
                    expr = "".join([expr,str(y),listseparator,str(val),listseparator])


                expr = "".join([expr[0:-1], ")"])
                leap.ActiveRegion=r
                leap.ActiveScenario=leap_scenarios[i]
                print('This region', r)
                print('leap expr before:', leap.Branches("Demand\Agriculture\Syr Darya\Water demand").Variables("Activity Level").Expression)
                leap.Branches("Demand\Agriculture\Syr Darya\Water demand").Variables("Activity Level").Expression = expr
                print('leap expr after:', leap.Branches("Demand\Agriculture\Syr Darya\Water demand").Variables("Activity Level").Expression)
		# END: Move Syr Darya agricultural water requirements from WEAP to LEAP.


        # Move industrial and domestic water requirements from WEAP to LEAP
        print('Moving industrial water requirements from WEAP to LEAP ....', flush = True)
        if lang == "RUS":
            msg = ["Перемещение информации о перекачке воды из WEAP в LEAP (итерация ", str(completed_iterations+1), ", промышленное и бытовое использование)." ]
        else :
            msg = ["Moving water pumping information from WEAP to LEAP (iteration ", str(completed_iterations+1), ", industrial and domestic use)."]
        leap.ShowProgressBar(procedure_title, "".join(msg))
        leap.SetProgressBar(55)

        region_inddom_demand_map = config_params['WEAP']['Industrial and domestic regions']
        for i in range(0, len(weap_scenarios)):
            for r in region_inddom_demand_map:
                expr = "Interp("  # Expression that will be set for Demand\Industry\Syr Darya\Water demand:Activity Level in LEAP

                for y in range(weap.BaseYear, weap.EndYear+1):
                    val = 0  # Value that will be written into expr for y
                    for wb in region_inddom_demand_map[r]:
                        val = val + weap.ResultValue("".join([region_inddom_demand_map[r][wb]['weap_path'], ":Supply Requirement[m^3]"]), y, 1, weap_scenarios[i], y, 12, 'Total')
                    expr = "".join([expr,str(y),listseparator,str(val),listseparator])

                expr = "".join([expr[0:-1], ")"])
                leap.ActiveRegion=r
                leap.ActiveScenario=leap_scenarios[i]
                print('This region', r)
                print('Original leap expr :', leap.Branches("Demand\Industry\Other\Syr Darya Water Pumping").Variables("Activity Level").Expression)
                leap.Branches("Demand\Industry\Other\Syr Darya Water Pumping").Variables("Activity Level").Expression = expr
                print('Upated leap expr:', leap.Branches("Demand\Industry\Other\Syr Darya Water Pumping").Variables("Activity Level").Expression)


        # BEGIN: Calculate LEAP.
        lst=time.time()
        if lang == "RUS":
            msg = ["Расчет площади LEAP (итерация ", str(completed_iterations+1), ")."]
        else:
            msg = ["Calculating LEAP area (iteration ", str(completed_iterations+1), ")."]
        leap.ShowProgressBar(procedure_title, "".join(msg))
        leap.SetProgressBar(50)

        print('Running LEAP...', flush = True)
        kill_excel()
        leap.Calculate(False)

        # ++++++++++++++++++
        # +++++ NOTE: script from Emily to be added prior to this, will get results from WEAP)
        # ++++++++++++++++++

        # BEGIN: Calculate LEAP Macro with new results from WEAP and LEAP.
        if leap_macro:
            kill_excel()
            for s in leap_scenarios:
                print('Running LEAP-Macro for scenario: ', s)
                for r, rinfo in config_params['LEAP-Macro']['regions'].items():
                    print('Region:', r)
                    macrodir = os.path.join(leap.ActiveArea.Directory,  rinfo['directory_name'], rinfo['script'])
                    exec_string = juliapath + " \"" + macrodir + "\" \"" +  s + "\" -y " + str(leap_calc_years[-1]) + " -r " + str(2*(completed_iterations + 1)) + " --load-leap-first"
                    print("Executing: '", exec_string, "'", flush = True)
                    errorcode= os.system(exec_string)
                    if errorcode != 0:
                        raise RuntimeError("LEAP-Macro exited with an error")

        # BEGIN: Record target results for this iteration.
        if lang == "RUS":
            msg = ["Запись результатов и проверка сходимости (итерация ", str(completed_iterations+1),")."]
        else:
            msg = ["Recording results and checking for convergence (iteration ", str(completed_iterations+1), ")."]
        leap.ShowProgressBar(procedure_title, "".join(msg))
        leap.SetProgressBar(80)

        print('Checking Leap results......')
        this_iteration_leap_results= numpy.empty((len(target_leap_results)*len(leap_scenarios)*len(leap_calc_years)), dtype=object)  # Array of target LEAP result values obtained in this iteration. Contains one set of result values for each scenario in leap_scenarios and year calculated in LEAP; results are ordered by scenario, year, and result in target_leap_results
        current_index = 0  # Index currently being written to this_iteration_leap_results/this_iteration_weap_results

        for e in target_leap_results:
            for s in leap_scenarios:
                for y in leap_calc_years:
                    # Elements in target_leap_results: Array(branch full name, variable name, region name, unit name)
                    this_iteration_leap_results[current_index] = leap.Branches(config_params['LEAP']['Hydropower_plants'][e]['leap_path']).Variables(config_params['LEAP']['Hydropower_plants'][e]['leap_variable']).ValueRS(leap.Regions(config_params['LEAP']['Hydropower_plants'][e]['leap_region']).Id, leap.Scenarios(s).Id, y, config_params['LEAP']['Hydropower_plants'][e]['leap_unit'])
                    current_index = current_index + 1

        print('Checking Macro results...')
        if leap_macro:
            this_iteration_leapmacro_results= numpy.empty((len(target_leapmacro_results)*len(config_params['LEAP-Macro']['regions'].keys())*len(leap_scenarios)*len(leap_calc_years)), dtype=object)  # Array of target LEAP result values obtained in this iteration. Contains one set of result values for each scenario in leap_scenarios and year calculated in LEAP; results are ordered by scenario, year, and result in target_leap_results
            current_index = 0  # Index currently being written to this_iteration_leap_results/this_iteration_weap_results/this_teration_leapmacro_results

            for e in target_leapmacro_results:
                for r in config_params['LEAP-Macro']['regions']:
                    for s in leap_scenarios:
                        for y in leap_calc_years:
                            # Elements in target_leap_results: Array(branch full name, variable name, region name, unit name)
                            this_iteration_leapmacro_results[current_index] = leap.Branches(config_params['LEAP']['Branches'][e]['path']).Variables(config_params['LEAP']['Branches'][e]['variable']).ValueRS(leap.Regions(r).Id, leap.Scenarios(s).Id, y)
                            print(this_iteration_leap_results[current_index])
                            current_index = current_index + 1

        if lang == "RUS":
            msg = ["Запись результатов и проверка сходимости (итерация ", str(completed_iterations+1),")."]
        else:
            msg = ["Recording results and checking for convergence (iteration ", str(completed_iterations+1), ")."]
        leap.ShowProgressBar(procedure_title, "".join(msg))
        leap.SetProgressBar(85)

        print('Checking WEAP results......')
        this_iteration_weap_results= numpy.empty((len(target_weap_results)*len(weap_scenarios)*weap.EndYear - weap.BaseYear + 1), dtype=object)  # Array of target WEAP result values obtained in this iteration. Contains one set of result values for each scenario in weap_scenarios and year calculated in WEAP; results are ordered by scenario, year, and result in target_weap_results
        current_index = 0  # Index currently being written to this_iteration_leap_results/this_iteration_weap_results

        for e in target_weap_results:
            for s in weap_scenarios:
                for y in range(weap.BaseYear, weap.EndYear):
                    # Elements in target_weap_results: full branch-variable-unit path
                    this_iteration_weap_results[current_index] = weap.ResultValue("".join([config_params['WEAP']['Hydropower_plants'][e]['weap_path'], config_params['WEAP']['Hydropower_plants'][e]['weap_variable']]), y, 1, s, y, 12, 'Total')
                    print(this_iteration_weap_results[current_index])
                    current_index = current_index + 1
        # END: Record target results for this iteration.

        # check for convergence if necessary
        if ((completed_iterations > 1) and (completed_iterations < max_iterations)):
            if lang == "RUS":
                msg = ["Запись результатов и проверка сходимости (итерация ", str(completed_iterations+1),")."]
            else:
                msg = ["Recording results and checking for convergence (iteration ", str(completed_iterations+1), ")."]
            leap.ShowProgressBar(procedure_title, "".join(msg))
            leap.SetProgressBar(95)

            results_converged = True # Tentative; may be overwritten during following convergence checks

            for i in range(0, len(this_iteration_leap_results)):
                if ((last_iteration_leap_results[i] == 0) and (this_iteration_leap_results[i] != 0)) :
                    results_converged = False
                    break
                elif abs(this_iteration_leap_results[i] / last_iteration_leap_results[i] - 1) > tolerance :
                    results_converged = False
                    break

            # Only carry out LEAP-Macro convergence checks if all LEAP-macro is turned on and all LEAP checks passed
            if (results_converged == True and leap_macro):
                for i in range(0, len(this_iteration_leapmacro_results)):
                    if ((last_iteration_leapmacro_results[i] == 0) and (this_iteration_leapmacro_results[i]!=0)):
                        results_converged = False
                        break
                    elif (abs(this_iteration_leapmacro_results[i] / last_iteration_leapmacro_results[i] - 1) > tolerance):
                        results_converged = False
                        break

            # Only carry out WEAP convergence checks if all LEAP (and LEAP-Macro) checks passed
            if results_converged == True :
                for i in range(0, len(this_iteration_weap_results)):
                    if ((last_iteration_weap_results[i] == 0) and (this_iteration_weap_results[i]!=0)):
                        results_converged = False
                        break
                    elif (abs(this_iteration_weap_results[i] / last_iteration_weap_results[i] - 1) > tolerance):
                        results_converged = False
                        break

            if results_converged == True :
                if lang == "RUS":
                    msg = ["Все целевые результаты WEAP и LEAP сошлись в пределах заданного допуска (", str(tolerance * 100), "%). Дополнительных итераций расчетов WEAP и LEAP не требуется."]
                else:
                    msg = ["All target WEAP and LEAP results converged to within the specified tolerance (", str(tolerance * 100), "%). No additional iterations of WEAP and LEAP calculations are needed."]
                leap.ShowProgressBar(procedure_title, "".join(msg))
                leap.SetProgressBar(100)

        # END: Check for convergence if necessary.

        # Update WEAP and LEAP target results
        last_iteration_leap_results = this_iteration_leap_results
        last_iteration_weap_results = this_iteration_weap_results

        completed_iterations += 1

    if lang == "RUS":
        msg ="Завершена процедура интеграции WEAP-LEAP."
    else :
        msg = "Completed WEAP-LEAP integration procedure."
    leap.ShowProgressBar(procedure_title, "".join(msg))
    

    tet = time.time()
    total_elapsed_time = tet - tst
    print('Total elapsed time:', total_elapsed_time, 'seconds')


main_integration(user_interface=False, tolerance=0.1, max_iterations=1) # can later be run from VB script
