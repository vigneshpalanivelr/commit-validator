# Logging Configuration Guide

**Date**: 2025-11-08
**Status**: Implementation Complete - Ready for Integration

---

## Overview

The new structured logging system provides:
- ✅ Pipe-separated, column-aligned format for easy parsing and visual scanning
- ✅ Millisecond precision timestamps
- ✅ Correlation IDs for request tracing
- ✅ Organized log directory structure (date/project-based)
- ✅ Key-value structured logging
- ✅ Configurable via environment variables
- ✅ Log rotation with configurable size limits

**Log Format**:
```
YYYY-MM-DD HH:MM:SS.mmm | LEVEL    | module.name                    | REQ_ID   | Message | key=value
```

**Example**:
```
2025-11-08 14:23:45.123 | INFO     | rate_my_mr.gitlab              | 4adcc17d | MR fetched | mr_iid=42 project=foo/bar
2025-11-08 14:23:45.456 | DEBUG    | rate_my_mr.llm_adapter         | 4adcc17d | JWT token acquired | duration_ms=234
2025-11-08 14:23:46.789 | WARNING  | rate_my_mr.security_scan       | 4adcc17d | Vulnerability found | severity=high file=auth.py
```

---

## Configuration via Environment Variables

### Required Variables

| Variable | Description | Default | Used By |
|----------|-------------|---------|---------|
| `LOG_DIR` | Base directory for logs | `/home/docker/tmp/mr-validator-logs` | All validators |
| `LOG_LEVEL` | Logging level | `DEBUG` | All validators |
| `LOG_MAX_BYTES` | Max size per log file | `52428800` (50MB) | All validators |
| `LOG_BACKUP_COUNT` | Number of backup files | `3` | All validators |
| `LOG_STRUCTURE` | Log structure type | `organized` | All validators |

### Environment Variable Details

#### `LOG_DIR` - Persistent Log Directory

**Purpose**: Base directory where all logs are stored

**Default**: `/home/docker/tmp/mr-validator-logs`

**Examples**:
```bash
# Store logs in NFS-mounted directory
LOG_DIR=/mnt/nfs/mr-validator-logs

# Store logs in local persistent volume
LOG_DIR=/var/log/mr-validator

# Store logs in Docker volume
LOG_DIR=/home/docker/logs
```

**Important**: The directory must be writable by the container user (UID 1000 or docker user)

---

#### `LOG_LEVEL` - Logging Verbosity

**Purpose**: Control logging verbosity

**Default**: `DEBUG`

**Valid Values**: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`

**Examples**:
```bash
# Production: INFO level
LOG_LEVEL=INFO

# Development: DEBUG level
LOG_LEVEL=DEBUG

# Errors only
LOG_LEVEL=ERROR
```

---

#### `LOG_MAX_BYTES` - Log File Size Limit

**Purpose**: Maximum size of each log file before rotation

**Default**: `52428800` (50MB)

**Examples**:
```bash
# 10MB files
LOG_MAX_BYTES=10485760

# 100MB files (webhook server)
LOG_MAX_BYTES=104857600

# 200MB files
LOG_MAX_BYTES=209715200
```

---

#### `LOG_BACKUP_COUNT` - Rotation Backup Count

**Purpose**: Number of rotated log files to keep

**Default**: `3`

**Examples**:
```bash
# Keep 5 backup files
LOG_BACKUP_COUNT=5

# Keep 10 backup files
LOG_BACKUP_COUNT=10

# No backups (only current log)
LOG_BACKUP_COUNT=0
```

**Note**: With `LOG_MAX_BYTES=50MB` and `LOG_BACKUP_COUNT=3`, you'll have:
- Current log: `rate-my-mr-12345678.log` (up to 50MB)
- Backup 1: `rate-my-mr-12345678.log.1` (50MB)
- Backup 2: `rate-my-mr-12345678.log.2` (50MB)
- Backup 3: `rate-my-mr-12345678.log.3` (50MB)
- **Total**: Up to 200MB per validator instance

---

#### `LOG_STRUCTURE` - Directory Organization

**Purpose**: Choose between organized (date/project-based) or flat structure

**Default**: `organized`

**Valid Values**: `organized`, `flat`

---

## Log Directory Structure

### Organized Structure (Default)

**Recommended for production**: Easy to find logs by date and project

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
    │   │   │   ├── rate-my-mr-4adcc17d.log.2
    │   │   │   └── gitlab-api-4adcc17d.log
    │   │   │
    │   │   └── mr-2/
    │   │       ├── rate-my-mr-8b3ef21a.log
    │   │       └── gitlab-api-8b3ef21a.log
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

**Benefits**:
- ✅ Easy to find logs by date
- ✅ Easy to find logs by project
- ✅ Easy to find logs by MR
- ✅ Automatic cleanup by date (delete old date directories)
- ✅ Clear separation of webhook vs validation logs

**Use Cases**:
- Production environments
- Long-term log retention
- Multiple projects with high MR volume
- Compliance/audit requirements

---

### Flat Structure (Legacy)

**Used when**: `LOG_STRUCTURE=flat`

```
/home/docker/tmp/mr-validator-logs/
├── webhook-server.log
├── webhook-server.log.1
├── webhook-server.log.2
├── rate-my-mr-4adcc17d-container123.log
├── rate-my-mr-4adcc17d-container123.log.1
├── rate-my-mr-8b3ef21a-container456.log
├── gitlab-api-4adcc17d-container123.log
└── gitlab-api-8b3ef21a-container456.log
```

**Benefits**:
- ✅ Simple structure
- ✅ All logs in one place
- ✅ Backward compatible

**Use Cases**:
- Development/testing
- Single project
- Low MR volume
- Temporary deployments

---

## Docker Configuration Changes

### 1. Update `mrproper.env`

Add logging configuration variables:

**Before**:
```bash
# mrproper.env
GITLAB_ACCESS_TOKEN=glpat-your-token-here
AI_SERVICE_URL=http://10.31.88.29:6006/generate
BFA_HOST=api-gateway.internal.com
```

**After**:
```bash
# mrproper.env
GITLAB_ACCESS_TOKEN=glpat-your-token-here
AI_SERVICE_URL=http://10.31.88.29:6006/generate
BFA_HOST=api-gateway.internal.com

# Logging Configuration
LOG_DIR=/home/docker/tmp/mr-validator-logs
LOG_LEVEL=INFO
LOG_MAX_BYTES=52428800
LOG_BACKUP_COUNT=3
LOG_STRUCTURE=organized
```

---

### 2. Webhook Server Docker Command

Update the `docker run` command to:
1. Pass logging environment variables
2. Mount persistent volume for logs

**Before**:
```bash
docker run -d \
  --name webhook-server \
  --env-file mrproper.env \
  -p 6565:6565 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  mr-checker-vp-test \
  webhook-server
```

**After**:
```bash
docker run -d \
  --name webhook-server \
  --env-file mrproper.env \
  -p 6565:6565 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /mnt/nfs/mr-validator-logs:/home/docker/tmp/mr-validator-logs \
  -e LOG_DIR=/home/docker/tmp/mr-validator-logs \
  -e LOG_LEVEL=INFO \
  -e LOG_MAX_BYTES=104857600 \
  -e LOG_BACKUP_COUNT=5 \
  -e LOG_STRUCTURE=organized \
  mr-checker-vp-test \
  webhook-server
```

**Key Changes**:
- ✅ Added volume mount: `-v /mnt/nfs/mr-validator-logs:/home/docker/tmp/mr-validator-logs`
- ✅ Added logging environment variables
- ✅ Webhook server uses 100MB files and 5 backups (higher traffic)

---

### 3. Validator Container Spawn (in webhook-server)

Update `webhook-server/server.py` to pass logging variables to spawned validator containers.

**File**: `webhook-server/server.py`

**Before**:
```python
docker_run_command = [
    "docker", "run", "--rm",
    "--env", f"GITLAB_ACCESS_TOKEN={token}",
    "--env", f"AI_SERVICE_URL={ai_service_url}",
    "--env", f"BFA_HOST={bfa_host}",
    "--env", f"PROJECT_ID={project_id}",
    "--env", f"MR_IID={mr_iid}",
    "--env", f"REQUEST_ID={request_id}",
    "mr-checker-vp-test",
    "rate-my-mr",
    project_encoded,
    str(mr_iid)
]
```

**After**:
```python
# Get logging configuration from environment
log_dir = os.environ.get('LOG_DIR', '/home/docker/tmp/mr-validator-logs')
log_level = os.environ.get('LOG_LEVEL', 'DEBUG')
log_max_bytes = os.environ.get('LOG_MAX_BYTES', '52428800')
log_backup_count = os.environ.get('LOG_BACKUP_COUNT', '3')
log_structure = os.environ.get('LOG_STRUCTURE', 'organized')

docker_run_command = [
    "docker", "run", "--rm",
    "--env", f"GITLAB_ACCESS_TOKEN={token}",
    "--env", f"AI_SERVICE_URL={ai_service_url}",
    "--env", f"BFA_HOST={bfa_host}",
    "--env", f"PROJECT_ID={project_id}",
    "--env", f"MR_IID={mr_iid}",
    "--env", f"REQUEST_ID={request_id}",
    # Pass logging configuration
    "--env", f"LOG_DIR={log_dir}",
    "--env", f"LOG_LEVEL={log_level}",
    "--env", f"LOG_MAX_BYTES={log_max_bytes}",
    "--env", f"LOG_BACKUP_COUNT={log_backup_count}",
    "--env", f"LOG_STRUCTURE={log_structure}",
    # Mount log directory
    "-v", f"{log_dir}:{log_dir}",
    "mr-checker-vp-test",
    "rate-my-mr",
    project_encoded,
    str(mr_iid)
]
```

**Key Changes**:
- ✅ Read logging configuration from webhook server's environment
- ✅ Pass configuration to validator containers
- ✅ Mount log directory into validator containers

---

### 4. Development/Testing Docker Command

For local testing without webhook server:

```bash
docker run --rm \
  --env-file mrproper.env \
  -v $(pwd)/logs:/home/docker/tmp/mr-validator-logs \
  -e LOG_DIR=/home/docker/tmp/mr-validator-logs \
  -e LOG_LEVEL=DEBUG \
  -e LOG_STRUCTURE=organized \
  -e PROJECT_ID=vigneshpalanivelr/commit-validator \
  -e MR_IID=1 \
  -e REQUEST_ID=test_$(date +%s)_$(openssl rand -hex 4) \
  mr-checker-vp-test \
  rate-my-mr \
  vigneshpalanivelr%2Fcommit-validator \
  1
```

**Check logs after run**:
```bash
ls -lh logs/validations/$(date +%Y-%m-%d)/vigneshpalanivelr_commit-validator/mr-1/
```

---

## Persistent Volume Setup

### Option 1: NFS Mount (Recommended for Production)

**Benefits**: Shared across multiple Docker hosts, survives container/host restarts

**Setup**:
```bash
# 1. Create NFS mount point
sudo mkdir -p /mnt/nfs/mr-validator-logs

# 2. Mount NFS share
sudo mount -t nfs nfs-server.internal.com:/exports/mr-validator-logs /mnt/nfs/mr-validator-logs

# 3. Add to /etc/fstab for persistence
echo "nfs-server.internal.com:/exports/mr-validator-logs /mnt/nfs/mr-validator-logs nfs defaults 0 0" | sudo tee -a /etc/fstab

# 4. Set permissions
sudo chown -R 1000:1000 /mnt/nfs/mr-validator-logs
```

**Docker Configuration**:
```bash
# In mrproper.env
LOG_DIR=/home/docker/tmp/mr-validator-logs

# In docker run command
-v /mnt/nfs/mr-validator-logs:/home/docker/tmp/mr-validator-logs
```

---

### Option 2: Docker Named Volume

**Benefits**: Managed by Docker, simple setup

**Setup**:
```bash
# Create named volume
docker volume create mr-validator-logs

# Inspect volume location
docker volume inspect mr-validator-logs
```

**Docker Configuration**:
```bash
# In docker run command
-v mr-validator-logs:/home/docker/tmp/mr-validator-logs
```

**Access logs**:
```bash
# Find volume location
VOLUME_PATH=$(docker volume inspect mr-validator-logs --format '{{ .Mountpoint }}')

# List logs
sudo ls -lh $VOLUME_PATH/validations/$(date +%Y-%m-%d)/
```

---

### Option 3: Host Directory (Development)

**Benefits**: Easy to access, simple for development

**Setup**:
```bash
# Create directory
mkdir -p /opt/mr-validator-logs

# Set permissions
sudo chown -R 1000:1000 /opt/mr-validator-logs
```

**Docker Configuration**:
```bash
# In docker run command
-v /opt/mr-validator-logs:/home/docker/tmp/mr-validator-logs
```

---

## Log Retention and Cleanup

### Automatic Rotation

Log rotation is automatic based on `LOG_MAX_BYTES` and `LOG_BACKUP_COUNT`.

**Example**: `LOG_MAX_BYTES=50MB`, `LOG_BACKUP_COUNT=3`
- Current log grows to 50MB → rotated to `.1`
- `.1` becomes `.2`, `.2` becomes `.3`, `.3` is deleted

---

### Manual Cleanup Scripts

#### Cleanup Old Dates (Organized Structure)

```bash
#!/bin/bash
# cleanup-old-logs.sh

LOG_BASE="/mnt/nfs/mr-validator-logs"
DAYS_TO_KEEP=30

# Find and delete validation logs older than 30 days
find "$LOG_BASE/validations" -type d -name "20*" -mtime +$DAYS_TO_KEEP -exec rm -rf {} \;

# Find and delete webhook logs older than 30 days
find "$LOG_BASE/webhook" -type d -name "20*" -mtime +$DAYS_TO_KEEP -exec rm -rf {} \;

echo "Cleaned up logs older than $DAYS_TO_KEEP days"
```

**Cron Schedule**:
```bash
# Run daily at 2 AM
0 2 * * * /opt/scripts/cleanup-old-logs.sh
```

---

#### Disk Space Monitoring

```bash
#!/bin/bash
# monitor-log-disk.sh

LOG_BASE="/mnt/nfs/mr-validator-logs"
THRESHOLD=80  # Alert if >80% used

# Get disk usage percentage
USAGE=$(df "$LOG_BASE" | tail -1 | awk '{print $5}' | sed 's/%//')

if [ "$USAGE" -gt "$THRESHOLD" ]; then
    echo "WARNING: Log disk usage at ${USAGE}%"
    # Send alert (email, Slack, PagerDuty, etc.)
fi
```

---

## Viewing and Analyzing Logs

### View Latest Logs for MR

**Organized Structure**:
```bash
# View latest rate-my-mr log for project/MR
LOG_DIR=/mnt/nfs/mr-validator-logs
PROJECT="vigneshpalanivelr_commit-validator"
MR_IID=42
DATE=$(date +%Y-%m-%d)

tail -f "$LOG_DIR/validations/$DATE/$PROJECT/mr-$MR_IID/rate-my-mr-*.log"
```

---

### Search Logs by Correlation ID

```bash
# Find all logs for a specific REQUEST_ID
REQUEST_ID_SHORT="4adcc17d"

grep "$REQUEST_ID_SHORT" /mnt/nfs/mr-validator-logs/validations/**/**/**/*.log
```

---

### Parse Structured Logs

**Extract key-value pairs**:
```bash
# Extract all pipeline_id values
grep "pipeline_id=" /path/to/log.log | sed 's/.*pipeline_id=\([^ ]*\).*/\1/'

# Extract errors with severity
grep "severity=" /path/to/log.log | awk -F '|' '{print $3, $5, $6}'
```

---

### Aggregate Logs with `jq` (if converted to JSON)

```bash
# Convert pipe format to JSON for analysis
cat rate-my-mr-*.log | awk -F '|' '{
    print "{"
    print "  \"timestamp\": \"" $1 "\","
    print "  \"level\": \"" $2 "\","
    print "  \"module\": \"" $3 "\","
    print "  \"correlation_id\": \"" $4 "\","
    print "  \"message\": \"" $5 "\""
    print "}"
}' | jq -s '.'
```

---

## Example Log Outputs

### rate-my-mr Validation

```
2025-11-08 14:23:45.123 | INFO     | rate_my_mr.gitlab              | 4adcc17d | Starting MR validation | project=vigneshpalanivelr/commit-validator mr_iid=42
2025-11-08 14:23:45.234 | DEBUG    | rate_my_mr.gitlab              | 4adcc17d | Fetching MR details | mr_iid=42
2025-11-08 14:23:45.567 | DEBUG    | rate_my_mr.gitlab              | 4adcc17d | MR fetched | title="Fix authentication bug" author=vigneshpalanivelr
2025-11-08 14:23:45.678 | DEBUG    | rate_my_mr.llm_adapter         | 4adcc17d | BFA_HOST configured | host=api-gateway.internal.com
2025-11-08 14:23:45.789 | DEBUG    | rate_my_mr.llm_adapter         | 4adcc17d | Acquiring JWT token | project_id=123 mr_iid=42
2025-11-08 14:23:46.012 | INFO     | rate_my_mr.llm_adapter         | 4adcc17d | JWT token acquired | duration_ms=223
2025-11-08 14:23:46.123 | DEBUG    | rate_my_mr.rate_my_mr          | 4adcc17d | Generating summary | prompt_size=1234
2025-11-08 14:23:48.456 | INFO     | rate_my_mr.rate_my_mr          | 4adcc17d | AI summary generated | duration_ms=2333 tokens=456
2025-11-08 14:23:48.567 | DEBUG    | rate_my_mr.loc                 | 4adcc17d | Calculating LOC | files=15
2025-11-08 14:23:48.789 | INFO     | rate_my_mr.loc                 | 4adcc17d | LOC calculated | loc=1234 files=15
2025-11-08 14:23:48.890 | DEBUG    | rate_my_mr.security_scan       | 4adcc17d | Running security scan | files=15
2025-11-08 14:23:49.123 | WARNING  | rate_my_mr.security_scan       | 4adcc17d | Vulnerability found | severity=medium type=sql_injection file=api.py line=45
2025-11-08 14:23:49.234 | INFO     | rate_my_mr.security_scan       | 4adcc17d | Security scan complete | vulnerabilities=1 duration_ms=344
2025-11-08 14:23:49.345 | INFO     | rate_my_mr.cal_rating          | 4adcc17d | Rating calculated | score=7.5 grade=B
2025-11-08 14:23:49.456 | INFO     | rate_my_mr.gitlab              | 4adcc17d | Posting comment to MR | mr_iid=42
2025-11-08 14:23:49.678 | INFO     | rate_my_mr.gitlab              | 4adcc17d | MR validation complete | duration_ms=4555 score=7.5
```

---

### Webhook Server

```
2025-11-08 14:23:44.001 | INFO     | webhook.server                 | unknown  | Webhook server started | port=6565
2025-11-08 14:23:44.912 | INFO     | webhook.server                 | 4adcc17d | Webhook received | project=vigneshpalanivelr/commit-validator mr_iid=42 action=update
2025-11-08 14:23:45.023 | DEBUG    | webhook.server                 | 4adcc17d | Spawning validator container | request_id=webhook_1699453425_4adcc17d
2025-11-08 14:23:45.123 | INFO     | webhook.server                 | 4adcc17d | Validator container spawned | container_id=abc123def456
2025-11-08 14:23:50.234 | INFO     | webhook.server                 | 4adcc17d | Validator container completed | exit_code=0 duration_ms=5111
```

---

## Troubleshooting

### Issue 1: Logs Not Created

**Symptom**: No log files in LOG_DIR

**Checks**:
```bash
# 1. Verify environment variables
docker exec <container> env | grep LOG

# 2. Check directory permissions
docker exec <container> ls -la /home/docker/tmp/mr-validator-logs

# 3. Check disk space
docker exec <container> df -h
```

**Solutions**:
- Ensure LOG_DIR is writable (UID 1000)
- Check disk space available
- Verify volume mount is correct

---

### Issue 2: Logs in Wrong Location

**Symptom**: Logs appear in container but not on host

**Cause**: Volume mount not configured

**Solution**:
```bash
# Add volume mount to docker run
-v /mnt/nfs/mr-validator-logs:/home/docker/tmp/mr-validator-logs
```

---

### Issue 3: Large Log Files Filling Disk

**Symptom**: Disk usage growing rapidly

**Solutions**:
1. Reduce `LOG_MAX_BYTES`:
   ```bash
   LOG_MAX_BYTES=10485760  # 10MB instead of 50MB
   ```

2. Reduce `LOG_BACKUP_COUNT`:
   ```bash
   LOG_BACKUP_COUNT=1  # Keep only 1 backup
   ```

3. Change `LOG_LEVEL` to INFO:
   ```bash
   LOG_LEVEL=INFO  # Less verbose than DEBUG
   ```

4. Set up automatic cleanup:
   ```bash
   # Delete logs older than 7 days
   find /mnt/nfs/mr-validator-logs -type f -mtime +7 -delete
   ```

---

## Migration from Old Logging

### Step 1: Deploy New Code

The new logging configuration is backward compatible. No code changes needed yet.

---

### Step 2: Configure Environment Variables

Add to `mrproper.env`:
```bash
LOG_DIR=/home/docker/tmp/mr-validator-logs
LOG_LEVEL=INFO
LOG_STRUCTURE=organized
```

---

### Step 3: Update Docker Commands

Add volume mount and environment variables as shown above.

---

### Step 4: Verify Logs

```bash
# Check new log format
LOG_DIR=/mnt/nfs/mr-validator-logs
tail -f $LOG_DIR/validations/$(date +%Y-%m-%d)/**/**/rate-my-mr-*.log
```

---

## Next Steps

1. ✅ Core formatter implemented (`logging_config.py`)
2. ⏳ Integrate into `rate_my_mr_gitlab.py`
3. ⏳ Integrate into `rate_my_mr.py`
4. ⏳ Integrate into `gitlab.py`
5. ⏳ Integrate into `llm_adapter.py`
6. ⏳ Integrate into `webhook-server/server.py`
7. ⏳ Test with real MR validations
8. ⏳ Update Docker compose/deployment scripts

---

## See Also

- **Debugging**: [DEBUGGING_GUIDE.md](./DEBUGGING_GUIDE.md)
- **Architecture**: [ARCHITECTURE.md](./ARCHITECTURE.md)

---

**Last Updated**: 2025-11-08
