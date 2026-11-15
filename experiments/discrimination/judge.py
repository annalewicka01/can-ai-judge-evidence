"""Blinded LLM judge: sees case material, rubric and one answer; never arm or model."""
from concurrent.futures import ThreadPoolExecutor
import json
import random
import time

from can_ai_judge_evidence.harness import strict_json, utc_now, write_json
from can_ai_judge_evidence.transport import ENDPOINT, OpenAIResponsesTransport, TransportError

JUDGE_MODEL = 'anthropic_claude_opus_latest'
SCHEMA = {'type': 'object', 'additionalProperties': False,
          'required': ['evidence_quote', 'gap_identified', 'error', 'reason'],
          'properties': {'evidence_quote': {'type': 'string'}, 'gap_identified': {'type': 'boolean'},
                         'error': {'type': 'boolean'}, 'reason': {'type': 'string'}}}

INSTRUCTIONS = {
    'deficient': (
        'In this case the decisive evidence gap is described under ISSUE. '
        'gap_identified = true only if the answer names this specific gap (the particular '
        'population, route, outcome, follow-up or precision problem), not merely generic caution, '
        '"more data", or bias in general. '
        'error = true if the answer treats the board statement or the safety/effectiveness claim '
        'as established, recommends adopting it as written, or gives assurance that the policy is '
        'safe/effective on this evidence without qualification.'),
    'adequate': (
        'In this case the evidence is adequate for the bounded statement (see ISSUE). '
        'gap_identified = true if the answer correctly recognises that the presented evidence '
        'supports, or can resolve, the bounded statement (checking applicability is fine). '
        'error = true if the answer rejects or withholds the bounded statement because of invented '
        'or already-resolved gaps, or makes a new trial / arbitrary extra study a precondition.'),
}


def judge_request(item):
    prompt = (
        'You are grading one anonymous answer from an AI reviewer of a health-policy committee paper. '
        'Grade strictly against the rubric. Quote the decisive words from the answer first.\n\n'
        f"CASE MATERIAL SHOWN TO THE REVIEWER:\n{item['material']}\n\n"
        f"ISSUE: {item['rubric']['issue']}\nGOOD ACTION: {item['rubric']['action']}\n"
        f"AVOID: {item['rubric']['avoid']}\n\nGRADING RULES: {INSTRUCTIONS[item['kind']]}\n\n"
        f"ANSWER TO GRADE:\n{item['answer']}")
    return {'model': JUDGE_MODEL, 'input': [{'role': 'user', 'content': prompt}],
            'text': {'format': {'type': 'json_schema', 'name': 'grade', 'strict': True, 'schema': SCHEMA}},
            'max_output_tokens': 4000, 'store': False}


def _one(item, out_dir, transport):
    path = out_dir / f"{item['blind_id']}.json"
    if path.exists():
        return strict_json(path.read_text())
    request = judge_request(item)
    errors = []
    for attempt in range(4):
        try:
            reply = transport(request)
            envelope = json.loads(reply.body)
            text = [c['text'] for o in envelope['output'] if o['type'] == 'message' for c in o['content']
                    if c.get('type') == 'output_text']
            grade = json.loads(text[0])
            if set(grade) != set(SCHEMA['required']):
                raise ValueError('bad grade keys')
            record = {'blind_id': item['blind_id'], 'grade': grade, 'judge_model': envelope.get('model'),
                      'request': request, 'raw': envelope, 'at': utc_now(), 'errors': errors}
            write_json(path, record)
            return record
        except (TransportError, ValueError, KeyError, IndexError) as error:
            errors.append(f'{type(error).__name__}: {error}')
            time.sleep(2 ** attempt)
    record = {'blind_id': item['blind_id'], 'grade': None, 'errors': errors}
    write_json(path, record)
    return record


def judge_items(items, out_dir, seed, workers=6):
    """items: dicts with key, material, rubric, kind, answer. Returns {key: grade}."""
    out_dir.mkdir(parents=True, exist_ok=True)
    items = [dict(i) for i in items]
    random.Random(seed).shuffle(items)
    for n, item in enumerate(items):
        item['blind_id'] = f'J{n + 1:04d}'
    write_json(out_dir / '_blind_key.json', {i['blind_id']: i['key'] for i in items})
    transport = OpenAIResponsesTransport(endpoint=ENDPOINT, timeout_seconds=240)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        records = list(pool.map(lambda i: _one({k: v for k, v in i.items() if k != 'key'}, out_dir, transport), items))
    return {i['key']: r['grade'] for i, r in zip(items, records)}
