# WXAdvisory
==========

WXAdvisory gets the current TAFOR from a certain airport and parses the text. If weather conditions are found to be beyond a specified threshold, it sends an email to warn about it. This email is formatted depending on several weather fenomena, some of which as well as the activating threshold can be configured throug a SQLite database.


![Picture](http://imgur.com/Vx3Ea8t)





==========

Changelog:

** v1.00 **

- Added database functionality
- Emails formatted for wind and other weather fenomena
- Crosswind calculations and also formatted in the email
