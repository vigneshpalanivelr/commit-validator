"""
Unit tests for manage_container.py

Tests cover:
- Utility functions (format_bytes, mask_value, get_host_ip)
- Configuration loading and validation
- Docker operations (build, start, stop, restart, logs, status, remove)
- Webhook testing
- CLI command handlers
- SimpleConsole, SimpleTable, SimpleProgress, SimplePrompt fallback classes
"""

import os
import sys
import pytest
import socket
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call
import docker.errors

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import manage_container as mc


# ============================================================================
# Utility Function Tests
# ============================================================================

class TestFormatBytes:
    """Tests for format_bytes()."""

    def test_bytes(self):
        assert mc.format_bytes(512) == "512.0 B"

    def test_kilobytes(self):
        assert mc.format_bytes(1024) == "1.0 KB"

    def test_megabytes(self):
        assert mc.format_bytes(1024 * 1024) == "1.0 MB"

    def test_gigabytes(self):
        assert mc.format_bytes(1024 ** 3) == "1.0 GB"

    def test_terabytes(self):
        assert mc.format_bytes(1024 ** 4) == "1.0 TB"

    def test_petabytes(self):
        assert mc.format_bytes(1024 ** 5) == "1.0 PB"

    def test_fractional(self):
        result = mc.format_bytes(1536)  # 1.5 KB
        assert "1.5 KB" == result

    def test_zero(self):
        assert mc.format_bytes(0) == "0.0 B"

    def test_large_value(self):
        result = mc.format_bytes(2.5 * 1024 ** 3)
        assert "2.5 GB" == result


class TestMaskValue:
    """Tests for mask_value()."""

    def test_none_returns_not_set(self):
        assert "Not Set" in mc.mask_value(None)

    def test_empty_string_returns_not_set(self):
        assert "Not Set" in mc.mask_value("")

    def test_not_set_literal(self):
        assert "Not Set" in mc.mask_value("Not Set")

    def test_short_value_fully_masked(self):
        result = mc.mask_value("abc", show_chars=8)
        assert result == "****"

    def test_long_value_shows_prefix(self):
        result = mc.mask_value("glpat-abcdefghij", show_chars=8)
        assert result.startswith("glpat-ab")
        assert "****" in result

    def test_exact_length_masked(self):
        result = mc.mask_value("12345678", show_chars=8)
        assert result == "****"

    def test_custom_show_chars(self):
        result = mc.mask_value("my-secret-token", show_chars=3)
        assert result.startswith("my-")
        assert "****" in result


class TestGetHostIp:
    """Tests for get_host_ip()."""

    def test_returns_string(self):
        with patch('socket.socket') as mock_sock:
            mock_sock.return_value.__enter__ = Mock(return_value=mock_sock.return_value)
            mock_sock.return_value.__exit__ = Mock(return_value=False)
            mock_sock.return_value.getsockname.return_value = ('192.168.1.100', 0)
            result = mc.get_host_ip()
        assert isinstance(result, str)

    def test_returns_fallback_on_exception(self):
        with patch('socket.socket', side_effect=Exception("network error")):
            result = mc.get_host_ip()
        assert result == '127.0.0.1'

    def test_returns_detected_ip(self):
        with patch('socket.socket') as mock_sock_class:
            mock_sock = Mock()
            mock_sock.getsockname.return_value = ('10.0.0.5', 0)
            mock_sock_class.return_value.__enter__ = Mock(return_value=mock_sock)
            mock_sock_class.return_value.__exit__ = Mock(return_value=False)
            result = mc.get_host_ip()
        assert result == '10.0.0.5'


# ============================================================================
# Configuration Tests
# ============================================================================

class TestLoadConfig:
    """Tests for load_config()."""

    def test_returns_none_for_missing_file(self, tmp_path):
        result = mc.load_config(tmp_path / "nonexistent.env")
        assert result is None

    def test_loads_existing_file(self, tmp_path):
        env_file = tmp_path / "test.env"
        env_file.write_text("GITLAB_ACCESS_TOKEN=test-token\nLOG_LEVEL=DEBUG\n")
        result = mc.load_config(env_file)
        assert result is not None
        assert result['GITLAB_ACCESS_TOKEN'] == 'test-token'
        assert result['LOG_LEVEL'] == 'DEBUG'

    def test_returns_dict(self, tmp_path):
        env_file = tmp_path / "test.env"
        env_file.write_text("KEY=VALUE\n")
        result = mc.load_config(env_file)
        assert isinstance(result, dict)

    def test_empty_file(self, tmp_path):
        env_file = tmp_path / "test.env"
        env_file.write_text("")
        result = mc.load_config(env_file)
        assert result is not None
        assert isinstance(result, dict)


class TestValidateRequiredFields:
    """Tests for validate_required_fields()."""

    def test_valid_config(self):
        config = {'GITLAB_ACCESS_TOKEN': 'glpat-test123'}
        errors, warnings = mc.validate_required_fields(config)
        assert errors == []

    def test_missing_token(self):
        config = {}
        errors, warnings = mc.validate_required_fields(config)
        assert any('GITLAB_ACCESS_TOKEN' in e for e in errors)

    def test_empty_token(self):
        config = {'GITLAB_ACCESS_TOKEN': ''}
        errors, warnings = mc.validate_required_fields(config)
        assert any('GITLAB_ACCESS_TOKEN' in e for e in errors)

    def test_returns_tuple(self):
        result = mc.validate_required_fields({'GITLAB_ACCESS_TOKEN': 'token'})
        assert isinstance(result, tuple)
        assert len(result) == 2


class TestValidateLoggingConfig:
    """Tests for validate_logging_config()."""

    def test_valid_log_level_debug(self):
        errors, warnings = mc.validate_logging_config({'LOG_LEVEL': 'DEBUG'})
        assert errors == []

    def test_valid_log_level_info(self):
        errors, warnings = mc.validate_logging_config({'LOG_LEVEL': 'INFO'})
        assert errors == []

    def test_valid_log_level_warning(self):
        errors, warnings = mc.validate_logging_config({'LOG_LEVEL': 'WARNING'})
        assert errors == []

    def test_valid_log_level_error(self):
        errors, warnings = mc.validate_logging_config({'LOG_LEVEL': 'ERROR'})
        assert errors == []

    def test_valid_log_level_critical(self):
        errors, warnings = mc.validate_logging_config({'LOG_LEVEL': 'CRITICAL'})
        assert errors == []

    def test_invalid_log_level(self):
        errors, _ = mc.validate_logging_config({'LOG_LEVEL': 'VERBOSE'})
        assert any('LOG_LEVEL' in e for e in errors)

    def test_case_insensitive_log_level(self):
        errors, _ = mc.validate_logging_config({'LOG_LEVEL': 'debug'})
        assert errors == []

    def test_no_log_level_no_error(self):
        errors, _ = mc.validate_logging_config({})
        assert errors == []

    def test_unwritable_log_dir(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        os.chmod(log_dir, 0o444)
        try:
            errors, _ = mc.validate_logging_config({'LOG_DIR': str(log_dir)})
            assert any('not writable' in e for e in errors)
        finally:
            os.chmod(log_dir, 0o755)

    def test_nonexistent_log_dir_no_error(self, tmp_path):
        errors, _ = mc.validate_logging_config({'LOG_DIR': str(tmp_path / "newdir")})
        assert errors == []


class TestValidateAiConfig:
    """Tests for validate_ai_config()."""

    def test_no_ai_config_warns(self):
        _, warnings = mc.validate_ai_config({})
        assert any('AI' in w or 'BFA' in w for w in warnings)

    def test_both_set_warns(self):
        config = {'BFA_HOST': 'http://bfa:8000', 'AI_SERVICE_URL': 'http://ai:6006'}
        _, warnings = mc.validate_ai_config(config)
        assert any('BFA_HOST' in w or 'precedence' in w for w in warnings)

    def test_only_bfa_host_valid(self):
        config = {'BFA_HOST': 'http://bfa:8000', 'API_TIMEOUT': '120'}
        errors, warnings = mc.validate_ai_config(config)
        assert errors == []
        assert not any('BFA_HOST' in w or 'precedence' in w for w in warnings)

    def test_only_ai_service_url_valid(self):
        config = {'AI_SERVICE_URL': 'http://ai:6006', 'API_TIMEOUT': '120'}
        errors, _ = mc.validate_ai_config(config)
        assert errors == []

    def test_ai_url_without_http_warns(self):
        config = {'AI_SERVICE_URL': 'ai-service:6006', 'API_TIMEOUT': '120'}
        _, warnings = mc.validate_ai_config(config)
        assert any('http' in w for w in warnings)

    def test_invalid_timeout_errors(self):
        config = {'BFA_HOST': 'http://bfa:8000', 'API_TIMEOUT': 'notanumber'}
        errors, _ = mc.validate_ai_config(config)
        assert any('API_TIMEOUT' in e for e in errors)

    def test_low_timeout_warns(self):
        config = {'BFA_HOST': 'http://bfa:8000', 'API_TIMEOUT': '10'}
        _, warnings = mc.validate_ai_config(config)
        assert any('low' in w or 'timeout' in w.lower() for w in warnings)

    def test_high_timeout_warns(self):
        config = {'BFA_HOST': 'http://bfa:8000', 'API_TIMEOUT': '400'}
        _, warnings = mc.validate_ai_config(config)
        assert any('high' in w for w in warnings)

    def test_default_timeout_used_when_not_set(self):
        config = {'BFA_HOST': 'http://bfa:8000'}
        errors, _ = mc.validate_ai_config(config)
        assert errors == []

    def test_https_url_valid(self):
        config = {'AI_SERVICE_URL': 'https://secure-ai:6006', 'API_TIMEOUT': '120'}
        errors, warnings = mc.validate_ai_config(config)
        assert errors == []
        assert not any('http' in w for w in warnings)


class TestValidateSystemResources:
    """Tests for validate_system_resources()."""

    def test_low_disk_warns(self, mocker):
        class FakeUsage:
            free = int(0.5 * 1024 ** 3)
            total = int(10 * 1024 ** 3)
            used = total - free

        mocker.patch('shutil.disk_usage', return_value=FakeUsage())
        _, warnings = mc.validate_system_resources({})
        assert any('disk' in w.lower() or 'space' in w.lower() for w in warnings)

    def test_adequate_disk_no_warn(self, mocker):
        class FakeUsage:
            free = int(50 * 1024 ** 3)
            total = int(100 * 1024 ** 3)
            used = total - free

        mocker.patch('shutil.disk_usage', return_value=FakeUsage())
        _, warnings = mc.validate_system_resources({})
        assert not any('disk' in w.lower() for w in warnings)

    def test_insecure_env_file_warns(self, tmp_path, mocker):
        env_file = tmp_path / "mrproper.env"
        env_file.write_text("KEY=VALUE\n")
        os.chmod(env_file, 0o644)
        mocker.patch.object(mc, 'ENV_FILE', str(env_file))
        _, warnings = mc.validate_system_resources({})
        assert any('permission' in w.lower() or 'insecure' in w.lower() for w in warnings)

    def test_disk_exception_no_crash(self, mocker):
        mocker.patch('shutil.disk_usage', side_effect=Exception("Disk error"))
        errors, warnings = mc.validate_system_resources({})
        assert errors == []


class TestValidateConfig:
    """Tests for validate_config() (aggregator)."""

    def test_valid_full_config_no_errors(self, mocker):
        class FakeUsage:
            free = int(50 * 1024 ** 3)
            total = int(100 * 1024 ** 3)
            used = total - free

        mocker.patch('shutil.disk_usage', return_value=FakeUsage())
        config = {
            'GITLAB_ACCESS_TOKEN': 'glpat-test',
            'BFA_HOST': 'http://bfa:8000',
            'API_TIMEOUT': '120',
            'LOG_LEVEL': 'INFO',
        }
        errors, _ = mc.validate_config(config)
        assert errors == []

    def test_missing_token_in_aggregate(self):
        errors, _ = mc.validate_config({})
        assert any('GITLAB_ACCESS_TOKEN' in e for e in errors)

    def test_returns_lists(self):
        errors, warnings = mc.validate_config({'GITLAB_ACCESS_TOKEN': 'token'})
        assert isinstance(errors, list)
        assert isinstance(warnings, list)


# ============================================================================
# Disk Space and File Permission Tests
# ============================================================================

class TestGetDiskSpace:
    """Tests for get_disk_space()."""

    def test_returns_tuple(self, mocker):
        class FakeUsage:
            free = int(10 * 1024 ** 3)
            total = int(100 * 1024 ** 3)
            used = total - free

        mocker.patch('shutil.disk_usage', return_value=FakeUsage())
        result = mc.get_disk_space(Path('/tmp'))
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_exception_returns_unknown(self, mocker):
        mocker.patch('shutil.disk_usage', side_effect=Exception("error"))
        available, total, percent = mc.get_disk_space(Path('/tmp'))
        assert available == "Unknown"
        assert total == "Unknown"
        assert percent == 0.0

    def test_percent_used_calculation(self, mocker):
        class FakeUsage:
            total = 100 * 1024 ** 3
            used = 80 * 1024 ** 3
            free = total - used

        mocker.patch('shutil.disk_usage', return_value=FakeUsage())
        _, _, percent = mc.get_disk_space(Path('/tmp'))
        assert abs(percent - 80.0) < 0.1


class TestCheckFilePermissions:
    """Tests for check_file_permissions()."""

    def test_secure_600(self, tmp_path):
        f = tmp_path / "test.env"
        f.write_text("content")
        os.chmod(f, 0o600)
        perms, is_secure = mc.check_file_permissions(f)
        assert perms == '600'
        assert is_secure is True

    def test_secure_400(self, tmp_path):
        f = tmp_path / "test.env"
        f.write_text("content")
        os.chmod(f, 0o400)
        perms, is_secure = mc.check_file_permissions(f)
        assert perms == '400'
        assert is_secure is True

    def test_insecure_644(self, tmp_path):
        f = tmp_path / "test.env"
        f.write_text("content")
        os.chmod(f, 0o644)
        perms, is_secure = mc.check_file_permissions(f)
        assert perms == '644'
        assert is_secure is False

    def test_nonexistent_file(self, tmp_path):
        perms, is_secure = mc.check_file_permissions(tmp_path / "missing.env")
        assert perms == "Unknown"
        assert is_secure is False


# ============================================================================
# SimpleConsole / SimpleTable / SimpleProgress / SimplePrompt Tests
# ============================================================================

class TestSimpleConsole:
    """Tests for SimpleConsole fallback class."""

    def test_print_string(self, capsys):
        console = mc.SimpleConsole()
        console.print("hello world")
        out = capsys.readouterr().out
        assert "hello world" in out

    def test_strips_rich_markup(self, capsys):
        console = mc.SimpleConsole()
        console.print("[bold red]Error[/bold red]")
        out = capsys.readouterr().out
        assert "Error" in out
        assert "[bold" not in out

    def test_print_with_style_kwarg(self, capsys):
        console = mc.SimpleConsole()
        console.print("test", style="red")
        out = capsys.readouterr().out
        assert "test" in out

    def test_print_simple_table(self, capsys):
        console = mc.SimpleConsole()
        table = mc.SimpleTable(title="My Table")
        table.add_column("Col1")
        table.add_column("Col2")
        table.add_row("a", "b")
        console.print(table)
        out = capsys.readouterr().out
        assert "a" in out


class TestSimpleTable:
    """Tests for SimpleTable fallback class."""

    def test_add_column(self):
        table = mc.SimpleTable(title="Test")
        table.add_column("Name")
        assert "Name" in table.columns

    def test_add_row(self):
        table = mc.SimpleTable()
        table.add_column("A")
        table.add_column("B")
        table.add_row("val1", "val2")
        assert ("val1", "val2") in table.rows

    def test_str_empty_table(self):
        table = mc.SimpleTable(title="Empty")
        assert str(table) == ""

    def test_str_with_rows(self):
        table = mc.SimpleTable(title="Test Table")
        table.add_column("Key")
        table.add_column("Value")
        table.add_row("name", "Alice")
        output = str(table)
        assert "name" in output
        assert "Alice" in output

    def test_str_strips_markup(self):
        table = mc.SimpleTable()
        table.add_column("Col")
        table.add_row("[green]yes[/green]")
        output = str(table)
        assert "yes" in output
        assert "[green]" not in output

    def test_title_in_output(self):
        table = mc.SimpleTable(title="My Title")
        table.add_column("X")
        table.add_row("data")
        output = str(table)
        assert "My Title" in output


class TestSimpleProgress:
    """Tests for SimpleProgress fallback class."""

    def test_context_manager(self):
        prog = mc.SimpleProgress()
        with prog as p:
            assert p is prog

    def test_add_task(self, capsys):
        prog = mc.SimpleProgress()
        task_id = prog.add_task("Building...")
        out = capsys.readouterr().out
        assert "Building..." in out
        assert isinstance(task_id, int)

    def test_update_no_error(self):
        prog = mc.SimpleProgress()
        task_id = prog.add_task("task")
        prog.update(task_id, advance=1)  # Should not raise


class TestSimplePrompt:
    """Tests for SimplePrompt fallback class."""

    def test_returns_valid_choice(self, monkeypatch):
        monkeypatch.setattr('builtins.input', lambda _: 'y')
        result = mc.SimplePrompt.ask("Continue?", choices=['y', 'n'], default='n')
        assert result == 'y'

    def test_default_when_empty(self, monkeypatch):
        monkeypatch.setattr('builtins.input', lambda _: '')
        result = mc.SimplePrompt.ask("Continue?", choices=['y', 'n'], default='n')
        assert result == 'n'

    def test_no_choices(self, monkeypatch):
        monkeypatch.setattr('builtins.input', lambda _: 'anything')
        result = mc.SimplePrompt.ask("Enter value:")
        assert result == 'anything'

    def test_retries_on_invalid(self, monkeypatch):
        responses = iter(['bad', 'good', 'y'])
        monkeypatch.setattr('builtins.input', lambda _: next(responses))
        result = mc.SimplePrompt.ask("Pick", choices=['y', 'n'])
        assert result == 'y'


# ============================================================================
# confirm_action Tests
# ============================================================================

class TestConfirmAction:
    """Tests for confirm_action()."""

    def test_auto_yes(self):
        assert mc.confirm_action("Continue?", auto_yes=True) is True

    def test_user_confirms_y(self, monkeypatch):
        monkeypatch.setattr('builtins.input', lambda _: 'y')
        assert mc.confirm_action("Continue?", auto_yes=False) is True

    def test_user_confirms_yes(self, monkeypatch):
        monkeypatch.setattr('builtins.input', lambda _: 'yes')
        assert mc.confirm_action("Continue?", auto_yes=False) is True

    def test_user_declines_n(self, monkeypatch):
        monkeypatch.setattr('builtins.input', lambda _: 'n')
        assert mc.confirm_action("Continue?", auto_yes=False) is False

    def test_user_declines_empty(self, monkeypatch):
        monkeypatch.setattr('builtins.input', lambda _: '')
        assert mc.confirm_action("Continue?", auto_yes=False) is False

    def test_keyboard_interrupt_returns_false(self, monkeypatch):
        def raise_interrupt(_):
            raise KeyboardInterrupt
        monkeypatch.setattr('builtins.input', raise_interrupt)
        assert mc.confirm_action("Continue?", auto_yes=False) is False

    def test_eof_error_returns_false(self, monkeypatch):
        def raise_eof(_):
            raise EOFError
        monkeypatch.setattr('builtins.input', raise_eof)
        assert mc.confirm_action("Continue?", auto_yes=False) is False


# ============================================================================
# Docker Client Tests
# ============================================================================

class TestGetDockerClient:
    """Tests for get_docker_client()."""

    def test_returns_client_when_docker_available(self, mock_docker_client):
        result = mc.get_docker_client()
        assert result is not None

    def test_returns_none_on_docker_exception(self, mocker):
        mocker.patch('docker.from_env', side_effect=docker.errors.DockerException("no docker"))
        result = mc.get_docker_client()
        assert result is None

    def test_returns_none_on_ping_failure(self, mocker):
        client = Mock()
        client.ping.side_effect = docker.errors.DockerException("ping failed")
        mocker.patch('docker.from_env', return_value=client)
        result = mc.get_docker_client()
        assert result is None


# ============================================================================
# container_exists / container_running Tests
# ============================================================================

class TestContainerExists:
    """Tests for container_exists()."""

    def test_returns_true_when_container_found(self, mock_docker_client):
        from tests.fixtures.mock_responses import MockDockerAPI
        container = MockDockerAPI.mock_container(mc.WEBHOOK_CONTAINER_NAME)
        mock_docker_client.containers._containers[mc.WEBHOOK_CONTAINER_NAME] = container
        assert mc.container_exists(mock_docker_client) is True

    def test_returns_false_when_not_found(self, mock_docker_client):
        assert mc.container_exists(mock_docker_client) is False


class TestContainerRunning:
    """Tests for container_running()."""

    def test_returns_true_when_running(self, mock_docker_client):
        from tests.fixtures.mock_responses import MockDockerAPI
        container = MockDockerAPI.mock_container(mc.WEBHOOK_CONTAINER_NAME, 'running')
        mock_docker_client.containers._containers[mc.WEBHOOK_CONTAINER_NAME] = container
        assert mc.container_running(mock_docker_client) is True

    def test_returns_false_when_exited(self, mock_docker_client):
        from tests.fixtures.mock_responses import MockDockerAPI
        container = MockDockerAPI.mock_container(mc.WEBHOOK_CONTAINER_NAME, 'exited')
        mock_docker_client.containers._containers[mc.WEBHOOK_CONTAINER_NAME] = container
        assert mc.container_running(mock_docker_client) is False

    def test_returns_false_when_not_found(self, mock_docker_client):
        assert mc.container_running(mock_docker_client) is False


# ============================================================================
# build_images Tests
# ============================================================================

class TestBuildImages:
    """Tests for build_images()."""

    def test_returns_true_on_success(self, mock_docker_client, mock_subprocess):
        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stderr = ""
        result = mc.build_images(mock_docker_client)
        assert result is True

    def test_returns_false_when_webhook_build_fails(self, mock_docker_client, mocker):
        from tests.fixtures.mock_responses import MockSubprocess
        call_count = [0]

        def mock_run(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return MockSubprocess.failure("Build failed", 1)
            return MockSubprocess.success()

        mocker.patch('subprocess.run', side_effect=mock_run)
        result = mc.build_images(mock_docker_client)
        assert result is False

    def test_returns_false_when_checker_build_fails(self, mock_docker_client, mocker):
        from tests.fixtures.mock_responses import MockSubprocess
        call_count = [0]

        def mock_run(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                return MockSubprocess.failure("Checker build failed", 1)
            return MockSubprocess.success()

        mocker.patch('subprocess.run', side_effect=mock_run)
        result = mc.build_images(mock_docker_client)
        assert result is False

    def test_returns_false_on_exception(self, mock_docker_client, mocker):
        mocker.patch('subprocess.run', side_effect=Exception("Unexpected error"))
        result = mc.build_images(mock_docker_client)
        assert result is False


# ============================================================================
# start_container Tests
# ============================================================================

class TestStartContainer:
    """Tests for start_container()."""

    def test_starts_new_container(self, mock_docker_client):
        mock_docker_client.images._images[f"{mc.WEBHOOK_IMAGE_NAME}:latest"] = Mock()
        config = {'GITLAB_ACCESS_TOKEN': 'test-token'}
        result = mc.start_container(mock_docker_client, config, skip_confirm=True)
        assert result is True

    def test_returns_true_when_already_running(self, mock_docker_client):
        from tests.fixtures.mock_responses import MockDockerAPI
        container = MockDockerAPI.mock_container(mc.WEBHOOK_CONTAINER_NAME, 'running')
        mock_docker_client.containers._containers[mc.WEBHOOK_CONTAINER_NAME] = container
        result = mc.start_container(mock_docker_client, {})
        assert result is True

    def test_starts_existing_stopped_container(self, mock_docker_client):
        from tests.fixtures.mock_responses import MockDockerAPI
        container = MockDockerAPI.mock_container(mc.WEBHOOK_CONTAINER_NAME, 'exited')
        mock_docker_client.containers._containers[mc.WEBHOOK_CONTAINER_NAME] = container
        result = mc.start_container(mock_docker_client, {})
        assert result is True
        assert container.status == 'running'

    def test_returns_false_when_image_not_found(self, mock_docker_client):
        # No image registered - containers.run raises ImageNotFound
        original_run = mock_docker_client.containers.run

        def run_raise(*args, **kwargs):
            raise docker.errors.ImageNotFound("Image not found")

        mock_docker_client.containers.run = run_raise
        result = mc.start_container(mock_docker_client, {}, skip_confirm=True)
        assert result is False

    def test_returns_false_on_api_error(self, mock_docker_client):
        def run_raise(*args, **kwargs):
            raise docker.errors.APIError("API error")

        mock_docker_client.containers.run = run_raise
        result = mc.start_container(mock_docker_client, {}, skip_confirm=True)
        assert result is False


# ============================================================================
# stop_container Tests
# ============================================================================

class TestStopContainer:
    """Tests for stop_container()."""

    def test_stops_running_container(self, mock_docker_client):
        from tests.fixtures.mock_responses import MockDockerAPI
        container = MockDockerAPI.mock_container(mc.WEBHOOK_CONTAINER_NAME, 'running')
        mock_docker_client.containers._containers[mc.WEBHOOK_CONTAINER_NAME] = container
        result = mc.stop_container(mock_docker_client)
        assert result is True

    def test_returns_true_when_not_running(self, mock_docker_client):
        from tests.fixtures.mock_responses import MockDockerAPI
        container = MockDockerAPI.mock_container(mc.WEBHOOK_CONTAINER_NAME, 'exited')
        mock_docker_client.containers._containers[mc.WEBHOOK_CONTAINER_NAME] = container
        result = mc.stop_container(mock_docker_client)
        assert result is True

    def test_returns_true_when_container_not_found(self, mock_docker_client):
        # Container doesn't exist
        result = mc.stop_container(mock_docker_client)
        assert result is True

    def test_returns_false_on_api_error(self, mock_docker_client):
        from tests.fixtures.mock_responses import MockDockerAPI
        container = MockDockerAPI.mock_container(mc.WEBHOOK_CONTAINER_NAME, 'running')
        container.stop = Mock(side_effect=docker.errors.APIError("Stop failed"))
        mock_docker_client.containers._containers[mc.WEBHOOK_CONTAINER_NAME] = container
        result = mc.stop_container(mock_docker_client)
        assert result is False


# ============================================================================
# restart_container Tests
# ============================================================================

class TestRestartContainer:
    """Tests for restart_container()."""

    def test_restart_running_container(self, mock_docker_client, mocker):
        from tests.fixtures.mock_responses import MockDockerAPI
        container = MockDockerAPI.mock_container(mc.WEBHOOK_CONTAINER_NAME, 'running')
        mock_docker_client.containers._containers[mc.WEBHOOK_CONTAINER_NAME] = container
        mock_docker_client.images._images[f"{mc.WEBHOOK_IMAGE_NAME}:latest"] = Mock()
        mocker.patch('time.sleep')
        result = mc.restart_container(mock_docker_client, {})
        assert result is True

    def test_returns_false_when_container_not_found(self, mock_docker_client):
        result = mc.restart_container(mock_docker_client, {})
        assert result is False

    def test_returns_false_when_container_not_running(self, mock_docker_client):
        from tests.fixtures.mock_responses import MockDockerAPI
        container = MockDockerAPI.mock_container(mc.WEBHOOK_CONTAINER_NAME, 'exited')
        mock_docker_client.containers._containers[mc.WEBHOOK_CONTAINER_NAME] = container
        result = mc.restart_container(mock_docker_client, {})
        assert result is False


# ============================================================================
# show_logs Tests
# ============================================================================

class TestShowLogs:
    """Tests for show_logs()."""

    def test_returns_false_when_no_container(self, mock_docker_client):
        result = mc.show_logs(mock_docker_client, follow=False)
        assert result is False

    def test_shows_static_logs(self, mock_docker_client, capsys):
        from tests.fixtures.mock_responses import MockDockerAPI
        container = MockDockerAPI.mock_container(mc.WEBHOOK_CONTAINER_NAME, 'running')
        mock_docker_client.containers._containers[mc.WEBHOOK_CONTAINER_NAME] = container
        result = mc.show_logs(mock_docker_client, follow=False)
        assert result is True

    def test_returns_false_on_api_error(self, mock_docker_client):
        from tests.fixtures.mock_responses import MockDockerAPI
        container = MockDockerAPI.mock_container(mc.WEBHOOK_CONTAINER_NAME, 'running')
        container.logs = Mock(side_effect=docker.errors.APIError("Logs failed"))
        mock_docker_client.containers._containers[mc.WEBHOOK_CONTAINER_NAME] = container
        result = mc.show_logs(mock_docker_client, follow=False)
        assert result is False


# ============================================================================
# show_status Tests
# ============================================================================

class TestShowStatus:
    """Tests for show_status()."""

    def test_returns_true_when_no_container(self, mock_docker_client):
        result = mc.show_status(mock_docker_client)
        assert result is True

    def test_shows_running_container_status(self, mock_docker_client):
        from tests.fixtures.mock_responses import MockDockerAPI
        container = MockDockerAPI.mock_container(mc.WEBHOOK_CONTAINER_NAME, 'running')
        container.attrs.update({
            'Created': '2023-01-01T12:00:00.000000Z',
            'State': {
                'Status': 'running',
                'Running': True,
                'StartedAt': '2023-01-01T12:00:00.000000Z'
            },
            'NetworkSettings': {
                'IPAddress': '172.17.0.2',
                'Ports': {f'{mc.WEBHOOK_PORT}/tcp': [{'HostPort': str(mc.WEBHOOK_PORT)}]}
            }
        })
        container.stats = Mock(return_value={
            'cpu_stats': {
                'cpu_usage': {'total_usage': 2000000},
                'system_cpu_usage': 200000000,
                'online_cpus': 2
            },
            'precpu_stats': {
                'cpu_usage': {'total_usage': 1000000},
                'system_cpu_usage': 100000000
            },
            'memory_stats': {'usage': 52428800, 'limit': 1073741824}
        })
        mock_docker_client.containers._containers[mc.WEBHOOK_CONTAINER_NAME] = container
        result = mc.show_status(mock_docker_client)
        assert result is True

    def test_shows_stopped_container_status(self, mock_docker_client):
        from tests.fixtures.mock_responses import MockDockerAPI
        container = MockDockerAPI.mock_container(mc.WEBHOOK_CONTAINER_NAME, 'exited')
        container.attrs.update({
            'Created': '2023-01-01T12:00:00Z',
            'State': {'Status': 'exited', 'Running': False},
            'NetworkSettings': {'Ports': {}}
        })
        mock_docker_client.containers._containers[mc.WEBHOOK_CONTAINER_NAME] = container
        result = mc.show_status(mock_docker_client)
        assert result is True

    def test_returns_false_on_api_error(self, mock_docker_client):
        mock_docker_client.containers.get = Mock(
            side_effect=docker.errors.APIError("Status failed")
        )
        # Patch container_exists to return True so we reach the get call
        with patch.object(mc, 'container_exists', return_value=True):
            result = mc.show_status(mock_docker_client)
        assert result is False


# ============================================================================
# remove_container Tests
# ============================================================================

class TestRemoveContainer:
    """Tests for remove_container()."""

    def test_returns_true_when_nothing_exists(self, mock_docker_client):
        result = mc.remove_container(mock_docker_client, force=True)
        assert result is True

    def test_removes_container_with_force(self, mock_docker_client):
        from tests.fixtures.mock_responses import MockDockerAPI
        container = MockDockerAPI.mock_container(mc.WEBHOOK_CONTAINER_NAME, 'exited')
        mock_docker_client.containers._containers[mc.WEBHOOK_CONTAINER_NAME] = container
        result = mc.remove_container(mock_docker_client, force=True)
        assert result is True

    def test_removes_container_and_images_with_force(self, mock_docker_client):
        from tests.fixtures.mock_responses import MockDockerAPI
        container = MockDockerAPI.mock_container(mc.WEBHOOK_CONTAINER_NAME, 'exited')
        mock_docker_client.containers._containers[mc.WEBHOOK_CONTAINER_NAME] = container
        mock_docker_client.images._images[f"{mc.WEBHOOK_IMAGE_NAME}:latest"] = Mock()
        mock_docker_client.images._images[f"{mc.CHECKER_IMAGE_NAME}:latest"] = Mock()
        mock_docker_client.images.remove = Mock()

        result = mc.remove_container(mock_docker_client, force=True, force_remove=True)
        assert result is True

    def test_interactive_cancel(self, mock_docker_client, monkeypatch):
        from tests.fixtures.mock_responses import MockDockerAPI
        container = MockDockerAPI.mock_container(mc.WEBHOOK_CONTAINER_NAME, 'exited')
        mock_docker_client.containers._containers[mc.WEBHOOK_CONTAINER_NAME] = container
        mock_docker_client.images._images[f"{mc.WEBHOOK_IMAGE_NAME}:latest"] = Mock()

        with patch.object(mc, 'Prompt') as mock_prompt:
            mock_prompt.ask.return_value = '3'
            result = mc.remove_container(mock_docker_client, force=False)
        assert result is False

    def test_stops_running_container_before_remove(self, mock_docker_client):
        from tests.fixtures.mock_responses import MockDockerAPI
        container = MockDockerAPI.mock_container(mc.WEBHOOK_CONTAINER_NAME, 'running')
        container.stop = Mock()
        container.remove = Mock()
        mock_docker_client.containers._containers[mc.WEBHOOK_CONTAINER_NAME] = container
        result = mc.remove_container(mock_docker_client, force=True)
        assert result is True
        container.stop.assert_called_once()

    def test_returns_false_on_api_error(self, mock_docker_client):
        from tests.fixtures.mock_responses import MockDockerAPI
        container = MockDockerAPI.mock_container(mc.WEBHOOK_CONTAINER_NAME, 'exited')
        container.remove = Mock(side_effect=docker.errors.APIError("Remove failed"))
        mock_docker_client.containers._containers[mc.WEBHOOK_CONTAINER_NAME] = container
        result = mc.remove_container(mock_docker_client, force=True)
        assert result is False


# ============================================================================
# test_webhook Tests
# ============================================================================

class TestTestWebhook:
    """Tests for test_webhook()."""

    def test_success(self, mocker):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mocker.patch('requests.post', return_value=mock_response)
        mocker.patch.object(mc, 'get_host_ip', return_value='127.0.0.1')
        result = mc.test_webhook(target='rate-my-mr')
        assert result is True

    def test_failure_on_request_exception(self, mocker):
        mocker.patch('requests.post', side_effect=Exception("Connection refused"))
        mocker.patch.object(mc, 'get_host_ip', return_value='127.0.0.1')
        result = mc.test_webhook(target='rate-my-mr')
        assert result is False

    def test_default_target(self, mocker):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_post = mocker.patch('requests.post', return_value=mock_response)
        mocker.patch.object(mc, 'get_host_ip', return_value='127.0.0.1')
        mc.test_webhook()
        called_url = mock_post.call_args[0][0]
        assert 'rate-my-mr' in called_url

    def test_custom_target(self, mocker):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_post = mocker.patch('requests.post', return_value=mock_response)
        mocker.patch.object(mc, 'get_host_ip', return_value='127.0.0.1')
        mc.test_webhook(target='mrproper-message')
        called_url = mock_post.call_args[0][0]
        assert 'mrproper-message' in called_url


# ============================================================================
# show_endpoints Tests
# ============================================================================

class TestShowEndpoints:
    """Tests for show_endpoints()."""

    def test_auto_detects_host(self, mocker, capsys):
        mocker.patch.object(mc, 'get_host_ip', return_value='192.168.1.1')
        mc.show_endpoints()
        # Should not raise

    def test_uses_provided_host(self, capsys):
        mc.show_endpoints(host='10.0.0.1')
        # Should not raise


# ============================================================================
# show_config_table / show_validation_results Tests
# ============================================================================

class TestShowConfigTable:
    """Tests for show_config_table()."""

    def test_quiet_mode_no_output(self, capsys):
        mc.show_config_table({'GITLAB_ACCESS_TOKEN': 'token'}, quiet=True)
        out = capsys.readouterr().out
        assert out == ""

    def test_shows_bfa_mode(self, capsys):
        config = {
            'GITLAB_ACCESS_TOKEN': 'token',
            'BFA_HOST': 'http://bfa:8000',
            'BFA_TOKEN_KEY': 'bfa-key'
        }
        mc.show_config_table(config, quiet=False)
        # Should not raise

    def test_shows_legacy_mode(self, capsys):
        config = {
            'GITLAB_ACCESS_TOKEN': 'token',
            'AI_SERVICE_URL': 'http://ai:6006'
        }
        mc.show_config_table(config, quiet=False)
        # Should not raise

    def test_shows_not_configured_mode(self, capsys):
        config = {'GITLAB_ACCESS_TOKEN': 'token'}
        mc.show_config_table(config, quiet=False)
        # Should not raise


class TestShowValidationResults:
    """Tests for show_validation_results()."""

    def test_errors_output(self, capsys):
        mc.show_validation_results(["error 1", "error 2"], [])
        # Should not raise and should print errors

    def test_warnings_output(self, capsys):
        mc.show_validation_results([], ["warning 1"])
        # Should not raise

    def test_no_output_when_empty(self, capsys):
        mc.show_validation_results([], [])
        # Should not raise


# ============================================================================
# create_config_table Tests
# ============================================================================

class TestCreateConfigTable:
    """Tests for create_config_table()."""

    def test_returns_table_object(self):
        table = mc.create_config_table("Test")
        assert table is not None

    def test_table_has_columns(self):
        table = mc.create_config_table("Test")
        # Simple or rich table: check either columns attr or add_row works
        table.add_row("key", "value")
        if hasattr(table, 'rows'):
            assert len(table.rows) == 1


# ============================================================================
# CLI Command Handler Tests
# ============================================================================

class TestCmdConfig:
    """Tests for cmd_config() CLI handler."""

    def test_exits_config_error_when_file_missing(self, tmp_path):
        args = Mock()
        args.env_file = str(tmp_path / "missing.env")
        args.quiet = False
        args.validate_only = False
        with pytest.raises(SystemExit) as exc_info:
            mc.cmd_config(args)
        assert exc_info.value.code == mc.EXIT_CONFIG_ERROR

    def test_exits_success_with_valid_config(self, tmp_path, mocker):
        env_file = tmp_path / "mrproper.env"
        env_file.write_text("GITLAB_ACCESS_TOKEN=test-token\nBFA_HOST=http://bfa:8000\nAPI_TIMEOUT=120\n")

        class FakeUsage:
            free = int(50 * 1024 ** 3)
            total = int(100 * 1024 ** 3)
            used = total - free

        mocker.patch('shutil.disk_usage', return_value=FakeUsage())

        args = Mock()
        args.env_file = str(env_file)
        args.quiet = True
        args.validate_only = False
        with pytest.raises(SystemExit) as exc_info:
            mc.cmd_config(args)
        assert exc_info.value.code == mc.EXIT_SUCCESS

    def test_exits_config_error_with_invalid_config(self, tmp_path):
        env_file = tmp_path / "mrproper.env"
        env_file.write_text("LOG_LEVEL=INVALID\n")  # Missing GITLAB_ACCESS_TOKEN
        args = Mock()
        args.env_file = str(env_file)
        args.quiet = True
        args.validate_only = False
        with pytest.raises(SystemExit) as exc_info:
            mc.cmd_config(args)
        assert exc_info.value.code == mc.EXIT_CONFIG_ERROR


class TestCmdBuild:
    """Tests for cmd_build() CLI handler."""

    def test_exits_docker_error_when_no_docker(self, mocker):
        mocker.patch('docker.from_env', side_effect=docker.errors.DockerException("No docker"))
        args = Mock()
        with pytest.raises(SystemExit) as exc_info:
            mc.cmd_build(args)
        assert exc_info.value.code == mc.EXIT_DOCKER_ERROR

    def test_exits_success_on_build_success(self, mock_docker_client, mock_subprocess):
        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stderr = ""
        args = Mock()
        with pytest.raises(SystemExit) as exc_info:
            mc.cmd_build(args)
        assert exc_info.value.code == mc.EXIT_SUCCESS

    def test_exits_docker_error_on_build_failure(self, mock_docker_client, mocker):
        from tests.fixtures.mock_responses import MockSubprocess
        mocker.patch('subprocess.run', return_value=MockSubprocess.failure("Build failed", 1))
        args = Mock()
        with pytest.raises(SystemExit) as exc_info:
            mc.cmd_build(args)
        assert exc_info.value.code == mc.EXIT_DOCKER_ERROR


class TestCmdStart:
    """Tests for cmd_start() CLI handler."""

    def test_exits_config_error_when_env_missing(self, mocker):
        mocker.patch.object(mc, 'ENV_FILE', '/nonexistent/mrproper.env')
        args = Mock()
        args.yes = True
        with pytest.raises(SystemExit) as exc_info:
            mc.cmd_start(args)
        assert exc_info.value.code == mc.EXIT_CONFIG_ERROR

    def test_exits_cancelled_when_user_declines(self, tmp_path, mock_docker_client, mocker):
        valid_config = {
            'GITLAB_ACCESS_TOKEN': 'test',
            'BFA_HOST': 'http://bfa:8000',
            'API_TIMEOUT': '120',
        }
        # load_config default arg is bound at define time, so patch the function directly
        mocker.patch.object(mc, 'load_config', return_value=valid_config)
        mocker.patch.object(mc, 'show_config_table')
        mocker.patch.object(mc, 'validate_config', return_value=([], []))
        mocker.patch.object(mc, 'show_validation_results')

        env_file = tmp_path / "mrproper.env"
        env_file.write_text("GITLAB_ACCESS_TOKEN=test\n")
        mocker.patch.object(mc, 'ENV_FILE', str(env_file))

        mocker.patch('builtins.input', return_value='n')

        args = Mock()
        args.yes = False
        with pytest.raises(SystemExit) as exc_info:
            mc.cmd_start(args)
        assert exc_info.value.code == mc.EXIT_CANCELLED


class TestCmdStop:
    """Tests for cmd_stop() CLI handler."""

    def test_exits_docker_error_when_no_docker(self, mocker):
        mocker.patch('docker.from_env', side_effect=docker.errors.DockerException("No docker"))
        args = Mock()
        with pytest.raises(SystemExit) as exc_info:
            mc.cmd_stop(args)
        assert exc_info.value.code == mc.EXIT_DOCKER_ERROR

    def test_exits_success_when_container_not_running(self, mock_docker_client):
        args = Mock()
        with pytest.raises(SystemExit) as exc_info:
            mc.cmd_stop(args)
        assert exc_info.value.code == mc.EXIT_SUCCESS


class TestCmdRestart:
    """Tests for cmd_restart() CLI handler."""

    def test_exits_config_error_when_no_env(self, mocker):
        mocker.patch.object(mc, 'load_config', return_value=None)
        args = Mock()
        with pytest.raises(SystemExit) as exc_info:
            mc.cmd_restart(args)
        assert exc_info.value.code == mc.EXIT_CONFIG_ERROR

    def test_exits_docker_error_when_no_docker(self, mocker):
        mocker.patch.object(mc, 'load_config', return_value={'GITLAB_ACCESS_TOKEN': 'token'})
        mocker.patch('docker.from_env', side_effect=docker.errors.DockerException("No docker"))
        args = Mock()
        with pytest.raises(SystemExit) as exc_info:
            mc.cmd_restart(args)
        assert exc_info.value.code == mc.EXIT_DOCKER_ERROR


class TestCmdLogs:
    """Tests for cmd_logs() CLI handler."""

    def test_exits_docker_error_when_no_docker(self, mocker):
        mocker.patch('docker.from_env', side_effect=docker.errors.DockerException("No docker"))
        args = Mock()
        args.follow = False
        with pytest.raises(SystemExit) as exc_info:
            mc.cmd_logs(args)
        assert exc_info.value.code == mc.EXIT_DOCKER_ERROR

    def test_exits_docker_error_when_container_not_found(self, mock_docker_client):
        args = Mock()
        args.follow = False
        with pytest.raises(SystemExit) as exc_info:
            mc.cmd_logs(args)
        assert exc_info.value.code == mc.EXIT_DOCKER_ERROR


class TestCmdStatus:
    """Tests for cmd_status() CLI handler."""

    def test_exits_docker_error_when_no_docker(self, mocker):
        mocker.patch('docker.from_env', side_effect=docker.errors.DockerException("No docker"))
        args = Mock()
        with pytest.raises(SystemExit) as exc_info:
            mc.cmd_status(args)
        assert exc_info.value.code == mc.EXIT_DOCKER_ERROR

    def test_exits_success_when_container_missing(self, mock_docker_client):
        args = Mock()
        with pytest.raises(SystemExit) as exc_info:
            mc.cmd_status(args)
        assert exc_info.value.code == mc.EXIT_SUCCESS


class TestCmdRemove:
    """Tests for cmd_remove() CLI handler."""

    def test_exits_docker_error_when_no_docker(self, mocker):
        mocker.patch('docker.from_env', side_effect=docker.errors.DockerException("No docker"))
        args = Mock()
        args.force = True
        args.force_remove = False
        with pytest.raises(SystemExit) as exc_info:
            mc.cmd_remove(args)
        assert exc_info.value.code == mc.EXIT_DOCKER_ERROR

    def test_exits_success_when_nothing_exists(self, mock_docker_client):
        args = Mock()
        args.force = True
        args.force_remove = False
        with pytest.raises(SystemExit) as exc_info:
            mc.cmd_remove(args)
        assert exc_info.value.code == mc.EXIT_SUCCESS

    def test_uses_force_remove_attribute(self, mock_docker_client):
        args = Mock()
        args.force = True
        del args.force_remove  # Simulate missing attribute
        args = Mock(spec=['force'])
        args.force = True
        # getattr fallback should give False
        with pytest.raises(SystemExit) as exc_info:
            mc.cmd_remove(args)
        assert exc_info.value.code == mc.EXIT_SUCCESS


class TestCmdTest:
    """Tests for cmd_test() CLI handler."""

    def test_exits_success_on_successful_webhook(self, mocker):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mocker.patch('requests.post', return_value=mock_response)
        mocker.patch.object(mc, 'get_host_ip', return_value='127.0.0.1')
        args = Mock()
        args.validator = 'rate-my-mr'
        with pytest.raises(SystemExit) as exc_info:
            mc.cmd_test(args)
        assert exc_info.value.code == mc.EXIT_SUCCESS

    def test_exits_error_on_failed_webhook(self, mocker):
        mocker.patch('requests.post', side_effect=Exception("Connection refused"))
        mocker.patch.object(mc, 'get_host_ip', return_value='127.0.0.1')
        args = Mock()
        args.validator = None
        with pytest.raises(SystemExit) as exc_info:
            mc.cmd_test(args)
        assert exc_info.value.code == mc.EXIT_ERROR

    def test_uses_default_validator_when_none(self, mocker):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_post = mocker.patch('requests.post', return_value=mock_response)
        mocker.patch.object(mc, 'get_host_ip', return_value='127.0.0.1')
        args = Mock()
        args.validator = None
        with pytest.raises(SystemExit):
            mc.cmd_test(args)
        called_url = mock_post.call_args[0][0]
        assert 'rate-my-mr' in called_url


# ============================================================================
# main() / argparse Tests
# ============================================================================

class TestMain:
    """Tests for main() CLI entry point."""

    def test_no_args_prints_help(self, capsys):
        with patch.object(sys, 'argv', ['manage_container.py']):
            with pytest.raises(SystemExit) as exc_info:
                mc.main()
        assert exc_info.value.code == mc.EXIT_ERROR

    def test_unknown_command_prints_help(self, capsys):
        with patch.object(sys, 'argv', ['manage_container.py', 'unknown']):
            with pytest.raises(SystemExit):
                mc.main()

    def test_build_command_dispatches(self, mocker):
        mock_cmd_build = mocker.patch.object(mc, 'cmd_build')
        with patch.object(sys, 'argv', ['manage_container.py', 'build']):
            try:
                mc.main()
            except SystemExit:
                pass
        mock_cmd_build.assert_called_once()

    def test_status_command_dispatches(self, mocker):
        mock_cmd_status = mocker.patch.object(mc, 'cmd_status')
        with patch.object(sys, 'argv', ['manage_container.py', 'status']):
            try:
                mc.main()
            except SystemExit:
                pass
        mock_cmd_status.assert_called_once()

    def test_stop_command_dispatches(self, mocker):
        mock_cmd_stop = mocker.patch.object(mc, 'cmd_stop')
        with patch.object(sys, 'argv', ['manage_container.py', 'stop']):
            try:
                mc.main()
            except SystemExit:
                pass
        mock_cmd_stop.assert_called_once()

    def test_restart_command_dispatches(self, mocker):
        mock_cmd_restart = mocker.patch.object(mc, 'cmd_restart')
        with patch.object(sys, 'argv', ['manage_container.py', 'restart']):
            try:
                mc.main()
            except SystemExit:
                pass
        mock_cmd_restart.assert_called_once()

    def test_logs_command_dispatches(self, mocker):
        mock_cmd_logs = mocker.patch.object(mc, 'cmd_logs')
        with patch.object(sys, 'argv', ['manage_container.py', 'logs']):
            try:
                mc.main()
            except SystemExit:
                pass
        mock_cmd_logs.assert_called_once()

    def test_remove_command_dispatches(self, mocker):
        mock_cmd_remove = mocker.patch.object(mc, 'cmd_remove')
        with patch.object(sys, 'argv', ['manage_container.py', 'remove']):
            try:
                mc.main()
            except SystemExit:
                pass
        mock_cmd_remove.assert_called_once()

    def test_test_command_dispatches(self, mocker):
        mock_cmd_test = mocker.patch.object(mc, 'cmd_test')
        with patch.object(sys, 'argv', ['manage_container.py', 'test']):
            try:
                mc.main()
            except SystemExit:
                pass
        mock_cmd_test.assert_called_once()

    def test_config_command_dispatches(self, mocker):
        mock_cmd_config = mocker.patch.object(mc, 'cmd_config')
        with patch.object(sys, 'argv', ['manage_container.py', 'config']):
            try:
                mc.main()
            except SystemExit:
                pass
        mock_cmd_config.assert_called_once()

    def test_start_yes_flag(self, mocker):
        mock_cmd_start = mocker.patch.object(mc, 'cmd_start')
        with patch.object(sys, 'argv', ['manage_container.py', 'start', '--yes']):
            try:
                mc.main()
            except SystemExit:
                pass
        mock_cmd_start.assert_called_once()
        args = mock_cmd_start.call_args[0][0]
        assert args.yes is True

    def test_logs_no_follow_flag(self, mocker):
        mock_cmd_logs = mocker.patch.object(mc, 'cmd_logs')
        with patch.object(sys, 'argv', ['manage_container.py', 'logs', '--no-follow']):
            try:
                mc.main()
            except SystemExit:
                pass
        mock_cmd_logs.assert_called_once()
        args = mock_cmd_logs.call_args[0][0]
        assert args.follow is False

    def test_remove_force_flag(self, mocker):
        mock_cmd_remove = mocker.patch.object(mc, 'cmd_remove')
        with patch.object(sys, 'argv', ['manage_container.py', 'remove', '--force']):
            try:
                mc.main()
            except SystemExit:
                pass
        mock_cmd_remove.assert_called_once()
        args = mock_cmd_remove.call_args[0][0]
        assert args.force is True

    def test_test_validator_flag(self, mocker):
        mock_cmd_test = mocker.patch.object(mc, 'cmd_test')
        with patch.object(sys, 'argv', ['manage_container.py', 'test', '--validator', 'mrproper-message']):
            try:
                mc.main()
            except SystemExit:
                pass
        mock_cmd_test.assert_called_once()
        args = mock_cmd_test.call_args[0][0]
        assert args.validator == 'mrproper-message'
