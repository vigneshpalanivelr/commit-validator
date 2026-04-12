# Container Management - Complete Guide

Comprehensive documentation for `manage_container.py` - MR Validator container management CLI.

---

## Table of Contents

- [Quick Reference](#quick-reference)
  - [Installation](#installation)
  - [Essential Commands](#essential-commands)
  - [Quick Start](#quick-start)
  - [Common Flags](#common-flags)
  - [Troubleshooting Quick Guide](#troubleshooting-quick-guide)
- [Command Decision Tree](#command-decision-tree)
- [Installation & Setup](#installation--setup)
  - [Prerequisites](#prerequisites)
  - [Install Dependencies](#install-dependencies)
  - [Verify Installation](#verify-installation)
- [Commands Reference](#commands-reference)
  - [config - Configuration Management](#config---configuration-management)
  - [build - Build Docker Images](#build---build-docker-images)
  - [start - Start Container](#start---start-container)
  - [stop - Stop Container](#stop---stop-container)
  - [restart - Restart Container](#restart---restart-container)
  - [logs - View Logs](#logs---view-logs)
  - [status - Container Status](#status---container-status)
  - [remove - Remove Container/Images](#remove---remove-containerimages)
  - [test - Test Webhooks](#test---test-webhooks)
- [Individual Command Examples](#individual-command-examples)
- [Command Workflows](#command-workflows)
  - [Command Flow Diagram](#command-flow-diagram)
  - [Command Combinations](#command-combinations)
  - [State Transitions](#state-transitions)
  - [Command Dependencies](#command-dependencies)
- [Combined Workflows](#combined-workflows)
- [Real-World Scenarios](#real-world-scenarios)
- [Automation Examples](#automation-examples)
- [Configuration Validation](#configuration-validation)
- [Monitoring & Logs](#monitoring--logs)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Advanced Usage](#advanced-usage)
- [Best Practices](#best-practices)
- [Exit Codes Reference](#exit-codes-reference)

---

## Quick Reference

### Installation

```bash
# Required dependencies
pip install python-dotenv docker

# Optional: Enhanced CLI output (recommended)
pip install rich==12.6.0
```

### Container Architecture

**Two Container Types:**

1. **Webhook Container** (`ratemymr-webhook-container`)
   - **Port:** 9912 (persistent, always exposed)
   - **Type:** Long-running service
   - **Purpose:** Receives GitLab webhooks, spawns validators
   - **Managed by:** `manage_container.py`

2. **Validator Container** (`ratemymr-validate-container`)
   - **Port:** None (ephemeral, uses host network)
   - **Type:** Short-lived, spawned per MR validation
   - **Purpose:** Performs actual code validation
   - **Managed by:** Webhook container (automatic)

### Essential Commands

| Command | Description |
|---------|-------------|
| `python manage_container.py config` | Validate configuration |
| `python manage_container.py build` | Build both Docker images |
| `python manage_container.py start` | Start webhook container (port 9912) |
| `python manage_container.py stop` | Stop webhook container |
| `python manage_container.py restart` | Restart webhook container |
| `python manage_container.py logs` | View webhook container logs |
| `python manage_container.py status` | Show webhook container status |
| `python manage_container.py test` | Test webhook endpoint (port 9912) |
| `python manage_container.py remove` | Remove containers/images |

### Quick Start

```bash
# 1. Setup
cp .env.example mrproper.env
vim mrproper.env  # Add GITLAB_ACCESS_TOKEN

# 2. Validate
python manage_container.py config

# 3. Deploy
python manage_container.py build
python manage_container.py start --yes

# 4. Verify
python manage_container.py status
python manage_container.py test
```

### Common Flags

| Flag | Description |
|------|-------------|
| `--yes` | Auto-confirm (no prompts) |
| `--quiet` | Minimal output |
| `--no-follow` | Don't follow logs |
| `--force` | Skip confirmation |
| `--force-remove` | Force remove running container |
| `--validator <name>` | Test specific validator |

### Troubleshooting Quick Guide

```bash
# Check config
python manage_container.py config

# Check status
python manage_container.py status

# View errors
python manage_container.py logs --no-follow | grep ERROR

# Test webhook
python manage_container.py test

# Full restart
python manage_container.py restart
```

---

## Command Decision Tree

```
Need to manage MR Validator?
│
├─ First time setup?
│  └─ config → build → start → status → test
│
├─ Container running?
│  │
│  ├─ NO → Why?
│  │  ├─ Never started → start --yes
│  │  ├─ Was stopped → start --yes
│  │  └─ Crashed → logs --no-follow (check errors) → restart
│  │
│  └─ YES → What do you need?
│     │
│     ├─ Check health → status
│     ├─ View activity → logs
│     ├─ Test functionality → test
│     ├─ Apply config changes → restart
│     ├─ Update code → build → restart
│     ├─ Debug issues → logs --no-follow | grep ERROR
│     └─ Stop it → stop
│
├─ Configuration issues?
│  └─ config (validate and review)
│
├─ Need to rebuild?
│  └─ build → restart
│
└─ Need to clean up?
   └─ remove (interactive) or remove --force
```

---

## Installation & Setup

### Prerequisites

- Python 3.6+
- Docker 20.10+
- pip (Python package manager)

### Install Dependencies

```bash
# Required dependencies
pip install python-dotenv docker

# Optional: Enhanced CLI output (recommended)
pip install rich==12.6.0
```

### Verify Installation

```bash
python manage_container.py --help
```

Expected output:
```
usage: manage_container.py [-h] [--version]
                          {config,build,start,stop,restart,logs,status,remove,test}
                          ...

MR Validator - Container Management Script
...
```

---

## Commands Reference

### config - Configuration Management

**Display and validate configuration from mrproper.env**

**Usage:**
```bash
# Full configuration review
python manage_container.py config

# Quiet mode (only show errors/warnings)
python manage_container.py config --quiet

# Validation only (no table output)
python manage_container.py config --validate-only

# Use custom env file
python manage_container.py config --env-file /path/to/custom.env
```

**Example output:**
```
Configuration Review
─────────────────────────────────────────────────────────
Setting                        Value
─────────────────────────────────────────────────────────
GitLab Access Token            glpat-abcd****
AI Mode                        BFA (JWT Auth)
BFA Host                       api-gateway.internal.com
API Timeout                    120s
Log Directory                  /home/docker/tmp/mr-validator-logs
Log Level                      INFO
Log Structure                  organized

Container Settings
─────────────────────────────────────────────────────────
Webhook Container              ratemymr-webhook-container
Webhook Image                  ratemymr-webhook-container
Validator Image                ratemymr-validate-container
Webhook Port                   9912 (persistent)
Validator Port                 N/A (ephemeral, no fixed port)

System Information
─────────────────────────────────────────────────────────
Disk Available                 25.3 GB / 100.0 GB (74.7% used)
mrproper.env Permissions       600

[OK] Configuration is valid
```

**Validation checks:**
- ✓ GITLAB_ACCESS_TOKEN present
- ✓ AI service configuration (BFA_HOST or AI_SERVICE_URL)
- ✓ Log level validity (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- ✓ API timeout range (30-300s recommended)
- ✓ Log directory writable
- ✓ Disk space availability (warns if <5GB)
- ✓ File permissions (warns if not 600/400)

---

### build - Build Docker Images

**Build both webhook server and checker images**

**Usage:**
```bash
python manage_container.py build
```

**What it does:**
1. Builds `ratemymr-validate-container` (validator - ephemeral containers)
2. Builds `ratemymr-webhook-container` (webhook server - port 9912)

**Example output:**
```
Building Docker images...

Building webhook server image: ratemymr-webhook-container
[OK] Built ratemymr-webhook-container

Building validator image: ratemymr-validate-container
[OK] Built ratemymr-validate-container

SUCCESS: All images built successfully!
```

**Image Details:**
- **ratemymr-webhook-container**: ~156MB, runs on port 9912
- **ratemymr-validate-container**: ~892MB, includes validation tools

---

### start - Start Container

**Start the webhook server container (creates if needed)**

**Usage:**
```bash
# Interactive mode (shows config, asks for confirmation)
python manage_container.py start

# Auto-confirm mode (no prompts)
python manage_container.py start --yes
```

**What it does:**
1. Validates mrproper.env exists
2. Loads and displays configuration
3. Runs validation checks
4. Shows errors/warnings
5. Asks for confirmation (unless --yes)
6. Starts or creates container

**Example output:**
```
Configuration Review
[... configuration tables ...]

Continue with this configuration? (y/N): y

Starting new container: ratemymr-webhook-container (port 9912)
[OK] Container started successfully!

Endpoint               URL
────────────────────────────────────────────────────────────────
Rate My MR             http://192.168.1.100:9912/mr-proper/rate-my-mr
Clang Format           http://192.168.1.100:9912/mr-proper/mrproper-clang-format
Message Check          http://192.168.1.100:9912/mr-proper/mrproper-message
Combined               http://192.168.1.100:9912/mr-proper/rate-my-mr+mrproper-message
```

---

### stop - Stop Container

**Stop the running webhook container**

**Usage:**
```bash
python manage_container.py stop
```

**Example output:**
```
Stopping container: ratemymr-webhook-container
[OK] Container stopped!
Shell equivalent: docker stop ratemymr-webhook-container
```

---

### restart - Restart Container

**Restart the webhook container**

**Usage:**
```bash
python manage_container.py restart
```

**What it does:**
1. Verifies container exists and is running
2. Stops container
3. Waits 2 seconds
4. Starts container again

**Use cases:**
- After modifying mrproper.env
- After updating environment variables
- When container is unresponsive

---

### logs - View Logs

**View webhook container logs (live or static)**

**Usage:**
```bash
# Follow logs in real-time (default)
python manage_container.py logs

# Show logs without following
python manage_container.py logs --no-follow
```

**Example output:**
```
Showing logs for: ratemymr-webhook-container
Press Ctrl+C to exit
Shell equivalent: docker logs -f ratemymr-webhook-container

=== MR Validator Webhook Server Starting ===
Docker connectivity verified
Starting webhook server on port 9912...
[2025-11-08 10:15:23] INFO - Server ready at http://0.0.0.0:9912
```

---

### status - Container Status

**Display container status, resource usage, and health**

**Usage:**
```bash
python manage_container.py status
```

**Example output:**
```
Container Status:

[OK] Container is RUNNING

Property          Value
────────────────────────────────────────────────────────
Container Name    ratemymr-webhook-container
Container ID      abc123def456
Status            running
Created           2025-11-08T10:15:23
Uptime            2d 5h 30m
Ports             9912/tcp -> 9912

Resource          Usage
────────────────────────────────────────────────────────
CPU               2.35%
Memory            156.2 MB / 16384.0 MB

[OK] No recent errors found
```

---

### remove - Remove Container/Images

**Remove webhook container and optionally images**

**Usage:**
```bash
# Interactive mode (prompts for what to remove)
python manage_container.py remove

# Force mode (skip confirmation)
python manage_container.py remove --force

# Force remove even if running
python manage_container.py remove --force-remove
```

**Interactive prompt:**
```
What would you like to remove?
1. Container only
2. Container and images
3. Cancel
Select option (1/2/3) [3]:
```

---

### test - Test Webhooks

**Send a test webhook to verify container is working**

**Usage:**
```bash
# Test rate-my-mr validator (default)
python manage_container.py test

# Test specific validator
python manage_container.py test --validator rate-my-mr
python manage_container.py test --validator mrproper-message
python manage_container.py test --validator mrproper-clang-format
```

**Example output:**
```
Testing rate-my-mr endpoint with sample payload...
Target: http://192.168.1.100:9912/mr-proper/rate-my-mr

[OK] Test webhook sent successfully!

Response status: 200

Check logs with: python manage_container.py logs
Check validator logs at: /home/docker/tmp/mr-validator-logs
```

---

## Individual Command Examples

### config Examples

**Example 1: Full configuration review**
```bash
python manage_container.py config
```

**Example 2: Quiet validation (errors/warnings only)**
```bash
python manage_container.py config --quiet
```

**Example 3: Validation only (exit code)**
```bash
python manage_container.py config --validate-only
echo "Exit code: $?"
```

**Example 4: Check configuration errors**
```bash
# Create invalid config
cat > test.env << EOF
GITLAB_ACCESS_TOKEN=
LOG_LEVEL=INVALID
API_TIMEOUT=abc
EOF

python manage_container.py config --env-file test.env
```
Output:
```
[X] ERRORS (must be fixed):
   - GITLAB_ACCESS_TOKEN is not set (required)
   - LOG_LEVEL 'INVALID' is invalid
   - API_TIMEOUT 'abc' is not a valid number
```

### build Examples

**Example 1: Build and verify**
```bash
python manage_container.py build && docker images | grep -E "webhook|checker"
```

**Example 2: Build with time tracking**
```bash
time python manage_container.py build
```

### start Examples

**Example 1: Interactive start**
```bash
python manage_container.py start
```

**Example 2: Non-interactive start**
```bash
python manage_container.py start --yes
```

**Example 3: Start and verify**
```bash
python manage_container.py start --yes && python manage_container.py status
```

**Example 4: Start and follow logs**
```bash
python manage_container.py start --yes && python manage_container.py logs
```

### logs Examples

**Example 1: Follow logs in real-time**
```bash
python manage_container.py logs
```

**Example 2: Show last 50 lines**
```bash
python manage_container.py logs --no-follow | tail -50
```

**Example 3: Search for errors**
```bash
python manage_container.py logs --no-follow | grep -i error
```

**Example 4: Filter by REQUEST_ID**
```bash
python manage_container.py logs --no-follow | grep "12345678"
```

**Example 5: Export logs to file**
```bash
python manage_container.py logs --no-follow > webhook-logs-$(date +%Y%m%d).txt
```

**Example 6: Follow logs and filter**
```bash
python manage_container.py logs | grep --line-buffered "ERROR\|WARNING"
```

### test Examples

**Example 1: Test default validator**
```bash
python manage_container.py test
```

**Example 2: Test all validators sequentially**
```bash
for validator in rate-my-mr mrproper-message mrproper-clang-format; do
  echo "Testing $validator..."
  python manage_container.py test --validator $validator
  sleep 2
done
```

**Example 3: Test and verify validator container spawned**
```bash
python manage_container.py test
sleep 2
docker ps -a | grep mr-checker | head -1
```

---

## Command Workflows

### Command Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     INITIAL SETUP                            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                  ┌───────────────────────┐
                  │   config (validate)   │
                  └───────────────────────┘
                              │
                              ▼
                  ┌───────────────────────┐
                  │   build (2 images)    │
                  └───────────────────────┘
                              │
                              ▼
                  ┌───────────────────────┐
                  │   start --yes         │
                  └───────────────────────┘
                              │
                              ▼
        ┌─────────────────────┴─────────────────────┐
        │                                             │
        ▼                                             ▼
┌───────────────┐                            ┌───────────────┐
│    status     │                            │     test      │
│  (verify OK)  │                            │ (smoke test)  │
└───────────────┘                            └───────────────┘

┌─────────────────────────────────────────────────────────────┐
│                  DAILY OPERATIONS                            │
└─────────────────────────────────────────────────────────────┘

    ┌───────────┐          ┌───────────┐          ┌───────────┐
    │  status   │ ────────▶│   logs    │ ────────▶│   test    │
    │ (health)  │          │ (monitor) │          │ (verify)  │
    └───────────┘          └───────────┘          └───────────┘

┌─────────────────────────────────────────────────────────────┐
│                CONFIGURATION UPDATES                         │
└─────────────────────────────────────────────────────────────┘

┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│ Edit .env    │ ────▶ │   config     │ ────▶ │   restart    │
│ vim mrproper │       │  (validate)  │       │ (apply new)  │
└──────────────┘       └──────────────┘       └──────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    CODE UPDATES                              │
└─────────────────────────────────────────────────────────────┘

┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│ Edit code    │ ────▶ │    build     │ ────▶ │   restart    │
│ vim server.py│       │ (rebuild img)│       │ (use new img)│
└──────────────┘       └──────────────┘       └──────────────┘
                                                      │
                                                      ▼
                                              ┌──────────────┐
                                              │     test     │
                                              │   (verify)   │
                                              └──────────────┘
```

### Command Combinations

**Pattern 1: Safe Deployment**
```bash
config → build → stop → start --yes → status → test
```
**When to use:** Production deployments, critical updates

**Pattern 2: Quick Update**
```bash
build → restart → test
```
**When to use:** Development, iterative changes

**Pattern 3: Health Check**
```bash
status → logs --no-follow → test
```
**When to use:** Daily monitoring, scheduled checks

**Pattern 4: Troubleshoot & Fix**
```bash
config → status → logs → restart → test
```
**When to use:** Container misbehaving, errors reported

**Pattern 5: Complete Rebuild**
```bash
stop → remove --force → build → start --yes → test
```
**When to use:** Major version changes, persistent issues

### State Transitions

```
   NOT EXIST ──start──▶ CREATING ──────▶ RUNNING
       ▲                                    │
       │                                    │
       │                              restart│
       │                                    │
       │                                    ▼
       │                                 RUNNING
       │                                    │
       │                                 stop│
       │                                    │
       │                                    ▼
       │                                 STOPPED
       │                                    │
       │                                start│
       │                                    │
       └────────remove──────────────────────┘
```

### Command Dependencies

```
┌──────────────────────────────────────────────────────────────┐
│  Commands That Don't Require Container                       │
├──────────────────────────────────────────────────────────────┤
│  • config  (reads mrproper.env)                              │
│  • build   (creates images)                                  │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│  Commands That Require Container Exists                      │
├──────────────────────────────────────────────────────────────┤
│  • start   (if already exists, just starts)                  │
│  • stop    (requires running container)                      │
│  • restart (requires container exists)                       │
│  • logs    (requires container exists)                       │
│  • status  (requires container exists)                       │
│  • remove  (requires container exists)                       │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│  Commands That Require Container Running                     │
├──────────────────────────────────────────────────────────────┤
│  • test    (webhook must be responding)                      │
│  • logs -f (best with running container)                     │
└──────────────────────────────────────────────────────────────┘
```

---

## Combined Workflows

### Workflow 1: First-Time Setup

```bash
# 1. Create configuration
cp .env.example mrproper.env
vim mrproper.env  # Edit: Add GITLAB_ACCESS_TOKEN and BFA_HOST

# 2. Validate configuration
python manage_container.py config

# 3. Build images
python manage_container.py build

# 4. Start container
python manage_container.py start --yes

# 5. Verify it's running
python manage_container.py status

# 6. Test webhook
python manage_container.py test

# 7. View logs
python manage_container.py logs
```

### Workflow 2: Daily Health Check

```bash
# Check status
python manage_container.py status

# Check for errors in last 100 lines
python manage_container.py logs --no-follow | tail -100 | grep -i error

# Test webhook endpoint
python manage_container.py test

# If issues found, restart
# python manage_container.py restart
```

### Workflow 3: Update Configuration

```bash
# 1. Stop container
python manage_container.py stop

# 2. Edit configuration
vim mrproper.env

# 3. Validate new config
python manage_container.py config

# 4. Start with new config
python manage_container.py start --yes

# 5. Verify
python manage_container.py status
python manage_container.py test
```

### Workflow 4: Rebuild and Redeploy

```bash
# 1. Stop and remove old container
python manage_container.py stop
python manage_container.py remove --force

# 2. Rebuild images
python manage_container.py build

# 3. Start fresh
python manage_container.py start --yes

# 4. Verify
python manage_container.py status
```

### Workflow 5: Troubleshooting

```bash
# 1. Check configuration
python manage_container.py config

# 2. Check container status
python manage_container.py status

# 3. Check recent logs for errors
python manage_container.py logs --no-follow | grep -E "ERROR|CRITICAL" | tail -20

# 4. Test webhook
python manage_container.py test

# 5. If container is stuck, force restart
python manage_container.py stop
sleep 2
python manage_container.py start --yes

# 6. Monitor logs
python manage_container.py logs
```

### Workflow 6: Complete Cleanup

```bash
# 1. Stop container
python manage_container.py stop

# 2. Remove container and images
python manage_container.py remove --force

# 3. Clean Docker system
docker system prune -a -f --volumes

# 4. Verify cleanup
docker ps -a | grep mrproper
docker images | grep -E "webhook|checker"
```

---

## Real-World Scenarios

### Scenario 1: Production Deployment

```bash
#!/bin/bash
# deploy-production.sh

set -e  # Exit on error

echo "=== Production Deployment ==="

# 1. Validate configuration
echo "Step 1: Validating configuration..."
python manage_container.py config --validate-only || {
  echo "ERROR: Configuration validation failed"
  exit 2
}

# 2. Build images
echo "Step 2: Building Docker images..."
python manage_container.py build || {
  echo "ERROR: Build failed"
  exit 3
}

# 3. Stop old container if running
echo "Step 3: Stopping old container..."
python manage_container.py stop || true

# 4. Start new container
echo "Step 4: Starting new container..."
python manage_container.py start --yes || {
  echo "ERROR: Failed to start container"
  exit 3
}

# 5. Wait for container to be ready
echo "Step 5: Waiting for container to be ready..."
sleep 5

# 6. Verify container is running
echo "Step 6: Verifying container status..."
python manage_container.py status || {
  echo "ERROR: Container is not healthy"
  exit 1
}

# 7. Run smoke test
echo "Step 7: Running smoke test..."
python manage_container.py test || {
  echo "WARNING: Smoke test failed, but container is running"
}

echo "=== Deployment Complete ==="
echo "Container is running on port 9912"
```

### Scenario 2: Automated Health Check (Cron Job)

```bash
#!/bin/bash
# healthcheck.sh - Run every 5 minutes via cron

LOG_FILE="/var/log/mr-validator-health.log"

{
  echo "=== Health Check: $(date) ==="

  # Check if container is running
  if python manage_container.py status > /dev/null 2>&1; then
    echo "OK: Container is running"

    # Check for recent errors
    ERROR_COUNT=$(python manage_container.py logs --no-follow | tail -100 | grep -c ERROR || echo 0)

    if [ "$ERROR_COUNT" -gt 10 ]; then
      echo "WARNING: Found $ERROR_COUNT errors in last 100 log lines"
      echo "Restarting container..."
      python manage_container.py restart

      # Send alert
      curl -X POST "https://alerts.example.com/webhook" \
        -d '{"message":"MR Validator restarted due to errors","errors":'$ERROR_COUNT'}'
    else
      echo "OK: Error count acceptable ($ERROR_COUNT)"
    fi
  else
    echo "CRITICAL: Container is not running"
    echo "Attempting to start..."

    if python manage_container.py start --yes; then
      echo "OK: Container started successfully"

      # Send alert
      curl -X POST "https://alerts.example.com/webhook" \
        -d '{"message":"MR Validator was down and has been restarted"}'
    else
      echo "CRITICAL: Failed to start container"

      # Send critical alert
      curl -X POST "https://alerts.example.com/webhook" \
        -d '{"message":"MR Validator is DOWN and failed to restart","severity":"critical"}'
    fi
  fi

  echo ""
} >> "$LOG_FILE" 2>&1
```

### Scenario 3: Backup Before Update

```bash
#!/bin/bash
# backup-and-update.sh

BACKUP_DIR="/backup/mr-validator/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# 1. Backup configuration
echo "Backing up configuration..."
cp mrproper.env "$BACKUP_DIR/mrproper.env"

# 2. Export current container config
echo "Backing up container..."
docker inspect ratemymr-webhook-container > "$BACKUP_DIR/container-config.json" || true

# 3. Backup logs
echo "Backing up recent logs..."
python manage_container.py logs --no-follow > "$BACKUP_DIR/logs.txt" || true

# 4. Update
echo "Updating..."
git pull
python manage_container.py build
python manage_container.py restart

# 5. Verify
if python manage_container.py status > /dev/null 2>&1; then
  echo "Update successful"
  echo "Backup stored in: $BACKUP_DIR"
else
  echo "Update failed! Rolling back..."
  cp "$BACKUP_DIR/mrproper.env" mrproper.env
  python manage_container.py restart
  exit 1
fi
```

---

## Automation Examples

### Example 1: Systemd Service

```ini
# /etc/systemd/system/mr-validator.service
[Unit]
Description=MR Validator Webhook Service
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/mr-validator
ExecStartPre=/usr/bin/python3 manage_container.py config --validate-only
ExecStart=/usr/bin/python3 manage_container.py start --yes
ExecStop=/usr/bin/python3 manage_container.py stop
ExecReload=/usr/bin/python3 manage_container.py restart

[Install]
WantedBy=multi-user.target
```

**Usage:**
```bash
sudo systemctl start mr-validator
sudo systemctl status mr-validator
sudo systemctl enable mr-validator  # Auto-start on boot
```

### Example 2: Makefile

```makefile
# Makefile for MR Validator

.PHONY: config build start stop restart logs status test clean deploy

config:
	python manage_container.py config

build:
	python manage_container.py build

start:
	python manage_container.py start --yes

stop:
	python manage_container.py stop

restart:
	python manage_container.py restart

logs:
	python manage_container.py logs

status:
	python manage_container.py status

test:
	python manage_container.py test

clean:
	python manage_container.py remove --force

deploy: config build start status test
	@echo "Deployment complete!"

redeploy: stop clean build start status test
	@echo "Redeployment complete!"
```

**Usage:**
```bash
make deploy      # Full deployment
make restart     # Quick restart
make test        # Run tests
make redeploy    # Clean rebuild
```

### Example 3: GitLab CI/CD

```yaml
# .gitlab-ci.yml

stages:
  - validate
  - build
  - deploy
  - test

variables:
  PYTHON_VERSION: "3.8"

validate_config:
  stage: validate
  image: python:${PYTHON_VERSION}
  before_script:
    - pip install python-dotenv docker
  script:
    - python manage_container.py config --validate-only
  only:
    - main
    - staging

build_images:
  stage: build
  image: python:${PYTHON_VERSION}
  services:
    - docker:dind
  before_script:
    - pip install python-dotenv docker
  script:
    - python manage_container.py build
  only:
    - main
    - staging

deploy_production:
  stage: deploy
  image: python:${PYTHON_VERSION}
  services:
    - docker:dind
  before_script:
    - pip install python-dotenv docker
  script:
    - python manage_container.py stop || true
    - python manage_container.py start --yes
    - python manage_container.py status
  environment:
    name: production
    url: http://validator.example.com:9912
  only:
    - main

smoke_test:
  stage: test
  image: python:${PYTHON_VERSION}
  before_script:
    - pip install python-dotenv docker requests
  script:
    - python manage_container.py test
    - python manage_container.py test --validator mrproper-message
  only:
    - main
    - staging
```

### Example 4: Docker Compose Integration

```yaml
# docker-compose.yml
version: '3.8'

services:
  webhook:
    image: ratemymr-webhook-container:latest
    container_name: ratemymr-webhook-container
    ports:
      - "9912:9912"
    env_file:
      - mrproper.env
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:rw
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9912/"]
      interval: 30s
      timeout: 10s
      retries: 3
```

**Wrapper script:**
```bash
#!/bin/bash
# manage-compose.sh

case "$1" in
  start)
    python manage_container.py build
    docker-compose up -d
    ;;
  stop)
    docker-compose down
    ;;
  restart)
    docker-compose restart
    ;;
  logs)
    docker-compose logs -f
    ;;
  status)
    docker-compose ps
    python manage_container.py status
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|logs|status}"
    exit 1
    ;;
esac
```

---

## Configuration Validation

### Validation Categories

#### Required Fields
- `GITLAB_ACCESS_TOKEN` - Must be present

#### AI/LLM Service
- `BFA_HOST` or `AI_SERVICE_URL` - At least one required
- Warning if both set (BFA_HOST takes precedence)
- URL format validation

#### Logging Configuration
- `LOG_LEVEL` - Must be valid level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `LOG_DIR` - Must be writable (if exists)

#### System Resources
- Disk space check (warns if <5GB, critical if <1GB)
- File permissions check (warns if not 600/400)

### Validation Messages

**Errors (must fix):**
```
[X] ERRORS (must be fixed):
   - GITLAB_ACCESS_TOKEN is not set (required)
   - LOG_LEVEL 'TRACE' is invalid (must be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL)
   - API_TIMEOUT 'abc' is not a valid number
```

**Warnings (should review):**
```
!  WARNINGS:
   - Neither BFA_HOST nor AI_SERVICE_URL is set - AI features will not work
   - Disk space is getting low: 4.2 GB available
   - mrproper.env has insecure permissions (644), consider setting to 600 or 400
   - API_TIMEOUT is very high (>300s), consider reducing it
```

---

## Monitoring & Logs

### Real-time Log Monitoring

```bash
# Follow all logs
python manage_container.py logs

# Filter for errors
python manage_container.py logs | grep -i error

# Filter for specific REQUEST_ID
python manage_container.py logs | grep "12345678"
```

### Log Analysis

```bash
# Show last 50 lines
python manage_container.py logs --no-follow | tail -50

# Search for MR IID
python manage_container.py logs --no-follow | grep "MR IID: 42"

# Count error lines
python manage_container.py logs --no-follow | grep -c ERROR

# Export logs to file
python manage_container.py logs --no-follow > webhook-logs.txt
```

### Resource Monitoring

```bash
# Check CPU/Memory usage
python manage_container.py status

# Watch resource usage continuously
watch -n 5 "python manage_container.py status"
```

---

## Testing

### Test Webhook Endpoints

```bash
# Test default validator
python manage_container.py test

# Test all validators
python manage_container.py test --validator rate-my-mr
python manage_container.py test --validator mrproper-message
python manage_container.py test --validator mrproper-clang-format
```

### Manual Testing with curl

```bash
# Test webhook endpoint directly
curl -X POST http://localhost:9912/mr-proper/rate-my-mr \
  -H "Content-Type: application/json" \
  -H "X-Gitlab-Event: Merge Request Hook" \
  -d '{
    "object_kind": "merge_request",
    "user": {"username": "test"},
    "project": {"path_with_namespace": "org/repo"},
    "object_attributes": {"iid": 1, "title": "Test MR"},
    "changes": {}
  }'
```

### Verify Validator Execution

```bash
# After sending test webhook
docker ps -a | grep mr-rate-my-mr

# Check validator logs
LOG_DIR=/home/docker/tmp/mr-validator-logs
ls -lh $LOG_DIR/validations/$(date +%Y-%m-%d)/*/mr-*/
```

---

## Troubleshooting

### Common Issues

#### 1. Configuration Errors

**Problem:** `GITLAB_ACCESS_TOKEN is not set`

**Solution:**
```bash
# Edit mrproper.env
echo "GITLAB_ACCESS_TOKEN=glpat-your-token-here" >> mrproper.env

# Validate
python manage_container.py config
```

#### 2. Container Won't Start

**Problem:** `Image 'ratemymr-webhook-container:latest' not found`

**Solution:**
```bash
# Build images first
python manage_container.py build

# Then start
python manage_container.py start
```

#### 3. Port Already in Use

**Problem:** `port is already allocated`

**Solution:**
```bash
# Find what's using port 9912
docker ps | grep 9912

# Stop conflicting container
docker stop <container-id>
```

#### 4. Permission Denied

**Problem:** `permission denied while trying to connect to Docker daemon`

**Solution:**
```bash
# Add user to docker group
sudo usermod -aG docker $USER

# Re-login for changes to take effect
newgrp docker
```

#### 5. Disk Space Low

**Problem:** Warning: `Disk space is getting low: 2.3 GB available`

**Solution:**
```bash
# Clean up old Docker images
docker image prune -a

# Clean up old containers
docker container prune

# Clean up old logs
find /home/docker/tmp/mr-validator-logs -mtime +30 -delete
```

### Debugging Workflow

```bash
# 1. Validate configuration
python manage_container.py config

# 2. Check container status
python manage_container.py status

# 3. Check recent logs
python manage_container.py logs --no-follow | tail -50

# 4. Test webhook
python manage_container.py test

# 5. Check spawned validators
docker ps -a | grep mr-checker

# 6. If all else fails, restart
python manage_container.py restart
```

### Error Handling Matrix

| Error Scenario | Detection Command | Resolution Command |
|----------------|-------------------|-------------------|
| Config invalid | `config` | Edit `mrproper.env` → `config` |
| Image not found | `start` | `build` → `start --yes` |
| Container stopped | `status` | `start --yes` |
| Container crashed | `status` | `logs --no-follow` → `restart` |
| Port in use | `start` | `stop` → `start --yes` |
| High memory usage | `status` | `restart` |
| Webhook failing | `test` | `logs` → `restart` |
| Container stuck | `status` | `stop` → `remove --force` → `start --yes` |

---

## Advanced Usage

### Custom Environment File

```bash
# Use different env file for config validation
python manage_container.py config --env-file /path/to/custom.env

# Note: start always uses mrproper.env
```

### Scripting/Automation

```bash
#!/bin/bash
# deploy.sh - Automated deployment script

# Validate config
python manage_container.py config --validate-only || exit 1

# Build images
python manage_container.py build || exit 1

# Start container (auto-confirm)
python manage_container.py start --yes || exit 1

# Verify it's running
python manage_container.py status || exit 1

echo "Deployment complete!"
```

### CI/CD Integration

```yaml
# .gitlab-ci.yml example
deploy:
  stage: deploy
  script:
    - pip install python-dotenv docker
    - python manage_container.py config --validate-only
    - python manage_container.py build
    - python manage_container.py start --yes
  only:
    - main
```

### Monitoring Integration

```bash
#!/bin/bash
# healthcheck.sh - Cron job for monitoring

# Check container status
if ! python manage_container.py status > /dev/null 2>&1; then
  echo "Container is down, restarting..."
  python manage_container.py start --yes

  # Send alert
  curl -X POST https://alerting.example.com/webhook \
    -d '{"message": "MR Validator container was down and restarted"}'
fi
```

---

## Best Practices

### Before Starting Container

1. ✓ Validate configuration: `python manage_container.py config`
2. ✓ Check disk space: `df -h`
3. ✓ Verify Docker running: `docker info`
4. ✓ Review warnings: Address any critical warnings

### Regular Maintenance

1. ✓ Monitor disk usage weekly
2. ✓ Check container status daily: `python manage_container.py status`
3. ✓ Review logs for errors: `python manage_container.py logs --no-follow | grep ERROR`
4. ✓ Clean old containers: `docker container prune`

### Security

1. ✓ Set mrproper.env permissions to 600: `chmod 600 mrproper.env`
2. ✓ Never commit mrproper.env to git (in .gitignore)
3. ✓ Rotate GITLAB_ACCESS_TOKEN regularly
4. ✓ Use least-privilege tokens (only required scopes)

### Performance

1. ✓ Monitor CPU/Memory with `status` command
2. ✓ Set appropriate API_TIMEOUT (120s default)
3. ✓ Use organized log structure for better performance
4. ✓ Implement log rotation for large deployments

---

## Exit Codes Reference

| Code | Meaning | Description |
|------|---------|-------------|
| `0` | SUCCESS | Operation completed successfully |
| `1` | ERROR | General error (see error message) |
| `2` | CONFIG_ERROR | Configuration validation failed |
| `3` | DOCKER_ERROR | Docker operation failed |
| `4` | CANCELLED | User cancelled operation |

### Using Exit Codes in Scripts

```bash
#!/bin/bash

python manage_container.py start --yes
EXIT_CODE=$?

case $EXIT_CODE in
  0)
    echo "✓ Success"
    ;;
  1)
    echo "✗ General error"
    ;;
  2)
    echo "✗ Configuration error - check mrproper.env"
    python manage_container.py config
    ;;
  3)
    echo "✗ Docker error - check Docker daemon"
    docker info
    ;;
  4)
    echo "✗ User cancelled"
    ;;
  *)
    echo "✗ Unknown error: $EXIT_CODE"
    ;;
esac

exit $EXIT_CODE
```

---

## Quick One-Liners

```bash
# Full deployment in one line
python manage_container.py build && python manage_container.py start --yes && python manage_container.py test

# Quick restart and verify
python manage_container.py restart && sleep 2 && python manage_container.py status

# Check if container is healthy
python manage_container.py status > /dev/null 2>&1 && echo "OK" || echo "FAILED"

# View last 100 errors
python manage_container.py logs --no-follow | grep ERROR | tail -100

# Test all validators
for v in rate-my-mr mrproper-message mrproper-clang-format; do python manage_container.py test --validator $v; done

# Export logs with timestamp
python manage_container.py logs --no-follow > logs-$(date +%Y%m%d-%H%M%S).txt

# Clean rebuild
python manage_container.py remove --force && python manage_container.py build && python manage_container.py start --yes
```

---

## Summary: Command Usage Matrix

| Use Case | Command(s) |
|----------|-----------|
| **First setup** | `config → build → start` |
| **Daily check** | `status → test` |
| **After config change** | `config → restart` |
| **Troubleshoot** | `config → status → logs → restart` |
| **Full rebuild** | `stop → remove → build → start` |
| **Monitor** | `logs` (follow mode) |
| **Test changes** | `build → restart → test` |
| **Production deploy** | `config → build → stop → start → status → test` |

---

## Quick Decision Guide

| I want to... | Command |
|--------------|---------|
| Check if setup is valid | `config` |
| Create images | `build` |
| Start for first time | `start` |
| Start quickly | `start --yes` |
| Check if running | `status` |
| See what's happening | `logs` |
| See errors | `logs --no-follow \| grep ERROR` |
| Apply config change | `restart` |
| Apply code change | `build` → `restart` |
| Test if working | `test` |
| Stop container | `stop` |
| Remove everything | `remove --force` |
| Rebuild from scratch | `stop` → `remove` → `build` → `start` |

---

## Getting Help

```bash
# Show all commands
python manage_container.py --help

# Show command-specific help
python manage_container.py start --help
python manage_container.py config --help
```

---

**For the latest updates and project documentation, see:**
- [README.md](./README.md) - Project overview
- [OPERATIONS.md](./OPERATIONS.md) - DevOps guide
- [ARCHITECTURE.md](./ARCHITECTURE.md) - Technical architecture
