---
name: start-task
description: Enable parallel development by creating isolated git worktrees per task. Use when starting a new ticket while other work is in progress. Auto-detects ports, copies .claude config, and sets up environment isolation.
argument-hint: '[task-id] [branch-name]'
---

# Start Task (Multi-Task Parallel Development)

**Trigger**: `/start-task <task-id> <branch-name>`

**Purpose**: Enable working on multiple tasks simultaneously using git worktrees with automatic environment isolation.

**Success Criteria**:

- Creates isolated git worktree for the task
- Auto-detects and handles port conflicts (Docker/dev servers)
- Preserves project configuration from `/initialize-project`
- Enables parallel `/implement-ticket` execution
- Works across ALL project types (1000+ projects)

---

## What This Skill Does

This skill enables engineers to work on multiple tickets in parallel without:

- Stashing changes or committing WIP
- Stopping/restarting containers
- Port conflicts
- Context switching overhead
- Rebuilding dependencies

**Use Cases**:

- Work on PROJ-123 while PROJ-122 builds/tests
- Review teammate's PR without stashing current work
- Handle urgent hotfix while feature work continues
- Parallel AI implementations: `/implement-ticket` in multiple worktrees

**How It Works**:

1. Reads `.claude/CLAUDE.md` to understand project structure
2. Creates git worktree in `../<project-name>-tasks/<task-id>/`
3. Auto-detects ports from project config (docker-compose, package.json, etc.)
4. Assigns unique ports to avoid conflicts (slot-based system)
5. Copies/generates environment files with updated ports
6. Displays access URLs and next steps

---

## Prerequisites

**Required**:

- Project must have run `/initialize-project` (needs `.claude/CLAUDE.md`)
- Git repository

**Optional** (auto-detected):

- Docker Compose (will handle port isolation)
- Package.json scripts (will detect dev server ports)
- Environment files (will copy and update)

---

## Usage

### Basic Usage

```bash
/start-task PROJ-123
```

Creates worktree with auto-generated branch `task/PROJ-123`

### With Custom Branch

```bash
/start-task PROJ-123 feat/awesome-feature
```

### List Active Tasks

```bash
/list-tasks
```

### Switch to Task

```bash
/switch-task PROJ-123
```

### Remove Task

```bash
/end-task PROJ-123
```

---

## Implementation Steps

### Step 1: Validate Prerequisites

```bash
# Check if initialize-project has run
if [[ ! -f ".claude/CLAUDE.md" ]]; then
    echo "Error: Project not initialized. Run /initialize-project first."
    exit 1
fi

# Check if in git repository
if ! git rev-parse --git-dir &>/dev/null; then
    echo "Error: Not a git repository"
    exit 1
fi

# Check for jq (required for registry)
if ! command -v jq &>/dev/null; then
    echo "Error: jq is required. Install with: brew install jq (macOS) or apt-get install jq (Linux)"
    exit 1
fi
```

### Step 2: Load Project Configuration

Read `.claude/CLAUDE.md` to extract:

```python
import re

def load_project_config():
    """Extract project configuration from CLAUDE.md"""

    with open('.claude/CLAUDE.md', 'r') as f:
        content = f.read()

    config = {
        'project_name': extract_project_name(content),
        'has_docker': 'docker' in content.lower() or 'compose' in content.lower(),
        'ports': extract_ports(content),
        'env_files': extract_env_files(content),
        'dev_commands': extract_dev_commands(content),
    }

    return config

def extract_ports(content):
    """Extract port numbers from CLAUDE.md"""
    ports = []

    # Common patterns
    patterns = [
        r'localhost:(\d+)',
        r'port[:\s]+(\d+)',
        r'PORT=(\d+)',
        r':(\d{4,5})\b',  # 4-5 digit numbers (likely ports)
    ]

    for pattern in patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        ports.extend(int(p) for p in matches if 1000 <= int(p) <= 65535)

    return sorted(set(ports))

def extract_env_files(content):
    """Find environment file patterns"""
    patterns = [
        r'\.env(?:\.\w+)?',
        r'config/.*\.(?:yml|yaml|json)',
    ]

    env_files = []
    for pattern in patterns:
        matches = re.findall(pattern, content)
        env_files.extend(matches)

    return list(set(env_files))
```

### Step 3: Initialize Task Registry

Create `.worktree-registry.json` to track active tasks:

```json
{
  "project_name": "gira",
  "tasks": {
    "PROJ-123": {
      "path": "../gira-tasks/PROJ-123",
      "branch": "task/PROJ-123",
      "slot": 1,
      "created": "2026-03-02T10:30:00Z",
      "ports": {
        "backend": 3051,
        "frontend": 2713,
        "keycloak": 7081
      },
      "urls": ["http://localhost:3051", "http://localhost:2713"]
    }
  }
}
```

### Step 4: Assign Port Slot

```python
def get_next_available_slot(registry_path, max_slots=10):
    """Find next available slot (0-9)"""

    with open(registry_path, 'r') as f:
        registry = json.load(f)

    used_slots = {task['slot'] for task in registry['tasks'].values()}

    for slot in range(max_slots):
        if slot not in used_slots:
            return slot

    raise Exception(f"No available slots (max {max_slots} concurrent tasks)")

def assign_ports(base_ports, slot):
    """Assign unique ports based on slot"""
    return {
        name: port + slot
        for name, port in base_ports.items()
    }
```

### Step 5: Create Worktree

```bash
TASK_ID="$1"
BRANCH_NAME="${2:-task/$TASK_ID}"
PROJECT_NAME=$(basename "$(pwd)")
WORKTREE_PATH="../${PROJECT_NAME}-tasks/${TASK_ID}"

# Create worktree
mkdir -p "$(dirname "$WORKTREE_PATH")"

if git rev-parse --verify "$BRANCH_NAME" &>/dev/null; then
    echo "Branch '$BRANCH_NAME' exists, checking out..."
    git worktree add "$WORKTREE_PATH" "$BRANCH_NAME"
else
    echo "Creating new branch '$BRANCH_NAME'..."
    git worktree add -b "$BRANCH_NAME" "$WORKTREE_PATH"
fi
```

### Step 6: Setup Environment

**For Docker Projects**:

```python
def setup_docker_env(worktree_path, task_id, ports, slot):
    """Create docker-compose.override.yml with unique ports"""

    # Read original docker-compose.yml to understand services
    with open('docker-compose.yml', 'r') as f:
        compose_config = yaml.safe_load(f)

    # Generate override
    override = {
        'services': {}
    }

    for service_name, service_config in compose_config['services'].items():
        if 'ports' in service_config:
            override['services'][service_name] = {
                'container_name': f"{task_id}_{service_name}",
                'ports': remap_ports(service_config['ports'], slot)
            }

    # Write override file
    override_path = f"{worktree_path}/docker-compose.override.yml"
    with open(override_path, 'w') as f:
        yaml.dump(override, f)
        f.write(f"\n# Auto-generated for task: {task_id}\n")
        f.write(f"# DO NOT commit this file\n")

def remap_ports(port_list, slot):
    """Remap ports by adding slot offset"""
    new_ports = []

    for port_mapping in port_list:
        if isinstance(port_mapping, str):
            host, container = port_mapping.split(':')
            new_host = str(int(host) + slot)
            new_ports.append(f"{new_host}:{container}")
        else:
            new_ports.append(port_mapping)

    return new_ports
```

**For Non-Docker Projects**:

```python
def setup_env_files(worktree_path, env_files, port_mappings):
    """Copy and update environment files with new ports"""

    for env_file in env_files:
        if not os.path.exists(env_file):
            continue

        # Read original
        with open(env_file, 'r') as f:
            content = f.read()

        # Update ports
        for old_port, new_port in port_mappings.items():
            content = re.sub(
                rf'\b{old_port}\b',
                str(new_port),
                content
            )

        # Write to worktree
        dest_path = os.path.join(worktree_path, env_file)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)

        with open(dest_path, 'w') as f:
            f.write(content)
            f.write(f"\n# Auto-updated for task worktree\n")
```

### Step 7: Copy .claude Configuration

```bash
# Copy config directory to worktree
cp -r .claude "$WORKTREE_PATH/"

# This preserves:
# - CLAUDE.md (project knowledge)
# - skills/ (project-specific skills)
```

### Step 8: Register Task

```python
def register_task(task_id, worktree_path, branch, slot, ports, urls):
    """Add task to registry"""

    registry_path = '.worktree-registry.json'

    # Load or create registry
    if os.path.exists(registry_path):
        with open(registry_path, 'r') as f:
            registry = json.load(f)
    else:
        registry = {
            'project_name': os.path.basename(os.getcwd()),
            'tasks': {}
        }

    # Add task
    registry['tasks'][task_id] = {
        'path': worktree_path,
        'branch': branch,
        'slot': slot,
        'created': datetime.utcnow().isoformat() + 'Z',
        'ports': ports,
        'urls': urls
    }

    # Save
    with open(registry_path, 'w') as f:
        json.dump(registry, f, indent=2)
```

### Step 9: Display Summary

```bash
echo ""
echo "✅ Task worktree created: $TASK_ID"
echo ""
echo "📁 Location:"
echo "   $WORKTREE_PATH"
echo ""
echo "🌿 Branch:"
echo "   $BRANCH_NAME"
echo ""
echo "🔗 Access URLs:"
for url in "${URLS[@]}"; do
    echo "   $url"
done
echo ""
echo "📝 Next Steps:"
echo ""
echo "   1. Switch to worktree:"
echo "      cd $WORKTREE_PATH"
echo ""
echo "   2. Start development environment:"
echo "      make up  # (or your project's start command)"
echo ""
echo "   3. Implement the ticket with AI:"
echo "      /implement-ticket $TASK_ID"
echo ""
echo "💡 Pro Tips:"
echo "   • Your main worktree continues running unaffected"
echo "   • Use /list-tasks to see all active tasks"
echo "   • Use /switch-task <id> to jump between tasks"
echo "   • Use /end-task <id> when done"
echo ""
```

---

## Additional Commands

### /list-tasks

```bash
#!/usr/bin/env bash

if [[ ! -f ".worktree-registry.json" ]]; then
    echo "No active tasks"
    exit 0
fi

echo ""
echo "Active Tasks:"
echo ""

jq -r '.tasks | to_entries[] |
    "  🏷️  \(.key)\n" +
    "    Branch: \(.value.branch)\n" +
    "    Path:   \(.value.path)\n" +
    "    URLs:   \(.value.urls | join(", "))\n"
' .worktree-registry.json
```

### /switch-task

```bash
#!/usr/bin/env bash

TASK_ID="$1"

if [[ -z "$TASK_ID" ]]; then
    echo "Usage: /switch-task <task-id>"
    exit 1
fi

WORKTREE_PATH=$(jq -r --arg id "$TASK_ID" '.tasks[$id].path' .worktree-registry.json)

if [[ "$WORKTREE_PATH" == "null" ]]; then
    echo "Task not found: $TASK_ID"
    exit 1
fi

echo "cd $WORKTREE_PATH"
```

Usage: `eval $(/switch-task PROJ-123)`

### /end-task

```bash
#!/usr/bin/env bash

TASK_ID="$1"

if [[ -z "$TASK_ID" ]]; then
    echo "Usage: /end-task <task-id>"
    exit 1
fi

WORKTREE_PATH=$(jq -r --arg id "$TASK_ID" '.tasks[$id].path' .worktree-registry.json)

if [[ "$WORKTREE_PATH" == "null" ]]; then
    echo "Task not found: $TASK_ID"
    exit 1
fi

echo "⚠️  This will remove worktree and stop containers for: $TASK_ID"
read -p "Continue? (y/N): " -n 1 -r
echo

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled"
    exit 0
fi

# Stop containers if using Docker
if [[ -f "$WORKTREE_PATH/docker-compose.yml" ]]; then
    echo "Stopping containers..."
    (cd "$WORKTREE_PATH" && docker compose down 2>/dev/null || true)
fi

# Remove worktree
echo "Removing worktree..."
git worktree remove "$WORKTREE_PATH" --force

# Update registry
jq --arg id "$TASK_ID" 'del(.tasks[$id])' .worktree-registry.json > .worktree-registry.json.tmp
mv .worktree-registry.json.tmp .worktree-registry.json

echo "✅ Task removed: $TASK_ID"
```

---

## Integration with /implement-ticket

The `/implement-ticket` skill works seamlessly in worktrees because:

1. **Isolated git context**: Each worktree has its own working directory
2. **Preserved AI knowledge**: `.claude/` directory is copied to worktree
3. **Independent containers**: Docker containers don't conflict
4. **Parallel execution**: Can run `/implement-ticket` in multiple worktrees simultaneously

**Example Workflow**:

```bash
# Main directory: working on PROJ-122
/implement-ticket PROJ-122

# While PROJ-122 is building/testing, handle urgent bug
/start-task PROJ-123
eval $(/switch-task PROJ-123)
/implement-ticket PROJ-123

# Both run in parallel without conflicts!
```

---

## Error Recovery

### Port Already in Use

If auto-assigned port is taken:

```python
def find_available_port(base_port, max_attempts=10):
    """Find next available port if assigned port is taken"""

    for offset in range(max_attempts):
        port = base_port + offset

        if is_port_available(port):
            return port

    raise Exception(f"Could not find available port near {base_port}")

def is_port_available(port):
    """Check if port is available"""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('localhost', port))
            return True
        except OSError:
            return False
```

### Worktree Already Exists

```bash
if git worktree list | grep -q "$WORKTREE_PATH"; then
    echo "Error: Worktree already exists for task: $TASK_ID"
    echo "Use /switch-task $TASK_ID to access it"
    echo "Or /end-task $TASK_ID to remove it first"
    exit 1
fi
```

### No Project Instruction File Found

```bash
if [[ ! -f ".claude/CLAUDE.md" ]]; then
    echo "Error: Project not initialized"
    echo ""
    echo "Run /initialize-project first to analyze this project"
    echo "This creates .claude/CLAUDE.md with project knowledge needed for task isolation"
    exit 1
fi
```

---

## Best Practices

1. **Shared vs Isolated Databases**:
   - By default: Share DB/Redis across worktrees (faster, uses less memory)
   - For schema migrations: Create isolated DB per worktree

2. **Port Organization**:
   - Main project: Uses default ports (slot 0)
   - Worktrees: Use slot 1-9 (supports 10 concurrent tasks)

3. **Cleanup**:
   - Run `/end-task` when done to free up slots
   - Orphaned worktrees: `git worktree prune`

4. **Performance**:
   - node_modules/vendor: Shared via symlinks (not duplicated)
   - Build artifacts: Isolated per worktree
   - Docker volumes: Shared by default, isolated on demand

---

## Platform Support

**Supported**:

- ✅ macOS (primary development platform)
- ✅ Linux (Ubuntu, Debian, RHEL)
- ✅ Windows (WSL2 required)

**Requirements**:

- Git 2.25+ (worktree improvements)
- jq (JSON processing)
- Docker (optional, auto-detected)

---

## Example: Real-World Usage

### Scenario: Critical Bug During Feature Work

```bash
# Working on feature in main directory
/implement-ticket PROJ-100

# CI fails, need to fix PROJ-101 urgently
/start-task PROJ-101
eval $(/switch-task PROJ-101)

# Fix runs in parallel with PROJ-100
/implement-ticket PROJ-101

# When done, merge and cleanup
git push origin task/PROJ-101
/end-task PROJ-101

# Return to feature work
cd ../gira  # back to main directory
```

### Scenario: Code Review Without Stashing

```bash
# Feature work in progress (uncommitted changes)
/start-task review-teammate-pr

eval $(/switch-task review-teammate-pr)
git fetch origin
git checkout origin/teammate-branch

# Review, test, comment
# No stashing needed!

/end-task review-teammate-pr
```

---

## Success Metrics

- **Task Creation**: < 10 seconds for new worktree
- **Port Conflicts**: 0% (auto-detected and resolved)
- **AI Integration**: 100% compatible with /implement-ticket
- **Project Coverage**: Works with any project that has `.claude/CLAUDE.md`
- **Concurrent Limit**: 10 tasks simultaneously

---

## Future Enhancements

1. **Cloud Sync**: Sync worktree state across machines
2. **AI Auto-Switch**: Automatically switch to worktree when `/implement-ticket TASK-ID` is called
3. **Smart Cleanup**: Auto-remove worktrees for merged/closed tickets
4. **Resource Quotas**: Limit total Docker containers/memory per user
5. **Team Coordination**: Show which tasks teammates are working on

---

## References

- [Git Worktrees Documentation](https://git-scm.com/docs/git-worktree)
- [Working on Multiple Branches Simultaneously](https://www.datacamp.com/tutorial/git-worktree-tutorial)
- [Mastering Git Worktrees with Claude Code](https://medium.com/@dtunai/mastering-git-worktrees-with-claude-code-for-parallel-development-workflow-41dc91e645fe)
- [Git Worktrees and Docker Compose](https://www.oliverdavies.uk/daily/2022/08/12/git-worktrees-docker-compose)
