"""Bundled, immutable RGB system templates. 1:1 transcription of user-provided presets."""
from __future__ import annotations
import json
from pathlib import Path
from .core import Presets, MetaCubeError, number

CATALOG = Path(__file__).with_name('system_templates.json')


def system_templates() -> list[dict]:
    """Return system templates separately from the 5 writable user preset slots."""
    try:
        content = json.loads(CATALOG.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise MetaCubeError(f'Cannot load bundled system templates: {exc}') from exc
    if not isinstance(content,dict) or set(content) != {'version','slots'} or content['version'] != 1:
        raise MetaCubeError('Invalid bundled system templates format')
    slots = Presets.validate_slots(content['slots'])
    return [{'id': index, 'name': entry['name'], 'lighting': entry['lighting']}
            for index,entry in enumerate(slots,1) if entry is not None]


def system_template(template_id: int) -> dict:
    template_id = number(template_id,1,5,'system template id')
    for entry in system_templates():
        if entry['id'] == template_id:
            return entry['lighting']
    raise MetaCubeError(f'System template {template_id} does not exist')
