## WXAdvisory


WXAdvisory gets the current TAFOR from a certain airport and parses the text. If weather conditions are found to be beyond a specified threshold, it sends an email to warn about it. This email is formatted depending on several weather phenomena, some of which, as well as the activating threshold, can be configured through an SQLite DB.


![Picture](https://raw.githubusercontent.com/Manuito83/WXAdvisory/master/email%20preview.PNG)




==========

Changelog:

** v1.00 **

- Added database functionality
- Emails formatted for wind and other weather fenomena
- Crosswind calculations and also formatted in the email
