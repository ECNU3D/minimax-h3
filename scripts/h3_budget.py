"""Durable submission budget, shared by all run directories of one campaign."""
import json
from pathlib import Path
import re
from workflow_client import save_json


class BudgetStop(RuntimeError):
    pass


class Budget:
    MAX_ATTEMPTS = 2
    MAX_FAILURES = 3

    def __init__(self, folder):
        self.folder = Path(folder)
        self.path = self.folder / 'budget.json'
        self.stop_path = self.folder / 'STOP.json'
        self.data = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {
            'max_attempts_per_shot': self.MAX_ATTEMPTS, 'max_failures': self.MAX_FAILURES,
            'attempts': {}, 'outcomes': {}, 'failure_count': 0}

    def check(self):
        if self.stop_path.exists():
            raise BudgetStop(f'Campaign latched STOP: {self.stop_path}')

    def halt(self, reason):
        save_json(self.stop_path, dict(status='STOP', reason=reason,
            agent_action='End this goal turn. Do not resubmit, change campaign/name, delete budget, or reset without a new user instruction.'))
        raise BudgetStop(reason)

    @staticmethod
    def logical_name(name):
        # Legacy s07b/s07c are revisions of s07, not fresh budgets.
        return re.sub(r'(_s\d+)[a-z]+$', r'\1', name)

    def reserve(self, name, attempt_key):
        self.check()
        if attempt_key in self.data['outcomes']:
            self.halt('Submission already reserved without a resumable job record; reconcile server history, do not resubmit.')
        name = self.logical_name(name)
        attempts = self.data['attempts'].setdefault(name, [])
        if len(attempts) >= self.data['max_attempts_per_shot']:
            self.halt(f'{name}: submission budget exhausted ({len(attempts)})')
        attempts.append(attempt_key)
        self.data['outcomes'][attempt_key] = 'reserved'
        save_json(self.path, self.data)

    def finish(self, name, attempt_key, success):
        if attempt_key not in self.data['outcomes']:
            return  # Read-only reuse of a pre-budget job does not claim accounting coverage.
        if self.data['outcomes'].get(attempt_key) in ('success', 'failed'):
            return
        self.data['outcomes'][attempt_key] = 'success' if success else 'failed'
        if not success:
            self.data['failure_count'] += 1
        save_json(self.path, self.data)
        if self.data['failure_count'] >= self.data['max_failures']:
            self.halt(f'Campaign execution failures reached {self.data["failure_count"]}')
        attempts = self.data['attempts'].get(self.logical_name(name), [])
        if not success and len(attempts) >= self.data['max_attempts_per_shot']:
            self.halt(f'{name}: second execution attempt failed')

    def rejected(self, attempt_key):
        # A definitive validation rejection consumes its reservation, but is not
        # an execution failure. Never refund attempts or clear STOP here.
        if self.data['outcomes'].get(attempt_key) == 'reserved':
            self.data['outcomes'][attempt_key] = 'rejected'
            save_json(self.path, self.data)
