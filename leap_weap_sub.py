import logging

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
        weap.ActiveScenario = weap_scenarios_local[i]
        logging.info('LEAP Scenario: ' + leap_scenarios_local[i] + '; LEAP Variable: ' + weap.Branches(weap_branch).Variables(weap_variable).Name)
        weap_expression = weap.Branches(weap_branch).Variables(weap_variable).Expression # ' Target expression in WEAP; must be an Interp expression
        logging.info('Current WEAP expression: ' + weap_expression)
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
        logging.info('Updated WEAP expression: ' + weap.Branches(weap_branch).Variables(weap_variable).Expression)
