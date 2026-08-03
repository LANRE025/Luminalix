# New cases of malaria per 1,000 people at risk - Data package

This data package contains the data that powers the chart ["New cases of malaria per 1,000 people at risk"](https://ourworldindata.org/grapher/incidence-of-malaria?v=1&csvType=full&useColumnShortNames=false) on the Our World in Data website. It was downloaded on August 3, 2026.

### Active Filters

A filtered subset of the full data was downloaded. The following filters were applied:

## CSV Structure

The high level structure of the CSV file is that each row is an observation for an entity (usually a country or region) and a timepoint (usually a year).

The first two columns in the CSV file are "Entity" and "Code". "Entity" is the name of the entity (e.g. "United States"). "Code" is the OWID internal entity code that we use if the entity is a country or region. For most countries, this is the same as the [iso alpha-3](https://en.wikipedia.org/wiki/ISO_3166-1_alpha-3) code of the entity (e.g. "USA") - for non-standard countries like historical countries these are custom codes.

The third column is either "Year" or "Day". If the data is annual, this is "Year" and contains only the year as an integer. If the column is "Day", the column contains a date string in the form "YYYY-MM-DD".

The final column is the data column, which is the time series that powers the chart. If the CSV data is downloaded using the "full data" option, then the column corresponds to the time series below. If the CSV data is downloaded using the "only selected data visible in the chart" option then the data column is transformed depending on the chart type and thus the association with the time series might not be as straightforward.


## Metadata.json structure

The .metadata.json file contains metadata about the data package. The "charts" key contains information to recreate the chart, like the title, subtitle etc.. The "columns" key contains information about each of the columns in the csv, like the unit, timespan covered, citation for the data etc..

## About the data

Our World in Data is almost never the original producer of the data - almost all of the data we use has been compiled by others. If you want to re-use data, it is your responsibility to ensure that you adhere to the sources' license and to credit them correctly. Please note that a single time series may have more than one source - e.g. when we stich together data from different time periods by different producers or when we calculate per capita metrics using population data from a second source.

## Detailed information about the data


## Incidence of malaria (per 1,000 population at risk)
Last updated: July 27, 2026  
Next update: January 2027  
Date range: 2000–2024  
Unit: per 1,000 population at risk  


### How to cite this data

#### In-line citation
If you have limited space (e.g. in data visualizations), you can use this abbreviated in-line citation:  
World Health Organization (Global Health Observatory), via World Bank (2026) – processed by Our World in Data

#### Full citation
World Health Organization (Global Health Observatory), via World Bank (2026) – processed by Our World in Data. “Incidence of malaria (per 1,000 population at risk)” [dataset]. World Health Organization (Global Health Observatory), via World Bank, “World Development Indicators 129” [original data].
Source: World Health Organization (Global Health Observatory), via World Bank (2026) – processed by Our World In Data

### How is this data described by its producer - World Health Organization (Global Health Observatory), via World Bank (2026)?
Incidence of malaria is the number of new cases of malaria in a year per 1,000 population at risk.

### Aggregation method:
Weighted average

### Statistical concept and methodology:
Methodology: Confirmed malaria cases for countries and areas outside Africa, and for low-transmission countries and areas in Africa are adjusted for extent of health service use (treatment seeking), underreporting and lack of case confirmation (the likelihood that cases are parasite positive). In high transmission areas in which the quality of surveillance data does not permit a robust estimate from the number of reported cases, but good data on parasite prevalence is available, the number of cases can be estimated from parasite prevalence. The denominator is estimated, using official UN population and population at risk estimates for countries with sub-national endemicity.
Statistical concept(s): Complete data on malaria cases reported through surveillance systems are the best source of data but are rarely available for large populations at high quality and accuracy. Reported data on malaria cases generally need to be adjusted for extent of health service use (treatment seeking), underreporting and lack of case confirmation (the likelihood that cases are parasite positive). WHO compiles data on reported confirmed cases of malaria and suspected cases tested with microscopy or RDT, submitted by national malaria control programmes. Underreporting is reported or estimated by countries. The extent of health service use (treatment seeking) data were obtained from nationally representative household surveys on health service use.

### Development relevance:
Malaria is a life-threatening disease caused by parasites that are transmitted to people through the bites of infected female Anopheles mosquitoes. It is preventable and curable. There are 5 parasite species that cause malaria in humans, and 2 of these species – Plasmodium falciparum and Plasmodium vivax – pose the greatest threat.

### Other notes:
This is the Sustainable Development Goal indicator 3.3.3[https://unstats.un.org/sdgs/metadata/].

### Source

#### World Health Organization (Global Health Observatory), via World Bank – World Development Indicators
Retrieved on: 2026-07-27  
Retrieved from: https://data.worldbank.org/indicator/SH.MLR.INCD.P3  


    