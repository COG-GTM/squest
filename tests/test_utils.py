import unittest
from unittest import mock

from Squest.utils.ansible_when import AnsibleWhen
from service_catalog.utils import str_to_bool, get_mysql_dump_major_version, \
    get_celery_crontab_parameters_from_crontab_line, get_images_link_from_markdown, \
    humanize_bytes, mask_sensitive_keys, truncate_string


class TestUtils(unittest.TestCase):

    def test_str_to_bool(self):
        self.assertTrue(str_to_bool("True"))
        self.assertTrue(str_to_bool("true"))
        self.assertTrue(str_to_bool(True))
        self.assertTrue(str_to_bool(1))
        self.assertTrue(str_to_bool("1"))
        self.assertFalse(str_to_bool("False"))
        self.assertFalse(str_to_bool("false"))
        self.assertFalse(str_to_bool(False))
        self.assertFalse(str_to_bool(0))
        self.assertFalse(str_to_bool("0"))

    @mock.patch('os.popen')
    def test_get_mysql_dump_major_version(self, mock_os_popen):
        map_test = {
            "mysqldump  Ver 8.0.26-0ubuntu0.20.04.2 for Linux on x86_64 ((Ubuntu))": 8,  # Ubuntu 20.04
            "mysqldump  Ver 10.19 Distrib 10.5.11-MariaDB, for debian-linux-gnu (x86_64)": 10,  # Debian Bullseye
            "mysqldump  Ver 10.19 Distrib 10.3.29-MariaDB, for debian-linux-gnu (x86_64)": 10,  # Debian Buster
            "mysqldump  Ver 12": 12,
            "mysqldump  Ver 101": 101,
            "other": None
        }

        for version_output, expected_result in map_test.items():
            process_mock = mock.Mock()
            attrs = {'read.return_value': version_output}
            process_mock.configure_mock(**attrs)
            mock_os_popen.return_value = process_mock
            self.assertEqual(get_mysql_dump_major_version(), expected_result)

    def test_get_celery_crontab_parameters_from_crontab_line(self):
        map_test = {
            "0 1 * * *": {
                "minute": "0",
                "hour": "1",
                "day_of_week": "*",
                "day_of_month": "*",
                "month_of_year": "*"
            },
            "1,4 1 * * *": {
                "minute": "1,4",
                "hour": "1",
                "day_of_week": "*",
                "day_of_month": "*",
                "month_of_year": "*"
            }
        }
        for crontab_line, expected_result in map_test.items():
            self.assertEqual(get_celery_crontab_parameters_from_crontab_line(crontab_line),
                              expected_result)

    def test_regex_for_media_cleanup(self):

        test_str = """
# Delete Images test
![Single picture on a line](/media/doc_images/uploads/to_be_kept1.jpg)
TextBefore ![Single picture on a line with text before](/media/doc_images/uploads/to_be_kept2.jpg)
![Single picture on a line with text after](/media/doc_images/uploads/to_be_kept3.jpg) Text after
TextBefore ![Single picture on a line with text before and after](/notmedia/doc_images/uploads/non_deleted.jpg) Text after
![Single picture on a line on /media](/media/doc_images/google/doc_images/uploads/to_be_kept4.jpg)
![First picture of the line](/media/doc_images/google/doc_images/uploads/to_be_kept5.jpg)Random![Second picture of the line](/media/doc_images/google/doc_images/uploads/to_be_kept6.jpg)
![Single picture on a line with space between] (/media/doc_images/uploads/picturelink.jpg)
![Single picture on a line with text between  ]eeeee(/media/doc_images/uploads/picturelink.jpg)
![Single picture on a line but not on /media/doc_images](/google/doc_images/uploads/picturelink.jpg) Text after
![Single picture on a line from google with /media/doc_images in path](https://google/media/doc_images/uploads/picturelink.jpg) 
"""
        list_expected = ['to_be_kept1.jpg',
                         'to_be_kept2.jpg',
                         'to_be_kept3.jpg',
                         'to_be_kept4.jpg',
                         'to_be_kept5.jpg',
                         'to_be_kept6.jpg']

        list_of_media = get_images_link_from_markdown(test_str)
        self.assertListEqual(list_expected, list_of_media)

    def test_humanize_bytes(self):
        self.assertEqual(humanize_bytes(None), "0 B")
        self.assertEqual(humanize_bytes(0), "0 B")
        self.assertEqual(humanize_bytes(512), "512 B")
        self.assertEqual(humanize_bytes(1023), "1023 B")
        self.assertEqual(humanize_bytes(1024), "1.0 KB")
        self.assertEqual(humanize_bytes(1536), "1.5 KB")
        self.assertEqual(humanize_bytes(1536, precision=3), "1.500 KB")
        self.assertEqual(humanize_bytes(1024 ** 2), "1.0 MB")
        self.assertEqual(humanize_bytes(1024 ** 3), "1.0 GB")
        self.assertEqual(humanize_bytes(1024 ** 4), "1.0 TB")
        self.assertEqual(humanize_bytes(1024 ** 5), "1.0 PB")
        # capped at the largest unit
        self.assertEqual(humanize_bytes(1024 ** 6), "1024.0 PB")

    def test_mask_sensitive_keys(self):
        data = {
            "username": "admin",
            "password": "secret_value",
            "Token": "abc",
            "nested": {
                "api_key": "key",
                "count": 3
            },
            "list": [{"secret": "s"}, "plain", 42],
            1: "not_a_string_key"
        }
        expected = {
            "username": "admin",
            "password": "******",
            "Token": "******",
            "nested": {
                "api_key": "******",
                "count": 3
            },
            "list": [{"secret": "******"}, "plain", 42],
            1: "not_a_string_key"
        }
        self.assertEqual(mask_sensitive_keys(data), expected)
        # original dict is not modified
        self.assertEqual(data["password"], "secret_value")
        # custom sensitive keys
        self.assertEqual(mask_sensitive_keys({"custom": "v", "password": "p"}, sensitive_keys=["custom"]),
                         {"custom": "******", "password": "p"})
        # non dict/list values returned as is
        self.assertEqual(mask_sensitive_keys("plain"), "plain")
        self.assertIsNone(mask_sensitive_keys(None))

    def test_truncate_string(self):
        self.assertEqual(truncate_string(None), "")
        self.assertEqual(truncate_string("short"), "short")
        self.assertEqual(truncate_string("a" * 50), "a" * 50)
        self.assertEqual(truncate_string("a" * 51), "a" * 47 + "...")
        self.assertEqual(truncate_string("abcdefghij", max_length=5), "ab...")
        self.assertEqual(truncate_string("abcdefghij", max_length=5, suffix="!"), "abcd!")
        # suffix as long as (or longer than) max_length: hard cut without suffix
        self.assertEqual(truncate_string("abcdefghij", max_length=3), "abc")
        self.assertEqual(truncate_string("abcdefghij", max_length=2, suffix="..."), "ab")

    def test_when_render(self):
        # None context
        context = None
        when_string = "test"
        self.assertFalse(AnsibleWhen.when_render(context, when_string))

        # None when_string
        context = {}
        when_string = None
        self.assertFalse(AnsibleWhen.when_render(context, when_string))

        # valid context
        context = {"instance": {"name": "test"}}
        when_string = "instance.name == 'test'"
        self.assertTrue(AnsibleWhen.when_render(context, when_string))

        # valid context but searched key not equal
        when_string = "instance.name == 'other'"
        self.assertFalse(AnsibleWhen.when_render(context, when_string))

        # invalid context
        context = {"random_key": {"name": "test"}}
        when_string = "instance.name == 'test'"
        self.assertFalse(AnsibleWhen.when_render(context, when_string))
