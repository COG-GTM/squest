"""Fixtures for the Playwright end to end suite.

The suite is deliberately black box: a real Squest dev server, a real MariaDB database seeded with
``insert_default_data`` + ``insert_demo_data``, a real browser, and the RHAAP/AWX boundary stubbed in
process (see ``e2e/aap_stub``). No Django test case, no mocked views.

Session scoped fixtures do the expensive work once per ``pytest`` run:

``seeded_database``  drops, recreates, migrates and seeds the end to end database
``live_server``      runs ``manage.py runserver`` against it and returns its base URL

Set ``E2E_REUSE_DB=1`` to keep the database from the previous run (it is migrated, but not dropped or
re-seeded), which turns a re-run of a single spec into a couple of seconds. Set ``E2E_PAUSE_MS`` to
hold the browser still for that long at the end of every test, which is what makes a ``--headed`` run
watchable and what keeps ``--video`` from cutting off the state a test asserts on.
"""
import contextlib
import fcntl
import os
import re
import tempfile
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from e2e.helpers import login
from service_catalog.utils import str_to_bool

REPO_ROOT = Path(__file__).resolve().parent.parent
# the mariadb container grants squest_user on this database only, and the Django test runner recreates
# it from scratch, so the end to end suite can own it without colliding with the dev database
E2E_DB_DATABASE = os.environ.get("E2E_DB_DATABASE", "test_squest_db")
# the name cannot be a placeholder in a DROP/CREATE DATABASE, so it is checked instead of quoted
if not re.fullmatch(r"[A-Za-z0-9_$]+", E2E_DB_DATABASE):
    raise RuntimeError(f"E2E_DB_DATABASE='{E2E_DB_DATABASE}' is not a plain database identifier, and the "
                       f"harness interpolates it into a DROP DATABASE statement.")
E2E_REUSE_DB = str_to_bool(os.environ.get("E2E_REUSE_DB", "False"))
# Playwright's screencast is driven by page activity, so a test asserting on a page it did not touch
# after loading it can end up with a video whose last frame is the login form. Off by default: this
# costs wall clock, and a green headless run has no reader
E2E_PAUSE_MS = int(os.environ.get("E2E_PAUSE_MS", "0"))
SERVER_START_TIMEOUT_SECONDS = 120
DATABASE_LOCK_TIMEOUT_SECONDS = 1800
DEFAULT_EXPECT_TIMEOUT_MS = 15_000

# Squest prints the whole environment at startup, so the server is started from an allow list
# instead of inheriting the shell: an unrelated secret must never end up in a test log
PASSTHROUGH_ENVIRONMENT_KEYS = ["PATH", "HOME", "LANG", "LC_ALL", "TZ", "VIRTUAL_ENV", "DB_HOST", "DB_PORT",
                                "DB_USER", "DB_PASSWORD", "REDIS_CACHE_HOST", "REDIS_CACHE_PORT",
                                "REDIS_CACHE_PASSWORD", "RABBITMQ_HOST", "RABBITMQ_PORT", "RABBITMQ_USER",
                                "RABBITMQ_PASSWORD"]
# ... and the value of every variable whose name looks like a credential is scrubbed out of the log on
# the way in, because that environment dump would otherwise put it in a file a CI job may keep as an
# artifact. By name rather than by an explicit list, so that adding a key to the allow list above
# cannot quietly start leaking it
SECRET_ENVIRONMENT_KEY_PATTERN = re.compile(r"PASSWORD|SECRET|TOKEN|_KEY$|CREDENTIAL")
REDACTED = "***redacted by the e2e harness***"

expect.set_options(timeout=DEFAULT_EXPECT_TIMEOUT_MS)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    """Keeps the browser on the asserted page for ``E2E_PAUSE_MS`` before the fixtures tear it down."""
    try:
        return (yield)
    finally:
        # in a finally because a failing test is the one whose last frames are worth watching
        if E2E_PAUSE_MS:
            time.sleep(E2E_PAUSE_MS / 1000)


@pytest.fixture(scope="session")
def announce(pytestconfig):
    """Prints a line the user needs to see even on a green run.

    pytest captures fixture output and only replays it for a failing test, which would hide both the
    server log path and the 'waiting for another run' line of a session that is not failing but is
    doing something the user is waiting on.
    """
    capture_manager = pytestconfig.pluginmanager.getplugin("capturemanager")

    def _announce(message):
        with capture_manager.global_and_fixture_disabled():
            print(f"\n[e2e] {message}", file=sys.stderr, flush=True)
    return _announce


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _secrets_of(environment):
    # longest first, so a secret containing another one does not leave its tail behind
    return sorted({value for key, value in environment.items()
                   if value and SECRET_ENVIRONMENT_KEY_PATTERN.search(key)}, key=len, reverse=True)


def _pump_redacted(stream, log_file, secrets):
    """Copies a subprocess' output into the log with the infrastructure passwords scrubbed out."""
    for line in stream:
        for secret in secrets:
            line = line.replace(secret, REDACTED)
        log_file.write(line)
        log_file.flush()


def _pump_redacted_to_file(stream, log_path, secrets):
    """``_pump_redacted`` owning the log file, for a pump running in a thread.

    The thread outlives the fixture that started it whenever the pipe has not reached EOF yet (a
    grandchild of the server inheriting stdout), so the handle it writes to must not belong to that
    fixture: it would be closed under the thread, and its next write would raise in the background.
    """
    with log_path.open("a") as log_file:
        _pump_redacted(stream, log_file, secrets)


def _run_management_command(*arguments, environment, log_file, log_path):
    command = [sys.executable, "manage.py", *arguments]
    log_file.write(f"\n$ {' '.join(command)}\n")
    log_file.flush()
    process = subprocess.Popen(command, cwd=REPO_ROOT, env=environment, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True)
    _pump_redacted(process.stdout, log_file, _secrets_of(environment))
    process.stdout.close()
    if process.wait() != 0:
        raise RuntimeError(f"'{' '.join(arguments)}' failed with {process.returncode}. See {log_path}.")


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
def seeded_database(squest_environment, server_log_path, announce):
    """A migrated database holding the demo data: admin, alice, bob, carol, catalog, instances, quotas.

    The database name is shared by every run in this checkout and is recreated from scratch, so the
    whole session holds an exclusive lock on it: a second ``pytest`` started on the same machine
    waits instead of dropping the database under the first one. Give the runs different
    ``E2E_DB_DATABASE`` values to have them run at the same time.
    """
    announce(f"Squest server log: {server_log_path}")
    with _database_lock(announce):
        with server_log_path.open("w") as log_file:
            if E2E_REUSE_DB:
                if not _database_is_seeded(squest_environment):
                    raise RuntimeError(f"E2E_REUSE_DB is set but the '{E2E_DB_DATABASE}' database does not hold the "
                                       f"demo data yet. Run once without E2E_REUSE_DB to create and seed it.")
                # a kept database was seeded by an older revision: a migration added since then would
                # otherwise surface as a column error deep inside a spec
                commands = [("migrate", "--noinput")]
            else:
                _recreate_database(squest_environment)
                commands = [("migrate", "--noinput"), ("insert_default_data",), ("insert_demo_data",)]
            for command in commands:
                _run_management_command(*command, environment=squest_environment, log_file=log_file,
                                        log_path=server_log_path)
        yield E2E_DB_DATABASE


@contextlib.contextmanager
def _database_lock(announce):
    lock_path = Path(tempfile.gettempdir()) / f"squest-e2e-{E2E_DB_DATABASE}.lock"
    with lock_path.open("w") as lock_file:
        deadline = time.monotonic() + DATABASE_LOCK_TIMEOUT_SECONDS
        waited = False
        while True:
            try:
                fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if not waited:
                    waited = True
                    announce(f"waiting for the run holding '{E2E_DB_DATABASE}' ({lock_path}) to finish")
                if time.monotonic() > deadline:
                    raise RuntimeError(f"Another end to end run has been holding '{E2E_DB_DATABASE}' for more than "
                                       f"{DATABASE_LOCK_TIMEOUT_SECONDS}s ({lock_path}). Set E2E_DB_DATABASE to run "
                                       f"both at the same time.")
                time.sleep(1)
        try:
            yield
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def _database_exists(environment):
    with _mysql_connection(environment) as connection:
        cursor = connection.cursor()
        # not SHOW DATABASES LIKE: its pattern reads '_' as a wildcard, so 'test_squest_db' would also
        # accept an unrelated 'testXsquestXdb' and let E2E_REUSE_DB run against an unseeded database
        cursor.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name = %s",
                       (E2E_DB_DATABASE,))
        return cursor.fetchone() is not None


def _database_is_seeded(environment):
    """Whether the database holds the demo data, rather than only existing.

    A run interrupted between ``_recreate_database`` and ``insert_demo_data`` leaves an empty schema
    behind, and an ``E2E_REUSE_DB`` re-run against that would fail one spec at a time on missing demo
    objects instead of saying what is wrong.
    """
    import MySQLdb

    if not _database_exists(environment):
        return False
    with _mysql_connection(environment) as connection:
        cursor = connection.cursor()
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {E2E_DB_DATABASE}.auth_user")
        except MySQLdb.Error:
            return False
        return cursor.fetchone()[0] > 0


def _recreate_database(environment):
    with _mysql_connection(environment) as connection:
        cursor = connection.cursor()
        cursor.execute(f"DROP DATABASE IF EXISTS {E2E_DB_DATABASE}")
        cursor.execute(f"CREATE DATABASE {E2E_DB_DATABASE} CHARACTER SET utf8mb4")
        connection.commit()


@contextlib.contextmanager
def _mysql_connection(environment):
    import MySQLdb

    connection = MySQLdb.connect(
        host=environment.get("DB_HOST", "127.0.0.1"),
        port=int(environment.get("DB_PORT", "3306")),
        user=environment.get("DB_USER", "squest_user"),
        passwd=environment.get("DB_PASSWORD", "squest_password"),
    )
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture(scope="session")
def live_server(seeded_database, squest_environment, server_log_path):
    """A Squest dev server serving the seeded database. Yields its base URL."""
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    environment = dict(squest_environment, SQUEST_HOST=base_url)
    server = subprocess.Popen(
        [sys.executable, "manage.py", "runserver", "--noreload", f"127.0.0.1:{port}"],
        cwd=REPO_ROOT, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    log_pump = threading.Thread(target=_pump_redacted_to_file,
                                args=(server.stdout, server_log_path, _secrets_of(environment)), daemon=True)
    log_pump.start()
    try:
        _wait_until_serving(server, base_url, server_log_path)
        yield base_url
    finally:
        server.terminate()
        try:
            server.wait(timeout=30)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
        # so the log holds everything the server said on its way down
        log_pump.join(timeout=10)
        if not log_pump.is_alive():
            server.stdout.close()


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
            pass
        time.sleep(0.5)
    raise RuntimeError(f"The Squest dev server did not answer on {base_url} within "
                       f"{SERVER_START_TIMEOUT_SECONDS}s. Log: {server_log_path}")


@pytest.fixture(scope="session")
def base_url(live_server):
    """Overrides the pytest-playwright fixture so ``page.goto('/ui/')`` hits the live server."""
    return live_server


@pytest.fixture
def login_as(new_context, base_url):
    """Returns a callable opening a new logged in page: ``login_as('bob')``.

    Every user gets its own browser context: a context has a single cookie jar, so signing a second
    user in through the ``page`` context would replace the first one's Django session and the spec
    would quietly drive whoever signed in last.

    The contexts come from pytest-playwright's own ``new_context``, which both closes them and
    registers them with the artifact recorder: a context created straight off ``browser`` gets a
    ``record_video_dir`` but is never handed to the recorder, so its video and trace are dropped at
    the end of the run instead of being saved next to the admin's. Those arguments already carry the
    overridden ``base_url``, so the context is not told about the live server again.

    The demo users all have their username as password, so the password is optional.
    """
    def _login_as(username, password=None):
        page = new_context().new_page()
        login(page, base_url, username, password or username)
        return page
    return _login_as


@pytest.fixture
def admin_page(page, base_url) -> Page:
    """A page logged in as ``admin``, the superuser created by ``insert_default_data``."""
    login(page, base_url, "admin", "admin")
    return page


@pytest.fixture
def scoped_user_page(login_as) -> Page:
    """A page logged in as ``bob``: a non admin holding the 'Squest user' role.

    ``bob`` is scoped to the 'Platform Engineering' organization and its 'SRE' team, so he sees the
    instances and requests of that scope and nothing of 'Marketing'. He is used to prove that a flow
    is not only reachable as a superuser.

    Its own browser context, so a spec can drive the admin and the scoped user side by side.
    """
    return login_as("bob")
