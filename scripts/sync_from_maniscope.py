#!/usr/bin/env python3
"""Extract benchmark metadata from the ManiScope repository into data/*.json.

Everything here is READ-ONLY with respect to ManiScope. Sources:

    suite/scenes_v2.yaml                 frozen membership, dimensions, tiers, notes
    description/task_instruction/*.json  seen / unseen instruction templates
    task_config/_eval_step_limit.yml     per-scene step limits
    suite/seeds/<scene>.json             frozen seed count
    envs/<scene>.py                      GOAL / SPEC / A_DESC / MIRROR via ast (never imported)
    envs/_compo_scene.py                 model-id -> noun table
    suite/policies.yaml                  integrated + planned policies
    docs/archive/EVAL_COMPARE.md         historical per-scene success rates (archival only)

Outputs:
    data/tasks.json        dimensions -> scenes with everything a task page needs
    data/policies.json     policy registry
    data/leaderboard.json  historical results table (flagged as archival)

Usage:
    python3 scripts/sync_from_maniscope.py [--maniscope /path/to/ManiScope]
"""
import argparse
import ast
import glob
import json
import os
import re
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.dirname(HERE)
DATA = os.path.join(WEB, "data")

# ---- English labels for the Chinese metadata in scenes_v2.yaml ---------------
# Keys are the repository ids (scenes_v2.yaml). The paper numbers the families D1–D6 and
# calls the mixture family D6; the legacy reports label the same family D7. `paper_id` is what
# the website displays; `id` in the repo stays untouched.
DIM_EN = {
    "D1": {"paper_id": "D1", "name": "Skill–object transfer", "short": "Skill–object",
           "desc": "A familiar skill is applied to an object that changes relative to the source task."},
    "D2": {"paper_id": "D2", "name": "Skill–spatial transfer", "short": "Skill–spatial",
           "desc": "A spatial condition (left / right / front / between) must be satisfied for a changed object pair or relation."},
    "D3": {"paper_id": "D3", "name": "Attribute selection", "short": "Attribute selection",
           "desc": "The instruction names an attribute (colour, size or category); the target must be selected among distractors that differ in it."},
    "D4": {"paper_id": "D4", "name": "Referring expressions", "short": "Referring expressions",
           "desc": "The target is identified through a relation, order or negation: on the plate, behind the can, leftmost, second from left, not the red one."},
    "D5": {"paper_id": "D5", "name": "Skill sequences", "short": "Skill sequences",
           "desc": "Familiar actions must achieve successive conditions in the requested order; stage progress is recorded."},
    "D7": {"paper_id": "D6", "name": "Mixed combinations", "short": "Mixed",
           "desc": "Scenes combine more than one of the above demands, or add semantically unrelated distractors to a source scene."},
}
AXIS_ORDER = ["skill_x_object", "skill_x_spatial", "attribute_binding",
              "instruction_structure", "skill_x_skill_temporal", "mixture"]

TIER_EN = {
    "L1": "Single substitution: one variable changed from a training task, 0-1 distractors, single-segment motion.",
    "L2": "One hop plus distraction: one new variable and a distractor differing in one attribute, or a two-segment motion.",
    "L3": "Two constraints / two segments: two constraints hold simultaneously, or two segments with a real ordering dependency.",
    "L4": "Compositional depth: three or more constraints, or repeated execution / multi-target dispatch.",
}

CONTEXT_EN = {
    "健身角": "Gym corner", "床头药盒": "Bedside pillbox", "办公桌": "Office desk",
    "超市称重": "Supermarket weighing", "工具台": "Workbench", "厨房备餐": "Kitchen prep",
    "书架": "Bookshelf", "玄关": "Entryway", "通用桌面": "Generic tabletop",
    "超市结账": "Supermarket checkout", "仓储上架": "Warehouse shelving",
    "餐桌摆盘": "Dining-table plating", "家务分拣": "Household sorting",
    "冰箱取饮": "Fridge drinks", "前台服务": "Front desk", "积木码垛": "Block stacking",
    "日用品收纳": "Toiletry storage", "餐桌收拾": "Table clearing",
    "快餐取餐": "Fast-food pickup", "垃圾清理": "Trash cleanup",
}

# The registry annotates some `hf_repo` URLs with a note in Chinese full-width parentheses. The site is
# English-only, so the URL is kept in `hf_repo` and the note goes to `hf_note_en` (translated when known).
HF_NOTE_EN = {
    "RoboTwin ckpt: robotwin_uncond_3cam_384.pt；LeRobot 版 https://huggingface.co/lerobot/fastwam_robotwin_uncond_3cam_384":
        "RoboTwin checkpoint robotwin_uncond_3cam_384.pt; LeRobot-format alternative: https://huggingface.co/lerobot/fastwam_robotwin_uncond_3cam_384",
    "robotwin_ahawam.pt + dataset_stats.json": "robotwin_ahawam.pt + dataset_stats.json",
    "robotwin_sft": "artifact robotwin_sft",
    "g05-robotwin20/ + action_tokenizer.pt + qwen3_5_2b_base_processor/，gated": "g05-robotwin20/ + action_tokenizer.pt + qwen3_5_2b_base_processor/; gated access",
    "RoboTwin-MeM 权重": "RoboTwin-MeM weights",
}


def split_hf_repo(value):
    """'https://…（note）' -> {'hf_repo': 'https://…', 'hf_note_en': 'English note'} (note optional)."""
    if not value or not isinstance(value, str):
        return {}
    url, sep, note = value.partition("（")
    if not sep:
        return {"hf_repo": value.strip()}
    note = note.rstrip("）").strip()
    en = HF_NOTE_EN.get(note) or note.replace("；", "; ").replace("，", ", ").replace(" 版", " version").replace("权重", "weights")
    return {"hf_repo": url.strip(), "hf_note_en": en}


# Paper Table 5 (control interfaces), keyed by suite/policies.yaml key.
CONTROL_IFACE = {
    "dm05": {"control": "Joint", "state": "14-D joint positions + gripper", "action": "chunks of 14-D absolute joint/gripper targets"},
    "pi05": {"control": "Joint", "state": "14-D joint positions + gripper", "action": "chunks of 14-D absolute joint/gripper targets"},
    "pi0": {"control": "Joint", "state": "14-D joint positions + gripper", "action": "chunks of 14-D absolute joint/gripper targets"},
    "starvla": {"control": "Joint", "state": "14-D joint positions + gripper", "action": "chunks of 14-D absolute joint/gripper targets"},
    "fastwam": {"control": "Joint", "state": "14-D joint positions + gripper", "action": "chunks of 14-D absolute joint/gripper targets"},
    "ahawam": {"control": "Joint", "state": "14-D joint positions + gripper", "action": "chunks of 14-D absolute joint/gripper targets"},
    "g05": {"control": "Joint", "state": "14-D joint positions + gripper", "action": "chunks of 14-D absolute joint/gripper targets"},
    "motus": {"control": "Joint", "state": "14-D joint positions + gripper", "action": "chunks of 14-D absolute joint/gripper targets"},
    "xvla": {"control": "EEF", "state": "20-D: xyz + rot6D + grip, two arms", "action": "16-D: xyz + quaternion + grip, two arms (cuRobo)"},
    "wla_formal": {"control": "EEF", "state": "16-D: xyz + quaternion + grip, two arms", "action": "16-D: xyz + quaternion + grip, two arms (cuRobo)"},
    "xwam": {"control": "EEF", "state": "16-D: xyz + quaternion + grip, two arms", "action": "16-D absolute EEF targets from 14-D incremental actions (cuRobo)"},
    "lingbot_va": {"control": "EEF", "state": "14-D joint positions + gripper", "action": "16-D EEF targets recovered from actions relative to the initial pose (cuRobo)"},
    "openwam": {"control": "EEF", "state": "20-D: xyz + rot6D + grip, two arms", "action": "16-D EEF targets (cuRobo)"},
    "eef_bridge": {"control": "EEF (agent)", "state": "EEF + joint/gripper state, contact feedback", "action": "move_eef tool: absolute EEF target per call"},
}
# English model descriptions (registry `desc` fields are Chinese). From the paper's Appendix B.2 and the reports.
POLICY_DESC_EN = {
    "dm05": "Dexmal DM0.5, RoboTwin 2.0 fine-tuned generalist checkpoint; three RGB views, 14-D absolute joint actions in chunks of 50.",
    "pi05": "π0.5 (motus-robotics/pi0.5_robotwin2), OpenPI; trained on all 50 RoboTwin 2.0 tasks with 50 clean + 500 randomized demonstrations per task; action horizon 32.",
    "xvla": "X-VLA 0.9B RoboTwin checkpoint (Florence-2-large + flow matching), trained on the full RoboTwin 2.0 task set; 20-D EEF state, 16-D EEF actions executed through cuRobo.",
    "pi0": "π0 (yuffish/robotwin-pi0_aloha-agilex_clean-50), OpenPI JAX; clean-50 adaptation for 35,000 steps.",
    "wla_formal": "WLA (RynnBrain-2B + SANA-600M + flow action head), RoboTwin all-task image_action weights; images resized to 224 and JPEG-encoded, eight historical head images; 16-D EEF state/actions, chunk 32. The evaluated action-sampling path does not call the World Expert or generate subtask text.",
    "starvla": "StarVLA instantiated as Qwen3-VL-OFT (Qwen3-VL-4B backbone + MLP action head; continuous L1 regression from action-token hidden states, not quantized tokens or a diffusion head); three 224 RGB views and the instruction only, no proprioception at the model boundary; 14-D absolute joint actions, chunk 50; clean + randomized training for 140k steps.",
    "fastwam": "FastWAM (Wan2.2-TI2V-5B video DiT + 1B action DiT); three views concatenated at 384×320, 14-D absolute joint actions, horizon 32 / replan 24. The evaluated uncond path skips future-video generation; instruction conditioning of this checkpoint remains to be verified.",
    "ahawam": "AHA-WAM (asynchronous dual-DiT world-action model on Wan2.2-TI2V-5B); three views at 384×320, 14-D absolute joint actions, chunk 16, video prefill every two chunks.",
    "xwam": "X-WAM (unified 4D world-action model with Wan2.2 video prior, asynchronous denoising), robotwin_sft weights; 16-D EEF state, native 14-D incremental EEF actions converted to absolute EEF targets, 32 steps per call. Evaluated with early stopping on action completion and the depth branch disabled.",
    "g05": "GalaxeaVLA G0.5 (Qwen3.5-2B + continuous action expert, adapted from g05-base); three views + 14-D joint state. Evaluated in continuous flow-matching mode with autoregressive action tokens and CoT disabled: 32 targets predicted per request, 8 executed by the client. Weights are gated.",
    "openwam": "OpenWAM-α (Wan2.2-TI2V-5B dual-system joint-attention world-action model), RoboTwin 2.0 all-task fine-tune; 20-D EEF state, EEF actions. Registered adapter; not part of the paper snapshot.",
    "motus": "Motus (unified latent-action world model: Wan2.2 video + Qwen3-VL-2B understanding + action expert), RoboTwin 2.0 fine-tune; three views at 384×320, 14-D absolute joint targets, full chunk executed.",
    "lingbot_va": "LingBot-VA (autoregressive causal video-action world model on Wan2.2 with cross-chunk KV cache), RoboTwin post-train; 14-D joint state, 16-D actions relative to the initial EEF pose recovered to absolute EEF targets.",
    "eef_bridge": "Externally hosted end-effector agent bridge (language-model agent with move_eef / finish tools). No provider implementation or credentials are bundled; used for the GPT-6 and Gemini 3.8 Flash runs.",
}
EXCLUDED_EN = {
    "reason": "Removed from the 51-scene candidate list because scripted-expert generation yield was below the 30 % threshold (12–15 % measured): the retained seed set would have concentrated on a narrow subset of states. These are feasibility decisions, not removals based on policy scores.",
    "status": "Scene definitions, instruction pools and configs were deleted from the repository on 2026-09-16; only this record of the exclusion remains.",
}
# Policy keys whose full-run results appear in the paper snapshot (twelve checkpoints).
PAPER_POLICIES = ["dm05", "pi05", "starvla", "fastwam", "pi0", "ahawam", "xvla", "wla_formal", "g05", "xwam", "motus", "lingbot_va"]

CRITERION_EN = {
    "lift": "Lift: the target's collision geometry leaves its initial support surface by the declared height while in contact with a gripper.",
    "on": "On: the target rests on top of the reference object within the declared xy/z tolerance.",
    "stack": "Stack: the target is stacked on the reference object (a special case of `on`).",
    "in": "In: the target is inside the container — touching it, low velocity, bottom below the rim, and displaced from its start.",
    "rel": "Relation: the target ends up on the declared side (left/right/front/behind) of the reference within a gap band and without lateral drift.",
    "between": "Between: the target ends up near the midpoint of the segment joining the two references.",
    "press": "Press: a gripper contact point touches the reference object and the object has not been carried away.",
    "beat": "Beat: the hammer/mallet contacts the referenced block (press-type criterion applied to a tool).",
    "seq": "Sequence: stage goals must be reached in order; the stage counter only increases.",
    "dual_carry_to": "Dual carry: both arms grasp the handles, lift the object by the declared height, then carry it above the pad and release.",
    "handwritten": "Handwritten: task-specific `check_success` in the environment file (see the description).",
}


# ---- helpers -----------------------------------------------------------------
def read_yaml(p):
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


def read_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def literal(node):
    try:
        return ast.literal_eval(node)
    except Exception:
        return None


def parse_env(path):
    """Pull class-level literals and docstrings out of an env file without importing it."""
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    out = {"module_doc": ast.get_docstring(tree) or "", "class_doc": "", "base": None,
           "GOAL": None, "SPEC": None, "A_DESC": None, "MIRROR": None, "EXCLUSIVE": None,
           "has_check_success": False}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            out["class_doc"] = ast.get_docstring(node) or ""
            out["base"] = ", ".join(getattr(b, "id", getattr(b, "attr", "?")) for b in node.bases)
            for item in node.body:
                if isinstance(item, ast.Assign) and len(item.targets) == 1 and isinstance(item.targets[0], ast.Name):
                    key = item.targets[0].id
                    if key in out:
                        out[key] = literal(item.value)
                if isinstance(item, ast.FunctionDef) and item.name == "check_success":
                    out["has_check_success"] = True
            break
    return out


def parse_noun_table(compo_path):
    tree = ast.parse(open(compo_path, encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "NOUN" for t in node.targets):
            return literal(node.value) or {}
    return {}


def goal_refs(goal):
    refs = []
    if not isinstance(goal, dict):
        return refs
    if goal.get("ref"):
        refs.append(goal["ref"])
    for r in goal.get("refs") or []:
        refs.append(r)
    for st in goal.get("stages") or []:
        refs.extend(goal_refs(st))
    return refs


def humanize(name):
    return name.replace("_", " ").strip().capitalize()


_COLOR_NAMES = {
    "red": (1, 0, 0), "green": (0, 1, 0), "blue": (0, 0, 1), "yellow": (1, 1, 0), "orange": (0.95, 0.6, 0.1),
    "purple": (0.6, 0.2, 0.8), "cyan": (0, 1, 1), "magenta": (1, 0, 1), "white": (1, 1, 1), "black": (0, 0, 0),
    "grey": (0.5, 0.5, 0.5), "brown": (0.55, 0.3, 0.1), "pink": (1, 0.6, 0.8),
}


def color_name(rgb):
    if not rgb or len(rgb) < 3:
        return None
    best, bd = None, 1e9
    for n, c in _COLOR_NAMES.items():
        d = sum((float(rgb[i]) - c[i]) ** 2 for i in range(3))
        if d < bd:
            best, bd = n, d
    return best


def noun_for(model, nouns):
    return nouns.get(model) or re.sub(r"^\d+_", "", model or "").replace("-", " ")


def describe_goal(goal, spec_roles, nouns, a_desc):
    """Plain-English sentence describing the declared goal."""
    if not isinstance(goal, dict):
        return ""
    t = goal.get("type")
    tgt = a_desc or "the target"

    def role_noun(r):
        s = spec_roles.get(r) or {}
        return s.get("desc") or noun_for(s.get("model"), nouns) or r

    if t == "lift":
        return f"Pick up the {tgt} and lift it at least {goal.get('dz', 0.10):.2f} m off its support."
    if t in ("on", "stack"):
        return f"Place the {tgt} on top of the {role_noun(goal.get('ref'))}."
    if t == "in":
        return f"Put the {tgt} inside the {role_noun(goal.get('ref'))}."
    if t == "rel":
        return f"Place the {tgt} to the {goal.get('dir')} of the {role_noun(goal.get('ref'))}."
    if t == "between":
        refs = goal.get("refs") or []
        return f"Place the {tgt} between the {role_noun(refs[0])} and the {role_noun(refs[1])}." if len(refs) == 2 else f"Place the {tgt} between the references."
    if t == "press":
        ref = goal.get("ref")
        return f"Press the {tgt if ref == 'target' else role_noun(ref)}."
    if t == "moved":
        return f"Move the {tgt} by at least {goal.get('eps', 0.05):.2f} m."
    if t == "dual_carry_to":
        return f"Grasp the {tgt} with both arms, lift it, carry it over the {role_noun(goal.get('ref'))} and release."
    if t == "dual_carry":
        return f"Grasp the {tgt} with both arms and lift it."
    if t == "seq":
        parts = [describe_goal(s, spec_roles, nouns, a_desc) for s in goal.get("stages") or []]
        parts = [p.rstrip(".") for p in parts if p]
        return "First " + parts[0][0].lower() + parts[0][1:] + ", then " + ", then ".join(p[0].lower() + p[1:] for p in parts[1:]) + "." if parts else ""
    return f"Goal type `{t}`."


def scoring_rows(goal, criterion, source, spec_roles, nouns, a_desc, exclusive, tier):
    """Binary 0/100 scoring table (ManiScope scores success only)."""
    rows = []
    if source == "handwritten":
        rows.append({"score": 0, "cond": "Task-specific `check_success` returns false (wrong object selected, or the declared end state not reached)."})
        rows.append({"score": 100, "cond": "Task-specific `check_success` returns true. See the environment docstring above for the exact rule."})
        return rows
    if exclusive is not False:
        rows.append({"score": 0, "cond": "Selection layer fails: the target's displacement is not strictly larger than every distractor's displacement (the policy did not act on the instructed object)."})
    if isinstance(goal, dict) and goal.get("type") == "seq":
        stages = goal.get("stages") or []
        for i, st in enumerate(stages[:-1], 1):
            rows.append({"score": 0, "cond": f"Stage {i} reached ({describe_goal(st, spec_roles, nouns, a_desc).rstrip('.')}) but later stages not completed. Stage progress is recorded per episode for diagnosis."})
        rows.append({"score": 100, "cond": "All stages reached in order: " + describe_goal(goal, spec_roles, nouns, a_desc)})
    else:
        rows.append({"score": 0, "cond": "Goal layer fails: " + (CRITERION_EN.get(criterion, "").split(":", 1)[-1].strip() or "declared end state not reached") + " is not satisfied at episode end."})
        rows.append({"score": 100, "cond": "Both layers hold: correct target selected and " + describe_goal(goal, spec_roles, nouns, a_desc)})
    return rows


def parse_md_table(lines, start):
    """Parse a GitHub-flavoured markdown table starting at lines[start] (header row)."""
    header = [c.strip() for c in lines[start].strip().strip("|").split("|")]
    rows = []
    i = start + 2
    while i < len(lines) and lines[i].strip().startswith("|"):
        rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
        i += 1
    return header, rows, i


def parse_rate(cell):
    m = re.search(r"\*\*([0-9.]+)\*\*(?:\s*\[([-0-9.]+),\s*([-0-9.]+)\])?", cell)
    if not m:
        try:
            return {"rate": float(cell.split()[0])}
        except Exception:
            return None
    d = {"rate": float(m.group(1))}
    if m.group(2):
        d["ci"] = [float(m.group(2)), float(m.group(3))]
    return d


def parse_eval_compare(path, scene_names):
    """Historical multi-policy comparison. Returns leaderboard dict or None."""
    if not os.path.exists(path):
        return None
    lines = open(path, encoding="utf-8").read().splitlines()
    lb = {"source": os.path.relpath(path), "archival": True, "policies": [], "per_scene": {},
          "by_dimension": {}, "by_tier": {}, "overall": {}, "episodes": {}, "runs": []}
    # runs
    for ln in lines:
        if ln.startswith("对比的 run"):
            lb["runs"] = re.findall(r"`([^`]+)`", ln)
    # main per-scene table: header starts with "| 维度 | 难度 | 场景 |"
    for i, ln in enumerate(lines):
        if ln.startswith("| 维度 | 难度 | 场景 |"):
            header, rows, _ = parse_md_table(lines, i)
            pol = [h for h in header[3:] if not h.startswith("Δ")]
            lb["policies"] = pol
            for r in rows:
                scene = r[2].strip("`")
                if scene not in scene_names:
                    continue
                lb["per_scene"][scene] = {p: parse_rate(r[3 + k]) for k, p in enumerate(pol)}
            break
    for i, ln in enumerate(lines):
        if ln.startswith("| 按维度均值"):
            header, rows, _ = parse_md_table(lines, i)
            for r in rows:
                lb["by_dimension"][r[0]] = {header[k]: float(r[k].split()[0]) for k in range(1, len(header))}
        if ln.startswith("| 按难度均值"):
            header, rows, _ = parse_md_table(lines, i)
            for r in rows:
                lb["by_tier"][r[0]] = {header[k]: float(r[k].split()[0]) for k in range(1, len(header))}
        if ln.startswith("**48 场景总均值**"):
            body = ln.split("：", 1)[-1]
            for part in body.split("、"):
                m = re.match(r"(.+?)\s+([0-9.]+)\s*$", part.strip())
                if m:
                    lb["overall"][m.group(1).strip()] = float(m.group(2))
        m = re.match(r"## 逐条对齐：DM0\.5 vs (.+?)（共 (\d+) 条", ln)
        if m:
            lb["episodes"][m.group(1).strip()] = int(m.group(2))
    return lb


# ---- main --------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--maniscope", default=os.environ.get("MANISCOPE_ROOT", os.path.join(WEB, "..", "ManiScope")))
    a = ap.parse_args()
    root = os.path.abspath(a.maniscope)
    if not os.path.isdir(os.path.join(root, "suite")):
        sys.exit(f"ManiScope not found at {root}; pass --maniscope")

    scenes_yaml = read_yaml(os.path.join(root, "suite", "scenes_v2.yaml"))
    step_limits = read_yaml(os.path.join(root, "task_config", "_eval_step_limit.yml")) or {}
    nouns = parse_noun_table(os.path.join(root, "envs", "_compo_scene.py"))
    policies_yaml = read_yaml(os.path.join(root, "suite", "policies.yaml"))
    protocol = read_json(os.path.join(root, "protocol.lock.json")) if os.path.exists(os.path.join(root, "protocol.lock.json")) else {}

    meta = scenes_yaml.get("meta", {})
    tiers = scenes_yaml.get("tiers", {})
    dims = []
    all_names = []
    for axis in AXIS_ORDER:
        block = scenes_yaml["axes"][axis]
        repo_dim = block["dim"]
        dim_id = DIM_EN[repo_dim]["paper_id"]          # displayed id (paper numbering, D1–D6)
        entry = {"id": dim_id, "repo_id": repo_dim, "axis": axis, "name_en": DIM_EN[repo_dim]["name"],
                 "short_en": DIM_EN[repo_dim]["short"], "desc_en": DIM_EN[repo_dim]["desc"],
                 "desc_zh": block.get("desc", ""), "scenes": []}
        for idx, sc in enumerate(block["scenes"], 1):
            name = sc["name"]
            all_names.append(name)
            tier = f"L{sc.get('tier')}"
            env_path = os.path.join(root, "envs", f"{name}.py")
            env = parse_env(env_path) if os.path.exists(env_path) else {}
            instr_path = os.path.join(root, "description", "task_instruction", f"{name}.json")
            instr = read_json(instr_path) if os.path.exists(instr_path) else {}
            seed_path = os.path.join(root, "suite", "seeds", f"{name}.json")
            seeds = read_json(seed_path) if os.path.exists(seed_path) else {}
            spec = env.get("SPEC") or []
            spec_roles = {s.get("role"): s for s in spec if isinstance(s, dict)}
            goal = env.get("GOAL")
            refs = set(goal_refs(goal))
            # roles used as placement anchors ("block on the plate") are references too
            refs |= {s.get("rel") for s in spec if isinstance(s, dict) and s.get("rel")}
            objects = []
            for s in spec:
                role = s.get("role")
                if role == "target":
                    kind = "target"
                elif role in refs:
                    kind = "reference"
                else:
                    kind = "distractor"
                if s.get("desc"):
                    desc = s["desc"]
                elif s.get("kind") == "box":
                    cn = color_name(s.get("color"))
                    desc = f"{cn} block" if cn else "block"
                else:
                    desc = noun_for(s.get("model"), nouns) if s.get("model") else None
                objects.append({
                    "role": role, "kind": kind, "type": s.get("kind"),
                    "model": s.get("model") or ("box" if s.get("kind") == "box" else None),
                    "ids": s.get("ids"), "desc": desc,
                    "static": bool(s.get("static")), "color": s.get("color"),
                    "rel": s.get("rel"),
                })
            a_desc = env.get("A_DESC")
            source = sc.get("source")
            criterion = str(sc.get("criterion"))
            if source == "handwritten":
                description = (instr.get("full_description") or "").strip()
                if description:
                    description = description[0].upper() + description[1:]
                    if not description.endswith("."):
                        description += "."
            else:
                description = describe_goal(goal, spec_roles, nouns, a_desc)
            doc = (env.get("module_doc") or env.get("class_doc") or "").strip()
            entry["scenes"].append({
                "name": name, "title": humanize(name), "index": idx,
                "dim": dim_id, "repo_dim": repo_dim, "tier": tier, "tier_desc_zh": tiers.get(tier, ""), "tier_desc_en": TIER_EN.get(tier, ""),
                "source": source, "criterion": criterion, "criterion_en": CRITERION_EN.get(criterion, ""),
                "context_zh": sc.get("context", ""), "context_en": CONTEXT_EN.get(sc.get("context", ""), sc.get("context", "")),
                "baseline": sc.get("baseline") or [], "note_zh": sc.get("note", ""), "smoke": str(sc.get("smoke", "")),
                "step_limit": step_limits.get(name),
                "seeds": {"count": seeds.get("count")},
                "instructions": {"seen": instr.get("seen", []), "unseen": instr.get("unseen", []),
                                 "schema": instr.get("schema", ""), "note": instr.get("_note", "")},
                "a_desc": a_desc, "goal": goal, "mirror": env.get("MIRROR"), "exclusive": env.get("EXCLUSIVE"),
                "base_class": env.get("base"), "objects": objects,
                "description_en": description, "env_doc": doc,
                "scoring": scoring_rows(goal, criterion, source, spec_roles, nouns, a_desc, env.get("EXCLUSIVE"), tier),
                # media slots: one successful and one failed rollout, plus initial-state renders
                "video": {"success": f"assets/videos/{name}_success.mp4", "failure": f"assets/videos/{name}_failure.mp4"},
                "init_images": sorted(
                    os.path.relpath(p, WEB).replace(os.sep, "/")
                    for p in glob.glob(os.path.join(WEB, "assets", "img", "init", name, "*"))
                    if p.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))),
                "thumbnail": f"assets/img/scenes/{name}.png",
            })
        dims.append(entry)

    # optional manual overrides: data/overrides/tasks/<name>.yaml
    ov_dir = os.path.join(DATA, "overrides", "tasks")
    n_ov = 0
    for d in dims:
        for sc in d["scenes"]:
            p = os.path.join(ov_dir, f"{sc['name']}.yaml")
            if os.path.exists(p):
                ov = read_yaml(p) or {}
                sc.update(ov)
                n_ov += 1

    tasks = {
        "suite": {"name": meta.get("formal_note", "formal48-v1").split(":")[0].replace("ManipScope ", ""),
                  "protocol_version": protocol.get("version"),
                  "episodes_default": meta.get("episodes"), "task_config": meta.get("task_config"),
                  "instruction_type": meta.get("instruction_type"), "formal_scenes": meta.get("formal_scenes"),
                  "seeds_per_scene": 100, "randomized_task_config": scenes_yaml.get("skill_x_scene", {}).get("task_config"),
                  "randomized_anchors": scenes_yaml.get("skill_x_scene", {}).get("anchors", [])},
        "tiers": {k: {"zh": v, "en": TIER_EN.get(k, "")} for k, v in tiers.items()},
        "excluded": {**(scenes_yaml.get("excluded_low_expert_yield") or {}), **EXCLUDED_EN},
        "dimensions": dims,
    }
    os.makedirs(DATA, exist_ok=True)
    json.dump(tasks, open(os.path.join(DATA, "tasks.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    pol = {"policies": [], "planned": []}
    for key, p in (policies_yaml.get("policies") or {}).items():
        pol["policies"].append({"key": key, **{k: v for k, v in p.items()}, **split_hf_repo(p.get("hf_repo")),
                                "desc_en": POLICY_DESC_EN.get(key, ""),
                                "interface": CONTROL_IFACE.get(key, {}),
                                "in_paper": key in PAPER_POLICIES,
                                "kind": "agent" if p.get("external_only") else "policy"})
    for key, p in (policies_yaml.get("planned_policies") or {}).items():
        pol["planned"].append({"key": key, **{k: v for k, v in p.items()}, **split_hf_repo(p.get("hf_repo"))})
    json.dump(pol, open(os.path.join(DATA, "policies.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    lb = parse_eval_compare(os.path.join(root, "docs", "archive", "EVAL_COMPARE.md"), set(all_names))
    if lb:
        # legacy reports label the mixture family D7; the paper (and the site) use D6
        lb["by_dimension"] = {DIM_EN[k]["paper_id"]: v for k, v in lb["by_dimension"].items() if k in DIM_EN}
        lb["snapshot"] = "formal-eval-v1 @ 39808b6"
        lb["note"] = ("Task-success rates of the paper snapshot (code freeze formal-eval-v1, commit 39808b6; "
                      "100 frozen seeds per scene for policies, first 5 seeds for agents), copied from the "
                      "evaluation reports in docs/archive/. The public repository has since been normalised; "
                      "re-validation of the simulator runtime on the current snapshot is pending (docs/NORMALIZATION.md).")
        json.dump(lb, open(os.path.join(DATA, "leaderboard.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    n_scenes = sum(len(d["scenes"]) for d in dims)
    print(f"tasks.json: {len(dims)} dimensions, {n_scenes} scenes ({n_ov} overrides applied)")
    print(f"policies.json: {len(pol['policies'])} integrated, {len(pol['planned'])} planned")
    if lb:
        print(f"leaderboard.json: {len(lb['policies'])} policies x {len(lb['per_scene'])} scenes (archival)")
    missing_video = [sc["name"] for d in dims for sc in d["scenes"] if not os.path.exists(os.path.join(WEB, sc["video"]["success"]))]
    no_init = [sc["name"] for d in dims for sc in d["scenes"] if not sc["init_images"]]
    print(f"success videos missing for {len(missing_video)}/{n_scenes} scenes; init images missing for {len(no_init)}/{n_scenes} (placeholders will be shown)")


if __name__ == "__main__":
    main()
