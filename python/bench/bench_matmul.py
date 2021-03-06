import triton
import torch

# square benchmarks
nt = {False: "n", True: "t"}
square_confs = [
    triton.testing.Benchmark(
        x_names=["M", "N", "K"],
        x_vals=[512 * i for i in range(1, 16)],
        y_name="provider",
        y_vals=["torch", "triton", "cutlass"],
        y_lines=["Torch", "Triton", "CUTLASS"],
        ylabel="TFLOPS",
        loglog=False,
        plot_name=f"matmul-square-{nt[AT]}{nt[BT]}",
        args={"AT": AT, "BT": BT, "dtype": torch.float16},
    ) for AT in [False, True] for BT in [False, True]
]

@triton.testing.perf_report(square_confs)
def bench_op(M, N, K, AT, BT, dtype, provider, warmup=5, rep=20):
    import os

    a = torch.rand((K, M) if AT else (M, K), device="cuda", dtype=dtype)
    b = torch.rand((N, K) if BT else (K, N), device="cuda", dtype=dtype)
    if AT:
        a = a.t()
    if BT:
        b = b.t()
    num_flops = 2 * M * N * K
    if provider == "torch":
        torch_ms = triton.testing.do_bench(lambda: torch.matmul(a, b), warmup=warmup, rep=rep)
        torch_tflops = num_flops / torch_ms * 1e-9
        return torch_tflops
    if provider == "triton":
        triton_ms = triton.testing.do_bench(lambda: triton.ops.matmul(a, b), warmup=warmup, rep=rep)
        triton_tflops = num_flops / triton_ms * 1e-9
        return triton_tflops
    if provider == "cutlass" and "CUTLASS_PROFILER" in os.environ:
        import subprocess
        import tempfile
        import pandas as pd

        # run program specified by CUTLASS_PROFILER env variable
        layout_a = "column" if AT else "row"
        layout_b = "column" if BT else "row"
        # create temporary file name
        fd, fname = tempfile.mkstemp()
        # run program and gets its output
        cmd = [
            os.environ["CUTLASS_PROFILER"],
            f"--m={M}",
            f"--n={N}",
            f"--k={K}",
            f"--A=f16:{layout_a}",
            f"--B=f16:{layout_b}",
            "--C=f16:column",
            "--accum=f32",
            "--operation=gemm",
            "--verification-enabled=false",
            f"--warmup-iterations={warmup}",
            f"--profiling-iterations={rep}",
            f"--output={fname}",
            "--verbose=false",
        ]
        # run cmd
        subprocess.run(cmd, stdout=subprocess.PIPE)
        # read CSV output
        df_c = pd.read_csv(f"{fname}.gemm.csv")
        cutlass_tflops = max(df_c["GFLOPs"]) / 1e3
        return cutlass_tflops
    return None

if __name__ == "__main__":
    bench_op.run()
