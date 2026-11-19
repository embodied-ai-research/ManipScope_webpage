---
title: Policy Integration
description: Add a new policy adapter, register it, and connect an externally hosted agent through the EEF bridge.
---

The simulator never imports model code. A policy is exposed as a small **adapter** in the simulation environment that talks to an **inference service** running in the model's own environment. The evaluator (`script/eval_policy.py`) drives the adapter through three functions.

```
script/eval_policy.py ──► policy/<Plugin>/deploy_policy.py ──HTTP/socket──► your model server
        │                       get_model()  eval()  reset_model()
        └── envs/<scene>.py  (observations, take_action, check_success)
```

## 1. Write the adapter

Create `policy/<Plugin>/deploy_policy.py` and `policy/<Plugin>/deploy_policy.yml`.

```python
# policy/MyPolicy/deploy_policy.py
import numpy as np, requests

class Client:
    def __init__(self, base_url, cameras, action_horizon):
        self.url, self.cameras, self.horizon = base_url, cameras, action_horizon

    def infer(self, obs, instruction):
        payload = {"instruction": instruction,
                   "images": {c: encode_png(obs["observation"][c]["rgb"]) for c in self.cameras},
                   "qpos": obs["joint_action"]["vector"].tolist()}
        return np.asarray(requests.post(self.url + "/infer", json=payload, timeout=300).json()["actions"])

def get_model(usr_args):
    return Client(usr_args["base_url"], usr_args["cameras"].split(","), int(usr_args["action_horizon"]))

def eval(TASK_ENV, model, observation):
    instruction = TASK_ENV.get_instruction()
    actions = model.infer(observation, instruction)          # (horizon, 14) absolute qpos
    assert np.isfinite(actions).all(), "non-finite action"   # NaN would crash SAPIEN silently
    for a in actions:
        TASK_ENV.take_action(a, action_type="qpos")
        if TASK_ENV.eval_success or TASK_ENV.take_action_cnt >= TASK_ENV.step_lim:
            break
        bridge = getattr(TASK_ENV, "maybe_bridge_to_stage2", None)
        if bridge: bridge()                                   # sequential scenes only

def reset_model(model):
    pass  # clear history / KV cache between episodes
```

```yaml
# policy/MyPolicy/deploy_policy.yml
policy_name: MyPolicy
task_config: demo_clean
ckpt_setting: mypolicy
instruction_type: unseen
base_url: http://localhost:7900
cameras: "head_camera_rgb,left_camera_rgb,right_camera_rgb"
action_horizon: 32
```

Rules every adapter must follow:

- Return **finite** actions; reset state between episodes.
- Respect `step_lim` and `eval_success`; do not blindly execute a whole chunk after success.
- Document image ordering, resize/encoding, state layout, coordinate conventions and action horizon.
- Log stage progress (`record_stage`) when the scene exposes stages so failures can be localised.

Use `policy/DM05/deploy_policy.py` (joint space) or `policy/XVLA/deploy_policy.py` (end-effector space) as templates.

## 2. Add a launcher

`suite/launch/start_<key>.sh` starts the inference service inside the model's environment, honouring `GPU` and `PORT`. Read model paths from environment variables defined in `configs/local.env`; never hard-code personal paths.

## 3. Register the policy

Add an entry to `suite/policies.yaml` under `policies` (only for implemented adapters; planned ones go to `planned_policies`):

```yaml
mypolicy:
  hf_repo: https://huggingface.co/...
  code_repo: https://github.com/...
  desc: One-line model description
  policy_name: MyPolicy
  ckpt_setting: mypolicy
  server: http
  port: 7900
  launch: suite/launch/start_mypolicy.sh
  required_env: [MYPOLICY_CKPT, MYPOLICY_DIR]
```

Then document the backend in `docs/BACKENDS.md` and run:

```bash
DRY_RUN=1 bash suite/run_suite.sh mypolicy move_can_coaster
EPISODES=1 RUN_NAME=smoke_mypolicy bash suite/run_suite.sh mypolicy move_can_coaster
```

## 4. Externally hosted agents (EEF bridge)

For agents that cannot run locally (e.g. a VLM-based planner behind an API), the `eef_bridge` registration accepts end-effector commands over an authenticated loopback HTTP bridge. Set `AUTO_LAUNCH=0`, `PORT` and `GPT6_BRIDGE_TOKEN_FILE`; the adapter sends the token as a Bearer header, accepts loopback origins only, and disables redirects.

The bridge must implement `POST /reset` and `POST /infer`. Infer input carries `instruction`, base64 PNG `images` (head/left/right), `eef_state`, `joint_state`, `feedback`, `contact_feedback`, `step`. Output is one of:

```json
{"type": "finish",   "note": "..."}
{"type": "rejected", "note": "..."}
{"type": "move_eef", "arm": "left", "position": [x, y, z], "quaternion_wxyz": [w, x, y, z], "gripper": 1}
```

Commands are bounds-checked before execution. Per-episode model-call and wall-time budgets apply and must be reported separately from step budgets. No provider implementation or credentials ship with the repository.

## 5. Reporting

A common evaluator does not equalise action spaces, inference budgets or training data. Alongside success rates, report: model and backend revision, checkpoint, control mode (joint vs EE), action horizon and replanning interval, image preprocessing, hardware, and sampling settings. The per-task `_run_metadata.json` records the evaluator-side half of this.
