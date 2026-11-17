"""Local graph contract and browser/API binding; no model/provider qualification."""
import copy
import importlib
import json
import socket

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from second_brain import evidence_graph as eg
from second_brain.evidence_console import render_evidence
from second_brain.web import app

lr = importlib.import_module('second_brain.lutar_reference')


def test_deterministic_typed_bounded_graph():
    a=eg.evidence_snapshot('Lutar formula authority',4)
    assert a == eg.evidence_snapshot('Lutar formula authority',4)
    assert a['ready'] and a['node_count'] == len(a['nodes']) <= 34
    assert a['edge_count'] == len(a['edges'])
    assert eg.check_backward_edges(a['nodes'],a['edges'])
    body=dict(a); sha=body.pop('content_sha256'); assert eg.digest(body)==sha
    assert {n['kind'] for n in a['nodes']} == {'CORPUS_HANDLE','REVIEW_CANDIDATE','LUTAR_REFERENCE','CITATION_PLAN','VIEW_RECEIPT'}
    assert len([n for n in a['nodes'] if n['kind']=='LUTAR_REFERENCE'])==8
    assert a['graph_condition']['formal_reference']=='F4'
    assert a['graph_condition']['refinement_proved'] is False


@pytest.mark.parametrize('bad',[0,13,True,1.5,'4'])
def test_strict_k(bad):
    with pytest.raises(ValidationError): eg.evidence_snapshot('formula',bad)


@pytest.mark.parametrize('bad',[None,[],{},'x'*2001])
def test_strict_query(bad):
    with pytest.raises(ValidationError): eg.evidence_snapshot(bad,4)


def test_empty_query_is_not_success():
    assert eg.evidence_snapshot('',4)['ready'] is False


def test_unknown_and_write_edges_fail_closed():
    a=eg.evidence_snapshot('formula',4)
    for edge in [{'source':0,'target':1,'relation':'CITES_HANDLE'},
                 {'source':99,'target':0,'relation':'CITES_HANDLE'},
                 {'source':1,'target':1,'relation':'CITES_HANDLE'},
                 {'source':True,'target':0,'relation':'CITES_HANDLE'},
                 {'source':1,'target':0,'relation':'EXECUTES'}]:
        assert not eg.check_backward_edges(a['nodes'],[edge])
    assert not eg.check_backward_edges(a['nodes'],a['edges']*2)
    assert not eg.check_backward_edges([],[])


def test_graph_contains_no_raw_query_or_claim_bodies_or_authority():
    sentinel='PRIVATE_QUERY_SENTINEL_c1a736'
    s=eg.evidence_snapshot(sentinel,4); text=json.dumps(s)
    assert sentinel not in text
    assert 'source_declared_answer' not in text and 'hypotheses' not in text
    assert s['execution_authority']==s['training_authority']=='NONE'
    assert s['provider_requests']==0 and s['provider_runtime']=='NOT_PROBED'
    assert s['model_generation']=='NOT_CONFIGURED'
    assert all(n['execution_authority']=='NONE' for n in s['nodes'])


def test_missing_lutar_is_local_partial_and_recovers(monkeypatch,tmp_path):
    original=lr.data_file; before=eg.evidence_snapshot('formula',4)
    monkeypatch.setattr(lr,'data_file',lambda _:tmp_path/'missing')
    missing=eg.evidence_snapshot('formula',4)
    assert missing['ready'] is False and missing['components']['lutar']['state']=='UNAVAILABLE'
    assert not any(n['kind']=='LUTAR_REFERENCE' for n in missing['nodes'])
    assert before['content_sha256']!=missing['content_sha256']
    monkeypatch.setattr(lr,'data_file',original)
    assert eg.evidence_snapshot('formula',4)==before


@pytest.mark.parametrize('mutation',['receipt','plan','handle','ranking','authority','evidence','generation','plan_source'])
def test_transaction_tampering_fails(monkeypatch,mutation):
    b=copy.deepcopy(eg.query_bundle('formula',4))
    if mutation=='receipt': b['receipt']['sha256']='0'*64
    elif mutation=='plan': b['plan']['decision']='EXECUTE'
    elif mutation=='handle': b['retrieve']['handles'][0]['nodeId']='forged'
    elif mutation=='ranking': b['retrieve']['ranking_receipt']['forged']=True
    elif mutation=='evidence': b['retrieve']['evidence'][0]['sha256']='0'*64
    elif mutation=='generation': b['retrieve']['generation_sha256']='0'*64
    elif mutation=='plan_source': b['plan']['retrieval_evidence_set_sha256']='0'*64
    else: b['execution_authority']='ALLOW'
    monkeypatch.setattr(eg,'query_bundle',lambda *_:b)
    with pytest.raises(eg.EvidenceGraphError):eg.evidence_snapshot('formula',4)


def test_ui_api_exact_contract_and_safe_links():
    with TestClient(app) as client:
        api=client.get('/api/v1/evidence-graph',params={'q':'Lutar','k':4})
        page=client.get('/evidence',params={'q':'Lutar','k':4})
        assert api.status_code==page.status_code==200
        data=api.json()
        assert data['content_sha256'] in page.text
        for n in data['nodes']: assert f'id="node-{n["ordinal"]}"' in page.text
        assert '/evidence' in client.get('/').text
        assert 'no-store' in api.headers['cache-control']
        assert "default-src 'none'" in page.headers['content-security-policy']
        assert client.get('/api/v1/evidence-graph?k=99').status_code==422
        assert client.get('/api/v1/evidence-graph?q=').status_code==503


def test_html_escapes_query_and_evidence():
    s=eg.evidence_snapshot('formula',4); s['nodes'][0]['title']='<img src=x onerror=alert(1)>'
    text=render_evidence('<script>alert(1)</script>',4,s)
    assert '<script>' not in text and '<img src=x' not in text
    assert '&lt;script&gt;' in text and '&lt;img src=x' in text


def test_unavailable_never_substitutes_sample(monkeypatch):
    import second_brain.web as web
    def fail(*_):raise eg.EvidenceGraphError('secret-path-that-must-not-echo')
    monkeypatch.setattr(web,'evidence_snapshot',fail)
    with TestClient(app) as client:
        a=client.get('/api/v1/evidence-graph');p=client.get('/evidence')
        assert a.status_code==p.status_code==503
        assert a.json()['nodes']==[]
        assert 'secret-path' not in a.text+p.text
        assert 'No sample result' in p.text


def test_local_observation_does_not_open_network(monkeypatch):
    def refuse(*_args,**_kwargs):raise AssertionError('NETWORK_FORBIDDEN')
    monkeypatch.setattr(socket,'create_connection',refuse)
    monkeypatch.setattr(socket.socket,'connect',refuse)
    monkeypatch.setattr(socket.socket,'connect_ex',refuse)
    assert eg.evidence_snapshot('formula',4)['provider_requests']==0


def test_augmented_view_does_not_relabel_the_original_query_receipt():
    value=eg.evidence_snapshot('formula',4)
    manifest=value['view_manifest'];root=value['nodes'][-1]
    assert root['kind']=='VIEW_RECEIPT'
    assert root['sha256']==eg.digest(manifest)
    assert root['sha256']!=value['query_receipt_sha256']
    assert manifest['query_receipt_sha256']==value['query_receipt_sha256']
    assert manifest['nodes_sha256']==eg.digest(value['nodes'][:-1])
    assert manifest['edges_sha256']==eg.digest([e for e in value['edges'] if e['source']!=root['ordinal']])
    assert manifest['lutar_source_sha256']==value['lutar_source_sha256']
