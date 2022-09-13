# leap-weap-integration
Code for integrating LEAP and WEAP models

Runs on python 3.9
Required files: 
                - Main script: wave_integration.py 
                - Integration config file: config.yaml
                - Scenario config file: scenario.yaml
                - KAZ_Macro folder: needs to located in the LEAP area wave central asia v35 folder

**Set-up instructions**
1. Install and register LEAP,  WEAP and NEMO softwares
2. Install latest LEAP and WEAP areas for WAVE
3. 
4. Install python3.9 and required packages (for full list see leap-weap-integration repository)
5. Download leap-weap-integration repository from github
6. If running with LEAP-Macro:
      a. Open Julia and add LEAP-Macro package
      b. Place LEAP-Macro country folders in LEAP area for each region you would like to run
6. Open LEAP area and select scenarios you would like to run (for production run all will be activated) - save
7. Configure config file as needed:
    - area name in config.yml needs to match they one you would like to use
    - comment out LEAP-Macro if you do not want run leap-macro
8. Open command prompt window and change to wave-integration directory
9. Execute integration by typing in command prompt window:
    $ python3.9 wave_integration.py

Default version will execute in English language with LEAP-Macro turned on
