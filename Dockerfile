# syntax=docker/dockerfile:1

# Comments are provided throughout this file to help you get started.
# If you need more help, visit the Dockerfile reference guide at
# https://docs.docker.com/go/dockerfile-reference/

# Want to help us make this template better? Share your feedback here: https://forms.gle/ybq9Krt8jtBL3iCk7

# This Dockerfile uses Docker Hardened Images (DHI) for enhanced security.
# For more information, see https://docs.docker.com/dhi/
ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim


RUN mkdir /app
COPY *.py /app
COPY *.sh /app
COPY utility /app/utility
COPY web /app/web

COPY requirements.txt /requirements.txt

# Download dependencies as a separate step to take advantage of Docker's caching.
# Leverage a cache mount to /root/.cache/pip to speed up subsequent builds.
# Leverage a bind mount to requirements.txt to avoid having to copy them into
# into this layer.
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,source=requirements.txt,target=requirements.txt \
    python -m pip install -r requirements.txt

ENV PATH="/app:${PATH}"

# RUN python3 -m pip install --no-cache-dir  \
#     --trusted-host engci-maven-master.cisco.com \
#     --extra-index-url http://engci-maven-master.cisco.com/artifactory/api/pypi/mig-optical-pypi/simple \
#     ciscotdrpy==3.1.5

WORKDIR /app

CMD ["start_web_app.sh"]
#CMD ["ls", "-la", "/app"]
