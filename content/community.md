---
title: Community
description: Where to ask questions, report issues and follow updates.
---

!!! note "Coming soon"
    Issue tracker, contact addresses and discussion channels.

## Reporting problems

Bug reports and reproduction problems should include the scene name, the policy key, the
`_run_metadata.json` of the affected run and the relevant log under `suite/logs/<run>/`.

## Contributing

To have a new model or system evaluated, follow [Participate]({{rel}}participate/): self-test on the
development set, then file an evaluation request so the organizers can run the private initial states.

Changes to scenes, seeds, instruction pools or step limits alter the frozen protocol and require a new
protocol version (see [Evaluation Protocol]({{rel}}usage/evaluation-protocol/)); adapters and
documentation can be added without one.

## Acknowledgements

ManipScope derives from [RoboTwin 2.0](https://github.com/RoboTwin-Platform/RoboTwin) and retains its MIT
licence. The vendored cuRobo snapshot is licensed separately by NVIDIA. Model weights and inference
backends remain under their own terms.
