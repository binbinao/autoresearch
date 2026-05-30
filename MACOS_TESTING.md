# macOS Testing Guide

This repository was originally tuned for a single NVIDIA GPU, but it can now be smoke-tested on Apple Silicon through the MPS backend. This guide is for bring-up and validation on Macs such as an M4 with 32 GB unified memory.

## Recommended Environment

- Apple Silicon Mac with MPS support enabled in PyTorch
- Python 3.10+
- `uv` for dependency management

Install dependencies:

```bash
uv sync
```

Prepare data and tokenizer once:

```bash
uv run prepare.py
```

## Quick Validation

Run the reduced setup check first:

```bash
AR_MAX_SEQ_LEN=512 \
AR_EVAL_TOKENS=262144 \
AR_TIME_BUDGET=60 \
AR_DEPTH=4 \
AR_WINDOW_PATTERN=L \
AR_DEVICE_BATCH_SIZE=8 \
AR_TOTAL_BATCH_SIZE=16384 \
uv run test_setup.py --quick
```

Expected result: all 4 checks pass and the reported device is `mps`.

## 60-Second Training Smoke Test

Use the same reduced configuration for an end-to-end run:

```bash
AR_MAX_SEQ_LEN=512 \
AR_EVAL_TOKENS=262144 \
AR_TIME_BUDGET=60 \
AR_DEPTH=4 \
AR_WINDOW_PATTERN=L \
AR_DEVICE_BATCH_SIZE=8 \
AR_TOTAL_BATCH_SIZE=16384 \
uv run train.py
```

On the validated M4 machine, this completed successfully with:

- `device: mps`
- `num_params_M: 11.5`
- `val_bpb: 1.905401`
- `training_seconds: 60.7`

## Why These Settings

- `AR_MAX_SEQ_LEN=512` reduces activation memory pressure.
- `AR_DEPTH=4` cuts model size enough for stable MPS testing.
- `AR_WINDOW_PATTERN=L` avoids the more expensive alternating window pattern.
- `AR_DEVICE_BATCH_SIZE=8` and `AR_TOTAL_BATCH_SIZE=16384` keep the run stable while preserving gradient accumulation.
- `AR_EVAL_TOKENS=262144` keeps validation short enough for iteration.

## Troubleshooting

- If you see memory pressure or process termination, lower `AR_DEVICE_BATCH_SIZE` to `4`.
- If setup passes but training fails, rerun with the exact environment variables above instead of repo defaults.
- If `uv` fails locally, verify the virtual environment and retry `uv sync`.
- For slower Macs, reduce `AR_TIME_BUDGET` to `30` for pure smoke tests.

## Notes

These settings are for validation, not for best research quality. Once the smoke test is stable, tune upward gradually by increasing `AR_DEPTH`, `AR_MAX_SEQ_LEN`, or `AR_TOTAL_BATCH_SIZE` one axis at a time.
