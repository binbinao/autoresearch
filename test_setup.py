#!/usr/bin/env python3
"""
Setup verification script for autoresearch.
Tests environment, tokenizer, dataloader, model creation, and a single training step.

Usage:
    uv run test_setup.py           # run all tests
    uv run test_setup.py --quick   # skip training step (faster)
"""

import os
import sys
import argparse
import time

import torch

sys.path.insert(0, os.path.dirname(__file__))


def detect_device():
    """Detect and return the best available device."""
    if torch.cuda.is_available():
        return torch.device("cuda")
    elif torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def test_environment():
    """Test basic environment and PyTorch setup."""
    print("=== Environment ===")
    print(f"  Python:  {sys.version.split()[0]}")
    print(f"  PyTorch: {torch.__version__}")
    print(f"  CUDA:    {torch.cuda.is_available()}")
    print(f"  MPS:     {torch.backends.mps.is_available()}")

    device = detect_device()
    print(f"  Device:  {device}")

    # Basic tensor smoke test
    t = torch.randn(2, 3, device=device)
    assert t.shape == (2, 3), "Tensor creation failed"
    print("  [PASS] tensor ops")
    return device


def test_tokenizer():
    """Test tokenizer loading and encode/decode roundtrip."""
    print("\n=== Tokenizer ===")
    from prepare import Tokenizer

    tokenizer = Tokenizer.from_directory()
    vocab_size = tokenizer.get_vocab_size()
    print(f"  Vocab size: {vocab_size}")

    text = "Hello world! Numbers: 123. Unicode: 你好"
    tokens = tokenizer.encode(text)
    decoded = tokenizer.decode(tokens)
    assert decoded == text, f"Roundtrip failed: {text!r} -> {decoded!r}"
    print(f"  [PASS] encode/decode roundtrip ({len(tokens)} tokens)")
    return tokenizer


def test_dataloader(tokenizer, device):
    """Test dataloader produces valid batches."""
    print("\n=== Dataloader ===")
    from prepare import make_dataloader

    B, T = 4, 128
    loader = make_dataloader(tokenizer, B, T, "train", device=device.type)
    x, y, epoch = next(loader)

    assert x.shape == (B, T), f"Unexpected input shape: {x.shape}"
    assert y.shape == (B, T), f"Unexpected target shape: {y.shape}"
    assert x.device.type == device.type
    print(f"  Shape: ({B}, {T}) on {device}")
    print(f"  Epoch: {epoch}")
    print("  [PASS] batch generation")
    return loader


def test_model(tokenizer, device):
    """Test model creation and forward pass."""
    print("\n=== Model ===")
    from train import GPT, GPTConfig

    vocab_size = tokenizer.get_vocab_size()
    config = GPTConfig(
        sequence_len=128,
        vocab_size=vocab_size,
        n_layer=2,
        n_head=2,
        n_kv_head=2,
        n_embd=128,
        window_pattern="L",
    )

    model = GPT(config)
    model.to(device)
    model.init_weights()

    num_params = sum(p.numel() for p in model.parameters())
    print(f"  Config: {config.n_layer} layers, {config.n_embd} dim")
    print(f"  Params: {num_params:,}")

    # Forward pass
    from prepare import make_dataloader

    loader = make_dataloader(tokenizer, 4, 128, "train", device=device.type)
    x, y, _ = next(loader)

    if torch.cuda.is_available():
        ctx = torch.amp.autocast(device_type="cuda", dtype=torch.bfloat16)
    elif torch.backends.mps.is_available():
        ctx = torch.amp.autocast(device_type="cpu", dtype=torch.bfloat16)
    else:
        ctx = torch.amp.autocast(device_type="cpu", dtype=torch.bfloat16)

    with torch.no_grad(), ctx:
        loss = model(x, y)

    print(f"  Forward loss: {loss.item():.4f}")
    print("  [PASS] forward pass")
    return model


def test_training_step(tokenizer, device):
    """Test a single optimizer step end-to-end."""
    print("\n=== Training Step ===")
    from train import GPT, GPTConfig
    from prepare import make_dataloader

    vocab_size = tokenizer.get_vocab_size()
    config = GPTConfig(
        sequence_len=128,
        vocab_size=vocab_size,
        n_layer=2,
        n_head=2,
        n_kv_head=2,
        n_embd=128,
        window_pattern="L",
    )

    model = GPT(config)
    model.to(device)
    model.init_weights()
    optimizer = model.setup_optimizer(
        unembedding_lr=0.004,
        embedding_lr=0.2,
        scalar_lr=0.5,
        matrix_lr=0.04,
        weight_decay=0.2,
    )

    loader = make_dataloader(tokenizer, 4, 128, "train", device=device.type)
    x, y, _ = next(loader)

    if torch.cuda.is_available():
        ctx = torch.amp.autocast(device_type="cuda", dtype=torch.bfloat16)
    elif torch.backends.mps.is_available():
        ctx = torch.amp.autocast(device_type="cpu", dtype=torch.bfloat16)
    else:
        ctx = torch.amp.autocast(device_type="cpu", dtype=torch.bfloat16)

    t0 = time.time()
    with ctx:
        loss = model(x, y)
    loss.backward()
    optimizer.step()
    model.zero_grad(set_to_none=True)
    dt = time.time() - t0

    print(f"  Loss: {loss.item():.4f}")
    print(f"  Time: {dt*1000:.0f}ms")
    print("  [PASS] training step")


def main():
    parser = argparse.ArgumentParser(description="Verify autoresearch setup")
    parser.add_argument("--quick", action="store_true", help="Skip training step test")
    args = parser.parse_args()

    passed = 0
    failed = 0

    try:
        device = test_environment()
        passed += 1
    except Exception as e:
        print(f"  [FAIL] {e}")
        failed += 1
        device = torch.device("cpu")

    try:
        tokenizer = test_tokenizer()
        passed += 1
    except Exception as e:
        print(f"  [FAIL] {e}")
        failed += 1
        tokenizer = None

    if tokenizer:
        try:
            test_dataloader(tokenizer, device)
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {e}")
            failed += 1

        try:
            test_model(tokenizer, device)
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {e}")
            failed += 1

        if not args.quick:
            try:
                test_training_step(tokenizer, device)
                passed += 1
            except Exception as e:
                print(f"  [FAIL] {e}")
                failed += 1

    print(f"\n{'='*40}")
    total = passed + failed
    if failed == 0:
        print(f"ALL {passed} TESTS PASSED. Ready to train.")
    else:
        print(f"{failed}/{total} tests FAILED.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
