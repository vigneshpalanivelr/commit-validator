# Comprehensive Test Plan for MR Validator System

**Date**: 2025-11-08
**Scope**: Complete application functionality testing
**Target**: All three validators + webhook server + LLM adapter

---

## Test Environment Setup

### Prerequisites
```bash
# 1. Environment variables configured
cat mrproper.env
# Should contain:
# GITLAB_ACCESS_TOKEN=glpat-xxxxxxxxxxxxxxxxxxxx
# Either legacy mode:
#   AI_SERVICE_URL=http://10.31.88.29:6006/generate
# Or new adapter mode:
#   BFA_HOST=api-gateway.internal.com
#   BFA_TOKEN_KEY=<optional-token>
#   API_TIMEOUT=120

# 2. Docker image built
docker images | grep mr-checker-vp-test

# 3. Webhook server running
ps aux | grep "python.*server.py"

# 4. Log directory exists and writable
ls -ld /home/docker/tmp/mr-validator-logs

# 5. Test GitLab project and MRs available
```

---

## Test Suite 1: Infrastructure Tests

### Test 1.1: Docker Image Build
**Objective**: Verify Docker image builds successfully with all dependencies

```bash
# Build image
docker build -t mr-checker-vp-test .

# Expected: Build SUCCESS
# Expected: No missing dependencies
```

**Success Criteria**:
- ✅ Image builds without errors
- ✅ All Python packages installed
- ✅ mrproper package installed
- ✅ All three entry points available

**Verification**:
```bash
docker run mr-checker-vp-test python -c "import mrproper; print('OK')"
docker run mr-checker-vp-test which rate-my-mr
docker run mr-checker-vp-test which mrproper-clang-format
docker run mr-checker-vp-test which mrproper-message
```

### Test 1.2: Webhook Server Startup
**Objective**: Verify webhook server starts and listens on port 9912

```bash
# Start server
cd webhook-server
python server.py &

# Check if running
sleep 2
curl -v http://localhost:9912/
```

**Success Criteria**:
- ✅ Server starts without errors
- ✅ Listens on port 9912
- ✅ Logs initialized
- ✅ Docker daemon accessible

**Expected Logs**:
```
=== MR Validator Webhook Server Starting ===
Current working directory: /path/to/webhook-server
Environment file check: mrproper.env exists = True
Docker connectivity verified
Starting webhook server on port 9912...
```

### Test 1.3: Log Directory Setup
**Objective**: Verify log directory and rotation configuration

```bash
# Check directory
ls -la /home/docker/tmp/mr-validator-logs/

# Check webhook log
test -f /home/docker/tmp/mr-validator-logs/webhook-server.log
echo "Status: $?"  # Should be 0

# Check rotation
# (Trigger validations until log rotates or manually test)
```

**Success Criteria**:
- ✅ Directory exists and writable
- ✅ webhook-server.log created
- ✅ Rotation configured (100MB x 5)

---

## Test Suite 2: Webhook Server Tests

### Test 2.1: Webhook Endpoint Routing
**Objective**: Verify correct routing for different validators

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
```

**Success Criteria**:
- ✅ All endpoints return 200 OK
- ✅ Docker containers spawned
- ✅ REQUEST_ID logged
- ✅ Multiple validators work with '+'

### Test 2.2: Invalid Checker Rejection
**Objective**: Verify invalid checker names are rejected

```bash
# Test invalid checker
curl -X POST http://localhost:9912/mr-proper/invalid-checker \
  -d @test-payloads/mr-event.json

# Expected: 403 Forbidden
```

**Success Criteria**:
- ✅ Returns 403 Forbidden
- ✅ Error logged
- ✅ No container spawned

### Test 2.3: REQUEST_ID Generation and Propagation
**Objective**: Verify unique REQUEST_ID generated and passed to containers

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
```

**Success Criteria**:
- ✅ Unique REQUEST_ID generated (timestamp-based)
- ✅ REQUEST_ID passed to Docker container via --env
- ✅ Validator log contains same REQUEST_ID
- ✅ REQUEST_ID correlatable across all logs

### Test 2.4: Container Naming Convention
**Objective**: Verify containers named correctly for identification

```bash
# Trigger validation for MR !42
curl -X POST http://localhost:9912/mr-proper/rate-my-mr -d '...'

# Check container name
docker ps -a | grep "mr-rate-my-mr-42-"

# Expected format: mr-{checker}-{mriid}-{request_id_short}
# Example: mr-rate-my-mr-42-abcd1234
```

**Success Criteria**:
- ✅ Container name includes checker name
- ✅ Container name includes MR IID
- ✅ Container name includes REQUEST_ID_SHORT
- ✅ Easy to identify in docker ps

---

## Test Suite 3: rate-my-mr Validator Tests (Legacy Mode)

### Test 3.1: Basic Validation Flow (Legacy AI Service)
**Objective**: Verify complete MR validation with legacy direct AI connection

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
```

**Success Criteria**:
- ✅ GitLab API connection successful
- ✅ MR data fetched
- ✅ Git repository cloned
- ✅ Diff generated
- ✅ All 4 AI calls made:
  - `generate_summary()`
  - `generate_initial_code_review()`
  - `generate_lint_disable_report()`
  - `generate_added_code_file()` (if applicable)
- ✅ Discussion posted to GitLab
- ✅ Container exits with code 0

**Expected Log Flow**:
```
[DEBUG] Using legacy direct AI service connection
[DEBUG] ===== STARTING MR ANALYSIS =====
[DEBUG] Fetching MR data from GitLab API...
[DEBUG] MR fetched successfully: <title>
[DEBUG] Cloning git repository...
[DEBUG] Diff generated...
[DEBUG] AI Service Request - URL: http://10.31.88.29:6006/generate
[DEBUG] AI Service Response - Status Code: 200
...
Successfully analyzed MR <iid>
```

### Test 3.2: AI Service Retry Logic (Legacy Mode)
**Objective**: Verify exponential backoff retry on failures

```bash
# Configure with unreachable AI service
AI_SERVICE_URL=http://invalid-host:6006/generate docker run ...

# Or use network disconnect to simulate failure
```

**Success Criteria**:
- ✅ Retry attempt 1 after 2s wait
- ✅ Retry attempt 2 after 4s wait
- ✅ Retry attempt 3 after 8s wait
- ✅ Fails gracefully after 3 attempts
- ✅ Error posted to GitLab MR

**Expected Logs**:
```
[DEBUG] AI Service Connection Error (attempt 1): ...
[DEBUG] Retry attempt 2/3 after 2s wait...
[DEBUG] AI Service Connection Error (attempt 2): ...
[DEBUG] Retry attempt 3/3 after 4s wait...
[DEBUG] AI Service Connection Error (attempt 3): ...
[DEBUG] All 3 attempts failed - AI service not reachable
[ERROR] Failed to generate summary: Connection failed after 3 attempts
```

### Test 3.3: GitLab API Error Handling
**Objective**: Verify proper handling of GitLab API failures

```bash
# Test with invalid token
GITLAB_ACCESS_TOKEN=invalid-token docker run ...

# Test with invalid project
docker run ... invalid-project-name 123

# Test with invalid MR IID
docker run ... valid-project 999999
```

**Success Criteria**:
- ✅ 401 error logged for invalid token
- ✅ 404 error logged for invalid project/MR
- ✅ Error message posted to GitLab (if possible)
- ✅ Container exits with non-zero code

---

## Test Suite 4: rate-my-mr Validator Tests (New LLM Adapter)

### Test 4.1: JWT Token Acquisition
**Objective**: Verify token acquisition from BFA service

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
```

**Success Criteria**:
- ✅ Detects BFA_HOST is configured
- ✅ Sets PROJECT_ID and MR_IID env vars
- ✅ Calls POST http://{BFA_HOST}:8000/api/token
- ✅ Payload: `{"subject": "rate-my-mr-<project>-<mriid>"}`
- ✅ Receives token in response: `{"token": "..."}`
- ✅ Token cached for session

**Expected Logs**:
```
[DEBUG] Using new LLM adapter (BFA_HOST is configured)
[DEBUG] LLM Adapter initialized - BFA_HOST: api-gateway.internal.com
Set environment for LLM adapter: PROJECT_ID=<project>, MR_IID=<mriid>
[DEBUG] Requesting JWT token from http://api-gateway.internal.com:8000/api/token
[DEBUG] Token subject: rate-my-mr-<project>-<mriid>
[DEBUG] Token API response status: 200
[DEBUG] JWT token acquired successfully for <project>-<mriid>
[DEBUG] Token (first 20 chars): eyJhbGciOiJIUzI1Ni...
```

### Test 4.2: Token Reuse Across Multiple AI Calls
**Objective**: Verify token acquired once and reused for all 4 AI calls

```bash
# Run validation and monitor logs
docker run ... | tee validation.log

# Count token acquisitions
grep "Requesting JWT token" validation.log | wc -l
# Expected: 1

# Count token reuse
grep "Reusing existing session token" validation.log | wc -l
# Expected: 3 (for calls 2, 3, 4)
```

**Success Criteria**:
- ✅ Token requested ONCE at start
- ✅ Token reused for subsequent calls
- ✅ Total: 1 token API call + 4 LLM API calls

**Expected Logs**:
```
# First AI call:
[DEBUG] Requesting JWT token from ...
[DEBUG] JWT token acquired successfully
[DEBUG] Sending POST request to LLM API (attempt 1/3)...

# Second AI call:
[DEBUG] Reusing existing session token for <project>-<mriid>
[DEBUG] Sending POST request to LLM API (attempt 1/3)...

# Third AI call:
[DEBUG] Reusing existing session token for <project>-<mriid>
[DEBUG] Sending POST request to LLM API (attempt 1/3)...

# Fourth AI call:
[DEBUG] Reusing existing session token for <project>-<mriid>
[DEBUG] Sending POST request to LLM API (attempt 1/3)...
```

### Test 4.3: Pre-configured Token (BFA_TOKEN_KEY)
**Objective**: Verify pre-configured token bypasses token API

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
```

**Success Criteria**:
- ✅ Uses pre-configured token
- ✅ NO token API call made
- ✅ Logs show "Using pre-configured BFA_TOKEN_KEY"
- ✅ LLM API calls succeed with pre-configured token

**Expected Logs**:
```
[DEBUG] Using new LLM adapter (BFA_HOST is configured)
[DEBUG] LLM Adapter initialized - ...Token pre-configured: True
[DEBUG] Using pre-configured BFA_TOKEN_KEY
[DEBUG] Sending POST request to LLM API (attempt 1/3)...
# Should NOT see "Requesting JWT token from..."
```

### Test 4.4: Token Expiration / 401 Handling
**Objective**: Verify token cache cleared on 401 errors

```bash
# Use expired or invalid token
BFA_TOKEN_KEY=expired_or_invalid_token docker run ...
```

**Success Criteria**:
- ✅ First LLM call fails with 401
- ✅ Error logged: "JWT token authentication failed"
- ✅ Token cache cleared
- ✅ Error reported to GitLab

**Expected Logs**:
```
[DEBUG] Using pre-configured BFA_TOKEN_KEY
[DEBUG] Sending POST request to LLM API...
[ERROR] LLM API HTTP Error (attempt 1): 401 Client Error: Unauthorized
[ERROR] JWT token authentication failed (401 Unauthorized)
[DEBUG] Client error 401, not retrying
[ERROR] Failed to generate summary: 401 Client Error
```

### Test 4.5: LLM Adapter Retry Logic
**Objective**: Verify retry logic with new adapter

```bash
# Configure with temporarily unavailable BFA service
# Or use network rules to simulate intermittent failures
```

**Success Criteria**:
- ✅ Retries on connection errors
- ✅ Retries on timeouts
- ✅ Retries on 5xx errors
- ✅ Retries on 429 rate limit
- ✅ Does NOT retry on 4xx (except 429)
- ✅ Exponential backoff: 2s, 4s, 8s

### Test 4.6: Backward Compatibility (No BFA_HOST)
**Objective**: Verify legacy mode still works when BFA_HOST not set

```bash
# Remove BFA_HOST from config
cat > mrproper.env <<EOF
GITLAB_ACCESS_TOKEN=glpat-your-token
AI_SERVICE_URL=http://10.31.88.29:6006/generate
EOF

# Run validation
docker run --env-file mrproper.env ...
```

**Success Criteria**:
- ✅ Falls back to legacy direct connection
- ✅ Logs show "Using legacy direct AI service connection"
- ✅ NO JWT token acquisition
- ✅ Validation completes successfully

---

## Test Suite 5: mrproper-clang-format Tests

### Test 5.1: Basic Clang Format Check
**Objective**: Verify clang-format validator works correctly

```bash
docker run --env-file mrproper.env \
  --env REQUEST_ID=test_$(date +%Y%m%d_%H%M%S_%N) \
  mr-checker-vp-test mrproper-clang-format \
  <project-name> <mr-iid>
```

**Success Criteria**:
- ✅ GitLab API connection
- ✅ MR data fetched
- ✅ Clang-format checks performed
- ✅ Results posted to GitLab
- ✅ Uses gitlab.py (common module)

### Test 5.2: Clang Format Violations Detection
**Objective**: Verify clang-format detects formatting issues

```bash
# Create test MR with badly formatted C/C++ code
# Trigger validation
# Check discussion posted
```

**Success Criteria**:
- ✅ Formatting violations detected
- ✅ GitLab discussion posted with details
- ✅ Line numbers provided
- ✅ Suggestions provided

---

## Test Suite 6: mrproper-message Tests

### Test 6.1: Basic Commit Message Check
**Objective**: Verify commit message validator works correctly

```bash
docker run --env-file mrproper.env \
  --env REQUEST_ID=test_$(date +%Y%m%d_%H%M%S_%N) \
  mr-checker-vp-test mrproper-message \
  <project-name> <mr-iid>
```

**Success Criteria**:
- ✅ GitLab API connection
- ✅ Commit messages fetched
- ✅ Message validation performed
- ✅ Results posted to GitLab
- ✅ Uses gitlab.py (common module)

### Test 6.2: Invalid Commit Message Detection
**Objective**: Verify validator detects poorly formatted commit messages

```bash
# Create test MR with poor commit messages
# Trigger validation
```

**Success Criteria**:
- ✅ Invalid messages detected
- ✅ Specific issues identified (too short, no capitalization, etc.)
- ✅ GitLab discussion posted
- ✅ Improvement suggestions provided

---

## Test Suite 7: Integration Tests

### Test 7.1: Multiple Validators in Parallel
**Objective**: Verify multiple validators can run simultaneously

```bash
# Trigger multiple validators at once
curl -X POST http://localhost:9912/mr-proper/rate-my-mr+mrproper-clang-format+mrproper-message \
  -d @test-payloads/mr-event.json

# Check multiple containers spawned
docker ps | grep "mr-"
```

**Success Criteria**:
- ✅ All validators started
- ✅ Each has unique container
- ✅ All use same REQUEST_ID
- ✅ All complete successfully
- ✅ Multiple discussions posted to GitLab

### Test 7.2: Concurrent MR Validations
**Objective**: Verify system handles multiple MRs simultaneously

```bash
# Trigger validations for multiple MRs
for i in {1..5}; do
  curl -X POST http://localhost:9912/mr-proper/rate-my-mr \
    -d @test-payloads/mr-event-${i}.json &
done
wait

# Check all containers
docker ps -a | grep "mr-rate-my-mr"
```

**Success Criteria**:
- ✅ All validations started
- ✅ Each has unique REQUEST_ID
- ✅ No conflicts or race conditions
- ✅ All complete successfully
- ✅ Logs correlatable by REQUEST_ID

### Test 7.3: End-to-End GitLab Webhook Flow
**Objective**: Verify complete flow from GitLab webhook to discussion

```bash
# 1. Create test MR in GitLab
# 2. Configure webhook URL pointing to server
# 3. Update MR or change state
# 4. Webhook triggered automatically
# 5. Observe validation and discussion
```

**Success Criteria**:
- ✅ Webhook received
- ✅ Container spawned automatically
- ✅ Validation completes
- ✅ Discussion appears on MR within 2-5 minutes
- ✅ Proper formatting and content

---

## Test Suite 8: Error Handling & Recovery

### Test 8.1: GitLab API Unavailable
**Objective**: Verify graceful handling when GitLab is down

```bash
# Block GitLab host temporarily
# Or use invalid GITLAB_ACCESS_TOKEN
# Trigger validation
```

**Success Criteria**:
- ✅ Error logged
- ✅ Retry attempted
- ✅ Graceful failure
- ✅ Container exits with non-zero code
- ✅ No crash or hang

### Test 8.2: AI Service / LLM Adapter Timeout
**Objective**: Verify timeout handling

```bash
# Set very low timeout
API_TIMEOUT=1 docker run ...

# Or simulate slow AI service
```

**Success Criteria**:
- ✅ Timeout detected after API_TIMEOUT seconds
- ✅ Retry attempted
- ✅ Eventually fails gracefully
- ✅ Error reported to GitLab

### Test 8.3: Disk Space Full
**Objective**: Verify handling when log directory full

```bash
# Fill up /home/docker/tmp/mr-validator-logs
# Trigger validation
```

**Success Criteria**:
- ✅ Error logged (if possible)
- ✅ Log rotation attempts to free space
- ✅ Validation continues if possible
- ✅ No system crash

### Test 8.4: Docker Daemon Failure
**Objective**: Verify webhook server handles Docker failures

```bash
# Stop Docker daemon
# Trigger webhook
```

**Success Criteria**:
- ✅ Error logged in webhook-server.log
- ✅ 500 error returned to webhook caller
- ✅ Server continues running (doesn't crash)
- ✅ Recovers when Docker comes back

---

## Test Suite 9: Performance Tests

### Test 9.1: Large MR Validation
**Objective**: Verify system handles large MRs

```bash
# Create MR with 100+ files changed, 10,000+ LOC
# Trigger validation
# Monitor time and resources
```

**Success Criteria**:
- ✅ Validation completes (may take 10-15 minutes)
- ✅ No memory leaks
- ✅ No timeouts
- ✅ Discussion posted successfully

### Test 9.2: Rate Limiting (LLM Adapter)
**Objective**: Verify handling of rate limits from BFA service

```bash
# Trigger many validations quickly to hit rate limits
for i in {1..20}; do
  docker run ... &
done
```

**Success Criteria**:
- ✅ 429 errors detected
- ✅ Retry logic engages
- ✅ Eventually succeeds
- ✅ No permanent failures

### Test 9.3: Token Acquisition Performance
**Objective**: Measure overhead of JWT token acquisition

```bash
# Run 10 validations and measure time
# Compare: legacy mode vs new adapter mode
```

**Expected**:
- ✅ Token acquisition adds ~50-200ms per MR
- ✅ Minimal impact on total validation time (~1%)
- ✅ Token reuse working (not 4 token calls)

---

## Test Suite 10: Debugging & Monitoring

### Test 10.1: Log Correlation
**Objective**: Verify REQUEST_ID enables log correlation

```bash
# Trigger validation
# Extract REQUEST_ID from webhook log
REQUEST_ID_SHORT=$(grep "=== NEW WEBHOOK REQUEST ===" webhook-server.log | tail -1 | grep -o '\[[^]]*\]' | tr -d '[]')

# Find all logs with this REQUEST_ID
grep -r "$REQUEST_ID_SHORT" /home/docker/tmp/mr-validator-logs/
```

**Success Criteria**:
- ✅ REQUEST_ID found in webhook-server.log
- ✅ REQUEST_ID found in rate-my-mr log
- ✅ REQUEST_ID found in gitlab-api log
- ✅ All logs correlatable
- ✅ Can trace complete flow

### Test 10.2: Log Rotation
**Objective**: Verify log files rotate at size limits

```bash
# Trigger many validations to generate logs
# Check log file sizes
ls -lh /home/docker/tmp/mr-validator-logs/

# Check rotated files exist
ls -lh /home/docker/tmp/mr-validator-logs/webhook-server.log*
ls -lh /home/docker/tmp/mr-validator-logs/rate-my-mr-*.log*
```

**Success Criteria**:
- ✅ webhook-server.log rotates at 100MB
- ✅ Up to 5 backup files (webhook-server.log.1 through .5)
- ✅ Validator logs rotate at 50MB
- ✅ Up to 3 backup files per validator log

### Test 10.3: Debugging Information Quality
**Objective**: Verify logs contain sufficient debugging info

```bash
# Review logs for completeness
cat /home/docker/tmp/mr-validator-logs/rate-my-mr-<request-id>.log
```

**Success Criteria**:
- ✅ REQUEST_ID in every log line
- ✅ Timestamps present
- ✅ Clear error messages
- ✅ Stack traces on exceptions
- ✅ API request/response details
- ✅ Retry attempts logged

---

## Test Report Template

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
- ... (continue for all tests)

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

---

## Automation Scripts

### Quick Test Script
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

### Full Test Script
```bash
#!/bin/bash
# full-test.sh - Run comprehensive tests

# Run all test suites
# Log results
# Generate report
```

---

## Test Data Requirements

### Sample GitLab Webhook Payloads

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

### Test GitLab Projects

Recommended test projects:
1. **Small MR**: 1-2 files, <100 LOC changed
2. **Medium MR**: 5-10 files, 500 LOC changed
3. **Large MR**: 50+ files, 5000+ LOC changed
4. **Complex MR**: High cyclomatic complexity
5. **Security MR**: Contains potential vulnerabilities

---

## Success Criteria Summary

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

---

**Test Plan Status**: Ready for execution
**Prerequisites**: GitLab instance, BFA service (for adapter tests)
**Estimated Time**: 4-6 hours for complete test suite

