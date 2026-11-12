# OWASP Top 10 2021 — Quick Reference

Source: https://owasp.org/Top10/

## Contents

- [Category Index](#category-index) — A01–A10 codes, names, and OWASP links
- [Category Descriptions](#category-descriptions) — what each category covers
- [Skill Scope vs `/security-review`](#skill-scope-vs-security-review) — which categories this skill tests at runtime and which defer to static analysis

---

## Category Index

| Code | Name | OWASP Page |
|------|------|------------|
| A01 | Broken Access Control | https://owasp.org/Top10/A01_2021-Broken_Access_Control/ |
| A02 | Cryptographic Failures | https://owasp.org/Top10/A02_2021-Cryptographic_Failures/ |
| A03 | Injection | https://owasp.org/Top10/A03_2021-Injection/ |
| A04 | Insecure Design | https://owasp.org/Top10/A04_2021-Insecure_Design/ |
| A05 | Security Misconfiguration | https://owasp.org/Top10/A05_2021-Security_Misconfiguration/ |
| A06 | Vulnerable and Outdated Components | https://owasp.org/Top10/A06_2021-Vulnerable_and_Outdated_Components/ |
| A07 | Identification and Authentication Failures | https://owasp.org/Top10/A07_2021-Identification_and_Authentication_Failures/ |
| A08 | Software and Data Integrity Failures | https://owasp.org/Top10/A08_2021-Software_and_Data_Integrity_Failures/ |
| A09 | Security Logging and Monitoring Failures | https://owasp.org/Top10/A09_2021-Security_Logging_and_Monitoring_Failures/ |
| A10 | Server-Side Request Forgery (SSRF) | https://owasp.org/Top10/A10_2021-Server-Side_Request_Forgery_%28SSRF%29/ |

---

## Category Descriptions

### A01 — Broken Access Control

Failures that allow users to act outside their intended permissions: IDOR, forced browsing to restricted resources, missing function-level authorization, privilege escalation, and CORS misconfiguration enabling cross-origin credential access. SSRF is a separate category in this edition — see A10.

Cheat sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html

### A02 — Cryptographic Failures

Sensitive data exposed due to missing or weak encryption: plaintext transmission of passwords or tokens, weak algorithms (MD5, SHA-1, DES), missing HTTPS enforcement, insecure cookie flags, and PII in URLs or response bodies.

Cheat sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html

### A03 — Injection

User-controlled data sent to an interpreter without proper sanitization: SQL injection, OS command injection, LDAP injection, XSS (stored, reflected, DOM), template injection, and NoSQL injection.

Cheat sheet: https://cheatsheetseries.owasp.org/cheatsheets/Injection_Prevention_Cheat_Sheet.html

### A04 — Insecure Design

Flaws in architecture and business logic that no amount of patching can fix: absent rate limiting, missing account lockout, client-side-only validation, workflow steps that can be skipped, and multi-application discount or quota abuse.

Cheat sheet: https://cheatsheetseries.owasp.org/cheatsheets/Threat_Modeling_Cheat_Sheet.html

### A05 — Security Misconfiguration

Default or insecure configuration: overly permissive CORS, missing security headers, verbose error messages revealing internals, debug mode in production, unnecessary HTTP methods enabled, and unpatched default credentials.

Cheat sheet: https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html

### A06 — Vulnerable and Outdated Components

Known CVEs in direct and transitive dependencies, outdated frameworks, end-of-life runtimes. Detected through dependency scanners (npm audit, pip-audit, govulncheck, osv-scanner).

**Deferred entirely to `/security-review`** — active runtime testing cannot enumerate dependency CVEs.

### A07 — Identification and Authentication Failures

Session fixation, tokens not invalidated on logout, missing brute-force protection, weak or missing MFA, JWT without expiry, concurrent session mismanagement, and password policy bypass.

Cheat sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html

### A08 — Software and Data Integrity Failures

Unsafe deserialization, missing Subresource Integrity on CDN assets, unsigned build artifacts, and CI/CD pipeline integrity gaps.

**Deferred entirely to `/security-review`** — requires source code and build artifact access.

### A09 — Security Logging and Monitoring Failures

Security-sensitive actions (login, delete, admin ops) not producing audit records; PII or credentials appearing in log output; log injection; absence of alerting on repeated failed authentication.

Cheat sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html

### A10 — Server-Side Request Forgery (SSRF)

User-supplied URLs processed by the server without allowlist validation, enabling internal network probing, cloud metadata access, local file reads via `file://` scheme, and open redirects via redirect parameters.

Cheat sheet: https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html

---

## Skill Scope vs `/security-review`

| Category | Covered by `/owasp-security-testing` | Defer to `/security-review` |
|----------|--------------------------------------|-----------------------------|
| A01 Broken Access Control | IDOR probes, forced browsing, auth bypass, privilege escalation, CORS header probes against running app | Static access control pattern review in source; unreachable route analysis |
| A02 Cryptographic Failures | Sensitive data in live responses, missing cookie flags, HTTP-to-HTTPS redirect behavior | Hardcoded keys, weak algorithm calls in source |
| A03 Injection | SQL/XSS/command injection probes via HTTP against running endpoints | Static data-flow tracing from input to sink |
| A04 Insecure Design | Rate limiting verification, workflow skip attempts, business logic abuse | Architectural review, threat modeling gaps |
| A05 Security Misconfiguration | Security headers on live responses, error message verbosity, HTTP method enumeration | IaC misconfig (Dockerfile, Terraform), framework default settings in source |
| A06 Vulnerable Components | Not applicable | Full scope: dependency audit, CVE scanning, reachability filtering |
| A07 Auth & Session Management | Session fixation, token post-logout reuse, brute-force threshold, expiry enforcement | Hardcoded credentials in source, JWT misconfiguration patterns |
| A08 Software & Data Integrity | Not applicable | Full scope: deserialization sinks, CI/CD integrity, SRI verification |
| A09 Logging & Monitoring | Audit log endpoint verification for sensitive operations; PII in error responses | Sensitive variable names passed to log calls in source |
| A10 SSRF | URL field probes (internal IP, cloud metadata, file scheme), open redirect verification | Static URL sink tracing in source |
