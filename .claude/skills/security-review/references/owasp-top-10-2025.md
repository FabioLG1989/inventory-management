# OWASP Top 10 2025 — Reference Guide

This document maps each OWASP category to its scanner coverage and LLM adjudicator
responsibilities as used by the security-review skill.

---

## A01 — Broken Access Control + SSRF

Broken Access Control remains the top vulnerability category. It encompasses
missing authorization checks on routes and resources, insecure direct object
references (IDOR), privilege escalation, and Server-Side Request Forgery (SSRF),
which was promoted into this category for 2025 due to cloud-metadata exploitation
patterns. **Scanner role:** semgrep rules (`p/owasp-top-ten`) flag unprotected
route decorators and HTTP client calls with variable URLs. **LLM role (A01 agent):**
confirms whether an authorization guard is actually applied by reading the
surrounding router definition, which scanners cannot always resolve statically.

References: https://owasp.org/Top10/A01_2021-Broken_Access_Control/
OWASP SSRF Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html

---

## A02 — Cryptographic Failures

Covers weak algorithms (MD5, SHA-1, DES, RC4), missing encryption for data in
transit or at rest, hardcoded keys and IVs, and disabled TLS verification. For
2025, the category explicitly includes post-quantum migration risk for long-lived
secrets. **Scanner role:** semgrep and bandit detect weak algorithm invocations.
gitleaks/trufflehog detect hardcoded key material. **LLM role (A04-crypto agent):**
determines whether the weak algorithm is used in a security-sensitive context or
a non-security purpose (ETag, cache key) where the weakness is not exploitable.

References: https://owasp.org/Top10/A02_2021-Cryptographic_Failures/
Crypto Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html

---

## A03 — Injection

Encompasses SQL injection, OS command injection, LDAP injection, XSS, template
injection, NoSQL injection, and expression language injection. **Scanner role:**
bandit (Python), gosec (Go), eslint-plugin-security (JS/TS), and semgrep (`p/owasp-top-ten`)
cover the common injection sinks. **LLM role (A05-injection agent):** traces data flow
from user-controlled input to the dangerous sink within the file, determining
whether parameterization or sanitization is correctly applied — a task that
static analysis frequently gets wrong for dynamic languages.

References: https://owasp.org/Top10/A03_2021-Injection/
SQL Injection Prevention: https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html

---

## A04 — Insecure Design

Design flaws that cannot be fixed by a code patch alone: absent rate limiting,
missing account lockout, client-side-only validation, lack of threat modelling
controls. **Scanner role:** limited; semgrep can flag absence of rate-limit
middleware on specific frameworks. **LLM role (A06-insecure-design agent):**
checks for the presence of rate-limiting, lockout, and server-side validation
logic near the flagged location, then recommends architectural remediation steps.

References: https://owasp.org/Top10/A04_2021-Insecure_Design/
Threat Modeling: https://cheatsheetseries.owasp.org/cheatsheets/Threat_Modeling_Cheat_Sheet.html

---

## A05 — Security Misconfiguration

Insecure defaults, permissive CORS, debug mode enabled in production, exposed
stack traces, missing security headers, open cloud storage. **Scanner role:**
trivy (IaC misconfigurations), checkov (Terraform/k8s), semgrep (framework-level
defaults). **LLM role (A02-config agent):** determines whether debug flags are
properly conditioned on environment variables and whether security headers are
applied globally by middleware.

References: https://owasp.org/Top10/A05_2021-Security_Misconfiguration/
HTTP Security Headers: https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html

---

## A06 — Vulnerable and Outdated Components

Known CVEs in direct and transitive dependencies. **Scanner role:** osv-scanner
(cross-ecosystem), pip-audit (Python), npm audit (JS/TS), cargo-audit (Rust),
govulncheck (Go), bundle-audit (Ruby), OWASP dependency-check (Java). These are
the primary scanners; the LLM plays a secondary role. **LLM role (A03-supply-chain
agent):** determines whether the vulnerable code path in the dependency is actually
reachable from the application code, reducing false-positive noise on transitive
dependencies.

References: https://owasp.org/Top10/A06_2021-Vulnerable_and_Outdated_Components/
Dependency Management: https://cheatsheetseries.owasp.org/cheatsheets/Third_Party_Javascript_Management_Cheat_Sheet.html

---

## A07 — Identification and Authentication Failures

Hardcoded credentials, weak passwords, broken session management, missing MFA,
JWT without expiry. **Scanner role:** gitleaks and trufflehog detect hardcoded
credentials (verified mode for trufflehog). semgrep detects JWT without expiry
and session ID in URL. **LLM role (A07-authn agent):** distinguishes real
credentials from placeholders and test fixtures; verifies JWT and session handling
patterns in context.

References: https://owasp.org/Top10/A07_2021-Identification_and_Authentication_Failures/
Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html

---

## A08 — Software and Data Integrity Failures

Insecure deserialization, missing Subresource Integrity on CDN assets, CI/CD
pipeline integrity gaps (unsigned artifacts, unpinned actions). **Scanner role:**
semgrep detects unsafe deserialization sinks (pickle, yaml.load, ObjectInputStream).
trivy and checkov detect unsigned artifacts in IaC. **LLM roles:** A08-integrity
agent handles SRI and CI/CD checks; triage-deserialization agent handles
deserialization data-flow verification.

References: https://owasp.org/Top10/A08_2021-Software_and_Data_Integrity_Failures/
Deserialization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Deserialization_Cheat_Sheet.html

---

## A09 — Security Logging and Monitoring Failures

Sensitive data in logs, missing audit trails on security events, log injection.
**Scanner role:** bandit and semgrep can detect sensitive variable names in log
calls. **LLM role (A09-logging agent):** determines whether the logged variable
actually contains sensitive data and whether audit events are captured by middleware
rather than inline.

References: https://owasp.org/Top10/A09_2021-Security_Logging_and_Monitoring_Failures/
Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html

---

## A10 — Server-Side Request Forgery (SSRF) / Unhandled Exceptions

SSRF is covered under A01 for 2025. This slot covers unhandled or improperly
handled exceptions that leak internal state, create exploitable error conditions,
or allow DoS via null pointer dereferences on user-controlled input. **Scanner
role:** semgrep detects bare-except blocks and raw exception messages in HTTP
responses. **LLM role (A10-exceptions agent):** confirms whether internal error
details reach the client and whether the bare-except is intentional.

References: https://owasp.org/Top10/A10_2021-Server-Side_Request_Forgery_%28SSRF%29/
Error Handling: https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html

---

## Scanner Coverage Summary

| Scanner | Languages | OWASP Categories |
|---|---|---|
| gitleaks | all | A07 (hardcoded secrets) |
| trufflehog | all | A07 (verified secrets) |
| semgrep | all | A01–A10 (multi-rule) |
| bandit | Python | A03, A02, A07, A09 |
| eslint-plugin-security | JS/TS | A03, A01 |
| gosec | Go | A03, A02, A07 |
| brakeman | Ruby | A03, A01, A07 |
| psalm-security | PHP | A03, A01 |
| cppcheck | C/C++ | A03, A04 |
| flawfinder | C/C++ | A03, A02 |
| cargo-audit | Rust | A06 |
| pip-audit | Python | A06 |
| npm audit | JS/TS | A06 |
| govulncheck | Go | A06 |
| bundle-audit | Ruby | A06 |
| osv-scanner | all | A06 |
| trivy | IaC | A05, A06, A08 |
| checkov | IaC | A05, A08 |
