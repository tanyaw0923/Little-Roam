import pytest
from pydantic import ValidationError
from app.refresh import Feed

def test_valid_curated_feed():
    feed=Feed.model_validate({'activities':[{'source_id':'editorial','activity_id':'abc',
        'city':'Calgary','province':'AB','name':'Sample Place','address':'Somewhere in Calgary',
        'source_url':'https://example.com/source'}]})
    assert len(feed.activities)==1

def test_reject_persisting_google_places():
    with pytest.raises(ValidationError):
        Feed.model_validate({'activities':[{'source_id':'google_places','activity_id':'abc',
            'city':'Calgary','province':'AB','name':'Sample Place','address':'Somewhere in Calgary',
            'source_url':'https://example.com/source'}]})

def test_reject_wrong_province():
    with pytest.raises(ValidationError):
        Feed.model_validate({'activities':[{'source_id':'editorial','activity_id':'abc',
            'city':'Calgary','province':'XX','name':'Sample Place','address':'Somewhere in Calgary',
            'source_url':'https://example.com/source'}]})
