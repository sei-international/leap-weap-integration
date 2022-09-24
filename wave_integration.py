# If install via Miniconda, must then run:
#   conda install pyyaml, numpy, psutil
#   conda install pywin32, then run in command prompt:
#      cd "C:\ProgramData\Miniconda3\Scripts"
#      python pywin32_postinstall.py -install

# If install via pip:
#   pip install pyyaml, pywin32, psutil, numpy

from errno import WSAEDQUOT
from ntpath import altsep
import win32com.client as win32
import win32gui
from tkinter import Tk, Label, Button, Radiobutton, IntVar
from tkinter import messagebox as tkmessagebox
import yaml
import time
from winreg import *
from calendar import monthrange
import os # os.path, os.system
from sys import float_info
import psutil
import numpy
import re
import uuid
import logging
from collections import OrderedDict
from julia_utils import get_julia_path
from leap_weap_sub import add_leap_data_to_weap_interp, get_leap_timeslice_info
from weap_macro_sub import exportcsvmodule, weaptomacroprocessing

# in julia: using LEAPMacro
# using YAML
# using ArgParse need to be installed
#==================================================================================================#
# Script for integrating WAVE WEAP and LEAP models.
#
# Copyright © 2022: Stockholm Environment Institute U.S.
#==================================================================================================#
logfile = 'wave_integration_' + str(uuid.uuid4().hex) + '.log'
print('Sending to log file "' + logfile + '"', flush = True)
logging.basicConfig(filename=logfile,
                    format='[%(asctime)s.%(msecs)03d]%(levelname)s:%(message)s',
                    encoding='utf-8',
                    level=logging.INFO,
                    datefmt='%Y-%m-%d %H:%M:%S')

tst = time.time()
# List of functions to be defined
# Convert number of seconds into HH::MM::SS
def hms_from_sec(dt):
    dtn = round(dt)
    h = dtn // 3600
    m = dtn % 3600 // 60
    s = dtn % 3600 % 60
    return '{:02}:{:02}:{:02}'.format(h,m,s)

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
    leap_calculated_years = []
    last_index = -1
    for y in range(app.FirstScenarioYear, app.EndYear+1) :
        if y%app.resultsEvery == 0:
            leap_calculated_years.append(y)
            last_index += 1
    return leap_calculated_years
    
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
def main_integration(user_interface, tolerance, max_iterations):

    #------------------------------------------------------------------------------------------------------------------------
    #
    # Define constants
    #
    #------------------------------------------------------------------------------------------------------------------------
    LIST_SEPARATOR = get_list_separator() # Windows list separator character (e.g., ",")
    if not len(LIST_SEPARATOR) == 1 :
        if lang == "RUS" : tkmessagebox.showerror(procedure_title, "Разделитель списка Windows длиннее 1 символа, что несовместимо с процедурой интеграции WEAP-LEAP. Выход...")
        else : tkmessagebox.showerror(procedure_title,  "The Windows list separator is longer than 1 character, which is incompatible with the WEAP-LEAP integration procedure. Exiting...")
        exit()

    CSV_ROW_SKIP = 3 # number of rows to skip in weap csv outputs

    #------------------------------------------------------------------------------------------------------------------------
    #
    # Initialize
    #
    #------------------------------------------------------------------------------------------------------------------------
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
    weap.Verbose = 0
    other_app = "WEAP"
    wait_apps(weap, leap)

    if not leap or not weap:
        logging.error("WAVE integration: Cannot start LEAP and WEAP. Exiting...")
        exit()
        
    leap_ts_info = get_leap_timeslice_info(leap)

    # leap.Verbose = 1

    if runfrom_app == "LEAP" :
        runfrom_app_obj = leap
        other_app_obj = weap
    elif runfrom_app == "WEAP" :
        runfrom_app_obj = weap
        other_app_obj = leap


    # Bring LEAP to front to enable showing progress bar to increase chances of showing progress bar
    shell = win32.Dispatch("WScript.Shell")
    shell.AppActivate("LEAP: ")

    # Check whether leap_macro is being run
    leap_macro = 'LEAP-Macro' in config_params.keys()

    # Set run time language
    lang = None
    if user_interface :
        lines = ["Would you like Russian language prompts? / Хотите подсказки на русском языке?", "Select Language / Выберите язык"]
        msg = "\n".join(lines)
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
        juliapath = get_julia_path(shell)
        if juliapath == None:
            msg = "Could not locate the Julia executable. Try adding the path to the executable to the Windows environment variable named 'Path'."
            leap.ShowProgressBar(procedure_title, msg)
            exit()

    weap.ActiveArea = config_params['WEAP']['Area']
    wait_apps(weap, leap)
    leap.ActiveArea = config_params['LEAP']['Area']
    wait_apps(leap, weap)

    # open correct leap area and select scenarios and years to be calculated
    if lang == "RUS" :
        msg = ["Пожалуйста, откройте модель WAVE (область) в LEAP (такую же, как определена в config.yml) и выберите сценарии и годы, которые вы хотели бы запустить.", "ПРИМЕЧАНИЕ: Настройки LEAP определяют рассчитанные сценарии. Выбор сценария в WEAP будет переписан."]
        title = "Открытая область LEAP"
    else :
        title = "Open LEAP Area"
        msg = ["Please open the WAVE model (area) in LEAP (the same as defined in config.yml) and select the scenarios and years you would like to run." , "NOTE: LEAP settings determine calculated scenarios. Scenario selection in WEAP will be overwritten."]
    messagebox = tkmessagebox.askokcancel(title, "\n".join(msg))
    if messagebox != True :
        exit()
    
    #------------------------------------------------------------------------------------------------------------------------
    #
    # Validate LEAP and WEAP areas
    #
    #------------------------------------------------------------------------------------------------------------------------
    if lang == "RUS" : msg = "Валидирование областей WEAP и LEAP."
    else : msg = "Validating WEAP and LEAP areas."
    leap.ShowProgressBar(procedure_title, msg)
    leap.SetProgressBar(5)

    # validate branches
    logging.info('Validating branches in WEAP and LEAP')
    for aep in config_params:
        if (aep == 'WEAP' or aep == "LEAP"):
            for key in config_params[aep]['Branches']:
                if aep== 'WEAP' :
                    check_branch_var(weap, config_params[aep]['Branches'][key]['path'], config_params[aep]['Branches'][key]['variable'], config_params[aep]['Branches'][key]['unit'])
                elif aep== 'LEAP' :
                    check_branch_var(leap, config_params[aep]['Branches'][key]['path'], config_params[aep]['Branches'][key]['variable'], config_params[aep]['Branches'][key]['unit'])
            if aep == "WEAP" :
                for r in config_params[aep]['Agricultural regions']:
                    for key in config_params[aep]['Agricultural regions'][r]:
                        check_branch_var(weap, config_params[aep]['Agricultural regions'][r][key]['weap_path'], config_params[aep]['Agricultural regions'][r][key]['variable'], config_params[aep]['Agricultural regions'][r][key]['unit'])
                for r in config_params[aep]['Industrial and domestic regions']:
                    for key in config_params[aep]['Industrial and domestic regions'][r]:
                        check_branch_var(weap, config_params[aep]['Industrial and domestic regions'][r][key]['weap_path'], config_params[aep]['Industrial and domestic regions'][r][key]['variable'], config_params[aep]['Industrial and domestic regions'][r][key]['unit'])

    # validate regions
    logging.info('Running the model for regions: ')
    calculated_leap_regions = config_params['LEAP']['Regions']
    for r in calculated_leap_regions :
        logging.info('\t' + r)
        check_region(leap, r)

    # validate hydropower plants in leap
    logging.info('Including LEAP hydropower plants: ')
    for b in config_params['LEAP']['Hydropower_plants'] :
        logging.info('\t' + b)
        check_branch_var(leap, config_params['LEAP']['Hydropower_plants'][b]['leap_path'], "Maximum Availability", "Percent")

    # validate hydropower reservoirs in weap
    logging.info('Including WEAP hydropower reservoirs: ')
    for b in config_params['WEAP']['Hydropower_plants'] :
        logging.info('\t' + b)
        check_branch_var(weap, config_params['WEAP']['Hydropower_plants'][b]['weap_path'], "Hydropower Generation", "GJ")


    #------------------------------------------------------------------------------------------------------------------------
    #
    # Find the scenarios being calculated
    #
    #------------------------------------------------------------------------------------------------------------------------
    # Logic in this section:
    #   1) Look at all scenarios in runfrom_app for which results are shown;
    #   2) Try to find corresponding scenarios in other_app, looking for exact name matches and checking predefined_mappings;
    #   3) Calculate:
    #       a) Scenarios from 1 with a corresponding scenario from 2;
    #       b) Corresponding scenarios from 2;
    #   4) Disable calculations for all other scenarios.
    if lang == "RUS": msg = "Определение сценариев для расчета."
    else : msg = "Identifying scenarios to calculate."
    leap.ShowProgressBar(procedure_title, msg)
    leap.SetProgressBar(10)

    scenarios_map = dict()
    # Disable all scenario calculations in other app - calculations will be turned on for scenarios corresponding to calculated scenarios in runfrom_app
    disable_all_scenario_calcs(other_app_obj)

    # Map scenarios by name first, then look in predefined_mappings if an exact name match isn't found
    at_least_1_calculated = False  # Indicates whether results are shown for at least one scenario in runfrom_app
    for s in runfrom_app_obj.Scenarios :
        if s.name != "Current Accounts" and s.ResultsShown == True :
            at_least_1_calculated = True

            if other_app_obj.Scenarios.Exists(s.Name) :
                scenarios_map.update({s.name : s.name})
            else: # look for scenario name in predefined mapping
                if runfrom_app == "LEAP":
                    if s.Name in scenarios['predefined scenarios'].keys():
                        scenarios_map.update({s.name: scenarios['predefined scenarios'][s.Name]})
                elif runfrom_app == "WEAP":
                    corr_leap_scenario_predef = [i for i in scenarios['predefined scenarios'] if scenarios['predefined scenarios'][i] == s.name]
                    if corr_leap_scenario_predef:
                        scenarios_map.update({corr_leap_scenario_predef[0] : s.name})

                if runfrom_app == "LEAP" :
                    if s.Name in scenarios_map.keys():
                        other_app_obj.Scenarios(scenarios_map[s.Name]).ResultsShown = True
                elif runfrom_app == "WEAP" :
                    corr_leap_scenario = [i for i in scenarios_map if scenarios_map[i] == s.Name]
                    if corr_leap_scenario:
                        other_app_obj.Scenarios(corr_leap_scenario[0]).ResultsShown = True


    if not at_least_1_calculated :
        if lang == "RUS": msg = ["Хотя бы один сценарий должен быть рассчитан в активной области", runfrom_app, ". Выход..."]
        else : msg = ["At least one scenario must be calculated in the active " ,runfrom_app, " area. Exiting..."]
        tkmessagebox.showerror(procedure_title, " ".join(msg))
        exit()
    elif len(scenarios_map)== 0:
        if lang == "RUS": msg= ["Не удалось найти сценарии в активной области", other_app, "соответствующие сценариям, рассчитанным в активной области", runfrom_app, ". Выход..."]
        else : msg = ["Could not find scenarios in the active ", other_app, " area corresponding to the scenarios calculated in the active ", runfrom_app , " area. Exiting..."]
        tkmessagebox.showerror(procedure_title, " ".join(msg))
        exit()

    # Populate leap_scenarios and weap_scenarios
    if runfrom_app == "LEAP" or runfrom_app == "WEAP":
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
        leap.SetProgressBar(10)

    # get calculated years in leap
    leap_calc_years = get_leap_calc_years(leap)

    # Clear hydropower reservoir energy demand from WEAP scenarios
    logging.info('Clearing hydropower reservoir energy demand from WEAP scenarios to avoid forcing model with results from past integration runs.')
    weap_hydro_branches = config_params['WEAP']['Hydropower_plants'].keys()
    for s in weap_scenarios:
        weap.ActiveScenario = s
        for wb in weap_hydro_branches:
            weap_path = config_params['WEAP']['Hydropower_plants'][wb]['weap_path']
            if not 'Run of River' in weap_path: 
                weap_path = config_params['WEAP']['Hydropower_plants'][wb]['weap_path']
                weap.Branches(config_params['WEAP']['Hydropower_plants'][wb]['weap_path']).Variables('Energy Demand').Expression = ""

    # Initial LEAP-Macro run, to provide macro-economic variables to LEAP
    if leap_macro:
        for s in leap_scenarios:
            logging.info('Running LEAP-Macro for scenario: ' + s)
            for r, rinfo in config_params['LEAP-Macro']['regions'].items():
                logging.info('\tRegion: ' + r)
                macrodir = os.path.join(leap.ActiveArea.Directory,  rinfo['directory_name'], rinfo['script'])
                exec_string = juliapath + " \"" + macrodir + "\" \"" +  s + "\" -c -p -v -y " + str(leap_calc_years[-1])
                logging.info("\tExecuting: '" + exec_string + "'")
                errorcode= os.system(exec_string)
                if errorcode != 0:
                    raise RuntimeError("LEAP-Macro exited with an error")

    # start iterative calculations
    last_iteration_leap_results = []
    last_iteration_weap_results = []
    if leap_macro:
        last_iteration_leapmacro_results = []

    #------------------------------------------------------------------------------------------------------------------------
    #
    # Start iterations
    #
    #------------------------------------------------------------------------------------------------------------------------
    completed_iterations = 0
    results_converged = False
    # set up target results for convergence checks during iterative calculations
    value = []
    list_leap_keys = list(config_params['LEAP']['Hydropower_plants'].keys())
    target_leap_results  = {list_leap_keys[i]: value for i in range(len(list_leap_keys))}

    list_weap_keys = list(config_params['WEAP']['Hydropower_plants'].keys())
    target_weap_results  = {list_weap_keys[i]: value for i in range(len(list_weap_keys))}

    if leap_macro:
        list_leapmacro_keys = (config_params['LEAP-Macro']['LEAP']['target_variables'])
        target_leapmacro_results = {list_leapmacro_keys[i]: value for i in range(len(list_leapmacro_keys))}

    while completed_iterations < max_iterations :
        if lang == "RUS":
            msg = ["Перемещение демографических и макроэкономических предположений из LEAP в WEAP (итерация ", str(completed_iterations+1), ")." ]
        else :
            msg = ["Moving demographic and macroeconomic assumptions from LEAP to WEAP (iteration ", str(completed_iterations+1), ")."]
        leap.ShowProgressBar(procedure_title, "".join(msg))
        leap.SetProgressBar(20)

        #------------------------------------------------------------------------------------------------------------------------
        # Push demographic and macroeconomic key assumptions from LEAP to WEAP
        #------------------------------------------------------------------------------------------------------------------------
        # Values from LEAP base year to end year are embedded in WEAP Interp expressions
        count = 0
        logging.info('Pushing demographic and macroeconomic drivers from LEAP to WEAP')
        for k in config_params['WEAP']['Branches'].keys():
            logging.info('\t' + k)
            leap_path = config_params['LEAP']['Branches'][config_params['WEAP']['Branches'][k]['leap_branch']]['path']
            leap_variable = config_params['LEAP']['Branches'][config_params['WEAP']['Branches'][k]['leap_branch']]['variable']
            leap_region = config_params['WEAP']['Branches'][k]['leap_region']
            if config_params['WEAP']['Branches'][k]['leap_branch'] == 'Population':
                unit_multiplier = 1
            elif config_params['WEAP']['Branches'][k]['leap_branch'] == 'GDP':
                unit_multiplier = 1e-9
            elif config_params['WEAP']['Branches'][k]['leap_branch'] == 'Industrial_VA_fraction':
                unit_multiplier = 100
            else:
                msg = 'Unit multiplier for this variable is unknown. Exiting....'
                tkmessagebox.showerror("WAVE integration", msg)
                exit()
            add_leap_data_to_weap_interp(weap, leap, weap_scenarios, leap_scenarios, config_params['WEAP']['Branches'][k]['path'], config_params['WEAP']['Branches'][k]['variable'],  leap_path, leap_variable, leap_region, unit_multiplier, LIST_SEPARATOR,procedure_title)

            count += 1
            
        logging.info('Pushed ' + str(count) + ' variable(s) to WEAP')
            
        #------------------------------------------------------------------------------------------------------------------------
        # Calculate WEAP
        #------------------------------------------------------------------------------------------------------------------------
        if lang == "RUS":
            msg = ["Расчет (итерация ", str(completed_iterations+1), ")." ]
        else :
            msg = ["Calculating WEAP (iteration ", str(completed_iterations+1), ")."]
        leap.ShowProgressBar(procedure_title, "".join(msg))
        leap.SetProgressBar(30)

        logging.info('Calculating WEAP (iteration ' + str(completed_iterations + 1) + ')')
        weap.Calculate()
        while weap.IsCalculating :
           leap.Sleep(1000)

        logging.info('Finished calculating WEAP. Moving hydropower maximum availabilities from WEAP to LEAP....')

        #------------------------------------------------------------------------------------------------------------------------
        # Move hydropower availability information from WEAP to LEAP.
        #------------------------------------------------------------------------------------------------------------------------
        # Availability information saved to Excel files specific to WEAP branches and LEAP scenarios.
        #   Note: Excel used since LEAP's performance is extremely poor when reading from text files.
        if lang == "RUS" : msg = ["Перемещение доступности гидроэнергетики из WEAP в LEAP (итерация ", str(completed_iterations+1), ")."]
        else : msg = ["Moving hydropower availability from WEAP to LEAP (iteration ", str(completed_iterations+1), ")."]
        leap.ShowProgressBar(procedure_title, " ".join(msg))
        leap.SetProgressBar(40)

        fs_obj = win32.Dispatch('Scripting.FileSystemObject') # Instance of scripting.FileSystemObject; used to manipulate CSV files in following loop
        excel = win32.Dispatch('Excel.Application') # Excel Application object used to create data files
        excel.ScreenUpdating = False

        weap_hydro_branches = config_params['WEAP']['Hydropower_plants'].keys()
        for i in range(0, len(weap_scenarios)):
            logging.info('WEAP scenario: ' + weap_scenarios[i])
            for wb in weap_hydro_branches:
                logging.info('\tWEAP hydropower reservoir: ' + wb)
                xlsx_file = "".join(["hydro_availability_wbranch", str(weap.Branches(config_params['WEAP']['Hydropower_plants'][wb]['weap_path']).Id), "_lscenario", str(leap.Scenarios(leap_scenarios[i]).Id), ".xlsx" ]) # Name of XLSX file being written
                xlsx_path = os.path.join(leap.ActiveArea.Directory, xlsx_file)  # Full path to XLSX file being written
                xlsx_path = fr"{xlsx_path}"
                csv_path = os.path.join(leap.ActiveArea.Directory, "temp.csv")  # Temporary CSV file used to expedite creation of XLSX files

                if os.path.isfile(xlsx_path): os.remove(xlsx_path)
                if os.path.isfile(csv_path): os.remove(csv_path)

                ts = fs_obj.CreateTextFile(csv_path, True, False)

                num_lines_written = 0 # Number of lines written to CSV file

                # check unit
                weap_unit= weap.Branches(config_params['WEAP']['Hydropower_plants'][wb]['weap_path']).Variables('Hydropower Generation').Unit
                if not weap_unit == 'GJ':
                    if lang == 'RUS':
                        msg = "Выработка энергии в WEAP должна быть в гигаджоулях. Выход..."
                    else:
                        msg = "Energy Generation in WEAP has to be in Gigajoules. Exiting..."
                    tkmessagebox.showerror("WAVE integration", msg)
                    exit()
                # if correct unit pull weap values from weap baseyear to endyear, remove first item, convert to GJ, and round)
                weap_hpp_gen = weap.Branches(config_params['WEAP']['Hydropower_plants'][wb]['weap_path']).Variables('Hydropower Generation').ResultValues(weap.BaseYear, weap.EndYear, weap_scenarios[i])[1:]

                # check that there are values for every month
                if not len(weap_hpp_gen)%12 == 0:
                    if lang == 'RUS':
                        msg = "Выработка энергии в WEAP не является ежемесячной или не доступна для каждого месяца моделирования. Выход...."
                    else:
                        msg = "Energy generation in WEAP is not monthly or not available for every simulation month. Exiting..."
                    tkmessagebox.showerror("WAVE integration", msg)
                    exit()
                y_range = range(weap.BaseYear, weap.EndYear+1)
                
                for y in y_range:
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
                        weap_branch_capacity += leap.Branches(leap_path).Variable("Exogenous Capacity").ValueRS(leap.Regions(leap_region).Id, leap.Scenarios(leap_scenarios[i]).Id, leap_capacity_year)  # Can't specify unit when querying data variables, but unit for Exogenous Capacity is MW

                    # Don't bother writing values for years where capacity = 0
                    if weap_branch_capacity > 0 :
                        month_vals = dict()
                        for ts_name, m_num in leap_ts_info.items():
                            if m_num in month_vals:
                                # Same value for all time slices in a month
                                val = month_vals[m_num]
                            else:
                                # Percentage availability value to be written to csv_path (Note: 1 MWh = 3.6 GJ)
                                val = round(weap_hpp_gen[(y - y_range[0])*12 + m_num - 1] / 3.6 / (weap_branch_capacity * monthrange(y, m_num)[1] * 24) * 100, 1)
                                if val > 100 : val = 100
                                month_vals[m_num] = val

                            ts.WriteLine("".join([str(y), LIST_SEPARATOR, ts_name, LIST_SEPARATOR, str(val)]))
                            num_lines_written += 1
                    
                ts.Close()
                
                if num_lines_written > 0 :
                    # Convert csv_path into an XLSX file
                    logging.info('\t\tSaving as Excel with filename "' + xlsx_file + '"')
                    try:
                        excel.Workbooks.OpenText(csv_path, 2, 1, 1, -4142, False, False, False, True)
                        excel.ActiveWorkbook.SaveAs(xlsx_path, 51)
                        excel.ActiveWorkbook.Close()
                    except Exception as e:
                        logging.error('Could not save to Excel: ' + str(e))
                    finally:
                        excel.Application.Quit()
                    if not os.path.isfile(xlsx_path):
                        logging.error('Excel file not written correctly: file does not exist')
                        # TODO: raise exception

                    # Update LEAP Maximum Availability
                    leap_hpps = config_params['WEAP']['Hydropower_plants'][wb]['leap_hpps']
                    for lhpp in leap_hpps:
                        logging.info('\t\tAssigning to LEAP hydropower plant: ' + lhpp)
                        lhpp_path = config_params['LEAP']['Hydropower_plants'][lhpp]['leap_path']
                        lhpp_region = config_params['LEAP']['Hydropower_plants'][lhpp]['leap_region']
                        leap.ActiveRegion = lhpp_region
                        leap.ActiveScenario = leap_scenarios[i]
                        leap.Branches(lhpp_path).Variable("Maximum Availability").Expression = "".join(["ReadFromExcel(" , xlsx_file , ", A1:C", str(num_lines_written), ")"])

        # Remove win32 objects
        if excel:
            del excel
        if fs_obj:
            del fs_obj
        # END: Move hydropower availability information from WEAP to LEAP.

        #------------------------------------------------------------------------------------------------------------------------
        # Move Syr Darya agricultural water requirements from WEAP to LEAP.
        #------------------------------------------------------------------------------------------------------------------------
        # TODO: Make this generic, not just for this application/Syr Darya
        if lang == "RUS":
            msg = ["Перемещение информации о перекачке воды из WEAP в LEAP (итерация ", str(completed_iterations+1), ", сельское хозяйство)." ]
        else :
            msg = ["Moving water pumping information from WEAP to LEAP (iteration ", str(completed_iterations+1), ", agricultural use)."]
        leap.ShowProgressBar(procedure_title, "".join(msg))
        leap.SetProgressBar(50)

        logging.info('Moving water pumping information from WEAP to LEAP')
        region_ag_demand_map = config_params['WEAP']['Agricultural regions']
        for i in range(0, len(weap_scenarios)):
            logging.info('\tScenario: ' + weap_scenarios[i] + ' (WEAP)/' + leap_scenarios[i] + ' (LEAP)')
            for r in region_ag_demand_map:
                expr = "Interp("  # Expression that will be set for Demand\Agriculture\Syr Darya\Water demand:Activity Level in LEAP

                for y in range(weap.BaseYear, weap.EndYear+1):
                    val = 0  # Value that will be written into expr for y
                    for wb in region_ag_demand_map[r]:
                        val = val + weap.ResultValue("".join([region_ag_demand_map[r][wb]['weap_path'], ":Supply Requirement[m^3]"]), y, 1, weap_scenarios[i], y, 12, 'Total')
                    expr = "".join([expr,str(y),LIST_SEPARATOR,str(val),LIST_SEPARATOR])


                expr = "".join([expr[0:-1], ")"])
                leap.ActiveRegion = r
                leap.ActiveScenario = leap_scenarios[i]
                logging.info('\t\tRegion: ' + r)
                leap.Branches("Demand\Agriculture\Syr Darya\Water demand").Variables("Activity Level").Expression = expr
		# END: Move Syr Darya agricultural water requirements from WEAP to LEAP.

        #------------------------------------------------------------------------------------------------------------------------
        # Move industrial and domestic water requirements from WEAP to LEAP
        #------------------------------------------------------------------------------------------------------------------------
        logging.info('Moving industrial water requirements from WEAP to LEAP')
        if lang == "RUS":
            msg = ["Перемещение информации о перекачке воды из WEAP в LEAP (итерация ", str(completed_iterations+1), ", промышленное и бытовое использование)." ]
        else :
            msg = ["Moving water pumping information from WEAP to LEAP (iteration ", str(completed_iterations+1), ", industrial and domestic use)."]
        leap.ShowProgressBar(procedure_title, "".join(msg))
        leap.SetProgressBar(55)

        region_inddom_demand_map = config_params['WEAP']['Industrial and domestic regions']
        for i in range(0, len(weap_scenarios)):
            logging.info('\tScenario: ' + weap_scenarios[i] + ' (WEAP)/' + leap_scenarios[i] + ' (LEAP)')
            for r in region_inddom_demand_map:
                expr = "Interp("  # Expression that will be set for Demand\Industry\Syr Darya\Water demand:Activity Level in LEAP

                for y in range(weap.BaseYear, weap.EndYear+1):
                    val = 0  # Value that will be written into expr for y
                    for wb in region_inddom_demand_map[r]:
                        val = val + weap.ResultValue("".join([region_inddom_demand_map[r][wb]['weap_path'], ":Supply Requirement[m^3]"]), y, 1, weap_scenarios[i], y, 12, 'Total')
                    expr = "".join([expr,str(y),LIST_SEPARATOR,str(val),LIST_SEPARATOR])

                expr = "".join([expr[0:-1], ")"])
                leap.ActiveRegion = r
                leap.ActiveScenario = leap_scenarios[i]
                logging.info('\t\tRegion: ' + r)
                leap.Branches("Demand\Industry\Other\Syr Darya Water Pumping").Variables("Activity Level").Expression = expr


        #------------------------------------------------------------------------------------------------------------------------
        # Calculate LEAP
        #------------------------------------------------------------------------------------------------------------------------
        if lang == "RUS":
            msg = ["Расчет площади LEAP (итерация ", str(completed_iterations+1), ")."]
        else:
            msg = ["Calculating LEAP area (iteration ", str(completed_iterations+1), ")."]
        leap.ShowProgressBar(procedure_title, "".join(msg))
        leap.SetProgressBar(50)

        logging.info('Calculating LEAP (iteration ' + str(completed_iterations + 1) + ')')
        kill_excel()
        leap.Calculate(False)

        # Ensure that areas are saved
        logging.info('Saving LEAP and WEAP areas')
        leap.SaveArea()
        weap.SaveArea()
        logging.info('Saving versions for iteration ' + str(completed_iterations + 1))
        leap.SaveVersion('Iteration ' + str(completed_iterations + 1))
        weap.SaveVersion('Iteration ' + str(completed_iterations + 1), True) # With WEAP, can save results

        #------------------------------------------------------------------------------------------------------------------------
        # Store target results used in the convergence check
        #------------------------------------------------------------------------------------------------------------------------
        if lang == "RUS":
            msg = ["Запись результатов и проверка сходимости (итерация ", str(completed_iterations+1),")."]
        else:
            msg = ["Recording results and checking for convergence (iteration ", str(completed_iterations+1), ")."]
        leap.ShowProgressBar(procedure_title, "".join(msg))
        leap.SetProgressBar(80)

        logging.info('Checking LEAP results...')
        this_iteration_leap_results= numpy.empty((len(target_leap_results)*len(leap_scenarios)*len(leap_calc_years)), dtype=object)  # Array of target LEAP result values obtained in this iteration. Contains one set of result values for each scenario in leap_scenarios and year calculated in LEAP; results are ordered by scenario, year, and result in target_leap_results
        current_index = 0  # Index currently being written to this_iteration_leap_results/this_iteration_weap_results

        for e in target_leap_results:
            for s in leap_scenarios:
                for y in leap_calc_years:
                    # Elements in target_leap_results: Array(branch full name, variable name, region name, unit name)
                    val = leap.Branches(config_params['LEAP']['Hydropower_plants'][e]['leap_path']).Variables(config_params['LEAP']['Hydropower_plants'][e]['leap_variable']).ValueRS(leap.Regions(config_params['LEAP']['Hydropower_plants'][e]['leap_region']).Id, leap.Scenarios(s).Id, y, config_params['LEAP']['Hydropower_plants'][e]['leap_unit'])
                    if val is None:
                        logging.error('LEAP did not return a value for "{e}" in year {y} of scenario {s}')
                    this_iteration_leap_results[current_index] = val
                    current_index += 1


        if leap_macro:
            logging.info('Checking Macro results...')
            this_iteration_leapmacro_results= numpy.empty((len(target_leapmacro_results)*len(config_params['LEAP-Macro']['regions'].keys())*len(leap_scenarios)*len(leap_calc_years)), dtype=object)  # Array of target LEAP result values obtained in this iteration. Contains one set of result values for each scenario in leap_scenarios and year calculated in LEAP; results are ordered by scenario, year, and result in target_leap_results
            current_index = 0  # Index currently being written to this_iteration_leap_results/this_iteration_weap_results/this_teration_leapmacro_results

            for e in target_leapmacro_results:
                for r in config_params['LEAP-Macro']['regions']:
                    for s in leap_scenarios:
                        for y in leap_calc_years:
                            # Elements in target_leap_results: Array(branch full name, variable name, region name, unit name)
                            val = leap.Branches(config_params['LEAP']['Branches'][e]['path']).Variables(config_params['LEAP']['Branches'][e]['variable']).ValueRS(leap.Regions(r).Id, leap.Scenarios(s).Id, y)
                            if val is None:
                                logging.error('LEAP did not return a value for Macro result "{e}" in year {y} of scenario {s} for {r}')
                            this_iteration_leapmacro_results[current_index] = val
                            current_index += 1

        if lang == "RUS":
            msg = ["Запись результатов и проверка сходимости (итерация ", str(completed_iterations+1),")."]
        else:
            msg = ["Recording results and checking for convergence (iteration ", str(completed_iterations+1), ")."]
        leap.ShowProgressBar(procedure_title, "".join(msg))
        leap.SetProgressBar(85)

        logging.info('Checking WEAP results...')
        this_iteration_weap_results= numpy.empty(len(target_weap_results)*len(weap_scenarios)*(weap.EndYear - weap.BaseYear + 1), dtype=object)  # Array of target WEAP result values obtained in this iteration. Contains one set of result values for each scenario in weap_scenarios and year calculated in WEAP; results are ordered by scenario, year, and result in target_weap_results
        current_index = 0  # Index currently being written to this_iteration_leap_results/this_iteration_weap_results

        for e in target_weap_results:
            for s in weap_scenarios:
                for y in range(weap.BaseYear, weap.EndYear):
                    # Elements in target_weap_results: full branch-variable-unit path
                    val = weap.ResultValue("".join([config_params['WEAP']['Hydropower_plants'][e]['weap_path'], config_params['WEAP']['Hydropower_plants'][e]['weap_variable']]), y, 1, s, y, 12, 'Total')
                    if val is None:
                        logging.error('WEAP did not return a value for "{e}" in year {y} of scenario {s}')
                    this_iteration_weap_results[current_index] = val
                    current_index += 1

        #------------------------------------------------------------------------------------------------------------------------
        # Check for convergence (after initial run)
        #------------------------------------------------------------------------------------------------------------------------
        if completed_iterations > 0:
            logging.info('Checking whether calculations converged...')
            if lang == "RUS":
                msg = ["Запись результатов и проверка сходимости (итерация ", str(completed_iterations+1),")."]
            else:
                msg = ["Recording results and checking for convergence (iteration ", str(completed_iterations+1), ")."]
            leap.ShowProgressBar(procedure_title, "".join(msg))
            leap.SetProgressBar(95)

            results_converged = True # Tentative; may be overwritten during following convergence checks

            # For each check, allow for deviations within precision, as given by system "epsilon"
            
            for i in range(0, len(this_iteration_leap_results)):
                if abs(this_iteration_leap_results[i] - last_iteration_leap_results[i]) > abs(last_iteration_leap_results[i]) * tolerance + float_info.epsilon:
                    results_converged = False
                    break

            # Only carry out LEAP-Macro convergence checks if all LEAP-macro is turned on and all LEAP checks passed
            if leap_macro and results_converged:
                for i in range(0, len(this_iteration_leapmacro_results)):
                    if abs(this_iteration_leapmacro_results[i] - last_iteration_leapmacro_results[i]) > abs(last_iteration_leapmacro_results[i]) * tolerance + float_info.epsilon:
                        results_converged = False
                        break

            # Only carry out WEAP convergence checks if all LEAP (and LEAP-Macro) checks passed
            if results_converged :
                for i in range(0, len(this_iteration_weap_results)):
                    if abs(this_iteration_weap_results[i] - last_iteration_weap_results[i]) > abs(last_iteration_weap_results[i]) * tolerance + float_info.epsilon:
                        results_converged = False
                        break

            if results_converged:
                if lang == "RUS":
                    msg = ["Все целевые результаты WEAP и LEAP сошлись в пределах заданного допуска (", str(tolerance * 100), "%). Дополнительных итераций расчетов WEAP и LEAP не требуется."]
                else:
                    msg = ["All target WEAP and LEAP results converged to within the specified tolerance (", str(tolerance * 100), "%). No additional iterations of WEAP and LEAP calculations are needed."]
                leap.ShowProgressBar(procedure_title, "".join(msg))
                leap.SetProgressBar(100)
                logging.info("".join(msg))
                break # Break out of the iteration loop
            else:
                if completed_iterations < max_iterations:
                    logging.info('Results did not converge. Iterating...')
                else:
                    logging.info('Reached maximum number of iterations ' + str(max_iterations) + ' without converging within tolerance ' + str(tolerance * 100) + '%')
        
        # Update information for next iteration
        last_iteration_leap_results = this_iteration_leap_results
        last_iteration_weap_results = this_iteration_weap_results
        last_iteration_leapmacro_results = this_iteration_leapmacro_results

        completed_iterations += 1
        
        #------------------------------------------------------------------------------------------------------------------------
        # Calculate Macro with new results from WEAP and LEAP
        #------------------------------------------------------------------------------------------------------------------------
        if leap_macro:
            logging.info('Pushing WEAP results to Macro...')
            for leap_scenario in leap_scenarios:
                weap_scenario = scenarios_map[leap_scenario]
                
                # create directory to store WEAP outputs
                fdirmain = os.path.dirname(leap.ActiveArea.Directory)
                fdirweapoutput = os.path.join(fdirmain, "WEAP outputs")
                if not os.path.exists(fdirweapoutput):
                    os.mkdir(fdirweapoutput)
                    
                # export weap data
                dfcov, dfcovdmd, dfcrop, dfcropprice = exportcsvmodule(fdirweapoutput, fdirmain, weap_scenario, weap, CSV_ROW_SKIP)
                
                logging.info('Processing for WEAP scenario: ' + weap_scenario)
                for r, rinfo in config_params['LEAP-Macro']['regions'].items():  
                    # set file directories for WEAP to leap-macro
                    fdirmain = os.path.join(leap.ActiveArea.Directory, rinfo['directory_name'])
                    fdirmacroinput = os.path.join(fdirmain, "inputs")
                        
                    # process WEAP data for leap-macro
                    weaptomacroprocessing(weap, weap_scenario, leap_scenario, config_params, r, rinfo['weap_region'], fdirmain, fdirmacroinput, fdirweapoutput, dfcov, dfcovdmd, dfcrop, dfcropprice)

            # Run LEAP-macro
            for s in leap_scenarios:
                logging.info('Running LEAP-Macro for scenario: ' + s)
                for r, rinfo in config_params['LEAP-Macro']['regions'].items():
                    logging.info('\tRegion: ' + r)
                    macrodir = os.path.join(leap.ActiveArea.Directory,  rinfo['directory_name'], rinfo['script'])
                    exec_string = juliapath + " \"" + macrodir + "\" \"" +  s + "\" -c -p -w -v -y " + str(leap_calc_years[-1]) + " -r " + str(completed_iterations) + " --load-leap-first"
                    logging.info("\tExecuting: '" + exec_string + "'")
                    errorcode= os.system(exec_string)
                    if errorcode != 0:
                        raise RuntimeError("LEAP-Macro exited with an error")
    
    #------------------------------------------------------------------------------------------------------------------------
    #
    # Completed iterations: wrap up
    #
    #------------------------------------------------------------------------------------------------------------------------
    
    # TODO: Provide monthly values and bring them into the iteration to allow WEAP to release water for other purposes if not needed for hydropower
    # if lang == "RUS":
        # msg ="Заключительный шаг: Перемещение выработки гидроэлектроэнергии в WEAP и повторный запуск WEAP..."
    # else :
        # msg = "Final Step: Moving hydropower generation to WEAP and rerunning WEAP..."
    # leap.ShowProgressBar(procedure_title, "".join(msg))
    # leap.SetProgressBar(95)
    
    # # TODO: Make this generic -- right now assumes "Run of River" is present in path with that capitalization
    # logging.info("Final Step: Moving hydropower generation to WEAP and rerunning WEAP...")
    # weap_hydro_branches = config_params['WEAP']['Hydropower_plants'].keys()
    # for i in range(0, len(weap_scenarios)):
        # weap.ActiveScenario = weap_scenarios[i]
        # for wb in weap_hydro_branches:
            # weap_path = config_params['WEAP']['Hydropower_plants'][wb]['weap_path']
            # logging.info('WEAP hydropower reservoir: ' + wb)
            # if 'Run of River' in weap_path: 
                # logging.info('This is a Run of River hydropower plant, ignoring....')
            # else:
                # new_data = 'Interp('
                # for y in range(weap.BaseYear, weap.EndYear):
                    # weap_branch_energydemand = 0.0
                    # leap_hpps = config_params['WEAP']['Hydropower_plants'][wb]['leap_hpps']
                    # for lb in leap_hpps:
                        # leap_path = config_params['LEAP']['Hydropower_plants'][lb]['leap_path']
                        # leap_region = config_params['LEAP']['Hydropower_plants'][lb]['leap_region']
                        # weap_branch_energydemand += leap.Branches(leap_path).Variables('Energy Generation').ValueRS(leap.regions(leap_region).id, leap_scenarios[i], y, 'GWh') 
                    # new_data ="".join([new_data, str(y), LIST_SEPARATOR, str(weap_branch_energydemand), LIST_SEPARATOR])
                # new_data ="".join([new_data[0:-1], ")"]) # remove last list separator and close bracket
                # weap.Branches(config_params['WEAP']['Hydropower_plants'][wb]['weap_path']).Variables('Energy Demand').Expression = new_data # Cannot specify unit, but is GWh in WEAP

    # logging.info('Calculating WEAP one last time...')
    # weap.Calculate()
    # while weap.IsCalculating :
        # leap.Sleep(1000)

    if lang == "RUS":
        msg ="Завершена процедура интеграции WEAP-LEAP."
    else :
        msg = "Completed WEAP-LEAP integration procedure."
    leap.ShowProgressBar(procedure_title, "".join(msg))
    leap.SetProgressBar(100)
    leap.CloseProgressBar()
    
    # TODO: This should not be needed
    weap.SaveArea()
    leap.SaveArea()

    tet = time.time()
    total_elapsed_time = tet - tst
    logging.info('Total elapsed time: ' + hms_from_sec(total_elapsed_time))

# TODO: Provide command-line interface
main_integration(user_interface=True, tolerance=0.1, max_iterations=3)
