import os
import re


def get_orderable_services_for_user(user, parent_portfolio_id=None, filter_by_portfolio=True):
    # imports are local: this module is imported by Squest.settings, before the app registry is ready
    from django.db.models import Q

    from profiles.models import Permission
    from service_catalog.models import Operation, OperationType, Service

    permission_filter = Q(
        operation__enabled=True,
        operation__type=OperationType.CREATE,
    )
    if filter_by_portfolio:
        permission_filter &= Q(
            operation__service__parent_portfolio__id=parent_portfolio_id
        )

    service_ids = []
    for permission in Permission.objects.filter(permission_filter).distinct():
        service_ids.extend(
            Operation.get_queryset_for_user_filtered(
                user,
                permission.permission_str,
            ).filter(
                permission=permission,
                enabled=True,
                type=OperationType.CREATE,
            ).values_list("service__id", flat=True)
        )

    service_filter = Q(id__in=service_ids, enabled=True)
    if filter_by_portfolio:
        service_filter &= Q(parent_portfolio__id=parent_portfolio_id)
    return Service.objects.filter(service_filter)


def str_to_bool(s):
    if isinstance(s, bool):  # do not convert if already a boolean
        return s
    else:
        if s == 'True' \
                or s == 'true' \
                or s == '1' \
                or s == 1 \
                or s == True:
            return True
        elif s == 'False' \
                or s == 'false' \
                or s == '0' \
                or s == 0 \
                or s == False:
            return False
    return False


def get_mysql_dump_major_version():
    """
    Return the major version of the mysqldump command. E.g: 8
    """
    stream = os.popen('mysqldump --version')
    output = stream.read()
    regex = r"mysqldump\s+Ver\s(?P<version>\d+).*"
    matches = re.search(regex, output)
    if matches:
        if matches.group("version") is not None:
            return int(matches.group("version"))
    return None


def get_celery_crontab_parameters_from_crontab_line(crontab_line):
    """
    Get a crontab line line '0 1 * * *' and return a dict that can be used in the Celery crontab scheduler

    """
    line_split_on_space = crontab_line.split()
    return {
        "minute": line_split_on_space[0],
        "hour": line_split_on_space[1],
        "day_of_week": line_split_on_space[2],
        "day_of_month": line_split_on_space[3],
        "month_of_year": line_split_on_space[4]
    }


def get_images_link_from_markdown(markdown_text):
    regex = r"!\[[^\]]*\]\((\/media\/doc_images\/.*?)\s*(\"(?:.*[^\"])\")?\s*\)"
    file_paths = [x.group(1) for x in re.finditer(regex, markdown_text, re.MULTILINE)]
    list_file_name = list()
    for file_path in file_paths:
        list_file_name.append(os.path.basename(file_path))
    return list_file_name
