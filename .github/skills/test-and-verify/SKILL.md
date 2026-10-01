---
name: test-and-verify
description: Use when validating NEXUS changes, numerical semantics, resource bounds, regressions, or phase verification gates.
---

# NEXUS Test and Verify

Treat tests and verification as evidence for a defined contract, not as a
substitute for understanding the behavior being implemented.

## When to Apply

Use this skill for:

- new analytical operations and typed interfaces;
- numerical correctness and deterministic result contracts;
- changes to bounded readers, limits, cleanup, or source safety;
- phase completion and checkpoint verification.

## Verification Rules

1. Read the relevant architecture and existing contracts before writing tests.
   Preserve all earlier-phase tests unless a genuine defect is demonstrated.
2. Define the expected behavior first. Use trusted small fixtures with exact
   references where possible; use explicit `math.isclose` tolerances only
   where floating-point representation requires them.
3. Test deterministic repeated runs, input-order independence where promised,
   and stable serialization or ordering.
4. Cover empty, single-row, all-null, constant, mixed-type, malformed,
   insufficient-data, invalid-parameter, and boundary-limit cases.
5. Test both sides of every bound. Confirm that materialization, groups,
   output rows, samples, and retained state never exceed their configured
   limits. Exact operations must fail visibly when a bound is insufficient.
6. Test resource ownership on success and failure: readers close, SQLite
   sources remain unchanged, no temporary persistence appears, and no worker,
   process, queue, or background task is introduced unintentionally.
7. Distinguish expected environmental unavailability from programming
   failures. Do not make tests pass by broad exception swallowing or by
   weakening the intended contract.
8. Verify existing phase behavior with the smallest relevant regression suite,
   then run the full suite before declaring a checkpoint complete.
9. For user-facing commands or APIs, verify valid output, invalid input,
   bounded behavior, and a representative manual invocation.
10. Do not claim a performance improvement from a passing test. Performance
    claims require `measure-dont-guess`: comparable inputs, timing/resource
    measurements, output validation, and reported variability.

## Phase Gate

The minimum repository gate is:

```bash
python -m pytest -q
git diff --check
git status --short --branch
```

Add targeted manual API/CLI checks when the change exposes such a surface.
Inspect the final diff for unrelated files, source mutation, persistence,
unbounded state, hidden concurrency, and documentation that claims more than
was verified.

