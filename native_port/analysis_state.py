"""Only associate an analysis artifact with the exact source/content hash."""
import hashlib
import json
from pathlib import Path
from .errors import PortError


def verified_analysis(workspace, source_sha):
    p = workspace.path('reports/xenon-analysis.json')
    if not p.is_file() or p.stat().st_size > 2*1024*1024:
        return None
    try:
        report = json.loads(p.read_text(encoding='utf8'))
        if report.get('schema')!=1 or report.get('state')!='decoded-and-validated' or report.get('source_sha256')!=source_sha:
            return None
        artifact = Path(report['normalized_path']).resolve()
        if not artifact.is_relative_to(workspace.root) or not artifact.is_file():
            return None
        if hashlib.sha256(artifact.read_bytes()).hexdigest()!=report['normalized_sha256']:
            return None
        return {'state':report['state'], 'normalized_path':str(artifact),
                'imports':report['imports'], 'native_leaf_probe':report.get('native_leaf_probe'),
                'game_ready':False}
    except (OSError, ValueError, TypeError, KeyError):
        return None
