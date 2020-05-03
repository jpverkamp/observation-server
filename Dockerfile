FROM python:3

EXPOSE 5000
VOLUME /app/data
WORKDIR /app

ADD requirements.txt .
RUN pip3 install -U pip && pip install -r requirements.txt

ADD . .

CMD python3 observations.py