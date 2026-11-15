"""Run the human form once per pair, without opening the answer key."""
import csv
import json
from pathlib import Path
import time

from can_ai_judge_evidence.transport import ENDPOINT, OpenAIResponsesTransport, TransportError

HERE = Path(__file__).resolve().parent
MODEL = 'anthropic_claude_opus_5_5'
COLUMNS = ['pair', 'version_x', 'version_y', 'comment']
SCHEMA = {'type': 'object', 'additionalProperties': False,
          'required': ['version_x', 'version_y', 'comment'],
          'properties': {'version_x': {'type': 'string', 'enum': ['yes', 'no', 'unsure']},
                         'version_y': {'type': 'string', 'enum': ['yes', 'no', 'unsure']},
                         'comment': {'type': 'string'}}}


def make_request(paper, form):
    return {'model': MODEL, 'input': [{'role': 'user', 'content': paper + '\n\n' + form}],
            'text': {'format': {'type': 'json_schema', 'name': 'review', 'strict': True, 'schema': SCHEMA}},
            'max_output_tokens': 4000, 'store': False}


def review_pair(path, form, transport, raw_dir, sleep=time.sleep):
    request = make_request(path.read_text(), form)
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f'{path.stem}.request.json').write_text(json.dumps(request, indent=2))
    for attempt in range(4):
        try:
            reply = transport(request)
            break
        except TransportError as error:
            record = {'error': str(error), 'retryable': error.retryable,
                      'body': error.reply.body.decode() if error.reply else None}
            (raw_dir / f'{path.stem}.error-{attempt}.json').write_text(json.dumps(record, indent=2))
            if not error.retryable or attempt == 3:
                raise
            sleep(2 ** attempt)
    envelope = json.loads(reply.body)
    (raw_dir / f'{path.stem}.response.json').write_text(json.dumps(envelope, indent=2))
    if envelope.get('status') not in (None, 'completed'):
        raise ValueError(f'Incomplete response: {envelope.get("status")}')
    text = ''.join(c['text'] for o in envelope['output'] if o['type'] == 'message'
                   for c in o['content'] if c.get('type') == 'output_text')
    answer = json.loads(text)
    if set(answer) != set(SCHEMA['required']) or any(answer[k] not in ('yes', 'no', 'unsure')
            for k in ('version_x', 'version_y')) or not isinstance(answer['comment'], str):
        raise ValueError('Invalid review answer')
    print(f'{path.stem}: X={answer["version_x"]}, Y={answer["version_y"]}; model={envelope.get("model")}', flush=True)
    return {'pair': path.stem, **answer}


def run(transport, root=HERE):
    form = (root / 'FORM.md').read_text()
    with (root / 'responses' / 'opus.csv').open('w', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=COLUMNS)
        writer.writeheader()
        for path in sorted((root / 'papers').glob('*.md')):
            writer.writerow(review_pair(path, form, transport, root / 'responses' / 'opus_raw'))
            output.flush()


if __name__ == '__main__':
    run(OpenAIResponsesTransport(endpoint=ENDPOINT, timeout_seconds=240))
