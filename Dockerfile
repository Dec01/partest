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
# Not `-r requirements.txt`: since 2.1.0 that file is the audit target (what a consumer
# gets from `pip install partest`), not an environment. It installs neither the package
# itself nor the plugins `pytest.ini` demands, so `pytest` below would die on `--reruns=2`
# before collecting anything.
RUN pip3 install -e ".[dev]"

CMD pytest --domain "$domain" -m "$env" --verbose -o junit_family=xunit2 --junitxml=reports\\pytest\\result.xml -s src/tests/*