---
title: Language-Following Diagnostics
description: Failure decomposition, target reassignment with its controls, attribute-selection measurements and a three-level protocol that separate instruction-conditioned target selection, forecast agreement and task completion.
---

Final task success does not say *why* a system failed: it may have chosen the wrong object, chosen the right one and dropped it, or never responded to the instruction at all. ManipScope complements the leaderboard scores with a **diagnostic chain** that runs on any policy (where failures arise, whether the choice follows the instruction, and whether the scene change or a missing skill explains it), an **attribute study** that measures which target every episode selects on nine formal tasks, and a **three-level controlled protocol** — behaviour, future video, internal interventions — instantiated on π0.5 and Motus in a paired colour-selection study. The diagnostic runs use their own conditions and are **never pooled** with the [leaderboard]({{rel}}leaderboard/) denominators. All of them are implemented in the `diagnostics/` directory of the [code repository](https://anonymous.4open.science/r/ManipScope); [run commands](#running-the-diagnostics) are at the end of this page.

## Where failures arise

The formal runs record, for every episode, how far each candidate object moved. On the eleven pick-type selection scenes (13,200 formal episodes of the twelve policy checkpoints), 9,587 episodes fail. Of these failures, **84.6% displace a distractor**, 3.0% displace only the target and 12.4% displace nothing (paper Section 5.2, Appendix D.6). The profile separates scenes that success rates do not: `ref_block_on_plate` and `ref_block_behind_can` both stay below 10% success, but 71.8% of failures in the former displace only a distractor, whereas 60.1% in the latter displace nothing, a failure to act.

A first contact alone cannot tell choosing a wrong object from touching one in passing, so contact is also classified from the gripper state (grasp, push or brush; paper Appendix D.5). In 2,400 reruns with gripper-state records, 83% of failed episodes grasp a non-target and 5.8% of successful ones do: a wrong selection in a failed episode is a wrong grasp.

## Target reassignment

Each formal scene fixes one requested rule, so a success can come from a preference that happens to coincide with the request. Target reassignment runs the ten pick-type selection scenes again on the same frozen initial states, with the instruction naming each candidate in turn and the evaluator's target reassigned to it (paper Section 5.3, Appendix G.2). A state counts as *follow* if every instruction selects its own target (first object displaced ≥ 5 cm), *fixed* if every instruction selects the same object, *no move* if nothing is displaced, and *mixed* otherwise. An instruction-blind chooser that picks uniformly among the k candidates gives *follow* k<sup>−k</sup> and *fixed* k<sup>1−k</sup> per state.

| System | States | Follow (95% CI) | Fixed | No move | Mixed |
| --- | --- | --- | --- | --- | --- |
| LingBot-VA | 100 | 17 (11–26) | 50 | 2 | 31 |
| StarVLA | 100 | 9 (5–16) | 52 | 8 | 31 |
| π0.5 | 100 | 8 (4–15) | 56 | 2 | 34 |
| Motus | 100 | 2 (1–7) | 72 | 4 | 22 |
| X-WAM | 100 | 1 (0–5) | 87 | 1 | 11 |
| AHA-WAM | 100 | 1 (0–5) | 71 | 6 | 22 |
| G0.5 | 100 | 1 (0–5) | 64 | 6 | 29 |
| WLA | 100 | 0 (0–4) | 90 | 5 | 5 |
| FastWAM | 100 | 0 (0–4) | 72 | 10 | 18 |
| DM0.5 | 100 | 0 (0–4) | 65 | 5 | 30 |
| **Ten checkpoints pooled** | 1000 | 4 (3–5) | 68 | 5 | 23 |
| X-VLA<sup>§</sup> | 100 | 0 (0–4) | 69 | 9 | 22 |
| π0<sup>¶</sup> | 100 | 0 (0–4) | 44 | 17 | 39 |
| Instruction-blind chooser | | 16 | 33 | | |

Share of initial states (%) per class, ten states per scene. <sup>§</sup> conditioned on task-name strings; <sup>¶</sup> near-zero success on the RoboTwin source tasks; both are excluded from pooled statements.

**The selection does not change with the instruction.** Ten checkpoints follow every instruction on 39 of 1,000 states (3.9%), below the instruction-blind 16%, and displace the same object under every instruction on 68% (blind chooser: 33%). LingBot-VA and π0.5 follow colour (10/10 and 6/10 states of the three-colour scene). Selection tracks a preference: the block next to the plate is displaced first in 99/100 runs that request it, the block on the plate in 2/100. Formal success therefore records whether the preferred object happens to be the target (77.0% where it is, 1.2% where it is not).

## Controls: training tasks and source tasks

**Training tasks remove the scene change** (paper Appendix G.3). On three unmodified RoboTwin training tasks (`blocks_ranking_rgb`, `stack_blocks_three`, `blocks_ranking_size`) the same reassignment is applied. Five of six verified checkpoints never displace the blue block first under "Pick up the blue block." (0/100 runs; π0.5: 15/20), and on the size task eight checkpoints displace the requested largest block first in 1 of 160 runs. In all three tasks the object displaced first under every instruction is the one the scripted demonstrations handle first: the red block in the two colour tasks, the smallest block in the size task.

**Source tasks test prerequisite skills.** Under training instructions, in the same evaluator, nine of the ten pooled checkpoints complete at least nine of the ten linked source tasks in 70% or more of episodes. Without the six checkpoint–scene pairs whose linked source task is below 30%, every instruction is followed on 3.1% of states. Neither the scene change nor a missing skill explains the fixed selection.

**First-decision sensitivity** (paper Appendix E) measures, for all twelve checkpoints on the frozen states of the three-colour scene, how much the first 16 commanded joint targets change when only the instruction, only the layout, or only the sampling repeat changes.

![The three diagnostic levels of the paper's Figure 2: behavioural readout with instructions crossed with layouts, future-video readout comparing predicted frames with later contact, and internal intervention replacing future representations at the action-attention interface]({{rel}}assets/img/diagnostics/protocol-levels.jpg)

## Attribute selection and completion on the formal tasks

Task success alone does not reveal which object a system initially selects. The attribute study (paper §5.3, Appendix D) measures selection on nine D3 attribute tasks (`attr_color_block_3way`, `attr_bind_soap_box`, `attr_bind_bottle`, `attr_size_block_pick`, `attr_size_rank_middle`, `attr_category_can_plasticbox`, `attr_category_press_bell`, `attr_color_beat_block`, `attr_size_beat_smaller`) with five fixed trials per task: 45 episodes per system, 315 in total, for five policies (π0.5, Motus, G0.5, X-VLA, StarVLA) and two agents (GPT-6, Gemini 3.8 Flash). Instructions, initial object states, candidate properties and the event definition are matched across systems.

**Selection event.** The first physical step with a loaded interaction of at least 0.1 N; a unique candidate identifies the selected object. The effector is the gripper in seven tasks and the hammer in the two tool-hit tasks. Unique events occur in 252/315 episodes with 63 no-event outcomes; the bell task registers 26/35 successes with *no* loaded target events because its success predicate is proximity-based. At 0.01 N and 1 N the correct-target counts change by at most a few episodes per system, and tool-hit counts are unchanged (paper Figure 8).

![First loaded interaction and task success for five policies and two agents: stacked shares of target/success, target/failure, non-target and no-event episodes, gripper and tool-hit tasks shown separately (paper Figure 3)]({{rel}}assets/img/diagnostics/attribute-outcomes.jpg)

### System-level outcomes (paper Table 14)

| System | Unique event | Target event | Native success | Target / fail | No event |
| --- | --- | --- | --- | --- | --- |
| π0.5 | 37/45 (82.2 %) | 25/45 (55.6 %) | 27/45 (60.0 %) | 5 | 8 |
| Motus | 39/45 (86.7 %) | 22/45 (48.9 %) | 26/45 (57.8 %) | 2 | 6 |
| G0.5 | 32/45 (71.1 %) | 20/45 (44.4 %) | 32/45 (71.1 %) | 3 | 13 |
| X-VLA | 39/45 (86.7 %) | 20/45 (44.4 %) | 17/45 (37.8 %) | 12 | 6 |
| StarVLA | 37/45 (82.2 %) | 19/45 (42.2 %) | 17/45 (37.8 %) | 8 | 8 |
| GPT-6 | 37/45 (82.2 %) | 35/45 (77.8 %) | 31/45 (68.9 %) | 10 | 8 |
| Gemini 3.8 Flash | 31/45 (68.9 %) | 19/45 (42.2 %) | 16/45 (35.6 %) | 10 | 14 |

Two findings that a success score hides. First, **50/315 episodes (15.9 %) select the correct target and still fail** (30 among policies, ten per agent). Second, selection and completion rank systems differently: GPT-6 selects the target first in 35/45 trials against 19–25/45 for the five policies, yet its task success (31/45) is close to G0.5's (32/45) — the final outcome obscures the difference in initial target selection.

### Attribute correctness (paper Tables 16–17)

Attribute correctness scores the requested properties of the selected object, so partial matches are retained: selecting a large red object when a small red one was requested earns colour credit but neither size nor exact-target credit. Colour is evaluated on four tasks, size and category on three each (the soap/box task contributes to both colour and category). Highlights from paper Table 16: GPT-6 reaches 19/20 on colour and 12/15 on size; the policies range from 10–15/20 on colour and 3–7/15 on size; correctness *conditional on a unique event* is consistently higher than the all-episode rate because no-event episodes score zero.

On the conjunctive colour–category soap/box task (paper Table 17), 20/35 episodes select the exact target, six match colour only, eight category only, and one Gemini episode has no qualifying event. In a Motus example, "Raise the brown coffee box" leads to a first loaded interaction with the *brown soap* — colour satisfied, category not, task failed.

Agents follow the shared tool protocol with budgets of 120 calls, 3,300 s and the task's action budget; budget termination counts as failure (paper Appendix D.4). These are behavioural measurements at a fixed event, not a readout of latent intention, and the study does not change instructions within an episode — that is what the controlled protocol below adds.

## Three levels of evidence

| Level | Question | Requires | Scored when unavailable |
| --- | --- | --- | --- |
| **Behaviour** | Does the chosen target change with the instruction, and does the choice survive a changed layout? Does selection lead to completion? | Only closed-loop rollouts; works for black-box policies and tool-using agents | — |
| **Future video** | When a system predicts images, does the visible approach target agree with the instruction, and with what the system later contacts? | Access to predicted frames | not applicable |
| **Internal intervention** | Does replacing an internal representation change the action, and does the change point toward the alternative goal? | Access to internal representations | not accessible |

Unavailable levels are marked not applicable, never scored as zero. The organisation describes diagnostic *access*, not a serial "imagine then act" architecture, and no level assigns a global modality weight to a model family.

## Paired design and measurements

Each scene *s* is evaluated under two valid target instructions *t* ∈ {red, blue} and two layouts *ℓ* ∈ {0, 1}, where the second layout exactly exchanges the poses of the red and blue objects while the green distractor and the robot's initial state stay fixed. Swaps act on simulated object poses, not on recoloured images. The evaluator's target role follows the instruction and is not supplied to the policy.

<img class="fig-small" src="{{rel}}assets/img/diagnostics/paired-conditions.jpg" alt="The four paired conditions of one scene: original and red/blue-exchanged layout, each with &quot;Pick up the red block.&quot; and &quot;Pick up the blue block.&quot;" loading="lazy">

Let *c<sub>s,ℓ,t</sub>* = 1 when the **first recorded loaded gripper contact** is uniquely with the requested object; missing or ambiguous contact scores zero. Alongside contact accuracy and task success, two paired rates are reported:

- **Both instructions correct** — *P*<sub>instr</sub> = (1/2S) Σ<sub>s,ℓ</sub> *c<sub>s,ℓ,red</sub>* · *c<sub>s,ℓ,blue</sub>*: in the same view, both instructions must select their target. A system that always grasps the same object cannot pass, even if one instruction happens to succeed.
- **Both layouts correct** — *P*<sub>layout</sub> = (1/2S) Σ<sub>s,t</sub> *c<sub>s,0,t</sub>* · *c<sub>s,1,t</sub>*: the same instruction must pick the requested colour after the objects trade places.

These are paired *correctness* rates, not rates of changed actions. All four cells of a scene stay together in uncertainty estimation (scene-cluster bootstrap). Contact is a behavioural proxy: it is separate from the task's native success predicate and is not a measurement of hidden intention. Completion *among correctly selected episodes* can be reported with its own denominator, but it describes different subsets for different systems and does not rank motor competence.

## Controlled colour-selection study

**Setup.** A separate version of the D3 task [`attr_color_block_3way`]({{rel}}sim-tasks/attr_color_block_3way/) with 20 new scene seeds (200000–200019), two instructions and two layouts: 80 closed-loop trajectories per checkpoint (160 in total), plus 80 first-decision internal interventions on Motus. Both systems receive three RGB views, the instruction and the 14-D joint state; native chunks stay at 32 (π0.5) and 16 (Motus) commands, so replanning frequency is not equalised. Each run stops at native success or 256 action calls. Initial RGB, robot state and the exact red–blue exchange were checked for all 20 scene groups; no scene was selected or discarded by outcome, and no expert-success filter was applied.

**Contact proxy.** Candidate-object contact with a gripper link whose summed contact impulse divided by the physics timestep is at least 0.1 N; only the first qualifying event is scored. Physics telemetry is sampled every 40 ms (simulator step 4 ms), so a briefer earlier event can be missed. Changing the threshold to 0.01 N or 1 N leaves both systems' target-correct counts unchanged.

### Behaviour level (paper Table 18)

| Measurement ↑ | π0.5 | Motus |
| --- | --- | --- |
| Correct target contact | 86.2 % [77.5, 93.8] (69/80) | 40.0 % [31.2, 48.8] (32/80) |
| Both instructions correct | 72.5 % [55.0, 87.5] (29/40) | 2.5 % [0.0, 7.5] (1/40) |
| Both layouts correct | 72.5 % [55.0, 87.5] (29/40) | 20.0 % [10.0, 30.0] (8/40) |
| Task success (≤ 256 calls) | 78.8 % [68.8, 87.5] (63/80) | 40.0 % [31.2, 48.8] (32/80) |

Intervals are 95 % scene-cluster bootstrap intervals (20 scenes, 20,000 resamples, all four cells of a sampled scene retained); they are descriptive, not multiplicity-adjusted tests, and a degenerate interval at a sample boundary does not imply population certainty. Completion among correctly contacting trajectories is 63/69 for π0.5 and 32/32 for Motus.

![Paired behavioural endpoints for π0.5 and Motus with scene-bootstrap intervals, and the Motus forecast–contact agreement matrix: 46 jointly wrong, 31 jointly correct, 3 unresolved (paper Figure 4)]({{rel}}assets/img/diagnostics/paired-outcomes.jpg)

Motus's 40 % task success coexists with a single successful instruction pair: its first contact is the red block in 25/40 red-requested and 23/40 blue-requested conditions, so most of its successes come from conditions in which red happened to be requested. The six π0.5 trials that contact the correct target and still fail show information that final success alone discards; they do not isolate a purely motor cause.

### Output sensitivity

First-decision sensitivity holds observation, state and sampling noise fixed and changes one factor. Joint RMS over the first 16 predicted commands (gripper coordinates excluded):

| Response (scene mean, rad) | π0.5 | Motus |
| --- | --- | --- |
| Language (red ↔ blue instruction) | 0.191 | 0.096 |
| Layout (red ↔ blue poses exchanged) | 0.191 | 0.394 |
| Noise (sampling seed 17 → 29) | 0.028 | 0.220 |
| "Please pick up …" wording (auxiliary, original layout) | 0.005 | 0.023 |

![Language, layout and noise response magnitudes per scene, with means and intervals]({{rel}}assets/img/diagnostics/response-magnitude.jpg)

These magnitudes describe responses to the tested interventions, not global modality weights: moving an object legitimately changes the required motion, and a pixel or joint change caused by the instruction need not switch to the correct target. Magnitudes must be read together with the target-switching rates above. Motus's language-induced change of its final predicted head frame is an RGB MAE of 0.015 (intensities in [0, 1]).

### Future-video level

![Scene 200000: (a) head-camera views of the original and red/blue-exchanged layouts before execution; (b) Motus's last predicted head-camera frame of the first decision in the original layout for the red and the blue instruction, both visibly approaching red]({{rel}}assets/img/diagnostics/source-panels.jpg)

Source imagery from the first scene (seed 200000), selected by index rather than by performance. (a) Simulator head-camera views before execution; both instructions are tested in each layout. (b) Last predicted head-camera frames from Motus's first decision in the original layout: both forecasts visibly approach red although different colours were requested. The frames retain their native resolution; they are forecast endpoints, not measured contact frames.

Motus jointly predicts eight video frames with each 16-command chunk. A fixed RGB rule reads the last predicted head frame of the first decision (dark gripper-like pixels near a coloured block; nearest candidate within 12 px, margin ≥ 6 px over the next), developed on scene 200000. The readouts have not received independent blinded annotation.

- Readable approach target: 77/80. Target agrees with the instruction: 31/80. Both instructions of a view predicted correctly: 1/40.
- All 77 readable forecasts agree with the object the system later contacts first, **including 46 wrong targets**.
- First contact happens in the second action chunk, beyond the forecast horizon, so this is target *identity* correspondence across horizons, not a frame-aligned prediction of a contact event.

Forecast–execution agreement can therefore preserve a wrong target. Predicted video is additional checkable evidence, but agreement is neither instruction following nor proof that the future representation causes the action; in this configuration Motus generates video and actions jointly rather than serially.

### Internal-intervention level (paper Table 19)

For each of 80 Motus first-decision conditions, the *donor* is the same observation, state and noise under the other instruction. At all 30 joint-attention layers and ten denoising steps, the K/V entries of 120 tokens in the first near-future temporal group, as read by the action queries, are replaced by the donor's, and only the affected action-expert output rows are written back. Token groups named *future*, *current video* and *understanding* are implementation segments that may already carry mixed information after joint attention.

| Intervention | Joint RMS (rad) | Shift toward donor goal (mm) |
| --- | --- | --- |
| Original-value writeback (sham) | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| Full instruction change | 0.096 [0.033, 0.173] | 2.529 [0.734, 5.339] |
| Future replacement | 0.030 [0.013, 0.051] | 0.560 [−0.019, 1.299] |
| Future, half strength | 0.010 [0.005, 0.015] | 0.041 [−0.190, 0.257] |
| Current-video replacement | 0.007 [0.003, 0.012] | 0.157 [0.017, 0.347] |
| Understanding replacement | 0.006 [0.003, 0.011] | 0.058 [−0.366, 0.430] |
| Future, norm-matched | 0.030 [0.013, 0.051] | 0.544 [−0.043, 1.292] |
| Current video, norm-matched | 0.015 [0.006, 0.025] | 0.357 [0.090, 0.748] |
| Understanding, norm-matched | 0.080 [0.030, 0.142] | 1.330 [−1.560, 4.050] |
| Future, scrambled + norm-matched | 0.003 [0.002, 0.005] | 0.048 [−0.041, 0.162] |

Means with 95 % scene-cluster intervals over 20 scenes. The directional endpoint converts the first 16 commanded actions to gripper positions by forward kinematics in an independent scene and measures the change in preference for the donor's target relative to the recipient's; positive values favour the donor goal. It is commanded geometry, not executed motion, selection or success, and averaging over arms and time can hide arm-specific or transient effects.

![Action response and requested-goal direction per intervention, BF16 perturbation-norm audit, and the count of readable different-target contrasts]({{rel}}assets/img/diagnostics/internal-interventions.jpg)

Replacing the near-future representation changes the predicted actions (0.030 rad) but does not establish consistent transfer toward the donor goal (0.560 mm, interval crossing zero). Only 31/80 donor forecasts visibly select their requested target, and only two recipient–donor pairs, both from the swapped layout of one scene, predict *different* readable objects; their shift is −4.432 mm, reported descriptively without an interval. After BF16 arithmetic, applied perturbation norms fall within 10 % of the reference at 100 % / 96.32 % / 100 % / 99.98 % of sites (future / current / understanding / scrambled), so nominal norm matching is not exact everywhere. No closed-loop rollout was run with an intervention applied, so neither task benefit nor its absence is established.

## What the study does and does not show

- Paired correctness separates *not switching the target* from *selecting correctly and then failing*; final success alone cannot.
- Agreement between predicted video and behaviour does not substitute for instruction correctness.
- Internal interventions must report direction, donor validity and controls, not only the most sensitive example.
- Scope: two checkpoints, one three-colour task family, 20 scenes, limited wording and sampling settings. Pretraining, adaptation data, chunk length, feedback access and controllers all differ between systems; no symmetric internal measurement was made for other architectures. The results do not rank VLA, world-model or agent classes.

## Applying the protocol to other policies and agents

1. **Check the interface first.** Does the exact instruction reach the model? Do vision and state match across the paired conditions? Is sampling reproducible? Do tool and feedback permissions agree?
2. **Run grouped instruction and layout interventions** and read the paired correctness rates. A small action response only shows weak sensitivity; it does not identify the failing module.
3. **Route the follow-up by pattern.** Neither forecasts nor actions switch → check language conditioning and target binding. Forecasts switch but actions do not → check action generation and the connecting computation. Both targets correct but the task fails → check control and physical execution. Actions correct but forecasts wrong → check the video readout's reliability and forecast–action consistency. These are investigation routes, not identified root causes.
4. **Black-box agents** use the same target-switching, layout-tracking, stage and execution metrics, and additionally log tool choice, tool arguments, interface rejections and corrections after feedback. An explicit plan is an observable output, not ground truth about internal reasoning; without video or internal access the corresponding levels are marked not applicable.

## Running the diagnostics

The code is in `diagnostics/` of the [code repository](https://anonymous.4open.science/r/ManipScope) (overview and definitions in `diagnostics/README.md`). Every diagnostic runs against any policy registered in `suite/policies.yaml`, with the formal evaluator and frozen initial states:

```bash
python3 diagnostics/run_diagnostic.py run selection_events --policy <policy> --start-server   # Sec. 5.2, App. D.5
python3 diagnostics/run_diagnostic.py run rotation         --policy <policy> --start-server   # Sec. 5.3, App. G.2
python3 diagnostics/run_diagnostic.py run training_control --policy <policy> --start-server   # App. G.3
python3 diagnostics/run_diagnostic.py run source_baseline  --policy <policy> --start-server   # App. G.3
python3 diagnostics/run_diagnostic.py run first_decision   --policy <policy> --start-server   # App. E
python3 diagnostics/analysis/rotation.py runs/diagnostics/rotation                            # follow / fixed / no move / mixed, blind reference
python3 diagnostics/analysis/failure_decomposition.py <policy>=<formal run directory>         # Sec. 5.2, App. D.6
```

The paired colour study, the future-video readout and the internal key/value intervention for Motus are in `diagnostics/probes/` (App. E.1–E.3). Example remedies (inference-time language guidance and an agent-selection relay, App. G.4) are in `diagnostics/remedies/`. The behavioural diagnostics need only the policy interface; the probes have been validated on the two continuous joint-action checkpoints above, and other architectures need their own adapters and checks.

Method background: Motus's joint video–action modelling ([paper](https://arxiv.org/abs/2512.13030), [code](https://github.com/thu-ml/Motus)); activation-patching methodology and its interpretation limits ([Zhang & Nanda](https://arxiv.org/abs/2309.16042)).
