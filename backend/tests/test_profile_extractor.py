from backend.app.profile_extractor import extract_candidates


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
