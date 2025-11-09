# MR Validator - Architecture Documentation

## Table of Contents

- [System Overview](#system-overview)
- [Deployment](#deployment)
- [System Operations](#system-operations)
- [Component Architecture](#component-architecture)
- [Technology Stack](#technology-stack)
- [Security Model](#security-model)
- [Performance & Scalability](#performance--scalability)
- [Logging Architecture](#logging-architecture)

---

## Quick Navigation

**Choose your path based on your role**:

- **🚀 New User?** Start with [README.md Quick Start](./README.md#quick-start) first
- **🔧 Operator/DevOps?** Focus on [Deployment](#deployment) and [System Operations](#system-operations) sections below
- **👨‍💻 Developer?** Read [Component Architecture](#component-architecture) and [Technology Stack](#technology-stack)
- **🐛 Troubleshooting?** See [DEBUGGING_GUIDE.md](./DEBUGGING_GUIDE.md) for REQUEST_ID-based debugging
- **🔌 LLM Adapter Setup?** See [LLM_ADAPTER_IMPLEMENTATION.md](./LLM_ADAPTER_IMPLEMENTATION.md)
- **🧪 Testing?** See [COMPREHENSIVE_TEST_PLAN.md](./COMPREHENSIVE_TEST_PLAN.md)

**Related Documents**:
- Configuration: [README.md Configuration](./README.md#configuration)
- Debugging: [DEBUGGING_GUIDE.md](./DEBUGGING_GUIDE.md)
- LLM Adapter: [LLM_ADAPTER_IMPLEMENTATION.md](./LLM_ADAPTER_IMPLEMENTATION.md)
- Testing: [COMPREHENSIVE_TEST_PLAN.md](./COMPREHENSIVE_TEST_PLAN.md)
- Logging: [LOGGING_CONFIGURATION.md](./LOGGING_CONFIGURATION.md)

---

## System Overview

The MR Validator is an automated GitLab merge request validation system using a webhook-driven architecture with isolated Docker containers for each validation.

### High-Level Architecture

```mermaid
flowchart TB
    subgraph GitLab
        A[MR Created/Updated]
    end

    subgraph "Webhook Server (Port 9912)"
        B[Tornado HTTP Server]
        C[Request Validator]
        D[Container Spawner]
    end

    subgraph "Docker Infrastructure"
        E1[mrproper-clang-format<br/>Container]
        E2[mrproper-message<br/>Container]
        E3[rate-my-mr<br/>Container]
    end

    subgraph "External Services"
        F[GitLab API]
        G[AI/LLM Service]
    end

    A -->|HTTP Webhook| B
    B --> C
    C --> D
    D -->|Spawn| E1
    D -->|Spawn| E2
    D -->|Spawn| E3
    E1 -->|Fetch MR| F
    E2 -->|Fetch MR| F
    E3 -->|Fetch MR| F
    E3 -->|Analysis| G
    E1 -->|Post Results| F
    E2 -->|Post Results| F
    E3 -->|Post Results| F
```

### LLM Integration Routing

The system supports two modes for AI service integration with automatic routing:

```mermaid
flowchart TD
    A[Rate-My-MR Starts] --> B{BFA_HOST<br/>configured?}
    B -->|Yes| C[LLM Adapter Module]
    B -->|No| D[Legacy Direct Module]
    C --> E[Get/Create JWT Token]
    E --> F[POST /api/token]
    F --> G[Token Cached for MR]
    G --> H[4 AI Calls with JWT]
    D --> I[4 Direct AI Calls]
    H --> J[BFA Service<br/>api-gateway:8000]
    I --> K[Legacy Service<br/>10.31.88.29:6006]
    J --> L[LLM Backend]
    K --> L
    L --> M[Analysis Results]
```

**Routing Logic**:
- `BFA_HOST` set → New LLM adapter with JWT authentication
- `BFA_HOST` not set → Legacy direct connection

**LLM Adapter Features**:
- JWT token acquisition: `POST http://{BFA_HOST}:8000/api/token`
- Token reuse: acquired once per MR, used for all 4 AI calls
- Retry logic: exponential backoff (2s, 4s, 8s)
- Pre-configured tokens: via `BFA_TOKEN_KEY` environment variable
- Configurable timeout: via `API_TIMEOUT` (default: 120s)

**See**: [LLM_ADAPTER_IMPLEMENTATION.md](./LLM_ADAPTER_IMPLEMENTATION.md) for complete details

---

## Deployment

### Deployment Architecture

```mermaid
flowchart TB
    subgraph "GitLab CI/CD"
        A[Git Push] --> B[CI Pipeline]
        B --> C[Build Docker Images]
        C --> D1[mrproper-webhook-vp-test]
        C --> D2[mr-checker-vp-test]
    end

    subgraph "Target Server (10.X.X.X)"
        E[SSH Connection]
        F[Create mrproper.env]
        G[Deploy Webhook Container]
        H[Volume Mounts]
    end

    D1 --> E
    D2 --> E
    E --> F
    F --> G
    G --> H

    H --> I[/var/run/docker.sock]
    H --> J[/home/docker/tmp/mr-validator-logs]
```

### CI/CD Deployment Flow

**Automated Deployment Steps**:

1. **Trigger**: Git push to main branch
2. **Build Phase**: Create Docker images
   - `mrproper-webhook-vp-test` (Alpine Python 3.9, ~150MB)
   - `mr-checker-vp-test` (Ubuntu 22.04, ~1.2GB)
3. **SSH Connection**: Connect to target server using `LDOCKER_SSH_KEY`
4. **Environment Setup**: Create `mrproper.env` from CI variables
5. **Container Deployment**: Start webhook server with volume mounts
6. **Verification**: Test webhook endpoint

**GitLab CI Variables**:

| Variable | Type | Purpose |
|----------|------|---------|
| `GITLAB_ACCESS_TOKEN` | Masked | GitLab API authentication |
| `LDOCKER_SSH_KEY` | Protected | SSH access to deployment server |
| `AI_SERVICE_URL` | Plain | AI service endpoint (optional) |
| `BFA_HOST` | Plain | LLM adapter host (optional) |

**Deployment Command Example**:
```bash
# SSH to server
ssh -i <ssh-key> docker@10.X.X.X

# Create environment file
cat > mrproper.env <<EOF
GITLAB_ACCESS_TOKEN=${GITLAB_ACCESS_TOKEN}
AI_SERVICE_URL=${AI_SERVICE_URL}
BFA_HOST=${BFA_HOST}
LOG_DIR=/home/docker/tmp/mr-validator-logs
LOG_LEVEL=INFO
LOG_STRUCTURE=organized
EOF

# Deploy webhook server
docker run -d \
  --name mrproper-webhook-vp-test \
  --env-file mrproper.env \
  -p 9912:9912 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /home/docker/tmp/mr-validator-logs:/home/docker/tmp/mr-validator-logs \
  mrproper-webhook-vp-test
```

**Expected Output**:
```
abc123def456789...
✅ Webhook server deployed successfully
Server listening on http://0.0.0.0:9912
```

**Verify Deployment**:
```bash
# Check container status
docker ps | grep webhook
```

**Expected Output**:
```
abc123def456   mrproper-webhook-vp-test   "python webhook..."   2 minutes ago   Up 2 minutes   0.0.0.0:9912->9912/tcp   mrproper-webhook-vp-test
```

---

## System Operations

### Webhook Processing Flow

```mermaid
sequenceDiagram
    participant GL as GitLab
    participant WH as Webhook Server
    participant DC as Docker
    participant VC as Validator Container
    participant AI as AI Service
    participant GA as GitLab API

    GL->>WH: POST /mr-proper/rate-my-mr
    Note over WH: Parse webhook event<br/>Generate REQUEST_ID
    WH->>DC: docker run rate-my-mr
    Note over DC: Spawn isolated container
    DC->>VC: Start validation
    VC->>GA: GET /projects/{id}/merge_requests/{iid}
    GA-->>VC: MR data
    VC->>VC: Clone repository<br/>Create diff
    VC->>AI: POST /generate (4 calls)
    Note over VC: 1. Summary<br/>2. Code Review<br/>3. Best Practices<br/>4. Improvements
    AI-->>VC: Analysis results
    VC->>VC: LOC, Security, Complexity
    VC->>VC: Calculate rating (1-5 stars)
    VC->>GA: POST /discussions (MR comment)
    GA-->>VC: Success
    VC-->>DC: Exit 0
    DC-->>WH: Container completed
```

### Request Flow Timeline

**Example: rate-my-mr validation of 150-line MR**

```
T+0ms     : GitLab sends webhook
T+50ms    : Webhook server receives, validates
T+100ms   : Docker container spawned (REQUEST_ID: 87654321)
T+1.2s    : MR data fetched from GitLab API
T+2.5s    : Git repository cloned, diff created
T+3.0s    : AI Summary requested
T+5.5s    : AI Summary completed (2.5s)
T+6.0s    : AI Code Review requested
T+9.0s    : AI Code Review completed (3.0s)
T+9.5s    : LOC analysis completed (500ms)
T+10.0s   : Security scan completed (500ms)
T+10.5s   : Complexity analysis completed (500ms)
T+11.0s   : Rating calculated
T+11.5s   : Results posted to GitLab
T+11.8s   : Container exits

Total: ~12 seconds
```

### Validator Lifecycle

```mermaid
stateDiagram-v2
    [*] --> Spawned: docker run
    Spawned --> Initializing: Load environment
    Initializing --> FetchingMR: GitLab API call
    FetchingMR --> Cloning: git init & fetch
    Cloning --> Analyzing: Run validation logic

    state Analyzing {
        [*] --> AI_Calls
        AI_Calls --> Static_Analysis
        Static_Analysis --> Rating
        Rating --> [*]
    }

    Analyzing --> PostingResults: GitLab API POST
    PostingResults --> Cleanup: Remove temp files
    Cleanup --> Success: Exit 0

    FetchingMR --> Failed: API Error (401/403/500)
    Cloning --> Failed: Git Error
    Analyzing --> Failed: Analysis Error
    PostingResults --> Failed: API Error

    Success --> [*]
    Failed --> [*]: Exit 1
```

---

## Component Architecture

### Directory Structure

```
commit-validator/
├── webhook-server/                          # Tornado webhook handler
│   ├── server.py                            # HTTP server (9912)
│   └── Dockerfile                           # Alpine Python 3.9
│
├── mrproper/                                # Validation library
│   ├── bin/                                 # Entry points
│   │   ├── mrproper-clang-format
│   │   ├── mrproper-message
│   │   └── rate-my-mr
│   │
│   ├── mrproper/                            # Python modules
│   │   ├── __init__.py
│   │   ├── gitlab.py                        # GitLab API client
│   │   ├── git_format.py                    # Clang-format validator
│   │   ├── message.py                       # Message validator
│   │   │
│   │   └── rate_my_mr/                      # AI validator package
│   │       ├── __init__.py
│   │       ├── rate_my_mr_gitlab.py         # Main entry point
│   │       ├── rate_my_mr.py                # AI integration
│   │       ├── llm_adapter.py               # JWT token adapter
│   │       ├── loc.py                       # LOC metrics
│   │       ├── cal_rating.py                # Rating algorithm
│   │       ├── cyclomatic_complexity.py     # Code complexity
│   │       ├── security_scan.py             # Bandit integration
│   │       ├── params.py                    # Configuration
│   │       ├── utils.py                     # Utilities
│   │       └── logging_config.py            # Structured logging
│   │
│   ├── requirements.txt                     # Dependencies
│   ├── setup.py                             # Package config
│   └── Dockerfile                           # Ubuntu 22.04
│
└── mrproper.env                             # Runtime configuration
```

### Component Responsibilities

#### Webhook Server (`webhook-server/server.py`)

**Purpose**: HTTP endpoint for GitLab webhooks

**Responsibilities**:
- Listen on port 9912
- Parse webhook JSON payloads
- Validate checker names against whitelist
- Generate unique REQUEST_ID per webhook
- Spawn Docker containers with environment variables
- Pass logging configuration to validators

**Key Code**:
```python
ALLOWED_CHECKERS = {
    'mrproper-clang-format',
    'mrproper-message',
    'rate-my-mr',
}

docker_cmd = [
    "docker", "run", "-d", "--rm",
    "--env-file", "mrproper.env",
    "--env", f"REQUEST_ID={request_id}",
    "--env", f"PROJECT_ID={project_id}",
    "--env", f"MR_IID={mr_iid}",
    "--env", f"LOG_DIR={log_dir}",
    "--env", f"LOG_LEVEL={log_level}",
    "-v", f"{log_dir}:{log_dir}",
    "mr-checker-vp-test", checker_name,
    project_encoded, str(mr_iid)
]
```

**Performance**:
- Handles 100+ concurrent webhooks
- Non-blocking async I/O (Tornado)
- ~50ms response time per webhook

#### GitLab API Client (`mrproper/gitlab.py`)

**Purpose**: Interact with GitLab API

**Responsibilities**:
- Fetch MR data (title, description, commits, diffs)
- Create/update MR discussions
- Handle pagination (X-Total, X-Next-Page headers)
- Authentication via PRIVATE-TOKEN header
- Retry logic for transient failures

**Key Functions**:
```python
def gitlab(endpoint, params=None):
    """
    Generic GitLab API client.

    Args:
        endpoint: API path (e.g., "/projects/{id}/merge_requests/{iid}")
        params: Query parameters

    Returns:
        AttrDict: Parsed JSON response
    """

def update_discussion(proj, mriid, header, body, must_not_be_resolved):
    """
    Post or update MR discussion.

    Args:
        proj: Project ID (URL-encoded)
        mriid: MR IID
        header: Discussion header (used to find existing discussion)
        body: Markdown content
        must_not_be_resolved: True if issues found (keeps discussion open)
    """
```

**Example Usage**:
```python
# Fetch MR
mr = gitlab.gitlab("/projects/{}/merge_requests/{}".format(proj, mriid))

# Get commits
commits = gitlab.gitlab("/projects/{}/merge_requests/{}/commits".format(proj, mriid))

# Post results
gitlab.update_discussion(
    proj=proj,
    mriid=mriid,
    header="## MR Quality Rating",
    body=report_markdown,
    must_not_be_resolved=(rating < 3)
)
```

#### Rate-My-MR Validator (`mrproper/rate_my_mr/`)

**Purpose**: AI-powered comprehensive quality assessment

**7-Step Analysis Pipeline**:

```mermaid
flowchart LR
    A[MR Data] --> B[1. AI Summary]
    A --> C[2. AI Code Review]
    A --> D[3. LOC Analysis]
    A --> E[4. Lint Patterns]
    A --> F[5. Security Scan]
    A --> G[6. Complexity]
    B --> H[7. Rating Calculation]
    C --> H
    D --> H
    E --> H
    F --> H
    G --> H
    H --> I[1-5 Star Score]
    I --> J[GitLab Discussion]
```

**Step 1: AI Summary** (`rate_my_mr.py:generate_summary()`)
- Input: Full MR diff
- LLM Prompt: "Summarize code changes in 2-3 sentences"
- Output: High-level overview
- Duration: ~2-3 seconds

**Step 2: AI Code Review** (`rate_my_mr.py:generate_initial_code_review()`)
- Input: Full MR diff
- LLM Prompt: "Review for bugs, security issues, best practices"
- Output: Detailed findings
- Duration: ~3-4 seconds

**Step 3: LOC Analysis** (`loc.py:LOCCalculator`)
- Input: Diff file
- Logic: Parse +/- lines, exclude comments
- Output: `{lines_added, lines_removed, net_change}`
- Duration: ~100ms

**Step 4: Lint Analysis** (`rate_my_mr.py:generate_lint_disable_report()`)
- Input: Diff file
- Logic: Regex search for `// NOLINTNEXTLINE`, `# pylint: disable`, etc.
- Output: `{num_lint_disable, lints_that_disabled}`
- Duration: ~50ms

**Step 5: Security Scan** (`security_scan.py:SecurityScanner`)
- Input: Changed files
- Tool: Bandit (Python AST analysis)
- Output: Vulnerabilities by severity
- Duration: ~500ms

**Step 6: Complexity** (`cyclomatic_complexity.py:CyclomaticComplexityCalculator`)
- Input: Changed files
- Tool: Radon
- Output: Average complexity score
- Duration: ~200ms

**Step 7: Rating** (`cal_rating.py:CalRating`)
- Input: All above metrics
- Logic: Scoring algorithm
  - Start: 5 points
  - Deduct for high LOC (>200 lines)
  - Deduct for lint disables
  - Deduct for high complexity
  - Deduct for security issues
- Output: 1-5 star score
- Duration: <10ms

**Rating Algorithm**:
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

## Technology Stack

### Infrastructure

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| **Container Runtime** | Docker | 20.10+ | Isolated validation execution |
| **Webhook Server** | Tornado | 6.4 | Async HTTP server |
| **Base Image (Webhook)** | Alpine Linux | 3.18 | Lightweight webhook container |
| **Base Image (Validator)** | Ubuntu | 22.04 | Full validation environment |
| **Python** | CPython | 3.9+ | Runtime for all validators |

### Python Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `requests` | 2.28+ | HTTP client for APIs |
| `tornado` | 6.4 | Webhook HTTP server |
| `prettytable` | 3.0+ | Table formatting |
| `bandit` | 1.7+ | Security analysis |
| `radon` | 5.1+ | Complexity metrics |

### GitLab Integration

| API | Endpoint | Purpose |
|-----|----------|---------|
| **Projects** | `GET /projects/{id}` | Project metadata |
| **Merge Requests** | `GET /projects/{id}/merge_requests/{iid}` | MR details |
| **Commits** | `GET /projects/{id}/merge_requests/{iid}/commits` | Commit list |
| **Discussions** | `POST /projects/{id}/merge_requests/{iid}/discussions` | Post results |
| **Notes** | `PUT /projects/{id}/merge_requests/{iid}/discussions/{discussion_id}/notes/{note_id}` | Update comment |

**Authentication**: `PRIVATE-TOKEN: {GITLAB_ACCESS_TOKEN}` header

### AI/LLM Services

**Mode 1: Legacy Direct**
- URL: `http://10.31.88.29:6006/generate`
- Auth: None
- Request: `{"messages": [{"role": "user", "content": "..."}]}`
- Response: `{"response": "...", "tokens": 123}`

**Mode 2: LLM Adapter (JWT)**
- Token URL: `http://{BFA_HOST}:8000/api/token`
- LLM URL: `http://{BFA_HOST}:8000/api/rate-my-mr`
- Auth: `Authorization: Bearer {JWT}`
- Features: Token reuse, retry logic, exponential backoff

---

## Security Model

### Authentication

| Component | Method | Token |
|-----------|--------|-------|
| **GitLab API** | PRIVATE-TOKEN header | `glpat-...` (CI masked variable) |
| **LLM Service (Legacy)** | None | - |
| **LLM Service (New)** | JWT Bearer | Acquired from token API |

### Network Security

- Webhook server exposed on port 9912 (internal network only)
- Validator containers use host Docker socket (requires trust)
- GitLab API over HTTPS (certificate verification enabled)
- AI service over HTTP (internal network, no TLS required)

### Secret Management

**CI/CD Variables** (GitLab):
- `GITLAB_ACCESS_TOKEN`: Masked, protected
- `LDOCKER_SSH_KEY`: Base64-encoded, protected
- `BFA_TOKEN_KEY`: Masked (optional, for pre-configured JWT)

**Runtime Environment** (`mrproper.env`):
- File permissions: `0600` (owner read/write only)
- Created by CI pipeline, not committed to Git
- Mounted into containers as environment variables

### Container Isolation

- Each validation runs in isolated Docker container
- Containers removed after completion (`--rm` flag)
- No persistent state between validations
- Temporary files cleaned up before exit

---

## Performance & Scalability

### Performance Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| **Webhook Response Time** | <100ms | Acknowledgment only, async processing |
| **Container Spawn Time** | ~500ms | Docker overhead |
| **MR Fetch (GitLab API)** | 200-500ms | Depends on MR size |
| **Git Clone (shallow)** | 1-3s | Depth = commit count |
| **AI Summary** | 2-4s | LLM generation |
| **AI Code Review** | 3-5s | LLM generation |
| **LOC Analysis** | 50-200ms | Diff parsing |
| **Security Scan** | 200-1000ms | File count dependent |
| **Total (rate-my-mr)** | 8-15s | For typical MR (100-200 lines) |

### Concurrent Load Capacity

**Test Scenario**: 100 simultaneous MR events

```mermaid
gantt
    title 100 Concurrent MR Validations
    dateFormat  s
    axisFormat %S

    section Webhook Server
    Handle 100 webhooks       :0, 5s

    section Docker
    Spawn 100 containers      :0, 30s

    section Validation
    Container 1-20 (fast)     :1, 10s
    Container 21-60 (medium)  :1, 15s
    Container 61-100 (slow)   :1, 20s

    section Completion
    All complete              :20, 1s
```

**Results**:
- Webhook server handles all 100 requests < 5 seconds
- Docker spawns 100 containers in ~30 seconds (limited by CPU/memory)
- All validations complete within 20-30 seconds
- Peak memory: ~20GB (100 containers × ~200MB each)
- Peak CPU: 80-100% (burst)

### Scalability Metrics

**Horizontal Scaling**:
- Deploy multiple webhook servers with load balancer
- Share Docker host or use separate hosts per webhook server
- NFS-mounted log directory for centralized logging

**Vertical Scaling**:
- More CPU cores → faster container spawning
- More RAM → higher concurrent container limit
- Recommended: 2 CPU cores, 8GB RAM for ~50 concurrent validations

### Optimization Strategies

**1. Shallow Git Clones**:
```bash
git fetch --depth=$(max(len(commits), 100))
```
Reduces clone time by 50-70%

**2. AI Call Parallelization** (potential future optimization):
```python
# Current: Sequential (12s total)
summary = generate_summary(diff)       # 3s
review = generate_code_review(diff)    # 4s
best_practices = generate_bp(diff)     # 3s
improvements = generate_imp(diff)      # 2s

# Potential: Parallel (4s total, bottlenecked by slowest)
with ThreadPoolExecutor() as executor:
    futures = [
        executor.submit(generate_summary, diff),
        executor.submit(generate_code_review, diff),
        executor.submit(generate_bp, diff),
        executor.submit(generate_imp, diff),
    ]
    results = [f.result() for f in futures]
```

**3. LLM Token Reuse**:
- Current: 1 token acquisition per MR
- Reused for all 4 AI calls
- Saves 3× token API roundtrips (600-900ms)

---

## Logging Architecture

### Structured Logging Format

**Format**:
```
YYYY-MM-DD HH:MM:SS.mmm | LEVEL    | module.name                    | REQ_ID   | Message | key=value
```

**Example**:
```
2025-11-09 10:15:23.456 | INFO     | rate_my_mr.gitlab              | 87654321 | Starting MR analysis | project=vigneshpalanivelr/commit-validator mr_iid=42
2025-11-09 10:15:23.567 | DEBUG    | rate_my_mr.gitlab              | 87654321 | Fetching MR details | mr_iid=42
2025-11-09 10:15:23.890 | INFO     | rate_my_mr.gitlab              | 87654321 | MR fetched | title="Update docs" author=user123
2025-11-09 10:15:24.123 | INFO     | rate_my_mr.llm_adapter         | 87654321 | JWT token acquired | duration_ms=233
```

### Log Directory Structure

**Organized** (default):
```
/home/docker/tmp/mr-validator-logs/
├── webhook/
│   └── 2025-11-09/
│       └── webhook-server.log
└── validations/
    └── 2025-11-09/
        └── vigneshpalanivelr_commit-validator/
            └── mr-42/
                └── rate-my-mr-87654321.log
```

**Features**:
- Organized by date (easy cleanup: `rm -rf validations/2025-10-*`)
- Organized by project (easy filtering)
- Organized by MR (all logs for one MR in one directory)
- Correlation ID in filename for quick identification

### Log Rotation

| Log Type | Max Size | Backup Count | Total Size |
|----------|----------|--------------|------------|
| Webhook | 100MB | 5 | 600MB |
| Validator | 50MB | 3 | 200MB per validator |

**Rotation Behavior**:
```
rate-my-mr-87654321.log        # Current (0-50MB)
rate-my-mr-87654321.log.1      # Backup 1 (50MB)
rate-my-mr-87654321.log.2      # Backup 2 (50MB)
rate-my-mr-87654321.log.3      # Backup 3 (50MB)
```

When current log reaches 50MB:
1. `.log.3` is deleted
2. `.log.2` → `.log.3`
3. `.log.1` → `.log.2`
4. `.log` → `.log.1`
5. New `.log` created

### REQUEST_ID Correlation

Every webhook generates unique REQUEST_ID:

```mermaid
flowchart LR
    A[Webhook Received] --> B[Generate REQUEST_ID<br/>webhook_20251109_101523_87654321]
    B --> C[Extract Short Form<br/>87654321]
    C --> D[Pass to Container<br/>via environment]
    D --> E[Logging Config<br/>AlignedPipeFormatter]
    E --> F[Every Log Line<br/>includes 87654321]
    F --> G[Easy Correlation<br/>grep 87654321 logs/**/*.log]
```

**Benefits**:
- Trace entire request from webhook → validator → GitLab
- Correlate across multiple log files
- Debug issues with single grep command

**Example Trace**:
```bash
grep "87654321" /home/docker/tmp/mr-validator-logs/**/**/**/*.log
```

**Output**:
```
webhook/2025-11-09/webhook-server.log:
  2025-11-09 10:15:23.456 | INFO | webhook.server | 87654321 | Webhook received

validations/2025-11-09/vigneshpalanivelr_commit-validator/mr-42/rate-my-mr-87654321.log:
  2025-11-09 10:15:23.567 | INFO | rate_my_mr.gitlab | 87654321 | Starting analysis
  2025-11-09 10:15:29.890 | INFO | rate_my_mr.gitlab | 87654321 | Completed | duration_ms=6434
```

**See**: [LOGGING_CONFIGURATION.md](./LOGGING_CONFIGURATION.md) for complete logging setup guide

---

## Advanced Topics

### Rate-My-MR Deep Dive

For comprehensive technical details on the AI-powered quality assessment validator, including:
- Detailed 7-step analysis pipeline
- AI prompt engineering strategies
- Scoring algorithm internals
- Error handling and resilience
- Performance optimization techniques
- Troubleshooting guide

**See**: Previous ARCHITECTURE.md Phase 3 section or contact development team for detailed documentation.

### Adding Custom Validators

**Steps**:
1. Create validator module in `mrproper/mrproper/`
2. Add entry point script in `mrproper/bin/`
3. Update `setup.py` scripts list
4. Add to `ALLOWED_CHECKERS` in `webhook-server/server.py`
5. Rebuild Docker images
6. Update GitLab webhook URL

**Example**: See README.md Integration Guide section

### Monitoring and Observability

**Recommended Monitoring**:
- Container count: `docker ps | grep mr-checker-vp-test | wc -l`
- Log disk usage: `du -sh /home/docker/tmp/mr-validator-logs/`
- Webhook server health: `curl http://localhost:9912/mr-proper/rate-my-mr`
- Failed validations: `docker ps -a | grep "Exited ([1-9]"`

**Alerting**:
- Alert if webhook server down (no response on port 9912)
- Alert if log directory > 10GB
- Alert if >50 concurrent containers (resource exhaustion risk)
- Alert if >10% validation failures in last hour

---

**Last Updated**: 2025-11-09
