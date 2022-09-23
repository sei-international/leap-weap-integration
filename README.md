# leap-weap-integration
Code for integrating LEAP and WEAP models

Runs on python 3.9
Repository contains: 
                - Main run script: wave_integration.py 
                - Integration config file: config.yaml
                - Scenario config file: scenario.yaml
                

**Set-up instructions**
1. Download and install solver of your choice: Gurobi, CPLEX or Highs
2. Install and register *NEMO*, *LEAP*, and *WEAP* softwares (in this order):
      - *NEMO v1.9*: download from this link https://www.dropbox.com/s/roa3iezrc8lg908/nemo-1.9.0-win64-install.exe?dl=0https://www.dropbox.com/s/roa3iezrc8lg908/nemo-1.9.0-win64-install.exe?dl=0
      - LEAP v77 beta: https://www.dropbox.com/s/faxrq60je31x29y/LEAP2020.1.77_64.exe?dl=0
      - latest WEAP model from website
3. Install *python3.9* and required packages for leap-weap-integration:
      - python 3.9.13 executable for windows: https://www.python.org/downloads/release/python-3914/ (this should also install pip)
        (Note: sometimes requires adding new (preferably system) environment variable: 
            Variable Name: PYTHON 
            Variable: location of python executable\python.exe
      - in command prompt window run:
        ```
        pip install pyyaml pywin32 psutil numpy pandas
        ```
        (if pip command is not recognised, get `get-pip.py` script (https://bootstrap.pypa.io/get-pip.py) and place in python installation folder;from command prompt window, change to python installation folder and run `py -3.9 get-pip.py`; change to where pip is installed (usually scripts folder in python installation folder) and run above installation command)
4. Download and install latest LEAP and WEAP areas for WAVE, currently:
      -  LEAP: wave central asia v41 (this will come with require LEAP-Macro country folders, if not or outdated check here: https://www.dropbox.com/home/USAID%20Central%20Asia%20WAVE%20project/Economic%20Modeling)
      -  WEAP: WAVE-SyrDarya 2022_09_13_MABIA 
5. Download or clone leap-weap-integration repository from github and place anywhere on your machine
6. If running with LEAP-Macro:
      - Open Julia window, and add LEAP-Macro package : 
      ```
      julia> ]

      pkg> add https://github.com/sei-international/LEAPMacro.jl
      ```
      - add and build PyCall: 
      ```
      julia> ]

      pkg> add PyCall
      pkg> build PyCall 
      ```
7. Configure config file as needed:
      - ensure area name in config.yml matches the LEAP and WEAP areas you would like to use
      - comment out LEAP-Macro if you do not want run leap-macro
8. In command prompt window, change to leap-weap-integration directory and execute integration script:
```
      python3.9 wave_integration.py
```
Default version will execute with LEAP-Macro turned on.
