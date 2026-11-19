---
title: Install & Download
description: Set up the simulation environment, link RoboTwin 2.0 assets, and validate the repository without a GPU.
---

ManipScope keeps three things in separate places: the **simulator** (RoboTwin 2.0 on SAPIEN 3, Python 3.10), the **model backend** (one isolated environment per policy), and **external downloads** (RoboTwin assets and model weights, which the repository does not redistribute).

!!! warning "Hardware"
    Linux with a compatible NVIDIA driver is required for rendering and planning. CPU-only checks (repository validation, tests, dry runs) work anywhere.

## 1. Clone and validate (CPU only)

```bash
# Download the anonymized repository from https://anonymous.4open.science/r/ManipScope
# and unpack it as ManiScope/
cd ManiScope
python3 -m pip install -r requirements/dev.txt
python3 tools/validate_repo.py     # manifest, seeds, protocol hashes
python3 -m pytest -q tests         # eight CPU regression tests
```

`validate_repo.py` checks that the 48 scenes, 100 seeds each, instruction pools and step limits match `protocol.lock.json`. It fails when the frozen protocol has drifted.

## 2. Simulation environment

Use a dedicated virtual environment for the simulator. Model packages must never be imported here.

```bash
python3.10 -m venv .venv-sim
source .venv-sim/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements/sim.txt -r requirements/client.txt
# Vendored cuRobo needs the CUDA toolkit/compiler and torch at build time.
SETUPTOOLS_SCM_PRETEND_VERSION=0.7.0 python -m pip install --no-build-isolation -e envs/curobo
```

System tools: `ffmpeg`, a C++ toolchain, and CUDA/Vulkan libraries compatible with SAPIEN. Install a PyTorch build that matches your driver; the pinned requirements are a reference, not a universal lockfile.

The `SETUPTOOLS_SCM_PRETEND_VERSION` override is a packaging label only. The vendored cuRobo snapshot is identified by a content digest in `provenance.json`, not by an upstream tag. Do not swap in a newer cuRobo without re-running validation.

## 3. Local configuration

```bash
cp configs/local.env.example configs/local.env
```

`configs/local.env` is git-ignored shell code sourced by every launcher. At minimum set:

| Variable | Meaning |
| --- | --- |
| `ROBOTWIN_PYTHON` | Python of the simulation environment (`.venv-sim/bin/python`) |
| `YAML_PY` | Any Python with PyYAML, used by the shell runner |
| `SIM_GPU` / `GPU` | GPU index for simulation / model inference |
| `EPISODES` | Default episodes per scene (50) |
| `ROBOTWIN_FROZEN_SEEDS` | Keep `1` for the formal protocol |
| `ROBOTWIN_VIDEO_FIRST_N` | Seeds eligible for head-camera video (10) |

Backend-specific paths (`DM05_MODEL`, `OPENPI`, `XVLA_CKPT`, …) are listed in [Configurations]({{rel}}usage/configurations/).

## 4. Assets

Download the RoboTwin 2.0 asset bundle from the [upstream project](https://github.com/RoboTwin-Platform/RoboTwin). It must contain `objects/`, `embodiments/` and the textures referenced by the task configuration.

```bash
python3 tools/link_assets.py /absolute/path/to/robotwin_assets
```

This creates an ignored symlink `assets/`. The tool refuses to replace an existing different link and never edits the target. Machine-specific paths inside migrated embodiment YAML files are resolved in memory by the planner; the shared files are not rewritten.

The formal seed lists are held by the organizers and are not part of the repository. Generate development seed files for the scenes you run (under the simulator environment):

```bash
python suite/gen_seeds.py move_can_coaster 100
```

## 5. Smoke tests without model weights

```bash
# Validate configuration and benchmark inputs, start nothing:
DRY_RUN=1 bash suite/run_suite.sh dm05 move_can_coaster

# Render one scene (needs GPU + assets):
CUDA_VISIBLE_DEVICES=0 "$ROBOTWIN_PYTHON" script/render_scenes.py move_can_coaster \
  --target 1 --max_tries 2 --out out/smoke

# Scripted-expert smoke (bounded, no model service):
CUDA_VISIBLE_DEVICES=0 "$ROBOTWIN_PYTHON" suite/diag/expert_smoke.py move_can_coaster \
  --target 1 --max_tries 2
```

Rendering returns a non-zero exit code when no image is produced; add `--traceback` for details.

## 6. Model backends

Install each backend in its own environment following its upstream instructions, download all weights (several adapters run in offline mode), then set the variables from [Configurations]({{rel}}usage/configurations/). Run a one-episode evaluation before a full campaign:

```bash
EPISODES=1 RUN_NAME=smoke_dm05 bash suite/run_suite.sh dm05 move_can_coaster
```

## Optional: Docker

!!! note
    A simulator-side container image is not yet published. The HTTP boundary between simulator and policy means a container only needs the simulation environment and assets; the policy server can stay on the host. This section will be filled in when the image is available.
