import logging

from jinja2 import UndefinedError, TemplateSyntaxError
from jinja2.sandbox import ImmutableSandboxedEnvironment, SecurityError

logger = logging.getLogger(__name__)


def _get_sandboxed_environment():
    """
    Jinja environment used to evaluate user provided 'when' expressions.
    The environment is sandboxed and stripped from its default globals
    (lipsum, cycler, joiner, namespace, range...) that are commonly used to
    escape the sandbox and reach the Python runtime.
    """
    environment = ImmutableSandboxedEnvironment()
    environment.globals.clear()
    return environment


SANDBOXED_ENVIRONMENT = _get_sandboxed_environment()


class AnsibleWhen(object):

    @classmethod
    def when_render(cls, context, when_string):
        if when_string is None or when_string == "" or context is None:
            return False
        template_string = "{% if " + when_string + " %}True{% else %}{% endif %}"
        try:
            template = SANDBOXED_ENVIRONMENT.from_string(template_string)
        except TemplateSyntaxError:
            logger.warning(f"when_render error when templating: {context} with string '{when_string}'")
            return False
        try:
            template_rendered = template.render(context)
            return bool(template_rendered)
        except UndefinedError:
            logger.warning(f"when_render error when templating: {context} with string '{when_string}'")
            return False
        except SecurityError:
            logger.warning(f"when_render blocked an unsafe operation when templating: {context} "
                           f"with string '{when_string}'")
            return False
