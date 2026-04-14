"""Mock responses for external services (GitLab API, Docker API, etc.)."""

from typing import Dict, Any
import docker.errors


# GitLab API mock responses
class MockGitLabAPI:
    """Mock GitLab API responses."""

    @staticmethod
    def success_response(data: Dict[str, Any], status_code: int = 200):
        """Create a successful API response."""
        class Response:
            def __init__(self, data, status_code):
                self.status_code = status_code
                self.json_data = data
                self.text = str(data)
                self.headers = {'Content-Type': 'application/json'}

            def json(self):
                return self.json_data

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise Exception(f"HTTP {self.status_code}")

        return Response(data, status_code)

    @staticmethod
    def error_response(status_code: int, message: str = "Error"):
        """Create an error API response."""
        return MockGitLabAPI.success_response(
            {"error": message},
            status_code
        )

    @staticmethod
    def paginated_response(items: list, page: int = 1, per_page: int = 20):
        """Create a paginated API response."""
        start = (page - 1) * per_page
        end = start + per_page
        page_items = items[start:end]

        response = MockGitLabAPI.success_response(page_items)

        # Add Link header for pagination
        if end < len(items):
            response.headers['Link'] = f'<https://gitlab.com/api/v4/test?page={page + 1}>; rel="next"'

        return response


# Docker API mock responses
class MockDockerAPI:
    """Mock Docker API responses."""

    @staticmethod
    def mock_container(name: str = "test-container", status: str = "running"):
        """Create a mock Docker container object."""
        class MockContainer:
            def __init__(self, name, status):
                self.name = name
                self.id = f"mock-{name}-id"
                self.short_id = f"mock-{name[:8]}"
                self.status = status
                self.attrs = {
                    'State': {'Status': status, 'Running': status == 'running'},
                    'Config': {'Image': 'test-image:latest'},
                    'NetworkSettings': {'IPAddress': '172.17.0.2'}
                }

            def start(self):
                self.status = "running"
                self.attrs['State']['Status'] = "running"
                self.attrs['State']['Running'] = True

            def stop(self, timeout=10):
                self.status = "exited"
                self.attrs['State']['Status'] = "exited"
                self.attrs['State']['Running'] = False

            def restart(self, timeout=10):
                self.stop(timeout)
                self.start()

            def remove(self, force=False):
                pass

            def logs(self, **kwargs):
                return b"Mock container logs\nLine 2\nLine 3"

            def stats(self, stream=False):
                if stream:
                    def generator():
                        yield {
                            'cpu_stats': {'cpu_usage': {'total_usage': 1000000}},
                            'memory_stats': {'usage': 50000000, 'limit': 100000000}
                        }
                    return generator()
                else:
                    return {
                        'cpu_stats': {'cpu_usage': {'total_usage': 1000000}},
                        'memory_stats': {'usage': 50000000, 'limit': 100000000}
                    }

        return MockContainer(name, status)

    @staticmethod
    def mock_image(name: str = "test-image", tag: str = "latest"):
        """Create a mock Docker image object."""
        class MockImage:
            def __init__(self, name, tag):
                self.id = f"mock-image-{name}-id"
                self.short_id = f"mock-img-{name[:8]}"
                self.tags = [f"{name}:{tag}"]
                self.attrs = {
                    'Size': 100000000,
                    'Created': '2023-01-01T12:00:00Z'
                }

        return MockImage(name, tag)

    @staticmethod
    def mock_docker_client():
        """Create a mock Docker client."""
        class MockContainers:
            def __init__(self):
                self._containers = {}

            def get(self, name_or_id):
                if name_or_id in self._containers:
                    return self._containers[name_or_id]
                raise docker.errors.NotFound(f"Container {name_or_id} not found")

            def list(self, all=False, filters=None):
                return list(self._containers.values())

            def run(self, image, **kwargs):
                name = kwargs.get('name', 'unnamed-container')
                container = MockDockerAPI.mock_container(name, 'running')
                self._containers[name] = container
                return container

            def create(self, image, **kwargs):
                name = kwargs.get('name', 'unnamed-container')
                container = MockDockerAPI.mock_container(name, 'created')
                self._containers[name] = container
                return container

        class MockImages:
            def __init__(self):
                self._images = {}

            def get(self, name):
                if name in self._images:
                    return self._images[name]
                raise docker.errors.ImageNotFound(f"Image {name} not found")

            def list(self):
                return list(self._images.values())

            def build(self, **kwargs):
                tag = kwargs.get('tag', 'unnamed-image')
                image = MockDockerAPI.mock_image(tag)
                self._images[tag] = image
                return image, []

        class MockDockerClient:
            def __init__(self):
                self.containers = MockContainers()
                self.images = MockImages()
                self.api = self

            def ping(self):
                return True

            def version(self):
                return {'Version': '20.10.0', 'ApiVersion': '1.41'}

        return MockDockerClient()


# AI Service mock responses
class MockAIService:
    """Mock AI/LLM service responses."""

    @staticmethod
    def success_response(content: str = "Mock AI response"):
        """Create a successful AI service response."""
        return {
            "choices": [
                {
                    "message": {
                        "content": content,
                        "role": "assistant"
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150
            }
        }

    @staticmethod
    def error_response(error_type: str = "rate_limit_error"):
        """Create an error AI service response."""
        return {
            "error": {
                "type": error_type,
                "message": "Mock AI service error"
            }
        }

    @staticmethod
    def jwt_token_response(token: str = "mock-jwt-token"):
        """Create a JWT token response."""
        return {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": 3600
        }


# Subprocess mock responses
class MockSubprocess:
    """Mock subprocess responses."""

    @staticmethod
    def success(stdout: str = "", stderr: str = "", returncode: int = 0):
        """Create a successful subprocess result."""
        class Result:
            def __init__(self, stdout, stderr, returncode):
                self.stdout = stdout
                self.stderr = stderr
                self.returncode = returncode

        return Result(stdout, stderr, returncode)

    @staticmethod
    def failure(stderr: str = "Command failed", returncode: int = 1):
        """Create a failed subprocess result."""
        return MockSubprocess.success("", stderr, returncode)
