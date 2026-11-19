---
title: Evaluation Issues
description: Known pitfalls when running policies against the formal protocol.
---

## `Port 7891 already in use`

The runner refuses to attach to a service it did not start. Either stop the stray service or opt in with `AUTO_LAUNCH=0 PORT=7891`. Simultaneous campaigns on one host need distinct `PORT_BASE` values.

## `Set these paths in configs/local.env: DM05_MODEL, ...`

Each backend declares `required_env` in `suite/policies.yaml`. Fill them in `configs/local.env` with absolute paths. A dry run reports missing variables without starting anything.

## `UnStableError` after seed acceptance

Cluttered task configs (`demo_randomized`) let distractors settle unstably during `setup_demo(is_test=True)`, which is outside the evaluator's retry scope and aborts the run. Use `demo_clean`, the formal protocol config.

## Requesting more episodes than saved seeds

`EPISODES` must not exceed the number of seeds in `suite/seeds/<scene>.json`. Preflight fails early with a clear message, also when the file is absent: the formal seed lists are held by the organizers, so generate development seeds with `suite/gen_seeds.py` first.

## Head-camera video shows only a dozen distinct frames

Historical issue: frames were read from the cached observation, refreshed once per action chunk. Frames are now re-rendered per `take_action`, so the video follows the simulation. If you still observe frame repetition, check that your adapter is not batching several `take_action` calls behind one observation.

## Sequential scenes always score zero

`seq` goals require stages in order. Check the `STAGE_LOG` output to see whether stage 1 is ever reached. Adapters must call `maybe_bridge_to_stage2()` at chunk boundaries if the scene provides it; otherwise the second instruction segment is never issued.

## A scene the expert solves scores 0 across policies

Twelve formal scenes scored zero for the first baseline while passing expert screening. Inspect the saved videos before concluding the criterion is too strict; several such scenes are solved by other policies (see the [leaderboard]({{rel}}leaderboard/)). Criterion changes require a new protocol version.

## End-effector policies consume fewer steps

`step_lim` counts `take_action` calls. In `action_type="ee"` mode a single call executes a planned trajectory segment, so EE policies effectively have a larger motion budget. Disclose the control mode; do not mix EE and joint results without stating it.

## Mirrored scenes changed the answer

`MIRROR` is enabled for selection scenes (attribute binding, reference structure) so the target is not always on one side. It must stay disabled for spatial-relation and ordinal scenes, where mirroring inverts the instruction. This is fixed per scene in the frozen release.

## Comparing runs from different code revisions

`_run_metadata.json` records commit, dirty state and protocol hashes per scene. Only compare runs whose protocol hashes match; `suite/compare_runs.py` performs a paired per-seed comparison for runs on the same protocol.
