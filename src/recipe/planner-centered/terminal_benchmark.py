"""Run reviewed Terminal-Bench tasks in isolated Harbor workspaces."""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from contextvars import ContextVar
from functools import partial
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4

SOURCE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOURCE_ROOT))

from harbor.agents.base import BaseAgent
from harbor.environments.docker.docker import DockerEnvironment
from harbor.models.task.config import NetworkMode
from harbor.models.task.task import strip_canary
from harbor.models.task.verifier_mode import VerifierEnvironmentMode, resolve_task_verifier_mode
from harbor.models.trial.config import AgentConfig, EnvironmentConfig, TaskConfig, TrialConfig
from harbor.trial.trial import Trial
from runner import run_trial
from toolkit.envs.base import BaseEnv
from toolkit.prompt.executor.template import render_executor_prompt
from toolkit.rollout.state import State
from toolkit.rollout.terminalbench import load_terminalbench_trial
from toolkit.tasks.terminalbench import TerminalBenchTask
from toolkit.utils.files import write_json


RELEASE = "v4.1.0"
SOURCE_COMMIT = "4070d6cef56a7d20cb5dc98d5e10ada88a6b9440"
HARBOR_VERSION = "0.26.0"
MUSIC_TASK = "music-harmony"
FINANCE_TASK = "fin-saccr-rwa"
PHOTONIC_TASK = "photonic-waveguide-routing"
PRODUCTION_TASK = "production-planning"
SOUND_CHANGE_TASK = "sound-change-cascade"
MVCC_TASK = "mvcc-lsm-compaction"
VF2_TASK = "vf2-speedup-networkx"
BATCHED_TASK = "batched-eval-parity"
COQ_TASK = "coq-block-bound"
KS_TASK = "ks-solver-cpp"
DRIFT_TASK = "embedding-drift-monitor"
CARGO_TASK = "cargo-flight-dispatch"
ONTOLOGY_TASK = "ontology-kg-querying"
WAL_TASK = "wal-recovery-ordering"
RISK_TASK = "risk-scorer-replay"
REVIEWED_TASK_VERSIONS = {
    MUSIC_TASK: "2.2.1", FINANCE_TASK: "3.0.6", PHOTONIC_TASK: "2.1.1",
    PRODUCTION_TASK: "2.0.6", SOUND_CHANGE_TASK: "2.0.8", MVCC_TASK: "2.2.1", VF2_TASK: "3.2.1",
    BATCHED_TASK: "3.1.1", COQ_TASK: "2.1.0", KS_TASK: "2.2.1", DRIFT_TASK: "2.3.0", CARGO_TASK: "2.4.0",
    ONTOLOGY_TASK: "2.2.1", WAL_TASK: "2.5.0", RISK_TASK: "2.2.1",
}
TASK_COUNT = 66
EXECUTOR_LIMIT = 40
RETURN_EVERY = 4
MAX_INPUT_BYTES = 131_072
CONSTRAINTS = [
    "Use only the public task files and the local /app workspace.",
    "The isolated task has no network access.",
]
INSTRUCTION = """You are the Executor for this Terminal-Bench task.
Return one Action line per turn. Action: <one shell command> runs a command in /app.
Use Action: finish when the complete task is ready for independent verification.
You can inspect local inputs, create task artifacts, and check your work.
Files persist across turns. Each command starts in /app."""
COMMAND_TIMEOUT = 30
OUTPUT_LIMIT = 2_000
OFFLINE_COMPOSE = Path(__file__).with_name("terminal-compose-offline.yaml")
COQ_IMAGES = {
    "environment": ("planner-coq-environment:v2.1.0", "sha256:3270787357d488a6f398d77c0a3d3022f81bcf8d1ab55bb305698fd8f4bf50dc"),
    "tests": ("planner-coq-verifier:v2.1.0", "sha256:742657720a182503e5d0a4210a33426251f56a0ea255686724a04766c6d91a4e"),
}
BOOKWORM_PYTHON312_BASE = {
    "python:3.12-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e":
        ("planner-finance-base-python312:v3.0.6", "sha256:febd0be41adb897a0ab8f1f1c693d8912669ea60c4940e076e9946b60e210ef0"),
}
REVIEWED_UV_BASE = {
    "ghcr.io/astral-sh/uv@sha256:95f2aa1fe59274951cfe9b0cbc7972e879ff1004bc8945d130a32eb0dbd85945":
        ("planner-finance-base-uv:v3.0.6", "sha256:82f83ac4c515f4555ef813062b75f38e0bad9240f49ada41556d223c53153192"),
}
FINANCE_BASES = {
    "python:3.11-slim@sha256:9a7765b36773a37061455b332f18e265e7f58f6fea9c419a550d2a8b0e9db834":
        ("planner-finance-base-python311:v3.0.6", "sha256:5d617d87925d3af2acb4b145faa27dea0e454ef9e87b091b97ac8bcfdadafe95"),
    **BOOKWORM_PYTHON312_BASE, **REVIEWED_UV_BASE,
}
BOOKWORM_PYTHON313_BASE = {
    "python:3.13-slim-bookworm@sha256:2325bb286ec344af3e5898cc224b5844e2707ac6e26b1632516fd3edc84a5e26":
        ("planner-photonic-base-python313:v2.1.1", "sha256:915835de46a63f9598442159437904042f1c69a9b41c4965fba1db9ceab66578"),
}
PHOTONIC_BASES = {**BOOKWORM_PYTHON313_BASE, **REVIEWED_UV_BASE}
REWARDKIT_VERIFIER_BASE = {
    "ghcr.io/astral-sh/uv@sha256:ba4857bf2a068e9bc0e64eed8563b065908a4cd6bfb66b531a9c424c8e25e142":
        ("planner-production-verifier-uv:v2.0.6", "sha256:488fd431354f6820b8c64070ead9a62ecac9dcab4a3dc6914a397f479061306c"),
}
PRODUCTION_BASES = {**PHOTONIC_BASES, **REWARDKIT_VERIFIER_BASE}
TRIXIE_PYTHON312_BASE = {
    "python:3.12-slim@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9":
        ("planner-sound-change-base-python312:v2.0.8", "sha256:9e87977b867847e186d066f531ef783b006d582a985c341c269446088d90f2c4"),
}
SOUND_CHANGE_BASES = {**TRIXIE_PYTHON312_BASE, **REWARDKIT_VERIFIER_BASE}
REVIEWED_UBUNTU2404_BASE = {
    "ubuntu:24.04@sha256:008173c23f95b170204355c12626cb5a965d779a7e1283b09e9cffbb1bf33ca3":
        ("planner-mvcc-base-ubuntu2404:v2.2.1", "sha256:6232b38791000e3818b58d8847b5a8f5612d606929e01156dd8febc423e0f2ef"),
}
MVCC_BASES = {**REVIEWED_UBUNTU2404_BASE, **BOOKWORM_PYTHON312_BASE, **REVIEWED_UV_BASE}
BATCHED_BASES = {
    "python:3.11-slim@sha256:da047cb8f9d1d98e5c070f5300ba9f7274e33b8fc0e5be5ed88740aed1b95ba9":
        ("planner-batched-base-python311:v3.1.1", "sha256:274d131132dbdc6058ed77088525d77adaf0749a6d99f2cf7d42feb9a10737c8"),
    **BOOKWORM_PYTHON312_BASE, **REVIEWED_UV_BASE, **REWARDKIT_VERIFIER_BASE,
}
WHEELHOUSE_BASES = {
    FINANCE_TASK: FINANCE_BASES, PHOTONIC_TASK: PHOTONIC_BASES,
    PRODUCTION_TASK: PRODUCTION_BASES, SOUND_CHANGE_TASK: SOUND_CHANGE_BASES, MVCC_TASK: MVCC_BASES,
    VF2_TASK: {**REVIEWED_UBUNTU2404_BASE, **REVIEWED_UV_BASE},
    BATCHED_TASK: BATCHED_BASES,
    KS_TASK: {**REVIEWED_UBUNTU2404_BASE, **REVIEWED_UV_BASE},
    DRIFT_TASK: {**REVIEWED_UBUNTU2404_BASE, **REVIEWED_UV_BASE},
    CARGO_TASK: {**BOOKWORM_PYTHON313_BASE, **REWARDKIT_VERIFIER_BASE},
    ONTOLOGY_TASK: {**TRIXIE_PYTHON312_BASE, **REVIEWED_UV_BASE},
    WAL_TASK: {
        "python:3.13-slim-bookworm@sha256:bb73517d48bd32016e15eade0c009b2724ec3a025a9975b5cd9b251d0dcadb33":
            ("planner-wal-base-python313:v2.5.0", "sha256:79e3b8337aa1781010bbd8a794decbb774be6ffe49e1b8efe48313d917e90077"),
        **REVIEWED_UV_BASE,
    },
    RISK_TASK: {**BOOKWORM_PYTHON312_BASE, **REVIEWED_UV_BASE},
}
OFFLINE_BUILD_PREFIX = {
    FINANCE_TASK: "finance", PHOTONIC_TASK: "photonic", PRODUCTION_TASK: "production", SOUND_CHANGE_TASK: "sound-change",
    MVCC_TASK: "mvcc", VF2_TASK: "vf2", BATCHED_TASK: "batched", COQ_TASK: "coq", KS_TASK: "ks", DRIFT_TASK: "drift",
    CARGO_TASK: "cargo", ONTOLOGY_TASK: "ontology", WAL_TASK: "wal", RISK_TASK: "risk",
}
FINANCE_ONLINE_INSTALL = (
    "RUN UV_PROJECT_ENVIRONMENT=/usr/local /tmp/uv sync --project /tmp/deps --locked --inexact "
    "--default-index https://pypi.org/simple"
)
DEBIAN_BUILDS = {
    RISK_TASK: {
        phase: (packages, (
            f"RUN apt-get update && apt-get install -y --no-install-recommends {packages} "
            "&& rm -rf /var/lib/apt/lists/*",
        )) for phase, packages in (
            ("environment", "gcc libc6-dev"),
            ("tests", "gcc libc6-dev util-linux git ca-certificates"),
        )
    },
    WAL_TASK: {
        "tests": ("git", (
            "RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*",
        )),
    },
    CARGO_TASK: {
        "tests": ("curl", (
            "RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*",
        )),
    },
    ONTOLOGY_TASK: {
        "tests": ("git ca-certificates", (
            "RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates "
            "&& rm -rf /var/lib/apt/lists/*",
        )),
    },
    BATCHED_TASK: {
        "tests": ("curl git ca-certificates", (
            "RUN apt-get update \\\n"
            "    && apt-get install -y --no-install-recommends curl \\\n"
            "    && rm -rf /var/lib/apt/lists/*",
            "RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates "
            "&& rm -rf /var/lib/apt/lists/*",
        )),
    },
    PRODUCTION_TASK: {
        "environment": ("bash ca-certificates", (
            "RUN apt-get update && apt-get install -y --no-install-recommends \\\n"
            "    bash \\\n    ca-certificates \\\n  && rm -rf /var/lib/apt/lists/*",
        )),
        "tests": ("curl ca-certificates git", (
            "RUN apt-get update && apt-get install -y --no-install-recommends \\\n"
            "        curl \\\n        ca-certificates \\\n    && rm -rf /var/lib/apt/lists/*",
            "RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*",
        )),
    },
    SOUND_CHANGE_TASK: {
        "environment": ("git", (
            "RUN apt-get update && apt-get install -y \\\n    git \\\n    && rm -rf /var/lib/apt/lists/*",
        )),
        "tests": ("curl", (
            "RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*",
        )),
    },
    MVCC_TASK: {
        "environment": ("build-essential make patch python3 ca-certificates", (
            "RUN apt-get update \\\n"
            "    && apt-get install -y --no-install-recommends build-essential make patch python3 ca-certificates \\\n"
            "    && rm -rf /var/lib/apt/lists/*",
        )),
        "tests": ("build-essential make git", (
            "RUN apt-get update \\\n"
            "    && apt-get install -y --no-install-recommends build-essential make git \\\n"
            "    && rm -rf /var/lib/apt/lists/*",
        )),
    },
    VF2_TASK: {
        "environment": ("python3 python3-pip python3-dev python3-venv build-essential cmake curl git pkg-config libssl-dev", (
            "RUN apt-get update && apt-get install -y \\\n"
            "    python3 \\\n    python3-pip \\\n    python3-dev \\\n    python3-venv \\\n    build-essential \\\n"
            "    cmake \\\n    curl \\\n    git \\\n    pkg-config \\\n    libssl-dev \\\n"
            "    && rm -rf /var/lib/apt/lists/*",
        )),
        "tests": ("python3 python3-pip git ca-certificates libatomic1", (
            "RUN apt-get update && apt-get install -y --no-install-recommends \\\n"
            "    python3 \\\n    python3-pip git ca-certificates libatomic1 \\\n"
            "    && rm -rf /var/lib/apt/lists/*",
        )),
    },
    KS_TASK: {
        "environment": ("g++ python3", (
            "RUN apt-get update && apt-get install -y --no-install-recommends \\\n"
            "    g++ \\\n    python3 \\\n"
            "    && rm -rf /var/lib/apt/lists/*",
        )),
        "tests": ("g++ python3 git ca-certificates", (
            "RUN apt-get update && apt-get install -y --no-install-recommends \\\n"
            "    g++ \\\n    python3 git ca-certificates \\\n"
            "    && rm -rf /var/lib/apt/lists/*",
        )),
    },
    DRIFT_TASK: {
        "environment": ("ca-certificates curl python3 python3-pip python3-numpy python3-scipy", (
            "RUN apt-get update \\\n"
            "  && apt-get install -y --no-install-recommends \\\n"
            "    ca-certificates \\\n    curl \\\n    python3 \\\n    python3-pip \\\n    python3-numpy \\\n    python3-scipy \\\n"
            "  && rm -rf /var/lib/apt/lists/*",
        )),
        "tests": ("ca-certificates git python3 python3-pip", (
            "RUN apt-get update \\\n"
            "  && apt-get install -y --no-install-recommends \\\n"
            "    ca-certificates \\\n    git \\\n    python3 \\\n    python3-pip \\\n"
            "  && rm -rf /var/lib/apt/lists/*",
        )),
    },
}
VF2_ONLINE_RUST = "RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y"
VF2_OFFLINE_RUST = (
    "RUN --mount=type=bind,from=reviewed_rust,target=/verified-rust cd /verified-rust && "
    "sha256sum --strict -c SHA256SUMS && RUSTUP_DIST_SERVER=file:///verified-rust "
    "./rustup/archive/1.29.3/x86_64-unknown-linux-gnu/rustup-init -y --no-modify-path --default-toolchain stable && "
    "/root/.cargo/bin/rustc --version"
)
_ACTIVE_TRIAL = ContextVar("terminal_benchmark_trial")


class HarborVerifierUnavailable(RuntimeError):
    """The native verifier did not return a valid score."""


def reviewed_task(root, task_key=MUSIC_TASK):
    """Accept only the pristine reviewed task from the pinned official release."""
    if task_key not in REVIEWED_TASK_VERSIONS:
        raise ValueError("Terminal-Bench task is outside the reviewed recipe scope")
    root = Path(root).resolve()
    git = ("git", "--no-optional-locks", "-C", str(root))
    commit = subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()
    # The sparse checkout excludes the unused reference solution and needs no GitHub access at runtime.
    directory = f"tasks/{task_key}"
    changes = subprocess.check_output(
        [*git, "status", "--porcelain", "--untracked-files=all", "--", directory,
         f":(exclude){directory}/solution"],
        env={**os.environ, "GIT_NO_LAZY_FETCH": "1"}, text=True,
    )
    if commit != SOURCE_COMMIT or changes:
        raise ValueError("Terminal-Bench requires the unchanged reviewed task from the pinned checkout")
    path = root / directory
    versions = {f"terminal-bench/{task_key}": REVIEWED_TASK_VERSIONS[task_key]}
    config = {"environments": {"terminalbench": {"reviewed_task_versions": versions}}}
    return path, TerminalBenchTask.load(path, config=config)


def visible_output(text):
    text = text or ""
    return text if len(text) <= OUTPUT_LIMIT else text[:OUTPUT_LIMIT] + "\n[output truncated]"


class TerminalWorkspace:
    """Adapt an isolated Harbor environment to the shared per-turn runner."""

    def __init__(self, environment, observation, max_steps):
        self.environment = environment
        self.initial_observation = observation
        self.max_steps = max_steps

    def reset(self):
        prompt = render_executor_prompt(INSTRUCTION, self.initial_observation)
        self.state = State(history=[{"role": "user", "content": prompt}])
        return prompt, self.state

    async def step(self, reply):
        state = self.state
        state.history.append({"role": "assistant", "content": reply})
        action = None
        dispatched = False
        valid = False
        try:
            parsed = BaseEnv.parse_action(reply)
        except ValueError:
            message = "Invalid format. Supply one nonempty 'Action: ...' line."
        else:
            if parsed == "finish":
                valid = True
                state.finished = True
                state.terminate_reason = "environment_done"
                message = "Executor returned the complete task for independent verification."
            else:
                action = parsed
                result = await self.environment.exec(command=action, cwd="/app", timeout_sec=COMMAND_TIMEOUT)
                dispatched = True
                valid = result.return_code == 0
                message = (f"Exit code: {result.return_code}\n"
                           f"stdout:\n{visible_output(result.stdout)}\nstderr:\n{visible_output(result.stderr)}")
        observation = f"Observation: {message}"
        state.action_trace.append({"action": action, "observation": observation, "valid": valid,
                                   "dispatched": dispatched})
        state.history.append({"role": "user", "content": observation})
        state.steps += 1
        if not state.finished and state.steps >= self.max_steps:
            state.finished = True
            state.terminate_reason = "max_steps"
        return observation, state


class OfflineTerminalTrial(Trial):
    """Use Harbor's native lifecycle with the reviewed test kept in its verifier."""

    @staticmethod
    async def _load_task(config):
        # The pinned Harbor hook preserves native task files and their lock.
        task, download = await Trial._load_task(config)
        reviewed = _ACTIVE_TRIAL.get()["task"]
        if task.config.task.name != reviewed.task_id or task.has_steps:
            raise ValueError("Expected the reviewed single-step Terminal-Bench task")
        if resolve_task_verifier_mode(task.config) != VerifierEnvironmentMode.SEPARATE:
            raise ValueError("The official verifier must run in a separate environment")
        task.config.environment.network_mode = NetworkMode.NO_NETWORK
        task.config.agent.network_mode = NetworkMode.NO_NETWORK
        task.config.verifier.network_mode = NetworkMode.NO_NETWORK
        return task, download


class IsolatedDocker(DockerEnvironment):
    """Use Harbor's static no-network Compose layer in both containers."""

    def __init__(self, environment_dir, environment_name, session_id, trial_paths, task_env_config,
                 *, extra_docker_compose=None, **kwargs):
        if extra_docker_compose:
            raise ValueError("Reviewed trials do not accept external Compose overrides")
        overlays = [OFFLINE_COMPOSE]
        active = _ACTIVE_TRIAL.get()
        task_key = active["task"].task_id.removeprefix("terminal-bench/")
        if task_key in WHEELHOUSE_BASES:
            overlays.append(offline_wheel_build(environment_dir, trial_paths.trial_dir, task_key, active["wheels"]))
        elif task_key == COQ_TASK:
            overlays.append(offline_coq_build(environment_dir, trial_paths.trial_dir))
        elif Path(environment_dir).name == "tests":
            overlays.append(offline_music_verifier(environment_dir, trial_paths.trial_dir))
        super().__init__(environment_dir, environment_name, session_id, trial_paths, task_env_config,
                         extra_docker_compose=overlays, **kwargs)

    @staticmethod
    def _requires_egress_control(**_):
        return False

    @property
    def capabilities(self):
        return super().capabilities.model_copy(update={"disable_internet": True})

    def validate_network_policy_support(self, network_policy=None):
        policy = network_policy or self.network_policy
        if policy.network_mode != NetworkMode.NO_NETWORK:
            raise ValueError("Reviewed trials require a static no-network policy")
        super().validate_network_policy_support(policy)


def offline_build_overlay(trial_dir, name, source, **build):
    dockerfile = trial_dir / f"{name}.Dockerfile"
    dockerfile.write_text(source, encoding="utf-8")
    build["dockerfile"] = str(dockerfile.resolve())
    overlay = trial_dir / f"{name}-compose.json"
    write_json(overlay, {"services": {"main": {"build": build}}})
    return overlay


def offline_music_verifier(environment_dir, trial_dir):
    """Keep the official verifier and lockfile, using only cached wheels at build time."""
    source = (Path(environment_dir) / "Dockerfile").read_text(encoding="utf-8")
    command = "RUN cd /tmp/verifier-deps &&"
    if source.count(command) != 1 or source.count("/tmp/uv sync --locked") != 1:
        raise ValueError("The reviewed music verifier build recipe has changed")
    cache_id = f"planner-{MUSIC_TASK}-verifier-uv"
    cached = f"RUN --mount=type=cache,id={cache_id},target=/root/.cache/uv cd /tmp/verifier-deps &&"
    return offline_build_overlay(
        trial_dir, "verifier-offline",
        source.replace(command, cached).replace("/tmp/uv sync --locked", "/tmp/uv sync --offline --locked")
        .replace(" /root/.cache/uv", ""),
    )


def verify_reviewed_images(task_key, images):
    local_tags, expected_ids = zip(*images)
    ids = subprocess.check_output(
        ["docker", "image", "inspect", "--format", "{{.Id}} {{.Os}}/{{.Architecture}}", *local_tags],
        text=True,
    ).splitlines()
    if ids != [f"{image_id} linux/amd64" for image_id in expected_ids]:
        raise ValueError(f"The local {task_key} images do not match the reviewed amd64 image configs")


def offline_coq_build(environment_dir, trial_dir):
    """Use the verified local build from the pinned Coq toolchain and original task files."""
    phase = Path(environment_dir).name
    image = COQ_IMAGES[phase]
    verify_reviewed_images(COQ_TASK, (image,))
    prefix = OFFLINE_BUILD_PREFIX[COQ_TASK]
    return offline_build_overlay(trial_dir, f"{prefix}-{phase}-offline", f"FROM {image[0]}\n")


def reviewed_wheels(root, task_key):
    """Require the exact published amd64 bases and the local verifier wheelhouse."""
    verify_reviewed_images(task_key, WHEELHOUSE_BASES[task_key].values())
    wheelhouse = Path(root).resolve().parent / f"{task_key}-review" / "wheels"
    if not wheelhouse.is_dir():
        raise FileNotFoundError(f"Missing locked wheels for {task_key} at {wheelhouse}")
    for phase in DEBIAN_BUILDS.get(task_key, {}):
        manifest = wheelhouse.parent / "deb" / phase / "SHA256SUMS"
        if not manifest.is_file():
            raise FileNotFoundError(f"Missing reviewed Debian archive manifest at {manifest}")
    if task_key == VF2_TASK and not (wheelhouse.parent / "rust" / "SHA256SUMS").is_file():
        raise FileNotFoundError("Missing reviewed VF2 Rust toolchain manifest")
    return wheelhouse


def offline_debian_build(source, task_key, phase):
    packages, online_commands = DEBIAN_BUILDS[task_key][phase]
    if task_key == RISK_TASK:
        # Preserve APT's automatic dependency tracking for the verifier's compiler removal.
        apt = "apt-get -o Dir::Etc::sourcelist=/tmp/risk-debs.list -o Dir::Etc::sourceparts=-"
        offline = (
            "RUN --mount=type=bind,from=reviewed_debs,target=/debs cd /debs && sha256sum --strict -c SHA256SUMS "
            "&& printf '%s\\n' 'deb [trusted=yes] file:/debs ./' > /tmp/risk-debs.list "
            f"&& {apt} update && {apt} install -y --no-install-recommends {packages} "
            "&& rm -f /tmp/risk-debs.list && rm -rf /var/lib/apt/lists/*"
        )
    else:
        archive_path, install = "$2", "dpkg -i -- $archives"
        if task_key in (MVCC_TASK, VF2_TASK, KS_TASK, DRIFT_TASK):
            # Apt orders local archives with Pre-Depends before unpacking them.
            archive_path = '"/debs/" substr($2, 3)'
            install = "cd / && apt-get -o Acquire::Retries=0 --no-install-recommends -y install $archives"
        offline = (
            "RUN --mount=type=bind,from=reviewed_debs,target=/debs cd /debs && "
            r"archives=$(awk 'NF != 2 || $2 !~ /^\.\/[A-Za-z0-9_.%+~:-]+\.deb$/ "
            f"{{ exit 1 }} {{ print {archive_path} }}' SHA256SUMS) && "
            'test -n "$archives" && sha256sum --strict -c SHA256SUMS && '
            f"set -f && {install} && "
            f"dpkg-query -W {packages}"
        )
    for command in online_commands:
        if source.count(command) != 1:
            raise ValueError(f"The reviewed {task_key} {phase} apt recipe has changed")
        source = source.replace(command, offline)
        offline = ""
    return source


def offline_wheel_build(environment_dir, trial_dir, task_key, wheelhouse):
    """Use local copies of the pinned images and install only lockfile-verified wheels."""
    environment_dir = Path(environment_dir)
    phase = environment_dir.name
    source = (environment_dir / "Dockerfile").read_text(encoding="utf-8")
    build = {}
    for original, (local_tag, _) in WHEELHOUSE_BASES[task_key].items():
        source = source.replace(original, local_tag)
    online_install = None
    uv = "/tmp/uv"
    install_setup = ""
    install_options = "--system"
    cleanup = "rm /tmp/locked-requirements.txt"
    if task_key == BATCHED_TASK or (task_key in (FINANCE_TASK, CARGO_TASK) and phase == "tests"):
        project = "/tmp/deps"
        online_install = FINANCE_ONLINE_INSTALL
        if task_key in (BATCHED_TASK, CARGO_TASK) and phase == "tests":
            online_install = online_install.replace("/tmp/uv", "uv")
            uv = "/root/.local/bin/uv"
    elif task_key in (PHOTONIC_TASK, PRODUCTION_TASK, ONTOLOGY_TASK) or (task_key == MVCC_TASK and phase == "tests"):
        project = {"environment": "/tmp/environment-deps", "tests": "/tmp/verifier-deps"}[phase]
        original_uv = uv
        if task_key == PRODUCTION_TASK and phase == "tests":
            original_uv, uv = "uv", "/root/.local/bin/uv"
        online_install = (
            f"RUN cd {project} && \\\n"
            f"    UV_PROJECT_ENVIRONMENT=/usr/local {original_uv} sync --locked --inexact "
            "--default-index https://pypi.org/simple"
        )
        if task_key == ONTOLOGY_TASK:
            online_install += f" \\\n    && rm -rf /tmp/uv {project} /root/.cache/uv"
            cleanup = f"rm -rf /tmp/uv {project} /tmp/locked-requirements.txt /root/.cache/uv"
    elif task_key == SOUND_CHANGE_TASK and phase == "tests":
        project, uv = "/opt/verifier-deps", "/root/.local/bin/uv"
        online_install = (
            f"RUN cd {project} && UV_PROJECT_ENVIRONMENT=/usr/local uv sync --locked --inexact "
            "--default-index https://pypi.org/simple"
        )
    elif task_key in (VF2_TASK, WAL_TASK) and phase == "tests":
        project = "/opt/verifier-deps"
        uv_target = "/usr" if task_key == VF2_TASK else "/usr/local"
        online_install = (
            f"RUN cd {project} && UV_PROJECT_ENVIRONMENT={uv_target} /tmp/uv sync --locked --inexact "
            "--default-index https://pypi.org/simple \\\n"
            "    && rm -rf /tmp/uv /opt/verifier-deps /root/.cache/uv"
        )
        if task_key == VF2_TASK:
            install_options = "--python /usr/bin/python3 --system --break-system-packages"
        cleanup = "rm -rf /tmp/uv /opt/verifier-deps /tmp/locked-requirements.txt /root/.cache/uv"
    elif task_key == RISK_TASK and phase == "tests":
        project = "/opt/verifier-deps"
        venv = "/opt/verifier-venv"
        online_install = (
            f"RUN python -m venv {venv} \\\n"
            f"    && cd {project} \\\n"
            f"    && UV_PROJECT_ENVIRONMENT={venv} /tmp/uv sync --locked --inexact "
            "--default-index https://pypi.org/simple \\\n"
            f"    && rm -rf /tmp/uv {project} /root/.cache/uv"
        )
        install_setup = f"python -m venv {venv} && "
        install_options = f"--python {venv}/bin/python"
        cleanup = f"rm -rf /tmp/uv {project} /tmp/locked-requirements.txt /root/.cache/uv"
    elif task_key in (KS_TASK, DRIFT_TASK) and phase == "tests":
        project = "/tmp/deps" if task_key == DRIFT_TASK else "/opt/worker-deps"
        project_cleanup = f" {project}" if task_key == DRIFT_TASK else ""
        online_install = (
            f"RUN UV_PROJECT_ENVIRONMENT=/usr /tmp/uv sync --project {project} --locked --inexact "
            "--default-index https://pypi.org/simple \\\n"
            f"    && rm -rf /tmp/uv{project_cleanup} /root/.cache/uv"
        )
        install_options = "--python /usr/bin/python3 --system --break-system-packages"
        cleanup = f"rm -rf /tmp/uv{project_cleanup} /tmp/locked-requirements.txt /root/.cache/uv"
    if online_install is not None:
        if source.count(online_install) != 1:
            raise ValueError(f"The reviewed {task_key} {phase} build recipe has changed")
        offline_install = (
            f"RUN --mount=type=bind,from=reviewed_wheels,target=/wheels {install_setup}"
            f"{uv} export --offline --locked --no-dev --no-emit-project --project {project} "
            "--output-file /tmp/locked-requirements.txt && "
            f"{uv} pip install {install_options} --offline --no-index --find-links /wheels --require-hashes "
            f"--requirement /tmp/locked-requirements.txt && {cleanup}"
        )
        source = source.replace(online_install, offline_install)
        build["additional_contexts"] = {"reviewed_wheels": str(wheelhouse)}
    if phase in DEBIAN_BUILDS.get(task_key, {}):
        source = offline_debian_build(source, task_key, phase)
        build.setdefault("additional_contexts", {})["reviewed_debs"] = str(wheelhouse.parent / "deb" / phase)
    if task_key == VF2_TASK and phase == "environment":
        if source.count(VF2_ONLINE_RUST) != 1:
            raise ValueError("The reviewed VF2 Rust installer has changed")
        source = source.replace(VF2_ONLINE_RUST, VF2_OFFLINE_RUST)
        build["additional_contexts"]["reviewed_rust"] = str(wheelhouse.parent / "rust")
    prefix = OFFLINE_BUILD_PREFIX[task_key]
    return offline_build_overlay(trial_dir, f"{prefix}-{phase}-offline", source, **build)


class TerminalRecipeAgent(BaseAgent):
    """Keep model transport on the host and use only the isolated task tool."""

    @staticmethod
    def name():
        return "planner-centered-reviewed-terminal"

    def version(self):
        return "1"

    async def setup(self, environment):
        if environment.network_policy.network_mode != NetworkMode.NO_NETWORK:
            raise ValueError("Terminal Executor environment must have no network policy")
        result = await environment.exec(command='test "$(ls -1 /sys/class/net)" = lo', cwd="/app", timeout_sec=10)
        if result.return_code != 0:
            raise RuntimeError("Terminal Executor network namespace is not isolated")

    async def run(self, instruction, environment, context):
        active = _ACTIVE_TRIAL.get()
        if instruction.strip() != strip_canary(active["task"].observation).strip():
            raise ValueError("Harbor returned an unexpected task instruction")
        options = active["runner_options"]
        env = TerminalWorkspace(environment, instruction, options["executor_limit"])
        active["record"] = await run_trial(
            env=env, goal=instruction, constraints=CONSTRAINTS,
            benchmark="terminalbench", external_verifier=True, **options,
        )


async def run_terminal_trial(root, trials_dir, *, task_key=MUSIC_TASK, **runner_options):
    """Run an arm and append Harbor's native verifier output after the runner stops."""
    if version("harbor") != HARBOR_VERSION:
        raise RuntimeError(f"Expected Harbor {HARBOR_VERSION}")
    task_dir, task = reviewed_task(root, task_key)
    config = TrialConfig(
        task=TaskConfig(path=task_dir),
        trial_name=f"{task_key}-{uuid4().hex[:12]}",
        trials_dir=Path(trials_dir),
        agent=AgentConfig(import_path=f"{__name__}:TerminalRecipeAgent"),
        environment=EnvironmentConfig(import_path=f"{__name__}:IsolatedDocker", force_build=False, delete=True),
    )
    active = {"task": task, "record": None, "runner_options": runner_options}
    if task_key in WHEELHOUSE_BASES:
        active["wheels"] = reviewed_wheels(root, task_key)
    token = _ACTIVE_TRIAL.set(active)
    try:
        trial = await OfflineTerminalTrial.create(config)
        await trial.run()
    finally:
        _ACTIVE_TRIAL.reset(token)
    record = active["record"]
    if record is None or record["events"][-1]["type"] != "stop":
        raise RuntimeError(f"Harbor did not finish the online runner. See {trial.paths.trial_dir}.")
    imported = load_terminalbench_trial(trial.paths.result_path, task)
    stop = record["events"][-1]
    prefix = OFFLINE_BUILD_PREFIX.get(task_key)
    verifier_dockerfile = f"{prefix}-tests-offline.Dockerfile" if prefix else "verifier-offline.Dockerfile"
    record["harbor"] = {
        "release": RELEASE, "commit": SOURCE_COMMIT, "task_version": task.version,
        "result": str(trial.paths.result_path), "lock": str(trial.paths.result_path.with_name("lock.json")),
        "agent_network": "no-network", "verifier_phase_network": "no-network",
        "verifier_dockerfile": str(trial.paths.trial_dir / verifier_dockerfile),
    }
    if prefix:
        record["harbor"]["agent_dockerfile"] = str(trial.paths.trial_dir / f"{prefix}-environment-offline.Dockerfile")
    if task_key == COQ_TASK:
        record["harbor"]["prepared_images"] = {phase: image_id for phase, (_, image_id) in COQ_IMAGES.items()}
    if imported["reward"] is None and stop["reason"] != "runtime_error":
        runner_options["save"](record)
        raise HarborVerifierUnavailable(f"See {trial.paths.result_path} for verifier details")
    assessable = stop["reason"] != "runtime_error"
    record["outcome"] = {
        "reason": stop["reason"],
        "success": imported["success"] if assessable else None,
        "reward": imported["reward"] if assessable else None,
    }
    record["events"].append({
        **{key: stop[key] for key in ("workspace_id", "request_id", "plan_version")},
        "event_id": stop["event_id"] + 1, "timestamp": trial.result.finished_at.isoformat(),
        "type": "verifier", **record["outcome"], "native_result": str(trial.paths.result_path),
    })
    runner_options["save"](record)
    return record


def scripted_model(texts):
    values = iter(texts)

    async def complete(_messages):
        return {"text": next(values), "finish_reason": "stop", "model": "scripted-preflight", "usage": None}

    return complete


def decision(stage, refs):
    mode = "delegate" if stage else "finish"
    body = {"decision": mode, "hypotheses": [], "remaining_work": [], "evidence_refs": refs}
    if stage:
        body["stage_objective"] = stage
    return f"<plan>Check the reviewed workspace and confirm persistence.</plan><decision>{json.dumps(body)}</decision>"


async def preflight(root, output, task_key=MUSIC_TASK):
    output.mkdir(parents=True, exist_ok=False)
    save = partial(write_json, output / "trial.json")
    if task_key == MUSIC_TASK:
        public_input, write_dummy = "Harmony.pdf", "touch harmony.mxl"
        absence_check = "test ! -e /tests/checks.py"
    elif task_key == FINANCE_TASK:
        public_input = "inputs/portfolio.csv"
        write_dummy = "touch output/sa_ccr_results.csv output/sa_ccr_workings.xlsx"
        absence_check = "test ! -d /tests"
    elif task_key == PRODUCTION_TASK:
        public_input = "data/erp.db"
        write_dummy = "touch output/erp_writeback.sql output/mes_writeback.sql output/wms_writeback.sql"
        absence_check = "test ! -d /tests && test -x data/dbgw && test ! -S /var/run/docker.sock"
    elif task_key == SOUND_CHANGE_TASK:
        public_input = "data/train.tsv"
        write_dummy = "printf '%s\\n' '[]' > rules.json && : > ordering.txt"
        absence_check = (
            'test "$(wc -l < data/train.tsv)" = 780 && test -f engine/apply.py '
            '&& test ! -d /tests && test ! -e data/hidden_test.tsv '
            '&& test ! -S /var/run/docker.sock && test -z "${OPENAI_API_KEY:-}"'
        )
    elif task_key == BATCHED_TASK:
        public_input, write_dummy = "evalbench/evaluate.py", ":"
        absence_check = (
            "test -f model/weights.json && test -f data/public_eval.jsonl "
            "&& python -c \"import numpy; assert numpy.__version__ == '1.26.4'\" "
            "&& test ! -e /tests/oracle_eval.py && test ! -S /var/run/docker.sock"
        )
    elif task_key == COQ_TASK:
        public_input, write_dummy = "Main.v", ":"
        absence_check = (
            'test ! -d /tests && test ! -e /var/run/docker.sock '
            '&& test -z "${OPENAI_API_KEY:-}" && coqc --version'
        )
    elif task_key == MVCC_TASK:
        public_input, write_dummy = "crash_report.txt", ":"
        absence_check = (
            "test -f src/lsm_db.cc && g++ --version >/dev/null "
            "&& test ! -e /tests/test_visibility.py && test ! -S /var/run/docker.sock"
        )
    elif task_key == VF2_TASK:
        public_input = "/usr/local/libexec/portable-compiler"
        write_dummy = "printf '# Intentionally empty negative control\\n' > fast_networkx.py"
        absence_check = (
            r"rustc --version | grep '^rustc 1\.100\.0 ' && g++ --version >/dev/null "
            "&& test ! -e /tests/test_outputs.py && test ! -S /var/run/docker.sock"
        )
    elif task_key == KS_TASK:
        public_input = "oracle.hpp"
        write_dummy = (
            "printf '%s\\n' 'void u_hat(const double*, int n, double* out) { "
            "for (int i = 0; i < n; ++i) out[i] = 0.0; }' > solution.cpp"
        )
        absence_check = "g++ --version >/dev/null && test ! -e /tests/test_state.py && test ! -S /var/run/docker.sock"
    elif task_key == DRIFT_TASK:
        public_input, write_dummy = "data/reference_embeddings.npy", ":"
        absence_check = (
            "test -f drift_monitor/__init__.py && python3 -c 'import numpy, scipy' "
            "&& test ! -e /tests/checks.py && test ! -e /tests/probe && test ! -S /var/run/docker.sock"
        )
    elif task_key == CARGO_TASK:
        public_input, write_dummy = "dispatch.py", ":"
        absence_check = (
            "test -f data/manifest.json && test -f data/weather.json "
            "&& python -c \"import json; assert json.load(open('data/manifest.json'))['date'] == '2024-03-15'\" "
            "&& test ! -e /tests/verify.py && test ! -S /var/run/docker.sock "
            "&& test ! -e requirements.txt && test ! -e apt-packages.txt"
        )
    elif task_key == ONTOLOGY_TASK:
        public_input = "2024-q2/austria_2024_q2.ttl"
        write_dummy = (
            "printf '%s\\n' 'from pathlib import Path' 'import sys' "
            "\"Path(sys.argv[1], 'unified.ttl').write_text('# negative control\\n')\" > pipeline.py "
            "&& printf '%s\\n' 'SELECT ?s WHERE { ?s ?p ?o } LIMIT 0' > cross_border_operational_points.rq "
            "&& cp cross_border_operational_points.rq qualified_cross_border_points.rq "
            "&& : > requirements.txt && python pipeline.py 2024-q2"
        )
        absence_check = (
            "test -f 2024-q1/ontology_core.owl && python -c 'import rdflib; assert rdflib.__version__ == \"7.1.4\"' "
            '&& test ! -d /tests && test ! -d /app/2024-q3 && test ! -S /var/run/docker.sock '
            '&& test -z "${OPENAI_API_KEY:-}"'
        )
    elif task_key == WAL_TASK:
        public_input, write_dummy = "app.py", "rm .planner-preflight"
        absence_check = (
            "test -f recovery.py && python -B -c 'import app; assert callable(app.make_engine)' "
            "&& test ! -e /tests/test_gates.py && test ! -S /var/run/docker.sock"
        )
    elif task_key == RISK_TASK:
        public_input, write_dummy = "parityctl/cli.py", "rm .planner-preflight"
        absence_check = (
            "test -f data/incidents/parity-2026-10/manifest.json && test -x /usr/local/bin/legacy-score "
            "&& test ! -e /tests/checks.py && test ! -S /var/run/docker.sock "
            '&& test -z "${OPENAI_API_KEY:-}"'
        )
    else:
        public_input = "layout_spec.json"
        write_dummy = "printf '%s\\n' '{}' > routing_result_1.json"
        absence_check = "test ! -d /tests"
    record = await run_terminal_trial(
        root, output / "harbor", task_key=task_key,
        mode="pc", workspace_id="reviewed-terminal-preflight", executor_limit=3,
        planner_limit=3, return_every=1, save=save,
        planner=scripted_model([
            decision("Check the public input and create a persistence marker.", [1]),
            decision("Check that the marker still exists in this stage.", [1]),
            decision(None, [1]),
        ]),
        executor=scripted_model([
            f"Action: test -f {public_input} && {absence_check} && test ! -d /solution "
            "&& test -z \"${TONGJI_API_KEY:-}\" && printf persistent > .planner-preflight",
            f'Action: test "$(cat .planner-preflight)" = persistent && {write_dummy} '
            '&& printf "workspace retained\\n"',
        ]),
    )
    actions = [event for event in record["events"] if event["type"] == "tool_event"]
    requests = [event for event in record["events"] if event["type"] == "execution_request"]
    assert len(actions) == 2 and all(event["valid"] for event in actions)
    if task_key == COQ_TASK:
        assert "version 8.18.0" in actions[0]["observation"] and "OCaml 4.13.1" in actions[0]["observation"]
    assert "workspace retained" in actions[-1]["observation"]
    assert len(requests) == 2 and requests[0]["request_id"] != requests[1]["request_id"]
    assert record["events"][-2]["type"] == "stop" and record["events"][-1]["type"] == "verifier"
    assert record["outcome"]["reward"] == 0, record["outcome"]
    for field in ("result", "lock", "verifier_dockerfile"):
        assert Path(record["harbor"][field]).is_file(), record["harbor"][field]
    print(output.resolve())


def selected_task_roots(root, task_key, finance_root, additional_task_roots):
    entries = [(task_key, root)]
    if finance_root is not None:
        if task_key != MUSIC_TASK:
            raise ValueError("--finance-bench-root requires music-harmony as the primary task")
        entries.append((FINANCE_TASK, finance_root))
    entries.extend(additional_task_roots)
    selected = {}
    for key, task_root in entries:
        if key not in REVIEWED_TASK_VERSIONS:
            raise ValueError(f"Terminal-Bench task {key!r} is outside the reviewed recipe scope")
        if key in selected:
            raise ValueError(f"Terminal-Bench task {key!r} has more than one root")
        selected[key] = Path(task_root).resolve()
    return selected


async def run_benchmark(root, run_dir, api_key, *, task_key=MUSIC_TASK, finance_root=None,
                        additional_task_roots=(), resume=False):
    from benchmark import run_matrix
    from run import model_call

    task_roots = selected_task_roots(root, task_key, finance_root, additional_task_roots)
    rows = {}
    for key, task_root in task_roots.items():
        _, task = reviewed_task(task_root, key)
        if key in WHEELHOUSE_BASES:
            reviewed_wheels(task_root, key)
        elif key == COQ_TASK:
            verify_reviewed_images(key, COQ_IMAGES.values())
        rows[key] = {"task_id": key, "goal": strip_canary(task.observation).strip(),
                     "task_version": task.version, "executor_limit": EXECUTOR_LIMIT}
    dataset = {
        "name": "Terminal-Bench", "split": "test", "selection": "reviewed_subset",
        "data_version": RELEASE, "source_commit": SOURCE_COMMIT, "canonical_task_count": TASK_COUNT,
        "data_dir": str(task_roots[task_key]), "tasks": list(rows.values()), "constraints": CONSTRAINTS,
        "runtime_packages": ["harbor", "openai", "PyYAML"],
        "return_every": RETURN_EVERY, "max_input_bytes": MAX_INPUT_BYTES,
    }
    if len(task_roots) > 1:
        dataset["task_roots"] = {key: str(task_root) for key, task_root in task_roots.items()}

    async def run_one(row, client, *, model_settings, max_input_bytes, executor_limit, planner_limit, **options):
        model_options = {"model_settings": model_settings, "max_input_bytes": max_input_bytes}
        key = row["task_id"]
        return await run_terminal_trial(
            task_roots[key], run_dir / "harbor", task_key=key,
            executor_limit=executor_limit, planner_limit=planner_limit,
            planner=model_call(client, "planner", planner_limit, **model_options) if planner_limit else None,
            executor=model_call(client, "executor", executor_limit, **model_options), **options,
        )

    await run_matrix(run_dir, rows, dataset, api_key, run_one=run_one, concurrency=1, resume=resume)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--terminal-bench-root", required=True, type=Path)
    parser.add_argument("--task-id", choices=REVIEWED_TASK_VERSIONS, default=MUSIC_TASK)
    parser.add_argument("--finance-bench-root", type=Path, help="Add the reviewed finance task to a music score matrix.")
    parser.add_argument("--additional-task-root", action="append", nargs=2, default=[], metavar=("TASK_ID", "ROOT"),
                        help="Add another allowlisted task and its pinned checkout to the score matrix.")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--preflight-output", type=Path, help="New output for the scripted native preflight.")
    action.add_argument("--run-dir", type=Path, help="Output for the reviewed real-model score matrix.")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    if args.preflight_output is not None and (args.finance_bench_root is not None or args.additional_task_root):
        parser.error("Additional task roots require --run-dir")
    try:
        selected_task_roots(args.terminal_bench_root, args.task_id, args.finance_bench_root, args.additional_task_root)
    except ValueError as error:
        parser.error(str(error))
    if args.preflight_output is not None:
        if args.resume:
            parser.error("--resume requires --run-dir")
        asyncio.run(preflight(args.terminal_bench_root, args.preflight_output.resolve(), args.task_id))
    else:
        api_key = os.getenv("TONGJI_API_KEY")
        if not api_key:
            parser.error("Set TONGJI_API_KEY in the host environment")
        asyncio.run(run_benchmark(
            args.terminal_bench_root, args.run_dir.resolve(), api_key, task_key=args.task_id,
            finance_root=args.finance_bench_root, additional_task_roots=args.additional_task_root, resume=args.resume,
        ))


if __name__ == "__main__":
    main()
