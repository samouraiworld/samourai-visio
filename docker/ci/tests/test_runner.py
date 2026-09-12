"""Exercise source isolation, cleanup, and real subprocess failure propagation."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

RUNNER = Path(__file__).resolve().parents[3] / "bin/test-ci-local"


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.repository = self.directory / "repository"
        (self.repository / "bin").mkdir(parents=True)
        shutil.copy2(RUNNER, self.repository / "bin/test-ci-local")
        (self.repository / "docker/e2e").mkdir(parents=True)
        for relative, name, status in [
            ("docker/e2e/test-runner.sh", "e2e-selftest", "E2E_SELFTEST_EXIT"),
            ("bin/test-e2e-local", "e2e", "E2E_EXIT"),
        ]:
            executable = self.repository / relative
            executable.write_text(
                '#!/bin/sh\nprintf "%s\\n" "'
                + name
                + '" >> "$CALL_LOG"\nexit "${'
                + status
                + ':-0}"\n'
            )
            executable.chmod(0o755)
        (self.repository / "fixture.txt").write_text("committed\n")
        (self.repository / "removed.txt").write_text("remove before testing\n")
        self.git("init", "-b", "fix/local-ci-fixture")
        self.git("add", ".")
        self.git(
            "-c",
            "user.name=CI test",
            "-c",
            "user.email=ci@example.test",
            "commit",
            "-m",
            "Exercise local execution failures",
        )
        (self.repository / "fixture.txt").write_text("working change\n")
        self.git("rm", "removed.txt")
        self.fake_bin = self.directory / "fake-bin"
        self.fake_bin.mkdir()
        fake = self.fake_bin / "docker"
        fake.write_text("""#!/bin/sh
set -eu
printf '%s\\n' "$*" >> "$CALL_LOG"
case " $* " in
  *" info "*) exit "${INFO_EXIT:-0}" ;;
  *" version "*) exit "${VERSION_EXIT:-0}" ;;
  *" build "*) exit "${BUILD_EXIT:-0}" ;;
  *" run "*)
    test "$(cat "$CI_LOCAL_SNAPSHOT/fixture.txt")" = "working change"
    test ! -e "$CI_LOCAL_SNAPSHOT/removed.txt"
    printf '%s' "$CI_LOCAL_SNAPSHOT" > "$SNAPSHOT_FILE"
    exit "${RUN_EXIT:-0}" ;;
  *" down "*) exit "${DOWN_EXIT:-0}" ;;
esac
""")
        fake.chmod(0o755)
        self.environment = dict(
            os.environ,
            PATH=str(self.fake_bin) + os.pathsep + os.environ["PATH"],
            CALL_LOG=str(self.directory / "calls"),
            SNAPSHOT_FILE=str(self.directory / "snapshot"),
            TMPDIR=str(self.directory),
        )

    def git(self, *arguments):
        subprocess.run(
            ["git", *arguments],
            cwd=self.repository,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def execute(self, skip_e2e=True, **overrides):
        environment = dict(self.environment, **overrides)
        command = [str(self.repository / "bin/test-ci-local"), "--base", "HEAD"]
        if skip_e2e:
            command.append("--skip-e2e")
        return subprocess.run(
            command,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

    def assert_cleaned(self):
        self.assertIn(" down ", " " + (self.directory / "calls").read_text())
        self.assertEqual(
            (self.repository / "fixture.txt").read_text(), "working change\n"
        )
        self.assertEqual(list(self.directory.glob("visio-ci-workspace-*")), [])

    def test_unavailable_docker_is_rejected_before_snapshot(self):
        result = self.execute(INFO_EXIT="11")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(list(self.directory.glob("visio-ci-workspace-*")), [])
        self.assertNotIn(" build ", " " + (self.directory / "calls").read_text())

    def test_missing_compose_is_rejected_before_snapshot(self):
        result = self.execute(VERSION_EXIT="11")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(list(self.directory.glob("visio-ci-workspace-*")), [])
        self.assertNotIn(" build ", " " + (self.directory / "calls").read_text())

    def test_missing_base_is_rejected_before_docker(self):
        result = subprocess.run(
            [str(self.repository / "bin/test-ci-local"), "--base", "missing-ref"],
            env=self.environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.directory / "calls").exists())

    def test_default_includes_browser_acceptance(self):
        result = self.execute(skip_e2e=False)
        self.assertEqual(result.returncode, 0, result.stdout)
        calls = (self.directory / "calls").read_text().splitlines()
        self.assertIn("e2e-selftest", calls)
        self.assertIn("e2e", calls)
        self.assert_cleaned()

    def test_browser_failure_is_not_reported_as_success(self):
        result = self.execute(skip_e2e=False, E2E_EXIT="29")
        self.assertEqual(result.returncode, 29, result.stdout)
        self.assert_cleaned()

    def test_ci_failure_blocks_browser_execution(self):
        result = self.execute(skip_e2e=False, RUN_EXIT="23")
        self.assertEqual(result.returncode, 23, result.stdout)
        self.assertNotIn("e2e", (self.directory / "calls").read_text().splitlines())
        self.assert_cleaned()

    def test_success_tests_working_files_and_cleans(self):
        result = self.execute()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assert_cleaned()

    def test_failed_check_is_not_reported_as_success(self):
        result = self.execute(RUN_EXIT="23")
        self.assertEqual(result.returncode, 23, result.stdout)
        self.assert_cleaned()

    def test_failed_build_still_cleans(self):
        result = self.execute(BUILD_EXIT="17")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assert_cleaned()

    def test_failed_cleanup_is_not_reported_as_success(self):
        result = self.execute(DOWN_EXIT="19")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assert_cleaned()


if __name__ == "__main__":
    unittest.main()
