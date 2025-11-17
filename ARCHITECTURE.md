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

### Complete Workflow Verification

This section provides an end-to-end verification of the MR validation workflow, showing exactly how the system processes GitLab webhooks, performs analysis, and updates MR comments.

#### Scenario 1: New MR Created

**Complete flow from GitLab webhook to MR comment creation:**

```
┌─────────────────────────────────────────────────────────────────────┐
│ 1. GitLab Event: User creates MR #42                                │
│    Project: my-org/my-project                                       │
│    Branch: feature/new-parser → main                                │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 2. GitLab Webhook: POST to webhook-server:9912/mr-proper/rate-my-mr │
│    Payload: {                                                        │
│      "project": {"path_with_namespace": "my-org/my-project"},       │
│      "object_attributes": {"iid": 42, "source_branch": "..."},      │
│      "user": {"email": "vishal@internal.com"}                       │
│    }                                                                 │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 3. webhook-server/server.py                                         │
│    - Generate REQUEST_ID: 20251114_143022_87654321                  │
│    - Spawn Docker container:                                        │
│      docker run -d --rm \                                           │
│        --env-file mrproper.env \                                    │
│        --env REQUEST_ID=20251114_143022_87654321 \                  │
│        --env PROJECT_ID=my-org%2Fmy-project \                       │
│        --env MR_IID=42 \                                            │
│        --env BFA_HOST=api-gateway.internal.com \                    │
│        -v /logs:/logs \                                             │
│        mr-checker-vp-test rate-my-mr \                              │
│        my-org%2Fmy-project 42                                       │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 4. rate_my_mr_gitlab.py: handle_mr()                                │
│                                                                      │
│    Step 4a: Fetch MR data from GitLab API                           │
│    GET https://git.internal.com/api/v4/projects/                    │
│        my-org%2Fmy-project/merge_requests/42                        │
│    Response: {                                                       │
│      "iid": 42,                                                      │
│      "title": "Add new parser functionality",                       │
│      "source_branch": "feature/new-parser",                         │
│      "target_branch": "main",                                       │
│      "author": {"email": "vishal@internal.com"},                    │
│      "web_url": "https://git.internal.com/.../merge_requests/42"    │
│    }                                                                 │
│                                                                      │
│    Step 4b: Fetch MR commits                                        │
│    GET /api/v4/projects/.../merge_requests/42/commits               │
│    Response: [                                                       │
│      {"id": "abc123def456...", "title": "Add parser class"},        │
│      {"id": "789xyz...", "title": "Add tests"}                      │
│    ]                                                                 │
│                                                                      │
│    Step 4c: Extract MR metadata (lines 271-307)                     │
│      MR_REPO = "my-org/my-project"  (URL decoded)                   │
│      MR_BRANCH = "feature/new-parser"                               │
│      MR_AUTHOR = "vishal@internal.com"                              │
│      MR_COMMIT = "789xyz..." (latest commit)                        │
│      MR_URL = "https://git.internal.com/.../merge_requests/42"      │
│                                                                      │
│    Step 4d: Set environment variables                               │
│      os.environ['MR_REPO'] = "my-org/my-project"                    │
│      os.environ['MR_BRANCH'] = "feature/new-parser"                 │
│      os.environ['MR_AUTHOR'] = "vishal@internal.com"                │
│      os.environ['MR_COMMIT'] = "789xyz..."                          │
│      os.environ['MR_URL'] = "https://git.internal.com/.../42"       │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 5. rate_my_mr_gitlab.py: Create diff file                           │
│    - Create temp directory: /tmp/tmpXXXXXX                          │
│    - git init -q                                                    │
│    - git fetch --depth=100 <clone_url> \                            │
│        merge-requests/42/head main:main                             │
│    - git checkout -q -b check FETCH_HEAD                            │
│    - git diff --no-color main...HEAD > mr_diff.txt                  │
│    - diff_file_path = "/tmp/tmpXXXXXX/mr_diff.txt"                  │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 6. AI Analysis Pipeline (4 AI Calls)                                │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 6a. Call #1: generate_summary(diff_file_path)                       │
│                                                                      │
│     rate_my_mr.py creates OLD format payload:                       │
│     payload = {                                                      │
│       "messages": [                                                  │
│         {"role": "system", "content": "You are a summarizer..."},   │
│         {"role": "user", "content": "<diff content>"}               │
│       ]                                                              │
│     }                                                                │
│                              ↓                                       │
│     send_request(payload)                                           │
│       → Checks: BFA_HOST configured? YES                            │
│       → Routes to: llm_adapter.send_request()                       │
│                              ↓                                       │
│     llm_adapter.py:                                                 │
│                                                                      │
│       Step 1: Get JWT token (first call only)                       │
│         POST http://api-gateway.internal.com:8000/api/token         │
│         Headers: {"Content-Type": "application/json"}               │
│         Body: {                                                      │
│           "subject": "rate-my-mr-my-org%2Fmy-project-42"            │
│         }                                                            │
│         Response: {"token": "eyJhbGciOiJIUzI1NiIs..."}              │
│         → Cache token in LLMAdapter._session_token                  │
│                              ↓                                       │
│       Step 2: Transform request (_transform_request)                │
│         - Read env vars: MR_REPO, MR_BRANCH, MR_AUTHOR, etc.        │
│         - Convert payload to JSON string: json.dumps(payload)       │
│         - Construct NEW format:                                     │
│         new_payload = {                                             │
│           "repo": "my-org/my-project",                              │
│           "branch": "feature/new-parser",                           │
│           "author": "vishal@internal.com",                          │
│           "commit": "789xyz...",                                    │
│           "mr_url": "https://git.internal.com/.../42",              │
│           "prompt": "{\"messages\": [...]}"  ← JSON string!         │
│         }                                                            │
│                              ↓                                       │
│       Step 3: Send to BFA API                                       │
│         POST http://api-gateway.internal.com:8000/api/rate-my-mr    │
│         Headers: {                                                   │
│           "Content-Type": "application/json",                       │
│           "Authorization": "Bearer eyJhbGciOiJIUzI1NiIs..."         │
│         }                                                            │
│         Body: <new_payload from Step 2>                             │
│         Timeout: 120 seconds                                        │
│                              ↓                                       │
│       Step 4: Receive BFA API response                              │
│         Status: 200 OK                                              │
│         Response: {                                                  │
│           "status": "ok",                                            │
│           "repo": "my-org/my-project",                              │
│           "branch": "feature/new-parser",                           │
│           "commit": "789xyz",                                       │
│           "author": "vishal@internal.com",                          │
│           "metrics": {                                               │
│             "summary_text": "This MR adds a new parser class..."    │
│           },                                                         │
│           "sent_to": "user not found in slack directory!"           │
│         }                                                            │
│                              ↓                                       │
│       Step 5: Transform response (_transform_response)              │
│         - Extract: metrics.summary_text                             │
│         - Wrap in OLD format for backward compatibility:            │
│         transformed = {                                             │
│           "content": [                                               │
│             {"type": "text", "text": "This MR adds a new..."}       │
│           ]                                                          │
│         }                                                            │
│                              ↓                                       │
│     Return to rate_my_mr.py:                                        │
│       status_code = 200                                             │
│       response = transformed (old format)                           │
│       content = response['content'][0]                              │
│       content_body = content['text']                                │
│       print(content_body)                                           │
│       ✅ Summary generated successfully                             │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 6b. Call #2: generate_initial_code_review(diff_file_path)           │
│     Same flow as 6a, but:                                           │
│     - Different system prompt: "You are a code reviewer..."         │
│     - Reuses cached JWT token (no token API call)                   │
│     - BFA returns code review analysis in metrics.summary_text      │
│     ✅ Code review completed                                        │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 6c. Call #3: generate_lint_disable_report(diff_file_path)           │
│     Same flow, reuses cached token                                  │
│     - System prompt: "Analyze pylint disables..."                   │
│     - BFA returns lint analysis in metrics.summary_text             │
│     - Extract JSON: {"num_lint_disable": 2, "lints_that_disabled":…}│
│     ✅ Lint analysis completed                                      │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 6d. Call #4: generate_added_code_file() [if needed]                 │
│     Same flow, reuses cached token                                  │
│     - Extracts added code for security scanning                     │
│     ✅ Security code extracted                                      │
│                                                                      │
│ Total AI API calls: 1 token + 4 LLM = 5 calls                       │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 7. Calculate LOC, Security, and Final Rating                        │
│    - LOC analysis: 145 added, 23 removed, net=122                   │
│    - Rating calculation: 5 - 0 = 5 (no penalties)                   │
│    - Format report with markdown                                    │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 8. gitlab.update_discussion(proj, mriid, HEADER, report_body, ...)  │
│                                                                      │
│    Step 8a: Fetch existing discussions                              │
│      GET /api/v4/projects/.../merge_requests/42/discussions         │
│      Response: []  (empty - no existing discussions)                │
│                                                                      │
│    Step 8b: Search for existing note                                │
│      for discussion in []:  ← empty list                            │
│        ...                                                           │
│      found_note = False  ⚠️ No existing note found                  │
│                                                                      │
│    Step 8c: Create new discussion                                   │
│      POST /api/v4/projects/.../merge_requests/42/discussions        │
│      Body: {                                                         │
│        "body": ":star2: MR Quality Rating Report\n..."             │
│      }                                                               │
│      Status: 201 Created                                            │
│      ✅ New comment posted to MR #42                                │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
                    ✅ WORKFLOW COMPLETE
         User sees new comment in GitLab MR (see visual example below)
```

#### Scenario 2: MR Updated (User Pushes New Commits)

**Same flow but comment gets UPDATED instead of creating new:**

```
┌─────────────────────────────────────────────────────────────────────┐
│ 1. GitLab Event: User pushes new commits to MR #42                  │
│    - User adds 2 more commits to feature/new-parser                 │
│    - GitLab triggers webhook again                                  │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 2-7. Same flow as Scenario 1                                        │
│      - Webhook triggered with updated event data                    │
│      - New REQUEST_ID generated: 20251114_145530_12345678           │
│      - Docker container spawned                                     │
│      - MR metadata extracted (NEW commit SHA: def456...)            │
│      - Git diff generated with new changes                          │
│      - 4 AI calls made with updated diff                            │
│      - JWT token acquired (or reused if still valid)                │
│      - New LOC calculated: 178 added, 30 removed, net=148           │
│      - New rating calculated: 5/5 (still no penalties)              │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 8. gitlab.update_discussion() - UPDATE SAME COMMENT                 │
│                                                                      │
│    Step 8a: Fetch existing discussions                              │
│      GET /api/v4/projects/.../merge_requests/42/discussions         │
│      Response: [                                                     │
│        {                                                             │
│          "id": "abc123",                                             │
│          "notes": [                                                  │
│            {                                                         │
│              "id": "note_xyz789",                                    │
│              "body": ":star2: MR Quality Rating Report\n...",       │
│              "resolved": false                                       │
│            }                                                         │
│          ]                                                           │
│        },                                                            │
│        ... other discussions ...                                     │
│      ]                                                               │
│                                                                      │
│    Step 8b: Search for existing note (gitlab.py line 177-198)       │
│      for discussion in discussions:                                 │
│        for note in discussion.notes:                                │
│          if note.body.startswith(":star2: MR Quality Rating"):      │
│            ✅ FOUND! (line 180-181)                                 │
│            found_note = True                                        │
│            discussion_id = "abc123"                                 │
│            note_id = "note_xyz789"                                  │
│            break                                                     │
│                                                                      │
│    Step 8c: Check if content differs (line 189)                     │
│      old_body = note.body                                           │
│      new_body = HEADER + report_body                                │
│      if old_body != new_body:                                       │
│        ✅ Content differs - UPDATE                                  │
│        PUT /api/v4/projects/.../discussions/abc123/notes/note_xyz…  │
│        Body: {                                                       │
│          "body": ":star2: MR Quality Rating Report\n<UPDATED>"     │
│        }                                                             │
│        Status: 200 OK                                               │
│                                                                      │
│    Step 8d: Update resolved status if needed                        │
│      if must_not_be_resolved and note.resolved:                     │
│        unresolve_note() (line 186)                                  │
│      if not must_not_be_resolved and not note.resolved:             │
│        resolve_note() (line 193-194)                                │
│                                                                      │
│    ✅ SAME COMMENT UPDATED                                          │
│       - No new comment created                                      │
│       - Existing comment shows updated metrics                      │
│       - User sees "edited" badge in GitLab UI                       │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
                    ✅ WORKFLOW COMPLETE
          User sees UPDATED comment in GitLab MR (not a new comment)
```

#### Visual Example: GitLab MR Comment

**How the comment appears in GitLab MR UI:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ GitLab Merge Request: !42 Add new parser functionality                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ 📋 Overview   💬 Discussion   🔄 Changes   📊 Commits                       │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  👤 MR Validator Bot  •  2 minutes ago  •  edited                           │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ :star2: MR Quality Rating Report :star2:                              │  │
│  │ ========================================                               │  │
│  │                                                                        │  │
│  │ ## Overall Rating: 5/5                                                │  │
│  │                                                                        │  │
│  │ ⭐⭐⭐⭐⭐                                                                │  │
│  │                                                                        │  │
│  │ ### Quality Assessment Results                                        │  │
│  │                                                                        │  │
│  │ #### 🔍 Summary Analysis                                              │  │
│  │ ✅ AI-powered summary generated successfully                          │  │
│  │                                                                        │  │
│  │ #### 🔬 Code Review Analysis                                          │  │
│  │ ✅ Comprehensive AI code review completed                             │  │
│  │                                                                        │  │
│  │ #### 📈 Lines of Code Analysis                                        │  │
│  │ - **Lines Added**: 178                                                │  │
│  │ - **Lines Removed**: 30                                               │  │
│  │ - **Net Change**: 148                                                 │  │
│  │                                                                        │  │
│  │ #### ⚠️ Lint Disable Analysis                                         │  │
│  │ - **New Lint Disables**: 0                                            │  │
│  │ - **Disabled Rules**: None                                            │  │
│  │                                                                        │  │
│  │ ### Scoring Breakdown                                                 │  │
│  │ | Metric | Status | Impact |                                          │  │
│  │ |--------|--------|--------|                                          │  │
│  │ | Lines of Code | 148 lines | Within limits |                        │  │
│  │ | Lint Disables | 0 new disables | No new disables |                 │  │
│  │                                                                        │  │
│  │ **Final Score**: 5/5 points                                           │  │
│  │                                                                        │  │
│  │ ✅ **Quality assessment passed** - MR meets quality standards.       │  │
│  │                                                                        │  │
│  │ ### Notes:                                                            │  │
│  │ - Detailed analysis available in container execution logs            │  │
│  │ - AI-powered insights have been generated for this MR                │  │
│  │ - Continue monitoring quality metrics in future MRs                  │  │
│  │                                                                        │  │
│  │ ---                                                                    │  │
│  │ *Generated by AI-powered MR quality assessment*                       │  │
│  │ *Scoring: LOC Analysis + Lint Pattern Detection + AI Code Review*    │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  💬 Reply...                                                                 │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  👤 Alice Developer  •  5 minutes ago                                       │
│  Looks good! Ready to merge.                                                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Key Features of the Comment:**

1. **Single Comment**: Always the same discussion thread (not multiple comments)
2. **Updated in Place**: Shows "edited" badge when MR changes
3. **Visual Rating**: Star emojis (⭐) for quick assessment
4. **Comprehensive Metrics**: LOC, lint analysis, AI review status
5. **Color-Coded Status**: ✅ for success, ⚠️ for warnings, ❌ for failures
6. **Actionable**: Must-not-be-resolved if score < 3 (blocks merge)

**Example: Low Quality MR (Score 2/5)**

```
┌───────────────────────────────────────────────────────────────────────────┐
│  👤 MR Validator Bot  •  1 minute ago  •  unresolved                      │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │ :star2: MR Quality Rating Report :star2:                            │  │
│  │ ========================================                             │  │
│  │                                                                      │  │
│  │ ## Overall Rating: 2/5                                              │  │
│  │                                                                      │  │
│  │ ⭐⭐⚪⚪⚪                                                              │  │
│  │                                                                      │  │
│  │ ### Quality Assessment Results                                      │  │
│  │ ...                                                                  │  │
│  │ #### 📈 Lines of Code Analysis                                      │  │
│  │ - **Lines Added**: 847                                              │  │
│  │ - **Lines Removed**: 12                                             │  │
│  │ - **Net Change**: 835                                               │  │
│  │                                                                      │  │
│  │ #### ⚠️ Lint Disable Analysis                                       │  │
│  │ - **New Lint Disables**: 5                                          │  │
│  │ - **Disabled Rules**: pylint:disable=too-many-locals, ...          │  │
│  │                                                                      │  │
│  │ ### Scoring Breakdown                                               │  │
│  │ | Metric | Status | Impact |                                        │  │
│  │ |--------|--------|--------|                                        │  │
│  │ | Lines of Code | 835 lines | ⚠️ Exceeds 500 line limit |          │  │
│  │ | Lint Disables | 5 new disables | ⚠️ New lint suppressions added |│  │
│  │                                                                      │  │
│  │ **Final Score**: 2/5 points                                         │  │
│  │                                                                      │  │
│  │ 💣 **QUALITY ISSUES IDENTIFIED** 💣                                 │  │
│  │ This MR has significant quality concerns that should be addressed   │  │
│  │ before merging. The assessment will be automatically updated when   │  │
│  │ changes are pushed.                                                 │  │
│  │                                                                      │  │
│  │ ### Recommended Actions:                                            │  │
│  │ - Review the AI-generated feedback in the container logs           │  │
│  │ - Address identified code quality issues                           │  │
│  │ - Consider breaking large changes into smaller MRs                 │  │
│  │ - Remove unnecessary lint disable statements                       │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                            │
│  🔒 This thread must be resolved before merging                           │
│                                                                            │
└───────────────────────────────────────────────────────────────────────────┘
```

**Note**: When score < 3, the discussion is marked as "must be resolved", which can block merging depending on GitLab project settings.

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
