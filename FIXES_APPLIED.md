# Fixes Applied to rate-my-mr

**Date**: 2025-11-03
**Issues Fixed**: 3 critical problems

---

## Summary of Changes

### ✅ Fix #1: AI Service URL Now Configurable

**Problem**: IP address hardcoded at `10.31.88.29:6006`, not configurable via environment.

**Solution**: Modified `params.py` to read from environment variable `AI_SERVICE_URL`.

**Files Changed**:
- `mrproper/mrproper/params.py`

**Changes**:
```python
# Before:
class RMMConstants(Enum):
    agent_url = "http://10.31.88.29:6006/generate"

# After:
class RMMConstants(Enum):
    agent_url = os.environ.get('AI_SERVICE_URL', 'http://10.31.88.29:6006/generate')
```

**How to Use**:
```bash
# Set custom AI service URL in mrproper.env:
AI_SERVICE_URL=http://my-custom-ai-server:8080/generate

# Or use default (10.31.88.29:6006)
```

---

### ✅ Fix #2: Request ID Correlation (Webhook → Container)

**Problem**: Cannot correlate webhook request `[a1b2c3d4]` with container logs. No way to link webhook request to validator logs.

**Solution**:
1. Webhook server now passes `REQUEST_ID` as environment variable to Docker containers
2. Validators read `REQUEST_ID` and include it in log filenames and messages
3. All log messages now include `[REQUEST_ID_SHORT]` prefix for easy correlation

**Files Changed**:
- `webhook-server/server.py`
- `mrproper/mrproper/rate_my_mr_gitlab.py`
- `mrproper/mrproper/gitlab.py`

**Changes**:

**webhook-server/server.py**:
```python
# Added --env flag to docker run command:
docker_cmd = [
    "docker", "run", "-d", "--rm",
    "--env-file", "mrproper.env",
    "--env", f"REQUEST_ID={request_id}",  # ✅ NEW: Pass request ID
    "--log-driver=syslog",
    # ... rest of command
]
```

**rate_my_mr_gitlab.py**:
```python
# Added at top of file:
REQUEST_ID = os.environ.get('REQUEST_ID', 'unknown')
REQUEST_ID_SHORT = REQUEST_ID.split('_')[-1][:8]

# Updated log filename:
log_filename = f'/home/docker/tmp/mr-validator-logs/rate-my-mr-{REQUEST_ID_SHORT}-{container_id}.log'

# Updated log format:
format=f'%(asctime)s - [{REQUEST_ID_SHORT}] - %(filename)s - %(levelname)s - %(message)s'

# Updated all print statements to include REQUEST_ID:
print(f"[{REQUEST_ID_SHORT}] [DEBUG] Starting MR analysis...")
```

**gitlab.py**:
```python
# Same changes as rate_my_mr_gitlab.py:
REQUEST_ID = os.environ.get('REQUEST_ID', 'unknown')
REQUEST_ID_SHORT = REQUEST_ID.split('_')[-1][:8]
log_filename = f'/home/docker/tmp/mr-validator-logs/gitlab-api-{REQUEST_ID_SHORT}-{container_id}.log'
format=f'%(asctime)s - [{REQUEST_ID_SHORT}] - %(filename)s - %(levelname)s - %(message)s'
```

---

## How Correlation Works Now

### Before Fix:
```
[webhook-server.log]
  2025-11-03 10:30:45 - [a1b2c3d4] === NEW WEBHOOK REQUEST ===
  2025-11-03 10:30:45 - [a1b2c3d4] Starting checker: rate-my-mr

[rate-my-mr-abc123def456.log]  ❌ No correlation!
  2025-11-03 10:30:46 - [DEBUG] Starting MR analysis...
```

**Problem**: No way to know which webhook request triggered which validation!

### After Fix:
```
[webhook-server.log]
  2025-11-03 10:30:45 - [a1b2c3d4] === NEW WEBHOOK REQUEST ===
  2025-11-03 10:30:45 - [a1b2c3d4] Starting checker: rate-my-mr

[rate-my-mr-a1b2c3d4-abc123def456.log]  ✅ Correlates via REQUEST_ID!
  2025-11-03 10:30:46 - [a1b2c3d4] - [DEBUG] Starting MR analysis...
  2025-11-03 10:30:47 - [a1b2c3d4] - [DEBUG] Fetching MR data...

[gitlab-api-a1b2c3d4-abc123def456.log]  ✅ Correlates too!
  2025-11-03 10:30:47 - [a1b2c3d4] - Making GitLab API request: ...
```

**Solution**: You can now `grep "a1b2c3d4" /home/docker/tmp/mr-validator-logs/*.log` to see all related logs!

---

## Benefits

### 1. Easy Debugging
```bash
# Find all logs for a specific request:
grep "a1b2c3d4" /home/docker/tmp/mr-validator-logs/*.log

# Or check specific request log file:
cat /home/docker/tmp/mr-validator-logs/rate-my-mr-a1b2c3d4-*.log
```

### 2. End-to-End Tracing
You can now trace a complete validation flow:
1. Webhook receives request → generates `[a1b2c3d4]`
2. Docker container starts with `REQUEST_ID=20251103_103045_a1b2c3d4`
3. Validator logs include `[a1b2c3d4]` in every message
4. GitLab API logs include `[a1b2c3d4]` in every message
5. Easy to correlate issues across all components!

### 3. Flexible AI Service Configuration
```bash
# Test with different AI service:
echo "AI_SERVICE_URL=http://staging-ai:6006/generate" >> mrproper.env

# Or use production:
echo "AI_SERVICE_URL=http://10.31.88.29:6006/generate" >> mrproper.env
```

---

## Testing

To test these changes:

1. **Build updated Docker image**:
   ```bash
   ./build-docker-images
   ```

2. **Restart webhook server**:
   ```bash
   ./start-server --restart
   ```

3. **Trigger a webhook** (or create test MR in GitLab)

4. **Check logs for correlation**:
   ```bash
   # Find the request ID from webhook log:
   tail -20 /home/docker/tmp/mr-validator-logs/webhook-server.log
   # Example output: [a1b2c3d4] === NEW WEBHOOK REQUEST ===

   # Find corresponding validator logs:
   ls -la /home/docker/tmp/mr-validator-logs/rate-my-mr-a1b2c3d4-*.log
   ls -la /home/docker/tmp/mr-validator-logs/gitlab-api-a1b2c3d4-*.log

   # Verify REQUEST_ID appears in all messages:
   grep "a1b2c3d4" /home/docker/tmp/mr-validator-logs/*.log
   ```

---

## Files Modified Summary

| File | Lines Changed | Purpose |
|------|---------------|---------|
| `mrproper/mrproper/params.py` | 3 lines | Make AI URL configurable |
| `webhook-server/server.py` | 1 line | Pass REQUEST_ID to containers |
| `mrproper/mrproper/rate_my_mr_gitlab.py` | ~30 lines | Use REQUEST_ID in logs |
| `mrproper/mrproper/gitlab.py` | 10 lines | Use REQUEST_ID in logs |

**Total**: ~44 lines changed across 4 files

---

## Next Steps (Optional)

These fixes address the 3 problems you requested. The analysis document (`RATE_MY_MR_ANALYSIS.md`) identifies 7 more issues if you want to tackle them:

**Critical** (not yet fixed):
- Issue #1: Bare exception silences GitLab posting errors (line 451)
- Issue #2: AI functions always return True even on failure (lines 91, 119)

**Medium Priority**:
- Issue #5: No retry logic for AI service
- Issue #6: Git commands without error checking
- Issue #7: Temporary file leaks in loc.py

Let me know if you want me to fix these next!

---

**Status**: ✅ All 3 requested problems fixed and ready to commit!
