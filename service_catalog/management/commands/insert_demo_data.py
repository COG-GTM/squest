import logging

from django.contrib.auth.models import User
from django.core.management import BaseCommand

from profiles.models import Organization, Quota, Role, Scope, Team
from resource_tracker_v2.models import AttributeDefinition, ResourceGroup, Transformer
from service_catalog.models import Instance, InstanceState, JobTemplate, Operation, OperationType, Portfolio, Request, \
    RequestState, Service, Support, TowerServer

logger = logging.getLogger(__name__)

DEMO_TOWER_NAME = "Demo AAP"
DEMO_USERS = [
    ("alice", "alice@squest.domain"),
    ("bob", "bob@squest.domain"),
    ("carol", "carol@squest.domain"),
]
DEMO_SURVEY = [
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
        "max": 262144,
        "min": 1024,
        "type": "integer",
        "choices": "",
        "default": 4096,
        "required": True,
        "variable": "memory",
        "question_name": "Memory (MB)",
        "question_description": "Amount of memory in MB",
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
]


class Command(BaseCommand):
    help = "Seed a demo-ready database. Does not require a reachable AAP/AWX server."

    def handle(self, *args, **options):
        print("[insert_demo_data] Start")
        users = self.create_users()
        tower, job_template = self.create_tower()
        services = self.create_catalog(job_template)
        scopes = self.create_scopes(users)
        instances = self.create_instances(services, scopes, users)
        self.create_requests(instances, users)
        self.create_supports(instances, users)
        self.create_resource_tracking(scopes, instances)
        print("[insert_demo_data] End")

    def create_users(self):
        users = {}
        for username, email in DEMO_USERS:
            user, created = User.objects.get_or_create(username=username, defaults={"email": email})
            if created:
                user.set_password(username)
                user.save()
                logger.info(f"Create User '{username}'")
            users[username] = user
        return users

    def create_tower(self):
        tower, _ = TowerServer.objects.get_or_create(
            name=DEMO_TOWER_NAME,
            defaults={"host": "aap.demo.local", "token": "demo-token"},
        )
        job_template, _ = JobTemplate.objects.get_or_create(
            name="Deploy virtual machine",
            tower_server=tower,
            defaults={"survey": {"spec": DEMO_SURVEY}, "tower_id": 1, "tower_job_template_data": dict()},
        )
        return tower, job_template

    def create_catalog(self, job_template):
        infrastructure, _ = Portfolio.objects.get_or_create(
            name="Infrastructure",
            defaults={"description": "Compute, storage and network services"},
        )
        databases, _ = Portfolio.objects.get_or_create(
            name="Databases",
            defaults={"description": "Managed database services", "parent_portfolio": infrastructure},
        )
        services = {}
        service_specs = [
            ("Virtual machine", "Provision a RHEL virtual machine", infrastructure),
            ("Kubernetes namespace", "Provision a namespace on the shared cluster", infrastructure),
            ("PostgreSQL database", "Provision a managed PostgreSQL database", databases),
        ]
        for name, description, portfolio in service_specs:
            service, _ = Service.objects.get_or_create(
                name=name,
                defaults={"description": description, "parent_portfolio": portfolio},
            )
            create_operation, _ = Operation.objects.get_or_create(
                name=f"Create {name.lower()}",
                service=service,
                type=OperationType.CREATE,
                defaults={"job_template": job_template, "process_timeout_second": 30},
            )
            create_operation.update_survey()
            update_operation, _ = Operation.objects.get_or_create(
                name=f"Resize {name.lower()}",
                service=service,
                type=OperationType.UPDATE,
                defaults={"job_template": job_template, "process_timeout_second": 30},
            )
            update_operation.update_survey()
            if not service.enabled:
                service.enabled = True
                service.save()
            services[name] = service
        return services

    def create_scopes(self, users):
        squest_user_role = Role.objects.filter(name="Squest user").first()
        scopes = {}
        for org_name, team_names in [("Platform Engineering", ["SRE", "Data"]), ("Marketing", ["Web"])]:
            org, _ = Organization.objects.get_or_create(name=org_name)
            scopes[org_name] = org
            for team_name in team_names:
                team, _ = Team.objects.get_or_create(name=team_name, org=org)
                scopes[f"{org_name}/{team_name}"] = team
        if squest_user_role is not None:
            for org_name, team_name, user in [
                ("Platform Engineering", None, users["alice"]),
                ("Platform Engineering", "SRE", users["bob"]),
                ("Marketing", "Web", users["carol"]),
            ]:
                # a user must belong to the organization before being added to one of its teams
                scopes[org_name].add_user_in_role(user, squest_user_role)
                if team_name is not None:
                    scopes[f"{org_name}/{team_name}"].add_user_in_role(user, squest_user_role)
        return scopes

    def create_instances(self, services, scopes, users):
        instances = {}
        instance_specs = [
            ("web-frontend-01", "Virtual machine", "Platform Engineering", users["alice"], InstanceState.AVAILABLE),
            ("web-frontend-02", "Virtual machine", "Platform Engineering", users["alice"], InstanceState.AVAILABLE),
            ("batch-worker-01", "Virtual machine", "Platform Engineering/SRE", users["bob"], InstanceState.AVAILABLE),
            ("analytics-ns", "Kubernetes namespace", "Platform Engineering/Data", users["bob"],
             InstanceState.PROVISIONING),
            ("reporting-db", "PostgreSQL database", "Platform Engineering/Data", users["alice"],
             InstanceState.AVAILABLE),
            ("campaign-site", "Virtual machine", "Marketing/Web", users["carol"], InstanceState.PENDING),
        ]
        for name, service_name, scope_name, requester, state in instance_specs:
            instance, created = Instance.objects.get_or_create(
                name=name,
                defaults={
                    "service": services[service_name],
                    "quota_scope": Scope.objects.get(id=scopes[scope_name].id),
                    "requester": requester,
                    "spec": {"environment": "dev"},
                },
            )
            if created:
                instance.state = state
                instance.save()
            instances[name] = instance
        return instances

    def create_requests(self, instances, users):
        request_specs = [
            ("web-frontend-01", RequestState.COMPLETE, users["alice"]),
            ("web-frontend-02", RequestState.COMPLETE, users["alice"]),
            ("batch-worker-01", RequestState.ACCEPTED, users["bob"]),
            ("analytics-ns", RequestState.PROCESSING, users["bob"]),
            ("reporting-db", RequestState.ON_HOLD, users["alice"]),
            ("campaign-site", RequestState.SUBMITTED, users["carol"]),
        ]
        for instance_name, state, user in request_specs:
            instance = instances[instance_name]
            operation = instance.service.operations.filter(type=OperationType.CREATE).first()
            request, created = Request.objects.get_or_create(
                instance=instance,
                operation=operation,
                defaults={
                    "user": user,
                    "fill_in_survey": {"vcpu": 2, "memory": 4096, "environment": "dev"},
                },
            )
            if created:
                request.state = state
                request.save()

    def create_supports(self, instances, users):
        support_specs = [
            ("Disk usage above 90%", "web-frontend-01"),
            ("Cannot reach the instance over SSH", "batch-worker-01"),
            ("Please increase the connection limit", "reporting-db"),
        ]
        for title, instance_name in support_specs:
            Support.objects.get_or_create(
                title=title,
                instance=instances[instance_name],
                defaults={"opened_by": users["alice"]},
            )

    def create_resource_tracking(self, scopes, instances):
        attributes = {}
        for name, description in [("vCPU", "Virtual CPU"), ("Memory", "Memory in GB"), ("Storage", "Storage in GB")]:
            attributes[name], _ = AttributeDefinition.objects.get_or_create(
                name=name, defaults={"description": description}
            )
        cluster, _ = ResourceGroup.objects.get_or_create(name="VMware cluster")
        servers, _ = ResourceGroup.objects.get_or_create(name="Physical servers")

        for attribute_name in ["vCPU", "Memory", "Storage"]:
            Transformer.objects.get_or_create(
                resource_group=servers,
                attribute_definition=attributes[attribute_name],
            )
            Transformer.objects.get_or_create(
                resource_group=cluster,
                attribute_definition=attributes[attribute_name],
                defaults={
                    "consume_from_resource_group": servers,
                    "consume_from_attribute_definition": attributes[attribute_name],
                },
            )

        for host_name, values in [
            ("esx-01", {"vCPU": 64, "Memory": 256, "Storage": 4096}),
            ("esx-02", {"vCPU": 64, "Memory": 256, "Storage": 4096}),
        ]:
            resource = servers.create_resource(host_name)
            for attribute_name, value in values.items():
                resource.set_attribute(attributes[attribute_name], value)

        for vm_name, values in [
            ("web-frontend-01", {"vCPU": 4, "Memory": 8, "Storage": 100}),
            ("web-frontend-02", {"vCPU": 4, "Memory": 8, "Storage": 100}),
            ("batch-worker-01", {"vCPU": 8, "Memory": 32, "Storage": 500}),
        ]:
            resource = cluster.create_resource(vm_name)
            resource.service_catalog_instance = instances[vm_name]
            resource.save()
            for attribute_name, value in values.items():
                resource.set_attribute(attributes[attribute_name], value)

        for scope_name, limits in [
            ("Platform Engineering", {"vCPU": 128, "Memory": 512, "Storage": 8192}),
            ("Marketing", {"vCPU": 16, "Memory": 64, "Storage": 1024}),
        ]:
            for attribute_name, limit in limits.items():
                Quota.objects.get_or_create(
                    scope=Scope.objects.get(id=scopes[scope_name].id),
                    attribute_definition=attributes[attribute_name],
                    defaults={"limit": limit},
                )
