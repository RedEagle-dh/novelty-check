Continuous-integration jobs on a cluster of Raspberry Pi boards slow down when boards overheat
and throttle. My idea: collect kernel-level traces with eBPF on each board (scheduler events,
frequency changes, per-process CPU load), train a small model that predicts throttling a minute
before it happens, and move or delay queued CI jobs to cooler boards so the whole test suite
finishes sooner and with fewer flaky timeouts.
