HtmlLogger
==========

Supybot Plugin for creating HTML channel logs.

An improved ChannelLogger:
* Delete old conversations
* Output log in a format suitable for inclusion into a web page with CSS
  formatting, and embed that log into an HTML template
* All times are in UTC
* Turns URLs into links

Notes:
* Tested with Limnoria and Python 3.2, and Supybot and Python 2.7.
* Currently the same header and footer templates are used for all channels

TODO:
* Insert into HTML template information like channel name + date
* Allow an authenticated user to opt out of channel logging
* Localization files are still for ChannelLogger
* Improve the linkify regex
* Unit tests, especially for linkify
