# MR Validator - Operations & Maintenance Guide

DevOps documentation for deployment, monitoring, debugging, and maintenance.

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
