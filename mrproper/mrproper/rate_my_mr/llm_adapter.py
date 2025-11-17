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

        slog.debug("Token acquisition started",
                   project_id=project_id,
                   mr_iid=mr_iid,
                   current_project_mr=current_project_mr)

        # If token is pre-configured, use it
        if self.bfa_token_key:
            slog.info("Using pre-configured BFA_TOKEN_KEY",
                      token_length=len(self.bfa_token_key),
                      token_prefix=self.bfa_token_key[:20] if len(self.bfa_token_key) > 20 else "***")
            return self.bfa_token_key

        # Check if we already have a token for this project/MR
        if LLMAdapter._session_token and LLMAdapter._token_project_mr == current_project_mr:
            slog.info("Reusing existing session token",
                      project_mr=current_project_mr,
                      token_length=len(LLMAdapter._session_token))
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

        slog.info("=== TOKEN ACQUISITION START ===")
        slog.debug("Token API request details",
                   token_url=token_url,
                   subject=subject,
                   request_payload=json.dumps(request_payload))

        try:
            slog.debug("Sending POST request to token endpoint", url=token_url)
            response = requests.post(
                token_url,
                headers={"Content-Type": "application/json"},
                json=request_payload,
                timeout=30
            )

            slog.debug("Token API raw response",
                       status_code=response.status_code,
                       headers=dict(response.headers),
                       content_length=len(response.content),
                       response_text=response.text[:500] if len(response.text) > 500 else response.text)

            response.raise_for_status()

            token_data = response.json()
            slog.debug("Token API JSON response", response_keys=list(token_data.keys()))

            token = token_data.get('token')

            if not token:
                slog.error("Token not found in response",
                           response_data=json.dumps(token_data),
                           available_keys=list(token_data.keys()))
                raise ValueError(f"Token not found in response: {token_data}")

            # Store token for reuse
            LLMAdapter._session_token = token
            LLMAdapter._token_project_mr = current_project_mr

            slog.info("=== TOKEN ACQUISITION SUCCESS ===",
                      project_mr=current_project_mr,
                      token_length=len(token),
                      token_prefix=token[:20] if len(token) > 20 else "***")

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
        slog.debug("=== REQUEST TRANSFORMATION START ===")

        # Extract metadata from environment (set by rate_my_mr_gitlab.py)
        repo = os.environ.get('MR_REPO', 'unknown')
        branch = os.environ.get('MR_BRANCH', 'unknown')
        author = os.environ.get('MR_AUTHOR', 'unknown@example.com')
        commit = os.environ.get('MR_COMMIT', 'unknown')
        mr_url = os.environ.get('MR_URL', 'unknown')

        slog.debug("Environment variables for BFA request",
                   MR_REPO=repo,
                   MR_BRANCH=branch,
                   MR_AUTHOR=author,
                   MR_COMMIT=commit,
                   MR_URL=mr_url)

        # Convert payload dict to JSON string (BFA API expects prompt as JSON string)
        prompt_json_string = json.dumps(payload)

        # Log the original payload structure
        if 'messages' in payload:
            slog.debug("Original payload structure",
                       num_messages=len(payload.get('messages', [])),
                       message_roles=[msg.get('role') for msg in payload.get('messages', [])])

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
                   author=author,
                   commit=commit[:8] if commit != 'unknown' else 'unknown',
                   mr_url=mr_url[:50] if mr_url != 'unknown' else 'unknown',
                   prompt_length=len(prompt_json_string),
                   total_payload_size=len(json.dumps(new_payload)))

        slog.debug("=== REQUEST TRANSFORMATION COMPLETE ===")
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
        slog.debug("=== RESPONSE TRANSFORMATION START ===")

        # Log the raw response structure
        slog.debug("BFA API response structure",
                   response_keys=list(response_data.keys()),
                   response_size=len(json.dumps(response_data)))

        # Check response status
        status = response_data.get('status', 'unknown')
        repo = response_data.get('repo', 'unknown')
        branch = response_data.get('branch', 'unknown')
        commit = response_data.get('commit', 'unknown')
        sent_to = response_data.get('sent_to', 'unknown')

        slog.debug("BFA API response metadata",
                   status=status,
                   repo=repo,
                   branch=branch,
                   commit=commit,
                   sent_to=sent_to)

        if status != 'ok':
            slog.warning("BFA API returned non-ok status",
                         status=status,
                         full_response=json.dumps(response_data)[:500])

        # Extract the AI response text from metrics.summary_text
        metrics = response_data.get('metrics', {})
        slog.debug("BFA API metrics field",
                   metrics_keys=list(metrics.keys()),
                   metrics_size=len(json.dumps(metrics)))

        summary_text = metrics.get('summary_text', '')

        if not summary_text:
            slog.error("No summary_text in BFA response",
                       metrics_keys=list(metrics.keys()),
                       metrics_content=json.dumps(metrics)[:200],
                       status=status,
                       full_response=json.dumps(response_data)[:1000])
            # Return error message to avoid breaking the pipeline
            summary_text = "Error: No AI response received from BFA service"
        else:
            slog.debug("summary_text extracted successfully",
                       text_length=len(summary_text),
                       text_preview=summary_text[:100] if len(summary_text) > 100 else summary_text)

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
                   status=status,
                   transformed_size=len(json.dumps(transformed)))

        slog.debug("=== RESPONSE TRANSFORMATION COMPLETE ===")
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

        slog.info("=" * 60)
        slog.info("=== LLM ADAPTER REQUEST START ===")
        slog.info("=" * 60)
        slog.debug("LLM Adapter request configuration",
                   url=bfa_url,
                   bfa_host=self.bfa_host,
                   timeout_s=self.api_timeout,
                   max_retries=max_retries,
                   payload_size=len(str(payload)))

        # Get or create JWT token
        try:
            slog.info("Step 1: Acquiring JWT token...")
            token = self._get_or_create_token()
            slog.info("Step 1: JWT token acquired successfully",
                      token_length=len(token))
        except Exception as e:
            slog.error("Step 1 FAILED: JWT token acquisition failed",
                       error=str(e),
                       error_type=type(e).__name__)
            return None, f"JWT token acquisition failed: {str(e)}"

        # Prepare headers with JWT token
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        slog.debug("Request headers prepared",
                   content_type=headers["Content-Type"],
                   auth_header_length=len(headers["Authorization"]))

        # Transform request payload
        slog.info("Step 2: Transforming request payload...")
        transformed_payload = self._transform_request(payload)
        slog.info("Step 2: Request payload transformed",
                  transformed_size=len(json.dumps(transformed_payload)))

        # Retry loop
        slog.info("Step 3: Sending request to BFA API...")
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    # Exponential backoff: 2s, 4s, 8s
                    wait_time = 2 ** attempt
                    slog.info("Retrying after backoff",
                              attempt=f"{attempt + 1}/{max_retries}",
                              wait_time_s=wait_time)
                    time.sleep(wait_time)

                slog.debug("Sending POST request to LLM API",
                           attempt=f"{attempt + 1}/{max_retries}",
                           url=bfa_url,
                           timeout=self.api_timeout)

                # Log request details before sending
                slog.debug("Full request details",
                           method="POST",
                           url=bfa_url,
                           headers_keys=list(headers.keys()),
                           payload_keys=list(transformed_payload.keys()),
                           payload_repo=transformed_payload.get('repo'),
                           payload_branch=transformed_payload.get('branch'),
                           payload_commit=transformed_payload.get('commit'),
                           prompt_length=len(transformed_payload.get('prompt', '')))

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

                slog.debug("LLM API response headers", headers=dict(resp.headers))

                # Raise an error for bad responses (4xx and 5xx)
                resp.raise_for_status()

                # Parse and transform response
                slog.info("Step 4: Parsing JSON response...")
                try:
                    response_data = resp.json()
                    slog.debug("LLM API JSON parsed successfully",
                               response_keys=list(response_data.keys()))
                except json.JSONDecodeError as json_err:
                    slog.error("Failed to parse JSON response",
                               response_text=resp.text[:500],
                               error=str(json_err))
                    return resp.status_code, f"Invalid JSON response: {str(json_err)}"

                slog.info("Step 5: Transforming response...")
                transformed_response = self._transform_response(response_data)

                slog.info("=" * 60)
                slog.info("=== LLM ADAPTER REQUEST SUCCESS ===")
                slog.info("=" * 60)

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
