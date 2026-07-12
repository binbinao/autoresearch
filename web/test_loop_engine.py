"""Smoke checks for loop engine helpers."""

from web.loop_engine import parse_metrics


def test_parse_metrics_ok():
    text = """
step 00010 ...
---
val_bpb:          0.997900
training_seconds: 300.1
total_seconds:    325.9
peak_vram_mb:     45060.2
mfu_percent:      39.80
total_tokens_M:   499.6
num_steps:        953
num_params_M:     50.3
depth:            8
device:           cuda
"""
    result = parse_metrics(text)
    assert not result.crashed
    assert abs(result.val_bpb - 0.9979) < 1e-6
    assert result.num_steps == 953
    assert result.device == "cuda"


def test_parse_metrics_crash():
    result = parse_metrics("Traceback (most recent call last):\nRuntimeError: boom\n")
    assert result.crashed
    assert result.val_bpb is None


if __name__ == "__main__":
    test_parse_metrics_ok()
    test_parse_metrics_crash()
    print("ok")
