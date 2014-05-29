# coding=utf-8
import re
import urllib2
import requests
import schedule
import time
import math
import sqlite3
from itertools import groupby
from ast import literal_eval
from mako.template import Template

__author__ = "manuortega@gmail.com"
__version__ = "1.00"

con = sqlite3.connect('airports.db')
con.row_factory = sqlite3.Row
cur = con.cursor()

cur.execute("SELECT * FROM airports ORDER BY ICAO ASC")
db_rows = cur.fetchall()

cur.execute("SELECT * FROM wind ORDER BY id ASC")
wind_rows = cur.fetchall()

for w in wind_rows:
    wind_warn = w["INT"]
    wind_warn_gust = w["GUST"]

normal_wx = ("FG", "BCFG", "0100", "0150", "0200", "0250", "0300", "0350", "0400", "0450", "0500",
             "0600", "0700", "0800", "0900", "1000", "1100", "1200", "1300", "1400", "1500", "1600",
             "1700", "1800", "1900", "2000", "2100", "2200", "2300", "2400", "2500", "2600", "2700",
             "2800", "2900", "3000", "VV000", "VV001", "VV002", "VV003", "TS", "TSRA", "SHRAGR",
             "TSRAGR", "SHRAGS", "TSRAGS", "WS", "SN", "SHSN")

heavy_wx = ("\\+TS", "\\+TSRA", "\\+SHRAGR", "\\+TSRAGR", "\\+SHRAGS", "\\+TSRAGS", "\\+SN",
            "\\+SHSN", "\\+SHRA")


def getwx(icao):
    icao = icao.upper()

    # NOAA URL for TAFORS:
    tafor_url = "http://weather.noaa.gov/pub/data/" \
                "forecasts/taf/stations/%s.TXT" % icao

    # NOAA URL for DECODED METAR - will be used to obtained decoded info (e.g. plain station name)
    decoded_url = "http://weather.noaa.gov/pub/data/" \
                  "observations/metar/decoded/%s.TXT" % icao

    urllib2.install_opener(urllib2.build_opener())

    try:
        get_tafor = urllib2.urlopen(tafor_url)   # Stores TXT
        station_forecast = get_tafor.read()
        time_received = (station_forecast.split("\n")).pop(0)    # Splits and pops first line (time)
        station_forecast = '\n'.join(station_forecast.split('\n')[1:])   # Then removes first line
    except urllib2.HTTPError:
        station_forecast = None
        time_received = None
        pass

    try:
        get_decoded = urllib2.urlopen(decoded_url)   # Stores TXT
        station_decoded = get_decoded.read()
    except urllib2.HTTPError:
        station_decoded = None
        pass

    return station_forecast, station_decoded, time_received


def station_parser(full_decoded):
    lines = full_decoded.split("\n")
    airport_name = lines[0]   # Obtains airport name

    return airport_name


def time_parser(full_tafor):
    # Parses time so that we can identify if tafor has changed from last time

    lines = full_tafor.split(" ")   # Split in words so that we reduce false positives with break in loop

    time_found = "0"

    for line in lines:
        if "Z" in line:
            if len(line) == 7:      # Trying to avoid ICAO with "Z" like LEZL
                time_found = (re.search("\w+(?<=Z)", line)).group(0)
                break               # Avoid false positives, break the loop

    return time_found


def wind_parser(full_tafor, specific_int, specific_gust):
    """
    Obtains the following variables:
        wind_data: wind after removing KT and G if it is found
        wind_full: whole wind information (example: 29005KT or 29005G20KT)

        RETURNS:
        wind_gust: only gust information, if G is wind_data_found
        wind_intensity: just normal intensity, no gust
        wind_component: just wind component
        wind_kt: the whole string

    Intensity will be controlling. We return the gust even it's below limits (or "None" if there is no gust
    but intensity is beyond limits). We need to keep in mind that every WIND_KT string might or might not have
    a gust, but it's always going to have an intensity. By always passing the gust except when intensity is below
    limits AND there is no gust in the string, we make sure that all crosswind calculations work properly.
    """
    wind_component, wind_intensity, wind_gust, wind_kt = ([] for _ in range(4))

    lines = full_tafor.split("\n")  # Splits TAFOR in several lines to analise separately (example: TEMPOS)

    for line in lines:
        if "KT" in line:
            wind_data_found = re.search("\w+(?=KT)", line)    # Finds and stores only numbers
            wind_full_found = re.search("\w+(?<=KT)", line)   # Finds and stores full wind data
            wind_data = wind_data_found.group(0)              # Convert to string, still with possible GUST!
            wind_full = wind_full_found.group(0)              # Convert to string

            if "G" in wind_data:
                gust = int((re.search("\w\w(?=KT)", wind_full)).group(0))   # What's the gust?
                wind_data = (re.search("\w+(?=G)", wind_data)).group(0)     # Get wind data

                if specific_int >= 0 or specific_gust >= 0:     # Use specific wind or use generic?
                    if int(wind_data[3:]) >= specific_int or gust >= specific_gust:
                        wind_gust.append(gust)
                else:                                           # No specific found, let's use generic
                    if int(wind_data[3:]) >= wind_warn or gust >= wind_warn_gust:
                        wind_gust.append(gust)          # Append the real gust only if one of the two is beyond limits
            else:
                gust = None                             # Reset value so it does not pass next time in loop
                if specific_int >= 0:
                    if int(wind_data[3:]) >= specific_int:
                        wind_gust.append("None")
                else:
                    if int(wind_data[3:]) >= wind_warn:
                        wind_gust.append("None")              # There's no gust BUT there is an out-of-limits intensity

            intensity = int(wind_data[3:])                    # Stores wind intensity as INT

            if specific_int >= 0 or specific_gust >= 0:
                if intensity >= specific_int or gust >= specific_gust:
                    wind_kt.append(wind_full)                          # Append to wind_kt[]
                    wind_component.append(wind_data[:3])               # This is a STR as it could be VRB as well!
                    wind_intensity.append(intensity)                   # Append to intensity[]
            else:
                if intensity >= wind_warn or gust >= wind_warn_gust:   # Append intensity only one is out of limits
                    wind_kt.append(wind_full)                          # Append to wind_kt[]
                    wind_component.append(wind_data[:3])               # This is a STR as it could be VRB as well!
                    wind_intensity.append(intensity)                   # Append to intensity[]

    return wind_component, wind_intensity, wind_gust, wind_kt


def warning():
    """
    Assess wind intensity and issues warning as necessary.

    guilty_time --> UTC time contained in the tafor (i.e. 1530Z) - Did we already warn about this one?
    guilty_name --> Station name with coordinates and elevation, obtained from NOAA's decoded tafors
    guilty_received --> Time at which the info was received by NOAA
    guilty_tafor --> The requested tafors
    guilty_windkt --> Whole wind string (e.g. 26023G45KT)
    guilty_component --> Calculate crosswind (e.g. 260)
    guilty_intensity --> Calculate crosswind (e.g. 23)
    guilty_gust --> Gust wind string (e.g. 45)
    """

    email = specific_int = specific_gust = None    # Declare variable for later use
    guilty_name, guilty_time, guilty_windkt, guilty_received, guilty_tafor = ([] for _ in range(5))
    guilty_component, guilty_intensity, guilty_gust, guilty_rwy = ([] for _ in range(4))
    crosswind_final, this_int, this_gust = ([] for _ in range(3))

    for row in db_rows:    # Global variable
        airport = row["ICAO"]     # Assign database ICAO to airport variable
        runway = row["RUNWAYS"]
        specific_int = row["WIND_INT"]
        specific_gust = row["WIND_GUST"]

        tafor, decoded, received = getwx(airport)    # Get tafor and decoded

        if tafor or decoded:    # If URL did not work, station_forecast and station_decoded = None
            name = station_parser(decoded)           # Call name parser
            zulu_time = time_parser(tafor)           # Call time parser
            component, intensity, gust, wind_kt = wind_parser(tafor, specific_int, specific_gust)    # Call wind parser

            if wind_kt:                     # If intensity or gust are not blank
                email = True                          # At least one airport out of limits, send email!
                guilty_time.append(zulu_time)         # NOT BEING USED YET!
                guilty_name.append(name)
                guilty_received.append(received)      # NOT BEING USED YET!
                guilty_tafor.append(tafor)
                guilty_windkt.append(wind_kt)
                guilty_component.append(component)
                guilty_intensity.append(intensity)
                guilty_gust.append(gust)
                this_int.append(specific_int)
                this_gust.append(specific_gust)

                if row["RUNWAYS"]:                    # If runway is specified in DB
                    guilty_rwy.append(runway)         # Append dict from database
                else:
                    guilty_rwy.append(None)         # Otherwise append None (in str format)

    if email:

        for index, value in enumerate(guilty_tafor):      # For each guilty_tafor

            # Sub all characters and only whole words (watch out for whitespaces around SPAN!)
            for normal in normal_wx:
                guilty_tafor[index] = re.sub(r" %s " % normal,
                                             ' <span style="color:orange; font-weight: bold;">'
                                             + normal + '</span> ', guilty_tafor[index])

            # Sub all characters and only whole words (watch out for whitespaces around SPAN!)
            for heavy in heavy_wx:
                heavy_no_sign = heavy[2:]  # Remove "\\+" front printing, otherwise it does not work correctly!
                guilty_tafor[index] = re.sub(r" %s " % heavy,
                                             ' <span style="color:orange; font-weight: bold;">'
                                             + "+" + heavy_no_sign + '</span> ', guilty_tafor[index])

            for wind in guilty_windkt[index]:             # For each guilty_windkt
                words = [wind]                            # Create a list of guilty_winds

                for word in words:                                      # Format colour for HTML string
                    guilty_tafor[index] = guilty_tafor[index].\
                        replace(word, '<b><span style="color:red; font-weight: bold;">'
                                      + word + '</span></b>')

                    guilty_tafor[index] = guilty_tafor[index]. \
                        replace("\n", "<br />")                         # Format lines for HTML string

            # ******************* CROSSWIND STARTS **********************
            each_component, each_intensity, each_gust, each_rwy_course, each_rwy_id = ([] for _ in range(5))
            each_kt, crosswind_kts, crosswind_values = ([] for _ in range(3))

            if guilty_rwy[index]:                           # If we have a runway in the database for this tafor

                my_dict = literal_eval(guilty_rwy[index])   # Stores tafor runway(s) as a dictionary

                for kt in guilty_windkt[index]:             # Stores KT for each tafor
                    each_kt.append(kt)

                for number, track in my_dict.iteritems():   # Stores runway identification (20/02 or 35, etc)
                    each_rwy_id.append(number)

                    if track[0] == "0":                     # Remove leading zero to course (035 becomes 35)
                        track = track[1:]                   # Otherwise calculations are all wrong

                    each_rwy_course.append(int(track))      # Stores corrected track as a int

                for comp in guilty_component[index]:
                    each_component.append(comp)             # Stores components for each tafor

                for intens in guilty_intensity[index]:      # Stores intensities for each tafor
                    each_intensity.append(intens)

                for gust in guilty_gust[index]:
                    if gust != "None":                      # Is there is GUST, store the gust
                        each_gust.append(gust)
                    else:
                        each_gust.append("None")            # Otherwise store "None"

                for ind, kt in enumerate(guilty_windkt[index]):

                    crosswind_kts.append("%s" % kt + " >> ")       # Append first part of the final string

                    for a, b in enumerate(each_rwy_id):

                        if each_component[ind] != "VRB":                     # If component is not variable
                            wind_from = int(each_component[ind])        # we can finally transform it to an int
                            rwy_course = each_rwy_course[a]             # It's easier to use this var names

                            if abs(rwy_course - wind_from) <= 180:
                                angle = abs(rwy_course - wind_from)
                            else:
                                angle = 360 - abs(rwy_course - wind_from)

                            # Actual crosswind calculation
                            xwind = round(abs(each_intensity[ind] * math.sin(math.radians(angle))), 1)

                            if each_gust[ind] != "None":      # Is there a gust outside limits?
                                xgust = round(abs(each_gust[ind] * math.sin(math.radians(angle))), 1)
                            else:
                                xgust = "None"     # Otherwise no calculations are necessary
                        else:
                            xwind = 999        # Easier than using a "VRB" string
                            xgust = 999

                        # Depending on the conditions we create the second part of the final string
                        if xwind <= 20:
                            xwind = "<b><span style='color:green; font-weight: bold;'>%.0f</span></b>" % xwind
                        elif 20 < xwind <= 35:
                            xwind = "<b><span style='color:orange; font-weight: bold;'>%.0f</span></b>" % xwind
                        elif 35 < xwind < 999:
                            xwind = "<b><span style='color:red; font-weight: bold;'>%.0f</span></b>" % xwind
                        else:
                            xwind = "<b><span style='color:orange; font-weight: bold;'>??</span></b>"

                        if xgust != "None":
                            if xgust <= 20:
                                xgust = "<b><span style='color:green; font-weight: bold;'>%.0f</span></b>" % xgust
                            elif 20 < xgust <= 35:
                                xgust = "<b><span style='color:orange; font-weight: bold;'>%.0f</span></b>" % xgust
                            elif 35 < xgust < 999:
                                xgust = "<b><span style='color:red; font-weight: bold;'>%.0f</span></b>" % xgust

                        # If there is no gust, we will just append the xwin
                        if xgust == "None" or xgust == 999:
                            crosswind_values.append("RWY %s" % b + " > " + xwind)
                        else:
                            crosswind_values.append("RWY %s" % b + " > " + "%sG%s" % (xwind, xgust))

                    crosswind_values.append("\n")       # Append \n to separate for every tafor

                # Join those values
                join_values = [" # ".join(g) for k, g in groupby(crosswind_values, "\n".__ne__) if k]

                # Join both parts of the string
                for a, b in enumerate(crosswind_kts):
                    crosswind_final.append(crosswind_kts[a] + join_values[a])

                # Separate strings
                crosswind_final.append("\n")

        # Then rejoin them if crosswind final exists
        if crosswind_final:
            the_crosswind = [list(g) for k, g in groupby(crosswind_final, "\n".__ne__) if k]
        else:
            the_crosswind = "None"
        # ******************* CROSSWIND ENDS **********************

        # HTML EMAIL TEMPLATE:
        template = Template("""
                    <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"
                    "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
                      <html xmlns="http://www.w3.org/1999/xhtml">
                        <head>
                          <style type="text/css">
                            h1 { background:#000; color:#990; font-family: verdana }
                            h2 { font-family: verdana; font-size: 15px }
                            h3 { font-family: verdana; font-size: 12px; font-weight:normal }
                            h4 { font-family: verdana; font-size: 9px; font-weight:normal }
                          </style>
                        </head>
                        <body>
                          <h1>ADVERSE WEATHER ADVISORY</h1><br />
                          % for index, value in enumerate(guilty_tafor):
                            <h2>${guilty_name[index]}</h2>
                            <pre><h3>${value}</h3></pre>
                              % if the_crosswind != "None":
                                % if guilty_rwy[index] != None:
                                    <h4>CROSSWIND:</h4>
                                    <blockquote>
                                      % for cross in the_crosswind[index]:
                                        <h4>${cross}</h4>
                                      % endfor
                                    </blockquote>
                                % endif
                              % endif
                              % if this_int[index] != 999 and this_gust[index] != 999:
                                <pre><i>SPECIFIC LIMIT: INT = ${this_int[index]} // GUST = ${this_gust[index]}</i></pre>
                              % elif this_int[index] != 999 and this_gust[index] == 999:
                                <pre><i>SPECIFIC LIMIT: INT = ${this_int[index]} // GUST = ${wind_warn_gust}</i></pre>
                              % elif this_int[index] == 999 and this_gust[index] != 999:
                                <pre><i>SPECIFIC LIMIT: INT = ${wind_warn} // GUST = ${this_gust[index]}</i></pre>
                              % endif
                            <br />
                          % endfor
                          <pre>#############</pre><br />
                          <pre>GENERIC LIMIT: INT = ${wind_warn}  //  GUST = ${wind_warn_gust}<br /></pre>
                        </body>
                      </html>
                      """)

        # ENABLE LINE FOR CONSOLE TESTING:
        print template.render(guilty_tafor=guilty_tafor, guilty_name=guilty_name,
                              wind_warn=wind_warn, wind_warn_gust=wind_warn_gust,
                              the_crosswind=the_crosswind, guilty_rwy=guilty_rwy,
                              this_int=this_int, this_gust=this_gust)

        """requests.post(
            "https://api.mailgun.net/v2/xxxxxx/messages",
            auth=("api", "key-320xxxxxxxxxxxxxxxxxxxxxxxxxx"),
            data={"from": "Safety BOT <safetybot@xxxxx.com>",
                  "to": ["xxxxxx@xxxxx.com"],
                  "subject": "ADVERSE WEATHER WARNING",
                  "html": template.render(guilty_tafor=guilty_tafor, guilty_name=guilty_name,
                                          wind_warn=wind_warn, wind_warn_gust=wind_warn_gust,
                                          the_crosswind=the_crosswind, guilty_rwy=guilty_rwy,
                                          this_int=this_int, this_gust=this_gust),
                  "o:tracking": "no"})"""


# Comment for scheduling:
warning()


"""schedule.every(8).hours.do(warning)

while True:
    schedule.run_pending()
    time.sleep(1)"""


if con:
    con.close()