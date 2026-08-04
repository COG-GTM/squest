---
name: squest-local-dev
description: How to run and manually test the Squest Django self-service portal locally (docker deps, poetry, celery, seeding, UI walkthrough paths, known log noise).
---

# Running & testing Squest locally

Squest is a Django app (`Squest/`) with two main sub-apps: `service_catalog/`,
`resource_tracker_v2/`, plus `profiles/` for orgs/teams/RBAC/quotas.

## Bring up the stack

From the repo root:

```bash
# 1. Backing services (mariadb 3306, rabbitmq 5672, redis 6379)
docker compose -f docker-compose.yml -f dev.docker-compose.yml up -d db rabbitmq redis-cache

# 2. Python + JS deps
poetry install
npm install            # required: static assets (adminlte, bootstrap-select, fontawesome,
                       # datatables, highlight.js) are pulled from node_modules by collectstatic

# 3. DB + static + seed data
poetry run python manage.py migrate
poetry run python manage.py collectstatic --noinput
poetry run python manage.py insert_default_data     # creates the admin/admin superuser from default_data.yml
                                                    # (the "Squest user" role comes from the post_migrate hook in profiles/apps.py)

# 4. Run (each in its own background process, log to a file)
IS_DEV_SERVER=True poetry run python manage.py runserver 0.0.0.0:8000
poetry run celery -A service_catalog worker -l INFO
poetry run celery -A service_catalog beat -l INFO
```

App is at http://localhost:8000/ (redirects to `/accounts/login/?next=/ui/`).
**Login: `admin` / `admin`** (defined in `default_data.yml`).
`IS_DEV_SERVER=True` renders a yellow "DEV SERVER" banner — handy proof in screenshots that you are
on the local build; the footer also shows the running version and commit.

## Seeding demo catalog data — blocked without AWX

`manage.py insert_testing_data` requires an `AWX_TOKEN` env var and a reachable AAP/AWX server; it
fails without them. Consequence: Service catalog / Requests / Instances / Tower server pages are
empty, and you **cannot** test service ordering, job templates, approval workflows, or the
request→instance lifecycle locally. If a task needs those, ask for `AWX_TOKEN` plus an AAP/AWX URL
up front rather than discovering it mid-run. It is also what creates the extra demo users
(Elias, Nicolas, Anthony, Mathijs, Jeff, Mark) — `insert_default_data` alone only creates `admin`.

### Creating demo data through the UI instead (works with no external deps)

A good, quick walkthrough that exercises writes across all three apps:

1. Access → Organization → **Add** → name it. (`/ui/profiles/organization/create/`)
2. On the org detail page → **Add team** (pre-fills the org FK). (`/ui/profiles/team/create/?org=<id>`)
3. Resource tracking → Attributes → **Add** (e.g. `vCPU`). (`/ui/resource-tracker/attribute/create/`)
4. Resource tracking → Resource groups → **Add** (e.g. `QA Cluster`). (`/ui/resource-tracker/resource-group/create/`)
   The Graph page then flips from the literal text "Nothing to display" to a rendered SVG node —
   a strong before/after assertion that the graph is wired to live data.
5. Org detail → **Set quotas** → set the attribute limit. (`/ui/profiles/organization/<id>/quota/`)
   It then appears in Resource tracking → Quota with Limit/Consumed/Available.

## Navigation map

The sidebar is generated in `profiles/templatetags/squest_utils.py::generate_sidebar` — read that
function to get the authoritative list of nav entries, their view names and required permissions.
Groups: **Service catalog** (Service catalog, Requests, Instances, Support, Docs),
**Resource tracking** (Attributes, Resource groups, Graph, Quota),
**Access** (Global scope, Organization, Team, Users),
**Administration** (RHAAP/AWX, Approval workflows, RBAC ▸ Role/Permission/Default permissions, Extras).

Other routes (`Squest/urls.py`): `/swagger/` and `/redoc/` (drf-yasg, needs an authenticated
session), `/admin/` (Django admin), `/api/...` for the REST API. There is a footer "API" link to
`/swagger/`, which is a nicer way to reach it on camera than typing the URL.

Note the sidebar permission block is wrapped in `{% cache 60 sidebar_permission ... %}`, so
permission changes may take up to 60s to show in the menu.

## Known log noise — do not report as a failure

`/ui/profiles/user/` prints an `AttributeError: type object 'User' has no attribute
'get_queryset_for_user'` traceback to the server log while still returning HTTP 200.
`Squest/utils/squest_views.py` `get_queryset()` deliberately catches this and falls back to
`self.model.objects.all()`, so the page still works. Pre-existing upstream behaviour.

## Security caution when sharing logs

When `DEBUG` is on (the default locally), `Squest/settings.py` runs `print(os.environ)` at startup,
so the runserver log contains **plaintext values of every env var**, including any unrelated session
secrets. Set `DEBUG=False` to suppress it. Never
attach or paste the raw django log; grep it for the specific lines you need
(`grep -E '" 5[0-9]{2} |Traceback|GET /static/.*" 4' <logfile>`).

## Devin Secrets Needed

- None for the basic local walkthrough (login is the hard-coded `admin`/`admin` dev account).
- `AWX_TOKEN` (+ a reachable AAP/AWX server URL) only if you need `insert_testing_data` or any
  service-ordering / job-template flow.
