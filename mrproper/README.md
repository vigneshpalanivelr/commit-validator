# MRProper - Core Validation Library

The MRProper package provides the core validation functionality for merge request quality checks. It serves as the engine that powers all validation types including code formatting, commit message validation, and AI-powered quality assessment.

## 📋 Table of Contents

- [Architecture Overview](#architecture-overview)
- [Package Structure](#package-structure)
  - [Entry Points (bin/)](#entry-points-bin)
  - [Core Library (mrproper/)](#core-library-mrproper)
- [Validation Modules](#validation-modules)
  - [Code Formatting (git_format.py)](#code-formatting-git_formatpy)
  - [Message Validation (message.py)](#message-validation-messagepy)
  - [AI Quality Assessment (rate_my_mr.py)](#ai-quality-assessment-rate_my_mrpy)
  - [GitLab Integration (rate_my_mr_gitlab.py)](#gitlab-integration-rate_my_mr_gitlabpy)
  - [Lines of Code Analysis (loc.py)](#lines-of-code-analysis-locpy)
  - [Configuration (params.py)](#configuration-paramspy)
  - [GitLab API Client (gitlab.py)](#gitlab-api-client-gitlabpy)
- [Docker Integration](#docker-integration)
- [Setup and Installation](#setup-and-installation)
- [Usage Patterns](#usage-patterns)
- [Configuration](#configuration)
- [Integration Points](#integration-points)

## Architecture Overview

The MRProper library follows a modular architecture:

```
webhook-server → Docker Container → bin/[validator] → mrproper/[module].py → GitLab API
```

1. **Webhook Server** triggers Docker containers for each validation type
2. **Entry Points** (bin/) provide command-line interfaces for each validator
3. **Core Modules** (mrproper/) implement validation logic and GitLab integration
4. **Results** are posted back to GitLab as MR discussions

## Package Structure

### Entry Points (bin/)

Command-line scripts that serve as entry points for Docker container execution:

- **`mrproper-clang-format`** - Code formatting validation
- **`mrproper-message`** - Commit message validation  
- **`rate-my-mr`** - AI-powered MR quality assessment

Each script delegates to corresponding modules in the `mrproper/` package.

### Core Library (mrproper/)

Python package containing all validation logic and utilities:

- **Validation Modules**: Core validation implementations
- **GitLab Integration**: API clients and discussion posting
- **Utilities**: Configuration, LOC analysis, and helper functions

## Validation Modules

### Code Formatting (git_format.py)

Handles clang-format validation for code style consistency:
- Runs clang-format on modified files
- Generates formatting suggestions
- Posts results to GitLab MR discussions

### Message Validation (message.py)

Validates commit message format and content:
- Checks commit message structure
- Validates conventional commit formats
- Ensures message quality standards

### AI Quality Assessment (rate_my_mr.py)

Core AI-powered analysis engine:
- **`send_request(payload, url)`** - Communicates with AI service at `http://10.31.88.29:6006/generate`
- **`generate_summary(file_path)`** - Creates concise MR summaries
- **`generate_initial_code_review(file_path)`** - Performs comprehensive code reviews
- **`generate_lint_disable_report(file_path)`** - Analyzes lint suppressions
- **`cal_rating(total_loc, lint_disable_count)`** - Calculates quality scores (1-5)

**Analysis Pipeline:**
1. Diff analysis and summarization
2. Bug detection and code quality review
3. Security and performance assessment
4. LOC metrics calculation
5. Lint disable pattern detection
6. Final quality scoring

### GitLab Integration (rate_my_mr_gitlab.py)

Wrapper providing GitLab-specific functionality for AI assessment:

**Key Functions:**
- **`create_diff_from_mr(proj, mriid, checkout_dir)`** - Generates git diff from MR data
- **`format_rating_report(summary_success, review_success, loc_data, lint_data, rating_score)`** - Creates formatted reports
- **`handle_mr(proj, mriid)`** - Main analysis pipeline with GitLab integration

**Analysis Flow:**
1. Fetch MR data via GitLab API
2. Create temporary git repository
3. Generate diff for analysis
4. Run complete AI analysis pipeline
5. Calculate quality metrics and rating
6. Post comprehensive report to GitLab discussion
7. Set discussion resolution status based on quality score

### Lines of Code Analysis (loc.py)

Calculates code change metrics using the Radon library:
- **Lines Added/Removed**: Tracks code change volume
- **Net Change**: Overall impact measurement
- **Complexity Analysis**: Code complexity metrics

**Integration**: Used by rate_my_mr for quality scoring and threshold enforcement.

### Configuration (params.py)

Centralized configuration using Python enums:

**RMMConstants:**
- `agent_url`: AI service endpoint configuration

**RMMWeights:**
- Scoring weights for different quality factors
- Total possible score configuration

**RMMLimits:**
- Thresholds for LOC limits and other constraints

### GitLab API Client (gitlab.py)

Handles all GitLab API communication:
- **Authentication**: Token-based GitLab access
- **MR Data Retrieval**: Fetches merge request information
- **Discussion Management**: Posts and updates MR discussions
- **Repository Operations**: Clone URL generation and git operations

## Docker Integration

The MRProper library is containerized for isolated execution:

**Base Image**: `artifact.internal.com:6555/python:3-alpine`

**Key Dependencies:**
- `radon` - Code metrics and LOC analysis
- `prettytable` - Formatted output generation
- `requests` - HTTP communication for AI service

**Container Execution Pattern:**
```bash
docker run -d --rm --env-file mrproper.env mr-checker-vp-test [validator] [project] [mr_iid]
```

## Setup and Installation

The package uses `setup.py` for installation and dependency management:

```python
# setup.py configures:
# - Package structure and dependencies
# - Entry point scripts in bin/
# - Python package installation
```

**Environment Requirements:**
- `mrproper.env` file with GitLab tokens and configuration
- Access to AI service at configured endpoint
- Docker runtime for containerized execution

## Usage Patterns

### Command Line Usage
```bash
# From within container:
mrproper-clang-format <project> <mr_iid>
mrproper-message <project> <mr_iid>  
rate-my-mr <project> <mr_iid>
```

### Python API Usage
```python
from mrproper.rate_my_mr_gitlab import handle_mr
from mrproper.loc import LOCCalculator
from mrproper import gitlab

# Analyze MR quality
handle_mr('my-org/my-project', 123)

# Calculate LOC metrics
loc_calc = LOCCalculator('diff_file.txt')
success, data = loc_calc.calculate_loc()
```

## Configuration

### Environment Variables
Configuration via `mrproper.env`:
- GitLab access tokens
- API endpoint URLs
- Service configurations

### AI Service Configuration
- **Endpoint**: `http://10.31.88.29:6006/generate`
- **Timeout**: 120 seconds
- **Format**: JSON payload with messages array

## Integration Points

### Input Sources
- **GitLab Webhooks**: Via webhook-server triggering
- **GitLab API**: Direct MR data retrieval
- **Git Repositories**: Diff generation and analysis

### Output Destinations  
- **GitLab Discussions**: MR comments and resolutions
- **Container Logs**: Debug output and analysis details
- **Syslog**: Centralized logging via Docker log driver

### External Dependencies
- **AI Service**: `http://10.31.88.29:6006/generate` for quality analysis
- **GitLab API**: Repository and MR data access
- **Docker Runtime**: Container orchestration and isolation
- **Git**: Repository operations and diff generation

---

*This package serves as the core validation engine for the MR Validator system, providing comprehensive code quality assessment through multiple validation approaches.*