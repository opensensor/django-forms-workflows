import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from django_forms_workflows.handlers.file_handler import FileOperationHandler


@pytest.mark.parametrize(
    ("operation", "target", "expected_log"),
    [
        ("rename", "renamed.txt", "Renamed managed file id=42"),
        ("move", "private/renamed.txt", "Moved managed file id=42"),
        ("copy", "private/copied.txt", "Copied managed file id=42"),
        ("delete", None, "Deleted managed file id=42"),
    ],
)
def test_file_operations_do_not_log_private_paths(
    caplog, operation, target, expected_log
):
    source_path = "private/customer-ssn/source.txt"
    managed_file = SimpleNamespace(
        id=42,
        file_path=source_path,
        stored_filename="source.txt",
        submission=MagicMock(),
        save=MagicMock(),
    )
    handler = FileOperationHandler(managed_file)
    handler.storage = MagicMock()
    handler.storage.exists.return_value = True
    handler.storage.open.return_value.__enter__.return_value.read.return_value = b"data"

    caplog.set_level(
        logging.INFO, logger="django_forms_workflows.handlers.file_handler"
    )

    if target is None:
        result = getattr(handler, operation)()
        private_paths = (source_path,)
    else:
        handler.resolver.resolve = MagicMock(return_value=target)
        result = getattr(handler, operation)(target)
        destination_path = (
            f"private/customer-ssn/{target}" if operation == "rename" else target
        )
        private_paths = (source_path, destination_path)

    assert result["success"] is True
    assert expected_log in caplog.text
    assert all(private_path not in caplog.text for private_path in private_paths)
