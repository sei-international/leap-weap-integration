# Integrating LEAP, WEAP, and AMES
The scripts in this repository implement the integration between LEAP/NEMO, WEAP, and AMES for the USAID WAVE Central Asia project. The integration script, which is written in Python, executes each program iteratively until convergence. Both LEAP and WEAP require Windows to run, and the full integration can consume substantial computer resources. The computer on which this script is run should have a reasonably fast processor and, more important, ample RAM and disk drive space.

## Installation
In addition to the integration script itself, it is necessary to install Python, LEAP (with NEMO), WEAP, AMES, and Microsoft Excel. It is also recommended to install the [Notepad++ text editor](https://notepad-plus-plus.org/), for reasons explained below.

### Installing Python
Download and install the [latest Python 3 release](https://www.python.org/downloads/windows/).

- Look for the "Windows installer", and select either 32-bit or 64-bit, depending on your computer hardware.
- When you run the installer, make sure to check "Add python.exe to PATH".
- After installing, open a Windows command prompt and run the following command:
	```
	pip install pywin32 psutil PyYaml numpy pandas XlsxWriter
	```

### Installing NEMO, LEAP, WEAP, and AMES
For LEAP and WEAP, a license is required. Go to the [LEAP](https://leap.sei.org/) and [WEAP](https://weap.sei.org/) websites to obtain licenses. You may be eligible for a free or reduced-cost license. Use the contact information on the websites for more information.

Both NEMO and AMES are written in Julia. They are open-source programs and do not require licenses. NEMO will install a copy of Julia, so it is convenient to install NEMO before AMES.

To set up the full system:
1. Go to the [WEAP](https://weap.sei.org/index.asp?action=40) download page, log in, download **WEAP**, and install it;
1. Go to the [LEAP](https://leap.sei.org/default.asp?action=download) download page, log in, download **LEAP** and **NEMO**, and install both of them;
3. If you are going to use AMES, go to the [AMES](https://sei-international.github.io/AMES.jl/stable/installation/) installation page and follow the instructions.
> If the AMES installation gives an error relating to Julia's `CSV` package or `Parsers.Options`, revert to version 0.10.4 of the CSV package:
>1. Open a Julia prompt;
>1. Press the `]` key to start the package manager;
>1. Type `add CSV@0.10.4` and press enter to install version 0.10.4.

### Installing Excel
Install Excel in the usual way. Then it is recommended to disable Excel's AutoRecover feature, as it can cause problems when restarting Excel after a crash of the integration program. To do this in Excel for Microsoft 365 (Version 2403 from April 2024), open Excel, choose File -> Options -> Save, and clear the checkbox for "Save AutoRecover information".

### Installing the integration program
The integration program, with configuration scripts and translations, is available from this website Github. You can either clone it, or you can download it as a ZIP file. Download the most recent ZIP file and unzip it in a convenient location on your computer (usually as a folder under Documents).

Note that the integration program requires the Julia `ArgParse` package. While julia will have already been installed during the installation of NEMO, you must add the package manually:
1. Open a Julia prompt;
1. Press the `]` key to start the package manager;
1. Type `add ArgParse` and press enter.

## Loading the models
Find the most recent LEAP and WEAP models. These will be made available separately -- for example, via Dropbox. They should have `.leap` and `.weap` extensions. Open the files by double-clicking on them, and they will be added to the areas available inside LEAP and WEAP. Then enable scripts in LEAP by going to Settings -> Scripts and choosing to run all scripts without approval. This is necessary because the integration program dynamically adds a script to the LEAP model to improve the robustness of LEAP's interactions with Excel.

The most recent AMES files will also be available separately. These are in the form of folders, such as "KAZ_Macro". To use the integration program out of the box, do the following:
1. Find where the `LEAP Areas` folder is located (its "parent" folder) -- this will usually be your `Documents` folder;
1. In the `LEAP Areas` parent folder (e.g., `Documents`), create a new folder called `WAVE_Macro`.
1. Copy all of the AMES models into that folder.

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
1. If available, double-click on the `wave_integration.exe` file or open a terminal window and run the file from there.
   Otherwise, open a terminal window or command prompt window
   - change directory to `leap-weap-integration` folder (e.g. `cd Documents/leap-weap-integration`)
   - then execute the python file (e.g. `py .\leap_weap_integration.py`)

The integration program will generate a log file. The log file will have the time stamp and end in `.log`. (E.g., `wave_integration_2023-06-24UTC15_02_54.log`.) The progress of the program can be monitored by watching the log file. There are at least two ways to do that:
- Open the log file in Notepad++ and click the "eye" icon (the `Monitoring (tail -f)` command);
- Open a Windows PowerShell window and run `Get-Content logfilename.log -Wait`, where `logfilename.log` is the name of the log file
