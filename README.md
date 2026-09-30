# NEXUS

NEXUS is a local, CPU-first compute and data observatory.

## Phase 2 observability

The read-only observatory samples Linux `/proc` and `/sys` interfaces. It
collects CPU counter deltas, load, memory and swap, Linux PSI, thermal
sensors from thermal zones and hwmon `temp*_input` files,
`/proc/diskstats` counters, and bounded process snapshots. Missing interfaces
are represented as `None` or empty collections; they do not fabricate zero
values or stop other collectors.

Thermal and hwmon temperature inputs follow the Linux ABI millidegree-Celsius
unit. For hwmon channels, a valid `temp*_fault=1` or `temp*_enable=0` status
causes the channel to be omitted as unavailable. Missing status files do not
invalidate nonzero channels. A zero-degree hwmon reading is reported only
when the kernel explicitly establishes the channel as valid
(`temp*_fault=0` and `temp*_enable=1`); otherwise it is treated as an
ambiguous unavailable sentinel. This avoids reporting drivers that expose
unsupported channels as `0` without globally rejecting genuine zero readings.
Thermal-zone and hwmon records are kept separate because the available
interfaces do not provide a universally reliable cross-tree identity for
deduplication.

`nexus doctor` reports relatively stable runtime and capability diagnostics.
`nexus observe` runs a finite session:

```bash
PYTHONPATH=src python -m nexus observe --interval 1 --samples 5
```

Sampling intervals are bounded to 0.25--5 seconds, and in-memory history is
bounded by configuration. The sampler uses monotonic scheduling and does not
catch up by firing a backlog after a slow collection. NEXUS does not require
root and does not modify governors, clocks, fans, thermal settings, or kernel
configuration.

Phase 2 does not persist telemetry or perform workload execution. Linux
systems without PSI, thermal zones, cpufreq files, or readable process status
continue with those measurements unavailable.

Phase 2 was manually verified with the project test suite, `nexus doctor`, and
a five-sample observation session. Collector-overhead measurement is not yet
implemented; NEXUS makes no claim about observer overhead.
