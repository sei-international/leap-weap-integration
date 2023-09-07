# -*- coding: utf-8 -*-
"""
Created on Tue Sep 13 12:48:10 2022

@author: emily
"""

import logging
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
    fname = os.path.join(os.getcwd(), "data", config_params['LEAP-Macro']['WEAP']['price_data'])
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
    for weap_sectorname, sectorentry in config_params['LEAP-Macro']['Regions'][region]['weap_coverage_mapping'].items():
        for macrosector in sectorentry:
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
            coveragetemp = coveragetemp.rename(index={countries[0]: macrosector})
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
    cropprod = pd.DataFrame()
    prodvalue = pd.DataFrame()
    realtemp2 = pd.DataFrame()
    real = pd.DataFrame()
    pricegrowthtemp2 = pd.DataFrame()
    pricegrowth = pd.DataFrame()

    # Invert dict of crop categories to create the map
    crop_categories = {}
    for category, crops in config_params['LEAP-Macro']['Regions'][region]['crop_categories'].items():
        for crop in crops:
            crop_categories[crop] = category

    for weap_sectorname, sectorentry in config_params['LEAP-Macro']['Regions'][region]['weap_crop_production_mapping'].items():
        for macrosector in sectorentry['value']:
            # Remove any branches not related to this sector
            dfcropsec = dfcrop[dfcrop['Branch'].str.contains(weap_sectorname)].copy()
            # Extract every row for the WEAP countries in this LEAP region
            conditions = list(map(dfcropsec.loc[:,'Branch'].str.contains, countries))
            # Add a column to list the countries (default to 'other' if not in the list)
            dfcropsec.loc[:,'country'] = np.select(conditions, countries, 'other')
            
            # Identify crops from branch
            dfcropsec.loc[:,'crop']= dfcropsec.loc[:,'Branch'].str.rsplit('\\', n=1).str.get(1)
            # Map WEAP crops to crop categories
            dfcropsec.loc[:,'crop category'] = dfcropsec.loc[:,'crop'].map(crop_categories)
            
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
            croptemp = dfcropsec.groupby(['country']).sum()
            croptemp = croptemp.drop('other', errors='ignore')
            
            # Replace country label (no longer needed) with the current macro sector within the current weap sector
            croptemp = croptemp.rename(index={countries[0]: macrosector})
            # Add to the cropprod dataframe
            cropprod = pd.concat([cropprod, croptemp])

        #----------------------------------------------------------------------------------------
        # Ensure number of columns in the prices matrix is same as the crop production matrix
        #----------------------------------------------------------------------------------------
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
                dfcropprice[x] = dfcropprice[maxyr]
            else:
                # Must include all years between the min & max, so any interpolation must be done offline
                msg = _('Must have a complete time series for crop prices: Missing value in year {a}, which is between the minimum and maximum years {b} and {c}').format(a = x, b = minyr, c = maxyr)
                logging.error(msg)
                sys.exit(msg)
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
        for macrosector in sectorentry['value']: # subsector data is the same across a given sector
            prodvaluetemp = dfcropsecgrp * dfcropprice
            prodvaluetemp = prodvaluetemp.groupby(['country']).sum()
            prodvaluetemp = prodvaluetemp.drop('other', errors='ignore') # Drop 'other' if it is present
            prodvaluetemp = prodvaluetemp.rename(index={countries[0]: macrosector})
            prodvalue = pd.concat([prodvalue, prodvaluetemp])

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
        dfcrop_cols = [x for x in dfcrop.columns if x.isdigit()] # keeps if column header has digits (years)
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
            crop_categories = sectorentry['real_index']
            if len(crop_categories) == 1:
                realtemp = realtemp.groupby(['country']).sum()
                for x in realtemp.index:
                    if x == 'other':
                        realtemp = realtemp.drop('other')
                for macrocrop in crop_categories['All crops']:
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
                for crop in config_params['LEAP-Macro']['Regions'][region]['crop_categories']:
                    for macrocrop in crop_categories[crop]:
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
            macrocrop = config_params['LEAP-Macro']['Regions'][region]['weap_price_index_mapping'][weap_sectorname]
            macrocropno = len(macrocrop)
            if macrocropno == 1:
                pricegrowthtemp = pricegrowthtemp.groupby(['country']).sum()
                for x in pricegrowthtemp.index:
                    if x == 'other':
                        pricegrowthtemp = pricegrowthtemp.drop('other')
                for macrocrop in config_params['LEAP-Macro']['Regions'][region]['weap_price_index_mapping'][weap_sectorname]['All crops']:
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
                for crop in config_params['LEAP-Macro']['Regions'][region]['crop_categories']:
                    for macrocrop in config_params['LEAP-Macro']['Regions'][region]['weap_price_index_mapping'][weap_sectorname][crop]:
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
    # Note: Must add some values to get to earlier years: go back to 2010 (only 2014 actually needed, for UZB)
    fname = os.path.join(fdirmacroinput, leap_scenario + "_realoutputindex.csv")
    real = real.transpose()
    real.index = real.index.astype('int64') # After transpose, the index is years
    val = 1
    factor = 1/real.loc[2021]
    for y in range(2020,2009,-1):
        real.loc[y] = val
        val *= factor
    real.sort_index(inplace=True)
    real.to_csv(fname, index=True, index_label = "year") # final output to csv

    fname = os.path.join(fdirmacroinput, leap_scenario + "_priceindex.csv")
    pricegrowth = pricegrowth.transpose()
    pricegrowth.index = pricegrowth.index.astype('int64') # After transpose, the index is years
    val = 1
    factor = 1/pricegrowth.loc[2021]
    for y in range(2020,2009,-1):
        pricegrowth.loc[y] = val
        val *= factor
    pricegrowth.sort_index(inplace=True)
    pricegrowth.to_csv(fname, index=True, index_label = "year") # final output to csv

    # TODO: Investment parameters
