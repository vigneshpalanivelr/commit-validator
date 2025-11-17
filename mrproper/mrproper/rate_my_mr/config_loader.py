"""
Configuration loader for Rate My MR.

Loads configuration from .rate-my-mr.yaml in the repository root.
Provides sensible defaults when config file is not present.
"""

import os
import yaml
import logging

logger = logging.getLogger(__name__)


DEFAULT_CONFIG = {
    # Feature toggles
    'features': {
        'ai_summary': True,
        'ai_code_review': True,
        'loc_analysis': True,
        'lint_disable_check': True,
        'cyclomatic_complexity': True,
        'security_scan': True,
    },

    # LOC settings
    'loc': {
        'max_lines': 500,
        'warning_threshold': 300,
    },

    # Cyclomatic complexity settings
    'cyclomatic_complexity': {
        'max_average': 10,
        'max_per_method': 15,
        'show_top_n_methods': 5,
    },

    # Security scan settings
    'security': {
        'fail_on_high': True,
        'fail_on_medium': False,
        'max_issues_per_loc': 0.05,  # 5% threshold
        'ignored_tests': [],  # e.g., ['B101', 'B311']
        'show_max_issues': 10,
    },

    # Lint disable settings
    'lint': {
        'allowed_disables': [],  # e.g., ['too-many-arguments', 'no-member']
        'max_new_disables': 10,
    },

    # Rating calculation
    'rating': {
        'pass_score': 3,  # MR blocked if score < this
        'deduct_for_high_loc': True,
        'deduct_for_lint_disables': True,
        'deduct_for_high_cc': False,  # Not currently implemented
        'deduct_for_security_issues': False,  # Not currently implemented
    },

    # Report customization
    'report': {
        'show_ai_content': True,  # Show AI summary/review in collapsible sections
        'show_security_details': True,  # Show security issue details
        'show_cc_breakdown': True,  # Show per-method CC
    },
}


def deep_merge(base, override):
    """
    Deep merge two dictionaries. Override values take precedence.

    Args:
        base: Base configuration dict
        override: Override configuration dict

    Returns:
        dict: Merged configuration
    """
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value

    return result


def load_config(repo_dir):
    """
    Load configuration from .rate-my-mr.yaml in the repository.

    Args:
        repo_dir: Path to the repository root

    Returns:
        dict: Configuration dictionary with defaults applied
    """
    config_path = os.path.join(repo_dir, '.rate-my-mr.yaml')

    # Start with defaults
    config = DEFAULT_CONFIG.copy()

    # Try to load repo-specific config
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                repo_config = yaml.safe_load(f)

            if repo_config and isinstance(repo_config, dict):
                # Deep merge repo config with defaults
                config = deep_merge(DEFAULT_CONFIG, repo_config)
                logger.info(f"Loaded configuration from {config_path}")
                logger.debug(f"Config features: {config.get('features', {})}")
            else:
                logger.warning(f"Config file {config_path} is empty or invalid, using defaults")
        except yaml.YAMLError as e:
            logger.error(f"Error parsing {config_path}: {e}")
            logger.warning("Using default configuration")
        except Exception as e:
            logger.error(f"Error loading {config_path}: {e}")
            logger.warning("Using default configuration")
    else:
        logger.info(f"No config file found at {config_path}, using defaults")

    return config


def is_feature_enabled(config, feature_name):
    """
    Check if a specific feature is enabled.

    Args:
        config: Configuration dictionary
        feature_name: Name of the feature (e.g., 'ai_summary', 'security_scan')

    Returns:
        bool: True if feature is enabled
    """
    features = config.get('features', {})
    # Default to True if not specified
    return features.get(feature_name, True)


def get_loc_settings(config):
    """Get LOC analysis settings."""
    return config.get('loc', DEFAULT_CONFIG['loc'])


def get_cc_settings(config):
    """Get cyclomatic complexity settings."""
    return config.get('cyclomatic_complexity', DEFAULT_CONFIG['cyclomatic_complexity'])


def get_security_settings(config):
    """Get security scan settings."""
    return config.get('security', DEFAULT_CONFIG['security'])


def get_lint_settings(config):
    """Get lint disable settings."""
    return config.get('lint', DEFAULT_CONFIG['lint'])


def get_rating_settings(config):
    """Get rating calculation settings."""
    return config.get('rating', DEFAULT_CONFIG['rating'])


def get_report_settings(config):
    """Get report customization settings."""
    return config.get('report', DEFAULT_CONFIG['report'])
