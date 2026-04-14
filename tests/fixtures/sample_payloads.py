"""Sample webhook payloads for testing."""

# Sample GitLab MR webhook payload
SAMPLE_MR_WEBHOOK = {
    "object_kind": "merge_request",
    "user": {
        "username": "test_user",
        "name": "Test User",
        "email": "test@example.com"
    },
    "project": {
        "id": 123,
        "name": "test-project",
        "path_with_namespace": "test-org/test-project",
        "web_url": "https://gitlab.com/test-org/test-project"
    },
    "object_attributes": {
        "iid": 42,
        "title": "Test MR Title",
        "description": "Test MR Description",
        "source_branch": "feature-branch",
        "target_branch": "main",
        "state": "opened",
        "merge_status": "can_be_merged",
        "author_id": 456,
        "assignee_id": 789,
        "created_at": "2023-01-01T12:00:00Z",
        "updated_at": "2023-01-01T12:30:00Z"
    },
    "changes": {}
}

# MR webhook with jenkins user
SAMPLE_MR_WEBHOOK_JENKINS = {
    **SAMPLE_MR_WEBHOOK,
    "user": {
        "username": "jenkins",
        "name": "Jenkins CI",
        "email": "jenkins@example.com"
    }
}

# MR webhook with changes
SAMPLE_MR_WEBHOOK_WITH_CHANGES = {
    **SAMPLE_MR_WEBHOOK,
    "changes": {
        "title": {
            "previous": "Old Title",
            "current": "New Title"
        },
        "total_time_spent": {
            "previous": 0,
            "current": 3600
        },
        "updated_at": {
            "previous": "2023-01-01T12:00:00Z",
            "current": "2023-01-01T12:30:00Z"
        }
    }
}

# Non-MR webhook (push event)
SAMPLE_PUSH_WEBHOOK = {
    "object_kind": "push",
    "user": {
        "username": "test_user",
        "name": "Test User"
    },
    "project": {
        "id": 123,
        "name": "test-project",
        "path_with_namespace": "test-org/test-project"
    },
    "commits": [
        {
            "id": "abc123",
            "message": "Test commit",
            "timestamp": "2023-01-01T12:00:00Z",
            "author": {
                "name": "Test User",
                "email": "test@example.com"
            }
        }
    ]
}

# Sample GitLab API responses
SAMPLE_MR_RESPONSE = {
    "iid": 42,
    "title": "Test MR Title",
    "description": "Test MR Description",
    "source_branch": "feature-branch",
    "target_branch": "main",
    "state": "opened",
    "merge_status": "can_be_merged",
    "author": {
        "id": 456,
        "username": "test_user",
        "name": "Test User"
    },
    "assignee": {
        "id": 789,
        "username": "assignee_user",
        "name": "Assignee User"
    },
    "web_url": "https://gitlab.com/test-org/test-project/-/merge_requests/42",
    "created_at": "2023-01-01T12:00:00Z",
    "updated_at": "2023-01-01T12:30:00Z",
    "diff_refs": {
        "base_sha": "base123",
        "head_sha": "head456",
        "start_sha": "start789"
    }
}

SAMPLE_COMMITS_RESPONSE = [
    {
        "id": "commit1",
        "short_id": "commit1",
        "title": "First commit",
        "message": "First commit\n\nDetailed message",
        "author_name": "Test User",
        "author_email": "test@example.com",
        "created_at": "2023-01-01T10:00:00Z"
    },
    {
        "id": "commit2",
        "short_id": "commit2",
        "title": "Second commit",
        "message": "Second commit",
        "author_name": "Test User",
        "author_email": "test@example.com",
        "created_at": "2023-01-01T11:00:00Z"
    }
]

SAMPLE_DISCUSSION_RESPONSE = {
    "id": "disc123",
    "individual_note": False,
    "notes": [
        {
            "id": 111,
            "type": "DiffNote",
            "body": "Test comment",
            "author": {
                "id": 456,
                "username": "test_user",
                "name": "Test User"
            },
            "created_at": "2023-01-01T13:00:00Z",
            "updated_at": "2023-01-01T13:00:00Z",
            "resolvable": True,
            "resolved": False
        }
    ]
}

SAMPLE_NOTES_RESPONSE = [
    {
        "id": 111,
        "type": "DiffNote",
        "body": "Test note 1",
        "author": {
            "id": 456,
            "username": "test_user",
            "name": "Test User"
        },
        "created_at": "2023-01-01T13:00:00Z",
        "resolvable": True,
        "resolved": False
    },
    {
        "id": 222,
        "type": "Note",
        "body": "Test note 2",
        "author": {
            "id": 789,
            "username": "other_user",
            "name": "Other User"
        },
        "created_at": "2023-01-01T14:00:00Z",
        "resolvable": False,
        "resolved": None
    }
]
