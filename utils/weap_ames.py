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
    """Export WEAP favorites so they can be converted to AMES inputs using weap_to_ames_processing()

    Input arguments:
        fdirweapoutput: the folder for WEAP outputs as prepared by get_weap_ag_results()
        fdirmain: the folder containing AMES models
        weap_scenario, leap_scenario: strings labeling the WEAP and LEAP scenarios to pull from and push to
        WEAP: WEAP object
        rowskip: Number of rows to skip in WEAP favorites export files

    Returns: Pandas dataframes for weap_to_ames_processing():
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
    dfcov.replace(r'^\s*$', 0.0, regex=True) # fill in blanks with 0

    # Water demand in order to figure out coverage for each country
    favname = "WEAP Macro\Water Demand Annual Total - Level 1"
    fname = os.path.join(fdirweapoutput, weap_scenario + "_Water_Demand_Lvl1.csv")
    export_csv(WEAP, fname, favname)
    dfwatdmd = pd.read_csv(fname, skiprows=rowskip)
    dfwatdmd.replace(r'^\s*$', 0.0, regex=True) # fill in blanks with 0

    #------------------------------------
    # Potential crop production (for realndx_incr and price series)
    #------------------------------------
    # TODO: Pull in actual crop production & use to construct a physically-based max utilization measure for ag
    favname = "WEAP Macro\Area"
    fname = os.path.join(fdirweapoutput, weap_scenario + "_Area.csv")
    export_csv(WEAP, fname, favname)
    dfcroparea = pd.read_csv(fname, skiprows=rowskip)
    dfcroparea = dfcroparea.replace(r'^\s*$', 0.0, regex=True) # fill in blanks with 0

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
    fname = os.path.join(os.getcwd(), "data", config_params['AMES']['WEAP']['price_data'])
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

def weap_to_ames_processing(weap_scenario, leap_scenario,
                             config_params, region, countries,
                             fdiramesinput, fdirweapoutput,
                             dfcov, dfwatdmd, dfcrop, dfcropprice):
    """Process WEAP results and generate CSV files for AMES

    Input arguments:
        weap_scenario, leap_scenario: strings labeling the WEAP and LEAP scenarios to pull from and push to
        config_params: the configuration data structure for the integration program
        region: the LEAP region to prepare CSV files for
        countries: the WEAP countries that corresponds to the region
        fdiramesinput: the input folder for AMES (where the files are placed)
        fdirweapoutput: the folder for WEAP outputs as prepared by get_weap_ag_results()
        dfcov, dfwatdmd, dfcrop, dfcropprice: the Pandas dataframes returned by get_weap_ag_results()
    Returns: Nothing

    TODO: Specify list_separator
    """

    dfcov_local = dfcov.copy()
    dfwatdmd_local = dfwatdmd.copy()
    dfcrop_local = dfcrop.copy()
    dfcropprice_local = dfcropprice.copy()
    #------------------------------------
    # Process coverage data
    #------------------------------------
    coverage = pd.DataFrame()
    for weap_sectorname, weap_sectorentry in config_params['AMES']['Regions'][region]['weap_coverage_mapping'].items():
        for ames_agsubsect in weap_sectorentry:
            #----------------------------------------------------------------
            # Get detailed WEAP coverage data
            #----------------------------------------------------------------
            # Remove any demand sites not related to this sector
            dfcovsec = dfcov_local[dfcov_local['Demand Site'].str.contains(weap_sectorname)].copy()
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
            dfcovsec = (dfcovsec.T.groupby(level=0).mean()).T
            # Normalize
            dfcovsec = dfcovsec/100

            #----------------------------------------------------------------
            # Get WEAP water demand (to calculate weights in weighted average)
            #----------------------------------------------------------------
            # Remove any branches not related to this sector
            dfwatdmdsec = dfwatdmd_local[dfwatdmd_local['Branch'].str.contains(weap_sectorname)].copy()
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
            
            # Replace country label (no longer needed) with the current AMES sector within the current weap sector
            coveragetemp = coveragetemp.rename(index={countries[0]: ames_agsubsect})
            # Add to the coverage dataframe
            coverage = pd.concat([coverage, coveragetemp])
    
    # Convert from coverage to maximum capacity utilization (if exponent = 0, max_util = 1.0; if = 1, then max_util = coverage)
    # TODO: For crops, should do actual output/potential
    coverage = coverage.T**config_params['AMES']['WEAP']['cov_to_util_exponent']
    # After transpose, the index is years, so convert to integer
    coverage.index = coverage.index.astype('int64')
    # Have to add entry for 2019: Assume it's the same as in 2020
    coverage.loc[2019] = coverage.loc[2020]
    coverage.sort_index(inplace=True)
    # Write to file
    fname = os.path.join(fdiramesinput, leap_scenario + "_max_util.csv")
    coverage.to_csv(fname, index=True, index_label = "year") # final output to csv

    #------------------------------------
    # Crop production
    #------------------------------------
    # Invert dict of crop categories to create the map
    weap_joint_crop_map = {}
    ames_joint_agsec_map = {}
    ames_joint_agprod_map = {}
    for category, entry in config_params['AMES']['Regions'][region]['crop_categories'].items():
        for crop in entry['weap']:
            weap_joint_crop_map[crop] = category
        for agsector in entry['ames']['sector']:
            ames_joint_agsec_map[agsector] = category
        for agprod in entry['ames']['product']:
            ames_joint_agprod_map[agprod] = category

    # Add crop categories to dfcropprice_local
    dfcropprice_local.loc[:,'crop category'] = dfcropprice_local.loc[:,'crop'].map(weap_joint_crop_map)
    dfcropprice_local.set_index(['country', 'crop', 'crop category'], inplace=True)  # sets first three columns as index

    # Only include branches related to this sector
    dfcropsec = dfcrop_local[dfcrop_local['Branch'].str.contains(config_params['AMES']['WEAP']['agsector'])].copy()
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
    
    #----------------------------------------------------------------------------------------
    # Ensure number of columns & rows are the same in the prices and crop production matrices
    #----------------------------------------------------------------------------------------
    # ***** Columns
    # Find difference between the columns in dfcrop_local and dfcropprice_local
    diff_cols = dfcropprice_local.columns.difference(dfcrop_local.columns)
    # Limit to those containing years (giving True for isdigit) and drop from dfcropprice_local
    diff_cols = [x for x in diff_cols if x.isdigit()]
    dfcropprice_local = dfcropprice_local.drop(columns = diff_cols)
    # Fill in any missing years from dfcrop_local, assuming constant below and above the min/max year
    dfcropprice_cols = dfcropprice_local.columns
    dfcropprice_cols = [x for x in dfcropprice_cols if x.isdigit()]
    diff_cols = dfcrop_local.columns.difference(dfcropprice_cols)
    diff_cols = [x for x in diff_cols if x.isdigit()]
    # If there are years beyond the available time series, set equal to the value for the earliest/latest year
    minyr = min(dfcropprice_cols)
    maxyr = max(dfcropprice_cols)
    for x in diff_cols:
        if x < minyr:
            dfcropprice_local[x] = dfcropprice_local[minyr]
        elif x > maxyr:
            dfcropprice_local[x] = dfcropprice_local[maxyr]
        else:
            # Must include all years between the min & max, so any interpolation must be done offline
            msg = _('Must have a complete time series for crop prices: Missing value in year {a}, which is between the minimum and maximum years {b} and {c}').format(a = x, b = minyr, c = maxyr)
            logging.error(msg)
            sys.exit(msg)
    # Resort columns labeling years to ensure they are in order
    dfcropprice_cols = dfcropprice_local.columns
    dfcropprice_cols = [x for x in dfcropprice_cols if x.isdigit()]
    dfcropprice_cols.sort()
    dfcropprice_local = dfcropprice_local.loc[:,dfcropprice_cols]

    # ***** Rows
    # Sector crop production: Create a "helper column" called "key"
    dfcropsecgrp = dfcropsec.groupby(['country','crop','crop category']).sum()
    dfcropsecgrp = dfcropsecgrp.reset_index()
    dfcropsecgrp['key'] = dfcropsecgrp['country']+dfcropsecgrp['crop'] # helper column
    # Crop price: Create a "helper column" and called "key"
    dfcropprice_local = dfcropprice_local.reset_index()
    dfcropprice_local['key'] = dfcropprice_local['country']+dfcropprice_local['crop'] # helper column
    # Delete any rows that don't match
    dfcropprice_local = dfcropprice_local[dfcropprice_local['key'].isin(dfcropsecgrp['key'])]
    # Sort on the (identical) helper columns & then drop, since no longer needed
    dfcropsecgrp = dfcropsecgrp.sort_values('key')
    dfcropprice_local = dfcropprice_local.sort_values('key')
    dfcropsecgrp = dfcropsecgrp.drop(columns = 'key')
    dfcropprice_local = dfcropprice_local.drop(columns = 'key')
    # Reset index columns (country x crop x crop category)
    dfcropsecgrp.set_index(['country', 'crop', 'crop category'], inplace=True)
    dfcropprice_local.set_index(['country', 'crop', 'crop category'], inplace=True)
    dfcropsecgrp.drop(index='other', level='country', errors='ignore', inplace=True) # Drop 'other' if it is present

    #------------------------------------
    # price inflation (growth rate of crop price)
    #------------------------------------
    dfinflation = dfcropprice_local.drop(columns = min(dfcropprice_local.columns))
    dfinflation_lag = dfcropprice_local.drop(columns = max(dfcropprice_local.columns))
    dfinflation = dfinflation/dfinflation_lag.values - 1.0
 
    #------------------------------------
    # share of production by joint crop category
    #------------------------------------
    # Numerator
    dfnum = dfcropsecgrp * dfcropprice_local
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
    dfcrop_cols = [x for x in dfcrop_local.columns if x.isdigit()] # keeps if column header has digits (years)
    dfshare = dfshare.drop(columns = min(dfcrop_cols))

    #------------------------------------
    # price growth indices (by sector & by product)
    #------------------------------------
    pricegrowth_jointcrop = dfinflation * dfshare
    pricegrowth_jointcrop = pricegrowth_jointcrop.droplevel('country')
    pricegrowth_jointcrop = pricegrowth_jointcrop.groupby(['crop category']).sum()
    
    #--- By AMES ag sector
    # Create dataframe with no entries
    pricegrowth_ames_agsec = pd.DataFrame.from_dict(ames_joint_agsec_map, columns=['crop category'], orient='index')
    pricegrowth_ames_agsec.reset_index(inplace = True)
    pricegrowth_ames_agsec = pricegrowth_ames_agsec.rename(columns = {'index':'ames_agsec'})
    
    # Merge with pricegrowth_jointcrop to assign values, then drop crop categories column
    pricegrowth_ames_agsec = pricegrowth_ames_agsec.merge(pricegrowth_jointcrop,
                                                              left_on=['crop category'],
                                                              right_on=['crop category'],
                                                              how='left')
    pricegrowth_ames_agsec.drop('crop category', axis=1, inplace=True)
    pricegrowth_ames_agsec.set_index('ames_agsec', inplace=True)
    
    # Convert from growth rate to index
    pricendx_ames_agsec = (1.0 + pricegrowth_ames_agsec).cumprod(axis = 1)
    # Insert index = 1 in first year position
    pricendx_ames_agsec.insert(0, int(min(pricendx_ames_agsec)) - 1, 1.0)
    
    #--- By AMES ag product
    # Create dataframe with no entries
    pricegrowth_ames_agprod = pd.DataFrame.from_dict(ames_joint_agprod_map, columns=['crop category'], orient='index')
    pricegrowth_ames_agprod.reset_index(inplace = True)
    pricegrowth_ames_agprod = pricegrowth_ames_agprod.rename(columns = {'index':'ames_agprod'})
    
    # Merge with pricegrowth_jointcrop to assign values, then drop crop categories column
    pricegrowth_ames_agprod = pricegrowth_ames_agprod.merge(pricegrowth_jointcrop,
                                                              left_on=['crop category'],
                                                              right_on=['crop category'],
                                                              how='left')
    pricegrowth_ames_agprod.drop('crop category', axis=1, inplace=True)
    pricegrowth_ames_agprod.set_index('ames_agprod', inplace=True)
    
    # Convert from growth rate to index
    pricendx_ames_agprod = (1.0 + pricegrowth_ames_agprod).cumprod(axis = 1)
    # Insert index = 1 in first year position
    pricendx_ames_agprod.insert(0, int(min(pricendx_ames_agprod)) - 1, 1.0)

    #------------------------------------
    # nominal output index
    #------------------------------------
    # Create a value index by joint product
    valndx_joint = dfcropsecgrp.groupby('crop category').sum()
    valndx_joint = valndx_joint.div(valndx_joint[min(valndx_joint)], axis=0)
    
    # Assign to AMES ag products
    # Create dataframe with no entries
    valndx_ames_agsec = pd.DataFrame.from_dict(ames_joint_agsec_map, columns=['crop category'], orient='index')
    valndx_ames_agsec.reset_index(inplace = True)
    valndx_ames_agsec = valndx_ames_agsec.rename(columns = {'index':'ames_agsec'})
    
    # Merge with valndx_joint to assign values, then drop crop categories column
    valndx_ames_agsec = valndx_ames_agsec.merge(valndx_joint,
                                                    left_on=['crop category'],
                                                    right_on=['crop category'],
                                                    how='left')
    valndx_ames_agsec.drop('crop category', axis=1, inplace=True)
    valndx_ames_agsec.set_index('ames_agsec', inplace=True)
    
    # Calculate real index by dividing value index by price index
    realndx_ames_agsec = valndx_ames_agsec/pricendx_ames_agsec.values
    
    #------------------------------------
    # Write out AMES input files
    #------------------------------------
    # Note: Must add some values to get to earlier years: go back to 2010 (only 2014 actually needed, for UZB)
    firstyear = int(min(realndx_ames_agsec))
    fname = os.path.join(fdiramesinput, leap_scenario + "_realoutputindex.csv")
    realndx_ames_agsec = realndx_ames_agsec.T
    realndx_ames_agsec.index = realndx_ames_agsec.index.astype('int64') # After transpose, the index is years
    val = 1
    factor = 1/realndx_ames_agsec.loc[firstyear+1]
    for y in range(firstyear,2009,-1):
        realndx_ames_agsec.loc[y] = val
        val *= factor
    realndx_ames_agsec.sort_index(inplace=True)
    realndx_ames_agsec.to_csv(fname, index=True, index_label = "year") # final output to csv

    fname = os.path.join(fdiramesinput, leap_scenario + "_priceindex.csv")
    pricendx_ames_agprod = pricendx_ames_agprod.T
    pricendx_ames_agprod.index = pricendx_ames_agprod.index.astype('int64') # After transpose, the index is years
    val = 1
    factor = 1/pricendx_ames_agprod.loc[firstyear+1]
    for y in range(firstyear,2009,-1):
        pricendx_ames_agprod.loc[y] = val
        val *= factor
    pricendx_ames_agprod.sort_index(inplace=True)
    pricendx_ames_agprod.to_csv(fname, index=True, index_label = "year") # final output to csv

    # TODO: Investment parameters
