import requests
import argparse
from prettytable import PrettyTable
import re
import json
import os
import time
import logging
from .loc import LOCCalculator
from .params import RMMConstants, RMMWeights, RMMLimits, get_all_applicable_checks
from .cyclomatic_complexity import CyclomaticComplexityCalculator
from .security_scan import SecurityScanner
from .cal_rating import CalRating

# Import LLM adapter for new API integration
try:
    from . import llm_adapter
    HAS_LLM_ADAPTER = True
except ImportError:
    HAS_LLM_ADAPTER = False

# Get logger (will use the logger set up by rate_my_mr_gitlab.py)
logger = logging.getLogger(__name__)

# Helper for structured logging
class StructuredLog:
    """Lightweight structured logging helper that uses module logger."""
    @staticmethod
    def _fmt(msg, **kwargs):
        if kwargs:
            fields = ' '.join(f'{k}={v}' for k, v in kwargs.items())
            return f'{msg} | {fields}'
        return msg

    @staticmethod
    def debug(msg, **kwargs):
        logger.debug(StructuredLog._fmt(msg, **kwargs))

    @staticmethod
    def info(msg, **kwargs):
        logger.info(StructuredLog._fmt(msg, **kwargs))

    @staticmethod
    def warning(msg, **kwargs):
        logger.warning(StructuredLog._fmt(msg, **kwargs))

    @staticmethod
    def error(msg, **kwargs):
        logger.error(StructuredLog._fmt(msg, **kwargs))

slog = StructuredLog


def print_banner(title):
    banner = "=" * 90  # Adjust the length as needed
    print(f"{banner}\n{title.center(90)}\n{banner}")


def send_request(payload, url=RMMConstants.agent_url.value, max_retries=3):
    """
    Send request to AI service with retry logic.

    Routing priority:
    1. BFA_HOST (new LLM adapter with JWT) - if set, always use this
    2. AI_SERVICE_URL (legacy direct connection) - only if BFA_HOST not set

    Args:
        payload: JSON payload to send
        url: AI service URL (used only in legacy mode)
        max_retries: Maximum number of retry attempts (default: 3)

    Returns:
        tuple: (status_code, response_json) or (None/status_code, error_message)
    """
    slog.info("=" * 50)
    slog.info("=== SEND REQUEST CALLED ===")
    slog.info("=" * 50)

    # Check routing: BFA_HOST takes priority over AI_SERVICE_URL
    bfa_host = os.environ.get('BFA_HOST')
    ai_service_url = os.environ.get('AI_SERVICE_URL')
    use_adapter = HAS_LLM_ADAPTER and bfa_host

    slog.debug("AI Service routing decision",
               HAS_LLM_ADAPTER=HAS_LLM_ADAPTER,
               BFA_HOST=bfa_host if bfa_host else 'NOT_SET',
               AI_SERVICE_URL=ai_service_url if ai_service_url else 'NOT_SET',
               use_adapter=use_adapter,
               url_provided=url)

    if use_adapter:
        slog.info("Routing to NEW LLM adapter (BFA_HOST configured)",
                  bfa_host=bfa_host,
                  note="BFA_HOST takes priority over AI_SERVICE_URL")
        result = llm_adapter.send_request(payload, url, max_retries)
        slog.info("LLM adapter returned",
                  status_code=result[0],
                  response_type=type(result[1]).__name__)
        return result

    # Legacy direct connection (only if BFA_HOST not set)
    slog.info("Routing to LEGACY direct AI service connection",
              url=url,
              reason="BFA_HOST not set")
    slog.debug("Legacy connection parameters",
               url=url,
               payload_size=len(str(payload)),
               timeout=120,
               max_retries=max_retries)

    for attempt in range(max_retries):
        try:
            if attempt > 0:
                # Exponential backoff: 2s, 4s, 8s
                wait_time = 2 ** attempt
                slog.debug("Retry attempt", attempt=f"{attempt + 1}/{max_retries}", wait_time_s=wait_time)
                time.sleep(wait_time)

            slog.debug("Sending POST request to AI service", attempt=f"{attempt + 1}/{max_retries}")
            resp = requests.post(url, json=payload, timeout=120)
            slog.debug("AI Service response", status_code=resp.status_code, content_length=len(resp.content))

            # Raise an error for bad responses (4xx and 5xx)
            resp.raise_for_status()

            response_json = resp.json()
            slog.debug("AI Service JSON parsed successfully")
            return resp.status_code, response_json

        except requests.exceptions.HTTPError as http_err:
            slog.error("AI Service HTTP error",
                       attempt=f"{attempt + 1}/{max_retries}",
                       status_code=resp.status_code,
                       error=str(http_err))

            # Don't retry on 4xx client errors (except 429 rate limit)
            if 400 <= resp.status_code < 500 and resp.status_code != 429:
                slog.debug("Client error, not retrying", status_code=resp.status_code)
                return resp.status_code, str(http_err)

            # Retry on 5xx server errors and 429 rate limit
            if attempt == max_retries - 1:
                return resp.status_code, str(http_err)

        except requests.exceptions.ConnectionError as conn_err:
            slog.error("AI Service connection error", attempt=f"{attempt + 1}/{max_retries}", error=str(conn_err))
            if attempt == max_retries - 1:
                slog.error("All attempts failed - AI service not reachable", max_retries=max_retries)
                return None, f"Connection failed after {max_retries} attempts: {str(conn_err)}"

        except requests.exceptions.Timeout as timeout_err:
            slog.error("AI Service timeout", attempt=f"{attempt + 1}/{max_retries}", error=str(timeout_err))
            if attempt == max_retries - 1:
                slog.error("All attempts timed out", max_retries=max_retries)
                return None, f"Timeout after {max_retries} attempts: {str(timeout_err)}"

        except requests.exceptions.RequestException as req_err:
            slog.error("AI Service request error",
                       attempt=f"{attempt + 1}/{max_retries}",
                       error=str(req_err),
                       error_type=type(req_err).__name__)
            if attempt == max_retries - 1:
                return None, str(req_err)

        except Exception as err:
            slog.error("AI Service unexpected error",
                       attempt=f"{attempt + 1}/{max_retries}",
                       error=str(err),
                       error_type=type(err).__name__)
            if attempt == max_retries - 1:
                return None, str(err)

    # Should not reach here, but just in case
    return None, f"Failed after {max_retries} attempts"


def generate_summary(file_path):
    # parser = argparse.ArgumentParser(
    #     description="Test Claude microservice with messages and optional thinking"
    # )
    # # Use parse_known_args so we can ignore Jupyter's '-f' if accidentally run in notebook
    # args, _ = parser.parse_known_args()
    # url = args.url if hasattr(args, 'url') else "http://10.31.88.29:6006/generate"

    # Read the git diff output from a file
    with open(file_path, 'r') as file:
        diff_output = file.read()
    payload1 = {
        "messages": [
            {"role": "system", "content": "You are a summarizer. Provide a concise summary of the git diff output."},
            {"role": "user", "content": diff_output}
        ]
    }
    # return send_request(url, payload1)
    status_code, code_summary = send_request(payload1)
    print_banner("Summary of the Merge Request")
    if status_code != 200:
        print(f"Failed to generate summary: {code_summary}")
        return False, code_summary
    else:
        try:
            content = code_summary.get('content')[0]
            content_type = content.get('type')
            content_body = content.get(content_type)
            print(content_body)
            print("\n")
            return True, content_body
        except (KeyError, IndexError, TypeError) as e:
            print(f"Failed to parse AI response: {e}")
            return False, str(e)

def generate_initial_code_review(file_path):
    with open(file_path, 'r') as file:
        diff_output = file.read()
    payload1 = {
        "messages": [
            {"role": "system", "content": ("You are a code reviewer tasked with evaluating the following code. Please analyze it thoroughly and provide detailed feedback, focusing on the following aspects:"
                                           "Bugs: Identify any potential bugs or logical errors in the code."
                                           "Code Quality: Suggest improvements for code readability, maintainability, and adherence to best practices."
                                           "Security Concerns: Highlight any security vulnerabilities or risks present in the code."
                                           "Performance: Point out any inefficiencies or areas where performance could be optimized."
                                           "Please provide specific examples from the code to support your comments and suggestions"
                                           )},
            {"role": "user", "content": diff_output}
        ]
    }
    # return send_request(url, payload1)
    print_banner("Initial Review")
    status_code, initial_review = send_request(payload1)
    if status_code != 200:
        print(f"Failed to generate code review: {initial_review}")
        return False, initial_review
    else:
        try:
            content = initial_review.get('content')[0]
            content_type = content.get('type')
            content_body = content.get(content_type)
            print(content_body)
            print("\n")
            return True, content_body
        except (KeyError, IndexError, TypeError) as e:
            print(f"Failed to parse AI response: {e}")
            return False, str(e)

def generate_lint_disable_report(file_path):
    try:
        with open(file_path, 'r') as file:
            diff_output = file.read()
        payload1 = {
            "messages": [
                {"role": "system", "content": ("Please analyze the following git diff output and extract all instances of # pylint: disable= comments. For each instance, provide a summary that includes:"
                                            "The specific pylint checks being disabled."
                                            "The lines of code they are associated with."
                                            "Any context or reasoning for why these disables might have been implemented."
                                            "Additionally, please count and report the total number of instances where pylint disables have been applied in this diff"
                                            "lines starts with single + is added and single - is removed"
                                            "nulliify if same is removed and added in another place for same function"
                                            "Also give report only added lints in json {\"num_lint_disable\": <number>, \"lints_that_disabled\":lints that disabled in commaseparated}")},
                {"role": "user", "content": diff_output}
            ]
        }
        status_code, lint_disbale = send_request(payload1)
        print_banner("Lint Disable report")
        if status_code != 200:
            print(f"Failed to generate lint disable report: {lint_disbale}")
        else:
            content = lint_disbale.get('content')[0]
            content_type = content.get('type')
            content_body = content.get(content_type)
            pattern = r'\{[^{}]*"num_lint_disable":\s*(\d+),\s*"lints_that_disabled":\s*"([^"]*)"[^{}]*\}'
            print(content_body)
            match = re.search(pattern, content_body)
            json_data = {}
            # Check if a match was found and print the result
            if match:
                json_data = match.group(0)
                json_data = json.loads(json_data)
                return True, json_data
            return False, "No data is available"
    except Exception as err:
        return False, str(err)


def generate_added_code_file(diff_file_path: str):
    """
    Calls LLM API with diff file and gets valid Python file containing:
    - Entirely new methods (as-is).
    - Loose added statements wrapped in __bandit_dummy__().
    """
    try:
        with open(diff_file_path, "r") as f:
            diff_output = f.read()

        payload = {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are given a git diff file content. Your task is to extract only the newly added code "
                        "from the diff and generate a valid Python file for Bandit scanning.\n\n"
                        "Rules:\n"
                        "1. Lines starting with '+' are additions. Ignore '-' lines and unchanged context lines (starting with ' ').\n"
                        "2. If an entirely new function or method is added (lines starting with 'def ...' and all subsequent '+' lines), include "
                        "the full function body exactly as shown, including docstrings, comments (e.g., pylint directives), and original indentation (after stripping '+').\n"
                        "3. If added lines are not part of a new function:\n"
                        "   - Strip their indentation (remove leading spaces after '+').\n"
                        "   - Wrap them under a dummy function called:\n"
                        "       def __bandit_dummy__():\n"
                        "           <added lines>\n"
                        "4. If any new function or added line uses 'self':\n"
                        "   - Place all such code inside a dummy class:\n"
                        "       class __BanditTmp__:\n"
                        "           def __init__(self):\n"
                        "               class DummyLogger:\n"
                        "                   def info(self, msg): pass\n"
                        "                   def warning(self, msg): pass\n"
                        "               self.logger = DummyLogger()\n"
                        "           def <method>(self, ...):\n"
                        "               ...\n"
                        "   - Non-method added lines that reference 'self' should be inside:\n"
                        "       def __dummy__(self):\n"
                        "           <added lines>\n"
                        "5. For any undefined variables (e.g., found_primary_disk_size, host_allocated_disk_gb) in the dummy function:\n"
                        "   - Add placeholder definitions at the start of __bandit_dummy__() or __dummy__(self):\n"
                        "       undefined_var = 0\n"
                        "   - Place these before other lines to avoid NameError.\n"
                        "6. Preserve all comments, including pylint directives (e.g., '# pylint: disable=...'), in their original positions.\n"
                        "7. Every function (real or dummy) must end with a valid statement, e.g., `return None`, to avoid dangling code.\n"
                        "8. Do not include markdown formatting (e.g., ```python or ```). Output only valid Python code.\n"
                        "9. Ensure the final file is valid Python syntax (AST-parsable) and can be scanned by Bandit.\n"
                        "10. Before returning, internally verify that `ast.parse(output)` succeeds. If it fails, adjust the output (e.g., add placeholders) to make it parseable.\n"
                        "11. Exclude docstring fragments like '@param' or '@return' unless they are part of a complete docstring in a new method.\n\n"
                        "Output only the extracted Python code, with no explanations or markdown fences."
                    ),
                },
                {"role": "user", "content": diff_output},
            ]
        }
        status_code, response = send_request(payload)

        if status_code != 200:
            return False, f"API call failed: {response}"

        # Extract assistant message
        content = response.get("content")[0]
        content_type = content.get("type")
        python_code = content.get(content_type, "").strip()
        # print("**"*9)
        # print(python_code)

        if not python_code:
            return False, "No Python code returned from LLM"

        # Always generate new file in current working directory
        out_file = os.path.join(os.getcwd(), "added_code_output.py")
        with open(out_file, "w") as f:
            f.write(python_code)

        return True, out_file

    except Exception as e:
        return False, str(e)

def cal_loc(file_path):
    print_banner("LOC Summary")
    loc_cal = LOCCalculator(file_path)
    return loc_cal.calculate_loc()


def cal_cc(file_path):
    print_banner("CC Summary")
    cc_cal = CyclomaticComplexityCalculator(file_path)
    return cc_cal.analyze()

def cal_ss(file_path):
    print_banner("Security Scan Summary")
    ok, result = generate_added_code_file(file_path)
    if ok:
        ss_cal = SecurityScanner(result)
        print(ss_cal.analyze())
        return ss_cal.analyze()


def cal_rating(net_loc, lint_disable_count):
    """
    Simple rating calculation function for GitLab integration.

    This is a lightweight version used for real-time MR validation.
    For more comprehensive analysis including cyclomatic complexity and
    security scanning, see CalRating class in cal_rating.py (currently
    not used in GitLab webhook mode due to execution time constraints).

    Args:
        net_loc: Net lines of code change (added - removed)
        lint_disable_count: Number of new lint disable statements

    Returns:
        int: Rating score from 0 to 5

    Scoring:
        - Start with 5 points (perfect score)
        - Deduct 1 point if net LOC > 500 (too large)
        - Deduct 1 point if lint_disable_count > 0 (code smell)
        - Minimum score: 0
        - Score < 3: MR should be blocked for review
    """
    score = 5  # Start with perfect score

    # Deduct for high LOC
    if net_loc > 500:
        score -= 1

    # Deduct for lint disables
    if lint_disable_count > 0:
        score -= 1

    return max(score, 0)  # Don't go below 0

def main():
    parser = argparse.ArgumentParser(
        description="Rate my MR required parameters"
    )
    parser.add_argument('filename', type=str, help='The name of the file to process')
    args, _ = parser.parse_known_args()
    all_checks = get_all_applicable_checks()
    # print(all_checks)
    checks_func_map = {
        "MR_SUMMARY": generate_summary,
        "INITIAL_REVIEW": generate_initial_code_review,
        "LINT_DISABLE": generate_lint_disable_report,
        "MAX_LOC": cal_loc,
        "CYCLOMATIC_COMPLEXITY": cal_cc,
        "SECURITY_SCAN": cal_ss
    }

    collected_data = {}

    for check, func in checks_func_map.items():
        # print(check)
        if check in all_checks:
            success, result = func(args.filename)
            # print(success)
            # print(result)
            if not success:
                print(f"Failed to execute {check}: {result}")
            collected_data[check] = result
    # print("@"*100)
    # print(collected_data)
    cal_rating_obj = CalRating(collected_data)
    cal_rating_obj.cal_rating()


if __name__ == "__main__":
    main()
