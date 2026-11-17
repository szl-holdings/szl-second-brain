"""Verify the installed graph and HTML contracts outside the checkout, offline."""
from __future__ import annotations
import argparse
import importlib
import json
from pathlib import Path
import sys
import sysconfig
from unittest.mock import patch


def refuse_network(*_args, **_kwargs):
    raise AssertionError('INSTALLED_EVIDENCE_NETWORK_FORBIDDEN')


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkout',type=Path,required=True)
    checkout=parser.parse_args().checkout.resolve()
    assert sys.flags.isolated and sys.prefix!=sys.base_prefix
    assert not Path.cwd().resolve().is_relative_to(checkout)
    assert all(not Path(p).resolve().is_relative_to(checkout) for p in sys.path)
    with patch('socket.create_connection',side_effect=refuse_network):
        import second_brain
        from fastapi.testclient import TestClient
        from second_brain.web import app
        from second_brain.evidence_graph import digest
        lr=importlib.import_module('second_brain.lutar_reference')
        package=Path(second_brain.__file__).resolve().parent
        assert package==Path(sysconfig.get_path('purelib')).resolve()/'second_brain'
        with (TestClient(app) as client,
              patch('socket.socket.connect',side_effect=refuse_network),
              patch('socket.socket.connect_ex',side_effect=refuse_network)):
            parameters={'q':'Lutar formula authority','k':4}
            before=client.get('/api/v1/frontier-status').json()
            response=client.get('/api/v1/evidence-graph',params=parameters)
            assert response.status_code==200,response.text
            value=response.json();body=dict(value);sha=body.pop('content_sha256')
            assert digest(body)==sha
            assert value['execution_authority']==value['training_authority']=='NONE'
            assert value['provider_requests']==0 and value['graph_condition']['refinement_proved'] is False
            assert len([n for n in value['nodes'] if n['kind']=='LUTAR_REFERENCE'])==8
            page=client.get('/evidence',params=parameters)
            assert page.status_code==200 and sha in page.text
            assert '/evidence' in client.get('/').text
            with patch.object(lr,'data_file',return_value=package/'absent-audit-fixture.json'):
                missing=client.get('/api/v1/evidence-graph',params=parameters)
                assert missing.status_code==503
                assert not missing.json()['components']['lutar']['ready']
                assert client.get('/evidence',params=parameters).status_code==503
                assert client.get('/api/v1/frontier-status').json()==before
            assert client.get('/api/v1/evidence-graph',params=parameters).json()==value
            assert client.get('/api/v1/evidence-graph?q=').status_code==503
        for name,module in tuple(sys.modules.items()):
            if name=='second_brain' or name.startswith('second_brain.'):
                location=getattr(module,'__file__',None)
                if location:assert Path(location).resolve().is_relative_to(package)
        assert not any(x in sys.modules for x in ('langgraph','langchain_core','nemo_relay'))
        print(json.dumps({'state':'PASS','scope':'INSTALLED_EVIDENCE_UI_API',
                          'content_sha256':sha,'node_count':value['node_count'],'edge_count':value['edge_count'],
                          'network':'FORBIDDEN','optional_sdks_loaded':False,
                          'missing_reference_status':503,'recovery_verified':True,
                          'execution_authority':'NONE'},sort_keys=True))

if __name__=='__main__':main()
