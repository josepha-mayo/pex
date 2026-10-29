"""Local authored CLI-process fixtures only: no provider, VM, or credentials."""
import asyncio
import json
import signal
import sqlite3
import sys
import time

import pytest

import opencode_cli as cli

SCRIPT = r'''
import json, os, sqlite3, sys, time
mode = os.environ['FIXTURE_MODE']
db = os.environ['FIXTURE_DB']
prompt = sys.stdin.read()
payload = {'finish': 'stop', 'rawFinish': 'stop', 'time': {'completed': 10},
           'content': [{'type': 'text', 'text': 'authored terminal'}]}
if mode == 'length': payload.update(finish='length', rawFinish='length')
if mode == 'incomplete': payload.pop('finish'); payload['time'] = {}
if mode == 'error': payload['error'] = {'name': 'AUTHORED_ERROR'}
if mode == 'tool': payload['content'].append({'type': 'tool', 'state': {'status': 'completed'}})
with sqlite3.connect(db) as c:
 c.executescript('CREATE TABLE session_v2(id,version,idle_outcome); CREATE TABLE session_message(id,type,seq,data,session_id); CREATE TABLE session_pending(session_id);')
 c.execute("INSERT INTO session_v2 VALUES ('s','2.1.4','succeeded')")
 c.execute('INSERT INTO session_message VALUES (?,?,?,?,?)', ('u','user',1,json.dumps({'text': prompt if mode != 'prompt' else 'wrong prompt'}),'s'))
 c.execute('INSERT INTO session_message VALUES (?,?,?,?,?)', ('a','assistant',2,json.dumps(payload),'s'))
 if mode == 'error_row': c.execute('INSERT INTO session_message VALUES (?,?,?,?,?)', ('e','error',3,json.dumps({'error': 'AUTHORED'}),'s'))
 if mode != 'incomplete': c.execute('INSERT INTO session_message VALUES (?,?,?,?,?)', ('i','idle',4,json.dumps({'outcome':'succeeded'}),'s'))
 if mode == 'pending': c.execute("INSERT INTO session_pending VALUES ('s')")
vendor = 'other' if mode == 'session' else 's'
event = {'type':'text','sessionID':vendor,'part':{'sessionID':vendor,'messageID':'a','text':'changed' if mode == 'text' else 'authored terminal'}}
line = json.dumps(event)
print(line[:-8] if mode == 'partial' else line, flush=True)
if mode == 'exit': sys.exit(0)
if mode == 'exit_error': os._exit(3)
while True: time.sleep(1)
'''


def invoke(tmp_path, mode='linger', seconds=1.5):
    binary = tmp_path / 'authored-cli'
    binary.write_text('#!' + sys.executable + '\n' + SCRIPT)
    binary.chmod(0o700)
    return cli.run_turn(
        executable=binary, workspace=tmp_path, model='authored/no-inference',
        prompt='exact authored prompt', environment={
            'FIXTURE_MODE': mode, 'FIXTURE_DB': str(tmp_path / 'cli.sqlite'),
        }, stdout_path=tmp_path / 'turn.jsonl', stderr_path=tmp_path / 'turn.stderr',
        deadline=time.monotonic() + seconds, terminal_database=tmp_path / 'cli.sqlite',
    )


@pytest.mark.parametrize('condition', ['baseline', 'pex'])
def test_trusted_stop_without_footer_shuts_lingering_owned_renderer(tmp_path, condition):
    # Identical adapter/configuration and stop rule for both condition labels.
    work = tmp_path / condition
    work.mkdir()
    started = time.monotonic()
    turn = asyncio.run(invoke(work))
    assert time.monotonic() - started < 1.4
    assert turn.messages == ('authored terminal',)
    assert turn.actual_process_exit_code == -signal.SIGKILL
    assert turn.completion_kind == 'committed_terminal_before_owned_shutdown'
    assert turn.terminal_observed_before_shutdown and turn.owned_process_group_exit_confirmed
    assert len(turn.committed_terminal_sha256) == 64
    assert 'step_finish' not in (work / 'turn.jsonl').read_text()
    evidence = json.loads((work / 'turn.jsonl.process.json').read_text())
    assert evidence['trusted_terminal_observed_before_shutdown']
    assert evidence['actual_process_exit_code'] == -signal.SIGKILL
    assert evidence['owned_process_group_exit_confirmed']
    assert (work / 'turn.jsonl.process.json').stat().st_mode & 0o077 == 0


def test_ordinary_exit_zero_keeps_actual_exit_provenance(tmp_path):
    turn = asyncio.run(invoke(tmp_path, 'exit'))
    assert turn.actual_process_exit_code in (0, -signal.SIGKILL)
    assert turn.owned_process_group_exit_confirmed
    assert turn.committed_terminal_sha256


def test_known_nonzero_exit_is_not_overridden_by_a_DB_stop(tmp_path):
    with pytest.raises(ValueError):
        asyncio.run(invoke(tmp_path, 'exit_error'))
    evidence = json.loads((tmp_path / 'turn.jsonl.process.json').read_text())
    assert evidence['actual_process_exit_code'] == 3


def test_terminal_first_observed_after_deadline_is_not_salvaged(tmp_path, monkeypatch):
    import opencode_v2_receipt as reader

    parse = reader.committed_turn_v2

    def delayed(*args, **kwargs):
        result = parse(*args, **kwargs)
        time.sleep(0.15)
        return result

    monkeypatch.setattr(reader, 'committed_turn_v2', delayed)
    with pytest.raises(TimeoutError):
        asyncio.run(invoke(tmp_path, seconds=0.15))


@pytest.mark.parametrize('mode', ['incomplete', 'length', 'error', 'error_row', 'tool', 'pending',
                                 'session', 'prompt', 'text', 'partial'])
def test_forced_midturn_or_mismatched_terminal_never_natural(tmp_path, mode):
    with pytest.raises(TimeoutError):
        asyncio.run(invoke(tmp_path, mode, seconds=0.25))
    evidence = json.loads((tmp_path / 'turn.jsonl.process.json').read_text())
    assert not evidence['trusted_terminal_observed_before_shutdown']
    assert evidence['owned_process_group_exit_confirmed']
    assert evidence['actual_process_exit_code'] == -signal.SIGKILL


def test_terminal_mutation_during_shutdown_is_rejected(tmp_path, monkeypatch):
    stop = cli._stop_owned_process

    async def mutate(process, tasks):
        with sqlite3.connect(tmp_path / 'cli.sqlite') as c:
            c.execute("UPDATE session_message SET data=? WHERE type='user'",
                      (json.dumps({'text': 'mutated after observation'}),))
        return await stop(process, tasks)

    monkeypatch.setattr(cli, '_stop_owned_process', mutate)
    with pytest.raises(ValueError, match='prompt'):
        asyncio.run(invoke(tmp_path))


def test_valid_but_different_terminal_proof_is_rejected(tmp_path, monkeypatch):
    stop = cli._stop_owned_process

    async def mutate(process, tasks):
        with sqlite3.connect(tmp_path / 'cli.sqlite') as c:
            payload = json.loads(c.execute("SELECT data FROM session_message WHERE type='assistant'").fetchone()[0])
            payload['time']['completed'] = 11  # Still valid, but not the observed proof.
            c.execute("UPDATE session_message SET data=? WHERE type='assistant'", (json.dumps(payload),))
        return await stop(process, tasks)

    monkeypatch.setattr(cli, '_stop_owned_process', mutate)
    with pytest.raises(ValueError, match='changed during owned shutdown'):
        asyncio.run(invoke(tmp_path))


def test_replaced_terminal_DB_even_with_identical_rows_is_rejected(tmp_path, monkeypatch):
    stop = cli._stop_owned_process

    async def replace_database(process, tasks):
        source = tmp_path / 'cli.sqlite'
        copy = tmp_path / 'copy.sqlite'
        with sqlite3.connect(source) as a, sqlite3.connect(copy) as b:
            a.backup(b)
        copy.replace(source)
        return await stop(process, tasks)

    monkeypatch.setattr(cli, '_stop_owned_process', replace_database)
    with pytest.raises(ValueError, match='changed during owned shutdown'):
        asyncio.run(invoke(tmp_path))


def test_unbounded_process_wait_cannot_hang_cleanup(monkeypatch):
    monkeypatch.setattr(cli, 'PROCESS_CLEANUP_SECONDS', 0.05)
    monkeypatch.setattr(cli.os, 'killpg', lambda *args: None)

    class Transport:
        closed = False

        def close(self):
            self.closed = True

    class Process:
        pid = 123456789
        returncode = None
        _transport = Transport()

    async def exercise():
        waiting = asyncio.Event()
        task = asyncio.create_task(waiting.wait())
        start = time.monotonic()
        with pytest.raises(cli.CliCleanupUnconfirmed):
            await cli._stop_owned_process(Process(), [task])
        assert time.monotonic() - start < 0.3
        await asyncio.sleep(0)
        assert task.cancelled() and Process._transport.closed

    asyncio.run(exercise())


def test_output_bound_does_not_become_terminal(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, 'MAX_OUTPUT_BYTES', 16)
    with pytest.raises(ValueError, match='output exceeded'):
        asyncio.run(invoke(tmp_path))


def test_legacy_mode_does_not_get_DB_terminal_bypass(tmp_path):
    binary = tmp_path / 'authored-legacy-cli'
    binary.write_text('#!' + sys.executable + '\nprint(\'{}\', flush=True)\n')
    binary.chmod(0o700)
    with pytest.raises(ValueError):
        asyncio.run(cli.run_turn(executable=binary, workspace=tmp_path, model='authored/no-inference',
            prompt='authored', environment={}, stdout_path=tmp_path/'out', stderr_path=tmp_path/'err',
            deadline=time.monotonic()+1))
