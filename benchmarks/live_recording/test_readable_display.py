"""Presentation-only authored fixtures; no live model or score claim."""
import copy
from record_support import EvidenceDisplay,sha


def sample(**kw):
    value={'event':'measurement','arm':'baseline','at_utc':'2026-10-30T01:00:00Z','worker_requests':2,'worker_input_tokens':100,'worker_output_tokens':40}
    value.update(kw);return value


def test_unknown_is_not_zero_and_fixture_is_unmissable():
    text=EvidenceDisplay('authored-recorder-readable',True).render()
    assert 'SIMULATED / AUTHORED FIXTURE - NOT REAL INFERENCE' in text
    assert 'PEX | requests not observed' in text
    assert 'No root-reviewed model excerpt' in text


def test_per_arm_metrics_remain_distinct_and_excerpt_persists_without_input_mutation():
    view=EvidenceDisplay('authored-recorder-readable',True)
    first=sample();original=copy.deepcopy(first);view.update(first);assert first==original
    text='Authored fixture statement, not a model response.\nSecond exact line.'
    excerpt=sample(event='worker_response',model_excerpt=text,reviewed_utc='2026-10-30T01:00:01Z',excerpt_origin='worker_json_assistant_content',model_excerpt_sha256=sha(text.encode()))
    view.update(excerpt)
    rendered=view.update(sample(arm='pex',worker_requests=3,supervisor_requests=1,supervisor_input_tokens=44,supervisor_output_tokens=12))
    assert 'BASELINE | requests 2' in rendered and 'PEX | requests 3' in rendered
    assert 'SUPERVISOR (separate) | requests 1' in rendered
    assert text in rendered and 'REVIEW-DELAYED' in rendered
    assert excerpt['model_excerpt']==text
    assert 'Source received UTC: unavailable' in rendered


def test_long_excerpt_prefix_is_explicit_and_full_hash_retained():
    text='\n'.join('authored fixture line '+str(i)for i in range(30));digest=sha(text.encode())
    view=EvidenceDisplay('authored-recorder-readable',True)
    rendered=view.update(sample(event='worker_response',model_excerpt=text,reviewed_utc='2026-10-30T01:00:01Z',excerpt_origin='worker_json_assistant_content',model_excerpt_sha256=digest))
    assert 'DISPLAY PREFIX ONLY' in rendered and digest in rendered
    assert 'authored fixture line 29' not in rendered
    assert view.excerpt['model_excerpt']==text


def test_terminal_does_not_claim_success_from_finished_receipt():
    view=EvidenceDisplay('authored-recorder-readable',True)
    text=view.update(sample(event='run_terminal',terminal='infrastructure_inconclusive',failure_category='observation_infrastructure',cleanup_confirmed=True,comparison_complete=False))
    assert 'cause: observation_infrastructure' in text
    assert 'comparison complete: False' in text and 'No task success or PEX lift inferred.' in text
