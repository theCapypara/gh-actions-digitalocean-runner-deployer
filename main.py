import asyncio
import datetime
import os
import random
import re
import traceback
from asyncio import sleep
from typing import NamedTuple, Set

import requests
import yaml
from digitalocean import Manager, Droplet
from github import Github, Organization, CheckRun, Repository

REGEX_MATRIX_BUILD_CR_NAME = re.compile(r'(.*?)( \(.*\))')



def create_self_hosted_runner_registration_token(org: Organization):
    headers, data = org._requester.requestJsonAndCheck(
        "POST",
        f"{org.url}/actions/runners/registration-token"
    )
    return data["token"]


def create_user_data_script(tags: Set[str], reg_token: str, org_name: str, runner_download_url: str, runner_name: str):
    custom_script = ""
    if "CUSTOM_SETUP_SCRIPT" in os.environ:
        with open(os.environ['CUSTOM_SETUP_SCRIPT'], 'r') as f:
            custom_script = f.read()

    script = f"""#!/usr/bin/env bash
mkdir /tmp/runner/work -p
chmod 777 /tmp/runner/work
{custom_script}
mkdir /actions-runner && cd /actions-runner
curl -o r.tar.gz -L {runner_download_url}
tar xzf ./r.tar.gz
./bin/installdependencies.sh
useradd github
chown github . -R
mkdir -p /home/github
chown github /home/github -R
su github -c './config.sh --unattended --url https://github.com/{org_name} --token {reg_token} --work /tmp/runner/work --labels {",".join(tags)} --name {runner_name} --ephemeral --disableupdate'
su github -c ./run.sh
poweroff
"""
    if len(script.encode('utf-8')) > 65536:
        raise ValueError("The digitalocean init user data script would exceed 64KiB. Please make sure your custom script isn't too big.")
    return script


def get_runner_download_url(g: Github):
    actions_repo = g.get_repo("actions/runner")
    release = actions_repo.get_latest_release()
    for asset in release.get_assets():
        if asset.name == f"actions-runner-linux-x64-{release.tag_name[1:]}.tar.gz":
            return asset.browser_download_url

    raise ValueError("Could not find runner image.")


class PendingJobPickup(NamedTuple):
    check_run_id: int
    pending_since: datetime.datetime


async def pickup_job(
        do: Manager,
        repo: Repository, check_run: CheckRun, org_name: str, repo_name: str, run_id: int,
        tags: Set[str], reg_token: str, runner_download_url: str
):
    name = f'gh-runner-{random.Random(check_run.id).randint(0, 10000000)}'
    await sleep(int(os.environ['PICKUP_DELAY']))
    # Reload the check run, see if it's still pending
    check_run = repo.get_check_run(check_run_id=check_run.id)
    if check_run.status != 'queued':
        return
    print(f"[{check_run.id}] Picking up job '{check_run.name}' for {repo_name} run {run_id}...")

    droplet = Droplet(
        name=name,
        region=os.environ['DIGITALOCEAN_DROPLET_REGION'],
        image=os.environ['DIGITALOCEAN_DROPLET_IMAGE'],
        size_slug=os.environ['DIGITALOCEAN_DROPLET_SIZE'],
        user_data=create_user_data_script(tags, reg_token, org_name, runner_download_url, name),
        tags=[os.environ['DIGITALOCEAN_TAG']]
     )
    droplet.create()
    print(f"[{check_run.id}] Running...")
    await sleep(60)
    while do.get_droplet(droplet.id).status != 'off':
        await sleep(60)
    print(f"[{check_run.id}] Done!")
    droplet.destroy()


def cleanup_pending(pending: Set[PendingJobPickup]):
    return set((x for x in pending if x.pending_since > datetime.datetime.utcnow() - datetime.timedelta(minutes=8, seconds=int(os.environ['PICKUP_DELAY']))))


async def deployloop(do: Manager, g: Github, go: Organization):
    pending_job_pickups: Set[PendingJobPickup] = set()
    monitored_runner_tags = set(os.environ['LABELS'].split(','))
    print("Running!")

    while True:
        try:
            for repo in go.get_repos():
                for run in repo.get_workflow_runs(status='queued'):
                    workflow_yml = None
                    check_suite = repo.get_check_suite(int(run.check_suite_url.split('/')[-1]))
                    for check_run in check_suite.get_check_runs(status='queued'):
                        if not any(x for x in pending_job_pickups if x.check_run_id == check_run.id):
                            pending_job_pickups.add(PendingJobPickup(
                                check_run_id=check_run.id, pending_since=datetime.datetime.utcnow()
                            ))
                            runner_tags = None

                            # Load runner tags:
                            try:
                                if workflow_yml is None:
                                    workflow = repo.get_workflow(run.workflow_id)
                                    workflow_url_parts = workflow.html_url.split('/')
                                    workflow_url_parts[5] = 'raw'
                                    workflow_url_parts[6] = run.head_sha
                                    workflow_yml = yaml.safe_load(requests.get('/'.join(workflow_url_parts)).text)
                                for job in workflow_yml['jobs'].values():
                                    cr_name = check_run.name
                                    if 'strategy' in job:
                                        if 'matrix' in job['strategy']:
                                            # This is a matrix build...
                                            # We remove the last pair of parenthesis from the check run name
                                            # This could obviously break later....
                                            match = REGEX_MATRIX_BUILD_CR_NAME.match(cr_name)
                                            if match:
                                                cr_name = match.group(1)

                                    if job['name'] == cr_name:
                                        runner_tags = job['runs-on']
                                        if not isinstance(runner_tags, list):
                                            runner_tags = [runner_tags]
                                        break
                            except Exception:
                                print("Error trying to load workflow YAML for a runner")
                                print(traceback.format_exc())

                            if runner_tags is not None and len(set(runner_tags).intersection(monitored_runner_tags)) > 0:
                                asyncio.get_event_loop().create_task(pickup_job(
                                    do, repo, check_run, go.login, repo.full_name, run.id, monitored_runner_tags,
                                    create_self_hosted_runner_registration_token(go), get_runner_download_url(g)
                                ))
        except Exception:
            print("Unexpected error in loop.")
            print(traceback.format_exc())
        await sleep(60)
        pending_job_pickups = cleanup_pending(pending_job_pickups)


def cleanup(do: Manager):
    print("Cleaning up running droplets...")
    for droplet in do.get_all_droplets(tag_name=os.environ['DIGITALOCEAN_TAG']):
        # safety sanity check
        if droplet.name.startswith("gh-runner-"):
            print(f"Destroying droplet {droplet.id}...")
            droplet.destroy()


def main():
    print("Starting...")
    do = Manager()
    g = Github(os.environ['GITHUB_ACCESS_TOKEN'])
    go = g.get_organization(os.environ['ORG_NAME'])

    # First clean up by shutting down all running runners...
    cleanup(do)

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(deployloop(do, g, go))
    except (KeyboardInterrupt, SystemExit):
        print("Exiting...")
        pass
    finally:
        # Try clean up by shutting down all running runners...
        cleanup(do)
        loop.close()


if __name__ == '__main__':
    main()
