# Canonical Script Structures

The exact k6 and Artillery templates the implementer agent starts from when generating scenario scripts (Phase 2 / [`agents/implementer.md`](../agents/implementer.md)).

## k6 (primary)

```javascript
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

const errorRate = new Rate('errors');

export const options = {
  stages: [
    { duration: '2m', target: 50 },
    { duration: '10m', target: 50 },
    { duration: '2m', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1000'],
    http_req_failed:   ['rate<0.01'],
    errors:            ['rate<0.01'],
  },
};

export default function () {
  const res = http.get(`${__ENV.BASE_URL}/api/products`);
  check(res, {
    'status is 200':             (r) => r.status === 200,
    'response time < 500ms':     (r) => r.timings.duration < 500,
  });
  errorRate.add(res.status !== 200);
  sleep(1);
}
```

Key conventions for all generated k6 scripts:
- Base URL from `__ENV.BASE_URL` — never hardcoded
- Auth token from `__ENV.AUTH_TOKEN` — set in Authorization header via `http.params`
- Custom `Rate` metric named `errors` for combined error tracking
- `sleep(1)` between iterations to simulate realistic think time (adjust per scenario; see [`scenario-profiles.md`](./scenario-profiles.md))
- `check()` assertions for both status code and response time per endpoint

## Artillery (fallback)

```yaml
config:
  target: "{{ $processEnvironment.BASE_URL }}"
  plugins:
    expect: {}
  phases:
    - duration: 120
      arrivalRate: 1
      rampTo: 50
      name: Ramp up
    - duration: 600
      arrivalRate: 50
      name: Sustained load
    - duration: 120
      arrivalRate: 50
      rampTo: 1
      name: Ramp down
  defaults:
    headers:
      Authorization: "Bearer {{ $processEnvironment.AUTH_TOKEN }}"
  ensure:
    p95: 500
    p99: 1000
    maxErrorRate: 1

scenarios:
  - name: Browse products
    flow:
      - get:
          url: "/api/products"
          expect:
            - statusCode: 200
            - maxResponseTime: 500
  - name: Get product detail
    flow:
      - get:
          url: "/api/products/{{ $randomInt(1, 100) }}"
          expect:
            - statusCode: 200
            - maxResponseTime: 500
```

Key conventions for all generated Artillery configs:
- `target` from `$processEnvironment.BASE_URL` — never hardcoded
- `plugins.expect: {}` is **required** — Artillery v2 only executes per-request `expect:` blocks (`statusCode`, `maxResponseTime`) when the `expect` plugin is declared; without it every `expect:` assertion is silently skipped. `ensure` is a separate, always-on top-level key and is unaffected.
- Auth from `$processEnvironment.AUTH_TOKEN` in `defaults.headers`
- `ensure` block mirrors the same p95/p99/errorRate thresholds as k6 defaults
- Ramp phases use `arrivalRate` + `rampTo`, not a constant rate or a zero-arrival phase — a phase with `arrivalRate: 0` produces no arrivals at all, not a ramp-down
- One `scenarios` entry per critical user journey from the test plan
