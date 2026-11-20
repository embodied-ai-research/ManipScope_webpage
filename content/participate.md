---
title: Participate
description: Run the development set, request an official evaluation, and get a result on the leaderboard.
---

!!! note "Process v0.1"
    The interfaces, file formats, schedule and credential channel below are in force. The benchmark
    repository is the authority on the exact commands and the result schema; this site's repository
    is where requests and results are filed.

ManipScope is evaluation-only and its 100 frozen initial states per scene are organizer-held, so a
score is comparable only when it was produced on those initial states. Participation therefore runs
in three stages: you verify your system locally on a public **development set**, you file a
**request**, and the organizers run the **official evaluation** on the private initial states.

Two kinds of contribution are in scope: **a new model** evaluated through the standard agent
framework or an existing policy adapter, and **a new method** — your own planner, memory, tools,
skills or controller.

## How it works

1. **Connect and self-test.** Public environment, locally generated development initial states, an
   example adapter and one command. Confirm your model actually drives the robot.
2. **File a request.** An issue or pull request in [this website's repository]({{submit}}) carrying
   the model configuration, the adapter or code revision, the development-set result file and a
   runnable recipe. Requests live here because this is where the leaderboard is built; problems with
   a scene, an instruction pool, a step limit or the evaluator belong in the benchmark repository,
   with the code.
3. **Official evaluation.** The organizers run the shared evaluator on the private initial states and
   publish the score together with the logs they produced.
4. **Site update.** After review the result file is merged under `submissions/` in the website
   repository and the leaderboard is rebuilt from it. The same format check that CI runs on the pull
   request can be run locally first: `python3 tools/validate_submission.py <file>`.

```bash
# interface check only: no simulator, no model calls
DRY_RUN=1 bash suite/run_dev_check.sh <policy_key>

# six development scenes, five episodes each, then export and validate a result file
bash suite/run_dev_check.sh <policy_key>
```

Development seeds are generated on your machine, so development initial states differ between
participants and from the formal set. **Development numbers are not leaderboard numbers**; they show
that the interface works and that your logs export cleanly.

## The five interfaces

| Interface | You provide | The organizers provide |
| --- | --- | --- |
| Model configuration | model id, API interface, reasoning setting, output cap | a fixed agent framework that tests a new model without new tool-calling or robot-control code |
| Agent / policy | `reset()` and `act(observation)`, or the equivalent HTTP service | fixed observation format, action convention and termination rules |
| Local evaluation entry | adapter and configuration | one command for the development set, an interface check and a result export |
| Result format | model version, configuration, code revision, results and log links | schema and coverage checks, re-aggregation, recorded review status |
| Contribution entry | new-model requests, scene problems, adapters, new task proposals | triage, review and protocol versioning |

For an API model the standard agent framework reduces participation to one JSON file: `provider`
(`responses`, `chat`, `anthropic` or `generateContent`), `base_url`, `model`, `reasoning_effort` and
`max_output_tokens`. Templates live in `configs/model_configs/`; the
[policy integration]({{rel}}usage/policy-integration/) page covers self-hosted models and the
external-agent bridge.

## Two leaderboard tracks

| Track | Fixed by the organizers | Chosen by you |
| --- | --- | --- |
| Standard agent framework | prompt, tools, memory handling, controller, budget rules | the base model and its request settings |
| Open system | the environment, scenes, initial states and success rule | planner, tools, memory, skills, control policy |

The standard-agent track is the one that compares base models; the open-system track compares
complete systems. The five agent results currently listed were obtained before this split and differ
in instruction delivery and time budget, so each row shows its own configuration version and the
column is not a controlled model comparison. A single frozen protocol per track is the precondition
for reading it as one.

## Result status

| Status | Meaning |
| --- | --- |
| Officially evaluated | produced by the organizers' evaluator on the private initial states |
| Community reported | produced by the submitter; format-checked only |

A schema check proves a file is well formed, not that the numbers came from a real run.
Community-reported rows help reproduction and are never shown as verified scores. Development-set
and formal-set results are displayed separately and never pooled.

## Cost and scheduling

| Stage | When |
| --- | --- |
| Development-set check | self-serve, any time |
| Request acknowledged, with anything missing listed | 5 working days |
| Batch cutoff | the 1st of each month |
| Official result published | within 15 days of the batch starting |
| Community-reported result merged or declined with a reason | 5 working days after the format check passes |

Each system gets one official run per protocol version. A second run happens only when the
organizers change the harness or the protocol, or when a defect on their side is recorded; both
results then stay visible with their dates and the superseded one is labelled.

Admission to a batch is by measured cost, not by quota. Simulation time dominates and differs by an
order of magnitude between systems: at 240 episodes the five agent systems listed here cost between
18 and 188 GPU-hours, so a slow model displaces several fast ones. The development set is one eighth
of an agent run, which is why its measured wall time per episode belongs in the request — that is
what the batch is planned from. A policy checkpoint is 4,800 episodes and is scheduled separately.

Simulation is the organizers' cost; inference is normally yours.

- **API models** — provide a quota-limited endpoint and key over a private channel; the organizers
  run the simulator and the agent framework against it.
- **Open-weights models** — provide a container image and a weights location; the organizers run both.

Credentials go to **<sayleefilipski@gmail.com>** and nowhere else — never an issue, a pull request,
a log or a result file, and a credential posted publicly is treated as compromised and must be
revoked. Send the least dangerous thing that works: the bridge accepts any HTTPS base URL, so a
gateway you control, with a disposable token and a hard spend cap, is preferred over a provider root
key. Scope it to this evaluation and set an expiry where the provider supports one — a 188 GPU-hour
run is also a long billing window, and the cap protects you. The organizers hold it only in the
evaluation machine's private runtime directory and ask you to revoke it when the batch ends. The
request template states who covers the simulator GPU hours, the API tokens and, for open weights,
the inference GPUs.

## What every result records

- exact model identifier, evaluation date, repository commit and protocol version;
- prompt and tool revision, reasoning setting, and the token, call and wall-time budgets, including
  whether the wall-time budget excludes provider waiting;
- per episode: success, termination reason, model calls, recorded steps and timings;
- every attempt, including retries and discarded runs. Uploading only successful episodes is
  rejected: coverage is checked against the scene list and the declared episode count.

Action and environment feedback logs are enough; hidden reasoning traces are not requested. Large
logs and videos stay in your own storage and are referenced by URL and digest, so this site keeps
only result summaries and links.

## New scenes

Proposals for new scenes enter a development area first and are released with a new protocol
version, so the existing 48-scene leaderboard stays comparable. Changing scenes, initial states,
instruction pools or step limits requires a new protocol version — see the
[evaluation protocol]({{rel}}usage/evaluation-protocol/).

What happens to a request after it is filed — batch planning, credential handling, the run commands
and the checklist applied before a result is published — is written down in the organizer runbook in
the benchmark repository, so the process is auditable rather than informal.

[Submission process and templates]({{submit}}){.btn} [Benchmark repository]({{repo}}){.btn}
