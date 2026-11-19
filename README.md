<p align="center">
    <img src="project-static/squest/img/squest_logo_v2_300_300.png">
</p>

<h3 align="center">Self service portal on top of Red Hat Ansible Automation Platform</h3>

<p align="center">
<a href="https://hewlettpackard.github.io/squest/latest"><img alt="Doc" src="https://img.shields.io/badge/read-documentation-1abc9c?style=flat-square"></a>
<a href="https://app.gitter.im/#/room/#HewlettPackard_squest:gitter.im"><img alt="Gitter" src="https://img.shields.io/gitter/room/HewlettPackard/squest?color=1abc9c&style=flat-square"></a>
<a href= "https://coveralls.io/github/HewlettPackard/squest"><img alt="Coveralls" src="https://img.shields.io/coveralls/github/HewlettPackard/squest?style=flat-square"></a>
<a href="https://github.com/HewlettPackard/squest/releases/latest"><img alt="GitHub release (latest)" src="https://img.shields.io/github/v/release/HewlettPackard/squest?style=flat-square"></a>
<a href="https://github.com/HewlettPackard/squest/blob/master/LICENSE.md"><img alt="License" src="https://img.shields.io/github/license/HewlettPackard/squest?style=flat-square"></a>
<img alt="GitHub Repo stars" src="https://img.shields.io/github/stars/HewlettPackard/squest?style=flat-square">
</p>

Squest is a sophisticated framework that empowers you to create a web portal offering a comprehensive **Everything-as-a-Service** experience.

In Squest, the services made available are not hardcoded. Instead, each service serves as a reference to your automation capabilities within the backend engine, 
Red Hat Ansible Automation Platform (RHAAP)/AWX (formerly known as Ansible Tower). This essentially means that anything, as long as it exists as an automation script, 
can be transformed into a service. Your only limitation lies in your own proficiency in automation.

Going beyond mere deployment, Squest maintains a record of every instance of services it provisions in its database. 
This allows you to augment these instances with additional automation, enabling your users to effectively manage the lifecycle of their resources. 
Each operation performed corresponds to yet another link to an automation process in the backend. This empowering feature enhances user autonomy, 
relieving you of the burden of providing extensive support and managing object updates.

If you want an idea of what you can do with Squest, click on the image below.

[![DEMO](https://i3.ytimg.com/vi/mQnNkSMMXwg/maxresdefault.jpg)](https://youtu.be/mQnNkSMMXwg)

## Features

- Service catalog:
  - Add services to your catalog based on job templates you have in your Red Hat Ansible Automation Platform/AWX instance
  - Manage requests for services (review, update, approve and process)
  - Manage lifecycle of each instance of a service
  - Integrated or external support page
  - Organization, team and user management
  - Approval workflows
  - Custom on-boarding documentation
  - RBAC (Roles, Permissions, Role bindings)

- Resource tracking:
  - Create generic objects
  - Link objects to compose layers of your infrastructure (Physical servers, Virtualization, Containers, Projects, Tenants,...)
  - Visualize pool of resource of what you have provided (CPU, vCPU, memory, disk...)
  - Check consumptions before approving new requests
  - Graph representation of resource layers
  - Set quotas on each attribute
  
## Architecture

Squest is a Django application (UI, REST API and Swagger served by gunicorn behind nginx) with a Celery worker and a
Celery beat scheduler, backed by MariaDB (or PostgreSQL), RabbitMQ and Redis. It launches and polls job templates on
RHAAP/AWX through `towerlib`. See [docs/dev/architecture.md](docs/dev/architecture.md) for the components, the request
lifecycle and CI.

![Squest architecture](docs/images/architecture.png)

## Repository layout

| Path | Contents |
|---|---|
| `Squest/` | Django project: settings, URLs, middleware and shared base classes |
| `service_catalog/` | Service catalog app: RHAAP/AWX servers, services, operations, requests, instances, approvals, hooks, Celery app and tasks, management commands |
| `resource_tracker_v2/` | Resource tracking app: attribute definitions, resource groups, resources |
| `profiles/` | Organizations, teams, RBAC roles, quotas, API tokens, notification filters |
| `monitoring/` | Prometheus exporter (`/metrics/`) |
| `plugins/` | Custom field and survey validators loaded at run time |
| `templates/`, `project-static/` | Django templates and static assets |
| `tests/` | Django test suite |
| `scripts/` | CI coverage-gate helpers |
| `docker/`, `docker-compose.yml`, `*.docker-compose.y*ml`, `k8s/` | Docker Compose and Kubernetes deployment |
| `docs/`, `mkdocs.yml` | MkDocs documentation |

## Quick start

Run the published image with Docker Compose, then open [http://127.0.0.1:8080](http://127.0.0.1:8080) and log in
as `admin` / `admin`:

```bash
docker compose up
```

For a local development setup (Poetry on Python 3.12, `npm install` for the front-end libraries, dependencies in
Docker, `manage.py runserver` and Celery), follow [docs/dev/dev-env.md](docs/dev/dev-env.md). Run the tests with
`python manage.py test`.

To fill an empty local or demo database with sample users (`alice`, `bob`, `carol`, password = username), services,
instances, requests and resources, run `python manage.py insert_demo_data`. It needs no reachable RHAAP/AWX and
refuses to run unless `DEBUG` is on or `--force` is passed.

## About this fork

This repository is a fork of [HewlettPackard/squest](https://github.com/HewlettPackard/squest). On top of upstream it
adds the `insert_demo_data` command and a pull-request coverage gate
(`.github/workflows/on-pull-request-workflow.yml`): project coverage must stay at 90% or more and the lines a PR
changes at 85% or more, and a failing patch gate starts a Devin session to add the missing tests. The badges above
and the published documentation and releases are upstream's.

## Links

:blue_book: [Documentation (upstream)](https://hewlettpackard.github.io/squest/latest)<br/>
:speech_balloon: [Chat on Gitter](https://app.gitter.im/#/room/#HewlettPackard_squest:gitter.im)<br/>
:movie_camera: [Demo video](https://youtu.be/mQnNkSMMXwg)<br/>
:monkey_face: [Our Ansible playbook testing framework](https://github.com/HewlettPackard/monkeyble)

> If you like the project, star it ⭐, it motivates us a lot 🙂
