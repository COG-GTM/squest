# End to end suite (Playwright)

Black box tests driving a real browser against a real Squest dev server: the 1170 unit tests cover the
units, this suite covers the flows a user actually walks through.

## What the harness gives a spec

| Fixture | What it is |
| --- | --- |
| `live_server` | a `manage.py runserver` on a free port, session scoped. Yields its base URL |
| `base_url` | the same URL, so `page.goto("/ui/")` works |
| `seeded_database` | `test_squest_db`, dropped, migrated and seeded with `insert_default_data` + `insert_demo_data` |
| `admin_page` | a page signed in as `admin` (superuser) |
| `scoped_user_page` | a page signed in as `bob`, a non admin with the "Squest user" role on the "Platform Engineering" org and its "SRE" team. Its own browser context |
| `login_as` | `login_as("carol")` opens another signed in page in its own browser context, to drive two users in one test |

The RHAAP/AWX boundary is stubbed in process by `e2e/aap_stub`: `e2e.settings_e2e` installs an app
whose `ready()` points `TowerServer.get_tower_instance()` and the `Tower` constructor of
`TowerServerForm` at `FakeTower`. Job template sync, token validation, job launch and job status
polling therefore work with no controller and no change to Squest's own code. Squest's code is never
patched from a spec. The stub serves two job templates, `Deploy virtual machine` (with a survey) and
`Decommission virtual machine` (deliberately not compliant: `ask_variables_on_launch` is false), a
launched job reports itself as `successful`, and the token `AUTH_FAILURE_TOKEN` is refused so a spec
can walk the "Fail to authenticate with provided token" branch of `TowerServerForm`.

The demo seed (see `service_catalog/management/commands/insert_demo_data.py`) gives you: users
`admin`/`alice`/`bob`/`carol` (password = username), the "Infrastructure" and "Databases" portfolios,
three services with a create and a resize operation, six instances across two organizations and three
teams, requests in every state, supports, resource groups, resources and quotas.

## Running it

```bash
docker compose -f docker-compose.yml -f dev.docker-compose.yml up -d db redis-cache
poetry install --with test
poetry run playwright install --with-deps chromium

poetry run pytest                                   # the whole suite
poetry run pytest e2e/specs/auth_and_navigation_spec.py
poetry run pytest --headed --slowmo 400              # watch it
E2E_PAUSE_MS=2000 poetry run pytest --headed -k nav  # ... and hold on the asserted page at the end
E2E_REUSE_DB=1 poetry run pytest -k instance         # keep the seeded database: re-runs in seconds
```

`--slowmo` pads Playwright actions, so a test whose last step is an assertion still flashes past in
about a second. `E2E_PAUSE_MS` holds every test on its final page instead, which is also what keeps
`--video on` from ending an assertion-only test's recording on the login form: the screencast follows
page activity, so a test that only reads the page it loaded has nothing to record after the load.

`E2E_DB_DATABASE` overrides the database name (`test_squest_db` by default: the mariadb container
grants `squest_user` on it, and the Django test runner recreates it anyway, so the suite can own it
without touching the dev database). That database is dropped and recreated at the start of a run, so
a session holds an exclusive lock on it for its whole duration: a second `pytest` on the same
machine waits for the first one instead of pulling the database out from under it. To run two suites
at the same time, give them different `E2E_DB_DATABASE` values (the compose file only grants
`squest_user` on `squest_db` and `test_squest_db`, so another name needs its own `GRANT`).

The harness drops and creates that database over `MySQLdb`, so it needs the MariaDB stack of
`dev.docker-compose.yml`: it does not work against the PostgreSQL one of `psql.docker-compose.yaml`.
It also starts the server from an allow list of environment variables rather than inheriting the
shell (Squest prints `os.environ` under `DEBUG`, and an unrelated secret must not end up in a log a
CI job keeps), so a variable the suite is not told about — including `SECRET_KEY`, which falls back
to the built-in development value — does not reach it. Add the key to `PASSTHROUGH_ENVIRONMENT_KEYS`
in `e2e/conftest.py` if a spec needs one, and to `SECRET_ENVIRONMENT_KEYS` if it is a secret.

## Writing a spec

* One file per flow family, `e2e/specs/<family>_spec.py`. `*_spec.py` keeps `manage.py test` from
  ever importing a Playwright spec, `pytest` collects nothing else.
* Navigate the way a user does: through the sidebar (`goto_sidebar_entry`) and through links and
  buttons, not by building URLs by hand. `NAV_MAP` in `e2e/helpers.py` mirrors
  `generate_sidebar` and is asserted against the rendered sidebar, so use it instead of literals.
* Cover a flow as the scoped non admin too whenever a user can walk it, and assert the boundary: a
  scope a user is not part of must answer 403, and its objects must not show up in a list.
* Assert on what the user sees: a django message (`expect_message`), a row in a list
  (`expect_table_contains`), a state badge. `e2e/helpers.py` holds the shared shell helpers.
* Keep specs independent: no ordering between tests, and create the objects you need with a unique
  name (the seed is shared and `E2E_REUSE_DB` may keep it between runs).
* A run prints the path of the dev server log at startup, which holds the Django traceback of a
  failing spec.
* Artifacts (`--video on`, `--tracing on`) land in `test-results/`, which pytest-playwright **wipes
  at the start of every run**: copy what you want to keep before re-running. Open a page for a second
  user through `login_as`, never off `browser` directly, or its artifacts are silently dropped.
