"""
Structured logging configuration with aligned, pipe-separated format.

Format:
YYYY-MM-DD HH:MM:SS.mmm | LEVEL    | module.name                    | REQ_ID   | Message | key=value

Example:
2025-11-08 14:23:45.123 | INFO     | rate_my_mr.gitlab              | 4adcc17d | MR fetched | mr_iid=42 project=foo/bar

Configuration via environment variables:
- LOG_DIR: Base directory for logs (default: /home/docker/tmp/mr-validator-logs)
- LOG_LEVEL: Logging level (default: DEBUG)
- LOG_MAX_BYTES: Max size per log file (default: 50MB for validators, 100MB for webhook)
- LOG_BACKUP_COUNT: Number of backup files (default: 3 for validators, 5 for webhook)
"""

import logging
import logging.handlers
import os
from pathlib import Path
from datetime import datetime


class AlignedPipeFormatter(logging.Formatter):
    """
    Custom formatter with pipe-separated, column-aligned output.

    Features:
    - Millisecond precision timestamps
    - Pipe separators for clean parsing
    - Column alignment for visual scanning
    - Correlation ID (REQUEST_ID_SHORT)
    - Module name instead of filename
    """

    # Column widths for alignment
    LEVEL_WIDTH = 8
    MODULE_WIDTH = 30
    CORRELATION_WIDTH = 8

    def __init__(self):
        # Format with milliseconds
        super().__init__(
            fmt='%(asctime)s.%(msecs)03d | %(levelname)-8s | %(module_name)-30s | %(correlation_id)-8s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

    def format(self, record):
        # Add correlation ID (REQUEST_ID_SHORT)
        request_id = os.environ.get('REQUEST_ID', 'unknown')
        record.correlation_id = request_id.split('_')[-1][:8] if request_id != 'unknown' else 'unknown'

        # Add module name (instead of filename)
        # Use logger name if available, otherwise module name
        module_name = record.name if record.name else record.module

        # Truncate or pad module name to fit width
        if len(module_name) > self.MODULE_WIDTH:
            record.module_name = module_name[:self.MODULE_WIDTH - 3] + '...'
        else:
            record.module_name = module_name

        # Add milliseconds
        record.msecs = record.msecs

        # Format the record
        return super().format(record)


class StructuredLogger:
    """
    Helper for structured logging with key=value pairs.

    Usage:
        slog = StructuredLogger(logging.getLogger(__name__))
        slog.info("Pipeline processed", pipeline_id=123, duration_ms=456, status="success")

    Output:
        2025-11-08 14:23:45.123 | INFO     | rate_my_mr.gitlab              | 4adcc17d | Pipeline processed | pipeline_id=123 duration_ms=456 status=success
    """

    def __init__(self, logger):
        self.logger = logger

    def _format_message(self, message, **kwargs):
        """Format message with structured fields."""
        if kwargs:
            # Convert kwargs to key=value pairs
            fields = ' '.join(f'{k}={v}' for k, v in kwargs.items())
            return f'{message} | {fields}'
        return message

    def debug(self, message, **kwargs):
        self.logger.debug(self._format_message(message, **kwargs))

    def info(self, message, **kwargs):
        self.logger.info(self._format_message(message, **kwargs))

    def warning(self, message, **kwargs):
        self.logger.warning(self._format_message(message, **kwargs))

    def error(self, message, **kwargs):
        self.logger.error(self._format_message(message, **kwargs))

    def critical(self, message, **kwargs):
        self.logger.critical(self._format_message(message, **kwargs))


class LogConfig:
    """
    Centralized logging configuration.

    Environment variables:
    - LOG_DIR: Base directory (default: /home/docker/tmp/mr-validator-logs)
    - LOG_LEVEL: Logging level (default: DEBUG)
    - LOG_MAX_BYTES: Max bytes per file (default: 50MB)
    - LOG_BACKUP_COUNT: Backup files count (default: 3)
    - LOG_STRUCTURE: 'flat' or 'organized' (default: organized)
    """

    def __init__(self):
        self.base_dir = os.environ.get('LOG_DIR', '/home/docker/tmp/mr-validator-logs')
        self.level = os.environ.get('LOG_LEVEL', 'DEBUG')
        self.max_bytes = int(os.environ.get('LOG_MAX_BYTES', 50 * 1024 * 1024))  # 50MB
        self.backup_count = int(os.environ.get('LOG_BACKUP_COUNT', 3))
        self.structure = os.environ.get('LOG_STRUCTURE', 'organized')

    def get_log_path(self, log_type, request_id=None, project=None, mr_iid=None):
        """
        Get log file path based on structure type.

        Args:
            log_type: Type of log (webhook, validator, gitlab-api)
            request_id: REQUEST_ID for correlation
            project: Project name (optional, for organized structure)
            mr_iid: MR IID (optional, for organized structure)

        Returns:
            Path: Log file path
        """
        base = Path(self.base_dir)

        if self.structure == 'flat':
            # Flat structure (current behavior)
            if log_type == 'webhook':
                return base / 'webhook-server.log'
            elif log_type == 'validator':
                request_id_short = request_id.split('_')[-1][:8] if request_id else 'unknown'
                container_id = os.environ.get('HOSTNAME', 'unknown')
                return base / f'rate-my-mr-{request_id_short}-{container_id}.log'
            elif log_type == 'gitlab-api':
                request_id_short = request_id.split('_')[-1][:8] if request_id else 'unknown'
                container_id = os.environ.get('HOSTNAME', 'unknown')
                return base / f'gitlab-api-{request_id_short}-{container_id}.log'
        else:
            # Organized structure by date and project
            today = datetime.now().strftime('%Y-%m-%d')

            if log_type == 'webhook':
                # Webhook logs go to dated directory
                log_dir = base / 'webhook' / today
                log_dir.mkdir(parents=True, exist_ok=True)
                return log_dir / 'webhook-server.log'

            elif log_type == 'validator' or log_type == 'gitlab-api':
                # Validator logs organized by date/project/mr
                if project and mr_iid:
                    # Sanitize project name for filesystem
                    safe_project = project.replace('/', '_').replace('%2F', '_')
                    log_dir = base / 'validations' / today / safe_project / f'mr-{mr_iid}'
                    log_dir.mkdir(parents=True, exist_ok=True)

                    request_id_short = request_id.split('_')[-1][:8] if request_id else 'unknown'

                    if log_type == 'validator':
                        return log_dir / f'rate-my-mr-{request_id_short}.log'
                    else:
                        return log_dir / f'gitlab-api-{request_id_short}.log'
                else:
                    # Fallback to flat if project/mr not provided
                    return self.get_log_path(log_type, request_id)

        return base / 'unknown.log'


def setup_logging(log_type='validator', request_id='unknown', project=None, mr_iid=None):
    """
    Setup logging with aligned pipe format and configurable directory.

    Args:
        log_type: Type of log (webhook, validator, gitlab-api)
        request_id: REQUEST_ID for correlation
        project: Project name (for organized structure)
        mr_iid: MR IID (for organized structure)

    Returns:
        tuple: (logging.Logger, StructuredLogger)
    """
    # Get configuration
    config = LogConfig()

    # Get log file path
    log_file_path = config.get_log_path(log_type, request_id, project, mr_iid)

    # Ensure log directory exists
    log_file_path.parent.mkdir(parents=True, exist_ok=True)

    # Set REQUEST_ID in environment for formatter
    os.environ['REQUEST_ID'] = request_id

    # Create formatter
    formatter = AlignedPipeFormatter()

    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        str(log_file_path),
        maxBytes=config.max_bytes,
        backupCount=config.backup_count,
        encoding='utf-8'
    )
    file_handler.setLevel(getattr(logging, config.level))
    file_handler.setFormatter(formatter)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # Create logger
    logger = logging.getLogger(f'{log_type}.{request_id}')
    logger.setLevel(getattr(logging, config.level))
    logger.handlers = []  # Clear existing handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # Prevent propagation to root logger
    logger.propagate = False

    # Create structured logger
    slog = StructuredLogger(logger)

    return logger, slog


# Convenience function for backward compatibility
def get_logger(module_name):
    """Get a logger for a specific module."""
    return logging.getLogger(module_name)
