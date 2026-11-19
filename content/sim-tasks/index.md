---
title: Simulation Tasks
---

ManipScope runs on RoboTwin 2.0 (SAPIEN 3) with the dual-arm `aloha-agilex` embodiment. Each evaluation scene is derived from RoboTwin base tasks: its scene card records the source tasks it links to, the added requirements, the changed conditions and the unavoidable motor differences. This mapping is evaluation metadata, not a reference plan. Scenes are eval-only; no demonstrations are distributed.

Each scene specifies an instruction, an initial-state distribution, target objects, spatial conditions, action-order requirements and a terminal success rule. Task pages show one successful rollout re-rendered with a presentation camera, the instruction templates, a plain-language description, the task family and level, the RoboTwin source skills, the declared goal, the step limit, the scoring rule and the per-scene results of the paper snapshot.

Training data is the unchanged RoboTwin 2.0 demonstration set of the source tasks; ManipScope adds evaluation scenes only, so there is no separate training split to show.

## World-axis orientation

RoboTwin uses a robot-centred table frame: **x < 0 is the robot's left**, **x > 0 its right**; **y increases away from the robot** (`behind`) and decreases towards it (`front`); **z is up**, table surface at about z = 0.74 m. Spatial-relation criteria (`rel`, `between`) are evaluated in this frame.

## Scene selection

Scenes entered the formal set only after a scripted expert could generate solvable seeds. Three candidates were removed from a 51-scene list because expert yield was below 30 % (12–15 % measured), which would have concentrated the retained states in a narrow subset; the exclusions are feasibility decisions, not removals based on policy scores. Expert-solvable seed filtering also limits the state distribution to which results apply.

!!! note "Rollout videos"
    Each scene page shows one successful rollout: GalaxeaVLA (G0.5) for 41 scenes and, where the re-rendered G0.5 candidates produced no success, the GPT-6 agent for the remaining 7. Recorded scene states of a scored episode are replayed under a separate presentation camera (1080p, 15 fps) without additional policy inference; the video shows simulation time only and is played at ×1–×8 so that every clip stays under 20 s. The label is the actual outcome of the re-run, not the historical result, and a single showcased episode is not an estimate of a policy's success rate. GPT-6 clips carry a side panel with the note the agent attached to each tool call.
