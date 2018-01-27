#!/usr/bin/env python3

# 2017, Georg Sauthoff <mail@gms.tf>, GPLv3+


import argparse
import calendar
import datetime
import hashlib
import html5lib
import logging
import os
import re
import requests
import sys
import time
import xml.etree.ElementTree as ET
#import lxml.etree as ET

default_treebuilder = 'etree'
#default_treebuilder = 'lxml'

ans = '{http://www.w3.org/2005/Atom}'
xns = '{http://www.w3.org/1999/xhtml}'



log = logging.getLogger(__name__)

log_format      = '%(asctime)s - %(levelname)-8s - %(message)s'
log_date_format = '%Y-%m-%d %H:%M:%S'

def setup_logging():
  logging.basicConfig(format=log_format,
      datefmt=log_date_format, level=logging.DEBUG)
  logging.getLogger().handlers[0].setLevel(logging.WARNING)


def mk_arg_parser():
  p = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description='Create a LWN.net feed',
        epilog='2017, Georg Sauthoff <mail@gms.tf>, GPLv3+')
  p.add_argument('--cache',
      help='cache directory (default: $HOME/.cache/lwn)')
  p.add_argument('--verbose', '-v', action='store_true',
      help='turn on verbose logging')

  p.add_argument('--url', default='https://lwn.net/Articles/?offset=0',
      metavar='URL', help='start url')
  p.add_argument('-n', default=3, type=int,
      help='how many index pages to fetch')

  p.add_argument('input', metavar='FILE', nargs='*',
      help='alternative to --url - when files are already loaded')

  p.add_argument('--output', '-o', metavar='FILE', default='feed.xml',
      help='output filename')
  p.add_argument('--force', '-f', action='store_true',
      help="force feed writing - even if is hasn't changed")
  p.add_argument('--no-default', action='store_true',
      help="don't write default namespace")
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
    args.cache = os.environ['HOME'] + '/.cache/lwn'
  return args


def parse_next(root):
  link = next(filter(lambda x:x.text and x.text.startswith('Next '),
      root.iter(tag=xns+'a')))
  # lol, as of Python 3.6 Element objects without children are false-ish ...
  if link is None:
    r = None
  else:
    r = link.get('href')
  log.debug('Found next link: ' + r)
  return r

comment_re = re.compile('^[cC]omments.{1,20}$')

def norm_comment(e):
  for a in e.iter(tag=xns+'a'):
    if a.text and comment_re.match(a.text):
      a.text = '(Comments)'
  return e

def parse_headlines(root):
  rs = []
  for e in root.iter(tag=xns+'div'):
    klasse = e.get('class')
    if not klasse:
      continue
    if klasse == 'Headline':
      if e.findall('.//'+xns+'font[@class="Subscription"]'):
        last_headline = None
      else:
        last_headline = e
    elif klasse == 'BlurbListing' and last_headline:
      headline_str = ' '.join(last_headline.itertext())
      link = next(map(lambda x:x.get('href'),
          filter(lambda x:x.text=='Full Story', e.iter(xns+'a'))), None)
      log.debug('Full story link for {}: {}'.format(headline_str,
          (link if link else 'None')))
      rs.append( [headline_str, norm_comment(e), link] )
  next_link = parse_next(root)
  return (rs, next_link)

def parse_headlines_s(s):
  root = html5lib.parse(s, default_treebuilder)
  return parse_headlines(root)

def parse_headlines_f(filename):
  with open(filename) as f:
    s = f.read()
    return parse_headlines_s(s)

# shared with heiser.py
def get_resource(url, session):
  log.debug('Getting: {}'.format(url))
  r = session.get(url)
  r.raise_for_status()
  return r.text

# shared with heiser.py
def clean_cache(cache, protected_days=7):
  assert cache
  for fn in os.listdir(cache):
    filename = '{}/{}'.format(cache, fn)
    # time.time() doesn't necessarily return the UTC unix epoche ...
    delta = (calendar.timegm(time.gmtime())
        - os.path.getmtime(filename) ) / 3600 / 24
    if delta > protected_days:
      log.debug('Removing cached item: ' + filename)
      os.remove(filename)

san_re = re.compile('[^A-Za-z0-9_-]')

# shared with heiser.py
def get_article(link, ident, cache, session):
  i = san_re.sub('_', ident)
  filename = '{}/{}'.format(cache, i)
  if os.path.exists(filename):
    log.debug('Found ID {} under {}'.format(ident, cache))
    return open(filename, 'r')
  else:
    s = get_resource(link, session)
    with open(filename, 'w') as f:
      f.write(s)
    return s

# shared with heiser.py
def update_urls(a, base):
  def f(e, att):
    href = e.get(att)
    if not href:
      return
    if href.startswith('//'):
      e.set(att, 'https:' + href)
    elif href.startswith('/'):
      e.set(att, base + href)

  for e in a.iter():
    if e.tag == xns+'a':
      att = 'href'
    elif e.tag == xns+'img' or e.tag == 'iframe':
      att = 'src'
    else:
      continue
    f(e, att)

# shared with cast.py
def gen_id(e):
  h = hashlib.sha256()
  for x in e.iter():
    if x.tag == ans+'updated':
      continue
    h.update(bytes(x.tag, encoding='utf8'))
    if x.text:
      h.update(bytes(x.text, encoding='utf8'))
    for k, v in sorted(x.items()):
      h.update(bytes(k, encoding='utf8'))
      h.update(bytes(v, encoding='utf8'))
  hex = h.hexdigest()
  return 'urn:sha256:' + hex

now = datetime.datetime.utcnow()

def updated(off=0):
  updated = ET.Element(ans+'updated')
  updated.text = (now - datetime.timedelta(hours=off)).isoformat()+'Z'
  return updated

def mk_entry(row, off):
  entry = ET.Element(ans+'entry')
  ET.SubElement(entry, ans+'title').text = row[0]
  entry.append(updated(off))
  if row[2]:
    ET.SubElement(entry, ans+'link', rel='alternate', type='text/html',
        href='https://lwn.net/' + row[2])
  content = ET.SubElement(entry, ans + 'content')
  content.set('type', 'xhtml')
  content.append(row[1])
  ET.SubElement(entry, ans+'id').text = gen_id(entry)
  return entry

def mk_feed(rows, args):
  feed = ET.Element(ans + 'feed')
  ET.SubElement(feed, ans+'title').text = 'LWN.net'
  ET.SubElement(feed, ans+'link', rel='alternate', type='text/html',
      href='https://lwn.net/')
  ET.SubElement(feed, ans+'id').text = 'lwn.net'
  feed.append(updated())
  for off, row in enumerate(rows):
    feed.append(mk_entry(row, off))
  return ET.ElementTree(feed)

def remove_header(a):
  header = a.find(xns+'center')
  if header and header.find(xns+'table'):
    a.remove(header)
  return a

def test_well_form_anchors():
  inp = '''<p>The discrete tuples, consisting of frequency and voltage pairs,
that the device supports are called &quot;operating performance
points&quot; (OPPs). These were explained in detail in
<a href="/Articles/718632/"</a>this article</a>.
<p>
'''
  d = html5lib.parse(inp)
  a = d.findall('./'+xns+'body/'+xns+'p/'+xns+'a')[0]
  assert sorted(a.attrib.keys()) == [ '<', 'a', 'href' ]
  well_form_anchors(d)
  a = d.findall('./'+xns+'body/'+xns+'p/'+xns+'a')[0]
  assert sorted(a.attrib.keys()) == [ 'href' ]


def well_form_anchors(tree):
  for a in tree.iter(tag=xns+'a'):
    keys = list(a.attrib.keys())
    for key in keys:
      if key not in set(( 'href', 'name', 'rel', 'rev', 'urn', 'title',
        'methods', 'id', 'download', 'hreflang', 'ping', 'referrerpolicy',
        'target', 'type')):
        a.attrib.pop(key)


def resolve_articles(rs, args, session):
  for r in rs:
    if not r[2]:
      continue
    link =  'https://lwn.net' + r[2]
    a = get_article(link, link, args.cache, session)
    d = html5lib.parse(a, default_treebuilder)
    divs = d.findall('.//'+xns+'div[@class="ArticleText"]')
    if divs:
      r[1] = remove_header(divs[0])
      well_form_anchors(r[1])

def get_ids(t):
  r = [ x.text for x in  t.getroot().findall('.//'+ans+'id') ]
  return r

def get_ids_f(filename):
  if not os.path.exists(filename):
    return None
  log.debug('Checking {} for IDs ...'.format(filename))
  t = ET.parse(filename)
  r = get_ids(t)
  log.debug('Found existing IDs: ' + str(r))
  return r

def write_feed(f, args):
  if get_ids(f) == get_ids_f(args.output) and not args.force:
    log.debug('''Don't write {} because feed IDs haven't changed'''
        .format(args.output))
  else:
    log.debug('Writing {} ...'.format(args.output))
    f.write(args.output)
  # only works with lxml - kind of - still looks ugly
  #f.write(args.output, pretty_print=True)

def main(args):
  rs = []
  if args.input:
    for i in args.input:
      rs += parse_headlines_f(i)[0]

    session = requests.Session()
    resolve_articles(rs, args, session)
  else:
    session = requests.Session()
    url = args.url
    for _ in range(args.n):
      s = get_resource(url, session)
      r = parse_headlines_s(s)
      rs += r[0]
      url = 'https://lwn.net' + r[1]
    resolve_articles(rs, args, session)
  f = mk_feed(rs, args)
  update_urls(f, 'https://lwn.net')
  write_feed(f, args)


if __name__ == '__main__':
  setup_logging()
  args = parse_args()
  os.makedirs(args.cache, exist_ok=True)
  clean_cache(args.cache)
  sys.exit(main(args))


