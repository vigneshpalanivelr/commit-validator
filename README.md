# MR Validator - Automated GitLab Merge Request Validation

A comprehensive merge request validation system that automatically checks code formatting, commit message standards, and performs AI-powered quality assessment for GitLab projects using webhook-triggered Docker containers.

## Table of Contents

- [Quick Start](#quick-start)
- [System Overview](#system-overview)
- [Installation & Setup](#installation--setup)
- [Configuration](#configuration)
- [Validators](#validators)
- [Logging](#logging)
- [Troubleshooting](#troubleshooting)
- [Documentation](#documentation)

---

## Quick Start

### Prerequisites

- **Docker** and Docker CLI installed
- **GitLab Access Token** with API permissions
- **Python 3.8+** environment
- Network access to GitLab instance

### 1. Build Docker Images

```bash
./build-docker-images
```

**Expected Output**:
```
Building mrproper-webhook-vp-test...
Step 1/8 : FROM python:3.9-alpine
 ---> abc123...
...
Successfully built abc123def456
Successfully tagged mrproper-webhook-vp-test:latest

Building mr-checker-vp-test...
Step 1/12 : FROM ubuntu:22.04
 ---> def456...
...
Successfully built def456ghi789
Successfully tagged mr-checker-vp-test:latest

✅ Build complete: 2 images created
```

### 2. Configure Environment

Create `mrproper.env` with your GitLab token:

```bash
cat > mrproper.env <<EOF
GITLAB_ACCESS_TOKEN=glpat-xxxxxxxxxxxxxxxxxxxx
EOF
```

**Optional Configuration**:
```bash
# For custom AI service
AI_SERVICE_URL=http://custom-ai-server:8080/generate

# For new LLM adapter with JWT authentication
BFA_HOST=api-gateway.internal.com
API_TIMEOUT=120
BFA_TOKEN_KEY=eyJhbGci...  # Optional: pre-configured token

# Logging configuration
LOG_DIR=/home/docker/tmp/mr-validator-logs
LOG_LEVEL=INFO
LOG_STRUCTURE=organized
```

### 3. Start Server

```bash
./start-server
```

**Expected Output**:
```
Starting MR Validator webhook server...
Container ID: abc123def456...
Server listening on port 9912
✅ Webhook server started successfully

Test endpoint:
curl http://localhost:9912/mr-proper/rate-my-mr
```

### 4. Configure GitLab Webhook

**GitLab Project → Settings → Webhooks**

| Field | Value |
|-------|-------|
| **URL** | `http://your-server:9912/mr-proper/rate-my-mr` |
| **Secret Token** | Leave empty |
| **Trigger** | ☑ Merge request events |
| **SSL** | ☑ Enable SSL verification (if using HTTPS) |

**For multiple validators**:
```
http://your-server:9912/mr-proper/mrproper-clang-format+mrproper-message+rate-my-mr
```

**Test the webhook**:
```bash
curl -X POST http://your-server:9912/mr-proper/rate-my-mr \
  -H "Content-Type: application/json" \
  -d '{
    "object_kind": "merge_request",
    "project": {"path_with_namespace": "test/project"},
    "object_attributes": {"iid": 1, "title": "Test MR"},
    "user": {"username": "testuser"}
  }'
```

**Expected Response**:
```
OK!
```

---

## System Overview

The MR Validator is a webhook-driven validation system with two main components:

```mermaid
flowchart TB
    A[GitLab MR Event] -->|Webhook POST| B[Webhook Server<br/>Port 9912]
    B -->|Spawn| C1[Docker Container<br/>mrproper-clang-format]
    B -->|Spawn| C2[Docker Container<br/>mrproper-message]
    B -->|Spawn| C3[Docker Container<br/>rate-my-mr]
    C1 -->|GitLab API| D[Update MR Discussion]
    C2 -->|GitLab API| D
    C3 -->|AI Service| E[LLM Analysis]
    E -->|Results| C3
    C3 -->|GitLab API| D
    D -->|Notification| F[Developer]
```

### How It Works

1. **GitLab** sends webhook event when MR is created/updated
2. **Webhook Server** (Tornado) receives event and validates parameters
3. **Docker Containers** spawn for each requested validator
4. **Validators** analyze code, commits, and quality metrics
5. **Results** posted as GitLab MR discussions
6. **Developers** receive notifications and can address issues

### Key Features

- ✅ **Parallel Validation** - Multiple validators run concurrently
- ✅ **Container Isolation** - Each validation in separate Docker container
- ✅ **Auto-Resolution** - Discussions auto-resolve when issues fixed
- ✅ **Request Tracing** - Unique REQUEST_ID for end-to-end correlation
- ✅ **Structured Logging** - Pipe-separated, millisecond-precision logs
- ✅ **LLM Integration** - AI-powered code analysis with JWT authentication

---

## Installation & Setup

### Build Process

The system consists of two Docker images:

| Image | Base | Purpose | Size |
|-------|------|---------|------|
| `mrproper-webhook-vp-test` | Alpine Python 3.9 | Webhook HTTP server | ~150MB |
| `mr-checker-vp-test` | Ubuntu 22.04 | Validation execution | ~1.2GB |

#### Build Commands

```bash
# Build both images
./build-docker-images

# Build individually
docker build -t mrproper-webhook-vp-test -f webhook-server/Dockerfile .
docker build -t mr-checker-vp-test -f mrproper/Dockerfile .
```

**Expected Output**:
```
=== Building Webhook Server Image ===
[+] Building 45.2s (12/12) FINISHED
 => [internal] load build definition                0.1s
 => => transferring dockerfile: 890B                0.0s
 ...
 => exporting to image                              2.3s
 => => naming to docker.io/library/mrproper-webhook-vp-test:latest

=== Building Validator Image ===
[+] Building 120.5s (18/18) FINISHED
 => [internal] load build definition                0.1s
 ...
 => exporting to image                              5.8s
 => => naming to docker.io/library/mr-checker-vp-test:latest

✅ Build complete
```

#### Verify Images

```bash
docker images | grep -E "mrproper|mr-checker"
```

**Expected Output**:
```
mr-checker-vp-test          latest    def456    2 minutes ago   1.2GB
mrproper-webhook-vp-test    latest    abc123    5 minutes ago   152MB
```

### Dependencies

Python package dependencies are automatically installed during Docker build.

**Core Dependencies** (`mrproper/requirements.txt`):
```
requests>=2.28.0        # HTTP client for API calls
prettytable>=3.0.0      # Table formatting for reports
bandit>=1.7.0           # Security vulnerability scanning
radon>=5.1.0            # Code complexity analysis
tornado>=6.1            # Webhook server framework
```

**Install locally for development**:
```bash
cd mrproper
pip install -r requirements.txt
```

**Expected Output**:
```
Collecting requests>=2.28.0
  Downloading requests-2.31.0-py3-none-any.whl (62 kB)
Collecting prettytable>=3.0.0
  Downloading prettytable-3.10.0-py3-none-any.whl (27 kB)
...
Successfully installed bandit-1.7.5 prettytable-3.10.0 radon-6.0.1 requests-2.31.0 tornado-6.4
```

### Directory Structure

```
commit-validator/
├── webhook-server/                          # Webhook HTTP server
│   ├── server.py                            # Tornado webhook handler
│   └── Dockerfile                           # Alpine-based webhook image
│
├── mrproper/                                # Validation library
│   ├── bin/                                 # CLI entry points
│   │   ├── mrproper-clang-format            # Formatting validator
│   │   ├── mrproper-message                 # Message validator
│   │   └── rate-my-mr                       # AI quality validator
│   │
│   ├── mrproper/                            # Python modules
│   │   ├── __init__.py
│   │   ├── gitlab.py                        # GitLab API client
│   │   ├── git_format.py                    # Clang-format logic
│   │   ├── message.py                       # Message validation
│   │   │
│   │   └── rate_my_mr/                      # AI validator package
│   │       ├── __init__.py
│   │       ├── rate_my_mr_gitlab.py         # Main entry point
│   │       ├── rate_my_mr.py                # AI integration
│   │       ├── llm_adapter.py               # LLM JWT adapter
│   │       ├── loc.py                       # LOC analysis
│   │       ├── cal_rating.py                # Rating calculation
│   │       ├── cyclomatic_complexity.py     # Complexity analysis
│   │       ├── security_scan.py             # Security scanning
│   │       ├── params.py                    # Configuration
│   │       ├── utils.py                     # Utilities
│   │       └── logging_config.py            # Structured logging
│   │
│   ├── requirements.txt                     # Python dependencies
│   ├── setup.py                             # Package configuration
│   └── Dockerfile                           # Ubuntu-based validator image
│
├── mrproper.env                             # Environment configuration
├── build-docker-images                      # Build script
├── start-server                             # Server startup script
│
├── README.md                                # This file
├── ARCHITECTURE.md                          # Technical architecture
├── DEBUGGING_GUIDE.md                       # Troubleshooting guide
├── LLM_ADAPTER_IMPLEMENTATION.md            # LLM adapter details
├── COMPREHENSIVE_TEST_PLAN.md               # Testing procedures
└── LOGGING_CONFIGURATION.md                 # Logging setup guide
```

### Automated CI/CD Deployment

The system supports automated deployment via GitLab CI/CD.

**GitLab CI Variables** (Project Settings → CI/CD → Variables):

| Variable | Value | Protected | Masked | Description |
|----------|-------|-----------|--------|-------------|
| `GITLAB_ACCESS_TOKEN` | `glpat-xxx...` | ✓ | ✓ | GitLab API token |
| `LDOCKER_SSH_KEY` | `<base64-ssh-key>` | ✓ | ✗ | SSH private key for deployment |
| `AI_SERVICE_URL` | `http://10.31.88.29:6006/generate` | ✗ | ✗ | AI service endpoint |
| `BFA_HOST` | `api-gateway.internal.com` | ✗ | ✗ | LLM adapter host (optional) |

**CI Pipeline Flow**:

```mermaid
flowchart LR
    A[Git Push] --> B[Build Images]
    B --> C[SSH to Server]
    C --> D[Create mrproper.env]
    D --> E[Deploy Containers]
    E --> F[Verify Deployment]
```

**Deployment Steps**:
1. CI builds Docker images
2. Connects to target server via SSH
3. Creates `mrproper.env` from CI variables
4. Deploys webhook server container
5. Verifies deployment success

---

## Configuration

### Environment Variables

All configuration via `mrproper.env` file or environment variables.

#### Core Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GITLAB_ACCESS_TOKEN` | ✓ | - | GitLab API token (glpat-...) |
| `AI_SERVICE_URL` | ✗ | `http://10.31.88.29:6006/generate` | Legacy AI service URL |

#### LLM Adapter Configuration (New)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BFA_HOST` | ✗ | - | LLM adapter host (enables new adapter) |
| `API_TIMEOUT` | ✗ | `120` | API timeout in seconds |
| `BFA_TOKEN_KEY` | ✗ | - | Pre-configured JWT token |

#### Logging Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LOG_DIR` | ✗ | `/home/docker/tmp/mr-validator-logs` | Base log directory |
| `LOG_LEVEL` | ✗ | `DEBUG` | Logging level (DEBUG/INFO/WARNING/ERROR) |
| `LOG_MAX_BYTES` | ✗ | `52428800` | Max log file size (50MB) |
| `LOG_BACKUP_COUNT` | ✗ | `3` | Number of backup files |
| `LOG_STRUCTURE` | ✗ | `organized` | Log structure (organized/flat) |

### Configuration Examples

#### Basic Configuration (Legacy AI Service)

```bash
# mrproper.env
GITLAB_ACCESS_TOKEN=glpat-xxxxxxxxxxxxxxxxxxxx
AI_SERVICE_URL=http://10.31.88.29:6006/generate
```

#### Advanced Configuration (New LLM Adapter)

```bash
# mrproper.env
GITLAB_ACCESS_TOKEN=glpat-xxxxxxxxxxxxxxxxxxxx

# New LLM adapter with JWT authentication
BFA_HOST=api-gateway.internal.com
API_TIMEOUT=120
BFA_TOKEN_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Structured logging
LOG_DIR=/mnt/nfs/mr-validator-logs
LOG_LEVEL=INFO
LOG_STRUCTURE=organized
LOG_MAX_BYTES=104857600  # 100MB
LOG_BACKUP_COUNT=5
```

#### Production Configuration with NFS Logs

```bash
# mrproper.env
GITLAB_ACCESS_TOKEN=glpat-xxxxxxxxxxxxxxxxxxxx
BFA_HOST=api-gateway.internal.com

# NFS-mounted persistent logs
LOG_DIR=/mnt/nfs/mr-validator-logs
LOG_LEVEL=INFO
LOG_STRUCTURE=organized
```

### LLM Integration Modes

The system automatically detects which AI integration to use:

```mermaid
flowchart TD
    A[Rate-My-MR Starts] --> B{BFA_HOST<br/>configured?}
    B -->|Yes| C[LLM Adapter<br/>JWT Authentication]
    B -->|No| D[Legacy Direct<br/>No Authentication]
    C --> E[api-gateway.internal.com:8000<br/>Token: JWT]
    D --> F[10.31.88.29:6006<br/>Token: None]
    E --> G[LLM Service]
    F --> G
```

**Mode 1: Legacy Direct Connection** (default when `BFA_HOST` not set):
- Direct connection to AI service
- No authentication required
- URL: `http://10.31.88.29:6006/generate`

**Mode 2: LLM Adapter with JWT** (enabled when `BFA_HOST` set):
- Routes through BFA intermediary service
- JWT token authentication
- Token acquired once, reused for all AI calls
- Automatic retry with exponential backoff
- URL: `http://{BFA_HOST}:8000/api/rate-my-mr`

**See**: [LLM_ADAPTER_IMPLEMENTATION.md](./LLM_ADAPTER_IMPLEMENTATION.md) for complete details

### Project-Specific Configuration

Optional `.mr-proper.conf` in project repository root:

```ini
[message]
# Valid commit tags
valid_tags = BUG,FEATURE,IMPROVEMENT,REFACTOR,HOTFIX

# Tags that don't require ticket numbers
valid_tags_without_ticket = IMPROVEMENT,REFACTOR
```

### Webhook URL Patterns

| URL Pattern | Validators Executed |
|-------------|---------------------|
| `/mr-proper/mrproper-clang-format` | Code formatting only |
| `/mr-proper/mrproper-message` | Commit message only |
| `/mr-proper/rate-my-mr` | AI quality assessment only |
| `/mr-proper/mrproper-clang-format+mrproper-message` | Formatting + Message |
| `/mr-proper/mrproper-clang-format+mrproper-message+rate-my-mr` | All three validators |

---

## Validators

### 1. Code Formatting (`mrproper-clang-format`)

Validates C/C++ code formatting using clang-format with organizational standards.

**Features**:
- Per-commit analysis
- Automatic fix suggestions
- Auto-resolves when issues fixed

**Example Output**:
```
git format report
===================================================

✓ Commit abc123f: Added user authentication - formatting OK
✗ Commit def456a: Updated database schema - contains formatting errors
   • File: src/database.cpp
   • Line: 42
   • Use 'git format --fixup' to fix automatically

git format instructions: https://wiki.internal.com/git-format
WARNING: DO NOT RESOLVE MANUALLY - Will auto-resolve when fixed
```

**Test Manually**:
```bash
docker run --rm --env-file mrproper.env \
  mr-checker-vp-test mrproper-clang-format \
  vigneshpalanivelr%2Fcommit-validator 1
```

**Expected Output**:
```
Fetching MR data for project vigneshpalanivelr/commit-validator, MR #1...
Analyzing 3 commits...
  ✓ Commit 1/3: abc123f - formatting OK
  ✓ Commit 2/3: def456a - formatting OK
  ✓ Commit 3/3: ghi789b - formatting OK

✅ All commits pass formatting checks
Posting results to GitLab...
Done!
```

### 2. Commit Message Validation (`mrproper-message`)

Validates commit message format and standards.

**Format**: `TAG(TICKET): Subject`

**Validation Rules**:
- Tag must be in valid_tags list
- Subject must start with capital letter
- Subject must not end with period
- Reviewed-By trailers cross-referenced with GitLab approvals

**Example Output**:
```
commit message check report
=============================================

| Commit | Status |
|--------|--------|
|abc123f<br>`BUG(PROJ-123): Fix login issue`|✓|
|def456a<br>`FEATURE(PROJ-456): Add dark mode`|✓|
|ghi789b<br>`Added new feature`|✗ Missing tag format|

WARNING: 1 commit is missing `Reviewed-By` trailer
Hint: Use `git gitlab-apply-reviewers`
```

**Test Manually**:
```bash
docker run --rm --env-file mrproper.env \
  -e REQUEST_ID=test_$(date +%s)_12345678 \
  mr-checker-vp-test mrproper-message \
  vigneshpalanivelr%2Fcommit-validator 1
```

### 3. AI Quality Assessment (`rate-my-mr`)

Comprehensive AI-powered code quality analysis.

**Analysis Components**:

```mermaid
flowchart LR
    A[Rate-My-MR] --> B[AI Summary]
    A --> C[AI Code Review]
    A --> D[LOC Analysis]
    A --> E[Complexity]
    A --> F[Security Scan]
    A --> G[Lint Analysis]
    B --> H[Rating Calculation]
    C --> H
    D --> H
    E --> H
    F --> H
    G --> H
    H --> I[1-5 Star Score]
```

**Features**:
- AI-powered code review (4 LLM calls)
- Lines of code metrics
- Cyclomatic complexity analysis
- Security vulnerability scanning (Bandit)
- Lint disable pattern detection
- Overall quality rating (1-5 stars)

**Example Output**:
```
:star2: MR Quality Rating Report :star2:
========================================

## Overall Rating: 4/5
:star::star::star::star::white_circle:

### Quality Assessment Results
:white_check_mark: AI-powered summary generated successfully
:white_check_mark: Comprehensive AI code review completed
Lines Added: 156, Lines Removed: 23, Net Change: 133
WARNING: New Lint Disables: 2

### Scoring Breakdown
| Metric | Status | Impact |
|--------|--------|--------|
| Lines of Code | 133 lines | Within limits |
| Lint Disables | 2 new disables | WARNING: New lint suppressions |

**Final Score**: 4/5 points
:white_check_mark: Quality assessment passed - MR meets quality standards
```

**Test Manually**:
```bash
docker run --rm --env-file mrproper.env \
  -e REQUEST_ID=test_$(date +%s)_87654321 \
  -e PROJECT_ID=vigneshpalanivelr/commit-validator \
  -e MR_IID=1 \
  mr-checker-vp-test rate-my-mr \
  vigneshpalanivelr%2Fcommit-validator 1
```

**Expected Output**:
```
2025-11-09 10:15:23.456 | INFO     | rate_my_mr.gitlab              | 87654321 | Starting MR analysis | project=vigneshpalanivelr/commit-validator mr_iid=1
2025-11-09 10:15:23.567 | INFO     | rate_my_mr.gitlab              | 87654321 | MR fetched successfully | title="Update documentation"
2025-11-09 10:15:24.123 | INFO     | rate_my_mr.llm_adapter         | 87654321 | JWT token acquired | duration_ms=234
2025-11-09 10:15:26.789 | INFO     | rate_my_mr.rate_my_mr          | 87654321 | AI summary completed | success=True
2025-11-09 10:15:29.012 | INFO     | rate_my_mr.rate_my_mr          | 87654321 | AI code review completed | success=True
2025-11-09 10:15:29.345 | INFO     | rate_my_mr.loc                 | 87654321 | LOC calculated | added=156 removed=23 net=133
2025-11-09 10:15:29.567 | INFO     | rate_my_mr.cal_rating          | 87654321 | Rating calculated | score=4.0
2025-11-09 10:15:29.890 | INFO     | rate_my_mr.gitlab              | 87654321 | Report posted to GitLab
2025-11-09 10:15:29.890 | INFO     | rate_my_mr.gitlab              | 87654321 | MR analysis completed | duration_ms=6434
```

---

## Logging

### Structured Logging Format

All validators use **pipe-separated, structured logging** for easy parsing:

**Format**:
```
YYYY-MM-DD HH:MM:SS.mmm | LEVEL    | module.name                    | REQ_ID   | Message | key=value
```

**Features**:
- ✅ Millisecond precision timestamps
- ✅ Column-aligned for visual scanning
- ✅ Correlation IDs (REQUEST_ID_SHORT) for request tracing
- ✅ Structured key=value pairs
- ✅ Organized directory structure (by date/project/MR)

### Log Directory Structure

**Organized Structure** (default when `LOG_STRUCTURE=organized`):

```
/home/docker/tmp/mr-validator-logs/
├── webhook/
│   └── 2025-11-09/
│       └── webhook-server.log
│
└── validations/
    └── 2025-11-09/
        └── vigneshpalanivelr_commit-validator/
            └── mr-42/
                └── rate-my-mr-87654321.log
```

**Flat Structure** (when `LOG_STRUCTURE=flat`):

```
/home/docker/tmp/mr-validator-logs/
├── webhook-server.log
├── rate-my-mr-87654321-container123.log
└── gitlab-api-87654321-container123.log
```

### Viewing Logs

**Find logs for specific MR**:
```bash
# Organized structure
LOG_DIR=/home/docker/tmp/mr-validator-logs
PROJECT="vigneshpalanivelr_commit-validator"
MR_IID=42
DATE=$(date +%Y-%m-%d)

tail -f $LOG_DIR/validations/$DATE/$PROJECT/mr-$MR_IID/*.log
```

**Expected Output**:
```
2025-11-09 10:15:23.456 | INFO     | rate_my_mr.gitlab              | 87654321 | Starting MR analysis | project=vigneshpalanivelr/commit-validator mr_iid=42
2025-11-09 10:15:23.567 | DEBUG    | rate_my_mr.gitlab              | 87654321 | Fetching MR details | mr_iid=42
2025-11-09 10:15:23.890 | INFO     | rate_my_mr.gitlab              | 87654321 | MR fetched successfully | title="Update docs" state=opened
```

**Trace by REQUEST_ID**:
```bash
# Find all logs for specific request
grep "87654321" /home/docker/tmp/mr-validator-logs/**/**/**/*.log
```

**Monitor webhook server**:
```bash
tail -f /home/docker/tmp/mr-validator-logs/webhook/$(date +%Y-%m-%d)/webhook-server.log
```

**See**: [LOGGING_CONFIGURATION.md](./LOGGING_CONFIGURATION.md) for complete logging setup guide

---

## Troubleshooting

### Quick Diagnostics

**Check webhook server status**:
```bash
docker ps | grep webhook
```

**Expected Output**:
```
abc123def456   mrproper-webhook-vp-test   "/bin/sh -c 'python…"   10 minutes ago   Up 10 minutes   0.0.0.0:9912->9912/tcp   mrproper-webhook-vp-test
```

**Check recent validation containers**:
```bash
docker ps -a | grep mr-checker-vp-test | head -5
```

**Expected Output**:
```
def456ghi789   mr-checker-vp-test   "rate-my-mr vignesh…"   2 minutes ago   Exited (0) 2 minutes ago                      mr-rate-my-mr-42-87654321
ghi789jkl012   mr-checker-vp-test   "mrproper-message v…"   5 minutes ago   Exited (0) 5 minutes ago                      mr-mrproper-message-42-12345678
```

**View webhook logs**:
```bash
docker logs mrproper-webhook-vp-test --tail 50
```

**Expected Output**:
```
2025-11-09 10:15:20.123 | INFO     | webhook.server                 | unknown  | Webhook server started | port=9912
2025-11-09 10:15:23.456 | INFO     | webhook.server                 | 87654321 | Webhook received | project=vigneshpalanivelr/commit-validator mr_iid=42
2025-11-09 10:15:23.567 | INFO     | webhook.server                 | 87654321 | Spawning validator | validator=rate-my-mr
```

### Common Issues

#### Issue: Webhook Not Responding

**Symptom**: No containers spawned when MR created/updated

**Diagnosis**:
```bash
# Check if webhook server is running
docker ps | grep webhook

# Test webhook endpoint
curl -X POST http://your-server:9912/mr-proper/rate-my-mr
```

**Expected Response**:
```
OK!
```

**Solutions**:
- Verify webhook server container is running
- Check GitLab webhook URL is correct
- Check port 9912 is accessible
- Review webhook server logs

#### Issue: GitLab API Errors (401 Unauthorized)

**Symptom**: Validator logs show "401 Unauthorized" or "Sorry, unauthorized"

**Diagnosis**:
```bash
# Test GitLab API access
source mrproper.env
curl -H "PRIVATE-TOKEN: $GITLAB_ACCESS_TOKEN" \
     https://git.internal.com/api/v4/projects | jq '.[] | {id, name}'
```

**Expected Output**:
```json
{
  "id": 123,
  "name": "commit-validator"
}
{
  "id": 456,
  "name": "another-project"
}
```

**Solutions**:
- Verify `GITLAB_ACCESS_TOKEN` is correct in `mrproper.env`
- Ensure token has `api` scope
- Check token hasn't expired
- Verify GitLab host in `gitlab.py` matches your instance

#### Issue: AI Service Connectivity

**Symptom**: AI validation fails or times out

**Diagnosis**:
```bash
# Test AI service
curl -X POST http://10.31.88.29:6006/generate \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "test"}],
    "temperature": 0.7
  }' | jq
```

**Expected Output**:
```json
{
  "response": "Test response from AI service",
  "tokens": 42
}
```

**Solutions**:
- Verify AI service is running
- Check network connectivity from validator containers
- Review `AI_SERVICE_URL` configuration
- Check firewall rules

#### Issue: Container Fails Immediately

**Symptom**: Validator containers exit with non-zero status

**Diagnosis**:
```bash
# Find recent failed containers
docker ps -a | grep "Exited ([1-9]" | grep mr-checker

# View logs of failed container
docker logs <container-id>
```

**Common Causes**:
- Missing `mrproper.env` file
- Wrong Docker image name
- Missing dependencies
- Python module import errors

**Solution**:
```bash
# Rebuild images with latest dependencies
./build-docker-images

# Test manual run
docker run --rm --env-file mrproper.env \
  mr-checker-vp-test rate-my-mr \
  test%2Fproject 1
```

### Debug Workflow

```mermaid
flowchart TD
    A[Issue Reported] --> B{Webhook<br/>responding?}
    B -->|No| C[Check webhook server<br/>docker ps grep webhook]
    B -->|Yes| D{Containers<br/>spawning?}
    D -->|No| E[Check webhook logs<br/>docker logs webhook]
    D -->|Yes| F{Containers<br/>succeeding?}
    F -->|No| G[Check container logs<br/>docker logs container-id]
    F -->|Yes| H{Results posting<br/>to GitLab?}
    H -->|No| I[Test GitLab API<br/>curl with token]
    H -->|Yes| J[Check MR discussions<br/>in GitLab UI]

    C --> K[Restart: ./start-server]
    E --> L[Check mrproper.env]
    G --> M[Check dependencies<br/>./build-docker-images]
    I --> N[Verify GITLAB_ACCESS_TOKEN]
```

### Request ID Correlation

Every webhook request generates a unique REQUEST_ID for end-to-end tracing.

**Format**: `webhook_YYYYMMDD_HHMMSS_XXXXXXXX`
**Short Form**: `XXXXXXXX` (last 8 characters)

**Example**:
- Full: `webhook_20251109_101523_87654321`
- Short: `87654321`

**Trace complete request flow**:
```bash
REQUEST_ID_SHORT="87654321"

# Search all logs
grep -r "$REQUEST_ID_SHORT" /home/docker/tmp/mr-validator-logs/
```

**Expected Output**:
```
/home/docker/tmp/mr-validator-logs/webhook/2025-11-09/webhook-server.log:
2025-11-09 10:15:23.456 | INFO     | webhook.server | 87654321 | Webhook received | project=vigneshpalanivelr/commit-validator mr_iid=42

/home/docker/tmp/mr-validator-logs/validations/2025-11-09/vigneshpalanivelr_commit-validator/mr-42/rate-my-mr-87654321.log:
2025-11-09 10:15:23.567 | INFO     | rate_my_mr.gitlab | 87654321 | Starting MR analysis | project=vigneshpalanivelr/commit-validator mr_iid=42
2025-11-09 10:15:29.890 | INFO     | rate_my_mr.gitlab | 87654321 | MR analysis completed | duration_ms=6434
```

**See**: [DEBUGGING_GUIDE.md](./DEBUGGING_GUIDE.md) for comprehensive troubleshooting procedures

---

## Documentation

### Core Documentation

| Document | Purpose | Audience |
|----------|---------|----------|
| [README.md](./README.md) | Setup and quick start | Users, Operators |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | System design and internals | Developers, DevOps |
| [DEBUGGING_GUIDE.md](./DEBUGGING_GUIDE.md) | Troubleshooting procedures | Operators, Support |
| [LLM_ADAPTER_IMPLEMENTATION.md](./LLM_ADAPTER_IMPLEMENTATION.md) | LLM JWT adapter details | Developers, Integrators |
| [COMPREHENSIVE_TEST_PLAN.md](./COMPREHENSIVE_TEST_PLAN.md) | Testing procedures | QA, Developers |
| [LOGGING_CONFIGURATION.md](./LOGGING_CONFIGURATION.md) | Logging setup guide | Operators, DevOps |

### Quick Links by Topic

| Topic | Link |
|-------|------|
| **System Architecture** | [ARCHITECTURE.md](./ARCHITECTURE.md) |
| **LLM Integration** | [LLM_ADAPTER_IMPLEMENTATION.md](./LLM_ADAPTER_IMPLEMENTATION.md) |
| **Structured Logging** | [LOGGING_CONFIGURATION.md](./LOGGING_CONFIGURATION.md) |
| **REQUEST_ID Tracing** | [DEBUGGING_GUIDE.md - REQUEST_ID Section](./DEBUGGING_GUIDE.md#request_id-your-debugging-superpower) |
| **Testing Procedures** | [COMPREHENSIVE_TEST_PLAN.md](./COMPREHENSIVE_TEST_PLAN.md) |
| **Webhook Configuration** | [Configuration](#configuration) above |

---

## Contributing

### Development Setup

```bash
# 1. Clone repository
git clone <repository-url>
cd commit-validator

# 2. Build development images
./build-docker-images

# 3. Create test environment
cp mrproper.env.example mrproper.env
# Edit mrproper.env with your token

# 4. Start development server
./start-server

# 5. Test webhook
curl -X POST http://localhost:9912/mr-proper/rate-my-mr
```

### Adding New Validators

See [Integration Guide](#validators) section above for step-by-step instructions.

### Code Standards

- Follow existing module patterns in `mrproper/mrproper/`
- Add comprehensive logging with structured fields
- Include REQUEST_ID in all log messages
- Update documentation and tests
- Test with real GitLab MR before merging

---

## License

Internal use - see company licensing policies.

---

**MR Validator** - Comprehensive automated code quality enforcement integrated directly into the GitLab development workflow.
