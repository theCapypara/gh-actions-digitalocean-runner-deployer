Github Actions Digitalocean Deployer
====================================

This tool allows you to automatically deploy new Digitalocean droplets for new
Github actions jobs.

Droplets are automatically started, the runner system is configured, a job is run
and then droplets are shut down again.

Workdir for all runner jobs is `/tmp/runner/work`. Runners are always ephemeral.

To run, you can use the docker image `...` or run it manually (only Python 3.10 tested):
```sh
pip install -r requirements.txt
python main.py
```

Example run command with Docker:
```sh
/usr/bin/docker run --rm --env-file ($pwd)/.env ...:latest
```

Configuration
-------------
This tool is configured via environment variables. All settings MUST be set, unless otherwise specified.

Currently the following configuration settings are available. If you need
more things configured, feel free to open an issue or fork / open a PR!
Only organization runners are supported at the moment.

| ORG_NAME                    | Name of the Github organization to register runners in.                                                                                                                                |
|-----------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| LABELS                      | Labels to add to runners and labels to "listen" for.                                                                                                                                   |
| PICKUP_DELAY                | Delay in seconds after which droplets are started when queued jobs are detected. Note that scanning is done every 60 seconds, so there is also a "natural" delay without this setting. |
| GITHUB_ACCESS_TOKEN         | Github personal access token with admin rights for orgs.                                                                                                                               |
| DIGITALOCEAN_ACCESS_TOKEN   | Digitaloean personal access token with write access.                                                                                                                                   |
| DIGITALOCEAN_TAG            | Tag to add to all managed droplets. Note that when the tool is started and stopped ALL DROPLETS with this tag will be DELETED.                                                         |
| DIGITALOCEAN_DROPLET_SIZE   | Droplet size slug. See: https://slugs.do-api.dev/                                                                                                                                      |
| DIGITALOCEAN_DROPLET_IMAGE  | Droplet image slug. See: https://slugs.do-api.dev/                                                                                                                                     |
| DIGITALOCEAN_DROPLET_REGION | Droplet region slug. See: https://slugs.do-api.dev/                                                                                                                                    |
| CUSTOM_SETUP_SCRIPT         | Path to a custom shell script. It will be injected into the "user data" that is used to initialize the droplets. Optional.                                                             |
