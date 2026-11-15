"""Pin tests."""

import json
import unittest

import pin


def line(built=None, commit=None):
    notes = {}
    if built:
        notes["build_timestamp"] = built
    if commit:
        notes["ports_top_git_hash"] = commit
    return json.dumps({"name": "x", "annotations": notes})


class NewestTestCase(unittest.TestCase):
    def test_the_commit_of_the_latest_build_wins(self):
        lines = [
            line("2026-10-24T01:06:11+0000", "aaa"),
            line("2026-11-13T21:13:55+0000", "ccc"),
            line("2026-11-05T01:03:51+0000", "bbb"),
        ]
        self.assertEqual(("ccc", "2026-11-13T21:13:55+0000"), pin.newest(lines))

    def test_packages_without_a_commit_are_ignored(self):
        lines = [
            line("2026-11-13T21:13:55+0000", None),
            line("2026-11-05T01:03:51+0000", "bbb"),
            json.dumps({"name": "y"}),
        ]
        self.assertEqual(("bbb", "2026-11-05T01:03:51+0000"), pin.newest(lines))

    def test_a_repo_without_any_commit_is_refused(self):
        self.assertRaises(ValueError, pin.newest, [line("2026-11-05T01:03:51+0000")])
