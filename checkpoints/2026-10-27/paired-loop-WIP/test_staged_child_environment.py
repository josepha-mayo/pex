"""Synthetic closed capability/child env only; never inspect actual proxy values."""
import pytest
from test_staged_accounting import funded
from test_staged_sdk_binding import bound
from test_staged_admission import candidate
from staged_worker_admission import bind_child_environment
from staged_admission import AdmissionRefused


def environment():
    return {'PATH':'/usr/bin:/bin','HTTPS_PROXY':'http://authored.invalid:8888',
            'NO_PROXY':'127.0.0.1,localhost,.unrelated.invalid'}


def test_no_binding_closed_before_environment_use():
    with pytest.raises(AdmissionRefused):bind_child_environment(None,{})


def test_current_ordinary_CA_inherited_without_copy_or_parent_mutation(funded,monkeypatch):
    _,scope=funded;before=environment()
    result=bind_child_environment(scope,before)
    assert 'SSL_CERT_FILE' not in before
    assert result['SSL_CERT_FILE']==scope.cfg['network']['ca']['path']
    assert result['HTTPS_PROXY']==before['HTTPS_PROXY'] and 'NODE_EXTRA_CA_CERTS' not in result


@pytest.mark.parametrize('name,value',[
    ('HTTPS_PROXY','http://other.invalid'),('https_proxy','http://other.invalid'),
    ('HTTP_PROXY','http://other.invalid'),('ALL_PROXY','socks5://other.invalid'),
    ('NO_PROXY','*'),('no_proxy','.nebius.com'),('NO_PROXY','*.tokenfactory.nebius.com'),
    ('NO_PROXY','api.tokenfactory.nebius.com:443'),('NO_PROXY','.nebius.com.:0443'),
    ('NO_PROXY','api.tokenfactory.nebius.com:*'),('NO_PROXY','NEBIUS.COM.'),
    ('NODE_TLS_REJECT_UNAUTHORIZED','0'),
    ('NODE_EXTRA_CA_CERTS','/unreviewed'),('SSL_CERT_DIR','/unreviewed'),
    ('NODE_OPTIONS','--unreviewed'),('BUN_OPTIONS','--unreviewed'),('SSL_CERT_FILE','/unreviewed')])
def test_conflicting_child_proxy_or_CA_is_refused_not_normalized(funded,name,value):
    _,scope=funded;env=environment();env[name]=value;before=dict(env)
    with pytest.raises(AdmissionRefused):bind_child_environment(scope,env)
    assert env==before


def test_same_proxy_aliases_and_unrelated_port_do_not_change_routing(funded):
    _,scope=funded;env=environment()
    env.update(https_proxy=env['HTTPS_PROXY'],ALL_PROXY=env['HTTPS_PROXY'],
               no_proxy='api.tokenfactory.nebius.com:8443,127.0.0.1')
    assert bind_child_environment(scope,env)['https_proxy']==env['HTTPS_PROXY']


def test_real_child_projection_omits_unused_fallback_parent_and_explicit_guards_unchanged(funded,monkeypatch,tmp_path):
    import os
    from staged_worker_admission import prepare_child_environment,validate_child_environment,local_admission_reason
    _,scope=funded
    monkeypatch.setenv('ALL_PROXY','http://127.0.0.1:1');monkeypatch.setenv('all_proxy','http://127.0.0.1:2')
    before=dict(os.environ);old=environment();old['ALL_PROXY']=os.environ['ALL_PROXY']
    with pytest.raises(AdmissionRefused) as error:validate_child_environment(scope.cfg,old)
    assert local_admission_reason(error.value)=='ambiguous_child_proxy_alias_refused'
    child=prepare_child_environment(scope.cfg,tmp_path/'future-profile')
    assert child['HTTPS_PROXY']==before['HTTPS_PROXY']
    assert not any(n in child for n in ('ALL_PROXY','all_proxy')) and os.environ==before
    child['ALL_PROXY']='http://127.0.0.1:1'
    with pytest.raises(AdmissionRefused,match='ambiguous'):validate_child_environment(scope.cfg,child)


def test_local_reason_is_allowlisted_not_raw_exception_message():
    from staged_worker_admission import local_admission_reason
    assert local_admission_reason(AdmissionRefused('ambiguous_child_proxy_alias_refused'))=='ambiguous_child_proxy_alias_refused'
    assert local_admission_reason(AdmissionRefused('https://AUTHORED-secret.invalid/token'))=='unclassified_local_admission_refusal'
