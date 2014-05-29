import re
import urllib2
import requests
from mako.template import Template

__author__ = "manuortega@gmail.com"
__version__ = "0.01"

airports = ("LEST", "LECO", "LEVX")
wind_warn = 0
wind_warn_gust = 0


def getwx(icao):
    icao.upper()

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


def wind_parser(full_tafor):
    """
    Obtains the following variables:
        wind_data: wind after removing KT and G if it is found
        wind_full: whole wind information (example: 29005KT or 29005G20KT)

        RETURNS (if above limits):
        wind_gust: only gust information, if G is wind_data_found
        wind_intensity: just normal intensity, no gust
        wind_component: just wind component
        wind_kt: the whole string
    """

    gust = None     # Declare variable for latter use inside for
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
                if gust >= wind_warn_gust:                                  # Shall it be passed?
                    wind_gust.append(gust)  # Stores GUST, converts to INT
                wind_data = (re.search("\w+(?=G)", wind_data)).group(0)     # Get wind data anyway

            intensity = int(wind_data[3:])                   # Stores wind intensity as INT

            if intensity >= wind_warn:                       # Shall the function return wind information?
                wind_component.append(wind_data[:3])         # This is a STR as it could be VRB as well!
                wind_intensity.append(intensity)             # Append to intensity[]

            if (intensity >= wind_warn) or (gust >= wind_warn_gust):     # Do it just once, no repetitions!
                wind_kt.append(wind_full)                                # Append to wind_kt[]

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

    email = None    # Declare variable for later use
    guilty_name, guilty_time, guilty_windkt, guilty_received, guilty_tafor = ([] for _ in range(5))
    guilty_component, guilty_intensity, guilty_gust = ([] for _ in range(3))

    for airport in airports:    # Global variable
        meet_conditions = False           # We need to check whether to send the email

        tafor, decoded, received = getwx(airport)    # Get tafor and decoded

        if tafor or decoded:    # If URL did not work, station_forecast and station_decoded = None
            name = station_parser(decoded)      # Call name parser
            time = time_parser(tafor)           # Call time parser
            component, intensity, gust, wind_kt = wind_parser(tafor)    # Call wind parser

            if intensity or gust:          # If intensity or gust are not blank
                meet_conditions = True     # Go ahead only if wind out of limits
                email = True               # At least one airport out of limits, send email!

            if meet_conditions:   # Global variables
                guilty_time.append(time)              # NOT BEING USED YET!
                guilty_name.append(name)
                guilty_received.append(received)      # NOT BEING USED YET!
                guilty_tafor.append(tafor)
                guilty_windkt.append(wind_kt)
                guilty_component.append(component)    # NOT BEING USED YET!
                guilty_intensity.append(intensity)    # NOT BEING USED YET!
                guilty_gust.append(gust)              # NOT BEING USED YET!

    if email:

        for index, value in enumerate(guilty_tafor):      # For each guilty_tafor

            for wind in guilty_windkt[index]:             # For each guilty_windkt
                words = [wind]                            # Create a list of guilty_winds

                for word in words:                                      # Format colour for HTML string
                    guilty_tafor[index] = guilty_tafor[index].\
                        replace(word, '<span style="color:red">'
                                      + word + '</span>')

                    guilty_tafor[index] = guilty_tafor[index]. \
                        replace("\n", "<br />")                         # Format lines for HTML string

        # HTML EMAIL TEMPLATE:
        template = Template("""
                    <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"
                    "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
                      <html xmlns="http://www.w3.org/1999/xhtml">
                        <head></head>
                        <body>
                          <h2>*** WEATHER ADVISORY ***<h2><br />
                          <pre>SETTINGS: MAX INTENSITY = ${wind_warn}  //  MAX GUST = ${wind_warn_gust}</pre><br />
                          % for index, value in enumerate(guilty_tafor):
                            <p>${guilty_name[index]}</p>
                            <pre>${value}</pre>
                            <br />
                          % endfor
                        </body>
                      </html>
                      """)


        # ENABLE LINE FOR CONSOLE TESTING:
        print template.render(guilty_tafor=guilty_tafor, guilty_name=guilty_name,
                              wind_warn=wind_warn, wind_warn_gust=wind_warn_gust)

        requests.post(
            "https://api.mailgun.net/v2/samples.mailgun.org/messages",
            auth=("api", "key-3ax6xnjp29jd6fds4gc373sgvjxteol0"),
            data={"from": "WX Advisory <your-mailgun@domain.com>",
                  "to": ["email@address.com"],
                  "subject": "*** WEATHER ADVISORY ***",
                  "html": template.render(guilty_tafor=guilty_tafor, guilty_name=guilty_name,
                              wind_warn=wind_warn, wind_warn_gust=wind_warn_gust),
                  "o:tracking": "no"})


# Test
warning()
