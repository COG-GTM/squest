"""Fixtures for the Playwright end to end suite.

The suite is deliberately black box: a real Squest dev server, a real MariaDB database seeded with
``insert_default_data`` + ``insert_demo_data``, a real browser, and the RHAAP/AWX boundary stubbed in
process (see ``e2e/aap_stub``). No Django test case, no mocked views.

Session scoped fixtures do the expensive work once per ``pytest`` run:

``seeded_database``  drops, recreates, migrates and seeds the end to end database
``live_server``      runs ``manage.py runserver`` against it and returns its base URL

Set ``E2E_REUSE_DB=1`` to keep the database from the previous run (skips drop/migrate/seed), which
turns a re-run of a single spec into a couple of seconds.
"""
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page, expect

from e2e.helpers import login

REPO_ROOT = Path(__file__).resolve().parent.parent
# the mariadb container grants squest_user on this database only, and the Django test runner recreates
# it from scratch, so the end to end suite can own it without colliding with the dev database
E2E_DB_DATABASE = os.environ.get("E2E_DB_DATABASE", "test_squest_db")
E2E_REUSE_DB = os.environ.get("E2E_REUSE_DB", "") not in ("", "0", "false", "False")
SERVER_START_TIMEOUT_SECONDS = 120
DEFAULT_EXPECT_TIMEOUT_MS = 15_000

# Squest prints the whole environment at startup, so the server is started from an allow list
# instead of inheriting the shell: an unrelated secret must never end up in a test log
PASSTHROUGH_ENVIRONMENT_KEYS = ["PATH", "HOME", "LANG", "LC_ALL", "TZ", "VIRTUAL_ENV", "DB_HOST", "DB_PORT",
                                "DB_USER", "DB_PASSWORD", "REDIS_CACHE_HOST", "REDIS_CACHE_PORT",
                                "REDIS_CACHE_PASSWORD", "RABBITMQ_HOST", "RABBITMQ_PORT"]

expect.set_options(timeout=DEFAULT_EXPECT_TIMEOUT_MS)


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _run_management_command(*arguments, environment, log_file):
    command = [sys.executable, "manage.py", *arguments]
    log_file.write(f"\n$ {' '.join(command)}\n")
    log_file.flush()
    subprocess.run(command, cwd=REPO_ROOT, env=environment, stdout=log_file, stderr=subprocess.STDOUT, check=True)


@pytest.fixture(scope="session")
def squest_environment():
    """The environment every Squest subprocess of the suite runs with."""
    environment = {key: os.environ[key] for key in PASSTHROUGH_ENVIRONMENT_KEYS if key in os.environ}
    environment.update({
        "DJANGO_SETTINGS_MODULE": "e2e.settings_e2e",
        "PYTHONPATH": str(REPO_ROOT),
        "PYTHONUNBUFFERED": "1",
        "DB_DATABASE": E2E_DB_DATABASE,
        # DEBUG also selects the dummy cache, which keeps the permission aware sidebar from being
        # served from a 60 second cache entry, and the fast password hasher used by the seed data
        "DEBUG": "True",
        "IS_DEV_SERVER": "True",
        "SQUEST_EMAIL_NOTIFICATION_ENABLED": "False",
        "METRICS_ENABLED": "True",
    })
    return environment


@pytest.fixture(scope="session")
def server_log_path(tmp_path_factory):
    return tmp_path_factory.mktemp("squest-e2e") / "squest-server.log"


@pytest.fixture(scope="session")
def seeded_database(squest_environment, server_log_path):
    """A migrated database holding the demo data: admin, alice, bob, carol, catalog, instances, quotas."""
    with server_log_path.open("w") as log_file:
        if not E2E_REUSE_DB:
            _recreate_database(squest_environment)
            _run_management_command("migrate", "--noinput", environment=squest_environment, log_file=log_file)
            _run_management_command("insert_default_data", environment=squest_environment, log_file=log_file)
            _run_management_command("insert_demo_data", environment=squest_environment, log_file=log_file)
    return E2E_DB_DATABASE


def _recreate_database(environment):
    import MySQLdb

    connection = MySQLdb.connect(
        host=environment.get("DB_HOST", "127.0.0.1"),
        port=int(environment.get("DB_PORT", "3306")),
        user=environment.get("DB_USER", "squest_user"),
        passwd=environment.get("DB_PASSWORD", "squest_password"),
    )
    try:
        cursor = connection.cursor()
        cursor.execute(f"DROP DATABASE IF EXISTS {E2E_DB_DATABASE}")
        cursor.execute(f"CREATE DATABASE {E2E_DB_DATABASE} CHARACTER SET utf8mb4")
        connection.commit()
    finally:
        connection.close()


@pytest.fixture(scope="session")
def live_server(seeded_database, squest_environment, server_log_path):
    """A Squest dev server serving the seeded database. Yields its base URL."""
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    environment = dict(squest_environment, SQUEST_HOST=base_url)
    with server_log_path.open("a") as log_file:
        server = subprocess.Popen(
            [sys.executable, "manage.py", "runserver", "--noreload", f"127.0.0.1:{port}"],
            cwd=REPO_ROOT, env=environment, stdout=log_file, stderr=subprocess.STDOUT,
        )
        try:
            _wait_until_serving(server, base_url, server_log_path)
            yield base_url
        finally:
            server.terminate()
            try:
                server.wait(timeout=30)
            except subprocess.TimeoutExpired:
                server.kill()


def _wait_until_serving(server, base_url, server_log_path):
    deadline = time.monotonic() + SERVER_START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise RuntimeError(f"The Squest dev server died during startup. Log: {server_log_path}\n"
                               f"{server_log_path.read_text()[-4000:]}")
        try:
            with urllib.request.urlopen(f"{base_url}/accounts/login/", timeout=5) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, ConnectionError, socket.timeout):
            time.sleep(0.5)
    raise RuntimeError(f"The Squest dev server did not answer on {base_url} within "
                       f"{SERVER_START_TIMEOUT_SECONDS}s. Log: {server_log_path}")


@pytest.fixture(scope="session")
def base_url(live_server):
    """Overrides the pytest-playwright fixture so ``page.goto('/ui/')`` hits the live server."""
    return live_server


@pytest.fixture
def login_as(context, base_url):
    """Returns a callable opening a new logged in page: ``login_as('bob')``.

    The demo users all have their username as password, so the password is optional.
    """
    def _login_as(username, password=None):
        page = context.new_page()
        login(page, base_url, username, password or username)
        return page
    return _login_as


@pytest.fixture
def admin_page(page, base_url) -> Page:
    """A page logged in as ``admin``, the superuser created by ``insert_default_data``."""
    login(page, base_url, "admin", "admin")
    return page


@pytest.fixture
def scoped_user_page(browser: Browser, base_url) -> Page:
    """A page logged in as ``bob``: a non admin holding the 'Squest user' role.

    ``bob`` is scoped to the 'Platform Engineering' organization and its 'SRE' team, so he sees the
    instances and requests of that scope and nothing of 'Marketing'. He is used to prove that a flow
    is not only reachable as a superuser.

    Its own browser context, so a spec can drive the admin and the scoped user side by side.
    """
    context = browser.new_context(base_url=base_url)
    page = context.new_page()
    login(page, base_url, "bob", "bob")
    yield page
    context.close()
