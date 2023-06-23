# Integrating LEAP, WEAP, and Macro
The scripts in this repository implement the integration between LEAP/NEMO, WEAP, and Macro for the USAID WAVE Central Asia project. The integration script, which is written in Python, executes each program iteratively until convergence. Both LEAP and WEAP require Windows to run, and the full integration can consume substantial computer resources. The computer on which this script is run should have a reasonably fast processor and, more important, ample RAM and disk drive space.

Runs on python 3.9
Repository contains: 
                - Main run script: wave_integration.py 
                - Integration config file: config.yaml
                - Scenario config file: scenario.yaml
                

## NOTES

 - Set scenarios and years in LEAP -- ones in WEAP are ignored
 - Have both LEAP and WEAP open

 - Strongly recommend Notepad++

## Installing NEMO, LEAP, WEAP, and Macro
To run the installation file, it is necessary to have a license for LEAP and WEAP. Go to the [LEAP](https://leap.sei.org/) and [WEAP](https://weap.sei.org/) websites to obtain licenses.

Both NEMO and Macro are written in Julia. They are open-source programs and do not require licenses. NEMO will install a copy of Julia, so it is best to install NEMO before Macro.

To set up the full system:
- Go to the [WEAP](https://weap.sei.org/index.asp?action=40) download page, log in, download **WEAP**, and install it;
- Go to the [LEAP](https://leap.sei.org/default.asp?action=download) download page, log in, download **LEAP** and **NEMO**, and install both of them.

After NEMO has been installed,
- Go to the [Macro](https://sei-international.github.io/LEAPMacro.jl/stable/installation/) installation page and follow the instructions.

## Installing the integration script
