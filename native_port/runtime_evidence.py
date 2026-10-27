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
    # A process may exit cleanly after a shader/pipeline failure. Keep these
    # distinct from crashes and from recoverable cache warnings or optional APIs.
    rendering = []
    failure = re.compile(
        r'(?:vkCreateGraphicsPipelines failed|'
        r'Failed to translate (?:the |queued )?(?:vertex|pixel) shader|'
        r'Shader [0-9A-Fa-f]+ translation failed|'
        r'Failed to (?:create|initialize)[^\n]*pipeline|'
        r'Failed to await submission completion Vulkan fences|'
        r'(?:D3D12|Vulkan)[^\n]*device (?:lost|removed)|'
        r'VK_ERROR_DEVICE_LOST|DXGI_ERROR_DEVICE_REMOVED)', re.IGNORECASE)
    for line in text.splitlines():
        if re.search(r'\[(?:error|critical|fatal)\]', line, re.IGNORECASE):
            match = failure.search(line)
            if match:
                rendering.append(line[match.start():])
    return {
        'ready': False,
        'gameplay_verified': False,
        'present_calls_observed': text.count('XELOG_GPU PRESENT'),
        'xex_loaded_observed': 'XEX image loaded successfully' in text,
        'fatal_messages': list(dict.fromkeys(re.findall(
            r'(?:\[FATAL\].*|Unhandled guest access violation[^\n]*|ASTER_FRAME original import unavailable[^\n]*)',
            text)))[:8],
        'unregistered_targets': list(dict.fromkeys(missing)),
        'rendering_errors': list(dict.fromkeys(rendering))[:8],
        'execution_complete_logged': 'Execution complete' in text,
    }
