"""Read bounded metadata from optional SDK patch 0018; never infer GPU RT size."""
import json
from dataclasses import dataclass
import re

PREFIX = 'ASTER_EFFECTS_META '
ATLAS_XXH3 = '20d7f7023b337e4a3b25e2d40cd10280'
MAX_STATES = 32


@dataclass(frozen=True)
class EffectsSource:
    fingerprint: str
    width: int
    height: int
    pitch: int
    extent: int

    def validate(self):
        if (not isinstance(self.fingerprint, str) or
                re.fullmatch(r'[0-9a-f]{32}', self.fingerprint) is None or
                any(type(v) is not int for v in (self.width, self.height, self.pitch, self.extent)) or
                not 64 <= self.width <= 2048 or not 64 <= self.height <= 2048 or
                not 1 <= self.pitch <= 64 or self.pitch * 32 < self.width or
                not 1 <= self.extent <= 4 << 20):
            raise ValueError('Invalid reviewed BC3 base-only source.')


def parse_effects_source_index(text):
    """Read a locally reviewed ASTERFX1 index, without loading any texture bytes."""
    if not isinstance(text, str) or not text or not text.isascii() or len(text.encode('utf8')) > 16 << 10:
        raise ValueError('Effects source index exceeds 16 KiB or is empty.')
    # Match the C++ getline contract: CRLF and one final newline are allowed;
    # blank records, comments and incomplete records are rejected.
    rows = text.split('\n')
    if rows[-1] == '':
        rows.pop()
    rows = [row[:-1] if row.endswith('\r') else row for row in rows]
    if not rows or rows[0] != 'ASTERFX1' or not 2 <= len(rows) <= 9:
        raise ValueError('Expected ASTERFX1 and one to eight reviewed sources.')
    sources, hashes = [], set()
    for row in rows[1:]:
        fields = row.split()
        if (len(fields) != 5 or any(re.fullmatch(r'[0-9]{1,10}', v) is None for v in fields[1:])):
            raise ValueError('Invalid effects source index row.')
        source = EffectsSource(fields[0], *(int(v) for v in fields[1:]))
        source.validate()
        if source.fingerprint in hashes:
            raise ValueError('Duplicate effects source fingerprint.')
        hashes.add(source.fingerprint)
        sources.append(source)
    return tuple(sources)


def format_effects_source_index(sources):
    """Format reviewed sources; callers should atomically replace the local file."""
    text = 'ASTERFX1\n' + ''.join(
        f'{s.fingerprint} {s.width} {s.height} {s.pitch} {s.extent}\n' for s in sources)
    parse_effects_source_index(text)
    return text


def parse_effects_metadata(lines, *, reviewed_sources=None):
    """Return exact-atlas records; reject malformed, unbounded or contradictory logs.

    Pass one process log at a time. A record proves an observed CPU source and
    guest/backend sampling state before draw submission, not rendered pixels.
    """
    if reviewed_sources is not None:
        reviewed_sources = tuple(reviewed_sources)
        # The same bounded contract applies to runtime and analysis allowlists.
        parse_effects_source_index(format_effects_source_index(reviewed_sources))
    records, seen = [], set()
    for line in lines:
        if PREFIX not in line:
            continue
        payload = line.split(PREFIX, 1)[1].strip()
        if len(payload) > 65536:
            raise ValueError('Effects metadata record exceeds 64 KiB.')
        try:
            record = json.loads(payload)
        except (ValueError, TypeError) as exc:
            raise ValueError('Malformed effects metadata JSON.') from exc
        if not isinstance(record, dict) or type(record.get('schema')) is not int or record['schema'] not in (1, 2):
            raise ValueError('Unsupported effects metadata schema.')
        if record['schema'] == 1:
            source_valid = (record.get('source_raw_xxh3_128') == ATLAS_XXH3 and
                            record.get('snapshot_bytes') == 2162688)
            if reviewed_sources is not None:
                source_valid = source_valid and EffectsSource(ATLAS_XXH3, 1440, 1344, 48, 2162688) in reviewed_sources
        else:
            if reviewed_sources is None:
                raise ValueError('Schema2 requires an explicit reviewed source allowlist.')
            geometry = record.get('source_geometry')
            source_valid = False
            if isinstance(geometry, dict):
                values = [geometry.get(k) for k in ('width', 'height', 'pitch', 'extent')]
                if (all(type(v) is int for v in values) and
                        geometry.get('format') == 20 and type(geometry.get('format')) is int and
                        geometry.get('endian') == 1 and type(geometry.get('endian')) is int and
                        geometry.get('tiled') is True and geometry.get('mip_max_level') == 0 and
                        type(geometry.get('mip_max_level')) is int):
                    source = EffectsSource(record.get('source_raw_xxh3_128'), *values)
                    source_valid = (source in reviewed_sources and
                                    record.get('snapshot_bytes') == source.extent)
        if not source_valid or record.get('gpu_written_pages') is not False:
            raise ValueError('Effects metadata does not identify the reviewed CPU atlas.')
        if ('actual_rt_size' not in record or record['actual_rt_size'] is not None or
                'actual_sampled_lod' not in record or record['actual_sampled_lod'] is not None or
                record.get('draw_completion') != 'unknown'):
            raise ValueError('This source diagnostic cannot establish GPU results.')
        state = record.get('state')
        if not isinstance(state, dict) or state.get('backend') not in ('vulkan', 'd3d12'):
            raise ValueError('Missing backend sampling state.')
        for name in ('vs_hash', 'ps_hash', 'base_page', 'host_resource_id'):
            value = state.get(name)
            if type(value) is not int or not 0 <= value < 1 << 64:
                raise ValueError('Invalid shader/source identity.')
        fetch = state.get('fetch')
        if type(fetch) is not int or not 0 <= fetch < 32:
            raise ValueError('Invalid texture fetch index.')
        for name in ('scale_x', 'scale_y'):
            if type(state.get(name)) is not int or not 1 <= state[name] <= 8:
                raise ValueError('Invalid draw resolution scale.')
        samplers = state.get('samplers')
        if not isinstance(samplers, list) or not 1 <= len(samplers) <= 256:
            raise ValueError('Missing or excessive sampler bindings.')
        for sampler in samplers:
            if not isinstance(sampler, dict) or sampler.get('fetch') != fetch or sampler.get('stage') not in (0, 1):
                raise ValueError('Sampler is unrelated to the atlas fetch.')
            for name in ('host_value', 'instruction_mag', 'instruction_min', 'instruction_mip',
                         'instruction_aniso', 'aniso', 'mip_min_level', 'mip_base_map',
                         'clamp_x', 'clamp_y', 'clamp_z', 'border'):
                if type(sampler.get(name)) is not int or not 0 <= sampler[name] < 1 << 32:
                    raise ValueError('Invalid sampler parameter.')
            for name in ('mag_linear', 'min_linear', 'mip_linear'):
                if type(sampler.get(name)) is not int or sampler[name] not in (0, 1):
                    raise ValueError('Invalid sampler filter flag.')
        fetch_raw = state.get('fetch_raw')
        if (not isinstance(fetch_raw, list) or len(fetch_raw) != 6 or
                any(type(v) is not int or not 0 <= v < 1 << 32 for v in fetch_raw)):
            raise ValueError('Invalid raw fetch constant.')
        if 'pixel_float_constant_255_raw' in state:
            constants = state['pixel_float_constant_255_raw']
            if (not isinstance(constants, list) or len(constants) != 4 or
                    any(type(v) is not int or not 0 <= v < 1 << 32 for v in constants)):
                raise ValueError('Invalid raw pixel float4 constant.')
        registers = state.get('guest_registers_raw')
        required = ('RB_COLORCONTROL', 'RB_ALPHA_REF', 'RB_SURFACE_INFO',
                    'RB_BLENDCONTROL0', 'RB_BLENDCONTROL1', 'RB_BLENDCONTROL2', 'RB_BLENDCONTROL3',
                    'PA_CL_VPORT_XSCALE', 'PA_CL_VPORT_YSCALE', 'PA_SC_WINDOW_SCISSOR_TL',
                    'PA_SC_WINDOW_SCISSOR_BR')
        if (not isinstance(registers, dict) or any(name not in registers for name in required) or
                any(type(v) is not int or not 0 <= v < 1 << 32 for v in registers.values())):
            raise ValueError('Missing or invalid guest transparency/viewport registers.')
        cc, surface = registers['RB_COLORCONTROL'], registers['RB_SURFACE_INFO']
        decoded = {'alpha_test_enable': (cc >> 3) & 1, 'alpha_func': cc & 7,
                   'alpha_to_mask_enable': (cc >> 4) & 1,
                   'guest_msaa_samples_enum': (surface >> 16) & 3,
                   'guest_surface_pitch': surface & 0x3fff}
        if any(type(state.get(k)) is not int or state[k] != v for k, v in decoded.items()):
            raise ValueError('Decoded transparency/pitch metadata contradicts raw registers.')
        identity = json.dumps(state, sort_keys=True, separators=(',', ':'))
        if identity in seen:
            continue
        if len(seen) >= MAX_STATES:
            raise ValueError('More than 32 unique states in one process log.')
        seen.add(identity)
        records.append(record)
    return records
