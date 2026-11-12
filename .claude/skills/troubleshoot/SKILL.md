---
name: troubleshoot
description: Quick targeted debugging for a specific failure. Paste a CI run URL, error message, cloud alarm, failed deployment description, or exception — get root cause + copy-paste fix commands in under a minute. Use when /troubleshoot is invoked, a deployment fails, a pod crashes, an exception is thrown, or something just stopped working. Lighter and faster than /triage-incident — no report saved, no Confluence lookup, no full incident lifecycle.
argument-hint: "[paste error, failed CI URL, alarm, or describe what broke]"
disable-model-invocation: true
---

# /troubleshoot

**What broke:**
$ARGUMENTS

---

## Quick Start — Examples

> Paste any of the following directly after `/troubleshoot` — no flags needed.

**Failed GitHub Actions deployment:**
```
/troubleshoot https://github.com/my-org/my-repo/actions/runs/12345678
```

**Application exception:**
```
/troubleshoot Error: connect ECONNREFUSED 10.0.1.45:5432 at service payment-api in production
```

**Cloud alarm:**
```
/troubleshoot CloudWatch alarm CRITICAL: payment-api ECS CPU utilization 94% us-east-1
```

**EKS pod crash:**
```
/troubleshoot payment-api pods CrashLoopBackOff in production namespace on EKS, OOMKilled, last 20 min
```

**GKE pod crash:**
```
/troubleshoot payment-api pods CrashLoopBackOff in production namespace on GKE us-central1, OOMKilled
```

**AKS pod crash:**
```
/troubleshoot payment-api pods CrashLoopBackOff in production namespace on AKS eastus, OOMKilled
```

**Azure deployment failure:**
```
/troubleshoot Azure App Service payment-api deployment failed: container exited with code 137
```

**GCP Cloud Run error:**
```
/troubleshoot Cloud Run service payment-api revision failed: memory limit exceeded, us-central1
```

**CI step failure (paste the failed step log):**
```
/troubleshoot
npm ERR! code ENOENT
npm ERR! path /app/node_modules/.bin/vitest
npm ERR! errno -2
Build failed at step "Run tests"
```

---

## Prerequisites — MCP Setup

All MCPs are optional. `/troubleshoot` degrades gracefully — any unavailable MCP is skipped and noted in output. Codebase + `gh` CLI always run.

> Run `claude mcp list` to check what is already connected before setup.

---

### Datadog MCP (app-error route — logs, monitors, traces)

```bash
claude mcp add --transport http datadog-mcp \
  "https://mcp.datadoghq.com/api/unstable/mcp-server/mcp?toolsets=all" \
  -H "DD-API-KEY: your-api-key" \
  -H "DD-APPLICATION-KEY: your-app-key"
```

Keys: [API](https://app.datadoghq.com/organization-settings/api-keys) · [App](https://app.datadoghq.com/organization-settings/application-keys)

**OAuth (browser login):**
```bash
claude mcp add --transport http datadog-mcp \
  "https://mcp.datadoghq.com/api/unstable/mcp-server/mcp?toolsets=all"
```

**Regional endpoints:**
| Site | Endpoint |
|------|----------|
| `app.datadoghq.com` (US1) | `https://mcp.datadoghq.com/api/unstable/mcp-server/mcp` |
| `us3.datadoghq.com` (US3) | `https://mcp.us3.datadoghq.com/api/unstable/mcp-server/mcp` |
| `us5.datadoghq.com` (US5) | `https://mcp.us5.datadoghq.com/api/unstable/mcp-server/mcp` |
| `app.datadoghq.eu` (EU1) | `https://mcp.datadoghq.eu/api/unstable/mcp-server/mcp` |
| `ap1.datadoghq.com` (AP1) | `https://mcp.ap1.datadoghq.com/api/unstable/mcp-server/mcp` |

Append `--scope project` (team-shared via `.mcp.json`) or `--scope user` (global).

**Verify:** `claude mcp list` → `datadog-mcp: ✓ Connected`

---

### AWS MCP (cloud-error route — CloudWatch, ECS, RDS, Lambda)

**Step 0 — AWS Login:**
```bash
# SSO (most common in org setups)
aws sso login --profile your-profile-name

# Verify
aws sts get-caller-identity --profile your-profile-name
```

**Step 1 — Install uv:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Step 2 — Add AWS MCP servers:**
```bash
claude mcp add awslabs.core-mcp-server \
  -e AWS_PROFILE=your-profile-name \
  -e AWS_REGION=us-east-1 \
  -e FASTMCP_LOG_LEVEL=ERROR \
  -- uvx awslabs.core-mcp-server@latest

claude mcp add awslabs.cloudwatch-logs-mcp-server \
  -e AWS_PROFILE=your-profile-name \
  -e AWS_REGION=us-east-1 \
  -e FASTMCP_LOG_LEVEL=ERROR \
  -- uvx awslabs.cloudwatch-logs-mcp-server@latest
```

**Step 3 — Verify credentials:** `aws sts get-caller-identity --profile your-profile-name`

**Step 4 — Restart Claude Code.**

**Verify:** `claude mcp list` → `awslabs.core-mcp-server: ✓ Connected`

---

### EKS MCP (cloud-error route — EKS pods, nodes, events, container logs)

> Add this when the issue involves EKS workloads (pods crashing, OOMKilled, CrashLoopBackOff, node pressure).

**Step 1 — uv already installed from AWS MCP setup above.**

**Step 2 — Add EKS MCP server:**
```bash
claude mcp add eks-mcp-server \
  -e AWS_PROFILE=your-profile-name \
  -e AWS_REGION=us-east-1 \
  -e FASTMCP_LOG_LEVEL=ERROR \
  -- uvx awslabs.eks-mcp-server@latest \
     --allow-write \
     --allow-sensitive-data-access
```

> `--allow-sensitive-data-access` is required to read pod logs, container logs, and k8s events. Without it all those calls return an access error.

**Step 3 — Restart Claude Code.**

**Verify:** `claude mcp list` → `eks-mcp-server: ✓ Connected`

> EKS MCP gives direct pod/node/event access without requiring local `kubectl` configured.

---

**Troubleshooting — SSL error on old clusters (pre-2022)**

If you see `CERTIFICATE_VERIFY_FAILED: Missing Authority Key Identifier`, the cluster CA cert was generated before Python 3.10+ SSL strictness. Fix: generate a kubeconfig with `insecure-skip-tls-verify` and switch to kubeconfig auth mode.

```bash
# 1. Generate kubeconfig
aws eks update-kubeconfig \
  --name YOUR_CLUSTER \
  --region YOUR_REGION \
  --profile your-profile-name \
  --kubeconfig /tmp/YOUR_CLUSTER-kubeconfig.yaml

# 2. Patch out the CA cert and add insecure-skip-tls-verify
pip3 install pyyaml -q
python3 -c "
import yaml
with open('/tmp/YOUR_CLUSTER-kubeconfig.yaml') as f: kc = yaml.safe_load(f)
for c in kc['clusters']:
    c['cluster'].pop('certificate-authority-data', None)
    c['cluster']['insecure-skip-tls-verify'] = True
with open('/tmp/YOUR_CLUSTER-kubeconfig-insecure.yaml', 'w') as f: yaml.dump(kc, f)
print('Done')
"

# 3. Re-register MCP with kubeconfig auth mode
claude mcp remove eks-mcp-server
claude mcp add eks-mcp-server \
  -e AWS_PROFILE=your-profile-name \
  -e AWS_REGION=YOUR_REGION \
  -e FASTMCP_LOG_LEVEL=ERROR \
  -e KUBECONFIG=/tmp/YOUR_CLUSTER-kubeconfig-insecure.yaml \
  -- uvx awslabs.eks-mcp-server@latest \
     --allow-write \
     --allow-sensitive-data-access \
     --auth-mode kubeconfig
```

Restart Claude Code after step 3.

---

### Azure MCP (cloud-error route — Azure Monitor, AKS, App Service)

**Step 1 — Install Azure CLI and log in:**
```bash
brew install azure-cli   # macOS
az login
```

**Step 2 — Add Azure MCP:**
```bash
claude mcp add azure -- npx -y @azure/mcp@latest server start
```

**Step 3 — Restart Claude Code.**

**Verify:** `claude mcp list` → `azure: ✓ Connected`

> **AKS workloads:** Azure MCP provides cloud-level access but not direct Kubernetes API calls. For pod/node/event detail, local `kubectl` + kubeconfig are also required: `az aks get-credentials --resource-group RG --name CLUSTER`

---

### GCP MCP (cloud-error route — Cloud Monitoring, GKE, Cloud Run, Cloud Logging)

**Step 1 — Install Google Cloud CLI and authenticate:**
```bash
gcloud auth application-default login
gcloud config set project your-project-id
```

**Step 2 — Add GCP MCP:**
```bash
claude mcp add gcp-mcp -- npx -y @google-cloud/mcp@latest
```

**Step 3 — Restart Claude Code.**

**Verify:** `claude mcp list` → `gcp-mcp: ✓ Connected`

> **GKE workloads:** GCP MCP provides cloud-level access but not direct Kubernetes API calls. For pod/node/event detail, local `kubectl` + kubeconfig are also required: `gcloud container clusters get-credentials CLUSTER --region REGION`

---

### Degraded mode — what runs without MCP

| Missing | Route impacted | Fallback |
|---------|----------------|---------|
| Datadog | app-error | Codebase grep + git log only. Confidence MEDIUM or LOW. |
| AWS MCP | cloud-error (AWS) | No CloudWatch/ECS data. Codebase + git only. |
| EKS MCP | cloud-error (AWS/EKS) | Falls back to CloudWatch Logs for pod output. No direct pod/node/event access. |
| Azure MCP | cloud-error (Azure) | No Azure Monitor/AKS data. Codebase + git only. |
| GCP MCP | cloud-error (GCP) | No Cloud Monitoring/GKE data. Codebase + git only. |
| `gh` CLI | ci-failure | No CI log fetch. Check if `gh` is installed and authenticated. |
| All missing | All routes | Codebase grep + git log. Always produces output. |

---

You are a senior engineer performing targeted, fast debugging. You have access to Datadog, AWS, Azure, GCP via MCP and the project codebase. Begin immediately — do not ask clarifying questions before starting. Follow phases in order. Skip sub-phases whose MCP is not available. Time-box each MCP call to 20 seconds — if a call hangs or returns no results, note it and move on.

## Phase 1 — Classify and Route

Parse $ARGUMENTS and extract:

**Required:**
- `failure-type`: one of `ci-failure` | `cloud-error` | `app-error` | `unknown`
- `error-string`: exact error message or alarm name (copy verbatim, no paraphrasing)
- `service-name`: name of the affected service, function, or component (if determinable)
- `environment`: prod / staging / dev / unknown

**Optional (extract if present):**
- `cloud-provider`: aws / azure / gcp / unknown
- `k8s-platform`: eks / gke / aks / unknown (extract if k8s workload issue detected)
- `namespace`: Kubernetes namespace if mentioned
- `run-id`: GitHub Actions run ID or URL
- `trace-id`: Datadog/observability trace ID (format: 16-character hex or decimal)
- `commit-sha`: git SHA mentioned or implied
- `time-window`: lookback window mentioned (default: 30 minutes if not specified)
- `region`: cloud region (e.g. us-east-1, eastus, us-central1)

**Routing rules (apply first match):**
- Mentions GitHub Actions URL, `actions/runs/`, workflow name, CI step, "pipeline failed", "build failed" → `ci-failure`
- Mentions CloudWatch, ECS, Lambda, RDS, EKS, `aws` → `cloud-error` (provider=aws)
- Mentions Azure Monitor, AKS, App Service, Container Apps, `azure` → `cloud-error` (provider=azure)
- Mentions Cloud Monitoring, GKE, Cloud Run, Cloud Functions, `gcp` → `cloud-error` (provider=gcp)
- Mentions stack trace, HTTP 5xx, exception, `Error:`, service name + error string → `app-error`
- Cannot determine → `unknown` (treat as `app-error`)

**K8s platform detection (apply after routing, sets `k8s-platform`):**
- Mentions EKS, `eks`, `eksctl` → k8s-platform=eks (provider=aws)
- Mentions GKE, `gke`, `gcloud container` → k8s-platform=gke (provider=gcp)
- Mentions AKS, `aks`, `az aks` → k8s-platform=aks (provider=azure)
- Mentions `kubectl`, `CrashLoopBackOff`, `OOMKilled`, `pod`, `namespace`, `k8s`, `kubernetes` without explicit platform → check CLAUDE.md for platform hint; default k8s-platform=unknown
- If k8s-platform detected: Phase 2 uses dedicated k8s sub-phase (2d) in addition to cloud sub-phases

**Load minimal codebase context:**
1. Read `.claude/CLAUDE.md` if it exists — extract: service names, stack, infrastructure platform
2. If service-name is known: `grep -r "<service-name>" --include="*.json" --include="*.yml" --include="*.yaml" -l` to find config files
3. If error-string is known: `grep -r "<error-string>" --include="*.ts" --include="*.js" --include="*.py" --include="*.go" -l --max-count=1` to find code origin

State what was extracted and which route is active before moving to Phase 2.

---

## Phase 2 — Targeted Signal Pull

Execute **only** the sub-phases for the active route. Skip others entirely.

---

### Route: ci-failure

#### 2a. Fetch failed CI logs
If `run-id` was extracted or a GitHub URL was given:
```bash
gh run view <run-id> --log-failed
```

If no run ID, find the most recent failure:
```bash
gh run list --limit 5 --json databaseId,status,conclusion,workflowName,createdAt \
  --jq '.[] | select(.conclusion=="failure")'
```
Then fetch its logs:
```bash
gh run view <run-id> --log-failed
```

#### 2b. Identify what changed
```bash
# Recent commits
git log --oneline -10

# Files changed in the failing commit or last 3 commits
git diff HEAD~3..HEAD --name-only

# Most recently merged PRs
gh pr list --state merged --limit 3 --json number,title,mergedAt,files \
  --jq '.[] | {number, title, mergedAt, files: [.files[].path]}'
```

#### 2c. Check dependency/config files mentioned in failed step
Read any config file, lock file, or Dockerfile mentioned in the CI failure output.

---

### Route: cloud-error (aws)

#### 2a. Active alarms
List CloudWatch alarms in ALARM state for the affected service. Filter by service-name if known.

#### 2b. Recent logs (last 30 minutes)
Search CloudWatch Logs for the affected service log group. Filter by error-string from Phase 1. Return 10 most recent entries with timestamps.

#### 2c. Service status
Based on what the project uses (check CLAUDE.md):
- **ECS**: describe service — running count vs desired, recent task stop reasons and exit codes
- **Lambda**: recent error count and duration for the affected function (last 30 min)
- **RDS/Aurora**: connection count, CPU, freeable memory (last 30 min)

#### 2d. EKS workload status (if k8s-platform=eks)
If `awslabs.eks-mcp-server` is connected, use it directly. Otherwise fall back to CloudWatch Logs for container output.

**With EKS MCP (awslabs.eks-mcp-server):**
- List pods in affected namespace: `list_k8s_resources(cluster_name=CLUSTER, kind='Pod', api_version='v1', namespace=NAMESPACE)` — note status, restart count, age, node assignment
- Get pod events: `get_k8s_events(cluster_name=CLUSTER, kind='Pod', name=POD_NAME, namespace=NAMESPACE)`
- Fetch container logs for crashed/restarting pod (last 100 lines): `get_pod_logs(cluster_name=CLUSTER, namespace=NAMESPACE, pod_name=POD_NAME, previous=true, tail_lines=100)`
- Check node conditions: `list_k8s_resources(cluster_name=CLUSTER, kind='Node', api_version='v1')` — look for MemoryPressure, DiskPressure, PIDPressure in conditions
- Describe the deployment/statefulset for resource limits and image version: `list_k8s_resources(cluster_name=CLUSTER, kind='Deployment', api_version='apps/v1', namespace=NAMESPACE)`

**Without EKS MCP (fallback):**
- Search CloudWatch Container Insights logs for pod name or namespace
- Note: "EKS MCP not connected — pod-level detail unavailable. See Prerequisites to add awslabs.eks-mcp-server."

#### 2e. Recent infrastructure events
CloudTrail or EventBridge: any deployments, config changes, scaling events, or IAM changes in the last 2 hours for the affected service.

#### 2f. Git context
```bash
git log --oneline -10
git log -1 --stat
```

---

### Route: cloud-error (azure)

#### 2a. Active alerts
Azure Monitor: list active alerts for the affected resource group or service. Note severity and fired time.

#### 2b. Recent logs (last 30 minutes)
Log Analytics or Application Insights: query errors matching error-string from Phase 1. Return 10 most recent with timestamps.

#### 2c. Service status
Based on what the project uses (check CLAUDE.md):
- **App Service / Function App**: error count, response time, instance count (last 30 min)
- **Container Apps**: replica status, revision errors
- **Azure SQL / CosmosDB**: connection count, throttle events (last 30 min)

#### 2d. AKS workload status (if k8s-platform=aks)
Use Azure MCP (`azure` server) for AKS cluster access.

> **Note:** kubectl commands below require local kubectl and kubeconfig configured for the cluster (`az aks get-credentials --resource-group RG --name CLUSTER`). Azure MCP provides cloud-level resource access but not direct Kubernetes API calls.

- List pods in affected namespace — status, restart count, age
- Get pod events: `kubectl get events --namespace <namespace> --field-selector involvedObject.name=<pod-name> --sort-by='.lastTimestamp'`
- Fetch container logs for crashed/restarting pod (last 100 lines): `kubectl logs <pod-name> -n <namespace> --previous --tail=100`
- Check node conditions: `kubectl describe node <node-name>` — MemoryPressure, DiskPressure, PIDPressure
- Describe deployment for resource limits and image version: `kubectl describe deployment <name> -n <namespace>`
- Check AKS node pool status via Azure MCP: node pool provisioning state, VM size, autoscaler status

If Azure MCP unavailable: note it and use Log Analytics for container logs as fallback.

#### 2e. Recent changes
Azure Activity Log: deployments, RBAC changes, resource health events in the last 2 hours.

#### 2f. Git context
```bash
git log --oneline -10
git log -1 --stat
```

---

### Route: cloud-error (gcp)

#### 2a. Active incidents
Cloud Monitoring: list active alerting policy violations for the affected service.

#### 2b. Recent logs (last 30 minutes)
Cloud Logging: query errors for the affected service matching error-string. Return 10 most recent with timestamps.

#### 2c. Service status
Based on what the project uses (check CLAUDE.md):
- **Cloud Run**: revision status, instance count, error rate (last 30 min)
- **Cloud Functions**: error count, duration metrics (last 30 min)
- **Cloud SQL / Spanner**: connection count, CPU, error rate (last 30 min)

#### 2d. GKE workload status (if k8s-platform=gke)
Use GCP MCP (`gcp-mcp` server) for GKE cluster access.

> **Note:** kubectl commands below require local kubectl and kubeconfig configured for the cluster (`gcloud container clusters get-credentials CLUSTER --region REGION`). GCP MCP provides cloud-level resource access but not direct Kubernetes API calls.

- List pods in affected namespace — status, restart count, age
- Get pod events: `kubectl get events --namespace <namespace> --field-selector involvedObject.name=<pod-name> --sort-by='.lastTimestamp'`
- Fetch container logs for crashed/restarting pod (last 100 lines): `kubectl logs <pod-name> -n <namespace> --previous --tail=100`
- Check node conditions: `kubectl describe node <node-name>` — MemoryPressure, DiskPressure, PIDPressure
- Describe deployment for resource limits and image version: `kubectl describe deployment <name> -n <namespace>`
- Check GKE node pool status via GCP MCP: node pool status, machine type, autoscaler config, any node upgrade events

If GCP MCP unavailable: use Cloud Logging `resource.type="k8s_container"` filter as fallback for container logs.

#### 2e. Recent changes
Cloud Audit Logs: deployments, IAM changes, config changes in the last 2 hours.

#### 2f. Git context
```bash
git log --oneline -10
git log -1 --stat
```

---

### Route: app-error

#### 2a. Datadog logs (if datadog-mcp available)
Search log stream for the exact error-string from Phase 1, within the last 30 minutes (or time-window if specified). Return 10 most recent entries with service, host, and timestamp.

#### 2b. Trace correlation (if datadog-mcp available and trace-id found)
If trace-id was extracted in Phase 1, pull the full trace:
- Fetch span tree for the trace ID
- Identify the root error span: operation name, error type, error message, duration
- Note calling service and downstream dependencies in the span tree

If no trace ID but error-string was found in logs:
- Pull the trace ID from the first matching log entry
- Fetch that trace

#### 2c. Active monitors (if datadog-mcp available)
Search for monitors in ALERT or WARN state for the affected service name. Note monitor name, metric, threshold.

#### 2d. Git context + recent deploy
```bash
# Recent commits
git log --oneline -10

# What changed in last commit (files + line summary)
git log -1 --stat

# If a deploy SHA or "after deploy" is mentioned in the description, diff it
git diff <deploy-sha>~1..<deploy-sha> --stat 2>/dev/null || true
```

#### 2e. Codebase — error origin and config
1. Grep for exact error-string to find origin file and line number
2. If found: read the surrounding function (±20 lines) for context
3. Find service config: connection pool size, timeout values, memory limits
4. Check infrastructure definition for the affected service (k8s manifest, ECS task def, Terraform resource)

---

### Route: unknown

Run all of the following in parallel:
- 2a from app-error route (Datadog logs)
- 2a from cloud-error route matching any available cloud MCP
- Git context: `git log --oneline -10` + `git log -1 --stat`
- Codebase grep for error-string

Note which sources returned data.

---

## Phase 3 — Quick Diagnosis and Actions

Combine all signals from Phase 2. Produce the following output inline — **do not save a file**.

State: one-line failure description, root cause, and three numbered copy-paste actions.

---

Output format (fill every field with real data from Phase 2):

```
🔍 Failure: [one sentence — what broke, where, when]
🎯 Root cause: [technical cause — config limit / code bug / bad deploy / infra sizing / cascading failure]

📍 Evidence:
  - [specific log line OR metric value OR alarm name OR commit SHA — from actual Phase 2 data]
  - [second evidence point if available]

⚡ Actions:

# 1. Verify — confirm still active
[exact runnable command]
# Expected: [what output confirms issue is active]
# If output shows normal: issue may have self-resolved — monitor for 5 min before continuing.

# 2. Fix / mitigate
[exact runnable command]
# What this does: [plain English — one sentence]
# Expected: [what output confirms it worked]

# 3. Confirm resolved
[exact runnable command]
# Expected: [what confirms recovery]

⏱️  Lookback: [time window used] | 📡 Sources: [list of MCPs used, or "codebase + git only"]
```

**Command requirements:**
- Every action must be a real, runnable command — no placeholders like `<your-service>` left unfilled if the value was found in Phase 1 or 2
- If a value could not be determined (e.g. region unknown), use a clearly marked placeholder: `YOUR_REGION` in ALL_CAPS
- Commands must match the detected stack (kubectl for k8s, aws CLI for AWS, az CLI for Azure, gcloud for GCP, gh for CI)

**After the actions block:**

Check these conditions:

1. If root cause is LOW confidence (could not determine from available data):
   ```
   ⚠️  Low confidence — missing data from: [list unavailable MCPs or data sources]
   Configure [MCP name] for richer signal. See Prerequisites above.
   ```

2. If multiple services are affected OR severity appears critical:
   ```
   ⚠️  This may be wider than one failure. Run /triage-incident for full incident analysis + runbook.
   ```

3. Always end with:
   ```
   ↩️  Paste the output of Step 1, a new error, or "it didn't work" to keep debugging.
   ```

---

## Rules

- Every command in the Actions block must use real values from Phase 1 and Phase 2 — no invented service names, metric names, or resource IDs
- If Phase 2 returned no data for a sub-phase (MCP not configured or no matching resources), state this in one line and continue — do not stop
- Do not save any file — output is always inline
- Do not perform rollbacks or destructive actions — output commands for the user to run, never execute them
- Trace-id extraction: look for 16+ character hex strings or `trace_id=`, `traceId:`, `x-datadog-trace-id:` patterns in the error input
- Do not invoke `/triage-incident` — only suggest it if conditions in Phase 3 are met
- If $ARGUMENTS is empty: ask the user to paste the error, failed CI URL, or alarm description — then wait
