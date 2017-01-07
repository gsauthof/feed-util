#!/usr/bin/env python3

# 2017, Georg Sauthoff <mail@gms.tf>, GPLv3+

import argparse
import calendar
import html5lib
import logging
import os
import re
import requests
import sys
import time
#import xml.etree.ElementTree as ET
import xml.etree.cElementTree as ET

ans = '{http://www.w3.org/2005/Atom}'
xns = '{http://www.w3.org/1999/xhtml}'

# just for writing
ET.register_namespace('atom', 'http://www.w3.org/2005/Atom')

log = logging.getLogger(__name__)

log_format      = '%(asctime)s - %(levelname)-8s - %(message)s'
log_date_format = '%Y-%m-%d %H:%M:%S'

def setup_logging():
  logging.basicConfig(format=log_format,
      datefmt=log_date_format, level=logging.DEBUG)
  logging.getLogger().handlers[0].setLevel(logging.WARNING)

def setup_file_logging(filename):
  log = logging.getLogger()
  fh = logging.FileHandler(filename)
  fh.setLevel(logging.DEBUG)
  f = logging.Formatter(log_format + ' - [%(name)s]', log_date_format)
  fh.setFormatter(f)
  log.addHandler(fh)

default_heise_feed_url = 'https://www.heise.de/newsticker/heise-atom.xml'

def mk_arg_parser():
  p = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description='Augment heise.de feed with full stories for a better mobile experience',
        epilog='2017, Georg Sauthoff <mail@gms.tf>, GPLv3+')
  p.add_argument('--cache',
      help='cache directory (default: $HOME/.cache/heiser)')
  p.add_argument('--feed', metavar='FILE', nargs='?', const='heise-atom.xml',
      help='read feed from a FILE instead the URL')
  p.add_argument('--feed-url',
      default=default_heise_feed_url,
      help='URL of the heise.de ATOM news feed (default: {})'
               .format(default_heise_feed_url))
  p.add_argument('--log', nargs='?', metavar='FILE',
      const='heiser.log', help='log all messages into FILE')
  p.add_argument('--output', '-o', metavar='FILE', default='heiser.xml',
      help='augmented ATOM feed (default: heiser.xml)')
  p.add_argument('--verbose', '-v', action='store_true',
      help='turn on verbose logging')
  return p

def parse_args(*a):
  arg_parser = mk_arg_parser()
  args = arg_parser.parse_args(*a)
  if args.verbose:
    logging.getLogger().handlers[0].setLevel(logging.DEBUG)
  if args.log:
    setup_file_logging(args.log)
  if not args.cache:
    args.cache = os.environ['HOME'] + '/.cache/heiser'
  return args

def get_resource(url, session):
  log.debug('Getting: {}'.format(url))
  r = session.get(url)
  if r.status_code != 200:
    raise Exception(r.text)
  return r.text

san_re = re.compile('[^A-Za-z0-9_-]')

def get_article(link, ident, cache, session):
  i = san_re.sub('_', ident)
  filename = '{}/{}.heiser'.format(cache, i)
  if os.path.exists(filename):
    log.debug('Found ID {} under {}'.format(ident, cache))
    return open(filename, 'r')
  else:
    s = get_resource(link, session)
    with open(filename, 'w') as f:
      f.write(s)
    return s

def parse_article(link, ident, cache, session):
  o = get_article(link, ident, cache, session)
  return html5lib.parse(o)

def remove_header(a):
  header = a.find(xns+'header')
  a.remove(header)
  return a

def update_urls(a, base='https://heise.de'):
  def f(e, att):
    href = e.get(att)
    if href.startswith('//'):
      e.set(att, 'https:' + href)
    elif href.startswith('/'):
      e.set(att, base + href)

  for e in a.iter(tag=xns+'a'):
    f(e, 'href')
  for e in a.iter(tag=xns+'img'):
    f(e, 'src')
  for e in a.iter(tag=xns+'iframe'):
    f(e, 'src')

def extract_article(link, ident, cache, session):
  root = parse_article(link, ident, cache, session)
  author = ', '.join([ e.get('content')
      for e in root.iter(tag=xns+'meta') if e.get('name') == 'author'])
  a = next(root.iter(tag=xns+'article'))
  remove_header(a)
  update_urls(a)
  return (a, author)

def replace_content(root, session, cache='./cache'):
  for entry in root.iter(ans + 'entry'):
    link = entry.find(ans + 'link')
    href = link.get('href')
    ident = entry.find(ans + 'id')
    log.debug('Inserting {} (ID: {})'.format(href, ident.text))
    (article, author_s) = extract_article(href, ident.text, cache, session)
    old_content = entry.find(ans + 'content')
    i = entry.getchildren().index(old_content)
    entry.remove(old_content)
    content = ET.Element(ans + 'content')
    content.set('type', 'xhtml')
    content.insert(0, article)
    entry.insert(i, content)

    author = ET.Element(ans + 'author')
    author_name = ET.SubElement(author, ans + 'name')
    author_name.text = author_s
    entry.insert(i, author)

def clean_cache(cache, protected_days=7):
  for fn in os.listdir(cache):
    if fn.endswith('.heiser'):
      delta = (calendar.timegm(time.gmtime())
          - os.path.getmtime('{}/{}'.format(cache, fn)) ) / 3600 / 24
      if delta > protected_days:
        log.debug('Removing cached item: ' + fn)
        os.remove(fn)

def main():
  setup_logging()
  args = parse_args()
  os.makedirs(args.cache, exist_ok=True)
  clean_cache(args.cache)
  session = requests.Session()
  if args.feed:
    log.debug('Reading news feed from file: ' + args.feed)
    d = ET.parse(args.feed)
  else:
    d = ET.ElementTree(ET.fromstring(get_resource(args.feed_url, session)))
  replace_content(d, session, cache=args.cache)
  log.info('Writing augemented feed to: ' + args.output)
  d.write(args.output)

if __name__ == '__main__':
  sys.exit(main())

