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
