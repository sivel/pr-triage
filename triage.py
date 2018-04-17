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
import urllib2

from bs4 import BeautifulSoup
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
    rejected_review = re.compile("is-rejected is-writer")
    approved_review = re.compile("is-approved is-writer")

    files = defaultdict(list)
    users = defaultdict(list)
    conflicts = defaultdict(list)
    ready = defaultdict(list)
    rejected = defaultdict(list)
    to_review = defaultdict(list)
    ci_failures = defaultdict(list)
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

            if pull.mergeable_state == 'unstable':
                ci_failures[login].append(pull)

            for pull_file in pull.get_files():
                files[pull_file.filename].append(pull)

            # Required Review Status
            # Have to get html content for this :(
            content = urllib2.urlopen(pull.html_url).read()
            soup = BeautifulSoup(content, 'html.parser')

            # rejected
            rejections = soup.find_all(class_=rejected_review)

            # approved
            approvals = soup.find_all(class_=approved_review)

            # Sort out of rejectors approved and whatnot
            isrejected = False
            isapproved = False
            if len(rejections) > 0:
                if len(approvals) > 0:
                    rejsbyauthor = {}
                    appsbyauthor = {}
                    
                    # find the latest rejection per author
                    for rej in rejections:
                        author = rej.find_all(class_="author")[0]
                        reltime = rej('relative-time')[0]['datetime']
                        rejsbyauthor[author] = reltime

                    # find the latest approvals per author
                    for app in approvals:
                        author = app.find_all(class_="author")[0]
                        reltime = app('relative-time')[0]['datetime']
                        appsbyauthor[author] = reltime

                    # If a rejection author doesn't have an approval, bad
                    for rej in [rej for rej in rejsbyauthor if rej
                                not in appsbyauthor.keys()]:
                        isrejected = True
                        rejected[login].append(pull)
                        break

                    # If a rejection has a newer approval allow it in
                    if not isrejected:
                        for rej in [rej for rej in rejsbyauthor if rej
                                    in appsbyauthor.keys()]:
                            latestapp = appsbyauthor[rej]
                            dtrej = datetime.strptime(rejsbyauthor[rej],
                                                      "%Y-%m-%dT%H:%M:%SZ")
                            dtapp = datetime.strptime(rejsbyauthor[rej],
                                                      "%Y-%m-%dT%H:%M:%SZ")
                            if dtrej > dtapp:
                                isrejected = True
                                rejected[login].append(pull)
                                break

                # no approvals, any rejection is a rejection
                else:
                    isrejected = True
                    rejected[login].append(pull)
            
            # no rejections, with approvals
            if not isrejected and len(approvals) > 0:
                isapproved = True

            if isapproved and pull.mergeable is True and pull.mergeable_state == 'clean':
                ready[login].append(pull)

            # things that need to be looked at
            if not isapproved and not isrejected:
                to_review[login].append(pull)

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

    return (config, files, usersbypulls, merges, conflicts, multi_author,
            ci_failures, ready, rejected, to_review)


def write_html(config, files, users, merges, conflicts, multi_author,
               ci_failures, ready, rejected, toreview):
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
                 'byconflict', 'bymultiauthor', 'bycifailures',
                 'byready', 'byrejected', 'bytoreview']

    for tmplfile in templates:
        now = datetime.utcnow()
        classes = {}
        for t in templates:
            classes['%s_classes' % t] = 'active' if tmplfile == t else ''

        template = environment.get_template('%s.html' % tmplfile)
        rendered = template.render(files=files, users=users, merges=merges,
                                   conflicts=conflicts,
                                   multi_author=multi_author,
                                   ci_failures=ci_failures,
                                   ready=ready, rejected=rejected,
                                   toreview=toreview,
                                   title=config['title'],
                                   now=now, **classes)

        with open('htmlout/%s.html' % tmplfile, 'w+b') as f:
            f.write(rendered.encode('ascii', 'ignore'))

        if config.get('use_rackspace', False):
            cont.upload_file('htmlout/%s.html' % tmplfile,
                             obj_name='%s.html' % tmplfile,
                             content_type='text/html')


if __name__ == '__main__':
    write_html(*scan_issues(get_config()))
