#!/usr/bin/env python3
"""Example project-owned adapter. Copy to scripts/ibridge_adapter.py and customize.

Fictional schema: data/tasks.csv has task_id,title,status,detail_path columns.
The generated checklist in docs/actions.md sits between tasks:start/tasks:end.
Use only open/complete statuses here; map other project states explicitly.

Task renames from the phone are optional. This example advertises editable=["title"] so a project that sets
`folderwise-ibridgerename: true` can rename tasks. `apply` then receives `title` and `expected_title`: compare
before writing and fail if the row changed on the Mac. Remove the `editable` entry to keep titles Mac-only.
"""
import csv
import json
import re
import sys
from pathlib import Path

SOURCE = Path('data/tasks.csv')
VIEW = Path('docs/actions.md')
BLOCK = r'<!-- tasks:start -->.*?<!-- tasks:end -->'


def rendered(rows):
    return '<!-- tasks:start -->\n' + ''.join(
        '- [ ] ' + row['title'] + '\n' for row in rows if row['status'] != 'complete'
    ) + '<!-- tasks:end -->'


def main():
    with SOURCE.open(newline='') as stream:
        reader = csv.DictReader(stream)
        rows, fields = list(reader), reader.fieldnames
    assert len({row['task_id'] for row in rows}) == len(rows), 'duplicate task IDs'
    assert all(row['status'] in ('open', 'complete') for row in rows), 'unknown status'
    command = sys.argv[1]
    if command == 'list':
        print(json.dumps([dict(id=row['task_id'], title=row['title'], editable=['title'],
                               checked=row['status'] == 'complete', path=str(VIEW)) for row in rows]))
    elif command == 'apply':
        changes = json.load(sys.stdin)
        by_id = {row['task_id']: row for row in rows}
        for change in changes:
            assert type(change['checked']) is bool, 'expected boolean'
            row = by_id[change['id']]
            row['status'] = 'complete' if change['checked'] else 'open'
            if 'title' in change:
                assert row['title'] == change['expected_title'], 'task changed on the Mac'
                row['title'] = change['title']
        with SOURCE.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        text, count = re.subn(BLOCK, lambda _: rendered(rows), VIEW.read_text(), flags=re.S)
        assert count == 1, 'expected exactly one generated task block'
        VIEW.write_text(text)
    elif command == 'validate':
        match = re.search(BLOCK, VIEW.read_text(), flags=re.S)
        assert match and match[0] == rendered(rows), 'generated checklist is stale'
    else:
        raise ValueError('expected list, apply or validate')


if __name__ == '__main__':
    main()
