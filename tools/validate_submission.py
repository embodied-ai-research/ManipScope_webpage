#!/usr/bin/env python3
"""Check a submission file before it is merged or evaluated.

The same file runs in the benchmark repository and in the website repository, where submissions are
filed: the scene list comes from suite/scenes_v2.yaml when present and from data/tasks.json
otherwise, so the two copies stay byte-identical and can be compared with diff.

Validates structure against submissions/schema/submission.schema.json, checks scene and episode
coverage against the frozen scene list, recomputes Overall and Pooled from the per-episode records,
and refuses files that carry credentials or private seed values. A clean report means the file is
well formed; it is not evidence that the numbers came from a real run. Only the organizers' own
evaluation can carry the `officially_evaluated` status.

    python3 tools/validate_submission.py submissions/.../submission.json
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = os.path.join(ROOT, "submissions", "schema", "submission.schema.json")
SCENES = os.path.join(ROOT, "suite", "scenes_v2.yaml")          # benchmark repository
TASKS_JSON = os.path.join(ROOT, "data", "tasks.json")           # website repository
DEV_SET = os.path.join(ROOT, "suite", "dev_set.yaml")
DEV_SET_JSON = os.path.join(ROOT, "submissions", "dev_set.json")

# Patterns that must never appear in a public submission file.
# The fixed tool surface of the standard-agent track, as registered in policy/GPT6/local_bridge.py.
STANDARD_AGENT_TOOLS = ["finish", "move_eef"]

SECRET_PATTERNS = [
    (r"sk-[A-Za-z0-9_\-]{16,}", "OpenAI-style API key"),
    (r"AIza[0-9A-Za-z_\-]{30,}", "Google API key"),
    (r"sk-ant-[A-Za-z0-9_\-]{16,}", "Anthropic API key"),
    (r"(?i)bearer\s+[A-Za-z0-9._\-]{16,}", "bearer token"),
    (r"(?i)\"?(api[_-]?key|secret|password|token)\"?\s*[:=]\s*\"[^\"]{8,}", "credential field"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private key"),
]


def load_yaml(path):
    try:
        import yaml
    except ImportError:
        return None
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_json(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except ValueError:
        return None


def scene_families():
    """{scene: family} from the frozen scene list, or {} when neither source can be read."""
    data = load_yaml(SCENES)
    if data:
        return {str(scene["name"]): axis
                for axis, block in (data.get("axes") or {}).items()
                for scene in (block.get("scenes") or [])
                if not str(scene.get("name", "<")).startswith("<")}
    tasks = load_json(TASKS_JSON)
    if tasks:
        return {str(scene["name"]): dim.get("axis") or dim.get("id")
                for dim in (tasks.get("dimensions") or [])
                for scene in (dim.get("scenes") or [])}
    return {}


def dev_scenes():
    data = load_yaml(DEV_SET) or load_json(DEV_SET_JSON)
    if not data:
        return []
    return [str(s) for s in (data.get("scenes") or [])]


def schema_check(doc, errors):
    """Full validation when jsonschema is installed; a structural subset otherwise."""
    try:
        import jsonschema
    except ImportError:
        jsonschema = None
    with open(SCHEMA, encoding="utf-8") as fh:
        schema = json.load(fh)
    if jsonschema is not None:
        validator = jsonschema.Draft202012Validator(schema)
        for err in sorted(validator.iter_errors(doc), key=lambda e: list(e.path)):
            errors.append("schema: %s at %s" % (err.message, "/".join(str(p) for p in err.path) or "<root>"))
        return True
    for key in schema["required"]:
        if key not in doc:
            errors.append("schema: missing required key %r" % key)
    for section, keys in (("system", ["display_name", "track", "kind"]),
                          ("protocol", ["version", "scene_set", "episodes_per_scene"]),
                          ("run", ["date", "repo_commit", "evaluated_by"]),
                          ("budgets", ["max_model_calls_per_episode"])):
        block = doc.get(section) or {}
        for key in keys:
            if key not in block:
                errors.append("schema: missing required key %s.%s" % (section, key))
    return False


def secret_scan(path, errors):
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    for pattern, label in SECRET_PATTERNS:
        for match in re.finditer(pattern, text):
            line = text.count("\n", 0, match.start()) + 1
            errors.append("secret: possible %s on line %d; remove it and rotate the credential" % (label, line))


def coverage_check(doc, families, errors, warnings):
    protocol = doc.get("protocol") or {}
    per_scene = protocol.get("episodes_per_scene")
    declared = {}
    for entry in doc.get("scenes") or []:
        name = entry.get("name")
        if name in declared:
            errors.append("scenes: %s listed twice" % name)
        declared[name] = entry

    expected = None
    if protocol.get("scene_set") == "formal48":
        expected = sorted(families)
        if families and len(expected) != 48:
            warnings.append("scene list has %d scenes, not 48; check suite/scenes_v2.yaml" % len(expected))
    elif protocol.get("scene_set") == "dev6":
        expected = sorted(dev_scenes())
    if expected:
        missing = [s for s in expected if s not in declared]
        extra = [s for s in declared if s not in expected]
        if missing:
            errors.append("coverage: %d scenes missing (%s%s)" % (
                len(missing), ", ".join(missing[:5]), ", ..." if len(missing) > 5 else ""))
        if extra:
            errors.append("coverage: scenes not in the declared set: %s" % ", ".join(sorted(extra)[:5]))
    elif families:
        for name in declared:
            if name not in families:
                warnings.append("scene %s is not in the frozen scene list" % name)

    by_scene = {}
    for episode in doc.get("episodes") or []:
        by_scene.setdefault(episode.get("scene"), []).append(episode)

    for name, entry in sorted(declared.items()):
        episodes = by_scene.get(name, [])
        if per_scene and entry.get("episodes") != per_scene:
            errors.append("coverage: %s declares %s episodes, protocol says %s"
                          % (name, entry.get("episodes"), per_scene))
        if len(episodes) != entry.get("episodes"):
            errors.append("coverage: %s has %d episode records for %s declared episodes"
                          % (name, len(episodes), entry.get("episodes")))
        indices = sorted(e.get("index") for e in episodes)
        if indices != list(range(len(episodes))):
            errors.append("coverage: %s episode indices are not 0..%d without gaps or repeats"
                          % (name, len(episodes) - 1))
        counted = sum(1 for e in episodes if e.get("success"))
        if counted != entry.get("successes"):
            errors.append("coverage: %s declares %s successes, episode records contain %d"
                          % (name, entry.get("successes"), counted))
    for name in by_scene:
        if name not in declared:
            errors.append("coverage: episode records for undeclared scene %r" % name)

    budget = (doc.get("budgets") or {}).get("max_model_calls_per_episode")
    if isinstance(budget, int):
        over = [e for e in doc.get("episodes") or []
                if isinstance(e.get("model_calls"), int) and e["model_calls"] > budget]
        if over:
            errors.append("budgets: %d episodes exceed the declared %d-call ceiling" % (len(over), budget))
    if not any(e.get("termination") for e in doc.get("episodes") or []):
        warnings.append("no episode records a termination reason; add one per episode")


def aggregate(doc, families):
    """Family-balanced Overall and pooled success, computed the way the protocol defines them."""
    per_family = {}
    total_ep = total_su = 0
    for entry in doc.get("scenes") or []:
        episodes, successes = entry.get("episodes") or 0, entry.get("successes") or 0
        total_ep += episodes
        total_su += successes
        family = entry.get("family") or families.get(entry.get("name")) or "unknown"
        per_family.setdefault(family, []).append(successes / episodes if episodes else 0.0)
    family_pct = {f: 100.0 * sum(v) / len(v) for f, v in per_family.items() if v}
    overall = sum(family_pct.values()) / len(family_pct) if family_pct else 0.0
    pooled = 100.0 * total_su / total_ep if total_ep else 0.0
    return overall, pooled, family_pct, total_ep, total_su


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="+", help="submission JSON file(s)")
    parser.add_argument("--allow-official", action="store_true",
                        help="organizer use: permit status=officially_evaluated")
    parser.add_argument("--strict", action="store_true", help="treat warnings as failures")
    args = parser.parse_args()

    failed = False
    for path in args.files:
        errors, warnings = [], []
        print("== %s" % path)
        try:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, ValueError) as exc:
            print("   error: cannot read as JSON: %s" % exc)
            failed = True
            continue

        full = schema_check(doc, errors)
        if not full:
            warnings.append("jsonschema not installed; only structural keys were checked "
                            "(pip install jsonschema for the full check)")
        secret_scan(path, errors)
        families = scene_families()
        if not families:
            warnings.append("could not read suite/scenes_v2.yaml; scene coverage not checked")
        coverage_check(doc, families, errors, warnings)

        if doc.get("status") == "officially_evaluated" and not args.allow_official:
            errors.append("status: only the organizers may set officially_evaluated")
        if (doc.get("run") or {}).get("evaluated_by") == "submitter" and doc.get("status") == "officially_evaluated":
            errors.append("status: evaluated_by=submitter cannot be officially_evaluated")
        if (doc.get("protocol") or {}).get("seed_source") == "self_generated_dev" \
                and (doc.get("protocol") or {}).get("scene_set") == "formal48":
            errors.append("protocol: the formal scene set requires organizer-held seeds")
        if (doc.get("run") or {}).get("repo_dirty"):
            warnings.append("run.repo_dirty is true; record what was modified")

        system = doc.get("system") or {}
        if not system.get("training_data"):
            warnings.append("system.training_data is absent; the training-data boundary cannot be "
                            "checked without it")
        if system.get("kind") == "policy" and not system.get("weights_digest"):
            warnings.append("system.weights_digest is absent; a policy result should name the "
                            "checkpoint it belongs to")
        if system.get("hosting") == "remote_blackbox" and not (doc.get("run") or {}).get("verification_scope"):
            warnings.append("hosting is remote_blackbox, so run.verification_scope must say what "
                            "the organizers could and could not verify")

        # The standard-agent track reads as a model comparison only if the tool surface is fixed.
        if system.get("track") == "standard_agent":
            declared = system.get("tools")
            if declared is None:
                warnings.append("standard_agent submissions should declare system.tools; the "
                                "track's surface is exactly %s" % STANDARD_AGENT_TOOLS)
            elif sorted(declared) != STANDARD_AGENT_TOOLS:
                errors.append("system.tools is %s; the standard_agent track is exactly %s. Use the "
                              "open_system track for a different tool surface."
                              % (sorted(declared), STANDARD_AGENT_TOOLS))

        overall, pooled, family_pct, total_ep, total_su = aggregate(doc, families)
        declared = doc.get("results") or {}
        for key, value in (("overall_pct", overall), ("pooled_pct", pooled)):
            if key in declared and abs(float(declared[key]) - value) > 0.05:
                errors.append("results: %s declares %.2f, recomputed %.2f" % (key, float(declared[key]), value))

        print("   episodes %d, successes %d, Overall %.2f%%, Pooled %.2f%% (%d families)"
              % (total_ep, total_su, overall, pooled, len(family_pct)))
        for line in warnings:
            print("   warning: %s" % line)
        for line in errors:
            print("   error: %s" % line)
        if errors or (args.strict and warnings):
            failed = True
        else:
            print("   ok")

    if failed:
        print("\nFAILED")
        return 1
    print("\nPASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
