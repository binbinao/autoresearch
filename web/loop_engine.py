"""Experiment loop state machine for the AutoResearch beginner console.

Loop Engineering principles:
- Explicit states with clear transitions
- Observable checkpoints (status payload)
- Safe stop / rollback paths
- Never silently advance on crash
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_TSV = REPO_ROOT / "results.tsv"
RUN_LOG = REPO_ROOT / "run.log"
PROGRAM_MD = REPO_ROOT / "program.md"
PROGRAM_ZH_MD = REPO_ROOT / "program_zh.md"
PROGRAM_MACOS_MD = REPO_ROOT / "program_macos.md"
PROGRAM_MACOS_ZH_MD = REPO_ROOT / "program_macos_zh.md"
PROGRAM_CPU_MD = REPO_ROOT / "program_cpu.md"
PROGRAM_CPU_ZH_MD = REPO_ROOT / "program_cpu_zh.md"
CACHE_DIR = Path.home() / ".cache" / "autoresearch"

PROGRAM_PLATFORMS = ("gpu", "macos", "cpu")
PROGRAM_LANGS = ("en", "zh")

PROGRAM_FILES = {
    ("gpu", "en"): PROGRAM_MD,
    ("gpu", "zh"): PROGRAM_ZH_MD,
    ("macos", "en"): PROGRAM_MACOS_MD,
    ("macos", "zh"): PROGRAM_MACOS_ZH_MD,
    ("cpu", "en"): PROGRAM_CPU_MD,
    ("cpu", "zh"): PROGRAM_CPU_ZH_MD,
}

PRESET_TO_PLATFORM = {
    "gpu_default": "gpu",
    "macos_small": "macos",
    "cpu_tiny": "cpu",
}

PLATFORM_TO_PRESET = {
    "gpu": "gpu_default",
    "macos": "macos_small",
    "cpu": "cpu_tiny",
}


def program_path(lang: str = "en", platform: str = "gpu") -> Path:
    lang_key = (lang or "en").lower().strip()
    plat_key = (platform or "gpu").lower().strip()
    if lang_key not in PROGRAM_LANGS:
        raise ValueError("lang 必须是 en 或 zh")
    if plat_key not in PROGRAM_PLATFORMS:
        raise ValueError("platform 必须是 gpu / macos / cpu")
    return PROGRAM_FILES[(plat_key, lang_key)]


def detect_device() -> str:
    """Return a short compute device tag: cuda:… / mps / cpu."""
    try:
        import torch

        if torch.cuda.is_available():
            return f"cuda:{torch.cuda.get_device_name(0)}"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
        return "cpu"
    except Exception:
        # Torch missing/broken: still classify by OS below; tag as cpu.
        return "cpu"


def detect_platform() -> str:
    """Map host to one of three experiment presets: gpu / macos / cpu.

    Rules (simple, intentional):
    1. NVIDIA CUDA available → gpu
    2. Running on macOS (Darwin) → macos
    3. Otherwise → cpu
    """
    import platform as py_platform

    device = detect_device()
    if device.startswith("cuda"):
        return "gpu"
    if py_platform.system() == "Darwin":
        return "macos"
    return "cpu"


def detect_runtime_env() -> dict[str, Any]:
    """Always return one of GPU / macOS / CPU — never an empty result."""
    import platform as py_platform
    import sys

    device = detect_device()
    plat = detect_platform()
    system = py_platform.system()
    machine = py_platform.machine()
    preset = PLATFORM_TO_PRESET[plat]
    labels = {"gpu": "GPU", "macos": "macOS", "cpu": "CPU"}

    if plat == "gpu":
        reason = f"本机有 NVIDIA GPU（{device}），使用 GPU 预设。"
    elif plat == "macos":
        accel = "MPS" if device == "mps" else "CPU 回退"
        reason = f"本机是 macOS（{machine}，加速：{accel}），使用 macOS 小模型预设。"
    else:
        reason = f"本机无 NVIDIA GPU 且非 macOS（{system} {machine}），使用 CPU 迷你预设。"

    return {
        "ok": True,
        "platform": plat,
        "label": labels[plat],
        "device": device,
        "os": system,
        "arch": machine,
        "python": sys.version.split()[0],
        "recommended_preset": preset,
        "reason": reason,
    }


class LoopState(str, Enum):
    IDLE = "idle"
    PREPARING = "preparing"
    RUNNING = "running"
    DECIDING = "deciding"
    APPLYING = "applying"
    ERROR = "error"


METRIC_RE = re.compile(
    r"^(val_bpb|training_seconds|total_seconds|peak_vram_mb|mfu_percent|"
    r"total_tokens_M|num_steps|num_params_M|depth|device):\s*(.+)$",
    re.MULTILINE,
)

# train.py prints progress with carriage returns: "\rstep 00012 (4.0%) | loss: 3.21 | ..."
PROGRESS_RE = re.compile(
    r"step\s+(\d+)\s+\(([0-9.]+)%\)\s*\|\s*loss:\s*([0-9.eE+-]+)"
    r"(?:\s*\|\s*lrm:\s*([0-9.eE+-]+))?"
    r"(?:.*?\|\s*tok/sec:\s*([0-9,]+))?"
    r"(?:.*?\|\s*mfu:\s*([0-9.]+)%)?",
)


@dataclass
class ExperimentResult:
    val_bpb: float | None = None
    peak_vram_mb: float | None = None
    training_seconds: float | None = None
    total_seconds: float | None = None
    mfu_percent: float | None = None
    total_tokens_M: float | None = None
    num_steps: int | None = None
    num_params_M: float | None = None
    depth: int | None = None
    device: str | None = None
    crashed: bool = False
    raw_summary: dict[str, str] = field(default_factory=dict)


@dataclass
class LoopSnapshot:
    state: LoopState = LoopState.IDLE
    message: str = "准备就绪"
    branch: str = ""
    best_val_bpb: float | None = None
    last_result: ExperimentResult | None = None
    pending_description: str = ""
    pending_commit: str = ""
    run_started_at: float | None = None
    run_pid: int | None = None
    env_overrides: dict[str, str] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    checkpoints: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        return data


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_metrics(text: str) -> ExperimentResult:
    found = {m.group(1): m.group(2).strip() for m in METRIC_RE.finditer(text)}
    result = ExperimentResult(raw_summary=found, crashed="val_bpb" not in found)

    def fget(key: str) -> float | None:
        try:
            return float(found[key]) if key in found else None
        except ValueError:
            return None

    def iget(key: str) -> int | None:
        try:
            return int(float(found[key])) if key in found else None
        except ValueError:
            return None

    result.val_bpb = fget("val_bpb")
    result.peak_vram_mb = fget("peak_vram_mb")
    result.training_seconds = fget("training_seconds")
    result.total_seconds = fget("total_seconds")
    result.mfu_percent = fget("mfu_percent")
    result.total_tokens_M = fget("total_tokens_M")
    result.num_steps = iget("num_steps")
    result.num_params_M = fget("num_params_M")
    result.depth = iget("depth")
    result.device = found.get("device")
    if result.val_bpb is None or result.val_bpb <= 0:
        result.crashed = True
    return result


def parse_progress_line(line: str) -> dict[str, Any] | None:
    match = PROGRESS_RE.search(line)
    if not match:
        return None
    tok = match.group(5)
    return {
        "step": int(match.group(1)),
        "pct": float(match.group(2)),
        "loss": float(match.group(3)),
        "lrm": float(match.group(4)) if match.group(4) else None,
        "tok_per_sec": int(tok.replace(",", "")) if tok else None,
        "mfu": float(match.group(6)) if match.group(6) else None,
    }


def parse_progress_text(text: str) -> list[dict[str, Any]]:
    """Extract unique progress points (last write wins per step)."""
    by_step: dict[int, dict[str, Any]] = {}
    for match in PROGRESS_RE.finditer(text):
        tok = match.group(5)
        point = {
            "step": int(match.group(1)),
            "pct": float(match.group(2)),
            "loss": float(match.group(3)),
            "lrm": float(match.group(4)) if match.group(4) else None,
            "tok_per_sec": int(tok.replace(",", "")) if tok else None,
            "mfu": float(match.group(6)) if match.group(6) else None,
        }
        by_step[point["step"]] = point
    return [by_step[k] for k in sorted(by_step)]


def synthesize_demo_progress(n: int = 40) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for i in range(n):
        # Smooth exponential-ish decay for teaching "convergence"
        loss = 4.2 * (0.92 ** i) + 0.85 + (0.03 if i % 7 == 0 else 0.0)
        points.append(
            {
                "step": i,
                "pct": round(100.0 * (i + 1) / n, 1),
                "loss": round(loss, 6),
                "lrm": 1.0 if i < n * 0.5 else max(0.0, 1.0 - (i - n * 0.5) / (n * 0.5)),
                "tok_per_sec": 12000 + i * 30,
                "mfu": 18.0,
            }
        )
    return points


def read_results_tsv() -> list[dict[str, str]]:
    if not RESULTS_TSV.exists():
        return []
    lines = RESULTS_TSV.read_text(encoding="utf-8").splitlines()
    if not lines:
        return []
    header = lines[0].split("\t")
    rows: list[dict[str, str]] = []
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split("\t")
        row = {header[i]: parts[i] if i < len(parts) else "" for i in range(len(header))}
        rows.append(row)
    return rows


def ensure_results_header() -> None:
    if not RESULTS_TSV.exists():
        RESULTS_TSV.write_text(
            "commit\tval_bpb\tmemory_gb\tstatus\tdescription\n",
            encoding="utf-8",
        )


def append_result_row(
    commit: str,
    val_bpb: float,
    memory_gb: float,
    status: str,
    description: str,
) -> None:
    ensure_results_header()
    safe_desc = description.replace("\t", " ").replace("\n", " ")
    with RESULTS_TSV.open("a", encoding="utf-8") as f:
        f.write(f"{commit}\t{val_bpb:.6f}\t{memory_gb:.1f}\t{status}\t{safe_desc}\n")


def best_val_bpb_from_rows(rows: list[dict[str, str]]) -> float | None:
    best: float | None = None
    for row in rows:
        if row.get("status") != "keep":
            continue
        try:
            value = float(row.get("val_bpb", "0") or "0")
        except ValueError:
            continue
        if value <= 0:
            continue
        if best is None or value < best:
            best = value
    return best


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=check,
    )


def current_branch() -> str:
    try:
        return git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    except subprocess.CalledProcessError:
        return ""


def short_commit() -> str:
    try:
        return git("rev-parse", "--short=7", "HEAD").stdout.strip()
    except subprocess.CalledProcessError:
        return "0000000"


def data_ready() -> bool:
    if not CACHE_DIR.exists():
        return False
    has_tokenizer = any(CACHE_DIR.glob("**/tokenizer*")) or (CACHE_DIR / "tokenizer.pkl").exists()
    has_shards = any(CACHE_DIR.glob("**/*.bin")) or any(CACHE_DIR.glob("**/*.npy"))
    # prepare.py may store shards differently; also accept any non-empty cache
    return has_tokenizer or has_shards or any(CACHE_DIR.iterdir())


PRESETS: dict[str, dict[str, str]] = {
    "gpu_default": {},
    "macos_small": {
        "AR_MAX_SEQ_LEN": "512",
        "AR_EVAL_TOKENS": "262144",
        "AR_TIME_BUDGET": "60",
        "AR_DEPTH": "4",
        "AR_WINDOW_PATTERN": "L",
        "AR_DEVICE_BATCH_SIZE": "8",
        "AR_TOTAL_BATCH_SIZE": "16384",
    },
    "cpu_tiny": {
        "AR_MAX_SEQ_LEN": "256",
        "AR_EVAL_TOKENS": "65536",
        "AR_TIME_BUDGET": "30",
        "AR_DEPTH": "2",
        "AR_WINDOW_PATTERN": "L",
        "AR_DEVICE_BATCH_SIZE": "2",
        "AR_TOTAL_BATCH_SIZE": "4096",
    },
}


class ExperimentLoop:
    """Owns one training subprocess and decision lifecycle."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.snap = LoopSnapshot()
        self._proc: subprocess.Popen[str] | None = None
        self._log_thread: threading.Thread | None = None
        self._log_lines: list[str] = []
        self._progress_series: list[dict[str, Any]] = []
        self._log_cond = threading.Condition()
        self.refresh_static()

    def refresh_static(self) -> None:
        rows = read_results_tsv()
        with self.lock:
            self.snap.branch = current_branch()
            self.snap.history = rows
            self.snap.best_val_bpb = best_val_bpb_from_rows(rows)

    def _reset_live_buffers(self) -> None:
        with self._log_cond:
            self._log_lines = []
            self._progress_series = []
            self._log_cond.notify_all()

    def _ingest_log_line(self, line: str) -> None:
        clean = line.rstrip("\n")
        if not clean:
            return
        point = parse_progress_line(clean)
        with self._log_cond:
            self._log_lines.append(clean)
            if len(self._log_lines) > 5000:
                self._log_lines = self._log_lines[-3000:]
            if point is not None:
                if self._progress_series and self._progress_series[-1]["step"] == point["step"]:
                    self._progress_series[-1] = point
                else:
                    self._progress_series.append(point)
                if len(self._progress_series) > 4000:
                    self._progress_series = self._progress_series[-2500:]
            self._log_cond.notify_all()

    def _reload_progress_from_log(self) -> None:
        if not RUN_LOG.exists():
            return
        text = RUN_LOG.read_text(encoding="utf-8", errors="replace")
        points = parse_progress_text(text)
        with self._log_cond:
            if points:
                self._progress_series = points

    def checkpoint(self, message: str) -> None:
        with self.lock:
            self.snap.message = message
            self.snap.checkpoints.append({"at": utc_now(), "message": message})
            self.snap.checkpoints = self.snap.checkpoints[-40:]

    def status(self) -> dict[str, Any]:
        self.refresh_static()
        if self.snap.state == LoopState.RUNNING:
            self._reload_progress_from_log()
        with self.lock:
            payload = self.snap.to_dict()
        with self._log_cond:
            series = list(self._progress_series)
            logs = list(self._log_lines[-200:])
        payload["data_ready"] = data_ready()
        payload["device"] = detect_device()
        payload["detected_platform"] = detect_platform()
        payload["runtime_env"] = detect_runtime_env()
        payload["active_preset"] = next(
            (
                name
                for name, values in PRESETS.items()
                if dict(values) == dict(payload.get("env_overrides") or {})
            ),
            None,
        )
        payload["program_exists"] = PROGRAM_MD.exists()
        payload["program_platforms"] = {
            plat: {lng: PROGRAM_FILES[(plat, lng)].exists() for lng in PROGRAM_LANGS}
            for plat in PROGRAM_PLATFORMS
        }
        payload["program_langs"] = {
            "en": PROGRAM_MD.exists(),
            "zh": PROGRAM_ZH_MD.exists(),
        }
        payload["results_count"] = len(payload["history"])
        payload["log_lines"] = logs
        payload["progress_series"] = series
        latest = series[-1] if series else None
        payload["live_progress"] = latest
        payload["presets"] = {k: dict(v) for k, v in PRESETS.items()}
        return payload

    def set_env_overrides(self, overrides: dict[str, str]) -> None:
        cleaned = {str(k): str(v) for k, v in overrides.items() if str(v).strip() != ""}
        with self.lock:
            self.snap.env_overrides = cleaned
            self.checkpoint(f"已更新 {len(cleaned)} 个环境变量覆盖")

    def apply_preset(self, name: str) -> dict[str, str]:
        if name not in PRESETS:
            raise ValueError(f"未知预设: {name}")
        preset = dict(PRESETS[name])
        self.set_env_overrides(preset)
        return preset

    def create_branch(self, tag: str) -> str:
        tag = tag.strip().replace(" ", "-")
        if not tag:
            raise ValueError("需要 run tag")
        branch = f"autoresearch/{tag}"
        existing = git("branch", "--list", branch, check=False).stdout.strip()
        if existing:
            git("checkout", branch)
        else:
            git("checkout", "-b", branch)
        ensure_results_header()
        self.refresh_static()
        self.checkpoint(f"已切换到分支 {branch}")
        return branch

    def start_prepare(self) -> None:
        with self.lock:
            if self.snap.state in {LoopState.RUNNING, LoopState.PREPARING}:
                raise RuntimeError("已有任务在运行")
            self.snap.state = LoopState.PREPARING
            self.snap.error = None
        self._reset_live_buffers()
        self.checkpoint("开始准备数据与 tokenizer…")
        self._spawn(["uv", "run", "prepare.py"], kind="prepare")

    def start_env_setup(self) -> dict[str, Any]:
        """Install deps for the detected host (GPU / macOS / CPU) and smoke-check torch."""
        with self.lock:
            if self.snap.state in {LoopState.RUNNING, LoopState.PREPARING}:
                raise RuntimeError("已有任务在运行")
            self.snap.state = LoopState.PREPARING
            self.snap.error = None

        info = detect_runtime_env()
        preset_name = info["recommended_preset"]
        self.apply_preset(preset_name)
        self._reset_live_buffers()
        self.checkpoint(
            f"开始环境准备：{info['label']}（{info['device']}）→ 预设 {preset_name}"
        )

        repo = str(REPO_ROOT)
        plat = info["platform"]
        label = info["label"]
        device = info["device"]
        # bash script: sync deps, verify torch, optional quick setup test if data exists
        script = f"""set -euo pipefail
cd {repo!r}
echo "[env-setup] platform={plat} label={label} device={device}"
echo "[env-setup] 安装依赖：uv sync --extra ui …"
uv sync --extra ui
echo "[env-setup] 验证 PyTorch 与设备…"
uv run python - <<'PY'
import platform
import sys

import torch

system = platform.system()
machine = platform.machine()
if torch.cuda.is_available():
    got = "gpu"
    device = f"cuda:{{torch.cuda.get_device_name(0)}}"
elif system == "Darwin":
    got = "macos"
    device = "mps" if torch.backends.mps.is_available() else "cpu"
else:
    got = "cpu"
    device = "cpu"

expected = {plat!r}
print(f"  Python:  {{sys.version.split()[0]}}")
print(f"  PyTorch: {{torch.__version__}}")
print(f"  OS:      {{system}} {{machine}}")
print(f"  Device:  {{device}}")
print(f"  Class:   {{got}} (expected {{expected}})")
if got != expected:
    raise SystemExit(f"[FAIL] 环境分类不匹配：got={{got}} expected={{expected}}")
# Tiny tensor smoke on the actual compute device
dev = torch.device("cuda" if got == "gpu" else ("mps" if device == "mps" else "cpu"))
t = torch.randn(2, 3, device=dev)
assert t.shape == (2, 3)
print(f"  [PASS] tensor ops on {{dev}}")
print("[env-setup] 依赖与设备检查通过")
PY
if [ -d "$HOME/.cache/autoresearch" ] && [ -n "$(ls -A "$HOME/.cache/autoresearch" 2>/dev/null || true)" ]; then
  echo "[env-setup] 检测到已有数据缓存，运行 test_setup.py --quick …"
  uv run test_setup.py --quick
else
  echo "[env-setup] 尚未准备数据，跳过 test_setup。下一步请点「准备数据」。"
fi
echo "[env-setup] DONE — {label} 环境可用"
"""
        self._spawn(["bash", "-lc", script], kind="env_setup")
        return {
            "platform": plat,
            "label": label,
            "device": device,
            "preset": preset_name,
        }

    def start_run(self, description: str) -> None:
        description = description.strip() or "untitled experiment"
        with self.lock:
            if self.snap.state in {LoopState.RUNNING, LoopState.PREPARING}:
                raise RuntimeError("已有任务在运行")
            self.snap.state = LoopState.RUNNING
            self.snap.error = None
            self.snap.pending_description = description
            self.snap.last_result = None
            self.snap.run_started_at = time.time()
        RUN_LOG.write_text("", encoding="utf-8")
        self._reset_live_buffers()
        self.checkpoint(f"启动训练实验：{description}")
        self._spawn(["uv", "run", "train.py"], kind="train", redirect_log=True)

    def start_demo(self, description: str = "demo walkthrough") -> None:
        """Synthetic deciding state so beginners can practice keep/discard without training."""
        with self.lock:
            if self.snap.state in {LoopState.RUNNING, LoopState.PREPARING}:
                raise RuntimeError("已有任务在运行")
            self.snap.pending_description = description.strip() or "demo walkthrough"
            best = self.snap.best_val_bpb
            demo_bpb = 0.990000 if best is None else max(0.01, best - 0.001)
            self.snap.last_result = ExperimentResult(
                val_bpb=demo_bpb,
                peak_vram_mb=1024.0,
                training_seconds=12.0,
                total_seconds=15.0,
                mfu_percent=0.0,
                total_tokens_M=1.0,
                num_steps=10,
                num_params_M=1.0,
                depth=4,
                device=detect_device(),
                crashed=False,
                raw_summary={"val_bpb": f"{demo_bpb:.6f}", "device": detect_device()},
            )
            self.snap.state = LoopState.DECIDING
            self.snap.error = None
            series = synthesize_demo_progress()
            with self._log_cond:
                self._progress_series = series
                self._log_lines = [
                    "[demo] 这是演示模式，没有真正启动 train.py。",
                    f"[demo] 合成 val_bpb={demo_bpb:.6f}",
                    f"[demo] 已生成 {len(series)} 个 loss 采样点，便于观察收敛曲线。",
                    "[demo] 请练习「保留 / 丢弃」，熟悉实验循环。",
                ]
                self._log_cond.notify_all()
        self.checkpoint(f"演示完成 val_bpb={demo_bpb:.6f}，进入决策")

    def stop(self) -> None:
        with self.lock:
            proc = self._proc
        if proc and proc.poll() is None:
            self.checkpoint("正在停止进程…")
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        with self.lock:
            self.snap.state = LoopState.IDLE
            self.snap.run_pid = None
            self._proc = None
        self.checkpoint("已停止")

    def decide(self, action: str) -> dict[str, Any]:
        action = action.lower().strip()
        if action not in {"keep", "discard", "crash"}:
            raise ValueError("action 必须是 keep / discard / crash")

        with self.lock:
            if self.snap.state not in {LoopState.DECIDING, LoopState.ERROR, LoopState.IDLE}:
                # Allow decide after completed run even if UI lagged
                if self.snap.last_result is None:
                    raise RuntimeError("没有待决策的实验结果")
            result = self.snap.last_result
            description = self.snap.pending_description or "experiment"
            self.snap.state = LoopState.APPLYING

        if result is None:
            raise RuntimeError("没有待决策的实验结果")

        commit = short_commit()
        memory_gb = (result.peak_vram_mb or 0.0) / 1024.0
        val = result.val_bpb if result.val_bpb is not None else 0.0

        if action == "keep":
            # Ensure working tree committed if dirty (optional lightweight commit)
            status = git("status", "--porcelain", check=False).stdout.strip()
            if status:
                git("add", "train.py", check=False)
                git(
                    "commit",
                    "-m",
                    f"experiment: {description}",
                    check=False,
                )
                commit = short_commit()
            append_result_row(commit, val, memory_gb, "keep", description)
            message = f"保留实验 {commit}，val_bpb={val:.6f}"
        elif action == "discard":
            append_result_row(commit, val, memory_gb, "discard", description)
            # Soft reset only if on autoresearch branch and train.py dirty/changed
            branch = current_branch()
            if branch.startswith("autoresearch/"):
                git("checkout", "--", "train.py", check=False)
            message = f"丢弃实验，回退 train.py 改动"
        else:
            append_result_row(commit, 0.0, 0.0, "crash", description)
            branch = current_branch()
            if branch.startswith("autoresearch/"):
                git("checkout", "--", "train.py", check=False)
            message = "已记录 crash"

        with self.lock:
            self.snap.state = LoopState.IDLE
            self.snap.pending_description = ""
            self.snap.pending_commit = commit
        self.refresh_static()
        self.checkpoint(message)
        return {"ok": True, "message": message, "commit": commit}

    def _spawn(self, cmd: list[str], kind: str, redirect_log: bool = False) -> None:
        env = os.environ.copy()
        with self.lock:
            env.update(self.snap.env_overrides)

        stdout_target: Any
        if redirect_log:
            stdout_target = RUN_LOG.open("w", encoding="utf-8")
        else:
            stdout_target = subprocess.PIPE

        proc = subprocess.Popen(
            cmd,
            cwd=REPO_ROOT,
            env=env,
            stdout=stdout_target,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        with self.lock:
            self._proc = proc
            self.snap.run_pid = proc.pid

        def flush_buffer(buf: str) -> str:
            # train.py uses \\r progress updates; split on both \\r and \\n
            while True:
                idx_n = buf.find("\n")
                idx_r = buf.find("\r")
                candidates = [i for i in (idx_n, idx_r) if i >= 0]
                if not candidates:
                    return buf
                cut = min(candidates)
                piece = buf[:cut]
                buf = buf[cut + 1 :]
                if piece:
                    self._ingest_log_line(piece)
            return buf

        def pump() -> None:
            try:
                if redirect_log:
                    with RUN_LOG.open("r", encoding="utf-8", errors="replace", newline="") as f:
                        buf = ""
                        while True:
                            chunk = f.read(2048)
                            if chunk:
                                buf += chunk
                                buf = flush_buffer(buf)
                            elif proc.poll() is not None:
                                rest = f.read()
                                if rest:
                                    buf += rest
                                buf = flush_buffer(buf)
                                if buf.strip():
                                    self._ingest_log_line(buf)
                                break
                            else:
                                time.sleep(0.15)
                else:
                    assert proc.stdout is not None
                    for line in proc.stdout:
                        self._ingest_log_line(line)
            finally:
                code = proc.wait()
                if kind == "train":
                    self._reload_progress_from_log()
                self._on_process_exit(kind, code)

        self._log_thread = threading.Thread(target=pump, name=f"loop-{kind}", daemon=True)
        self._log_thread.start()

    def _on_process_exit(self, kind: str, code: int) -> None:
        with self.lock:
            self.snap.run_pid = None
            self._proc = None

        if kind in {"prepare", "env_setup"}:
            label = "数据准备" if kind == "prepare" else "环境准备"
            if code == 0:
                with self.lock:
                    self.snap.state = LoopState.IDLE
                self.checkpoint(f"{label}完成")
            else:
                with self.lock:
                    self.snap.state = LoopState.ERROR
                    self.snap.error = f"{label}失败，退出码 {code}"
                self.checkpoint(self.snap.error)
            return

        # train finished
        log_text = RUN_LOG.read_text(encoding="utf-8", errors="replace") if RUN_LOG.exists() else ""
        result = parse_metrics(log_text)
        if code != 0:
            result.crashed = True

        with self.lock:
            self.snap.last_result = result
            if result.crashed:
                self.snap.state = LoopState.ERROR
                self.snap.error = "训练崩溃或未产出 val_bpb"
                self.checkpoint(self.snap.error)
            else:
                self.snap.state = LoopState.DECIDING
                best = self.snap.best_val_bpb
                improved = best is None or (result.val_bpb is not None and result.val_bpb < best)
                hint = "优于当前最佳，建议保留" if improved else "未优于当前最佳，建议丢弃"
                self.checkpoint(f"训练完成 val_bpb={result.val_bpb:.6f} — {hint}")

    def iter_log(self, from_index: int = 0):
        idx = from_index
        while True:
            with self._log_cond:
                while idx >= len(self._log_lines):
                    if self.snap.state not in {LoopState.RUNNING, LoopState.PREPARING}:
                        # flush any remaining then stop
                        if idx >= len(self._log_lines):
                            return
                    self._log_cond.wait(timeout=1.0)
                batch = self._log_lines[idx:]
                idx = len(self._log_lines)
            for line in batch:
                yield line


# Singleton used by FastAPI
engine = ExperimentLoop()
