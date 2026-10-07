"""Data-only intake for externally generated CAD proposals; never executes them."""
from __future__ import annotations

import json
from pathlib import Path
import jsonschema
from .geometry.base import GeometryUnsupported
from .geometry.contract import validate_component
from .identity import identity_map
from .util import sha256_file, write_json


def stage_proposal(project: Path, source: Path, schema: dict, engine: str) -> dict:
    if engine not in ('text-to-cad', 'cadgen', 'manual'):
        raise ValueError('proposal engine must be text-to-cad, cadgen or manual')
    if source.suffix.lower() != '.json':
        raise ValueError('only data-only canonical JSON proposals are accepted; scripts and STEP are not authoritative inputs')
    data = json.loads(source.read_text(encoding='utf-8'))
    if not isinstance(data, list) or not data:
        raise ValueError('proposal must be a nonempty canonical component array')
    for component in data:
        jsonschema.validate(component, schema)
    labels = identity_map(data)
    issues = []
    for component in data:
        try:
            validate_component(component)
        except GeometryUnsupported as exc:
            issues.append({'component_id': component['id'], 'severity': 'BLOCK_PRODUCTION', 'message': str(exc)})
    digest = sha256_file(source)
    destination = project / 'work' / 'proposals' / digest
    destination.mkdir(parents=True, exist_ok=True)
    # Preserve the exact candidate bytes and Unicode labels. No active model is changed.
    candidate = destination / 'components.json'
    candidate.write_bytes(source.read_bytes())
    report = {'status': 'CANDIDATE_BLOCKED' if issues else 'CANDIDATE_REVIEW', 'engine': engine,
              'input_sha256': digest, 'candidate': str(candidate), 'issues': issues,
              'label_map': labels, 'active_model_changed': False, 'scripts_executed': False,
              'next_step': 'Check source dimensions/materials, explicitly components-import the reviewed JSON, then obtain current scope confirmation.'}
    write_json(destination / 'proposal_report.json', report)
    return report
