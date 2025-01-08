FROM python:3.12-slim-bullseye

ENV DOTNET_CLI_HOME=/tmp/dotnet \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    sudo \
    git \
    lsb-release \
    gnupg2 \
    curl \
    apt-transport-https \
    wget \
    patch \
    openjdk-17-jre \
  && apt-get clean && rm -rf /var/lib/apt/lists/* \
  && wget https://packages.microsoft.com/config/debian/11/packages-microsoft-prod.deb \
  && dpkg -i packages-microsoft-prod.deb \
  && rm packages-microsoft-prod.deb \
  && apt-get update \
  && apt-get install -y --no-install-recommends dotnet-sdk-8.0 \
  && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN chmod 1777 /usr/local/bin \
  && mkdir -p /tmp/dotnet && chmod -R 1777 /tmp/dotnet

COPY requirements.txt requirements.txt
RUN python -m pip install --upgrade pip \
  && pip install --no-cache-dir -r requirements.txt \
  && rm -rf ~/.cache/pip