# MR Validator - Architecture & Technical Guide

Technical documentation for developers and system architects.

## System Overview

```mermaid
flowchart TB
    subgraph GitLab
        A[MR Event]
    end

    subgraph Webhook["Webhook Server :9912"]
        B[Tornado HTTP]
        C[Request Router]
    end

    subgraph Docker["Docker Containers"]
        D1[rate-my-mr]
        D2[mrproper-clang-format]
        D3[mrproper-message]
    end

    subgraph Services["External Services"]
        E[GitLab API]
        F[BFA/LLM Service]
    end

    A -->|POST| B
    B --> C
    C -->|spawn| D1
    C -->|spawn| D2
    C -->|spawn| D3
    D1 --> E
    D1 --> F
    D2 --> E
    D3 --> E
```

### Request Flow

```mermaid
sequenceDiagram
    participant GL as GitLab
    participant WH as Webhook
    participant DC as Docker
    participant VA as Validator
    participant BFA as BFA Service

    GL->>WH: POST /mr-proper/rate-my-mr
    Note over WH: Generate REQUEST_ID
    WH->>DC: docker run rate-my-mr
    DC->>VA: Start container
    VA->>GL: GET MR data
    VA->>BFA: POST /api/token
    BFA-->>VA: JWT token
    VA->>BFA: POST /api/rate-my-mr (x4)
    BFA-->>VA: AI analysis
    VA->>GL: POST discussion
    VA-->>DC: Exit 0
```

---

## Component Architecture

### Directory Structure

```
commit-validator/
├── webhook-server/
│   ├── server.py              # Tornado HTTP handler
│   └── Dockerfile             # Alpine Python 3.9
├── mrproper/
│   ├── bin/
│   │   ├── rate-my-mr         # Entry point
│   │   ├── mrproper-clang-format
│   │   └── mrproper-message
│   ├── mrproper/
│   │   ├── gitlab.py          # GitLab API client
│   │   └── rate_my_mr/
│   │       ├── rate_my_mr_gitlab.py    # Main orchestrator
│   │       ├── rate_my_mr.py           # AI integration
│   │       ├── llm_adapter.py          # JWT auth adapter
│   │       ├── config_loader.py        # Repo config
│   │       ├── logging_config.py       # Structured logging
│   │       ├── loc.py                  # LOC metrics
│   │       ├── cyclomatic_complexity.py
│   │       ├── security_scan.py
│   │       └── cal_rating.py
│   └── Dockerfile             # Ubuntu 22.04
└── mrproper.env               # Runtime config
```

### Component Responsibilities

| Component | File | Purpose |
|-----------|------|---------|
| **Webhook Server** | `server.py` | HTTP endpoint, container spawning |
| **GitLab Client** | `gitlab.py` | API calls, discussion updates |
| **Orchestrator** | `rate_my_mr_gitlab.py` | Pipeline coordination |
| **LLM Adapter** | `llm_adapter.py` | JWT auth, request transformation |
| **Config Loader** | `config_loader.py` | Repository-level settings |
| **Logging** | `logging_config.py` | Structured pipe-separated logs |

---

## LLM Integration

### Routing Logic

```mermaid
flowchart TD
    A[send_request] --> B{BFA_HOST set?}
    B -->|Yes| C[LLM Adapter]
    B -->|No| D[Legacy Direct]
    C --> E[Get JWT Token]
    E --> F[Transform Request]
    F --> G[POST /api/rate-my-mr]
    D --> H[POST /generate]
```

### JWT Token Flow

```python
# Token acquired once per MR, reused for all 4 AI calls

# 1. Token request
POST http://{BFA_HOST}:8000/api/token
Body: {"subject": "rate-my-mr-org%2Frepo-42"}
Response: {"token": "eyJhbGci..."}

# 2. LLM calls with token
POST http://{BFA_HOST}:8000/api/rate-my-mr
Headers: Authorization: Bearer {token}
```

### Request Transformation

**Old format** (from rate_my_mr.py):
```python
{
    "messages": [
        {"role": "system", "content": "You are..."},
        {"role": "user", "content": "diff..."}
    ]
}
```

**New BFA format** (transformed by llm_adapter.py):
```python
{
    "repo": "org/repo",
    "branch": "feature/x",
    "author": "user@example.com",
    "commit": "abc123",
    "mr_url": "https://gitlab.com/.../42",
    "prompt": "{\"messages\": [...]}"  # JSON string
}
```

### Response Transformation

**BFA response:**
```python
{
    "status": "ok",
    "metrics": {"summary_text": "AI analysis..."},
    "sent_to": "..."
}
```

**Transformed** (backward compatible):
```python
{
    "content": [{"type": "text", "text": "AI analysis..."}]
}
```

---

## Configuration System

### Loading Priority

```mermaid
flowchart LR
    A[Default Config] --> B[Repo Config]
    B --> C[Deep Merge]
    C --> D[Final Config]
```

### config_loader.py

```python
DEFAULT_CONFIG = {
    'features': {
        'ai_summary': True,
        'ai_code_review': True,
        'loc_analysis': True,
        'lint_disable_check': True,
        'cyclomatic_complexity': True,
        'security_scan': True,
    },
    'loc': {'max_lines': 500},
    'cyclomatic_complexity': {'max_average': 10},
    'security': {'fail_on_high': True},
    'rating': {'pass_score': 3},
}

def load_config(repo_dir):
    """Load .rate-my-mr.yaml from repo root, merge with defaults."""
    config_path = os.path.join(repo_dir, '.rate-my-mr.yaml')
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            repo_config = yaml.safe_load(f)
        return deep_merge(DEFAULT_CONFIG, repo_config)
    return DEFAULT_CONFIG.copy()

def is_feature_enabled(config, feature_name):
    """Check if feature is enabled in config."""
    return config.get('features', {}).get(feature_name, True)
```

### Feature Flag Usage

```python
# In rate_my_mr_gitlab.py
config = load_config(repo_dir)

if is_feature_enabled(config, 'ai_summary'):
    summary_success, summary_content = generate_summary(diff_file_path)
else:
    slog.info("AI summary skipped (disabled in config)")
    summary_success = False
```

---

## Logging System

### Structured Format

```
TIMESTAMP | LEVEL | MODULE | REQ_ID | MESSAGE | key=value
```

**Example:**
```
2025-11-17 10:15:23.456 | INFO  | main           | 12345678 | Starting MR analysis | project=org/repo mr_iid=42
2025-11-17 10:15:24.123 | INFO  | llm-adapter    | 12345678 | JWT token acquired | duration_ms=234
2025-11-17 10:15:26.789 | INFO  | rate-my-mr     | 12345678 | AI summary completed | success=True
```

### Module Name Mapping

```python
# In logging_config.py
MODULE_NAME_MAP = {
    'mrproper.rate_my_mr.rate_my_mr': 'rate-my-mr',
    'mrproper.rate_my_mr.llm_adapter': 'llm-adapter',
    'mrproper.rate_my_mr.loc': 'loc-analyzer',
    'mrproper.rate_my_mr.cyclomatic_complexity': 'cc-analyzer',
    'mrproper.rate_my_mr.security_scan': 'security-scan',
    'mrproper.rate_my_mr.cal_rating': 'rating-calc',
    'mrproper.rate_my_mr.config_loader': 'config-loader',
}

# Dynamic mapping
if module_name.startswith('validator.'):
    module_name = 'main'
elif module_name.startswith('webhook.'):
    module_name = 'webhook'
```

### Child Logger Configuration

```python
# In rate_my_mr_gitlab.py - ensures all modules log to same file
def configure_child_loggers():
    module_loggers = [
        'mrproper.rate_my_mr.rate_my_mr',
        'mrproper.rate_my_mr.llm_adapter',
        'mrproper.rate_my_mr.config_loader',
        # ...
    ]
    for module_name in module_loggers:
        module_logger = logging.getLogger(module_name)
        module_logger.handlers = []
        module_logger.addHandler(file_handler)
```

### Directory Structure

**Organized** (LOG_STRUCTURE=organized):
```
/home/docker/tmp/mr-validator-logs/
├── webhook/
│   └── 2025-11-17/
│       └── webhook-server.log
└── validations/
    └── 2025-11-17/
        └── org_repo/
            └── mr-42/
                └── rate-my-mr-12345678.log
```

---

## Analysis Pipeline

```mermaid
stateDiagram-v2
    [*] --> LoadConfig
    LoadConfig --> CreateDiff
    CreateDiff --> AISummary
    AISummary --> AICodeReview
    AICodeReview --> LOCAnalysis
    LOCAnalysis --> LintCheck
    LintCheck --> SecurityScan
    SecurityScan --> Complexity
    Complexity --> Rating
    Rating --> PostToGitLab
    PostToGitLab --> [*]
```

### Pipeline Steps

| Step | Module | Duration | Conditional |
|------|--------|----------|-------------|
| 1. Load Config | config_loader | ~10ms | Always |
| 2. Create Diff | git subprocess | ~1-3s | Always |
| 3. AI Summary | llm_adapter | ~2-4s | `features.ai_summary` |
| 4. AI Code Review | llm_adapter | ~3-5s | `features.ai_code_review` |
| 5. LOC Analysis | loc.py | ~50ms | `features.loc_analysis` |
| 6. Lint Check | rate_my_mr.py | ~50ms | `features.lint_disable_check` |
| 7. Security Scan | security_scan.py | ~500ms | `features.security_scan` |
| 8. Complexity | cyclomatic_complexity.py | ~200ms | `features.cyclomatic_complexity` |
| 9. Calculate Rating | cal_rating.py | ~10ms | Always |
| 10. Post to GitLab | gitlab.py | ~200ms | Always |

**Total: 8-15 seconds** for typical MR

### Rating Algorithm

```python
def cal_rating(net_loc, num_lint_disable):
    score = 5.0

    # LOC penalty
    if net_loc > 500:
        score -= 2.0
    elif net_loc > 200:
        score -= 1.0

    # Lint disable penalty
    if num_lint_disable > 5:
        score -= 1.0
    elif num_lint_disable > 0:
        score -= 0.5

    return max(1.0, min(5.0, score))
```

---

## GitLab API Integration

### Key Functions

```python
# gitlab.py

def gitlab(endpoint, params=None):
    """Generic GitLab API client."""
    headers = {"PRIVATE-TOKEN": GITLAB_ACCESS_TOKEN}
    response = requests.get(f"{GITLAB_HOST}/api/v4{endpoint}", headers=headers)
    return AttrDict(response.json())

def update_discussion(proj, mriid, header, body, must_not_be_resolved):
    """Create or update MR discussion."""
    # 1. Fetch existing discussions
    # 2. Search for note with matching header
    # 3. Update if found, create if not
    # 4. Set resolved status based on score
```

### Comment Update Logic

```mermaid
flowchart TD
    A[Fetch Discussions] --> B{Found existing?}
    B -->|Yes| C[Update Note]
    B -->|No| D[Create Discussion]
    C --> E{Content changed?}
    E -->|Yes| F[PUT /notes/:id]
    E -->|No| G[Skip update]
    D --> H[POST /discussions]
```

---

## Security Model

### Authentication Methods

| Service | Method | Token Storage |
|---------|--------|---------------|
| GitLab API | PRIVATE-TOKEN header | mrproper.env (file permission 0600) |
| BFA Service | JWT Bearer token | Memory only (not logged) |

### Token Security

- JWT scoped to `rate-my-mr-{project}-{mriid}`
- Token cleared on 401 errors
- Never fully logged (first 20 chars only)
- Expires server-side

### Container Isolation

- Each validation in isolated Docker container
- `--rm` flag removes container after completion
- No persistent state between validations
- Temporary files cleaned up

---

## Performance Metrics

| Metric | Value |
|--------|-------|
| Webhook response | <100ms |
| Container spawn | ~500ms |
| Token acquisition | ~50-200ms |
| AI call (each) | 2-5s |
| Total validation | 8-15s |
| Peak memory (100 containers) | ~20GB |

### Optimization Strategies

1. **Shallow git clones**: `--depth=$(max(commits, 100))`
2. **Token reuse**: 1 token call per MR (not 4)
3. **Conditional features**: Skip disabled analyses
4. **Parallel potential**: AI calls could be parallelized (future)

---

## Error Handling

### Retry Logic

```python
# LLM Adapter
MAX_RETRIES = 3
RETRY_DELAYS = [2, 4, 8]  # Exponential backoff

for attempt in range(MAX_RETRIES):
    try:
        response = requests.post(url, ...)
        if response.status_code == 200:
            return response
        elif response.status_code == 401:
            # Don't retry auth errors
            break
        elif response.status_code in [429, 500, 502, 503]:
            # Retry server errors
            time.sleep(RETRY_DELAYS[attempt])
    except requests.exceptions.Timeout:
        time.sleep(RETRY_DELAYS[attempt])
```

### Graceful Degradation

- AI service down → Report error in GitLab comment
- Config file invalid → Use defaults
- Feature disabled → Skip and continue pipeline
- Partial failure → Post available results

---

## Adding New Features

### 1. Add New Analysis Module

```python
# mrproper/mrproper/rate_my_mr/new_analyzer.py
import logging
logger = logging.getLogger(__name__)

def analyze(diff_file_path):
    logger.debug("Starting analysis")
    # ... analysis logic
    return {"result": data}
```

### 2. Register Logger

```python
# rate_my_mr_gitlab.py
module_loggers = [
    # ... existing
    'mrproper.rate_my_mr.new_analyzer',
]
```

### 3. Add Module Name Mapping

```python
# logging_config.py
MODULE_NAME_MAP = {
    # ... existing
    'mrproper.rate_my_mr.new_analyzer': 'new-analyzer',
}
```

### 4. Add Feature Flag

```python
# config_loader.py
DEFAULT_CONFIG = {
    'features': {
        # ... existing
        'new_analysis': True,
    },
}
```

### 5. Integrate in Pipeline

```python
# rate_my_mr_gitlab.py
if is_feature_enabled(config, 'new_analysis'):
    from .new_analyzer import analyze
    result = analyze(diff_file_path)
    slog.info("New analysis completed", **result)
```

---

## Related Documentation

- [README.md](./README.md) - User & Operator Guide
- [OPERATIONS.md](./OPERATIONS.md) - DevOps & Maintenance Guide
