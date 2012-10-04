#! /usr/bin/env python
__author__ = 'mhouse01'

import requests
import re
import urllib2
import json
import shutil
import os
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
        self.isUnique = None
        self.instanceNum = None
        self.instanceName = None
        self.instanceIncluded = None
        self.fileList = None
    def __repr__(self):
        return "<seriesDetails seriesNum:%s seriesQualityText:%s seriesQualityNumeric:%s seriesDesc:%s niftiCount:%s seriesDate:%s>" \
               % (self.seriesNum, self.seriesQualityText, self.seriesQualityNumeric, self.seriesDesc, self.niftiCount, self.seriesDate)

def QualityTextToNumeric(QualityText):
    """Convert 'quality' string to numeric score"""
    qualityDict = dict(unusable=0, poor=1, fair=2, good=3, excellent=4, usable=5, undetermined=6)
    QualityNumeric = qualityDict.get( QualityText, -1)
    return int( QualityNumeric )

# TODO Declaring REST Request Parameters manually here for now
project = "HCP_Phase2"
subject = "792564"
experiment = "792564_diff"
username = importUsername
password = importPassword

destDir = os.path.normpath( "/Users/mhouse01/NIFTI_temp" )

jsonFormat ={'format': 'json'}
restServerName = "intradb.humanconnectome.org"
restInsecureRoot = "http://" + restServerName + ":8080"
restSecureRoot = "https://" + restServerName
restSelectedRoot = restSecureRoot
restExperimentURL = restSelectedRoot + "/data/archive/projects/" + project + "/subjects/" + subject + "/experiments/" + experiment

# Establish a Session ID
r = requests.get( restSecureRoot + "/data/JSESSION", auth=(username, password) )
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
    seriesList[0].isUnique = True
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
            #currentSeries.instanceName = currentSeries.seriesDesc
            currentSeries.isUnique = True
        else:
            # This is not unique
            currentSeries.isUnique = False
            # Neither is the previous one
            previousSeries.isUnique = False
            # Increment the current instance number
            currentSeries.instanceNum = previousSeries.instanceNum + 1

# Re-sort by Series Number
seriesList.sort( key=attrgetter('seriesNum') )

# Tag Single Special Cases as not being unique
specialCases = ["FieldMap_Magnitude", "FieldMap_Phase", "BOLD_RL_SB_SE", "BOLD_LR_SB_SE"]
# Iterate over the list of Series objects
for item in seriesList:
    # If the current Series Description matches one of our special cases
    if item.seriesDesc in specialCases:
        # Tag it as not unique
        item.isUnique = False

# Set the Instance Names
for item in seriesList:
    # For unique instances...
    if item.isUnique:
        # Just use the Series Description
        item.instanceName = item.seriesDesc
    # For non-unique instances...
    else:
        # Append the Series Description with the Instance Number
        item.instanceName = item.seriesDesc + "_" + str(item.instanceNum)

# Sanity Check. Verify that all Instance Names are unique
instanceNames = [item.instanceName for item in seriesList]
# Compare the number of Series to the number of unique Instance Names
if len(seriesList) == len( set(instanceNames) ):
    print "Instance names verified as unique"
else:
    print "Instance names not unique."
    exit(1)

# Create the filtered list; Exclude specified scan types from the list
excludeList = ["Localizer", "AAHScout"]
# Create a regular expression search object
searchRegex = re.compile( '|'.join(excludeList) )

# Iterate over the list of Series objects
for item in seriesList:
    # if the scan quality is a 3 or greater and if the Instance Name does not match anything from the exclude list
    if item.seriesQualityNumeric >= 3 and not re.search( searchRegex, item.instanceName ):
        # Include the item in the final list
        item.instanceIncluded = True
    else:
        # Exclude this item from the final list
        item.instanceIncluded = False

# Create a tuple of the included resource types
IncludedTypes = ('.nii.gz', '.bvec', '.bval')
# Get the actual list of file names and URLs for each series
for item in seriesList:
    # If the Series is included, get it's file list
    if item.instanceIncluded:
        # Create a URL pointing to the NIFTI resources for the series
        niftiURL = restExperimentURL + "/scans/" + str( item.seriesNum) + "/resources/NIFTI/files"
        # Get the list of NIFTI resources for the series in JSON format
        r = requests.get( niftiURL, params=jsonFormat, headers=restSessionHeader)
        # Parse the JSON from the GET
        seriesJSON = json.loads( r.content )
        # Strip off the trash that comes back with it and store it as a list of name/value pairs
        fileResults = seriesJSON.get('ResultSet').get('Result')
        # List Comprehensions Rock!  http://docs.python.org/tutorial/datastructures.html
        # Filter the File List to only include items where the URI ends with one of the defined file types
        fileResultsFiltered = [ fileItem for fileItem in fileResults
                                if fileItem.get('URI').endswith( IncludedTypes )]
        # Let us know what was found and how many matched
        print "Series %s, %s file(s) found; %s file(s) matching criteria" %\
              ( item.seriesNum, len( fileResults ), len( fileResultsFiltered ) )
        # Create a stripped down version of the results with a new field for FileName; Store it in the Series object
        item.fileList = [ dict( zip( ('OriginalName', 'FileName', 'URI', 'Size'),
            (result.get('Name'), None, result.get('URI'), long( result.get('Size') ) ) ) )
                          for result in fileResultsFiltered ]
        # Iterate across the individual files entries
        for fileItem in item.fileList:
            # Substitute the Instance Name in for the Series Description in File Names
            fileItem['FileName'] = re.sub(item.seriesDesc, item.instanceName, fileItem.get('OriginalName'))
            print fileItem['FileName'], fileItem['URI']

# Make sure that the destination folder exists
if not os.path.exists( destDir ):
    os.makedirs(destDir)
# Make a session specific folder
sessionFolder = destDir + os.sep + experiment
if not os.path.exists( sessionFolder ):
    os.makedirs( sessionFolder )

# Download the final filtered list
for item in seriesList:
    print "Series %s, Instance Name: %s, Included: %s" % (item.seriesNum, item.instanceName, item.instanceIncluded )
    if item.instanceIncluded:
        for fileItem in item.fileList:
            # Get the current NIFTI resource in the series.
            niftiURL = restSelectedRoot + fileItem.get('URI')
            # Create a Request object associated with the URL
            niftiRequest = urllib2.Request( niftiURL )
            # Add the Session Header to the Request
            niftiRequest.add_header( "Cookie", restSessionHeader.get("Cookie") )
            # Generate a fully qualified local filename to dump the data into
            local_filename = destDir + os.sep + experiment + os.sep + fileItem.get('FileName')
            print "Downloading %s..." % fileItem.get('FileName')
            # Try to write the remote file to disk
            try:
                # Open a socket to the URL and get a file-like object handle
                remote_fo = urllib2.urlopen( niftiRequest )
                # Write the URL contents out to a file and make sure it gets closed
                with open( local_filename, 'wb') as local_fo:
                    shutil.copyfileobj( remote_fo, local_fo )
            # If we fail to open the remote object, error out
            except urllib2.URLError, e:
                print e.args
                exit(1)
            #print "File Size: %s " %  os.path.getsize(local_filename)
            local_filesize = os.path.getsize(local_filename)
            print "Local File Size: %0.1f MB;" % (local_filesize/(1024*1024.0)),
            if fileItem.get('Size') == local_filesize:
                print "Matches remote"
            else:
                print "Does not match remote!"

# Pathing to find stuff in XNAT
# For lists, can append: ?format=json
# jsonFormat ={'format': 'json'}
# Projects:
#   https://intradb.humanconnectome.org/data/archive/projects
# Subjects:
#   https://intradb.humanconnectome.org/data/archive/projects/HCP_Phase2/subjects
# MR Sessions:
#   https://intradb.humanconnectome.org/data/archive/projects/HCP_Phase2/subjects/792564/experiments/?xsiType=xnat:mrSessionData
# Scans:
#   https://intradb.humanconnectome.org/data/archive/projects/HCP_Phase2/subjects/792564/experiments/792564_fnca/scans
# Scan XML:
#   https://intradb.humanconnectome.org/data/archive/projects/HCP_Phase2/subjects/792564/experiments/792564_fnca/scans/1
# Resources:
#   https://intradb.humanconnectome.org/data/archive/projects/HCP_Phase2/subjects/792564/experiments/792564_fnca/scans/1/resources
# Resource XML:
#   https://intradb.humanconnectome.org/data/archive/projects/HCP_Phase2/subjects/792564/experiments/792564_fnca/scans/1/resources/NIFTI
# Resource File List:
#   https://intradb.humanconnectome.org/data/archive/projects/HCP_Phase2/subjects/792564/experiments/792564_fnca/scans/1/resources/NIFTI/files
#
# URL Request Parameters
# payload = {'key1': 'value1', 'key2': 'value2'}
# r = requests.get("http://httpbin.org/get", params=payload)
# print r.url
# u'http://httpbin.org/get?key2=value2&key1=value1'

