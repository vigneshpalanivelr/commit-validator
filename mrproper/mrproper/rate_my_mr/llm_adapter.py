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

# Helper for structured logging
class StructuredLog:
    """Lightweight structured logging helper."""
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
            slog.info("Using pre-configured BFA_TOKEN_KEY")
            return self.bfa_token_key

        # Check if we already have a token for this project/MR
        if LLMAdapter._session_token and LLMAdapter._token_project_mr == current_project_mr:
            slog.info("Reusing existing session token", project_mr=current_project_mr)
            return LLMAdapter._session_token

        # Need to get a new token
        if not project_id or not mr_iid:
            raise ValueError("PROJECT_ID and MR_IID environment variables required for JWT token generation")

        subject = f"rate-my-mr-{project_id}-{mr_iid}"
        token_url = f"http://{self.bfa_host}:8000/api/token"

        slog.debug("Requesting JWT token", token_url=token_url, subject=subject)

        try:
            response = requests.post(
                token_url,
                headers={"Content-Type": "application/json"},
                json={"subject": subject},
                timeout=30
            )

            slog.debug("Token API response", status_code=response.status_code)
            response.raise_for_status()

            token_data = response.json()
            token = token_data.get('token')

            if not token:
                raise ValueError(f"Token not found in response: {token_data}")

            # Store token for reuse
            LLMAdapter._session_token = token
            LLMAdapter._token_project_mr = current_project_mr

            slog.info("JWT token acquired successfully",
                      project_mr=current_project_mr,
                      token_prefix=token[:20])

            return token

        except requests.exceptions.RequestException as e:
            slog.error("Failed to acquire JWT token", error=str(e))
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
            slog.warning("BFA API returned non-ok status", status=status)

        # Extract the AI response text from metrics.summary_text
        metrics = response_data.get('metrics', {})
        summary_text = metrics.get('summary_text', '')

        if not summary_text:
            slog.error("No summary_text in BFA response",
                       metrics_keys=list(metrics.keys()),
                       status=status)
            # Return error message to avoid breaking the pipeline
            summary_text = "Error: No AI response received from BFA service"

        # Transform to expected format (compatible with rate_my_mr.py parsing)
        transformed = {
            "content": [
                {
                    "type": "text",
                    "text": summary_text
                }
            ]
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
            url: Override LLM endpoint URL (optional, uses default if not provided)
            max_retries: Override default max_retries (optional)

        Returns:
            tuple: (status_code, response_data) or (None/status_code, error_message)
        """
        max_retries = max_retries or self.max_retries

        # Use provided URL or construct default from BFA_HOST
        if url is None:
            url = f"http://{self.bfa_host}:8000/api/rate-my-mr"

        slog.debug("LLM Adapter request",
                   url=url,
                   timeout_s=self.api_timeout,
                   max_retries=max_retries,
                   payload_size=len(str(payload)))

        # Get or create JWT token
        try:
            token = self._get_or_create_token()
        except Exception as e:
            slog.error("Failed to get JWT token", error=str(e))
            return None, f"JWT token acquisition failed: {str(e)}"

        # Prepare headers with JWT token
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }

        # Transform request payload
        transformed_payload = self._transform_request(payload)

        # Retry loop
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    # Exponential backoff: 2s, 4s, 8s
                    wait_time = 2 ** attempt
                    slog.debug("Retry attempt", attempt=f"{attempt + 1}/{max_retries}", wait_time_s=wait_time)
                    time.sleep(wait_time)

                slog.debug("Sending POST request to LLM API", attempt=f"{attempt + 1}/{max_retries}")

                resp = requests.post(
                    url,
                    json=transformed_payload,
                    headers=headers,
                    timeout=self.api_timeout
                )

                slog.debug("LLM API response", status_code=resp.status_code, content_length=len(resp.content))

                # Raise an error for bad responses (4xx and 5xx)
                resp.raise_for_status()

                # Parse and transform response
                response_data = resp.json()
                slog.debug("LLM API JSON parsed successfully")

                transformed_response = self._transform_response(response_data)

                return resp.status_code, transformed_response

            except requests.exceptions.HTTPError as http_err:
                slog.error("LLM API HTTP error",
                           attempt=f"{attempt + 1}/{max_retries}",
                           status_code=resp.status_code,
                           error=str(http_err))

                # Special handling for authentication errors
                if resp.status_code == 401:
                    slog.error("JWT token authentication failed", status_code=401)
                    # Clear cached token so next call will get a new one
                    LLMAdapter._session_token = None
                    LLMAdapter._token_project_mr = None

                # Don't retry on 4xx client errors (except 429 rate limit)
                if 400 <= resp.status_code < 500 and resp.status_code != 429:
                    slog.debug("Client error, not retrying", status_code=resp.status_code)
                    return resp.status_code, str(http_err)

                # Retry on 5xx server errors and 429 rate limit
                if attempt == max_retries - 1:
                    return resp.status_code, str(http_err)

            except requests.exceptions.ConnectionError as conn_err:
                slog.error("LLM API connection error", attempt=f"{attempt + 1}/{max_retries}", error=str(conn_err))
                if attempt == max_retries - 1:
                    slog.error("All attempts failed - LLM API not reachable", max_retries=max_retries)
                    return None, f"Connection failed after {max_retries} attempts: {str(conn_err)}"

            except requests.exceptions.Timeout as timeout_err:
                slog.error("LLM API timeout", attempt=f"{attempt + 1}/{max_retries}", error=str(timeout_err))
                if attempt == max_retries - 1:
                    slog.error("All attempts timed out", max_retries=max_retries)
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
                           error_type=type(err).__name__)
                if attempt == max_retries - 1:
                    return None, str(err)

        # Should not reach here, but just in case
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
