"""Read-only accounting of local H3 jobs; missing history is not proof of failure."""
import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import re
import statistics

ROOT = Path(__file__).resolve().parents[1]


def audit(prefix):
    paths = list((ROOT / 'runs').glob(f'{prefix}*/jobs/**/job.json'))
    paths += list((ROOT / 'logs').glob('*.json'))
    records = {}
    image_jobs = []
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding='utf-8-sig'))
        except (ValueError, OSError):
            continue
        name = data.get('settings', {}).get('name', path.as_posix())
        prompt_path = data.get('settings', {}).get('prompt_file', '') or ''
        if prefix not in name and prefix not in path.as_posix() and prefix.rstrip('_') not in prompt_path:
            continue
        match = re.search(r'ep(\d+)_s(\d+)([a-z]?)', name)
        if not match:
            continue
        history = data.get('history', {})
        graph = history.get('prompt', [None, None, {}])[2]
        graph_file = path.parent / 'workflow_api.json'
        if not graph and graph_file.exists():
            graph = json.loads(graph_file.read_text(encoding='utf-8-sig'))
        pid = data.get('prompt_id')
        if not pid:
            continue
        if not any(n.get('class_type', '').startswith('MiniMaxH3') for n in graph.values()):
            # Direct-client incomplete records have settings but no embedded graph.
            if not data.get('settings'):
                image_jobs.append({'prompt_id': pid, 'path': str(path.relative_to(ROOT)),
                                   'seconds': data.get('server_seconds', 0)})
                continue
        events = dict(history.get('status', {}).get('messages', []))
        start = events.get('execution_start', {}).get('timestamp')
        end = events.get('execution_success', events.get('execution_error', {})).get('timestamp')
        status = history.get('status', {}).get('status_str', data.get('status', 'unresolved'))
        if status == 'running':
            status = 'unresolved'
        seconds = (end - start) / 1000 if start is not None and end is not None else data.get('server_seconds')
        resource = path.with_suffix('.resources.jsonl') if path.parent == ROOT / 'logs' else path.parent / 'resources.jsonl'
        observed = 0
        if resource.exists():
            with resource.open(encoding='utf-8') as stream:
                for line in stream:
                    try:
                        observed = max(observed, json.loads(line).get('elapsed_seconds', 0))
                    except ValueError:
                        pass
        submitted = data.get('started_at')
        if submitted is None and data.get('submitted_at'):
            submitted = datetime.fromisoformat(data['submitted_at']).timestamp()
        files = [f for out in history.get('outputs', {}).values()
                 for f in out.get('images', [])]
        record = dict(prompt_id=pid, episode=int(match[1]), shot='s' + match[2], variant=match[3],
                      status=status, server_seconds=seconds, observed_seconds=observed,
                      submitted_epoch=submitted, outputs=files, record=str(path.relative_to(ROOT)))
        if pid not in records or history:
            records[pid] = record
    rows = sorted(records.values(), key=lambda r: (r['submitted_epoch'] or 0, r['record']))
    episodes = {}
    for ep in sorted({r['episode'] for r in rows}):
        selected = [r for r in rows if r['episode'] == ep]
        durations = [r['server_seconds'] for r in selected if r['status'] == 'success' and r['server_seconds'] is not None]
        episodes[str(ep)] = dict(attempts=len(selected), statuses=dict(Counter(r['status'] for r in selected)),
            success_server_minutes=round(sum(durations)/60, 2),
            success_median_seconds=round(statistics.median(durations), 2) if durations else None,
            unresolved_observed_minutes=round(sum(r['observed_seconds'] for r in selected if r['status'] == 'unresolved')/60, 2),
            per_shot=dict(Counter(r['shot'] for r in selected)))
    return dict(note='Unique prompt IDs. Success means execution only. Unresolved observations are lower bounds, may overlap, and are not GPU compute time. Prefix scan is not a complete wall-clock ledger.',
                episodes=episodes, image_jobs_count=len({r['prompt_id'] for r in image_jobs}),
                image_server_minutes=round(sum(r['seconds'] or 0 for r in image_jobs)/60, 2), records=rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', default='47ky_')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.prefix)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'records'}, ensure_ascii=False, indent=2))
