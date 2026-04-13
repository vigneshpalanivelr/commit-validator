# MR Validator - Complete Operational Guide

Comprehensive documentation covering deployment, container management, monitoring, and technical specifications.

## Table of Contents

### Part 1: Quick Start & Overview
- [Quick Reference](#quick-reference)
  - [Container Architecture](#container-architecture)
  - [Essential Commands](#essential-commands)
  - [Quick Start](#quick-start)
  - [Common Flags](#common-flags)
  - [Troubleshooting Quick Guide](#troubleshooting-quick-guide)

### Part 2: Deployment
- [Deployment](#deployment)
  - [Infrastructure Overview](#infrastructure-overview)
  - [Deployment Diagram](#deployment-diagram)
  - [Production Setup](#production-setup)
  - [Volume Configuration](#volume-configuration)

### Part 3: Container Management CLI
- [Container Management CLI](#container-management-cli)
  - [Installation & Setup](#installation--setup)
  - [Commands Reference](#commands-reference)
  - [Individual Command Examples](#individual-command-examples)
  - [Command Workflows](#command-workflows)
  - [Combined Workflows](#combined-workflows)
  - [Real-World Scenarios](#real-world-scenarios)
  - [Automation Examples](#automation-examples)
  - [Configuration Validation](#configuration-validation)
  - [Monitoring & Logs](#monitoring--logs)
  - [Testing (Container CLI)](#testing-container-cli)
  - [Troubleshooting (Container CLI)](#troubleshooting-container-cli)
  - [Advanced Usage](#advanced-usage)
  - [Best Practices](#best-practices)

### Part 4: Operations & Maintenance
- [Operations & Maintenance](#operations--maintenance)
  - [Monitoring](#monitoring)
  - [Maintenance](#maintenance)

### Part 5: Debugging & Troubleshooting
- [Debugging & Troubleshooting](#debugging--troubleshooting)
  - [REQUEST_ID Correlation](#request_id-correlation)
  - [Common Failure Scenarios](#common-failure-scenarios)
  - [Debug Workflow](#debug-workflow)
  - [Quick Debug Script](#quick-debug-script)

### Part 6: Testing
- [Testing](#testing)
  - [Infrastructure Tests](#infrastructure-tests)
  - [Validator Tests](#validator-tests)
  - [Integration Tests](#integration-tests)
  - [Performance Tests](#performance-tests)
  - [Complete Test Suite Reference](#complete-test-suite-reference)

### Part 7: Technical Specifications
- [Technical Specifications](#technical-specifications)
  - [Architecture Overview](#architecture-overview)
  - [Component Details](#component-details)
  - [API Payloads](#api-payloads)
  - [Container Communication](#container-communication)
  - [Sequence Diagrams](#sequence-diagrams)

### Part 8: Configuration Reference
- [Configuration Reference](#configuration-reference)
  - [Required Variables](#required-variables)
  - [AI/LLM Service Configuration](#aillm-service-configuration)
  - [Logging Configuration](#logging-configuration)
  - [Auto-Set Variables](#auto-set-variables)

### Appendices
- [Exit Codes Reference](#exit-codes-reference)
- [Related Documentation](#related-documentation)

---

# Part 1: Quick Start & Overview

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

**Option 1: Using manage_container.py (Recommended)**

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

**Option 2: Using shell scripts**

```bash
# 1. Build images
./build-docker-images

# 2. Start server
./start-server

# 3. Verify
curl http://localhost:9912/
```

**Option 3: Manual Docker commands**

```bash
# 1. Build
docker build -t ratemymr-validate-container mrproper
docker build -t ratemymr-webhook-container webhook-server

# 2. Start
docker run -d \
  --name ratemymr-webhook-container \
  --restart=unless-stopped \
  --env-file mrproper.env \
  -p 9912:9912 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /mnt/nfs/mr-validator-logs:/home/docker/tmp/mr-validator-logs \
  ratemymr-webhook-container
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

# Part 2: Deployment

## Deployment

### Infrastructure Overview

```mermaid
flowchart TB
    subgraph Host["▣ Docker Host"]
        A[◉ Webhook Container<br/>Port 9912<br/>Long-running]
        B[★ Validator Containers<br/>Spawned on demand<br/>Short-lived]
        C[▤ Shared Volume<br/>/mr-validator-logs<br/>Persistent storage]
    end

    subgraph External["◈ External Services"]
        D[◆ GitLab<br/>Source control<br/>API v4]
        E[◎ BFA Service<br/>AI/LLM<br/>JWT auth]
        F[▦ NFS Storage<br/>Log persistence<br/>Shared mount]
    end

    D -->|"1. POST webhook<br/>MR event"| A
    A -->|"2. docker run<br/>--env-file"| B
    B -->|"3. POST /api/rate-my-mr<br/>Bearer token"| E
    B -->|"4. GET /api/v4<br/>PRIVATE-TOKEN"| D
    A -->|"Write logs"| C
    B -->|"Write logs"| C
    C -->|"Mount"| F

    classDef host fill:#c5e8f7,color:#333,stroke:#9ad0e8
    classDef external fill:#fff8dc,color:#333,stroke:#e8d890
    classDef gitlab fill:#ffd4c4,color:#333,stroke:#e8a090
    classDef bfa fill:#c8e6c9,color:#333,stroke:#a5d6a7
    classDef storage fill:#e1bee7,color:#333,stroke:#ce93d8

    class A,B,C host
    class D gitlab
    class E bfa
    class F storage
```

### Deployment Diagram

```mermaid
graph TB
    subgraph "External Services"
        GL[GitLab Instance<br/>gitlab.com]
        BFA[BFA Service<br/>api-gateway.internal.com:8000<br/>JWT-authenticated AI service]
    end

    subgraph "MR Validator Infrastructure"
        subgraph "Persistent Container"
            WS[Webhook Server<br/>ratemymr-webhook-container<br/>Port: 9912<br/>Framework: Tornado]
        end

        subgraph "Ephemeral Containers"
            VC1[Validator Container 1<br/>mr-rate-my-mr-42-abc123<br/>Image: ratemymr-validate-container]
            VC2[Validator Container 2<br/>mr-mrproper-message-43-def456<br/>Image: ratemymr-validate-container]
            VC3[Validator Container 3<br/>mr-mrproper-clang-format-44-ghi789<br/>Image: ratemymr-validate-container]
        end

        subgraph "Shared Storage"
            LOGS[Log Directory<br/>/home/docker/tmp/mr-validator-logs<br/>webhook/, validations/]
        end
    end

    GL -->|1. MR Webhook Event<br/>POST /mr-proper/rate-my-mr| WS
    WS -->|2. Spawn Docker Container<br/>docker run -d| VC1
    WS -->|3. Spawn Docker Container| VC2
    WS -->|4. Spawn Docker Container| VC3

    VC1 -->|5. Get MR Data<br/>GET /api/v4/projects/:id/merge_requests/:iid| GL
    VC1 -->|6. Clone Repository<br/>git fetch| GL
    VC1 -->|7. Acquire JWT Token<br/>POST /api/token| BFA
    BFA -->|8. JWT Token| VC1
    VC1 -->|9. AI Analysis Request<br/>POST /api/rate-my-mr<br/>Bearer Token| BFA
    BFA -->|10. AI Response<br/>Summary & Code Review| VC1
    VC1 -->|11. Post Results<br/>POST /api/v4/projects/:id/merge_requests/:iid/discussions| GL

    WS -.->|Mount Volume| LOGS
    VC1 -.->|Write Logs| LOGS
    VC2 -.->|Write Logs| LOGS
    VC3 -.->|Write Logs| LOGS

    style GL fill:#e1f5ff,stroke:#01579b,stroke-width:2px
    style BFA fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style WS fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
    style VC1 fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px
    style VC2 fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px
    style VC3 fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px
    style LOGS fill:#fff9c4,stroke:#f57f17,stroke-width:2px
```

### Production Setup

**1. Create log directory:**
```bash
mkdir -p /mnt/nfs/mr-validator-logs
chown -R 1000:1000 /mnt/nfs/mr-validator-logs
chmod 755 /mnt/nfs/mr-validator-logs
```

**2. Create mrproper.env:**
```bash
cat > mrproper.env << 'EOF'
GITLAB_ACCESS_TOKEN=glpat-xxxxxxxxxxxxxxxxxxxx
BFA_HOST=api-gateway.internal.com
API_TIMEOUT=120
LOG_DIR=/home/docker/tmp/mr-validator-logs
LOG_LEVEL=INFO
LOG_MAX_BYTES=52428800
LOG_BACKUP_COUNT=3
LOG_STRUCTURE=organized
EOF

chmod 600 mrproper.env
```

**3. Start webhook server:**
```bash
docker run -d \
  --name ratemymr-webhook-container \
  --restart=unless-stopped \
  --env-file mrproper.env \
  -p 9912:9912 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /mnt/nfs/mr-validator-logs:/home/docker/tmp/mr-validator-logs \
  ratemymr-webhook-container
```

**4. Verify:**
```bash
docker ps | grep webhook
curl http://localhost:9912/
docker logs ratemymr-webhook-container --tail 20
```

**Expected output:**
```
CONTAINER ID   IMAGE                          STATUS          PORTS
abc123def456   ratemymr-webhook-container     Up 2 minutes    0.0.0.0:9912->9912/tcp

=== MR Validator Webhook Server Starting ===
Docker connectivity verified
Starting webhook server on port 9912...
```

**Container Ports:**
- **Webhook Container:** Port 9912 (GitLab webhook endpoint)
- **Validator Containers:** No fixed port (ephemeral, spawned on-demand)

### Volume Configuration

| Mount | Purpose | Size |
|-------|---------|------|
| `/var/run/docker.sock` | Docker API access | N/A |
| `/mnt/nfs/mr-validator-logs` | Persistent logs | ~100GB |

**NFS Mount:**
```bash
# /etc/fstab entry
nfs-server:/exports/mr-validator-logs /mnt/nfs/mr-validator-logs nfs defaults 0 0

# Mount
mount /mnt/nfs/mr-validator-logs
```

---

# Part 3: Container Management CLI

## Container Management CLI

The `manage_container.py` script provides a comprehensive CLI for managing MR Validator containers. For the complete guide with 100+ examples, automation templates, and detailed workflows, see [Part 3](#container-management-cli).

### Installation & Setup

#### Prerequisites

- Python 3.6+
- Docker 20.10+
- pip (Python package manager)

#### Install Dependencies

```bash
# Required dependencies
pip install python-dotenv docker

# Optional: Enhanced CLI output (recommended)
pip install rich==12.6.0
```

#### Verify Installation

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

### Commands Reference

#### config - Configuration Management

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

#### build - Build Docker Images

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

#### start - Start Container

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

#### stop - Stop Container

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

#### restart - Restart Container

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

#### logs - View Logs

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

#### status - Container Status

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

#### remove - Remove Container/Images

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

#### test - Test Webhooks

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

### Individual Command Examples

For detailed examples of each command (50+ examples total), see the [CONTAINER_MANAGEMENT_COMPLETE_GUIDE.md](./CONTAINER_MANAGEMENT_COMPLETE_GUIDE.md) or continue reading this guide.

**Quick examples:**

```bash
# Config validation
python manage_container.py config --quiet

# Build and verify
python manage_container.py build && docker images | grep -E "webhook|checker"

# Start and verify
python manage_container.py start --yes && python manage_container.py status

# Search for errors
python manage_container.py logs --no-follow | grep -i error

# Test all validators
for validator in rate-my-mr mrproper-message mrproper-clang-format; do
  python manage_container.py test --validator $validator
  sleep 2
done
```

### Command Workflows

#### Command Decision Tree

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

#### Command Flow Diagram

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

### Combined Workflows

#### Workflow 1: First-Time Setup

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

#### Workflow 2: Daily Health Check

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

#### Workflow 3: Update Configuration

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

### Real-World Scenarios

#### Scenario 1: Production Deployment

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

#### Scenario 2: Automated Health Check (Cron Job)

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

### Automation Examples

#### Example 1: Systemd Service

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

#### Example 2: Makefile

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

### Configuration Validation

#### Validation Categories

**Required Fields**
- `GITLAB_ACCESS_TOKEN` - Must be present

**AI/LLM Service**
- `BFA_HOST` or `AI_SERVICE_URL` - At least one required
- Warning if both set (BFA_HOST takes precedence)
- URL format validation

**Logging Configuration**
- `LOG_LEVEL` - Must be valid level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `LOG_DIR` - Must be writable (if exists)

**System Resources**
- Disk space check (warns if <5GB, critical if <1GB)
- File permissions check (warns if not 600/400)

#### Validation Messages

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

### Monitoring & Logs

#### Real-time Log Monitoring

```bash
# Follow all logs
python manage_container.py logs

# Filter for errors
python manage_container.py logs | grep -i error

# Filter for specific REQUEST_ID
python manage_container.py logs | grep "12345678"
```

#### Log Analysis

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

#### Resource Monitoring

```bash
# Check CPU/Memory usage
python manage_container.py status

# Watch resource usage continuously
watch -n 5 "python manage_container.py status"
```

### Testing (Container CLI)

#### Test Webhook Endpoints

```bash
# Test default validator
python manage_container.py test

# Test all validators
python manage_container.py test --validator rate-my-mr
python manage_container.py test --validator mrproper-message
python manage_container.py test --validator mrproper-clang-format
```

#### Manual Testing with curl

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

#### Verify Validator Execution

```bash
# After sending test webhook
docker ps -a | grep mr-rate-my-mr

# Check validator logs
LOG_DIR=/home/docker/tmp/mr-validator-logs
ls -lh $LOG_DIR/validations/$(date +%Y-%m-%d)/*/mr-*/
```

### Troubleshooting (Container CLI)

#### Common Issues

**1. Configuration Errors**

**Problem:** `GITLAB_ACCESS_TOKEN is not set`

**Solution:**
```bash
# Edit mrproper.env
echo "GITLAB_ACCESS_TOKEN=glpat-your-token-here" >> mrproper.env

# Validate
python manage_container.py config
```

**2. Container Won't Start**

**Problem:** `Image 'ratemymr-webhook-container:latest' not found`

**Solution:**
```bash
# Build images first
python manage_container.py build

# Then start
python manage_container.py start
```

**3. Port Already in Use**

**Problem:** `port is already allocated`

**Solution:**
```bash
# Find what's using port 9912
docker ps | grep 9912

# Stop conflicting container
docker stop <container-id>
```

**4. Permission Denied**

**Problem:** `permission denied while trying to connect to Docker daemon`

**Solution:**
```bash
# Add user to docker group
sudo usermod -aG docker $USER

# Re-login for changes to take effect
newgrp docker
```

**5. Disk Space Low**

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

#### Debugging Workflow

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

### Advanced Usage

#### Custom Environment File

```bash
# Use different env file for config validation
python manage_container.py config --env-file /path/to/custom.env

# Note: start always uses mrproper.env
```

#### Scripting/Automation

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

### Best Practices

#### Before Starting Container

1. ✓ Validate configuration: `python manage_container.py config`
2. ✓ Check disk space: `df -h`
3. ✓ Verify Docker running: `docker info`
4. ✓ Review warnings: Address any critical warnings

#### Regular Maintenance

1. ✓ Monitor disk usage weekly
2. ✓ Check container status daily: `python manage_container.py status`
3. ✓ Review logs for errors: `python manage_container.py logs --no-follow | grep ERROR`
4. ✓ Clean old containers: `docker container prune`

#### Security

1. ✓ Set mrproper.env permissions to 600: `chmod 600 mrproper.env`
2. ✓ Never commit mrproper.env to git (in .gitignore)
3. ✓ Rotate GITLAB_ACCESS_TOKEN regularly
4. ✓ Use least-privilege tokens (only required scopes)

#### Performance

1. ✓ Monitor CPU/Memory with `status` command
2. ✓ Set appropriate API_TIMEOUT (120s default)
3. ✓ Use organized log structure for better performance
4. ✓ Implement log rotation for large deployments

---

# Part 4: Operations & Maintenance

## Operations & Maintenance

### Monitoring

#### Health Check Commands

```bash
# Webhook server status
docker ps | grep webhook
curl -s http://localhost:9912/ | head -1

# Recent validations
docker ps -a --filter "name=mr-checker" | head -10

# Active containers
docker ps --filter "name=mr-checker" --format "{{.Names}}\t{{.Status}}"

# Failed containers (last 24h)
docker ps -a --filter "name=mr-checker" --filter "exited=1" \
  --format "{{.Names}}\t{{.CreatedAt}}"
```

#### Log Analysis

**Validation success rate:**
```bash
LOG_DIR=/mnt/nfs/mr-validator-logs/validations/$(date +%Y-%m-%d)

TOTAL=$(find $LOG_DIR -name "*.log" -type f | wc -l)
ERRORS=$(grep -l "ERROR" $LOG_DIR/**/**/*.log 2>/dev/null | wc -l)
SUCCESS=$((TOTAL - ERRORS))

echo "Total: $TOTAL, Success: $SUCCESS, Errors: $ERRORS"
echo "Success rate: $((SUCCESS * 100 / TOTAL))%"
```

**Average validation time:**
```bash
for log in $(find $LOG_DIR -name "*.log" -type f | head -10); do
  START=$(head -1 "$log" | cut -d'|' -f1)
  END=$(tail -1 "$log" | cut -d'|' -f1)
  echo "$log: $START -> $END"
done
```

**Most common errors:**
```bash
grep -h "ERROR" $LOG_DIR/**/**/*.log | \
  sed 's/.*| //' | sort | uniq -c | sort -rn | head -10
```

#### Disk Usage Monitoring

```bash
#!/bin/bash
# monitor-disk.sh

LOG_DIR=/mnt/nfs/mr-validator-logs
THRESHOLD=80

USAGE=$(df "$LOG_DIR" | tail -1 | awk '{print $5}' | sed 's/%//')

if [ "$USAGE" -gt "$THRESHOLD" ]; then
    echo "WARNING: Log disk at ${USAGE}%" | mail -s "MR Validator Disk Alert" ops@example.com
fi

# Log sizes
du -sh "$LOG_DIR/webhook/"
du -sh "$LOG_DIR/validations/"
du -sh "$LOG_DIR/validations/$(date +%Y-%m-%d)/"
```

**Cron schedule:**
```bash
# Check every hour
0 * * * * /opt/scripts/monitor-disk.sh
```

#### Alerting

**Container failures:**
```bash
#!/bin/bash
# alert-failures.sh

FAILURES=$(docker ps -a --filter "name=mr-checker" --filter "exited=1" \
  --since="1h" --format "{{.Names}}" | wc -l)

if [ "$FAILURES" -gt 5 ]; then
    echo "High failure rate: $FAILURES in last hour"
fi
```

### Maintenance

#### Log Rotation

**Automatic rotation** (configured via environment):
```bash
LOG_MAX_BYTES=52428800   # 50MB per file
LOG_BACKUP_COUNT=3       # Keep 3 rotated files

# Result:
# rate-my-mr-12345678.log        (current, up to 50MB)
# rate-my-mr-12345678.log.1      (50MB)
# rate-my-mr-12345678.log.2      (50MB)
# rate-my-mr-12345678.log.3      (50MB, oldest)
```

#### Cleanup Old Logs

**Delete logs older than 30 days:**
```bash
#!/bin/bash
# cleanup-logs.sh

LOG_BASE=/mnt/nfs/mr-validator-logs
DAYS_TO_KEEP=30

# Cleanup validation logs
find "$LOG_BASE/validations" -type d -name "20*" -mtime +$DAYS_TO_KEEP -exec rm -rf {} \;

# Cleanup webhook logs
find "$LOG_BASE/webhook" -type d -name "20*" -mtime +$DAYS_TO_KEEP -exec rm -rf {} \;

# Report
echo "Cleaned up logs older than $DAYS_TO_KEEP days"
du -sh "$LOG_BASE"
```

**Cron schedule:**
```bash
# Run daily at 2 AM
0 2 * * * /opt/scripts/cleanup-logs.sh >> /var/log/cleanup.log 2>&1
```

#### Disk Space Recovery

**Emergency cleanup:**
```bash
# Delete all logs older than 7 days
find /mnt/nfs/mr-validator-logs -type f -mtime +7 -delete

# Delete empty directories
find /mnt/nfs/mr-validator-logs -type d -empty -delete
```

**Reduce log verbosity:**
```bash
# In mrproper.env
LOG_LEVEL=WARNING        # Only warnings and errors
LOG_MAX_BYTES=10485760   # 10MB instead of 50MB
LOG_BACKUP_COUNT=1       # Only 1 backup
```

#### Docker Cleanup

**Remove old containers:**
```bash
# Remove stopped validator containers older than 1 day
docker container prune --filter "until=24h" --filter "name=mr-"

# Remove dangling images
docker image prune -f

# Full cleanup (careful!)
docker system prune -f
```

#### Restart Procedures

**Restart webhook server:**
```bash
docker restart ratemymr-webhook-container

# Or full restart
docker stop ratemymr-webhook-container
docker rm ratemymr-webhook-container
./start-server
```

**Rebuild images:**
```bash
./build-docker-images --no-cache
docker restart ratemymr-webhook-container
```

#### Backup Strategy

**Configuration backup:**
```bash
cp mrproper.env mrproper.env.backup.$(date +%Y%m%d)
```

**Log backup (optional):**
```bash
# Compress and archive old logs
tar -czf logs_$(date +%Y%m%d).tar.gz \
  /mnt/nfs/mr-validator-logs/validations/$(date -d "7 days ago" +%Y-%m-%d)

# Move to archive storage
mv logs_*.tar.gz /archive/mr-validator/
```

#### Upgrade Procedure

```mermaid
flowchart TD
    A[1. Pull latest code<br/>git pull origin main] --> B[2. Build new images<br/>./build-docker-images]
    B --> C[3. Test locally<br/>docker run --rm rate-my-mr --help]
    C --> D{Tests pass?}
    D -->|No| E[Fix issues<br/>Review build logs]
    E --> C
    D -->|Yes| F[4. Stop webhook server<br/>docker stop ratemymr-webhook-container]
    F --> G[5. Backup config<br/>cp mrproper.env .backup]
    G --> H[6. Deploy new images<br/>docker tag :latest]
    H --> I[7. Start webhook server<br/>docker start ratemymr-webhook-container]
    I --> J[8. Verify health<br/>curl localhost:9912]
    J --> K{Healthy?}
    K -->|No| L[[x] Rollback<br/>Restore from backup]
    K -->|Yes| M[✓ Done<br/>Upgrade complete]

    classDef prepare fill:#d4e5f7,color:#333,stroke:#a8c8e8
    classDef build fill:#e3f2fd,color:#333,stroke:#b3d4f7
    classDef test fill:#fff8dc,color:#333,stroke:#e8d890
    classDef deploy fill:#e1bee7,color:#333,stroke:#ce93d8
    classDef verify fill:#c8e6c9,color:#333,stroke:#a5d6a7
    classDef error fill:#ffcdd2,color:#333,stroke:#ef9a9a
    classDef success fill:#e8f5e9,color:#333,stroke:#c8e6c9

    class A,G prepare
    class B,H build
    class C,E test
    class D,K test
    class F,I deploy
    class J verify
    class L error
    class M success
```

**Steps:**
```bash
# 1. Pull latest
git pull origin main

# 2. Build
./build-docker-images

# 3. Test
docker run --rm ratemymr-validate-container rate-my-mr --help

# 4. Deploy
docker stop ratemymr-webhook-container
cp mrproper.env mrproper.env.backup
# Make any config changes
./start-server

# 5. Verify
curl http://localhost:9912/
docker logs ratemymr-webhook-container --tail 20

# 6. Monitor first few validations
tail -f /mnt/nfs/mr-validator-logs/webhook/*/webhook-server.log
```

---

# Part 5: Debugging & Troubleshooting

## Debugging & Troubleshooting

### REQUEST_ID Correlation

Every webhook request gets unique ID: `YYYYMMDD_HHMMSS_MICROSECONDS`

**Find REQUEST_ID:**
```bash
# From webhook log
grep "NEW WEBHOOK REQUEST" webhook-server.log | tail -1
# Output: [12345678] === NEW WEBHOOK REQUEST ===

# REQUEST_ID_SHORT = first 8 chars of microseconds
```

**Trace complete flow:**
```bash
REQ_ID="12345678"

# 1. Webhook received
grep "\[$REQ_ID\]" /path/to/webhook-server.log

# 2. Container spawned
grep "\[$REQ_ID\] Checker" /path/to/webhook-server.log

# 3. Validator logs
ls /mnt/nfs/mr-validator-logs/validations/**/**/*$REQ_ID*.log
cat /mnt/nfs/mr-validator-logs/validations/**/**/*$REQ_ID*.log

# 4. Final status
grep "Final rating" /mnt/nfs/mr-validator-logs/validations/**/**/*$REQ_ID*.log
```

### Common Failure Scenarios

#### Container Fails Immediately

```bash
# Check exit code
docker inspect mr-rate-my-mr-42-12345678 --format='{{.State.ExitCode}}'

# Exit codes:
# 0 = Success
# 1 = Application error (check logs)
# 137 = OOM killed
# 139 = Segfault
```

**Debug steps:**
```bash
# 1. Find log file
ls -t /mnt/nfs/mr-validator-logs/validations/$(date +%Y-%m-%d)/**/*12345678*.log

# 2. Check startup
head -20 /path/to/log

# 3. Check errors
grep -i error /path/to/log

# 4. Common causes:
grep "GITLAB_ACCESS_TOKEN" /path/to/log  # Missing token
grep "GitLab API" /path/to/log           # API failure
grep "git clone" /path/to/log            # Clone failure
```

#### AI Service Timeout

```bash
# Search for timeout errors
grep "Timeout\|timeout" /path/to/log

# Check retry attempts
grep "Retry attempt" /path/to/log

# Check BFA connectivity
curl -s -o /dev/null -w "%{http_code}" http://api-gateway.internal.com:8000/health
```

#### JWT Token Issues

```bash
# Token acquisition
grep "JWT token" /path/to/log

# Expected flow:
# [DEBUG] Requesting JWT token from http://...
# [DEBUG] Token subject: rate-my-mr-org%2Frepo-42
# [DEBUG] Token API response status: 200
# [DEBUG] JWT token acquired successfully

# Common issues:
grep "401\|403\|Token" /path/to/log
```

**Manual token test:**
```bash
curl -X POST "http://${BFA_HOST}:8000/api/token" \
  -H "Content-Type: application/json" \
  -d '{"subject":"rate-my-mr-test-123"}' \
  -v

# Should return:
# {"token": "eyJhbGci..."}
```

#### GitLab API 401

```bash
# Check token validity
curl -H "PRIVATE-TOKEN: $GITLAB_ACCESS_TOKEN" \
  "https://gitlab.com/api/v4/user"

# Check MR access
curl -H "PRIVATE-TOKEN: $GITLAB_ACCESS_TOKEN" \
  "https://gitlab.com/api/v4/projects/org%2Frepo/merge_requests/42"
```

#### Wrong API URL

```bash
# Check which URL is being used
grep "bfa_url\|legacy_url" /path/to/log

# Ensure BFA_HOST is set
docker exec ratemymr-webhook-container env | grep BFA_HOST
```

### Debug Workflow

```mermaid
flowchart TD
    A[> User Reports Issue<br/>MR not validated] --> B[1. Get MR IID<br/>from GitLab URL]
    B --> C[2. Find REQUEST_ID<br/>grep webhook-server.log]
    C --> D[3. Find validator log<br/>validations/DATE/PROJECT/mr-IID/]
    D --> E{Log exists?}
    E -->|No| F[[x] Container never started<br/>Check Docker daemon]
    E -->|Yes| G[4. Check for errors<br/>grep ERROR|WARN]
    G --> H{Error type?}
    H -->|Auth 401| I[✓ Check tokens<br/>GITLAB_ACCESS_TOKEN<br/>JWT token validity]
    H -->|Timeout| J[✓ Check connectivity<br/>BFA_HOST reachable<br/>API_TIMEOUT setting]
    H -->|Config| K[✓ Check repo config<br/>.rate-my-mr.yaml syntax<br/>Feature flags]
    H -->|Git clone| L[✓ Check repo access<br/>Token permissions<br/>Network connectivity]

    classDef start fill:#d4e5f7,color:#333,stroke:#a8c8e8
    classDef step fill:#e3f2fd,color:#333,stroke:#b3d4f7
    classDef decision fill:#fff8dc,color:#333,stroke:#e8d890
    classDef error fill:#ffcdd2,color:#333,stroke:#ef9a9a
    classDef solution fill:#c8e6c9,color:#333,stroke:#a5d6a7

    class A start
    class B,C,D,G step
    class E,H decision
    class F error
    class I,J,K,L solution
```

### Quick Debug Script

```bash
#!/bin/bash
# debug-mr.sh <mr_iid>

MR_IID=$1
DATE=$(date +%Y-%m-%d)
LOG_BASE=/mnt/nfs/mr-validator-logs

echo "=== Finding REQUEST_ID for MR $MR_IID ==="
REQ_SHORT=$(grep "MR IID: $MR_IID" $LOG_BASE/webhook/*/webhook-server.log | \
  tail -1 | grep -o '\[[0-9]*\]' | tr -d '[]')

echo "REQUEST_ID_SHORT: $REQ_SHORT"

echo "=== Finding validator log ==="
LOG_FILE=$(find $LOG_BASE/validations -name "*$REQ_SHORT*.log" | head -1)

if [ -z "$LOG_FILE" ]; then
    echo "No log found"
    exit 1
fi

echo "Log file: $LOG_FILE"

echo "=== Last 20 lines ==="
tail -20 "$LOG_FILE"

echo "=== Errors ==="
grep -i error "$LOG_FILE"

echo "=== Final rating ==="
grep "Final rating" "$LOG_FILE"
```

---

# Part 6: Testing

## Testing

### Infrastructure Tests

```bash
# Test 1: Docker image exists
docker images | grep ratemymr-validate-container
# Expected: ratemymr-validate-container   latest   abc123   1 hour ago   1.2GB

# Test 2: Webhook server responds
curl -s http://localhost:9912/ | head -1
# Expected: MR Validator Webhook Server

# Test 3: Environment file readable
test -f mrproper.env && echo "EXISTS" || echo "MISSING"
# Expected: EXISTS

# Test 4: Log directory writable
touch /mnt/nfs/mr-validator-logs/test && rm /mnt/nfs/mr-validator-logs/test && echo "OK"
# Expected: OK

# Test 5: GitLab API accessible
curl -s -H "PRIVATE-TOKEN: $GITLAB_ACCESS_TOKEN" https://gitlab.com/api/v4/user | jq .username
# Expected: "your-username"

# Test 6: BFA service accessible
curl -s http://${BFA_HOST}:8000/health
# Expected: {"status": "ok"}
```

### Validator Tests

**Smoke test:**
```bash
docker run --rm --env-file mrproper.env \
  -e REQUEST_ID=test_$(date +%s)_smoke001 \
  -e PROJECT_ID=org/repo \
  -e MR_IID=1 \
  ratemymr-validate-container rate-my-mr --help

# Expected: Usage information, exit 0
```

**Full validation test:**
```bash
REQUEST_ID=test_$(date +%Y%m%d_%H%M%S)_$(openssl rand -hex 4)

docker run --rm --env-file mrproper.env \
  -e REQUEST_ID=$REQUEST_ID \
  -v /mnt/nfs/mr-validator-logs:/home/docker/tmp/mr-validator-logs \
  ratemymr-validate-container rate-my-mr org%2Frepo 42

echo "Check logs: grep '$REQUEST_ID' /mnt/nfs/mr-validator-logs/**/**/**/*.log"
```

### Integration Tests

**Multiple validators:**
```bash
curl -X POST http://localhost:9912/mr-proper/rate-my-mr+mrproper-message \
  -H "Content-Type: application/json" \
  -d '{"object_kind":"merge_request","project":{"path_with_namespace":"org/repo"},"object_attributes":{"iid":42}}'

# Check both containers spawned
docker ps -a | grep "mr-.*-42-"
```

**Concurrent requests:**
```bash
for i in 1 2 3 4 5; do
  curl -X POST http://localhost:9912/mr-proper/rate-my-mr \
    -H "Content-Type: application/json" \
    -d "{\"object_kind\":\"merge_request\",\"project\":{\"path_with_namespace\":\"org/repo\"},\"object_attributes\":{\"iid\":$i}}" &
done
wait

# Check all containers
docker ps -a | grep "mr-rate-my-mr"
```

### Performance Tests

**Large MR (1000+ LOC):**
```bash
time docker run --rm --env-file mrproper.env \
  -e REQUEST_ID=perf_test_1 \
  ratemymr-validate-container rate-my-mr org%2Flarge-mr 99

# Expected: <5 minutes
```

**Token acquisition overhead:**
```bash
# With BFA_HOST (new adapter)
time curl -s -X POST "http://${BFA_HOST}:8000/api/token" \
  -d '{"subject":"test"}' | jq -r '.token'

# Expected: <200ms
```

### Complete Test Suite Reference

<details>
<summary><b># Complete Test Suite Reference (Click to expand - 650+ lines, 44+ tests)</b></summary>

#### Test Suite 1: Infrastructure Tests

**Test 1.1: Docker Image Build**
```bash
# Build image
docker build -t ratemymr-validate-container .
# Expected: Build SUCCESS, no missing dependencies

# Verification
docker run ratemymr-validate-container python -c "import mrproper; print('OK')"
docker run ratemymr-validate-container which rate-my-mr
docker run ratemymr-validate-container which mrproper-clang-format
docker run ratemymr-validate-container which mrproper-message

# Success Criteria:
# - Image builds without errors
# - All Python packages installed
# - mrproper package installed
# - All three entry points available
```

**Test 1.2: Webhook Server Startup**
```bash
# Start server
cd webhook-server
python server.py &

# Check if running
sleep 2
curl -v http://localhost:9912/

# Expected logs:
# === MR Validator Webhook Server Starting ===
# Docker connectivity verified
# Starting webhook server on port 9912...

# Success Criteria:
# - Server starts without errors
# - Listens on port 9912
# - Logs initialized
# - Docker daemon accessible
```

**Test 1.3: Log Directory Setup**
```bash
# Check directory
ls -la /home/docker/tmp/mr-validator-logs/

# Check webhook log
test -f /home/docker/tmp/mr-validator-logs/webhook-server.log
echo "Status: $?"  # Should be 0

# Check rotation
ls -lh /home/docker/tmp/mr-validator-logs/webhook-server.log*

# Success Criteria:
# - Directory exists and writable
# - webhook-server.log created
# - Rotation configured (100MB x 5)
```

#### Test Suite 2: Webhook Server Tests

**Test 2.1: Webhook Endpoint Routing**
```bash
# Test rate-my-mr endpoint
curl -X POST http://localhost:9912/mr-proper/rate-my-mr \
  -H "Content-Type: application/json" \
  -d @test-payloads/mr-event.json

# Test clang-format endpoint
curl -X POST http://localhost:9912/mr-proper/mrproper-clang-format \
  -d @test-payloads/mr-event.json

# Test message endpoint
curl -X POST http://localhost:9912/mr-proper/mrproper-message \
  -d @test-payloads/mr-event.json

# Test combined (multiple validators)
curl -X POST http://localhost:9912/mr-proper/rate-my-mr+mrproper-message \
  -d @test-payloads/mr-event.json

# Success Criteria:
# - All endpoints return 200 OK
# - Docker containers spawned
# - REQUEST_ID logged
# - Multiple validators work with '+'
```

**Test 2.2: Invalid Checker Rejection**
```bash
# Test invalid checker
curl -X POST http://localhost:9912/mr-proper/invalid-checker \
  -d @test-payloads/mr-event.json

# Expected: 403 Forbidden

# Success Criteria:
# - Returns 403 Forbidden
# - Error logged
# - No container spawned
```

**Test 2.3: REQUEST_ID Generation and Propagation**
```bash
# Trigger validation
curl -X POST http://localhost:9912/mr-proper/rate-my-mr \
  -d @test-payloads/mr-event.json

# Check webhook log for REQUEST_ID
grep "=== NEW WEBHOOK REQUEST ===" /home/docker/tmp/mr-validator-logs/webhook-server.log | tail -1

# Extract REQUEST_ID from docker command
grep "REQUEST_ID=" /home/docker/tmp/mr-validator-logs/webhook-server.log | tail -1

# Check validator log has same REQUEST_ID
ls -t /home/docker/tmp/mr-validator-logs/rate-my-mr-*.log | head -1 | xargs grep REQUEST_ID

# Success Criteria:
# - Unique REQUEST_ID generated (timestamp-based)
# - REQUEST_ID passed to Docker container via --env
# - Validator log contains same REQUEST_ID
# - REQUEST_ID correlatable across all logs
```

**Test 2.4: Container Naming Convention**
```bash
# Trigger validation for MR !42
curl -X POST http://localhost:9912/mr-proper/rate-my-mr -d '...'

# Check container name
docker ps -a | grep "mr-rate-my-mr-42-"

# Expected format: mr-{checker}-{mriid}-{request_id_short}
# Example: mr-rate-my-mr-42-abcd1234

# Success Criteria:
# - Container name includes checker name
# - Container name includes MR IID
# - Container name includes REQUEST_ID_SHORT
# - Easy to identify in docker ps
```

#### Test Suite 3: rate-my-mr Validator Tests (Legacy Mode)

**Test 3.1: Basic Validation Flow (Legacy AI Service)**
```bash
# Configure legacy mode
cat > mrproper.env <<EOF
GITLAB_ACCESS_TOKEN=glpat-your-token
AI_SERVICE_URL=http://10.31.88.29:6006/generate
EOF

# Trigger validation
docker run --env-file mrproper.env \
  --env REQUEST_ID=test_$(date +%Y%m%d_%H%M%S_%N) \
  ratemymr-validate-container rate-my-mr \
  <project-name> <mr-iid>

# Check logs
tail -f /home/docker/tmp/mr-validator-logs/rate-my-mr-*.log

# Expected Log Flow:
# [DEBUG] Using legacy direct AI service connection
# [DEBUG] ===== STARTING MR ANALYSIS =====
# [DEBUG] Fetching MR data from GitLab API...
# [DEBUG] MR fetched successfully: <title>
# [DEBUG] Cloning git repository...
# [DEBUG] Diff generated...
# [DEBUG] AI Service Request - URL: http://10.31.88.29:6006/generate
# [DEBUG] AI Service Response - Status Code: 200
# ...
# Successfully analyzed MR <iid>

# Success Criteria:
# - GitLab API connection successful
# - MR data fetched
# - Git repository cloned
# - Diff generated
# - All 4 AI calls made
# - Discussion posted to GitLab
# - Container exits with code 0
```

**Test 3.2: AI Service Retry Logic (Legacy Mode)**
```bash
# Configure with unreachable AI service
AI_SERVICE_URL=http://invalid-host:6006/generate docker run ...

# Expected Logs:
# [DEBUG] AI Service Connection Error (attempt 1): ...
# [DEBUG] Retry attempt 2/3 after 2s wait...
# [DEBUG] AI Service Connection Error (attempt 2): ...
# [DEBUG] Retry attempt 3/3 after 4s wait...
# [DEBUG] AI Service Connection Error (attempt 3): ...
# [DEBUG] All 3 attempts failed - AI service not reachable
# [ERROR] Failed to generate summary: Connection failed after 3 attempts

# Success Criteria:
# - Retry attempt 1 after 2s wait
# - Retry attempt 2 after 4s wait
# - Retry attempt 3 after 8s wait
# - Fails gracefully after 3 attempts
# - Error posted to GitLab MR
```

**Test 3.3: GitLab API Error Handling**
```bash
# Test with invalid token
GITLAB_ACCESS_TOKEN=invalid-token docker run ...

# Test with invalid project
docker run ... invalid-project-name 123

# Test with invalid MR IID
docker run ... valid-project 999999

# Success Criteria:
# - 401 error logged for invalid token
# - 404 error logged for invalid project/MR
# - Error message posted to GitLab (if possible)
# - Container exits with non-zero code
```

#### Test Suite 4: rate-my-mr Validator Tests (New LLM Adapter)

**Test 4.1: JWT Token Acquisition**
```bash
# Configure new adapter mode
cat > mrproper.env <<EOF
GITLAB_ACCESS_TOKEN=glpat-your-token
BFA_HOST=api-gateway.internal.com
API_TIMEOUT=120
EOF

# Trigger validation
docker run --env-file mrproper.env \
  --env REQUEST_ID=test_$(date +%Y%m%d_%H%M%S_%N) \
  ratemymr-validate-container rate-my-mr \
  <project-name> <mr-iid>

# Expected Logs:
# [DEBUG] Using new LLM adapter (BFA_HOST is configured)
# [DEBUG] LLM Adapter initialized - BFA_HOST: api-gateway.internal.com
# Set environment for LLM adapter: PROJECT_ID=<project>, MR_IID=<mriid>
# [DEBUG] Requesting JWT token from http://api-gateway.internal.com:8000/api/token
# [DEBUG] Token subject: rate-my-mr-<project>-<mriid>
# [DEBUG] Token API response status: 200
# [DEBUG] JWT token acquired successfully for <project>-<mriid>
# [DEBUG] Token (first 20 chars): eyJhbGciOiJIUzI1Ni...

# Success Criteria:
# - Detects BFA_HOST is configured
# - Sets PROJECT_ID and MR_IID env vars
# - Calls POST http://{BFA_HOST}:8000/api/token
# - Payload: {"subject": "rate-my-mr-<project>-<mriid>"}
# - Receives token in response: {"token": "..."}
# - Token cached for session
```

**Test 4.2: Token Reuse Across Multiple AI Calls**
```bash
# Run validation and monitor logs
docker run ... | tee validation.log

# Count token acquisitions
grep "Requesting JWT token" validation.log | wc -l
# Expected: 1

# Count token reuse
grep "Reusing existing session token" validation.log | wc -l
# Expected: 3 (for calls 2, 3, 4)

# Success Criteria:
# - Token requested ONCE at start
# - Token reused for subsequent calls
# - Total: 1 token API call + 4 LLM API calls
```

**Test 4.3: Pre-configured Token (BFA_TOKEN_KEY)**
```bash
# Get a token manually first
TOKEN=$(curl -s -X POST "http://${BFA_HOST}:8000/api/token" \
  -H "Content-Type: application/json" \
  -d '{"subject":"rate-my-mr-test-123"}' | jq -r '.token')

# Configure with pre-set token
cat > mrproper.env <<EOF
GITLAB_ACCESS_TOKEN=glpat-your-token
BFA_HOST=api-gateway.internal.com
BFA_TOKEN_KEY=${TOKEN}
API_TIMEOUT=120
EOF

# Run validation
docker run --env-file mrproper.env ...

# Expected Logs:
# [DEBUG] Using new LLM adapter (BFA_HOST is configured)
# [DEBUG] LLM Adapter initialized - ...Token pre-configured: True
# [DEBUG] Using pre-configured BFA_TOKEN_KEY
# [DEBUG] Sending POST request to LLM API (attempt 1/3)...
# Should NOT see "Requesting JWT token from..."

# Success Criteria:
# - Uses pre-configured token
# - NO token API call made
# - Logs show "Using pre-configured BFA_TOKEN_KEY"
# - LLM API calls succeed with pre-configured token
```

**Test 4.4: Token Expiration / 401 Handling**
```bash
# Use expired or invalid token
BFA_TOKEN_KEY=expired_or_invalid_token docker run ...

# Expected Logs:
# [DEBUG] Using pre-configured BFA_TOKEN_KEY
# [DEBUG] Sending POST request to LLM API...
# [ERROR] LLM API HTTP Error (attempt 1): 401 Client Error: Unauthorized
# [ERROR] JWT token authentication failed (401 Unauthorized)
# [DEBUG] Client error 401, not retrying
# [ERROR] Failed to generate summary: 401 Client Error

# Success Criteria:
# - First LLM call fails with 401
# - Error logged: "JWT token authentication failed"
# - Token cache cleared
# - Error reported to GitLab
```

#### Test Suite 5: Integration Tests

**Test 5.1: Multiple Validators in Parallel**
```bash
# Trigger multiple validators at once
curl -X POST http://localhost:9912/mr-proper/rate-my-mr+mrproper-clang-format+mrproper-message \
  -d @test-payloads/mr-event.json

# Check multiple containers spawned
docker ps | grep "mr-"

# Success Criteria:
# - All validators started
# - Each has unique container
# - All use same REQUEST_ID
# - All complete successfully
# - Multiple discussions posted to GitLab
```

**Test 5.2: Concurrent MR Validations**
```bash
# Trigger validations for multiple MRs
for i in {1..5}; do
  curl -X POST http://localhost:9912/mr-proper/rate-my-mr \
    -d @test-payloads/mr-event-${i}.json &
done
wait

# Check all containers
docker ps -a | grep "mr-rate-my-mr"

# Success Criteria:
# - All validations started
# - Each has unique REQUEST_ID
# - No conflicts or race conditions
# - All complete successfully
# - Logs correlatable by REQUEST_ID
```

**Test 5.3: End-to-End GitLab Webhook Flow**
```bash
# 1. Create test MR in GitLab
# 2. Configure webhook URL pointing to server
# 3. Update MR or change state
# 4. Webhook triggered automatically
# 5. Observe validation and discussion

# Success Criteria:
# - Webhook received
# - Container spawned automatically
# - Validation completes
# - Discussion appears on MR within 2-5 minutes
# - Proper formatting and content
```

#### Test Suite 6: Error Handling & Recovery

**Test 6.1: GitLab API Unavailable**
```bash
# Block GitLab host temporarily
# Or use invalid GITLAB_ACCESS_TOKEN
# Trigger validation

# Success Criteria:
# - Error logged
# - Retry attempted
# - Graceful failure
# - Container exits with non-zero code
# - No crash or hang
```

**Test 6.2: AI Service / LLM Adapter Timeout**
```bash
# Set very low timeout
API_TIMEOUT=1 docker run ...

# Success Criteria:
# - Timeout detected after API_TIMEOUT seconds
# - Retry attempted
# - Eventually fails gracefully
# - Error reported to GitLab
```

**Test 6.3: Disk Space Full**
```bash
# Fill up /home/docker/tmp/mr-validator-logs
# Trigger validation

# Success Criteria:
# - Error logged (if possible)
# - Log rotation attempts to free space
# - Validation continues if possible
# - No system crash
```

#### Test Suite 7: Performance Tests

**Test 7.1: Large MR Validation**
```bash
# Create MR with 100+ files changed, 10,000+ LOC
# Trigger validation
# Monitor time and resources

# Success Criteria:
# - Validation completes (may take 10-15 minutes)
# - No memory leaks
# - No timeouts
# - Discussion posted successfully
```

**Test 7.2: Rate Limiting (LLM Adapter)**
```bash
# Trigger many validations quickly to hit rate limits
for i in {1..20}; do
  docker run ... &
done

# Success Criteria:
# - 429 errors detected
# - Retry logic engages
# - Eventually succeeds
# - No permanent failures
```

**Test 7.3: Token Acquisition Performance**
```bash
# Run 10 validations and measure time
# Compare: legacy mode vs new adapter mode

# Expected:
# - Token acquisition adds ~50-200ms per MR
# - Minimal impact on total validation time (~1%)
# - Token reuse working (not 4 token calls)
```

#### Test Suite 8: Debugging & Monitoring

**Test 8.1: Log Correlation**
```bash
# Trigger validation
# Extract REQUEST_ID from webhook log
REQUEST_ID_SHORT=$(grep "=== NEW WEBHOOK REQUEST ===" webhook-server.log | tail -1 | grep -o '\[[^]]*\]' | tr -d '[]')

# Find all logs with this REQUEST_ID
grep -r "$REQUEST_ID_SHORT" /home/docker/tmp/mr-validator-logs/

# Success Criteria:
# - REQUEST_ID found in webhook-server.log
# - REQUEST_ID found in rate-my-mr log
# - REQUEST_ID found in gitlab-api log
# - All logs correlatable
# - Can trace complete flow
```

**Test 8.2: Log Rotation**
```bash
# Trigger many validations to generate logs
# Check log file sizes
ls -lh /home/docker/tmp/mr-validator-logs/

# Check rotated files exist
ls -lh /home/docker/tmp/mr-validator-logs/webhook-server.log*
ls -lh /home/docker/tmp/mr-validator-logs/rate-my-mr-*.log*

# Success Criteria:
# - webhook-server.log rotates at 100MB
# - Up to 5 backup files
# - Validator logs rotate at 50MB
# - Up to 3 backup files per validator log
```

**Test 8.3: Debugging Information Quality**
```bash
# Review logs for completeness
cat /home/docker/tmp/mr-validator-logs/rate-my-mr-<request-id>.log

# Success Criteria:
# - REQUEST_ID in every log line
# - Timestamps present
# - Clear error messages
# - Stack traces on exceptions
# - API request/response details
# - Retry attempts logged
```

#### Test Execution Report Template

```markdown
# Test Execution Report

**Date**: YYYY-MM-DD
**Tester**: Name
**Environment**: Dev/Staging/Production
**Configuration**: Legacy/New Adapter

## Summary
- Total Tests: X
- Passed: X
- Failed: X
- Skipped: X
- Pass Rate: X%

## Test Results

### Suite 1: Infrastructure Tests
- [[OK]/[X]] Test 1.1: Docker Image Build
- [[OK]/[X]] Test 1.2: Webhook Server Startup
- [[OK]/[X]] Test 1.3: Log Directory Setup

... (continue for all tests)

## Failed Tests Details

### Test X.Y: Test Name
**Failure Reason**: ...
**Logs**: ...
**Action Items**: ...

## Performance Metrics
- Average validation time: X seconds
- Token acquisition time: X ms
- Peak memory usage: X MB
- Disk usage: X GB

## Issues Found
1. Issue description
2. Issue description

## Recommendations
1. Recommendation
2. Recommendation
```

#### Sample GitLab Webhook Payload

**test-payloads/mr-event.json**:
```json
{
  "object_kind": "merge_request",
  "user": {
    "username": "testuser"
  },
  "project": {
    "path_with_namespace": "test-org/test-project"
  },
  "object_attributes": {
    "iid": 123,
    "title": "Test MR for validation",
    "state": "opened",
    "source_branch": "feature/test",
    "target_branch": "main"
  },
  "changes": {}
}
```

#### Success Criteria Summary

**System is production-ready when**:
- [OK] All infrastructure tests pass
- [OK] All webhook tests pass
- [OK] All three validators work correctly
- [OK] Both legacy and new adapter modes work
- [OK] Error handling is robust
- [OK] Logging and debugging is comprehensive
- [OK] Performance is acceptable (<5 min for typical MR)
- [OK] Token reuse working (1 token call per MR)
- [OK] No memory leaks or resource issues
- [OK] Documentation is complete and accurate

**Estimated Time**: 4-6 hours for complete test suite

</details>

---

# Part 7: Technical Specifications

## Technical Specifications

### Architecture Overview

The MR Validator is a distributed system that provides automated code quality assessment for GitLab merge requests. It consists of:

1. **Webhook Server**: Receives GitLab webhook events and orchestrates validation
2. **Validator Containers**: Ephemeral Docker containers that perform actual MR analysis
3. **External Services**: GitLab API and BFA/AI Service for code analysis

**Key Features**:
- AI-powered code review and summary generation
- Lines of Code (LOC) analysis
- Cyclomatic complexity measurement
- Security scanning (Bandit)
- Lint disable pattern detection
- Automated quality scoring (1-5 stars)

### Component Details

#### 1. Webhook Server (`ratemymr-webhook-container`)

**Purpose**: Persistent HTTP server that receives GitLab webhook events and spawns validator containers

**Technology**:
- Python 3.8+ with Tornado web framework
- Docker API client

**Key Responsibilities**:
- Listen for GitLab webhook events on port 9912
- Parse webhook payload and extract MR metadata
- Spawn ephemeral Docker containers for each validator
- Manage environment variables and configuration
- Centralized logging coordination

**Container Details**:
- Image: `ratemymr-webhook-container`
- Port: `9912` (exposed to host, persistent)
- Restart Policy: `always`
- Environment: Loaded from `mrproper.env`

#### 2. Validator Container (`ratemymr-validate-container`)

**Purpose**: Ephemeral containers that perform MR analysis and quality assessment

**Technology**:
- Python 3.8+ with analysis libraries

**Container Details**:
- Image: `ratemymr-validate-container`
- Port: None (ephemeral, uses host network, no fixed port)
- Lifecycle: Created per validation, removed after completion
- Environment: Inherited from webhook server + MR-specific vars
- Git client for repository operations
- Bandit (security scanner)
- Radon (cyclomatic complexity)
- Custom AI integration (LLM adapter)

**Key Responsibilities**:
- Clone GitLab repository
- Generate git diff for analysis
- Call AI service for summary and code review
- Calculate LOC, complexity, security metrics
- Calculate quality rating (1-5)
- Post results to GitLab MR discussion

**Container Lifecycle**:
1. Created by webhook server on MR event
2. Runs analysis pipeline (~30-120 seconds)
3. Posts results to GitLab
4. Self-destructs (--rm flag)

**Container Naming Convention**:
```
mr-{validator}-{mr_iid}-{request_id_short}

Examples:
- mr-rate-my-mr-42-a3b4c5d6
- mr-mrproper-message-123-f7e8d9c0
- mr-mrproper-clang-format-456-1a2b3c4d
```

#### 3. External Services

**GitLab Instance**
- **Purpose**: Source code management, webhook source, result destination
- **Endpoints Used**:
  - `/api/v4/projects/:id/merge_requests/:iid` (GET MR data)
  - `/api/v4/projects/:id/merge_requests/:iid/commits` (GET commits)
  - `/api/v4/projects/:id/merge_requests/:iid/discussions` (POST results)
  - Git clone endpoint for repository access
- **Authentication**: GitLab Personal Access Token (API scope)

**BFA Service (AI/LLM Gateway)**
- **Purpose**: JWT-authenticated AI service for code analysis
- **Endpoints**:
  - `/api/token` (POST - JWT token acquisition)
  - `/api/rate-my-mr` (POST - AI analysis)
- **Authentication**: JWT Bearer tokens

### API Payloads

#### GitLab Webhook Payload

**Endpoint**: `POST http://webhook-server:9912/mr-proper/{validator}`

**Headers**:
```http
Content-Type: application/json
X-Gitlab-Event: Merge Request Hook
X-Gitlab-Token: <webhook_secret>
```

**Request Body** (Merge Request Event):
```json
{
  "object_kind": "merge_request",
  "event_type": "merge_request",
  "user": {
    "id": 123,
    "name": "John Doe",
    "username": "johndoe",
    "email": "john.doe@example.com"
  },
  "project": {
    "id": 456,
    "name": "my-project",
    "path_with_namespace": "my-org/my-project",
    "git_http_url": "https://gitlab.com/my-org/my-project.git"
  },
  "object_attributes": {
    "iid": 42,
    "title": "Add new authentication middleware",
    "state": "opened",
    "target_branch": "main",
    "source_branch": "feature/auth-middleware"
  },
  "changes": {}
}
```

**Key Fields Used by Validator**:
- `object_kind`: Must be "merge_request"
- `project.path_with_namespace`: Project identifier (e.g., "my-org/my-project")
- `object_attributes.iid`: MR internal ID (e.g., 42)
- `object_attributes.title`: MR title
- `user.username`: User who triggered the webhook

**Response**:
```http
HTTP/1.1 200 OK
Content-Type: text/plain

OK!
```

#### Token API (JWT Authentication)

**Endpoint**: `POST http://{BFA_HOST}:8000/api/token`

**Purpose**: Acquire JWT token for authenticating LLM API requests

**Request Headers**:
```http
Content-Type: application/json
```

**Request Body**:
```json
{
  "subject": "rate-my-mr-my-org%2Fmy-project-42"
}
```

**Subject Format**: `rate-my-mr-{url_encoded_project_id}-{mr_iid}`

**Response** (Success):
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Token Usage**:
- Token is acquired once per MR validation session
- Cached and reused for all AI calls (typically 4 calls: summary, review, etc.)
- Sent as Bearer token in Authorization header for LLM API requests
- Cleared on 401 errors to force re-authentication

#### LLM/BFA API

**Endpoint**: `POST http://{BFA_HOST}:8000/api/rate-my-mr`

**Purpose**: AI-powered code analysis (summary, code review)

**Request Headers**:
```http
Content-Type: application/json
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Request Body**:
```json
{
  "repo": "my-org/my-project",
  "branch": "feature/auth-middleware",
  "author": "john.doe@example.com",
  "commit": "abc123def456789012345678901234567890abcd",
  "mr_url": "https://gitlab.com/my-org/my-project/-/merge_requests/42",
  "prompt": "{\"messages\":[{\"role\":\"system\",\"content\":\"You are a senior software engineer...\"},{\"role\":\"user\",\"content\":\"Please analyze this git diff...\"}]}"
}
```

**Response** (Success):
```json
{
  "status": "ok",
  "repo": "my-org/my-project",
  "metrics": {
    "summary_text": "This merge request adds JWT authentication middleware..."
  }
}
```

**Timeout**: 120 seconds (configurable via `API_TIMEOUT`)

**Retry Logic**:
- Max retries: 3
- Backoff: Exponential (2s, 4s, 8s)
- Retry on: 5xx errors, 429 rate limit, connection errors
- No retry on: 4xx client errors (except 429)

#### GitLab API Integration

**1. Get Merge Request Data**

**Endpoint**: `GET https://gitlab.com/api/v4/projects/{project_id}/merge_requests/{mr_iid}`

**Headers**:
```http
PRIVATE-TOKEN: glpat-xxxxxxxxxxxxxxxxxxxx
```

**2. Get Merge Request Commits**

**Endpoint**: `GET https://gitlab.com/api/v4/projects/{project_id}/merge_requests/{mr_iid}/commits`

**3. Post Discussion (Results)**

**Endpoint**: `POST https://gitlab.com/api/v4/projects/{project_id}/merge_requests/{mr_iid}/discussions`

**Request Body**:
```json
{
  "body": "## Overall Rating: 4/5\n\n### Quality Assessment Results\n..."
}
```

### Container Communication

#### Communication Flow

```mermaid
sequenceDiagram
    participant GL as GitLab
    participant WS as Webhook Server
    participant VC as Validator Container
    participant BFA as BFA Service

    GL->>WS: 1. POST /mr-proper/rate-my-mr<br/>(MR webhook event)
    WS->>WS: 2. Parse webhook payload
    WS->>VC: 3. docker run -d --rm --env ...<br/>(spawn validator)
    WS->>GL: 4. HTTP 200 OK

    Note over VC: Container startup
    VC->>GL: 5. GET /api/v4/projects/{id}/merge_requests/{iid}
    GL->>VC: 6. MR metadata
    VC->>GL: 7. git fetch (clone repository)
    GL->>VC: 8. Repository data

    Note over VC: Generate git diff

    VC->>BFA: 9. POST /api/token<br/>{"subject": "rate-my-mr-..."}
    BFA->>VC: 10. {"token": "eyJhbGci..."}

    VC->>BFA: 11. POST /api/rate-my-mr<br/>Bearer Token<br/>(Summary request)
    BFA->>VC: 12. AI Summary

    VC->>BFA: 13. POST /api/rate-my-mr<br/>Bearer Token<br/>(Code review request)
    BFA->>VC: 14. AI Code Review

    Note over VC: Calculate LOC, Complexity,<br/>Security metrics

    Note over VC: Calculate rating (1-5)

    VC->>GL: 15. POST /api/v4/.../discussions<br/>(Quality report)
    GL->>VC: 16. HTTP 201 Created

    Note over VC: Container exits (--rm)
```

### Sequence Diagrams

#### Complete MR Validation Flow

```mermaid
sequenceDiagram
    autonumber
    participant Dev as Developer
    participant GL as GitLab
    participant WS as Webhook Server
    participant Docker as Docker Engine
    participant VC as Validator Container
    participant BFA as BFA Service
    participant Logs as Log Storage

    Dev->>GL: Create/Update MR
    GL->>WS: Webhook: MR Event

    rect rgb(200, 230, 201)
        Note over WS: Request Processing
        WS->>WS: Generate REQUEST_ID
        WS->>WS: Parse webhook payload
        WS->>WS: Validate checker names
        WS->>Logs: Log webhook received
    end

    rect rgb(243, 229, 245)
        Note over Docker,VC: Container Orchestration
        WS->>Docker: docker run -d --rm<br/>--env REQUEST_ID=...<br/>--volume {LOG_DIR}:{LOG_DIR}
        Docker->>VC: Create & start container
        WS->>GL: HTTP 200 OK (webhook processed)
    end

    rect rgb(255, 243, 224)
        Note over VC,GL: Repository Analysis
        VC->>Logs: Initialize validation log
        VC->>GL: GET MR data (API)
        GL->>VC: MR metadata
        VC->>GL: git fetch (clone)
        GL->>VC: Repository contents
        VC->>VC: Generate git diff
    end

    rect rgb(255, 249, 196)
        Note over VC,BFA: AI Analysis
        VC->>BFA: POST /api/token<br/>{"subject": "rate-my-mr-..."}
        BFA->>VC: JWT Token
        VC->>VC: Cache token for session

        loop AI Calls (Summary, Review, etc.)
            VC->>BFA: POST /api/rate-my-mr<br/>Bearer {token}
            BFA->>VC: AI Response
            VC->>VC: Parse & store results
        end
    end

    rect rgb(225, 245, 254)
        Note over VC: Quality Analysis
        VC->>VC: Calculate LOC metrics
        VC->>VC: Calculate cyclomatic complexity
        VC->>VC: Run security scan (Bandit)
        VC->>VC: Calculate rating (1-5)
        VC->>VC: Format report
    end

    rect rgb(200, 230, 201)
        Note over VC,GL: Post Results
        VC->>GL: POST /api/v4/.../discussions<br/>(Quality report)
        GL->>VC: HTTP 201 Created
        VC->>Logs: Write completion log
    end

    rect rgb(243, 229, 245)
        Note over Docker,VC: Cleanup
        VC->>VC: Exit (success/failure)
        Docker->>Docker: Remove container (--rm)
    end

    GL->>Dev: Email notification (new comment)
    Dev->>GL: View MR with quality report
```

---

# Part 8: Configuration Reference

## Configuration Reference

### Required Variables

| Variable | Description | Example | Used By |
|----------|-------------|---------|---------|
| `GITLAB_ACCESS_TOKEN` | GitLab Personal Access Token (API scope) | `glpat-xxxxxxxxxxxxxxxxxxxx` | Webhook Server, Validator |

### AI/LLM Service Configuration

| Variable | Required | Description | Default | Example | Used By |
|----------|----------|-------------|---------|---------|---------|
| `BFA_HOST` | Yes | BFA service hostname (without http://) | None | `api-gateway.internal.com` | Validator |
| `API_TIMEOUT` | No | API call timeout in seconds | `120` | `180` | Validator |
| `BFA_TOKEN_KEY` | No | Pre-configured JWT token (skips token API) | None | `eyJhbGciOiJIUzI1...` | Validator |
| `AI_SERVICE_URL` | No | Legacy direct AI service URL | None | `http://10.31.88.29:6006/generate` | Validator (fallback) |

### Logging Configuration

| Variable | Description | Default | Example | Used By |
|----------|-------------|---------|---------|---------|
| `LOG_DIR` | Base directory for all logs | `/home/docker/tmp/mr-validator-logs` | `/mnt/nfs/logs` | Webhook Server, Validator |
| `LOG_LEVEL` | Logging verbosity | `DEBUG` | `INFO`, `WARNING`, `ERROR` | Webhook Server, Validator |
| `LOG_MAX_BYTES` | Max size per log file before rotation | `52428800` (50MB) | `104857600` (100MB) | Validator |
| `LOG_BACKUP_COUNT` | Number of rotated log files to keep | `3` | `5` | Validator |
| `LOG_STRUCTURE` | Directory organization style | `organized` | `flat` | Validator |

### Auto-Set Variables (Runtime)

These are set automatically by the system and should not be configured manually:

| Variable | Description | Set By | Example |
|----------|-------------|--------|---------|
| `REQUEST_ID` | Unique request identifier | Webhook Server | `20250115_103000_123456` |
| `PROJECT_ID` | GitLab project path (URL encoded) | Webhook Server | `my-org%2Fmy-project` |
| `MR_IID` | Merge request internal ID | Webhook Server | `42` |
| `MR_REPO` | Repository name (decoded) | Validator | `my-org/my-project` |
| `MR_BRANCH` | Source branch name | Validator | `feature/auth-middleware` |
| `MR_AUTHOR` | MR author email | Validator | `john.doe@example.com` |
| `MR_COMMIT` | Latest commit SHA | Validator | `abc123def456...` |
| `MR_URL` | Full MR URL | Validator | `https://gitlab.com/...` |

---

# Appendices

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
    echo "[x] General error"
    ;;
  2)
    echo "[x] Configuration error - check mrproper.env"
    python manage_container.py config
    ;;
  3)
    echo "[x] Docker error - check Docker daemon"
    docker info
    ;;
  4)
    echo "[x] User cancelled"
    ;;
  *)
    echo "[x] Unknown error: $EXIT_CODE"
    ;;
esac

exit $EXIT_CODE
```

## Related Documentation

- [README.md](./README.md) - User & Operator Guide
- [ARCHITECTURE.md](./ARCHITECTURE.md) - Developer & Technical Guide

---

**Document Version**: 1.0
**Last Updated**: 2026-04-13
**Maintained By**: MR Validator Team
