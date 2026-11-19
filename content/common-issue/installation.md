---
title: Installation Issues
description: Known problems when setting up the simulator, cuRobo and assets.
---

## `CUDA error: an illegal instruction was encountered` during rendering

Observed on a host whose GPU runtime had been migrated between machines. The first failure localises to cuRobo's LBFGS kernel (`lbfgs_step_cu.forward`) during planner warm-up; Warp also reports errors during cleanup.

Fix: rebuild the isolated GPU runtime (matching driver, CUDA toolkit and PyTorch build), delete the cuRobo extension cache, reinstall `envs/curobo` with `--no-build-isolation`, then re-run the rendering smoke and the expert smoke. Do not report benchmark numbers from an environment that has not passed both.

## Stale absolute paths inside embodiment YAML

Migrated asset bundles may reference the original machine's paths for URDF and collision files. The planner resolves known embodiment-local paths in memory against the current `assets/embodiments/` directory. Unknown or missing external paths raise a clear error; configure them explicitly rather than editing the shared asset files.

## `Assets missing; see docs/INSTALLATION.md`

`assets/` must be a link to a RoboTwin 2.0 bundle containing `objects/` and `embodiments/`. Create it with `tools/link_assets.py`. The tool refuses to overwrite a link that points elsewhere.

## `ROBOTWIN_PYTHON not executable`

`configs/local.env` must point `ROBOTWIN_PYTHON` at the simulation environment's interpreter. Launchers source `local.env` automatically; for direct `python` commands export the variable in your shell first.

## SCM version error when installing cuRobo

The vendored cuRobo snapshot has no Git metadata. Install with `SETUPTOOLS_SCM_PRETEND_VERSION=0.7.0` (a label, not an upstream tag claim) and `--no-build-isolation` so it compiles against the already-installed torch.

## `expat` / XML parser crash on import

A migrated Python occasionally needs an isolated `expat` preload. Prefer creating a fresh virtual environment from a system Python 3.10 over patching the interpreter.

## `ffmpeg is required for evaluation videos`

Install `ffmpeg` system-wide or set `ROBOTWIN_VIDEO_FIRST_N=0` for runs where videos are not needed.

## Legacy `script/_install.sh` edited SAPIEN / mplib in place

That behaviour was removed. The current script does not modify installed packages. If a backend still requires a patch, apply it in your own environment, record it, and re-run the smoke tests.
