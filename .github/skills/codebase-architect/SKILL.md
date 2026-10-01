---
name: codebase-architect
description: Use when planning or changing NEXUS architecture, module boundaries, typed contracts, or cross-phase behavior.
---

# NEXUS Codebase Architecture

Maintain NEXUS as a small, layered, typed local application. Prefer a
coherent boundary over a broad framework or speculative extensibility.

## When to Apply

Use this skill before:

- introducing a subsystem or cross-module contract;
- changing ownership of data, resources, or lifecycle;
- adding adapters, backends, operations, or result models;
- planning a new phase or reviewing phase scope.

## Core Rules

1. Inspect ARCHITECTURE.md, the roadmap, decisions, existing modules, and
   tests before changing code. Treat Phase 0--3 contracts as stable unless a
   genuine dependency defect or explicitly approved architectural change is
   found.
2. Implement the smallest coherent slice. Keep module ownership explicit:
   dataset sources read and validate data, analysis operates on typed table
   contracts, observability reports system state, and later layers schedule,
   persist, expose, or render results.
3. Use typed records and protocols at subsystem boundaries. Adapters belong at
   boundaries; source-specific behavior must not leak into analytical
   operations.
4. Keep dependency direction one-way and visible. Do not create a shared god
   object, hidden global state, circular imports, or duplicate representations
   without documenting the conversion and reason.
5. Preserve resource ownership and lifecycle clarity. The component that opens
   a reader, sampler, file, or device owns its cleanup on success, failure,
   cancellation, and shutdown.
6. Prefer direct, standard-library solutions and existing helpers. Do not
   introduce a framework, plugin system, or dependency merely to generalize a
   future phase.
7. Record an ADR only when a decision changes a durable boundary, semantic
   contract, dependency policy, or lifecycle guarantee. Do not create ADRs for
   routine implementation details.
8. Preserve backward compatibility where practical. Existing CLI commands,
   observatory contracts, dataset readers, tests, and JSON fields must not
   change accidentally.
9. Keep analytical work CPU-only and synchronous until a later approved phase
   introduces execution infrastructure. Make exactness, bounds, errors, and
   cancellation points explicit rather than hiding them behind a framework.

## Phase Boundaries

Phase 4 analysis must not leak into scheduler behavior, pipeline DAG
execution, persistence, FastAPI, React, OpenCL, adaptive scheduling, or
background workers. Defer those concerns rather than adding placeholders or
premature integration hooks.

## Architecture Review

For every proposed boundary, state:

- owner and consumer;
- input and output types;
- validation and failure behavior;
- resource and lifecycle ownership;
- deterministic ordering and numerical semantics;
- what is deliberately deferred.

Reject changes that cannot answer those questions without relying on implicit
global behavior or future framework assumptions.
