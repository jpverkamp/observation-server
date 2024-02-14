#!/usr/bin/env python3

import coloredlogs
import datetime
import dateutil.relativedelta
import hashlib
import humanize
import logging
import flask
import os
import random
import sys
import tarfile
import yaml

if '--debug' in sys.argv:
    coloredlogs.install(level=logging.INFO)

app = flask.Flask(__name__)
app.jinja_env.globals['hash'] = lambda el: hashlib.md5(str(el).encode()).hexdigest()

EPOCH = datetime.date(2012, 11, 16)
FAVORITES_FILE = os.path.join('data', 'favorites.yaml')
FAVORITES = {}

if os.path.exists(FAVORITES_FILE):
    with open(FAVORITES_FILE) as fin:
        FAVORITES = yaml.safe_load(fin) or {}


def random_date():
    total_days = (datetime.date.today() - EPOCH).days
    offset = dateutil.relativedelta.relativedelta(
        days=random.randint(0, total_days)
    )
    return EPOCH + offset


@app.route('/')
@app.route('/today')
def today():
    logging.info(f'today()')
    date = datetime.date.today()
    return get_date(date.year, date.month, date.day)


@app.route('/random')
def get_random():
    logging.info(f'get_random()')
    date = random_date()
    return get_date(date.year, date.month, date.day)


@app.route('/favorites', methods=['GET', 'POST'])
def favorite():
    logging.info(f'favorite()')
    global FAVORITES

    if flask.request.method == 'GET':
        return flask.render_template('favorites.html', favorites=FAVORITES)

    elif flask.request.method == 'POST':
        params = flask.request.get_json()
        date = params.get('date')
        hash = params.get('hash')
        text = params.get('text')

        if FAVORITES.get(date, {}).get(hash):
            del FAVORITES[date][hash]

            if not FAVORITES[date]:
                del FAVORITES[date]
        else:
            if not date in FAVORITES:
                FAVORITES[date] = {}

            FAVORITES[date][hash] = text

        with open(FAVORITES_FILE, 'w') as fout:
            yaml.dump(FAVORITES, fout, default_flow_style=False)

        return 'ok'


@app.route('/<int:year>/<int:month>/<int:day>')
def get_date(year, month, day):
    logging.info(f'get_date({year=}, {month=}, {day=})')

    date = datetime.date(year, month, day)
    data = {}

    while date > EPOCH:
        observations = parse_observations(get_observations(date), include_all='all' in flask.request.args)
        categories = set(observations.keys())
        data[date] = {'observations': observations, 'categories': categories}

        if 'history' in flask.request.args:
            date = date + dateutil.relativedelta.relativedelta(years=-1)
        else:
            break

    def jumplink(text, **kwargs):
        if kwargs.get('today'):
            new_date = datetime.date.today()
        elif kwargs.get('random'):
            new_date = random_date()
        else:
            new_date = date + dateutil.relativedelta.relativedelta(**kwargs)

        return '<a class="button" href="{link}">{text}</a>'.format(
            link=new_date.strftime('/%Y/%m/%d'),
            text=text
        )

    def is_favorite(hash):
        return bool(FAVORITES.get(str(date), {}).get(hash))

    return flask.render_template(
        'daily.html',
        date=date,
        offset=lambda date: humanize.naturaldelta(datetime.date.today() - date),
        data=data,
        jumplink=jumplink,
        is_favorite=is_favorite
    )


def parse_observations(data, include_all=False):
    logging.info(f'parse_observations({data=}, {include_all=})')

    data = data or ''
    md_mode = data.strip().startswith('#')

    category_tree = []
    category = 'none'
    entries = {'none': []}
    first_line = True
    previous_blank = False

    if not data:
        return entries

    for line in data.split('\n'):
        line = line.rstrip()
        if not line:
            previous_blank = True
            continue

        if md_mode and line.startswith('#'):
            depth = len(line) - len(line.lstrip('#')) - 1
            category_tree = category_tree[:depth] + [line.lstrip('#').lstrip()]
            category = ' -- '.join(category_tree)

            if not category in entries:
                entries[category] = []

        elif not md_mode and line.endswith(':') and not line.startswith('-') and (previous_blank or first_line):
            category = line
            if not category in entries:
                entries[category] = []
            continue

        elif line.startswith('-'):
            line = line.lstrip('-').strip()
            if not line:
                previous_blank = False
                continue

            entries[category].append([line])

        else:
            if entries[category]:
                entries[category][-1].append(line)
            else:
                entries[category].append([line])

        previous_blank = False
        first_line = False

    for category in list(entries.keys()):
        if not entries[category]:
            del entries[category]

        elif len(entries[category]) == 1 and 'backfill' in entries[category][0][0].lower():
            del entries[category]

        elif 'memorable' in category.lower() and not include_all:
            del entries[category]

        elif 'interesting people' in category.lower() and not include_all:
            del entries[category]

        elif 'things i learned' in category.lower() and not include_all:
            del entries[category]

        elif 'exercise' in category.lower() and not include_all:
            del entries[category]

    return entries


def get_observations(date):
    logging.info(f'get_obserations({date=})')

    ymstr = date.strftime('%Y-%m')
    datestrs = [
        date.strftime('%Y-%m-%d.txt'),
        date.strftime('%Y-%m-%d.md')
    ]
    
    for datestr in datestrs:
        # File exists directly as txt
        path = os.path.join('data', ymstr, datestr)
        if os.path.exists(path):
            with open(path, 'rb') as fin:
                logging.info(f'Loaded local file: {path}')
                return fin.read().decode('utf-8', 'replace')
        else:
            logging.info(f'{path} does not exist')

        # Check for an archive
        path = os.path.join('data', date.strftime('%Y.tgz'))
        if os.path.exists(path):
            logging.info(f'Tarball exists: {path}')

            with tarfile.open(path, 'r') as tf:
                for ti in tf.getmembers():
                    # Skip mac files
                    if '._' in ti.name:
                        continue

                    # We found the date we were looking for
                    if ti.name.endswith(datestr):
                        logging.info(f'Loaded nested file: {ti.name} in {path}')
                        with tf.extractfile(ti) as fin:
                            return fin.read().decode('utf-8', 'replace')

                    # We found a nested tarball with the month
                    elif ymstr in ti.name and ti.name.endswith('tgz'):
                        print('Deal with nested tarballs')
                        raise NotImplemented
        else:
            logging.info(f'{path} does not exist')


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug='--debug' in sys.argv)
