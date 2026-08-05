import contextlib
import io
import tempfile
from pathlib import Path
from unittest import mock

from django.test import TestCase

from scripts import check_static_refs


class CheckStaticRefsTest(TestCase):

    def setUp(self):
        super(CheckStaticRefsTest, self).setUp()
        self.root = Path(tempfile.mkdtemp())
        templates = self.root / "templates" / "nested"
        templates.mkdir(parents=True)
        (templates / "page.html").write_text(
            '{% load static %}\n'
            '<link href="{% static \'squest/css/squest.css\' %}">\n'
            '<script src="{% static "squest/js/squest.js" %}"></script>\n'
        )

    def run_main(self):
        output = io.StringIO()
        with mock.patch.object(check_static_refs, "ROOT", self.root):
            with contextlib.redirect_stdout(output):
                returned_code = check_static_refs.main()
        return returned_code, output.getvalue()

    def test_static_ref_regex(self):
        self.assertEqual(
            ["squest/css/squest.css"],
            check_static_refs.STATIC_REF.findall('<link href="{% static \'squest/css/squest.css\' %}">')
        )
        self.assertEqual([], check_static_refs.STATIC_REF.findall('<link href="/squest/css/squest.css">'))

    def test_main_without_missing_static(self):
        with mock.patch.object(check_static_refs.finders, "find", return_value="/found") as find:
            returned_code, output = self.run_main()
        self.assertEqual(0, returned_code)
        self.assertIn("Checked 2 distinct static paths.", output)
        self.assertIn("No missing static paths.", output)
        self.assertEqual(
            {"squest/css/squest.css", "squest/js/squest.js"},
            {call.args[0] for call in find.call_args_list}
        )

    def test_main_with_missing_static(self):
        with mock.patch.object(check_static_refs.finders, "find", return_value=None):
            returned_code, output = self.run_main()
        self.assertEqual(1, returned_code)
        self.assertIn("Missing static paths:", output)
        self.assertIn("- squest/css/squest.css: templates/nested/page.html:2", output)
        self.assertIn("- squest/js/squest.js: templates/nested/page.html:3", output)

    def test_main_reports_every_location_of_a_missing_static(self):
        (self.root / "templates" / "other.html").write_text(
            '{% static "squest/css/squest.css" %}\n'
        )
        with mock.patch.object(check_static_refs.finders, "find", return_value=None):
            returned_code, output = self.run_main()
        self.assertEqual(1, returned_code)
        # rglob does not guarantee an order, so only the reported set of locations is asserted
        reported = next(line for line in output.splitlines() if line.startswith("- squest/css/squest.css:"))
        self.assertEqual(
            {"templates/nested/page.html:2", "templates/other.html:1"},
            set(reported.split(": ", 1)[1].split(", "))
        )

    def test_main_rejects_leading_slash(self):
        (self.root / "templates" / "absolute.html").write_text('{% static "/squest/css/absolute.css" %}\n')
        with mock.patch.object(check_static_refs.finders, "find", return_value="/found") as find:
            returned_code, output = self.run_main()
        self.assertEqual(1, returned_code)
        self.assertIn("- /squest/css/absolute.css: templates/absolute.html:1", output)
        self.assertIn("/squest/css/absolute.css", {call.args[0] for call in find.call_args_list})
