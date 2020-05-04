#!/usr/bin/env python3

import datetime
import dateutil.relativedelta
import flask
import os
import random
import tarfile

app = flask.Flask(__name__)

EPOCH = datetime.date(2012, 11, 16)

@app.route('/')
def hello_world():
    today = datetime.date.today()
    return flask.redirect(today.strftime('/%Y/%m/%d'))

@app.route('/<int:year>/<int:month>/<int:day>')
def get_date(year, month, day):
    date = datetime.date(year, month, day)
    observations = parse_observations(get_observations(date))
    categories = set(observations.keys())

    def jumplink(text, **kwargs):
        if kwargs.get('today'):
            new_date = datetime.date.today()
        elif kwargs.get('random'):
            total_days = (datetime.date.today() - EPOCH).days
            offset = dateutil.relativedelta.relativedelta(
                days = random.randint(0, total_days)
            )

            print(total_days, offset)
            new_date = EPOCH + offset

        else:
            new_date = date + dateutil.relativedelta.relativedelta(**kwargs)

        return '<a class="button" href="{link}">{text}</a>'.format(
            link = new_date.strftime('/%Y/%m/%d'),
            text = text
        )

    return flask.render_template(
        'daily.html',
        date = date,
        categories = categories,
        entries = observations,
        jumplink = jumplink
    )

def parse_observations(data):
    category = None
    entries = {}

    if not data:
        return entries

    for line in data.split('\n'):
        line = line.strip()
        if not line: continue

        if line.endswith(':') and not line.startswith('-'):
            category = line
            if not category in entries:
                entries[category] = []
            continue

        elif line.startswith('-'):
            line = line.lstrip('-').strip()
            if not line: continue

            entries[category].append([line])

        else:
            if entries[category]:
                entries[category][-1].append(line)
            else:
                entries[category].append([line])

    for category in list(entries.keys()):
        if not entries[category]:
            del entries[category]

        elif len(entries[category]) == 1 and 'backfill' in entries[category][0][0].lower():
            del entries[category]

        elif 'memorable' in category.lower():
            del entries[category]

        elif 'things i learned' in category.lower():
            del entries[category]

        elif 'exercise' in category.lower():
            del entries[category]

    return entries

def get_observations(date):
    ymstr = date.strftime('%Y-%m')
    datestr = date.strftime('%Y-%m-%d.txt')

    # File exists directly
    path = os.path.join('data', ymstr, datestr)
    if os.path.exists(path):
        with open(path, 'r') as fin:
            return fin.read()

    # Check for an archive
    path = os.path.join('data', date.strftime('%Y.tgz'))
    if os.path.exists(path):
        with tarfile.open(path, 'r') as tf:
            for ti in tf.getmembers():
                # Skip mac files
                if '._' in ti.name:
                    continue

                # We found the date we were looking for 
                if ti.name.endswith(datestr):
                    with tf.extractfile(ti) as fin:
                        return fin.read().decode('utf-8', 'replace')

                # We found a nested tarball with the month
                elif ymstr in ti.name and ti.name.endswith('tgz'):
                    logging.warning('Deal with nested tarballs')
                    raise NotImplemented

if __name__ == '__main__':
    app.run(host = '0.0.0.0', debug = False)