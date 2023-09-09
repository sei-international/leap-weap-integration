# -*- coding: utf-8 -*-
"""
Created on Tue Sep 13 12:48:10 2022

@author: emily
"""

import logging
import numpy as np
import pandas as pd
import os
import sys # TODO: **DEBUGGING** Only for debugging
import win32com.client as win32 # TODO: **DEBUGGING** Only for debugging
import yaml # TODO: **DEBUGGING** Only for debugging
import gettext, locale, ctypes
# Allow a user to "short-circuit" the system language with an environment variable
if os.environ.get('LANG') is not None:
    language = os.environ['LANG']
elif os.environ.get('LANGUAGE') is not None:
    language = os.environ['LANGUAGE']
else:
    language = locale.windows_locale[ctypes.windll.kernel32.GetUserDefaultUILanguage()]
if gettext.find('wave_integration', localedir='locale', languages=[language]) is not None:
    transl = gettext.translation('wave_integration', localedir='locale', languages=[language])
    transl.install()
else:
    gettext.install('wave_integration')



# Load and calculate correct scenario
def load_weap_scen(WEAP, weap_scenario):
    WEAP.View = "Results"
    WEAP.ActiveScenario = weap_scenario

# Export WEAP files
def export_csv(WEAP, fname, favname):
    WEAP.LoadFavorite(favname)
    WEAP.ExportResults(fname)

# WEAP favorites to export
def get_weap_ag_results(fdirweapoutput, fdirmain, weap_scenario, WEAP, config_params, rowskip):
    """Export WEAP favorites so they can be converted to Macro inputs using weap_to_macro_processing()

    Input arguments:
        fdirweapoutput: the folder for WEAP outputs as prepared by get_weap_ag_results()
        fdirmain: the folder containing LEAP_Macro models
        weap_scenario, leap_scenario: strings labeling the WEAP and LEAP scenarios to pull from and push to
        WEAP: WEAP object
        rowskip: Number of rows to skip in WEAP favorites export files

    Returns: Pandas dataframes for weap_to_macro_processing():
        dfcov: Demand site coverage at detailed level
        dfwatdmd: Water demand used as weights to calculate average coverage
        dfcrop: Potential crop production using MABIA potential yields and crop areas
        dfcropprice: Crop prices

    TODO: Specify list_separator
    """

    load_weap_scen(WEAP, weap_scenario)

    #------------------------------------
    # Coverage (for utilization calculation)
    #------------------------------------
    # TODO: Put favnames in config file
    # Coverage
    favname = "WEAP Macro\Demand Site Coverage"
    fname = os.path.join(fdirweapoutput, weap_scenario + "_Coverage_Percent.csv")
    export_csv(WEAP, fname, favname)
    dfcov = pd.read_csv(fname, skiprows=rowskip)

    # Water demand in order to figure out coverage for each country
    favname = "WEAP Macro\Water Demand Annual Total - Level 1"
    fname = os.path.join(fdirweapoutput, weap_scenario + "_Water_Demand_Lvl1.csv")
    export_csv(WEAP, fname, favname)
    dfwatdmd = pd.read_csv(fname, skiprows=rowskip)

    #------------------------------------
    # Potential crop production (for realndx_incr and price series)
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
    fname = os.path.join(os.getcwd(), "data", config_params['LEAP-Macro']['WEAP']['price_data'])
    dfcropprice = pd.read_csv(fname, skiprows=rowskip)

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

    return dfcov, dfwatdmd, dfcrop, dfcropprice

def weap_to_macro_processing(weap_scenario, leap_scenario,
                             config_params, region, countries,
                             fdirmacroinput, fdirweapoutput,
                             dfcov, dfwatdmd, dfcrop, dfcropprice):
    """Process WEAP results and generate CSV files for Macro

    Input arguments:
        weap_scenario, leap_scenario: strings labeling the WEAP and LEAP scenarios to pull from and push to
        config_params: the configuration data structure for the integration program
        region: the LEAP region to prepare CSV files for
        countries: the WEAP countries that corresponds to the region
        fdirmacroinput: the input folder for LEAP-Macro (where the files are placed)
        fdirweapoutput: the folder for WEAP outputs as prepared by get_weap_ag_results()
        dfcov, dfwatdmd, dfcrop, dfcropprice: the Pandas dataframes returned by get_weap_ag_results()
    Returns: Nothing

    TODO: Specify list_separator
    """

    #------------------------------------
    # Process coverage data
    #------------------------------------
    coverage = pd.DataFrame()
    for weap_sectorname, weap_sectorentry in config_params['LEAP-Macro']['Regions'][region]['weap_coverage_mapping'].items():
        for macro_agsubsect in weap_sectorentry:
            #----------------------------------------------------------------
            # Get detailed WEAP coverage data
            #----------------------------------------------------------------
            # Remove any demand sites not related to this sector
            dfcovsec = dfcov[dfcov['Demand Site'].str.contains(weap_sectorname)].copy()
            # Extract every row for the WEAP countries in this LEAP region
            conditions = list(map(dfcovsec.loc[:,'Demand Site'].str.contains, countries))
            # Add a column to list the countries (default to 'other' if not in the list)
            dfcovsec.loc[:,'country'] = np.select(conditions, countries, 'other')
            
            # Move country column to index 1 and reorder dataframe
            cols = list(dfcovsec)
            cols.insert(1, cols.pop(cols.index('country')))
            dfcovsec = dfcovsec.loc[:,cols]
            
            # Index on Demand site x country
            dfcovsec.set_index(['Demand Site', 'country'], inplace=True)
            # Remove month name and get monthly average over the year
            dfcovsec.columns = dfcovsec.columns.str[4:]
            dfcovsec = dfcovsec.groupby(level=0, axis=1).mean()
            # Normalize
            dfcovsec = dfcovsec/100

            #----------------------------------------------------------------
            # Get WEAP water demand (to calculate weights in weighted average)
            #----------------------------------------------------------------
            # Remove any branches not related to this sector
            dfwatdmdsec = dfwatdmd[dfwatdmd['Branch'].str.contains(weap_sectorname)].copy()
            # Extract every row for the WEAP countries in this LEAP region
            conditions = list(map(dfwatdmdsec.loc[:,'Branch'].str.contains, countries))
            # Add a column to list the countries (default to 'other' if not in the list)
            dfwatdmdsec.loc[:,'country'] = np.select(conditions, countries, 'other')
            
            # Move country column to index 1 and reorder dataframe
            cols = list(dfwatdmdsec)
            cols.insert(1, cols.pop(cols.index('country')))
            dfwatdmdsec = dfwatdmdsec.loc[:,cols]
            
            # Index on Branch x country
            dfwatdmdsec.set_index(['Branch', 'country'], inplace=True)

            #----------------------------------------------------------------
            # Calculate coverage as a weighted average
            #----------------------------------------------------------------
            # Numerator, summed by country
            wtcovtop = dfcovsec * dfwatdmdsec
            wtcovtop = wtcovtop.groupby('country').sum()
            # Denominator
            wtcovbot = dfwatdmdsec.groupby('country').sum()
            # Calculate ratio (wtd average coverage)
            coveragetemp = wtcovtop.div(wtcovbot)
            # Drop 'other' region if present
            coveragetemp = coveragetemp.drop('other', errors='ignore')
            
            # Replace country label (no longer needed) with the current macro sector within the current weap sector
            coveragetemp = coveragetemp.rename(index={countries[0]: macro_agsubsect})
            # Add to the coverage dataframe
            coverage = pd.concat([coverage, coveragetemp])
    
    # Convert from coverage to maximum capacity utilization (if exponent = 0, max_util = 1.0; if = 1, then max_util = coverage)
    # TODO: For crops, should do actual output/potential
    coverage = coverage.transpose()**config_params['LEAP-Macro']['WEAP']['cov_to_util_exponent']
    # After transpose, the index is years, so convert to integer
    coverage.index = coverage.index.astype('int64')
    # Have to add entry for 2019: Assume it's the same as in 2020
    coverage.loc[2019] = coverage.loc[2020]
    coverage.sort_index(inplace=True)
    # Write to file
    fname = os.path.join(fdirmacroinput, leap_scenario + "_max_util.csv")
    coverage.to_csv(fname, index=True, index_label = "year") # final output to csv

    #------------------------------------
    # Crop production
    #------------------------------------
    pricegrowthtemp2 = pd.DataFrame()
    pricegrowth = pd.DataFrame()

    # Invert dict of crop categories to create the map
    weap_joint_crop_map = {}
    macro_joint_agsec_map = {}
    macro_joint_agprod_map = {}
    for category, entry in config_params['LEAP-Macro']['Regions'][region]['crop_categories'].items():
        for crop in entry['weap']:
            weap_joint_crop_map[crop] = category
        for agsector in entry['macro']['sector']:
            macro_joint_agsec_map[agsector] = category
        for agprod in entry['macro']['product']:
            macro_joint_agprod_map[agprod] = category

    # Add crop categories to dfcropprice
    dfcropprice.loc[:,'crop category'] = dfcropprice.loc[:,'crop'].map(weap_joint_crop_map)
    dfcropprice.set_index(['country', 'crop', 'crop category'], inplace=True)  # sets first three columns as index

    # Only include branches related to this sector
    dfcropsec = dfcrop[dfcrop['Branch'].str.contains(config_params['LEAP-Macro']['WEAP']['agsector'])].copy()
    # Extract every row for the WEAP countries in this LEAP region
    conditions = list(map(dfcropsec.loc[:,'Branch'].str.contains, countries))
    # Add a column to list the countries (default to 'other' if not in the list)
    dfcropsec.loc[:,'country'] = np.select(conditions, countries, 'other')
    
    # Identify crops from branch
    dfcropsec.loc[:,'crop']= dfcropsec.loc[:,'Branch'].str.rsplit('\\', n=1).str.get(1)
    # Map WEAP crops to crop categories
    dfcropsec.loc[:,'crop category'] = dfcropsec.loc[:,'crop'].map(weap_joint_crop_map)
    
    # Move country, crop, and crop category columns to indices 1, 2, and 3 and reorder dataframe
    cols = list(dfcropsec) # list of columns
    cols.insert(1, cols.pop(cols.index('country')))
    cols.insert(2, cols.pop(cols.index('crop')))
    cols.insert(3, cols.pop(cols.index('crop category')))
    dfcropsec = dfcropsec.loc[:,cols]
    
    # Index on Branch x country x crop x crop category
    dfcropsec.set_index(['Branch', 'country', 'crop', 'crop category'], inplace=True)
    # Convert columns to numeric, sum to country values, and drop 'other' if present
    dfcropsec = dfcropsec.apply(pd.to_numeric)
    
    # TODO: This is never used
    # # Create cropprod dataframe
    # cropprod = pd.DataFrame() # By Macro sector
    # croptemp = dfcropsec.groupby(['country']).sum()
    # croptemp = croptemp.drop('other', errors='ignore')
    # for joint_cropname, joint_cropentry in config_params['LEAP-Macro']['Regions'][region]['crop_categories'].items():
        # # Replace country label with a placeholder
        # croptemp = croptemp.rename(index={countries[0]: 'TEMP'})
        # for macro_agsubsect in joint_cropentry['macro']['sector']:
            # # Replace country label with the current macro sector within the current weap sector
            # croptemp = croptemp.rename(index={'TEMP': macro_agsubsect})
            # # Add to the cropprod dataframe
            # cropprod = pd.concat([cropprod, croptemp])
            # # Return to 'TEMP' so it can be reused
            # croptemp = croptemp.rename(index={macro_agsubsect: 'TEMP'})

    #----------------------------------------------------------------------------------------
    # Ensure number of columns & rows are the same in the prices and crop production matrices
    #----------------------------------------------------------------------------------------
    # ***** Columns
    # Find difference between the columns in dfcrop and dfcropprice
    diff_cols = dfcropprice.columns.difference(dfcrop.columns)
    # Limit to those containing years (giving True for isdigit) and drop from dfcropprice
    diff_cols = [x for x in diff_cols if x.isdigit()]
    dfcropprice = dfcropprice.drop(columns = diff_cols)
    # Fill in any missing years from dfcrop, assuming constant below and above the min/max year
    dfcropprice_cols = dfcropprice.columns
    dfcropprice_cols = [x for x in dfcropprice_cols if x.isdigit()]
    diff_cols = dfcrop.columns.difference(dfcropprice_cols)
    diff_cols = [x for x in diff_cols if x.isdigit()]
    # If there are years beyond the available time series, set equal to the value for the earliest/latest year
    minyr = min(dfcropprice_cols)
    maxyr = max(dfcropprice_cols)
    for x in diff_cols:
        if x < minyr:
            dfcropprice[x] = dfcropprice[minyr]
        elif x > maxyr:
            dfcropprice[x] = dfcropprice[maxyr] * 1.01**(int(x) - int(maxyr)) # TODO: **DEBUGGING** Return to zero realndx_incr price growth
        else:
            # Must include all years between the min & max, so any interpolation must be done offline
            msg = _('Must have a complete time series for crop prices: Missing value in year {a}, which is between the minimum and maximum years {b} and {c}').format(a = x, b = minyr, c = maxyr)
            logging.error(msg)
            sys.exit(msg)
    # Resort columns labeling years to ensure they are in order
    dfcropprice_cols = dfcropprice.columns
    dfcropprice_cols = [x for x in dfcropprice_cols if x.isdigit()]
    dfcropprice_cols.sort()
    dfcropprice = dfcropprice.loc[:,dfcropprice_cols]

    # ***** Rows
    # Sector crop production: Create a "helper column" called "key"
    dfcropsecgrp = dfcropsec.groupby(['country','crop','crop category']).sum()
    dfcropsecgrp = dfcropsecgrp.reset_index()
    dfcropsecgrp['key'] = dfcropsecgrp['country']+dfcropsecgrp['crop'] # helper column
    # Crop price: Create a "helper column" and called "key"
    dfcropprice = dfcropprice.reset_index()
    dfcropprice['key'] = dfcropprice['country']+dfcropprice['crop'] # helper column
    # Delete any rows that don't match
    dfcropprice = dfcropprice[dfcropprice['key'].isin(dfcropsecgrp['key'])]
    # Sort on the (identical) helper columns & then drop, since no longer needed
    dfcropsecgrp = dfcropsecgrp.sort_values('key')
    dfcropprice = dfcropprice.sort_values('key')
    dfcropsecgrp = dfcropsecgrp.drop(columns = 'key')
    dfcropprice = dfcropprice.drop(columns = 'key')
    # Reset index columns (country x crop x crop category)
    dfcropsecgrp.set_index(['country', 'crop', 'crop category'], inplace=True)
    dfcropprice.set_index(['country', 'crop', 'crop category'], inplace=True)
    dfcropsecgrp.drop(index='other', level='country', errors='ignore', inplace=True) # Drop 'other' if it is present

    print("---------------------- dfcropprice")
    print(dfcropprice)
    
    print("---------------------- dfcropsecgrp")
    print(dfcropsecgrp)
    
    # TODO: This isn't used
    #------------------------------------
    # calculate nominal production value as price x prod
    #------------------------------------
    # prodvalue = pd.DataFrame() # By joint crop category
    # # Start with value by crop
    # prodvalue_by_crop = dfcropsecgrp * dfcropprice
    # # prodvalue_by_crop = prodvalue_by_crop.groupby(['country']).sum()
    # prodvalue_by_crop = prodvalue_by_crop.drop('other', errors='ignore') # Drop 'other' if it is present
    # prodvalue_by_crop = prodvalue_by_crop.droplevel('country')
    # # Sum to get by joint category
    # prodvalue = prodvalue_by_crop.groupby(['crop category']).sum()


    # print("---------------------- prodvalue")
    # print(prodvalue)
    
    #------------------------------------
    # price inflation (change in crop price)
    #------------------------------------
    dfinflation = dfcropprice
    dfinflation = dfinflation.drop(columns = min(dfcropprice.columns))
    for x in dfcropprice.columns:
        if x < max(dfcropprice.columns):
            year1 = int(x)
            year2 = year1+1
        else:
            break
        dfinflation[str(year2)] = dfcropprice[str(year2)] - dfcropprice[str(year1)]
        dfinflation[str(year2)] = dfinflation[str(year2)].div(dfcropprice[str(year1)])

    print("---------------------- dfinflation")
    print(dfinflation)

    #------------------------------------
    # growth rate of production
    #------------------------------------
    dfcrop_cols = [x for x in dfcrop.columns if x.isdigit()] # keeps if column header has digits (years)
    dfcropprod_gr = dfcropsecgrp
    dfcropprod_gr = dfcropprod_gr.drop(columns = min(dfcrop_cols))
    for x in dfcrop_cols:
        if x < max(dfcrop_cols):
            year1 = int(x)
            year2 = year1+1
        else:
            break
        dfcropprod_gr[str(year2)] = dfcropsecgrp[str(year2)] - dfcropsecgrp[str(year1)]
        dfcropprod_gr[str(year2)] = dfcropprod_gr[str(year2)].div(dfcropsecgrp[str(year1)])

    print("---------------------- dfcropprod_gr")
    print(dfcropprod_gr)
    
    #------------------------------------
    # share of production by joint crop category
    #------------------------------------
    # Numerator
    dfnum = dfcropsecgrp * dfcropprice
    # Denominator
    dfdom = dfnum.groupby(['country', 'crop category']).sum()
    # Associate denominator with numerator by merging -- will assign "_x" and "_y" for the year columns in dfnum & dfdom
    dfnum = dfnum.reset_index()
    dfdom = dfnum.merge(dfdom, left_on=['country','crop category'], right_on=['country','crop category'], how='right')
    # Get rid of dfnum columns & get rid of "_y" so same denom for all country/crop combinations
    dfdom = dfdom[dfdom.columns.drop(list(dfdom.filter(regex='x')))]
    dfdom.columns = dfdom.columns.str.replace('_y', '')
    # Assign dfnum & dfdom identically structured indices
    dfnum.set_index(['country', 'crop', 'crop category'], inplace=True)
    dfdom.set_index(['country', 'crop', 'crop category'], inplace=True)
    # Divide numerator by denominator
    dfshare = dfnum.div(dfdom)
    # Drop first year because it's not present in the growth rate data frames
    dfshare = dfshare.drop(columns = min(dfcrop_cols))
        
    print("---------------------- dfshare")
    print(dfshare)

    # TODO: This is not needed
    # #------------------------------------
    # # realndx_incr output growth
    # #------------------------------------
    # # Note: This is exact for contribution to percent change in value; it doesn't drop second-order terms
    # realndx_cum = pd.DataFrame()
    # realndx_incr = pd.Series()
    # nomprod_gr = dfshare * (1 + dfinflation) * dfcropprod_gr
    # nomprod_gr = nomprod_gr.droplevel('country') # TODO: Can do this earlier -- never carry 'other'
    # nomprod_gr = nomprod_gr.groupby(['crop category']).sum()
    # # convert realndx_incr output growth to indices
    # for x in nomprod_gr:
        # if x == min(nomprod_gr):
            # realndx_incr[x] = 1*(1+(nomprod_gr[x]))
            # y = realndx_incr[x]
        # else:
            # realndx_incr[x] = y*(1+(nomprod_gr[x]))
            # y = realndx_incr[x]
    # realndx_cum = pd.concat([realndx_cum, nomprod_gr])
    
    # # crop_categories = joint_cropentry['macro']['sector']
    # # if len(crop_categories) == 1:
        # # nomprod_gr = nomprod_gr.groupby(['country']).sum()
        # # for x in nomprod_gr.index:
            # # if x == 'other':
                # # nomprod_gr = nomprod_gr.drop('other')
        # # for macrocrop in crop_categories['All crops']:
            # # nomprod_gr = nomprod_gr.rename(index={countries[0]: macrocrop})
            # # realndx_cum = pd.concat([realndx_cum, nomprod_gr])
        # # realndx_cum = realndx_cum.drop_duplicates()
    # # else:
        # # nomprod_gr = nomprod_gr.groupby(['country', 'crop category']).sum()
        # # for x, y in nomprod_gr.index:
            # # if x == 'other':
                # # try:
                    # # nomprod_gr = nomprod_gr.drop('other', axis=0)
                # # except:
                    # # pass
        # # nomprod_gr = nomprod_gr.droplevel('country')
        # # for crop in config_params['LEAP-Macro']['Regions'][region]['crop_categories']:
            # # for macrocrop in crop_categories[crop]:
                # # nomprod_gr = nomprod_gr.rename(index={crop: macrocrop})
                # # realndx_cum = pd.concat([realndx_cum, nomprod_gr.loc[macrocrop]])

    # # # convert realndx_incr output growth to indices
    # # for x in realndx_cum:
        # # if x == min(realndx_cum):
            # # realndx_incr[x] = 1*(1+(realndx_cum[x]))
            # # y = realndx_incr[x]
        # # else:
            # # realndx_incr[x] = y*(1+(realndx_cum[x]))
            # # y = realndx_incr[x]

    # print("----------------------------- realndx_cum")
    # print(realndx_cum)
    
    # for macro_agsubsect in joint_cropentry['macro']['sector']:
    #------------------------------------
    # price growth
    #------------------------------------
    pricegrowth_jointcrop = dfinflation * dfshare
    pricegrowth_jointcrop = pricegrowth_jointcrop.droplevel('country') # TODO: Can do this earlier -- never carry 'other'
    pricegrowth_jointcrop = pricegrowth_jointcrop.groupby(['crop category']).sum()
    
    # Create dataframe with no entries
    pricegrowth_macro_agprod = pd.DataFrame.from_dict(macro_joint_agprod_map, columns=['crop category'], orient='index')
    pricegrowth_macro_agprod.reset_index(inplace = True)
    pricegrowth_macro_agprod = pricegrowth_macro_agprod.rename(columns = {'index':'macro_agprod'})
    
    # Merge with pricegrowth_jointcrop to assign values, then drop crop categories column
    pricegrowth_macro_agprod = pricegrowth_macro_agprod.merge(pricegrowth_jointcrop,
                                                              left_on=['crop category'],
                                                              right_on=['crop category'],
                                                              how='right')
    pricegrowth_macro_agprod.drop('crop category', axis=1, inplace=True)
    pricegrowth_macro_agprod.set_index('macro_agprod', inplace=True)
    
    # Convert from growth rate to index
    pricendx_macro_agprod = (1.0 + pricegrowth_macro_agprod).cumprod(axis = 1)
    # Insert index = 1 in first year position
    pricendx_macro_agprod.insert(0, int(min(pricendx_macro_agprod)) - 1, 1.0)
    
    # macro_agprod_list = joint_cropentry['macro']['product']
    # pricegrowth_jointcrop = pricegrowth_jointcrop.groupby(['country', 'crop category']).sum()
    # for x, y in pricegrowth_jointcrop.index:
        # if x == 'other':
            # try:
                # pricegrowth_jointcrop = pricegrowth_jointcrop.drop('other', axis=0)
            # except:
                # pass
    # pricegrowth_jointcrop = pricegrowth_jointcrop.droplevel('country')
    # for macro_agprod in macro_agprod_list:
        # pricegrowth_jointcrop = pricegrowth_jointcrop.rename(index={crop: macro_agprod})
        # # Because pricegrowthtemp_cum starts empty, have to explicitly transpose the rows being added
        # pricegrowthtemp_cum = pd.concat([pricegrowthtemp_cum, pricegrowth_jointcrop.loc[macro_agprod].to_frame().T])
        # pricegrowth_jointcrop = pricegrowth_jointcrop.rename(index={macro_agprod: crop})

    print("----------------------------- pricegrowth_jointcrop")
    print(pricegrowth_jointcrop)
    print("----------------------------- pricegrowth_macro_agprod")
    print(pricendx_macro_agprod)
    
    # Create a value index by joint product
    valndx_joint = dfcropsecgrp.groupby('crop category').sum()
    valndx_joint = valndx_joint.div(valndx_joint[min(valndx_joint)], axis=0)
    
    # Assign to macro ag products
    # Create dataframe with no entries
    valndx_macro_agprod = pd.DataFrame.from_dict(macro_joint_agprod_map, columns=['crop category'], orient='index')
    valndx_macro_agprod.reset_index(inplace = True)
    valndx_macro_agprod = valndx_macro_agprod.rename(columns = {'index':'macro_agprod'})
    
    # Merge with valndx_joint to assign values, then drop crop categories column
    valndx_macro_agprod = valndx_macro_agprod.merge(valndx_joint,
                                                    left_on=['crop category'],
                                                    right_on=['crop category'],
                                                    how='right')
    valndx_macro_agprod.drop('crop category', axis=1, inplace=True)
    valndx_macro_agprod.set_index('macro_agprod', inplace=True)
    
    # Calculate real index by dividing value index by price index
    realndx_macro_agprod = valndx_macro_agprod/pricendx_macro_agprod.values
    
    print("----------------------------- pricendx_macro_agprod")
    print(pricendx_macro_agprod)
    print("----------------------------- valndx_joint")
    print(valndx_joint)
    print("----------------------------- valndx_macro_agprod")
    print(valndx_macro_agprod)
    print("----------------------------- realndx_macro_agprod")
    print(realndx_macro_agprod)

    #------------------------------------
    # Write out Macro input files
    #------------------------------------
    # Note: Must add some values to get to earlier years: go back to 2010 (only 2014 actually needed, for UZB)
    firstyear = int(min(realndx_macro_agprod))
    fname = os.path.join(fdirmacroinput, leap_scenario + "_realoutputindex.csv")
    realndx_macro_agprod = realndx_macro_agprod.transpose()
    realndx_macro_agprod.index = realndx_macro_agprod.index.astype('int64') # After transpose, the index is years
    val = 1
    factor = 1/realndx_macro_agprod.loc[firstyear+1]
    for y in range(firstyear,2009,-1):
        realndx_macro_agprod.loc[y] = val
        val *= factor
    realndx_macro_agprod.sort_index(inplace=True)
    realndx_macro_agprod.to_csv(fname, index=True, index_label = "year") # final output to csv

    fname = os.path.join(fdirmacroinput, leap_scenario + "_priceindex.csv")
    pricendx_macro_agprod = pricendx_macro_agprod.transpose()
    pricendx_macro_agprod.index = pricendx_macro_agprod.index.astype('int64') # After transpose, the index is years
    val = 1
    factor = 1/pricendx_macro_agprod.loc[firstyear+1]
    for y in range(firstyear,2009,-1):
        pricendx_macro_agprod.loc[y] = val
        val *= factor
    pricendx_macro_agprod.sort_index(inplace=True)
    pricendx_macro_agprod.to_csv(fname, index=True, index_label = "year") # final output to csv

    # TODO: Investment parameters

# TODO: **DEBUGGING**
weap = win32.Dispatch('WEAP.WEAPApplication')
with open(r'config.yml') as file:
    config_params = yaml.full_load(file)

macromodelspath = os.path.normpath(os.path.join(weap.ActiveArea.Directory, "..\\..", config_params['LEAP-Macro']['Folder']))

fdirmain = macromodelspath
fdirweapoutput = os.path.join(fdirmain, "WEAP outputs")

leap_scenario = 'S1 Baseline Historical'
weap_scenario = 'S1 Historical'
CSV_ROW_SKIP = 3 # number of rows to skip in weap csv outputs

# export weap data
dfcov, dfcovdmd, dfcrop, dfcropprice = get_weap_ag_results(fdirweapoutput, fdirmain, weap_scenario, weap, config_params, CSV_ROW_SKIP)

logging.info(_('Processing for WEAP scenario: {s}').format(s = weap_scenario))
for r, rinfo in config_params['LEAP-Macro']['Regions'].items():  
    # set file directories for WEAP to LEAP-Macro
    fdirmacroinput = os.path.join(macromodelspath, rinfo['directory_name'], "inputs")
        
    # process WEAP data for LEAP-Macro
    weap_to_macro_processing(weap_scenario, leap_scenario, config_params, r, rinfo['weap_region'], fdirmacroinput, fdirweapoutput, dfcov, dfcovdmd, dfcrop, dfcropprice)
