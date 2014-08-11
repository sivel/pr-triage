# pr-triage

GitHub Pull Request Triage Assistant

## triage.yaml

This file can live at `./triage.yaml`, `~/.triage.yaml`, or `/etc/triage.yaml`

```yaml
---
github_client_id: 1ecad3b34f7b437db6d0
github_client_secret: 6689ba85bb024d1b97370c45f1316a16d08bba20
github_repository: 'ansible/ansible'

use_rackspace: true
pyrax_credentials: ~/.rackspace_cloud_credentials
pyrax_region: DFW
pyrax_container: ansible-pr-triage
```

### GitHub credentials

You will need to [register an application](https://github.com/settings/applications/new)
to provide API access.

## Rackspace CloudFiles

It is not required that you upload the files to Rackspace CloudFiles, this is
just here for convenience. The container should already exist and be CDN
enabled.

If you do not have this enabled, the files will still be accessible in the
same directory as `triage.py`, titled `htmlout`.

## Running

It is recommended that you run `triage.py` via cron. The fewer pull requests a
project has the more frequently you can run the cron job. I'd recommend
starting with every 60 minutes (1 hour).
