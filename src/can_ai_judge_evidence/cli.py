"""Offline authoring/export, live smoke/pilot, and gated evaluation CLI."""
import argparse
from pathlib import Path

from .authoring import audit_suite
from .cases import case_pairs
from .freeze import create_freeze, review_template, verify_freeze
from .harness import ModelSettings, run_jobs, write_json
from .prompts import ARMS, messages, validate_prompt_arms
from .response_schema import response_schema
from .transport import ENDPOINT, OpenAIResponsesTransport


def export_cases(root: Path, out: Path) -> dict:
    report = audit_suite()
    words = validate_prompt_arms()
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / 'authoring-audit.json', report)
    write_json(out / 'human-review-template.json', review_template(root))
    for case in case_pairs():
        for variant in ('blind', 'adequate'):
            config = case.config(variant)
            write_json(out / f'{case.case_id}-{variant}-schema.json', response_schema(config))
            for arm in ARMS:
                # These files are actual request inputs, not dumps of CasePair.
                write_json(out / f'{case.case_id}-{variant}-{arm}-messages.json',
                           messages(case, variant, arm))
                write_json(out / f'{case.case_id}-{variant}-{arm}-open-messages.json',
                           messages(case, variant, arm, 'open'))
    return {'pairs': len(report['pairs']), 'variants': 10, 'arm_words': words,
            'human_review_complete': False, 'out': str(out)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog='caje')
    parser.add_argument('--root', type=Path, default=Path.cwd(), help='source project root for provenance')
    sub = parser.add_subparsers(dest='command', required=True)
    validate = sub.add_parser('validate', help='gate cases; optionally export review materials')
    validate.add_argument('--out', type=Path)
    for name in ('smoke', 'pilot', 'evaluation', 'freeze'):
        command = sub.add_parser(name)
        command.add_argument('--model', required=True, help='explicit provider model ID; dated snapshot to freeze')
        command.add_argument('--reasoning-effort', default='medium')
        command.add_argument('--endpoint', default=ENDPOINT, help='https Responses API URL')
        command.add_argument('--response-model', help='returned model ID to pin, if it differs from --model')
        command.add_argument('--allow-undated-model', action='store_true',
                             help='recorded opt-in: freeze an undated gateway model ID')
        command.add_argument('--brief', choices=('scaffolded', 'open'), default='scaffolded',
                             help='open: changing group not named in public facts')
        command.add_argument('--max-output-tokens', type=int, default=16000)
        command.add_argument('--timeout-seconds', type=int, default=120)
        command.add_argument('--max-attempts', type=int, default=3)
        command.add_argument('--out', required=True, type=Path)
        if name == 'freeze':
            command.add_argument('--smoke', required=True, type=Path)
            command.add_argument('--pilot', required=True, type=Path)
            command.add_argument('--review', required=True, type=Path)
        else:
            command.add_argument('--dry-run', action='store_true', help='no model calls; never pilot evidence')
            command.add_argument('--repeats', type=int, default=1)
            command.add_argument('--seed', type=int, default=1729)
            if name == 'evaluation':
                command.add_argument('--freeze', type=Path)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == 'validate':
            report = (export_cases(root, args.out) if args.out else
                      {'pairs': len(audit_suite()['pairs']), 'arm_words': validate_prompt_arms()})
        else:
            settings = ModelSettings(args.model, args.reasoning_effort, args.max_output_tokens,
                                     args.timeout_seconds, args.max_attempts, args.endpoint,
                                     args.response_model, args.allow_undated_model, args.brief)
            if args.command == 'freeze':
                report = create_freeze(root=root, out=args.out, smoke=args.smoke,
                                       pilot=args.pilot, review=args.review, settings=settings)
            else:
                frozen = None
                if args.command == 'evaluation' and not args.dry_run:
                    if args.freeze is None:
                        raise ValueError('live evaluation requires --freeze')
                    frozen = verify_freeze(root, args.freeze, settings)
                transport = None if args.dry_run else OpenAIResponsesTransport(
                    timeout_seconds=settings.timeout_seconds, endpoint=settings.endpoint)
                report = run_jobs(root=root, out=args.out, settings=settings, transport=transport,
                                  mode=args.command, repeats=args.repeats, seed=args.seed,
                                  dry_run=args.dry_run, freeze_record=frozen)
        import json
        print(json.dumps(report, indent=2, allow_nan=False))
        if report.get('aborted') or report.get('format_failures', 0):
            return 1
        if report.get('dry_run') is False and report.get('pipeline_pass') is False:
            return 1
        return 0
    except (ValueError, OSError) as error:
        parser.exit(2, f'caje: {error}\n')


if __name__ == '__main__':
    raise SystemExit(main())
