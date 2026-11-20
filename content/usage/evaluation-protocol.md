---
title: Evaluation Protocol
description: What is frozen, how episodes are scored and aggregated, what is measured beyond success, and what must be disclosed.
---

## Task requirements and generalization

Each scene specifies an instruction, an initial-state distribution, target objects, spatial conditions, action-order requirements and a terminal success rule. An evaluated system maps its permitted observations and the instruction to actions through its recorded controller or tools.

- **Instruction following** concerns whether behaviour satisfies the stated requirements.
- **Generalization** concerns performance under a *declared* change from training or prior task exposure. Each scene is linked to RoboTwin source tasks that identify relevant skills, objects or relations; the scene card records the added requirements and changed conditions. Calling a result *spatial* or *compositional* generalization additionally requires a documented change in layout, relation or combination relative to the documented training data; unknown pretraining exposure limits the claim to the documented adaptation data.
- **Execution measurements** record selection and progress toward the physical goal.

These questions overlap within scenes and do not define independent latent abilities. Source-task results with the same system configuration are supporting evidence for a transfer analysis, not a guarantee that a derived task isolates generalization.

## The frozen release

The frozen release is defined by five checked-in artefacts, hashed together in `protocol.lock.json`:

| Artefact | Location |
| --- | --- |
| Scene membership and metadata | `suite/scenes_v2.yaml` |
| Scene implementations | `envs/<scene>.py`, `envs/_compo_scene.py` |
| Instruction pools (seen / unseen) | `description/task_instruction/<scene>.json` |
| Step limits | `task_config/_eval_step_limit.yml` |
| Frozen seeds and initial poses | organizer-managed private seed lists (retained privately to protect public-evaluation fairness; evaluation runs through the public interface) |

The paper reports the code freeze as `formal-eval-v1` at commit `39808b6`. Generators (`suite/table.py`, `suite/gen_scenes.py`) produce *candidates* under `out/`; they do not modify the release.

## Episodes and inputs

- **48 scenes** in six task families (D1–D6: 10 / 9 / 9 / 7 / 6 / 7 tasks), evaluated in manifest order.
- **100 expert-checked initial states per scene**; each fixes the initial layout and the sampled instruction, so every system faces the identical episode list. A scripted expert checks task feasibility before initial states are fixed; expert demonstrations for training on the evaluation scenes are deliberately not part of the release. The paper evaluates all 100 for policies (4,800 episodes per checkpoint) and the first 5 for agents (240 episodes). The corresponding seed lists are organizer-managed and retained privately.
- Task config `demo_clean`; instruction type `unseen`.
- **Observations**: three RGB views (head, left wrist, right wrist) at 320 × 240 plus proprioception; no depth, no privileged object state. Model-side preprocessing (resize, encoding, view concatenation) belongs to the method.
- **Step limits**: 1,000 recorded `take_action` calls in 41 scenes and 600 in seven, fixed per scene across methods. End-effector policies execute a planned segment per call, so the recorded counter is not comparable across control interfaces.
- Videos: the first 10 seeds per scene are recorded regardless of outcome.

`ROBOTWIN_FROZEN_SEEDS=0` is an exploratory mode. Results obtained with it must not be presented as the formal protocol.

## Task success

Task success is the primary measurement. An episode succeeds when it satisfies the instruction's required target, goal and, when relevant, order conditions. For a target-selection task, let *q<sub>i</sub>* indicate correct target selection and *g<sub>i</sub>* physical goal completion in episode *i*; the success label is *y<sub>i</sub> = q<sub>i</sub> g<sub>i</sub>*. A sequence additionally requires all specified stages in order. Task success rate is the fraction of valid episodes with *y<sub>i</sub>* = 1. Timeouts and inaction count as failures; simulator-invalid episodes are identified independently and handled by a predeclared rerun rule.

In the current implementation, generated scenes (`CompoScene`) realise the two factors as:

1. **Selection (EXCLUSIVE)** — a movement goal requires target displacement above 5 cm and greater than every distractor's; the first object crossing the threshold must be the target, simultaneous crossings resolve by greatest displacement, and tools and goal references are excluded from the distractor set. Reference objects must remain within 5 cm of their initial positions. Press and beat goals use location/contact conditions and reject distractor displacement of 5 cm or more. In the formal-task attribute study, selection is additionally measured at the first physical step with a loaded interaction of at least 0.1 N (gripper in seven tasks, hammer in two tool-hit tasks), with checks at 0.01 and 1 N.
2. **Goal** — the declared end state (`lift`, `on`, `stack`, `in`, `rel`, `between`, `press`, `seq`, `dual_carry_to`; `moved` only for L1 pure-grasp scenes), with reference objects required to remain stable.

Hand-written scenes keep task-specific `check_success` implementations that follow the same principle.

## Measurements beyond success

These measurements describe observable behaviour, not internal understanding. Attribute selection is now measured on nine attribute tasks (paper §5.3 and Appendix D); subtask completion remains to be exported for the full suite.

- **Attribute selection** (measured; see the [attribute study]({{rel}}diagnostics/#attribute-selection-and-completion-on-the-formal-tasks)). For a required attribute *a*, *z<sub>i,a</sub>* = 1 when the object chosen at the predefined interaction event satisfies the instruction (Eq. 2 in the paper). Per-scene rate *S<sub>c,a</sub>* averages over the eligible episodes *E<sub>c,a</sub>*; eligibility is fixed by scene and instruction before observing behaviour, a missing selection counts as zero, and an attribute absent from the instruction is not applicable rather than incorrect. Eligible tasks receive equal weight; rates computed on different task subsets are descriptive, not a controlled comparison between attributes. Attribute correctness and exact-target correctness are distinct: selecting a large red object when a small red one was requested earns colour credit but not size or exact-target credit. The proportion of episodes with *q<sub>i</sub>* = 1 and *y<sub>i</sub>* = 0 records correct selection without completion — 50 of 315 episodes in the measured study; completion among correctly selected episodes may be shown with its own denominator (undefined when zero) and cannot replace overall success.
- **Subtask completion.** A sequence is divided into the subtasks required by its instruction. *U<sub>c,k</sub>* records whether stage *k*'s own condition was achieved anywhere in the rollout; *V<sub>c,k</sub>* records whether the first *k* stages were completed in the requested order, including target and transition conditions (non-increasing in *k*). Both use all valid episodes as denominator. The continuation rate Σ*p<sub>i,k</sub>* / Σ*p<sub>i,k−1</sub>* measures continuation on the states the policy actually reached, is undefined if no episode reaches the preceding prefix, and does not measure standalone subskill ability. Stage predicates must state whether a condition has to persist or may be released before the next stage. Full-suite stage labels are not inferred from final success.

## Controlled language-following diagnostics

Beyond these per-episode labels, a [three-level diagnostic protocol]({{rel}}diagnostics/) separates observable behaviour, future-video outputs (where a system predicts images) and internal interventions (where representations are accessible). At the behaviour level every scene is run under two valid target instructions and two layouts with the two candidate objects exchanged; *c<sub>s,ℓ,t</sub>* marks a first recorded loaded gripper contact uniquely with the requested object, and the paired rates

*P*<sub>instr</sub> = (1/2S) Σ<sub>s,ℓ</sub> *c<sub>s,ℓ,r</sub> c<sub>s,ℓ,b</sub>*,  *P*<sub>layout</sub> = (1/2S) Σ<sub>s,t</sub> *c<sub>s,0,t</sub> c<sub>s,1,t</sub>*

require correct choices for both instructions in the same view and for the same instruction across layouts. Unavailable levels are marked not applicable, never scored as failures. The first controlled study (20 seeds, 160 trajectories, π0.5 and Motus) uses its own seeds and budgets and is never pooled with the leaderboard.

## Aggregation

For family *d* with task set *C<sub>d</sub>*, let *s<sub>c</sub>* be the success fraction over all episodes of task *c*. Then

*S<sub>d</sub>* = (1 / |*C<sub>d</sub>*|) Σ<sub>c∈C<sub>d</sub></sub> *s<sub>c</sub>*,  **Overall** = (1/6) Σ<sub>d=1..6</sub> *S<sub>d</sub>*  (Eq. 1 in the paper).

Each family receives equal weight despite unequal task counts. **Pooled** success is the fraction of all episodes that succeed (4,800 per policy; 240 per agent). **Within-family level rates** average the tasks in each family–level subset (the layout of the paper's Table 1; subsets hold one to six tasks, and a family mean is recovered by weighting its level cells by task count). **Global L1/L2/L3** rates average all tasks within each level (9 / 29 / 10 scenes) without family balancing. Neither aggregation changes the definition of Overall; all are computed before rounding. Per-task 95 % Wilson intervals are reported per scene and do not quantify uncertainty of the family-balanced Overall score or variation across training runs.

## Levels

| Level | Scenes | Registry definition |
| --- | --- | --- |
| L1 | 9 | Single substitution: one variable changed from a training task, 0–1 distractors, single-segment motion |
| L2 | 29 | One hop + distraction: a new variable and a distractor differing in one attribute, or a two-segment motion |
| L3 | 10 | Two constraints / two segments: two constraints simultaneously, or two segments with a real ordering dependency |
| L4 | 0 | Compositional depth: three or more constraints, or repeated execution / multi-target dispatch (reserved) |

Levels are manual design annotations summarising the designed combination of requirements, not a calibrated difficulty scale: changes in object geometry and execution demands can also affect performance. All twelve checkpoints in the paper show lower success from L1 to L3, but different task sets do not isolate semantic from motor difficulty, and this gradient alone does not validate a general difficulty scale.

## Policies versus agents

The public leaderboards separate **learned policies** (VLA and world-action models, 100 episodes per scene) from **agent systems** (an explicit language-model agent layer with tools or a controller, currently the first 5 seeds per scene). A matched-seed subset — the first five frozen seeds of every scene, 240 episodes per system — supports a limited comparison between the groups.

Agents act through a shared tool interface: `move_eef` requests an absolute world-frame end-effector target (position, quaternion [w, x, y, z], phase, gripper command, explanatory note), `finish` ends the attempt without establishing success. These two are the entire tool surface: the camera views, measured end-effector and joint state and the execution, contact and tracking feedback are supplied with every request rather than fetched by the model, and the schema contains no code-execution, shell, file-access or retrieval tool, so only `move_eef` actuates the robot. For submissions to the standard-agent track this surface is part of the contract (see [Participate]({{rel}}participate/#the-standard-agent-tool-surface)); for the systems already listed it is the checked-in tool schema rather than an audit of their raw call logs. Phase envelopes are 45 cm / 90° for transit, 12 cm / 30° for approach and 3 cm / 10° for contact; rejected commands return feedback without advancing the simulation, and accepted targets are interpolated without further model calls, stopping early on unexpected contact or a tracking error above 2.5 cm / 10°. Agents observe the current three camera views, measured EEF and joint/gripper state and contact/tracking feedback; earlier images are dropped before the next request while text and tool history are retained within an episode and reset between episodes. Budgets are 120 calls and a soft 3,300 s wall limit checked between invocations (a blocking request may exceed it) plus the scene step limit; the client retries a failed request up to three times and can synthesise `finish` after five consecutive failures. The recorded step counter is forced to the scene limit when an agent finishes or a budget terminates the episode, so it is not executed steps. A `finish` ending is not automatically a false completion claim: the prompt permits it when the model cannot proceed. Two skill-sequence tasks differ in instruction delivery: policies receive oracle-staged instructions that switch after stage 1 succeeds, whereas GPT-6 Astra and Gemini 3.8 Flash receive the full compound instruction from the start; their exported instruction wording also differs from the policies on 84 of the 240 matched episodes. Shared seeds do not equalise instructions, interfaces, deployments, provider settings or model-side clocks.

GPT-6.2 Astra, Opus 5.5 and Gemini 4 Argon use policy-exported instruction wording. Their soft 3,300 s budget excludes API waiting to avoid using the action budget on provider latency; the 120-call ceiling and scene step limit still apply. Gemini 4 Argon uses a 65,536-token output cap because the preliminary 8,192-token cap could be exhausted during reasoning before a tool action. See the [agent configurations]({{rel}}leaderboard/#agents-config) for exact API identifiers and request settings. Given evaluation cost, each model is tested on five episodes per scene (240 in total). We welcome community contributions to broaden evaluation across models.

## Scene selection and exclusions

Scenes entered the formal set only after a scripted expert could generate solvable seeds. Three candidates (`place_a2b_behind_novel`, `attr_color_bottle_basket`, `ref_cube_on_plate_to_pad`) were removed from a 51-scene list because expert yield fell below 30 % (12–15 % measured): their seed sets would have been filtered into an unrepresentative subset. They were not removed for low policy scores. Historical expert smoke-test fractions shown on task pages are not 100-seed expert evaluation rates.

## What the evaluator does not equalise

Systems differ in training provenance (backbone, robot or latent-action pretraining, RoboTwin adaptation quota), enabled inference modules (several world-action checkpoints ran without future-video, depth or world-expert branches), control interface (joint vs. end-effector with cuRobo planning), prediction and execution lengths, observation history, image preprocessing, inference budget and, for agents, tools, prompts, provider versions and request handling. The evaluator holds the *environment* fixed; the rest is the method. Reports must state these alongside success rates and compare only runs with matching scene, seed and instruction settings; see the [per-checkpoint records]({{rel}}policies/#provenance).

## Provenance and versioning

Each scene run writes `_run_metadata.json` with the repository commit, dirty state, selected controls and protocol hashes. Record model revision, backend revision, hardware and sampling settings in your own report. Website entries added after the paper snapshot must state their evaluation version separately.

For a new protocol version: develop and smoke-test the scene, verify seen/unseen instruction pools, update membership and step limits, regenerate expert-solvable seeds and initial poses, document the change, then refresh the lock:

```bash
python3 tools/lock_protocol.py --version formal48-v2
python3 tools/validate_repo.py
python3 -m pytest -q tests
```
