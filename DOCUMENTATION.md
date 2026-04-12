# MR Validator - Deployment & API Documentation

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Deployment Diagram](#deployment-diagram)
- [Component Details](#component-details)
- [API Payloads](#api-payloads)
  - [GitLab Webhook Payload](#gitlab-webhook-payload)
  - [Token API (JWT Authentication)](#token-api-jwt-authentication)
  - [LLM/BFA API](#llmbfa-api)
  - [GitLab API Integration](#gitlab-api-integration)
- [Container Communication](#container-communication)
- [Sequence Diagrams](#sequence-diagrams)
- [Environment Variables](#environment-variables)
- [Deployment Guide](#deployment-guide)

---

## Architecture Overview

The MR Validator is a distributed system that provides automated code quality assessment for GitLab merge requests. It consists of:

1. **Webhook Server**: Receives GitLab webhook events and orchestrates validation
2. **Validator Containers**: Ephemeral Docker containers that perform actual MR analysis
3. **External Services**: GitLab API and BFA/AI Service for code analysis

**Key Features**:
- AI-powered code review and summary generation
- Lines of Code (LOC) analysis
- Cyclomatic complexity measurement
- Security scanning (Bandit)
- Lint disable pattern detection
- Automated quality scoring (1-5 stars)

---

## Deployment Diagram

```mermaid
graph TB
    subgraph "External Services"
        GL[GitLab Instance<br/>gitlab.com]
        BFA[BFA Service<br/>api-gateway.internal.com:8000<br/>JWT-authenticated AI service]
    end

    subgraph "MR Validator Infrastructure"
        subgraph "Persistent Container"
            WS[Webhook Server<br/>ratemymr-webhook-container<br/>Port: 9912<br/>Framework: Tornado]
        end

        subgraph "Ephemeral Containers"
            VC1[Validator Container 1<br/>mr-rate-my-mr-42-abc123<br/>Image: ratemymr-validate-container]
            VC2[Validator Container 2<br/>mr-mrproper-message-43-def456<br/>Image: ratemymr-validate-container]
            VC3[Validator Container 3<br/>mr-mrproper-clang-format-44-ghi789<br/>Image: ratemymr-validate-container]
        end

        subgraph "Shared Storage"
            LOGS[Log Directory<br/>/home/docker/tmp/mr-validator-logs<br/>webhook/, validations/]
        end
    end

    GL -->|1. MR Webhook Event<br/>POST /mr-proper/rate-my-mr| WS
    WS -->|2. Spawn Docker Container<br/>docker run -d| VC1
    WS -->|3. Spawn Docker Container| VC2
    WS -->|4. Spawn Docker Container| VC3

    VC1 -->|5. Get MR Data<br/>GET /api/v4/projects/:id/merge_requests/:iid| GL
    VC1 -->|6. Clone Repository<br/>git fetch| GL
    VC1 -->|7. Acquire JWT Token<br/>POST /api/token| BFA
    BFA -->|8. JWT Token| VC1
    VC1 -->|9. AI Analysis Request<br/>POST /api/rate-my-mr<br/>Bearer Token| BFA
    BFA -->|10. AI Response<br/>Summary & Code Review| VC1
    VC1 -->|11. Post Results<br/>POST /api/v4/projects/:id/merge_requests/:iid/discussions| GL

    WS -.->|Mount Volume| LOGS
    VC1 -.->|Write Logs| LOGS
    VC2 -.->|Write Logs| LOGS
    VC3 -.->|Write Logs| LOGS

    style GL fill:#e1f5ff,stroke:#01579b,stroke-width:2px
    style BFA fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style WS fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
    style VC1 fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px
    style VC2 fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px
    style VC3 fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px
    style LOGS fill:#fff9c4,stroke:#f57f17,stroke-width:2px
```

### Component Network Diagram

```mermaid
graph LR
    subgraph "Network: host"
        WS[Webhook Server<br/>0.0.0.0:9912]
    end

    subgraph "Network: bridge (default)"
        VC[Validator Containers<br/>Dynamic Ports]
    end

    subgraph "External Networks"
        GL[GitLab API<br/>gitlab.com:443]
        BFA[BFA Service<br/>api-gateway:8000]
    end

    Internet -->|HTTPS Webhook| WS
    WS -->|Docker API| VC
    VC -->|HTTPS| GL
    VC -->|HTTP| BFA

    style Internet fill:#ffebee,stroke:#c62828,stroke-width:2px
    style WS fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
    style VC fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px
    style GL fill:#e1f5ff,stroke:#01579b,stroke-width:2px
    style BFA fill:#fff3e0,stroke:#e65100,stroke-width:2px
```

---

## Component Details

### 1. Webhook Server (`ratemymr-webhook-container`)

**Purpose**: Persistent HTTP server that receives GitLab webhook events and spawns validator containers

**Technology**:
- Python 3.8+ with Tornado web framework
- Docker API client

**Key Responsibilities**:
- Listen for GitLab webhook events on port 9912
- Parse webhook payload and extract MR metadata
- Spawn ephemeral Docker containers for each validator
- Manage environment variables and configuration
- Centralized logging coordination

**Container Details**:
- Image: `ratemymr-webhook-container`
- Port: `9912` (exposed to host, persistent)
- Restart Policy: `always`
- Environment: Loaded from `mrproper.env`

### 2. Validator Container (`ratemymr-validate-container`)

**Purpose**: Ephemeral containers that perform MR analysis and quality assessment

**Technology**:
- Python 3.8+ with analysis libraries

**Container Details**:
- Image: `ratemymr-validate-container`
- Port: None (ephemeral, uses host network, no fixed port)
- Lifecycle: Created per validation, removed after completion
- Environment: Inherited from webhook server + MR-specific vars
- Git client for repository operations
- Bandit (security scanner)
- Radon (cyclomatic complexity)
- Custom AI integration (LLM adapter)

**Key Responsibilities**:
- Clone GitLab repository
- Generate git diff for analysis
- Call AI service for summary and code review
- Calculate LOC, complexity, security metrics
- Calculate quality rating (1-5)
- Post results to GitLab MR discussion

**Container Lifecycle**:
1. Created by webhook server on MR event
2. Runs analysis pipeline (~30-120 seconds)
3. Posts results to GitLab
4. Self-destructs (--rm flag)

**Container Naming Convention**:
```
mr-{validator}-{mr_iid}-{request_id_short}

Examples:
- mr-rate-my-mr-42-a3b4c5d6
- mr-mrproper-message-123-f7e8d9c0
- mr-mrproper-clang-format-456-1a2b3c4d
```

### 3. External Services

#### GitLab Instance
- **Purpose**: Source code management, webhook source, result destination
- **Endpoints Used**:
  - `/api/v4/projects/:id/merge_requests/:iid` (GET MR data)
  - `/api/v4/projects/:id/merge_requests/:iid/commits` (GET commits)
  - `/api/v4/projects/:id/merge_requests/:iid/discussions` (POST results)
  - Git clone endpoint for repository access
- **Authentication**: GitLab Personal Access Token (API scope)

#### BFA Service (AI/LLM Gateway)
- **Purpose**: JWT-authenticated AI service for code analysis
- **Endpoints**:
  - `/api/token` (POST - JWT token acquisition)
  - `/api/rate-my-mr` (POST - AI analysis)
- **Authentication**: JWT Bearer tokens

---

## API Payloads

### GitLab Webhook Payload

**Endpoint**: `POST http://webhook-server:9912/mr-proper/{validator}`

**Headers**:
```http
Content-Type: application/json
X-Gitlab-Event: Merge Request Hook
X-Gitlab-Token: <webhook_secret>
```

**Request Body** (Merge Request Event):
```json
{
  "object_kind": "merge_request",
  "event_type": "merge_request",
  "user": {
    "id": 123,
    "name": "John Doe",
    "username": "johndoe",
    "avatar_url": "https://gitlab.com/uploads/-/system/user/avatar/123/avatar.png",
    "email": "john.doe@example.com"
  },
  "project": {
    "id": 456,
    "name": "my-project",
    "description": "My awesome project",
    "web_url": "https://gitlab.com/my-org/my-project",
    "path_with_namespace": "my-org/my-project",
    "namespace": "my-org",
    "git_http_url": "https://gitlab.com/my-org/my-project.git",
    "git_ssh_url": "git@gitlab.com:my-org/my-project.git"
  },
  "object_attributes": {
    "id": 789,
    "iid": 42,
    "title": "Add new authentication middleware",
    "description": "This MR adds JWT authentication middleware for API endpoints",
    "state": "opened",
    "created_at": "2025-01-15T10:30:00.000Z",
    "updated_at": "2025-01-15T10:30:00.000Z",
    "target_branch": "main",
    "source_branch": "feature/auth-middleware",
    "source_project_id": 456,
    "target_project_id": 456,
    "author_id": 123,
    "assignee_ids": [124, 125],
    "source": {
      "name": "my-project",
      "path_with_namespace": "my-org/my-project",
      "git_http_url": "https://gitlab.com/my-org/my-project.git"
    },
    "target": {
      "name": "my-project",
      "path_with_namespace": "my-org/my-project",
      "git_http_url": "https://gitlab.com/my-org/my-project.git"
    },
    "last_commit": {
      "id": "abc123def456789012345678901234567890abcd",
      "message": "Add JWT authentication middleware",
      "timestamp": "2025-01-15T10:25:00.000Z",
      "author": {
        "name": "John Doe",
        "email": "john.doe@example.com"
      }
    },
    "work_in_progress": false,
    "url": "https://gitlab.com/my-org/my-project/-/merge_requests/42",
    "action": "open",
    "merge_status": "can_be_merged"
  },
  "changes": {
    "updated_at": {
      "previous": "2025-01-15T10:20:00.000Z",
      "current": "2025-01-15T10:30:00.000Z"
    }
  },
  "labels": [],
  "repository": {
    "name": "my-project",
    "url": "git@gitlab.com:my-org/my-project.git",
    "description": "My awesome project",
    "homepage": "https://gitlab.com/my-org/my-project"
  }
}
```

**Key Fields Used by Validator**:
- `object_kind`: Must be "merge_request"
- `project.path_with_namespace`: Project identifier (e.g., "my-org/my-project")
- `object_attributes.iid`: MR internal ID (e.g., 42)
- `object_attributes.title`: MR title
- `object_attributes.source_branch`: Source branch name
- `object_attributes.target_branch`: Target branch name
- `user.username`: User who triggered the webhook

**Response**:
```http
HTTP/1.1 200 OK
Content-Type: text/plain

OK!
```

**URL Patterns**:
- Single validator: `/mr-proper/rate-my-mr`
- Multiple validators: `/mr-proper/rate-my-mr+mrproper-message`

---

### Token API (JWT Authentication)

**Endpoint**: `POST http://{BFA_HOST}:8000/api/token`

**Purpose**: Acquire JWT token for authenticating LLM API requests

**Request Headers**:
```http
Content-Type: application/json
```

**Request Body**:
```json
{
  "subject": "rate-my-mr-my-org%2Fmy-project-42"
}
```

**Request Schema**:
| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `subject` | string | Yes | Unique identifier for this validation session | `"rate-my-mr-org%2Frepo-123"` |

**Subject Format**: `rate-my-mr-{url_encoded_project_id}-{mr_iid}`

**Response** (Success):
```http
HTTP/1.1 200 OK
Content-Type: application/json
```

```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJyYXRlLW15LW1yLW15LW9yZyUyRm15LXByb2plY3QtNDIiLCJpYXQiOjE3MzcwMjQwMDAsImV4cCI6MTczNzAyNzYwMH0.abcdefghijklmnopqrstuvwxyz0123456789"
}
```

**Response Schema**:
| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `token` | string | JWT token for LLM API authentication | `"eyJhbGci..."` |

**Error Response** (Unauthorized):
```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json
```

```json
{
  "error": "Invalid credentials",
  "message": "Unable to generate token"
}
```

**Token Usage**:
- Token is acquired once per MR validation session
- Cached and reused for all AI calls (typically 4 calls: summary, review, etc.)
- Sent as Bearer token in Authorization header for LLM API requests
- Cleared on 401 errors to force re-authentication

---

### LLM/BFA API

**Endpoint**: `POST http://{BFA_HOST}:8000/api/rate-my-mr`

**Purpose**: AI-powered code analysis (summary, code review)

**Request Headers**:
```http
Content-Type: application/json
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Request Body**:
```json
{
  "repo": "my-org/my-project",
  "branch": "feature/auth-middleware",
  "author": "john.doe@example.com",
  "commit": "abc123def456789012345678901234567890abcd",
  "mr_url": "https://gitlab.com/my-org/my-project/-/merge_requests/42",
  "prompt": "{\"messages\":[{\"role\":\"system\",\"content\":\"You are a senior software engineer reviewing code changes.\"},{\"role\":\"user\",\"content\":\"Please analyze this git diff and provide a brief summary:\\n\\n```diff\\n@@ -1,5 +1,10 @@\\n+import jwt\\n+from functools import wraps\\n...\"}]}"
}
```

**Request Schema**:
| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `repo` | string | Yes | Repository path (org/project) | `"my-org/my-project"` |
| `branch` | string | Yes | Source branch name | `"feature/auth-middleware"` |
| `author` | string | Yes | MR author email | `"john.doe@example.com"` |
| `commit` | string | Yes | Latest commit SHA | `"abc123de..."` |
| `mr_url` | string | Yes | Full MR URL | `"https://gitlab.com/..."` |
| `prompt` | string | Yes | JSON-stringified messages array | See below |

**Prompt Field Format** (JSON string):
```json
{
  "messages": [
    {
      "role": "system",
      "content": "You are a senior software engineer reviewing code changes."
    },
    {
      "role": "user",
      "content": "Please analyze this git diff and provide a brief summary:\n\n```diff\n@@ -1,5 +1,10 @@\n+import jwt\n+from functools import wraps\n+\n+def require_auth(f):\n+    @wraps(f)\n+    def decorated(*args, **kwargs):\n+        token = request.headers.get('Authorization')\n+        if not token:\n+            return jsonify({'error': 'No token'}), 401\n...\n```"
    }
  ]
}
```

**Prompt Types** (4 typical AI calls per MR):
1. **Summary Generation**: "Provide a brief summary of the changes..."
2. **Code Review**: "Identify potential issues, improvements, and best practices..."
3. **Security Analysis**: "Analyze for security vulnerabilities..."
4. **Quality Assessment**: "Evaluate code quality and maintainability..."

**Response** (Success):
```http
HTTP/1.1 200 OK
Content-Type: application/json
```

```json
{
  "status": "ok",
  "repo": "my-org/my-project",
  "branch": "feature/auth-middleware",
  "commit": "abc123def456",
  "author": "john.doe@example.com",
  "metrics": {
    "summary_text": "This merge request adds JWT authentication middleware to the API endpoints. The changes include:\n\n1. New `require_auth` decorator for protecting endpoints\n2. JWT token validation logic\n3. Error handling for missing or invalid tokens\n4. Integration with existing request handlers\n\nThe implementation follows Flask best practices and includes proper error handling. However, consider adding token expiration checks and refresh token support for improved security."
  },
  "sent_to": "user not found in slack directory!"
}
```

**Response Schema**:
| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `status` | string | Response status | `"ok"` or `"error"` |
| `repo` | string | Echo of request repo | `"my-org/my-project"` |
| `branch` | string | Echo of request branch | `"feature/auth-middleware"` |
| `commit` | string | Echo of request commit | `"abc123def456"` |
| `author` | string | Echo of request author | `"john.doe@example.com"` |
| `metrics` | object | Analysis results container | See below |
| `metrics.summary_text` | string | AI-generated analysis text | `"This MR adds..."` |
| `sent_to` | string | Notification status | `"user not found..."` |

**Transformed Response** (Internal Format):
The LLM adapter transforms the BFA response to maintain compatibility:
```json
{
  "content": [
    {
      "type": "text",
      "text": "This merge request adds JWT authentication middleware..."
    }
  ]
}
```

**Error Response** (401 - Unauthorized):
```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json
```

```json
{
  "error": "Invalid or expired token",
  "message": "Please acquire a new token"
}
```

**Error Response** (500 - Server Error):
```http
HTTP/1.1 500 Internal Server Error
Content-Type: application/json
```

```json
{
  "error": "AI service error",
  "message": "LLM processing failed",
  "details": "Model timeout after 120 seconds"
}
```

**Timeout**: 120 seconds (configurable via `API_TIMEOUT`)

**Retry Logic**:
- Max retries: 3
- Backoff: Exponential (2s, 4s, 8s)
- Retry on: 5xx errors, 429 rate limit, connection errors
- No retry on: 4xx client errors (except 429)

---

### GitLab API Integration

#### 1. Get Merge Request Data

**Endpoint**: `GET https://gitlab.com/api/v4/projects/{project_id}/merge_requests/{mr_iid}`

**Headers**:
```http
PRIVATE-TOKEN: glpat-xxxxxxxxxxxxxxxxxxxx
```

**Response**:
```json
{
  "id": 789,
  "iid": 42,
  "title": "Add new authentication middleware",
  "description": "This MR adds JWT authentication...",
  "state": "opened",
  "created_at": "2025-01-15T10:30:00.000Z",
  "updated_at": "2025-01-15T10:30:00.000Z",
  "target_branch": "main",
  "source_branch": "feature/auth-middleware",
  "author": {
    "id": 123,
    "username": "johndoe",
    "name": "John Doe",
    "email": "john.doe@example.com"
  },
  "assignees": [],
  "merge_status": "can_be_merged",
  "web_url": "https://gitlab.com/my-org/my-project/-/merge_requests/42",
  "sha": "abc123def456789012345678901234567890abcd"
}
```

#### 2. Get Merge Request Commits

**Endpoint**: `GET https://gitlab.com/api/v4/projects/{project_id}/merge_requests/{mr_iid}/commits`

**Response**:
```json
[
  {
    "id": "abc123def456789012345678901234567890abcd",
    "short_id": "abc123de",
    "title": "Add JWT authentication middleware",
    "author_name": "John Doe",
    "author_email": "john.doe@example.com",
    "message": "Add JWT authentication middleware\n\nImplements secure token-based auth for API endpoints",
    "created_at": "2025-01-15T10:25:00.000Z"
  },
  {
    "id": "def456abc789012345678901234567890abcdef1",
    "short_id": "def456ab",
    "title": "Add unit tests for auth middleware",
    "author_name": "John Doe",
    "author_email": "john.doe@example.com",
    "message": "Add unit tests for auth middleware",
    "created_at": "2025-01-15T10:28:00.000Z"
  }
]
```

#### 3. Post Discussion (Results)

**Endpoint**: `POST https://gitlab.com/api/v4/projects/{project_id}/merge_requests/{mr_iid}/discussions`

**Headers**:
```http
PRIVATE-TOKEN: glpat-xxxxxxxxxxxxxxxxxxxx
Content-Type: application/json
```

**Request Body**:
```json
{
  "body": "## Overall Rating: 4/5\n\n### Quality Assessment Results\n\n#### :mag: Summary Analysis\n:white_check_mark: AI-powered summary generated successfully\n\n<details>\n<summary>Click to expand AI Summary</summary>\n\nThis merge request adds JWT authentication middleware...\n\n</details>\n...",
  "position": {
    "base_sha": "main_branch_sha",
    "head_sha": "abc123def456789012345678901234567890abcd",
    "position_type": "text"
  }
}
```

**Response**:
```json
{
  "id": "discussion_123456",
  "individual_note": false,
  "notes": [
    {
      "id": 987654,
      "type": "DiscussionNote",
      "body": "## Overall Rating: 4/5...",
      "author": {
        "id": 1,
        "username": "mr-validator-bot",
        "name": "MR Validator"
      },
      "created_at": "2025-01-15T10:32:00.000Z",
      "resolvable": false
    }
  ]
}
```

---

## Container Communication

### Communication Flow

```mermaid
sequenceDiagram
    participant GL as GitLab
    participant WS as Webhook Server
    participant VC as Validator Container
    participant BFA as BFA Service

    GL->>WS: 1. POST /mr-proper/rate-my-mr<br/>(MR webhook event)
    WS->>WS: 2. Parse webhook payload
    WS->>VC: 3. docker run -d --rm --env ...<br/>(spawn validator)
    WS->>GL: 4. HTTP 200 OK

    Note over VC: Container startup
    VC->>GL: 5. GET /api/v4/projects/{id}/merge_requests/{iid}
    GL->>VC: 6. MR metadata
    VC->>GL: 7. GET /api/v4/projects/{id}/merge_requests/{iid}/commits
    GL->>VC: 8. Commits list
    VC->>GL: 9. git fetch (clone repository)
    GL->>VC: 10. Repository data

    Note over VC: Generate git diff

    VC->>BFA: 11. POST /api/token<br/>{"subject": "rate-my-mr-..."}
    BFA->>VC: 12. {"token": "eyJhbGci..."}

    VC->>BFA: 13. POST /api/rate-my-mr<br/>Bearer Token<br/>(Summary request)
    BFA->>VC: 14. AI Summary

    VC->>BFA: 15. POST /api/rate-my-mr<br/>Bearer Token<br/>(Code review request)
    BFA->>VC: 16. AI Code Review

    Note over VC: Calculate LOC, Complexity,<br/>Security metrics

    Note over VC: Calculate rating (1-5)

    VC->>GL: 17. POST /api/v4/projects/{id}/merge_requests/{iid}/discussions<br/>(Post results)
    GL->>VC: 18. HTTP 201 Created

    Note over VC: Container exits (--rm)
```

### Environment Variable Propagation

```mermaid
graph TD
    ENV[mrproper.env File] -->|Loaded at startup| WS[Webhook Server]
    WS -->|docker run --env| VC[Validator Container]

    subgraph "Webhook Server Sets"
        WS1[REQUEST_ID]
        WS2[PROJECT_ID]
        WS3[MR_IID]
    end

    subgraph "From mrproper.env"
        ENV1[GITLAB_ACCESS_TOKEN]
        ENV2[BFA_HOST]
        ENV3[BFA_TOKEN_KEY]
        ENV4[API_TIMEOUT]
        ENV5[LOG_DIR]
        ENV6[LOG_LEVEL]
    end

    subgraph "Validator Extracts"
        VC1[MR_REPO]
        VC2[MR_BRANCH]
        VC3[MR_AUTHOR]
        VC4[MR_COMMIT]
        VC5[MR_URL]
    end

    WS --> WS1 & WS2 & WS3
    ENV --> ENV1 & ENV2 & ENV3 & ENV4 & ENV5 & ENV6
    WS1 & WS2 & WS3 & ENV1 & ENV2 & ENV3 & ENV4 & ENV5 & ENV6 --> VC
    VC --> VC1 & VC2 & VC3 & VC4 & VC5

    style ENV fill:#fff9c4,stroke:#f57f17
    style WS fill:#c8e6c9,stroke:#2e7d32
    style VC fill:#f3e5f5,stroke:#6a1b9a
```

---

## Sequence Diagrams

### Complete MR Validation Flow

```mermaid
sequenceDiagram
    autonumber
    participant Dev as Developer
    participant GL as GitLab
    participant WS as Webhook Server
    participant Docker as Docker Engine
    participant VC as Validator Container
    participant BFA as BFA Service
    participant Logs as Log Storage

    Dev->>GL: Create/Update MR
    GL->>WS: Webhook: MR Event

    rect rgb(200, 230, 201)
        Note over WS: Request Processing
        WS->>WS: Generate REQUEST_ID
        WS->>WS: Parse webhook payload
        WS->>WS: Validate checker names
        WS->>Logs: Log webhook received
    end

    rect rgb(243, 229, 245)
        Note over Docker,VC: Container Orchestration
        WS->>Docker: docker run -d --rm<br/>--env REQUEST_ID=...<br/>--volume {LOG_DIR}:{LOG_DIR}
        Docker->>VC: Create & start container
        WS->>GL: HTTP 200 OK (webhook processed)
    end

    rect rgb(255, 243, 224)
        Note over VC,GL: Repository Analysis
        VC->>Logs: Initialize validation log
        VC->>GL: GET MR data (API)
        GL->>VC: MR metadata
        VC->>GL: GET MR commits (API)
        GL->>VC: Commits list
        VC->>GL: git fetch (clone)
        GL->>VC: Repository contents
        VC->>VC: git checkout
        VC->>VC: Load .rate-my-mr.yaml config
        VC->>VC: Generate git diff
    end

    rect rgb(255, 249, 196)
        Note over VC,BFA: AI Analysis
        VC->>BFA: POST /api/token<br/>{"subject": "rate-my-mr-..."}
        BFA->>VC: JWT Token
        VC->>VC: Cache token for session

        loop AI Calls (Summary, Review, etc.)
            VC->>BFA: POST /api/rate-my-mr<br/>Bearer {token}<br/>+MR metadata +prompt
            BFA->>VC: AI Response
            VC->>VC: Parse & store results
        end
    end

    rect rgb(225, 245, 254)
        Note over VC: Quality Analysis
        VC->>VC: Calculate LOC metrics
        VC->>VC: Analyze lint disables
        VC->>VC: Calculate cyclomatic complexity
        VC->>VC: Run security scan (Bandit)
        VC->>VC: Calculate rating (1-5)
        VC->>VC: Format report
    end

    rect rgb(200, 230, 201)
        Note over VC,GL: Post Results
        VC->>GL: POST /api/v4/.../discussions<br/>(Quality report)
        GL->>VC: HTTP 201 Created
        VC->>Logs: Write completion log
    end

    rect rgb(243, 229, 245)
        Note over Docker,VC: Cleanup
        VC->>VC: Exit (success/failure)
        Docker->>Docker: Remove container (--rm)
    end

    GL->>Dev: Email notification (new comment)
    Dev->>GL: View MR with quality report
```

### Token Acquisition & Reuse Flow

```mermaid
sequenceDiagram
    autonumber
    participant VC as Validator Container
    participant Adapter as LLM Adapter
    participant BFA as BFA Service

    Note over VC: First AI call (Summary)
    VC->>Adapter: send_request(summary_payload)
    Adapter->>Adapter: Check _session_token<br/>(None - first call)
    Adapter->>Adapter: Check BFA_TOKEN_KEY env<br/>(Not set)

    rect rgb(255, 249, 196)
        Note over Adapter,BFA: Token Acquisition
        Adapter->>BFA: POST /api/token<br/>{"subject": "rate-my-mr-org%2Fproject-42"}
        BFA->>Adapter: {"token": "eyJhbGci..."}
        Adapter->>Adapter: Cache token in<br/>_session_token<br/>_token_project_mr = "org%2Fproject-42"
    end

    Adapter->>BFA: POST /api/rate-my-mr<br/>Authorization: Bearer eyJhbGci...
    BFA->>Adapter: AI Summary Response
    Adapter->>VC: (200, transformed_response)

    Note over VC: Second AI call (Code Review)
    VC->>Adapter: send_request(review_payload)
    Adapter->>Adapter: Check _session_token<br/>(Found - reuse!)
    Adapter->>Adapter: Check _token_project_mr<br/>(Matches current MR)

    rect rgb(200, 230, 201)
        Note over Adapter: Token Reuse
        Adapter->>Adapter: Reuse cached token<br/>(Skip /api/token call)
    end

    Adapter->>BFA: POST /api/rate-my-mr<br/>Authorization: Bearer eyJhbGci...<br/>(SAME TOKEN)
    BFA->>Adapter: AI Code Review Response
    Adapter->>VC: (200, transformed_response)

    Note over VC: Third & Fourth AI calls
    VC->>Adapter: send_request(...)
    Adapter->>Adapter: Reuse cached token
    Adapter->>BFA: POST /api/rate-my-mr<br/>Authorization: Bearer eyJhbGci...
    BFA->>Adapter: AI Response
    Adapter->>VC: (200, transformed_response)
```

---

## Environment Variables

### Required Variables

| Variable | Description | Example | Used By |
|----------|-------------|---------|---------|
| `GITLAB_ACCESS_TOKEN` | GitLab Personal Access Token (API scope) | `glpat-xxxxxxxxxxxxxxxxxxxx` | Webhook Server, Validator |

### AI/LLM Service Configuration

| Variable | Required | Description | Default | Example | Used By |
|----------|----------|-------------|---------|---------|---------|
| `BFA_HOST` | Yes | BFA service hostname (without http://) | None | `api-gateway.internal.com` | Validator |
| `API_TIMEOUT` | No | API call timeout in seconds | `120` | `180` | Validator |
| `BFA_TOKEN_KEY` | No | Pre-configured JWT token (skips token API) | None | `eyJhbGciOiJIUzI1...` | Validator |
| `AI_SERVICE_URL` | No | Legacy direct AI service URL | None | `http://10.31.88.29:6006/generate` | Validator (fallback) |

### Logging Configuration

| Variable | Description | Default | Example | Used By |
|----------|-------------|---------|---------|---------|
| `LOG_DIR` | Base directory for all logs | `/home/docker/tmp/mr-validator-logs` | `/mnt/nfs/logs` | Webhook Server, Validator |
| `LOG_LEVEL` | Logging verbosity | `DEBUG` | `INFO`, `WARNING`, `ERROR` | Webhook Server, Validator |
| `LOG_MAX_BYTES` | Max size per log file before rotation | `52428800` (50MB) | `104857600` (100MB) | Validator |
| `LOG_BACKUP_COUNT` | Number of rotated log files to keep | `3` | `5` | Validator |
| `LOG_STRUCTURE` | Directory organization style | `organized` | `flat` | Validator |

### Auto-Set Variables (Runtime)

These are set automatically by the system and should not be configured manually:

| Variable | Description | Set By | Example |
|----------|-------------|--------|---------|
| `REQUEST_ID` | Unique request identifier | Webhook Server | `20250115_103000_123456` |
| `PROJECT_ID` | GitLab project path (URL encoded) | Webhook Server | `my-org%2Fmy-project` |
| `MR_IID` | Merge request internal ID | Webhook Server | `42` |
| `MR_REPO` | Repository name (decoded) | Validator | `my-org/my-project` |
| `MR_BRANCH` | Source branch name | Validator | `feature/auth-middleware` |
| `MR_AUTHOR` | MR author email | Validator | `john.doe@example.com` |
| `MR_COMMIT` | Latest commit SHA | Validator | `abc123def456...` |
| `MR_URL` | Full MR URL | Validator | `https://gitlab.com/...` |

---

## Deployment Guide

### Prerequisites

1. Docker 20.10+ installed
2. GitLab instance with webhook access
3. GitLab Personal Access Token with API scope
4. Access to BFA service (if using AI features)
5. Network connectivity to GitLab and BFA service

### Step 1: Build Docker Images

```bash
./build-docker-images
```

Expected images:
- `ratemymr-webhook-container:latest` (Webhook server)
- `ratemymr-validate-container:latest` (Validator)

### Step 2: Configure Environment

Create `mrproper.env`:
```bash
# Required
GITLAB_ACCESS_TOKEN=glpat-xxxxxxxxxxxxxxxxxxxx

# AI Service (BFA mode - recommended)
BFA_HOST=api-gateway.internal.com
API_TIMEOUT=120

# Logging
LOG_DIR=/home/docker/tmp/mr-validator-logs
LOG_LEVEL=INFO
LOG_STRUCTURE=organized
```

### Step 3: Start Webhook Server

```bash
./start-server
```

This will:
1. Create log directory if it doesn't exist
2. Start webhook server container on port 9912
3. Load environment from `mrproper.env`
4. Enable auto-restart on failure

Verify:
```bash
curl http://localhost:9912/
docker logs ratemymr-webhook-container
```

### Step 4: Configure GitLab Webhook

**In GitLab Project Settings > Webhooks**:

- **URL**: `http://your-server-hostname:9912/mr-proper/rate-my-mr`
- **Secret Token**: (optional, for webhook authentication)
- **Trigger**: ✓ Merge request events
- **SSL verification**: Enable if using HTTPS

**Test the webhook**:
```bash
curl -X POST http://localhost:9912/mr-proper/rate-my-mr \
  -H "Content-Type: application/json" \
  -d '{
    "object_kind": "merge_request",
    "project": {
      "path_with_namespace": "my-org/my-project"
    },
    "object_attributes": {
      "iid": 42,
      "title": "Test MR"
    },
    "user": {
      "username": "testuser"
    }
  }'
```

### Step 5: Verify Deployment

1. **Check webhook server logs**:
   ```bash
   docker logs -f ratemymr-webhook-container
   ```

2. **Create a test MR in GitLab**

3. **Monitor validator container**:
   ```bash
   docker ps | grep mr-rate-my-mr
   ```

4. **Check validation logs**:
   ```bash
   ls -la /home/docker/tmp/mr-validator-logs/validations/$(date +%Y-%m-%d)/
   ```

5. **Verify GitLab comment**:
   - Open the test MR
   - Check for quality assessment comment

### Network Architecture

```
Internet (GitLab) → [Port 9912] → Webhook Server (Host Network)
                                         ↓
                                  Docker Engine
                                         ↓
                            Validator Containers (Bridge Network)
                                         ↓
                    ┌────────────────────┴─────────────────┐
                    ↓                                      ↓
            GitLab API (HTTPS)                    BFA Service (HTTP)
            gitlab.com:443                        api-gateway:8000
```

### Security Considerations

1. **Network Security**:
   - Webhook server exposed on port 9912 (configure firewall)
   - GitLab webhook secret recommended for production
   - HTTPS recommended for webhook endpoint

2. **Secrets Management**:
   - `GITLAB_ACCESS_TOKEN`: Stored in `mrproper.env` (restrict file permissions)
   - `BFA_TOKEN_KEY`: Optional pre-configured token
   - JWT tokens: Ephemeral, session-scoped

3. **Container Isolation**:
   - Validator containers run with `--rm` (auto-cleanup)
   - No privileged mode required
   - Log directory mounted read-write

4. **Access Control**:
   - GitLab token requires API scope (read/write MRs)
   - BFA service requires network reachability
   - Validator containers have no incoming ports

### Monitoring & Troubleshooting

**Monitor webhook server**:
```bash
docker logs -f ratemymr-webhook-container
```

**Find validation logs by MR**:
```bash
PROJECT="my-org_my-project"
MR_IID=42
DATE=$(date +%Y-%m-%d)
tail -f /home/docker/tmp/mr-validator-logs/validations/$DATE/$PROJECT/mr-$MR_IID/*.log
```

**Trace by REQUEST_ID**:
```bash
REQUEST_ID_SHORT="a3b4c5d6"
grep "$REQUEST_ID_SHORT" /home/docker/tmp/mr-validator-logs/**/**/**/*.log
```

**Check container status**:
```bash
docker ps -a | grep mr-rate-my-mr | head -5
```

**Debug validator execution**:
```bash
docker run --rm --env-file mrproper.env \
  -e REQUEST_ID=test_$(date +%s)_12345678 \
  -e PROJECT_ID=my-org%2Fmy-project \
  -e MR_IID=42 \
  ratemymr-validate-container rate-my-mr my-org%2Fmy-project 42
```

For detailed troubleshooting, see [README.md - Troubleshooting](./README.md#troubleshooting).

---

## Additional Resources

- [README.md](./README.md) - User & Operator Guide
- [ARCHITECTURE.md](./ARCHITECTURE.md) - Developer & Technical Guide
- [OPERATIONS.md](./OPERATIONS.md) - DevOps & Maintenance Guide

---

**Document Version**: 1.0
**Last Updated**: 2026-01-16
**Maintained By**: MR Validator Team
