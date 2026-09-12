"""Execute CI shell steps using local equivalents of hosted setup actions."""

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# These infrastructure steps are supplied by the image and Compose health checks.
# Match their content so workflow changes cannot silently bypass a new command.
BOOTSTRAP = {
    "Create writable /data": "75b5819eac64805e03fe8351aabb293c9a569a04175b12e8ad8384387a815de1",
    "Start MinIO": "3b87b7e1592a03b63728cfa111e8878782ce8148fffece7f53ad66c57e74ad74",
    "Install Dockerize": "4b9e0abd0f7af52ce4c642e006b028544e94cf8bde7b7497d290a2b7b053f183",
    "Wait for MinIO to be ready": "3e406ff42604d2ea6c29f9ee33813532a05776561d5a34a83ef06f977d1a2ee4",
    "Configure MinIO": "8d337bdcbe5584ee89b50c140b5fd121286435f8615bb37b4803955788f58176",
    "Install gettext (required to compile messages)": "f635fedbed55f1bb70ee6ee82c35d68944632b2bda49a0fb11b6f358edf957a8",
    "Install ffmpeg": "035f1c7552c0cfb6efc03d7ac9363d264f973547ee669a65134b09ca1f51beb1",
}
MINIO_IMAGE = "quay.io/minio/minio@sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e"
ACTIONS = {
    "actions/checkout",
    "actions/cache",
    "actions/setup-node",
    "actions/setup-python",
    "astral-sh/setup-uv",
    "azure/setup-helm",
}
CONDITIONS = {None, "always()", "steps.mail-templates.outputs.cache-hit != 'true'"}
JOB_CONDITIONS = {
    None,
    "github.event_name == 'pull_request'",
    "contains(github.event.pull_request.labels.*.name, 'noChangeLog') == false && github.event_name == 'pull_request'",
}


def expand(command, base):
    """Resolve the explicit PR context supported by local runs."""
    replacements = {
        "origin/${{ github.event.pull_request.base.ref }}": base,
        "${{ github.event.pull_request.base.sha }}": base,
        "${{ github.event.after }}": "HEAD",
    }
    for expression, value in replacements.items():
        command = command.replace(expression, value)
    if "${{" in command:
        raise ValueError("Unsupported workflow expression: " + command)
    return command


def validate_step(step):
    """Reject unmapped hosted-runner semantics before executing any checks."""
    if step.get("if") not in CONDITIONS:
        raise ValueError("Unsupported step condition: " + str(step.get("if")))
    if "uses" in step:
        action = step["uses"].split("@", 1)[0]
        if action not in ACTIONS:
            raise ValueError("Unsupported action: " + action)
        options = step.get("with", {})
        if action == "actions/checkout" and set(options) - {"fetch-depth"}:
            raise ValueError("Unsupported checkout options")
        if (
            action == "azure/setup-helm"
            and options.get("version", "3.19.0") != "3.19.0"
        ):
            raise ValueError("Helm image version must match the workflow")
        if (
            action == "astral-sh/setup-uv"
            and options.get("version", "0.9.26") != "0.9.26"
        ):
            raise ValueError("uv image version must match the workflow")
        if (
            action == "actions/setup-python"
            and str(options.get("python-version")) != "3.13"
        ):
            raise ValueError("Python image version must match the workflow")
        if action == "actions/setup-node" and str(options.get("node-version")) != "22":
            raise ValueError("Node image version must match the workflow")
    elif "run" not in step:
        raise ValueError("Step has neither uses nor run")
    name = step.get("name")
    if name in BOOTSTRAP:
        digest = hashlib.sha256(step["run"].encode()).hexdigest()
        if digest != BOOTSTRAP[name]:
            raise ValueError(
                "Changed infrastructure step needs a local mapping: " + name
            )
    if name == "Start MinIO" and step.get("env") != {"MINIO_IMAGE": MINIO_IMAGE}:
        raise ValueError("Changed MinIO image needs a local mapping")
    if step.get("continue-on-error") or step.get("shell", "bash") != "bash":
        raise ValueError("Unsupported shell or continue-on-error semantics")


def job_order(jobs):
    """Keep workflow dependencies while retaining readable workflow order."""
    pending = dict(jobs)
    ordered = []
    while pending:
        ready = [
            name
            for name, job in pending.items()
            if all(dependency in ordered for dependency in dependencies(job))
        ]
        if not ready:
            raise ValueError("Missing or cyclic workflow dependency")
        for name in ready:
            ordered.append(name)
            del pending[name]
    return ordered


def dependencies(job):
    value = job.get("needs", [])
    return [value] if isinstance(value, str) else value


def validate_job(job):
    """Keep hosted execution semantics and service versions explicit."""
    condition = job.get("if")
    condition = " ".join(condition.split()) if condition else None
    if condition not in JOB_CONDITIONS:
        raise ValueError("Unsupported job condition: " + str(condition))
    if "strategy" in job or "uses" in job or "container" in job:
        raise ValueError("Matrix/reusable/container jobs need explicit local support")
    if job.get("runs-on", "ubuntu-latest") != "ubuntu-latest":
        raise ValueError("Unsupported runner operating system")
    expected_services = {"postgres": "postgres:16", "redis": "redis:5"}
    for name, service in job.get("services", {}).items():
        if (
            name not in expected_services
            or service.get("image") != expected_services[name]
        ):
            raise ValueError("Unsupported service image: " + name)


def validate_e2e_job(job):
    """The host wrapper owns only the two documented browser entry points."""
    validate_job(job)
    allowed = {
        "docker/e2e/test-runner.sh",
        "bin/test-e2e-local",
        "python3 -m unittest discover -s docker/ci/tests",
    }
    for step in job.get("steps", []):
        if step.get("uses", "").startswith("actions/upload-artifact@"):
            continue
        validate_step(step)
        for command in step.get("run", "").strip().splitlines():
            if command.removeprefix("./") not in allowed:
                raise ValueError("Unsupported browser workflow command: " + command)


def validate_base(base):
    """Refs become shell text only after restricting their character set."""
    if not re.fullmatch(r"[A-Za-z0-9_./-]+", base) or base.startswith("-"):
        raise ValueError("Invalid base ref")


def main():
    import yaml

    base = os.environ.get("CI_LOCAL_BASE", "origin/develop")
    validate_base(base)
    with Path(".github/workflows/ci.yml").open() as stream:
        jobs = yaml.safe_load(stream)["jobs"]
    # Browser orchestration runs on the host after these jobs, avoiding nested Docker.
    browser_job = jobs.pop("test-e2e", None)
    if browser_job:
        validate_e2e_job(browser_job)
    for job in jobs.values():
        validate_job(job)
        for step in job["steps"]:
            validate_step(step)
            if "run" in step:
                expand(step["run"], base)
    Path(os.environ["HOME"]).mkdir(parents=True, exist_ok=True)
    Path("/data/media").mkdir(parents=True, exist_ok=True)
    Path("/data/static").mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "docker/ci/tests"],
        check=True,
    )
    outcomes = {}
    for name in job_order(jobs):
        job = jobs[name]
        if any(outcomes[dependency] != "passed" for dependency in dependencies(job)):
            outcomes[name] = "blocked"
            continue
        sys.stdout.write("\n=== " + name + " ===\n")
        sys.stdout.flush()
        environment = dict(
            os.environ, **{key: str(value) for key, value in job.get("env", {}).items()}
        )
        if name == "test-back":
            environment.update(
                DB_HOST="postgres",
                REDIS_URL="redis://redis:6379/1",
                AWS_S3_ENDPOINT_URL="http://minio:9000",
            )
        working = job.get("defaults", {}).get("run", {}).get("working-directory", ".")
        passed = True
        with Path("/reports", name + ".log").open("w") as log:
            for step in job["steps"]:
                if "run" not in step or step.get("name") in BOOTSTRAP:
                    continue
                if not passed and step.get("if") != "always()":
                    continue
                step_env = dict(
                    environment,
                    **{key: str(value) for key, value in step.get("env", {}).items()},
                )
                command = expand(step["run"], base)
                log.write("\n$ " + command + "\n")
                log.flush()
                result = subprocess.run(
                    ["bash", "-eo", "pipefail", "-c", command],
                    cwd=step.get("working-directory", working),
                    env=step_env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
                if result.returncode:
                    passed = False
                    sys.stdout.write("FAILED: " + step.get("name", command) + "\n")
                    sys.stdout.flush()
        outcomes[name] = "passed" if passed else "failed"
        sys.stdout.write(name + ": " + outcomes[name] + "\n")
        sys.stdout.flush()
    Path("/reports/results.json").write_text(json.dumps(outcomes, indent=2) + "\n")
    return int(any(outcome != "passed" for outcome in outcomes.values()))


if __name__ == "__main__":
    sys.exit(main())
