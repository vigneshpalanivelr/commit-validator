# Logging Improvement Plan - Structured Format with Alignment

**Goal**: Upgrade logging to use pipe-separated, column-aligned, structured format with milliseconds

**Status**: Not yet implemented
**Effort**: 4-6 hours
**Priority**: Medium-High (improves debugging significantly)

---

## Current vs Desired Format

### Current Format
```
2025-11-08 19:07:39 - [12345678] - gitlab.py - ERROR - Message here
```

**Problems**:
- No milliseconds (can't distinguish rapid events)
- Dash separators (hard to parse, messy)
- No alignment (hard to scan)
- Filename instead of module
- Plain text only

### Desired Format
```
2025-11-05 11:04:39.397 | DEBUG    | src.error_handler              | 4adcc17d | Attempt 1/4 for fetch_job_log
2025-11-05 11:04:39.480 | DEBUG    | urllib3.connectionpool         | 4adcc17d | https://git.internal.com:443 "GET /api/v4/..." 200 None
2025-11-05 11:04:39.558 | INFO     | src.webhook_listener           | 4adcc17d | Pipeline logs fetched | pipeline_id=1063551 duration_ms=1036
```

**Format Breakdown**:
1. **Timestamp with milliseconds**: `2025-11-05 11:04:39.397`
2. **Pipe separator**: `|`
3. **Log level (padded to 8 chars)**: `DEBUG    ` or `INFO     `
4. **Pipe separator**: `|`
5. **Module name (padded to 30 chars)**: `src.error_handler              `
6. **Pipe separator**: `|`
7. **Correlation ID (8 chars)**: `4adcc17d`
8. **Pipe separator**: `|`
9. **Message with structured fields**: `key=value key2=value2`

**Advantages**:
- ✅ Millisecond precision for timing analysis
- ✅ Clean visual separation with pipes
- ✅ **Column alignment** - easy to scan logs
- ✅ **Structured logging** - easy to parse and filter
- ✅ Module names instead of filenames
- ✅ Consistent correlation ID placement

---

## Implementation Options

### Option A: Custom Formatter (Recommended for now)
**Pros**:
- Simple to implement
- No new dependencies
- Compatible with existing logging infrastructure

**Cons**:
- Manual structured logging (need to format key=value in messages)
- Less flexible than dedicated library

### Option B: Loguru Library
**Pros**:
- Built-in structured logging
- Beautiful formatting out of the box
- Better performance
- Async logging support

**Cons**:
- New dependency (need to add to requirements.txt)
- Need to migrate all existing logging calls
- More complex refactoring

### Option C: structlog Library
**Pros**:
- Industry standard for structured logging
- JSON output support
- Excellent for log aggregation systems

**Cons**:
- Steeper learning curve
- Bigger migration effort
- May be overkill for current needs

---

## Recommended Approach: Option A (Custom Formatter)

Start with custom formatter, migrate to Loguru later if needed.

---

## Implementation Details

### Step 1: Create Custom Formatter

**File**: `mrproper/mrproper/rate_my_mr/logging_config.py` (NEW)

```python
"""
Structured logging configuration with aligned, pipe-separated format.

Format:
YYYY-MM-DD HH:MM:SS.mmm | LEVEL    | module.name                    | REQ_ID   | Message | key=value

Example:
2025-11-08 14:23:45.123 | INFO     | rate_my_mr.gitlab              | 4adcc17d | MR fetched | mr_iid=42 project=foo/bar
"""

import logging
import os


class AlignedPipeFormatter(logging.Formatter):
    """
    Custom formatter with pipe-separated, column-aligned output.

    Features:
    - Millisecond precision timestamps
    - Pipe separators for clean parsing
    - Column alignment for visual scanning
    - Correlation ID (REQUEST_ID_SHORT)
    - Module name instead of filename
    """

    # Column widths for alignment
    LEVEL_WIDTH = 8
    MODULE_WIDTH = 30
    CORRELATION_WIDTH = 8

    def __init__(self):
        # Format with milliseconds
        super().__init__(
            fmt='%(asctime)s.%(msecs)03d | %(levelname)-8s | %(module_name)-30s | %(correlation_id)-8s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

    def format(self, record):
        # Add correlation ID (REQUEST_ID_SHORT)
        request_id = os.environ.get('REQUEST_ID', 'unknown')
        record.correlation_id = request_id.split('_')[-1][:8] if request_id != 'unknown' else 'unknown'

        # Add module name (instead of filename)
        # Convert filename to module name: rate_my_mr_gitlab.py → rate_my_mr.gitlab
        module_name = record.name if record.name else record.module

        # Truncate or pad module name to fit width
        if len(module_name) > self.MODULE_WIDTH:
            record.module_name = module_name[:self.MODULE_WIDTH - 3] + '...'
        else:
            record.module_name = module_name

        # Format the record
        return super().format(record)


def setup_logging(log_file_path, request_id='unknown'):
    """
    Setup logging with aligned pipe format.

    Args:
        log_file_path: Path to log file
        request_id: REQUEST_ID for correlation

    Returns:
        logging.Logger: Configured logger
    """
    # Ensure log directory exists
    os.makedirs(os.path.dirname(log_file_path), exist_ok=True)

    # Set REQUEST_ID in environment for formatter
    os.environ['REQUEST_ID'] = request_id

    # Create formatter
    formatter = AlignedPipeFormatter()

    # File handler with rotation
    from logging.handlers import RotatingFileHandler
    file_handler = RotatingFileHandler(
        log_file_path,
        maxBytes=50 * 1024 * 1024,  # 50 MB
        backupCount=3,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # Root logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.handlers = []  # Clear existing handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


# Structured logging helper
class StructuredLogger:
    """
    Helper for structured logging with key=value pairs.

    Usage:
        logger = StructuredLogger(logging.getLogger(__name__))
        logger.info("Pipeline processed", pipeline_id=123, duration_ms=456, status="success")

    Output:
        2025-11-08 14:23:45.123 | INFO     | rate_my_mr.gitlab              | 4adcc17d | Pipeline processed | pipeline_id=123 duration_ms=456 status=success
    """

    def __init__(self, logger):
        self.logger = logger

    def _format_message(self, message, **kwargs):
        """Format message with structured fields."""
        if kwargs:
            # Convert kwargs to key=value pairs
            fields = ' '.join(f'{k}={v}' for k, v in kwargs.items())
            return f'{message} | {fields}'
        return message

    def debug(self, message, **kwargs):
        self.logger.debug(self._format_message(message, **kwargs))

    def info(self, message, **kwargs):
        self.logger.info(self._format_message(message, **kwargs))

    def warning(self, message, **kwargs):
        self.logger.warning(self._format_message(message, **kwargs))

    def error(self, message, **kwargs):
        self.logger.error(self._format_message(message, **kwargs))

    def critical(self, message, **kwargs):
        self.logger.critical(self._format_message(message, **kwargs))
```

### Step 2: Update rate_my_mr_gitlab.py

**Before**:
```python
# Lines 23-46 in rate_my_mr_gitlab.py
file_handler = logging.handlers.RotatingFileHandler(...)
file_handler.setFormatter(logging.Formatter(
    f'%(asctime)s - [{REQUEST_ID_SHORT}] - %(filename)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
))
```

**After**:
```python
from .logging_config import setup_logging, StructuredLogger

# Setup logging with new format
logger = setup_logging(log_filename, REQUEST_ID)
slog = StructuredLogger(logger)

# Usage examples:
slog.info("MR analysis started", project=proj, mr_iid=mriid)
slog.debug("Fetching MR data from GitLab API", project=proj, mr_iid=mriid)
slog.info("MR fetched successfully", mr_iid=mriid, title=mr.title, state=mr.state)
slog.error("GitLab API error", error_type=type(api_error).__name__, details=str(api_error))
```

### Step 3: Update gitlab.py

Similar changes to use new logging config.

### Step 4: Update webhook-server/server.py

Similar changes for webhook server logging.

---

## Example Output After Implementation

### Current Output:
```
2025-11-08 19:07:39 - [12345678] - rate_my_mr_gitlab.py - INFO - [12345678] [DEBUG] Fetching MR data from GitLab API...
2025-11-08 19:07:40 - [12345678] - rate_my_mr_gitlab.py - INFO - [12345678] [DEBUG] MR fetched successfully: Fix authentication bug
2025-11-08 19:07:41 - [12345678] - rate_my_mr.py - DEBUG - [DEBUG] AI Service Request - URL: http://10.31.88.29:6006/generate
```

### After Implementation:
```
2025-11-08 19:07:39.123 | INFO     | rate_my_mr.gitlab              | 12345678 | MR analysis started | project=foo%2Fbar mr_iid=42
2025-11-08 19:07:39.124 | DEBUG    | rate_my_mr.gitlab              | 12345678 | Fetching MR data from GitLab API | project=foo%2Fbar mr_iid=42
2025-11-08 19:07:40.456 | INFO     | rate_my_mr.gitlab              | 12345678 | MR fetched successfully | mr_iid=42 title="Fix authentication bug" state=opened
2025-11-08 19:07:41.234 | DEBUG    | rate_my_mr.rate_my_mr          | 12345678 | AI Service Request | url=http://10.31.88.29:6006/generate payload_size=1234 timeout=120
2025-11-08 19:07:42.567 | INFO     | rate_my_mr.rate_my_mr          | 12345678 | AI Service Response | status_code=200 content_length=5678 attempt=1
2025-11-08 19:07:45.890 | INFO     | rate_my_mr.gitlab              | 12345678 | Discussion posted to GitLab | discussion_id=123 mr_iid=42
2025-11-08 19:07:45.891 | INFO     | rate_my_mr.gitlab              | 12345678 | MR analysis completed | mr_iid=42 duration_ms=6768 status=success
```

### Filtering Examples:

```bash
# Filter by correlation ID
grep "12345678" rate-my-mr.log

# Filter by level
grep "| ERROR " rate-my-mr.log

# Filter by module
grep "| rate_my_mr.gitlab " rate-my-mr.log

# Extract structured fields
grep "duration_ms" rate-my-mr.log | awk -F'|' '{print $5}'

# Find slow requests (duration > 5000ms)
grep "duration_ms=" rate-my-mr.log | grep -oP 'duration_ms=\K[0-9]+' | awk '$1>5000 {print}'
```

---

## Implementation Phases

### Phase 1: Core Formatter (2-3 hours)
1. Create `logging_config.py` with `AlignedPipeFormatter`
2. Add `StructuredLogger` helper class
3. Test formatter in isolation

### Phase 2: Migrate rate-my-mr (2-3 hours)
1. Update `rate_my_mr_gitlab.py` to use new formatter
2. Update `rate_my_mr.py` to use structured logging
3. Update `gitlab.py`
4. Update `llm_adapter.py`
5. Test with actual MR validation

### Phase 3: Migrate webhook-server (1 hour)
1. Update `webhook-server/server.py`
2. Test webhook processing

### Phase 4: Update Documentation (1 hour)
1. Update `DEBUGGING_GUIDE.md` with new log format examples
2. Update `README.md` log examples
3. Update `ARCHITECTURE.md` logging section

---

## Benefits After Implementation

### For Debugging:
- ✅ **Millisecond precision** - trace rapid events precisely
- ✅ **Visual alignment** - scan logs 10x faster
- ✅ **Easy parsing** - pipe separators perfect for scripts
- ✅ **Structured fields** - extract metrics easily

### For Monitoring:
- ✅ **Duration tracking** - every operation logged with `duration_ms`
- ✅ **Error correlation** - structured error details
- ✅ **Performance analysis** - extract timing data easily

### For Operations:
- ✅ **Consistent format** - all logs look the same
- ✅ **Log aggregation ready** - easy to parse and index
- ✅ **Grep-friendly** - filter by any column

---

## Migration Strategy

### Option A: Big Bang (Recommended)
- Migrate all logging in one PR
- Test thoroughly
- Deploy once

**Pros**: Consistent format immediately
**Cons**: Larger change, more testing needed

### Option B: Gradual
- Migrate rate-my-mr first
- Then webhook-server
- Then other validators

**Pros**: Smaller changes
**Cons**: Inconsistent format during transition

---

## Risks & Mitigation

### Risk 1: Log Parsing Scripts Break
**Mitigation**: Update `DEBUGGING_GUIDE.md` with new grep examples

### Risk 2: Performance Impact
**Mitigation**: Formatting is fast, no measurable impact expected

### Risk 3: Disk Space
**Mitigation**: Slightly more verbose, but still within rotation limits

---

## Success Criteria

- ✅ All logs use new pipe-separated format
- ✅ Milliseconds present in all timestamps
- ✅ Columns align visually
- ✅ Correlation ID in every log line
- ✅ Structured fields used for important events
- ✅ Documentation updated
- ✅ No performance degradation

---

## Future Enhancements (Post-Implementation)

### Phase 2: JSON Output (Optional)
Add JSON logging for log aggregation systems:

```python
# Example JSON log line
{"timestamp": "2025-11-08T19:07:39.123Z", "level": "INFO", "module": "rate_my_mr.gitlab", "correlation_id": "12345678", "message": "MR fetched", "mr_iid": 42, "title": "Fix bug", "duration_ms": 123}
```

### Phase 3: Log Metrics Export
Export metrics from logs:
- Request duration percentiles (p50, p95, p99)
- Error rates
- AI service latency
- Success/failure counts

### Phase 4: Real-time Log Viewer
Web UI to view logs with:
- Live tail
- Filtering by correlation ID, level, module
- Duration graphs
- Error highlighting

---

## Estimated Effort Summary

| Phase | Effort | Priority |
|-------|--------|----------|
| Phase 1: Core Formatter | 2-3 hours | High |
| Phase 2: Migrate rate-my-mr | 2-3 hours | High |
| Phase 3: Migrate webhook-server | 1 hour | High |
| Phase 4: Update Documentation | 1 hour | Medium |
| **Total** | **6-8 hours** | **High** |

---

## Decision Required

**Question**: Should we proceed with this logging improvement?

**Recommendation**: ✅ **YES** - High value for debugging effort

**Next Steps if Approved**:
1. Implement Phase 1 (core formatter)
2. Test with rate-my-mr
3. Migrate all validators
4. Update documentation
5. Deploy

---

**Status**: Awaiting approval to proceed
**Last Updated**: 2025-11-08
