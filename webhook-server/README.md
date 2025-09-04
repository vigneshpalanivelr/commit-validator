# Webhook Server

The webhook server is a Tornado-based web application that receives GitLab merge request events and triggers validation checks. It acts as the entry point for the MR validation pipeline.

## 📋 Table of Contents

- [Architecture Overview](#architecture-overview)
- [Components](#components)
  - [server.py](#serverpy)
  - [Tornado Web Framework](#tornado-web-framework)
  - [Request Flow](#request-flow)
  - [Key Classes and Functions](#key-classes-and-functions)
  - [Detailed Handler Flow](#detailed-handler-flow)
  - [Allowed Checkers](#allowed-checkers)
  - [Docker Integration](#docker-integration)
  - [Environment Requirements](#environment-requirements)
- [Dockerfile](#dockerfile)
- [Configuration](#configuration)
- [Error Handling](#error-handling)
- [Integration Points](#integration-points)
- [Usage](#usage)

## Architecture Overview

The webhook server follows this flow:
1. **main()** → Validates environment and starts server
2. **app.listen()** → Binds to port 9912 and starts listening
3. **routes** → Maps `/mr-proper/*` to GitLabWebHookHandler
4. **GitLabWebHookHandler** → Processes webhook events and launches validators

## Components

### server.py

Main server implementation with the following key components:

#### Tornado Web Framework
- **Framework**: Uses Tornado for asynchronous web handling
- **Port**: Listens on port 9912 (configurable via environment)
- **Route**: `/mr-proper/{checker}` where checker specifies validation types

#### Request Flow
```
GitLab Webhook → Tornado Server → GitLabWebHookHandler.post() → Docker Container Launch
```

#### Key Classes and Functions

**AttrDict (Lines 14-21)**
- Custom dictionary class enabling attribute-style access
- Used for convenient access to JSON webhook data

**json_decode() (Lines 23-24)**
- JSON decoder that converts objects to AttrDict instances
- Enables `data.object_kind` instead of `data['object_kind']`

**GitLabWebHookHandler (Lines 27-71)**
- Main webhook handler class inheriting from `tornado.web.RequestHandler`
- Processes POST requests from GitLab webhooks

#### Detailed Handler Flow

**1. Checker Validation (Lines 30-35)**
- Extracts checker names from URL path (e.g., "mrproper-clang-format+mrproper-message+rate-my-mr")
- Splits on "+" to support multiple validators in single request
- Validates each checker against `ALLOWED_CHECKERS` whitelist
- Returns HTTP 403 Forbidden if any invalid checker requested
- Prevents unauthorized validator execution

**2. JSON Parsing (Line 37)**  
- Decodes GitLab webhook JSON payload from request body
- Uses custom `json_decode()` with `AttrDict` for dot-notation access
- Converts `data['object_kind']` to `data.object_kind` syntax
- Handles UTF-8 encoding from GitLab webhook

**3. MR Event Detection (Line 38)**
- Filters webhook events to process only `merge_request` events
- Ignores other GitLab events (push, issue, pipeline, etc.)
- Logs detailed MR event data for debugging (Lines 39-41)
- Early exit if not a merge request event

**4. Change Analysis (Lines 42-52)**
- Extracts `changes` object from webhook payload
- Removes noise changes that don't affect validation:
  - `total_time_spent`: Time tracking updates
  - `updated_at`: Automatic timestamp changes
- Determines if MR has substantive changes requiring validation
- Helps avoid unnecessary validation runs

**5. User Filtering (Line 54)**
- Ignores webhook events triggered by "jenkins" user
- Prevents validation loops from automated systems
- Allows manual override via debugging flag (Line 56)
- Ensures only human-triggered events are processed

**6. Branch Change Detection (Lines 56-59)**
- Logic currently assumes branch changed if no other significant changes
- Future enhancement point for more sophisticated change detection
- Could be extended to check specific file types or paths

**7. Docker Container Launch (Lines 61-69)**
- **Iterates through each requested checker**
- **Creates Subprocess for each validator**:
  - `docker run -d`: Detached mode for non-blocking execution
  - `--rm`: Auto-cleanup container when complete
  - `--env-file mrproper.env`: Inject GitLab tokens and config
  - `--log-driver=syslog`: Centralized logging
  - `mr-checker-vp-test`: Uses pre-built validation container image
- **Passes runtime arguments**:
  - Checker type (e.g., "mrproper-clang-format", "rate-my-mr")
  - Project namespace (`data.project.path_with_namespace`)
  - Merge request IID (`data.object_attributes.iid`)
- **Waits for container launch**: `yield p.wait_for_exit()` ensures container starts
- **Parallel execution**: Multiple validators run simultaneously

**8. Response Handling (Line 70)**
- Returns "OK!" to GitLab to acknowledge webhook receipt
- Prevents GitLab webhook timeout and retry attempts
- Does not wait for validation completion (asynchronous processing)

### Allowed Checkers

The system supports three validation types:
- **mrproper-clang-format**: Code formatting validation
- **mrproper-message**: Commit message validation
- **rate-my-mr**: AI-powered MR quality assessment

### Docker Integration

For each requested checker, the handler:
1. Launches a Docker container with `mr-checker-vp-test` image
2. Passes environment variables via `mrproper.env`
3. Provides project namespace and MR IID as arguments
4. Uses detached mode (`-d`) and auto-cleanup (`--rm`)
5. Configures syslog driver for logging

### Environment Requirements

- **mrproper.env**: Must contain GitLab access token and configuration
- **Docker**: Must be available and accessible to the server process

## Dockerfile

The webhook server Docker image:
- **Base**: `artifact.internal.com:6555/python:3-alpine` for minimal footprint
- **Dependencies**: 
  - `docker-cli` for launching validation containers
  - `tornado` web framework
  - Internal artifact repository configuration
- **Port**: Exposes 9912
- **Entry**: Runs `server.py` directly

## Configuration

### Environment Variables
- Configured via `mrproper.env` file
- Contains GitLab access tokens and API endpoints

### Port Configuration
- Currently runs on port 9912
- Configurable via environment variables

## Error Handling

- **403 Forbidden**: Returned for invalid checker requests
- **Docker Validation**: Ensures Docker is available before starting
- **File Validation**: Ensures mrproper.env exists before starting

## Integration Points

- **Input**: GitLab webhook events (JSON payload)
- **Output**: Docker container execution for validation
- **Dependencies**: 
  - **[../mrproper/](../mrproper/)** - Core validation library and Docker containers
    - Uses `mr-checker-vp-test` Docker image built from mrproper/
    - Executes [mrproper-clang-format](../mrproper/bin/mrproper-clang-format), [mrproper-message](../mrproper/bin/mrproper-message), and [rate-my-mr](../mrproper/bin/rate-my-mr) scripts
    - Leverages [GitLab API client](../mrproper/mrproper/gitlab.py) for posting results
  - **Docker daemon** for container orchestration
  - **GitLab API** for webhook delivery
  - **Root configuration** via [../mrproper.env](../mrproper.env) and [../start-server](../start-server) script

## Usage

The server is typically started via the [../start-server](../start-server) script in the project root, which:
1. Validates [../mrproper.env](../mrproper.env) exists
2. Runs the webhook server in a Docker container
3. Mounts Docker socket for container-in-container execution
4. References [../build-docker-images](../build-docker-images) for initial setup