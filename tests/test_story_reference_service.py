import pytest
from fastapi import HTTPException

from app.services.story_reference_service import (
    StoryReferenceService,
    _normalize_name,
    _normalize_product_url,
)


def test_normalizes_reference_name_and_official_product_url():
    assert _normalize_name("  Mido  Baroncelli Héritage ") == "mido baroncelli heritage"
    assert _normalize_product_url("https://newstorerj.com.br/mido/baroncelli/#foto") == (
        "https://www.newstorerj.com.br/mido/baroncelli"
    )


@pytest.mark.parametrize("url", [
    "http://www.newstorerj.com.br/produto",
    "https://example.com/produto",
    "https://www.newstorerj.com.br/",
])
def test_rejects_non_official_or_incomplete_url(url):
    with pytest.raises(HTTPException) as error:
        _normalize_product_url(url)
    assert error.value.status_code == 422


def test_supervisor_cannot_mutate_reference():
    with pytest.raises(HTTPException) as error:
        StoryReferenceService._require_admin("supervisor")
    assert error.value.status_code == 403
