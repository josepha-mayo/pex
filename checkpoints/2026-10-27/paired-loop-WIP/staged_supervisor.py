"""WIP fresh closed-grant supervisor composition, no legacy approval reuse.

Reuses the reviewed full owned planner/verifier protocol and its exact task /
session binding, NOT the legacy admission loader. No model or credential is
constructed on import. Shared accounting belongs to StagedAccounting.
"""
from pathlib import Path
from staged_admission import AdmissionRefused,read_pin
from staged_accounting import StagedAccounting
from successor_supervisor import ManagedSuccessor,_telemetry
from stockroom_task import load_package,FILES,digest,encoded,package_contract


class StagedSupervisor(ManagedSuccessor):
    def __init__(self,accounting):
        if type(accounting) is not StagedAccounting:raise AdmissionRefused('closed_staged_accounting_required')
        accounting.before_reserve();_telemetry()
        self.accounting=accounting;self.closed=False;self.routes=accounting.routes
        self.ledger=accounting.supervisor_ledger
        self.config,self.objective=self._frozen_inputs()
        self.identity=(accounting.binding.admitted.grant.config_sha256,
                       accounting.binding.admitted.grant.approval_ref,accounting.cfg['predecessor']['sha256'])
        db=self.ledger.db
        db.execute('CREATE TABLE IF NOT EXISTS staged_supervisor_admission(config TEXT,approval TEXT,predecessor TEXT,state TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS successor_binding(goal TEXT,session TEXT,vendor TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS successor_reviews(request_sha TEXT PRIMARY KEY)')
        db.execute('BEGIN IMMEDIATE')
        try:
            if db.execute('SELECT * FROM staged_supervisor_admission').fetchall() or db.execute('SELECT COUNT(*) FROM calls').fetchone()[0]:
                raise AdmissionRefused('fresh_single_supervisor_runtime_required')
            db.execute('INSERT INTO staged_supervisor_admission VALUES (?,?,?,?)',(*self.identity,'active'))
            db.execute('COMMIT')
        except BaseException:db.execute('ROLLBACK');raise

    def _frozen_inputs(self):
        cfg=self.accounting.cfg
        read_pin(cfg['task'])
        package=Path(cfg['task']['path']).parent
        contract=package_contract(package)
        if cfg['task']['sha256']!=contract['manifest_sha256']:raise AdmissionRefused('source_pinned_stockroom_task_required')
        task=load_package(package)
        public=digest(encoded({n:digest(task['public/'+n]) for n in FILES}))
        net=cfg['network']
        narrow={'public_sha256':public,'key':dict(cfg['nebius_key']),
            'platform_proxy':{'proxy_sha256':net['proxy_sha256'],'ca_path':net['ca']['path'],'ca_sha256':net['ca']['sha256']}}
        objective=task['INITIAL_PROMPT.txt'].decode()+'\n\nFrozen PUBLIC TASK.md:\n'+task['public/TASK.md'].decode()
        return narrow,objective

    def revalidate(self):
        if self.closed:raise AdmissionRefused('staged_supervisor_closed')
        self.accounting.before_reserve();_telemetry()
        for pin in self.accounting.cfg['sources'].values():read_pin(pin)
        if self._frozen_inputs()!=(self.config,self.objective):raise AdmissionRefused('frozen_staged_supervisor_inputs_changed')
        if self.ledger.db.execute('SELECT * FROM staged_supervisor_admission').fetchall()!=[(*self.identity,'active')]:
            raise AdmissionRefused('staged_supervisor_identity_changed')
        return self.config

    def credential(self,route):
        self.revalidate()
        from managed_chat import _ScopedCredential
        if route not in self.routes:raise AdmissionRefused('supervisor_route_changed')
        raw=read_pin(self.config['key'],private=True,limit=16384)
        return _ScopedCredential(raw.decode('ascii').strip(),route.fingerprint)

    def summary(self):return self.accounting.summary()

    def archive_wire(self,kind,invocation_id,route,body,status):
        # Body-only private evidence, not a transport or authority capability.
        if self.closed:raise AdmissionRefused('staged_supervisor_closed')
        return self.accounting.archive_supervisor_wire(kind,invocation_id,route,body,status)

    def close(self):
        if self.closed:return
        db=self.ledger.db
        db.execute('BEGIN IMMEDIATE')
        try:
            if db.execute('SELECT * FROM staged_supervisor_admission').fetchall()!=[(*self.identity,'active')]:
                raise AdmissionRefused('staged_supervisor_close_identity_unconfirmed')
            db.execute("UPDATE staged_supervisor_admission SET state='closed'");db.execute('COMMIT')
        except BaseException:db.execute('ROLLBACK');raise
        self.closed=True  # Accounting owner closes the shared ledger separately.
