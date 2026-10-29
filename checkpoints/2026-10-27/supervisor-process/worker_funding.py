"""OPTIONAL paid worker accounting. No network/key code; exact approval-bound admission.

Each arm owns $0.375 and twelve attempts. Existing NVIDIA supervisor funding is
separate and unchanged. Guard-only RPC may call these methods; never expose
settlement to the model, remote tools, or candidate-controlled code.
"""
import hashlib
import json
import os
import re
import sqlite3
import stat
import threading
from functools import wraps
from pathlib import Path

# Exact owner approval of the one $1-total paired pilot; never future/unlimited authority.
APPROVED_SUCCESSOR_WORKER_REF = None  # One authorized pair consumed; no additional dispatch.
APPROVED_WORKER_REF = "Sentinel_9df859db703081919786cd38c9678f05"
ENDPOINT = "https://api.tokenfactory.nebius.com/v1/chat/completions"
MODEL = "deepseek-ai/DeepSeek-V4.1-Flash-1017"
INPUT_BOUND, OUTPUT_BOUND = 1048576, 4096
INPUT_RATE, OUTPUT_RATE = 300, 1200
RESERVATION = INPUT_BOUND * INPUT_RATE + OUTPUT_BOUND * OUTPUT_RATE
ARM_BUDGET, MAX_ATTEMPTS = 375000000, 12
PRICING_SHA = "50e7bb6a6548514fbfe49c25148234644b39a29a2f3caf5cd6b85cd6fc8f20a4"
ARMS = ("baseline", "pex")
MAX_BYTES = 2 * 1024 * 1024
ALLOWED_TOOLS = {"pex_remote_run", "pex_remote_read", "pex_remote_write", "pex_remote_list"}
WIRE_USAGE_REASONS = frozenset((
    'invalid worker accounting integer','duplicate wire field','nonfinite wire value',
    'missing complete usage','wire usage outside envelope','invalid usage details',
    'invalid usage detail count','response status uncertain','response size uncertain',
    'response type uncertain','incomplete worker response','unsupported worker response type',
    'truncated SSE framing','unsupported SSE field','SSE data after completion',
    'SSE model/identity mismatch','mixed SSE responses','SSE choices invalid',
    'SSE choice index invalid','SSE finish invalid','SSE output after finish',
    'ambiguous/nonterminal SSE usage','missing terminal SSE usage'))


def wire_usage_reason(error):
    """Only static parser codes; never retain arbitrary exception text."""
    if isinstance(error,json.JSONDecodeError):return 'wire_json_parse_invalid'
    if isinstance(error,UnicodeError):return 'wire_UTF8_invalid'
    value=error.args[0] if len(error.args)==1 else None
    return value.replace(' ','_').replace('/','_') if type(value)is str and value in WIRE_USAGE_REASONS else 'wire_validation_unclassified'


class WorkerBudgetExhausted(ValueError):
    def __init__(self, code):
        if code not in ("worker_budget_reservation_refused", "worker_attempt_cap_refused"):
            raise ValueError("invalid worker budget code")
        self.code = code
        super().__init__(code)


def _integer(value, maximum=10**15):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError("invalid worker accounting integer")
    return value


def _digest(value):
    if type(value) is not str or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError("invalid worker accounting digest")
    return value


def _json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError("duplicate wire field")
            result[key] = value
        return result
    def bad_constant(value): raise ValueError("nonfinite wire value")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=bad_constant)


def _request(raw, digest):
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_BYTES:
        raise ValueError("bounded exact request bytes required")
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("worker request digest mismatch")
    body = _json(raw)
    if (type(body) is not dict or body.get("model") != MODEL
            or type(body.get("max_completion_tokens")) is not int or body["max_completion_tokens"] != OUTPUT_BOUND
            or type(body.get("n", 1)) is not int or body.get("n", 1) != 1
            or "max_tokens" in body or "extra_body" in body or "best_of" in body
            or body.get("service_tier", "default") != "default"
            or type(body.get("messages")) is not list or not body["messages"]
            or type(body.get("stream", False)) is not bool):
        raise ValueError("worker request route/output/tier refused")
    if body.get("stream") and body.get("stream_options") != {"include_usage": True}:
        raise ValueError("streaming final usage required")
    tools = body.get("tools")
    if (type(tools) is not list or not tools or any(type(t) is not dict
            or t.get("type") != "function" or type(t.get("function")) is not dict
            or t["function"].get("name") not in ALLOWED_TOOLS for t in tools)):
        raise ValueError("worker tool admission refused")


def _usage(value):
    if type(value) is not dict:
        raise ValueError("missing complete usage")
    i, o, t = (_integer(value.get(k)) for k in ("prompt_tokens", "completion_tokens", "total_tokens"))
    if i + o != t or i > INPUT_BOUND or o > OUTPUT_BOUND:
        raise ValueError("wire usage outside envelope")
    for field, count in (("prompt_tokens_details", i), ("completion_tokens_details", o)):
        details = value.get(field)
        if details is not None:
            if type(details) is not dict: raise ValueError("invalid usage details")
            for item in details.values():
                if _integer(item) > count: raise ValueError("invalid usage detail count")
    # Cached tokens remain charged at full input rate; reasoning is already output.
    return {"input_tokens": i, "output_tokens": o, "total_tokens": t}


def _wire_usage(status, content_type, raw):
    if type(status) is not int or status != 200:
        raise ValueError("response status uncertain")
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_BYTES:
        raise ValueError("response size uncertain")
    if type(content_type) is not str: raise ValueError("response type uncertain")
    kind = content_type.split(";", 1)[0].strip().lower()
    if kind == "application/json":
        value = _json(raw)
        if (type(value) is not dict or value.get("model") != MODEL or value.get("error") is not None
                or type(value.get("choices")) is not list or len(value["choices"]) != 1
                or type(value["choices"][0]) is not dict
                or type(value["choices"][0].get("index")) is not int
                or value["choices"][0].get("index") != 0
                or value["choices"][0].get("finish_reason") not in ("stop", "length", "tool_calls")):
            raise ValueError("incomplete worker response")
        return _usage(value.get("usage"))
    if kind != "text/event-stream": raise ValueError("unsupported worker response type")
    text = raw.decode("utf-8").replace("\r\n", "\n")
    if not text.endswith("\n\n"): raise ValueError("truncated SSE framing")
    done = False
    usage = None
    finished = False
    stream_id = None
    for frame in text.split("\n\n"):
        if not frame.strip(): continue
        data = []
        for line in frame.splitlines():
            if line.startswith(":"): continue
            if not line.startswith("data:"): raise ValueError("unsupported SSE field")
            data.append(line[5:].lstrip(" "))
        if not data: continue
        payload = "\n".join(data)
        if done: raise ValueError("SSE data after completion")
        if payload == "[DONE]": done = True; continue
        value = _json(payload)
        if (type(value) is not dict or value.get("model") != MODEL
                or value.get("error") is not None or type(value.get("id")) is not str
                or not value["id"]): raise ValueError("SSE model/identity mismatch")
        if stream_id is None: stream_id = value["id"]
        if value["id"] != stream_id: raise ValueError("mixed SSE responses")
        choices = value.get("choices")
        if type(choices) is not list or len(choices) > 1: raise ValueError("SSE choices invalid")
        if choices:
            choice = choices[0]
            if type(choice) is not dict or type(choice.get("index")) is not int or choice["index"] != 0:
                raise ValueError("SSE choice index invalid")
            finish = choice.get("finish_reason")
            if finish is not None:
                if finished or finish not in ("stop", "length", "tool_calls"):
                    raise ValueError("SSE finish invalid")
                finished = True
            elif finished: raise ValueError("SSE output after finish")
        if value.get("usage") is not None:
            if usage is not None or not finished or choices:
                raise ValueError("ambiguous/nonterminal SSE usage")
            usage = _usage(value["usage"])
    if not done or not finished or usage is None:
        raise ValueError("missing terminal SSE usage")
    return usage


def _locked(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return call


class _WorkerLedger:
    """Private pure-accounting implementation; never grants provider authority."""
    def __init__(self, path, *, arm, approved_config_digest, approval_ref, pricing_provenance_sha256,
                 prior_charged_nano_usd=None, predecessor_sha256=None,
                 arm_budget_nano_usd=ARM_BUDGET, phase_limit_nano_usd=None,wire_evidence_sink=None):
        if wire_evidence_sink is not None and not callable(wire_evidence_sink):raise ValueError('trusted wire evidence sink required')
        self.wire_evidence_sink=wire_evidence_sink
        if arm not in ARMS or pricing_provenance_sha256 != PRICING_SHA:
            raise ValueError("worker arm/pricing identity refused")
        _digest(approved_config_digest)
        if type(approval_ref) is not str or not approval_ref:
            raise ValueError("worker approval identity missing")
        path = Path(path)
        if not path.is_absolute() or path.resolve() != path or path.is_symlink():
            raise ValueError("worker ledger absolute unlinked path required")
        parent = path.parent.stat()
        if parent.st_uid != os.geteuid() or stat.S_IMODE(parent.st_mode) & 0o077:
            raise ValueError("worker ledger private parent required")
        fresh = not path.exists()
        if fresh:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            os.close(fd)
        info = path.stat()
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) & 0o077): raise ValueError("worker ledger private file required")
        if type(arm_budget_nano_usd) is not int or arm_budget_nano_usd not in (375000000,350000000,410081800):
            raise ValueError("exact legacy or successor worker split required")
        self.arm_budget = arm_budget_nano_usd
        prior = {a: 0 for a in ARMS} if prior_charged_nano_usd is None else prior_charged_nano_usd
        if type(prior) is not dict or set(prior) != set(ARMS) or any(type(v) is not int or not 0 <= v <= self.arm_budget for v in prior.values()):
            raise ValueError("invalid prior worker charges")
        if any(prior.values()): _digest(predecessor_sha256)
        elif predecessor_sha256 is not None: _digest(predecessor_sha256)
        self.prior = dict(prior)
        phase = min(self.arm_budget-v for v in prior.values()) if phase_limit_nano_usd is None else phase_limit_nano_usd
        if type(phase) is not int or phase < 0 or any(v+phase>self.arm_budget for v in prior.values()):
            raise ValueError("common phase allowance exceeds original arm pool")
        if self.arm_budget == 350000000 and phase != 339918200:
            raise ValueError("exact preregistered successor phase allowance required")
        if self.arm_budget == 410081800 and (
            phase != 400000000 or prior != {"baseline":10081800,"pex":9382800}
        ):
            raise ValueError("exact pending USD2 predecessor and equal fresh phase required")
        self.phase_limit = phase
        self.predecessor_identity = (json.dumps(self.prior,sort_keys=True),predecessor_sha256,phase)
        self.arm = arm
        self.identity = (approved_config_digest, approval_ref, PRICING_SHA, ENDPOINT, MODEL,
                         INPUT_BOUND, OUTPUT_BOUND, INPUT_RATE, OUTPUT_RATE, self.arm_budget, MAX_ATTEMPTS)
        self._lock = threading.RLock()
        self.db = sqlite3.connect(path, timeout=2, isolation_level=None, check_same_thread=False)
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA journal_mode=DELETE")
        self.db.execute("CREATE TABLE IF NOT EXISTS config (digest TEXT,approval TEXT,pricing TEXT,endpoint TEXT,model TEXT,input_bound INTEGER,output_bound INTEGER,ir INTEGER,outr INTEGER,budget INTEGER,attempts INTEGER)")
        self.db.execute("CREATE TABLE IF NOT EXISTS calls (id TEXT PRIMARY KEY,arm TEXT,request_sha TEXT,reserved INTEGER,charged INTEGER,state TEXT,receipt TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS predecessor (charges TEXT,sha256 TEXT,phase_limit INTEGER)")
        predecessors = self.db.execute("SELECT * FROM predecessor").fetchall()
        if not predecessors and fresh:
            self.db.execute("INSERT INTO predecessor VALUES (?,?,?)",self.predecessor_identity)
        elif predecessors != [self.predecessor_identity]:
            self.db.close(); raise ValueError("worker predecessor identity changed")
        stored = self.db.execute("SELECT * FROM config").fetchall()
        if fresh and not stored:
            self.db.execute("INSERT INTO config VALUES (?,?,?,?,?,?,?,?,?,?,?)", self.identity)
        elif stored != [self.identity]:
            self.db.close(); raise ValueError("worker pricing/approval identity changed")
        try:
            self._validate()
        except BaseException:
            self.db.close()
            raise

    def _validate(self):
        if self.db.execute("SELECT * FROM config").fetchall() != [self.identity]:
            raise ValueError("stored worker config corrupt")
        if self.db.execute("SELECT * FROM predecessor").fetchall() != [self.predecessor_identity]:
            raise ValueError("stored worker predecessor corrupt")
        totals, counts = dict(self.prior), {a: 0 for a in ARMS}
        for call, arm, request, reserve, charge, state, receipt in self.db.execute("SELECT * FROM calls"):
            if (type(call) is not str or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", call)
                    or arm not in ARMS or _digest(request) != request
                    or type(reserve) is not int or reserve != RESERVATION
                    or _integer(charge) > reserve
                    or state not in ("reserved_uncertain", "uncertain", "settled_raw_wire")):
                raise ValueError("stored worker accounting corrupt")
            if state != "settled_raw_wire" and charge != reserve:
                raise ValueError("uncertain worker charge reduced")
            if state == "reserved_uncertain":
                if receipt is not None: raise ValueError("unexpected pending worker receipt")
            else:
                value = _json(receipt)
                if (type(value) is not dict or value.get("request_sha256") != request
                        or value.get("arm") != arm or value.get("call_id") != call):
                    raise ValueError("stored worker receipt identity corrupt")
                _digest(value.get("response_sha256"))
                if state == "settled_raw_wire":
                    u = value.get("usage")
                    if type(u) is not dict or value.get("status") != 200:
                        raise ValueError("stored worker usage corrupt")
                    i,o,t=(_integer(u.get(k)) for k in ("input_tokens","output_tokens","total_tokens"))
                    if i+o!=t or i>INPUT_BOUND or o>OUTPUT_BOUND or charge!=i*INPUT_RATE+o*OUTPUT_RATE:
                        raise ValueError("stored worker usage charge corrupt")
            totals[arm] += charge; counts[arm] += 1
        if any(totals[a] > self.arm_budget or totals[a]-self.prior[a] > self.phase_limit or counts[a] > MAX_ATTEMPTS for a in ARMS):
            raise ValueError("stored arm cap exceeded")
        return totals, counts

    @_locked
    def reserve(self, call_id, request_sha256, request_body):
        if type(call_id) is not str or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", call_id):
            raise ValueError("worker invocation id invalid")
        _digest(request_sha256); _request(request_body, request_sha256)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            totals, counts = self._validate()
            if counts[self.arm] >= MAX_ATTEMPTS: raise WorkerBudgetExhausted("worker_attempt_cap_refused")
            if totals[self.arm] + RESERVATION > self.arm_budget or totals[self.arm]-self.prior[self.arm]+RESERVATION > self.phase_limit: raise WorkerBudgetExhausted("worker_budget_reservation_refused")
            self.db.execute("INSERT INTO calls VALUES (?,?,?,?,?,?,?)", (call_id,self.arm,request_sha256,RESERVATION,RESERVATION,"reserved_uncertain",None))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK"); raise
        return {"reserved_nano_usd": RESERVATION, "arm": self.arm, "call_id": call_id}

    @_locked
    def settle_raw(self, call_id, request_sha256, status, content_type, rawbytes):
        _digest(request_sha256)
        if type(rawbytes) is not bytes or len(rawbytes)>MAX_BYTES:
            # Oversized/unavailable response never refunds pending reservation.
            raise ValueError("bounded raw wire bytes required")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self._validate()
            row=self.db.execute("SELECT arm,request_sha,state FROM calls WHERE id=?",(call_id,)).fetchone()
            if row!=(self.arm,request_sha256,"reserved_uncertain"):
                raise ValueError("worker reservation missing/settled/identity mismatch")
            state,charge,usage="uncertain",RESERVATION,None
            validation_code='validated_complete_wire'
            try:
                usage=_wire_usage(status,content_type,rawbytes)
            except (ValueError,TypeError,KeyError,UnicodeError) as error:
                validation_code=wire_usage_reason(error)
            else:
                charge=usage["input_tokens"]*INPUT_RATE+usage["output_tokens"]*OUTPUT_RATE
                state="settled_raw_wire"
            receipt=dict(call_id=call_id,arm=self.arm,request_sha256=request_sha256,
                         response_sha256=hashlib.sha256(rawbytes).hexdigest(),
                         status=status if type(status)is int else None,usage=usage,
                         usage_validation_code=validation_code)
            if self.wire_evidence_sink is not None:
                # NEW explicitly composed private evidence only. No legacy body
                # logging, header/key capture, changed settlement or old-row edit.
                evidence=self.wire_evidence_sink(self.arm,call_id,request_sha256,status,content_type,rawbytes,validation_code)
                if type(evidence)is not dict or set(evidence)!={'path','sha256'} or type(evidence['path'])is not str:
                    raise ValueError('exact private wire evidence pin required')
                _digest(evidence['sha256']);receipt['wire_evidence']=evidence
            self.db.execute("UPDATE calls SET charged=?,state=?,receipt=? WHERE id=? AND state='reserved_uncertain'",(charge,state,json.dumps(receipt,sort_keys=True),call_id))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK"); raise
        return {"charged_nano_usd":charge,"state":state,"arm":self.arm,"call_id":call_id}

    @_locked
    def usage_snapshot(self):
        """Trusted controller accounting only; unknown wire usage stays explicit.

        Counts accepted reservations for this arm, including uncertain delivery.
        Token sums include only validated raw-wire receipts, never guessed usage.
        This method is not exposed by the guard RPC or any model/remote tool.
        """
        self._validate()
        result = dict(calls=0, input_tokens=0, output_tokens=0, uncertain_calls=0)
        for state, receipt in self.db.execute(
                "SELECT state,receipt FROM calls WHERE arm=?", (self.arm,)):
            result["calls"] += 1
            if state != "settled_raw_wire":
                result["uncertain_calls"] += 1
                continue
            usage = _json(receipt)["usage"]
            for name in ("input_tokens", "output_tokens"):
                result[name] += usage[name]
        return result

    @_locked
    def summary(self):
        totals,counts=self._validate()
        return {"charged_nano_usd":totals,"attempts":counts,"per_arm_budget_nano_usd":self.arm_budget}

    @_locked
    def close(self): self.db.close()


class WorkerFunding(_WorkerLedger):
    """Reject every approval except the exact bounded one-pilot owner approval."""
    def __init__(self, *args, approval_ref=None, **kwargs):
        expected = (APPROVED_SUCCESSOR_WORKER_REF
                    if kwargs.get("arm_budget_nano_usd") == 410081800
                    else APPROVED_WORKER_REF)
        if expected is None or approval_ref != expected:
            raise PermissionError("optional_paid_worker_not_authorized")
        super().__init__(*args, approval_ref=approval_ref, **kwargs)
