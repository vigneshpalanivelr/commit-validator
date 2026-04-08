"""
LLM API Adapter with JWT Authentication

This adapter handles communication with the intermediary LLM service that requires
JWT token authentication. The token is obtained once per validation session and
reused for all AI calls (typically 4 calls per MR validation).

Environment Variables:
- BFA_HOST: Hostname for the BFA service (required)
- BFA_TOKEN_KEY: Pre-configured JWT token (optional, skips token API if set)
- API_TIMEOUT: Timeout in seconds for API calls (default: 120)
- PROJECT_ID: Project identifier for JWT subject (set by rate_my_mr_gitlab.py)
- MR_IID: MR IID for JWT subject (set by rate_my_mr_gitlab.py)

Token Authentication Flow:
1. Check if BFA_TOKEN_KEY is set → use it directly
2. Otherwise, call POST http://{BFA_HOST}:8000/api/token
   with payload: {"subject": "rate-my-mr-<project_id>-<mr_iid>"}
3. Extract token from response: {"token": "<jwt_token>"}
4. Store token for reuse across all 4 AI calls in this session

LLM Endpoint:
- POST http://{BFA_HOST}:8000/api/rate-my-mr
- Headers: Authorization: Bearer {token}

Request/Response Format:
- Currently assumes same format as old API (may need adjustment)
- Request: {"messages": [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]}
- Response: {"content": [{"type": "text", "text": "..."}]}
- TODO: Update transformation methods when actual format is provided

Created: 2025-11-04
"""

import os
import requests
import time
import logging
import json

logger = logging.getLogger(__name__)

# Helper for structured logging — uses the shared formatter so the message
# column stays aligned with every other log source in the project.
from .logging_config import format_structured_message as _fmt_msg


class StructuredLog:
    @staticmethod
    def debug(msg, **kwargs):
        logger.debug(_fmt_msg(msg, **kwargs))

    @staticmethod
    def info(msg, **kwargs):
        logger.info(_fmt_msg(msg, **kwargs))

    @staticmethod
    def warning(msg, **kwargs):
        logger.warning(_fmt_msg(msg, **kwargs))

    @staticmethod
    def error(msg, **kwargs):
        logger.error(_fmt_msg(msg, **kwargs))

slog = StructuredLog


class LLMAdapter:
    """
    Adapter for intermediary LLM API service with JWT authentication.
    Handles token management and request/response transformation.
    """

    # Class variable to store token across all instances in this session
    _session_token = None
    _token_project_mr = None  # Track which project/MR this token is for

    def __init__(self):
        """Initialize adapter with configuration from environment."""
        self.bfa_host = os.environ.get('BFA_HOST')
        self.bfa_token_key = os.environ.get('BFA_TOKEN_KEY', '')
        self.api_timeout = int(os.environ.get('API_TIMEOUT', '120'))
        self.max_retries = 3

        # Validate configuration
        if not self.bfa_host:
            raise ValueError("BFA_HOST environment variable is required")

        slog.info("LLM Adapter initialized",
                  bfa_host=self.bfa_host,
                  timeout_s=self.api_timeout,
                  token_preconfigured=bool(self.bfa_token_key))

    def _get_project_and_mr(self):
        """Get project and MR IID from environment."""
        project_id = os.environ.get('PROJECT_ID', '')
        mr_iid = os.environ.get('MR_IID', '')

        if not project_id or not mr_iid:
            slog.warning("PROJECT_ID or MR_IID not set in environment",
                         project_id=project_id,
                         mr_iid=mr_iid)
            return None, None

        return project_id, mr_iid

    def _get_or_create_token(self):
        """
        Get JWT token for this validation session.
        Token is obtained once and reused for all 4 AI calls.

        Returns:
            str: JWT token

        Raises:
            Exception: If token acquisition fails
        """
        project_id, mr_iid = self._get_project_and_mr()
        current_project_mr = f"{project_id}-{mr_iid}"

        # If token is pre-configured, use it
        if self.bfa_token_key:
            slog.info("Token: using pre-configured BFA_TOKEN_KEY",
                      token_length=len(self.bfa_token_key))
            return self.bfa_token_key

        # Check if we already have a token for this project/MR
        if LLMAdapter._session_token and LLMAdapter._token_project_mr == current_project_mr:
            slog.info("Token: reusing session token", project_mr=current_project_mr)
            return LLMAdapter._session_token

        # Need to get a new token
        if not project_id or not mr_iid:
            slog.error("Missing required environment variables for token generation",
                       project_id=project_id,
                       mr_iid=mr_iid)
            raise ValueError("PROJECT_ID and MR_IID environment variables required for JWT token generation")

        subject = f"rate-my-mr-{project_id}-{mr_iid}"
        token_url = f"http://{self.bfa_host}:8000/api/token"
        request_payload = {"subject": subject}

        try:
            response = requests.post(
                token_url,
                headers={"Content-Type": "application/json"},
                json=request_payload,
                timeout=30
            )
            response.raise_for_status()
            token_data = response.json()

            token = token_data.get('token')
            if not token:
                slog.error("Token not found in response",
                           response_data=json.dumps(token_data),
                           available_keys=list(token_data.keys()))
                raise ValueError(f"Token not found in response: {token_data}")

            # Store token for reuse
            LLMAdapter._session_token = token
            LLMAdapter._token_project_mr = current_project_mr

            slog.info("Token: acquired from BFA",
                      project_mr=current_project_mr,
                      token_length=len(token))
            return token

        except requests.exceptions.ConnectionError as conn_err:
            slog.error("Token API connection error - service may be down",
                       token_url=token_url,
                       error=str(conn_err),
                       error_type=type(conn_err).__name__)
            raise
        except requests.exceptions.Timeout as timeout_err:
            slog.error("Token API timeout after 30 seconds",
                       token_url=token_url,
                       error=str(timeout_err))
            raise
        except requests.exceptions.HTTPError as http_err:
            slog.error("Token API HTTP error",
                       token_url=token_url,
                       status_code=response.status_code,
                       response_text=response.text,
                       error=str(http_err))
            raise
        except requests.exceptions.RequestException as e:
            slog.error("Failed to acquire JWT token",
                       token_url=token_url,
                       error=str(e),
                       error_type=type(e).__name__)
            raise
        except json.JSONDecodeError as json_err:
            slog.error("Token API response is not valid JSON",
                       token_url=token_url,
                       response_text=response.text,
                       error=str(json_err))
            raise

    def _transform_request(self, payload):
        """
        Transform request from current format to new BFA API format.

        Current format:
        {
            "messages": [
                {"role": "system", "content": "..."},
                {"role": "user", "content": "..."}
            ]
        }

        New BFA API format:
        {
            "repo": "my-org/my-project",
            "branch": "feature/new-parser",
            "author": "vishal@internal.com",
            "commit": "abc123def456",
            "mr_url": "https://git.internal.com/my-org/my-project/merge_requests/42",
            "prompt": "{\"messages\": [...]}"  # JSON string, not object
        }

        Args:
            payload: Original request payload dict

        Returns:
            dict: Transformed payload for new BFA API
        """
        # Extract metadata from environment (set by rate_my_mr_gitlab.py)
        repo = os.environ.get('MR_REPO', 'unknown')
        branch = os.environ.get('MR_BRANCH', 'unknown')
        author = os.environ.get('MR_AUTHOR', 'unknown@example.com')
        commit = os.environ.get('MR_COMMIT', 'unknown')
        mr_url = os.environ.get('MR_URL', 'unknown')

        # Convert payload dict to JSON string (BFA API expects prompt as JSON string)
        prompt_json_string = json.dumps(payload)

        # Construct new BFA API format
        new_payload = {
            "repo": repo,
            "branch": branch,
            "author": author,
            "commit": commit,
            "mr_url": mr_url,
            "prompt": prompt_json_string  # JSON string, not dict
        }

        slog.debug("Request transformed to BFA format",
                   repo=repo,
                   branch=branch,
                   commit=commit[:8] if commit != 'unknown' else 'unknown',
                   prompt_length=len(prompt_json_string))

        return new_payload

    def _transform_response(self, response_data):
        """
        Transform response from BFA API format to expected format.

        BFA API response format:
        {
            "status": "ok",
            "repo": "my-org/my-project",
            "branch": "feature/new-parser",
            "commit": "abc123",
            "author": "vishal@internal.com",
            "metrics": {
                "summary_text": "AI generated response text..."
            },
            "sent_to": "user not found in slack directory!"
        }

        Expected format (for backward compatibility with rate_my_mr.py):
        {
            "content": [
                {"type": "text", "text": "AI generated response text..."}
            ]
        }

        Args:
            response_data: Raw response from BFA API

        Returns:
            dict: Transformed response in expected format
        """
        # Check response status
        status = response_data.get('status', 'unknown')

        if status != 'ok':
            slog.warning("BFA API returned non-ok status",
                         status=status,
                         full_response=json.dumps(response_data)[:500])

        # Extract the AI response from the metrics field.
        # The BFA API returns a structured metrics object with fields like:
        #   overall_summary, potential_vulnerabilities, recommended_improvements,
        #   quality_score, security_score, maintainability_score,
        #   num_lint_disable, lints_that_disabled
        # Legacy contract used metrics.summary_text (kept as fallback).
        metrics = response_data.get('metrics', {}) or {}

        def _as_list(val):
            if val is None:
                return []
            if isinstance(val, list):
                return [str(v) for v in val if v is not None]
            return [str(val)]

        summary_text = metrics.get('summary_text') or ''

        # New schema: assemble a human-readable text block from structured fields
        if not summary_text:
            parts = []
            overall = metrics.get('overall_summary')
            if overall:
                parts.append(str(overall).strip())

            vulns = _as_list(metrics.get('potential_vulnerabilities'))
            if vulns:
                parts.append("**Potential Vulnerabilities:**\n" +
                             "\n".join(f"- {v}" for v in vulns))

            improvements = _as_list(metrics.get('recommended_improvements'))
            if improvements:
                parts.append("**Recommended Improvements:**\n" +
                             "\n".join(f"- {v}" for v in improvements))

            score_bits = []
            for key, label in (('quality_score', 'Quality'),
                               ('security_score', 'Security'),
                               ('maintainability_score', 'Maintainability')):
                if metrics.get(key) is not None:
                    score_bits.append(f"{label}: {metrics.get(key)}/10")
            if score_bits:
                parts.append("**Scores:** " + " | ".join(score_bits))

            summary_text = "\n\n".join(parts).strip()

        if not summary_text:
            slog.error("No usable content in BFA response",
                       metrics_keys=list(metrics.keys()),
                       metrics_content=json.dumps(metrics)[:200],
                       status=status,
                       full_response=json.dumps(response_data)[:1000])
            # Return an empty-content structure so the caller marks this step
            # as failed instead of producing a fake-success report entry.
            return {
                "content": [],
                "error": "No usable content in BFA response",
                "metrics": metrics,
                "bfa_status": status,
            }

        # Transform to expected format (compatible with rate_my_mr.py parsing).
        # Also expose the raw metrics dict so callers can consume structured
        # fields (e.g. num_lint_disable) without re-parsing text.
        transformed = {
            "content": [
                {
                    "type": "text",
                    "text": summary_text
                }
            ],
            "metrics": metrics,
            "bfa_status": status,
        }

        slog.debug("Response transformed from BFA format",
                   text_length=len(summary_text),
                   status=status)
        return transformed

    def send_request(self, payload, url=None, max_retries=None):
        """
        Send request to intermediary LLM API with JWT authentication and retry logic.

        Args:
            payload: Request payload (in current format)
            url: IGNORED - kept for backward compatibility, BFA endpoint is always used
            max_retries: Override default max_retries (optional)

        Returns:
            tuple: (status_code, response_data) or (None/status_code, error_message)
        """
        max_retries = max_retries or self.max_retries

        # ALWAYS use BFA API endpoint - ignore any passed URL (legacy parameter)
        # The passed URL is from legacy direct connection mode and should not be used
        bfa_url = f"http://{self.bfa_host}:8000/api/rate-my-mr"

        if url and url != bfa_url:
            slog.warning("Ignoring legacy URL parameter, using BFA endpoint instead",
                         legacy_url=url,
                         bfa_url=bfa_url)

        slog.info("LLM adapter request",
                  url=bfa_url, max_retries=max_retries,
                  payload_size=len(str(payload)))

        # 1. Get or create JWT token
        try:
            token = self._get_or_create_token()
        except Exception as e:
            slog.error("JWT token acquisition failed",
                       error=str(e), error_type=type(e).__name__)
            return None, f"JWT token acquisition failed: {str(e)}"

        # 2. Prepare headers with JWT token
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }

        # 3. Transform request payload
        transformed_payload = self._transform_request(payload)

        # 4. Retry loop: POST -> parse JSON -> transform response
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    # Exponential backoff: 2s, 4s, 8s
                    wait_time = 2 ** attempt
                    slog.info("Retrying after backoff",
                              attempt=f"{attempt + 1}/{max_retries}",
                              wait_time_s=wait_time)
                    time.sleep(wait_time)

                request_start_time = time.time()
                resp = requests.post(
                    bfa_url,
                    json=transformed_payload,
                    headers=headers,
                    timeout=self.api_timeout
                )
                request_duration = time.time() - request_start_time

                slog.info("LLM API response received",
                          status_code=resp.status_code,
                          content_length=len(resp.content),
                          response_time_s=f"{request_duration:.2f}")

                # Raise an error for bad responses (4xx and 5xx)
                resp.raise_for_status()

                # Parse and transform response
                try:
                    response_data = resp.json()
                except json.JSONDecodeError as json_err:
                    slog.error("Failed to parse JSON response",
                               response_text=resp.text[:500],
                               error=str(json_err))
                    return resp.status_code, f"Invalid JSON response: {str(json_err)}"

                transformed_response = self._transform_response(response_data)
                return resp.status_code, transformed_response

            except requests.exceptions.HTTPError as http_err:
                slog.error("LLM API HTTP error",
                           attempt=f"{attempt + 1}/{max_retries}",
                           status_code=resp.status_code,
                           response_text=resp.text[:500],
                           response_headers=dict(resp.headers),
                           error=str(http_err))

                # Special handling for authentication errors
                if resp.status_code == 401:
                    slog.error("JWT token authentication failed - token may be invalid or expired",
                               status_code=401,
                               token_prefix=token[:20] if len(token) > 20 else "***")
                    # Clear cached token so next call will get a new one
                    LLMAdapter._session_token = None
                    LLMAdapter._token_project_mr = None

                # Don't retry on 4xx client errors (except 429 rate limit)
                if 400 <= resp.status_code < 500 and resp.status_code != 429:
                    slog.error("Client error - not retrying",
                               status_code=resp.status_code,
                               response_body=resp.text)
                    return resp.status_code, str(http_err)

                # Retry on 5xx server errors and 429 rate limit
                if attempt == max_retries - 1:
                    slog.error("All retries exhausted",
                               max_retries=max_retries,
                               final_status_code=resp.status_code)
                    return resp.status_code, str(http_err)

            except requests.exceptions.ConnectionError as conn_err:
                slog.error("LLM API connection error - service may be unreachable",
                           attempt=f"{attempt + 1}/{max_retries}",
                           url=bfa_url,
                           error=str(conn_err),
                           error_type=type(conn_err).__name__)
                if attempt == max_retries - 1:
                    slog.error("All attempts failed - LLM API not reachable",
                               max_retries=max_retries,
                               url=bfa_url)
                    return None, f"Connection failed after {max_retries} attempts: {str(conn_err)}"

            except requests.exceptions.Timeout as timeout_err:
                slog.error("LLM API timeout - request took too long",
                           attempt=f"{attempt + 1}/{max_retries}",
                           timeout_s=self.api_timeout,
                           error=str(timeout_err))
                if attempt == max_retries - 1:
                    slog.error("All attempts timed out",
                               max_retries=max_retries,
                               timeout_s=self.api_timeout)
                    return None, f"Timeout after {max_retries} attempts: {str(timeout_err)}"

            except requests.exceptions.RequestException as req_err:
                slog.error("LLM API request error",
                           attempt=f"{attempt + 1}/{max_retries}",
                           error=str(req_err),
                           error_type=type(req_err).__name__)
                if attempt == max_retries - 1:
                    return None, str(req_err)

            except Exception as err:
                slog.error("LLM API unexpected error",
                           attempt=f"{attempt + 1}/{max_retries}",
                           error=str(err),
                           error_type=type(err).__name__,
                           traceback=True)
                if attempt == max_retries - 1:
                    return None, str(err)

        # Should not reach here, but just in case
        slog.error("Request failed after all retries", max_retries=max_retries)
        return None, f"Failed after {max_retries} attempts"


# Singleton instance for this session
_adapter_instance = None


def get_adapter():
    """
    Get or create the LLM adapter singleton instance.

    Returns:
        LLMAdapter: Shared adapter instance for this session
    """
    global _adapter_instance
    if _adapter_instance is None:
        _adapter_instance = LLMAdapter()
    return _adapter_instance


def send_request(payload, url=None, max_retries=3):
    """
    Send request to LLM API through the adapter.
    This function maintains backward compatibility with the old send_request API.

    Args:
        payload: Request payload
        url: Override URL (optional, uses BFA_HOST-based URL if not provided)
        max_retries: Maximum retry attempts (default: 3)

    Returns:
        tuple: (status_code, response_data) or (None/status_code, error_message)
    """
    adapter = get_adapter()
    return adapter.send_request(payload, url, max_retries)
