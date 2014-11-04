#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright 2014 Matt Martz
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import os
import re
import yaml
import jinja2

from github import Github
from datetime import datetime
from collections import defaultdict, OrderedDict

try:
    import pyrax
    HAS_PYRAX = True
except ImportError:
    HAS_PYRAX = False


def get_config():
    config_files = [
        './triage.yaml',
        os.path.expanduser('~/.triage.yaml'),
        '/etc/triage.yaml'
    ]
    for config_file in config_files:
        try:
            with open(os.path.realpath(config_file)) as f:
                config = yaml.load(f)
        except:
            pass
        else:
            return config

    raise SystemExit('Config file not found at: %s' % ', '.join(config_files))


def scan_issues(config):
    merge_commit = re.compile("Merge branch \S+ into ", flags=re.I)

    files = defaultdict(list)
    users = defaultdict(list)
    conflicts = defaultdict(list)
    merges = defaultdict(list)
    multi_author = defaultdict(list)

    g = Github(client_id=config['github_client_id'],
               client_secret=config['github_client_secret'],
               per_page=100)

    if not isinstance(config['github_repository'], list):
        repos = [config['github_repository']]
    else:
        repos = config['github_repository']

    for repo_name in repos:
        repo = g.get_repo(repo_name)

        for pull in repo.get_pulls():
            if pull.user is None:
                login = pull.head.user.login
            else:
                login = pull.user.login

            users[login].append(pull)

            if pull.mergeable is False or pull.mergeable_state == 'dirty':
                conflicts[login].append(pull)

            for pull_file in pull.get_files():
                files[pull_file.filename].append(pull)

            authors = set()
            for commit in pull.get_commits():
                authors.add(commit.commit.author.email)
                try:
                    if merge_commit.match(commit.commit.message):
                        merges[login].append(pull)
                        break
                except TypeError:
                    pass

            if len(authors) > 1:
                multi_author[login].append(pull)

    usersbypulls = OrderedDict()
    for user, pulls in sorted(users.items(),
                              key=lambda t: len(t[-1]), reverse=True):
        usersbypulls[user] = pulls

    return config, files, usersbypulls, merges, conflicts, multi_author


def write_html(config, files, users, merges, conflicts, multi_author):
    if config.get('use_rackspace', False):
        if not HAS_PYRAX:
            raise SystemExit('The pyrax python module is required to use '
                             'Rackspace CloudFiles')
        pyrax.set_setting('identity_type', 'rackspace')
        credentials = os.path.expanduser(config['pyrax_credentials'])
        pyrax.set_credential_file(credentials, region=config['pyrax_region'])
        cf = pyrax.cloudfiles
        cont = cf.get_container(config['pyrax_container'])

    os.chdir(os.path.dirname(os.path.realpath(__file__)))
    loader = jinja2.FileSystemLoader('templates')
    environment = jinja2.Environment(loader=loader, trim_blocks=True)

    if not os.path.isdir('htmlout'):
        os.makedirs('htmlout')

    templates = ['index', 'byfile', 'byuser', 'bymergecommits',
                 'byconflict', 'bymultiauthor']

    for tmplfile in templates:
        now = datetime.utcnow()
        classes = {}
        for t in templates:
            classes['%s_classes' % t] = 'active' if tmplfile == t else ''

        template = environment.get_template('%s.html' % tmplfile)
        rendered = template.render(files=files, users=users, merges=merges,
                                   conflicts=conflicts,
                                   multi_author=multi_author,
                                   title=config['title'],
                                   now=now, **classes)

        with open('htmlout/%s.html' % tmplfile, 'w+b') as f:
            f.write(rendered)

        if config.get('use_rackspace', False):
            obj = cont.upload_file('htmlout/%s.html' % tmplfile,
                                   obj_name='%s.html' % tmplfile,
                                   content_type='text/html')


if __name__ == '__main__':
    write_html(*scan_issues(get_config()))
