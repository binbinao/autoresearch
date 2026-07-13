# autoresearch (macOS / Apple Silicon)

This is the Auto Research brief for **Mac (MPS)**. You are on unified memory, not an NVIDIA discrete GPU. Stock H100-oriented defaults will OOM or crawl. Follow Mac realities below.

> See also `MACOS_TESTING.md`. In the console, apply the **macOS** preset before running.

## Platform realities (read first)

- Device should be `mps` on Apple Silicon. If you land on `cpu`, check PyTorch MPS availability.
- **Do not use stock large defaults.** Start from the small preset:
  - `AR_MAX_SEQ_LEN=512`
  - `AR_DEPTH=4`
  - `AR_WINDOW_PATTERN=L` (avoid `SSSL` at first)
  - `AR_DEVICE_BATCH_SIZE=8` (drop to `4` under pressure)
  - `AR_TOTAL_BATCH_SIZE=16384`
  - `AR_EVAL_TOKENS=262144`
- **Time budget:** use `AR_TIME_BUDGET=60` for smoke / fast loops; only then scale to 120 / 300.
- **No Flash Attention 3** on MPS — expect much lower throughput than CUDA.
- **`peak_vram_mb` is often 0 on MPS** — do not treat it as the main memory signal; watch for jetsam / kill / incomplete runs.
- Reference (M4 32GB, 60s smoke): about `num_params_M ≈ 11.5`, `val_bpb` around ~1.9 — **do not expect H100-scale ~1.0 / 50M-param numbers**.

## Setup

1. Agree on a tag (e.g. `jul12-mac`); `autoresearch/<tag>` must not exist.
2. `git checkout -b autoresearch/<tag>`.
3. Read `README.md`, `MACOS_TESTING.md`, `prepare.py` (read-only), `train.py` (editable).
4. Ensure `~/.cache/autoresearch/` exists or run `uv run prepare.py`.
5. Init `results.tsv` with header only.
6. Confirm device is `mps` and macOS env overrides are applied.

## Experimentation

Launch with `uv run train.py` (console injects `AR_*`).

**You MAY:**
- Edit `train.py`, or tune mainly via `AR_*` / console knobs.
- Scale **one axis at a time** once stable: depth → seq len → batch → time budget.

**You MAY NOT:**
- Edit `prepare.py`, add deps, or change `evaluate_bpb`.
- Jump straight to CUDA defaults (big depth, long context, `SSSL`, huge batches).

**Goal:** lowest `val_bpb` under configs that finish reliably on this Mac.  
**Memory:** unified memory is hard. OS kill ≈ crash — reduce batch / depth / seq first.

**First run:** baseline with macOS preset and unmodified `train.py`.

## Suggested Mac order

1. 60s smoke baseline (macOS preset)
2. Scalar LR tweaks (e.g. `AR_MATRIX_LR`)
3. Slightly larger `AR_TOTAL_BATCH_SIZE` or `AR_DEVICE_BATCH_SIZE`
4. Then `AR_DEPTH` or `AR_MAX_SEQ_LEN` (one change each)
5. Only after 120s/300s budgets are stable, try costlier patterns

## Logging

Prefer `device`, `val_bpb`, `training_seconds`, `num_params_M`, `num_steps`.

```
grep "^val_bpb:\|^peak_vram_mb:\|^device:" run.log
```

TSV columns unchanged. On MPS you may log `memory_gb=0.0` and note `mps` + key `AR_*` in the description.

## Loop

Same forever loop: idea → commit → train → read metric → tsv → keep or discard.

**Timeout:** 60s smoke should finish in ~2 minutes; kill if hung. For 300s runs, kill after 10 minutes.

**NEVER STOP** after setup until the human interrupts. When stuck, return to the `MACOS_TESTING.md` preset and try smaller changes.
