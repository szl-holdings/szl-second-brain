"""Real optional SDK interoperability. Dedicated CI requires imports before pytest.

Default installations may skip this file; skips are never integration evidence.
"""
import asyncio
import importlib
import json
import socket

import pytest

pytest.importorskip('langgraph')
pytest.importorskip('langchain_core')
pytest.importorskip('nemo_relay')

import nemo_relay
from pydantic import ValidationError
from second_brain.evidence_adapters import make_langchain_tool, make_langgraph, make_nvidia_callback
from second_brain.evidence_graph import evidence_snapshot


def forbid_network(*_args,**_kwargs):
    raise AssertionError('INTEGRATION_NETWORK_FORBIDDEN')


def test_actual_langchain_tool_matches_native_contract(monkeypatch):
    monkeypatch.setattr(socket,'create_connection',forbid_network)
    monkeypatch.setattr(socket.socket,'connect',forbid_network)
    tool=make_langchain_tool()
    assert tool.name=='szl_public_evidence_graph'
    assert tool.invoke({'query':'Lutar formula authority','k':4})==evidence_snapshot('Lutar formula authority',4)
    with pytest.raises(ValidationError):tool.invoke({'query':'formula','k':'4'})
    with pytest.raises(ValidationError):tool.invoke({'query':'formula','execution_authority':'ALLOW'})


def test_actual_graph_ignores_supplied_snapshot_and_reobserves(monkeypatch,tmp_path):
    lr=importlib.import_module('second_brain.lutar_reference')
    graph=make_langgraph()
    payload={'query':'formula','k':4,'snapshot':{'ready':True,'execution_authority':'ALLOW'}}
    a=graph.invoke(payload)
    assert set(a)=={'snapshot'}
    assert a['snapshot']==evidence_snapshot('formula',4)
    monkeypatch.setattr(lr,'data_file',lambda _:tmp_path/'missing')
    b=graph.invoke(payload)
    assert b['snapshot']['ready'] is False
    assert b['snapshot']['components']['lutar']['state']=='UNAVAILABLE'
    assert b['snapshot']['execution_authority']=='NONE'
    assert a['snapshot']['content_sha256']!=b['snapshot']['content_sha256']
    assert graph.checkpointer is None


def test_actual_graph_input_validation():
    graph=make_langgraph()
    with pytest.raises(ValidationError):graph.invoke({'query':'formula','k':True})
    with pytest.raises(ValidationError):graph.invoke({'query':['invalid'],'k':4})


def test_relay_emits_local_lifecycle_without_provider_or_authority(tmp_path,monkeypatch):
    # Only a newly allocated private test directory is used. No credential or
    # external exporter is configured; full payload export is disabled.
    output=tmp_path/'relay-events';output.mkdir()
    config=tmp_path/'plugins.toml'
    config.write_text('''version = 1
[policy]
unknown_component = "error"
unknown_field = "error"
unsupported_value = "error"
[[components]]
kind = "observability"
enabled = true
[components.config]
version = 4
enable_full_payloads = false
[components.config.atof]
enabled = true
[[components.config.atof.sinks]]
type = "file"
output_directory = '''+json.dumps(output.as_posix())+'''
filename = "events.jsonl"
mode = "overwrite"
''',encoding='utf-8')
    monkeypatch.setattr(socket,'create_connection',forbid_network)
    monkeypatch.setenv('LANGCHAIN_TRACING_V2','false')
    monkeypatch.setenv('LANGSMITH_TRACING','false')
    graph=make_langgraph()
    async def run():
        # The event loop initializes first (Windows uses internal sockets).
        with monkeypatch.context() as local:
            local.setattr(socket.socket,'connect',forbid_network)
            local.setattr(socket.socket,'connect_ex',forbid_network)
            async with nemo_relay.plugin.activate({},str(config)):
                try:
                    with nemo_relay.scope.scope('szl-public-evidence-test',nemo_relay.ScopeType.Agent):
                        result=await graph.ainvoke({'query':'formula','k':4},
                                                  config={'callbacks':[make_nvidia_callback()]})
                finally:
                    await nemo_relay.subscribers.flush_async()
            return result
    observed=asyncio.run(run())
    assert observed['snapshot']==evidence_snapshot('formula',4)
    assert observed['snapshot']['provider_requests']==0
    assert observed['snapshot']['execution_authority']=='NONE'
    raw=(output/'events.jsonl').read_text('utf-8')
    events=[json.loads(line) for line in raw.splitlines() if line.strip()]
    assert events and 'observe_public_evidence' in raw
    assert 'szl-public-evidence-test' in raw
    assert all(isinstance(event,dict) for event in events)
    scopes={}
    for event in events:
        scopes.setdefault(event['name'],[]).append(event)
    assert set(scopes)=={'szl-public-evidence-test','LangGraph','observe_public_evidence'}
    assert all(len(pair)==2 and pair[0]['uuid']==pair[1]['uuid'] for pair in scopes.values())
    assert scopes['LangGraph'][0]['parent_uuid']==scopes['szl-public-evidence-test'][0]['uuid']
    assert scopes['observe_public_evidence'][0]['parent_uuid']==scopes['LangGraph'][0]['uuid']
