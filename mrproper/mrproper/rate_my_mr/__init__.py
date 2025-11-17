"""
Rate-My-MR: AI-powered Merge Request quality analyzer

This package provides comprehensive MR analysis including:
- AI-powered code review and summarization
- Lines of code metrics
- Cyclomatic complexity analysis
- Security vulnerability scanning
- Overall quality rating

Entry point: main() function from rate_my_mr_gitlab module
"""

from .rate_my_mr_gitlab import main

__all__ = ['main']
