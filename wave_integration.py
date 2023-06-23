import sys
from errno import WSAEDQUOT
from ntpath import altsep
import win32com.client as win32
import win32gui
import yaml
import time
from winreg import *
from calendar import monthrange
import os # os.path, os.system
from sys import float_info
import psutil
import numpy as np
import re
import uuid
import logging
from collections import OrderedDict # Not necessary with Python 3.7+

import gettext, locale, ctypes
# Allow a user to "short-circuit" the system language with an environment variable
if os.environ.get('LANG') is not None:
    language = os.environ['LANG']
elif os.environ.get('LANGUAGE') is not None:
    language = os.environ['LANGUAGE']
else:
    language = locale.windows_locale[ctypes.windll.kernel32.GetUserDefaultUILanguage()]
if gettext.find('wave_integration', localedir='locale', languages=[language]) is not None:
    transl = gettext.translation('wave_integration', localedir='locale', languages=[language])
    transl.install()
else:
    gettext.install('wave_integration')

# Load gettext and install translator before importing other local scripts
from utils.julia import get_julia_path
from utils.leap_weap import add_leap_data_to_weap_interp, get_leap_timeslice_info
from utils.weap_macro import export_csv_module, weap_to_macro_processing

#==================================================================================================#
# Script for integrating WAVE WEAP and LEAP models.
#
# Copyright © 2022-2023: Stockholm Environment Institute U.S.
#==================================================================================================#
run_uuid = str(uuid.uuid4().hex)
logfile = "wave_integration_" + run_uuid + ".log"
print('Sending to log file "{f}"'.format(f = logfile), flush = True)
logging.basicConfig(filename=logfile,
                    format='[%(asctime)s.%(msecs)03d]%(levelname)s:%(message)s',
                    encoding='utf-8',
                    level=logging.INFO,
                    datefmt='%Y-%m-%d %H:%M:%S')

tst = time.time()

##############################################################
#
# Functions used by the main routine
#
##############################################################
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
        msg = _('The active {a} area does not contain the required variable {b}:{v} with unit {v}. Please check the area and try again. Exiting...').format(a = app_name, b = branch_path, v = variable, u = unit)
        logging.error(msg)
        sys.exit(msg)

# function that checks whether region (this argument should be a region name) exists in the active LEAP area. If it does, enables calculations for region.
def check_region(leap, region) :
    check_passed = False
    if leap.Regions.Exists(region) :
        leap.Regions(region).ResultsShown = True
        check_passed = True
    if not check_passed :
        msg = _('Could not enable calculations for region {r} in the active LEAP area. Please check the area and try again. Exiting...').format(r = region)
        logging.error(msg)
        sys.exit(msg)

# function that disables all scenarios in current area in app (which should be a LEAP or WEAP application object).
def disable_all_scenario_calcs(app):
    for s in app.Scenarios :
        s.ResultsShown = False

# function that returns an array of years calculated in LEAP.
def get_leap_calc_years(app) :
    leap_calculated_years = []
    last_index = -1
    for y in range(app.FirstScenarioYear, app.EndYear+1) :
        if y % app.resultsEvery == 0:
            leap_calculated_years.append(y)
            last_index += 1
    return leap_calculated_years
    
def get_leap_region_ids(leap) :
    leap_region_ids = {}
    for r in leap.Regions:
        leap_region_ids[r.Name] = r.ID
    return leap_region_ids
    
def get_leap_scenario_ids(leap) :
    leap_scenario_ids = {}
    for s in leap.Scenarios:
        leap_scenario_ids[s.Name] = s.ID
    return leap_scenario_ids

# Convert a "long" index based on looping over multiple lists into corresponding elements from the different lists
def index_to_elements(i, *lists_tuple):
    lists = list(reversed(list(lists_tuple)))
    elements = []
    i_rem = i
    for (l, llen) in zip(lists, [len(l) for l in lists]):
        elements.append(l[i_rem % llen])
        i_rem //= llen
    return list(reversed(elements))
    
# function to clear out any running instances of Excel (no return value)
def kill_excel():
    ps_re = re.compile(r'excel', flags=re.IGNORECASE)
    for proc in psutil.process_iter():
        if ps_re.search(proc.name()) is not None:
            proc.kill()

#==================================================================================================#
#                                         MAIN ROUTINE                                             #
#==================================================================================================#
def main_integration(tolerance, max_iterations):
    """Main code: call to run the integrated models
    
    Input arguments:
        tolerance: A number less than 1 (e.g., 0.1, 0.05) that sets the tolerance for discrepancies between values in subsequent runs
        max_iterations: Maximum iterations if results do not converge
    Returns: Nothing    
    """

    #------------------------------------------------------------------------------------------------------------------------
    #
    # Define constants
    #
    #------------------------------------------------------------------------------------------------------------------------
    LIST_SEPARATOR = get_list_separator() # Windows list separator character (e.g., ",")
    if not len(LIST_SEPARATOR) == 1 :
        msg = _('The Windows list separator is longer than 1 character, which is incompatible with the WEAP-LEAP integration procedure. Exiting...')
        logging.error(msg)
        sys.exit(msg)

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
        msg = _('WAVE integration: Cannot start LEAP and WEAP. Exiting...')
        logging.error(msg)
        sys.exit(msg)
        
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

    procedure_title = _('WEAP-LEAP Integration Procedure')
    msg = _('Initiating integration procedure...')

    shell.AppActivate("LEAP: ")
    leap.ShowProgressBar(procedure_title, msg)

    if leap_macro:
        # get Julia install location path
        juliapath = get_julia_path(shell)
        if juliapath == None:
            msg = _('Could not locate the Julia executable. Try adding the path to the executable to the Windows PATH environment variable.')
            logging.error(msg)
            sys.exit(msg)
        # Get Macro models folder path and create it if it doesn't exist
        macromodelspath = os.path.normpath(os.path.join(leap.ActiveArea.Directory, "..\\..", config_params['LEAP-Macro']['Folder']))
        if not os.path.exists(macromodelspath):
            os.makedirs(macromodelspath)

    # Get path for storing Excel files and create it if it doesn't exist
    hydroexcelpath = os.path.normpath(os.path.join(leap.ActiveArea.Directory, "..\\..", config_params['LEAP']['Folder']))
    if not os.path.exists(hydroexcelpath):
        os.makedirs(hydroexcelpath)

    weap.ActiveArea = config_params['WEAP']['Area']
    wait_apps(weap, leap)
    leap.ActiveArea = config_params['LEAP']['Area']
    wait_apps(leap, weap)

    leap_ts_info = get_leap_timeslice_info(leap, config_params['LEAP']['Months'])
    leap_region_ids = get_leap_region_ids(leap)
    leap_scenario_ids = get_leap_scenario_ids(leap)

    # open correct leap area and select scenarios and years to be calculated
    title = _('Open LEAP Area')
    msg1 = _('Please open the WAVE model (area) in LEAP (the same as defined in config.yml) and select the scenarios and years you would like to run.')
    msg2 = _('NOTE: LEAP settings determine calculated scenarios. Scenario selection in WEAP will be overwritten.')
    print('{t}:\n• {m1}\n •{m2}'.format(t = title, m1 = msg1, m2=msg2), flush = True)
    
    #------------------------------------------------------------------------------------------------------------------------
    #
    # Validate LEAP and WEAP areas
    #
    #------------------------------------------------------------------------------------------------------------------------
    # if lang == "RUS" : msg = "Валидирование областей WEAP и LEAP."
    # else : msg = _('Validating WEAP and LEAP areas')
    msg = _('Validating WEAP and LEAP areas')
    leap.ShowProgressBar(procedure_title, msg)
    leap.SetProgressBar(5)

    # validate branches
    logging.info(_('Validating branches in WEAP and LEAP'))
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
    logging.info(_('Running the model for regions:'))
    calculated_leap_regions = config_params['LEAP']['Regions']
    for r in calculated_leap_regions :
        logging.info('\t' + r)
        check_region(leap, r)

    # validate hydropower plants in leap
    logging.info(_('Including LEAP hydropower plants:'))
    for b in config_params['LEAP']['Hydropower_plants'] :
        logging.info('\t' + b)
        check_branch_var(leap, config_params['LEAP']['Hydropower_plants'][b]['leap_path'], "Maximum Availability", "Percent")

    # validate hydropower reservoirs in weap
    logging.info(_('Including WEAP hydropower reservoirs:'))
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
    # if lang == "RUS": msg = "Определение сценариев для расчета."
    # else : msg = _('Identifying scenarios to calculate')
    msg = _('Identifying scenarios to calculate')
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
        msg = _('At least one scenario must be calculated in the active {a} area. Exiting...').format(a = runfrom_app)
        logging.error(msg)
        sys.exit(msg)
    elif len(scenarios_map)== 0:
        msg = _('Could not find scenarios in the active {a2} area corresponding to the scenarios calculated in the active {a1} area. Exiting...').format(a1 = runfrom_app, a2 = other_app)
        logging.error(msg)
        sys.exit(msg)

    # Populate leap_scenarios and weap_scenarios
    if runfrom_app == "LEAP" or runfrom_app == "WEAP":
        leap_scenarios = list(scenarios_map.keys())
        weap_scenarios = list(scenarios_map.values())
    else :
        msg = _('Unsupported application: "{a}". Exiting...').format(a = runfrom_app)
        logging.error(msg)
        sys.exit(msg)

    msg1 = _('Calculating the following scenarios:')
    logging.info(msg1)

    for k in scenarios_map.keys():
        msg2 = '{l} (LEAP) ←→ {w} (WEAP)'.format(l = k, w = scenarios_map[k])
        logging.info('\t' + msg2)
        msg = " ".join([msg1,msg2])
        leap.ShowProgressBar(procedure_title, msg)
        leap.SetProgressBar(10)

    # get calculated years in leap
    leap_calc_years = get_leap_calc_years(leap)

    # Clear hydropower reservoir energy demand from WEAP scenarios
    logging.info(_('Clearing hydropower reservoir energy demand from WEAP scenarios to avoid forcing model with results from past integration runs.'))
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
            logging.info(_('Running LEAP-Macro for scenario: {s}').format(s = s))
            for r, rinfo in config_params['LEAP-Macro']['Regions'].items():
                logging.info('\t' + _('Region: {r}').format(r = r))
                macrodir = os.path.join(macromodelspath,  rinfo['directory_name'], rinfo['script'])
                exec_string = juliapath + " \"" + macrodir + "\" \"" +  s + "\" -c -p -v -y " + str(leap_calc_years[-1])
                logging.info('\t' + _('Executing: {e}').format(e = exec_string))
                errorcode= os.system(exec_string)
                if errorcode != 0:
                    msg = _('LEAP-Macro exited with an error')
                    logging.error(msg)
                    sys.exit(msg)

    #------------------------------------------------------------------------------------------------------------------------
    #
    # Start iterations
    #
    #------------------------------------------------------------------------------------------------------------------------
    completed_iterations = 0
    results_converged = False
    # set up target results for convergence checks during iterative calculations, by scenario
    
    target_leap_results = list(config_params['LEAP']['Hydropower_plants'].keys())
    target_weap_results = list(config_params['WEAP']['Hydropower_plants'].keys())
    if leap_macro:
        target_leapmacro_results = config_params['LEAP-Macro']['LEAP']['target_variables']

    while completed_iterations < max_iterations :
        msg = _('Moving demographic and macroeconomic assumptions from LEAP to WEAP (iteration {i})').format(i = completed_iterations+1)
        leap.ShowProgressBar(procedure_title, "".join(msg))
        leap.SetProgressBar(20)

        #------------------------------------------------------------------------------------------------------------------------
        # Push demographic and macroeconomic key assumptions from LEAP to WEAP
        #------------------------------------------------------------------------------------------------------------------------
        # Values from LEAP base year to end year are embedded in WEAP Interp expressions
        count = 0
        logging.info(_('Pushing demographic and macroeconomic drivers from LEAP to WEAP'))
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
                msg = _('Unit multiplier for variable "{v}" is unknown. Exiting...').format(v = leap_variable)
                logging.error(msg)
                sys.exit(msg)
            add_leap_data_to_weap_interp(weap, leap, weap_scenarios, leap_scenarios, config_params['WEAP']['Branches'][k]['path'], config_params['WEAP']['Branches'][k]['variable'],  leap_path, leap_variable, leap_region, unit_multiplier, LIST_SEPARATOR)

            count += 1
            
        logging.info(_('Pushed {n} variable(s) to WEAP').format(n = count))
            
        #------------------------------------------------------------------------------------------------------------------------
        # Calculate WEAP
        #------------------------------------------------------------------------------------------------------------------------
        msg = _('Calculating WEAP (iteration {i})').format(i = completed_iterations+1)
        leap.ShowProgressBar(procedure_title, msg)
        leap.SetProgressBar(30)

        logging.info(_('Calculating WEAP (iteration {i})').format(i = completed_iterations + 1))
        weap.Calculate(0, 0, False) # Only calculate what needs calculation
        while weap.IsCalculating :
           leap.Sleep(1000)

        logging.info(_('Finished calculating WEAP. Moving hydropower maximum availabilities from WEAP to LEAP....'))

        #------------------------------------------------------------------------------------------------------------------------
        # Move hydropower availability information from WEAP to LEAP.
        #------------------------------------------------------------------------------------------------------------------------
        # Availability information saved to Excel files specific to WEAP branches and LEAP scenarios.
        #   Note: Excel used since LEAP's performance is extremely poor when reading from text files.
        msg = _('Moving hydropower availability from WEAP to LEAP (iteration {i})').format(i = completed_iterations+1)
        leap.ShowProgressBar(procedure_title, msg)
        leap.SetProgressBar(40)

        fs_obj = win32.Dispatch('Scripting.FileSystemObject') # Instance of scripting.FileSystemObject; used to manipulate CSV files in following loop
        excel = win32.Dispatch('Excel.Application') # Excel Application object used to create data files
        excel.ScreenUpdating = False

        weap_hydro_branches = config_params['WEAP']['Hydropower_plants'].keys()
        for i in range(0, len(weap_scenarios)):
            logging.info(_('WEAP scenario: {s}').format(s = weap_scenarios[i]))
            leap_scenario_id = leap_scenario_ids[leap_scenarios[i]]
            for wb in weap_hydro_branches:
                logging.info('\t' + _('WEAP hydropower reservoir: {r}').format(r = wb))
                xlsx_file = "".join(["hydro_availability_wbranch", str(weap.Branches(config_params['WEAP']['Hydropower_plants'][wb]['weap_path']).Id), "_lscenario", str(leap_scenario_id), ".xlsx" ])
                xlsx_path = os.path.join(hydroexcelpath, xlsx_file)  # Full path to XLSX file being written
                xlsx_path = fr"{xlsx_path}" # TODO: Is this needed with os.path.join?
                csv_path = os.path.join(hydroexcelpath, "temp.csv")  # Temporary CSV file used to expedite creation of XLSX files

                if os.path.isfile(xlsx_path): os.remove(xlsx_path)
                if os.path.isfile(csv_path): os.remove(csv_path)

                ts = fs_obj.CreateTextFile(csv_path, True, False)

                num_lines_written = 0 # Number of lines written to CSV file

                # check unit
                weap_unit= weap.Branches(config_params['WEAP']['Hydropower_plants'][wb]['weap_path']).Variables('Hydropower Generation').Unit
                if not weap_unit == 'GJ':
                    msg = _('Energy Generation in WEAP has to be in Gigajoules. Exiting...')
                    logging.error(msg)
                    sys.exit(msg)
                # if correct unit pull weap values from weap baseyear to endyear, remove first item, convert to GJ, and round)
                weap_hpp_gen = weap.Branches(config_params['WEAP']['Hydropower_plants'][wb]['weap_path']).Variables('Hydropower Generation').ResultValues(weap.BaseYear, weap.EndYear, weap_scenarios[i])[1:]

                # check that there are values for every month
                if not len(weap_hpp_gen)%12 == 0:
                    msg = _('Energy generation in WEAP is not monthly or not available for every simulation month. Exiting...')
                    logging.error(msg)
                    sys.exit(msg)
                y_range = range(weap.BaseYear, weap.EndYear+1)
                
                for y in y_range:
                    leap_capacity_year = y
                    if leap.BaseYear > y :
                        leap_capacity_year = leap.BaseYear
                    if leap.EndYear < y :
                        leap_capacity_year = leap.EndYear
                    weap_branch_capacity = 0  # Capacity in LEAP corresponding to WEAP branch [MW]
                    leap_hpps = config_params['WEAP']['Hydropower_plants'][wb]['leap_hpps']
                    for lb in leap_hpps:
                        leap_path = config_params['LEAP']['Hydropower_plants'][lb]['leap_path']
                        leap_region = config_params['LEAP']['Hydropower_plants'][lb]['leap_region']
                        leap_region_id = leap_region_ids[leap_region]
                        # TODO: Find the unit using Variable.DataUnitID, convert using Unit.ConversionFactor; set a target unit and store its conversion factor
                        # Can't specify unit when querying data variables, but unit for Exogenous Capacity is MW
                        leap_exog_capacity = leap.Branches(leap_path).Variable("Exogenous Capacity").ValueRS(leap_region_id, leap_scenario_id, leap_capacity_year)
                        leap_minimum_capacity = leap.Branches(leap_path).Variable("Minimum Capacity").ValueRS(leap_region_id, leap_scenario_id, leap_capacity_year)
                        weap_branch_capacity += max(leap_exog_capacity, leap_minimum_capacity)

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
                    logging.info('\t\t' + _('Saving as Excel with filename "{f}"').format(f = xlsx_file))
                    try:
                        excel.Workbooks.OpenText(csv_path, 2, 1, 1, -4142, False, False, False, True)
                        excel.ActiveWorkbook.SaveAs(xlsx_path, 51)
                        excel.ActiveWorkbook.Close()
                    except Exception as err:
                        logging.error(_('Could not save to Excel: {e}').format(e = str(err)))
                    finally:
                        excel.Application.Quit()
                    if not os.path.isfile(xlsx_path):
                        # TODO: This should be default expression, not existing expression, in case this is a second iteration
                        msg = _('Excel file "{f}" not written correctly: file does not exist. Will use existing expression.').format(f = xlsx_file)
                        logging.warning(msg)
                    else:
                        # Update LEAP Maximum Availability expression
                        leap_hpps = config_params['WEAP']['Hydropower_plants'][wb]['leap_hpps']
                        for lhpp in leap_hpps:
                            logging.info('\t\t' + _('Assigning to LEAP hydropower plant: {h}').format(h = lhpp))
                            lhpp_path = config_params['LEAP']['Hydropower_plants'][lhpp]['leap_path']
                            lhpp_region = config_params['LEAP']['Hydropower_plants'][lhpp]['leap_region']
                            leap.ActiveRegion = lhpp_region
                            leap.ActiveScenario = leap_scenarios[i]
                            leap.Branches(lhpp_path).Variable("Maximum Availability").Expression = "".join(["ReadFromExcel(" , xlsx_path , ", A1:C", str(num_lines_written), ")"])

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
        msg = _('Moving water pumping information from WEAP to LEAP (iteration {i}), agricultural use').format(i = completed_iterations+1)
        leap.ShowProgressBar(procedure_title, "".join(msg))
        leap.SetProgressBar(50)

        logging.info(_('Moving water pumping information from WEAP to LEAP'))
        region_ag_demand_map = config_params['WEAP']['Agricultural regions']
        for i in range(0, len(weap_scenarios)):
            logging.info('\t' + _('Scenario: {w} (WEAP)/{l} (LEAP)').format(w = weap_scenarios[i], l = leap_scenarios[i]))
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
                logging.info('\t\t' + _('Region: {r}').format(r = r))
                leap.Branches("Demand\Agriculture\Syr Darya\Water demand").Variables("Activity Level").Expression = expr
		# END: Move Syr Darya agricultural water requirements from WEAP to LEAP.

        #------------------------------------------------------------------------------------------------------------------------
        # Move industrial and domestic water requirements from WEAP to LEAP
        #------------------------------------------------------------------------------------------------------------------------
        logging.info(_('Moving industrial water requirements from WEAP to LEAP'))
        msg = _('Moving water pumping information from WEAP to LEAP (iteration {i}), industrial and domestic use').format(i = completed_iterations+1)
        leap.ShowProgressBar(procedure_title, msg)
        leap.SetProgressBar(55)

        region_inddom_demand_map = config_params['WEAP']['Industrial and domestic regions']
        for i in range(0, len(weap_scenarios)):
            logging.info('\t' + _('Scenario: {w} (WEAP)/{l} (LEAP)').format(w = weap_scenarios[i], l = leap_scenarios[i]))
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
                logging.info('\t\t' + _('Region: {r}').format(r = r))
                leap.Branches("Demand\Industry\Other\Syr Darya Water Pumping").Variables("Activity Level").Expression = expr

        #------------------------------------------------------------------------------------------------------------------------
        # Calculate LEAP
        #------------------------------------------------------------------------------------------------------------------------
        msg = _('Calculating LEAP area (iteration {i})').format(i = completed_iterations+1)
        leap.ShowProgressBar(procedure_title, msg)
        leap.SetProgressBar(50)

        logging.info(msg)
        kill_excel()
        leap.Calculate(False)

        # Ensure that areas are saved
        logging.info(_('Saving LEAP and WEAP areas'))
        leap.SaveArea()
        weap.SaveArea()
        logging.info(_('Saving versions for iteration {i}').format(i = completed_iterations + 1))
        version_comment = _('Iteration {i} - {u}').format(i = completed_iterations + 1, u = run_uuid)
        leap.SaveVersion(version_comment, True) # Save results
        weap.SaveVersion(version_comment, True) # Save results

        #------------------------------------------------------------------------------------------------------------------------
        # Store target results used in the convergence check
        #------------------------------------------------------------------------------------------------------------------------
        msg = _('Recording results and checking for convergence (iteration {i})').format(i = completed_iterations+1)
        leap.ShowProgressBar(procedure_title, msg)
        leap.SetProgressBar(80)
        
        this_iteration_leap_results = {}
        this_iteration_leapmacro_results = {}
        this_iteration_weap_results = {}

        for sl in leap_scenarios:
            leap_scenario_id = leap_scenario_ids[sl]
            sw = scenarios_map[sl]
            logging.info(_('Checking results for scenario: {w} (WEAP)/{l} (LEAP)').format(w = sw, l = sl))
            
            logging.info('\t' + _('Checking LEAP results...'))
            # Create an array of target LEAP result values obtained in this iteration
            leap_results_size = len(target_leap_results) * len(leap_calc_years)
            this_iteration_leap_results[sl] = np.empty(leap_results_size, dtype=object)
            
            current_index = 0
            for e in target_leap_results:
                leap_var = leap.Branches(config_params['LEAP']['Hydropower_plants'][e]['leap_path']).Variables(config_params['LEAP']['Hydropower_plants'][e]['leap_variable'])
                leap_unit = config_params['LEAP']['Hydropower_plants'][e]['leap_unit']
                leap_region_id = leap_region_ids[config_params['LEAP']['Hydropower_plants'][e]['leap_region']]
                for y in leap_calc_years:
                    val = leap_var.ValueRS(leap_region_id, leap_scenario_id, y, leap_unit)
                    if val is None:
                        logging.error(_('LEAP did not return a value for "{e}" in year {y} of scenario {s}').format(e = e, y = y, s = sl))
                    this_iteration_leap_results[sl][current_index] = val
                    current_index += 1


            if leap_macro:
                logging.info('\t' + _('Checking Macro results...'))
                # Create an array of target Macro result values obtained in this iteration and stored in LEAP
                leapmacro_results_size = len(target_leapmacro_results) * len(config_params['LEAP-Macro']['Regions'].keys()) * len(leap_calc_years)
                this_iteration_leapmacro_results[sl] = np.empty(leapmacro_results_size, dtype=object)
                
                current_index = 0
                for e in target_leapmacro_results:
                    leap_var = leap.Branches(config_params['LEAP']['Branches'][e]['path']).Variables(config_params['LEAP']['Branches'][e]['variable'])
                    for r in config_params['LEAP-Macro']['Regions']:
                        leap_region_id = leap_region_ids[r]
                        for y in leap_calc_years:
                            val = leap_var.ValueRS(leap_region_id, leap_scenario_id, y)
                            if val is None:
                                logging.error(_('LEAP did not return a value for Macro result "{e}" in year {y} of scenario {s} for {r}').format(e = e, y = y, s = sl, r = r))
                            this_iteration_leapmacro_results[sl][current_index] = val
                            current_index += 1

            logging.info('\t' + _('Checking WEAP results...'))
            # Create an array of target WEAP result values obtained in this iteration
            weap_results_size = len(target_weap_results) * (weap.EndYear - weap.BaseYear + 1)
            this_iteration_weap_results[sw] = np.empty(weap_results_size, dtype=object)
            
            current_index = 0
            for e in target_weap_results:
                weap_pathvar = "".join([config_params['WEAP']['Hydropower_plants'][e]['weap_path'], config_params['WEAP']['Hydropower_plants'][e]['weap_variable']])
                for y in range(weap.BaseYear, weap.EndYear + 1):
                    val = weap.ResultValue(weap_pathvar, y, 1, sw, y, 12, 'Total')
                    if val is None:
                        logging.error(_('WEAP did not return a value for "{e}" in year {y} of scenario {s}').format(e = e, y = y, s = sw))
                    this_iteration_weap_results[sw][current_index] = val
                    current_index += 1

        #------------------------------------------------------------------------------------------------------------------------
        # Check for convergence (after initial run)
        #------------------------------------------------------------------------------------------------------------------------
        if completed_iterations > 0:
            logging.info(_('Checking whether calculations converged...'))
            msg = _('Recording results and checking for convergence (iteration {i})').format(i = completed_iterations+1)
            leap.ShowProgressBar(procedure_title, msg)
            leap.SetProgressBar(95)

            for sl in leap_scenarios:
                sw = scenarios_map[sl]
                
                logging.info('\t' + _('Checking convergence for scenario: {w} (WEAP)/{l} (LEAP)').format(w = sw, l = sl))

                results_converged = True # Tentative; may be overwritten during following convergence checks

                # For each check, allow for deviations within machine precision, as given by system "epsilon"
                
                for i in range(0, len(this_iteration_leap_results[sl])):
                    if abs(this_iteration_leap_results[sl][i] - last_iteration_leap_results[sl][i]) > abs(last_iteration_leap_results[sl][i]) * tolerance + float_info.epsilon:
                        diff_loc = index_to_elements(i, target_leap_results, leap_calc_years)
                        logging.info('\t\t' + _('Difference exceeded tolerance for LEAP result "{e}" in year {y}: previous value = {p}, current value = {c}').format(e = diff_loc[0], y = diff_loc[1], p = last_iteration_leap_results[sl][i], c = this_iteration_leap_results[sl][i]))
                        results_converged = False
                        break

                # Only carry out LEAP-Macro convergence checks if all LEAP-Macro is turned on and all LEAP checks passed
                if leap_macro and results_converged:
                    for i in range(0, len(this_iteration_leapmacro_results[sl])):
                        if abs(this_iteration_leapmacro_results[sl][i] - last_iteration_leapmacro_results[sl][i]) > abs(last_iteration_leapmacro_results[sl][i]) * tolerance + float_info.epsilon:
                            diff_loc = index_to_elements(i, target_leapmacro_results, list(config_params['LEAP-Macro']['Regions'].keys()), leap_calc_years)
                            logging.info('\t\t' + _('Difference exceeded tolerance for LEAP-Macro result "{e}" in year {y} for region {r}: previous value = {p}, current value = {c}').format(e = diff_loc[0], y = diff_loc[2], r = diff_loc[1], p = last_iteration_leap_results[sl][i], c = this_iteration_leap_results[sl][i]))
                            results_converged = False
                            break

                # Only carry out WEAP convergence checks if all LEAP (and LEAP-Macro) checks passed
                if results_converged :
                    for i in range(0, len(this_iteration_weap_results[sw])):
                        if abs(this_iteration_weap_results[sw][i] - last_iteration_weap_results[sw][i]) > abs(last_iteration_weap_results[sw][i]) * tolerance + float_info.epsilon:
                            diff_loc = index_to_elements(i, target_weap_results, weap.EndYear - weap.BaseYear + 1)
                            logging.info('\t\t' + _('Difference exceeded tolerance for WEAP result "{e}" in year {y}: previous value = {p}, current value = {c}').format(e = diff_loc[0], y = diff_loc[1], p = last_iteration_weap_results[sw][i], c = this_iteration_weap_results[sw][i]))
                            results_converged = False
                            break

                if results_converged:
                    msg = '\t\t' + _('All target WEAP and LEAP results converged to within the specified tolerance ({t}%). No additional iterations of WEAP and LEAP calculations are needed for this scenario.').format(t = tolerance * 100)
                    logging.info(msg)
                    # Remove this scenario from lists
                    del scenarios_map[sl]
                    del this_iteration_leap_results[sl]
                    del this_iteration_leapmacro_results[sl]
                    del this_iteration_weap_results[sw]
                    continue # Go to next scenario, if any
                else:
                    logging.info('\t\t' + _('Results did not converge for this scenario.'))
        
            # Are any scenarios left?
            if len(scenarios_map) == 0:
                msg = _('All target WEAP and LEAP results converged to within the specified tolerance ({t}%) for all scenarios.').format(t = tolerance * 100)
                leap.ShowProgressBar(procedure_title, msg)
                leap.SetProgressBar(100)
                logging.info(msg)
                break # Break out of the iteration loop
            else:
                if completed_iterations < max_iterations:
                    logging.info(_('Results have not converged in at least one scenario. Iterating...'))
                else:
                    logging.info(_('Reached maximum number of iterations {m} without converging within tolerance {t}% for at least one scenario').format(m = max_iterations, t = tolerance * 100))
                    break # Break out of the iteration loop

        # Re-populate leap_scenarios and weap_scenarios
        leap_scenarios = list(scenarios_map.keys())
        weap_scenarios = list(scenarios_map.values())

        # Update information for next iteration
        last_iteration_leap_results = this_iteration_leap_results
        last_iteration_weap_results = this_iteration_weap_results
        last_iteration_leapmacro_results = this_iteration_leapmacro_results

        completed_iterations += 1
        
        #------------------------------------------------------------------------------------------------------------------------
        # Calculate Macro with new results from WEAP and LEAP
        #------------------------------------------------------------------------------------------------------------------------
        if leap_macro:
            logging.info(_('Pushing WEAP results to Macro...'))
            for leap_scenario in leap_scenarios:
                weap_scenario = scenarios_map[leap_scenario]
                
                # create directory to store WEAP outputs
                fdirmain = macromodelspath
                fdirweapoutput = os.path.join(fdirmain, "WEAP outputs")
                if not os.path.exists(fdirweapoutput):
                    os.mkdir(fdirweapoutput)
                    
                # export weap data
                dfcov, dfcovdmd, dfcrop, dfcropprice = export_csv_module(fdirweapoutput, fdirmain, weap_scenario, weap, CSV_ROW_SKIP)
                
                logging.info(_('Processing for WEAP scenario: {s}').format(s = weap_scenario))
                for r, rinfo in config_params['LEAP-Macro']['Regions'].items():  
                    # set file directories for WEAP to LEAP-Macro
                    fdirmacroinput = os.path.join(macromodelspath, rinfo['directory_name'], "inputs")
                        
                    # process WEAP data for LEAP-Macro
                    weap_to_macro_processing(weap_scenario, leap_scenario, config_params, r, rinfo['weap_region'], fdirmacroinput, fdirweapoutput, dfcov, dfcovdmd, dfcrop, dfcropprice)

            # Run LEAP-Macro
            for s in leap_scenarios:
                logging.info(_('Running LEAP-Macro for scenario: {s}').format(s = s))
                for r, rinfo in config_params['LEAP-Macro']['Regions'].items():
                    logging.info('\t' + _('Region: {r}').format(r = r))
                    macrodir = os.path.join(macromodelspath,  rinfo['directory_name'], rinfo['script'])
                    exec_string = juliapath + " \"" + macrodir + "\" \"" + s + "\"" + \
                                    " -c -p -w -v" + \
                                    " -y " + str(leap_calc_years[-1]) + \
                                    " -u \"" + version_comment + "\"" + \
                                    " -r " + str(completed_iterations) + \
                                    " --load-leap-first"
                    logging.info('\t' + _('Executing: {e}').format(e = exec_string))
                    errorcode= os.system(exec_string)
                    if errorcode != 0:
                        msg = _('LEAP-Macro exited with an error')
                        logging.error(msg)
                        sys.exit(msg)
    
    #------------------------------------------------------------------------------------------------------------------------
    #
    # Completed iterations: wrap up
    #
    #------------------------------------------------------------------------------------------------------------------------
    
    # TODO: Provide monthly values and bring them into the iteration to allow WEAP to release water for other purposes if not needed for hydropower
    # TODO: Replace older style of translation with gettext strings
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
            # logging.info(_('WEAP hydropower reservoir: {r}').format(r = wb))
            # if 'Run of River' in weap_path: 
                # logging.info(_('This is a Run of River hydropower plant, ignoring....'))
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

    # logging.info(_('Calculating WEAP one last time...'))
    # weap.Calculate(0, 0, False) # Only calculate if needed
    # while weap.IsCalculating :
        # leap.Sleep(1000)

    msg = _('Completed WEAP-LEAP integration procedure')
    leap.ShowProgressBar(procedure_title, msg)
    leap.SetProgressBar(100)
    leap.CloseProgressBar()
    logging.info(msg)
    
    # This should not be needed, but being thorough
    weap.SaveArea()
    leap.SaveArea()

    tet = time.time()
    total_elapsed_time = tet - tst
    logging.info(_('Total elapsed time: {t}').format(t = hms_from_sec(total_elapsed_time)))

# TODO: Provide command-line interface
main_integration(tolerance=0.1, max_iterations=5)
