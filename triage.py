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
import logging
import jinja2
import cPickle

import pprint
pp = pprint.pprint

from github import Github
from datetime import datetime
from collections import defaultdict, OrderedDict

try:
    import pyrax
    HAS_PYRAX = True
except ImportError:
    HAS_PYRAX = False

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


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

def repo_config(config):
    if not isinstance(config['github_repository'], list):
        repos = [config['github_repository']]
    else:
        repos = config['github_repository']
    return repos

def get_data_path(config):
    repos = repo_config(config)
    data_dir_path = config.get('data_path', 'data/')
    data_file_name = '-'.join(repos).replace('/','_') + '.pickle'
    if not os.path.exists(data_dir_path):
        log.warning('The data_path \"%s\" did not exist. Creating it now.', data_dir_path)
        os.makedirs(data_dir_path)
    data_path = os.path.join(data_dir_path, data_file_name)
    return data_path

def scan_issues(config):
    merge_commit = re.compile("Merge branch \S+ into ", flags=re.I)

    files = defaultdict(list)
    dirs = defaultdict(set)
    users = defaultdict(list)
    conflicts = defaultdict(list)
    ci_failures = defaultdict(list)
    merges = defaultdict(list)
    multi_author = defaultdict(list)

    g = Github(client_id=config['github_client_id'],
               client_secret=config['github_client_secret'],
               per_page=100)

    repos = repo_config(config)

    for repo_name in repos:
        log.info('Scanning repo: %s', repo_name)
        repo = g.get_repo(repo_name)

        prs = repo.get_pulls()
        for pull in prs:
            log.info('pull.id: %s', pull.id)
            if pull.user is None:
                login = pull.head.user.login
            else:
                login = pull.user.login

            users[login].append(pull)

            if pull.mergeable is False or pull.mergeable_state == 'dirty':
                conflicts[login].append(pull)

            if pull.mergeable_state == 'unstable':
                ci_failures[login].append(pull)

            for pull_file in pull.get_files():
                files[pull_file.filename].append(pull)
                dirs[os.path.dirname(pull_file.filename)].add(pull)

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

            log.info('Saving data snapshot')
            snapshot = [config, files, merges, conflicts, multi_author, ci_failures, prs, dirs]
            with open('data/snapshot.pickle', 'w') as f:
                cPickle.dump(snapshot, f)

    usersbypulls = OrderedDict()
    for user, pulls in sorted(users.items(),
                              key=lambda t: len(t[-1]), reverse=True):
        usersbypulls[user] = pulls

    a = [config, files, usersbypulls, merges, conflicts, multi_author, ci_failures, prs, dirs]

    data_file_name = get_data_path(config)
    log.info('saving data to %s', data_file_name)

    with open(data_file_name, 'w') as f:
        cPickle.dump(a, f)

    return (config, files, usersbypulls, merges, conflicts, multi_author,
            ci_failures, prs, dirs)


def write_html(config, files, users, merges, conflicts, multi_author,
               ci_failures, prs, dirs):
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
    # TODO: make template/htmlout configurable
    loader = jinja2.FileSystemLoader('templates')
    environment = jinja2.Environment(loader=loader, trim_blocks=True)

    if not os.path.isdir('htmlout'):
        os.makedirs('htmlout')

    templates = ['index', 'byfile', 'bydir', 'byuser', 'bymergecommits',
                 'byconflict', 'bymultiauthor', 'bycifailures']

    for tmplfile in templates:
        now = datetime.utcnow()
        classes = {}
        for t in templates:
            classes['%s_classes' % t] = 'active' if tmplfile == t else ''

        template = environment.get_template('%s.html' % tmplfile)
        rendered = template.render(files=files, dirs=dirs, users=users,
                                   merges=merges, conflicts=conflicts,
                                   multi_author=multi_author,
                                   ci_failures=ci_failures,
                                   title=config['title'],
                                   now=now, **classes)

        with open('htmlout/%s.html' % tmplfile, 'w+b') as f:
            f.write(rendered.encode('ascii', 'ignore'))

        if config.get('use_rackspace', False):
            cont.upload_file('htmlout/%s.html' % tmplfile,
                             obj_name='%s.html' % tmplfile,
                             content_type='text/html')


if __name__ == '__main__':
    import sys

    config = get_config()

    if '--cached' in sys.argv:
        log.info('using cached data')
        data_file_name = get_data_path(config)
        with open(data_file_name, 'r') as f:
            data = cPickle.load(f)
        log.info('loaded cached data')
    else:
        data = scan_issues(get_config())

    #files = data[1]
    #pp(files)
    #pp(files,collapse_duplicates=True)

    #for file_path,value in files.items():
    #    pp(file_path)
    #    print(value)

    write_html(*data)
