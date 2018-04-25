FROM python:2.7-alpine

ADD . /src
WORKDIR /src
RUN pip install -r requirements.txt
RUN python setup.py develop
