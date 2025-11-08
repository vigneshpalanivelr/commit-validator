# LLM Integration Migration Plan

**Date Created**: 2025-11-03
**Last Updated**: 2025-11-08
**Change**: Migrate from direct LLM connection to intermediary API service
**Impact**: Low (with proper planning)

---

## ✅ IMPLEMENTATION STATUS (2025-11-08)

### Completed Items

✅ **JWT Authentication Adapter Implemented** (2025-11-08)
- Created `llm_adapter.py` with complete JWT token authentication
- Token endpoint: `POST http://{BFA_HOST}:8000/api/token`
- LLM endpoint: `POST http://{BFA_HOST}:8000/api/rate-my-mr`
- Token acquired once per MR, reused for all 4 AI calls
- Support for pre-configured tokens via `BFA_TOKEN_KEY`
- Exponential backoff retry logic implemented
- Comprehensive error handling and logging

✅ **Automatic Routing Logic** (2025-11-08)
- Updated `rate_my_mr.py` with automatic adapter routing
- When `BFA_HOST` is set → uses new adapter
- When `BFA_HOST` not set → uses legacy direct connection
- 100% backward compatible

✅ **Environment Variable Setup** (2025-11-08)
- Updated `rate_my_mr_gitlab.py` to set `PROJECT_ID` and `MR_IID`
- Added configuration documentation to `params.py`

✅ **Documentation** (2025-11-08)
- Created `LLM_ADAPTER_IMPLEMENTATION.md` with comprehensive guide
- Includes testing procedures and debugging guide

### Pending Items

⏳ **Request/Response Format Transformation** - AWAITING API SPECIFICATIONS
- `_transform_request()` method currently passes through (assumes same format)
- `_transform_response()` method currently passes through (assumes same format)
- Need actual API format from BFA team to implement transformations

⏳ **Error Response Format Handling** - AWAITING API SPECIFICATIONS
- Need examples of error responses from new API
- Need specific error codes and formats

⏳ **Production Testing** - AWAITING BFA SERVICE AVAILABILITY
- Cannot test until BFA service endpoint is available
- Need to verify token acquisition
- Need to verify all 4 AI calls work
- Need to test error scenarios

### What's Needed to Complete

1. **API Specifications** (from BFA team):
   - Request format for `POST /api/rate-my-mr`
   - Response format from the API
   - Error response formats and codes
   - Any additional headers or parameters

2. **Testing Environment**:
   - BFA_HOST value for testing
   - Test endpoint availability
   - Sample tokens or credentials

### Implementation Location

See **LLM_ADAPTER_IMPLEMENTATION.md** for:
- Detailed implementation architecture
- Configuration options
- Testing procedures
- Debugging guide
- Rollback plan

**Implementation Files**:
- `mrproper/mrproper/llm_adapter.py` (360 lines) - Complete adapter
- `mrproper/mrproper/rate_my_mr.py` - Updated with routing
- `mrproper/mrproper/rate_my_mr_gitlab.py` - Updated with env vars
- `mrproper/mrproper/params.py` - Updated with config docs

---

## Table of Contents

1. [Current State Analysis](#current-state-analysis)
2. [Proposed Architecture](#proposed-architecture)
3. [Impact Assessment](#impact-assessment)
4. [Implementation Plan](#implementation-plan)
5. [Configuration Strategy](#configuration-strategy)
6. [Testing Strategy](#testing-strategy)
7. [Deployment Plan](#deployment-plan)
8. [Rollback Strategy](#rollback-strategy)

---

## Current State Analysis

### Current Architecture
```
rate-my-mr → AI Service (10.31.88.29:6006) → LLM
                         ↓
                    Direct connection
                    (Already has retry logic)
```

### Current Integration Points

**File**: `mrproper/mrproper/rate_my_mr.py`

**Main Function**: `send_request(payload, url, max_retries=3)`
- Location: Line 20
- Current URL: `RMMConstants.agent_url.value`
- Retry logic: ✅ Already implemented (exponential backoff)
- Timeout: 120 seconds per attempt

**AI Calls** (4 total):
1. **Line 115**: `generate_summary()` - MR summary generation
2. **Line 149**: `generate_initial_code_review()` - Code review analysis
3. **Line 182**: `generate_lint_disable_report()` - Lint pattern detection
4. **Line 259**: `generate_added_code_file()` - Security code generation

### Current Request/Response Format

**Request Format**:
```json
{
  "messages": [
    {
      "role": "system",
      "content": "You are a summarizer..."
    },
    {
      "role": "user",
      "content": "{diff_content}"
    }
  ]
}
```

**Response Format**:
```json
{
  "content": [
    {
      "type": "text",
      "text": "AI generated response..."
    }
  ]
}
```

### Current Configuration

**File**: `mrproper/mrproper/params.py`
```python
class RMMConstants(Enum):
    agent_url = os.environ.get('AI_SERVICE_URL', 'http://10.31.88.29:6006/generate')
```

**Environment Variable**: `AI_SERVICE_URL`
- ✅ Already configurable
- ✅ Already documented in README.md

---

## Proposed Architecture

### New Architecture
```
rate-my-mr → Intermediary API Service → LLM
                      ↓
            (Authentication, routing,
             logging, quota management)
                      ↓
                  Response
```

### Benefits of Intermediary Service
1. **Centralized Authentication**: API keys managed in one place
2. **Rate Limiting**: Control LLM usage across all services
3. **Cost Tracking**: Monitor and limit LLM costs
4. **Request/Response Transformation**: Adapt to different LLM providers
5. **Centralized Logging**: All LLM requests logged in one place
6. **Multi-LLM Routing**: Route to different LLMs based on request type
7. **Caching**: Cache common requests to reduce costs

---

## Impact Assessment

### Code Changes Required

#### Minimal Impact Scenario (API Compatible)
**IF** new API service accepts same format:

✅ **No code changes needed!**
- Just update `AI_SERVICE_URL` environment variable
- Example: `AI_SERVICE_URL=http://new-api-service.internal.com/llm/generate`

#### Medium Impact Scenario (Different Format)
**IF** new API service has different request/response format:

**Changes Needed**:
1. Update `send_request()` function to transform request format
2. Update response parsing logic
3. Update error handling for new API errors
4. Update retry logic if needed

**Files to Modify**: 1 file (`rate_my_mr.py`)
**Estimated Effort**: 2-4 hours

#### High Impact Scenario (Authentication Required)
**IF** new API service requires authentication headers:

**Changes Needed**:
1. Add authentication configuration
2. Update `send_request()` to include auth headers
3. Handle authentication errors (401, 403)
4. Add token refresh logic if needed

**Files to Modify**: 2 files (`rate_my_mr.py`, `params.py`)
**Estimated Effort**: 4-6 hours

---

## Implementation Plan

### Phase 1: Information Gathering (1-2 hours)

**Questions to Ask About New API Service**:

1. **Endpoint URL**:
   - What is the new API endpoint?
   - Example: `http://api-gateway.internal.com/v1/llm/generate`

2. **Request Format**:
   - Does it accept the same JSON format?
   - ```json
     {"messages": [...]}  // Same as current?
     ```
   - OR different format?
   - ```json
     {"prompt": "...", "system": "...", "parameters": {...}}
     ```

3. **Response Format**:
   - Does it return the same JSON structure?
   - ```json
     {"content": [{"type": "text", "text": "..."}]}  // Same?
     ```
   - OR different format?
   - ```json
     {"response": "...", "metadata": {...}}
     ```

4. **Authentication**:
   - Does it require authentication?
   - API key in header? (`Authorization: Bearer <token>`)
   - API key in query param? (`?api_key=<key>`)
   - OAuth token?

5. **Rate Limiting**:
   - What are the rate limits?
   - Do we need to implement additional retry logic?
   - Are there specific error codes for rate limit exceeded?

6. **Timeout Settings**:
   - What timeout should we use?
   - Current: 120 seconds per attempt

7. **Error Responses**:
   - What error format does it return?
   - Status codes used?
   - Error message structure?

8. **Additional Headers**:
   - Any required headers? (Content-Type, User-Agent, etc.)
   - Request ID tracking?

### Phase 2: Design Solution (Based on Answers)

#### Option A: No Code Changes (Best Case)
**IF** API is compatible:

```python
# Only configuration change needed
# In mrproper.env:
AI_SERVICE_URL=http://new-api-service.internal.com/llm/generate
```

**Testing**: Update URL and verify all 4 AI calls work

---

#### Option B: Request/Response Transformation

**IF** API has different format, create adapter layer:

**New File**: `mrproper/mrproper/llm_adapter.py`

```python
"""
LLM API Adapter Layer
Handles transformation between rate-my-mr format and intermediary API format.
"""

import os
import requests
import time
from .params import RMMConstants


class LLMAdapter:
    """
    Adapter for intermediary LLM API service.
    Transforms requests/responses between formats.
    """

    def __init__(self, base_url=None, api_key=None):
        self.base_url = base_url or os.environ.get(
            'AI_SERVICE_URL',
            RMMConstants.agent_url.value
        )
        self.api_key = api_key or os.environ.get('AI_SERVICE_API_KEY', '')
        self.timeout = 120
        self.max_retries = 3

    def _transform_request(self, payload):
        """
        Transform from current format to new API format.

        Current format:
        {
            "messages": [
                {"role": "system", "content": "..."},
                {"role": "user", "content": "..."}
            ]
        }

        New format (example - adjust based on actual API):
        {
            "prompt": "user content",
            "system_prompt": "system content",
            "parameters": {
                "max_tokens": 4096,
                "temperature": 0.7
            }
        }
        """
        messages = payload.get('messages', [])

        # Extract system and user messages
        system_content = ""
        user_content = ""

        for msg in messages:
            if msg.get('role') == 'system':
                system_content = msg.get('content', '')
            elif msg.get('role') == 'user':
                user_content = msg.get('content', '')

        # Transform to new format
        new_payload = {
            "prompt": user_content,
            "system_prompt": system_content,
            "parameters": {
                "max_tokens": 4096,
                "temperature": 0.7
            }
        }

        return new_payload

    def _transform_response(self, response_data):
        """
        Transform from new API format to current expected format.

        New format (example):
        {
            "response": "AI generated text...",
            "metadata": {...}
        }

        Current expected format:
        {
            "content": [
                {"type": "text", "text": "AI generated text..."}
            ]
        }
        """
        # Extract response text from new format
        response_text = response_data.get('response', '')

        # Transform to expected format
        transformed = {
            "content": [
                {
                    "type": "text",
                    "text": response_text
                }
            ]
        }

        return transformed

    def _get_headers(self):
        """Get request headers including authentication if needed."""
        headers = {
            "Content-Type": "application/json"
        }

        # Add authentication header if API key is provided
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            # OR use different auth format based on API requirements:
            # headers["X-API-Key"] = self.api_key

        return headers

    def send_request(self, payload, max_retries=None):
        """
        Send request to intermediary API with retry logic.

        Args:
            payload: Original payload format (messages array)
            max_retries: Override default max_retries

        Returns:
            tuple: (status_code, response_data) or (None/status_code, error_message)
        """
        max_retries = max_retries or self.max_retries

        print(f"[DEBUG] LLM Adapter - URL: {self.base_url}")
        print(f"[DEBUG] LLM Adapter - Max retries: {max_retries}")

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    wait_time = 2 ** attempt
                    print(f"[DEBUG] Retry attempt {attempt + 1}/{max_retries} after {wait_time}s wait...")
                    time.sleep(wait_time)

                # Transform request to new format
                transformed_payload = self._transform_request(payload)
                print(f"[DEBUG] Sending POST request (attempt {attempt + 1}/{max_retries})...")

                # Send request with auth headers
                resp = requests.post(
                    self.base_url,
                    json=transformed_payload,
                    headers=self._get_headers(),
                    timeout=self.timeout
                )

                print(f"[DEBUG] Response - Status Code: {resp.status_code}")
                print(f"[DEBUG] Response - Content Length: {len(resp.content)}")

                # Handle response
                resp.raise_for_status()

                # Parse and transform response
                response_data = resp.json()
                transformed_response = self._transform_response(response_data)

                print(f"[DEBUG] Response transformed successfully")
                return resp.status_code, transformed_response

            except requests.exceptions.HTTPError as http_err:
                print(f"[DEBUG] HTTP Error (attempt {attempt + 1}): {http_err}")

                # Don't retry on 4xx client errors (except 429 rate limit)
                if 400 <= resp.status_code < 500 and resp.status_code != 429:
                    print(f"[DEBUG] Client error {resp.status_code}, not retrying")
                    return resp.status_code, str(http_err)

                # Retry on 5xx server errors and 429 rate limit
                if attempt == max_retries - 1:
                    return resp.status_code, str(http_err)

            except requests.exceptions.ConnectionError as conn_err:
                print(f"[DEBUG] Connection Error (attempt {attempt + 1}): {conn_err}")
                if attempt == max_retries - 1:
                    return None, f"Connection failed after {max_retries} attempts: {str(conn_err)}"

            except requests.exceptions.Timeout as timeout_err:
                print(f"[DEBUG] Timeout (attempt {attempt + 1}): {timeout_err}")
                if attempt == max_retries - 1:
                    return None, f"Timeout after {max_retries} attempts: {str(timeout_err)}"

            except Exception as err:
                print(f"[DEBUG] Unexpected Error (attempt {attempt + 1}): {err}")
                if attempt == max_retries - 1:
                    return None, str(err)

        return None, f"Failed after {max_retries} attempts"


# Singleton instance
_adapter = None


def get_adapter():
    """Get or create LLM adapter instance."""
    global _adapter
    if _adapter is None:
        _adapter = LLMAdapter()
    return _adapter


def send_request(payload, url=None, max_retries=3):
    """
    Backward-compatible send_request function.
    Routes through adapter for transformation.
    """
    adapter = get_adapter()
    return adapter.send_request(payload, max_retries)
```

**Update** `rate_my_mr.py`:
```python
# OLD:
# from .params import RMMConstants

# NEW:
from .llm_adapter import send_request

# No other changes needed!
# All 4 AI calls use send_request() which now goes through adapter
```

---

#### Option C: Authentication Required

**Add to** `params.py`:
```python
class RMMConstants(Enum):
    agent_url = os.environ.get('AI_SERVICE_URL', 'http://10.31.88.29:6006/generate')
    api_key = os.environ.get('AI_SERVICE_API_KEY', '')  # NEW
```

**Update** `mrproper.env`:
```bash
GITLAB_ACCESS_TOKEN=glpat-xxxxxxxxxxxxxxxxxxxx
AI_SERVICE_URL=http://new-api-service.internal.com/llm/generate
AI_SERVICE_API_KEY=your-api-key-here  # NEW
```

**Update** `send_request()` in `rate_my_mr.py`:
```python
def send_request(payload, url=RMMConstants.agent_url.value, max_retries=3):
    # ... existing code ...

    # Add authentication header
    headers = {
        "Content-Type": "application/json"
    }

    # Add API key if configured
    if RMMConstants.api_key.value:
        headers["Authorization"] = f"Bearer {RMMConstants.api_key.value}"

    # ... retry loop ...
        resp = requests.post(
            url,
            json=payload,
            headers=headers,  # ✅ NEW: Pass headers
            timeout=120
        )
    # ... rest of code ...
```

---

### Phase 3: Implementation

**Step 1**: Choose implementation option based on new API specifications

**Step 2**: Implement chosen solution
- Option A: Update environment variable only
- Option B: Create adapter layer
- Option C: Add authentication

**Step 3**: Update tests
- Test all 4 AI function calls
- Test retry logic
- Test error handling
- Test authentication (if applicable)

**Step 4**: Update documentation
- Update README.md with new configuration
- Update ARCHITECTURE.md with new architecture diagram
- Update deployment instructions

---

## Configuration Strategy

### Environment Variables

**Current**:
```bash
AI_SERVICE_URL=http://10.31.88.29:6006/generate
```

**New (Minimal)**:
```bash
AI_SERVICE_URL=http://new-api-service.internal.com/v1/llm/generate
```

**New (With Auth)**:
```bash
AI_SERVICE_URL=http://new-api-service.internal.com/v1/llm/generate
AI_SERVICE_API_KEY=sk-xxxxxxxxxxxxxxxxxxxx
```

**New (With Advanced Options)**:
```bash
AI_SERVICE_URL=http://new-api-service.internal.com/v1/llm/generate
AI_SERVICE_API_KEY=sk-xxxxxxxxxxxxxxxxxxxx
AI_SERVICE_TIMEOUT=180  # Optional: override default 120s
AI_SERVICE_MAX_RETRIES=5  # Optional: override default 3
```

### Backward Compatibility

**Approach**: Feature flag for gradual rollout

```python
# params.py
class RMMConstants(Enum):
    # Use new API if URL points to it, otherwise use old format
    agent_url = os.environ.get('AI_SERVICE_URL', 'http://10.31.88.29:6006/generate')
    use_adapter = os.environ.get('USE_LLM_ADAPTER', 'auto')  # auto, true, false
```

```python
# rate_my_mr.py or llm_adapter.py
def send_request(payload, url=None, max_retries=3):
    use_adapter = RMMConstants.use_adapter.value

    if use_adapter == 'auto':
        # Auto-detect based on URL
        use_adapter = 'new-api-service' in (url or RMMConstants.agent_url.value)
    else:
        use_adapter = use_adapter.lower() == 'true'

    if use_adapter:
        # Use new adapter
        adapter = get_adapter()
        return adapter.send_request(payload, max_retries)
    else:
        # Use old direct connection (current implementation)
        return send_request_direct(payload, url, max_retries)
```

---

## Testing Strategy

### Unit Tests

**Test Cases**:
1. **Request Transformation**:
   - Test current format → new format conversion
   - Test edge cases (missing fields, empty messages)

2. **Response Transformation**:
   - Test new format → current format conversion
   - Test error responses

3. **Authentication**:
   - Test with valid API key
   - Test with invalid API key (401)
   - Test with missing API key

4. **Retry Logic**:
   - Test exponential backoff
   - Test max retries
   - Test different error codes

### Integration Tests

**Test Environment**:
- Staging environment with new API service
- Test all 4 AI function calls:
  1. `generate_summary()`
  2. `generate_initial_code_review()`
  3. `generate_lint_disable_report()`
  4. `generate_added_code_file()`

**Test Scenarios**:
1. ✅ Happy path: All calls succeed
2. ⚠️ Timeout: API takes >120s
3. ⚠️ Rate limit: 429 response
4. ⚠️ Server error: 5xx response
5. ⚠️ Auth failure: 401/403 response
6. ⚠️ Network failure: Connection refused

### Load Testing

**Test with**:
- 10 concurrent MR validations
- 50 concurrent validations
- 100 concurrent validations

**Monitor**:
- Response times
- Error rates
- Retry counts
- API service performance

---

## Deployment Plan

### Stage 1: Development Environment (Day 1)

1. Get new API service details from team
2. Implement chosen solution
3. Test locally with sample MR
4. Verify all 4 AI calls work

### Stage 2: Staging Environment (Day 2-3)

1. Deploy to staging
2. Update `mrproper.env` with new API URL
3. Trigger test MRs
4. Monitor logs for errors
5. Verify GitLab discussions updated correctly

### Stage 3: Canary Deployment (Day 4-5)

1. Deploy to 10% of production traffic
2. Monitor for 24 hours
3. Check error rates, response times
4. Compare with baseline metrics

### Stage 4: Full Production (Day 6-7)

1. Deploy to 50% of traffic
2. Monitor for 24 hours
3. Deploy to 100% if no issues
4. Monitor for 48 hours

### Stage 5: Cleanup (Day 8+)

1. Remove old code paths if using adapter
2. Update documentation
3. Remove feature flags

---

## Rollback Strategy

### Quick Rollback (< 5 minutes)

**If new API fails**:
```bash
# Revert environment variable
AI_SERVICE_URL=http://10.31.88.29:6006/generate

# Restart webhook server
./start-server --restart
```

### Code Rollback (< 15 minutes)

**If code changes needed reverting**:
```bash
# Revert to previous commit
git revert <commit-hash>

# Rebuild Docker images
./build-docker-images

# Restart server
./start-server --restart
```

### Feature Flag Rollback (< 1 minute)

**If using feature flag**:
```bash
# Disable adapter, use old path
USE_LLM_ADAPTER=false

# No restart needed if using dynamic config
```

---

## Monitoring & Validation

### Metrics to Track

**Before Migration (Baseline)**:
- AI call success rate: __%
- Average response time: __s
- P95 response time: __s
- Error rate: __%
- Timeout rate: __%

**After Migration (Compare)**:
- Same metrics
- Additional: Authentication failures
- Additional: Rate limit hits

### Log Analysis

**Search for issues**:
```bash
# Find all AI service errors
grep "AI Service.*Error" /home/docker/tmp/mr-validator-logs/rate-my-mr-*.log

# Check retry patterns
grep "Retry attempt" /home/docker/tmp/mr-validator-logs/rate-my-mr-*.log

# Monitor success rate
grep "AI Service Response - Status Code: 200" /home/docker/tmp/mr-validator-logs/rate-my-mr-*.log | wc -l
```

### Alerts

**Set up alerts for**:
- AI service error rate > 5%
- Authentication failures > 0
- Average response time > 150s
- Retry rate > 20%

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| New API incompatible format | Medium | High | Implement adapter layer |
| New API slower than current | Low | Medium | Monitor performance, adjust timeouts |
| Authentication issues | Medium | High | Test thoroughly in staging |
| Rate limiting more strict | Medium | Medium | Implement request queuing if needed |
| Network connectivity issues | Low | High | Keep old endpoint as fallback |
| Backward compatibility breaks | Low | High | Use feature flags, gradual rollout |

---

## Success Criteria

### Must Have
✅ All 4 AI function calls work with new API
✅ Error handling properly logs issues
✅ Retry logic functions correctly
✅ No regression in validation accuracy
✅ Rollback procedure tested and documented

### Should Have
✅ Performance equal or better than current
✅ Proper authentication if required
✅ Comprehensive logging
✅ Updated documentation

### Nice to Have
✅ Request/response caching
✅ Circuit breaker pattern
✅ Metrics dashboard
✅ A/B testing framework

---

## Timeline Estimate

| Phase | Duration | Effort |
|-------|----------|--------|
| Information Gathering | 1-2 hours | Low |
| Design Solution | 2-4 hours | Low |
| Implementation | 4-8 hours | Medium |
| Testing | 4-6 hours | Medium |
| Documentation | 2-3 hours | Low |
| Staging Deployment | 1 day | Low |
| Production Deployment | 2-3 days | Medium |
| **Total** | **~1 week** | **Medium** |

---

## Next Steps

### Immediate Actions

1. **Get API Specifications**:
   - Request documentation from API team
   - Get test endpoint URL
   - Get sample requests/responses
   - Get authentication details

2. **Test Connectivity**:
   ```bash
   # Test new API endpoint
   curl -X POST http://new-api-service.internal.com/v1/llm/generate \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer <token>" \
     -d '{"test": "payload"}'
   ```

3. **Choose Implementation**:
   - Based on API specs, decide: Option A, B, or C
   - Create implementation plan
   - Set up development environment

4. **Communicate**:
   - Notify team of migration plan
   - Schedule staging deployment
   - Plan production rollout window

---

## Questions for API Team

Before starting implementation, ask:

1. What is the exact endpoint URL?
2. What is the request format? (Share example)
3. What is the response format? (Share example)
4. Is authentication required? What type?
5. What are the rate limits?
6. What is the expected response time (SLA)?
7. What error codes can we expect?
8. Is there a staging/test environment?
9. Are there any special headers required?
10. Is there monitoring/logging on the API side?

---

**Status**: Ready for implementation once API details are provided

**Last Updated**: 2025-11-03

**Owner**: DevOps/Backend Team
