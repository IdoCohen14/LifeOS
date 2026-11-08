"""Inspect the exact Git index without printing candidate secret values.

Optional private terms are loaded from an external local JSON file, never from
command-line secret values. This is a publication guard, not a security guarantee.
"""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


def git(*args, data=None):
    return subprocess.run(['git', *args], input=data, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, check=True).stdout


def inspect_index(private_terms=()):
    entries = []
    for item in git('ls-files', '--stage', '-z').split(b'\0'):
        if not item:
            continue
        metadata, raw_name = item.split(b'\t', 1)
        mode, oid, stage = metadata.decode('ascii').split()
        if stage != '0':
            raise ValueError('Resolve index conflicts before publication')
        entries.append((raw_name.decode('utf-8'), mode, oid))
    if not entries:
        raise ValueError('Stage an explicit publication snapshot first')
    raw = git('cat-file', '--batch', data=''.join(oid+'\n' for _, _, oid in entries).encode())
    offset = 0
    findings, manifest = [], {}
    patterns = {
        'private-key': r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
        'credential-format': r'(?:GOCSPX-[A-Za-z0-9_-]{12,}|AIza[A-Za-z0-9_-]{30,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|ya29\.[A-Za-z0-9._-]{20,})',
        'private-tailnet-host': r'[\w.-]+\.tail[\w-]+\.ts\.net',
    }
    for name, mode, oid in entries:
        boundary = raw.index(b'\n', offset)
        header = raw[offset:boundary].decode('ascii').split()
        if header[0] != oid or header[1] != 'blob':
            raise ValueError('Unexpected Git object')
        size = int(header[2]); content = raw[boundary+1:boundary+1+size]
        offset = boundary+size+2
        manifest[name] = hashlib.sha256(content).hexdigest()
        parts = Path(name).parts
        if mode not in {'100644', '100755'}:
            findings.append({'file': name, 'category': 'unsupported-file-mode'})
        if any(p in {'.runtime','.venv','node_modules','.git','browser-profiles','backups','exports'} or p.startswith('.next') for p in parts):
            findings.append({'file': name, 'category': 'private-or-generated-directory'})
        base = Path(name).name.lower()
        if (base.startswith('.env') and base != '.env.example'
            or base in {'auth.json','account-mode.json','provider.key','runtime.env','edge.env'}
            or re.search(r'(?:client_secret|credentials|tokens?).*\.json$', base)
            or re.search(r'\.(?:sqlite3?|db)(?:-.*)?$|\.(?:log|har|dump|bak|partial|pem|p12|pfx|zip|7z|xlsx|ics)$', base)):
            findings.append({'file': name, 'category': 'forbidden-data-file'})
        if name.startswith('docs/') and not name.startswith('docs/public/'):
            findings.append({'file': name, 'category': 'unreviewed-operational-document'})
        try:
            text = content.decode('utf-8-sig')
        except UnicodeDecodeError:
            if not (name.startswith('apps/web/public/') and Path(name).suffix in {'.png','.ttf'}):
                findings.append({'file': name, 'category': 'unreviewed-binary'})
            continue
        for number, line in enumerate(text.splitlines(), 1):
            for category, pattern in patterns.items():
                if re.search(pattern, line):
                    findings.append({'file': name, 'line': number, 'category': category})
            if any(term and term.casefold() in line.casefold() for term in private_terms):
                findings.append({'file': name, 'line': number, 'category': 'private-term'})
    return {'files': len(entries), 'tree': git('write-tree').decode().strip(),
            'findings': findings, 'sha256': manifest}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private-terms-file', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    terms = json.loads(args.private_terms_file.read_text(encoding='utf-8-sig'))['terms'] if args.private_terms_file else []
    result = inspect_index(terms)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'sha256'}, indent=2))
    raise SystemExit(bool(result['findings']))


if __name__ == '__main__':
    main()
