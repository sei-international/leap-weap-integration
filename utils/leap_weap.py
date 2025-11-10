import os
import csv
import yaml
import re
import time
import sys
import win32com.client as win32
import logging
from collections import OrderedDict # Not necessary with Python 3.7+
import ctypes, threading # needed for checking cursor
#import win32gui, win32con # needed for checking cursor
from ctypes import wintypes  # needed for checking cursor
from contextlib import contextmanager  # needed for checking cursor

# Handle the missing value entry "-" in LEAP
def leapfloat(x):
    if x == '-':
        return 0.0
    else:
        return float(x)

user32 = ctypes.WinDLL("user32", use_last_error=True)

class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

# HCURSOR is not defined in ctypes.wintypes on many Python builds; use HANDLE.
try:
    HCURSOR = wintypes.HCURSOR  # if present on your build
except AttributeError:
    HCURSOR = wintypes.HANDLE   # correct fallback everywhere

class CURSORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize",      wintypes.DWORD),
        ("flags",       wintypes.DWORD),
        ("hCursor",     HCURSOR),       # ← use alias instead of wintypes.HCURSOR
        ("ptScreenPos", POINT),
    ]

GetCursorInfo = user32.GetCursorInfo
GetCursorInfo.argtypes = [ctypes.POINTER(CURSORINFO)]
GetCursorInfo.restype  = wintypes.BOOL

def _safe_get_cursor_handle():
    """Return HCURSOR (int-like) or None if unreadable this tick."""
    ci = CURSORINFO(cbSize=ctypes.sizeof(CURSORINFO))
    ok = GetCursorInfo(ctypes.byref(ci))
    if not ok:
        # e.g., transient UI boundary or access denied
        return None
    return ci.hCursor

@contextmanager
def print_while_busy_ctypes(poll=1.0, warmup_idle_secs=0.2,
                            busy_if_seen_n=2, idle_if_seen_n=2, debug=False):
    """
    Prints 'busy loading results' every `poll` seconds while the cursor is "busy".
    - Learns custom busy cursors when the same non-idle handle is seen busy_if_seen_n times consecutively.
    - Treats any handle seen during the warmup period as 'idle' baseline(s).
    - Stops after seeing an idle handle idle_if_seen_n times in a row.
    """
    stop = threading.Event()
    idle_handles = set()   # learned during warmup only
    busy_handles = set()   # learned during run

    def watcher():
        # Warmup: learn baseline idle cursor(s)
        t_end = time.time() + max(0.0, warmup_idle_secs)
        while time.time() < t_end and not stop.is_set():
            h = _safe_get_cursor_handle()
            if h is not None:
                idle_handles.add(h)
            time.sleep(0.05)

        last_h = None
        same_count = 0
        idle_streak = 0
        printing = False

        while not stop.is_set():
            h = _safe_get_cursor_handle()
            if h is None:
                time.sleep(poll)
                continue

            if h == last_h:
                same_count += 1
            else:
                last_h = h
                same_count = 1

            is_idle = h in idle_handles

            # Learn a custom busy handle only if it persists and isn't in idle set
            if (not is_idle) and (h not in busy_handles) and same_count >= busy_if_seen_n:
                busy_handles.add(h)
                if debug:
                    try:
                        print(f"learned busy cursor: {hex(int(h))}", flush=True)
                    except Exception:
                        pass

            if (h in busy_handles) and (not is_idle):
                print("busy loading timesliced energy generation results results", flush=True)
                printing = True
                idle_streak = 0
            else:
                if printing and is_idle:
                    idle_streak += 1
                    if idle_streak >= idle_if_seen_n:
                        break

            time.sleep(poll)

    t = threading.Thread(target=watcher, daemon=True)
    t.start()
    try:
        yield
    finally:
        stop.set()
        t.join(timeout=2)

# Load favorite for selected scenario and export -- takes a long time to render, so disable controls
def export_leap_favorite_to_csv(leap, favname, leap_scenario, leap_export_fname, units):
    leap.ActiveView = "Results"
    # Should be calculated, but check
    while leap.IsCalculating:
        time.sleep(1)
    with print_while_busy_ctypes(poll=1.0, warmup_idle_secs=0.2, busy_if_seen_n=2, idle_if_seen_n=2, debug=False):
        leap.Favorites(favname).Activate()
        leap.ActiveScenario = leap_scenario # reordered to after leap.Favorites(favname).Activate)
    print("ready; continuing…", flush=True)
    leap.ActiveUnit = units
    leap.ExportResultsCSV(leap_export_fname)
    leap.ActiveView = "Analysis"

def get_leap_timeslice_info(leap, months):
    month_dict = dict(zip(months, [i+1 for i in range(len(months))]))

    leap_ts_info = OrderedDict()
    for tsl in leap.timeslices :
        month_name = tsl.Name[:tsl.Name.index(":")]
        try:
            leap_ts_info[tsl.Name] = month_dict[month_name]
        except:
            msg = _('Unrecognized month "{m}" in month_num function. Exiting...').format(m = month_name)
            logging.error(msg)
            sys.exit(msg)
            
    return leap_ts_info
    
def split_interp_ex(exp, startyear, endyear, listseparator):
    """Extract and return from Interp expression expression the part before the startyear and the part after the endyear
    
    Input arguments:
        exp is an Interp expression
        startyear, endyear are integers
        listseparator is the currently active Windows list separator character (e.g., "," or ";")
    Returns: A list of the form [before_startyear_expression, after_endyear_expression]
    """
    return_val = []
    return_val.append("Interp(")
    return_val.append("")
    interp_termination = exp[-(len(exp) - exp.find(")") ):len(exp)]  # Closing ) and any subsequent content in Interp expression
    exp = exp.lower().replace("interp(", "")
    exp = exp[0:exp.find(")")]
    exp_split = exp.split(listseparator)
    for i in range(0, len(exp_split),2):
        if i == len(exp_split)-1:
            # exp_split[i] is final, optional growth rate parameter for Interp
            return_val[1] = "".join([return_val[1], exp_split[-1].strip()])
            break
        if int(exp_split[i].strip())<startyear :
            return_val[0] = "".join([return_val[0], exp_split[i].strip(), listseparator, exp_split[i+1].strip(), listseparator])
        if int(exp_split[i].strip())>endyear :
            return_val[1] = "".join([return_val[1], exp_split[i].strip(), listseparator, exp_split[i+1].strip(), listseparator])
    # Trim extra list separators
    if return_val[0][-1] == listseparator: return_val[0] = return_val[0][0:-1]
    if len(return_val[1])>0:
        if return_val[1][-1] == listseparator:
            return_val[1] = return_val[1][0:-1]
            return_val[1] = "".join([return_val[1], interp_termination])
        else:
            return_val[1] = "".join([return_val[1], interp_termination])
    else:
        return_val[1] = "".join([return_val[1], interp_termination])
    return return_val

def add_leap_data_to_weap_interp(weap, leap, weap_scenarios, leap_scenarios, weap_branch, weap_variable, leap_branch, leap_variable, leap_region, data_multiplier, listseparator):
    """Insert LEAP data from specified branch, variable, and region into a WEAP Interp expression for a specified branch and variable
    
    Input arguments:
        weap and leap are WEAP and LEAP application objects
        weap_scenarios and leap_scenarios are arrays of the names of the WEAP and LEAP scenarios being calculated
        weap_branch and weap_variable are strings specifying a WEAP branch and variable
        leap_branch, leap_variable, and leap_region are strings specifying LEAP branch, variable, and region
        data_multiplier corrects for different units: Set the value so that LEAP and WEAP units are compatible when LEAP values are multiplied by data_multiplier
        listseparator is the currently active Windows list separator character (e.g., "," or ";")
    Returns: Nothing
    
    Notes:
        This procedure doesn't validate branches, variables, and regions: use check_branch_var() and check_region() before the procedure is called.
        The variables weap_scenarios and leap_scenarios should exclude Current Accounts: The procedure adds Current Accounts to local copies of weap_scenarios and leap_scenarios.
    """
    leap_scenarios_local = leap_scenarios.copy()
    weap_scenarios_local = weap_scenarios.copy()
    leap_scenarios_local.append('Current Accounts')
    weap_scenarios_local.append('Current Accounts')
    leap.ActiveRegion = leap_region
    # Loop over scenarios and add LEAP data to WEAP expressions.
    for i in range(0, len(leap_scenarios_local)):
        weap.ActiveScenario = weap_scenarios_local[i]
        leap.ActiveScenario = leap_scenarios_local[i]
        # logging.info('LEAP Scenario: ' + leap_scenarios_local[i] + '; LEAP Variable: ' + weap.Branches(weap_branch).Variables(weap_variable).Name)
        weap_expression = weap.Branches(weap_branch).Variables(weap_variable).Expression # ' Target expression in WEAP; must be an Interp expression
        if not weap_expression[0:6] == 'Interp':
            msg = _('The expression for {b}:{v} is not an Interp() expression: Cannot update with data from LEAP. Exiting...').format(b = weap_branch, v = weap_variable)
            sys.exit(msg)
        startyear = leap.baseyear # Starting year for LEAP data transcribed to WEAP
        endyear = leap.endyear # Ending year for LEAP data transcribed to WEAP
        split_weap_expression = split_interp_ex(weap_expression, startyear, endyear, listseparator)
        new_data = "" #New data to be inserted into target WEAP expression
        for y in range(startyear, endyear+1):
            new_data = "".join([new_data, str(y), listseparator, str(leap.Branches(leap_branch).Variables(leap_variable).Value(y) * data_multiplier), listseparator])
        new_weap_expression = split_weap_expression[0]
        if new_weap_expression[-1] == "(":
            new_weap_expression = "".join([new_weap_expression, new_data])
        else:
            new_weap_expression = "".join([new_weap_expression, listseparator, new_data])
        if split_weap_expression[1][0] == ")":
            new_weap_expression = "".join([new_weap_expression[0:-1], split_weap_expression[1]])
        else:
            new_weap_expression = "".join([new_weap_expression, split_weap_expression[1]])
        weap.Branches(weap_branch).Variables(weap_variable).Expression = new_weap_expression

#--------------------------------------------------------------------------------
# Process LEAP HPPs
#--------------------------------------------------------------------------------
def proc_leap_hpp(leap_export_fname, config_params):
    hpp = {} # This is the return variable
    for h in list(config_params['LEAP']['Hydropower_plants']['plants'].keys()):
        hpp[h] = {}

    # Extracts, e.g., "January" from "January: Hour 1" in first match
    month_re = re.compile(r'^([A-Za-z]+):')
    year_re = re.compile(r'[1-9][0-9]{3}')

    with open(leap_export_fname) as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=',')
        # Search for header row
        for hdr in csv_reader:
            if hdr[0] == "Time slice":
                break
        # Extract columns for each hydropower plant
        for h in hpp:
            # Will execute regex multiple times per HPP plant, so compile; get indices and years for each HPP
            hpp_re = re.compile(h)
            hpp[h]['cols'] = [i for i, item in enumerate(hdr[1:]) if re.search(hpp_re, item)]
            hpp[h]['years'] = [int(re.match(year_re, hdr[i + 1]).group()) for i in hpp[h]['cols']]
            hpp[h]['vals'] = {}
        
        # Loop over rows of values, summing up months
        curr_month = ""
        for val in csv_reader:
            # If there is a total row it will give "None"
            month_match = month_re.match(val[0])
            if month_match is not None:
                m = month_match.group(1)
                if m != curr_month:
                    new = True
                    curr_month = m
                else:
                    new = False
                for h in hpp:
                    if hpp[h]['cols']:
                        curr_vals = [leapfloat(x) for x in [val[i + 1] for i in hpp[h]['cols']]]
                        if new:
                            hpp[h]['vals'][m] = curr_vals
                        else:
                            hpp[h]['vals'][m] = [hpp[h]['vals'][m][i] + curr_vals[i] for i in range(len(curr_vals))]
                        
    return hpp
                
#--------------------------------------------------------------------------------
# Aggregate from LEAP to WEAP HPPs
#--------------------------------------------------------------------------------
def proc_weap_hpp(weap, hpp, config_params):
    hpp_weap = {}
    hpp_weap['dams'] = {}
    
    # Store the current scenario -- checking expressions only in current accounts
    curr_scenario = weap.ActiveScenario
    weap.ActiveScenario = "Current Accounts"
    
    for hw, entry in config_params['WEAP']['Hydropower_plants']['dams'].items():
        # Consider adding this check as a short-cut
        # weap_path = config_params['WEAP']['Hydropower_plants']['dams'][wb]['weap_path']
            # if not 'Run of River' in weap_path: 
            # weap.Branches(weap_path).Variables('Energy Demand').Expression = ""
        # Assume zero means default; Can't check if expression is inherited, because in Python properties cannot have arguments
        if weap.Branch(entry['weap_path']).Variable("Energy Demand").Expression != "0":
            new = True
            hpp_weap['dams'][hw] = {}
            hpp_weap['dams'][hw]['path'] = entry['weap_path']
            hpp_weap['dams'][hw]['vals'] = {}
            for hl in entry['leap_hpps']:
                # If no years, then no entries at all
                if hpp[hl]['years']:
                    # Years should be the same for all dams, so set at level of hpp_weap
                    if new:
                        hpp_weap['years'] = hpp[hl]['years']
                        for m in config_params['LEAP']['Months']:
                            hpp_weap['dams'][hw]['vals'][m] = hpp[hl]['vals'][m]
                        new = False
                    else:
                        if hpp_weap['years'] != hpp[hl]['years']:
                            msg = _('When aggregating WEAP hydropower plant {a} found inconsistent years in LEAP hydropower plants {b}.  Exiting...').format(a = hw, b = ", ".join(entry['leap_hpps']))
                            logging.error(msg)
                            sys.exit(msg)
                        for m in config_params['LEAP']['Months']:
                            hpp_weap['dams'][hw]['vals'][m] = [hpp_weap['dams'][hw]['vals'][m][i] + hpp[hl]['vals'][m][i] for i in range(len(hpp_weap['years']))]
    
    # Restore the current scenario
    weap.ActiveScenario = curr_scenario

    return hpp_weap
            
def export_leap_hpp_to_weap(leap, weap, iteration, leap_scenario, weap_scenario, config_params):
    energy_unit = config_params['LEAP']['Hydropower_plants']['convergence_check']['leap_unit']
    # 1. Get values from LEAP
    # Get path for storing files and create it if it doesn't exist
    leap_export_path = os.path.normpath(os.path.join(leap.ActiveArea.Directory, "..\\..", config_params['LEAP']['Folder']))
    if not os.path.exists(leap_export_path):
        os.makedirs(leap_export_path)
    leap_export_fname = os.path.join(leap_export_path, leap_scenario + "_iteration_" + str(iteration) + "_HPP.csv")
    favname = "WEAP#hydropower"
    export_leap_favorite_to_csv(leap, favname, leap_scenario, leap_export_fname, energy_unit)
    hpp = proc_leap_hpp(leap_export_fname, config_params)

    # 2. Load values into WEAP 
    hpp_weap = proc_weap_hpp(weap, hpp, config_params)
    energy_unit_string = "[" + energy_unit + "]"
    hpp_hdr = "\"" + (energy_unit_string + "\",\"").join(list(hpp_weap['dams'].keys())) + energy_unit_string + "\""
    hdr = ",".join(["$Columns = Year","Month",hpp_hdr]) + "\n"

    weap_export_path = os.path.normpath(os.path.join(weap.ActiveArea.Directory, config_params['WEAP']['Folder']))
    weap_fname = weap_scenario + "_iteration_" + str(iteration) + "_HPP_demand.csv"
    if not os.path.exists(weap_export_path):
        os.makedirs(weap_export_path)
    with open(os.path.join(weap_export_path, weap_fname), 'w') as csvfile:
        csvfile.writelines(["\"$ListSeparator = ,\"\n", "\"$DecimalSymbol = .\"\n"])
        csvfile.write(hdr)
        for yearndx, year in enumerate(hpp_weap['years']):
            for monthndx, monthname in enumerate(config_params['LEAP']['Months']):
                vals = []
                for hpp in hpp_weap['dams'].values():
                    vals.append(hpp['vals'][monthname][yearndx])
                csvfile.write(",".join(map(str, ([year, monthndx + 1] + vals))) + "\n")

    weap.ActiveScenario = weap_scenario
    weap_fname_full = os.path.join(config_params['WEAP']['Folder'], weap_fname)
    for hppname, hppitem in hpp_weap['dams'].items():
        expression = "ReadFromFile(\"" + weap_fname_full + "\", \"" + hppname + "\")"
        hppobj = weap.Branches(hppitem['path'])
        # A particular plant may not be active in a scenario -- check
        if hppobj is not None:
            hppobj.Variables('Energy Demand').Expression = expression
