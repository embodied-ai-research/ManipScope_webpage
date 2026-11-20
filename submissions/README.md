# submissions

Evaluation results for the leaderboard. One file per evaluated system and scene set:

```
submissions/<track>/<system-slug>/<YYYY-MM-DD>/submission.json
```

`<track>` is `standard_agent` or `open_system`. Every file follows
[`schema/submission.schema.json`](schema/submission.schema.json) and is checked by
`tools/validate_submission.py` in CI on every pull request.

- `status: community_reported` — produced by the submitter, format-checked only.
- `status: officially_evaluated` — produced by the organizers on the private initial states. Only
  the organizers set this; the validator rejects it from a submitter.

A passing check means the file is well formed. It is not evidence that the numbers came from a real
run, and the two statuses are displayed separately on the leaderboard.

Rules for files in this directory:

- no API keys, tokens or other credentials;
- no frozen seed values and no initial-pose dumps — episodes are identified by index;
- raw logs and videos live in the submitter's own storage and are referenced by URL and digest under
  `run.artifacts`, not committed here;
- one record per episode, including retries and discarded runs; a partial upload of successful
  episodes only is rejected by the coverage check.

## Where things live

The benchmark repository is authoritative for the protocol and the tooling: it holds the
development-set runner, `tools/export_submission.py`, the organizer runbook and the scene-level
issue templates. **It is being prepared for public release; its link will be added here.** Ask in an
issue meanwhile and the organizers will send what you need.

`tools/validate_submission.py`, `schema/submission.schema.json`, `examples/example_submission.json`
and `dev_set.json` here are copies of the files kept there; the validator reads the scene list from
`data/tasks.json` in this repository and from `suite/scenes_v2.yaml` there, so the copies are
byte-identical and `diff` is enough to check drift. `schema_version` changes whenever the format
does.

Run it before opening a pull request:

```bash
python3 -m pip install jsonschema
python3 tools/validate_submission.py submissions/<track>/<system>/<date>/submission.json
```

See [Participate](https://embodied-ai-research.github.io/ManipScope_webpage/participate/) for the process; the full specification lives with the benchmark
code and is linked from there once that repository is public.
