#!/usr/bin/env python3

# 2017, Georg Sauthoff <mail@gms.tf>, GPLv3+

import argparse
import datetime
import logging
import os
import sys
import re
import email.utils

import html5lib
import xml.etree.ElementTree as ET

default_treebuilder = 'etree'
ans = '{http://www.w3.org/2005/Atom}'
xns = '{http://www.w3.org/1999/xhtml}'

import requests
# note that 0.11.5 has a bug in the ExpiresAge heuristics
# we need >= 0.12.3
import cachecontrol
assert tuple(int(x) for x in cachecontrol.__version__.split('.')) >= (0, 12, 3)
from cachecontrol import CacheControl
from cachecontrol.caches.file_cache import FileCache
import cachecontrol.heuristics

# handle for the module
log = logging.getLogger(__name__)

def setup_logging():
  log_format      = '%(asctime)s - %(levelname)-8s - %(message)s [%(name)s]'
  log_date_format = '%Y-%m-%d %H:%M:%S'
  logging.basicConfig(format=log_format, datefmt=log_date_format,
      level=logging.DEBUG) # or: loggin.INFO
  # restrict console logger - in that way, another handler can be more verbose
  logging.getLogger().handlers[0].setLevel(logging.WARNING)

def mk_arg_parser():
  p = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description='Convert RSS2 to Atom - deep copy item links',
        epilog='2017, Georg Sauthoff <mail@gms.tf>, GPLv3+')
  p.add_argument('--cache',
      help='cache directory (default: $HOME/.cache/feed-util)')
  p.add_argument('--output', '-o', metavar='FILE', default='feed.xml',
      help='output filename')
  p.add_argument('--url', default='https://example.org/rss2.xml',
      metavar='URL', help='start url')
  p.add_argument('--limit', '-n', type=int, default=10,
      help='number of articles to retain')
  p.add_argument('--no-default', action='store_true',
      help="don't write default namespace")
  p.add_argument('--force', '-f', action='store_true',
      help='force the generation of the feed - even if it is cached')
  p.add_argument('--verbose', '-v', action='store_true',
      help='turn on verbose logging')
  p.add_argument('--fetch', action='store_true', default=True,
      help='replace entry content with fetched content (default: fetch)')
  p.add_argument('--no-fetch', action='store_false', dest='fetch',
      help='replace entry content with fetched content (default: fetch)')
  return p

def parse_args(*a):
  arg_parser = mk_arg_parser()
  args = arg_parser.parse_args(*a)
  if not args.no_default:
    # just for writing
    # i.e. sets the default namespace - with that the feed is created like:
    #
    #    <feed xmlns="http://www.w3.org/2005/Atom"><id>...
    #
    # and not like:
    #
    #    <feed xmlns:ns0="http://www.w3.org/2005/Atom"><ns0:id>...
    #
    # this doesn't work with lxml
    ET.register_namespace('', 'http://www.w3.org/2005/Atom')
  if args.verbose:
    logging.getLogger().handlers[0].setLevel(logging.DEBUG)
  if not args.cache:
    args.cache = os.environ['HOME'] + '/.cache/feed-util'
  return args

def setup_sessions():
  # as CacheControl patches the session object, we can't share
  # one between both
  feed_sess = CacheControl(requests.Session(),
      cache=FileCache(args.cache + '/feed'))
  #article_sess = CacheControl(session,
  #    cache=FileCache(args.cache + '/forever', forever=True))
  article_sess = CacheControl(requests.Session(),
      cache=FileCache(args.cache + '/article'),
      heuristic=cachecontrol.heuristics.ExpiresAfter(days=2*365))
  return (feed_sess, article_sess)

# shared with heiser.py
def get(url, session):
  log.debug('Getting: {}'.format(url))
  r = session.get(url)
  r.raise_for_status()
  return r.text

def to_feed(s):
  d = ET.fromstring(s)
  return d

def to_article(s):
  # fix non-conforming html where <mail@example.org> isn't escaped
  s = re.sub('<([a-zA-Z0-9._-]+@[a-zA-Z0-9.-]+)>', '&lt;\\1&gt;', s)
  d = html5lib.parse(s, default_treebuilder)
  xs = d.findall('.//'+xns+'article')
  if xs:
    return xs[0]
  xs = d.findall('.//'+xns+'div[@class="post"]')
  if xs:
    return xs[0]
  xs = d.findall('.//'+xns+'body')
  if xs:
    a = ET.Element(xns+'article')
    for i in xs[0]:
      a.append(i)
    return a
  raise RuntimeError('''Didn't find article nor body element.''')

def to_isodate(s):
  t = email.utils.parsedate_tz(s)
  z = 'Z'
  off = t[9]
  if off:
    if off < 0:
      z = '-'
      off = off * -1
    else:
      z = '+'
    z += '{:02d}'.format(int(off/3600))
    z += ':{:02d}'.format(int( (off%3600)/60 ))
  s = '{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}{}'.format(
  #    *t[0:6], z) # < -this requires Python 3.5
      *(t[0:6] + (z,)))
  return s

def test_to_isodate():
  assert to_isodate('Wed, 07 Jun 2017 00:00:00 +0000') == '2017-06-07T00:00:00Z'
  assert to_isodate('Fri, 19 Aug 2016 23:21:47 +0530') == '2016-08-19T23:21:47+05:30'
  assert to_isodate('Mon, 26 Nov 2012 03:05:12 -0200') == '2012-11-26T03:05:12-02:00'
  assert to_isodate('Thu, 04 Aug 2016 20:32:26 -0700') == '2016-08-04T20:32:26-07:00'

def item2entry(item, url, use_description):
  entry = ET.Element(ans+'entry')
  ET.SubElement(entry, ans+'title').text = item.find('title').text
  ET.SubElement(entry, ans+'id').text = item.find('guid').text
  ET.SubElement(entry, ans+'updated').text = to_isodate(
      item.find('pubDate').text)
  link_url = item.find('link').text
  link = ET.SubElement(entry, ans+'link', rel='alternate', type='text/html',
      href=link_url)
  update_urls(link, url)
  content = ET.SubElement(entry, ans+'content', type='xhtml')
  if use_description:
    a = ET.SubElement(content, ans+'article')
    a.append(html5lib.parse(item.find('description').text, default_treebuilder))
    update_urls(a, url)
  return entry

now = datetime.datetime.now(datetime.UTC)

# shared with lwn.py
def updated(off=0):
  updated = ET.Element(ans+'updated')
  updated.text = (now - datetime.timedelta(hours=off)).isoformat()[:-6] + 'Z'
  return updated

def rss2atom(rss_feed, url, use_description, n):
  channel = rss_feed.find('channel')
  feed = ET.Element(ans + 'feed')
  ET.SubElement(feed, ans+'title').text = channel.find('title').text
  ET.SubElement(feed, ans+'link', rel='alternate', type='text/html',
      href=channel.find('link').text)
  ET.SubElement(feed, ans+'id').text = channel.find('link').text
  feed.append(updated())
  for _, item in zip(range(n), channel.findall('.//item')):
    feed.append(item2entry(item, url, use_description))
  return ET.ElementTree(feed)

def enrich_content(feed, session):
  for entry in feed.findall('.//'+ans+'entry'):
    url = entry.find(ans+'link').get('href')
    a = to_article(get(url, session))
    if sum(1 for _ in a.iter()) < 20:
      us = [ x.get('href') for x in a.findall('.//'+xns+'a') if x.get('href') ]
      if us and us.__len__() < 5:
        url = us[0]
        a = to_article(get(url, session))
    update_urls(a, url)
    content = entry.find(ans+'content')
    content.insert(0, a)

# shared with heiser.py
def update_urls(a, url):
  base = base_url(url)
  def f(e, att):
    href = e.get(att)
    if not href:
      return
    if href.startswith('//'):
      e.set(att, 'https:' + href)
    elif href.startswith('/') or href.startswith('./'):
      e.set(att, base + href)
    elif '://' not in href:
      if url.endswith('/'):
        e.set(att, url + href)
      else:
        e.set(att, url + '/' + href)

  for e in a.iter():
    if e.tag == xns+'a':
      att = 'href'
    elif e.tag == xns+'img':
      att = 'src'
    elif e.tag == ans+'link':
      att = 'href'
    else:
      continue
    f(e, att)

def base_url(s):
  return s[0:s.find('/', s.find('://')+3)]

def main(args):
  feed_sess, article_sess = setup_sessions()
  req = feed_sess.get(args.url)
  req.raise_for_status()
  log.debug(req.headers)
  if req.from_cache and not args.force:
    log.debug('Do nothing because because feed is still cached')
    return 0
  rss_feed = to_feed(req.text)
  feed = rss2atom(rss_feed, args.url, not args.fetch, args.limit)
  if args.fetch:
    enrich_content(feed, article_sess)
  feed.write(args.output)
  return 0

if __name__ == '__main__':
  setup_logging()
  args = parse_args()
  sys.exit(main(args))


