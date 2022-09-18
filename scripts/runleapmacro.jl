# script 'runleapmacro.jl'
using LEAPMacro
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
            help = "load results from LEAP before running Macro"
            action = :store_true
        "--only-push-leap-results", "-p"
            help = "only push results to LEAP and do not run LEAP from Macro"
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

curr_working_dir = pwd()
cd(@__DIR__)

parsed_args = parse_commandline()
cfg_file = parsed_args["config_file"]
cfg_yaml = YAML.load_file(cfg_file)
# These must be set to these values for the script to work
cfg_yaml["model"]["run_leap"] = true
cfg_yaml["model"]["max_runs"] = 0
# Get options from command line
cfg_yaml["output_folder"] = parsed_args["scenario"]
cfg_yaml["LEAP-info"]["scenario"] = parsed_args["scenario"]
cfg_yaml["model"]["hide_leap"] = parsed_args["suppress_leap"]
cfg_yaml["years"]["end"] = parsed_args["final_year"]
cfg_yaml["report-diagnostics"] = parsed_args["report_diagnostics"]

if parsed_args["use_weap_results"]
	cfg_yaml["exog-files"]["pot_output"] = parsed_args["scenario"] * "_realoutputindex.csv"
	cfg_yaml["exog-files"]["max_util"] = parsed_args["scenario"] * "_max_util.csv"
	cfg_yaml["exog-files"]["real_price"] = parsed_args["scenario"] * "_priceindex.csv"
end

if parsed_args["init_run_number"] != 0
    cfg_yaml["clear-folders"]["results"] = false
    cfg_yaml["clear-folders"]["calibration"] = false
    cfg_yaml["clear-folders"]["diagnostics"] = false
end
YAML.write_file(cfg_file, cfg_yaml)

LEAPMacro.run(parsed_args["config_file"],
              dump_err_stack = parsed_args["verbose_errors"],
			  load_leap_first = parsed_args["load_leap_first"],
			  only_push_leap_results = parsed_args["only_push_leap_results"],
              run_number_start = parsed_args["init_run_number"],
              include_energy_sectors = parsed_args["include_energy_sectors"],
              continue_if_error = parsed_args["continue_if_error"])
			  
cd(curr_working_dir)
