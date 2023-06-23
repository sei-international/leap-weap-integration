import logging
from collections import OrderedDict # Not necessary with Python 3.7+

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
    # Loop over scenarios and add LEAP data to WEAP expressions.
    for i in range(0, len(leap_scenarios_local)):
        weap.ActiveScenario = weap_scenarios_local[i]
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
            new_data = "".join([new_data, str(y), listseparator, str(leap.Branches(leap_branch).Variables(leap_variable).ValueRS(leap.regions(leap_region).id, leap_scenarios_local[i], y) * data_multiplier), listseparator])
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