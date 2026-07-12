"""Smoke checks for loop engine helpers."""

from web.loop_engine import parse_metrics, parse_progress_text, synthesize_demo_progress


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


def test_parse_progress_cr_log():
    text = (
        "\rstep 00000 (0.0%) | loss: 5.100000 | lrm: 1.00 | dt: 10ms | tok/sec: 1,000 | mfu: 10.0% | epoch: 0 | remaining: 300s"
        "\rstep 00001 (1.0%) | loss: 4.800000 | lrm: 1.00 | dt: 10ms | tok/sec: 1,100 | mfu: 11.0% | epoch: 0 | remaining: 290s"
        "\rstep 00002 (2.0%) | loss: 4.500000 | lrm: 1.00 | dt: 10ms | tok/sec: 1,200 | mfu: 12.0% | epoch: 0 | remaining: 280s"
    )
    points = parse_progress_text(text)
    assert len(points) == 3
    assert points[0]["step"] == 0
    assert abs(points[2]["loss"] - 4.5) < 1e-6
    assert points[2]["tok_per_sec"] == 1200


def test_demo_progress_converges():
    points = synthesize_demo_progress(20)
    assert len(points) == 20
    assert points[0]["loss"] > points[-1]["loss"]


if __name__ == "__main__":
    test_parse_metrics_ok()
    test_parse_metrics_crash()
    test_parse_progress_cr_log()
    test_demo_progress_converges()
    print("ok")
