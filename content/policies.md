---
title: Policies
---

Adapters are thin clients: they encode observations, call the model service, and feed the returned actions to the simulator step by step while honouring the step limit and early success. Joint-space policies (DM0.5, π0, π0.5, StarVLA, FastWAM, AHA-WAM, G0.5, Motus) return chunks of 14-D absolute joint/gripper targets; end-effector policies (X-VLA, WLA, X-WAM, LingBot-VA) return pose targets that RoboTwin's `take_action(ee)` executes through cuRobo planning. Reported success therefore includes the effects of state representation, action conversion and motion planning; cross-model differences cannot be attributed solely to instruction following or generalization.

The website separates **learned policies** (VLA and world-action models) from **agent systems** (an explicit language-model agent layer using tools or a controller). A motion planner inside an EEF adapter alone does not make a policy an agent; an entry must describe its actual execution path. An earlier internal WLA integration that mistakenly used the 14-D joint interface is excluded from all comparisons.

Descriptions below record the *evaluated* configuration, which can differ from the modules a model paper describes: several world-action checkpoints ran without their future-video, depth or world-expert branches, and G0.5 ran in continuous mode without autoregressive action tokens or CoT. The [provenance section](#provenance) lists these settings per checkpoint together with the three layers of training provenance.

See [Policy Integration]({{rel}}usage/policy-integration/) for adding a new adapter.
