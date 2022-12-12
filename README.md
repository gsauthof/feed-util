This repository contains news feed related utilities.

- `heiser.py` - a program that augments
  the heise.de news feed with content of the referenced articles
- `lwn.py` - create an atom feed with content for lwn.net
  articles
- `rss2atom.py` - convert an RSS 2 feed into an Atom one
  and deep copy the entry links as Atom content
- `cast.py` - create a minimal audio-cast Atom feed via
  extracting the information from some HTML pages
- `betterflix.py` - create atom feed of newly added Neflix/Prime
  movies that don't have a poor IMDB score

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

## `lwn.py`

Similar to `heiser.py` this program creates a rich [atom][atom] feed of
the latest [LWN.net][lwn] articles. Such a feed is optimal for
minimal feed readers and has value even without a proper internet
connection.

In contrast to the heise situation, since lwn.net only provides
RSS feeds, the `lwn.py` program doesn't augment anything.
Instead, it creates the atom feed, from scratch.

Besides being in a weird format and missing the article contents,
the RSS feeds published on lwn.net usually rotate too soon. That
means before all the latest articles are de-embargoed (lwn.net
has a time-limited paywall for new articles).

## `betterflix.py`

Netflix more and more develops into a dumping ground for low
quality movies and series. In addition, it comes with a horrible
UI that doesn't allow to filter the content in any meaningful
way. For example, it isn't even possible to filter for just
movies, to exclude movies one has downvoted, one has already
watched or to exclude movies made by certain directors one
dislikes.

It also doesn't help that Netflix completely fails to come up
with a good recommendation system. FWIW, I rated hundreds of
movies on Netflix (good and bad ones) and it doesn't make a
difference. The Netflix system still stubbornly suggests me the
most garbage movies and includes negatively rated movies in all
of their automatically 'curated' categories.

I thus created `betterflix.py`, a small script that fetches a
list of movies newly added by Netflix (or Prime) from the German
[wer-streamt.es][wse] service, fetches the [IMDB][imdb] score of
each movie and only selects movies with a score above a threshold
(say 6.5) into an [Atom][atom] feed.

Of course, using the IMDB score isn't perfect, but in my
experience it works surprisingly well - at least as a first
filter. Perhaps there is less fake reviewing happening on IMDB
than - say - on Amazon (for products), although IMDB is nowadays
also owned by Amazon.

One exception I noticed is when a popular Hollywood actor
switches the usual pattern and participates in an independent art
house production. In those cases a high quality movie might get
an unusual bad IMDB score because suddenly a crowd of fans that
are used to mainstream genres watch something completely
different (because their favourite actor stars in it) and might
be easily frustrated.

### Example Usage

Create an atom feed for new releases on Netflix:

    ./betterflix.py -o net-flix.xml

Create a similar feed for movies recently added to Amazon Prime:

    ./betterflix.py --prime -o prime-flix.xml

Use a different filter threshold (greater or equal):

    ./betterflix.py --thresh 7.1 -o net-flix.xml

As always, one can add such a call to a crontab on your private
web server such that your private feed is updated once a day,
for consumption by a mobile device.


[atom]: https://en.wikipedia.org/wiki/Atom_(standard)
[et]: https://docs.python.org/3.5/library/xml.etree.elementtree.html
[html5lib]: https://github.com/html5lib/html5lib-python
[requests]: http://docs.python-requests.org/en/master/
[crontab]: https://en.wikipedia.org/wiki/Cron
[lwn]: https://lwn.net/
[rss]: https://en.wikipedia.org/wiki/RSS
[wse]: https://www.werstreamt.es
[imdb]: https://en.wikipedia.org/wiki/IMDb

