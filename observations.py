#!/usr/bin/env python3

import coloredlogs
import datetime
from zoneinfo import ZoneInfo
import dateutil.relativedelta
import hashlib
import humanize
import logging
import flask
import os
import random
import re
import sys
import tarfile
import yaml

if '--debug' in sys.argv:
    coloredlogs.install(level=logging.INFO)

app = flask.Flask(__name__)
app.jinja_env.globals['hash'] = lambda el: hashlib.md5(str(el).encode()).hexdigest()

# Timezone configuration: set TZ environment variable to your timezone (e.g., 'America/Denver')
# Defaults to UTC if not set. Full list: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
TIMEZONE_STR = os.environ.get("TZ", "UTC")
try:
    TIMEZONE = ZoneInfo(TIMEZONE_STR)
except Exception as e:
    logging.warning(f"Invalid timezone {TIMEZONE_STR}: {e}; falling back to UTC")
    TIMEZONE = ZoneInfo("UTC")


def get_today():
    """Get today's date in the configured timezone."""
    return datetime.datetime.now(tz=TIMEZONE).date()


EPOCH = datetime.date(2012, 11, 16)
FAVORITES_FILE = os.path.join('data', 'favorites.yaml')
FAVORITES = {}

if os.path.exists(FAVORITES_FILE):
    with open(FAVORITES_FILE) as fin:
        FAVORITES = yaml.safe_load(fin) or {}


def random_date():
    total_days = (get_today() - EPOCH).days
    offset = dateutil.relativedelta.relativedelta(
        days=random.randint(0, total_days)
    )
    return EPOCH + offset


@app.route("/")
@app.route("/today", methods=["GET", "POST"])
def today():
    logging.info(f'today()')
    date = get_today()

    if flask.request.method == "POST":
        return get_date(date.year, date.month, date.day)

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


@app.route("/<int:year>/<int:month>/<int:day>", methods=["GET", "POST"])
def get_date(year, month, day):
    logging.info(f'get_date({year=}, {month=}, {day=})')

    if flask.request.method == "POST":
        params = flask.request.get_json(silent=True)
        if not params:
            params = flask.request.form.to_dict()

        if not params:
            return flask.jsonify({"error": "Expected a POST body"}), 400

        if "todo_index" in params:
            update = {
                "todo_index": params.get("todo_index"),
                "checked": params.get("checked"),
            }
        elif "text" in params:
            update = {"text": params.get("text")}
        elif len(params) == 1:
            update = {"text": next(iter(params.values()))}
        else:
            return (
                flask.jsonify({"error": "Expected a text update or todo_index update"}),
                400,
            )

        result, status = update_date(year, month, day, update)
        return flask.jsonify(result), status

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
            new_date = get_today()
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
        "daily.html",
        date=date,
        offset=lambda date: humanize.naturaldelta(get_today() - date),
        data=data,
        jumplink=jumplink,
        is_favorite=is_favorite,
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


def update_date(year, month, day, update):
    date = datetime.date(year, month, day)
    month_dir = os.path.join("data", date.strftime("%Y-%m"))
    os.makedirs(month_dir, exist_ok=True)

    path = os.path.join(month_dir, date.strftime("%Y-%m-%d.md"))
    if not os.path.exists(path):
        template_path = os.path.join("data", "template.md")
        if os.path.exists(template_path):
            with open(template_path) as fin:
                seed = fin.read().rstrip() + "\n"
        else:
            seed = ""

        with open(path, "w") as fout:
            fout.write(seed)

    with open(path) as fin:
        content = fin.read()

    def section_level(line):
        return len(line) - len(line.lstrip("#"))

    def find_section_bounds(lines, heading):
        heading_lower = heading.strip().lower()

        for i, line in enumerate(lines):
            if line.strip().lower() == heading_lower:
                level = section_level(line)
                end = len(lines)

                for j in range(i + 1, len(lines)):
                    stripped = lines[j].lstrip()
                    if stripped.startswith("#") and section_level(lines[j]) <= level:
                        end = j
                        break

                return i, end, level

        return None, None, None

    def section_children(lines, heading):
        start, end, level = find_section_bounds(lines, heading)
        if start is None:
            return []

        children = []
        for line in lines[start + 1 : end]:
            stripped = line.strip()
            if stripped.startswith("#") and section_level(stripped) == level + 1:
                children.append(stripped.lstrip("#").strip())

        return children

    def mentions_name(text, name):
        text = text.lower()
        tokens = [token.strip().lower() for token in name.split() if token.strip()]
        aliases = set(tokens)
        aliases.add(name.lower())

        for alias in aliases:
            if re.search(rf"\b{re.escape(alias)}\b", text):
                return True

        return False

    def classify_observation(raw_text):
        text = (raw_text or "").strip()
        if not text:
            raise ValueError("No observation text provided")

        template_lines = []
        template_path = os.path.join("data", "template.md")
        if os.path.exists(template_path):
            with open(template_path) as fin:
                template_lines = fin.read().splitlines()

        current_lines = content.splitlines()
        child_names = section_children(
            template_lines, "# Stories about the children"
        ) or section_children(current_lines, "# Stories about the children")
        cat_names = section_children(
            template_lines, "# Stories about cats"
        ) or section_children(current_lines, "# Stories about cats")

        child_map = {}
        for name in child_names:
            if name:
                first = name[0].lower()
                if first in ["a", "e", "i", "o"] and first not in child_map:
                    child_map[first] = name

        if "z" not in child_map:
            izzy_match = next(
                (name for name in child_names if name and name[0].lower() == "i"), None
            )
            if izzy_match:
                child_map["z"] = izzy_match

        explicit = re.search(r"(^|\s)([aezio]):", text, re.IGNORECASE)
        if explicit:
            initial = explicit.group(2).lower()
            if initial in child_map:
                text = re.sub(r"(^|\s)[aezio]:", " ", text, flags=re.IGNORECASE)
                text = re.sub(r"\s+", " ", text).strip()
                return f"## {child_map[initial]}", text

        matched_children = [name for name in child_names if mentions_name(text, name)]
        matched_cats = [name for name in cat_names if mentions_name(text, name)]

        if len(matched_children) > 1:
            return "# Stories about the children", text
        if len(matched_children) == 1:
            return f"## {matched_children[0]}", text

        if len(matched_cats) > 1:
            return "# Stories about cats", text
        if len(matched_cats) == 1:
            return f"## {matched_cats[0]}", text

        text_lower = text.lower()
        if re.match(r"^\[\s*[xX ]?\s*\]", text) or "todo" in text_lower:
            if not re.match(r"^\[\s*[xX ]\s*\]", text):
                text = f"[ ] {text}"
            return "# TODOs", text

        if re.search(r"\btil\b", text, re.IGNORECASE):
            return "# Today I learned", text

        if re.search(r"(^|\s)#work\b", text, re.IGNORECASE):
            text = re.sub(r"(^|\s)#work\b", " ", text, flags=re.IGNORECASE)
            text = re.sub(r"\s+", " ", text).strip()
            return "## At work", text

        if re.search(r"(^|\s)#home\b", text, re.IGNORECASE):
            text = re.sub(r"(^|\s)#home\b", " ", text, flags=re.IGNORECASE)
            text = re.sub(r"\s+", " ", text).strip()
            return "## Not at work", text

        return "# Something worth doing", text

    def append_markdown_item(heading, text):
        lines = content.splitlines()
        item = f"- {text.strip()}"

        start, end, level = find_section_bounds(lines, heading)
        if start is None:
            if lines and lines[-1].strip():
                lines.append("")
            lines.extend([heading, "", item])
            return "\n".join(lines).rstrip() + "\n"

        insert_at = end
        for i in range(start + 1, end):
            stripped = lines[i].strip()
            if stripped.startswith("#") and section_level(stripped) > level:
                insert_at = i
                break

        while insert_at > start + 1 and not lines[insert_at - 1].strip():
            insert_at -= 1

        lines.insert(insert_at, item)
        return "\n".join(lines).rstrip() + "\n"

    def set_todo_state(todo_index, checked):
        lines = content.splitlines()
        start, end, _ = find_section_bounds(lines, "# TODOs")
        if start is None:
            return None, {"error": "No TODO section found"}, 400

        todo_lines = []
        for i in range(start + 1, end):
            stripped = lines[i].strip()
            if stripped.startswith("-"):
                todo_lines.append(i)

        if todo_index < 0 or todo_index >= len(todo_lines):
            return None, {"error": "TODO index out of range"}, 400

        line_index = todo_lines[todo_index]
        line = lines[line_index]
        indent = line[: len(line) - len(line.lstrip())]
        body = line.strip().lstrip("-").strip()

        current_checked = bool(re.match(r"^\[\s*[xX]\s*\]", body))
        if checked is None:
            checked = not current_checked

        text_body = re.sub(r"^\[\s*[xX ]\s*\]\s*", "", body).strip()
        marker = "[x]" if checked else "[ ]"
        lines[line_index] = f"{indent}- {marker} {text_body}".rstrip()

        return (
            "\n".join(lines).rstrip() + "\n",
            {
                "status": "ok",
                "date": str(date),
                "path": path,
                "todo_index": todo_index,
                "checked": checked,
                "item": lines[line_index].strip(),
            },
            200,
        )

    if not isinstance(update, dict):
        return {"error": "Invalid update payload"}, 400

    if "todo_index" in update:
        try:
            todo_index = int(update.get("todo_index"))
        except (TypeError, ValueError):
            return {"error": "todo_index must be an integer"}, 400

        checked = update.get("checked")
        if isinstance(checked, str):
            lowered = checked.strip().lower()
            if lowered in ["true", "1", "yes", "on"]:
                checked = True
            elif lowered in ["false", "0", "no", "off"]:
                checked = False
            elif lowered in ["", "toggle", "none", "null"]:
                checked = None
            else:
                return {"error": "checked must be boolean-like"}, 400

        if checked not in [True, False, None]:
            return {"error": "checked must be true, false, or omitted"}, 400

        updated_content, response, status = set_todo_state(todo_index, checked)
        if status != 200:
            return response, status

        with open(path, "w") as fout:
            fout.write(updated_content)

        return response, status

    raw_text = update.get("text")
    if raw_text is None:
        return {"error": "Expected text for observation update"}, 400

    try:
        heading, cleaned = classify_observation(raw_text)
    except ValueError as ex:
        return {"error": str(ex)}, 400

    updated_content = append_markdown_item(heading, cleaned)

    with open(path, "w") as fout:
        fout.write(updated_content)

    return {
        "status": "ok",
        "date": str(date),
        "path": path,
        "section": heading,
        "item": f"- {cleaned}",
    }, 200


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
    port = int(os.environ.get("PORT", 8000))

    app.run(host="0.0.0.0", port=port, debug="--debug" in sys.argv)
