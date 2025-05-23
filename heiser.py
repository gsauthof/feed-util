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
# since Python >= 3.3 xml.etree.cElementTree is deprecated
import xml.etree.ElementTree as ET

ans = '{http://www.w3.org/2005/Atom}'
xns = '{http://www.w3.org/1999/xhtml}'
# reserved namespace, must not be declared
xmlns = '{http://www.w3.org/2000/xmlns/}'

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
        help='URL of the heise.de ATOM news feed (default: %(default)s)')
    p.add_argument('--log', nargs='?', metavar='FILE',
        const='heiser.log', help='log all messages into FILE')
    p.add_argument('--output', '-o', metavar='FILE', default='heiser.xml',
        help='augmented ATOM feed (default: %(default)s)')
    p.add_argument('--verbose', '-v', action='store_true',
        help='turn on verbose logging')
    p.add_argument('--filter', help=('Filter entries based on the title'
        ' (i.e. no ads/TechStage/heise+) (default: %(default)s)'), nargs=1,
        default='Anzeige:|TechStage|heise\\+')
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
    r.raise_for_status()
    return r.text

san_re = re.compile('[^A-Za-z0-9_-]')

def get_article(link, ident, cache, session):
    i = san_re.sub('_', ident)
    filename = '{}/{}.heiser'.format(cache, i)
    if os.path.exists(filename):
        log.debug('Found ID {} under {}'.format(ident, cache))
        return open(filename, 'r')
    else:
        url = link.split('?')[0] + '?seite=all'
        s = get_resource(url, session)
        with open(filename, 'w') as f:
            f.write(s)
        return s

def parse_article(link, ident, cache, session):
    o = get_article(link, ident, cache, session)
    return html5lib.parse(o)


def stack_iter(element, tag=None):
    stack = []
    stack.append(iter([element]))
    es = [ None ]
    while stack:
        e = next(stack[-1], None)
        es[-1] = e
        if e == None:
            stack.pop()
            es.pop()
        else:
            stack.append(iter(e))
            if tag == None or e.tag == tag:
                yield (e, es)
            es.append(None)

def oneof_in(qs, t):
    for q in qs:
        if q in t:
            return True
    return False

# and facebook/twitter/... share boilerplate
# and static ads
# and custom tags
def remove_script(a):
    l = []
    for e, stack in stack_iter(a):
        if e.tag in (xns+'script', xns+'noscript'):
            l.append( (stack[-2], e) )
        elif e.tag == xns+'div' and 'shariff' in e.get('class', ''):
            l.append( (stack[-2], e) )
        elif e.tag == xns+'div' and 'creator' in e.get('class', ''):
            l.append( (stack[-2], e) )
        elif e.tag == xns+'footer':
            l.append( (stack[-2], e) )
        elif e.tag == xns+'div' and 'footer' in e.get('class', ''):
            l.append( (stack[-2], e) )
        elif e.tag == xns+'header':
            l.append( (stack[-2], e) )
        elif e.tag == xns+'p' and 'article_page_category' in e.get('class', ''):
            l.append( (stack[-2], e) )
        elif e.tag == xns+'ul' and 'article_page_info' in e.get('class', ''):
            l.append( (stack[-2], e) )
        # i.e. match double-click ads <html:aside class="teaser ad-microsites">
        # and similar
        elif (e.tag in (xns+'div', xns+'aside')
                and oneof_in(('-ad-container', 'img-ad', 'teaser', 'newsletter-subscription'), e.get('class', '')) ):
            l.append( (stack[-2], e) )
        elif e.tag == xns+'div' and '-ad-' in e.get('id', ''):
            l.append( (stack[-2], e) )
        elif str(e.tag).startswith(xns+'a-'):
            if e.tag == xns+'a-img':
                e.tag = xns+'img'
            else:
                l.append( (stack[-2], e) )
        elif e.tag == xns+'a' and 'a-button' in e.get('class', ''):
            l.append( (stack[-2], e) )
        # i.e. match class="ad-microsites__item" or
        # <html:aside class="us-ad">
        elif e.get('class', '').startswith('ad-') or e.get('class', '').endswith('-ad'):
            l.append( (stack[-2], e) )
    for parent, node in l:
        parent.remove(node)

def remove_entries(d, expr):
    if not expr:
        return
    ex = re.compile(expr)
    l = []
    log.debug('Filtering titles ...')
    for e, stack in stack_iter(d):
        if e.tag == ans+'entry':
            t = e.find(ans+'title')
            if ex.match(t.text):
                log.debug('Removing entry because of its title: {}'.format(t.text))
                l.append( (stack[-2], e) )
    for parent, node in l:
        parent.remove(node)

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


def str_contains(s, xs):
    return any(x in s for x in xs)

# work around html5lib parses that contain invalid characters
# in attribute names. Example HTML input:
#   <a href="/thema/Missing-Link"
#   title="Mehr zum Feuilleton "Missing Link"">
#     Mehr zum Feuilleton "Missing Link"
#   </a>
def fix_attributes(a):
    for e in a.iter():
        ks = []
        for k, v in e.attrib.items():
            if str_contains(k, ('"', ',', '!', '?', '-')):
                ks.append(k)
        for k in ks:
            e.attrib.pop(k)

def fix_xmlns(a):
    for e in a.iter():
        xs = []
        for k, v in e.attrib.items():
            if k == xmlns + 'xmlns':
                xs.append((k, v))
        for k, v in xs:
            e.attrib.pop(k)
            a.attrib['xmlns'] = v

class No_Article_Error(Exception):
    pass

def find_article(root):
    for a in root.iter():
        if a.tag == xns+'article' and a.get('id', None) == 'meldung':
            return a
        if a.tag == xns+'div' and 'article_page' in a.get('class', ''):
            return a
    raise No_Article_Error("Couldn't find any article element")

def extract_article(link, ident, cache, session):
    root = parse_article(link, ident, cache, session)
    author = ', '.join([ e.get('content')
        for e in root.iter(tag=xns+'meta') if e.get('name') == 'author'])
    a = find_article(root)
    remove_script(a)
    i = link.index('//')
    prefix = link[:link.index('/', i+2)]
    update_urls(a, prefix)
    fix_attributes(a)
    fix_xmlns(a)
    return (a, author)

def replace_content(root, session, cache='./cache'):
    xs = []
    for entry, stack in stack_iter(root):
        if entry.tag != ans+'entry':
            continue
        link = entry.find(ans + 'link')
        href = link.get('href')
        ident = entry.find(ans + 'id')
        if '/bestenlisten/' in href:
            log.debug(f'Removing {href} because TechStage')
            xs.append( (stack[-2], entry) )
            continue
        log.debug('Inserting {} (ID: {})'.format(href, ident.text))
        try:
            (article, author_s) = extract_article(href, ident.text, cache, session)
        except No_Article_Error as e:
            log.debug('Not modifying entry: {}'.format(e))
            continue
        except requests.exceptions.HTTPError as e:
            log.debug('Not modifying entry due to HTTP error: {}'.format(e))
            continue

        old_content = entry.find(ans + 'content')
        i = list(entry).index(old_content)
        entry.remove(old_content)
        content = ET.Element(ans + 'content')
        content.set('type', 'xhtml')
        content.append(article)
        entry.insert(i, content)

        author = ET.Element(ans + 'author')
        author_name = ET.SubElement(author, ans + 'name')
        author_name.text = author_s
        entry.insert(i, author)
    for parent, e in xs:
        parent.remove(e)

def clean_cache(cache, protected_days=7):
    for fn in os.listdir(cache):
        if fn.endswith('.heiser'):
            filename = '{}/{}'.format(cache, fn)
            delta = (calendar.timegm(time.gmtime())
                - os.path.getmtime(filename) ) / 3600 / 24
            if delta > protected_days:
                log.debug('Removing cached item: ' + filename)
                os.remove(filename)

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
    replace_content(d.getroot(), session, cache=args.cache)
    remove_entries(d.getroot(), args.filter)
    ET.indent(d, space='    ')
    log.info('Writing augmented feed to: ' + args.output)
    d.write(args.output)

if __name__ == '__main__':
    sys.exit(main())
