"""Tests for private, selected authoring-material projections."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


from dynamic_agent_runner.workflow_host.authoring_materials import (  # noqa: E402
    AuthoringMaterialError,
    AuthoringMaterialInput,
    AuthoringMaterialService,
)
from dynamic_agent_runner.workflow_host.state import PrivateStateStore  # noqa: E402


NOW = datetime(2026, 8, 24, tzinfo=UTC)


def _service(tmp_path: Path, *, owner: str = "local-user") -> AuthoringMaterialService:
    return AuthoringMaterialService(
        store=PrivateStateStore(tmp_path / "state"),
        owner=owner,
        max_material_bytes=128,
        max_materials=4,
        material_ttl=timedelta(minutes=5),
    )


def _manifest(tmp_path: Path, members: list[dict[str, str]]) -> Path:
    path = tmp_path / "materials.json"
    path.write_text(
        json.dumps({"format_version": 1, "members": members}), encoding="utf-8"
    )
    return path


def test_issues_a_bounded_opaque_material_set_and_selected_projection(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)

    receipt = service.issue(
        materials=(
            AuthoringMaterialInput(
                role="example", content="approved example", disposition="reference_only"
            ),
            AuthoringMaterialInput(
                role="template",
                content="exportable template",
                disposition="distributable",
            ),
        ),
        now=NOW,
    )
    projection = service.project(receipt.material_set_id, now=NOW)

    assert receipt.material_set_id.startswith("v1.")
    assert [member.role for member in receipt.members] == ["example", "template"]
    assert all(len(member.digest) == 64 for member in receipt.members)
    assert not hasattr(receipt.members[0], "content")
    assert [member.content for member in projection.members] == [
        "approved example",
        "exportable template",
    ]
    assert all("path" not in member.__dict__ for member in projection.members)
    assert projection.members[0].disposition == "reference_only"
    assert projection.members[1].disposition == "distributable"


def test_material_sets_fail_closed_for_other_owners_expiry_and_unselected_content(
    tmp_path: Path,
) -> None:
    receipt = _service(tmp_path).issue(
        materials=(
            AuthoringMaterialInput(
                role="example", content="selected", disposition="reference_only"
            ),
        ),
        now=NOW,
    )

    with pytest.raises(AuthoringMaterialError, match="unavailable"):
        _service(tmp_path, owner="other-user").project(receipt.material_set_id, now=NOW)
    with pytest.raises(AuthoringMaterialError, match="unavailable"):
        _service(tmp_path).project(
            receipt.material_set_id, now=NOW + timedelta(minutes=6)
        )
    with pytest.raises(AuthoringMaterialError, match="at least one"):
        _service(tmp_path).issue(materials=(), now=NOW)


def test_human_manifest_issues_only_selected_regular_text_files(tmp_path: Path) -> None:
    selected = tmp_path / "selected.txt"
    unselected = tmp_path / "unselected.txt"
    selected.write_text("approved example", encoding="utf-8")
    unselected.write_text("unselected example", encoding="utf-8")
    receipt = _service(tmp_path).issue_human_manifest(
        manifest_path=_manifest(
            tmp_path,
            [
                {
                    "disposition": "reference_only",
                    "path": str(selected),
                    "role": "example",
                }
            ],
        ),
        now=NOW,
    )
    projection = _service(tmp_path).project(receipt.material_set_id, now=NOW)

    assert projection.members[0].content == "approved example"
    assert "unselected example" not in repr(projection)
    assert str(selected) not in repr(projection)


@pytest.mark.parametrize(
    "member",
    [
        {"content": "raw", "disposition": "reference_only", "role": "example"},
        {"disposition": "reference_only", "path": "relative.txt", "role": "example"},
    ],
)
def test_human_manifest_rejects_raw_content_and_relative_paths(
    tmp_path: Path, member: dict[str, str]
) -> None:
    with pytest.raises(AuthoringMaterialError, match="manifest is invalid"):
        _service(tmp_path).issue_human_manifest(
            manifest_path=_manifest(tmp_path, [member]), now=NOW
        )


def test_human_manifest_rejects_symlinked_or_oversized_materials(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target.txt"
    target.write_text("approved example", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    oversized = tmp_path / "oversized.txt"
    oversized.write_text("x" * 129, encoding="utf-8")

    for source in (link, oversized):
        with pytest.raises(AuthoringMaterialError, match="manifest is invalid"):
            _service(tmp_path).issue_human_manifest(
                manifest_path=_manifest(
                    tmp_path,
                    [
                        {
                            "disposition": "reference_only",
                            "path": str(source),
                            "role": "example",
                        }
                    ],
                ),
                now=NOW,
            )

    manifest_target = _manifest(
        tmp_path,
        [
            {
                "disposition": "reference_only",
                "path": str(target),
                "role": "example",
            }
        ],
    )
    manifest_link = tmp_path / "manifest-link.json"
    manifest_link.symlink_to(manifest_target)
    with pytest.raises(AuthoringMaterialError, match="manifest is invalid"):
        _service(tmp_path).issue_human_manifest(manifest_path=manifest_link, now=NOW)


@pytest.mark.parametrize(
    "material",
    (
        AuthoringMaterialInput(
            role="", content="content", disposition="reference_only"
        ),
        AuthoringMaterialInput(
            role="example", content="", disposition="reference_only"
        ),
        AuthoringMaterialInput(
            role="example", content="content", disposition="private"
        ),
        AuthoringMaterialInput(
            role="example", content="x" * 129, disposition="reference_only"
        ),
    ),
)
def test_material_set_rejects_invalid_or_oversized_members(
    tmp_path: Path, material: AuthoringMaterialInput
) -> None:
    with pytest.raises(AuthoringMaterialError):
        _service(tmp_path).issue(materials=(material,), now=NOW)
