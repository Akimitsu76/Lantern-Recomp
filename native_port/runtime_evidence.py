"""Read retained runtime logs without equating presentation with playability."""
from pathlib import Path
import re


def read_runtime_logs(attempt: Path) -> tuple[str, list[str]]:
    numbered = []
    for path in attempt.glob('runtime.*.log'):
        match = re.fullmatch(r'runtime\.(\d+)\.log', path.name)
        if match:
            numbered.append((int(match.group(1)), path))
    # spdlog's .1 is the newest rotated file; current log comes last.
    paths = [p for _, p in sorted(numbered, reverse=True)]
    current = attempt / 'runtime.log'
    if current.is_file():
        paths.append(current)
    return ''.join(p.read_text(errors='replace', encoding='utf8') for p in paths), [p.name for p in paths]


def summarize_runtime_log(text: str) -> dict:
    missing = re.findall(r'invalid or unregistered function at guest address (0x[0-9A-Fa-f]+)', text)
    return {
        'ready': False,
        'gameplay_verified': False,
        'present_calls_observed': text.count('XELOG_GPU PRESENT'),
        'xex_loaded_observed': 'XEX image loaded successfully' in text,
        'fatal_messages': list(dict.fromkeys(re.findall(
            r'(?:\[FATAL\].*|Unhandled guest access violation[^\n]*|ASTER_FRAME original import unavailable[^\n]*)',
            text)))[:8],
        'unregistered_targets': list(dict.fromkeys(missing)),
        'execution_complete_logged': 'Execution complete' in text,
    }
