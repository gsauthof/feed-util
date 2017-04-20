This repository contains news feed related utilities.

- `heiser.py` - a program that augments
the heise.de news feed with content of the referenced articles
- `cast.py` - create a minimal audio-cast Atom feed via
extracting the information from some HTML pages

2017, Georg Sauthoff <mail@gms.tf>

## `heiser.py`

Example:

    $ ./heiser.py -o /srv/website/heiser.xml

Or running it periodically via a [crontab][crontab] entry:

    */20 * * * * /path/to/heiser.py -o /srv/website/heiser.xml

(runs it every 20 minutes)

Say a http daemon serves `/srv/website` as `https://example.org/`
then you can retrieve the augmented feed via subscribing to
`https://example.org/heiser.xml`.


### Motivation

The standard heise.de news feed just contains a summary of each
article thus it is poorly suited for minimal feed readers and
usage on mobile devices.

### What it does

`heiser.py` fetches the heise.de feed and edits it such that in
the end each entry contains proper author information and the
complete article content. It also converts relative URL
references into absolute ones..

### How it works

The program is written in Python 3. [html5lib][html5lib] is used
for parsing the real-world HTML articles into XML trees (e.g.
libxml2 fails on those inputs - even in HTML mode). For parsing
XML and other XML massaging (i.e. the input and output feeds are
encoded in [Atom][atom]) the [ElementTree-API][et] that is part
of the Python standard library is used. Referenced articles are
locally cached for a few days to avoid redundant retrievals. The
convenient [requests][requests] library is used for all HTTP
operations. They go through a `requests.Session` object such that
a connection is reused for multiple HTTP GET operations that
target the same server.

[atom]: https://en.wikipedia.org/wiki/Atom_(standard)
[et]: https://docs.python.org/3.5/library/xml.etree.elementtree.html
[html5lib]: https://github.com/html5lib/html5lib-python
[requests]: http://docs.python-requests.org/en/master/
[crontab]: https://en.wikipedia.org/wiki/Cron
