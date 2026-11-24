"""Copy selected canonical skills to agent discovery folders; back up changed files."""
import argparse
from datetime import datetime
import hashlib
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').digest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--names', nargs='+', required=True)
    p.add_argument('--apply', action='store_true')
    args = p.parse_args()
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    changed = 0
    for name in args.names:
        if '/' in name or '\\' in name or name in ('.', '..'):
            raise ValueError('Use skill directory names only')
        source = ROOT/'skills'/name
        if not (source/'SKILL.md').is_file():
            raise ValueError(f'No skill: {source}')
        for agent in ('.trae', '.agents', '.claude'):
            dest = ROOT/agent/'skills'/name
            # Some Windows checkouts preserve Unix symlinks as small text files.
            if dest.is_file():
                placeholder = dest.read_text(encoding='utf-8').strip().rstrip('/') if dest.stat().st_size < 4096 else ''
                if not placeholder.endswith('/skills/' + name):
                    raise ValueError(f'Not a recognized legacy skill link; preserve and inspect: {dest}')
                changed += 1
                if args.apply:
                    backup = ROOT/'.cache/skill-sync-backups'/stamp/agent/(name + '.legacy-link.txt')
                    dest.resolve().relative_to(ROOT.resolve())
                    backup.resolve().relative_to(ROOT.resolve())
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(dest), str(backup))
            for file in source.rglob('*'):
                if not file.is_file() or '__pycache__' in file.parts or file.suffix == '.pyc':
                    continue
                target = dest/file.relative_to(source)
                target.resolve().relative_to(ROOT.resolve())
                if target.exists() and digest(target) == digest(file):
                    continue
                changed += 1
                if args.apply:
                    if target.exists():
                        backup = ROOT/'.cache/skill-sync-backups'/stamp/agent/name/file.relative_to(source)
                        backup.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(target, backup)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(file, target)
    print(f'{"Synced" if args.apply else "Would sync"} {changed} files; originals backed up; no files deleted.')


if __name__ == '__main__':
    main()
