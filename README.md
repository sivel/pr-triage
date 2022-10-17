# pr-triage

GitHub Pull Request Triage Assistant

## About

This application provides various reports of GitHub pull requests, so it's easy to identify pull requests that correspond to certain parts of an application, or that are submitted by certain authors.  It can also be used to identify pull requests
with merge conflicts that need revisions, so that authors can go back and resolve those conflicts.

In short, it simplifies running large, very active projects that use pull requests for contribution.

A demo is available at https://bobby285271.github.io/pr-triage/

## Installing

1. `git clone https://github.com/bobby285271/pr-triage.git`
1. `cd pr-triage`
1. `pip install -r requirements.txt`
1. Create a `triage.yaml` configuration file as described below

## triage.yaml

This file can live at `./triage.yaml`, `~/.triage.yaml`, or `/etc/triage.yaml`

```yaml
---
# Required Configuration
title: Nixpkgs Pull Request Triage
github_repository:
  - "NixOS/nixpkgs"
```

### GitHub credentials

You will need a GitHub token as an environment variable `GITHUB_TOKEN`.

## Hosting

`triage.py` will write out HTML files to a directory called `docs`. You can
host these files directly out of that directory using a webserver such as
Apache or nginx.

## Running

It is recommended that you run `triage.py` via cron. The fewer pull requests a
project has the more frequently you can run the cron job. I'd recommend
starting with every 60 minutes (1 hour).
