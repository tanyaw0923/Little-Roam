import pytest
from app.calgary_import import transform, convert_feature, category_tags, fetch_features

SAMPLE = {
    'attributes': {
        'OBJECTID': 42,'GLOBALID':'{abc-123}','FACILITY_NAME':'Sample Recreation Centre',
        'ADDRESS':'123 Test St','FACILITY_TYPE':'Recreation Centre','INDR_POOL':'Y'},
    'geometry':{'x':-114.07,'y':51.04}
}

def test_transform_fields():
    feed=transform([SAMPLE])
    a=feed.activities[0]
    assert a.source_id=='calgary_recreation_facilities'
    assert a.activity_id=='abc-123'
    assert a.city=='Calgary' and a.province=='AB'
    assert a.latitude==51.04
    assert a.price_category=='any' and a.min_age is None
    assert 'swimming' in a.categories

def test_missing_key_fields_skipped():
    assert convert_feature({'attributes':{'OBJECTID':12,'FACILITY_NAME':'A'}}) is None

def test_reject_empty_source():
    with pytest.raises(ValueError,match='No usable'):
        transform([{'attributes':{'OBJECTID':12}}])

def test_reject_duplicates():
    with pytest.raises(ValueError,match='Duplicate'):
        transform([SAMPLE,SAMPLE])

def test_unknown_website_is_not_trusted():
    row={'attributes':{**SAMPLE['attributes'],'WEBSITE':'javascript:alert(1)'},'geometry':SAMPLE['geometry']}
    assert convert_feature(row).website_url is None

def test_bad_coordinates_not_inferred():
    row={'attributes':SAMPLE['attributes'],'geometry':{'x':400,'y':500}}
    assert convert_feature(row).latitude is None

class DummyResponse:
    def raise_for_status(self): pass
    def json(self): return {'features':[SAMPLE]}
class DummyClient:
    def get(self, url,params):
        assert params['outSR']=='4326'
        return DummyResponse()

def test_fetch_features_pages():
    assert len(fetch_features(DummyClient()))==1
