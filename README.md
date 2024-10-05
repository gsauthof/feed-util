This repository contains news feed related utilities.

- [`heiser.py`](#heiserpy) - a program that augments
  the heise.de news feed with content of the referenced articles
- [`lwn.py`](#lwnpy) - create an atom feed with content for lwn.net
  articles
- `rss2atom.py` - convert an RSS 2 feed into an Atom one
  and deep copy the entry links as Atom content
- `cast.py` - create a minimal audio-cast Atom feed via
  extracting the information from some HTML pages
- [`betterflix.py`](#betterflixpy) - create atom feed of newly added Neflix/Prime
  movies that don't have a poor IMDB score
- [`castproxy.py`](#castproxypy) - aggregate multiple audiocasts (podcasts) into
  a single Atom feed, optionally filtering each episode
- [`estr.py`](#estr) - fetch the daily Euro short-term rate (€STR/ESTR)

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


## `castproxy.py`

Castproxy aggregates multiple audiocasts (podcasts) into a single
Atom feed, based on a TOML feed configuration file.

It's killer feature is being able to configure a filter command
that is applied to each episode.

Such a filter can be used to convert weird audio formats,
normalize the volume or cut certain crap out of the audio file.

For example, integrating [cutbynoise][cutbynoise] - a
audiocast/podcast [ad blocker][adblock], may look like this:

```
[[feed]]
url = 'https://feeds.lagedernation.org/feeds/ldn-mp3.xml'
name = 'Lage der Nation'
short = 'ldn'
limit = 3
filter = [ 'cutbynoise', '-w', '-b', 'ldn-end.flac', '-v', '%src', '-o', '%dst' ]

[[feed]]
url = 'https://minkorrekt.podigee.io/feed/mp3'
name = 'Methodisch Inkorrekt'
short = 'mi'
limit = 3
filter = [ 'cutbynoise', '-w', '-b', 'mi-begin.flac', '-e', 'mi-end.flac', '-v', '%src', '-o', '%dst' ]
```

Such filtering is optional. Also, in case a filter fails, the
original episode file is delivered.

Besides the filtering, the aggregation can be useful, in its own
right. For example, when the target client is running on a mobile
device, only requesting an aggregated feed may save battery, save
mobile bandwidth and increase feed refresh speed, in comparison
to having to request each feed separately, from their sources.

Also, such an aggregated feed may improve your privacy, as it
limits tracking of your (mobile) IP connection and may block
additional tracking and advertisement links in the HTML included
in a feed.


### Setup

Castproxy is intended to run periodically, i.e. as a cron job or
a systemd timer.

Since it uses the fine [Configargparse][cargparse] package, its
options can be placed in a configuration file, for clarity.
A somewhat minimal example of such a configuration:

```
# NB: work directory needs to be on the same filesystem as the media directory
work   = /path/to/tmp/dir
feeds  = /path/to/feedcfg/castproxy.toml
url    = https://example.org/somebase
output = /srv/example.org/somebase/feed.xml
media  = /srv/example.org/somebase/media
```

Cron job call:

```
/path/to/castproxy -c /path/to/castproxy.ini
```

### How it works

Castproxy goes to some lengths to eliminate superfluous HTTP
requests.  Thus, it keeps some state in its work directory (in
JSON files) to store [ETag][etag] and last-modified header values for
the next follow-up request.
In that way, when a feed hasn't changed since the last request,
the server can simply respond with HTTP 304 Not Modified and
castproxy is saved from fetching and processing that feed,
needlessly.

Similarly, the aggregated feed (cf. `--output`) is only written
when at least one of the sources did change. Hence, a downstream
client that properly implements this protocol, also only ever
updates the aggregated feed on real changes.

To simplify the parsing of audiocast (podcast) feeds, which can
be quite diverse to due to wild growth of RSS versions and
podcast format extensions, castproxy relies on
[feedparser][feedparser] for this task.

In contrast, the aggregated output is just a minimal Atom
conforming feed, generated directly using the Python
[ElementTree][et] API.

For all HTTP needs castproxy uses [pycurl][pycurl] and to
normalize dates it relies on [dateutil][dateutil].


## ESTR

The utility `estr.py` fetches the current [Euro short-term
rate](https://www.ecb.europa.eu/stats/financial_markets_and_interest_rates/euro_short-term_rate/html/index.en.html)
([€STR a.k.a. ESTR](https://en.wikipedia.org/wiki/%E2%82%ACSTR))
from the European Central Bank.

The ESTR is based on real money-market transactions between
financial institutes. Building a local time-series over time can
be handy for a couple a use cases:

- Determining the spread between the ESTR and your [money market
  account](https://en.wikipedia.org/wiki/Money_market_account)
  interest rate.
  In case it's too high it may be a sign that you want to
  complain to your bank and look for alternatives.
- Checking that an investment in an ETF that tracks the ESTR
  still makes sense.

An ETF that tracks the ESTR (such as
[FR0010510800](https://isin.toolforge.org/?isin=FR0010510800) or
[LU0290358497](https://isin.toolforge.org/?isin=LU0290358497))
can be seen as an alternative to a traditional money market
account (MMA, German: Tagesgeldkonto) your bank offers.
Where banks often calculate relatively high costs for MMAs (e.g. 0.8 %
to 2.9 % when the ESTR is at 3.4 %), the example ETFs
only have a cost rate of 0.1 %.

While European MMAs are part of the mandatory and
state-guaranteed [deposit insurance
system](https://en.wikipedia.org/wiki/Deposit_insurance) (up to
100k € per customer per bank, basically), the fund assets have
special protection (that is not limited to 100k €!) if the issuer
collapses.

Technically, with an ETF, there is a tiny risk that a fraudulent
broker scams you out of your shares, and then the German bank
regulation safety net might limit compensation to [20k € per
person](https://de.wikipedia.org/wiki/Anlegerentsch%C3%A4digungsgesetz).
Also, although the kind of
[swaps](https://en.wikipedia.org/wiki/Swap_(finance)) used by an
ESTR tracking ETF is considered low risk by many, incompetent
fund management could still screw up big time, internal and
external control could fail at the same time and/or fund
management could deceive the public and regulators, given enough
criminal energy is available.
However, the probability of something like this may be relatively
tiny in comparison to other bad things that might happen to you.

As the ESTR approaches and crosses the inflation rate one may
want to reevaluate and reconsider any investments into ESTR
tracking ETFs.


### Usage Examples

Fetch last ESTR and print in CSV format:

```
./estr.py --csv
ref_date,pub_date,rate,initial_volume,number_banks,number_trnx,sh_vol_top_banks,pub_mode,vol_dist_25,vol_dist_75,pub_type
2024-10-03,2024-10-04,3.407,37573,31,497,58,Normal,3.39,3.43,Standard
```

Generate create statement for a table of ESTR data:

```
./estr.py --create
CREATE TABLE estr (
    ref_date         timestamp PRIMARY KEY,
    pub_date         timestamp,
    rate             decimal,
    initial_volume   bigint,
    number_banks     bigint,
    number_trnx      bigint,
    sh_vol_top_banks bigint,
    pub_mode         varchar(14),
    vol_dist_25      decimal,
    vol_dist_75      decimal,
    pub_type         varchar(14)
);
```

Command you can put into a cron job that imports the last ESTR on
each work day:

```
psql -d mydb --no-psqlrc --quiet --echo-errors -c "$(/usr/local/bin/estr --sql)"
```


[atom]: https://en.wikipedia.org/wiki/Atom_(standard)
[et]: https://docs.python.org/3/library/xml.etree.elementtree.html
[html5lib]: https://github.com/html5lib/html5lib-python
[requests]: http://docs.python-requests.org/en/master/
[crontab]: https://en.wikipedia.org/wiki/Cron
[lwn]: https://lwn.net/
[rss]: https://en.wikipedia.org/wiki/RSS
[wse]: https://www.werstreamt.es
[imdb]: https://en.wikipedia.org/wiki/IMDb
[cutbynoise]: https://github.com/gsauthof/cutbynoise
[adblock]: https://en.wikipedia.org/wiki/Ad_blocking
[cargparse]: https://github.com/bw2/ConfigArgParse
[etag]: https://en.wikipedia.org/wiki/HTTP_ETag
[feedparser]: https://github.com/kurtmckee/feedparser
[pycurl]: http://pycurl.io/
[dateutil]: https://github.com/dateutil/dateutil

