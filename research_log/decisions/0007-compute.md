# 0007: Compute

**Status:** Accepted, 2026-11-20

**Context.** The code is pure Python on the CPU; GPUs give no speed-up. Speed comes from
running missions in parallel processes. A local check: one 24-robot mission with all
failure modes and methods takes ~2 s of CPU.

**Probe (2026-11-20, 39 of 57 hosts reachable).** Most cores: `vanilla` and `cream`
(48 threads, Xeon Silver 4214R, ~360/270 GB free); `vanilla` had load 2 and `cream` load 8.
Fastest single-thread: the `-l` lab 1.05 machines (i9-12900K, 24 threads).

**Decision.** Run on `vanilla` with `--jobs 40`, leaving headroom for other users.
Report CPU time (`cpu_s`, per process) as runtime, because wall time is affected by the
other processes running in parallel.
