#!/usr/bin/env python3

import subprocess
import sys
import tempfile
import urllib.parse
import os

import logging

# Ensure log directory exists
os.makedirs('/home/docker/tmp/mr-validator-logs', exist_ok=True)

# Get REQUEST_ID from environment (passed from webhook server)
REQUEST_ID = os.environ.get('REQUEST_ID', 'unknown')
REQUEST_ID_SHORT = REQUEST_ID.split('_')[-1][:8] if REQUEST_ID != 'unknown' else 'unknown'

# Generate unique log filename per container (using REQUEST_ID for correlation)
container_id = os.environ.get('HOSTNAME', 'unknown')
log_filename = f'/home/docker/tmp/mr-validator-logs/rate-my-mr-{REQUEST_ID_SHORT}-{container_id}.log'

# Setup logging for rate_my_mr_gitlab with REQUEST_ID in format
logging.basicConfig(
    level=logging.DEBUG,
    format=f'%(asctime)s - [{REQUEST_ID_SHORT}] - %(filename)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(log_filename),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

from . import gitlab
from .rate_my_mr import (
    generate_summary, generate_initial_code_review,
    generate_lint_disable_report, cal_rating, print_banner
)
from .loc import LOCCalculator

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
    print(f"[{REQUEST_ID_SHORT}] [DEBUG] Creating diff for MR {mriid} in project {proj}")
    print(f"[{REQUEST_ID_SHORT}] [DEBUG] Working directory: {checkout_dir}")

    try:
        # Check current branch and remotes
        print("[DEBUG] Checking git status...")
        try:
            branches = subprocess.check_output(["git", "branch", "-a"], cwd=checkout_dir).decode("utf-8")
            print(f"[DEBUG] Available branches:\n{branches}")
        except subprocess.CalledProcessError as e:
            print(f"[DEBUG] Could not list branches: {e}")

        # Get diff between MR base and head using target branch
        target_branch = mr_data.target_branch
        print(f"[DEBUG] Attempting git diff {target_branch}...HEAD")
        diff_output = subprocess.check_output([
            "git", "diff", "--no-color", f"{target_branch}...HEAD"
        ], cwd=checkout_dir).decode("utf-8")

        print(f"[DEBUG] Generated diff length: {len(diff_output)} characters")

        # Save diff to temporary file
        diff_file_path = os.path.join(checkout_dir, "mr_diff.txt")
        with open(diff_file_path, 'w') as diff_file:
            diff_file.write(diff_output)

        print(f"[DEBUG] Saved diff to: {diff_file_path}")
        print(f"[DEBUG] Diff file exists: {os.path.exists(diff_file_path)}")

        return diff_file_path

    except subprocess.CalledProcessError as e:
        print(f"[DEBUG] Primary diff method failed: {e}")
        print(f"[DEBUG] Attempting fallback diff methods...")
        # Fallback: create diff using commit-based approach
        try:
            print("[DEBUG] Using commit list from GitLab API...")
            # Get commits from the MR data we already fetched
            print(f"[DEBUG] Found {len(mrcommits)} commits in MR")

            if len(mrcommits) >= 2:
                first_commit = mrcommits[0].id
                last_commit = mrcommits[-1].id
                print(f"[DEBUG] Attempting diff between {first_commit[:8]}..{last_commit[:8]}")
                diff_output = subprocess.check_output([
                    "git", "diff", "--no-color", f"{first_commit}..{last_commit}"
                ], cwd=checkout_dir).decode("utf-8")
            else:
                # Single commit diff
                commit_id = mrcommits[0].id
                print(f"[DEBUG] Single commit MR, using git show for {commit_id[:8]}")
                diff_output = subprocess.check_output([
                    "git", "show", "--no-color", commit_id
                ], cwd=checkout_dir).decode("utf-8")

            print(f"[DEBUG] Fallback diff generated, length: {len(diff_output)} characters")

            diff_file_path = os.path.join(checkout_dir, "mr_diff.txt")
            with open(diff_file_path, 'w') as diff_file:
                diff_file.write(diff_output)

            print(f"[DEBUG] Fallback diff saved to: {diff_file_path}")
            return diff_file_path

        except Exception as fallback_error:
            print(f"[DEBUG] Fallback diff creation failed: {fallback_error}")
            print(f"[DEBUG] Error type: {type(fallback_error).__name__}")
            return None


def format_rating_report(summary_success, review_success, loc_data, lint_data, rating_score):
    """
    Format the complete rating report for GitLab discussion

    Args:
        summary_success: Success status of AI summary
        review_success: Success status of AI review
        loc_data: LOC analysis results
        lint_data: Lint disable analysis results
        rating_score: Final quality rating

    Returns:
        tuple: (report_body, must_not_be_resolved)
    """

    # Rating visualization
    stars = ":star:" * int(rating_score) + ":white_circle:" * (5 - int(rating_score))
    report = f"""
## Overall Rating: {rating_score}/5

{stars}

### Quality Assessment Results

#### :mag: Summary Analysis
"""

    if summary_success:
        report += ":white_check_mark: AI-powered summary generated successfully\n"
    else:
        report += ":x: Summary generation failed - check AI service connectivity\n"

    report += """
#### :microscope: Code Review Analysis
"""

    if review_success:
        report += ":white_check_mark: Comprehensive AI code review completed\n"
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

    # Rating breakdown
    report += f"""### Scoring Breakdown
| Metric | Status | Impact |
|--------|--------|--------|
| Lines of Code | {loc_data.get('net_lines_of_code_change', 0)} lines | {'Within limits' if loc_data.get('net_lines_of_code_change', 0) <= 500 else '⚠️ Exceeds 500 line limit'} |
| Lint Disables | {lint_data.get('num_lint_disable', 0) if isinstance(lint_data, dict) else 0} new disables | {'No new disables' if (isinstance(lint_data, dict) and lint_data.get('num_lint_disable', 0) == 0) else '⚠️ New lint suppressions added'} |

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

    logger.info("===== STARTING MR ANALYSIS =====")
    logger.info(f"GitLab host configured as: {gitlab.GITLAB_HOST}")
    logger.info(f"Project: {proj}")
    logger.info(f"MR IID: {mriid}")
    try:
        gitlab_token = os.environ.get('GITLAB_ACCESS_TOKEN', '')
        token_available = bool(gitlab_token)
        logger.info(f"Environment check - GITLAB_ACCESS_TOKEN available: {token_available}")
        if token_available:
            logger.info(f"Token starts with: {gitlab_token[:10]}...")
    except Exception as e:
        logger.error(f"Error checking environment: {e}")
        token_available = False
    
    print(f"[{REQUEST_ID_SHORT}] [DEBUG] ===== STARTING MR ANALYSIS =====")
    print(f"[{REQUEST_ID_SHORT}] [DEBUG] Project: {proj}")
    print(f"[{REQUEST_ID_SHORT}] [DEBUG] MR IID: {mriid}")
    print_banner(f"[{REQUEST_ID_SHORT}] Processing MR {mriid} in project {proj}")

    try:
        print(f"[{REQUEST_ID_SHORT}] [DEBUG] Fetching MR data from GitLab API...")
        # Fetch MR data from GitLab
        mr = gitlab.gitlab("/projects/{}/merge_requests/{}".format(proj, mriid))
        print(f"[{REQUEST_ID_SHORT}] [DEBUG] MR fetched successfully: {mr.title}")
        print(f"[{REQUEST_ID_SHORT}] [DEBUG] MR state: {mr.state}")
        print(f"[{REQUEST_ID_SHORT}] [DEBUG] Source branch: {mr.source_branch}")
        print(f"[{REQUEST_ID_SHORT}] [DEBUG] Target branch: {mr.target_branch}")

        print(f"[{REQUEST_ID_SHORT}] [DEBUG] Fetching MR commits...")
        mrcommits = gitlab.gitlab("/projects/{}/merge_requests/{}/commits".format(proj, mr.iid))
        print(f"[{REQUEST_ID_SHORT}] [DEBUG] Found {len(mrcommits)} commits in MR {mriid}")

        for i, commit in enumerate(mrcommits):
            print(f"[DEBUG] Commit {i+1}: {commit.id[:8]} - {commit.title}")

    except Exception as api_error:
        print(f"[DEBUG] GitLab API error: {api_error}")
        print(f"[DEBUG] Error type: {type(api_error).__name__}")
        raise

    # Setup temporary git repository for analysis
    print("[DEBUG] Setting up temporary git repository...")
    with tempfile.TemporaryDirectory() as tdir:
        print(f"[DEBUG] Temporary directory: {tdir}")

        print("[DEBUG] Initializing git repository...")
        subprocess.call(["git", "init", "-q"], cwd=tdir)

        clone_url = gitlab.get_clone_url(proj.replace('%2F', '/'))
        print(f"[DEBUG] Clone URL: {clone_url}")
        print(f"[DEBUG] Target branch: {mr.target_branch}")
        print(f"[DEBUG] Source branch: {mr.source_branch}")
        print(f"[DEBUG] Fetching MR head: merge-requests/{mr.iid}/head and target branch: {mr.target_branch}")

        try:
            # Fetch both MR head and target branch for proper diff
            subprocess.call(["git", "fetch", "-q",
                             "--depth={}".format(max(len(mrcommits), 100)),
                             clone_url,
                             "merge-requests/{}/head".format(mr.iid),
                             "{}:{}".format(mr.target_branch, mr.target_branch)],
                            cwd=tdir)
            print("[DEBUG] Git fetch completed successfully")
        except Exception as fetch_error:
            print(f"[DEBUG] Git fetch failed: {fetch_error}")
            raise

        try:
            subprocess.check_output(["git", "checkout", "-q", "-b", "check", "FETCH_HEAD"], cwd=tdir)
            print("[DEBUG] Git checkout completed successfully")
        except Exception as checkout_error:
            print(f"[DEBUG] Git checkout failed: {checkout_error}")
            raise

        # Create diff file for analysis
        print("[DEBUG] Creating diff file for analysis...")
        diff_file_path = create_diff_from_mr(proj, mriid, tdir, mr, mrcommits)

        if not diff_file_path or not os.path.exists(diff_file_path):
            print("[DEBUG] ERROR: Could not create diff file for analysis")
            # Post error report to GitLab
            error_report = """
## :x: MR Quality Assessment Failed

Unable to generate diff for analysis. This could be due to:
- Empty MR with no changes
- Git repository access issues
- Merge conflicts or other git problems

Please check the MR manually and retry if necessary.
"""
            print("[DEBUG] Posting error report to GitLab...")
            gitlab.update_discussion(proj, mriid, HEADER, error_report, False)
            return

        # Verify diff file content
        try:
            with open(diff_file_path, 'r') as f:
                diff_content = f.read()
                print(f"[DEBUG] Diff file content preview (first 500 chars):")
                print(f"[DEBUG] {diff_content[:500]}...")
        except Exception as read_error:
            print(f"[DEBUG] Could not read diff file: {read_error}")

        # Run analysis pipeline
        print_banner(f"[{REQUEST_ID_SHORT}] Starting Analysis Pipeline")
        print(f"[{REQUEST_ID_SHORT}] [DEBUG] ===== ANALYSIS PIPELINE START =====")

        # 1. Generate AI summary
        print(f"[{REQUEST_ID_SHORT}] [DEBUG] Step 1: Generating AI summary...")
        summary_success, _ = generate_summary(diff_file_path)
        print(f"[{REQUEST_ID_SHORT}] [DEBUG] AI summary result: {'SUCCESS' if summary_success else 'FAILED'}")

        # 2. Generate AI code review
        print(f"[{REQUEST_ID_SHORT}] [DEBUG] Step 2: Generating AI code review...")
        review_success, _ = generate_initial_code_review(diff_file_path)
        print(f"[{REQUEST_ID_SHORT}] [DEBUG] AI code review result: {'SUCCESS' if review_success else 'FAILED'}")

        # 3. Calculate LOC metrics
        print(f"[{REQUEST_ID_SHORT}] [DEBUG] Step 3: Calculating LOC metrics...")
        print_banner(f"[{REQUEST_ID_SHORT}] LOC Analysis")
        loc_calculator = LOCCalculator(diff_file_path)
        loc_success, loc_data = loc_calculator.calculate_loc()
        print(f"[{REQUEST_ID_SHORT}] [DEBUG] LOC analysis result: {'SUCCESS' if loc_success else 'FAILED'}")

        if not loc_success:
            print(f"[DEBUG] LOC analysis failed: {loc_data}")
            loc_data = {'lines_of_code_added': 0, 'lines_of_code_removed': 0, 'net_lines_of_code_change': 0}
        else:
            print(f"[DEBUG] LOC data: {loc_data}")

        # 4. Analyze lint disables
        print(f"[{REQUEST_ID_SHORT}] [DEBUG] Step 4: Analyzing lint disables...")
        lint_success, lint_data = generate_lint_disable_report(diff_file_path)
        print(f"[{REQUEST_ID_SHORT}] [DEBUG] Lint analysis result: {'SUCCESS' if lint_success else 'FAILED'}")

        if not lint_success:
            print(f"[{REQUEST_ID_SHORT}] [DEBUG] Lint analysis failed: {lint_data}")
            lint_data = {'num_lint_disable': 0, 'lints_that_disabled': ''}
        else:
            print(f"[{REQUEST_ID_SHORT}] [DEBUG] Lint data: {lint_data}")

        # 5. Calculate overall rating
        print(f"[{REQUEST_ID_SHORT}] [DEBUG] Step 5: Calculating overall rating...")
        rating_score = cal_rating(
            loc_data.get('net_lines_of_code_change', 0),
            lint_data.get('num_lint_disable', 0) if isinstance(lint_data, dict) else 0
        )
        print(f"[{REQUEST_ID_SHORT}] [DEBUG] Final rating calculated: {rating_score}/5")
        print_banner(f"[{REQUEST_ID_SHORT}] Final Rating: {rating_score}/5")

    # Format report for GitLab
    print(f"[{REQUEST_ID_SHORT}] [DEBUG] Step 6: Formatting report for GitLab...")
    report_body, must_not_be_resolved = format_rating_report(
        summary_success, review_success, loc_data, lint_data, rating_score
    )
    print(f"[{REQUEST_ID_SHORT}] [DEBUG] Report formatted, must_not_be_resolved: {must_not_be_resolved}")

    # Post results to GitLab
    print(f"[{REQUEST_ID_SHORT}] [DEBUG] Step 7: Posting results to GitLab...")
    try:
        gitlab.update_discussion(proj, mriid, HEADER, report_body, must_not_be_resolved)
        print(f"[{REQUEST_ID_SHORT}] [DEBUG] Successfully posted report to GitLab")
    except Exception as gitlab_error:
        print(f"[{REQUEST_ID_SHORT}] [DEBUG] Failed to post to GitLab: {gitlab_error}")
        print(f"[{REQUEST_ID_SHORT}] [DEBUG] Error type: {type(gitlab_error).__name__}")
        raise

    print(f"[{REQUEST_ID_SHORT}] [DEBUG] ===== MR ANALYSIS COMPLETED =====")
    print(f"[{REQUEST_ID_SHORT}] MR quality assessment completed successfully")


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
        except:  # noqa: E722
            pass  # Don't fail on error reporting failure

        sys.exit(1)


if __name__ == '__main__':
    main()
