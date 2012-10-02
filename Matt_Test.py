#! /usr/bin/env python
__author__ = 'mhouse01'

import requests
import re
from datetime import datetime
from lxml import etree
from sys import exit
from operator import attrgetter
from Matt_PW import importUsername, importPassword

# Declare the XNAT Namespace for use in XML parsing
xnatNS = "{http://nrg.wustl.edu/xnat}"

class seriesDetails:
    """A simple class to store information about a scan series"""
    def __init__(self):
        self.seriesNum = None
        self.seriesQualityText = None
        self.seriesQualityNumeric = None
        self.seriesDesc = None
        self.niftiCount = None
        self.seriesDate = None
        self.instanceNum = None
        self.instanceName = None
        self.instanceIncluded = None
    def __repr__(self):
        return "<seriesDetails seriesNum:%s seriesQualityText:%s seriesQualityNumeric:%s seriesDesc:%s niftiCount:%s seriesDate:%s>" \
               % (self.seriesNum, self.seriesQualityText, self.seriesQualityNumeric, self.seriesDesc, self.niftiCount, self.seriesDate)

def QualityTextToNumeric(QualityText):
    """Convert 'quality' string to numeric score"""
    qualityDict = dict(unknown=-1, unusable=0, poor=1, fair=2, good=3, excellent=4, usable=5)
    QualityNumeric = qualityDict.get( QualityText, -1)
    return int( QualityNumeric )

# TODO Declaring REST Request Parameters manually here for now
project = "HCP_Phase2"
subject = "792564"
experiment = "792564_fnca"
username = importUsername
password = importPassword

restRoot = "https://intradb.humanconnectome.org"
restExperimentURL = restRoot + "/data/archive/projects/" + project + "/subjects/" + subject + "/experiments/" + experiment

# Establish a Session ID
r = requests.get( restRoot + "/data/JSESSION", auth=(username, password) )
# Check if the REST Request fails
if r.status_code != 200 :
    print "Failed to retrieve REST Session ID"
    exit(1)
restSessionID = r.content
print "Rest Session ID: %s " % (restSessionID)
restSessionHeader = {"Cookie": "JSESSIONID=" + restSessionID}

# Make a rest request to get the complete XNAT Session XML
r = requests.get( restExperimentURL + "?format=xml", headers=restSessionHeader )
# Check if the REST Request fails
if r.status_code != 200 :
    print "Failed to retrieve XML"
    exit(1)

# Parse the XML result into an Element Tree
root = etree.fromstring(r.text.encode(r.encoding))
# Extract the Study Date for the session
studyDate = root.find(".//" + xnatNS + "date").text
print "Assuming study date of " + studyDate

# Start with an empty series list
seriesList = list()

# Iterate over 'scan' records that contain an 'ID' element
for element in root.iterfind(".//" + xnatNS + "scan[@ID]"):
    # Create an empty seriesDetails record
    currentSeries = seriesDetails()
    # Record the Series Number
    currentSeries.seriesNum = int( element.get("ID") )
    # Record the Series Description
    currentSeries.seriesDesc = element.find(".//" + xnatNS + "series_description").text
    # Record the Scan Quality
    currentSeries.seriesQualityText = element.find(".//" + xnatNS + "quality").text
    # Record the Convert the Scan Quality to a numeric value
    currentSeries.seriesQualityNumeric = QualityTextToNumeric(currentSeries.seriesQualityText)
    # Find the file record under the current element associated with NIFTI files
    niftiElement = element.find(".//" + xnatNS + "file[@label='NIFTI']")
    # Record the number of NIFTI files from the file record
    currentSeries.niftiCount = int( niftiElement.get("file_count") )
    # Extract the scan Start Time from the current Series record
    startTime=element.find(".//" + xnatNS + "startTime").text
    # Record the series Date and Time in
    currentSeries.seriesDate = datetime.strptime(studyDate + " " + startTime, "%Y-%m-%d %H:%M:%S")
    # Add the current series to the end of the list
    seriesList.append(currentSeries)

# Sort by primary then secondary key (utilizes sorting stability)
seriesList.sort( key=attrgetter('seriesDesc', 'seriesDate') )

# Make sure that the list is not empty
if len(seriesList) > 0:
    # The first one is always unique
    seriesList[0].instanceNum = 1
    seriesList[0].instanceName = seriesList[0].seriesDesc
# Make sure that the list has additional elements
if len(seriesList) > 1:
    # Start with the second item in the list
    for i in range( 1, len(seriesList) ):
        previousSeries = seriesList[i-1]
        currentSeries = seriesList[i]
        # Look for duplicate Series Descriptions, remembering that we have a sorted list
        if previousSeries.seriesDesc != currentSeries.seriesDesc:
            # This is unique because it's not the same as the previous one
            currentSeries.instanceNum = 1
            currentSeries.instanceName = currentSeries.seriesDesc
        else:
            # This is not unique.  Increment it's instance number
            currentSeries.instanceNum = previousSeries.instanceNum + 1
            # And derive it's instance name
            currentSeries.instanceName = currentSeries.seriesDesc + "_" + str( currentSeries.instanceNum )
            # If this is the second instance, then go back and label the first one
            if currentSeries.instanceNum == 2:
                previousSeries.instanceName = previousSeries.seriesDesc + "_" + str( previousSeries.instanceNum )

# Re-sort by Series Number
seriesList.sort( key=attrgetter('seriesNum') )

# Number Single Special Cases
specialCases = ["FieldMap_Magnitude", "FieldMap_Phase", "BOLD_RL_SB_SE", "BOLD_LR_SB_SE"]
# We're going to store the instance names for later use
instanceNames = list()
# Iterate over the list of Series objects
for item in seriesList:
    # If the current Instance Name matches one of our special cases
    if specialCases.count(item.instanceName) > 0:
        # Append the instance name with "_1"
        item.instanceName += "_1"
    # Add the modified instance name to the general list
    instanceNames.append(item.instanceName)

# Sanity Check. Verify that all Instance Names are unique
# Compare the number of Series to the number of unique Instance Names
if len(seriesList) == len( set(instanceNames) ):
    print "Instance names verified as unique"
else:
    print "Instance names not unique."
    exit(1)

# Create the Final filtered list
# Remove specified scan types from list
excludeList = ["Localizer", "AAHScout"]
searchRegex = re.compile( '|'.join(excludeList) )


# Iterate over the list of Series objects
for item in seriesList:
    # if the Instance Name does not match anything from the exclude list...
    if not re.match( searchRegex, item.instanceName ):
        # And if the Scan Quality value is greater than 3
        if item.seriesQualityNumeric > 3:
            # Include this item in the final list
            item.instanceIncluded = True
        else:
            item.instanceIncluded = False
    else:
        item.instanceIncluded = False

# Print the final filtered list
for item in seriesList:
    #print item.seriesNum, item.seriesDesc, item.seriesQualityText, item.seriesQualityNumeric, item.niftiCount, item.seriesDate
    #print "Series %s, %s, Instance %s, Instance Name: %s, %s, %s" % (item.seriesNum, item.seriesDesc, item.instanceNum, item.instanceName, item.seriesQualityText, item.seriesDate.ctime() )
    print "Series %s, Instance Name: %s, Instance Included: %s" % (item.seriesNum, item.instanceName, item.instanceIncluded )

