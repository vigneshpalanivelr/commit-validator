# MR Validator - Operations & Maintenance Guide

DevOps documentation for deployment, monitoring, debugging, and maintenance.

## Table of Contents

- [Deployment](#deployment)
- [Monitoring](#monitoring)
- [Debugging](#debugging)
- [Testing](#testing)
- [Maintenance](#maintenance)
- [Related Documentation](#related-documentation)

---

## Deployment

### Infrastructure Overview

```mermaid
flowchart TB
    subgraph Host["Docker Host"]
        A[Webhook Container<br/>Port 9912]
        B[Validator Containers<br/>Spawned on demand]
        C[Shared Volume<br/>/mr-validator-logs]
    end

    subgraph External
        D[GitLab]
        E[BFA Service]
        F[NFS Storage]
    end

    D -->|Webhook| A
    A -->|Spawn| B
    B -->|POST| E
    B -->|API| D
    A --> C
    B --> C
    C --> F
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
  --name mrproper-webhook-vp-test \
  --restart=unless-stopped \
  --env-file mrproper.env \
  -p 9912:9912 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /mnt/nfs/mr-validator-logs:/home/docker/tmp/mr-validator-logs \
  mrproper-webhook-vp-test
```

**4. Verify:**
```bash
docker ps | grep webhook
curl http://localhost:9912/
docker logs mrproper-webhook-vp-test --tail 20
```

**Expected output:**
```
CONTAINER ID   IMAGE                      STATUS          PORTS
abc123def456   mrproper-webhook-vp-test   Up 2 minutes    0.0.0.0:9912->9912/tcp

=== MR Validator Webhook Server Starting ===
Docker connectivity verified
Starting webhook server on port 9912...
```

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

## Monitoring

### Health Check Commands

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

### Log Analysis

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

### Disk Usage Monitoring

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

### Alerting

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

---

## Debugging

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
docker inspect mr-checker-42-12345678 --format='{{.State.ExitCode}}'

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
docker exec mrproper-webhook-vp-test env | grep BFA_HOST
```

### Debug Workflow

```mermaid
flowchart TD
    A[User Reports Issue] --> B[Get MR IID]
    B --> C[Find REQUEST_ID in webhook log]
    C --> D[Find validator log]
    D --> E{Log exists?}
    E -->|No| F[Container never started]
    E -->|Yes| G[Check for errors]
    G --> H{Error type?}
    H -->|Auth| I[Check tokens]
    H -->|Timeout| J[Check service connectivity]
    H -->|Config| K[Check repo .rate-my-mr.yaml]
    H -->|Git| L[Check repository access]
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

## Testing

### Infrastructure Tests

```bash
# Test 1: Docker image exists
docker images | grep mr-checker-vp-test
# Expected: mr-checker-vp-test   latest   abc123   1 hour ago   1.2GB

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
  mr-checker-vp-test rate-my-mr --help

# Expected: Usage information, exit 0
```

**Full validation test:**
```bash
REQUEST_ID=test_$(date +%Y%m%d_%H%M%S)_$(openssl rand -hex 4)

docker run --rm --env-file mrproper.env \
  -e REQUEST_ID=$REQUEST_ID \
  -v /mnt/nfs/mr-validator-logs:/home/docker/tmp/mr-validator-logs \
  mr-checker-vp-test rate-my-mr org%2Frepo 42

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
  mr-checker-vp-test rate-my-mr org%2Flarge-mr 99

# Expected: <5 minutes
```

**Token acquisition overhead:**
```bash
# With BFA_HOST (new adapter)
time curl -s -X POST "http://${BFA_HOST}:8000/api/token" \
  -d '{"subject":"test"}' | jq -r '.token'

# Expected: <200ms
```

<details>
<summary><b>Click to expand: Complete Test Suite Reference</b></summary>

#### Test Suite 1: Infrastructure Tests

**Test 1.1: Docker Image Build**
```bash
# Build image
docker build -t mr-checker-vp-test .
# Expected: Build SUCCESS, no missing dependencies

# Verification
docker run mr-checker-vp-test python -c "import mrproper; print('OK')"
docker run mr-checker-vp-test which rate-my-mr
docker run mr-checker-vp-test which mrproper-clang-format
docker run mr-checker-vp-test which mrproper-message

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
  mr-checker-vp-test rate-my-mr \
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
# - All 4 AI calls made:
#   - generate_summary()
#   - generate_initial_code_review()
#   - generate_lint_disable_report()
#   - generate_added_code_file() (if applicable)
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
  mr-checker-vp-test rate-my-mr \
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

# Expected Logs:
# First AI call:
# [DEBUG] Requesting JWT token from ...
# [DEBUG] JWT token acquired successfully
# [DEBUG] Sending POST request to LLM API (attempt 1/3)...

# Second AI call:
# [DEBUG] Reusing existing session token for <project>-<mriid>
# [DEBUG] Sending POST request to LLM API (attempt 1/3)...

# Third AI call:
# [DEBUG] Reusing existing session token for <project>-<mriid>
# [DEBUG] Sending POST request to LLM API (attempt 1/3)...

# Fourth AI call:
# [DEBUG] Reusing existing session token for <project>-<mriid>
# [DEBUG] Sending POST request to LLM API (attempt 1/3)...

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

**Test 4.5: LLM Adapter Retry Logic**
```bash
# Configure with temporarily unavailable BFA service

# Success Criteria:
# - Retries on connection errors
# - Retries on timeouts
# - Retries on 5xx errors
# - Retries on 429 rate limit
# - Does NOT retry on 4xx (except 429)
# - Exponential backoff: 2s, 4s, 8s
```

**Test 4.6: Backward Compatibility (No BFA_HOST)**
```bash
# Remove BFA_HOST from config
cat > mrproper.env <<EOF
GITLAB_ACCESS_TOKEN=glpat-your-token
AI_SERVICE_URL=http://10.31.88.29:6006/generate
EOF

# Run validation
docker run --env-file mrproper.env ...

# Success Criteria:
# - Falls back to legacy direct connection
# - Logs show "Using legacy direct AI service connection"
# - NO JWT token acquisition
# - Validation completes successfully
```

#### Test Suite 5: mrproper-clang-format Tests

**Test 5.1: Basic Clang Format Check**
```bash
docker run --env-file mrproper.env \
  --env REQUEST_ID=test_$(date +%Y%m%d_%H%M%S_%N) \
  mr-checker-vp-test mrproper-clang-format \
  <project-name> <mr-iid>

# Success Criteria:
# - GitLab API connection
# - MR data fetched
# - Clang-format checks performed
# - Results posted to GitLab
# - Uses gitlab.py (common module)
```

**Test 5.2: Clang Format Violations Detection**
```bash
# Create test MR with badly formatted C/C++ code
# Trigger validation
# Check discussion posted

# Success Criteria:
# - Formatting violations detected
# - GitLab discussion posted with details
# - Line numbers provided
# - Suggestions provided
```

#### Test Suite 6: mrproper-message Tests

**Test 6.1: Basic Commit Message Check**
```bash
docker run --env-file mrproper.env \
  --env REQUEST_ID=test_$(date +%Y%m%d_%H%M%S_%N) \
  mr-checker-vp-test mrproper-message \
  <project-name> <mr-iid>

# Success Criteria:
# - GitLab API connection
# - Commit messages fetched
# - Message validation performed
# - Results posted to GitLab
# - Uses gitlab.py (common module)
```

**Test 6.2: Invalid Commit Message Detection**
```bash
# Create test MR with poor commit messages
# Trigger validation

# Success Criteria:
# - Invalid messages detected
# - Specific issues identified (too short, no capitalization, etc.)
# - GitLab discussion posted
# - Improvement suggestions provided
```

#### Test Suite 7: Integration Tests

**Test 7.1: Multiple Validators in Parallel**
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

**Test 7.2: Concurrent MR Validations**
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

**Test 7.3: End-to-End GitLab Webhook Flow**
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

#### Test Suite 8: Error Handling & Recovery

**Test 8.1: GitLab API Unavailable**
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

**Test 8.2: AI Service / LLM Adapter Timeout**
```bash
# Set very low timeout
API_TIMEOUT=1 docker run ...

# Success Criteria:
# - Timeout detected after API_TIMEOUT seconds
# - Retry attempted
# - Eventually fails gracefully
# - Error reported to GitLab
```

**Test 8.3: Disk Space Full**
```bash
# Fill up /home/docker/tmp/mr-validator-logs
# Trigger validation

# Success Criteria:
# - Error logged (if possible)
# - Log rotation attempts to free space
# - Validation continues if possible
# - No system crash
```

**Test 8.4: Docker Daemon Failure**
```bash
# Stop Docker daemon
# Trigger webhook

# Success Criteria:
# - Error logged in webhook-server.log
# - 500 error returned to webhook caller
# - Server continues running (doesn't crash)
# - Recovers when Docker comes back
```

#### Test Suite 9: Performance Tests

**Test 9.1: Large MR Validation**
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

**Test 9.2: Rate Limiting (LLM Adapter)**
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

**Test 9.3: Token Acquisition Performance**
```bash
# Run 10 validations and measure time
# Compare: legacy mode vs new adapter mode

# Expected:
# - Token acquisition adds ~50-200ms per MR
# - Minimal impact on total validation time (~1%)
# - Token reuse working (not 4 token calls)
```

#### Test Suite 10: Debugging & Monitoring

**Test 10.1: Log Correlation**
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

**Test 10.2: Log Rotation**
```bash
# Trigger many validations to generate logs
# Check log file sizes
ls -lh /home/docker/tmp/mr-validator-logs/

# Check rotated files exist
ls -lh /home/docker/tmp/mr-validator-logs/webhook-server.log*
ls -lh /home/docker/tmp/mr-validator-logs/rate-my-mr-*.log*

# Success Criteria:
# - webhook-server.log rotates at 100MB
# - Up to 5 backup files (webhook-server.log.1 through .5)
# - Validator logs rotate at 50MB
# - Up to 3 backup files per validator log
```

**Test 10.3: Debugging Information Quality**
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
- [✅/❌] Test 1.1: Docker Image Build
- [✅/❌] Test 1.2: Webhook Server Startup
- [✅/❌] Test 1.3: Log Directory Setup

### Suite 2: Webhook Server Tests
- [✅/❌] Test 2.1: Webhook Endpoint Routing
- [✅/❌] Test 2.2: Invalid Checker Rejection
- [✅/❌] Test 2.3: REQUEST_ID Generation
- [✅/❌] Test 2.4: Container Naming

... (continue for all tests)

## Failed Tests Details

### Test X.Y: Test Name
**Failure Reason**: ...
**Logs**: ...
**Screenshots/Evidence**: ...
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

#### Quick Test Script

```bash
#!/bin/bash
# quick-test.sh - Run basic smoke tests

set -e

echo "=== Quick Test Suite ==="

echo "Test 1: Docker image exists"
docker images | grep mr-checker-vp-test || exit 1

echo "Test 2: Webhook server responds"
curl -s http://localhost:9912/ >/dev/null || exit 1

echo "Test 3: Environment file exists"
test -f mrproper.env || exit 1

echo "Test 4: Log directory writable"
test -w /home/docker/tmp/mr-validator-logs || exit 1

echo "Test 5: Run rate-my-mr (dry run)"
docker run mr-checker-vp-test rate-my-mr --help || exit 1

echo "=== All tests passed ==="
```

#### Success Criteria Summary

**System is production-ready when**:
- ✅ All infrastructure tests pass
- ✅ All webhook tests pass
- ✅ All three validators work correctly
- ✅ Both legacy and new adapter modes work
- ✅ Error handling is robust
- ✅ Logging and debugging is comprehensive
- ✅ Performance is acceptable (<5 min for typical MR)
- ✅ Token reuse working (1 token call per MR)
- ✅ No memory leaks or resource issues
- ✅ Documentation is complete and accurate

**Estimated Time**: 4-6 hours for complete test suite

</details>

---

## Maintenance

### Log Rotation

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

### Cleanup Old Logs

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

### Disk Space Recovery

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

### Docker Cleanup

**Remove old containers:**
```bash
# Remove stopped validator containers older than 1 day
docker container prune --filter "until=24h" --filter "name=mr-"

# Remove dangling images
docker image prune -f

# Full cleanup (careful!)
docker system prune -f
```

### Restart Procedures

**Restart webhook server:**
```bash
docker restart mrproper-webhook-vp-test

# Or full restart
docker stop mrproper-webhook-vp-test
docker rm mrproper-webhook-vp-test
./start-server
```

**Rebuild images:**
```bash
./build-docker-images --no-cache
docker restart mrproper-webhook-vp-test
```

### Backup Strategy

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

### Upgrade Procedure

```mermaid
flowchart TD
    A[Pull latest code] --> B[Build new images]
    B --> C[Test locally]
    C --> D{Tests pass?}
    D -->|No| E[Fix issues]
    E --> C
    D -->|Yes| F[Stop webhook server]
    F --> G[Backup current config]
    G --> H[Deploy new images]
    H --> I[Start webhook server]
    I --> J[Verify health]
    J --> K{Healthy?}
    K -->|No| L[Rollback]
    K -->|Yes| M[Done]
```

**Steps:**
```bash
# 1. Pull latest
git pull origin main

# 2. Build
./build-docker-images

# 3. Test
docker run --rm mr-checker-vp-test rate-my-mr --help

# 4. Deploy
docker stop mrproper-webhook-vp-test
cp mrproper.env mrproper.env.backup
# Make any config changes
./start-server

# 5. Verify
curl http://localhost:9912/
docker logs mrproper-webhook-vp-test --tail 20

# 6. Monitor first few validations
tail -f /mnt/nfs/mr-validator-logs/webhook/*/webhook-server.log
```

---

## Related Documentation

- [README.md](./README.md) - User & Operator Guide
- [ARCHITECTURE.md](./ARCHITECTURE.md) - Developer & Technical Guide
