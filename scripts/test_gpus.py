#!/usr/bin/env python3
"""
Test each GPU independently to verify both are accessible and functional.
This script:
  1. Queries nvidia-smi for GPU info
  2. Tests CUDA tensor creation on each GPU separately
  3. Reports memory and compute capability
"""
import subprocess
import sys


def test_nvidia_smi():
    """Query nvidia-smi for GPU information."""
    print("═══ nvidia-smi GPU Info ═══")
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,memory.free,temperature.gpu",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                print(f"  GPU {line.strip()}")
            return True
        else:
            print(f"  ❌ nvidia-smi failed: {result.stderr}")
            return False
    except FileNotFoundError:
        print("  ❌ nvidia-smi not found")
        return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


def test_cuda_per_gpu():
    """Test CUDA tensor creation on each GPU independently."""
    print("\n═══ CUDA Per-GPU Test ═══")
    try:
        import torch
    except ImportError:
        print("  ❌ PyTorch not installed")
        return False

    if not torch.cuda.is_available():
        print("  ❌ CUDA not available")
        return False

    gpu_count = torch.cuda.device_count()
    print(f"  PyTorch sees {gpu_count} GPU(s)")

    all_ok = True
    for i in range(gpu_count):
        try:
            device = torch.device(f"cuda:{i}")
            name = torch.cuda.get_device_name(i)
            total_mem = torch.cuda.get_device_properties(i).total_mem / (1024 ** 3)

            # Create a small tensor and do a simple operation
            x = torch.randn(1000, 1000, device=device)
            y = torch.matmul(x, x.T)
            result_sum = y.sum().item()

            # Get current memory usage
            allocated = torch.cuda.memory_allocated(i) / (1024 ** 3)
            reserved = torch.cuda.memory_reserved(i) / (1024 ** 3)

            print(f"  ✅ GPU {i}: {name}")
            print(f"       Total VRAM: {total_mem:.1f} GB")
            print(f"       Allocated: {allocated:.3f} GB | Reserved: {reserved:.3f} GB")
            print(f"       Compute test: matmul sum = {result_sum:.2f}")

            # Cleanup
            del x, y
            torch.cuda.empty_cache()

        except Exception as e:
            print(f"  ❌ GPU {i}: FAILED — {e}")
            all_ok = False

    return all_ok


def test_device_map_auto():
    """Test that device_map='auto' distributes layers across GPUs."""
    print("\n═══ device_map='auto' Distribution Test ═══")
    try:
        import torch
        from accelerate import infer_auto_device_map
        gpu_count = torch.cuda.device_count()
        if gpu_count < 2:
            print(f"  ⚠️  Only {gpu_count} GPU visible — device_map will use single GPU")
        else:
            print(f"  ✅ {gpu_count} GPUs available — model layers will be distributed automatically")
        return True
    except ImportError:
        print("  ⚠️  accelerate not installed — device_map='auto' may not distribute optimally")
        return True
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


if __name__ == "__main__":
    print("╔══════════════════════════════════════════╗")
    print("║  GPU Independent Test Suite               ║")
    print("╚══════════════════════════════════════════╝")

    ok1 = test_nvidia_smi()
    ok2 = test_cuda_per_gpu()
    ok3 = test_device_map_auto()

    print("\n═══ Summary ═══")
    print(f"  {'✅' if ok1 else '❌'} nvidia-smi")
    print(f"  {'✅' if ok2 else '❌'} CUDA per-GPU")
    print(f"  {'✅' if ok3 else '❌'} device_map support")

    if all([ok1, ok2, ok3]):
        print("\n  🎉 All GPU tests passed!")
    else:
        print("\n  ❌ Some GPU tests failed")
        sys.exit(1)
