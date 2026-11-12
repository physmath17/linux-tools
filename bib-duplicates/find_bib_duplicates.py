#!/usr/bin/env python3
"""
find_bib_duplicates.py

Scan a (potentially very large) .bib file and report entries that share the same 'title' field, even if capitalization, whitespace, braces, or trailing punctuation differ.

Usage:
    python find_bib_duplicates.py references.bib
    python find_bib_duplicates.py references.bib --output report.txt
"""

import re
import sys
import argparse
from collections import defaultdict


def find_matching_brace(text, start):
    """Given text and the index of an opening '{', return the index of its
    matching closing '}', correctly handling nested braces."""
    depth = 0
    i = start
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1  # malformed / unmatched braces


def extract_entries(bib_text):
    """Yield (cite_key, entry_type, fields_text) for every @type{key, ...}
    block in the file. Skips @comment, @string, @preamble."""
    entries = []
    pattern = re.compile(r'@(\w+)\s*\{', re.IGNORECASE)
    for m in pattern.finditer(bib_text):
        entry_type = m.group(1).lower()
        if entry_type in ('comment', 'string', 'preamble'):
            continue
        brace_start = m.end() - 1
        brace_end = find_matching_brace(bib_text, brace_start)
        if brace_end == -1:
            continue  # skip malformed entry
        body = bib_text[brace_start + 1:brace_end]
        comma_idx = body.find(',')
        if comma_idx == -1:
            continue  # no fields, skip
        cite_key = body[:comma_idx].strip()
        fields_text = body[comma_idx + 1:]
        entries.append((cite_key, entry_type, fields_text))
    return entries


def extract_field(fields_text, field_name):
    """Extract the raw value of `field_name` from a bib entry's field text.
    Handles {...} and "..." delimited values, including nested braces."""
    pattern = re.compile(r'\b' + re.escape(field_name) + r'\s*=\s*', re.IGNORECASE)
    m = pattern.search(fields_text)
    if not m:
        return None
    idx = m.end()
    while idx < len(fields_text) and fields_text[idx].isspace():
        idx += 1
    if idx >= len(fields_text):
        return None

    if fields_text[idx] == '{':
        end = find_matching_brace(fields_text, idx)
        if end == -1:
            return None
        value = fields_text[idx + 1:end]
    elif fields_text[idx] == '"':
        end = idx + 1
        while end < len(fields_text):
            if fields_text[end] == '"' and fields_text[end - 1] != '\\':
                break
            end += 1
        if end >= len(fields_text):
            return None
        value = fields_text[idx + 1:end]
    else:
        end = idx
        while end < len(fields_text) and fields_text[end] not in ',\n':
            end += 1
        value = fields_text[idx:end]

    return value.strip()


def normalize_title(title):
    """Normalize a title for robust comparison: strip protective braces,
    collapse whitespace, drop trailing punctuation, lowercase."""
    if not title:
        return None
    t = title.replace('{', '').replace('}', '')
    t = re.sub(r'\s+', ' ', t).strip()
    t = t.rstrip('.').strip()
    return t.lower()


def find_duplicate_titles(bib_path):
    with open(bib_path, 'r', encoding='utf-8', errors='replace') as f:
        bib_text = f.read()

    entries = extract_entries(bib_text)

    title_map = defaultdict(list)  # normalized_title -> [(cite_key, orig_title, type), ...]
    for cite_key, entry_type, fields_text in entries:
        raw_title = extract_field(fields_text, 'title')
        norm_title = normalize_title(raw_title)
        if not norm_title:
            continue
        title_map[norm_title].append((cite_key, raw_title.strip(), entry_type))

    duplicates = {t: v for t, v in title_map.items() if len(v) > 1}
    return duplicates, len(entries)


def report(duplicates, total_entries, bib_path, out=sys.stdout):
    print(f"Scanned {total_entries} entries in '{bib_path}'.\n", file=out)

    if not duplicates:
        print("No duplicate titles found.", file=out)
        return

    dup_entry_count = sum(len(v) for v in duplicates.values())
    print(f"Found {len(duplicates)} duplicate title group(s) "
          f"covering {dup_entry_count} entries:\n", file=out)

    for i, (norm_title, entries) in enumerate(sorted(duplicates.items()), 1):
        print(f"{i}. Title: \"{entries[0][1]}\"", file=out)
        print(f"   Duplicate count: {len(entries)}", file=out)
        for cite_key, orig_title, entry_type in entries:
            print(f"     - {cite_key}  (@{entry_type})", file=out)
        print(file=out)


def main():
    parser = argparse.ArgumentParser(description="Find duplicate titles in a .bib file.")
    parser.add_argument("bib_file", help="Path to the .bib file to scan")
    parser.add_argument("-o", "--output", help="Optional path to write the report to a text file")
    args = parser.parse_args()

    duplicates, total_entries = find_duplicate_titles(args.bib_file)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            report(duplicates, total_entries, args.bib_file, out=f)
        print(f"Report written to {args.output}")
    else:
        report(duplicates, total_entries, args.bib_file)


if __name__ == '__main__':
    main()
