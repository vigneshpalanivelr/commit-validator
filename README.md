# MR Validator - GitLab Merge Request Quality Assessment

Automated MR validation with AI-powered code review, security scanning, and quality metrics.

## Quick Start

### Prerequisites
- Docker 20.10+
- GitLab Access Token (API scope)
- Python 3.8+ (for local development)

### Build & Install

```bash
# Build Docker images
./build-docker-images
```

**Expected output:**
```
Building mrproper-webhook-vp-test...
Successfully tagged mrproper-webhook-vp-test:latest
Building mr-checker-vp-test...
Successfully tagged mr-checker-vp-test:latest
```

### Configure

Create `mrproper.env`:
```bash
# Required
GITLAB_ACCESS_TOKEN=glpat-xxxxxxxxxxxxxxxxxxxx

# AI Service (BFA mode - recommended)
BFA_HOST=api-gateway.internal.com
API_TIMEOUT=120

# Logging
LOG_DIR=/home/docker/tmp/mr-validator-logs
LOG_LEVEL=INFO
LOG_STRUCTURE=organized
```

### Run

```bash
./start-server
```

**Expected output:**
```
Starting webhook server on port 9912...
Server ready: http://0.0.0.0:9912
```

### Configure GitLab Webhook

**Settings > Webhooks:**
- URL: `http://your-server:9912/mr-proper/rate-my-mr`
- Trigger: Merge request events

**Test:**
```bash
curl -X POST http://localhost:9912/mr-proper/rate-my-mr \
  -H "Content-Type: application/json" \
  -d '{"object_kind":"merge_request","project":{"path_with_namespace":"org/repo"},"object_attributes":{"iid":1}}'
```

---

## Configuration

### Environment Variables (.env.example)

```bash
# =============================================================================
# Required
# =============================================================================
GITLAB_ACCESS_TOKEN=glpat-xxxxxxxxxxxxxxxxxxxx

# =============================================================================
# AI/LLM Service
# =============================================================================
# BFA Mode (recommended) - JWT authenticated
BFA_HOST=api-gateway.internal.com
API_TIMEOUT=120
# BFA_TOKEN_KEY=eyJhbGci...  # Optional: pre-configured token

# Legacy Mode (fallback if BFA_HOST not set)
# AI_SERVICE_URL=http://10.31.88.29:6006/generate

# =============================================================================
# Logging
# =============================================================================
LOG_DIR=/home/docker/tmp/mr-validator-logs
LOG_LEVEL=DEBUG                    # DEBUG, INFO, WARNING, ERROR
LOG_MAX_BYTES=52428800             # 50MB per file
LOG_BACKUP_COUNT=3                 # Rotated files to keep
LOG_STRUCTURE=organized            # organized or flat
```

<details>
<summary><b>Click to expand: Complete Environment Variable Reference</b></summary>

#### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `GITLAB_ACCESS_TOKEN` | GitLab personal access token with API scope | `glpat-xxxxxxxxxxxxxxxxxxxx` |

#### AI/LLM Service Variables

| Variable | Required | Description | Default | Example |
|----------|----------|-------------|---------|---------|
| `BFA_HOST` | Yes (for BFA mode) | BFA service hostname | None | `api-gateway.internal.com` |
| `API_TIMEOUT` | No | API call timeout in seconds | `120` | `180` |
| `BFA_TOKEN_KEY` | No | Pre-configured JWT token (skips token API) | None | `eyJhbGciOiJIUzI1...` |
| `AI_SERVICE_URL` | No (legacy) | Direct AI service URL | None | `http://10.31.88.29:6006/generate` |

#### Logging Variables

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `LOG_DIR` | Base directory for all logs | `/home/docker/tmp/mr-validator-logs` | `/mnt/nfs/logs` |
| `LOG_LEVEL` | Logging verbosity | `DEBUG` | `INFO`, `WARNING`, `ERROR` |
| `LOG_MAX_BYTES` | Max size per log file before rotation | `52428800` (50MB) | `104857600` (100MB) |
| `LOG_BACKUP_COUNT` | Number of rotated log files to keep | `3` | `5` |
| `LOG_STRUCTURE` | Directory organization style | `organized` | `flat` |

#### Auto-Set Variables (by system)

| Variable | Description | Set By |
|----------|-------------|--------|
| `PROJECT_ID` | GitLab project path (URL encoded) | `rate_my_mr_gitlab.py` |
| `MR_IID` | Merge request internal ID | `rate_my_mr_gitlab.py` |
| `REQUEST_ID` | Unique request identifier | Webhook server |
| `MR_REPO` | Repository name | `rate_my_mr_gitlab.py` |
| `MR_BRANCH` | Source branch name | `rate_my_mr_gitlab.py` |
| `MR_AUTHOR` | MR author email | `rate_my_mr_gitlab.py` |
| `MR_COMMIT` | Latest commit SHA | `rate_my_mr_gitlab.py` |
| `MR_URL` | Full MR URL | `rate_my_mr_gitlab.py` |

#### Production Configuration Examples

**High-traffic production:**
```bash
LOG_LEVEL=INFO
LOG_MAX_BYTES=104857600    # 100MB
LOG_BACKUP_COUNT=5
LOG_STRUCTURE=organized
```

**Development/debugging:**
```bash
LOG_LEVEL=DEBUG
LOG_MAX_BYTES=52428800     # 50MB
LOG_BACKUP_COUNT=3
LOG_STRUCTURE=organized
```

**Disk space constrained:**
```bash
LOG_LEVEL=WARNING
LOG_MAX_BYTES=10485760     # 10MB
LOG_BACKUP_COUNT=1
LOG_STRUCTURE=flat
```

</details>

### Repository Configuration (.rate-my-mr.yaml)

Place in repository root to customize per-project:

```yaml
# Feature toggles
features:
  ai_summary: true
  ai_code_review: true
  loc_analysis: true
  lint_disable_check: true
  cyclomatic_complexity: true
  security_scan: true

# Thresholds
loc:
  max_lines: 500

cyclomatic_complexity:
  max_average: 10

security:
  fail_on_high: true
  ignored_tests: []  # e.g., ['B101', 'B311']

lint:
  max_new_disables: 10

rating:
  pass_score: 3
```

**Example: Disable AI features for faster validation:**
```yaml
features:
  ai_summary: false
  ai_code_review: false
```

**Example: Strict security policy:**
```yaml
security:
  fail_on_high: true
  fail_on_medium: true
```

<details>
<summary><b>Click to expand: Complete .rate-my-mr.yaml Configuration Reference</b></summary>

```yaml
# =============================================================================
# Rate My MR - Full Configuration Reference
# =============================================================================

# Feature toggles - enable/disable specific analysis types
features:
  ai_summary: true            # AI-generated MR summary
  ai_code_review: true        # AI-powered code review feedback
  loc_analysis: true          # Lines of Code change analysis
  lint_disable_check: true    # Check for new lint disable statements
  cyclomatic_complexity: true # Code complexity analysis
  security_scan: true         # Bandit security vulnerability scan

# Lines of Code thresholds
loc:
  max_lines: 500              # Maximum allowed net lines changed
  warning_threshold: 300      # Threshold for warning

# Cyclomatic Complexity settings
cyclomatic_complexity:
  max_average: 10             # Maximum average complexity score
  max_per_method: 15          # Maximum complexity per method
  show_top_n_methods: 5       # Number of high-complexity methods to show

# Security scan settings
security:
  fail_on_high: true          # Block MR on HIGH severity issues
  fail_on_medium: false       # Block MR on MEDIUM severity issues
  max_issues_per_loc: 0.05    # Max security issues per line of code (5%)
  ignored_tests: []           # Bandit test IDs to ignore (e.g., ['B101', 'B311'])
  show_max_issues: 10         # Maximum issues to display in report

# Lint disable settings
lint:
  allowed_disables: []        # Allowed lint disable patterns
  max_new_disables: 10        # Maximum new lint disables allowed

# Rating calculation settings
rating:
  pass_score: 3               # Minimum score to pass (out of 5)
  deduct_for_high_loc: true   # Deduct points for exceeding LOC limit
  deduct_for_lint_disables: true  # Deduct points for lint disables

# Report customization
report:
  show_ai_content: true       # Show AI summary/review in collapsible sections
  show_security_details: true # Show detailed security issue information
  show_cc_breakdown: true     # Show per-method complexity breakdown
```

#### Example Configurations

**Minimal (disable AI for speed):**
```yaml
features:
  ai_summary: false
  ai_code_review: false
loc:
  max_lines: 1000
```

**Data Science Project (relaxed complexity):**
```yaml
loc:
  max_lines: 2000
cyclomatic_complexity:
  max_average: 15
security:
  ignored_tests:
    - B101  # assert used
    - B311  # random not for crypto
```

**Legacy Codebase:**
```yaml
cyclomatic_complexity:
  max_average: 20
  max_per_method: 25
lint:
  max_new_disables: 50
rating:
  pass_score: 2
```

**Security-Critical Application:**
```yaml
security:
  fail_on_high: true
  fail_on_medium: true
  show_max_issues: 20
rating:
  pass_score: 4
```

</details>

### Webhook URL Patterns

| URL | Validators |
|-----|-----------|
| `/mr-proper/rate-my-mr` | AI quality assessment |
| `/mr-proper/mrproper-clang-format` | Code formatting |
| `/mr-proper/mrproper-message` | Commit messages |
| `/mr-proper/rate-my-mr+mrproper-message` | Multiple validators |

---

## Validators

### AI Quality Assessment (rate-my-mr)

```mermaid
flowchart LR
    A[MR Diff] --> B[AI Summary]
    A --> C[Code Review]
    A --> D[LOC Analysis]
    A --> E[Lint Check]
    A --> F[Security Scan]
    A --> G[Complexity]
    B & C & D & E & F & G --> H[Rating 1-5]
```

**Test manually:**
```bash
docker run --rm --env-file mrproper.env \
  -e REQUEST_ID=test_$(date +%s)_12345678 \
  -e PROJECT_ID=org/repo \
  -e MR_IID=42 \
  mr-checker-vp-test rate-my-mr org%2Frepo 42
```

**Expected log output:**
```
2025-11-17 10:15:23.456 | INFO  | main           | 12345678 | Starting MR analysis
2025-11-17 10:15:24.123 | INFO  | llm-adapter    | 12345678 | JWT token acquired
2025-11-17 10:15:26.789 | INFO  | rate-my-mr     | 12345678 | AI summary completed | success=True
2025-11-17 10:15:29.012 | INFO  | loc-analyzer   | 12345678 | LOC calculated | added=156 removed=23
2025-11-17 10:15:29.567 | INFO  | security-scan  | 12345678 | Security scan completed | high=0 medium=1
2025-11-17 10:15:29.890 | INFO  | main           | 12345678 | Final rating: 4/5
```

**GitLab MR Comment Example:**
```
## Overall Rating: 4/5

### Quality Assessment Results

#### :mag: Summary Analysis
:white_check_mark: AI-powered summary generated successfully

<details>
<summary>Click to expand AI Summary</summary>
This MR adds authentication middleware...
</details>

#### :cyclone: Cyclomatic Complexity Analysis
- **Average Complexity**: 8 (Good)
- **Methods Analyzed**: 12

#### :shield: Security Scan Analysis
- **HIGH Severity Issues**: 0
- **MEDIUM Severity Issues**: 1
- **LOW Severity Issues**: 3
```

### Code Formatting (mrproper-clang-format)

```bash
docker run --rm --env-file mrproper.env \
  mr-checker-vp-test mrproper-clang-format org%2Frepo 42
```

### Commit Message (mrproper-message)

```bash
docker run --rm --env-file mrproper.env \
  mr-checker-vp-test mrproper-message org%2Frepo 42
```

---

## Troubleshooting

### Quick Diagnostics

```bash
# Check webhook server
docker ps | grep webhook
curl http://localhost:9912/

# Check recent validations
docker ps -a | grep mr-checker | head -5

# View webhook logs
docker logs mrproper-webhook-vp-test --tail 50

# Find logs for specific MR
ls /home/docker/tmp/mr-validator-logs/validations/$(date +%Y-%m-%d)/*/mr-42/
```

### Common Issues

| Issue | Diagnosis | Solution |
|-------|-----------|----------|
| No containers spawned | `grep "container started" webhook-server.log` | Check mrproper.env exists |
| 401 Unauthorized | `grep "401" rate-my-mr-*.log` | Verify GITLAB_ACCESS_TOKEN |
| AI service timeout | `grep "Timeout" rate-my-mr-*.log` | Check BFA_HOST reachable |
| Wrong API URL | `grep "bfa_url" rate-my-mr-*.log` | Ensure BFA_HOST is set |

### Debug by REQUEST_ID

Every request has unique ID for correlation:

```bash
# Find REQUEST_ID
grep "NEW WEBHOOK" webhook-server.log | tail -1
# Output: [87654321] === NEW WEBHOOK REQUEST ===

# Trace full flow
grep "87654321" /home/docker/tmp/mr-validator-logs/**/**/**/*.log
```

### Log Module Names

| Module Name | Description |
|-------------|-------------|
| `main` | Main validator orchestrator |
| `rate-my-mr` | AI analysis coordinator |
| `llm-adapter` | LLM/BFA API client |
| `loc-analyzer` | Lines of code metrics |
| `cc-analyzer` | Cyclomatic complexity |
| `security-scan` | Bandit security scanner |
| `config-loader` | Repository config loader |
| `rating-calc` | Final score calculator |

<details>
<summary><b>Click to expand: Complete Troubleshooting Scenarios</b></summary>

#### Scenario 1: Container Starts But Fails Immediately

**Symptoms:** Container in `docker ps -a` with non-zero exit code

**Debug Steps:**
```bash
# 1. Check webhook log for container start
grep "\[12345678\] Checker rate-my-mr container" webhook-server.log

# 2. Check validator log for startup errors
head -50 /home/docker/tmp/mr-validator-logs/rate-my-mr-*12345678*.log

# 3. Check exit code
docker inspect mr-rate-my-mr-42-12345678 --format='{{.State.ExitCode}}'
# Exit codes: 0=Success, 1=Error, 137=OOM, 139=Segfault
```

**Common causes:**
- Missing environment variables (GITLAB_ACCESS_TOKEN, BFA_HOST)
- GitLab API authentication failure
- Git clone failure (network, permissions)

#### Scenario 2: Container Never Starts

**Symptoms:** No container found in `docker ps -a`

**Debug Steps:**
```bash
# Check webhook log for docker command failure
grep -A 5 "\[12345678\] Failed to start checker" webhook-server.log

# Check Docker daemon
docker info
```

**Common causes:**
- Docker image not found: `mr-checker-vp-test`
- Docker daemon not responding
- mrproper.env file missing
- Insufficient Docker permissions

#### Scenario 3: Container Runs But AI Service Fails

**Symptoms:** Container exits, but analysis incomplete

**Debug Steps:**
```bash
# Search for AI service errors
grep "AI Service\|LLM API" /path/to/rate-my-mr-*.log | grep -i error

# Check retry attempts
grep "Retry attempt" /path/to/rate-my-mr-*.log

# Check BFA connectivity
curl -s http://${BFA_HOST}:8000/health
```

**Expected retry logs:**
```
[DEBUG] AI Service Connection Error (attempt 1): ...
[DEBUG] Retry attempt 2/3 after 2s wait...
[DEBUG] AI Service Connection Error (attempt 2): ...
[DEBUG] Retry attempt 3/3 after 4s wait...
[ERROR] All 3 attempts failed - AI service not reachable
```

**Common causes:**
- BFA_HOST misconfigured
- AI service timeout (>120s per attempt)
- AI service returns 5xx errors
- Network connectivity issues

#### Scenario 4: Container Runs But No GitLab Comment

**Symptoms:** Container exits successfully (code 0) but no comment on MR

**Debug Steps:**
```bash
# Search for GitLab API posting
grep "Posting discussion" /path/to/rate-my-mr-*.log

# Check for posting errors
grep "Failed to post" /path/to/rate-my-mr-*.log

# Test GitLab API
curl -H "PRIVATE-TOKEN: $GITLAB_ACCESS_TOKEN" \
  "https://gitlab.com/api/v4/user"
```

**Common causes:**
- GITLAB_ACCESS_TOKEN invalid or expired
- Insufficient GitLab permissions (need API scope)
- Network issues reaching GitLab API
- MR already merged/closed

#### Scenario 5: Container Stuck/Hanging

**Symptoms:** Container running for >10 minutes

**Debug Steps:**
```bash
# Check if container is still running
docker ps | grep mr-rate-my-mr-42-12345678

# Check resource usage
docker stats mr-rate-my-mr-42-12345678 --no-stream

# Check processes inside container
docker top mr-rate-my-mr-42-12345678

# Check validator log for last activity
tail -20 /path/to/rate-my-mr-*.log
```

**Common causes:**
- AI service timeout (waiting for response)
- Large MR taking long time to process
- Network issue (hanging on git clone)
- Deadlock or infinite loop (rare)

#### Scenario 6: LLM Adapter (JWT Token) Issues

**Symptoms:** Validation fails with token-related errors

**Debug Steps:**
```bash
# Check token acquisition
grep "JWT token" /path/to/rate-my-mr-*.log

# Expected successful flow:
# [DEBUG] Requesting JWT token from http://api-gateway.internal.com:8000/api/token
# [DEBUG] Token subject: rate-my-mr-org%2Frepo-42
# [DEBUG] Token API response status: 200
# [DEBUG] JWT token acquired successfully for org%2Frepo-42
# [DEBUG] Token (first 20 chars): eyJhbGciOiJIUzI1Ni...

# Count token acquisitions (should be 1 per MR)
grep -c "Requesting JWT token" /path/to/rate-my-mr-*.log
# Expected: 1

# Count token reuse (should be 3 for 4 AI calls)
grep -c "Reusing existing session token" /path/to/rate-my-mr-*.log
# Expected: 3

# Check for 401 errors
grep "401\|Unauthorized\|authentication failed" /path/to/rate-my-mr-*.log
```

**Manual token test:**
```bash
# Test token endpoint
curl -X POST "http://${BFA_HOST}:8000/api/token" \
  -H "Content-Type: application/json" \
  -d '{"subject":"rate-my-mr-test-project-123"}' \
  -v

# Expected response:
# HTTP/1.1 200 OK
# {"token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."}
```

**Common causes:**
- BFA_HOST unreachable → Check network
- Token API returns 401 → Invalid credentials
- 401 on LLM calls → Expired/invalid token
- Connection refused → BFA service down

#### Log Directory Structure (Organized Mode)

```
/home/docker/tmp/mr-validator-logs/
│
├── webhook/
│   ├── 2025-11-08/
│   │   ├── webhook-server.log
│   │   ├── webhook-server.log.1
│   │   └── webhook-server.log.2
│   │
│   └── 2025-11-09/
│       └── webhook-server.log
│
└── validations/
    ├── 2025-11-08/
    │   ├── vigneshpalanivelr_commit-validator/
    │   │   ├── mr-1/
    │   │   │   ├── rate-my-mr-4adcc17d.log
    │   │   │   ├── rate-my-mr-4adcc17d.log.1
    │   │   │   └── gitlab-api-4adcc17d.log
    │   │   │
    │   │   └── mr-2/
    │   │       └── rate-my-mr-8b3ef21a.log
    │   │
    │   └── another_project/
    │       └── mr-5/
    │           └── rate-my-mr-1c2d3e4f.log
    │
    └── 2025-11-09/
        └── vigneshpalanivelr_commit-validator/
            └── mr-3/
                └── rate-my-mr-9f8e7d6c.log
```

#### Viewing and Analyzing Logs

**View latest logs for MR:**
```bash
LOG_DIR=/mnt/nfs/mr-validator-logs
PROJECT="vigneshpalanivelr_commit-validator"
MR_IID=42
DATE=$(date +%Y-%m-%d)

tail -f "$LOG_DIR/validations/$DATE/$PROJECT/mr-$MR_IID/rate-my-mr-*.log"
```

**Search logs by correlation ID:**
```bash
REQUEST_ID_SHORT="4adcc17d"
grep "$REQUEST_ID_SHORT" /mnt/nfs/mr-validator-logs/validations/**/**/**/*.log
```

**Parse structured logs:**
```bash
# Extract all pipeline_id values
grep "pipeline_id=" /path/to/log.log | sed 's/.*pipeline_id=\([^ ]*\).*/\1/'

# Extract errors with severity
grep "severity=" /path/to/log.log | awk -F '|' '{print $3, $5, $6}'
```

#### Troubleshooting Checklist

- [ ] **Webhook received?** Check webhook-server.log for REQUEST_ID
- [ ] **Container spawned?** Check webhook log for "container started successfully"
- [ ] **Container still running?** Use `docker ps` with container name
- [ ] **Container exit code?** Use `docker inspect` for exit code
- [ ] **Validator log exists?** Check /home/docker/tmp/mr-validator-logs/
- [ ] **Validator started?** Check first 10 lines of validator log
- [ ] **Git clone succeeded?** Grep validator log for "git clone" or "Git init"
- [ ] **Config loaded?** Grep for "Configuration loaded"
- [ ] **JWT token acquired?** Grep for "JWT token acquired"
- [ ] **AI service reachable?** Grep for "AI Service Response"
- [ ] **AI service timeout?** Grep for "Timeout" or "Retry attempt"
- [ ] **GitLab posting succeeded?** Grep for "Successfully posted discussion"
- [ ] **Environment variables set?** Check mrproper.env file
- [ ] **Network connectivity?** Test from Docker host to GitLab & BFA service

</details>

---

## Documentation

| Document | Purpose |
|----------|---------|
| [README.md](./README.md) | User & Operator Guide |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Developer & Technical Guide |
| [OPERATIONS.md](./OPERATIONS.md) | DevOps & Maintenance Guide |

---

## License

Internal use - see company licensing policies.
