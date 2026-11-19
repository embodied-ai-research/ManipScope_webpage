#!/usr/bin/env python3
"""Turn the HiFi rollout renders into the website's per-scene videos.

Source (read-only): the ManipScope_HiFi workspace, given by $MANIPSCOPE_HIFI (default ../ManipScope_HiFi)
    g05/videos, gpt6_agent/videos, supplement_20260924/videos  (mp4 + sidecar json)
Output:
    assets/videos/<scene>_success.mp4   one successful rollout per scene (G0.5 where available,
                                        otherwise the GPT-6 fallback), 1920x1080, 15 fps, sped up
    data/videos.json                    metadata rendered by build.py (system, instruction, speed,
                                        durations, and for GPT-6 the per-call decision notes)

Per video: keep every k-th frame with k the smallest of 1/2/4/8 such that duration/k <= 20 s;
top banner = system · kind · outcome · scene · seed / instruction (opaque, hides the small label
baked into the source render); bottom-right badge = speed and simulation time; GPT-6 videos get
a right-hand panel listing every tool call with the model's note, current call highlighted.

    python3 scripts/process_videos.py            # all 48 scenes
    python3 scripts/process_videos.py grab_dumbbell ref_cup_on_tray   # subset
"""
import glob
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.dirname(HERE)
HIFI = os.environ.get("MANIPSCOPE_HIFI", os.path.join(WEB, "..", "ManipScope_HiFi"))
SRC_DIRS = ["g05/videos", "gpt6_agent/videos", "supplement_20260924/videos"]
DECISIONS_LOG = os.path.join(HIFI, "gpt6_agent", "bridge_logs", "decisions.jsonl")
OUT_DIR = os.path.join(WEB, "assets", "videos")
OUT_JSON = os.path.join(WEB, "data", "videos.json")

FONT_DIR = "/usr/share/fonts/truetype/dejavu/"
F_BOLD, F_REG, F_OBL = FONT_DIR + "DejaVuSans-Bold.ttf", FONT_DIR + "DejaVuSans.ttf", FONT_DIR + "DejaVuSans-Oblique.ttf"
TARGET_SECONDS = 20.0
W, H, FPS = 1920, 1080, 15
PANEL_W = 800
SYSTEMS = {"G05": ("GalaxeaVLA (G0.5)", "policy"), "GPT6": ("GPT-6", "agent"), "Pi0": ("π0", "policy")}
NAME_RE = re.compile(r"^(G05|GPT6|Pi0)_(.+?)_(success|failure)_ep(\d+)_seed(\d+)_(\w+)\.mp4$")


def font(path, size):
    return ImageFont.truetype(path, size)


def speed_factor(duration):
    for k in (1, 2, 4, 8):
        if duration / k <= TARGET_SECONDS:
            return k
    return 8


def probe(path):
    out = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                   "stream=width,height,nb_frames:format=duration", "-of", "json", path])
    j = json.loads(out)
    s = j["streams"][0]
    return int(s["width"]), int(s["height"]), int(s["nb_frames"]), float(j["format"]["duration"])


def wrap(draw, text, fnt, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=fnt) <= width:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


class Overlay:
    def __init__(self, meta, k, out_dur, decisions=None, sim_seconds=None):
        self.meta, self.k, self.out_dur = meta, k, out_dur
        self.decisions = decisions or []
        self.sim_seconds = sim_seconds
        self.f_title, self.f_instr, self.f_badge, self.f_small = font(F_BOLD, 30), font(F_OBL, 30), font(F_BOLD, 26), font(F_REG, 21)
        self.f_p_title, self.f_p_sub, self.f_p_head, self.f_p_note, self.f_p_foot = font(F_BOLD, 32), font(F_OBL, 23), font(F_BOLD, 23), font(F_REG, 22), font(F_REG, 17)
        self.banner = self._banner()
        self.badge = self._badge()

    def _banner(self):
        c = self.meta["candidate"]
        name, kind = SYSTEMS[self.meta["system"]]
        outcome = "SUCCESS" if self.meta["actual_success"] else "FAILURE"
        line1 = f'{name}  ·  {kind}  ·  {outcome}  ·  {c["task"]}'
        line2 = f'\u201c{c["instruction"]}\u201d'
        bh = 118
        layer = Image.new("RGBA", (W, bh), (10, 12, 18, 255))   # opaque: hides the source render's own label
        d = ImageDraw.Draw(layer)
        d.text((32, 16), line1, font=self.f_title, fill=(255, 255, 255, 255))
        d.text((32, 62), line2, font=self.f_instr, fill=(235, 238, 245, 255))
        return layer

    def _badge(self):
        txt = f'\u00d7{self.k} speed  \u00b7  simulation time {self.meta["duration"]:.1f} s \u2192 {self.out_dur:.1f} s'
        pad = 14
        tw = self.f_badge.getlength(txt)
        layer = Image.new("RGBA", (int(tw + 2 * pad), 26 + 2 * pad), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        d.rounded_rectangle([0, 0, layer.width - 1, layer.height - 1], radius=10, fill=(47, 111, 237, 220))
        d.text((pad, pad - 2), txt, font=self.f_badge, fill=(255, 255, 255, 255))
        return layer

    def active_call(self, frame_idx):
        """Output frame -> tool call whose motion is executing (through the recorded step counter)."""
        if not self.decisions:
            return None
        t_sim = frame_idx * self.k / FPS
        frac = min(1.0, t_sim / max(self.sim_seconds, 1e-6))
        steps = [d["step_after"] for d in self.decisions if d["step_after"] is not None]
        final_step = max(steps) if steps else 0
        step = frac * final_step
        prev = 0
        for d in self.decisions:
            if d["step_after"] is None:
                if step <= 0.4 and prev == 0:
                    return d["call"]
                continue
            if step <= d["step_after"] and d["step_after"] > prev:
                return d["call"]
            prev = max(prev, d["step_after"])
        return self.decisions[-1]["call"]

    def panel(self, frame_idx):
        act = self.active_call(frame_idx)
        img = Image.new("RGB", (PANEL_W, H), (20, 22, 29))
        d = ImageDraw.Draw(img)
        x0, y = 28, 26
        d.text((x0, y), "GPT-6 decisions", font=self.f_p_title, fill=(255, 255, 255)); y += 44
        d.text((x0, y), "one entry per tool call, in order", font=self.f_p_sub, fill=(139, 145, 163)); y += 34
        n_move = sum(1 for c in self.decisions if c["type"] == "move_eef")
        n_rej = sum(1 for c in self.decisions if c["type"] == "rejected")
        d.text((x0, y), f"{len(self.decisions)} calls  ·  {n_move} move_eef  ·  {n_rej} rejected  ·  finish", font=self.f_small, fill=(139, 145, 163)); y += 36
        d.line([x0, y, PANEL_W - x0, y], fill=(44, 49, 64), width=1); y += 12
        foot_h = 84
        avail = H - y - foot_h
        blocks = []
        for c in self.decisions:
            head = f'#{c["call"]}  {c["type"]}'
            if c["type"] == "move_eef":
                head += f'  ·  {c["phase"]}  ·  {c["arm"]} arm'
                if c.get("gripper") is not None:
                    head += f'  ·  gripper {c["gripper"]:g}'
            lines = wrap(d, c["note"] or "(no note)", self.f_p_note, PANEL_W - 2 * x0 - 14)
            blocks.append((c, head, lines, 30 + 27 * len(lines) + 14))
        if sum(b[3] for b in blocks) > avail:          # window around the active call
            idx = next((i for i, b in enumerate(blocks) if b[0]["call"] == act), 0)
            lo = idx
            while lo > 0 and sum(b[3] for b in blocks[lo - 1: idx + 1]) < avail * 0.45:
                lo -= 1
            hi = idx
            while hi + 1 < len(blocks) and sum(b[3] for b in blocks[lo: hi + 2]) <= avail:
                hi += 1
            blocks = blocks[lo: hi + 1]
        for c, head, lines, bh in blocks:
            is_act = c["call"] == act
            done = c["call"] < (act or 0)
            if is_act:
                d.rounded_rectangle([x0 - 10, y - 6, PANEL_W - x0 + 10, y + bh - 8], radius=8, fill=(31, 42, 69))
                d.rectangle([x0 - 10, y - 6, x0 - 6, y + bh - 8], fill=(109, 155, 255))
            col_h = (255, 255, 255) if is_act else ((184, 189, 204) if done else (110, 116, 135))
            col_n = (231, 233, 239) if is_act else ((160, 166, 182) if done else (95, 101, 120))
            if c["type"] == "rejected":
                col_h = (232, 130, 130) if is_act else (150, 90, 90)
            d.text((x0 + 4, y), head, font=self.f_p_head, fill=col_h); y += 30
            for ln in lines:
                d.text((x0 + 4, y), ln, font=self.f_p_note, fill=col_n); y += 27
            y += 14
        fy = H - foot_h + 8
        d.line([x0, fy - 8, PANEL_W - x0, fy - 8], fill=(44, 49, 64), width=1)
        for ln in wrap(d, "Text is the note the model attached to each move_eef / finish call. Its internal reasoning is not recorded. "
                          "Highlight follows the recorded step counter (approximate).", self.f_p_foot, PANEL_W - 2 * x0):
            d.text((x0, fy), ln, font=self.f_p_foot, fill=(120, 126, 145)); fy += 22
        return img

    def compose(self, frame, frame_idx):
        frame.paste(self.banner, (0, 0), self.banner)
        frame.paste(self.badge, (W - self.badge.width - 24, H - self.badge.height - 24), self.badge)
        if self.decisions:
            canvas = Image.new("RGB", (W + PANEL_W, H))
            canvas.paste(frame, (0, 0))
            canvas.paste(self.panel(frame_idx), (W, 0))
            return canvas
        return frame


# ---- GPT-6 decisions --------------------------------------------------------------------------
_EPISODES = None


def decision_episodes():
    """The bridge appends every call of every episode to one log; split where the call index restarts."""
    global _EPISODES
    if _EPISODES is None:
        eps, cur = [], []
        for line in open(DECISIONS_LOG):
            r = json.loads(line)
            if r["call"] == 1 and cur:
                eps.append(cur); cur = []
            cur.append(r)
        if cur:
            eps.append(cur)
        _EPISODES = eps
    return _EPISODES


def load_decisions(run_dir, instruction):
    """Pick the logged episode for this run: same instruction, same number of calls, and the summed
    model-side seconds matching the run's timing record (several runs share an instruction)."""
    timing = json.loads(open(os.path.join(run_dir, "_agent_timing.jsonl")).readline())
    cands = [e for e in decision_episodes()
             if e[0]["observation"].get("instruction") == instruction and len(e) == timing["api_calls"]]
    if not cands:
        raise RuntimeError(f"no decision episode for {instruction!r} with {timing['api_calls']} calls")
    if len(cands) > 1:
        cands.sort(key=lambda e: abs(sum(r["api_seconds"] for r in e) - timing["api_seconds"]))
        if abs(sum(r["api_seconds"] for r in cands[0]) - timing["api_seconds"]) > 1.0:
            raise RuntimeError(f"ambiguous decision episodes for {instruction!r}")
    ep = cands[0]
    steps = {}
    for line in open(os.path.join(run_dir, "audit", "checks.jsonl")):
        s = json.loads(line)
        steps[s["call"]] = s["step"]
    out = []
    for r in ep:
        a = r["action"]
        out.append({"call": r["call"], "type": a["type"], "phase": a.get("phase"), "arm": a.get("arm"),
                    "gripper": a.get("gripper"), "note": a.get("note", ""),
                    "step_after": steps.get(r["call"]) if a["type"] != "rejected" else None,
                    "reasoning_tokens": ((r.get("usage") or {}).get("output_tokens_details") or {}).get("reasoning_tokens")})
    return out


# ---- processing --------------------------------------------------------------------------------
def process(job):
    src, out_mp4, system = job["src"], job["out"], job["system"]
    m = json.load(open(src[:-4] + ".json"))
    sw, sh, nb, dur = probe(src)
    k = speed_factor(dur)
    decisions = sim = None
    if system == "GPT6":
        decisions = load_decisions(m["source_run"], m["candidate"]["instruction"])
        sim = json.load(open(os.path.join(m["source_run"], "trajectory.json")))["simulation_seconds"]
    ov = Overlay({"system": system, "candidate": m["candidate"], "actual_success": m["actual_success"], "duration": dur}, k, dur / k, decisions, sim)
    out_w = W + (PANEL_W if decisions else 0)
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", src, "-vf",
                            f"select='not(mod(n\\,{k}))',setpts=N/{FPS}/TB,scale={W}:{H}:flags=lanczos",
                            "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{out_w}x{H}",
                            "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "22", "-threads", "4",
                            "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-map_metadata", "-1", out_mp4], stdin=subprocess.PIPE)
    n, frame_bytes = 0, W * H * 3
    while True:
        buf = dec.stdout.read(frame_bytes)
        if len(buf) < frame_bytes:
            break
        enc.stdin.write(ov.compose(Image.frombytes("RGB", (W, H), buf), n).tobytes())
        n += 1
    dec.wait(); enc.stdin.close(); enc.wait()
    if enc.returncode != 0:
        raise RuntimeError(f"encode failed for {src}")
    ow, oh, onb, odur = probe(out_mp4)
    poster = write_poster(out_mp4)
    name, kind = SYSTEMS[system]
    return job["scene"], {
        "file": os.path.relpath(out_mp4, WEB).replace(os.sep, "/"),
        "poster": os.path.relpath(poster, WEB).replace(os.sep, "/"),
        "system": name, "kind": kind, "outcome": "success" if m["actual_success"] else "failure",
        "episode": m["candidate"]["original_episode_index"],
        "instruction": m["candidate"]["instruction"],
        "historical_success": m["candidate"].get("historical_success"),
        "source_resolution": f"{sw}x{sh}", "source_frames": nb,
        "source_seconds": round(dur, 2), "speed": k, "output_resolution": f"{ow}x{oh}",
        "output_frames": onb, "output_seconds": round(odur, 2), "output_bytes": os.path.getsize(out_mp4),
        "decisions": decisions,
    }


def write_poster(out_mp4):
    """First frame of the processed video (banner included) as the player's poster image."""
    poster = out_mp4[:-4] + ".jpg"
    subprocess.check_call(["ffmpeg", "-v", "error", "-y", "-i", out_mp4, "-vf", "select='eq(n\\,0)',scale=1280:-2:flags=lanczos",
                           "-vframes", "1", "-q:v", "3", poster])
    return poster


def select_sources(scenes):
    """One success video per scene: prefer G0.5, otherwise the GPT-6 fallback."""
    found = {}
    for d in SRC_DIRS:
        for p in sorted(glob.glob(os.path.join(HIFI, d, "*.mp4"))):
            mm = NAME_RE.match(os.path.basename(p))
            if not mm or mm.group(3) != "success":
                continue
            system, scene = mm.group(1), mm.group(2)
            if scene not in scenes:
                continue
            cur = found.get(scene)
            rank = {"G05": 0, "GPT6": 1, "Pi0": 2}[system]
            if cur is None or rank < cur[0]:
                found[scene] = (rank, system, p)
    return {sc: (sysname, p) for sc, (_, sysname, p) in found.items()}


def main(argv):
    tasks = json.load(open(os.path.join(WEB, "data", "tasks.json")))
    all_scenes = [sc["name"] for d in tasks["dimensions"] for sc in d["scenes"]]
    if argv[:1] == ["--posters"]:            # regenerate poster images for existing outputs only
        results = json.load(open(OUT_JSON))
        for sc, rec in results.items():
            rec["poster"] = os.path.relpath(write_poster(os.path.join(WEB, rec["file"])), WEB).replace(os.sep, "/")
        json.dump(results, open(OUT_JSON, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        print(f"posters written for {len(results)} scenes")
        return
    scenes = argv or all_scenes
    sources = select_sources(set(scenes))
    missing = [s for s in scenes if s not in sources]
    os.makedirs(OUT_DIR, exist_ok=True)
    jobs = [{"scene": sc, "system": sysname, "src": p, "out": os.path.join(OUT_DIR, f"{sc}_success.mp4")} for sc, (sysname, p) in sources.items()]
    print(f"{len(jobs)} success videos to process ({sum(1 for j in jobs if j['system']=='G05')} G0.5, "
          f"{sum(1 for j in jobs if j['system']=='GPT6')} GPT-6); missing: {missing or 'none'}", flush=True)
    existing = json.load(open(OUT_JSON)) if os.path.exists(OUT_JSON) else {}
    results = dict(existing) if argv else {}
    with ProcessPoolExecutor(max_workers=int(os.environ.get("VIDEO_WORKERS", "12"))) as ex:
        for scene, rec in ex.map(process, jobs):
            results[scene] = rec
            print(f"  {scene:34s} {rec['system']:18s} x{rec['speed']}  {rec['source_seconds']:6.1f}s -> {rec['output_seconds']:5.1f}s  {rec['output_bytes']/1e6:4.1f} MB", flush=True)
    ordered = {sc: results[sc] for sc in all_scenes if sc in results}
    json.dump(ordered, open(OUT_JSON, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    total = sum(r["output_bytes"] for r in ordered.values())
    print(f"wrote {OUT_JSON}: {len(ordered)} scenes, {total/1e6:.0f} MB of video")


if __name__ == "__main__":
    main(sys.argv[1:])
