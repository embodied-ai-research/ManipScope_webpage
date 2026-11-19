---
title: Configurations
description: Task configs, camera and embodiment settings, step limits, and per-backend environment variables.
---

## Task configs

Task configs live in `task_config/*.yml` and control rendering, domain randomization and recorded observations. The formal protocol uses a single config, `demo_clean`: clean background, fixed lighting and table height, no clutter. Key fields:

```yaml
embodiment: [aloha-agilex]
language_num: 100
domain_randomization:
  random_background: false
  cluttered_table: false
  random_light: false
camera:
  head_camera_type: D435
  wrist_camera_type: D435
data_type:
  rgb: true
  depth: false
  endpose: true
  qpos: true
eval_video_log: true
```

Do not use `demo_randomized` for formal reporting: its cluttered table can throw `UnStableError` during `setup_demo(is_test=True)`, outside the evaluator's retry scope.

## Observations delivered to a policy

Every adapter receives the same observation dictionary from `script/eval_policy.py`:

| Key | Content |
| --- | --- |
| `head_camera_rgb`, `left_camera_rgb`, `right_camera_rgb` | 320×240 RGB, D435 intrinsics |
| `qpos` | 14-dim joint positions (7 per arm incl. gripper) |
| `endpose` | left/right end-effector poses |
| `instruction` | Sampled natural-language instruction |

Policies may resize, crop or encode images differently. Those choices belong to the method and must be disclosed in reports.

## Action interfaces

| Mode | Adapter call | Notes |
| --- | --- | --- |
| Joint | `take_action(action, action_type="qpos")` | 14-dim absolute joint targets; step budget counts each call |
| End-effector | `take_action(action, action_type="ee")` | 16-dim pose targets, executed via cuRobo; one call = one planned segment |

The step limit is counted in `take_action` calls in both modes, so EE-mode policies consume fewer steps per motion. Disclose the control mode when reporting.

## Step limits

`task_config/_eval_step_limit.yml` gives per-scene budgets: 41 formal scenes use 1000, 7 use 600. The same limit applies to every policy on a scene; cite it when reporting per-scene numbers.

## Frozen seeds

The formal seed lists (100 expert-checked initial states per scene) are held by the organizers to protect public-evaluation fairness; their SHA-256 digests are recorded in `protocol.lock.json`, and formal evaluation of a new policy reuses them. For local development and for running the diagnostics on your own policy, generate seed files of the same format with `python suite/gen_seeds.py <scene> 100` (default search start 300000; see `suite/seeds/README.md`). Seeds are consumed in file order and also fix the sampled instruction. A formal scene without a seed file is refused, and results on development seeds are not leaderboard results.

## Backend environment variables

Set these in `configs/local.env` for the backend you evaluate. Launchers are under `suite/launch/`.

| Policy key | Required variables | Launcher |
| --- | --- | --- |
| `dm05` | `DM05_MODEL`, `OPENDM_DIR`, `OPENDM_ENV` | `start_dm05.sh` |
| `pi05` | `OPENPI`, `PI05_CKPT` | `start_pi05.sh` |
| `pi0` | `OPENPI`, `PI0_CKPT` | `start_pi0.sh` |
| `xvla` | `XVLA_CKPT`, `XVLA_DIR` | `start_xvla.sh` |
| `wla_formal` | `WLA_MODEL_ID`, `WLA_ROOT` | `start_wla_formal.sh` |
| `starvla` | `STARVLA_CKPT`, `STARVLA_DIR` | `start_starvla.sh` |
| `fastwam` | `DIFFSYNTH_MODEL_BASE_PATH`, `FASTWAM_CKPT`, `FASTWAM_ROOT`, `FASTWAM_STATS` | `start_fastwam.sh` |
| `ahawam` | `AHAWAM_CKPT`, `AHAWAM_ROOT`, `AHAWAM_STATS`, `DIFFSYNTH_MODEL_BASE_PATH` | `start_ahawam.sh` |
| `xwam` | `TOKENIZERS_PARALLELISM`, `XWAM_EXP`, `XWAM_ROOT`, `XWAM_WAN_DIR` | `start_xwam.sh` |
| `g05` | `G05_ROOT` | `start_g05.sh` |
| `openwam` | `OPENWAM_CKPT`, `OPENWAM_DIR` | `start_openwam.sh` |
| `motus` | `MOTUS_CKPT`, `MOTUS_ROOT`, `MOTUS_VLM`, `MOTUS_WAN` | `start_motus.sh` |
| `lingbot_va` | `LB_CKPT`, `LB_DIR` | `start_lingbot_va.sh` |
| `eef_bridge` | `GPT6_BRIDGE_TOKEN_FILE`, `PORT`, `AUTO_LAUNCH=0` | external |

Upstream code and weight links for each backend are on the [Policies]({{rel}}policies/) page.

## Protocol lock

`protocol.lock.json` hashes the scene implementations, manifest, instruction pools, step limits and seeds. `tools/validate_repo.py` fails when any of them change. Refreshing the lock is a deliberate act for a new protocol version:

```bash
python3 tools/lock_protocol.py --version formal48-v2
python3 tools/validate_repo.py
```
