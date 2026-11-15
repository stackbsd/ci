"""Snapshot tests."""

import pathlib
import subprocess
import tempfile
import unittest

import snapshot

SUBDIR = snapshot.DIST_SUBDIR
MAKEFILE = (
    "PORTNAME=\tnova-bhyve\n"
    "DISTVERSION=\t0.9.4\n"
    "PORTREVISION=\t2\n"
    "CATEGORIES=\tnet python\n"
)


class VersionTestCase(unittest.TestCase):
    def test_commits_after_the_tag_extend_the_version(self):
        self.assertEqual("0.9.5.54", snapshot.version_from("v0.9.5-54-gc8bbf16"))

    def test_the_tagged_commit_keeps_the_tag_version(self):
        self.assertEqual("0.9.1", snapshot.version_from("v0.9.1-0-g0cee66c"))

    def test_a_tag_that_is_not_a_version_is_refused(self):
        for bad in ("v0.9.5", "release-1-2-gabc", "v1.0rc1-3-gabc", ""):
            self.assertRaises(snapshot.SnapshotError, snapshot.version_from, bad)


class StampTestCase(unittest.TestCase):
    def test_distversion_is_replaced_and_portrevision_dropped(self):
        self.assertEqual(
            "PORTNAME=\tnova-bhyve\n"
            "DISTVERSION=\t0.9.4.9\n"
            "DIST_SUBDIR=\tstackbsd-snapshot\n"
            "CATEGORIES=\tnet python\n",
            snapshot.stamp_makefile(MAKEFILE, "0.9.4.9"),
        )

    def test_a_makefile_without_distversion_is_refused(self):
        self.assertRaises(
            snapshot.SnapshotError, snapshot.stamp_makefile, "PORTNAME=\tx\n", "1.0"
        )

    def test_a_makefile_with_its_own_dist_subdir_is_refused(self):
        text = MAKEFILE + "DIST_SUBDIR=\tx\n"
        self.assertRaises(snapshot.SnapshotError, snapshot.stamp_makefile, text, "1.0")

    def test_distinfo_names_the_distfile(self):
        snap = snapshot.Snapshot(
            name="nova-bhyve",
            port="net/nova-bhyve",
            commit="0" * 40,
            timestamp=1794434097,
            version="0.9.4.9",
            distfile="nova_bhyve-0.9.4.9.tar.gz",
            sha256="ab" * 32,
            size=33396,
        )
        self.assertEqual(
            "TIMESTAMP = 1794434097\n"
            f"SHA256 (stackbsd-snapshot/nova_bhyve-0.9.4.9.tar.gz) = {'ab' * 32}\n"
            "SIZE (stackbsd-snapshot/nova_bhyve-0.9.4.9.tar.gz) = 33396\n",
            snapshot.distinfo(snap),
        )


class SourcesTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = pathlib.Path(tmp.name) / "sources.toml"
        self.path.write_text('[a]\nurl = "https://example.org/a"\nport = "net/a"\n')

    def test_sources_default_to_main(self):
        self.assertEqual(
            [snapshot.Source("a", "https://example.org/a", "net/a", "main")],
            snapshot.load_sources(self.path, {}, {}),
        )

    def test_overrides_replace_the_url_and_ref(self):
        self.assertEqual(
            [snapshot.Source("a", "/src/a", "net/a", "topic")],
            snapshot.load_sources(self.path, {"a": "/src/a"}, {"a": "topic"}),
        )

    def test_an_override_for_an_unknown_source_is_refused(self):
        self.assertRaises(
            snapshot.SnapshotError, snapshot.load_sources, self.path, {}, {"b": "x"}
        )

    def test_a_malformed_override_is_refused(self):
        for bad in ("a", "=x", "a="):
            self.assertRaises(snapshot.SnapshotError, snapshot.pairs, [bad])


class TakeTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = pathlib.Path(tmp.name)
        self.repo = self.tmp / "repo"
        (self.repo / "src" / "demo_pkg").mkdir(parents=True)
        (self.repo / "src" / "demo_pkg" / "__init__.py").write_text("")
        (self.repo / "README.md").write_text("demo\n")
        (self.repo / "pyproject.toml").write_text(
            "[project]\n"
            'name = "demo-pkg"\n'
            'version = "0.0.0"\n'
            'requires-python = ">=3.12"\n'
            "[build-system]\n"
            'requires = ["uv_build"]\n'
            'build-backend = "uv_build"\n'
        )
        self.git("init", "-q", "-b", "main")
        self.commit("first")
        self.git("tag", "v1.2.0")
        (self.repo / "README.md").write_text("demo two\n")
        self.commit("second")
        self.port = self.tmp / "ports" / "net" / "demo-pkg"
        self.port.mkdir(parents=True)
        (self.port / "Makefile").write_text(
            "PORTNAME=\tdemo-pkg\nDISTVERSION=\t1.2.0\n"
        )

    def git(self, *args):
        subprocess.run(
            ("git", "-c", "user.name=t", "-c", "user.email=t@example.org", *args),
            cwd=self.repo,
            check=True,
            capture_output=True,
        )

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def run_main(self, *extra):
        return snapshot.main(
            [
                "--ports", str(self.tmp / "ports"),
                "--distfiles", str(self.tmp / "distfiles"),
                "--work", str(self.tmp / "work"),
                "--sources", str(self.tmp / "sources.toml"),
                "--manifest", str(self.tmp / "manifest.json"),
                *extra,
            ]
        )  # fmt: skip

    def test_a_snapshot_stamps_the_port_and_writes_the_distfile(self):
        (self.tmp / "sources.toml").write_text(
            f'[demo-pkg]\nurl = "{self.repo}"\nport = "net/demo-pkg"\n'
        )
        self.assertEqual(0, self.run_main())
        distfile = self.tmp / "distfiles" / SUBDIR / "demo_pkg-1.2.0.1.tar.gz"
        self.assertTrue(distfile.exists())
        self.assertIn("DISTVERSION=\t1.2.0.1\n", (self.port / "Makefile").read_text())
        info = (self.port / "distinfo").read_text()
        self.assertIn(
            f"SIZE ({SUBDIR}/demo_pkg-1.2.0.1.tar.gz) = {distfile.stat().st_size}", info
        )
        self.assertIn('"version": "1.2.0.1"', (self.tmp / "manifest.json").read_text())

    def test_a_ref_override_builds_that_ref(self):
        (self.tmp / "sources.toml").write_text(
            f'[demo-pkg]\nurl = "{self.repo}"\nport = "net/demo-pkg"\n'
        )
        self.assertEqual(0, self.run_main("--ref", "demo-pkg=v1.2.0"))
        self.assertTrue(
            (self.tmp / "distfiles" / SUBDIR / "demo_pkg-1.2.0.tar.gz").exists()
        )

    def test_a_missing_port_fails(self):
        (self.tmp / "sources.toml").write_text(
            f'[demo-pkg]\nurl = "{self.repo}"\nport = "net/absent"\n'
        )
        self.assertEqual(1, self.run_main())
