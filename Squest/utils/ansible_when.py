import logging

from jinja2 import TemplateSyntaxError
from jinja2.exceptions import SecurityError
from jinja2.sandbox import ImmutableSandboxedEnvironment

logger = logging.getLogger(__name__)


class AnsibleWhen(object):
    _environment = ImmutableSandboxedEnvironment()

    @classmethod
    def when_render(cls, context, when_string):
        if when_string is None or when_string == "" or context is None:
            return False
        template_string = "{% if " + when_string + " %}True{% else %}{% endif %}"
        try:
            template = cls._environment.from_string(template_string)
        except TemplateSyntaxError:
            logger.warning(f"when_render error when templating: {context} with string '{when_string}'")
            return False
        try:
            template_rendered = template.render(context)
            return bool(template_rendered)
        except SecurityError:
            logger.warning(f"when_render blocked unsafe expression: '{when_string}'")
            return False
        except Exception:
            logger.warning(f"when_render error when templating: {context} with string '{when_string}'")
            return False
