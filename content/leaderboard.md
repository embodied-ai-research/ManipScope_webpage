---
title: Leaderboard
---

All systems were evaluated on the same 48 scenes with the same frozen seeds, the same evaluator and the same per-scene step limits (1,000 recorded steps in 41 scenes, 600 in seven). Policies receive three RGB views (head, left, right; 320 × 240) and proprioception, without depth or privileged object state; model preprocessing differs. Checkpoints were trained on RoboTwin and evaluated directly on the derived scenes without adaptation; training data and budgets differ between checkpoints (for example, π0.5 reports clean and randomized RoboTwin data while the evaluated π0 checkpoint's data quota and parent weights remain unverified), so the comparison concerns the supplied checkpoints rather than architectures under matched training.

Aggregates follow the paper: for family *d* with task set *C<sub>d</sub>* and per-task success *s<sub>c</sub>*, *S<sub>d</sub>* = mean of *s<sub>c</sub>* over *C<sub>d</sub>* and **Overall** = mean of *S<sub>1..6</sub>*; **Pooled** is successes divided by all episodes; **L1/L2/L3** average tasks within a level without family balancing. All aggregates are computed here from the per-scene rates before rounding. Per-task Wilson intervals do not quantify uncertainty of the family-balanced Overall score or variation across training runs.
