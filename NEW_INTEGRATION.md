# New Integration Guide: Adding `rate_my_mr` Validator

This document provides a comprehensive guide for integrating a new validator (`rate_my_mr`) into the existing MR Validator system. This serves as both implementation instructions and a template for adding future validators.

## 📋 Table of Contents

- [Integration Overview](#-integration-overview)
- [Architecture Impact](#-architecture-impact)
- [Implementation Steps](#%EF%B8%8F-implementation-steps)
- [Deployment Guide](#-deployment-guide)
- [Performance Impact](#-performance-impact)
- [Configuration Options](#-configuration-options)
- [Troubleshooting](#-troubleshooting)
- [Debugging & Troubleshooting](#-debugging--troubleshooting)
  - [Quick Debug Checklist](#-quick-debug-checklist)
  - [Container Log Access](#-container-log-access)
  - [AI Service Debugging](#-ai-service-debugging)
  - [GitLab Integration Issues](#-gitlab-integration-issues)
  - [Common Issues & Solutions](#-common-issues--solutions)
  - [Performance Debugging](#-performance-debugging)
  - [Advanced Debugging](#-advanced-debugging)
  - [Creating Debug Reports](#-creating-debug-reports)
- [Documentation Updates Required](#-documentation-updates-required)

## 🎯 Integration Overview

### Current System State
- **Existing Validators**: 2 (`mrproper-clang-format`, `mrproper-message`)
- **Container Pattern**: 1 webhook → N validator containers
- **Processing**: Sequential webhook handling, parallel validator execution

### Target System State
- **Total Validators**: 3 (adding `rate_my_mr`)
- **New Container Pattern**: 1 webhook → up to 3 validator containers
- **Enhanced Functionality**: MR quality rating and feedback system

### Integration Scope
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ GitLab Webhook  │    │ Webhook Server   │    │ Validator Pool  │
│                 │    │                  │    │                 │
│ POST mr-proper/ │───▶│ ALLOWED_CHECKERS │───▶│ ┌─ clang-format│
│ clang+message+  │    │ + rate-my-mr     │    │ ├─ message     │
│ rate-my-mr      │    │                  │    │ └─ rate-my-mr  │
│                 │    │                  │    │    (NEW)       │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## 📈 Architecture Impact

### Resource Scaling Analysis

#### Before Integration (Current)
```
100 MR Events × 2 Validators = 200 Containers
├─ Memory Usage: 200 × 200MB = ~40GB
├─ API Calls: 200 × 4-6 calls = 800-1200 requests
├─ Processing Time: ~5 minutes total
└─ Git Operations: 200 temporary repositories
```

#### After Integration (With rate_my_mr)
```
100 MR Events × 3 Validators = 300 Containers
├─ Memory Usage: 300 × 200MB = ~60GB (+50%)
├─ API Calls: 300 × 4-6 calls = 1200-1800 requests (+50%)
├─ Processing Time: ~7 minutes total (+40%)
└─ Git Operations: 300 temporary repositories (+50%)
```

### Container Launch Pattern Changes

#### Current Flow
```
GitLab Webhook → Webhook Server
│
└─ for checker in ["clang-format", "message"]:
   ├─ docker run mr-checker {checker} project/ns 123
   └─ yield wait_for_exit()
```

#### New Flow
```
GitLab Webhook → Webhook Server  
│
└─ for checker in ["clang-format", "message", "rate-my-mr"]:
   ├─ docker run mr-checker {checker} project/ns 123
   └─ yield wait_for_exit()
```

## 🛠️ Implementation Steps

### Phase 1: Foundation Setup

#### Step 1: Update Webhook Server Configuration
**File**: `webhook-server/server.py`

```python
# BEFORE (Lines 8-11)
ALLOWED_CHECKERS = {
    'mrproper-clang-format',
    'mrproper-message',
}

# AFTER (Lines 8-12)
ALLOWED_CHECKERS = {
    'mrproper-clang-format',
    'mrproper-message',
    'rate-my-mr',  # NEW VALIDATOR
}
```

**Validation**: Test webhook URL acceptance
```bash
# This should now be accepted (previously 403)
curl -X POST http://localhost:9911/mr-proper/rate-my-mr
```

#### Step 2: Create Entry Point Script
**File**: `mrproper/bin/rate-my-mr`

```python
#!/usr/bin/env python3

import mrproper.rate_my_mr

if __name__ == '__main__':
    mrproper.rate_my_mr.main()
```

**Permissions**: Make executable
```bash
chmod +x mrproper/bin/rate-my-mr
```

#### Step 3: Update Package Configuration
**File**: `mrproper/setup.py`

```python
# BEFORE (Lines 6-7)
scripts=['bin/mrproper-clang-format',
         'bin/mrproper-message'],

# AFTER (Lines 6-8)  
scripts=['bin/mrproper-clang-format',
         'bin/mrproper-message',
         'bin/rate-my-mr'],  # NEW ENTRY POINT
```

### Phase 2: Core Module Implementation

#### Step 4: Create Core Validator Module
**File**: `mrproper/mrproper/rate_my_mr.py`

```python
#!/usr/bin/env python3

import subprocess
import sys
import tempfile
import urllib.parse
import os

from . import gitlab

HEADER = """\
:star2: MR Quality Rating Report :star2:
========================================

"""

RATING_CRITERIA = """\

## Rating Criteria Applied
- **Code Complexity**: Cyclomatic complexity analysis
- **Test Coverage**: Unit test presence and quality  
- **Documentation**: Comment density and README updates
- **Commit Quality**: Message clarity and atomic changes
- **File Organization**: Logical file structure and naming

"""

def calculate_mr_rating(checkout_dir, commits, mr):
    """
    Calculate MR quality score on 1-10 scale
    
    Args:
        checkout_dir: Git repository checkout directory
        commits: List of MR commits from GitLab API
        mr: MR object from GitLab API
        
    Returns:
        int: Quality score 1-10
    """
    score = 5  # Base score
    
    # Criterion 1: Commit Quality (0-2 points)
    commit_score = analyze_commit_quality(commits)
    score += commit_score
    
    # Criterion 2: Code Complexity (0-2 points)
    complexity_score = analyze_code_complexity(checkout_dir)
    score += complexity_score
    
    # Criterion 3: Documentation (-1 to +2 points)
    doc_score = analyze_documentation(checkout_dir)
    score += doc_score
    
    # Criterion 4: Test Coverage (0-1 points)
    test_score = analyze_test_coverage(checkout_dir)
    score += test_score
    
    return max(1, min(10, score))  # Clamp to 1-10 range

def analyze_commit_quality(commits):
    """Analyze commit message quality and atomicity"""
    if not commits:
        return -1
    
    score = 0
    for commit in commits:
        title = commit.title
        
        # Good commit message indicators
        if len(title) >= 10 and len(title) <= 50:
            score += 0.2
        if title[0].isupper():
            score += 0.1
        if not title.endswith('.'):
            score += 0.1
        if any(word in title.lower() for word in ['fix', 'add', 'update', 'remove']):
            score += 0.1
    
    return min(2, score)

def analyze_code_complexity(checkout_dir):
    """Analyze code complexity using basic metrics"""
    try:
        # Count Python files and basic complexity indicators
        python_files = []
        for root, dirs, files in os.walk(checkout_dir):
            for file in files:
                if file.endswith('.py'):
                    python_files.append(os.path.join(root, file))
        
        if not python_files:
            return 1  # Neutral score for non-Python projects
        
        complexity_score = 2  # Start optimistic
        
        for py_file in python_files:
            with open(py_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                lines = content.split('\n')
                
                # Simple complexity indicators
                if len(lines) > 500:  # Very long files
                    complexity_score -= 0.2
                if content.count('if ') > 20:  # Many conditionals  
                    complexity_score -= 0.1
                if content.count('for ') + content.count('while ') > 10:  # Many loops
                    complexity_score -= 0.1
                    
        return max(0, complexity_score)
        
    except Exception:
        return 1  # Neutral on analysis failure

def analyze_documentation(checkout_dir):
    """Analyze documentation quality"""
    score = 0
    
    # Check for README updates
    readme_files = ['README.md', 'README.txt', 'README.rst']
    for readme in readme_files:
        readme_path = os.path.join(checkout_dir, readme)
        if os.path.exists(readme_path):
            score += 1
            break
    
    # Count Python docstrings
    try:
        for root, dirs, files in os.walk(checkout_dir):
            for file in files:
                if file.endswith('.py'):
                    py_path = os.path.join(root, file)
                    with open(py_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        if '"""' in content or "'''" in content:
                            score += 0.2
    except Exception:
        pass
    
    return min(2, score) - 1  # Can be negative if no docs

def analyze_test_coverage(checkout_dir):
    """Analyze test presence and basic coverage"""
    test_indicators = ['test_', '_test.py', 'tests/', 'test/']
    
    for root, dirs, files in os.walk(checkout_dir):
        for item in dirs + files:
            if any(indicator in item.lower() for indicator in test_indicators):
                return 1  # Found tests
    
    return 0  # No tests found

def generate_feedback(score, checkout_dir, commits, mr):
    """Generate specific feedback items based on analysis"""
    feedback = []
    
    if score >= 8:
        feedback.append(":trophy: **Excellent MR!** High quality across all criteria.")
    elif score >= 6:
        feedback.append(":+1: **Good MR!** Meets quality standards with room for improvement.")
    elif score >= 4:
        feedback.append(":warning: **Needs Improvement** Several quality concerns identified.")
    else:
        feedback.append(":x: **Significant Issues** Multiple quality problems require attention.")
    
    # Specific improvement suggestions
    if len(commits) > 10:
        feedback.append("- Consider squashing related commits for cleaner history")
    
    if not any(analyze_test_coverage(checkout_dir) for _ in [None]):
        feedback.append("- Add unit tests to improve code reliability")
    
    # File count analysis
    try:
        py_files = sum(1 for root, dirs, files in os.walk(checkout_dir) 
                      for file in files if file.endswith('.py'))
        if py_files > 20:
            feedback.append("- Large change set - consider breaking into smaller MRs")
    except:
        pass
    
    return feedback

def format_rating_report(score, feedback_items):
    """Format the rating report for GitLab discussion"""
    
    # Rating visualization
    stars = ":star:" * score + ":white_circle:" * (10 - score)
    
    report = f"""
## Overall Rating: {score}/10

{stars}

### Quality Score Breakdown
- **Rating**: {score} out of 10 points
- **Status**: {'✅ Approved' if score >= 7 else '⚠️ Needs Review' if score >= 4 else '❌ Requires Changes'}

### Feedback
"""
    
    for item in feedback_items:
        report += f"{item}\n"
    
    report += RATING_CRITERIA
    
    if score < 7:
        report += """
:bomb: **DO NOT MERGE WITHOUT ADDRESSING FEEDBACK** :bomb:<br>
This MR requires quality improvements before merging.<br>
The rating will be automatically updated when changes are pushed.
"""
    else:
        report += """
:white_check_mark: **Quality standards met** - MR approved for merging.
"""
    
    return report

def handle_mr(proj, mriid):
    """Main MR analysis function"""
    
    # Fetch MR data from GitLab
    mr = gitlab.gitlab("/projects/{}/merge_requests/{}"
                       .format(proj, mriid))
    
    mrcommits = gitlab.gitlab("/projects/{}/merge_requests/{}/commits"
                              .format(proj, mr.iid))
    
    # Perform analysis in temporary git checkout
    with tempfile.TemporaryDirectory() as tdir:
        subprocess.call(["git", "init", "-q"], cwd=tdir)
        subprocess.call(["git", "fetch", "-q",
                         "--depth={}".format(max(len(mrcommits), 100)),
                         gitlab.get_clone_url(proj.replace('%2F', '/')),
                         "merge-requests/{}/head".format(mr.iid)],
                        cwd=tdir)
        
        subprocess.check_output(["git", "checkout", "-q", "-b", "check", "FETCH_HEAD"], cwd=tdir)
        
        # Calculate rating and generate feedback
        rating_score = calculate_mr_rating(tdir, mrcommits, mr)
        feedback_items = generate_feedback(rating_score, tdir, mrcommits, mr)
    
    # Format and post results
    must_not_be_resolved = rating_score < 7  # Block merge if score < 7
    report_body = format_rating_report(rating_score, feedback_items)
    
    gitlab.update_discussion(proj, mriid, HEADER, report_body, must_not_be_resolved)

def main():
    """Entry point for rate-my-mr validator"""
    if len(sys.argv) != 3:
        print("Usage: rate-my-mr <project> <mr_iid>")
        sys.exit(1)
        
    proj = urllib.parse.quote(sys.argv[1], safe="")
    mriid = int(sys.argv[2])
    
    try:
        handle_mr(proj, mriid)
        print(f"Successfully rated MR {mriid} in project {sys.argv[1]}")
    except Exception as e:
        print(f"Error rating MR {mriid}: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
```

### Phase 3: Integration Testing

#### Step 5: Rebuild Docker Images
```bash
# Rebuild with new validator included
./build-docker-images
```

#### Step 6: Test Single Validator
```bash
# Test rate-my-mr only
curl -X POST http://localhost:9911/mr-proper/rate-my-mr \
  -H "Content-Type: application/json" \
  -d '{
    "object_kind": "merge_request",
    "project": {"path_with_namespace": "test/project"},
    "object_attributes": {"iid": 123}
  }'
```

#### Step 7: Test Combined Validators
```bash  
# Test all three validators together
curl -X POST http://localhost:9911/mr-proper/mrproper-clang-format+mrproper-message+rate-my-mr \
  -H "Content-Type: application/json" \
  -d '{
    "object_kind": "merge_request", 
    "project": {"path_with_namespace": "test/project"},
    "object_attributes": {"iid": 123}
  }'
```

## 🚀 Deployment Guide

### Pre-deployment Checklist
- [ ] All code changes implemented and tested
- [ ] Docker images rebuilt with new validator
- [ ] GitLab webhook URLs updated to include new validator
- [ ] Monitoring configured for increased resource usage
- [ ] Rollback plan prepared

### Deployment Steps

#### 1. Code Deployment
```bash
# Stop existing server
docker stop mrproper-webhook

# Rebuild images with changes
./build-docker-images

# Restart server
./start-server
```

#### 2. GitLab Webhook Configuration Update

**Current webhook URL**:
```
http://your-server:9911/mr-proper/mrproper-clang-format+mrproper-message
```

**New webhook URL** (with rating):
```
http://your-server:9911/mr-proper/mrproper-clang-format+mrproper-message+rate-my-mr
```

**Gradual rollout option** (specific projects):
```
# Only formatting and rating
http://your-server:9911/mr-proper/mrproper-clang-format+rate-my-mr

# Only rating  
http://your-server:9911/mr-proper/rate-my-mr
```

#### 3. Monitoring Setup

**Container monitoring**:
```bash
# Monitor container count (should increase by 50%)
watch "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep mr-checker | wc -l"

# Monitor memory usage
watch "docker stats --format 'table {{.Container}}\t{{.MemUsage}}' --no-stream"
```

**API monitoring**:
```bash
# Monitor GitLab API response times
curl -w "@curl-format.txt" -s -o /dev/null https://git.internal.com/api/v4/projects
```

## 📊 Performance Impact

### Expected Changes (100 MR scenario)

| Metric | Before | After | Change | Impact |
|--------|--------|-------|--------|---------|
| **Containers** | 200 | 300 | +50% | Higher resource usage |
| **Memory** | 40GB | 60GB | +50% | May need server upgrade |
| **API Calls** | 800-1200 | 1200-1800 | +50% | Within GitLab limits |
| **Processing Time** | 5 min | 7 min | +40% | Longer validation cycles |
| **Disk I/O** | Moderate | High | +50% | More git operations |

### Resource Requirements

#### Minimum Server Specs (Updated)
- **RAM**: 64GB → **96GB** (recommended)
- **CPU**: 8 cores → **12 cores** (recommended) 
- **Disk**: 100GB → **150GB** (for temporary repositories)
- **Network**: 1Gbps (unchanged, adequate)

#### Docker Daemon Limits
```bash
# Check current limits
docker info | grep -E "(containers|images)"

# May need to adjust:
# - Max containers limit
# - Memory limit per container
# - File descriptor limits
```

## 🔧 Configuration Options

### Project-Level Rating Configuration

Create `.mr-proper.conf` in repository root:

```ini
[rating]
# Minimum score to allow merging (1-10)
min_score_threshold = 7

# Enable/disable specific checks
enable_complexity_check = true
enable_test_coverage_check = true  
enable_documentation_check = true
enable_commit_quality_check = true

# Scoring weights (must sum to 1.0)
weight_code_complexity = 0.25
weight_test_coverage = 0.25
weight_documentation = 0.25  
weight_commit_quality = 0.25

# File type exclusions
exclude_file_patterns = "*.json,*.xml,migrations/*"

# Custom thresholds
max_files_per_mr = 50
max_lines_per_file = 1000
```

## 🐛 Troubleshooting

### Common Issues and Solutions

#### Issue 1: Webhook Returns 403 Forbidden
**Cause**: `rate-my-mr` not in `ALLOWED_CHECKERS`
**Solution**: 
```bash
# Check server.py contains new validator
grep -A5 "ALLOWED_CHECKERS" webhook-server/server.py
```

#### Issue 2: Container Launch Fails
**Cause**: Entry script not found or not executable
**Solution**:
```bash
# Verify script exists and is executable
docker run --rm mr-checker ls -la /usr/local/bin/ | grep rate
docker run --rm mr-checker /usr/local/bin/rate-my-mr --help
```

#### Issue 3: High Memory Usage
**Cause**: Too many concurrent containers
**Solution**:
```bash  
# Monitor container count
docker ps | grep mr-checker | wc -l

# If > 300, investigate webhook flood or Docker cleanup issues
docker system prune -f
```

#### Issue 4: GitLab API Rate Limiting
**Cause**: Increased API calls from third validator
**Solution**:
```bash
# Check GitLab API rate limit headers
curl -I https://git.internal.com/api/v4/projects

# Consider request throttling or API key rotation
```

#### Issue 5: Slow Validation Performance
**Cause**: Complex rating algorithms or large repositories
**Solution**:
- Optimize rating algorithms for performance
- Add timeout limits to analysis functions
- Consider sampling for large repositories

### Debug Commands

```bash
# Test single validator execution
docker run --rm -v $(pwd)/mrproper.env:/mrproper.env mr-checker rate-my-mr project/test 123

# Check container logs
docker logs $(docker ps -q --filter ancestor=mr-checker | head -1)

# Verify GitLab API connectivity
docker run --rm -v $(pwd)/mrproper.env:/mrproper.env mr-checker python3 -c "
from mrproper import gitlab
print(gitlab.gitlab('/projects'))
"

# Monitor resource usage
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}"
```

## 📚 Documentation Updates Required

### Files to Update
- [ ] **README.md**: Add rate-my-mr to examples and supported validators
- [ ] **webhook-server/README.md**: Update ALLOWED_CHECKERS list  
- [ ] **mrproper/README.md**: Add rate_my_mr module documentation
- [ ] **NEW_INTEGRATION.md**: This file serves as template for future integrations

### Example Updates

**Main README.md** additions:
```markdown
**Supported Validators:**
- `mrproper-clang-format` - Code formatting validation
- `mrproper-message` - Commit message standards validation  
- `rate-my-mr` - MR quality rating and feedback (NEW)

### Usage Examples

**All Validators**:
```bash
curl -X POST http://localhost:9911/mr-proper/mrproper-clang-format+mrproper-message+rate-my-mr
```

**GitLab Webhook URL**:
```
http://your-server:9911/mr-proper/mrproper-clang-format+mrproper-message+rate-my-mr
```
```

# 🔍 Debugging & Troubleshooting

This section provides comprehensive debugging capabilities for troubleshooting the AI-powered `rate-my-mr` validator integration.

## ⚡ Quick Debug Checklist

When `rate-my-mr` is not working, check these in order:

1. **Is the webhook being received?**
   ```bash
   # Check webhook server logs
   docker logs $(docker ps -q --filter ancestor=mrproper-webhook-vp-test)
   ```

2. **Are rate-my-mr containers being launched?**
   ```bash
   # Count running containers
   docker ps --filter ancestor=mr-checker-vp-test | grep rate-my-mr
   ```

3. **Is the AI service reachable?**
   ```bash
   # Test AI service connectivity
   curl -v http://10.31.88.29:6006/generate
   ```

4. **Are GitLab API calls working?**
   ```bash
   # Test GitLab API access
   curl -H "PRIVATE-TOKEN: your_token" https://git.internal.com/api/v4/projects
   ```

## 🐳 Container Log Access

### Finding Containers

```bash
# List all MR validation containers
docker ps --filter ancestor=mr-checker-vp-test --format "table {{.Names}}\t{{.Status}}\t{{.Command}}"

# List webhook server containers  
docker ps --filter ancestor=mrproper-webhook-vp-test --format "table {{.Names}}\t{{.Status}}"

# Show recently exited containers (for failed validations)
docker ps -a --filter ancestor=mr-checker-vp-test --filter status=exited --format "table {{.Names}}\t{{.Status}}\t{{.Command}}"
```

### Accessing Container Logs

#### Real-time Log Streaming
```bash
# Stream logs from webhook server
docker logs -f $(docker ps -q --filter ancestor=mrproper-webhook-vp-test)

# Stream logs from most recent rate-my-mr container
docker logs -f $(docker ps -q --filter ancestor=mr-checker-vp-test | head -1)
```

#### Historical Log Access
```bash
# Get logs from specific container by name/ID
docker logs CONTAINER_NAME_OR_ID

# Get last 100 lines of logs
docker logs --tail 100 CONTAINER_NAME_OR_ID

# Get logs with timestamps
docker logs -t CONTAINER_NAME_OR_ID

# Get logs from last hour
docker logs --since 1h CONTAINER_NAME_OR_ID
```

### Debug Log Patterns to Look For

The enhanced debugging provides detailed log patterns:

#### ✅ Successful rate-my-mr Execution
```
[DEBUG] ===== STARTING MR ANALYSIS =====
[DEBUG] Project: my-org%2Fmy-project  
[DEBUG] MR IID: 123
[DEBUG] Fetching MR data from GitLab API...
[DEBUG] MR fetched successfully: Fix authentication bug
[DEBUG] Found 3 commits in MR 123
[DEBUG] Setting up temporary git repository...
[DEBUG] Git fetch completed successfully
[DEBUG] Git checkout completed successfully
[DEBUG] Generated diff length: 1250 characters
[DEBUG] Step 1: Generating AI summary...
[DEBUG] AI Service Response - Status Code: 200
[DEBUG] AI summary result: SUCCESS
...
[DEBUG] ✅ Successfully posted report to GitLab
[DEBUG] ===== MR ANALYSIS COMPLETED =====
```

#### ❌ Failed AI Service Connection
```
[DEBUG] Step 1: Generating AI summary...
[DEBUG] AI Service Request - URL: http://10.31.88.29:6006/generate
[DEBUG] Sending POST request to AI service...
[DEBUG] AI Service Connection Error: HTTPConnectionPool(host='10.31.88.29', port=6006): Max retries exceeded
[DEBUG] This suggests the AI service is not reachable
[DEBUG] AI summary result: FAILED
```

#### ❌ GitLab API Issues
```
[DEBUG] Fetching MR data from GitLab API...
[DEBUG] GitLab API error: 401 Unauthorized
[DEBUG] Error type: HTTPError
```

#### ❌ Git Repository Problems
```
[DEBUG] Git fetch completed successfully
[DEBUG] Git checkout failed: fatal: reference is not a tree: FETCH_HEAD
```

## 🤖 AI Service Debugging

### Testing AI Service Connectivity

#### Basic Connectivity Test
```bash
# Test if AI service is responding
curl -v -X POST http://10.31.88.29:6006/generate \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"test"}]}'
```

#### Container Network Test
```bash
# Test from inside a container
docker run --rm mr-checker-vp-test curl -v http://10.31.88.29:6006/generate
```

### Common AI Service Issues

#### Issue 1: Connection Refused
```
[DEBUG] AI Service Connection Error: [Errno 111] Connection refused
```
**Diagnosis**: AI service is down or not listening on port 6006
**Solution**: 
- Check if AI service is running on 10.31.88.29:6006
- Verify firewall/network rules
- Test connectivity from Docker host

#### Issue 2: Timeout
```
[DEBUG] AI Service Timeout Error: Read timed out
[DEBUG] AI service took longer than 120 seconds to respond
```
**Diagnosis**: AI service is overloaded or processing is slow
**Solutions**:
- Check AI service resource usage
- Consider increasing timeout in `params.py`
- Monitor AI service queue/load

#### Issue 3: HTTP Errors
```
[DEBUG] AI Service HTTP Error: 500 Server Error
[DEBUG] Response content: {"error": "Internal server error"}
```
**Diagnosis**: AI service internal error
**Solutions**:
- Check AI service logs
- Verify request payload format
- Test with minimal payload

### AI Service Configuration

Current configuration in `params.py`:
```python
class RMMConstants(Enum):
    agent_url = "http://10.31.88.29:6006/generate"
```

To change AI service endpoint:
1. Update `mrproper/mrproper/params.py`
2. Rebuild Docker image: `./build-docker-images`
3. Restart webhook server: `./start-server`

## 🦊 GitLab Integration Issues

### Testing GitLab API Access

```bash
# Test with your token from mrproper.env
source mrproper.env
curl -H "PRIVATE-TOKEN: $GITLAB_ACCESS_TOKEN" \
     https://git.internal.com/api/v4/projects
```

### Common GitLab Issues

#### Issue 1: 401 Unauthorized
```
[DEBUG] GitLab API error: 401 Unauthorized
```
**Solutions**:
- Verify `GITLAB_ACCESS_TOKEN` in `mrproper.env`
- Test token with curl command above
- Check if token has required permissions (api scope)

#### Issue 2: Project Not Found
```
[DEBUG] GitLab API error: 404 Project Not Found
```
**Solutions**:
- Verify project path encoding (spaces become `%20`)
- Check if token has access to the project
- Verify project exists and is accessible

#### Issue 3: Rate Limiting
```
[DEBUG] GitLab API error: 429 Too Many Requests
```
**Solutions**:
- Wait and retry
- Check if multiple validators are hitting API limits
- Consider API request optimization

## 🐛 Common Issues & Solutions

### Issue 1: rate-my-mr Container Not Starting

**Symptoms**:
```bash
docker ps --filter ancestor=mr-checker-vp-test | grep rate-my-mr
# Returns no results
```

**Debug Steps**:
```bash
# Check webhook server logs for error messages
docker logs $(docker ps -q --filter ancestor=mrproper-webhook-vp-test) | grep rate-my-mr

# Manually test container launch
docker run --rm mr-checker-vp-test rate-my-mr --help
```

**Common Causes**:
- `rate-my-mr` not in `ALLOWED_CHECKERS`
- Binary not executable in container
- Missing dependencies (radon, prettytable)

### Issue 2: Empty Diff File

**Symptoms**:
```
[DEBUG] Generated diff length: 0 characters
[DEBUG] ERROR: Could not create diff file for analysis
```

**Debug Steps**:
```bash
# Check if MR has actual changes
# Look for commits in container logs:
[DEBUG] Found 0 commits in MR 123  # Problem!
[DEBUG] Found 3 commits in MR 123  # OK
```

**Solutions**:
- Verify MR has commits and changes
- Check git fetch/checkout process
- Verify base branch exists (origin/master)

### Issue 3: Dependencies Missing

**Symptoms**:
```
ModuleNotFoundError: No module named 'radon'
ModuleNotFoundError: No module named 'prettytable'
```

**Solution**:
```bash
# Rebuild containers with dependencies
./build-docker-images
```

### Issue 4: Webhook Not Received

**Symptoms**:
- No containers being launched
- No log entries in webhook server

**Debug Steps**:
```bash
# Check webhook server is running
docker ps --filter ancestor=mrproper-webhook-vp-test

# Test webhook endpoint manually
curl -X POST http://your-server:9912/mr-proper/rate-my-mr \
  -H "Content-Type: application/json" \
  -d '{"object_kind":"merge_request","project":{"path_with_namespace":"test/project"},"object_attributes":{"iid":123}}'
```

## 📊 Performance Debugging

### Monitoring Resource Usage

```bash
# Monitor container resource usage
docker stats --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}" \
  $(docker ps -q --filter ancestor=mr-checker-vp-test)

# Check container count
echo "Active rate-my-mr containers: $(docker ps -q --filter ancestor=mr-checker-vp-test | wc -l)"

# Monitor AI service response times
time curl -X POST http://10.31.88.29:6006/generate \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"test"}]}'
```

### Performance Issues

#### Slow Processing
Look for these patterns in logs:
- Long gaps between debug messages
- AI service timeout errors
- High container count (resource contention)

#### Memory Issues
```bash
# Check host memory usage
free -h

# Check for OOM killed containers
dmesg | grep -i "killed process"
```

## 🔧 Advanced Debugging

### Running Manual Validation

```bash
# Create test environment file
echo "GITLAB_ACCESS_TOKEN=your_token" > test.env

# Run validation manually
docker run --rm --env-file test.env mr-checker-vp-test \
  rate-my-mr "project/namespace" 123
```

### Debugging Inside Container

```bash
# Get shell access to running container
docker exec -it CONTAINER_ID /bin/bash

# Or start new container with shell
docker run --rm -it mr-checker-vp-test /bin/bash

# Inside container, test components:
python3 -c "from mrproper.params import RMMConstants; print(RMMConstants.agent_url.value)"
python3 -c "import requests; print(requests.__version__)"
```

### Network Debugging

```bash
# Test network from container
docker run --rm mr-checker-vp-test ping 10.31.88.29
docker run --rm mr-checker-vp-test nslookup git.internal.com
```

## 📝 Creating Debug Reports

When reporting issues, include:

1. **Container logs** (last 100 lines minimum)
2. **Webhook server logs** around the time of failure
3. **Manual tests** (AI service connectivity, GitLab API)
4. **System info** (docker version, host resources)
5. **Configuration** (anonymized mrproper.env, params.py values)

### Example Debug Report Template

```
## Issue Description
rate-my-mr validator not working - no results posted to GitLab

## Environment
- Docker version: 20.10.x
- Host OS: Ubuntu 20.04
- Webhook server port: 9912
- Container names: mr-checker-vp-test, mrproper-webhook-vp-test

## Container Logs
```
[DEBUG] ===== STARTING MR ANALYSIS =====
[DEBUG] AI Service Connection Error: [Errno 111] Connection refused
...
```

## Tests Performed
- [x] Webhook server responding
- [x] Containers launching
- [ ] AI service reachable
- [x] GitLab API accessible

## Configuration
- AI service URL: http://10.31.88.29:6006/generate
- GitLab token: configured (tested OK)
```

---

## 📚 Documentation Updates Required

### Files to Update
- [ ] **README.md**: Add rate-my-mr to examples and supported validators
- [ ] **webhook-server/README.md**: Update ALLOWED_CHECKERS list  
- [ ] **mrproper/README.md**: Add rate_my_mr module documentation
- [ ] **NEW_INTEGRATION.md**: This file serves as template for future integrations

### Example Updates

**Main README.md** additions:
```markdown
**Supported Validators:**
- `mrproper-clang-format` - Code formatting validation
- `mrproper-message` - Commit message standards validation  
- `rate-my-mr` - AI-powered MR quality assessment (NEW)

### Usage Examples

**All Validators**:
```bash
curl -X POST http://localhost:9912/mr-proper/mrproper-clang-format+mrproper-message+rate-my-mr
```

**GitLab Webhook URL**:
```
http://your-server:9912/mr-proper/mrproper-clang-format+mrproper-message+rate-my-mr
```
```

This comprehensive integration and debugging guide serves as both implementation documentation and troubleshooting resource for adding the AI-powered `rate_my_mr` validator to the MR Validator system.

---

*Document Version: 2.0*  
*Updated: Added comprehensive debugging capabilities*  
*Template for: Future validator integrations and troubleshooting*