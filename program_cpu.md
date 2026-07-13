# autoresearch (CPU)

This brief is for **CPU-only** machines. Without CUDA/MPS, throughput is tiny — use mini configs and optimize for “finishes and compares,” not GPU-paper numbers.

> In the console, apply the **CPU** preset first.

## Platform realities

- Device should be `cpu`.
- **Force small settings** (CPU preset; shrink further if needed):
  - `AR_MAX_SEQ_LEN=256`
  - `AR_DEPTH=2`
  - `AR_WINDOW_PATTERN=L`
  - `AR_DEVICE_BATCH_SIZE=2`
  - `AR_TOTAL_BATCH_SIZE=4096`
  - `AR_EVAL_TOKENS=65536`
  - `AR_TIME_BUDGET=30` (try 60 only after stability)
- Few `num_steps` per run is normal. Compare **relative** `val_bpb`, not against GPU baselines.
- `peak_vram_mb` is meaningless (usually 0).
- Prefer tiny hyperparameter edits over wide/deep/long-context architecture swings.

## Setup

1. Tag like `jul12-cpu`; create `autoresearch/<tag>`.
2. Read `README.md`, `prepare.py` (read-only), `train.py`.
3. Run `uv run prepare.py` if cache is empty.
4. Init `results.tsv`; confirm `cpu` + CPU preset overrides.

## Experimentation

**MAY:** edit `train.py` or `AR_*`; one tiny knob per experiment.  
**MAY NOT:** edit `prepare.py`, add deps, change eval, or use GPU/macOS medium/large presets.

**Goal:** finish within 30–60s and minimize `val_bpb`.  
**First run:** CPU-preset baseline, unmodified `train.py`.

## Suggested order

1. 30s baseline  
2. LR tweak  
3. Slightly larger batch or depth only if still fast  
4. If timeouts dominate: cut depth / seq / eval tokens again

## Loop

```
grep "^val_bpb:\|^device:\|^num_steps:" run.log
```

Same keep/discard loop. Kill hung 30s runs after ~3 minutes ( ~5 minutes for 60s). Never stop after setup until interrupted.
