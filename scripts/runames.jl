# script 'runames.jl'
using AMES
using YAML
using ArgParse

function parse_commandline()
    argp = ArgParseSettings(autofix_names = true)
    @add_arg_table! argp begin
        "scenario"
            help = "name of the scenario"
            arg_type = AbstractString
            required = true
        "--config-file", "-f"
            help = "name of the base configuration file"
            arg_type = AbstractString
            default = "config.yml"
        "--verbose-errors", "-v"
            help = "send detailed error message to log file"
            action = :store_true
        "--include-energy-sectors", "-e"
            help = "include energy sectors in the model simulation"
            action = :store_true
        "--continue-if-error", "-c"
            help = "try to continue if the linear goal program returns an error"
            action = :store_true
        "--load-leap-first", "-l"
            help = "load results from LEAP before running AMES"
            action = :store_true
        "--use-leap-version", "-u"
            help = "If load-leap-first is set, pull results from this version"
			# Default arg_type = Any
			# Default default = nothing
        "--only-push-leap-results", "-p"
            help = "only push results to LEAP and do not run LEAP from AMES"
            action = :store_true
        "--init-run-number", "-r"
            help = "initial run number"
			arg_type = Int64
            default = 0
        "--report-diagnostics", "-d"
            help = "report diagnostic information"
            action = :store_true
        "--suppress-leap", "-s"
            help = "hide LEAP while running"
            action = :store_true
        "--final-year", "-y"
            help = "final year in LEAP"
 			arg_type = Int64
            default = 2050
        "--use-weap-results", "-w"
            help = "use exported WEAP results"
            action = :store_true
    end

    return parse_args(argp)
end

"Return a string vector whether given a string or a vector of strings"
function stringvec(s::Union{String,Vector{String}})
	if s isa String
		return [s]
	else
		return s
	end
end

"Check whether a Dict has a key and that the value is not `nothing`"
function haskeyvalue(d::Dict, k::Any)
    return haskey(d,k) && !isnothing(d[k])
end # haskeyvalue

curr_working_dir = pwd()
cd(@__DIR__)

# Get command line arguments
parsed_args = parse_commandline()

# Read the config file
cfg_file = parsed_args["config_file"]
cfg_yaml = YAML.load_file(cfg_file)

# These must be set to these values for the script to work
cfg_yaml["model"]["run_leap"] = true
cfg_yaml["model"]["max_runs"] = 0

if parsed_args["init_run_number"] != 0
    cfg_yaml["clear-folders"]["results"] = false
    cfg_yaml["clear-folders"]["calibration"] = false
    cfg_yaml["clear-folders"]["diagnostics"] = false
end

#--------------------------------------------
# Get options from command line
#--------------------------------------------
cfg_yaml["output_folder"] = parsed_args["scenario"]
cfg_yaml["LEAP-info"]["scenario"] = parsed_args["scenario"]
cfg_yaml["model"]["hide_leap"] = parsed_args["suppress_leap"]
cfg_yaml["years"]["end"] = parsed_args["final_year"]
cfg_yaml["report-diagnostics"] = parsed_args["report_diagnostics"]

#--------------------------------------------
# Several cases for exogenous files
#--------------------------------------------
exog_dict = Dict(
				 "pot_output" => "_realoutputindex",
				 "max_util" => "_max_util",
				 "real_price" => "_priceindex"
				)
exog_files_block = cfg_yaml["exog-files"]
for (c, f) in exog_dict
	# First, clean up by getting rid of any prior integration script filenames
	if haskeyvalue(exog_files_block, c)
		flist = stringvec(exog_files_block[c])
		deleteat!(flist, occursin.(f, flist))
	else
		flist = []
	end
	# Next, if using WEAP results, add integration script filenames
	if parsed_args["use_weap_results"]
		push!(flist, parsed_args["scenario"] * f * ".csv")
	end
	# Finally, assign to the YAML file
	if length(flist) > 0
		exog_files_block[c] = flist
	else
		exog_files_block[c] = nothing
	end
end

YAML.write_file(cfg_file, cfg_yaml)

AMES.run(parsed_args["config_file"],
              dump_err_stack = parsed_args["verbose_errors"],
			  load_leap_first = parsed_args["load_leap_first"],
              get_results_from_leap_version = parsed_args["use_leap_version"], 
			  only_push_leap_results = parsed_args["only_push_leap_results"],
              run_number_start = parsed_args["init_run_number"],
              include_energy_sectors = parsed_args["include_energy_sectors"],
              continue_if_error = parsed_args["continue_if_error"])
			  
cd(curr_working_dir)
