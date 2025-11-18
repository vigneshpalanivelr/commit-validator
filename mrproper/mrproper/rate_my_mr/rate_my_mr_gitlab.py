#!/usr/bin/env python3

import subprocess
import sys
import tempfile
import urllib.parse
import os

# Import new structured logging
from .logging_config import setup_logging

# Get REQUEST_ID from environment (passed from webhook server)
REQUEST_ID = os.environ.get('REQUEST_ID', 'unknown')
REQUEST_ID_SHORT = REQUEST_ID.split('_')[-1][:8] if REQUEST_ID != 'unknown' else 'unknown'

# Get project and MR for organized logging
PROJECT_ID = os.environ.get('PROJECT_ID', 'unknown')
MR_IID = os.environ.get('MR_IID', '0')

# Setup structured logging with pipe-separated format
logger, slog = setup_logging(
    log_type='validator',
    request_id=REQUEST_ID,
    project=PROJECT_ID,
    mr_iid=MR_IID
)

# Configure child module loggers to use the same handlers
# This ensures logs from llm_adapter.py, rate_my_mr.py appear in the same log file
import logging
from .logging_config import AlignedPipeFormatter, LogConfig

def configure_child_loggers():
    """Configure module loggers to use the same file handler as main logger."""
    config = LogConfig()
    formatter = AlignedPipeFormatter()

    # Get handlers from main logger
    file_handler = None
    console_handler = None
    for handler in logger.handlers:
        if isinstance(handler, logging.handlers.RotatingFileHandler):
            file_handler = handler
        elif isinstance(handler, logging.StreamHandler):
            console_handler = handler

    # Module loggers to configure
    module_loggers = [
        'mrproper.rate_my_mr.rate_my_mr',
        'mrproper.rate_my_mr.llm_adapter',
        'mrproper.rate_my_mr.loc',
        'mrproper.rate_my_mr.cyclomatic_complexity',
        'mrproper.rate_my_mr.security_scan',
        'mrproper.rate_my_mr.cal_rating',
        'mrproper.rate_my_mr.config_loader',
    ]

    for module_name in module_loggers:
        module_logger = logging.getLogger(module_name)
        module_logger.setLevel(getattr(logging, config.level))
        module_logger.handlers = []  # Clear existing handlers
        if file_handler:
            module_logger.addHandler(file_handler)
        if console_handler:
            module_logger.addHandler(console_handler)
        module_logger.propagate = False

    slog.debug("Child module loggers configured", modules=len(module_loggers))

configure_child_loggers()

# Debug: Log all environment variables related to AI/LLM configuration
slog.debug("=" * 60)
slog.debug("ENVIRONMENT VARIABLES DEBUG")
slog.debug("=" * 60)
slog.debug("AI/LLM Configuration",
           BFA_HOST=os.environ.get('BFA_HOST', 'NOT_SET'),
           BFA_TOKEN_KEY=f"{os.environ.get('BFA_TOKEN_KEY', 'NOT_SET')[:20]}..." if os.environ.get('BFA_TOKEN_KEY') else 'NOT_SET',
           AI_SERVICE_URL=os.environ.get('AI_SERVICE_URL', 'NOT_SET'),
           API_TIMEOUT=os.environ.get('API_TIMEOUT', 'NOT_SET'))
slog.debug("GitLab Configuration",
           GITLAB_ACCESS_TOKEN=f"{os.environ.get('GITLAB_ACCESS_TOKEN', 'NOT_SET')[:15]}..." if os.environ.get('GITLAB_ACCESS_TOKEN') else 'NOT_SET')
slog.debug("Logging Configuration",
           LOG_DIR=os.environ.get('LOG_DIR', 'NOT_SET'),
           LOG_LEVEL=os.environ.get('LOG_LEVEL', 'NOT_SET'),
           LOG_STRUCTURE=os.environ.get('LOG_STRUCTURE', 'NOT_SET'))
slog.debug("Request Context",
           REQUEST_ID=REQUEST_ID,
           PROJECT_ID=PROJECT_ID,
           MR_IID=MR_IID)
slog.debug("=" * 60)

from .. import gitlab  # Import from parent directory (common module)
from .rate_my_mr import (
    generate_summary, generate_initial_code_review,
    generate_lint_disable_report, cal_rating, print_banner,
    cal_cc, cal_ss
)
from .loc import LOCCalculator
from .config_loader import load_config, is_feature_enabled, get_loc_settings, get_cc_settings, get_security_settings, get_lint_settings, get_rating_settings, get_report_settings

HEADER = """\
:star2: MR Quality Rating Report :star2:
========================================

"""


def create_diff_from_mr(proj, mriid, checkout_dir, mr_data, mrcommits):
    """
    Create a git diff file from MR data for analysis

    Args:
        proj: Project identifier
        mriid: MR IID
        checkout_dir: Git checkout directory

    Returns:
        str: Path to created diff file
    """
    slog.debug("Creating diff for MR", mr_iid=mriid, working_dir=checkout_dir)

    try:
        # Check current branch and remotes
        slog.debug("Checking git status")
        try:
            branches = subprocess.check_output(["git", "branch", "-a"], cwd=checkout_dir).decode("utf-8")
            slog.debug("Available branches", count=len(branches.split('\n')))
        except subprocess.CalledProcessError as e:
            slog.warning("Could not list branches", error=str(e))

        # Get diff between MR base and head using target branch
        target_branch = mr_data.target_branch
        slog.debug("Generating git diff", target_branch=target_branch, method="target...HEAD")
        diff_output = subprocess.check_output([
            "git", "diff", "--no-color", f"{target_branch}...HEAD"
        ], cwd=checkout_dir).decode("utf-8")

        slog.info("Git diff generated", size_chars=len(diff_output))

        # Save diff to temporary file
        diff_file_path = os.path.join(checkout_dir, "mr_diff.txt")
        with open(diff_file_path, 'w') as diff_file:
            diff_file.write(diff_output)

        slog.info("Diff saved to file", path=diff_file_path, exists=os.path.exists(diff_file_path))
        return diff_file_path

    except subprocess.CalledProcessError as e:
        slog.warning("Primary diff method failed", error=str(e))
        slog.debug("Attempting fallback diff methods")
        # Fallback: create diff using commit-based approach
        try:
            slog.debug("Using commit list from GitLab API", commits=len(mrcommits))

            if len(mrcommits) >= 2:
                first_commit = mrcommits[0].id
                last_commit = mrcommits[-1].id
                slog.debug("Multi-commit diff", first=first_commit[:8], last=last_commit[:8])
                diff_output = subprocess.check_output([
                    "git", "diff", "--no-color", f"{first_commit}..{last_commit}"
                ], cwd=checkout_dir).decode("utf-8")
            else:
                # Single commit diff
                commit_id = mrcommits[0].id
                slog.debug("Single commit MR", commit=commit_id[:8], method="git_show")
                diff_output = subprocess.check_output([
                    "git", "show", "--no-color", commit_id
                ], cwd=checkout_dir).decode("utf-8")

            slog.info("Fallback diff generated", size_chars=len(diff_output))

            diff_file_path = os.path.join(checkout_dir, "mr_diff.txt")
            with open(diff_file_path, 'w') as diff_file:
                diff_file.write(diff_output)

            slog.info("Fallback diff saved", path=diff_file_path)
            return diff_file_path

        except Exception as fallback_error:
            slog.error("Fallback diff creation failed", error=str(fallback_error), error_type=type(fallback_error).__name__)
            return None


def format_rating_report(summary_success, summary_content, review_success, review_content, loc_data, lint_data, cc_data, ss_data, rating_score):
    """
    Format the complete rating report for GitLab discussion

    Args:
        summary_success: Success status of AI summary
        summary_content: AI-generated summary text
        review_success: Success status of AI review
        review_content: AI-generated code review text
        loc_data: LOC analysis results
        lint_data: Lint disable analysis results
        cc_data: Cyclomatic complexity analysis results
        ss_data: Security scan analysis results
        rating_score: Final quality rating

    Returns:
        tuple: (report_body, must_not_be_resolved)
    """

    # Rating visualization (without stars emoji repetition)
    report = f"""
## Overall Rating: {rating_score}/5

### Quality Assessment Results

#### :mag: Summary Analysis
"""

    if summary_success and summary_content:
        report += f":white_check_mark: AI-powered summary generated successfully\n\n"
        report += f"<details>\n<summary>Click to expand AI Summary</summary>\n\n{summary_content}\n\n</details>\n"
    else:
        report += ":x: Summary generation failed - check AI service connectivity\n"

    report += """
#### :microscope: Code Review Analysis
"""

    if review_success and review_content:
        report += f":white_check_mark: Comprehensive AI code review completed\n\n"
        report += f"<details>\n<summary>Click to expand AI Code Review</summary>\n\n{review_content}\n\n</details>\n"
    else:
        report += ":x: Code review analysis failed - check AI service connectivity\n"

    report += f"""
#### :chart_with_upwards_trend: Lines of Code Analysis
- **Lines Added**: {loc_data.get('lines_of_code_added', 0)}
- **Lines Removed**: {loc_data.get('lines_of_code_removed', 0)}
- **Net Change**: {loc_data.get('net_lines_of_code_change', 0)}

"""

    if lint_data and isinstance(lint_data, dict):
        report += f"""#### :warning: Lint Disable Analysis
- **New Lint Disables**: {lint_data.get('num_lint_disable', 0)}
- **Disabled Rules**: {lint_data.get('lints_that_disabled', 'None')}

"""
    else:
        report += """#### :warning: Lint Disable Analysis
- **Status**: Analysis completed (see console output for details)

"""

    # Cyclomatic Complexity section
    report += """#### :cyclone: Cyclomatic Complexity Analysis
"""
    if cc_data and isinstance(cc_data, dict):
        avg_cc = cc_data.get('avg_cc', 0)
        method_cc = cc_data.get('method_wise_cc', {})
        cc_status = "Good" if avg_cc <= 10 else "High complexity"
        report += f"- **Average Complexity**: {avg_cc} ({cc_status})\n"
        if method_cc:
            report += f"- **Methods Analyzed**: {len(method_cc)}\n"
            high_cc_methods = {k: v for k, v in method_cc.items() if v > 10}
            if high_cc_methods:
                report += f"- **High Complexity Methods** (CC > 10):\n"
                for method, cc in sorted(high_cc_methods.items(), key=lambda x: x[1], reverse=True)[:5]:
                    report += f"  - `{method}`: {cc}\n"
        report += "\n"
    else:
        report += "- **Status**: Analysis not performed or failed\n\n"

    # Security Scan section
    report += """#### :shield: Security Scan Analysis
"""
    if ss_data and isinstance(ss_data, dict):
        severity_count = ss_data.get('severity_count', {})
        avg_score = ss_data.get('avg_security_scan_value', 0)
        high_issues = severity_count.get('HIGH', 0)
        medium_issues = severity_count.get('MEDIUM', 0)
        low_issues = severity_count.get('LOW', 0)

        report += f"- **HIGH Severity Issues**: {high_issues} {'(Critical!)' if high_issues > 0 else ''}\n"
        report += f"- **MEDIUM Severity Issues**: {medium_issues}\n"
        report += f"- **LOW Severity Issues**: {low_issues}\n"
        report += f"- **Security Score**: {avg_score:.4f} issues/LOC\n"

        security_report = ss_data.get('security_report', {})
        results = security_report.get('results', [])
        if results:
            report += "\n<details>\n<summary>Click to expand Security Issues</summary>\n\n"
            for issue in results[:10]:
                report += f"- **{issue.get('issue_severity', 'UNKNOWN')}** - {issue.get('issue_text', 'Unknown issue')}\n"
                report += f"  - Test: `{issue.get('test_name', 'unknown')}`\n"
                report += f"  - Line: {issue.get('line_number', 'N/A')}\n"
                if issue.get('more_info'):
                    report += f"  - [More Info]({issue.get('more_info')})\n"
                report += "\n"
            report += "</details>\n"
        report += "\n"
    else:
        report += "- **Status**: Analysis not performed or failed\n\n"

    # Rating breakdown
    report += f"""### Scoring Breakdown
| Metric | Status | Impact |
|--------|--------|--------|
| Lines of Code | {loc_data.get('net_lines_of_code_change', 0)} lines | {'Within limits' if loc_data.get('net_lines_of_code_change', 0) <= 500 else 'Exceeds 500 line limit'} |
| Lint Disables | {lint_data.get('num_lint_disable', 0) if isinstance(lint_data, dict) else 0} new disables | {'No new disables' if (isinstance(lint_data, dict) and lint_data.get('num_lint_disable', 0) == 0) else 'New lint suppressions added'} |
| Cyclomatic Complexity | Avg: {cc_data.get('avg_cc', 'N/A') if isinstance(cc_data, dict) else 'N/A'} | {'Good' if isinstance(cc_data, dict) and cc_data.get('avg_cc', 0) <= 10 else 'High complexity'} |
| Security Issues | {(ss_data.get('severity_count', {}).get('HIGH', 0) + ss_data.get('severity_count', {}).get('MEDIUM', 0)) if isinstance(ss_data, dict) else 0} HIGH/MEDIUM | {'No critical issues' if isinstance(ss_data, dict) and ss_data.get('severity_count', {}).get('HIGH', 0) == 0 else 'Security concerns'} |

**Final Score**: {rating_score}/5 points

"""

    # Determine if MR should be blocked
    must_not_be_resolved = rating_score < 3  # Block if score < 3

    if must_not_be_resolved:
        report += """
:bomb: **QUALITY ISSUES IDENTIFIED** :bomb:<br>
This MR has significant quality concerns that should be addressed before merging.<br>
The assessment will be automatically updated when changes are pushed.

### Recommended Actions:
- Review the AI-generated feedback in the container logs
- Address identified code quality issues
- Consider breaking large changes into smaller MRs
- Remove unnecessary lint disable statements
"""
    else:
        report += """
:white_check_mark: **Quality assessment passed** - MR meets quality standards.

### Notes:
- Detailed analysis available in container execution logs
- AI-powered insights have been generated for this MR
- Continue monitoring quality metrics in future MRs
"""

    report += """

---
*Generated by AI-powered MR quality assessment*
*Scoring: LOC Analysis + Lint Pattern Detection + AI Code Review*
"""

    return report, must_not_be_resolved


def handle_mr(proj, mriid):
    """
    Main MR analysis function with GitLab integration

    Args:
        proj: Project identifier (URL-encoded)
        mriid: Merge request IID
    """

    slog.info("Starting MR analysis", project=proj, mr_iid=mriid, gitlab_host=gitlab.GITLAB_HOST)

    try:
        gitlab_token = os.environ.get('GITLAB_ACCESS_TOKEN', '')
        token_available = bool(gitlab_token)
        slog.debug("Environment check", token_available=token_available)
        if token_available:
            logger.debug(f"Token starts with: {gitlab_token[:10]}...")
    except Exception as e:
        slog.error("Error checking environment", error=str(e))
        token_available = False

    print_banner(f"[{REQUEST_ID_SHORT}] Processing MR {mriid} in project {proj}")

    # Set PROJECT_ID and MR_IID for LLM adapter JWT token generation
    # These are needed if BFA_HOST is configured (new LLM adapter)
    os.environ['PROJECT_ID'] = proj
    os.environ['MR_IID'] = str(mriid)
    slog.debug("Environment configured for LLM adapter", project_id=proj, mr_iid=mriid)

    try:
        slog.debug("Fetching MR data from GitLab API", project=proj, mr_iid=mriid)
        # Fetch MR data from GitLab
        mr = gitlab.gitlab("/projects/{}/merge_requests/{}".format(proj, mriid))
        slog.info("MR fetched successfully",
                  title=mr.title,
                  state=mr.state,
                  source_branch=mr.source_branch,
                  target_branch=mr.target_branch)

        slog.debug("Fetching MR commits", project=proj, mr_iid=mriid)
        mrcommits = gitlab.gitlab("/projects/{}/merge_requests/{}/commits".format(proj, mr.iid))
        slog.info("MR commits fetched", commit_count=len(mrcommits))

        for i, commit in enumerate(mrcommits):
            slog.debug(f"Commit {i+1}", commit_id=commit.id[:8], title=commit.title)

        # Extract MR metadata for LLM adapter (new BFA API integration)
        # These environment variables are used by llm_adapter.py to construct the request
        slog.debug("Extracting MR metadata for LLM adapter")

        # Decode project name from URL encoding (e.g., "my-org%2Fmy-project" → "my-org/my-project")
        MR_REPO = urllib.parse.unquote(proj)

        # Extract branch name
        MR_BRANCH = mr.source_branch

        # Extract author email (with fallback if not available)
        mr_author = getattr(mr, 'author', None)
        if mr_author:
            # Try to get email from author object
            MR_AUTHOR = getattr(mr_author, 'email', None) or getattr(mr_author, 'username', 'unknown') + '@internal.com'
        else:
            MR_AUTHOR = 'unknown@internal.com'

        # Extract latest commit SHA
        MR_COMMIT = mrcommits[-1].id if mrcommits else 'unknown'

        # Construct MR URL (use web_url if available, otherwise construct it)
        MR_URL = getattr(mr, 'web_url', None) or f"https://{gitlab.GITLAB_HOST}/{MR_REPO}/merge_requests/{mriid}"

        # Set environment variables for LLM adapter
        os.environ['MR_REPO'] = MR_REPO
        os.environ['MR_BRANCH'] = MR_BRANCH
        os.environ['MR_AUTHOR'] = MR_AUTHOR
        os.environ['MR_COMMIT'] = MR_COMMIT
        os.environ['MR_URL'] = MR_URL

        slog.info("MR metadata extracted for LLM adapter",
                  repo=MR_REPO,
                  branch=MR_BRANCH,
                  author=MR_AUTHOR,
                  commit=MR_COMMIT[:8] if MR_COMMIT != 'unknown' else 'unknown',
                  mr_url=MR_URL)

    except Exception as api_error:
        slog.error("GitLab API error", error=str(api_error), error_type=type(api_error).__name__)
        raise

    # Setup temporary git repository for analysis
    slog.debug("Setting up temporary git repository")
    with tempfile.TemporaryDirectory() as tdir:
        slog.debug("Temporary directory created", path=tdir)

        slog.debug("Initializing git repository")
        init_result = subprocess.call(["git", "init", "-q"], cwd=tdir)
        if init_result != 0:
            slog.error("Git init failed", return_code=init_result)
            raise RuntimeError(f"Git init failed with return code {init_result}")

        clone_url = gitlab.get_clone_url(proj.replace('%2F', '/'))
        slog.debug("Fetching git repository",
                   target_branch=mr.target_branch,
                   source_branch=mr.source_branch,
                   mr_ref=f"merge-requests/{mr.iid}/head")

        try:
            # Fetch both MR head and target branch for proper diff
            fetch_depth = max(len(mrcommits), 100)
            fetch_result = subprocess.call(["git", "fetch", "-q",
                             f"--depth={fetch_depth}",
                             clone_url,
                             f"merge-requests/{mr.iid}/head",
                             f"{mr.target_branch}:{mr.target_branch}"],
                            cwd=tdir)
            if fetch_result != 0:
                slog.error("Git fetch failed", return_code=fetch_result, depth=fetch_depth)
                raise RuntimeError(f"Git fetch failed with return code {fetch_result}")
            slog.info("Git fetch completed", depth=fetch_depth, commits=len(mrcommits))
        except RuntimeError:
            raise
        except Exception as fetch_error:
            slog.error("Git fetch exception", error=str(fetch_error), error_type=type(fetch_error).__name__)
            raise

        try:
            subprocess.check_output(["git", "checkout", "-q", "-b", "check", "FETCH_HEAD"], cwd=tdir)
            slog.debug("Git checkout completed", branch="check")
        except Exception as checkout_error:
            slog.error("Git checkout failed", error=str(checkout_error), error_type=type(checkout_error).__name__)
            raise

        # Load repository-specific configuration
        slog.debug("Loading repository configuration", repo_dir=tdir)
        config = load_config(tdir)
        slog.info("Configuration loaded",
                  ai_summary=is_feature_enabled(config, 'ai_summary'),
                  ai_code_review=is_feature_enabled(config, 'ai_code_review'),
                  loc_analysis=is_feature_enabled(config, 'loc_analysis'),
                  lint_disable_check=is_feature_enabled(config, 'lint_disable_check'),
                  cyclomatic_complexity=is_feature_enabled(config, 'cyclomatic_complexity'),
                  security_scan=is_feature_enabled(config, 'security_scan'))

        # Create diff file for analysis
        slog.debug("Creating diff file for analysis")
        diff_file_path = create_diff_from_mr(proj, mriid, tdir, mr, mrcommits)

        if not diff_file_path or not os.path.exists(diff_file_path):
            slog.error("Could not create diff file for analysis")
            # Post error report to GitLab
            error_report = """
## :x: MR Quality Assessment Failed

Unable to generate diff for analysis. This could be due to:
- Empty MR with no changes
- Git repository access issues
- Merge conflicts or other git problems

Please check the MR manually and retry if necessary.
"""
            slog.info("Posting error report to GitLab")
            gitlab.update_discussion(proj, mriid, HEADER, error_report, False)
            return

        # Verify diff file content
        try:
            with open(diff_file_path, 'r') as f:
                diff_content = f.read()
                slog.debug("Diff file created", size_bytes=len(diff_content), preview=diff_content[:200])
        except Exception as read_error:
            slog.warning("Could not read diff file", error=str(read_error))

        # Run analysis pipeline
        print_banner(f"[{REQUEST_ID_SHORT}] Starting Analysis Pipeline")
        slog.info("Analysis pipeline started")

        # 1. Generate AI summary (if enabled)
        slog.debug("Step 1: Generating AI summary")
        if is_feature_enabled(config, 'ai_summary'):
            summary_success, summary_content = generate_summary(diff_file_path)
            slog.info("AI summary completed", success=summary_success)
            if not summary_success:
                summary_content = ""
        else:
            slog.info("AI summary skipped (disabled in config)")
            summary_success = False
            summary_content = ""

        # 2. Generate AI code review (if enabled)
        slog.debug("Step 2: Generating AI code review")
        if is_feature_enabled(config, 'ai_code_review'):
            review_success, review_content = generate_initial_code_review(diff_file_path)
            slog.info("AI code review completed", success=review_success)
            if not review_success:
                review_content = ""
        else:
            slog.info("AI code review skipped (disabled in config)")
            review_success = False
            review_content = ""

        # 3. Calculate LOC metrics (if enabled)
        slog.debug("Step 3: Calculating LOC metrics")
        if is_feature_enabled(config, 'loc_analysis'):
            print_banner(f"[{REQUEST_ID_SHORT}] LOC Analysis")
            loc_settings = get_loc_settings(config)
            loc_calculator = LOCCalculator(diff_file_path)
            loc_success, loc_data = loc_calculator.calculate_loc()

            if not loc_success:
                slog.warning("LOC analysis failed", error=loc_data)
                loc_data = {'lines_of_code_added': 0, 'lines_of_code_removed': 0, 'net_lines_of_code_change': 0}
            else:
                slog.info("LOC analysis completed",
                          added=loc_data.get('lines_of_code_added', 0),
                          removed=loc_data.get('lines_of_code_removed', 0),
                          net=loc_data.get('net_lines_of_code_change', 0),
                          max_lines=loc_settings.get('max_lines', 500))
        else:
            slog.info("LOC analysis skipped (disabled in config)")
            loc_data = {'lines_of_code_added': 0, 'lines_of_code_removed': 0, 'net_lines_of_code_change': 0}

        # 4. Analyze lint disables (if enabled)
        slog.debug("Step 4: Analyzing lint disables")
        if is_feature_enabled(config, 'lint_disable_check'):
            lint_settings = get_lint_settings(config)
            lint_success, lint_data = generate_lint_disable_report(diff_file_path)

            if not lint_success:
                slog.warning("Lint analysis failed", error=lint_data)
                lint_data = {'num_lint_disable': 0, 'lints_that_disabled': ''}
            else:
                slog.info("Lint analysis completed",
                          num_disables=lint_data.get('num_lint_disable', 0),
                          disabled_lints=lint_data.get('lints_that_disabled', ''),
                          max_new_disables=lint_settings.get('max_new_disables', 10))
        else:
            slog.info("Lint disable analysis skipped (disabled in config)")
            lint_data = {'num_lint_disable': 0, 'lints_that_disabled': ''}

        # 5. Calculate cyclomatic complexity (if enabled)
        slog.debug("Step 5: Calculating cyclomatic complexity")
        if is_feature_enabled(config, 'cyclomatic_complexity'):
            print_banner(f"[{REQUEST_ID_SHORT}] Cyclomatic Complexity Analysis")
            cc_settings = get_cc_settings(config)
            try:
                cc_data = cal_cc(diff_file_path)
                if cc_data:
                    slog.info("Cyclomatic complexity completed",
                              avg_cc=cc_data.get('avg_cc', 0),
                              methods=len(cc_data.get('method_wise_cc', {})),
                              max_average=cc_settings.get('max_average', 10))
                else:
                    cc_data = {}
            except Exception as cc_error:
                slog.warning("Cyclomatic complexity failed", error=str(cc_error))
                cc_data = {}
        else:
            slog.info("Cyclomatic complexity analysis skipped (disabled in config)")
            cc_data = {}

        # 6. Security scan (if enabled)
        slog.debug("Step 6: Running security scan")
        if is_feature_enabled(config, 'security_scan'):
            print_banner(f"[{REQUEST_ID_SHORT}] Security Scan Analysis")
            security_settings = get_security_settings(config)
            try:
                ss_data = cal_ss(diff_file_path)
                if ss_data:
                    severity = ss_data.get('severity_count', {})
                    slog.info("Security scan completed",
                              high=severity.get('HIGH', 0),
                              medium=severity.get('MEDIUM', 0),
                              low=severity.get('LOW', 0),
                              fail_on_high=security_settings.get('fail_on_high', True))
                else:
                    ss_data = {}
            except Exception as ss_error:
                slog.warning("Security scan failed", error=str(ss_error))
                ss_data = {}
        else:
            slog.info("Security scan skipped (disabled in config)")
            ss_data = {}

        # 7. Calculate overall rating
        slog.debug("Step 7: Calculating overall rating")
        rating_settings = get_rating_settings(config)
        rating_score = cal_rating(
            loc_data.get('net_lines_of_code_change', 0),
            lint_data.get('num_lint_disable', 0) if isinstance(lint_data, dict) else 0
        )
        slog.info("Final rating calculated",
                  score=rating_score,
                  max_score=5,
                  pass_threshold=rating_settings.get('pass_score', 3))
        print_banner(f"[{REQUEST_ID_SHORT}] Final Rating: {rating_score}/5")

    # Format report for GitLab
    slog.debug("Step 8: Formatting report for GitLab")
    report_body, must_not_be_resolved = format_rating_report(
        summary_success, summary_content, review_success, review_content, loc_data, lint_data, cc_data, ss_data, rating_score
    )
    slog.debug("Report formatted", must_not_be_resolved=must_not_be_resolved)

    # Post results to GitLab
    slog.debug("Step 9: Posting results to GitLab")
    try:
        gitlab.update_discussion(proj, mriid, HEADER, report_body, must_not_be_resolved)
        slog.info("Report posted to GitLab successfully")
    except Exception as gitlab_error:
        slog.error("Failed to post to GitLab", error=str(gitlab_error), error_type=type(gitlab_error).__name__)
        raise

    slog.info("MR analysis completed successfully")


def main():
    """
    Entry point for GitLab-integrated rate-my-mr validator
    """
    if len(sys.argv) != 3:
        print("Usage: rate-my-mr <project> <mr_iid>")
        print("Example: rate-my-mr my-org/my-project 123")
        sys.exit(1)

    proj = urllib.parse.quote(sys.argv[1], safe="")
    mriid = int(sys.argv[2])

    try:
        handle_mr(proj, mriid)
        print(f"Successfully analyzed MR {mriid} in project {sys.argv[1]}")
    except Exception as e:
        print(f"Error analyzing MR {mriid}: {e}")

        # Post error to GitLab if possible
        try:
            error_report = f"""
## :x: MR Quality Assessment Error

An error occurred during MR analysis:

```
{str(e)}
```

This may be due to:
- AI service connectivity issues
- Repository access problems
- Resource constraints

Please check the system status and retry.
"""
            gitlab.update_discussion(proj, mriid, HEADER, error_report, False)
            slog.info("Posted error report to GitLab", mr_iid=mriid)
        except Exception as posting_error:
            # Log the error but don't fail the entire process
            slog.error("Failed to post error report to GitLab", error=str(posting_error), error_type=type(posting_error).__name__)
            print(f"[{REQUEST_ID_SHORT}] WARNING: Could not post error to GitLab: {posting_error}")

        sys.exit(1)


if __name__ == '__main__':
    main()
