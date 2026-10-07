#!/usr/bin/env python3
from pathlib import Path
import re, sys

def main():
    root=Path(sys.argv[1] if len(sys.argv)>1 else '.').resolve(); errors=[]
    skill=root/'SKILL.md'
    if not skill.exists(): errors.append('SKILL.md missing')
    else:
        txt=skill.read_text(encoding='utf-8')
        if not txt.startswith('---\n'): errors.append('YAML front matter missing')
        m=re.search(r'^name:\s*([^\n]+)$',txt,re.M)
        if not m: errors.append('name missing')
        elif m.group(1).strip()!=root.name: errors.append(f'name {m.group(1).strip()} != parent dir {root.name}')
        if not re.search(r'^description:\s*.+$',txt,re.M): errors.append('description missing')
    skills=list(root.rglob('SKILL.md'))
    if len(skills)!=1: errors.append(f'exactly one SKILL.md required, found {len(skills)}')
    forbidden=[]
    for p in root.rglob('*'):
        if '__pycache__' in p.parts or p.name in {'.pytest_cache','.DS_Store'} or p.suffix in {'.pyc','.pyo'}: forbidden.append(str(p))
    if forbidden: errors.append('runtime artifacts present: '+', '.join(forbidden[:5]))
    refs=['references/architecture.md','references/data-contract.md','references/adapters.md','references/engineering.md','references/operations.md','references/sources.md','config/project.example.yaml','schemas/component.schema.json']
    for r in refs:
        if not (root/r).exists(): errors.append(f'missing referenced file: {r}')
    if errors:
        print('\n'.join('ERROR: '+e for e in errors)); return 1
    print('OK: skill package structure is valid'); return 0
if __name__=='__main__': raise SystemExit(main())
