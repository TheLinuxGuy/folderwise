"""Lossless task fields and the Obsidian Tasks projection protocol (no Obsidian runtime required).

The plugin owns recurrence calculations. The bridge validates its resulting rows and imports
them atomically, rather than implementing a second recurrence engine. See docs/obsidian.md.
"""
from __future__ import annotations

import datetime as dt
import re
import unicodedata


CHECKBOX = re.compile(r"^([\t >]*(?:[-*+]|\d+[.)])\s+\[)([^\]\r\n])(\].*)$")
SOURCE = re.compile(r' \(\[source\]\(([^)\n]+)\)\)')
ROW_ID = re.compile(r' "fw:([a-f0-9]+)"$')
DATES = {'start', 'scheduled', 'due', 'created', 'done', 'cancelled'}
SYMBOLS = {'🛫': 'start', '⏳': 'scheduled', '⌛': 'scheduled', '📅': 'due', '📆': 'due',
           '🗓': 'due', '➕': 'created', '✅': 'done', '❌': 'cancelled', '🔁': 'repeat',
           '🏁': 'onCompletion', '🆔': 'id', '⛔': 'dependsOn'}
PRIORITIES = {'🔺': 'highest', '⏫': 'high', '🔼': 'medium', '🔽': 'low', '⏬': 'lowest'}
EMOJI = re.compile(r'(?:^|[ \t]+)([🛫⏳⌛📅📆🗓➕✅❌🔁🏁🆔⛔🔺⏫🔼🔽⏬])\ufe0f?')
INLINE = re.compile(r'(?:^|[ \t]+)(\[(\w+):: *([^\]\n]*)\]|\((\w+):: *([^\)\n]*)\)) *,?$')
BLOCK = re.compile(r'\s+(\^[a-zA-Z0-9-]+)$')
KEYS = {'completion': 'done', **{k: k for k in [*DATES, 'priority', 'repeat', 'onCompletion', 'id', 'dependsOn']}}


def mask_fences(text):
    """Hide quoted/list-indented fences while retaining source line numbers and offsets."""
    lines, fence = [], None
    for raw in text.splitlines(keepends=True):
        content = re.sub(r'^[\t >]*', '', raw.rstrip('\r\n'))
        marker = re.match(r'(`{3,}|~{3,})(.*)$', content)
        hidden = fence is not None
        if marker:
            token, tail = marker.groups()
            if fence:
                if token[0] == fence[0] and len(token) >= fence[1] and not tail.strip():
                    fence = None
            elif token[0] != '`' or '`' not in tail:
                fence = (token[0], len(token))
                hidden = True
        lines.append(re.sub(r'[^\r\n]', ' ', raw) if hidden else raw)
    return ''.join(lines)


def fields(text):
    """Split description and trailing fields, preserving each field's exact spelling/order.

    Like Tasks, only a trailing metadata run is interpreted. Unknown inline fields remain
    description text. Tags may occur between fields. No date/recurrence is inferred.
    """
    rest, parts, values = text.rstrip(), [], {}
    hardbreak = text[len(text.rstrip()):] if text.endswith('  ') else ''
    block = BLOCK.search(rest)
    if block:
        parts.insert(0, ('block', block[0]))
        values['block'] = block[1]
        rest = rest[:block.start()].rstrip()
    while rest:
        tag = re.search(r'(?:^|[ \t]+)(#[^\s#]+)$', rest)
        inline = INLINE.search(rest)
        emojis = list(EMOJI.finditer(rest))
        emoji = emojis[-1] if emojis else None
        if tag:
            key, value, raw, start = 'tag', tag[1], rest[tag.start():], tag.start()
        elif inline and (inline[2] or inline[4]) in KEYS:
            key = KEYS[inline[2] or inline[4]]
            value, raw, start = (inline[3] if inline[2] else inline[5]).strip(), rest[inline.start():], inline.start()
        elif emoji:
            symbol, value = emoji[1], rest[emoji.end():].strip()
            key = 'priority' if symbol in PRIORITIES else SYMBOLS[symbol]
            if key == 'priority':
                if value:
                    break
                value = PRIORITIES[symbol]
            raw, start = rest[emoji.start():], emoji.start()
        else:
            break
        if key != 'tag' and key in values:
            raise ValueError(f'duplicate task field: {key}')
        parts.insert(0, (key, raw))
        if key != 'tag':
            values[key] = value
        rest = rest[:start].rstrip()
    return dict(description=rest, fields=values, parts=parts, hardbreak=hardbreak)


def render(parsed, description=None, source=''):
    """A source link belongs to the description, before metadata (block IDs stay last)."""
    text = parsed['description'] if description is None else description
    return text + source + ''.join(raw if raw[:1].isspace() else ' ' + raw for _, raw in parsed['parts']) + parsed.get('hardbreak', '')


def validate(parsed):
    for key, value in parsed['fields'].items():
        if key in DATES:
            try:
                if dt.date.fromisoformat(value).isoformat() != value:
                    raise ValueError()
            except ValueError:
                raise ValueError(f'{key} must be a valid YYYY-MM-DD date') from None
        elif key == 'priority' and value not in PRIORITIES.values():
            raise ValueError('unrecognised task priority')
        elif key == 'onCompletion' and value not in {'keep', 'delete'}:
            raise ValueError('onCompletion must be keep or delete')
        elif key == 'repeat' and (not value or not re.fullmatch(r'[a-zA-Z0-9, !]+', value)):
            raise ValueError('invalid recurrence rule')
        elif key == 'id' and not re.fullmatch(r'[a-zA-Z0-9_-]+', value):
            raise ValueError('invalid task ID')
        elif key == 'dependsOn' and not re.fullmatch(r'[a-zA-Z0-9_-]+(?: *, *[a-zA-Z0-9_-]+)*', value):
            raise ValueError('invalid task dependencies')


def project_ids(text, inverse=False):
    """Keep Tasks' globally indexed IDs distinct from the copied authoritative notes."""
    parsed = fields(text)
    values = parsed['fields']
    for i, (key, raw) in enumerate(parsed['parts']):
        if key not in {'id', 'dependsOn'}:
            continue
        value = values[key]
        def convert(match):
            token = match[0]
            return token.removeprefix('fwview-') if inverse else 'fwview-' + token
        projected = re.sub(r'[a-zA-Z0-9_-]+', convert, value)
        start = raw.rfind(value)
        parsed['parts'][i] = (key, raw[:start] + projected + raw[start + len(value):])
    return render(parsed)


def safe_text(text):
    """Allow emoji shaping (ZWJ/variation selectors), never bidi/control or forged markers."""
    if any(unicodedata.category(c) in {'Cc', 'Cf', 'Zl', 'Zp'} and c != '\u200d' for c in text):
        raise ValueError('a title cannot contain control, direction or line-break characters')
    if '<!--' in text or '-->' in text or ' ([source](' in text:
        raise ValueError('a title cannot contain comment markers or a source link')


def view_row(line):
    body = line.rstrip('\r\n')
    match = CHECKBOX.match(body)
    if not match or not match[3].startswith('] '):
        return None
    links = list(SOURCE.finditer(match[3][1:]))
    if len(links) != 1:
        return None
    link = links[0]
    text = match[3][1:]
    title = (text[:link.start()] + text[link.end():]).lstrip(' ')
    marker = ROW_ID.search(link[1])
    return dict(head=match[1], status=match[2], title=title, source=link[0],
                token=marker[1] if marker else link[0], ending=line[len(body):], suffix=text[link.end():])


def merge_title(base, phone, current):
    """Merge independent field changes; a same-field disagreement requires review."""
    a, b, c = map(fields, (base, phone, current))
    validate(b)
    a_raw, b_raw = dict(a['parts']), dict(b['parts'])
    changed = {k for k in a['fields'].keys() | b['fields'].keys()
               if a['fields'].get(k) != b['fields'].get(k) or a_raw.get(k) != b_raw.get(k)}
    if a['description'] != b['description']:
        if c['description'] not in (a['description'], b['description']):
            raise ValueError('description also changed on the Mac')
        c['description'] = b['description']
    for key in changed:
        if c['fields'].get(key) not in (a['fields'].get(key), b['fields'].get(key)):
            raise ValueError(f'{key} also changed on the Mac')
    # Keep untouched Mac tokens verbatim. Replace only fields edited by the phone.
    seen, result = set(), []
    for key, raw in c['parts']:
        seen.add(key)
        if key not in changed:
            result.append((key, raw))
        elif key in b_raw:
            result.append((key, b_raw[key]))
    result += [(key, raw) for key, raw in b['parts'] if key in changed and key not in seen]
    c['parts'] = [p for p in result if p[0] != 'block'] + [p for p in result if p[0] == 'block']
    # Tags are part of the description semantically; preserve them unless the phone changed them.
    tags_a = [raw for key, raw in a['parts'] if key == 'tag']
    tags_b = [raw for key, raw in b['parts'] if key == 'tag']
    if tags_a != tags_b:
        tags_c = [raw for key, raw in c['parts'] if key == 'tag']
        if tags_c not in (tags_a, tags_b):
            raise ValueError('tags also changed on the Mac')
        c['parts'] = [(k, v) for k, v in c['parts'] if k != 'tag']
        pos = next((i for i, p in enumerate(c['parts']) if p[0] == 'block'), len(c['parts']))
        c['parts'][pos:pos] = [('tag', raw) for raw in tags_b]
    if a['hardbreak'] != b['hardbreak']:
        c['hardbreak'] = b['hardbreak']
    return render(c)
