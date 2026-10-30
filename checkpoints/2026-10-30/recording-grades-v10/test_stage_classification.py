"""Authored local reports only; no providers or historical evidence rewriting."""
import json
from pathlib import Path
import pytest
import ledger_sidecar as s
from record_support import ENUMS

@pytest.mark.parametrize('stage,kind,status,expected',[
 ('setup','wall_timeout','wall_budget_terminal_inconclusive','setup_infrastructure'),
 ('public_observation','wall_timeout','wall_budget_terminal_inconclusive','observation_infrastructure'),
 ('public_observation','infrastructure','infrastructure_inconclusive','observation_infrastructure'),
 ('supervisor_review','wall_timeout','wall_budget_terminal_inconclusive','supervisor_infrastructure'),
 ('worker_phase','worker_budget','worker_budget_terminal_inconclusive','budget'),
 ('worker_phase','wall_timeout','wall_budget_terminal_inconclusive','timeout'),
 ('untrusted','wall_timeout','wall_budget_terminal_inconclusive','unknown'),
 ('public_observation','worker_budget','worker_budget_terminal_inconclusive','unknown')])
def test_finite_caught_classification(stage,kind,status,expected):
    report={'arms':{'baseline':{'status':'staged_natural_stop'},'pex':{'status':status,'failure_stage':stage,'failure_kind':kind}}}
    assert s.caught_failure_category(report)==expected
    assert expected in ENUMS['failure_category']


def test_historical_missing_stage_and_conflicting_outcomes_stay_unknown():
    assert s.caught_failure_category({'arms':{'pex':{'status':'wall_budget_terminal_inconclusive','error_type':'TimeoutError'}}})=='unknown'
    assert s.caught_failure_category({'arms':{'baseline':{'status':'worker_budget_terminal_inconclusive','failure_stage':'worker_phase','failure_kind':'worker_budget'},'pex':{'status':'wall_budget_terminal_inconclusive','failure_stage':'public_observation','failure_kind':'wall_timeout'}}})=='unknown'


def test_only_hashbound_report_can_supply_stage_and_cleanup_has_priority(tmp_path):
    (tmp_path/'run').mkdir()
    report={'config_sha256':'1'*64,'arms':{'pex':{'status':'wall_budget_terminal_inconclusive','failure_stage':'public_observation','failure_kind':'wall_timeout'}}}
    raw=json.dumps(report).encode();(tmp_path/'run/report.json').write_bytes(raw)
    terminal={'schema':'pex.staged.launcher-terminal.v1','run_id':'authored-test','config_sha256':'1'*64,'status':'inconclusive','comparison_complete':False,'cleanup_confirmed':True,'failure_category':None,'report_sha256':s.sha(raw)}
    path=tmp_path/'launcher-terminal.json';path.write_text(json.dumps(terminal))
    fields,_=s.terminal_record(tmp_path,'authored-test','1'*64)
    assert fields['failure_category']=='observation_infrastructure' and fields['terminal']=='infrastructure_inconclusive'
    terminal['cleanup_confirmed']=False;terminal['cleanup_errors']=['authored'];path.write_text(json.dumps(terminal))
    assert s.terminal_record(tmp_path,'authored-test','1'*64)[0]['failure_category']=='cleanup'
    (tmp_path/'run/report.json').write_bytes(raw+b' ')
    with pytest.raises(ValueError,match='report_hash_mismatch'):s.terminal_record(tmp_path,'authored-test','1'*64)


@pytest.mark.parametrize('stage',[None,[],{},1])
def test_malformed_stage_is_unknown(stage):
    assert s.caught_failure_category({'arms':{'pex':{'status':'wall_budget_terminal_inconclusive','failure_stage':stage,'failure_kind':'wall_timeout'}}})=='unknown'


def test_observation_timeout_flows_through_writer_and_follower_validator(tmp_path):
    from unittest.mock import patch
    import time
    import record_support as r
    from test_split_storage import paths
    actual,display,start,args=paths(tmp_path)
    (actual/'launcher-admission.json').write_text(json.dumps({'run_id':args.run_id,'config_sha256':args.config_sha256}))
    (actual/'run').mkdir()
    report={'config_sha256':args.config_sha256,'arms':{'pex':{'status':'wall_budget_terminal_inconclusive',
            'failure_stage':'public_observation','failure_kind':'wall_timeout'}}}
    report_raw=json.dumps(report).encode();(actual/'run/report.json').write_bytes(report_raw)
    def finish(_):
        (actual/'launcher-terminal.json').write_text(json.dumps({
            'schema':'pex.staged.launcher-terminal.v1','run_id':args.run_id,'config_sha256':args.config_sha256,
            'status':'inconclusive','comparison_complete':False,'cleanup_confirmed':True,
            'failure_category':None,'report_sha256':s.sha(report_raw)}))
    with patch.object(s.time,'sleep',side_effect=finish):assert s.run(args)==0
    records=[json.loads(line)for line in (display/'safe-display.jsonl').read_text().splitlines()]
    assert [x['event']for x in records]==['setup','run_terminal']
    started=r.timestamp(json.loads(start.read_text())['started_utc'])
    for seq,record in enumerate(records,1):
        # This exact validator is used by the native follower; no visual claim.
        r.validate(record,run_id=args.run_id,expected_seq=seq,not_before=started,now=time.time(),authored_fixture=True)
    assert records[-1]['failure_category']=='observation_infrastructure'
    assert records[-1]['terminal']=='infrastructure_inconclusive'
    assert records[-1]['comparison_complete'] is False
