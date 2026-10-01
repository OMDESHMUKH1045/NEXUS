---
name: data-engineering
description: Use when designing or implementing NEXUS dataset ingestion, typed table boundaries, bounded analytical state, or deterministic data processing.
---

# NEXUS Data Engineering

Design dataset and analytical data flows so source meaning is preserved,
memory remains bounded, and repeated runs produce the same result.

## When to Apply

Use this skill for:

- source readers and dataset adapters;
- schema, type, null, and missing-value handling;
- streaming, chunked, grouped, or materialized analytical processing;
- analytical result contracts and bounded output;
- changes crossing the Phase 3 dataset and Phase 4 analysis boundaries.

## Core Rules

1. Keep raw source values, typed analysis values, schemas, and operations as
   separate concepts with explicit adapters between them.
2. Define an explicit schema before analytical operations consume values.
   Operations must not independently infer or coerce types.
3. Preserve source semantics. `None` remains missing, booleans remain distinct
   from numbers, and native SQLite numeric values remain numeric.
4. Choose and document deterministic CSV/JSONL typing rules. Numeric-looking
   text must not become numeric through operation-specific guessing.
5. Handle non-finite numeric values explicitly. Reject, mark unavailable, or
   exclude them according to the documented contract; never silently convert
   them to ordinary numbers.
6. Prefer streaming and one-pass state. Any materialized values, rank pairs,
   groups, caches, samples, or returned rows require an explicit bound.
7. If an exact operation cannot satisfy its bound, fail with a typed,
   visible limit error. Never silently approximate, evict, truncate, or merge
   state unless truncation/approximation is part of the result contract.
8. Keep group state and output state bounded. Deterministic canonical ordering
   must not depend on input order or Python ordering of heterogeneous values.
9. Keep source access read-only unless a future feature explicitly requires
   writes and records that architectural decision. Close readers on success,
   failure, and cancellation.
10. Prefer the standard library and existing Phase 3 readers. Do not add
    pandas, NumPy, Polars, SciPy, DuckDB, PyArrow, or another dataframe
    framework without explicit architectural approval and measured need.

## Phase 3/4 Boundary

The intended boundary is:

```text
raw source -> Phase 3 reader -> typed AnalysisTable adapter
           -> ColumnSchema and typed values -> AnalysisOperation
```

The adapter owns source-specific behavior. Statistics, correlations,
outliers, and aggregation consume the typed table contract and must not
duplicate CSV, JSONL, SQLite, or inference logic.

## Required Review

Before implementation, identify the largest possible state structure, its
bound, its failure behavior, and whether the operation is streaming,
replayable, or requires exact materialization. Test empty, null, mixed-type,
malformed, limit, and repeated-run cases with small deterministic fixtures.

