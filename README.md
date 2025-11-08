# MR Validator - Automated GitLab Merge Request Validation

A comprehensive merge request validation system that automatically checks code formatting, commit message standards, and performs AI-powered quality assessment for GitLab projects. The system receives webhook events from GitLab and performs validation in isolated Docker containers.

## Table of Contents

- [MR Validator - Automated GitLab Merge Request Validation](#mr-validator---automated-gitlab-merge-request-validation)
  - [Table of Contents](#table-of-contents)
  - [Quick Start](#quick-start)
    - [Prerequisites](#prerequisites)
    - [1. Build Docker Images](#1-build-docker-images)
    - [2. Configure Environment](#2-configure-environment)
      - [Automated CI/CD Setup (Recommended)](#automated-cicd-setup-recommended)
      - [Manual Setup (Local Development)](#manual-setup-local-development)
    - [3. Start Server](#3-start-server)
    - [4. Configure GitLab Webhook](#4-configure-gitlab-webhook)
  - [System Overview](#system-overview)
  - [Installation \& Setup](#installation--setup)
    - [Build Process](#build-process)
      - [Dependencies](#dependencies)
      - [Automated Deployment Flow](#automated-deployment-flow)
    - [Configuration Files](#configuration-files)
      - [Environment Configuration (`mrproper.env`)](#environment-configuration-mrproperenv)
      - [Project-Specific Configuration (`.mr-proper.conf`)](#project-specific-configuration-mr-properconf)
    - [Directory Structure](#directory-structure)
  - [Configuration](#configuration)
    - [GitLab Webhook Configuration](#gitlab-webhook-configuration)
      - [Single Validator](#single-validator)
      - [Multiple Validators](#multiple-validators)
    - [Supported Validators](#supported-validators)
  - [Usage](#usage)
    - [Development Workflow Integration](#development-workflow-integration)
      - [For Developers](#for-developers)
      - [For Repository Maintainers](#for-repository-maintainers)
    - [Example API Calls](#example-api-calls)
  - [Validation Types](#validation-types)
    - [1. Code Formatting (`mrproper-clang-format`)](#1-code-formatting-mrproper-clang-format)
      - [Results Format](#results-format)
    - [2. Commit Message Validation (`mrproper-message`)](#2-commit-message-validation-mrproper-message)
      - [Results Format](#results-format-1)
    - [3. AI Quality Assessment (`rate-my-mr`)](#3-ai-quality-assessment-rate-my-mr)
      - [Results Format](#results-format-2)
  - [Integration Guide](#integration-guide)
    - [Adding New Validators](#adding-new-validators)
      - [Integration Best Practices](#integration-best-practices)
      - [Implementation Steps](#implementation-steps)
      - [Testing Integration](#testing-integration)
  - [Troubleshooting](#troubleshooting)
    - [Common Issues](#common-issues)
      - [Webhook Server Not Responding](#webhook-server-not-responding)
      - [Validation Containers Failing](#validation-containers-failing)
      - [GitLab API Issues](#gitlab-api-issues)
      - [Invalid Checkers Error](#invalid-checkers-error)
      - [Dependencies Missing](#dependencies-missing)
      - [AI Service Connectivity](#ai-service-connectivity)
    - [Debug Logging Locations](#debug-logging-locations)
      - [Comprehensive Debug Workflow](#comprehensive-debug-workflow)
      - [Request ID Tracking](#request-id-tracking)
    - [Performance Monitoring](#performance-monitoring)
    - [Deployment Verification](#deployment-verification)
    - [Security Notes](#security-notes)
  - [Architecture](#architecture)
    - [Key Components](#key-components)
    - [Performance Characteristics](#performance-characteristics)
  - [Contributing](#contributing)
    - [Development Setup](#development-setup)
    - [Adding Features](#adding-features)

## Quick Start

### Prerequisites
- Docker and Docker CLI
- GitLab access token with API permissions
- Python 3 environment

### 1. Build Docker Images
```bash
./build-docker-images
```

### 2. Configure Environment

#### Automated CI/CD Setup (Recommended)
Add these variables in your GitLab project:
**Project Settings → CI/CD → Variables**

| Variable Name | Value | Protected | Masked |
|---------------|-------|-----------|---------|
| `GITLAB_ACCESS_TOKEN` | `glpat-xxxxxxxxxxxxxxxxxxxx` | Yes | Yes |
| `LDOCKER_SSH_KEY` | `<base64-encoded-ssh-private-key>` | Yes | No |

**Getting Your GitLab Access Token:**
1. Go to GitLab → **User Settings** → **Access Tokens**
2. Create token with scopes: `api`, `read_repository`, `write_repository`
3. Copy the token (starts with `glpat-`)
4. Add to GitLab CI variables as `GITLAB_ACCESS_TOKEN`

#### Manual Setup (Local Development)
Create `mrproper.env`:
```bash
GITLAB_ACCESS_TOKEN=your_gitlab_token_here
```

### 3. Start Server
```bash
./start-server
```

### 4. Configure GitLab Webhook
Point your GitLab project webhook to:
- **URL**: `http://your-server:9912/mr-proper/mrproper-clang-format+mrproper-message+rate-my-mr`
- **Events**: Merge request events

## System Overview

The MR Validator consists of two main components working together:

```mermaid
flowchart LR
    A[GitLab MR Event] --> B[Webhook Server]
    B --> C[Docker Validators]
    C --> D[GitLab API Updates]
```

1. **GitLab** sends webhook events when merge requests are created/updated
2. **Webhook Server** receives events and validates request parameters
3. **Docker Containers** execute validation logic in isolated environments
4. **MRProper Library** performs actual validation and updates GitLab discussions

## Features

### Multi-Validator Support
- **Code Formatting**: Clang-format validation with per-commit analysis
- **Commit Messages**: Organizational standards enforcement
- **AI Quality Assessment**: Comprehensive code review and quality scoring

### High Performance
- **Concurrent Processing**: Handles 100+ simultaneous MR validations
- **Container Isolation**: Each validation runs independently
- **Auto-Scaling**: Dynamic container spawning based on load
- **Reliability**: Retry logic with exponential backoff for transient failures

### Smart Analysis
- **AI-Powered Reviews**: Bug detection, security analysis, performance insights
- **Quality Scoring**: 1-5 star rating system with automatic blocking
- **LOC Analysis**: Lines of code tracking with configurable limits
- **Lint Pattern Detection**: Identifies new code suppression patterns

### GitLab Integration
- **Automatic Discussion Updates**: Results posted as MR comments
- **Resolution Management**: Auto-resolves when issues are fixed
- **Approval Cross-Reference**: Validates reviewer trailers against GitLab approvals
- **Request Correlation**: End-to-end tracing with unique REQUEST_ID

## Recent Improvements (2025-11-03)

### Reliability Enhancements
✅ **AI Service Retry Logic**: Exponential backoff (2s, 4s, 8s) for up to 3 retries on failures
✅ **Proper Error Handling**: All exceptions now logged with stack traces (no silent failures)
✅ **Git Command Validation**: Return codes checked and failures properly reported
✅ **Resource Cleanup**: Temporary files properly cleaned up with thread-safe handling

### Debugging & Monitoring
✅ **Request Correlation**: REQUEST_ID now propagates from webhook through all validator logs
✅ **Enhanced Logging**: All log messages include `[REQUEST_ID]` prefix for easy tracing
✅ **Log Rotation**: Automatic rotation at 50-100MB to prevent disk exhaustion
✅ **Accurate Status**: AI validation failures now properly reported (no false positives)

### Configuration Flexibility
✅ **Configurable AI Service**: Set `AI_SERVICE_URL` environment variable for custom AI endpoints
✅ **Documented Rating Systems**: Clear documentation on simple vs comprehensive rating calculations

### Log File Naming Convention
```
/home/docker/tmp/mr-validator-logs/
├── webhook-server.log                              # Webhook activities (100MB × 5 backups)
├── rate-my-mr-{REQUEST_ID}-{container}.log        # Per-request logs (50MB × 3 backups)
├── gitlab-api-{REQUEST_ID}-{container}.log        # API interactions
```

**Trace requests across all logs**:
```bash
# Find all activity for specific request
grep "a1b2c3d4" /home/docker/tmp/mr-validator-logs/*.log
```

## 📚 Documentation

**New here?** Continue with [Quick Start](#quick-start) above or [Installation & Setup](#installation--setup) below.

**Full Documentation Roadmap**: See [DOCUMENTATION.md](./DOCUMENTATION.md)

**Quick Links**:
- 🏗️ System Architecture: [ARCHITECTURE.md](./ARCHITECTURE.md)
- 🐛 Troubleshooting & Debugging: [DEBUGGING_GUIDE.md](./DEBUGGING_GUIDE.md)
- 🔌 LLM Adapter Setup: [LLM_ADAPTER_IMPLEMENTATION.md](./LLM_ADAPTER_IMPLEMENTATION.md)
- 🧪 Testing Procedures: [COMPREHENSIVE_TEST_PLAN.md](./COMPREHENSIVE_TEST_PLAN.md)
- 📋 Logging Configuration: [LOGGING_CONFIGURATION.md](./LOGGING_CONFIGURATION.md)

## 📋 Structured Logging

The system uses **pipe-separated, structured logging** for easy parsing and visual scanning:

**Log Format**:
```
YYYY-MM-DD HH:MM:SS.mmm | LEVEL    | module.name                    | REQ_ID   | Message | key=value
```

**Example Output**:
```
2025-11-08 14:23:45.123 | INFO     | rate_my_mr.gitlab              | 4adcc17d | Starting MR analysis | project=vigneshpalanivelr/commit-validator mr_iid=42
2025-11-08 14:23:46.012 | INFO     | rate_my_mr.llm_adapter         | 4adcc17d | JWT token acquired | duration_ms=223
2025-11-08 14:23:48.456 | INFO     | rate_my_mr.rate_my_mr          | 4adcc17d | AI summary completed | success=True
2025-11-08 14:23:49.678 | INFO     | rate_my_mr.gitlab              | 4adcc17d | MR validation complete | score=7.5 duration_ms=4555
```

**Features**:
- ✅ Millisecond precision timestamps
- ✅ Column-aligned format for visual scanning
- ✅ Correlation IDs (REQUEST_ID_SHORT) for tracing
- ✅ Structured key=value pairs
- ✅ Organized log structure (by date/project/MR)

**Configuration**: See [LOGGING_CONFIGURATION.md](./LOGGING_CONFIGURATION.md) for detailed setup

## Installation & Setup

### Build Process
The system creates two Docker images:
- `mrproper-webhook-vp-test` - Webhook server container
- `mr-checker-vp-test` - Validation library container

```bash
# Build both images
./build-docker-images

# This creates:
# - mrproper-webhook-vp-test: Tornado-based webhook handler
# - mr-checker-vp-test: Ubuntu-based validation environment with clang-format
```

#### Dependencies
Before running the system, ensure these dependencies are available:

```bash
cd mrproper
pip install -r requirements.txt
```

Required packages:
- `requests>=2.28.0` - For API calls
- `prettytable>=3.0.0` - For tabular output formatting
- `bandit>=1.7.0` - For security scanning
- `radon>=5.1.0` - For code complexity analysis

#### Automated Deployment Flow
1. **CI Pipeline triggers** on push/merge
2. **Builds Docker images** (`mr-checker-vp-test`, `mrproper-webhook-vp-test`)
3. **SSH to target server** (10.X.X.X)
4. **Creates mrproper.env** from GitLab CI variable automatically
5. **Deploys container** with volume mount to the created file

### Configuration Files

#### Environment Configuration (`mrproper.env`)
```bash
GITLAB_ACCESS_TOKEN=glpat-xxxxxxxxxxxxxxxxxxxx

# Optional: Custom AI service URL (defaults to 10.31.88.29:6006)
AI_SERVICE_URL=http://custom-ai-server:8080/generate
```

#### Project-Specific Configuration (`.mr-proper.conf`)
```ini
[message]
valid_tags = BUG,FEATURE,IMPROVEMENT,REFACTOR,HOTFIX
valid_tags_without_ticket = IMPROVEMENT,REFACTOR
```

### Directory Structure
```
mr-validator/
├── webhook-server/                # Tornado webhook handler
│   ├── server.py                  # Main webhook server
│   └── Dockerfile                 # Alpine-based webhook image
├── mrproper/                      # Core validation library
│   ├── bin/                       # Entry point scripts
│   │   ├── mrproper-clang-format  # Code formatting validator
│   │   ├── mrproper-message       # Commit message validator
│   │   └── rate-my-mr             # AI quality assessment
│   ├── mrproper/                  # Python validation modules
│   │   ├── git_format.py          # clang-format validation
│   │   ├── message.py             # Commit message validation
│   │   ├── rate_my_mr_gitlab.py   # AI-powered MR analysis
│   │   ├── gitlab.py              # GitLab API client
│   │   └── ...                    # Supporting modules
│   ├── setup.py                   # Package installation
│   └── Dockerfile                 # Ubuntu-based validation image
├── mrproper.env                   # Environment configuration
├── build-docker-images            # Build script
├── start-server                   # Server startup script
├── README.md                      # Complete user guide
└── ARCHITECTURE.md                # Technical documentation
```

## LLM Adapter Configuration (New)

The system supports two modes for AI service integration with automatic routing:

### Mode 1: Legacy Direct Connection (Current Default)

Connects directly to AI service without authentication:

```bash
# In mrproper.env
GITLAB_ACCESS_TOKEN=glpat-your-token-here
AI_SERVICE_URL=http://10.31.88.29:6006/generate
```

**Use when**: You're using the existing AI service

### Mode 2: LLM Adapter with JWT Authentication (NEW)

Routes through intermediary BFA service with JWT token authentication:

```bash
# In mrproper.env
GITLAB_ACCESS_TOKEN=glpat-your-token-here
BFA_HOST=api-gateway.internal.com
API_TIMEOUT=120                      # Optional: default 120 seconds
BFA_TOKEN_KEY=eyJhbGci...            # Optional: pre-configured token
```

**Use when**: You're integrating with the new BFA intermediary service

**Features**:
- ✅ JWT token authentication with automatic token acquisition
- ✅ Token acquired once per MR, reused for all 4 AI calls (efficient)
- ✅ Automatic retry with exponential backoff (2s, 4s, 8s)
- ✅ Support for pre-configured tokens (bypasses token API)
- ✅ 100% backward compatible - falls back to legacy mode when BFA_HOST not set

**How it works**:
1. System detects `BFA_HOST` environment variable at startup
2. If set → uses new adapter with JWT authentication
3. If not set → uses legacy direct connection (unchanged)
4. No code changes or restarts needed - automatic routing

**Documentation**: See [LLM_ADAPTER_IMPLEMENTATION.md](./LLM_ADAPTER_IMPLEMENTATION.md) for complete details

**Status**: ✅ Implementation complete, awaiting BFA API format specifications

---

## Configuration

### GitLab Webhook Configuration
Configure your GitLab project webhooks:

#### Single Validator
```
URL: http://your-server:9912/mr-proper/mrproper-clang-format
Events: Merge request events
```

#### Multiple Validators
```
URL: http://your-server:9912/mr-proper/mrproper-clang-format+mrproper-message+rate-my-mr
Events: Merge request events
```

### Supported Validators
- `mrproper-clang-format` - Code formatting validation
- `mrproper-message` - Commit message standards validation
- `rate-my-mr` - AI-powered comprehensive quality assessment


## Usage

### Development Workflow Integration

#### For Developers
1. Create merge request in GitLab
2. Validation automatically triggered on MR creation/updates
3. Review validation results in MR discussions
4. Fix issues and push updates to trigger re-validation
5. Merge when all validations pass

#### For Repository Maintainers
1. Configure webhook pointing to your MR Validator instance
2. Customize validation rules via `.mr-proper.conf` if needed
3. Validation results prevent merging of non-compliant code
4. Automatic resolution when issues are addressed

### Example API Calls
```bash
# Test single validator
curl -X POST http://localhost:9912/mr-proper/mrproper-clang-format

# Test multiple validators
curl -X POST http://localhost:9912/mr-proper/mrproper-clang-format+mrproper-message+rate-my-mr
```

## Validation Types

### 1. Code Formatting (`mrproper-clang-format`)
- **Technology**: clang-format with organizational standards
- **Scope**: Per-commit formatting validation
- **Output**: Detailed formatting errors with fix suggestions
- **Resolution**: Auto-resolves when all formatting issues are fixed

#### Results Format
```
git format report
===================================================

✓ Commit abc123f: Added user authentication - formatting OK
✗ Commit def456a: Updated database schema - contains formatting errors
   • Use 'git format --fixup' to fix automatically

git format instructions: https://wiki.internal.com/git-format
WARNING: DO NOT RESOLVE MANUALLY - Will auto-resolve when fixed
```

### 2. Commit Message Validation (`mrproper-message`)
- **Format**: `TAG(TICKET): Subject`
- **Validation**: Length, capitalization, trailer verification
- **Cross-Reference**: Reviewed-By trailers vs GitLab approvals
- **Configuration**: Project-specific via `.mr-proper.conf`

#### Results Format
```
commit message check report
=============================================

| Commit | Status |
|--------|--------|
|abc123f<br>`BUG(PROJ-123): Fix login issue`|✓|
|def456a<br>`Added new feature`|✗ Missing tag format|

WARNING: 1 commit is missing `Reviewed-By` trailer
Hint: Use `git gitlab-apply-reviewers`
```

### 3. AI Quality Assessment (`rate-my-mr`)
The most comprehensive validator that combines AI-powered analysis with static code metrics to provide a holistic quality assessment.

- **AI Analysis**: Code review, bug detection, security scanning
- **Metrics**: LOC analysis, complexity measurement, lint patterns
- **Scoring**: 1-5 star quality rating with automatic blocking
- **Integration**: GitLab discussion with detailed breakdown

#### Results Format
```
:star2: MR Quality Rating Report :star2:
========================================

## Overall Rating: 4/5
:star::star::star::star::white_circle:

### Quality Assessment Results
:white_check_mark: AI-powered summary generated successfully
:white_check_mark: Comprehensive AI code review completed
Lines Added: 156, Lines Removed: 23, Net Change: 133
WARNING: New Lint Disables: 2

### Scoring Breakdown
| Metric | Status | Impact |
|--------|--------|--------|
| Lines of Code | 133 lines | Within limits |
| Lint Disables | 2 new disables | WARNING: New lint suppressions added |

**Final Score**: 4/5 points
:white_check_mark: Quality assessment passed - MR meets quality standards
```

For detailed technical architecture, AI prompts, scoring algorithms, and configuration options, see **[Phase 3: Rate my MR Deep Dive](./ARCHITECTURE.md#phase-3-rate-my-mr-deep-dive)** in the Architecture documentation.

## Integration Guide

### Adding New Validators

#### Integration Best Practices

**1. Dependency Management**
- Always add new dependencies to `requirements.txt`
- Test imports before committing
- Use virtual environments for development

**2. Code Structure Pattern**
For new validators, follow this pattern:
```
mrproper/mrproper/
├── your_validator.py          # Core logic
├── your_validator_gitlab.py   # GitLab integration
└── bin/your-validator         # CLI entry point
```

**3. Import Standards**
- Use relative imports: `from .module import Class`
- Add all imports at the top
- Group imports: stdlib, third-party, local

#### Implementation Steps

**Step 1: Create Validation Module**
```python
# mrproper/mrproper/my_validator.py
import sys
import urllib.parse
from . import gitlab

HEADER = """\
My Validator Report
===================

"""

def handle_mr(proj, mriid):
    # Get MR data
    mr = gitlab.gitlab(f"/projects/{proj}/merge_requests/{mriid}")

    # Implement validation logic
    results = perform_validation(mr)

    # Format results for GitLab discussion
    report_body = format_results(results)

    # Update GitLab discussion
    gitlab.update_discussion(proj, mriid, HEADER, report_body,
                           must_not_be_resolved=has_issues(results))

def main():
    proj = urllib.parse.quote(sys.argv[1], safe="")
    mriid = int(sys.argv[2])
    handle_mr(proj, mriid)
```

**Step 2: Add Entry Point Script**
```python
# mrproper/bin/my-validator
#!/usr/bin/env python3
import mrproper.my_validator

if __name__ == '__main__':
    mrproper.my_validator.main()
```

**Step 3: Update Allowed Checkers**
```python
# webhook-server/server.py
ALLOWED_CHECKERS = {
    'mrproper-clang-format',
    'mrproper-message',
    'rate-my-mr',
    'my-validator',  # Add new validator
}
```

**Step 4: Update Setup Configuration**
```python
# mrproper/setup.py
scripts=['bin/mrproper-clang-format',
         'bin/mrproper-message',
         'bin/rate-my-mr',
         'bin/my-validator']  # Add new script
```

**Step 5: Integration Checklist**
- [ ] Add validator to `ALLOWED_CHECKERS`
- [ ] Create `*_gitlab.py` wrapper module
- [ ] Add binary script to `setup.py`
- [ ] Test with webhook server
- [ ] Update Docker builds
- [ ] Document configuration

#### Testing Integration
```bash
# Test imports
cd mrproper
python -c "from mrproper import your_module; print('OK')"

# Rebuild containers
./build-docker-images

# Test single validator
curl -X POST http://localhost:9912/mr-proper/my-validator

# Test combined validators
curl -X POST http://localhost:9912/mr-proper/mrproper-clang-format+my-validator
```

## Troubleshooting

### Common Issues

#### Webhook Server Not Responding
**Symptoms**: No validation containers being launched
```bash
# Check server status
ssh docker@10.X.X.X "docker ps | grep webhook"

# View webhook logs
ssh docker@10.X.X.X "tail -f /home/docker/tmp/mr-validator-logs/webhook-server.log"

# Test webhook endpoint
curl -X POST http://your-server:9912/mr-proper/mrproper-clang-format
```
**Fix**: Check GitLab webhook configuration points to correct URL

#### Validation Containers Failing
**Symptoms**: Containers exit immediately or with errors
```bash
# List recent containers
ssh docker@10.X.X.X "docker ps -a | grep mr-checker-vp-test"

# Check specific container logs
ssh docker@10.X.X.X "docker logs <container-name>"

# Test container manually
docker run --rm --env-file mrproper.env mr-checker-vp-test mrproper-clang-format project/test 123
```
**Common Causes**:
- `mrproper.env` file missing
- Wrong Docker image name
- Missing dependencies

#### GitLab API Issues
**Symptoms**: "401 Unauthorized" or "403 Forbidden" errors
- Verify `GITLAB_ACCESS_TOKEN` in `mrproper.env`
- Check token permissions (API access required)
- Ensure GitLab host configuration matches your instance

**Test API Access**:
```bash
source mrproper.env
curl -H "PRIVATE-TOKEN: $GITLAB_ACCESS_TOKEN" \
     https://git.internal.com/api/v4/projects
```

#### Invalid Checkers Error
**Symptoms**: Webhook returns "Invalid checkers requested"
**Fix**: Ensure webhook URL uses correct validator names:
- `mrproper-clang-format`
- `mrproper-message`
- `rate-my-mr`

#### Dependencies Missing
**Symptoms**: `ModuleNotFoundError` in container logs
```bash
# Rebuild containers with dependencies
./build-docker-images
```

#### AI Service Connectivity
**Symptoms**: AI analysis fails or times out
- Verify AI service at `http://10.31.88.29:6006` is accessible
- Check network connectivity from validation containers
- Review timeout settings (default: 120 seconds)

**Test AI Service**:
```bash
curl -X POST http://10.31.88.29:6006/generate \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"test"}]}'
```


### Debug Logging Locations
```
Host: /home/docker/tmp/mr-validator-logs/
├── webhook-server.log                              # Webhook activities with REQUEST_ID
├── rate-my-mr-{REQUEST_ID}-{container}.log        # AI analysis logs per request
├── gitlab-api-{REQUEST_ID}-{container}.log        # GitLab API calls per request
└── ...                                             # Per-container logs
```

#### Comprehensive Debug Workflow

**Step 1: Check if Webhook is Received**
```bash
# Monitor webhook server logs in real-time
ssh docker@10.X.X.X "tail -f /home/docker/tmp/mr-validator-logs/webhook-server.log"

# Look for log entries like:
# [a1b2c3d4] === NEW WEBHOOK REQUEST ===
# REQUEST_ID: 20241103_103045_a1b2c3d4
```

**Step 2: Verify Container Launch**
```bash
# Check if validation containers are created
ssh docker@10.X.X.X "docker ps | grep mr-"

# Check specific container logs
ssh docker@10.X.X.X "docker logs <container-name>"
```

**Step 3: Check GitLab API Access**
```bash
# View validator container logs for API errors
ssh docker@10.X.X.X "docker logs <mr-container> 2>&1 | grep -i 'gitlab\|error\|401\|403'"
```

**Step 4: Monitor All Activity in Real-time**
```bash
# Terminal 1: Webhook logs
ssh docker@10.X.X.X "tail -f /home/docker/tmp/mr-validator-logs/webhook-server.log"

# Terminal 2: Docker events
ssh docker@10.X.X.X "docker events --filter container=mrproper-webhook-vp-test"

# Terminal 3: All container logs
ssh docker@10.X.X.X "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep mr-"
```

#### Request ID Tracking
Each webhook request gets a unique ID like `20241103_103045_a1b2c3d4` (REQUEST_ID_SHORT: `a1b2c3d4`).

**How it works**:
1. Webhook generates REQUEST_ID: `20241103_103045_a1b2c3d4`
2. Passes to containers via environment variable
3. All logs include `[a1b2c3d4]` prefix for correlation

**Find all logs for specific request**:
```bash
# Trace entire request flow
ssh docker@10.X.X.X "grep 'a1b2c3d4' /home/docker/tmp/mr-validator-logs/*.log"

# View specific request log file
ssh docker@10.X.X.X "cat /home/docker/tmp/mr-validator-logs/rate-my-mr-a1b2c3d4-*.log"
```

**Benefits**:
- End-to-end tracing from webhook → validator → GitLab
- Easy debugging: one grep command shows entire flow
- Correlate errors across multiple log files

### Performance Monitoring
```bash
# Container count monitoring
docker ps --format "table {{.Names}}\t{{.Status}}" | grep mr-checker-vp-test | wc -l

# Memory usage tracking
docker stats --format "table {{.Container}}\t{{.MemUsage}}" $(docker ps -q --filter ancestor=mr-checker-vp-test)

# Log directory size
du -sh /home/docker/tmp/mr-validator-logs/

# Monitor AI service response times
time curl -X POST http://10.31.88.29:6006/generate \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"test"}]}'

# Check GitLab API rate limits
curl -I https://git.internal.com/api/v4/projects
```

### Deployment Verification
After deployment, verify the system is working:

```bash
# SSH to target server
ssh docker@10.X.X.X

# Check if mrproper.env was created correctly
cat mrproper.env
# Should show: GITLAB_ACCESS_TOKEN=glpat-...

# Check container is running
docker ps | grep mrproper-webhook-vp-test

# Check logs
docker logs mrproper-webhook-vp-test

# Test webhook endpoint
curl http://localhost:9912/mr-proper/mrproper-clang-format
```

### Security Notes
- **GitLab token is masked** in CI variables
- **File created with restricted permissions** on target server
- **SSH key is base64-encoded** in CI variables
- **No secrets in git repository**

## Architecture

For detailed technical architecture, deployment flows, and system internals, see:

**[ARCHITECTURE.md](./ARCHITECTURE.md)** - Comprehensive technical documentation


### Key Components
- **Webhook Server**: Tornado-based HTTP handler (Port 9912)
- **Validation Library**: Python-based analysis modules
- **Docker Integration**: Isolated container execution
- **GitLab API Client**: Comprehensive API integration
- **AI Service Integration**: External code analysis service

### Performance Characteristics
- **High Concurrency**: 100+ simultaneous MR validations
- **Resource Efficient**: ~200MB per validation container
- **Fast Response**: <5 second webhook acknowledgment
- **Comprehensive Analysis**: 3-5 minute complete validation

## Contributing

### Development Setup
1. Clone repository
2. Build development images: `./build-docker-images`
3. Configure test environment: `cp mrproper.env.example mrproper.env`
4. Start development server: `./start-server`

### Adding Features
- See [Integration Guide](#integration-guide) for adding validators
- Follow existing patterns in `mrproper/mrproper/` modules
- Update documentation and tests

## License

Internal use - see company licensing policies.

---

*MR Validator provides comprehensive automated code quality enforcement integrated directly into the GitLab development workflow, ensuring consistent standards while providing detailed feedback to developers.*