#!/usr/bin/env python3
"""Create a Devin session that backfills unit tests for the symbols a PR left uncovered.

Called by the PR workflow when the patch coverage gate fails. Reads the report produced by
`scripts/patch_coverage.py` and prints the session URL, also exposing it as the `session_url`
step output when running in GitHub Actions.

Required environment:
    DEVIN_API_KEY   service user API key (repository secret)
    DEVIN_ORG_ID    organization the session is created in
    PR_NUMBER, PR_BRANCH, REPO
Optional:
    DEVIN_BASE_URL              defaults to https://api.devin.ai
    DEVIN_CREATE_AS_USER_ID     create the session as this user instead of the service user
                                (needs the ImpersonateOrgSessions permission)
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

PROMPT = """\
@{repo} Coverage gate failed on pull request #{pr_number} (branch `{branch}`).

{report}

Add unit tests that cover those symbols, then push them to `{branch}` (the same PR branch) so the
gate re-runs. Constraints:

- Tests only: do not change application code. If a symbol looks untestable without a production
  change, say so in a PR comment instead of changing it.
- Follow the existing conventions: tests live under `tests/` mirroring the app layout, reuse the
  fixtures in `tests/setup/`, and mock the AAP/AWX boundary with `unittest.mock` the way the
  neighbouring tests do rather than reaching the network.
- Run the tests you add before pushing, and report the patch coverage you reached.
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print the request instead of sending it")
    args = parser.parse_args()

    org_id = os.environ["DEVIN_ORG_ID"]
    base_url = os.environ.get("DEVIN_BASE_URL", "https://api.devin.ai").rstrip("/")
    repo = os.environ["REPO"]
    pr_number = os.environ["PR_NUMBER"]
    branch = os.environ["PR_BRANCH"]
    report = Path(os.environ.get("PATCH_COVERAGE_REPORT", "patch-coverage.md")).read_text().strip()

    payload = {
        "prompt": PROMPT.format(repo=repo, pr_number=pr_number, branch=branch, report=report),
        "title": f"Backfill coverage for {repo}#{pr_number}",
        "tags": ["coverage-gate"],
    }
    create_as_user_id = os.environ.get("DEVIN_CREATE_AS_USER_ID")
    if create_as_user_id:
        payload["create_as_user_id"] = create_as_user_id

    url = f"{base_url}/v3/organizations/{org_id}/sessions"
    if args.dry_run:
        print(f"POST {url}")
        print(json.dumps(payload, indent=2))
        return 0

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {os.environ['DEVIN_API_KEY']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            session = json.loads(response.read())
        session_url = session.get("url") or f"https://app.devin.ai/sessions/{session['session_id']}"
    except urllib.error.HTTPError as error:
        print(f"Failed to create Devin session: HTTP {error.code} {error.read().decode()}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, TimeoutError) as error:
        print(f"Failed to reach the Devin API: {error}", file=sys.stderr)
        return 1
    except (json.JSONDecodeError, KeyError) as error:
        print(f"Unexpected response from the Devin API: {error}", file=sys.stderr)
        return 1

    print(f"Created Devin session: {session_url}")
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as handle:
            handle.write(f"session_url={session_url}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
