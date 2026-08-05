"""Settings used by the Playwright end to end suite.

The suite drives a real dev server against a real database, so this module only differs from the
production settings where a test needs it: the RHAAP/AWX boundary is replaced by a stub app and
emails are kept in memory instead of being handed to an SMTP server.

Everything else (DEBUG, the database name, ...) is passed through the environment by
``e2e/conftest.py``.
"""
from Squest.settings import *  # noqa: F401,F403

INSTALLED_APPS = INSTALLED_APPS + ["e2e.aap_stub.apps.AapStubConfig"]  # noqa: F405

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# a relative host would make the "squest" extra vars of a request unusable in assertions
SQUEST_HOST = os.environ.get("SQUEST_HOST", "http://127.0.0.1:8000")  # noqa: F405
