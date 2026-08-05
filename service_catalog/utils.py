import os
import re


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


def humanize_bytes(size, precision=1):
    """
    Return a human readable string for a byte count. E.g: 1536 -> '1.5 KB'
    """
    if size is None:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(size)
    unit_index = 0
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    return f"{size:.{precision}f} {units[unit_index]}"


def mask_sensitive_keys(data, sensitive_keys=None):
    """
    Return a copy of a dict with values of sensitive keys replaced by '******'.
    Nested dicts and lists are processed recursively.
    """
    if sensitive_keys is None:
        sensitive_keys = ["password", "token", "secret", "api_key"]
    if isinstance(data, dict):
        masked = dict()
        for key, value in data.items():
            if isinstance(key, str) and any(sensitive in key.lower() for sensitive in sensitive_keys):
                masked[key] = "******"
            else:
                masked[key] = mask_sensitive_keys(value, sensitive_keys)
        return masked
    if isinstance(data, list):
        return [mask_sensitive_keys(item, sensitive_keys) for item in data]
    return data


def truncate_string(text, max_length=50, suffix="..."):
    """
    Truncate a string to max_length characters, appending a suffix when truncated.
    """
    if text is None:
        return ""
    if len(text) <= max_length:
        return text
    if max_length <= len(suffix):
        return text[:max_length]
    return text[:max_length - len(suffix)] + suffix


def get_images_link_from_markdown(markdown_text):
    regex = r"!\[[^\]]*\]\((\/media\/doc_images\/.*?)\s*(\"(?:.*[^\"])\")?\s*\)"
    file_paths = [x.group(1) for x in re.finditer(regex, markdown_text, re.MULTILINE)]
    list_file_name = list()
    for file_path in file_paths:
        list_file_name.append(os.path.basename(file_path))
    return list_file_name
