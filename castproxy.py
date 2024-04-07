#!/usr/bin/env python3


# castproxy - aggregate and filter audiocasts (podcasts)
#
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: © 2024 Georg Sauthoff <mail@gms.tf>


import configargparse
import datetime
import dateutil.parser
import feedparser
import json
import logging
import os
import pycurl
try:
    import selinux
    HAVE_SELINUX = True
except ImportError:
    HAVE_SELINUX = False
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET


log = logging.getLogger(__name__)

ans = '{http://www.w3.org/2005/Atom}'


def parse_args():
    dcf = ('/usr/lib/castproxy/config.ini', '/etc/castproxy.ini',
           '/usr/local/etc/castproxy.ini', '~/.config/castproxy.ini')
    p = configargparse.ArgumentParser(default_config_files=dcf)
    p.add_argument('--feeds', '-f', help='feed configuration toml file')
    p.add_argument('--config', '-c', is_config_file=True, help='config file')
    p.add_argument('--url', default='https://example.org/podcast/feed.xml',
                   help='URL that serves the generated feed (default: %(default)s)')
    p.add_argument('--output', default='feed.xml',
                   help='output feed filename (default: %(default)s)')
    p.add_argument('--debug', '-d', action='store_true', help='print debug messages')
    p.add_argument('--verbose', '-v', action='store_true', help='print verbose messages')
    p.add_argument('--agent', '-a', default='interoffice/2.3', help='HTTP user agent (default: %(default)s')
    p.add_argument('--work', default='work', help='work directory where files are downloaded and state is kept (default: %(default)s)')
    p.add_argument('--title', default='Aggregated Audio', help='feed title (default: %(default)s)')
    p.add_argument('--media', default='media', help='media directory podcast files are moved (default: %(default)s)')

    args = p.parse_args()

    args.level = logging.WARNING
    if args.verbose:
        args.level = logging.INFO
    if args.debug:
        args.level = logging.DEBUG

    return args


def setup_logging(level):
    log_format      = '%(asctime)s - %(levelname)-8s - %(message)s [%(name)s]'
    log_date_format = '%Y-%m-%d %H:%M:%S'
    logging.basicConfig(format=log_format, datefmt=log_date_format, level=level)


def setup_curl(user_agent):
    global curl

    def check_size(d_total, d_n, u_total, u_n):
        limit = 2 * 1024 * 1024 * 1024
        if d_total > limit or d_n > limit:
            return 23 # abort

    curl = pycurl.Curl()
    curl.setopt(curl.USERAGENT       , user_agent)
    curl.setopt(curl.FOLLOWLOCATION  , True)
    curl.setopt(curl.NOPROGRESS      , False)
    curl.setopt(curl.XFERINFOFUNCTION, check_size)


def mk_filename(shortname, e, href):
    # we need to sanitize it since its remotely controlled input
    # that could be used for injecting things ...
    i = int(e.itunes_episode)
    k = href.rfind('?')
    if k != -1:
        href = href[:k]
    _, ext = os.path.splitext(href)
    if not ext:
        ext = '.mp3'
    s = f'{shortname}{i}{ext}'
    return s


def instantiate_cmd(cmd, h):
    return [ h.get(x, x) for x in cmd ]


def download(url, filename, tmp_dir, dl_dir):
    dst = f'{dl_dir}/{filename}'
    if os.path.exists(dst):
        log.debug(f'Skipping {url} - already present in {dst}') 
        return
    tmp = f'{tmp_dir}/{filename}'
    log.debug(f'Downloading {url} into {tmp} ...')
    with open(tmp, 'wb') as f:
        curl.setopt(curl.WRITEDATA, f)
        curl.setopt(curl.URL, url)
        curl.perform()
    code = curl.getinfo(curl.RESPONSE_CODE)
    if code != 200:
        os.unlink(tmp)
        raise RuntimeError(f'Downloading {url} failed: {code}')

    log.debug(f'Renaming {tmp} to {dst}') 
    os.rename(tmp, dst)


def post_process(filename, new_dir, cur_dir, filter_cmd):
    src = f'{new_dir}/{filename}'
    dst = f'{cur_dir}/{filename}'
    if os.path.exists(dst):
        log.debug(f'Skipping filtering {src} - {dst} already present') 
        return
    cmd = instantiate_cmd(filter_cmd, {'%src': src, '%dst': dst})
    log.debug(f'Filtering {src} to {dst} ({cmd})')
    with open(src + '.log', 'wb', buffering=0) as f:
        r = subprocess.run(cmd, stdout=f, stderr=f)
    if r.returncode != 0:
        log.debug(f'Filtering failed ({r.returncode}) - linking instead: {dst}')
        os.link(src, dst)


def obtain(url, filename, tmp_dir, new_dir, cur_dir, media_dir, filter_cmd=None):
    dl_dir = new_dir if filter_cmd else cur_dir
    
    download(url, filename, tmp_dir, dl_dir)

    if filter_cmd:
        post_process(filename, new_dir, cur_dir, filter_cmd)

    src = f'{cur_dir}/{filename}'
    dst = f'{media_dir}/{filename}'
    if not os.path.exists(dst):
        log.debug(f'Linking {src} -> {dst}')
        os.link(src, dst)
        # apparently, only newly created files inherit the label type of
        # the parent label, whereas a hardlink inherits from the label of
        # the link's source ...
        if HAVE_SELINUX:
            selinux.restorecon(dst)


def refresh_entry(e, shortname, tmp_dir, new_dir, cur_dir, media_dir, filter_cmd):
    if 'enclosures' not in e:
        return
    m = e.enclosures[0]
    if not m.type.startswith('audio'):
        return
    h = {}
    fn = mk_filename(shortname, e, m.href)
    obtain(m.href, fn, tmp_dir, new_dir, cur_dir, media_dir, filter_cmd)
    h['filename']  = fn
    h['alternate'] = [x for x in e.links if x.rel == 'alternate' and x.type.startswith('text')][0]
    h['title']     = e.title
    h['enclosure'] = m
    h['id']        = e.id
    h['published'] = e.published
    h['updated']   = e.updated
    h['episode']   = int(e.itunes_episode)
    return h

def refresh(name, shortname, url, limit, base_work_dir, media_dir, filter_cmd=None):
    log.info(f'Refreshing {name}: {shortname} <- {url} ...')

    work_dir = f'{base_work_dir}/{shortname}'
    tmp_dir = work_dir + '/tmp'
    new_dir = work_dir + '/new'
    cur_dir = work_dir + '/cur'
    for x in (tmp_dir, new_dir, cur_dir):
        os.makedirs(x, exist_ok=True)

    feed_state_fn = f'{work_dir}/state.json'
    if os.path.exists(feed_state_fn):
        with open(feed_state_fn) as f:
            state = json.load(f)
    else:
        state = {}

    paras = {}
    # prefer modified-since to work around buggy servers
    # such as LdN - who check etags incorrectly on compressed connections ...
    if 'modified' in state:
        paras['modified'] = state['modified']
    elif 'etag' in state:
        paras['etag'] = state['etag']

    d = feedparser.parse(url, **paras)
    if d.status == 304:
        log.debug(f'Skipping {shortname} because feed not modified')
        return False

    hs = []
    for e in d.entries[:limit]:
        h = refresh_entry(e, shortname, tmp_dir, new_dir, cur_dir, media_dir, filter_cmd)
        if h:
            hs.append(h)

    with open(f'{work_dir}/{shortname}.json', 'w') as f:
        json.dump(hs, f, indent=4)

    if 'etag' in d:
        state['etag'] = d.etag
    if 'modified' in d:
        state['modified'] = d.modified
    with open(feed_state_fn, 'w') as f:
        json.dump(state, f, indent=4)

    return True


def normalize_date(s):
    d = dateutil.parser.parse(s)
    return d.isoformat(timespec='seconds')


def mk_entries(shortname, url, base_work_dir):
    fn = f'{base_work_dir}/{shortname}/{shortname}.json'
    log.debug(f'Reading {fn} ...')
    with open(fn) as f:
        hs = json.load(f)
    es = []
    for h in hs:
        e = ET.Element(ans+'entry')
        ET.SubElement(e, ans+'id').text = h['id']
        ET.SubElement(e, ans+'title').text = h['title']
        ET.SubElement(e, ans+'updated').text = normalize_date(h['updated'])
        ET.SubElement(e, ans+'published').text = normalize_date(h['published'])
        episode = h['episode']
        ET.SubElement(e, ans+'content').text = f'Episode {episode}'
        ET.SubElement(e, ans+'link', rel='alternate', type=h['alternate']['type'], href=h['alternate']['href'])
        m = h['enclosure']
        fn = h['filename']
        # apparently, at least some podcast clients don't understand relative URLs in enclosures
        u = f'{url}/media/{fn}'
        ET.SubElement(e, ans+'link', rel='enclosure', type=m['type'], length=m['length'], href=u)
        es.append(e)
    return es


def mk_feed(url, title, shortnames, base_work_dir):
    feed = ET.Element(ans + 'feed')
    ET.SubElement(feed, ans+'title').text = title
    ET.SubElement(feed, ans+'id').text = url
    ET.SubElement(feed, ans+'updated').text = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
    for sn in shortnames:
        feed.extend(mk_entries(sn, url, base_work_dir))
    return ET.ElementTree(feed)



def main():
    args = parse_args()
    feedparser.USER_AGENT = args.agent
    setup_curl(args.agent)
    setup_logging(args.level)
    # make atom the default namespace for writing
    ET.register_namespace('', ans[1:-1])

    with open(args.feeds, 'rb') as f:
        feeds = tomllib.load(f)

    sns = []
    b = False
    for feed in feeds['feed']:
        a = refresh(feed['name'], feed['short'], feed['url'], feed['limit'], args.work, args.media, feed.get('filter'))
        b = b or a
        sns.append(feed['short'])

    if not b:
        log.info('No source feed changed - done')
        return

    d = mk_feed(args.url, args.title, sns, args.work)
    ET.indent(d, space='    ')
    tmp_output = args.output + '.tmp'
    d.write(tmp_output)
    log.info(f'Creating {args.output} ...')
    os.rename(tmp_output, args.output)


if __name__ == '__main__':
    sys.exit(main())



