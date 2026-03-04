FROM python:3-buster

EXPOSE 8000
VOLUME /app/data
WORKDIR /app

RUN pip install uv
ADD pyproject.toml uv.lock ./
RUN uv sync --frozen

ADD . .

CMD .venv/bin/python observations.py
