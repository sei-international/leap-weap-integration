# -*- coding: utf-8 -*-
"""
Created on Tue Sep 13 12:48:10 2022

@author: emily
"""

import numpy as np
import pandas as pd
import os

#Load and calculate correct scenario
def loadweapscen(WEAP, scenario):
    WEAP.View = "Results"
    WEAP.ActiveScenario = scenario
    
#Export WEAP files    
def exportcsv(WEAP, fname, favname):
    WEAP.LoadFavorite(favname)
    WEAP.ExportResults(fname)

#WEAP favorites to export
def exportcsvmodule(fdirweapoutput, fdirmain, scenario, WEAP, rowskip):
    
    loadweapscen(WEAP, scenario)
    
    #Coverage
    favname = "WEAP Macro\Demand Site Coverage"
    fname = os.path.join(fdirweapoutput, scenario + "_Coverage_Percent.csv")
    exportcsv(WEAP, fname, favname) 
    dfcov = pd.read_csv(fname, skiprows=rowskip) 
    
    #Water demand in order to figure out coverage for each country
    favname = "WEAP Macro\Water Demand Annual Total - Level 1"
    fname = os.path.join(fdirweapoutput, scenario + "_Water_Demand_Lvl1.csv")
    exportcsv(WEAP, fname, favname)
    dfcovdmd = pd.read_csv(fname, skiprows=rowskip) 
    
    #Crop production
    favname = "WEAP Macro\Annual Crop Production"
    fname = os.path.join(fdirweapoutput, scenario + "_Annual_Crop_Production.csv")
    exportcsv(WEAP, fname, favname)
    dfcrop = pd.read_csv(fname, skiprows=rowskip)
    dfcrop = dfcrop.replace(r'^\s*$', 0, regex=True) #fill in blanks with 0
    
    #Water demand in order to figure out crop production for each country
    #favname = "WEAP Macro\Water Demand Annual Total - Level 2"
    #fname = "C:\\Users\\emily\\Documents\\GitHub\\WAVE\\WEAP Outputs\\Water_Demand_Lvl2_" + scenario + ".csv"
    #exportcsv(scenario, fname, favname)
    #dfcropdmd = pd.read_csv(fname, skiprows=rowskip) 
    
    #Crop list categorization
    #fname = fdirmain + "\\Crop_Categorization.csv"
    #dfcropcat = pd.read_csv(fname, usecols=['WEAP Category','Macro Category']) #reads in list for specific columns
    #dfcropcat = dfcropcat.drop_duplicates() #removes duplicate rows
    #dfcropcat.set_index(['WEAP Category'], inplace=True) #sets first two columns as index  
    #cropcat = dfcropcat.to_dict()
    
    #Crop prices
    fname = os.getcwd() + "\\Prices_v2.csv"
    dfcropprice = pd.read_csv(fname, skiprows=rowskip)
    dfcropprice.set_index(['country', 'crop', 'crop category'], inplace=True)  #sets first three columns as index 
        
    #Investment
    #favname = "WEAP Macro\Reservoir Storage Capacity"
    #fname = "C:\\Users\\emily\\Documents\\GitHub\\WAVE\\WEAP Outputs\\Reservoir_Capacity_" + scenario + ".csv"
    #exportcsv(scenario, fname, favname)
    
    return dfcov, dfcovdmd, dfcrop, dfcropprice

#WEAP RESULTS PROCESSING 
def weaptomacroprocessing(weap, scenario, config_params, region, countries, fdirmain, fdirmacroinput, fdirweapoutput, dfcov, dfcovdmd, dfcrop, dfcropprice):

    #Process coverage data
    coverage = pd.DataFrame()
    for sector in config_params['LEAP-Macro']['WEAP']['sectorlist']:    
        for subsector in config_params['LEAP-Macro']['regions'][region]['weap_coverage_mapping'][sector]: #subsector data is the same across a given sector
            dfcovsec = dfcov[dfcov['Demand Site'].str.contains(sector)] #removes strings not related to sector
            conditions = list(map(dfcovsec['Demand Site'].str.contains, countries)) #figure out which row is associated with which country
            dfcovsec['country'] = np.select(conditions, countries, 'other') #new column for countries
            cols = list(dfcovsec) #list of columns
            cols.insert(1, cols.pop(cols.index('country'))) #move the country column to specified index location
            dfcovsec = dfcovsec.loc[:,cols] #reorder columns in dataframe
            dfcovsec.set_index(['Demand Site', 'country'], inplace=True) #sets first two columns as index  
            dfcovsec.columns = dfcovsec.columns.str[4:] #removes month name
            dfcovsec = dfcovsec.groupby(level=0, axis=1).mean() #averages coverage for each year
            dfcovsec = dfcovsec/100 #indexes to 1
         
            dfcovdmdsec = dfcovdmd[dfcovdmd['Branch'].str.contains(sector)] #removes strings not related to sector
            conditions = list(map(dfcovdmdsec['Branch'].str.contains, countries)) #figure out which row is associated with which country
            dfcovdmdsec['country'] = np.select(conditions, countries, 'other') #new column for countries
            cols = list(dfcovdmdsec) #list of columns
            cols.insert(1, cols.pop(cols.index('country'))) #move the country column to specified index location
            dfcovdmdsec = dfcovdmdsec.loc[:,cols] #reorder columns in dataframe
            dfcovdmdsec.set_index(['Branch', 'country'], inplace=True) #sets first two columns as index  
        
            wtcovtop = dfcovsec * dfcovdmdsec #weighted average calculation - numerator
            wtcovtop = wtcovtop.groupby('country').sum() #add up numerator for each country
            wtcovbot = dfcovdmdsec.groupby('country').sum() #weighted average calculation - denominator by country
            coveragetemp = wtcovtop.div(wtcovbot) #weighted average calculation
            for x in coveragetemp.index: 
                if x == 'other': 
                    coveragetemp = coveragetemp.drop('other') 
            coveragetemp = coveragetemp.rename(index={countries[0]: subsector})
            coverage = coverage.append(coveragetemp)
    fname = os.path.join(fdirmacroinput, scenario + "_coverage.csv")
    coverage = coverage.transpose()
    coverage.to_csv(fname, index=True, index_label = "year") #final output to csv
        

    #Crop production
    cropprod = pd.DataFrame()
    prodvalue = pd.DataFrame()
    realtemp2 = pd.DataFrame()
    real = pd.DataFrame()
    pricegrowthtemp2 = pd.DataFrame()
    pricegrowth = pd.DataFrame()
    for sector in config_params['LEAP-Macro']['WEAP']['sectorlist']:    
        try:
            for subsector in config_params['LEAP-Macro']['regions'][region]['weap_crop_production_value_mapping'][sector]: #subsector data is the same across a given sector
                dfcropsec = dfcrop[dfcrop['Branch'].str.contains(sector)] #removes strings not related to sector  
                conditions = list(map(dfcropsec['Branch'].str.contains, countries)) #figure out which row is associated with which country
                dfcropsec['country'] = np.select(conditions, countries, 'other') #new column for countries
                dfcropsec['crop']= dfcropsec['Branch'].str.rsplit('\\', n=1).str.get(1)
                dfcropsec['crop category'] = dfcropsec['crop'].map(config_params['LEAP-Macro']['crop_categories']['WEAP_to_Macro'])
                cols = list(dfcropsec) #list of columns
                cols.insert(1, cols.pop(cols.index('country'))) #move the country column to specified index location
                cols.insert(2, cols.pop(cols.index('crop'))) #move the country column to specified index location
                cols.insert(3, cols.pop(cols.index('crop category'))) #move the country column to specified index location
                dfcropsec = dfcropsec.loc[:,cols] #reorder columns in dataframe
                dfcropsec.set_index(['Branch', 'country', 'crop', 'crop category'], inplace=True) #sets first two columns as index  
                dfcropsec = dfcropsec.apply(pd.to_numeric) #convert all columns to numeric
                #crop = dfcropsec.groupby(['country','crop category']).sum()
                croptemp = dfcropsec.groupby(['country']).sum()
                for x in croptemp.index: 
                    if x == 'other': 
                        croptemp = croptemp.drop('other') 
                croptemp = croptemp.rename(index={countries[0]: subsector})
                cropprod = cropprod.append(croptemp)
        except:
            pass

        ## makes sure number of columns in the prices matrix is same as the crop production matrix
        dfcrop_cols = dfcrop.columns #column names for dfcrop
        dfcropprice_cols = dfcropprice.columns #column names for dfcropprice
        diff_cols = dfcropprice_cols.difference(dfcrop_cols) #checks for differences between columns
        diff_cols = [x for x in diff_cols if x.isdigit()] #keeps if column header has digits (years)
        dfcropprice = dfcropprice.drop(columns = diff_cols) #drops columns not needed
        dfcropprice_cols = dfcropprice.columns #column names for dfcropprice
        dfcropprice_cols = [x for x in dfcropprice_cols if x.isdigit()] #keeps if column header has digits (years)
        diff_cols = dfcrop_cols.difference(dfcropprice_cols)
        diff_cols = [x for x in diff_cols if x.isdigit()]
    #       diff_cols = ['1994', '2021'] # test code
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
        dfcropprice_cols = dfcropprice.columns #column names for dfcropprice
        dfcropprice_cols = [x for x in dfcropprice_cols if x.isdigit()] #keeps if column header has digits (years)
        dfcropprice_cols.sort() # sort column names
        dfcropprice = dfcropprice.loc[:,dfcropprice_cols] #sorted columns
        
        ## makes sure number of rows in the prices matrix is same as the crop production matrix
        dfcropsecgrp = dfcropsec.groupby(['country','crop','crop category']).sum()
    #       dfcrop_rows = dfcrop.rows #column names for dfcrop
        dfcropsecgrp = dfcropsecgrp.reset_index()
        dfcropsecgrp['key'] = dfcropsecgrp['country']+dfcropsecgrp['crop'] #helper column
        dfcropprice = dfcropprice.reset_index()
        dfcropprice['key'] = dfcropprice['country']+dfcropprice['crop'] #helper column
        dfcropprice = dfcropprice[dfcropprice['key'].isin(dfcropsecgrp['key'])] #deletes rows that do not match
        dfcropsecgrp = dfcropsecgrp.sort_values('key')
        dfcropprice = dfcropprice.sort_values('key')
        dfcropsecgrp = dfcropsecgrp.drop(columns = 'key') #drops helper column       
        dfcropprice = dfcropprice.drop(columns = 'key') #drops helper column 
        dfcropsecgrp.set_index(['country', 'crop', 'crop category'], inplace=True) #sets first two columns as index  
        dfcropprice.set_index(['country', 'crop', 'crop category'], inplace=True) #sets first two columns as index  

        ## production value
        try:
            for subsector in config_params['LEAP-Macro']['regions'][region]['weap_crop_production_value_mapping'][sector]: #subsector data is the same across a given sector
                prodvaluetemp = dfcropsecgrp * dfcropprice
            #    prodvaluetemp = prodvaluetemp.groupby(['country', 'crop category']).sum()
                prodvaluetemp = prodvaluetemp.groupby(['country']).sum()
                for x in prodvaluetemp.index: 
                    if x == 'other': 
                        prodvaluetemp = prodvaluetemp.drop('other') 
                prodvaluetemp = prodvaluetemp.rename(index={countries[0]: subsector})
                prodvalue = prodvalue.append(prodvaluetemp)
        except:
            pass
     
        ## price inflation (change in crop price)
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
        
        ## change in production 
        dfcrop_cols = [x for x in dfcrop_cols if x.isdigit()] #keeps if column header has digits (years)
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
        
    #       dfcropsecgrp = dfcropsecgrp.reset_index()
       
        ##share of production
        dfnum = dfcropsecgrp * dfcropprice
        dfdom = dfnum.groupby(['country']).sum()
        dfnum = dfnum.reset_index()
        dfdom = dfnum.merge(dfdom, left_on=['country'], right_on=['country'], how='right')
        dfdom = dfdom[dfdom.columns.drop(list(dfdom.filter(regex='x')))]
        dfdom.columns = dfdom.columns.str.replace('_y', '')
        dfnum.set_index(['country', 'crop', 'crop category'], inplace=True) #sets first two columns as index   
        dfdom.set_index(['country', 'crop', 'crop category'], inplace=True) #sets first two columns as index  
        dfshare = dfnum.div(dfdom)
        dfshare = dfshare.drop(columns = min(dfcrop_cols))
        
        
        ##real output growth
        realtemp = dfshare * (1 + dfinflation) * dfcropchange   
        try:
            macrocrop = config_params['LEAP-Macro']['regions'][region]['weap_real_output_index_mapping'][sector]
            macrocropno = len(macrocrop)        
            if macrocropno == 1:
                realtemp = realtemp.groupby(['country']).sum()
                for x in realtemp.index: 
                    if x == 'other': 
                        realtemp = realtemp.drop('other')
                for macrocrop in config_params['LEAP-Macro']['regions'][region]['weap_real_output_index_mapping'][sector]['All crops']: 
                    realtemp = realtemp.rename(index={countries[0]: macrocrop})
                    realtemp2 = realtemp2.append(realtemp)
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
                    for macrocrop in config_params['LEAP-Macro']['regions'][region]['weap_real_output_index_mapping'][sector][crop]: 
                        realtemp = realtemp.rename(index={crop: macrocrop})
                        realtemp2 = realtemp2.append(realtemp.loc[macrocrop])
        except:
            pass
        
        
        ## convert real output growth to indices
        for x in realtemp2:
            if x == min(realtemp2):
                real[x] = 1*(1+(realtemp2[x]))
                y = real[x]
            else:
                real[x] = y*(1+(realtemp2[x]))
                y = real[x]
                    
        ##price growth
        pricegrowthtemp = dfinflation * dfshare
        try:
            macrocrop = config_params['LEAP-Macro']['regions'][region]['weap_price_index_mapping'][sector]
            macrocropno = len(macrocrop)     
            if macrocropno == 1:             
                pricegrowthtemp = pricegrowthtemp.groupby(['country']).sum()
                for x in pricegrowthtemp.index: 
                    if x == 'other': 
                        pricegrowthtemp = pricegrowthtemp.drop('other') 
                for macrocrop in config_params['LEAP-Macro']['regions'][region]['weap_price_index_mapping'][sector]['All crops']: 
                    pricegrowthtemp = pricegrowthtemp.rename(index={countries[0]: macrocrop})
                    pricegrowthtemp2 = pricegrowthtemp2.append(pricegrowthtemp.loc[macrocrop])
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
                    for macrocrop in config_params['LEAP-Macro']['regions'][region]['weap_price_index_mapping'][sector][crop]: 
                        pricegrowthtemp = pricegrowthtemp.rename(index={crop: macrocrop})
                        pricegrowthtemp2 = pricegrowthtemp2.append(pricegrowthtemp.loc[macrocrop])
        except:
            pass    

        ## convert price growth to indices
        for x in pricegrowthtemp2:
            if x == min(pricegrowthtemp2):
                pricegrowth[x] = 1*(1+(pricegrowthtemp2[x]))
                y = pricegrowth[x]
            else:
                pricegrowth[x] = y*(1+(pricegrowthtemp2[x]))
                y = pricegrowth[x]
                    
                
    fname = os.path.join(fdirmacroinput, scenario + "_crop_production.csv")
    cropprod = cropprod.transpose()
    cropprod.to_csv(fname, index=True, index_label = "year") #final output to csv

    fname = os.path.join(fdirmacroinput, scenario + "_productionvalue.csv")
    prodvalue = prodvalue.transpose()
    prodvalue.to_csv(fname, index=True, index_label = "year") #final output to csv
    
    fname = os.path.join(fdirmacroinput, scenario + "_realoutputindex.csv")
    real = real.transpose()
    real.to_csv(fname, index=True, index_label = "year") #final output to csv
    
    fname = os.path.join(fdirmacroinput, scenario + "_priceindex.csv")
    pricegrowth = pricegrowth.transpose()
    pricegrowth.to_csv(fname, index=True, index_label = "year") #final output to csv
    
    #Investment parameters
    #RESERVOIR NAMES NOT BY COUNTRY; 
    #UNSURE IF NEW RESERVOIR; currently only historical scenario is active
    #OTHER SOURCES OF INVESTMENT: pipes/canals, boreholes, pumping stations, treatment plants
    
