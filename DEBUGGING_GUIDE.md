# Debugging Guide: Two-Container Architecture

**Architecture**:
```
Container 1 (webhook-server) → Receives GitLab webhook
                              ↓
                    Spawns Container 2 (validator)
                              ↓
                    Performs MR analysis
```

---

## REQUEST_ID: Your Debugging Superpower

Every webhook request generates a unique `REQUEST_ID` that flows through both containers:

**Format**: `20251104_153045_123456`
- Date: 20251104 (2025-11-04)
- Time: 153045 (15:30:45)
- Microseconds: 123456

**Short version**: First 8 chars of microseconds → `12345678`

---

## Method 1: Find Request in Webhook Logs

### Step 1: Search webhook-server.log for the MR

```bash
# Find all webhooks for a specific MR
grep "MR IID: 42" /home/docker/tmp/mr-validator-logs/webhook-server.log

# Example output:
# 2025-11-04 15:30:45 - server.py - INFO - [12345678] MR IID: 42
# 2025-11-04 15:30:45 - server.py - INFO - [12345678] MR Title: Fix authentication bug
```

**You got the REQUEST_ID_SHORT**: `12345678`

### Step 2: Get full REQUEST_ID

```bash
# Find the full REQUEST_ID for this short ID
grep "\[12345678\] === NEW WEBHOOK REQUEST ===" /home/docker/tmp/mr-validator-logs/webhook-server.log -A 1

# Or extract it from the docker command log:
grep "\[12345678\] Docker command:" /home/docker/tmp/mr-validator-logs/webhook-server.log | grep -o 'REQUEST_ID=[^ ]*'

# Example output:
# REQUEST_ID=20251104_153045_123456
```

**Full REQUEST_ID**: `20251104_153045_123456`

---

## Method 2: Find Validator Container Logs

### Step 3A: Find log file by REQUEST_ID

The validator creates its own log file with the REQUEST_ID in the filename:

```bash
# List all rate-my-mr logs
ls -lth /home/docker/tmp/mr-validator-logs/rate-my-mr-*.log | head -20

# Find specific request log
ls -lth /home/docker/tmp/mr-validator-logs/rate-my-mr-*20251104_153045_123456*.log

# Example output:
# -rw-r--r-- 1 docker docker 45K Nov  4 15:31 rate-my-mr-vigneshpalanivelr-my-project-42-20251104_153045_123456.log
```

### Step 3B: Read the validator log

```bash
# Full log
cat /home/docker/tmp/mr-validator-logs/rate-my-mr-vigneshpalanivelr-my-project-42-20251104_153045_123456.log

# Last 50 lines
tail -50 /home/docker/tmp/mr-validator-logs/rate-my-mr-vigneshpalanivelr-my-project-42-20251104_153045_123456.log

# Search for errors
grep -i error /home/docker/tmp/mr-validator-logs/rate-my-mr-vigneshpalanivelr-my-project-42-20251104_153045_123456.log

# Search for AI service issues
grep "AI Service" /home/docker/tmp/mr-validator-logs/rate-my-mr-vigneshpalanivelr-my-project-42-20251104_153045_123456.log
```

---

## Method 3: Check Docker Container Status

### Step 4: Find the container

```bash
# Container name format: mr-{checker}-{mr_iid}-{request_id_short}
# Example: mr-rate-my-mr-42-12345678

# Check if container is still running
docker ps | grep "mr-rate-my-mr-42-12345678"

# Check if container exited (shows last 10 containers)
docker ps -a --filter "name=mr-rate-my-mr-42-12345678"

# Example output:
# CONTAINER ID   IMAGE                  COMMAND                  CREATED         STATUS                     PORTS     NAMES
# abc123def456   mr-checker-vp-test     "rate-my-mr vignes..."  2 minutes ago   Exited (1) 1 minute ago              mr-rate-my-mr-42-12345678
```

### Step 5: Check container exit code

```bash
# Inspect container exit code
docker inspect mr-rate-my-mr-42-12345678 --format='{{.State.ExitCode}}'

# Exit code meanings:
# 0  = Success
# 1  = General error (check validator logs)
# 2  = Misuse of shell command
# 125 = Docker daemon error
# 126 = Command cannot execute
# 127 = Command not found
# 137 = SIGKILL (killed, out of memory?)
# 139 = SIGSEGV (segmentation fault)
```

---

## Method 4: Check Docker Logs (Syslog)

Since containers use `--log-driver=syslog`, you can also check syslog:

```bash
# Check syslog for container output
journalctl CONTAINER_NAME=mr-rate-my-mr-42-12345678

# Or check system syslog
grep "mr-rate-my-mr-42-12345678" /var/log/syslog

# Show last 100 lines for this container
journalctl CONTAINER_NAME=mr-rate-my-mr-42-12345678 -n 100
```

---

## Common Failure Scenarios

### Scenario 1: Container Starts But Fails Immediately

**Symptom**: Container appears in `docker ps -a` with non-zero exit code

**Debug Steps**:
1. Check webhook log for container start:
   ```bash
   grep "\[12345678\] Checker rate-my-mr container" /home/docker/tmp/mr-validator-logs/webhook-server.log
   ```

2. Check validator log for startup errors:
   ```bash
   head -50 /home/docker/tmp/mr-validator-logs/rate-my-mr-*20251104_153045_123456*.log
   ```

3. Common causes:
   - Missing environment variables (GITLAB_ACCESS_TOKEN, AI_SERVICE_URL)
   - GitLab API authentication failure
   - Git clone failure (network, permissions)

### Scenario 2: Container Never Starts

**Symptom**: No container found in `docker ps -a`

**Debug Steps**:
1. Check webhook log for docker command failure:
   ```bash
   grep -A 5 "\[12345678\] Failed to start checker" /home/docker/tmp/mr-validator-logs/webhook-server.log
   ```

2. Common causes:
   - Docker image not found: `mr-checker-vp-test`
   - Docker daemon not responding
   - mrproper.env file missing
   - Insufficient Docker permissions

### Scenario 3: Container Runs But AI Service Fails

**Symptom**: Container exits with code 0 or 1, but analysis incomplete

**Debug Steps**:
1. Search validator log for AI service errors:
   ```bash
   grep "AI Service" /home/docker/tmp/mr-validator-logs/rate-my-mr-*20251104_153045_123456*.log | grep -i error
   ```

2. Check retry attempts:
   ```bash
   grep "Retry attempt" /home/docker/tmp/mr-validator-logs/rate-my-mr-*20251104_153045_123456*.log
   ```

3. Common causes:
   - AI service URL misconfigured (AI_SERVICE_URL)
   - AI service timeout (>120s per attempt)
   - AI service returns 5xx errors
   - Network connectivity issues

### Scenario 4: Container Runs But No GitLab Comment

**Symptom**: Container exits successfully (code 0) but no comment on MR

**Debug Steps**:
1. Search for GitLab API posting:
   ```bash
   grep "Posting discussion" /home/docker/tmp/mr-validator-logs/rate-my-mr-*20251104_153045_123456*.log
   ```

2. Check for posting errors:
   ```bash
   grep "Failed to post" /home/docker/tmp/mr-validator-logs/rate-my-mr-*20251104_153045_123456*.log
   ```

3. Common causes:
   - GITLAB_ACCESS_TOKEN invalid or expired
   - Insufficient GitLab permissions
   - Network issues reaching GitLab API
   - MR already merged/closed

### Scenario 5: Container Stuck/Hanging

**Symptom**: Container running for >10 minutes

**Debug Steps**:
1. Check if container is still running:
   ```bash
   docker ps | grep mr-rate-my-mr-42-12345678
   ```

2. Check what it's doing:
   ```bash
   # Check CPU/memory usage
   docker stats mr-rate-my-mr-42-12345678 --no-stream

   # Check processes inside container
   docker top mr-rate-my-mr-42-12345678
   ```

3. Check validator log for last activity:
   ```bash
   tail -20 /home/docker/tmp/mr-validator-logs/rate-my-mr-*20251104_153045_123456*.log
   ```

4. Common causes:
   - AI service timeout (waiting for response)
   - Large MR taking long time to process
   - Network issue (hanging on git clone)
   - Deadlock or infinite loop (rare)

---

## Quick Debug Commands

### Find Most Recent Request

```bash
# Get last REQUEST_ID_SHORT from webhook log
grep "=== NEW WEBHOOK REQUEST ===" /home/docker/tmp/mr-validator-logs/webhook-server.log | tail -1

# Example output:
# 2025-11-04 15:30:45 - server.py - INFO - [12345678] === NEW WEBHOOK REQUEST ===
```

### Find All Requests for Specific MR

```bash
# Replace 42 with your MR IID
MR_IID=42
grep "MR IID: ${MR_IID}" /home/docker/tmp/mr-validator-logs/webhook-server.log | grep -o '\[[0-9]*\]' | sort -u

# This gives you all REQUEST_ID_SHORT values for this MR
```

### Find All Failures in Last Hour

```bash
# Check webhook log for container start failures
grep "container failed to start" /home/docker/tmp/mr-validator-logs/webhook-server.log | tail -20

# Check for recent validator errors
find /home/docker/tmp/mr-validator-logs -name "rate-my-mr-*.log" -mmin -60 -exec grep -l "ERROR" {} \;
```

### Check System Health

```bash
# Check disk space (log volume)
df -h /home/docker/tmp/mr-validator-logs

# Check Docker daemon
docker info

# Check recent container failures
docker ps -a --filter "status=exited" --filter "name=mr-" --format "table {{.Names}}\t{{.Status}}\t{{.CreatedAt}}" | head -20
```

---

## Correlation Example: Full Debug Session

Let's say user reports: **"MR !42 validation didn't work"**

### Step-by-Step Investigation:

```bash
# 1. Find the webhook request
grep "MR IID: 42" /home/docker/tmp/mr-validator-logs/webhook-server.log | tail -5

# Output shows:
# 2025-11-04 15:30:45 - server.py - INFO - [12345678] MR IID: 42
# 2025-11-04 15:30:45 - server.py - INFO - [12345678] Starting checker 1/1: rate-my-mr
# 2025-11-04 15:30:46 - server.py - INFO - [12345678] Checker rate-my-mr container started successfully

# 2. Get full REQUEST_ID
grep "\[12345678\]" /home/docker/tmp/mr-validator-logs/webhook-server.log | grep "REQUEST_ID="

# Output shows:
# --env REQUEST_ID=20251104_153045_123456

# 3. Find validator log
ls -lth /home/docker/tmp/mr-validator-logs/ | grep 20251104_153045_123456

# Output shows:
# -rw-r--r-- 1 docker docker 12K Nov 4 15:31 rate-my-mr-vigneshpalanivelr-my-project-42-20251104_153045_123456.log

# 4. Check validator log for errors
grep -i error /home/docker/tmp/mr-validator-logs/rate-my-mr-vigneshpalanivelr-my-project-42-20251104_153045_123456.log

# Output shows:
# 2025-11-04 15:31:02 - rate_my_mr.py - ERROR - [12345678] AI Service Error (attempt 1): Connection refused
# 2025-11-04 15:31:04 - rate_my_mr.py - ERROR - [12345678] AI Service Error (attempt 2): Connection refused
# 2025-11-04 15:31:08 - rate_my_mr.py - ERROR - [12345678] AI Service Error (attempt 3): Connection refused
# 2025-11-04 15:31:08 - rate_my_mr_gitlab.py - ERROR - [12345678] Failed to generate summary: Connection failed after 3 attempts

# 5. Root cause identified: AI service is down or unreachable
# Check AI_SERVICE_URL configuration:
grep AI_SERVICE_URL mrproper.env

# Fix: Verify AI service is running at that URL
```

---

## Log Retention & Rotation

Current configuration:
- **Webhook logs**: 100 MB × 5 files = 500 MB total
- **Validator logs**: 50 MB × 3 files per request

Old logs are automatically rotated when size limits are reached.

To find old rotated logs:
```bash
# Webhook rotated logs
ls -lth /home/docker/tmp/mr-validator-logs/webhook-server.log*

# Example:
# webhook-server.log       (current)
# webhook-server.log.1     (previous)
# webhook-server.log.2     (older)
# webhook-server.log.3
# webhook-server.log.4
# webhook-server.log.5     (oldest)
```

---

## Monitoring Commands

### Real-time Monitoring

```bash
# Watch webhook log in real-time
tail -f /home/docker/tmp/mr-validator-logs/webhook-server.log

# Watch for new validator containers starting
watch -n 2 'docker ps --filter "name=mr-"'

# Monitor most recent validator log
tail -f $(ls -t /home/docker/tmp/mr-validator-logs/rate-my-mr-*.log | head -1)
```

### Periodic Health Checks

```bash
# Count validations in last hour
find /home/docker/tmp/mr-validator-logs -name "rate-my-mr-*.log" -mmin -60 | wc -l

# Count errors in last hour
find /home/docker/tmp/mr-validator-logs -name "rate-my-mr-*.log" -mmin -60 -exec grep -l "ERROR" {} \; | wc -l

# Success rate calculation
TOTAL=$(find /home/docker/tmp/mr-validator-logs -name "rate-my-mr-*.log" -mmin -60 | wc -l)
ERRORS=$(find /home/docker/tmp/mr-validator-logs -name "rate-my-mr-*.log" -mmin -60 -exec grep -l "ERROR" {} \; | wc -l)
SUCCESS=$((TOTAL - ERRORS))
echo "Success rate: ${SUCCESS}/${TOTAL} ($((SUCCESS * 100 / TOTAL))%)"
```

---

## Error Pattern Analysis

### Find Most Common Errors

```bash
# Extract all ERROR lines from recent logs
find /home/docker/tmp/mr-validator-logs -name "rate-my-mr-*.log" -mtime -1 -exec grep "ERROR" {} \; | \
  sed 's/\[.*\]/[ID]/g' | \  # Remove REQUEST_IDs
  sort | uniq -c | sort -rn | head -10

# Example output:
#  15 ERROR - [ID] AI Service Error (attempt 3): Timeout
#   8 ERROR - [ID] Failed to post discussion to GitLab: 401 Unauthorized
#   3 ERROR - [ID] Git clone failed with return code 128
```

### Slowest Requests

```bash
# Find requests that took >5 minutes (check log timestamp differences)
for log in $(ls -t /home/docker/tmp/mr-validator-logs/rate-my-mr-*.log | head -20); do
  START=$(head -5 "$log" | grep -o '[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\} [0-9]\{2\}:[0-9]\{2\}:[0-9]\{2\}' | head -1)
  END=$(tail -5 "$log" | grep -o '[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\} [0-9]\{2\}:[0-9]\{2\}:[0-9]\{2\}' | tail -1)

  if [ -n "$START" ] && [ -n "$END" ]; then
    DURATION=$(($(date -d "$END" +%s) - $(date -d "$START" +%s)))
    if [ $DURATION -gt 300 ]; then  # >5 minutes
      echo "Slow request: $log (${DURATION}s)"
    fi
  fi
done
```

---

## Summary: Debug Workflow

```
User Reports Issue
       ↓
1. Find REQUEST_ID from webhook log (grep MR IID or timestamp)
       ↓
2. Find validator log file (ls with REQUEST_ID pattern)
       ↓
3. Read validator log for errors
       ↓
4. Check Docker container status (docker ps -a)
       ↓
5. Check syslog if needed (journalctl)
       ↓
6. Identify root cause
       ↓
7. Fix and verify
```

**Key Insight**: REQUEST_ID is your correlation key across all logs and containers!

---

## Troubleshooting Checklist

When investigating failures, check these in order:

- [ ] **Webhook received?** Check webhook-server.log for REQUEST_ID
- [ ] **Container spawned?** Check webhook log for "container started successfully"
- [ ] **Container still running?** Use `docker ps` with container name
- [ ] **Container exit code?** Use `docker inspect` for exit code
- [ ] **Validator log exists?** Check /home/docker/tmp/mr-validator-logs/
- [ ] **Validator started?** Check first 10 lines of validator log
- [ ] **Git clone succeeded?** Grep validator log for "git clone" or "Git init"
- [ ] **AI service reachable?** Grep validator log for "AI Service Response"
- [ ] **AI service timeout?** Grep validator log for "Timeout" or "Retry attempt"
- [ ] **GitLab posting succeeded?** Grep validator log for "Successfully posted discussion"
- [ ] **Environment variables set?** Check mrproper.env file
- [ ] **Network connectivity?** Test from Docker host to GitLab & AI service

---

**Last Updated**: 2025-11-04
**Related Docs**: README.md, ARCHITECTURE.md
