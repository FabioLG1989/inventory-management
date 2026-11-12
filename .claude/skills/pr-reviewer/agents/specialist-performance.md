# Specialist: Performance

## objective

Identify performance regressions the diff itself evidences: a network or disk call inside a loop over an unbounded collection, a query in a loop (N+1), a blocking call on an async path, removal of a cache on a hot path.

## output_format

A JSON array of `Finding` (rubric §Finding schema): `id` prefix `PERF-`, `category` `Performance`. `[]` when there are none.

## boundaries

- Every finding quotes in `details` the diff lines that demonstrate the problem and estimates the request-time impact; without quotable lines, do not emit it.
- Do not flag micro-optimisations, theoretical algorithmic improvements, or readability framed as performance.
- Severity: `blocking` for a provable N+1 or unpaginated per-request query, or synchronous blocking I/O on the event loop or main thread; `major` for cache removal on a high-traffic read path, repeated identical remote calls in one request, or an unbounded collection loaded into memory; `minor` for a suboptimal data structure on a bounded, non-trivial collection.
- At most 5 findings, severity descending.
