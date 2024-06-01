#!/usr/bin/env python3

# Create a minimal audio-cast feed from some legacy HTML pages.
#
# 2017, Georg Sauthoff <mail@gms.tf>

import argparse
import datetime
import hashlib
import html5lib
import sys
import xml.etree.ElementTree as ET


ans = '{http://www.w3.org/2005/Atom}'
xns = '{http://www.w3.org/1999/xhtml}'


now = datetime.datetime.now(datetime.UTC).isoformat()[:-6] + 'Z'
updated = ET.Element(ans+'updated')
updated.text = now


def mk_arg_parser():
  p = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description='Create minimal netcast feed',
        epilog='...')
  p.add_argument('--title', metavar='TITLE', help='feed title')
  p.add_argument('--site', default='http://example.org', metavar='URL',
      help='feed html site')
  p.add_argument('input', metavar='FILE', nargs='+',
      help='html input files (already downloaded')
  p.add_argument('--output', '-o', metavar='FILE', default='feed.xml',
      help='output filename')
  p.add_argument('--no-default', action='store_true',
      help="don't write default namespace")
  return p

def parse_args(*a):
  arg_parser = mk_arg_parser()
  args = arg_parser.parse_args(*a)
  return args

def collect_media(d):
  rs = []
  for e in d.iter():
    if e.tag == xns + 'h2':
      a = e.findall('.//{}a'.format(xns))
      link = a[0].get('href') if a else ''
      text = ''.join(e.itertext())
    elif e.tag == xns + 'a' and e.get('href').endswith('.mp3'):
      media = e.get('href')
      rs.append((media, link, text))
  return rs

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

def mk_entry(l):
  entry = ET.Element(ans+'entry')
  ET.SubElement(entry, ans+'title').text = l[2]
  entry.insert(100, updated)
  ET.SubElement(entry, ans+'link', rel='alternate', type='text/html',
    href=l[1])
  t = 'audio/ogg; codecs=opus' if l[0].endswith('.opus') else 'audio/mpeg'
  ET.SubElement(entry, ans+'link', rel='enclosure', type=t, href=l[0])
  ET.SubElement(entry, ans+'id').text = gen_id(entry)
  return entry

def mk_feed(ls, args):
  feed = ET.Element(ans + 'feed')
  ET.SubElement(feed, ans+'title').text = args.title
  ET.SubElement(feed, ans+'link', rel='alternate', type='text/html',
    href=args.site)
  feed.append(updated)
  for l in ls:
    feed.append(mk_entry(l))
  id = ET.Element(ans+'id')
  id.text = gen_id(feed)
  feed.insert(0, id)
  return ET.ElementTree(feed)

def set_defaults(d, args):
  if not args.title:
    args.title =  d.find('./'+xns+'head/'+xns+'title').text.strip(' \t\r\n~')
  if not args.title:
    args.title = 'Example'

def main(args):
  if args.input:
    ls = []
    for i, filename in enumerate(args.input):
      with open(filename) as f:
        t = f.read()
        d = html5lib.parse(t)
        if i == 0:
          set_defaults(d, args)
        l = collect_media(d)
        ls += l
    #mk_feed(ls, args).write(args.output, method='c14n')
    mk_feed(ls, args).write(args.output)
  return 0

if __name__ == '__main__':
  args = parse_args()
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
    # note: Antennapod can't deal with such feeds ...
    ET.register_namespace('', 'http://www.w3.org/2005/Atom')
  sys.exit(main(args))


