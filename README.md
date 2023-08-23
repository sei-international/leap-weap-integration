# Integrating LEAP, WEAP, and Macro
The scripts in this repository implement the integration between LEAP/NEMO, WEAP, and Macro for the USAID WAVE Central Asia project. The integration script, which is written in Python, executes each program iteratively until convergence. Both LEAP and WEAP require Windows to run, and the full integration can consume substantial computer resources. The computer on which this script is run should have a reasonably fast processor and, more important, ample RAM and disk drive space.

## Installation
In addition to the integration script itself, it is necessary to first install Python, LEAP (with NEMO), WEAP, and Macro. It is also recommended to install the [Notepad++ text editor](https://notepad-plus-plus.org/), for reasons explained below.

### Installing Python
Download and install the [latest Python 3 release](https://www.python.org/downloads/windows/).

- Look for the "Windows installer", and select either 32-bit or 64-bit, depending on your computer hardware.
- When you run the installer, make sure to check "Add python.exe to PATH".
- After installing, open a Windows command prompt and run the following command:
	```
	pip install pywin32 psutil PyYaml numpy pandas
	```

### Installing NEMO, LEAP, WEAP, and Macro
For LEAP and WEAP, a license is required. Go to the [LEAP](https://leap.sei.org/) and [WEAP](https://weap.sei.org/) websites to obtain licenses. You may be available for a free or reduced-cost license. Use the contact information on the websites for more information.

Both NEMO and Macro are written in Julia. They are open-source programs and do not require licenses. NEMO will install a copy of Julia, so it is convenient to install NEMO before Macro.

To set up the full system:
1. Go to the [WEAP](https://weap.sei.org/index.asp?action=40) download page, log in, download **WEAP**, and install it;
1. Go to the [LEAP](https://leap.sei.org/default.asp?action=download) download page, log in, download **LEAP** and **NEMO**, and install both of them;
3. Go to the [Macro](https://sei-international.github.io/LEAPMacro.jl/stable/installation/) installation page and follow the instructions.
> If the Macro installation gives an error relating to Julia's `CSV` package or `Parsers.Options`, revert to version 0.10.4 of the CSV package:
>1. Open a Julia prompt;
>1. Press the `]` key to start the package manager;
>1. Type `add CSV@0.10.4` and press enter to install version 0.10.4.
### Installing the integration program
The integration program, with configuration scripts and translations, is available as a ZIP file. It is included as part of a release of the integration software on this site. Download the most recent ZIP file and unzip it in a convenient location on your computer.

Note that the integration program requires the Julia `ArgParse` package. You must add it manually:
1. Open a Julia prompt;
1. Press the `]` key to start the package manager;
1. Type `add ArgParse` and press enter.

## Loading the models
Find the most recent LEAP and WEAP models. These will be made available separately -- for example, via Dropbox. They should have `.leap` and `.weap` extensions. Open the files by double-clicking on them and they will be added to the Areas available from inside LEAP and WEAP.

The most recent Macro files will also be available separately. These are in the form of folders, such as "KAZ_Macro". To use the integration program out of the box, do the following:
1. Find where the `LEAP Areas` folder is located (its "parent" folder) -- this will usually be your `Documents` folder;
1. In the `LEAP Areas` parent folder (e.g., `Documents`), create a new folder called `WAVE_Macro`.
1. Copy all of the Macro models into that folder.

If you prefer a different folder name, you will need to change the name in the `config.yml` configuration file for the integration script.

## Running the integration program
1. Navigate to the folder where you have installed the integration program.
1. Open the `scenarios.yml` file and confirm that the WEAP and LEAP scenarios are properly mapped one to the other. (It is convenient to view the file in Notepad++ because it color-codes the text to make it easier to read.)
1. Open the `config.yml` file and confirm that the correct LEAP and WEAP Areas are listed.
1. Start LEAP and then
  1. Open the most recent WAVE LEAP area;
  1. Select the scenarios that you wish to run;
  1. Select the end year for the run.
1. Start WEAP and open the most recent WAVE WEAP area.
1. If available, double-click on the `wave_integration.exe` file or open a terminal window and run the file from there
   - change directory to `leap-weap-integration` folder
   - `.\run.bat`

The integration program will generate a log file. The log file will have the time stamp and end in `.log`. (E.g., `wave_integration_2023-06-24UTC15_02_54.log`.) The progress of the program can be monitored by watching the log file. There are at least two ways to do that:
- Open the log file in Notepad++ and click the "eye" icon (the `Monitoring (tail -f)` command);
- Open a Windows PowerShell window and run `Get-Content logfilename.log -Wait`, where `logfilename.log` is the name of the log file.
