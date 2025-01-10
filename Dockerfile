FROM python:3.10-alpine

ARG run_env
ARG run_domain
ENV env $run_env
ENV domain $run_domain

LABEL "channel"="Test"
LABEL "Creator"="Test"

WORKDIR ./usr/corp-test-stable
COPY . .

RUN apk update && apk upgrade && apk add bash
RUN pip3 install -r requirements.txt

CMD pytest --domain "$domain" -m "$env" --verbose -o junit_family=xunit2 --junitxml=reports\\pytest\\result.xml -s src/tests/*