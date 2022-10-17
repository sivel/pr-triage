#!/usr/bin/env python3
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
import sys
import time
import yaml
import jinja2

from github import Github
from datetime import datetime
from collections import defaultdict, OrderedDict


def get_token():
    token = os.getenv("TOKEN_GITHUB")
    if not token:
        token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("Missing GitHub token")
        sys.exit(1)
    return token


def get_config():
    config_files = [
        './triage.yaml',
        os.path.expanduser('~/.triage.yaml'),
        '/etc/triage.yaml'
    ]
    for config_file in config_files:
        try:
            with open(os.path.realpath(config_file)) as f:
                config = yaml.load(f, Loader=yaml.SafeLoader)
        except:
            pass
        else:
            return config

    raise SystemExit('Config file not found at: %s' % ', '.join(config_files))


def ensure_rate_limit(g):
    if g.rate_limiting[0] < 100:
        r = g.get_rate_limit()
        delta = r.core.reset - datetime.utcnow()
        print('SLEEP: %s' % (delta.total_seconds() + 10))
        time.sleep(delta.total_seconds() + 10)


def scan_issues(config):
    files = defaultdict(list)
    users = defaultdict(list)
    conflicts = defaultdict(list)
    merges = defaultdict(list)
    multi_authors = defaultdict(list)
    approvals = defaultdict(list)

    g = Github(get_token())

    if not isinstance(config['github_repository'], list):
        repos = [config['github_repository']]
    else:
        repos = config['github_repository']

    for repo_name in repos:
        ensure_rate_limit(g)

        while 1:
            try:
                repo = g.get_repo(repo_name)
            except Exception as e:
                print('ERROR: %s' % e)
                print('SLEEP')
                time.sleep(5)
            else:
                break

        print(repo)

        while 1:
            try:
                pull_list = list(repo.get_pulls(
                    state='open', sort='updated', direction='desc'))
            except Exception as e:
                print('ERROR: %s' % e)
                print('SLEEP')
                time.sleep(5)
            else:
                break

        counter = 0
        for pull in pull_list:
            ensure_rate_limit(g)
            if pull.user is None:
                login = pull.head.user.login
            else:
                login = pull.user.login

            users[login].append(pull)

            while 1:
                try:
                    mergeable = pull.mergeable
                except Exception as e:
                    print('ERROR: %s' % e)
                    print('SLEEP')
                    time.sleep(5)
                else:
                    break
            if mergeable is False:
                conflicts[login].append(pull)

            while 1:
                try:
                    file_list = list(pull.get_files())
                except Exception as e:
                    print('ERROR: %s' % e)
                    print('SLEEP')
                    time.sleep(5)
                else:
                    break
            if len(file_list) >= 10:
                files['* - Touches more than 10 files'].append(pull)
            else:
                for pull_file in file_list:
                    files[pull_file.filename].append(pull)

            authors = set()
            while 1:
                try:
                    commit_list = list(pull.get_commits())
                except Exception as e:
                    print('ERROR: %s' % e)
                    print('SLEEP')
                    time.sleep(5)
                else:
                    break

            for commit in commit_list:
                authors.add(commit.commit.author.email)

            for commit in commit_list:
                try:
                    if len(commit.commit.parents) > 1:
                        merges[login].append(pull)
                        break
                except TypeError:
                    pass

            if len(authors) > 1:
                multi_authors[login].append(pull)

            while 1:
                try:
                    review_list = list(pull.get_reviews())
                except Exception as e:
                    print('ERROR: %s' % e)
                    print('SLEEP')
                    time.sleep(5)
                else:
                    break

            approvers = dict()
            for review in review_list:
                if review.state == "APPROVED":
                    approvers[review.user] = review
                else:
                    try:
                        del approvers[review.user]
                    except KeyError:
                        pass

            approvals[f"Approvals: {len(approvers)}"].append(pull)

            counter += 1
            if counter >= 500:
                break

    usersbypulls = OrderedDict()
    for user, pulls in sorted(users.items(),
                              key=lambda t: len(t[-1]), reverse=True):
        usersbypulls[user] = pulls

    return (config, files, usersbypulls, merges, conflicts, multi_authors, approvals)


def write_html(config, files, users, merges, conflicts, multi_authors, approvals):

    os.chdir(os.path.dirname(os.path.realpath(__file__)))
    loader = jinja2.FileSystemLoader('templates')
    environment = jinja2.Environment(loader=loader, trim_blocks=True)

    if not os.path.isdir('docs'):
        os.makedirs('docs')

    templates = ['index', 'byfile', 'byuser', 'bymergecommit',
                 'byconflict', 'bymultiauthor', 'byapproval']

    for tmplfile in templates:
        now = datetime.utcnow()
        classes = {}
        for t in templates:
            classes['%s_classes' % t] = 'active' if tmplfile == t else ''

        template = environment.get_template('%s.html' % tmplfile)
        rendered = template.render(files=files, users=users, merges=merges,
                                   conflicts=conflicts,
                                   multi_authors=multi_authors,
                                   approvals=approvals,
                                   title=config['title'],
                                   now=now, **classes)

        with open('docs/%s.html' % tmplfile, 'w+b') as f:
            f.write(rendered.encode('ascii', 'ignore'))


if __name__ == '__main__':
    if os.path.exists('/tmp/pr-triage.lock'):
        print('Lock exists')
        sys.exit(0)
    with open('/tmp/pr-triage.lock', 'w+'):
        pass
    try:
        write_html(*scan_issues(get_config()))
    finally:
        os.unlink('/tmp/pr-triage.lock')
