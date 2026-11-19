# Per-scene media

| Path | Shown as |
| --- | --- |
| `assets/videos/<scene>_success.mp4` | "Successful rollout" on the scene page; produced by `scripts/process_videos.py` from the HiFi re-renders, described in `data/videos.json` |
| `assets/depgraph/index.html` | Home-page interactive graph relating evaluation scenes to RoboTwin base tasks (fallback: `assets/img/source-task-map.png` or `.svg`) |

`scripts/process_videos.py` reads `$MANIPSCOPE_HIFI/{g05,gpt6_agent,supplement_20260924}/videos` (the HiFi
re-render workspace, read-only; default `../ManipScope_HiFi`), picks one *success* video per scene (G0.5 preferred, GPT-6 fallback), keeps every k-th frame
(k = smallest of 1/2/4/8 with duration/k ≤ 20 s), scales to 1920×1080 @ 15 fps, adds the top banner
(system · kind · outcome · scene · seed / instruction), the bottom-right speed badge and, for GPT-6, a
right-hand panel with the note attached to every tool call (matched from `gpt6_agent/bridge_logs/decisions.jsonl`
by instruction, call count and summed model-side seconds; aligned with `audit/checks.jsonl`).
Re-run `python3 scripts/process_videos.py` (optionally with scene names) and then `python3 build.py`.

Videos total ~130 MB; if the repository must stay small, uncomment the `assets/videos/*.mp4` line in
`.gitignore` and deploy them separately.
