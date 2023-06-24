# -*- coding: utf-8 -*-
"""
Created on Tue Sep 13 12:48:10 2022

@author: emily
"""

import numpy as np
import pandas as pd
import os

# Load and calculate correct scenario
def load_weap_scen(WEAP, weap_scenario):
    WEAP.View = "Results"
    WEAP.ActiveScenario = weap_scenario
    
# Export WEAP files    
def export_csv(WEAP, fname, favname):
    WEAP.LoadFavorite(favname)
    WEAP.ExportResults(fname)

# WEAP favorites to export
def get_weap_ag_results(fdirweapoutput, fdirmain, weap_scenario, WEAP, rowskip):
    """Export WEAP favorites so they can be converted to Macro inputs using weap_to_macro_processing()
    
    Input arguments:
        fdirweapoutput: the folder for WEAP outputs as prepared by get_weap_ag_results()
        fdirmain: the folder containing LEAP_Macro models
        weap_scenario, leap_scenario: strings labeling the WEAP and LEAP scenarios to pull from and push to
        WEAP: WEAP object
        rowskip: Number of rows to skip in WEAP favorites export files
        
    Returns: Pandas dataframes for weap_to_macro_processing():
        dfcov: Demand site coverage at detailed level
        dfcovdmd: Water demand used as weights to calculate average coverage
        dfcrop: Potential crop production using MABIA potential yields and crop areas
        dfcropprice: Crop prices
    
    TODO: Specify list_separator
    """
    
    load_weap_scen(WEAP, weap_scenario)
    
    #------------------------------------
    # Coverage (for utilization calculation)
    #------------------------------------
    # Coverage
    favname = "WEAP Macro\Demand Site Coverage"
    fname = os.path.join(fdirweapoutput, weap_scenario + "_Coverage_Percent.csv")
    export_csv(WEAP, fname, favname) 
    dfcov = pd.read_csv(fname, skiprows=rowskip) 
    
    # Water demand in order to figure out coverage for each country
    favname = "WEAP Macro\Water Demand Annual Total - Level 1"
    fname = os.path.join(fdirweapoutput, weap_scenario + "_Water_Demand_Lvl1.csv")
    export_csv(WEAP, fname, favname)
    dfcovdmd = pd.read_csv(fname, skiprows=rowskip) 
    
    #------------------------------------
    # Potential crop production (for real and price series)
    #------------------------------------
    # TODO: Pull in actual crop production & use to construct a physically-based max utilization measure for ag
    favname = "WEAP Macro\Area"
    fname = os.path.join(fdirweapoutput, weap_scenario + "_Area.csv")
    export_csv(WEAP, fname, favname)
    dfcroparea = pd.read_csv(fname, skiprows=rowskip)
    dfcroparea = dfcroparea.replace(r'^\s*$', 0, regex=True) # fill in blanks with 0
    
    favname = "WEAP Macro\Potential Yield"
    fname = os.path.join(fdirweapoutput, weap_scenario + "_Potential_Yield.csv")
    export_csv(WEAP, fname, favname)
    dfcroppotyld = pd.read_csv(fname, skiprows=rowskip)
    dfcroppotyld = dfcroppotyld.replace(r'^\s*$', 0, regex=True) # fill in blanks with 0
    
    # The tables pull a lot of irrelevant branches -- the intersection is what we want
    common_branches = set(dfcroparea['Branch']).intersection(set(dfcroppotyld['Branch']))
    dfcroparea = dfcroparea[dfcroparea['Branch'].isin(common_branches)]
    dfcroparea = dfcroparea.set_index('Branch')
    dfcroppotyld = dfcroppotyld[dfcroppotyld['Branch'].isin(common_branches)]
    dfcroppotyld = dfcroppotyld.set_index('Branch')
    # Ensure that they are aligned
    dfcroppotyld.reindex_like(dfcroparea)
    # Compute total potential yield based on area
    dfcrop = dfcroparea * dfcroppotyld
    dfcrop.reset_index(inplace=True)

    #------------------------------------
    # Crop prices
    #------------------------------------
    fname = os.getcwd() + "\\Prices_v2.csv"
    dfcropprice = pd.read_csv(fname, skiprows=rowskip)
    dfcropprice.set_index(['country', 'crop', 'crop category'], inplace=True)  # sets first three columns as index 
        
    #------------------------------------
    # Investment
    #------------------------------------
    # TODO: Investment not currently implemented
    
    # RESERVOIR NAMES NOT BY COUNTRY; 
    # UNSURE IF NEW RESERVOIR; currently only historical scenario is active
    # OTHER SOURCES OF INVESTMENT: pipes/canals, boreholes, pumping stations, treatment plants
    
    # favname = "WEAP Macro\Reservoir Storage Capacity"
    # fname = "C:\\Users\\emily\\Documents\\GitHub\\WAVE\\WEAP Outputs\\Reservoir_Capacity_" + weap_scenario + ".csv"
    # export_csv(weap_scenario, fname, favname)
    
    return dfcov, dfcovdmd, dfcrop, dfcropprice

def weap_to_macro_processing(weap_scenario, leap_scenario, config_params, region, countries, fdirmacroinput, fdirweapoutput, dfcov, dfcovdmd, dfcrop, dfcropprice):
    """Process WEAP results and generate CSV files for Macro
    
    Input arguments:
        weap_scenario, leap_scenario: strings labeling the WEAP and LEAP scenarios to pull from and push to
        config_params: the configuration data structure for the integration program
        region: the LEAP region to prepare CSV files for
        countries: the WEAP countries that corresponds to the region
        fdirmacroinput: the input folder for LEAP-Macro (where the files are placed)
        fdirweapoutput: the folder for WEAP outputs as prepared by get_weap_ag_results()
        dfcov, dfcovdmd, dfcrop, dfcropprice: the Pandas dataframes returned by get_weap_ag_results()
    Returns: Nothing
    
    TODO: Specify list_separator
    """
    
    #------------------------------------
    # Process coverage data
    #------------------------------------
    coverage = pd.DataFrame()
    for sector in config_params['LEAP-Macro']['WEAP']['sectorlist']:    
        for subsector in config_params['LEAP-Macro']['Regions'][region]['weap_coverage_mapping'][sector]: # subsector data is the same across a given sector
            dfcovsec = dfcov[dfcov['Demand Site'].str.contains(sector)].copy() # removes strings not related to sector
            conditions = list(map(dfcovsec.loc[:,'Demand Site'].str.contains, countries)) # figure out which row is associated with which country
            dfcovsec.loc[:,'country'] = np.select(conditions, countries, 'other') # new column for countries
            cols = list(dfcovsec) # list of columns
            cols.insert(1, cols.pop(cols.index('country'))) # move the country column to specified index location
            dfcovsec = dfcovsec.loc[:,cols] # reorder columns in dataframe
            dfcovsec.set_index(['Demand Site', 'country'], inplace=True) # sets first two columns as index  
            dfcovsec.columns = dfcovsec.columns.str[4:] # removes month name
            dfcovsec = dfcovsec.groupby(level=0, axis=1).mean() # averages coverage for each year
            dfcovsec = dfcovsec/100 # indexes to 1
         
            dfcovdmdsec = dfcovdmd[dfcovdmd['Branch'].str.contains(sector)].copy() # removes strings not related to sector
            conditions = list(map(dfcovdmdsec.loc[:,'Branch'].str.contains, countries)) # figure out which row is associated with which country
            dfcovdmdsec.loc[:,'country'] = np.select(conditions, countries, 'other') # new column for countries
            cols = list(dfcovdmdsec) # list of columns
            cols.insert(1, cols.pop(cols.index('country'))) # move the country column to specified index location
            dfcovdmdsec = dfcovdmdsec.loc[:,cols] # reorder columns in dataframe
            dfcovdmdsec.set_index(['Branch', 'country'], inplace=True) # sets first two columns as index  
        
            wtcovtop = dfcovsec * dfcovdmdsec # weighted average calculation - numerator
            wtcovtop = wtcovtop.groupby('country').sum() # add up numerator for each country
            wtcovbot = dfcovdmdsec.groupby('country').sum() # weighted average calculation - denominator by country
            coveragetemp = wtcovtop.div(wtcovbot) # weighted average calculation
            coveragetemp = coveragetemp.drop('other', errors='ignore') # Drop 'other' if it is present
            coveragetemp = coveragetemp.rename(index={countries[0]: subsector})
            coverage = pd.concat([coverage, coveragetemp])
    fname = os.path.join(fdirmacroinput, leap_scenario + "_max_util.csv") # After conversion, this is max utilization
    coverage = coverage.transpose()**config_params['LEAP-Macro']['WEAP']['cov_to_util_exponent'] # If exponent = 0, max_util = 1.0; if = 1, then max_util = coverage
    coverage.index = coverage.index.astype('int64') # After transpose, the index is years
    # Have to add for 2019
    coverage.loc[2019] = coverage.loc[2020]
    coverage.sort_index(inplace=True)
    coverage.to_csv(fname, index=True, index_label = "year") # final output to csv
        

    #------------------------------------
    # Crop production
    #------------------------------------
    cropprod = pd.DataFrame()
    prodvalue = pd.DataFrame()
    realtemp2 = pd.DataFrame()
    real = pd.DataFrame()
    pricegrowthtemp2 = pd.DataFrame()
    pricegrowth = pd.DataFrame()
    for sector in config_params['LEAP-Macro']['WEAP']['sectorlist']:    
        try:
            for subsector in config_params['LEAP-Macro']['Regions'][region]['weap_crop_production_value_mapping'][sector]: # subsector data is the same across a given sector
                dfcropsec = dfcrop[dfcrop['Branch'].str.contains(sector)].copy() # removes strings not related to sector  
                conditions = list(map(dfcropsec.loc[:,'Branch'].str.contains, countries)) # figure out which row is associated with which country
                dfcropsec.loc[:,'country'] = np.select(conditions, countries, 'other') # new column for countries
                dfcropsec.loc[:,'crop']= dfcropsec.loc[:,'Branch'].str.rsplit('\\', n=1).str.get(1)
                dfcropsec.loc[:,'crop category'] = dfcropsec.loc[:,'crop'].map(config_params['LEAP-Macro']['Crop_categories']['WEAP_to_Macro'])
                cols = list(dfcropsec) # list of columns
                cols.insert(1, cols.pop(cols.index('country'))) # move the country column to specified index location
                cols.insert(2, cols.pop(cols.index('crop'))) # move the country column to specified index location
                cols.insert(3, cols.pop(cols.index('crop category'))) # move the country column to specified index location
                dfcropsec = dfcropsec.loc[:,cols] # reorder columns in dataframe
                dfcropsec.set_index(['Branch', 'country', 'crop', 'crop category'], inplace=True) # sets first two columns as index  
                dfcropsec = dfcropsec.apply(pd.to_numeric) # convert all columns to numeric
                # crop = dfcropsec.groupby(['country','crop category']).sum()
                croptemp = dfcropsec.groupby(['country']).sum()
                croptemp = croptemp.drop('other', errors='ignore') # Drop 'other' if it is present
                croptemp = croptemp.rename(index={countries[0]: subsector})
                cropprod = pd.concat([cropprod, croptemp])
        except:
            pass

        ## ensure number of columns in the prices matrix is same as the crop production matrix
        dfcrop_cols = dfcrop.columns # column names for dfcrop
        dfcropprice_cols = dfcropprice.columns # column names for dfcropprice
        diff_cols = dfcropprice_cols.difference(dfcrop_cols) # checks for differences between columns
        diff_cols = [x for x in diff_cols if x.isdigit()] # keeps if column header has digits (years)
        dfcropprice = dfcropprice.drop(columns = diff_cols) # drops columns not needed
        dfcropprice_cols = dfcropprice.columns # column names for dfcropprice
        dfcropprice_cols = [x for x in dfcropprice_cols if x.isdigit()] # keeps if column header has digits (years)
        diff_cols = dfcrop_cols.difference(dfcropprice_cols)
        diff_cols = [x for x in diff_cols if x.isdigit()]
        for x in diff_cols: 
            minyr = min(dfcropprice_cols)
            maxyr = max(dfcropprice_cols)
            medyr = round(len(dfcropprice_cols)/2)
            if x < minyr:
                dfcropprice[x] = dfcropprice[minyr]
            elif x > maxyr:
                dfcropprice[x] = dfcropprice[maxyr]
            else:
                dfcropprice[x] = dfcropprice[medyr]
        dfcropprice_cols = dfcropprice.columns # column names for dfcropprice
        dfcropprice_cols = [x for x in dfcropprice_cols if x.isdigit()] # keeps if column header has digits (years)
        dfcropprice_cols.sort() # sort column names
        dfcropprice = dfcropprice.loc[:,dfcropprice_cols] # sorted columns
        
        ## ensure number of rows in the prices matrix is same as the crop production matrix
        dfcropsecgrp = dfcropsec.groupby(['country','crop','crop category']).sum()
        dfcropsecgrp = dfcropsecgrp.reset_index()
        dfcropsecgrp['key'] = dfcropsecgrp['country']+dfcropsecgrp['crop'] # helper column
        dfcropprice = dfcropprice.reset_index()
        dfcropprice['key'] = dfcropprice['country']+dfcropprice['crop'] # helper column
        dfcropprice = dfcropprice[dfcropprice['key'].isin(dfcropsecgrp['key'])] # deletes rows that do not match
        dfcropsecgrp = dfcropsecgrp.sort_values('key')
        dfcropprice = dfcropprice.sort_values('key')
        dfcropsecgrp = dfcropsecgrp.drop(columns = 'key') # drops helper column       
        dfcropprice = dfcropprice.drop(columns = 'key') # drops helper column 
        dfcropsecgrp.set_index(['country', 'crop', 'crop category'], inplace=True) # sets first two columns as index  
        dfcropprice.set_index(['country', 'crop', 'crop category'], inplace=True) # sets first two columns as index  

        #------------------------------------
        # production value
        #------------------------------------
        try:
            for subsector in config_params['LEAP-Macro']['Regions'][region]['weap_crop_production_value_mapping'][sector]: # subsector data is the same across a given sector
                prodvaluetemp = dfcropsecgrp * dfcropprice
                prodvaluetemp = prodvaluetemp.groupby(['country']).sum()
                prodvaluetemp = prodvaluetemp.drop('other', errors='ignore') # Drop 'other' if it is present
                prodvaluetemp = prodvaluetemp.rename(index={countries[0]: subsector})
                prodvalue = pd.concat([prodvalue, prodvaluetemp])
        except:
            pass
     
        #------------------------------------
        # price inflation (change in crop price)
        #------------------------------------
        dfinflation = dfcropprice
        dfinflation = dfinflation.drop(columns = min(dfcropprice_cols))
        for x in dfcropprice_cols:
            if x < max(dfcropprice_cols):
                year1 = int(x)
                year2 = year1+1
            else:
                break
            dfinflation[str(year2)] = dfcropprice[str(year2)] - dfcropprice[str(year1)]
            dfinflation[str(year2)] = dfinflation[str(year2)].div(dfcropprice[str(year1)])
        
        #------------------------------------
        # change in production 
        #------------------------------------
        dfcrop_cols = [x for x in dfcrop_cols if x.isdigit()] # keeps if column header has digits (years)
        dfcropchange = dfcropsecgrp
        dfcropchange = dfcropchange.drop(columns = min(dfcrop_cols))
        for x in dfcrop_cols:
            if x < max(dfcrop_cols):
                year1 = int(x)
                year2 = year1+1
            else:
                break
            dfcropchange[str(year2)] = dfcropsecgrp[str(year2)] - dfcropsecgrp[str(year1)]
            dfcropchange[str(year2)] = dfcropchange[str(year2)].div(dfcropsecgrp[str(year1)])
        
        #------------------------------------
        # share of production
        #------------------------------------
        dfnum = dfcropsecgrp * dfcropprice
        dfdom = dfnum.groupby(['country']).sum()
        dfnum = dfnum.reset_index()
        dfdom = dfnum.merge(dfdom, left_on=['country'], right_on=['country'], how='right')
        dfdom = dfdom[dfdom.columns.drop(list(dfdom.filter(regex='x')))]
        dfdom.columns = dfdom.columns.str.replace('_y', '')
        dfnum.set_index(['country', 'crop', 'crop category'], inplace=True) # sets first two columns as index   
        dfdom.set_index(['country', 'crop', 'crop category'], inplace=True) # sets first two columns as index  
        dfshare = dfnum.div(dfdom)
        dfshare = dfshare.drop(columns = min(dfcrop_cols))
        
        #------------------------------------
        # real output growth
        #------------------------------------
        realtemp = dfshare * (1 + dfinflation) * dfcropchange   
        try:
            macrocrop = config_params['LEAP-Macro']['Regions'][region]['weap_real_output_index_mapping'][sector]
            macrocropno = len(macrocrop)        
            if macrocropno == 1:
                realtemp = realtemp.groupby(['country']).sum()
                for x in realtemp.index: 
                    if x == 'other': 
                        realtemp = realtemp.drop('other')
                for macrocrop in config_params['LEAP-Macro']['Regions'][region]['weap_real_output_index_mapping'][sector]['All crops']: 
                    realtemp = realtemp.rename(index={countries[0]: macrocrop})
                    realtemp2 = pd.concat([realtemp2, realtemp])
                realtemp2 = realtemp2.drop_duplicates()
            else:
                realtemp = realtemp.groupby(['country', 'crop category']).sum()
                for x, y in realtemp.index: 
                    if x == 'other': 
                        try: 
                            realtemp = realtemp.drop('other', axis=0)
                        except:
                            pass
                realtemp = realtemp.droplevel('country')
                for crop in config_params['LEAP-Macro']['WEAP']['croplist']:   
                    for macrocrop in config_params['LEAP-Macro']['Regions'][region]['weap_real_output_index_mapping'][sector][crop]: 
                        realtemp = realtemp.rename(index={crop: macrocrop})
                        realtemp2 = pd.concat([realtemp2, realtemp.loc[macrocrop]])
        except:
            pass
        
        # convert real output growth to indices
        for x in realtemp2:
            if x == min(realtemp2):
                real[x] = 1*(1+(realtemp2[x]))
                y = real[x]
            else:
                real[x] = y*(1+(realtemp2[x]))
                y = real[x]
                    
        #------------------------------------
        # price growth
        #------------------------------------
        pricegrowthtemp = dfinflation * dfshare
        try:
            macrocrop = config_params['LEAP-Macro']['Regions'][region]['weap_price_index_mapping'][sector]
            macrocropno = len(macrocrop)     
            if macrocropno == 1:             
                pricegrowthtemp = pricegrowthtemp.groupby(['country']).sum()
                for x in pricegrowthtemp.index: 
                    if x == 'other': 
                        pricegrowthtemp = pricegrowthtemp.drop('other') 
                for macrocrop in config_params['LEAP-Macro']['Regions'][region]['weap_price_index_mapping'][sector]['All crops']: 
                    pricegrowthtemp = pricegrowthtemp.rename(index={countries[0]: macrocrop})
                    # Because pricegrowthtemp2 starts empty, have to explicitly transpose the rows being added
                    pricegrowthtemp2 = pd.concat([pricegrowthtemp2, pricegrowthtemp.loc[macrocrop].to_frame().T])
                pricegrowthtemp2 = pricegrowthtemp2.drop_duplicates()
            else:
                pricegrowthtemp = pricegrowthtemp.groupby(['country', 'crop category']).sum()
                for x, y in pricegrowthtemp.index: 
                    if x == 'other': 
                        try: 
                            pricegrowthtemp = pricegrowthtemp.drop('other', axis=0)
                        except:
                            pass
                pricegrowthtemp = pricegrowthtemp.droplevel('country')
                for crop in config_params['LEAP-Macro']['WEAP']['croplist']:   
                    for macrocrop in config_params['LEAP-Macro']['Regions'][region]['weap_price_index_mapping'][sector][crop]: 
                        pricegrowthtemp = pricegrowthtemp.rename(index={crop: macrocrop})
                        # Because pricegrowthtemp2 starts empty, have to explicitly transpose the rows being added
                        pricegrowthtemp2 = pd.concat([pricegrowthtemp2, pricegrowthtemp.loc[macrocrop].to_frame().T])
        except:
            pass    

        # convert price growth to indices
        for x in pricegrowthtemp2:
            if x == min(pricegrowthtemp2):
                pricegrowth[x] = 1*(1+(pricegrowthtemp2[x]))
                y = pricegrowth[x]
            else:
                pricegrowth[x] = y*(1+(pricegrowthtemp2[x]))
                y = pricegrowth[x]
                
    #------------------------------------
    # Write out Macro input files
    #------------------------------------
    fname = os.path.join(fdirmacroinput, leap_scenario + "_realoutputindex.csv")
    real = real.transpose()
    real.index = real.index.astype('int64') # After transpose, the index is years
    # Must add some values to get to 2019
    real.loc[2020] = 1
    real.loc[2019] = 1/real.loc[2021]
    real.sort_index(inplace=True)
    real.to_csv(fname, index=True, index_label = "year") # final output to csv
    
    fname = os.path.join(fdirmacroinput, leap_scenario + "_priceindex.csv")
    pricegrowth = pricegrowth.transpose()
    pricegrowth.index = pricegrowth.index.astype('int64') # After transpose, the index is years
    pricegrowth.loc[2020] = 1
    pricegrowth.loc[2019] = 1/pricegrowth.loc[2021]
    pricegrowth.sort_index(inplace=True)
    pricegrowth.to_csv(fname, index=True, index_label = "year") # final output to csv
    
    # TODO: Investment parameters
