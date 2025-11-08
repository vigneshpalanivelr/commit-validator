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

logger = logging.getLogger(__name__)


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

        logger.info(f"[DEBUG] LLM Adapter initialized - BFA_HOST: {self.bfa_host}, "
                   f"Timeout: {self.api_timeout}s, Token pre-configured: {bool(self.bfa_token_key)}")

    def _get_project_and_mr(self):
        """Get project and MR IID from environment."""
        project_id = os.environ.get('PROJECT_ID', '')
        mr_iid = os.environ.get('MR_IID', '')

        if not project_id or not mr_iid:
            logger.warning(f"[DEBUG] PROJECT_ID or MR_IID not set in environment. "
                          f"PROJECT_ID={project_id}, MR_IID={mr_iid}")
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
            logger.info(f"[DEBUG] Using pre-configured BFA_TOKEN_KEY")
            return self.bfa_token_key

        # Check if we already have a token for this project/MR
        if LLMAdapter._session_token and LLMAdapter._token_project_mr == current_project_mr:
            logger.info(f"[DEBUG] Reusing existing session token for {current_project_mr}")
            return LLMAdapter._session_token

        # Need to get a new token
        if not project_id or not mr_iid:
            raise ValueError("PROJECT_ID and MR_IID environment variables required for JWT token generation")

        subject = f"rate-my-mr-{project_id}-{mr_iid}"
        token_url = f"http://{self.bfa_host}:8000/api/token"

        logger.info(f"[DEBUG] Requesting JWT token from {token_url}")
        logger.info(f"[DEBUG] Token subject: {subject}")

        try:
            response = requests.post(
                token_url,
                headers={"Content-Type": "application/json"},
                json={"subject": subject},
                timeout=30
            )

            logger.info(f"[DEBUG] Token API response status: {response.status_code}")
            response.raise_for_status()

            token_data = response.json()
            token = token_data.get('token')

            if not token:
                raise ValueError(f"Token not found in response: {token_data}")

            # Store token for reuse
            LLMAdapter._session_token = token
            LLMAdapter._token_project_mr = current_project_mr

            logger.info(f"[DEBUG] JWT token acquired successfully for {current_project_mr}")
            logger.info(f"[DEBUG] Token (first 20 chars): {token[:20]}...")

            return token

        except requests.exceptions.RequestException as e:
            logger.error(f"[ERROR] Failed to acquire JWT token: {e}")
            raise

    def _transform_request(self, payload):
        """
        Transform request from current format to new API format.

        Current format (assumed):
        {
            "messages": [
                {"role": "system", "content": "..."},
                {"role": "user", "content": "..."}
            ]
        }

        TODO: Update this method when actual new API format is provided.
        For now, keeping the same format as input.

        Args:
            payload: Original request payload

        Returns:
            dict: Transformed payload for new API
        """
        # TODO: Implement actual transformation based on new API specification
        # For now, pass through as-is
        logger.info(f"[DEBUG] Request transformation - keeping original format (TODO: update when format provided)")
        return payload

    def _transform_response(self, response_data):
        """
        Transform response from new API format to expected format.

        Expected format (for compatibility):
        {
            "content": [
                {"type": "text", "text": "..."}
            ]
        }

        TODO: Update this method when actual new API response format is provided.
        For now, assuming same format as output.

        Args:
            response_data: Raw response from new API

        Returns:
            dict: Transformed response in expected format
        """
        # TODO: Implement actual transformation based on new API specification
        # For now, pass through as-is
        logger.info(f"[DEBUG] Response transformation - keeping original format (TODO: update when format provided)")
        return response_data

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

        logger.info(f"[DEBUG] LLM Adapter - URL: {url}")
        logger.info(f"[DEBUG] LLM Adapter - Timeout: {self.api_timeout}s, Max retries: {max_retries}")
        logger.info(f"[DEBUG] LLM Adapter - Payload size: {len(str(payload))} chars")

        # Get or create JWT token
        try:
            token = self._get_or_create_token()
        except Exception as e:
            logger.error(f"[ERROR] Failed to get JWT token: {e}")
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
                    logger.info(f"[DEBUG] Retry attempt {attempt + 1}/{max_retries} after {wait_time}s wait...")
                    time.sleep(wait_time)

                logger.info(f"[DEBUG] Sending POST request to LLM API (attempt {attempt + 1}/{max_retries})...")

                resp = requests.post(
                    url,
                    json=transformed_payload,
                    headers=headers,
                    timeout=self.api_timeout
                )

                logger.info(f"[DEBUG] LLM API Response - Status Code: {resp.status_code}")
                logger.info(f"[DEBUG] LLM API Response - Content Length: {len(resp.content)}")

                # Raise an error for bad responses (4xx and 5xx)
                resp.raise_for_status()

                # Parse and transform response
                response_data = resp.json()
                logger.info(f"[DEBUG] LLM API Response - JSON parsed successfully")

                transformed_response = self._transform_response(response_data)

                return resp.status_code, transformed_response

            except requests.exceptions.HTTPError as http_err:
                logger.error(f"[DEBUG] LLM API HTTP Error (attempt {attempt + 1}): {http_err}")
                logger.error(f"[DEBUG] Response content: {resp.content[:500] if 'resp' in locals() else 'No response'}")

                # Special handling for authentication errors
                if resp.status_code == 401:
                    logger.error(f"[ERROR] JWT token authentication failed (401 Unauthorized)")
                    # Clear cached token so next call will get a new one
                    LLMAdapter._session_token = None
                    LLMAdapter._token_project_mr = None

                # Don't retry on 4xx client errors (except 429 rate limit)
                if 400 <= resp.status_code < 500 and resp.status_code != 429:
                    logger.error(f"[DEBUG] Client error {resp.status_code}, not retrying")
                    return resp.status_code, str(http_err)

                # Retry on 5xx server errors and 429 rate limit
                if attempt == max_retries - 1:
                    return resp.status_code, str(http_err)

            except requests.exceptions.ConnectionError as conn_err:
                logger.error(f"[DEBUG] LLM API Connection Error (attempt {attempt + 1}): {conn_err}")
                if attempt == max_retries - 1:
                    logger.error(f"[DEBUG] All {max_retries} attempts failed - LLM API not reachable")
                    return None, f"Connection failed after {max_retries} attempts: {str(conn_err)}"

            except requests.exceptions.Timeout as timeout_err:
                logger.error(f"[DEBUG] LLM API Timeout (attempt {attempt + 1}): {timeout_err}")
                if attempt == max_retries - 1:
                    logger.error(f"[DEBUG] All {max_retries} attempts timed out")
                    return None, f"Timeout after {max_retries} attempts: {str(timeout_err)}"

            except requests.exceptions.RequestException as req_err:
                logger.error(f"[DEBUG] LLM API Request Error (attempt {attempt + 1}): {req_err}")
                logger.error(f"[DEBUG] Error type: {type(req_err).__name__}")
                if attempt == max_retries - 1:
                    return None, str(req_err)

            except Exception as err:
                logger.error(f"[DEBUG] LLM API Unexpected Error (attempt {attempt + 1}): {err}")
                logger.error(f"[DEBUG] Error type: {type(err).__name__}")
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
