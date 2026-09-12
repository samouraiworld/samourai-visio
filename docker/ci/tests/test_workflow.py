"""Mutation acceptance tests for the local workflow adapter."""

import hashlib
import importlib.util
import unittest
from pathlib import Path
from unittest import mock

SPEC = importlib.util.spec_from_file_location(
    "workflow", Path(__file__).resolve().parents[1] / "workflow.py"
)
WORKFLOW = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WORKFLOW)


class WorkflowTests(unittest.TestCase):
    def test_unknown_action_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported action"):
            WORKFLOW.validate_step({"uses": "somewhere/new-action@v1"})

    def test_changed_python_version_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Python"):
            WORKFLOW.validate_step(
                {"uses": "actions/setup-python@sha", "with": {"python-version": "3.14"}}
            )

    def test_changed_helm_version_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Helm"):
            WORKFLOW.validate_step(
                {"uses": "azure/setup-helm@sha", "with": {"version": "4.0.0"}}
            )

    def test_changed_uv_version_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "uv image"):
            WORKFLOW.validate_step(
                {"uses": "astral-sh/setup-uv@sha", "with": {"version": "0.10.0"}}
            )

    def test_other_checkout_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "checkout options"):
            WORKFLOW.validate_step(
                {"uses": "actions/checkout@sha", "with": {"ref": "main"}}
            )

    def test_changed_node_version_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Node"):
            WORKFLOW.validate_step(
                {"uses": "actions/setup-node@sha", "with": {"node-version": "24"}}
            )

    def test_unknown_expression_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "expression"):
            WORKFLOW.expand("echo ${{ secrets.EXAMPLE }}", "origin/develop")

    def test_unknown_step_condition_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "condition"):
            WORKFLOW.validate_step(
                {"run": "false", "if": "github.event_name == 'push'"}
            )

    def test_changed_bootstrap_command_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Changed infrastructure"):
            WORKFLOW.validate_step({"name": "Start MinIO", "run": "exit 0"})

    def test_changed_minio_image_is_rejected(self):
        command = "true"
        with (
            mock.patch.dict(
                WORKFLOW.BOOTSTRAP,
                {"Start MinIO": hashlib.sha256(command.encode()).hexdigest()},
            ),
            self.assertRaisesRegex(ValueError, "Changed MinIO image"),
        ):
            WORKFLOW.validate_step(
                {
                    "name": "Start MinIO",
                    "run": command,
                    "env": {"MINIO_IMAGE": "minio/minio:latest"},
                }
            )

    def test_missing_dependency_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "dependency"):
            WORKFLOW.job_order({"test": {"needs": "missing"}})

    def test_cyclic_dependency_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "dependency"):
            WORKFLOW.job_order({"test": {"needs": "test"}})

    def test_dependency_order_is_preserved(self):
        self.assertEqual(
            WORKFLOW.job_order({"test": {"needs": "build"}, "build": {}}),
            ["build", "test"],
        )

    def test_unknown_shell_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported shell"):
            WORKFLOW.validate_step({"run": "false", "shell": "pwsh"})

    def test_continue_on_error_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "continue-on-error"):
            WORKFLOW.validate_step({"run": "false", "continue-on-error": True})

    def test_new_service_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "service image"):
            WORKFLOW.validate_job({"services": {"search": {"image": "search:1"}}})

    def test_changed_service_version_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "service image"):
            WORKFLOW.validate_job({"services": {"postgres": {"image": "postgres:17"}}})

    def test_unknown_job_condition_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "job condition"):
            WORKFLOW.validate_job({"if": "false"})

    def test_special_job_execution_is_rejected(self):
        for field in ["strategy", "uses", "container"]:
            with (
                self.subTest(field=field),
                self.assertRaisesRegex(ValueError, "Matrix"),
            ):
                WORKFLOW.validate_job({field: {}})

    def test_other_operating_system_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "operating system"):
            WORKFLOW.validate_job({"runs-on": "windows-latest"})

    def test_new_browser_command_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "browser workflow command"):
            WORKFLOW.validate_e2e_job({"steps": [{"run": "npm test"}]})

    def test_missing_step_command_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "neither uses nor run"):
            WORKFLOW.validate_step({"name": "Missing command"})

    def test_unsafe_base_ref_is_rejected(self):
        for base in ["--help", "HEAD; true", "$(id)"]:
            with (
                self.subTest(base=base),
                self.assertRaisesRegex(ValueError, "Invalid base"),
            ):
                WORKFLOW.validate_base(base)

    def test_expected_expression_is_expanded(self):
        self.assertEqual(
            WORKFLOW.expand(
                "git diff origin/${{ github.event.pull_request.base.ref }}...HEAD",
                "origin/develop",
            ),
            "git diff origin/develop...HEAD",
        )

    def test_new_command_is_preserved(self):
        step = {"run": "exit 23"}
        WORKFLOW.validate_step(step)
        self.assertEqual(step["run"], "exit 23")


if __name__ == "__main__":
    unittest.main()
