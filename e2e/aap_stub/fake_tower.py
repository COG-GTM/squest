"""An in-process stand-in for a RHAAP/AWX controller.

Squest reaches AAP through exactly two doors: ``TowerServer.get_tower_instance()`` (job template
sync and job launch) and the ``Tower`` constructor imported by ``TowerServerForm`` (credential
validation). ``e2e.aap_stub.apps`` closes both of them onto the objects below, so the end to end
suite can exercise every AAP backed flow without a controller and without touching Squest's code.

The stub mirrors the towerlib surface Squest actually uses, and nothing more.
"""
import itertools
import logging
import threading

import towerlib

logger = logging.getLogger(__name__)

# a spec that needs the "Fail to authenticate with provided token" branch of TowerServerForm uses this
AUTH_FAILURE_TOKEN = "a-token-the-stub-rejects"

VM_SURVEY_SPEC = {
    "name": "",
    "description": "",
    "spec": [
        {
            "max": 64,
            "min": 1,
            "type": "integer",
            "choices": "",
            "default": 2,
            "required": True,
            "variable": "vcpu",
            "question_name": "vCPU",
            "question_description": "Number of virtual CPUs",
        },
        {
            "max": 256,
            "min": 1,
            "type": "integer",
            "choices": "",
            "default": 8,
            "required": True,
            "variable": "memory",
            "question_name": "Memory (GB)",
            "question_description": "Amount of memory in GB",
        },
        {
            "max": 0,
            "min": 0,
            "type": "multiplechoice",
            "choices": "dev\nstaging\nprod",
            "default": "dev",
            "required": True,
            "variable": "environment",
            "question_name": "Environment",
            "question_description": "Target environment",
        },
    ],
}

# (tower id, name, ask_variables_on_launch, survey spec). The second template is deliberately not
# compliant so that the compliancy flows have something to show.
JOB_TEMPLATE_FIXTURES = [
    (1, "Deploy virtual machine", True, VM_SURVEY_SPEC),
    (2, "Decommission virtual machine", False, {}),
]
INVENTORY_FIXTURES = [(1, "Demo inventory"), (2, "Production inventory")]
CREDENTIAL_FIXTURES = [(1, "Demo machine credential")]

_job_ids = itertools.count(1000)
# runserver serves requests on several threads, so two launches must not be handed the same id
_job_ids_lock = threading.Lock()


def _next_job_id():
    with _job_ids_lock:
        return next(_job_ids)


class FakeTowerJob:
    def __init__(self, job_id, job_template, parameters):
        self.id = job_id
        self.job_template = job_template
        self.parameters = parameters
        # the stub controller runs a playbook instantly, so a polled job is already done
        self.status = "successful"


class FakeJobTemplate:
    def __init__(self, tower_id, name, ask_variables_on_launch, survey_spec):
        self.id = tower_id
        self.name = name
        self.survey_spec = survey_spec
        # Squest copies the whole payload into JobTemplate.tower_job_template_data and reads
        # ask_variables_on_launch back out of it for its compliancy check
        self._data = {
            "id": tower_id,
            "name": name,
            "ask_variables_on_launch": ask_variables_on_launch,
            "survey_enabled": bool(survey_spec),
        }
        self.launches = []

    def launch(self, **parameters):
        job = FakeTowerJob(_next_job_id(), self, parameters)
        self.launches.append(job)
        LAUNCHED_JOBS[job.id] = job
        logger.info(f"[aap-stub] Launched job template '{self.name}' as job {job.id}")
        return job


class FakeInventory:
    def __init__(self, tower_id, name):
        self.id = tower_id
        self.name = name


class FakeCredential:
    def __init__(self, tower_id, name):
        self.id = tower_id
        self.name = name


# one controller for the whole run, the way a real one outlives the requests talking to it
JOB_TEMPLATES = [FakeJobTemplate(*fixture) for fixture in JOB_TEMPLATE_FIXTURES]
INVENTORIES = [FakeInventory(*fixture) for fixture in INVENTORY_FIXTURES]
CREDENTIALS = [FakeCredential(*fixture) for fixture in CREDENTIAL_FIXTURES]
LAUNCHED_JOBS = {}


class FakeTower:
    """Replaces ``towerlib.Tower``. Constructed with the same positional and keyword arguments."""

    def __init__(self, host=None, username=None, password=None, secure=True, ssl_verify=False, token=None,
                 aap_environment=False):
        if token == AUTH_FAILURE_TOKEN:
            raise towerlib.towerlibexceptions.AuthFailed(f"[aap-stub] refused the token of {host}")
        self.host = host
        self.token = token
        self.job_templates = JOB_TEMPLATES
        self.inventories = INVENTORIES
        self.credentials = CREDENTIALS

    def get_job_template_by_id(self, tower_id):
        for job_template in self.job_templates:
            if job_template.id == int(tower_id):
                return job_template
        return None

    def get_unified_job_by_id(self, job_id):
        """How ``Request.check_job_status`` polls a launched job.

        A real controller still knows a job launched before the server restarted, while
        ``LAUNCHED_JOBS`` only lives in the current process: an id it never handed out is answered
        with a finished job rather than with ``None``, which the caller would dereference.
        """
        job_id = int(job_id)
        if job_id not in LAUNCHED_JOBS:
            LAUNCHED_JOBS[job_id] = FakeTowerJob(job_id, self.job_templates[0], {})
        return LAUNCHED_JOBS[job_id]
