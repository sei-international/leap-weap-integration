' Script for integrating WAVE WEAP and LEAP models.
'
' Copyright © 2022: Stockholm Environment Institute U.S.

' BEGIN: Define supporting functions and procedures.
' Runs the script at script_path in global scope.
Sub include(script_path)
	Dim fso_obj, file_obj
	Set fso_obj = CreateObject("Scripting.FileSystemObject")
	Set file_obj = fso_obj.OpenTextFile(script_path)
	ExecuteGlobal file_obj.ReadAll()
	file_obj.Close
End Sub  ' include()

' Sleeps sleep_app while wait_app.ProgramStarted <> true. wait_app and sleep_app should be LEAP/WEAP application objects.
Sub wait_apps(wait_app, sleep_app)
	While not wait_app.ProgramStarted  
		sleep_app.Sleep(1000)
	Wend
End Sub  ' wait_apps()

' Checks whether a branch-variable-unit combination exists in app (which should be a LEAP or WEAP application object). branch_path is the path to the branch, and variable and unit are the names of the variable and unit (including any unit scaling factor).
Sub check_branch_var(app, branch_path, variable, unit)
	check_passed = False  ' Indicates whether branch, variable, and unit exist in app
	Dim app_name  ' Name of app
	
	If app Is LEAP Then
		app_name = "LEAP"
		
		If app.Branches.Exists(branch_path) Then
			If app.Branches(branch_path).VariableExists(variable) Then
				If app.Branches(branch_path).Variable(variable).DataUnitText = unit Then
					check_passed = True
				End If
			End If
		End If
	ElseIf app Is WEAP Then
		app_name = "WEAP"

		If app.BranchExists(branch_path) Then
			If app.Branch(branch_path).VariableExists(variable) Then
				If app.Branch(branch_path).Variable(variable).ScaleUnit = unit Then
					check_passed = True
				End If
			End If
		End If	
	End If
	
	If Not check_passed Then Err.Raise vbObjectError + 2, "WAVE integration", "The active " & app_name & " area does not contain the required variable " & branch_path & ":" & variable & " with unit " & unit & ". Please check the area and try again. Exiting..."
End Sub  ' check_branch_var()

' Checks whether region (this argument should be a region name) exists in the active LEAP area. If it does, enables calculations for region.
Sub check_region(leap, region)
	check_passed = False
	
	If leap.Regions.Exists(region) Then
		leap.Regions(region).ResultsShown = True
		check_passed = True
	End If
	
	If Not check_passed Then Err.Raise vbObjectError + 3, "WAVE integration", "Could not enable calculations for region " & region & " in the active LEAP area. Please check the area and try again. Exiting..."
End Sub  ' check_region()

' Returns an array of years calculated in LEAP.
Function get_leap_calc_years(leap)
	Dim return_val()  ' Return value of this function
	last_index = -1  ' Maximum index in return_val
	
	for y = leap.FirstScenarioYear To leap.EndYear step 1
		If y mod leap.ResultsEvery = 0 Then
			Redim Preserve return_val(last_index + 1)
			return_val(last_index + 1) = y
			last_index = last_index + 1
		End If
	next

	get_leap_calc_years = return_val
End Function  ' get_leap_calc_years()

' Turns off calculations for all scenarios in current area in app (which should be a LEAP or WEAP application object).
Sub disable_all_scenario_calcs(app)
	for each s in app.Scenarios
		s.ResultsShown = False
	next
End Sub  ' disable_all_scenario_calcs()

' Splits the Interp expression exp into two parts: before startyear and after endyear (years from startyear to endyear are omitted). Returns an array with the two parts. listseparator is the currently active Windows list separator character (e.g., ",").
Function split_interp(exp, startyear, endyear, listseparator)
	Dim return_val(1)  ' This function's return value - item 0 is Interp expression before startyear, item 1 is Interp expression after endyear
	return_val(0) = "Interp("
	return_val(1) = ""
	interp_termination = right(exp, len(exp) - instr(exp, ")") + 1)  ' Closing ) and any subsequent content in Interp expression

	exp = LCase(exp)
	exp = Replace(exp, "interp(", "")
	exp = Left(exp, instr(exp, ")") - 1)
	exp_split = Split(exp, listseparator)
	
	For i = 0 to UBound(exp_split) step 2
		If i = UBound(exp_split) Then
			' exp_split(i) is final, optional growth rate parameter for Interp
			return_val(1) = return_val(1) & trim(exp_split(i))
			Exit For
		End If
	
		If CInt(trim(exp_split(i))) < startyear Then return_val(0) = return_val(0) & trim(exp_split(i)) & listseparator & trim(exp_split(i+1)) & listseparator
		If CInt(trim(exp_split(i))) > endyear Then return_val(1) = return_val(1) & trim(exp_split(i)) & listseparator & trim(exp_split(i+1)) & listseparator
	Next
	
	' Trim extra list separators
	If Right(return_val(0), 1) = listseparator Then return_val(0) = Left(return_val(0), Len(return_val(0)) - 1)
	If Right(return_val(1), 1) = listseparator Then return_val(1) = Left(return_val(1), Len(return_val(1)) - 1)
	
	return_val(1) = return_val(1) & interp_termination
	
	split_interp = return_val
End Function  ' split_interp()

' Inserts LEAP data from leap_branch, leap_variable, and leap_region into the WEAP Interp expression for weap_branch and weap_variable. weap and leap are WEAP and LEAP application objects, respectively; weap_scenarios and leap_scenarios are arrays of the names of the WEAP and LEAP scenarios being calculated. The procedure assumes that the units of the LEAP and WEAP variables are compatible if LEAP values are multiplied by data_multiplier. listseparator is the currently active Windows list separator character (e.g., ",").
Sub add_leap_data_to_weap_interp(weap, leap, ByVal weap_scenarios, ByVal leap_scenarios, weap_branch, weap_variable, leap_branch, leap_variable, leap_region, data_multiplier, listseparator)
	' This procedure doesn't validate branches, variables, and regions. This is assumed to happen via check_branch_var() and check_region() before the procedure is called.

	' BEGIN: Add Current Accounts to local copies of weap_scenarios and leap_scenarios.
	' Scenarios in weap_scenarios and leap_scenarios should exclude Current Accounts; add it here to ensure Current Accounts values are transcribed to WEAP
	Redim Preserve leap_scenarios(UBound(leap_scenarios) + 1)
	leap_scenarios(UBound(leap_scenarios)) = "Current Accounts"
	
	Redim Preserve weap_scenarios(UBound(weap_scenarios) + 1)
	weap_scenarios(UBound(weap_scenarios)) = "Current Accounts"
	' END: Add Current Accounts to local copies of weap_scenarios and leap_scenarios.
	
	' BEGIN: Loop over scenarios and add LEAP data to WEAP expressions.
	For i = 0 to UBound(leap_scenarios)
		weap.ActiveScenario = weap_scenarios(i)
		weap_expression = weap.Branches(weap_branch).Variables(weap_variable).Expression  ' Target expression in WEAP; must be an Interp expression
		
		If LCase(Left(weap_expression, 7)) <> "interp(" Then Err.Raise vbObjectError + 7, "WAVE integration", "Cannot update the expression for " & weap_branch & ":" & weap_variable & " with data from LEAP. The expression must be an Interp() expression. Exiting..."
		
		Dim startyear  ' Starting year for LEAP data transcribed to WEAP
		Dim endyear  ' Ending year for LEAP data transcribed to WEAP

		startyear = leap.baseyear
		endyear = leap.endyear  ' Move all LEAP data into WEAP for all scenarios, including Current Accounts; this handles possibility that LEAP and WEAP Current Accounts cover disjoint periods
	
		split_weap_expression  = split_interp(weap_expression, startyear, endyear, listseparator)
	
		new_data = ""  ' New data to be inserted into target WEAP expression
		
		for y = startyear to endyear
			new_data = new_data & y & listseparator & leap.branches(leap_branch).variables(leap_variable).ValueRS(leap.regions(leap_region).id, leap_scenarios(i), y) * data_multiplier & listseparator
		next
		
		new_weap_expression = split_weap_expression(0)  ' New expression for WEAP
		
		If Right(new_weap_expression, 1) = "(" Then
			new_weap_expression = new_weap_expression & new_data
		Else
			new_weap_expression = new_weap_expression & listseparator & new_data
		End If
		
		If Left(split_weap_expression(1), 1) = ")" Then
			new_weap_expression = Left(new_weap_expression, Len(new_weap_expression) - 1) & split_weap_expression(1)
		Else
			new_weap_expression = new_weap_expression & split_weap_expression(1)		
		End If
		
		weap.Branches(weap_branch).Variables(weap_variable).Expression = new_weap_expression
	Next  ' i (index of leap_scenarios)
	' END: Loop over scenarios and add LEAP data to WEAP expressions.
End Sub  ' add_leap_data_to_weap_interp()

' Returns the number of days in month (a month number) in year
Function days_in_month(year, month)
	days_in_month = Day(DateSerial(year, month + 1, 0))
End Function  ' days_in_month()

' Returns the month number associated with the month named month_name.
Function month_num(month_name)
	Select Case month_name
		Case "January"
			month_num = 1
		Case "February"
			month_num = 2
		Case "March"
			month_num = 3
		Case "April"
			month_num = 4
		Case "May"
			month_num = 5			
		Case "June"
			month_num = 6
		Case "July"
			month_num = 7
		Case "August"
			month_num = 8
		Case "September"
			month_num = 9
		Case "October"
			month_num = 10
		Case "November"
			month_num = 11
		Case "December"
			month_num = 12
		Case Else
			Err.Raise vbObjectError + 8, "WAVE integration", "Unrecognized month (" & month_name & ") in month_num function. Exiting..."
	End Select
End Function  ' month_num()

' Returns an array whose length is length argument; allows creating an array based on an expression for the length.
Function dynamic_length_array(length)
	return_val = Array()
	l = -1
	
	For i = 1 To length
		ReDim return_val(l + 1)
		l = l + 1
	Next

	dynamic_length_array = return_val
End Function  ' dynamic_length_array()
' END: Define supporting functions and procedures.

' BEGIN: Ensure LEAP and WEAP are both started.
' Assumes this script is run from either LEAP or WEAP.
Dim runfrom_app  ' Name of app from which this script is being run - LEAP or WEAP
Dim other_app  ' Name of whichever of LEAP or WEAP isn't runfrom_app

If IsObject(LEAP) then
	If not IsObject(WEAP) then
		runfrom_app = "LEAP"
		
		Set WEAP = CreateObject("WEAP.WEAPApplication")  
		wait_apps WEAP, LEAP
		other_app = "WEAP"
	End If
End If

If IsObject(WEAP) then
	If not IsObject(LEAP) then
		runfrom_app = "WEAP"
	
		Set LEAP = CreateObject("LEAP.LEAPApplication")  
		wait_apps LEAP, WEAP
		other_app = "LEAP"
	End If	
End If

If not IsObject(LEAP) or not IsObject(WEAP) then
	Err.Raise vbObjectError + 1, "WAVE integration", "Cannot start LEAP and WEAP. Exiting..."
End If

'msgbox("runfrom_app = " & runfrom_app)
' END: Ensure LEAP and WEAP are both started.

' BEGIN: Set run-time language.
Dim shell_obj  ' WScript.Shell object in global scope
Set shell_obj = CreateObject("WScript.Shell")

If MsgBox("Would you like Russian language prompts?" & vbCrlf & "Хотите подсказки на русском языке?", vbYesNo, "Select Language / Выберите язык") = vbYes Then
	lang = "RUS"
Else
	lang = "ENG"
End If
' END: Set run-time language.

' BEGIN: Define main integration procedure.
Sub run_wave_model()
	' BEGIN: Turn on progress bar.
	' Activate LEAP in order to maximize chances of user seeing progress bar
	shell_obj.AppActivate("LEAP")
	LEAP.BringToFront
	
	Dim msg  ' Variable used to assemble dynamic MsgBox and progress bar messages
	Dim title  ' Variable used to assemble dynamic MsgBox titles
	Dim procedure_title  ' Static title identifying WEAP-LEAP integration procedure

	If lang = "RUS" Then msg = "Инициирование процедуры интеграции." Else msg = "Initiating integration procedure."
	If lang = "RUS" Then procedure_title = "Процедура интеграции WEAP-LEAP" Else procedure_title = "WEAP-LEAP Integration Procedure"

	Call LEAP.ShowProgressBar(procedure_title, msg)
	' END: Turn on progress bar.
	
	' BEGIN: Define parameters controlling calculation iterations.
	' One iteration = running both LEAP and WEAP once
	max_iterations = 1  ' Maximum number of iterations; if in conflict with convergence_tol, max_iterations controls
	convergence_tol = 0.1  ' Models are considered to have converged if % change in target results from one iteration to another is <= convergence_tol; both WEAP and LEAP target results are checked and compared to convergence_tol
	completed_iterations = 0  ' Number of iterations that have been completed
	results_converged = False  ' Indicates whether convergence has occurred
	' END: Define parameters controlling calculation iterations.

	' BEGIN: Open WAVE LEAP and WEAP areas.
	If runfrom_app = "LEAP" Then
		' Assume appropriate LEAP area is open
		If lang = "RUS" Then msg = "Пожалуйста, откройте модель WAVE (область) в WEAP." Else msg = "Please open the WAVE model (area) in WEAP."
		If lang = "RUS" Then title = "Открытая область WEAP" Else title = "Open WEAP Area"
		
		If MsgBox(msg, vbOKCancel, title) <> vbOK Then
			Exit Sub
		Else
			wait_apps WEAP, LEAP
		End If
	ElseIf runfrom_app = "WEAP" Then
		If lang = "RUS" Then msg = "Пожалуйста, откройте модель WAVE (область) в LEAP." Else msg = "Please open the WAVE model (area) in LEAP."
		If lang = "RUS" Then title = "Открытая область LEAP" Else title = "Open LEAP Area"

		' Assume appropriate WEAP area is open
		If MsgBox(msg, vbOKCancel, title) <> vbOK Then
			Exit Sub
		Else
			wait_apps LEAP, WEAP
		End If
	ElseIf IsEmpty(runfrom_app) Then
		If lang = "RUS" Then msg = "Пожалуйста, откройте модель WAVE (область) в WEAP." Else msg = "Please open the WAVE model (area) in WEAP."
		If lang = "RUS" Then title = "Открытая область WEAP" Else title = "Open WEAP Area"
	
		If MsgBox(msg, vbOKCancel, title) <> vbOK Then
			Exit Sub
		Else
			wait_apps WEAP, LEAP
		End If

		If lang = "RUS" Then msg = "Пожалуйста, откройте модель WAVE (область) в LEAP." Else msg = "Please open the WAVE model (area) in LEAP."
		If lang = "RUS" Then title = "Открытая область LEAP" Else title = "Open LEAP Area"
		
		If MsgBox(msg, vbOKCancel, title) <> vbOK Then
			Exit Sub
		Else
			wait_apps LEAP, WEAP
		End If
		
		runfrom_app = "WEAP"
		other_app = "LEAP"
	End If
	' END: Open WAVE LEAP and WEAP areas.
	
	' BEGIN: Define runfrom_app_obj and other_app_obj.
	' Convenience objects to simplify some code where LEAP and WEAP APIs have same syntax
	Dim runfrom_app_obj  ' LEAP/WEAP application object corresponding to runfrom_app
	Dim other_app_obj  ' LEAP/WEAP application object corresponding to other_app
	
	If runfrom_app = "LEAP" Then
		Set runfrom_app_obj = LEAP
		Set other_app_obj = WEAP
	ElseIf runfrom_app = "WEAP" Then
		Set runfrom_app_obj = WEAP
		Set other_app_obj = LEAP
	End If	
	' END: Define runfrom_app_obj and other_app_obj.
	
	' BEGIN: Validate LEAP area.
	If lang = "RUS" Then msg = "Валидирование областей WEAP и LEAP." Else msg = "Validating WEAP and LEAP areas."
	Call LEAP.ShowProgressBar(procedure_title, msg)
	Call LEAP.SetProgressBar(15)
	
	Call check_branch_var(LEAP, "Key\Macroeconomic\Gross Domestic Product", "Activity Level", "2020 USD")
	Call check_branch_var(LEAP, "Key\Demographic\Population", "Activity Level", "people")
	Call check_branch_var(LEAP, "Key\Macroeconomic\Industrial\Industry_Value Added Fraction", "Activity Level", "Fraction")
	Call check_branch_var(LEAP, "Demand\Agriculture\Syr Darya\Water demand", "Activity Level", "Cubic Meter/No Data")
	
	Dim leap_hydro_branches_map  ' Map of LEAP hydropower branches (keys) to regions in which plants are located (values)
	Set leap_hydro_branches_map = CreateObject("Scripting.Dictionary")
	
	leap_hydro_branches_map.Add "Transformation\Electricity Production\Processes\AKHANGARAN RESERVOIR", "Uzbekistan"
	leap_hydro_branches_map.Add "Transformation\Electricity Production\Processes\ANDIJAN_1", "Uzbekistan"
	leap_hydro_branches_map.Add "Transformation\Electricity Production\Processes\AKKAVAK_1", "Uzbekistan"
	leap_hydro_branches_map.Add "Transformation\Electricity Production\Processes\ANDIJAN_2", "Uzbekistan"
	leap_hydro_branches_map.Add "Transformation\Electricity Production\Processes\CHARVAK", "Uzbekistan"
	leap_hydro_branches_map.Add "Transformation\Electricity Production\Processes\CHIRCHIK_1", "Uzbekistan"
	leap_hydro_branches_map.Add "Transformation\Electricity Production\Processes\CHIRCHIK_2", "Uzbekistan"
	leap_hydro_branches_map.Add "Transformation\Electricity Production\Processes\FARKHAD", "Uzbekistan"
	leap_hydro_branches_map.Add "Transformation\Electricity Production\Processes\GAZALKENT", "Uzbekistan"
	leap_hydro_branches_map.Add "Transformation\Electricity Production\Processes\KAIRAKKUM", "Tajikistan"
	leap_hydro_branches_map.Add "Transformation\Electricity Production\Processes\KAMBARATA_2", "Kyrgyzstan"
	leap_hydro_branches_map.Add "Transformation\Electricity Production\Processes\KHODZHIKENT", "Uzbekistan"
	leap_hydro_branches_map.Add "Transformation\Electricity Production\Processes\KURPSAI", "Kyrgyzstan"
	leap_hydro_branches_map.Add "Transformation\Electricity Production\Processes\SHAMALDYSAI", "Kyrgyzstan"
	leap_hydro_branches_map.Add "Transformation\Electricity Production\Processes\SHARDARINSKYA", "Kazakhstan"
	leap_hydro_branches_map.Add "Transformation\Electricity Production\Processes\TASH_KUMYR", "Kyrgyzstan"
	leap_hydro_branches_map.Add "Transformation\Electricity Production\Processes\TAVAK", "Uzbekistan"
	leap_hydro_branches_map.Add "Transformation\Electricity Production\Processes\TOKTOGUL", "Kyrgyzstan"
	leap_hydro_branches_map.Add "Transformation\Electricity Production\Processes\UCH_KURGANSK", "Kyrgyzstan"

	For Each b in leap_hydro_branches_map.keys
		Call check_branch_var(LEAP, b, "Maximum Availability", "Percent")
	Next
	
	calculated_leap_regions = Array("Kazakhstan", "Kyrgyzstan", "Tajikistan", "Uzbekistan")  ' Names of regions that should be calculated in LEAP model
	
	for each r in calculated_leap_regions
		Call check_region(LEAP, r)
	next
	' END: Validate LEAP area.

	' BEGIN: Validate WEAP area.
	Call check_branch_var(WEAP, "Key\Demographic\KAZ\National population", "Annual Activity Level", "cap")
	Call check_branch_var(WEAP, "Key\Demographic\KGZ\National population", "Annual Activity Level", "cap")
	Call check_branch_var(WEAP, "Key\Demographic\TJK\National population", "Annual Activity Level", "cap")
	Call check_branch_var(WEAP, "Key\Demographic\UZB\National population", "Annual Activity Level", "cap")
	Call check_branch_var(WEAP, "Key\Macroeconomic\KAZ\GDP", "Annual Activity Level", "Billion 2020 USD")
	Call check_branch_var(WEAP, "Key\Macroeconomic\KGZ\GDP", "Annual Activity Level", "Billion 2020 USD")
	Call check_branch_var(WEAP, "Key\Macroeconomic\TJK\GDP", "Annual Activity Level", "Billion 2020 USD")
	Call check_branch_var(WEAP, "Key\Macroeconomic\UZB\GDP", "Annual Activity Level", "Billion 2020 USD")
	Call check_branch_var(WEAP, "Key\Macroeconomic\KAZ\Industrial value added", "Annual Activity Level", "% share")
	Call check_branch_var(WEAP, "Key\Macroeconomic\KGZ\Industrial value added", "Annual Activity Level", "% share")
	Call check_branch_var(WEAP, "Key\Macroeconomic\TJK\Industrial value added", "Annual Activity Level", "% share")
	Call check_branch_var(WEAP, "Key\Macroeconomic\UZB\Industrial value added", "Annual Activity Level", "% share")
	Call check_branch_var(WEAP, "Demand Sites and Catchments\Agriculture_KAZ_Kyzylorda", "Supply Requirement", "m^3")
	Call check_branch_var(WEAP, "Demand Sites and Catchments\Agriculture_KAZ_Turkestan_Shymkent", "Supply Requirement", "m^3")
	Call check_branch_var(WEAP, "Demand Sites and Catchments\Agriculture_KGZ_Naryn_JalalAbat_Osh_Batken", "Supply Requirement", "m^3")
	Call check_branch_var(WEAP, "Demand Sites and Catchments\Agriculture_TJK_Sogd", "Supply Requirement", "m^3")
	Call check_branch_var(WEAP, "Demand Sites and Catchments\Agriculture_UZB_Andijan_Namangan_Fergana", "Supply Requirement", "m^3")
	Call check_branch_var(WEAP, "Demand Sites and Catchments\Agriculture_UZB_SyrDarya_Tashkent_Jizzakh", "Supply Requirement", "m^3")

	weap_hydro_branches = Array("Supply and Resources\River\Syr Darya River\Reservoirs\Toktogul reservoir", "Supply and Resources\River\Syr Darya River\Reservoirs\Kambarata_II", "Supply and Resources\River\Syr Darya River\Reservoirs\Kayrakkum reservoir", "Supply and Resources\River\Syr Darya River\Reservoirs\Shardara reservoir", "Supply and Resources\River\Syr Darya River\Reservoirs\Kurpsaiskaja", "Supply and Resources\River\Syr Darya River\Reservoirs\Taschkumyrskaja_cascade", "Supply and Resources\River\Syr Darya River\Reservoirs\Farkhad reservoir", "Supply and Resources\River\Ahangaran\Reservoirs\Akhangaran reservoir", "Supply and Resources\River\Circik River\Reservoirs\Charvak reservoir", "Supply and Resources\River\Circik River\Reservoirs\Chirchik_cascade", "Supply and Resources\River\Andijan River\Reservoirs\Andijan Reservoir")  ' Array of names of WEAP hydropower branches
	
	Dim hydro_branches_map  ' Dictionary mapping names of WEAP hydropower branches (keys) to arrays of names of corresponding LEAP hydropower branches (values)
	Set hydro_branches_map = CreateObject("Scripting.Dictionary")

	hydro_branches_map.Add weap_hydro_branches(0), Array("Transformation\Electricity Production\Processes\TOKTOGUL")
	hydro_branches_map.Add weap_hydro_branches(1), Array("Transformation\Electricity Production\Processes\KAMBARATA_2")
	hydro_branches_map.Add weap_hydro_branches(2), Array("Transformation\Electricity Production\Processes\KAIRAKKUM")
	hydro_branches_map.Add weap_hydro_branches(3), Array("Transformation\Electricity Production\Processes\SHARDARINSKYA")
	hydro_branches_map.Add weap_hydro_branches(4), Array("Transformation\Electricity Production\Processes\KURPSAI")
	hydro_branches_map.Add weap_hydro_branches(5), Array("Transformation\Electricity Production\Processes\TASH_KUMYR", "Transformation\Electricity Production\Processes\SHAMALDYSAI", "Transformation\Electricity Production\Processes\UCH_KURGANSK")
	hydro_branches_map.Add weap_hydro_branches(6), Array("Transformation\Electricity Production\Processes\FARKHAD")
	hydro_branches_map.Add weap_hydro_branches(7), Array("Transformation\Electricity Production\Processes\AKHANGARAN RESERVOIR")
	hydro_branches_map.Add weap_hydro_branches(8), Array("Transformation\Electricity Production\Processes\CHARVAK", "Transformation\Electricity Production\Processes\KHODZHIKENT", "Transformation\Electricity Production\Processes\GAZALKENT")
	hydro_branches_map.Add weap_hydro_branches(9), Array("Transformation\Electricity Production\Processes\TAVAK", "Transformation\Electricity Production\Processes\CHIRCHIK_1", "Transformation\Electricity Production\Processes\CHIRCHIK_2", "Transformation\Electricity Production\Processes\AKKAVAK_1")
	hydro_branches_map.Add weap_hydro_branches(10), Array("Transformation\Electricity Production\Processes\ANDIJAN_1","Transformation\Electricity Production\Processes\ANDIJAN_2")
	
	For Each b in weap_hydro_branches
		Call check_branch_var(WEAP, b, "Hydropower Generation", "GJ")
	Next
	' END: Validate WEAP area.

	' BEGIN: Define target results for convergence checks during iterative calculations.
	target_leap_results = dynamic_length_array(leap_hydro_branches_map.Count)  ' LEAP branch-variable-region-unit combinations that will be checked for convergence
	keys_arr = leap_hydro_branches_map.keys  ' Variable for accessing dictionary keys
	items_arr = leap_hydro_branches_map.items  ' Variable for accessing dictionary items	
	
	For i = 0 To leap_hydro_branches_map.Count - 1
		target_leap_results(i) = Array(keys_arr(i), "Energy Generation", items_arr(i), "GWh")
	Next

	target_weap_results = dynamic_length_array(UBound(weap_hydro_branches) + 1)  ' WEAP branch-variable-unit combinations that will be checked for convergence

	For i = 0 To UBound(weap_hydro_branches)
		target_weap_results(i) = weap_hydro_branches(i) & ":Hydropower Generation[GWH]"
	Next
	' END: Define target results for convergence checks during iterative calculations.

	' BEGIN: Determine which scenarios are calculated.
	' Logic in this section: 1) look at all scenarios in runfrom_app for which results are shown; 2) try to find corresponding scenarios in other_app, looking for exact name matches and checking predefined_mappings; 3) calculate a) scenarios from 1 with a corresponding scenario from 2; and b) corresponding scenarios from 2. Disable calculations for all other scenarios.
	If lang = "RUS" Then msg = "Определение сценариев для расчета." Else msg = "Identifying scenarios to calculate."
	Call LEAP.ShowProgressBar(procedure_title, msg)
	Call LEAP.SetProgressBar(25)

	Dim scenarios_map  ' Dictionary mapping names of calculated scenarios in runfrom_app (keys) to names of corresponding scenarios in other_app (values)
	Dim predefined_mappings  ' Dictionary of pre-defined scenario correspondences where LEAP scenario name <> WEAP scenario name; contains two key-value pairs for each LEAP scenario mapped to a WEAP scenario - one with LEAP scenario name as key (and WEAP scenario name as value), and one with WEAP scenario name as key (and LEAP scenario name as value)
	Dim leap_scenarios  ' Array of LEAP scenario names in scenarios_map
	Dim weap_scenarios  ' Array of WEAP scenario names in scenarios_map
	
	Set scenarios_map = CreateObject("Scripting.Dictionary")
	Set predefined_mappings = CreateObject("Scripting.Dictionary")

	predefined_mappings.Add "Baseline", "Historical Medium"
	
	for each k in predefined_mappings.keys
		predefined_mappings.Add predefined_mappings(k), k
	next
	
	' Disable all scenario calculations in other_app - calculations will be turned on for scenarios corresponding to calculated scenarios in runfrom_app
	disable_all_scenario_calcs(other_app_obj)

	' Map scenarios by name first, then look in predefined_mappings if an exact name match isn't found
	at_least_1_calculated = False  ' Indicates whether results are shown for at least one scenario in runfrom_app	
	
	For Each s in runfrom_app_obj.Scenarios
		If s.name <> "Current Accounts" and s.ResultsShown = True Then
			at_least_1_calculated = True
		
			If other_app_obj.Scenarios.Exists(s.Name) Then
				scenarios_map.Add s.Name, s.Name
			ElseIf predefined_mappings.Exists(s.Name) and other_app_obj.Scenarios.Exists(predefined_mappings(s.Name)) Then
				scenarios_map.Add s.Name, predefined_mappings(s.Name)
			End If
			
			If scenarios_map.Exists(s.Name) Then
				other_app_obj.Scenarios(scenarios_map(s.Name)).ResultsShown = True
			Else
				' No corresponding scenario found in other_app; disable calculations
				runfrom_app_obj.Scenarios(s.Name).ResultsShown = False
			End If
		End If
	Next
	
	If at_least_1_calculated = False Then
		Err.Raise vbObjectError + 4, "WAVE integration", "At least one scenario must be calculated in the active " & runfrom_app & " area. Exiting..."
	ElseIf scenarios_map.Count = 0 Then
		Err.Raise vbObjectError + 5, "WAVE integration", "Could not find scenarios in the active " & other_app & " area corresponding to the scenarios calculated in the active " & runfrom_app & " LEAP area. Exiting..."
	End If
	
	' Populate leap_scenarios and weap_scenarios
	If runfrom_app = "LEAP" Then
		leap_scenarios = scenarios_map.keys
		weap_scenarios = scenarios_map.items
	ElseIf runfrom_app = "WEAP" Then
		leap_scenarios = scenarios_map.items
		weap_scenarios = scenarios_map.keys
	Else
		Err.Raise vbObjectError + 6, "WAVE integration", "Unsupported runfrom_app in run_wave_model()."
	End If
	
	If lang = "RUS" Then msg = "Расчет следующих сценариев:" Else msg = "Calculating the following scenarios:"

	For Each k in scenarios_map.keys
		msg = msg & vbCrlf & k & " (" & runfrom_app & ") <-> " & scenarios_map(k) & " (" & other_app & ")"
	Next

	Call MsgBox(msg, vbOKOnly, procedure_title)
	' END: Determine which scenarios are calculated.

	' BEGIN: Carry out iterative calculations.
	leap_calc_years = get_leap_calc_years(LEAP)  ' Array of years calculated in LEAP model

	Dim last_iteration_leap_results  ' Array of target LEAP result values (specified in target_leap_results) obtained in previous iteration; contains one set of result values for each scenario in leap_scenarios and year calculated in LEAP, ordered in the order of the scenarios in leap_scenarios and the calculated years
	
	Dim last_iteration_weap_results  ' Array of target WEAP result values (specified in target_weap_results) obtained in previous iteration; contains one set of result values for each scenario in weap_scenarios and year calculated in WEAP, ordered in the order of the scenarios in weap_scenarios and the calculated years

	Dim fs_obj  ' Instance of scripting.FileSystemObject; used to manipulate CSV files in following loop
	Set fs_obj = CreateObject("Scripting.FileSystemObject")
	
	Dim excel  ' Excel Application object used to create data files and query Windows list separator
	Set excel = CreateObject("Excel.Application")  ' Creates a new instance of Excel
	' Set excel = GetObject(, "Excel.Application")  ' Connects to an existing instance of Excel if possible; otherwise creates a new instance
	excel.ScreenUpdating = False

	listseparator = excel.International(5)  ' Windows list separator character (e.g., ",")
	If Len(listseparator) <> 1 Then Err.Raise vbObjectError + 9, "WAVE integration", "The Windows list separator is longer than 1 character, which is incompatible with the WEAP-LEAP integration procedure. Exiting..."
	
	Do While completed_iterations < max_iterations
		' BEGIN: Push demographic and macroeconomic key assumptions from LEAP to WEAP.
		' Values from LEAP base year to end year are embedded in WEAP Interp expressions
		If lang = "RUS" Then msg = "Перемещение демографических и макроэкономических предположений из LEAP в WEAP (итерация " & CStr(completed_iterations+1) & ")." Else msg = "Moving demographic and macroeconomic assumptions from LEAP to WEAP (iteration " & CStr(completed_iterations+1) & ")."
		Call LEAP.ShowProgressBar(procedure_title, msg)
		Call LEAP.SetProgressBar(50)		
		
		Call add_leap_data_to_weap_interp(weap, leap, weap_scenarios, leap_scenarios, "Key\Demographic\KAZ\National population", "Annual Activity Level", "Key\Demographic\Population", "Activity Level", "Kazakhstan", 1, listseparator)
		Call add_leap_data_to_weap_interp(weap, leap, weap_scenarios, leap_scenarios, "Key\Demographic\KGZ\National population", "Annual Activity Level", "Key\Demographic\Population", "Activity Level", "Kyrgyzstan", 1, listseparator)
		Call add_leap_data_to_weap_interp(weap, leap, weap_scenarios, leap_scenarios, "Key\Demographic\TJK\National population", "Annual Activity Level", "Key\Demographic\Population", "Activity Level", "Tajikistan", 1, listseparator)
		Call add_leap_data_to_weap_interp(weap, leap, weap_scenarios, leap_scenarios, "Key\Demographic\UZB\National population", "Annual Activity Level", "Key\Demographic\Population", "Activity Level", "Uzbekistan", 1, listseparator)
		
		Call add_leap_data_to_weap_interp(weap, leap, weap_scenarios, leap_scenarios, "Key\Macroeconomic\KAZ\GDP", "Annual Activity Level", "Key\Macroeconomic\Gross Domestic Product", "Activity Level", "Kazakhstan", 1/10^9, listseparator)
		Call add_leap_data_to_weap_interp(weap, leap, weap_scenarios, leap_scenarios, "Key\Macroeconomic\KGZ\GDP", "Annual Activity Level", "Key\Macroeconomic\Gross Domestic Product", "Activity Level", "Kyrgyzstan", 1/10^9, listseparator)
		Call add_leap_data_to_weap_interp(weap, leap, weap_scenarios, leap_scenarios, "Key\Macroeconomic\TJK\GDP", "Annual Activity Level", "Key\Macroeconomic\Gross Domestic Product", "Activity Level", "Tajikistan", 1/10^9, listseparator)
		Call add_leap_data_to_weap_interp(weap, leap, weap_scenarios, leap_scenarios, "Key\Macroeconomic\UZB\GDP", "Annual Activity Level", "Key\Macroeconomic\Gross Domestic Product", "Activity Level", "Uzbekistan", 1/10^9, listseparator)
		
		Call add_leap_data_to_weap_interp(weap, leap, weap_scenarios, leap_scenarios, "Key\Macroeconomic\KAZ\Industrial value added", "Annual Activity Level", "Key\Macroeconomic\Industrial\Industry_Value Added Fraction", "Activity Level", "Kazakhstan", 100, listseparator)
		Call add_leap_data_to_weap_interp(weap, leap, weap_scenarios, leap_scenarios, "Key\Macroeconomic\KGZ\Industrial value added", "Annual Activity Level", "Key\Macroeconomic\Industrial\Industry_Value Added Fraction", "Activity Level", "Kyrgyzstan", 100, listseparator)
		Call add_leap_data_to_weap_interp(weap, leap, weap_scenarios, leap_scenarios, "Key\Macroeconomic\TJK\Industrial value added", "Annual Activity Level", "Key\Macroeconomic\Industrial\Industry_Value Added Fraction", "Activity Level", "Tajikistan", 100, listseparator)
		Call add_leap_data_to_weap_interp(weap, leap, weap_scenarios, leap_scenarios, "Key\Macroeconomic\UZB\Industrial value added", "Annual Activity Level", "Key\Macroeconomic\Industrial\Industry_Value Added Fraction", "Activity Level", "Uzbekistan", 100, listseparator)
		' END: Push demographic and macroeconomic key assumptions from LEAP to WEAP.

		' BEGIN: Calculate WEAP.
		If lang = "RUS" Then msg = "Расчет площади WEAP (итерация " & CStr(completed_iterations+1) & ")." Else msg = "Calculating WEAP area (iteration " & CStr(completed_iterations+1) & ")."
		Call LEAP.ShowProgressBar(procedure_title, msg)
		Call LEAP.SetProgressBar(50)
		
		WEAP.Calculate()
		
		While WEAP.IsCalculating
			LEAP.Sleep(1000)
		Wend
		' END: Calculate WEAP.
		
		' BEGIN: Move hydropower availability information from WEAP to LEAP.
		' Availability information saved to Excel files specific to WEAP branches and LEAP scenarios. Excel pathway used since LEAP's performance is extremely poor when reading from text files.
		If lang = "RUS" Then msg = "Перемещение доступности гидроэнергетики из WEAP в LEAP (итерация " & CStr(completed_iterations+1) & ")." Else msg = "Moving hydropower availability from WEAP to LEAP (iteration " & CStr(completed_iterations+1) & ")."
		Call LEAP.ShowProgressBar(procedure_title, msg)
		Call LEAP.SetProgressBar(50)
		
		For i = 0 To UBound(weap_scenarios)
			For Each wb in weap_hydro_branches
				xlsx_file = "hydro_availability_wbranch" & CStr(WEAP.Branches(wb).Id) & "_lscenario" & CStr(LEAP.Scenarios(leap_scenarios(i)).Id) & ".xlsx"  ' Name of XLSX file being written
				xlsx_path = LEAP.ActiveArea.Directory & xlsx_file  ' Full path to XLSX file being written
				csv_path = LEAP.ActiveArea.Directory & "temp.csv"  ' Temporary CSV file used to expedite creation of XLSX files

				If fs_obj.FileExists(xlsx_path) Then fs_obj.DeleteFile xlsx_path, True
				If fs_obj.FileExists(csv_path) Then fs_obj.DeleteFile csv_path, True
				
				Set ts = fs_obj.CreateTextFile(csv_path, True, False)  ' TextStream object for csv_path
				num_lines_written = 0  ' Number of lines written to csv_path
		
				For y = WEAP.BaseYear To WEAP.EndYear
					Dim leap_capacity_year  ' Year for which Exogenous Capacity is queried in LEAP; adjusted to account for years not covered in LEAP
					leap_capacity_year = y

					If LEAP.BaseYear > y Then leap_capacity_year = LEAP.BaseYear
					If LEAP.EndYear < y Then leap_capacity_year = LEAP.EndYear
				
					weap_branch_capacity = 0  ' Exogenous capacity in LEAP corresponding to WEAP branch [MW]
					
					For Each lb In hydro_branches_map(wb)
						weap_branch_capacity = weap_branch_capacity + LEAP.Branches(lb).Variable("Exogenous Capacity").ValueRS(LEAP.Regions(leap_hydro_branches_map(lb)).Id, LEAP.Scenarios(leap_scenarios(i)).Id, leap_capacity_year)  ' Can't specify unit when querying data variables, but unit for Exogenous Capacity is MW 
					Next

					' If y = 2020 Then msgbox("Capacity for " & wb & " = " & CStr(weap_branch_capacity) & " in " & CStr(y))

					' Don't bother writing values for years where capacity = 0
					If weap_branch_capacity > 0 Then
						Dim month_vals  ' Dictionary of month numbers to percentage availability values
						Set month_vals = CreateObject("Scripting.Dictionary")
					
						For Each tsl in LEAP.timeslices
							m_num = month_num(Left(tsl.name, instr(tsl.Name, ":") - 1))  ' Number of month of current time slice
							
							If month_vals.Exists(m_num) Then
								val = month_vals(m_num)
							Else
								val = Round(WEAP.resultvalue(wb & ":Hydropower Generation[MWH]", y, m_num, weap_scenarios(i)) / (weap_branch_capacity * days_in_month(y, m_num) * 24) * 100, 1)  ' Percentage availability value to be written to csv_path
							
								If val > 100 Then val = 100
								
								month_vals(m_num) = val
							End If
							
							ts.WriteLine(y & listseparator & tsl.Name & listseparator & CStr(val))
							num_lines_written = num_lines_written + 1
						Next
					End If
				Next  ' y

				ts.Close
				Set ts = Nothing

				' Convert csv_path into an XLSX file
				Call excel.Workbooks.OpenText(csv_path, 2, 1, 1, -4142, False, False, False, True)
				Call excel.ActiveWorkbook.SaveAs(xlsx_path, 51)
				excel.ActiveWorkbook.Close
				
				' Update LEAP Maximum Availability
				For Each lb In hydro_branches_map(wb)
					LEAP.Branches(lb).Variable("Maximum Availability").ExpressionRS(LEAP.Regions(leap_hydro_branches_map(lb)).Id, LEAP.Scenarios(leap_scenarios(i)).Id) = "ReadFromExcel(" & xlsx_file & ", A1:C" & CStr(num_lines_written) & ")"
				Next
			Next  ' wb
		Next  ' i (scenario index)
		
		If IsObject(excel) Then excel.Quit()
		Set excel = Nothing
		' END: Move hydropower availability information from WEAP to LEAP.
		
		' BEGIN: Move Syr Darya agricultural water requirements from WEAP to LEAP.
		If lang = "RUS" Then msg = "Перемещение информации о перекачке воды из WEAP в LEAP (итерация " & CStr(completed_iterations+1) & ")." Else msg = "Moving water pumping information from WEAP to LEAP (iteration " & CStr(completed_iterations+1) & ")."
		Call LEAP.ShowProgressBar(procedure_title, msg)
		Call LEAP.SetProgressBar(50)
		
		Dim region_ag_demand_map  ' Dictionary mapping LEAP region names (keys) to arrays of the names of WEAP branches whose Supply Requirement should be summed to give agricultural water demand in the Syr Darya Basin (values)
		Set region_ag_demand_map = CreateObject("Scripting.Dictionary")
		
		region_ag_demand_map.Add "Kazakhstan", Array("Demand Sites and Catchments\Agriculture_KAZ_Kyzylorda", "Demand Sites and Catchments\Agriculture_KAZ_Turkestan_Shymkent")
		region_ag_demand_map.Add "Kyrgyzstan", Array("Demand Sites and Catchments\Agriculture_KGZ_Naryn_JalalAbat_Osh_Batken")
		region_ag_demand_map.Add "Tajikistan", Array("Demand Sites and Catchments\Agriculture_TJK_Sogd")
		region_ag_demand_map.Add "Uzbekistan", Array("Demand Sites and Catchments\Agriculture_UZB_Andijan_Namangan_Fergana", "Demand Sites and Catchments\Agriculture_UZB_SyrDarya_Tashkent_Jizzakh")
		
		For i = 0 To UBound(weap_scenarios)
			For Each r In region_ag_demand_map.keys
				expr = "Interp("  ' Expression that will be set for Demand\Agriculture\Syr Darya\Water demand:Activity Level in LEAP
			
				For y = WEAP.BaseYear To WEAP.EndYear
					val = 0  ' Value that will be written into expr for y
					
					For Each wb In region_ag_demand_map(r)
						val = val + WEAP.resultvalue(wb & ":Supply Requirement[m^3]", y, 1, weap_scenarios(i), y, 12, Total)
					Next ' wb
				
					expr = expr & CStr(y) & listseparator & CStr(val) & listseparator
				Next  ' y

				expr = Left(expr, Len(expr) - 1) & ")"

				LEAP.Branches("Demand\Agriculture\Syr Darya\Water demand").Variables("Activity Level").ExpressionRS(LEAP.Regions(r).Id, LEAP.Scenarios(leap_scenarios(i)).Id) = expr
			Next  ' r
		Next  ' i (scenario index)
		' END: Move Syr Darya agricultural water requirements from WEAP to LEAP.

		' BEGIN: Calculate LEAP.
		If lang = "RUS" Then msg = "Расчет площади LEAP (итерация " & CStr(completed_iterations+1) & ")." Else msg = "Calculating LEAP area (iteration " & CStr(completed_iterations+1) & ")."
		Call LEAP.ShowProgressBar(procedure_title, msg)
		Call LEAP.SetProgressBar(50)
		
		LEAP.Calculate(False)
		
		While LEAP.IsCalculating
			WEAP.Sleep(1000)		
		Wend
		' END: Calculate LEAP.
		
		' BEGIN: Record target results for this iteration.
		If lang = "RUS" Then msg = "Запись результатов и проверка сходимости (итерация " & CStr(completed_iterations+1) & ")." Else msg = "Recording results and checking for convergence (iteration " & CStr(completed_iterations+1) & ")."
		Call LEAP.ShowProgressBar(procedure_title, msg)
		Call LEAP.SetProgressBar(50)
		
		this_iteration_leap_results = dynamic_length_array((UBound(target_leap_results) + 1) * (UBound(leap_scenarios) + 1) * (UBound(leap_calc_years) + 1))  ' Array of target LEAP result values obtained in this iteration. Contains one set of result values for each scenario in leap_scenarios and year calculated in LEAP; results are ordered by scenario, year, and result in target_leap_results
		
		current_index = 0  ' Index currently being written to this_iteration_leap_results/this_iteration_weap_results
		
		For Each s In leap_scenarios
			For Each y In leap_calc_years
				For Each e In target_leap_results
					' Elements in target_leap_results: Array(branch full name, variable name, region name, unit name)
					this_iteration_leap_results(current_index) = LEAP.Branches(e(0)).Variables(e(1)).ValueRS(LEAP.Regions(e(2)).Id, LEAP.Scenarios(s).Id, y, e(3))
					current_index = current_index + 1
				Next
			Next
		Next
		
		this_iteration_weap_results = dynamic_length_array((UBound(target_weap_results) + 1) * (UBound(weap_scenarios) + 1) * ((WEAP.EndYear - WEAP.BaseYear) + 1))  ' Array of target WEAP result values obtained in this iteration. Contains one set of result values for each scenario in weap_scenarios and year calculated in WEAP; results are ordered by scenario, year, and result in target_weap_results

		current_index = 0
		
		For Each s In weap_scenarios
			For y = WEAP.BaseYear To WEAP.EndYear
				For Each e In target_weap_results
					' Elements in target_weap_results: full branch-variable-unit path
					this_iteration_weap_results(current_index) = WEAP.ResultValue(e, y, 1, s, y, 12, Total)
					current_index = current_index + 1
				Next
			Next
		Next
		' END: Record target results for this iteration.

		' BEGIN: Check for convergence if necessary.
		If completed_iterations > 1 And completed_iterations < max_iterations Then
			results_converged = True  ' Tentative; may be overwritten during following convergence checks
			
			For i = 0 To UBound(this_iteration_leap_results)
				If last_iteration_leap_results(i) = 0 And this_iteration_leap_results(i) <> 0 Then
					results_converged = False
					Exit For
				ElseIf Abs(this_iteration_leap_results(i) / last_iteration_leap_results(i) - 1) > convergence_tol Then
					results_converged = False
					Exit For
				End If
			Next
			
			' Only carry out WEAP convergence checks if all LEAP checks passed
			If results_converged = True Then
				For i = 0 To UBound(this_iteration_weap_results)
					If last_iteration_weap_results(i) = 0 And this_iteration_weap_results(i) <> 0 Then
						results_converged = False
						Exit For
					ElseIf Abs(this_iteration_weap_results(i) / last_iteration_weap_results(i) - 1) > convergence_tol Then
						results_converged = False
						Exit For
					End If
				Next
			End If
			
			If results_converged = True Then
				If lang = "RUS" Then msg = "Все целевые результаты WEAP и LEAP сошлись в пределах заданного допуска (" & CStr(convergence_tol * 100) & "%). Дополнительных итераций расчетов WEAP и LEAP не требуется." Else msg = "All target WEAP and LEAP results converged to within the specified tolerance (" & CStr(convergence_tol * 100) & "%). No additional iterations of WEAP and LEAP calculations are needed."
			
				Call MsgBox(msg, vbOKOnly, procedure_title)
				Exit Do
			End If
		End If
		' END: Check for convergence if necessary.
		
		' Update WEAP and LEAP target results
		last_iteration_leap_results = this_iteration_leap_results
		last_iteration_weap_results = this_iteration_weap_results
		
		completed_iterations = completed_iterations + 1
		
		' If lang = "RUS" Then msg = "Завершена итерация " & completed_iterations & " вычислений WEAP и LEAP. Максимальное количество итераций = " & max_iterations & ". Продолжаем..." Else msg = "Completed iteration #" & completed_iterations & " of WEAP and LEAP calculations. Maximum iterations = " & max_iterations & ". Continuing..."
		
		' Call MsgBox(msg, vbOKOnly, procedure_title)
	Loop
	' END: Carry out iterative calculations.
	
	LEAP.CloseProgressBar
	
	If lang = "RUS" Then msg = "Завершена процедура интеграции WEAP-LEAP." Else msg = "Completed WEAP-LEAP integration procedure."
	Call MsgBox(msg, vbokonly, procedure_title)
End Sub  ' run_wave_model()
' END: Define main integration procedure.

run_wave_model()
'' SIG '' Begin signature block
'' SIG '' MIIhwwYJKoZIhvcNAQcCoIIhtDCCIbACAQExDzANBglg
'' SIG '' hkgBZQMEAgEFADB3BgorBgEEAYI3AgEEoGkwZzAyBgor
'' SIG '' BgEEAYI3AgEeMCQCAQEEEE7wKRaZJ7VNj+Ws4Q8X66sC
'' SIG '' AQACAQACAQACAQACAQAwMTANBglghkgBZQMEAgEFAAQg
'' SIG '' S7Sl7dBEFsTcuVkR0ytlxRQVDjnF6Ie/IIIV6gGo6bag
'' SIG '' ggtcMIIFXzCCBEegAwIBAgIRAJhRmGdnH0nzo4lNRzCZ
'' SIG '' 95cwDQYJKoZIhvcNAQELBQAwfDELMAkGA1UEBhMCR0Ix
'' SIG '' GzAZBgNVBAgTEkdyZWF0ZXIgTWFuY2hlc3RlcjEQMA4G
'' SIG '' A1UEBxMHU2FsZm9yZDEYMBYGA1UEChMPU2VjdGlnbyBM
'' SIG '' aW1pdGVkMSQwIgYDVQQDExtTZWN0aWdvIFJTQSBDb2Rl
'' SIG '' IFNpZ25pbmcgQ0EwHhcNMjAwMjExMDAwMDAwWhcNMjMw
'' SIG '' MjEwMjM1OTU5WjCBzzELMAkGA1UEBhMCVVMxDjAMBgNV
'' SIG '' BBEMBTAyMTQ0MRYwFAYDVQQIDA1NYXNzYWNodXNldHRz
'' SIG '' MRMwEQYDVQQHDApTb21lcnZpbGxlMRkwFwYDVQQJDBAx
'' SIG '' MSBDdXJ0aXMgQXZlbnVlMTMwMQYDVQQKDCpTVE9DS0hP
'' SIG '' TE0gRU5WSVJPTk1FTlQgSU5TVElUVVRFIFUuUy4sIElO
'' SIG '' Qy4xMzAxBgNVBAMMKlNUT0NLSE9MTSBFTlZJUk9OTUVO
'' SIG '' VCBJTlNUSVRVVEUgVS5TLiwgSU5DLjCCASIwDQYJKoZI
'' SIG '' hvcNAQEBBQADggEPADCCAQoCggEBAKL2QAwxGVfd2o1E
'' SIG '' JGn6/nPdNgPolb0qIDMsBVGoKhsvJcXvf7wFGq7VrdeI
'' SIG '' q5ZAXUyKibRAm5jHc0xbItmsgbsHq2ivDngeO4qUsMfR
'' SIG '' UP2pRal0eY4MdoYnmxllA4qU6+lpjLJESNpB2iDa9uLO
'' SIG '' T5nVoYLq+PfW08nhD+jnMXqbfi+TdIfFdJ5PIaGEFVHh
'' SIG '' RWcGk2XYpqLmIHse3XIyHao8qa4j9smZM8Kgb3nX/Rgv
'' SIG '' uEXfrtv2ueXZH0eYcs4I/061Qh6o1oVjsJc2TeFz3DsT
'' SIG '' RAC+5h5Oiz3JGwtfEXeMYJqZWUruCNcfZ43pjrhZC1XI
'' SIG '' VXV54CkDmrwjLRxdz00CAwEAAaOCAYYwggGCMB8GA1Ud
'' SIG '' IwQYMBaAFA7hOqhTOjHVir7Bu61nGgOFrTQOMB0GA1Ud
'' SIG '' DgQWBBSY3etSMrfJrpjt0mpL/zDGzVQ7xTAOBgNVHQ8B
'' SIG '' Af8EBAMCB4AwDAYDVR0TAQH/BAIwADATBgNVHSUEDDAK
'' SIG '' BggrBgEFBQcDAzARBglghkgBhvhCAQEEBAMCBBAwQAYD
'' SIG '' VR0gBDkwNzA1BgwrBgEEAbIxAQIBAwIwJTAjBggrBgEF
'' SIG '' BQcCARYXaHR0cHM6Ly9zZWN0aWdvLmNvbS9DUFMwQwYD
'' SIG '' VR0fBDwwOjA4oDagNIYyaHR0cDovL2NybC5zZWN0aWdv
'' SIG '' LmNvbS9TZWN0aWdvUlNBQ29kZVNpZ25pbmdDQS5jcmww
'' SIG '' cwYIKwYBBQUHAQEEZzBlMD4GCCsGAQUFBzAChjJodHRw
'' SIG '' Oi8vY3J0LnNlY3RpZ28uY29tL1NlY3RpZ29SU0FDb2Rl
'' SIG '' U2lnbmluZ0NBLmNydDAjBggrBgEFBQcwAYYXaHR0cDov
'' SIG '' L29jc3Auc2VjdGlnby5jb20wDQYJKoZIhvcNAQELBQAD
'' SIG '' ggEBAEUXA7d3fTVZ7ynRRHkDLkSi1ExDswu6OywNndVy
'' SIG '' 28BgEcdM2PiosXdt8nZE51J8nrJ1AmVu3QRoJm9+pyix
'' SIG '' L0DYvYQpHBfSyPiYV7yf4o7T58tZuO6lE1Ra2/pZ+l3D
'' SIG '' K5PvGf6fL4uLYjYEUKMwi5ziAuo07rXVbt++x0oH6t4v
'' SIG '' wZpLCZ3kQ4tFz1OKE22w29wp2hfIjz3vfpcTkAH5UPen
'' SIG '' KUa/58lH7zSKGoveRlp68Trye7l+sgAYJuljtPruNtWD
'' SIG '' 3tDn8Xkpe0EcPPSaj14j3QNk0EAOdcXRz6u7wWzAlATs
'' SIG '' IjzGyq5EBd4AB3yQlki1qzpczXTt5sYuXfuYUVswggX1
'' SIG '' MIID3aADAgECAhAdokgwb5smGNCC4JZ9M9NqMA0GCSqG
'' SIG '' SIb3DQEBDAUAMIGIMQswCQYDVQQGEwJVUzETMBEGA1UE
'' SIG '' CBMKTmV3IEplcnNleTEUMBIGA1UEBxMLSmVyc2V5IENp
'' SIG '' dHkxHjAcBgNVBAoTFVRoZSBVU0VSVFJVU1QgTmV0d29y
'' SIG '' azEuMCwGA1UEAxMlVVNFUlRydXN0IFJTQSBDZXJ0aWZp
'' SIG '' Y2F0aW9uIEF1dGhvcml0eTAeFw0xODExMDIwMDAwMDBa
'' SIG '' Fw0zMDEyMzEyMzU5NTlaMHwxCzAJBgNVBAYTAkdCMRsw
'' SIG '' GQYDVQQIExJHcmVhdGVyIE1hbmNoZXN0ZXIxEDAOBgNV
'' SIG '' BAcTB1NhbGZvcmQxGDAWBgNVBAoTD1NlY3RpZ28gTGlt
'' SIG '' aXRlZDEkMCIGA1UEAxMbU2VjdGlnbyBSU0EgQ29kZSBT
'' SIG '' aWduaW5nIENBMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8A
'' SIG '' MIIBCgKCAQEAhiKNMoV6GJ9J8JYvYwgeLdx8nxTP4ya2
'' SIG '' JWYpQIZURnQxYsUQ7bKHJ6aZy5UwwFb1pHXGqQ5QYqVR
'' SIG '' kRBq4Etirv3w+Bisp//uLjMg+gwZiahse60Aw2Gh3Gll
'' SIG '' bR9uJ5bXl1GGpvQn5Xxqi5UeW2DVftcWkpwAL2j3l+1q
'' SIG '' cr44O2Pej79uTEFdEiAIWeg5zY/S1s8GtFcFtk6hPldr
'' SIG '' H5i8xGLWGwuNx2YbSp+dgcRyQLXiX+8LRf+jzhemLVWw
'' SIG '' t7C8VGqdvI1WU8bwunlQSSz3A7n+L2U18iLqLAevRtn5
'' SIG '' RhzcjHxxKPP+p8YU3VWRbooRDd8GJJV9D6ehfDrahjVh
'' SIG '' 0wIDAQABo4IBZDCCAWAwHwYDVR0jBBgwFoAUU3m/Wqor
'' SIG '' Ss9UgOHYm8Cd8rIDZsswHQYDVR0OBBYEFA7hOqhTOjHV
'' SIG '' ir7Bu61nGgOFrTQOMA4GA1UdDwEB/wQEAwIBhjASBgNV
'' SIG '' HRMBAf8ECDAGAQH/AgEAMB0GA1UdJQQWMBQGCCsGAQUF
'' SIG '' BwMDBggrBgEFBQcDCDARBgNVHSAECjAIMAYGBFUdIAAw
'' SIG '' UAYDVR0fBEkwRzBFoEOgQYY/aHR0cDovL2NybC51c2Vy
'' SIG '' dHJ1c3QuY29tL1VTRVJUcnVzdFJTQUNlcnRpZmljYXRp
'' SIG '' b25BdXRob3JpdHkuY3JsMHYGCCsGAQUFBwEBBGowaDA/
'' SIG '' BggrBgEFBQcwAoYzaHR0cDovL2NydC51c2VydHJ1c3Qu
'' SIG '' Y29tL1VTRVJUcnVzdFJTQUFkZFRydXN0Q0EuY3J0MCUG
'' SIG '' CCsGAQUFBzABhhlodHRwOi8vb2NzcC51c2VydHJ1c3Qu
'' SIG '' Y29tMA0GCSqGSIb3DQEBDAUAA4ICAQBNY1DtRzRKYaTb
'' SIG '' 3moqjJvxAAAeHWJ7Otcywvaz4GOz+2EAiJobbRAHBE++
'' SIG '' uOqJeCLrD0bs80ZeQEaJEvQLd1qcKkE6/Nb06+f3FZUz
'' SIG '' w6GDKLfeL+SU94Uzgy1KQEi/msJPSrGPJPSzgTfTt2Sw
'' SIG '' piNqWWhSQl//BOvhdGV5CPWpk95rcUCZlrp48bnI4sMI
'' SIG '' FrGrY1rIFYBtdF5KdX6luMNstc/fSnmHXMdATWM19jDT
'' SIG '' z7UKDgsEf6BLrrujpdCEAJM+U100pQA1aWy+nyAlEA0Z
'' SIG '' +1CQYb45j3qOTfafDh7+B1ESZoMmGUiVzkrJwX/zOgWb
'' SIG '' +W/fiH/AI57SHkN6RTHBnE2p8FmyWRnoao0pBAJ3fEtL
'' SIG '' zXC+OrJVWng+vLtvAxAldxU0ivk2zEOS5LpP8WKTKCVX
'' SIG '' KftRGcehJUBqhFfGsp2xvBwK2nxnfn0u6ShMGH7EezFB
'' SIG '' cZpLKewLPVdQ0srd/Z4FUeVEeN0B3rF1mA1UJP3wTuPi
'' SIG '' +IO9crrLPTru8F4XkmhtyGH5pvEqCgulufSe7pgyBYWe
'' SIG '' 6/mDKdPGLH29OncuizdCoGqC7TtKqpQQpOEN+BfFtlp5
'' SIG '' MxiS47V1+KHpjgolHuQe8Z9ahyP/n6RRnvs5gBHN27XE
'' SIG '' p6iAb+VT1ODjosLSWxr6MiYtaldwHDykWC6j81tLB9wy
'' SIG '' WfOHpxptWDGCFb8wghW7AgEBMIGRMHwxCzAJBgNVBAYT
'' SIG '' AkdCMRswGQYDVQQIExJHcmVhdGVyIE1hbmNoZXN0ZXIx
'' SIG '' EDAOBgNVBAcTB1NhbGZvcmQxGDAWBgNVBAoTD1NlY3Rp
'' SIG '' Z28gTGltaXRlZDEkMCIGA1UEAxMbU2VjdGlnbyBSU0Eg
'' SIG '' Q29kZSBTaWduaW5nIENBAhEAmFGYZ2cfSfOjiU1HMJn3
'' SIG '' lzANBglghkgBZQMEAgEFAKB8MBAGCisGAQQBgjcCAQwx
'' SIG '' AjAAMBkGCSqGSIb3DQEJAzEMBgorBgEEAYI3AgEEMBwG
'' SIG '' CisGAQQBgjcCAQsxDjAMBgorBgEEAYI3AgEVMC8GCSqG
'' SIG '' SIb3DQEJBDEiBCBd1a3GN3b/xC/6jb2TX57FcBPKhIsQ
'' SIG '' Bu/euZznj0PSjzANBgkqhkiG9w0BAQEFAASCAQCRdTZY
'' SIG '' dVgjuKL2fctQTUC7IBIvSyfeOA35rGcHTKlLU3Mm0XiP
'' SIG '' gKM5oVH91J4SxwghwXMH0N0Ez4E325FtzxlSPf3ZXGm6
'' SIG '' arPjnV18V/VrQZlEH4193eay3dOzFWetd+AsMc0BMsfk
'' SIG '' z+GchsYQWuVdBsM8v+hSJKe8PS/gHtw0EN/gu2vwT+hw
'' SIG '' AGJNVJt5n0V+IyOLv2gmaalU2O3s2rRz80GaQ0p4wf6N
'' SIG '' fXVVmO2kiwcby58h50s04kUetG8fkBq1z+tbRZnPSlV0
'' SIG '' Q1rheJl1MWPVz2MoiDn77tzUFqPOtq8Pocj3BXVtV57W
'' SIG '' o88dh0VAcf3em1L4IwdkN3iRCOGroYITgDCCE3wGCisG
'' SIG '' AQQBgjcDAwExghNsMIITaAYJKoZIhvcNAQcCoIITWTCC
'' SIG '' E1UCAQMxDzANBglghkgBZQMEAgIFADCCAQ0GCyqGSIb3
'' SIG '' DQEJEAEEoIH9BIH6MIH3AgEBBgorBgEEAbIxAgEBMDEw
'' SIG '' DQYJYIZIAWUDBAIBBQAEIIAu9DOHqKm8GNKSoyuSXIJK
'' SIG '' YiX2sUHgL4xTaO3oJfffAhUAm54B/S8FvD+tUoukJzbH
'' SIG '' fmlxUPEYDzIwMjIwNTE3MTM0NDIyWqCBiqSBhzCBhDEL
'' SIG '' MAkGA1UEBhMCR0IxGzAZBgNVBAgTEkdyZWF0ZXIgTWFu
'' SIG '' Y2hlc3RlcjEQMA4GA1UEBxMHU2FsZm9yZDEYMBYGA1UE
'' SIG '' ChMPU2VjdGlnbyBMaW1pdGVkMSwwKgYDVQQDDCNTZWN0
'' SIG '' aWdvIFJTQSBUaW1lIFN0YW1waW5nIFNpZ25lciAjMqCC
'' SIG '' DfswggcHMIIE76ADAgECAhEAjHegAI/00bDGPZ86SION
'' SIG '' azANBgkqhkiG9w0BAQwFADB9MQswCQYDVQQGEwJHQjEb
'' SIG '' MBkGA1UECBMSR3JlYXRlciBNYW5jaGVzdGVyMRAwDgYD
'' SIG '' VQQHEwdTYWxmb3JkMRgwFgYDVQQKEw9TZWN0aWdvIExp
'' SIG '' bWl0ZWQxJTAjBgNVBAMTHFNlY3RpZ28gUlNBIFRpbWUg
'' SIG '' U3RhbXBpbmcgQ0EwHhcNMjAxMDIzMDAwMDAwWhcNMzIw
'' SIG '' MTIyMjM1OTU5WjCBhDELMAkGA1UEBhMCR0IxGzAZBgNV
'' SIG '' BAgTEkdyZWF0ZXIgTWFuY2hlc3RlcjEQMA4GA1UEBxMH
'' SIG '' U2FsZm9yZDEYMBYGA1UEChMPU2VjdGlnbyBMaW1pdGVk
'' SIG '' MSwwKgYDVQQDDCNTZWN0aWdvIFJTQSBUaW1lIFN0YW1w
'' SIG '' aW5nIFNpZ25lciAjMjCCAiIwDQYJKoZIhvcNAQEBBQAD
'' SIG '' ggIPADCCAgoCggIBAJGHSyyLwfEeoJ7TB8YBylKwvnl5
'' SIG '' XQlmBi0vNX27wPsn2kJqWRslTOrvQNaafjLIaoF9tFw+
'' SIG '' VhCBNToiNoz7+CAph6x00BtivD9khwJf78WA7wYc3F5O
'' SIG '' k4e4mt5MB06FzHDFDXvsw9njl+nLGdtWRWzuSyBsyT5s
'' SIG '' /fCb8Sj4kZmq/FrBmoIgOrfv59a4JUnCORuHgTnLw7c6
'' SIG '' zZ9QBB8amaSAAk0dBahV021SgIPmbkilX8GJWGCK7/Gs
'' SIG '' zYdjGI50y4SHQWljgbz2H6p818FBzq2rdosggNQtlQeN
'' SIG '' x/ULFx6a5daZaVHHTqadKW/neZMNMmNTrszGKYogwWDG
'' SIG '' 8gIsxPnIIt/5J4Khg1HCvMmCGiGEspe81K9EHJaCIpUq
'' SIG '' hVSu8f0+SXR0/I6uP6Vy9MNaAapQpYt2lRtm6+/a35Qu
'' SIG '' 2RrrTCd9TAX3+CNdxFfIJgV6/IEjX1QJOCpi1arK3+3P
'' SIG '' U6sf9kSc1ZlZxVZkW/eOUg9m/Jg/RAYTZG7p4RVgUKWx
'' SIG '' 7M+46MkLvsWE990Kndq8KWw9Vu2/eGe2W8heFBy5r4Qt
'' SIG '' d6L3OZU3b05/HMY8BNYxxX7vPehRfnGtJHQbLNz5fKrv
'' SIG '' wnZJaGLVi/UD3759jg82dUZbk3bEg+6CviyuNxLxvFbD
'' SIG '' 5K1Dw7dmll6UMvqg9quJUPrOoPMIgRrRRKfM97gxAgMB
'' SIG '' AAGjggF4MIIBdDAfBgNVHSMEGDAWgBQaofhhGSAPw0F3
'' SIG '' RSiO0TVfBhIEVTAdBgNVHQ4EFgQUaXU3e7udNUJOv1fT
'' SIG '' mtufAdGu3tAwDgYDVR0PAQH/BAQDAgbAMAwGA1UdEwEB
'' SIG '' /wQCMAAwFgYDVR0lAQH/BAwwCgYIKwYBBQUHAwgwQAYD
'' SIG '' VR0gBDkwNzA1BgwrBgEEAbIxAQIBAwgwJTAjBggrBgEF
'' SIG '' BQcCARYXaHR0cHM6Ly9zZWN0aWdvLmNvbS9DUFMwRAYD
'' SIG '' VR0fBD0wOzA5oDegNYYzaHR0cDovL2NybC5zZWN0aWdv
'' SIG '' LmNvbS9TZWN0aWdvUlNBVGltZVN0YW1waW5nQ0EuY3Js
'' SIG '' MHQGCCsGAQUFBwEBBGgwZjA/BggrBgEFBQcwAoYzaHR0
'' SIG '' cDovL2NydC5zZWN0aWdvLmNvbS9TZWN0aWdvUlNBVGlt
'' SIG '' ZVN0YW1waW5nQ0EuY3J0MCMGCCsGAQUFBzABhhdodHRw
'' SIG '' Oi8vb2NzcC5zZWN0aWdvLmNvbTANBgkqhkiG9w0BAQwF
'' SIG '' AAOCAgEASgN4kEIz7Hsagwk2M5hVu51ABjBrRWrxlA4Z
'' SIG '' UP9bJV474TnEW7rplZA3N73f+2Ts5YK3lcxXVXBLTvSo
'' SIG '' h90ihaZXu7ghJ9SgKjGUigchnoq9pxr1AhXLRFCZjOw+
'' SIG '' ugN3poICkMIuk6m+ITR1Y7ngLQ/PATfLjaL6uFqarqF6
'' SIG '' nhOTGVWPCZAu3+qIFxbradbhJb1FCJeA11QgKE/Ke7Oz
'' SIG '' pdIAsGA0ZcTjxcOl5LqFqnpp23WkPnlomjaLQ6421GFy
'' SIG '' PA6FYg2gXnDbZC8Bx8GhxySUo7I8brJeotD6qNG4JRwW
'' SIG '' 5sDVf2gaxGUpNSotiLzqrnTWgufAiLjhT3jwXMrAQFzC
'' SIG '' n9UyHCzaPKw29wZSmqNAMBewKRaZyaq3iEn36AslM7U/
'' SIG '' ba+fXwpW3xKxw+7OkXfoIBPpXCTH6kQLSuYThBxN6w21
'' SIG '' uIagMKeLoZ+0LMzAFiPJkeVCA0uAzuRN5ioBPsBehaAk
'' SIG '' oRdA1dvb55gQpPHqGRuAVPpHieiYgal1wA7f0GiUeaGg
'' SIG '' no62t0Jmy9nZay9N2N4+Mh4g5OycTUKNncczmYI3RNQm
'' SIG '' KSZAjngvue76L/Hxj/5QuHjdFJbeHA5wsCqFarFsaOkq
'' SIG '' 5BArbiH903ydN+QqBtbD8ddo408HeYEIE/6yZF7psTzm
'' SIG '' 0Hgjsgks4iZivzupl1HMx0QygbKvz98wggbsMIIE1KAD
'' SIG '' AgECAhAwD2+s3WaYdHypRjaneC25MA0GCSqGSIb3DQEB
'' SIG '' DAUAMIGIMQswCQYDVQQGEwJVUzETMBEGA1UECBMKTmV3
'' SIG '' IEplcnNleTEUMBIGA1UEBxMLSmVyc2V5IENpdHkxHjAc
'' SIG '' BgNVBAoTFVRoZSBVU0VSVFJVU1QgTmV0d29yazEuMCwG
'' SIG '' A1UEAxMlVVNFUlRydXN0IFJTQSBDZXJ0aWZpY2F0aW9u
'' SIG '' IEF1dGhvcml0eTAeFw0xOTA1MDIwMDAwMDBaFw0zODAx
'' SIG '' MTgyMzU5NTlaMH0xCzAJBgNVBAYTAkdCMRswGQYDVQQI
'' SIG '' ExJHcmVhdGVyIE1hbmNoZXN0ZXIxEDAOBgNVBAcTB1Nh
'' SIG '' bGZvcmQxGDAWBgNVBAoTD1NlY3RpZ28gTGltaXRlZDEl
'' SIG '' MCMGA1UEAxMcU2VjdGlnbyBSU0EgVGltZSBTdGFtcGlu
'' SIG '' ZyBDQTCCAiIwDQYJKoZIhvcNAQEBBQADggIPADCCAgoC
'' SIG '' ggIBAMgbAa/ZLH6ImX0BmD8gkL2cgCFUk7nPoD5T77Na
'' SIG '' wHbWGgSlzkeDtevEzEk0y/NFZbn5p2QWJgn71TJSeS7J
'' SIG '' Y8ITm7aGPwEFkmZvIavVcRB5h/RGKs3EWsnb111JTXJW
'' SIG '' D9zJ41OYOioe/M5YSdO/8zm7uaQjQqzQFcN/nqJc1zjx
'' SIG '' FrJw06PE37PFcqwuCnf8DZRSt/wflXMkPQEovA8NT7OR
'' SIG '' AY5unSd1VdEXOzQhe5cBlK9/gM/REQpXhMl/VuC9RpyC
'' SIG '' vpSdv7QgsGB+uE31DT/b0OqFjIpWcdEtlEzIjDzTFKKc
'' SIG '' vSb/01Mgx2Bpm1gKVPQF5/0xrPnIhRfHuCkZpCkvRuPd
'' SIG '' 25Ffnz82Pg4wZytGtzWvlr7aTGDMqLufDRTUGMQwmHSC
'' SIG '' Ic9iVrUhcxIe/arKCFiHd6QV6xlV/9A5VC0m7kUaOm/N
'' SIG '' 14Tw1/AoxU9kgwLU++Le8bwCKPRt2ieKBtKWh97oaw7w
'' SIG '' W33pdmmTIBxKlyx3GSuTlZicl57rjsF4VsZEJd8GEpoG
'' SIG '' LZ8DXv2DolNnyrH6jaFkyYiSWcuoRsDJ8qb/fVfbEnb6
'' SIG '' ikEk1Bv8cqUUotStQxykSYtBORQDHin6G6UirqXDTYLQ
'' SIG '' jdprt9v3GEBXc/Bxo/tKfUU2wfeNgvq5yQ1TgH36tjlY
'' SIG '' Mu9vGFCJ10+dM70atZ2h3pVBeqeDAgMBAAGjggFaMIIB
'' SIG '' VjAfBgNVHSMEGDAWgBRTeb9aqitKz1SA4dibwJ3ysgNm
'' SIG '' yzAdBgNVHQ4EFgQUGqH4YRkgD8NBd0UojtE1XwYSBFUw
'' SIG '' DgYDVR0PAQH/BAQDAgGGMBIGA1UdEwEB/wQIMAYBAf8C
'' SIG '' AQAwEwYDVR0lBAwwCgYIKwYBBQUHAwgwEQYDVR0gBAow
'' SIG '' CDAGBgRVHSAAMFAGA1UdHwRJMEcwRaBDoEGGP2h0dHA6
'' SIG '' Ly9jcmwudXNlcnRydXN0LmNvbS9VU0VSVHJ1c3RSU0FD
'' SIG '' ZXJ0aWZpY2F0aW9uQXV0aG9yaXR5LmNybDB2BggrBgEF
'' SIG '' BQcBAQRqMGgwPwYIKwYBBQUHMAKGM2h0dHA6Ly9jcnQu
'' SIG '' dXNlcnRydXN0LmNvbS9VU0VSVHJ1c3RSU0FBZGRUcnVz
'' SIG '' dENBLmNydDAlBggrBgEFBQcwAYYZaHR0cDovL29jc3Au
'' SIG '' dXNlcnRydXN0LmNvbTANBgkqhkiG9w0BAQwFAAOCAgEA
'' SIG '' bVSBpTNdFuG1U4GRdd8DejILLSWEEbKw2yp9KgX1vDsn
'' SIG '' 9FqguUlZkClsYcu1UNviffmfAO9Aw63T4uRW+VhBz/FC
'' SIG '' 5RB9/7B0H4/GXAn5M17qoBwmWFzztBEP1dXD4rzVWHi/
'' SIG '' SHbhRGdtj7BDEA+N5Pk4Yr8TAcWFo0zFzLJTMJWk1vSW
'' SIG '' Vgi4zVx/AZa+clJqO0I3fBZ4OZOTlJux3LJtQW1nzclv
'' SIG '' kD1/RXLBGyPWwlWEZuSzxWYG9vPWS16toytCiiGS/qhv
'' SIG '' WiVwYoFzY16gu9jc10rTPa+DBjgSHSSHLeT8AtY+dwS8
'' SIG '' BDa153fLnC6NIxi5o8JHHfBd1qFzVwVomqfJN2Udvuq8
'' SIG '' 2EKDQwWli6YJ/9GhlKZOqj0J9QVst9JkWtgqIsJLnfE5
'' SIG '' XkzeSD2bNJaaCV+O/fexUpHOP4n2HKG1qXUfcb9bQ11l
'' SIG '' PVCBbqvw0NP8srMftpmWJvQ8eYtcZMzN7iea5aDADHKH
'' SIG '' wW5NWtMe6vBE5jJvHOsXTpTDeGUgOw9Bqh/poUGd/rG4
'' SIG '' oGUqNODeqPk85sEwu8CgYyz8XBYAqNDEf+oRnR4GxqZt
'' SIG '' Ml20OAkrSQeq/eww2vGnL8+3/frQo4TZJ577AWZ3uVYQ
'' SIG '' 4SBuxq6x+ba6yDVdM3aO8XwgDCp3rrWiAoa6Ke60WgCx
'' SIG '' jKvj+QrJVF3UuWp0nr1IrpgxggQtMIIEKQIBATCBkjB9
'' SIG '' MQswCQYDVQQGEwJHQjEbMBkGA1UECBMSR3JlYXRlciBN
'' SIG '' YW5jaGVzdGVyMRAwDgYDVQQHEwdTYWxmb3JkMRgwFgYD
'' SIG '' VQQKEw9TZWN0aWdvIExpbWl0ZWQxJTAjBgNVBAMTHFNl
'' SIG '' Y3RpZ28gUlNBIFRpbWUgU3RhbXBpbmcgQ0ECEQCMd6AA
'' SIG '' j/TRsMY9nzpIg41rMA0GCWCGSAFlAwQCAgUAoIIBazAa
'' SIG '' BgkqhkiG9w0BCQMxDQYLKoZIhvcNAQkQAQQwHAYJKoZI
'' SIG '' hvcNAQkFMQ8XDTIyMDUxNzEzNDQyMlowPwYJKoZIhvcN
'' SIG '' AQkEMTIEMPzRI9AcdHTw6PmvPaA4vvvKTG0XTd1LvLk2
'' SIG '' 6P68ZQv+7wCpnWemCzSnU7ApRriRTzCB7QYLKoZIhvcN
'' SIG '' AQkQAgwxgd0wgdowgdcwFgQUlRE3EB2ILzG9UT+UmtpM
'' SIG '' aK2MCPUwgbwEFALWW5Xig3DBVwCV+oj5I92Tf62PMIGj
'' SIG '' MIGOpIGLMIGIMQswCQYDVQQGEwJVUzETMBEGA1UECBMK
'' SIG '' TmV3IEplcnNleTEUMBIGA1UEBxMLSmVyc2V5IENpdHkx
'' SIG '' HjAcBgNVBAoTFVRoZSBVU0VSVFJVU1QgTmV0d29yazEu
'' SIG '' MCwGA1UEAxMlVVNFUlRydXN0IFJTQSBDZXJ0aWZpY2F0
'' SIG '' aW9uIEF1dGhvcml0eQIQMA9vrN1mmHR8qUY2p3gtuTAN
'' SIG '' BgkqhkiG9w0BAQEFAASCAgAldy3mzbqTwnNfssbXZQ0N
'' SIG '' 0PcPJzplykWAxzYUiweT1llj0YhW3UwoO8/FGvu+EKEB
'' SIG '' 5oJ0dHMr1HTHoYbk8eovlY3H0BHQXDGprvWEWOi7He69
'' SIG '' CW7wK0puAeJk19RMQJy98oSUC2eKj10COXMupX73ITWS
'' SIG '' YKNoFv3z4pJNqUHDAOwYKBtqM7yzEWOYWPGiEoR5eK47
'' SIG '' tGCDI/GiuK8nnYHppoU4jb+Fu3aLni3CttKZxDYwmcLk
'' SIG '' u4xwRuagfyN51bKYDIs3hs+IksTLIoLdUZp77p4E7W7E
'' SIG '' ZIUVrjnn0aMNgcE8wJu+ccV66Dfabnx7+BBS7TveuBag
'' SIG '' CJaUVrazNAVwi2WadJ6i5FGonzri2Qba0NM0kMDqcBiJ
'' SIG '' mSNKucU2JAe2IgwxRaeFQSUUtLlc7pynLKgLUKDQNrWV
'' SIG '' n5j1zkalEk+l0uU1zGQKSbTZ6b+RyeIlMikXSA+6gK3s
'' SIG '' jlS4MhfufExXyG+/Tvvc/ph5vOOqSAUZDmbIS9CAIWa9
'' SIG '' dJ4Ff2O7zgtoat1k/0z25soRRTIZ0TdCFslotV2wpsjq
'' SIG '' igofnawLYDyYWH7/OCnVrFhmrV1qyEnYrDcGvkqfpoBE
'' SIG '' cGDd3k+GmKKPVvN0WPKvvQXg20N6TBo7JXInzhm82owj
'' SIG '' f4+H9Ty56VsVj5EIOlZy3RfA3tQjfDRE764YMcGzf48x+Q==
'' SIG '' End signature block
