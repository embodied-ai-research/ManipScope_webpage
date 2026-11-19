---
title: Quick Evaluation
description: Run a single scene, a dimension, or the full 48-scene formal protocol with suite/run_suite.sh.
---

Evaluation is launched with one shell entry point. It validates inputs, starts the policy service, runs the simulator against it, and writes results plus provenance:

```bash
bash suite/run_suite.sh <policy> [scene ...]
```

`<policy>` is a key from `suite/policies.yaml` (`dm05`, `pi05`, `xvla`, `starvla`, …). With no scene arguments all 48 formal scenes run sequentially in manifest order.

## Dry run

Always start with a dry run. It checks `configs/local.env`, the manifest, seeds, step limits and required backend variables without starting a simulation or a model:

```bash
DRY_RUN=1 bash suite/run_suite.sh dm05 move_can_coaster
# Validated 1 scenes for dm05; run=dm05_...; port=7891
```

## Single scene

```bash
EPISODES=1 RUN_NAME=smoke_dm05 bash suite/run_suite.sh dm05 move_can_coaster
```

The runner launches `suite/launch/start_dm05.sh` in its own process group, waits for the port, evaluates, then stops the service. A scene failure makes the runner return non-zero after finishing the remaining scenes.

## Reusing a running service

Existing services are never reused silently. Opt in explicitly:

```bash
AUTO_LAUNCH=0 PORT=7891 EPISODES=1 bash suite/run_suite.sh dm05 move_can_coaster
```

This is also how externally hosted policies (see [Policy Integration]({{rel}}usage/policy-integration/)) are evaluated.

## Full formal protocol

```bash
EPISODES=50 RUN_NAME=dm05_formal bash suite/run_suite.sh dm05
```

Defaults are those of the frozen manifest: 50 episodes per scene, `demo_clean`, unseen instructions, seeds in file order. The formal seed lists are held by the organizers; generate development seeds with `suite/gen_seeds.py` before a local run. Requesting more episodes than saved seeds fails early.

## Multi-GPU

```bash
bash suite/run_parallel.sh dm05 0,1 50    # policy, GPU list, episodes
python3 suite/collect.py --stages         # aggregate when all lanes finish
```

Each lane launches its own inference service and co-locates model and simulator on its GPU; check memory headroom. Use a distinct `PORT_BASE` when running several campaigns at once. `suite/run_robust.sh` adds retry-on-failure around the same lanes.

## Controlling GPUs, video and seeds

| Variable | Default | Meaning |
| --- | --- | --- |
| `SIM_GPU` | `0` | GPU for SAPIEN rendering and cuRobo planning |
| `GPU` | `SIM_GPU` | GPU for the model service |
| `EPISODES` | `50` | Episodes per scene (≤ 100 frozen seeds) |
| `SCENE_TASK_CONFIG` | `demo_clean` | Task config used by the formal protocol |
| `ROBOTWIN_FROZEN_SEEDS` | `1` | `0` = exploratory random seeds, **not** the formal protocol |
| `ROBOTWIN_VIDEO_FIRST_N` | `10` | First N seeds get head-camera video, success or not |
| `MAX_SUCC_VIDEOS` / `MAX_FAIL_VIDEOS` | unset | Additional caps on saved videos |
| `EVAL_WRIST_VIDEO` | `0` | Also record the left-wrist camera |
| `STAGE_LOG` | unset | File receiving per-episode stage progress for sequential scenes |

## Output

```
eval_result/<run>/<scene>/<Plugin>/<task-config>/<checkpoint>/<timestamp>/
  _result*.txt          success count, per-episode outcomes
  _run_metadata.json    commit, dirty state, controls, protocol hashes
  instructions          actual sampled instruction per episode
  *.mp4                 head-camera videos for eligible seeds
suite/logs/<run>/server_<port>.log
```

Aggregate and compare:

```bash
python3 suite/collect.py                  # table of all policies × scenes
python3 suite/collect.py --gradient       # L1 → L3 monotonicity self-check
python3 suite/compare_runs.py RUN_A RUN_B # paired per-seed comparison
python3 suite/gen_eval_report.py          # markdown report
```
