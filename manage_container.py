"""
MR Validator - Container Management Script

This script manages the Docker container lifecycle with beautiful CLI output,
configuration validation, and comprehensive error handling.

Compatible with Python 3.6+

Features:
- Docker container operations (build, start, stop, restart, logs, status, remove)
- Configuration display and validation from mrproper.env file
- Test webhook functionality (GitLab MR events)
- Rich terminal output with colors, tables, and progress bars

Exit Codes:
    0: Success
    1: General error
    2: Configuration error
    3: Docker error
    4: User cancelled operation

Testing:
    Run unit tests with: python -m pytest tests/test_manage_container.py -v
    Run with coverage: python -m pytest tests/test_manage_container.py --cov=. --cov-report=html

Usage:
    python manage_container.py --help
    python manage_container.py build
    python manage_container.py start
    python manage_container.py status
    python manage_container.py logs
"""

import sys
import os
import json
import argparse
import socket
import subprocess
import traceback
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import time
import requests

try:
    import docker
    from docker.errors import DockerException, ImageNotFound, NotFound, APIError
    from dotenv import dotenv_values
except ImportError as e:
    print(f"Error: Required package not found: {e}")
    print("Please install dependencies: pip install python-dotenv docker")
    sys.exit(1)

# Try to import rich, but make it optional for Python 3.6.0 compatibility
RICH_AVAILABLE = False
try:
    from rich.console import Console
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.prompt import Prompt
    RICH_AVAILABLE = True
except ImportError:
    # Rich not available - will use basic fallback
    pass


# Constants
ENV_FILE = "mrproper.env"
WEBHOOK_CONTAINER_NAME = "ratemymr-webhook-container"
WEBHOOK_IMAGE_NAME = "ratemymr-webhook-container"
CHECKER_IMAGE_NAME = "ratemymr-validate-container"
WEBHOOK_PORT = 9912  # Webhook server listens on this port

# Exit codes - These must remain in Python code (not in .env)
# They are used by sys.exit() to communicate process exit status to the shell
EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_CONFIG_ERROR = 2
EXIT_DOCKER_ERROR = 3
EXIT_CANCELLED = 4


# Simple console wrapper that works with or without rich
class SimpleConsole:
    """Fallback console for when rich is not available."""

    def print(self, *args, **kwargs):
        """Simple print that strips rich markup."""
        if len(args) == 1 and isinstance(args[0], SimpleTable):
            # Handle SimpleTable objects
            print(str(args[0]))
        else:
            message = ' '.join(str(arg) for arg in args)
            # Remove rich markup tags like [bold], [red], etc.
            import re
            message = re.sub(r'\[/?[a-z]+[^\]]*\]', '', message)
            print(message)


class SimpleTable:
    """Fallback table for when rich is not available."""

    def __init__(self, title="", **kwargs):
        self.title = title
        self.columns = []
        self.rows = []

    def add_column(self, name, **kwargs):
        """Add a column to the table."""
        self.columns.append(name)

    def add_row(self, *values):
        """Add a row to the table."""
        self.rows.append(values)

    def __str__(self):
        import re
        output = []

        # Helper function to strip rich markup
        def strip_markup(text):
            return re.sub(r'\[/?[a-z]+[^\]]*\]', '', str(text))

        if not self.rows:
            return ""

        # Calculate column widths based on stripped text
        col_widths = [len(strip_markup(col)) for col in self.columns]
        for row in self.rows:
            for i, val in enumerate(row):
                col_widths[i] = max(col_widths[i], len(strip_markup(val)))

        # Calculate total table width (columns + separators + padding)
        # Format: "col1 | col2 | col3" so separators are " | " (3 chars each)
        total_width = sum(col_widths) + (len(col_widths) - 1) * 3

        # Add title if present (centered)
        if self.title:
            title_stripped = strip_markup(self.title)
            title_padding = (total_width - len(title_stripped)) // 2
            output.append("")
            output.append(" " * title_padding + title_stripped)

        # Top border
        output.append("-" * total_width)

        # Header row
        header = " | ".join(strip_markup(col).ljust(col_widths[i]) for i, col in enumerate(self.columns))
        output.append(header)

        # Header separator
        output.append("-" * total_width)

        # Data rows with stripped markup
        for row in self.rows:
            row_str = " | ".join(strip_markup(val).ljust(col_widths[i]) for i, val in enumerate(row))
            output.append(row_str)

        # Empty line after table for spacing
        output.append("")

        return "\n".join(output)


class SimpleProgress:
    """Fallback progress for when rich is not available."""

    def __init__(self, *args, **kwargs):
        self.tasks = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def add_task(self, description, **kwargs):
        """Add a task to the progress tracker."""
        print(f"  {description}")
        return len(self.tasks)

    def update(self, task_id, **kwargs):
        """Update a task's progress."""
        pass


class SimplePrompt:
    """Fallback prompt for when rich is not available."""

    @staticmethod
    def ask(prompt, choices=None, default=None):
        """Simple input prompt with choices validation."""
        while True:
            if choices:
                prompt_text = f"{prompt} ({'/'.join(choices)})"
                if default:
                    prompt_text += f" [{default}]"
                prompt_text += ": "
            else:
                prompt_text = f"{prompt}: "

            response = input(prompt_text).strip()

            if not response and default:
                return default

            if choices is None or response in choices:
                return response

            print(f"Invalid choice. Please select from: {', '.join(choices)}")


# Initialize console (rich or simple fallback)
if RICH_AVAILABLE:
    console = Console()
else:
    # Dummy classes for Progress columns (only needed in simple mode)
    class SpinnerColumn:  # noqa: F811
        """Dummy spinner column for simple mode."""
        pass

    class TextColumn:  # noqa: F811
        """Dummy text column for simple mode."""
        def __init__(self, *args, **kwargs):
            pass

    console = SimpleConsole()
    Table = SimpleTable  # noqa: F811
    Progress = SimpleProgress  # noqa: F811
    Prompt = SimplePrompt  # noqa: F811
    print("Note: Running in basic mode (rich library not available)")
    print("For enhanced output, upgrade to Python 3.6.1+ and install rich==12.6.0\n")


# Configuration Management
def format_bytes(bytes_val: int) -> str:
    """
    Format bytes to human-readable size.

    Args:
        bytes_val: Size in bytes

    Returns:
        Formatted string (e.g., "1.2 GB")
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_val < 1024.0:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.1f} PB"


def mask_value(value: Optional[str], show_chars: int = 8) -> str:
    """
    Mask sensitive values, showing only first N characters.

    Args:
        value: The value to mask
        show_chars: Number of characters to show before masking

    Returns:
        Masked string (e.g., "glpat-ab****")
    """
    if not value or value == "Not Set":
        return "[dim]Not Set[/dim]"
    if len(value) <= show_chars:
        return "****"
    return f"{value[:show_chars]}****"


def create_config_table(title: str):
    """
    Create a standardized configuration table with consistent styling.

    Args:
        title: Table title

    Returns:
        Configured Rich Table or SimpleTable ready for adding rows
    """
    if RICH_AVAILABLE:
        table = Table(title=title, show_header=True, header_style="bold cyan")
        table.add_column("Setting", style="yellow", width=30)
        table.add_column("Value", style="green")
    else:
        table = SimpleTable(title=title)
        table.add_column("Setting")
        table.add_column("Value")
    return table


def get_host_ip() -> str:
    """Get the local IP address of the host machine."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(('8.8.8.8', 80))
            return s.getsockname()[0]
    except Exception:
        return '127.0.0.1'


def load_config(env_file: Path = Path(ENV_FILE)) -> Optional[Dict[str, str]]:
    """
    Load configuration from mrproper.env file.

    Args:
        env_file: Path to mrproper.env file

    Returns:
        Dictionary of configuration values, or None if file doesn't exist
    """
    if not env_file.exists():
        return None

    # Load from mrproper.env file
    config = dotenv_values(env_file)

    return config


def validate_required_fields(config: Dict[str, str]) -> Tuple[List[str], List[str]]:
    """Validate required configuration fields."""
    errors = []
    warnings = []

    if not config.get('GITLAB_ACCESS_TOKEN'):
        errors.append("GITLAB_ACCESS_TOKEN is not set (required)")

    return errors, warnings


def _validate_log_level(config: Dict[str, str], errors: List[str]) -> None:
    """Validate LOG_LEVEL setting."""
    valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
    if config.get('LOG_LEVEL'):
        log_level = config.get('LOG_LEVEL').upper()
        if log_level not in valid_levels:
            errors.append(f"LOG_LEVEL '{log_level}' is invalid (must be one of: {', '.join(valid_levels)})")


def validate_logging_config(config: Dict[str, str]) -> Tuple[List[str], List[str]]:
    """Validate logging configuration."""
    errors = []
    warnings = []

    _validate_log_level(config, errors)

    # Log output directory validation
    if config.get('LOG_DIR'):
        log_dir = Path(config.get('LOG_DIR'))
        # Only check if directory exists - if not, it will be created on start (no warning needed)
        if log_dir.exists() and not os.access(log_dir, os.W_OK):
            errors.append(f"Log directory '{log_dir}' is not writable")

    return errors, warnings


def validate_ai_config(config: Dict[str, str]) -> Tuple[List[str], List[str]]:
    """Validate AI/LLM service configuration."""
    errors = []
    warnings = []

    bfa_host = config.get('BFA_HOST', '').strip()
    ai_service_url = config.get('AI_SERVICE_URL', '').strip()

    if not bfa_host and not ai_service_url:
        warnings.append("Neither BFA_HOST nor AI_SERVICE_URL is set - AI features will not work")
    elif bfa_host and ai_service_url:
        warnings.append("Both BFA_HOST and AI_SERVICE_URL are set - BFA_HOST will take precedence")

    if ai_service_url and not ai_service_url.startswith(('http://', 'https://')):
        warnings.append("AI_SERVICE_URL should start with http:// or https://")

    try:
        timeout = int(config.get('API_TIMEOUT', '120'))
        if timeout < 30:
            warnings.append("API_TIMEOUT is very low (<30s), AI calls may timeout")
        elif timeout > 300:
            warnings.append("API_TIMEOUT is very high (>300s), consider reducing it")
    except ValueError:
        errors.append(f"API_TIMEOUT '{config.get('API_TIMEOUT')}' is not a valid number")

    return errors, warnings


def validate_system_resources(config: Dict[str, str]) -> Tuple[List[str], List[str]]:
    """Validate system resources (disk space, permissions)."""
    errors = []
    warnings = []

    # Check disk space
    try:
        import shutil
        stat = shutil.disk_usage(Path.cwd())
        gb_free = stat.free / (1024 ** 3)
        if gb_free < 1:
            warnings.append(f"Low disk space: Only {gb_free:.1f} GB available")
        elif gb_free < 5:
            warnings.append(f"Disk space is getting low: {gb_free:.1f} GB available")
    except Exception:
        pass

    # Check mrproper.env file permissions
    env_file = Path(ENV_FILE)
    if env_file.exists():
        try:
            st = env_file.stat()
            perms = oct(st.st_mode)[-3:]
            if perms not in ['600', '400']:
                warnings.append(f"{ENV_FILE} has insecure permissions ({perms}), consider setting to 600 or 400")
        except Exception:
            pass

    return errors, warnings


def validate_config(config: Dict[str, str]) -> Tuple[List[str], List[str]]:
    """
    Validate configuration with comprehensive checks.

    Args:
        config: Configuration dictionary

    Returns:
        Tuple of (errors, warnings) lists
    """
    all_errors, all_warnings = [], []

    # Run all validation functions
    validators = [
        validate_required_fields,
        validate_logging_config,
        validate_ai_config,
        validate_system_resources
    ]

    for validator in validators:
        errors, warnings = validator(config)
        all_errors.extend(errors)
        all_warnings.extend(warnings)

    return all_errors, all_warnings


def get_disk_space(path: Path) -> Tuple[str, str, float]:
    """
    Get available and total disk space.

    Args:
        path: Path to check

    Returns:
        Tuple of (available, total, percent_used)
    """
    try:
        import shutil
        stat = shutil.disk_usage(path)

        available = format_bytes(stat.free)
        total = format_bytes(stat.total)
        percent_used = (stat.used / stat.total) * 100

        return available, total, percent_used
    except Exception:
        return "Unknown", "Unknown", 0.0


def check_file_permissions(file_path: Path) -> Tuple[str, bool]:
    """
    Check file permissions.

    Args:
        file_path: Path to file

    Returns:
        Tuple of (permissions_string, is_secure)
    """
    try:
        st = file_path.stat()
        mode = st.st_mode

        # Get octal permissions (e.g., 0o600)
        perms = oct(mode)[-3:]

        # Check if secure (600 or 400)
        is_secure = perms in ['600', '400']

        return perms, is_secure
    except Exception:
        return "Unknown", False


def show_config_table(config: Dict[str, str], quiet: bool = False) -> None:
    """
    Display configuration in formatted tables using Rich.

    Args:
        config: Configuration dictionary
        quiet: If True, show minimal output
    """
    if quiet:
        return

    # Environment Configuration
    env_table = create_config_table("Configuration Review")
    env_table.add_row("GitLab Access Token", mask_value(config.get('GITLAB_ACCESS_TOKEN', 'Not Set'), 12))

    # AI/LLM Service Configuration
    bfa_host = config.get('BFA_HOST', '').strip()
    ai_service_url = config.get('AI_SERVICE_URL', '').strip()

    if bfa_host:
        env_table.add_row("AI Mode", "[bold green]BFA (JWT Auth)[/bold green]")
        env_table.add_row("BFA Host", bfa_host)
        bfa_token = config.get('BFA_TOKEN_KEY')
        if bfa_token:
            env_table.add_row("BFA Token (Pre-configured)", mask_value(bfa_token, 12))
    elif ai_service_url:
        env_table.add_row("AI Mode", "[bold yellow]Legacy (Direct)[/bold yellow]")
        env_table.add_row("AI Service URL", ai_service_url)
    else:
        env_table.add_row("AI Mode", "[bold red]Not Configured[/bold red]")

    env_table.add_row("API Timeout", f"{config.get('API_TIMEOUT', '120')}s")
    env_table.add_row("Log Directory", config.get('LOG_DIR', '[dim]Not Set[/dim]'))
    env_table.add_row("Log Level", config.get('LOG_LEVEL', '[dim]Not Set[/dim]'))
    env_table.add_row("Log Structure", config.get('LOG_STRUCTURE', 'organized'))
    console.print(env_table)
    console.print()

    # Container Configuration
    container_table = create_config_table("Container Settings")
    container_table.add_row("Webhook Container", WEBHOOK_CONTAINER_NAME)
    container_table.add_row("Webhook Image", WEBHOOK_IMAGE_NAME)
    container_table.add_row("Checker Image", CHECKER_IMAGE_NAME)
    container_table.add_row("Webhook Port", str(WEBHOOK_PORT))
    console.print(container_table)
    console.print()

    # System Information
    system_table = create_config_table("System Information")

    available, total, percent_used = get_disk_space(Path.cwd())
    disk_color = "green" if percent_used < 80 else ("yellow" if percent_used < 90 else "red")
    disk_info = (
        f"[{disk_color}]{available} / {total} ({percent_used:.1f}% used)[/{disk_color}]"
    )
    system_table.add_row("Disk Available", disk_info)

    env_file = Path(ENV_FILE)
    if env_file.exists():
        perms, is_secure = check_file_permissions(env_file)
        perm_color = "green" if is_secure else "yellow"
        perm_text = f"[{perm_color}]{perms}[/{perm_color}]"
        if not is_secure:
            perm_text += " [yellow](consider 600 or 400)[/yellow]"
        system_table.add_row(f"{ENV_FILE} Permissions", perm_text)

    console.print(system_table)
    console.print()


def show_validation_results(errors: List[str], warnings: List[str]) -> None:
    """
    Display validation errors and warnings using Rich.

    Args:
        errors: List of error messages
        warnings: List of warning messages
    """
    if errors:
        console.print("\n[bold red][X] ERRORS (must be fixed):[/bold red]")
        for error in errors:
            console.print(f"   - {error}", style="red")
        console.print()

    if warnings:
        console.print("[bold yellow]!  WARNINGS:[/bold yellow]")
        for warning in warnings:
            console.print(f"   - {warning}", style="yellow")
        console.print()


def confirm_action(message: str = "Continue with this configuration?", auto_yes: bool = False) -> bool:
    """
    Ask user for confirmation.

    Args:
        message: Confirmation message to display
        auto_yes: If True, auto-confirm without prompting

    Returns:
        True if user confirmed, False otherwise
    """
    if auto_yes:
        console.print("[OK] Auto-confirmed (--yes flag)", style="green")
        return True

    while True:
        try:
            response = input(f"{message} (y/N): ").strip().lower()
            if response in ['y', 'yes']:
                return True
            elif response in ['n', 'no', '']:
                return False
            else:
                console.print("[yellow]Please enter 'y' or 'n'[/yellow]")
        except (KeyboardInterrupt, EOFError):
            console.print("\n")
            return False


# Docker Operations
def get_docker_client() -> Optional[docker.DockerClient]:
    """
    Get Docker client, return None if Docker is not available.

    Returns:
        Docker client or None
    """
    try:
        client = docker.from_env()
        client.ping()  # Test connection
        return client
    except DockerException as e:
        console.print(f"[bold red][X] Docker Error:[/bold red] {str(e)}", style="red")
        console.print("\nPlease ensure Docker is installed and running.")
        return None


def build_images(client: docker.DockerClient) -> bool:
    """
    Build both Docker images (webhook server and checker).

    Args:
        client: Docker client

    Returns:
        True if successful, False otherwise
    """
    try:
        console.print("[bold blue]Building Docker images...[/bold blue]\n")

        # Build webhook server image
        console.print(f"[blue]Building webhook server image:[/blue] {WEBHOOK_IMAGE_NAME}")
        webhook_result = subprocess.run(
            ['docker', 'build', '-t', WEBHOOK_IMAGE_NAME, 'webhook-server'],
            capture_output=True,
            text=True
        )

        if webhook_result.returncode != 0:
            console.print(f"[bold red][X] Failed to build {WEBHOOK_IMAGE_NAME}[/bold red]")
            console.print(webhook_result.stderr)
            return False

        console.print(f"[bold green][OK] Built {WEBHOOK_IMAGE_NAME}[/bold green]\n")

        # Build checker image
        console.print(f"[blue]Building checker image:[/blue] {CHECKER_IMAGE_NAME}")
        checker_result = subprocess.run(
            ['docker', 'build', '-t', CHECKER_IMAGE_NAME, 'mrproper'],
            capture_output=True,
            text=True
        )

        if checker_result.returncode != 0:
            console.print(f"[bold red][X] Failed to build {CHECKER_IMAGE_NAME}[/bold red]")
            console.print(checker_result.stderr)
            return False

        console.print(f"[bold green][OK] Built {CHECKER_IMAGE_NAME}[/bold green]\n")
        console.print("[bold green]SUCCESS: All images built successfully![/bold green]")
        return True

    except Exception as e:
        console.print(f"[bold red][X] Build error:[/bold red] {str(e)}")
        return False


def container_exists(client: docker.DockerClient) -> bool:
    """
    Check if container exists.

    Args:
        client: Docker client

    Returns:
        True if container exists, False otherwise
    """
    try:
        client.containers.get(WEBHOOK_CONTAINER_NAME)
        return True
    except NotFound:
        return False


def container_running(client: docker.DockerClient) -> bool:
    """
    Check if container is running.

    Args:
        client: Docker client

    Returns:
        True if container is running, False otherwise
    """
    try:
        container = client.containers.get(WEBHOOK_CONTAINER_NAME)
        return container.status == 'running'
    except NotFound:
        return False


def start_container(client: docker.DockerClient, config: Dict[str, str], skip_confirm: bool = False) -> bool:
    """
    Start container (create if needed).

    Args:
        client: Docker client
        config: Configuration dictionary
        skip_confirm: Skip confirmation prompt

    Returns:
        True if successful, False otherwise
    """
    try:
        if container_exists(client):
            if container_running(client):
                console.print("[yellow]!  Container is already running. Use 'restart' to restart it.[/yellow]")
                return True
            console.print(f"[blue]Starting existing container: {WEBHOOK_CONTAINER_NAME}[/blue]")
            client.containers.get(WEBHOOK_CONTAINER_NAME).start()
            console.print("[bold green][OK] Container started![/bold green]")
            console.print(f"[dim]Shell equivalent: docker start {WEBHOOK_CONTAINER_NAME}[/dim]\n")
            show_endpoints()
            return True

        console.print(f"[bold blue]Starting new container: {WEBHOOK_CONTAINER_NAME} (port {WEBHOOK_PORT})[/bold blue]")

        # Build volumes dictionary with absolute paths
        env_path = Path.cwd() / ENV_FILE
        volumes = {
            '/var/run/docker.sock': {'bind': '/var/run/docker.sock', 'mode': 'rw'},
            str(env_path.absolute()): {'bind': f'/srv/{ENV_FILE}', 'mode': 'ro'}
        }

        # Start container
        client.containers.run(
            f"{WEBHOOK_IMAGE_NAME}:latest",
            name=WEBHOOK_CONTAINER_NAME,
            detach=True,
            ports={f'{WEBHOOK_PORT}/tcp': WEBHOOK_PORT},
            volumes=volumes,
            restart_policy={"Name": "unless-stopped"},
            environment={k: v for k, v in config.items()}
        )
        console.print("[bold green][OK] Container started successfully![/bold green]")

        # Show shell equivalent
        shell_cmd = (
            f"docker run -d --name {WEBHOOK_CONTAINER_NAME} "
            f"-p {WEBHOOK_PORT}:{WEBHOOK_PORT} "
            f"-v /var/run/docker.sock:/var/run/docker.sock:rw "
            f"-v {env_path.absolute()}:/srv/{ENV_FILE}:ro "
            f"--restart unless-stopped "
            f"--env-file {ENV_FILE} "
            f"{WEBHOOK_IMAGE_NAME}:latest"
        )
        console.print("[dim]Shell equivalent:[/dim]")
        console.print(f"[dim]{shell_cmd}[/dim]\n")

        show_endpoints()
        return True
    except ImageNotFound:
        console.print(f"[bold red][X] Image '{WEBHOOK_IMAGE_NAME}:latest' not found. Run 'build' command first.[/bold red]")
        return False
    except APIError as e:
        console.print(f"[bold red][X] Failed to start container: {str(e)}[/bold red]")
        return False


def show_endpoints(host: Optional[str] = None) -> None:
    """
    Display service endpoints.

    Args:
        host: Host IP address (defaults to auto-detected IP)
    """
    if host is None:
        host = get_host_ip()

    endpoints_table = Table(show_header=True, header_style="bold cyan")
    endpoints_table.add_column("Endpoint", style="yellow")
    endpoints_table.add_column("URL", style="green")

    endpoints_table.add_row("Rate My MR", f"http://{host}:{WEBHOOK_PORT}/mr-proper/rate-my-mr")
    endpoints_table.add_row("Clang Format", f"http://{host}:{WEBHOOK_PORT}/mr-proper/mrproper-clang-format")
    endpoints_table.add_row("Message Check", f"http://{host}:{WEBHOOK_PORT}/mr-proper/mrproper-message")
    endpoints_table.add_row("Combined", f"http://{host}:{WEBHOOK_PORT}/mr-proper/rate-my-mr+mrproper-message")

    console.print(endpoints_table)


def stop_container(client: docker.DockerClient) -> bool:
    """
    Stop container.

    Args:
        client: Docker client

    Returns:
        True if successful, False otherwise
    """
    try:
        if not container_running(client):
            console.print("[yellow]!  Container is not running.[/yellow]")
            return True

        console.print(f"[blue]Stopping container:[/blue] {WEBHOOK_CONTAINER_NAME}")
        container = client.containers.get(WEBHOOK_CONTAINER_NAME)
        container.stop()
        console.print("[bold green][OK] Container stopped![/bold green]")
        console.print(f"[dim]Shell equivalent: docker stop {WEBHOOK_CONTAINER_NAME}[/dim]")
        return True

    except NotFound:
        console.print(f"[yellow]!  Container '{WEBHOOK_CONTAINER_NAME}' does not exist.[/yellow]")
        return True
    except APIError as e:
        console.print(f"[bold red][X] Failed to stop container:[/bold red] {str(e)}", style="red")
        return False


def restart_container(client: docker.DockerClient, config: Dict[str, str]) -> bool:
    """
    Restart container. Container must exist and be running.

    Args:
        client: Docker client
        config: Configuration dictionary

    Returns:
        True if successful, False otherwise
    """
    # Check if container exists first
    if not container_exists(client):
        console.print(f"[bold red][X] Container '{WEBHOOK_CONTAINER_NAME}' does not exist.[/bold red]")
        console.print("[yellow]Use 'start' command to create and start the container.[/yellow]")
        return False

    # Check if container is running
    if not container_running(client):
        console.print("[yellow]!  Container exists but is not running.[/yellow]")
        console.print("[yellow]Use 'start' command to start it.[/yellow]")
        return False

    console.print(f"[bold blue]Restarting container:[/bold blue] {WEBHOOK_CONTAINER_NAME}")
    console.print(f"[dim]Shell equivalent: docker restart {WEBHOOK_CONTAINER_NAME}[/dim]\n")

    if not stop_container(client):
        return False

    time.sleep(2)

    return start_container(client, config, skip_confirm=True)


def show_logs(client: docker.DockerClient, follow: bool = True) -> bool:
    """
    Show container logs.

    Args:
        client: Docker client
        follow: If True, follow logs in real-time

    Returns:
        True if successful, False otherwise
    """
    try:
        if not container_exists(client):
            console.print(f"[bold red][X] Container '{WEBHOOK_CONTAINER_NAME}' does not exist.[/bold red]")
            return False

        console.print(f"[blue]Showing logs for:[/blue] {WEBHOOK_CONTAINER_NAME}")
        if follow:
            console.print("[dim]Press Ctrl+C to exit[/dim]")
            console.print(f"[dim]Shell equivalent: docker logs -f {WEBHOOK_CONTAINER_NAME}[/dim]\n")
        else:
            console.print(f"[dim]Shell equivalent: docker logs {WEBHOOK_CONTAINER_NAME}[/dim]\n")

        container = client.containers.get(WEBHOOK_CONTAINER_NAME)

        if follow:
            try:
                for line in container.logs(stream=True, follow=True):
                    console.print(line.decode('utf-8'), end='')
            except KeyboardInterrupt:
                console.print("\n[yellow]Stopped following logs.[/yellow]")
                return True
        else:
            logs = container.logs().decode('utf-8')
            console.print(logs)

        return True

    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped following logs.[/yellow]")
        return True
    except NotFound:
        console.print(f"[bold red][X] Container '{WEBHOOK_CONTAINER_NAME}' not found.[/bold red]")
        return False
    except APIError as e:
        console.print(f"[bold red][X] Failed to get logs:[/bold red] {str(e)}", style="red")
        return False


def show_status(client: docker.DockerClient) -> bool:
    """
    Show container status and resource usage.

    Args:
        client: Docker client

    Returns:
        True if successful, False otherwise
    """
    console.print("[bold blue]Container Status:[/bold blue]\n")
    if not container_exists(client):
        console.print("[yellow]!  Container does not exist. Use 'start' command to create it.[/yellow]")
        return True

    try:
        container = client.containers.get(WEBHOOK_CONTAINER_NAME)
        if container.status == 'running':
            console.print("[bold green][OK] Container is RUNNING[/bold green]\n")

            info_table = Table(show_header=True, header_style="bold cyan")
            info_table.add_column("Property", style="yellow")
            info_table.add_column("Value", style="green")
            info_table.add_row("Container Name", container.name)
            info_table.add_row("Container ID", container.short_id)
            info_table.add_row("Status", container.status)
            info_table.add_row("Created", container.attrs['Created'][:19])

            from datetime import datetime, timezone
            import re
            started_at = container.attrs['State'].get('StartedAt')
            if started_at:
                # Python 3.6 compatible: Manual ISO format parsing instead of fromisoformat()
                started_at = re.sub(r'(\.\d{6})\d+', r'\1', started_at)
                # Parse ISO 8601 format manually for Python 3.6 compatibility
                datetime_str = started_at.replace('Z', '').replace('+00:00', '').replace('-00:00', '')
                try:
                    if '.' in datetime_str:
                        start_time = datetime.strptime(datetime_str, '%Y-%m-%dT%H:%M:%S.%f')
                    else:
                        start_time = datetime.strptime(datetime_str, '%Y-%m-%dT%H:%M:%S')
                    start_time = start_time.replace(tzinfo=timezone.utc)
                except ValueError:
                    start_time = datetime.now(timezone.utc)
                uptime = datetime.now(timezone.utc) - start_time
                days, hours = uptime.days, uptime.seconds // 3600
                minutes = (uptime.seconds % 3600) // 60
                if days > 0:
                    uptime_str = f"{days}d {hours}h {minutes}m"
                elif hours > 0:
                    uptime_str = f"{hours}h {minutes}m"
                else:
                    uptime_str = f"{minutes}m"
                info_table.add_row("Uptime", uptime_str)

            ports = container.attrs.get('NetworkSettings', {}).get('Ports', {})
            port_str = ", ".join([f"{k} -> {v[0]['HostPort']}" for k, v in ports.items() if v])
            info_table.add_row("Ports", port_str if port_str else "None")
            console.print(info_table)
            console.print()

            try:
                stats = container.stats(stream=False)
                cpu_total = stats['cpu_stats']['cpu_usage']['total_usage']
                precpu_total = stats['precpu_stats']['cpu_usage']['total_usage']
                cpu_delta = cpu_total - precpu_total
                system_current = stats['cpu_stats']['system_cpu_usage']
                system_previous = stats['precpu_stats']['system_cpu_usage']
                system_delta = system_current - system_previous
                if system_delta > 0 and cpu_delta > 0:
                    online_cpus = stats['cpu_stats'].get('online_cpus', 1)
                    cpu_percent = (cpu_delta / system_delta) * online_cpus * 100.0
                else:
                    cpu_percent = 0.0
                mem_usage = stats['memory_stats'].get('usage', 0) / (1024 * 1024)
                mem_limit = stats['memory_stats'].get('limit', 0) / (1024 * 1024)

                resource_table = Table(show_header=True, header_style="bold cyan")
                resource_table.add_column("Resource", style="yellow")
                resource_table.add_column("Usage", style="green")
                resource_table.add_row("CPU", f"{cpu_percent:.2f}%")
                resource_table.add_row("Memory", f"{mem_usage:.1f} MB / {mem_limit:.1f} MB")
                console.print(resource_table)
                console.print()
            except Exception as e:
                console.print(f"[yellow]!  Could not fetch resource usage: {str(e)}[/yellow]")

            try:
                logs = container.logs(tail=100, timestamps=True).decode('utf-8', errors='ignore')
                error_lines = [
                    line[:97] + '...' if len(line) > 100 else line
                    for line in logs.split('\n')
                    if any(p in line.lower() for p in ['error', 'critical', 'exception', 'traceback', 'failed'])
                ]

                if error_lines:
                    console.print("[bold yellow]Recent Errors (last 100 log lines):[/bold yellow]")
                    for error_line in error_lines[-5:]:
                        console.print(f"[red]  {error_line}[/red]")
                    if len(error_lines) > 5:
                        console.print(f"[yellow]  ... and {len(error_lines) - 5} more errors[/yellow]")
                    console.print()
                else:
                    console.print("[green][OK] No recent errors found[/green]\n")
            except Exception as e:
                console.print(f"[yellow]!  Could not fetch recent logs: {str(e)}[/yellow]\n")
        else:
            console.print(f"[yellow]!  Container exists but is NOT RUNNING (Status: {container.status})[/yellow]")
            console.print("Use 'start' command to start it.")
        return True
    except NotFound:
        console.print(f"[bold red][X] Container '{WEBHOOK_CONTAINER_NAME}' not found.[/bold red]")
        return False
    except APIError as e:
        console.print(f"[bold red][X] Failed to get status:[/bold red] {str(e)}", style="red")
        return False


def remove_container(
    client: docker.DockerClient,
    force: bool = False,
    force_remove: bool = False
) -> bool:
    """
    Remove container and optionally images with user confirmation.

    Args:
        client: Docker client
        force: If True, skip confirmation
        force_remove: If True, force remove even if container is running/restarting

    Returns:
        True if successful, False otherwise
    """
    try:
        # Check what exists
        container_exists_flag = container_exists(client)

        try:
            client.images.get(f"{WEBHOOK_IMAGE_NAME}:latest")
            webhook_image_exists = True
        except ImageNotFound:
            webhook_image_exists = False

        try:
            client.images.get(f"{CHECKER_IMAGE_NAME}:latest")
            checker_image_exists = True
        except ImageNotFound:
            checker_image_exists = False

        if not container_exists_flag and not webhook_image_exists and not checker_image_exists:
            console.print("[yellow]!  Neither container nor images exist.[/yellow]")
            return True

        # Get user confirmation
        remove_images = False
        if not force:
            console.print("[bold yellow]What would you like to remove?[/bold yellow]")

            if container_exists_flag and (webhook_image_exists or checker_image_exists):
                console.print(
                    "[cyan]1.[/cyan] Container only\n"
                    "[cyan]2.[/cyan] Container and images\n"
                    "[cyan]3.[/cyan] Cancel"
                )
                choice = Prompt.ask("Select option", choices=["1", "2", "3"], default="3")
                if choice == "3":
                    console.print("[blue]Cancelled.[/blue]")
                    return False
                remove_images = (choice == "2")
            elif container_exists_flag:
                if not confirm_action("Remove container?", False):
                    console.print("[blue]Cancelled.[/blue]")
                    return False
            elif webhook_image_exists or checker_image_exists:
                if not confirm_action("Remove images?", False):
                    console.print("[blue]Cancelled.[/blue]")
                    return False
                remove_images = True

        # Remove container if exists
        if container_exists_flag:
            console.print(f"[blue]Removing container: {WEBHOOK_CONTAINER_NAME}[/blue]")
            container = client.containers.get(WEBHOOK_CONTAINER_NAME)

            if not force_remove and container.status in ['running', 'restarting']:
                try:
                    console.print("[blue]Stopping container first...[/blue]")
                    container.stop(timeout=10)
                    console.print(f"[dim]Shell equivalent: docker stop {WEBHOOK_CONTAINER_NAME}[/dim]")
                except Exception as e:
                    console.print(
                        f"[yellow]!  Could not stop: {e}. Attempting force removal...[/yellow]"
                    )
                    force_remove = True

            container.remove(force=force_remove)
            console.print("[bold green][OK] Container removed![/bold green]")

            if force_remove:
                console.print(f"[dim]Shell equivalent: docker rm -f {WEBHOOK_CONTAINER_NAME}[/dim]")
            else:
                console.print(f"[dim]Shell equivalent: docker rm {WEBHOOK_CONTAINER_NAME}[/dim]")

        # Remove images if requested and exist
        if remove_images:
            if webhook_image_exists:
                console.print(f"[blue]Removing image: {WEBHOOK_IMAGE_NAME}:latest[/blue]")
                try:
                    client.images.remove(f"{WEBHOOK_IMAGE_NAME}:latest", force=force_remove)
                    console.print("[bold green][OK] Webhook image removed![/bold green]")
                except APIError as e:
                    console.print(f"[bold red][X] Failed to remove webhook image: {str(e)}[/bold red]")

            if checker_image_exists:
                console.print(f"[blue]Removing image: {CHECKER_IMAGE_NAME}:latest[/blue]")
                try:
                    client.images.remove(f"{CHECKER_IMAGE_NAME}:latest", force=force_remove)
                    console.print("[bold green][OK] Checker image removed![/bold green]")
                except APIError as e:
                    console.print(f"[bold red][X] Failed to remove checker image: {str(e)}[/bold red]")

        return True

    except NotFound:
        console.print(f"[yellow]!  Container '{WEBHOOK_CONTAINER_NAME}' does not exist.[/yellow]")
        return True
    except APIError as e:
        console.print(f"[bold red][X] Failed to remove: {str(e)}[/bold red]")
        console.print("[yellow][TIP] Tip: Try --force-remove flag[/yellow]")
        return False


# Testing Operations
def test_webhook(target: str = 'rate-my-mr') -> bool:
    """
    Send test webhook to container.

    Args:
        target: Validator to test ('rate-my-mr', 'mrproper-message', etc.)

    Returns:
        True if successful, False otherwise
    """
    try:
        host = get_host_ip()

        console.print(f"[blue]Testing {target} endpoint with sample payload...[/blue]")
        console.print(f"[blue]Target:[/blue] http://{host}:{WEBHOOK_PORT}/mr-proper/{target}\n")

        # Sample GitLab MR webhook payload
        sample_payload = {
            "object_kind": "merge_request",
            "user": {
                "username": "test-user"
            },
            "project": {
                "path_with_namespace": "test-org/test-repo"
            },
            "object_attributes": {
                "iid": 42,
                "title": "Test MR: Add new feature",
                "source_branch": "feature/test",
                "target_branch": "main",
                "state": "opened",
                "action": "open"
            },
            "changes": {}
        }

        response = requests.post(
            f"http://{host}:{WEBHOOK_PORT}/mr-proper/{target}",
            json=sample_payload,
            headers={
                "Content-Type": "application/json",
                "X-Gitlab-Event": "Merge Request Hook"
            },
            timeout=30
        )

        response.raise_for_status()

        console.print("[bold green][OK] Test webhook sent successfully![/bold green]")
        console.print(f"\n[bold]Response status:[/bold] {response.status_code}")
        console.print(f"\n[dim]Check logs with: python manage_container.py logs[/dim]")
        console.print(f"[dim]Check validator logs at: {os.environ.get('LOG_DIR', '/home/docker/tmp/mr-validator-logs')}[/dim]")

        return True

    except Exception as e:
        console.print(f"[bold red][X] Failed to send test webhook:[/bold red] {str(e)}", style="red")
        return False


# CLI Commands (argparse)
def cmd_config(args):
    """Display and validate configuration from mrproper.env file."""

    # Load configuration
    cfg = load_config(Path(args.env_file))
    if cfg is None:
        console.print(f"[bold red][X] Configuration file not found: {args.env_file}[/bold red]")
        console.print(f"Please create {args.env_file} from .env.example:")
        console.print(f"  cp .env.example {args.env_file}")
        sys.exit(EXIT_CONFIG_ERROR)

    # Display configuration
    if not args.quiet:
        show_config_table(cfg, args.quiet)

    # Validate
    errors, warnings = validate_config(cfg)
    show_validation_results(errors, warnings)

    # Exit on errors
    if errors:
        console.print("[bold red][X] Configuration has critical errors. Please fix mrproper.env file.[/bold red]")
        sys.exit(EXIT_CONFIG_ERROR)

    if args.validate_only:
        if warnings:
            console.print("[bold green][OK] Configuration is valid (but has warnings)[/bold green]")
        else:
            console.print("[bold green][OK] Configuration is valid[/bold green]")

    sys.exit(EXIT_SUCCESS)


def cmd_build(args):
    """Build the Docker images."""

    client = get_docker_client()
    if not client:
        sys.exit(EXIT_DOCKER_ERROR)

    success = build_images(client)
    sys.exit(EXIT_SUCCESS if success else EXIT_DOCKER_ERROR)


def cmd_start(args):
    """Start the container (creates if needed)."""

    # Check mrproper.env file
    if not Path(ENV_FILE).exists():
        console.print(f"[bold red][X] Configuration file not found: {ENV_FILE}[/bold red]")
        console.print(f"Please create {ENV_FILE} from .env.example:")
        console.print(f"  cp .env.example {ENV_FILE}")
        sys.exit(EXIT_CONFIG_ERROR)

    # Load and validate configuration
    cfg = load_config()
    if cfg is None:
        sys.exit(EXIT_CONFIG_ERROR)

    # Display configuration
    show_config_table(cfg)

    # Validate
    errors, warnings = validate_config(cfg)
    show_validation_results(errors, warnings)

    if errors:
        console.print("[bold red][X] Configuration has critical errors. Please fix mrproper.env file.[/bold red]")
        sys.exit(EXIT_CONFIG_ERROR)

    # Confirm
    if not confirm_action("Continue with this configuration?", args.yes):
        console.print("[blue]Cancelled by user.[/blue]")
        sys.exit(EXIT_CANCELLED)

    # Start container
    client = get_docker_client()
    if not client:
        sys.exit(EXIT_DOCKER_ERROR)

    success = start_container(client, cfg, skip_confirm=args.yes)
    sys.exit(EXIT_SUCCESS if success else EXIT_DOCKER_ERROR)


def cmd_stop(args):
    """Stop the container."""

    client = get_docker_client()
    if not client:
        sys.exit(EXIT_DOCKER_ERROR)

    success = stop_container(client)
    sys.exit(EXIT_SUCCESS if success else EXIT_DOCKER_ERROR)


def cmd_restart(args):
    """Restart the container."""

    # Load config
    cfg = load_config()
    if cfg is None:
        console.print(f"[bold red][X] Configuration file not found: {ENV_FILE}[/bold red]")
        sys.exit(EXIT_CONFIG_ERROR)

    client = get_docker_client()
    if not client:
        sys.exit(EXIT_DOCKER_ERROR)

    success = restart_container(client, cfg)
    sys.exit(EXIT_SUCCESS if success else EXIT_DOCKER_ERROR)


def cmd_logs(args):
    """View container logs."""

    client = get_docker_client()
    if not client:
        sys.exit(EXIT_DOCKER_ERROR)

    success = show_logs(client, args.follow)
    sys.exit(EXIT_SUCCESS if success else EXIT_DOCKER_ERROR)


def cmd_status(args):
    """Show container status and resource usage."""

    client = get_docker_client()
    if not client:
        sys.exit(EXIT_DOCKER_ERROR)

    success = show_status(client)
    sys.exit(EXIT_SUCCESS if success else EXIT_DOCKER_ERROR)


def cmd_remove(args):
    """Remove the container (and optionally images)."""

    client = get_docker_client()
    if not client:
        sys.exit(EXIT_DOCKER_ERROR)

    force_remove = getattr(args, 'force_remove', False)
    success = remove_container(client, args.force, force_remove=force_remove)
    sys.exit(EXIT_SUCCESS if success else EXIT_DOCKER_ERROR)


def cmd_test(args):
    """Send test webhook to the container."""
    target = args.validator if args.validator else 'rate-my-mr'
    success = test_webhook(target=target)
    sys.exit(EXIT_SUCCESS if success else EXIT_ERROR)


def main():
    """Main CLI entry point using argparse."""
    parser = argparse.ArgumentParser(
        prog='manage_container.py',
        description='MR Validator - Container Management Script',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s build                    # Build Docker images
  %(prog)s start                    # Start container with confirmation
  %(prog)s start --yes              # Start container without confirmation
  %(prog)s logs                     # Follow logs in real-time
  %(prog)s logs --no-follow         # Show logs without following
  %(prog)s status                   # Show container status
  %(prog)s test                     # Test rate-my-mr webhook endpoint
  %(prog)s test --validator mrproper-message  # Test message validator
  %(prog)s remove                   # Remove container/images (interactive)

For more information, see README.md and OPERATIONS.md
        """
    )

    parser.add_argument('--version', action='version', version='%(prog)s 1.0.0')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    parser_config = subparsers.add_parser('config', help='Display and validate configuration')
    parser_config.add_argument('--env-file', default=ENV_FILE, help='Path to mrproper.env file')
    parser_config.add_argument('-q', '--quiet', action='store_true', help='Minimal output')
    parser_config.add_argument('--validate-only', action='store_true', help='Only validate')
    parser_config.set_defaults(func=cmd_config)

    parser_build = subparsers.add_parser('build', help='Build the Docker images')
    parser_build.set_defaults(func=cmd_build)

    parser_start = subparsers.add_parser('start', help='Start container (creates if needed)')
    parser_start.add_argument('-y', '--yes', action='store_true', help='Auto-confirm')
    parser_start.set_defaults(func=cmd_start)

    parser_stop = subparsers.add_parser('stop', help='Stop the container')
    parser_stop.set_defaults(func=cmd_stop)

    parser_restart = subparsers.add_parser('restart', help='Restart the container')
    parser_restart.set_defaults(func=cmd_restart)

    parser_logs = subparsers.add_parser('logs', help='View container logs')
    parser_logs.add_argument('-f', '--follow', action='store_true', default=True, help='Follow logs')
    parser_logs.add_argument('--no-follow', dest='follow', action='store_false', help='No follow')
    parser_logs.set_defaults(func=cmd_logs)

    parser_status = subparsers.add_parser('status', help='Show container status')
    parser_status.set_defaults(func=cmd_status)

    parser_remove = subparsers.add_parser('remove', help='Remove container/images')
    parser_remove.add_argument('-f', '--force', action='store_true', help='Skip confirmation')
    parser_remove.add_argument('--force-remove', action='store_true', help='Force remove if running')
    parser_remove.set_defaults(func=cmd_remove)

    parser_test = subparsers.add_parser('test', help='Send test webhook')
    parser_test.add_argument('--validator',
                             choices=['rate-my-mr', 'mrproper-message', 'mrproper-clang-format'],
                             help='Validator to test (default: rate-my-mr)')
    parser_test.set_defaults(func=cmd_test)

    args = parser.parse_args()

    # Handle Python 3.6 compatibility - required=True not supported in add_subparsers
    if not hasattr(args, 'func') or args.command is None:
        parser.print_help()
        sys.exit(EXIT_ERROR)

    args.func(args)


if __name__ == "__main__":
    main()
