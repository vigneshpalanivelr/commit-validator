"""Shared pytest fixtures for all tests."""

import os
import tempfile
import pytest
from unittest.mock import Mock, MagicMock
from tests.fixtures.sample_payloads import (
    SAMPLE_MR_WEBHOOK,
    SAMPLE_MR_WEBHOOK_JENKINS,
    SAMPLE_MR_WEBHOOK_WITH_CHANGES,
    SAMPLE_PUSH_WEBHOOK,
    SAMPLE_MR_RESPONSE,
    SAMPLE_COMMITS_RESPONSE,
    SAMPLE_DISCUSSION_RESPONSE,
    SAMPLE_NOTES_RESPONSE
)
from tests.fixtures.sample_diffs import (
    SAMPLE_PYTHON_DIFF,
    SAMPLE_MULTI_FILE_DIFF,
    SAMPLE_SECURITY_DIFF,
    SAMPLE_COMPLEX_DIFF,
    SAMPLE_LINT_DISABLE_DIFF
)
from tests.fixtures.mock_responses import (
    MockDockerAPI,
    MockGitLabAPI,
    MockAIService
)


# ============================================================================
# Environment and Configuration Fixtures
# ============================================================================

@pytest.fixture
def mock_env(monkeypatch):
    """Mock environment variables with defaults for testing."""
    env_vars = {
        'GITLAB_ACCESS_TOKEN': 'test-token-12345',
        'BFA_HOST': 'http://test-bfa-host:8000',
        'BFA_TOKEN_KEY': 'test-bfa-token',
        'AI_SERVICE_URL': 'http://test-ai-service:6006',
        'API_TIMEOUT': '120',
        'LOG_DIR': '/tmp/test-logs',
        'LOG_LEVEL': 'DEBUG',
        'LOG_MAX_BYTES': '52428800',
        'LOG_BACKUP_COUNT': '3',
        'LOG_STRUCTURE': 'organized',
        'REQUEST_ID': 'test-request-123',
        'PROJECT_ID': 'test-org/test-project',
        'MR_IID': '42'
    }
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)
    return env_vars


@pytest.fixture
def temp_env_file(tmp_path):
    """Create a temporary .env file for testing."""
    env_file = tmp_path / "test.env"
    env_content = """
GITLAB_ACCESS_TOKEN=test-token-12345
BFA_HOST=http://test-bfa-host:8000
BFA_TOKEN_KEY=test-bfa-token
AI_SERVICE_URL=http://test-ai-service:6006
API_TIMEOUT=120
LOG_DIR=/tmp/test-logs
LOG_LEVEL=DEBUG
"""
    env_file.write_text(env_content.strip())
    return str(env_file)


@pytest.fixture
def temp_dir(tmp_path):
    """Create a temporary directory for testing."""
    return tmp_path


@pytest.fixture
def temp_log_dir(tmp_path):
    """Create a temporary log directory."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    return str(log_dir)


# ============================================================================
# Docker Fixtures
# ============================================================================

@pytest.fixture
def mock_docker_client(mocker):
    """Mock Docker client for testing."""
    client = MockDockerAPI.mock_docker_client()
    mocker.patch('docker.from_env', return_value=client)
    mocker.patch('docker.DockerClient', return_value=client)
    return client


@pytest.fixture
def mock_docker_container():
    """Mock Docker container."""
    return MockDockerAPI.mock_container()


@pytest.fixture
def mock_docker_image():
    """Mock Docker image."""
    return MockDockerAPI.mock_image()


# ============================================================================
# GitLab API Fixtures
# ============================================================================

@pytest.fixture
def mock_gitlab_api(mocker):
    """Mock GitLab API requests."""
    def mock_request(method, url, **kwargs):
        # Default success response
        return MockGitLabAPI.success_response({'message': 'success'})

    mock = mocker.patch('requests.request', side_effect=mock_request)
    mocker.patch('requests.get', side_effect=mock_request)
    mocker.patch('requests.post', side_effect=mock_request)
    mocker.patch('requests.put', side_effect=mock_request)
    mocker.patch('requests.delete', side_effect=mock_request)
    return mock


@pytest.fixture
def sample_mr_data():
    """Sample MR data from GitLab API."""
    return SAMPLE_MR_RESPONSE


@pytest.fixture
def sample_commits_data():
    """Sample commits data from GitLab API."""
    return SAMPLE_COMMITS_RESPONSE


@pytest.fixture
def sample_discussion_data():
    """Sample discussion data from GitLab API."""
    return SAMPLE_DISCUSSION_RESPONSE


# ============================================================================
# Webhook Payload Fixtures
# ============================================================================

@pytest.fixture
def sample_mr_webhook():
    """Sample MR webhook payload."""
    return SAMPLE_MR_WEBHOOK.copy()


@pytest.fixture
def sample_jenkins_webhook():
    """Sample webhook from jenkins user."""
    return SAMPLE_MR_WEBHOOK_JENKINS.copy()


@pytest.fixture
def sample_webhook_with_changes():
    """Sample webhook with changes."""
    return SAMPLE_MR_WEBHOOK_WITH_CHANGES.copy()


@pytest.fixture
def sample_push_webhook():
    """Sample push webhook (non-MR)."""
    return SAMPLE_PUSH_WEBHOOK.copy()


# ============================================================================
# Git Diff Fixtures
# ============================================================================

@pytest.fixture
def sample_python_diff():
    """Sample Python file diff."""
    return SAMPLE_PYTHON_DIFF


@pytest.fixture
def sample_multi_file_diff():
    """Sample multi-file diff."""
    return SAMPLE_MULTI_FILE_DIFF


@pytest.fixture
def sample_security_diff():
    """Sample diff with security issues."""
    return SAMPLE_SECURITY_DIFF


@pytest.fixture
def sample_complex_diff():
    """Sample diff with high cyclomatic complexity."""
    return SAMPLE_COMPLEX_DIFF


@pytest.fixture
def sample_lint_disable_diff():
    """Sample diff with lint disable comments."""
    return SAMPLE_LINT_DISABLE_DIFF


@pytest.fixture
def temp_git_repo(tmp_path):
    """Create a temporary git repository for testing."""
    import subprocess

    repo_dir = tmp_path / "test-repo"
    repo_dir.mkdir()

    # Initialize git repo
    subprocess.run(['git', 'init'], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(['git', 'config', 'user.email', 'test@example.com'], cwd=repo_dir, check=True)
    subprocess.run(['git', 'config', 'user.name', 'Test User'], cwd=repo_dir, check=True)

    # Create initial commit
    test_file = repo_dir / "test.py"
    test_file.write_text("def hello():\n    print('Hello')\n")
    subprocess.run(['git', 'add', '.'], cwd=repo_dir, check=True)
    subprocess.run(['git', 'commit', '-m', 'Initial commit'], cwd=repo_dir, check=True)

    return str(repo_dir)


# ============================================================================
# AI Service Fixtures
# ============================================================================

@pytest.fixture
def mock_ai_service(mocker):
    """Mock AI/LLM service responses."""
    def mock_post(url, **kwargs):
        if '/api/token' in url:
            return MockGitLabAPI.success_response(
                MockAIService.jwt_token_response()
            )
        else:
            return MockGitLabAPI.success_response(
                MockAIService.success_response()
            )

    mocker.patch('requests.post', side_effect=mock_post)
    return mock_post


# ============================================================================
# Subprocess Fixtures
# ============================================================================

@pytest.fixture
def mock_subprocess(mocker):
    """Mock subprocess calls."""
    from tests.fixtures.mock_responses import MockSubprocess

    mock = mocker.patch('subprocess.run')
    mock.return_value = MockSubprocess.success()
    return mock


@pytest.fixture
def mock_subprocess_popen(mocker):
    """Mock subprocess.Popen."""
    class MockPopen:
        def __init__(self, *args, **kwargs):
            self.returncode = 0
            self.stdout = Mock()
            self.stderr = Mock()
            self.stdout.read = Mock(return_value=b"")
            self.stderr.read = Mock(return_value=b"")

        def communicate(self):
            return (b"", b"")

        def wait(self):
            return 0

    mock = mocker.patch('subprocess.Popen', return_value=MockPopen())
    return mock


# ============================================================================
# Tornado Async Fixtures
# ============================================================================

@pytest.fixture
def mock_tornado_subprocess(mocker):
    """Mock Tornado subprocess for async testing."""
    class MockTornadoSubprocess:
        def __init__(self, *args, **kwargs):
            self.returncode = 0

        async def wait_for_exit(self):
            return

    mock = mocker.patch('tornado.process.Subprocess', return_value=MockTornadoSubprocess())
    return mock


# ============================================================================
# Time and Date Fixtures
# ============================================================================

@pytest.fixture
def frozen_time():
    """Freeze time for testing."""
    from freezegun import freeze_time
    with freeze_time("2023-01-01 12:00:00"):
        yield


# ============================================================================
# File System Fixtures
# ============================================================================

@pytest.fixture
def mock_file_permissions(tmp_path, mocker):
    """Create files with specific permissions for testing."""
    def create_file_with_perms(filename, mode):
        file_path = tmp_path / filename
        file_path.write_text("test content")
        os.chmod(file_path, mode)
        return str(file_path)

    return create_file_with_perms


@pytest.fixture
def mock_disk_usage(mocker):
    """Mock disk usage statistics."""
    def set_disk_usage(total, used, free):
        class MockUsage:
            def __init__(self, total, used, free):
                self.total = total
                self.used = used
                self.free = free

        mocker.patch('shutil.disk_usage', return_value=MockUsage(total, used, free))

    return set_disk_usage
