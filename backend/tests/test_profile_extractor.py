import io
import json
import tarfile

from backend.app.profile_extractor import extract_candidates, extract_github_export_candidates


def test_extract_candidates_finds_obvious_cv_facts() -> None:
    text = """Sameer Faisal
sameer@example.com | +44 7700 900123
https://www.linkedin.com/in/sameer-faisal
https://github.com/sameer
"""
    candidates = {(item.label, item.value) for item in extract_candidates(text)}
    assert ("Full name", "Sameer Faisal") in candidates
    assert ("Email", "sameer@example.com") in candidates
    assert ("Phone", "+44 7700 900123") in candidates
    assert ("GitHub", "https://github.com/sameer") in candidates


def test_github_export_only_suggests_public_active_projects(tmp_path) -> None:
    export = tmp_path / "github.tar.gz"
    repositories = [
        {"name": "Public-App", "url": "https://github.com/example/public-app", "private": False, "is_archived": False},
        {"name": "Private-App", "url": "https://github.com/example/private-app", "private": True, "is_archived": False},
        {"name": "Old-App", "url": "https://github.com/example/old-app", "private": False, "is_archived": True},
    ]
    payload = json.dumps(repositories).encode()
    with tarfile.open(export, "w:gz") as archive:
        metadata = tarfile.TarInfo("./repositories_000001.json")
        metadata.size = len(payload)
        archive.addfile(metadata, io.BytesIO(payload))

    candidates = extract_github_export_candidates(export)
    assert [(item.label, item.value) for item in candidates] == [("Public-App", "https://github.com/example/public-app")]
