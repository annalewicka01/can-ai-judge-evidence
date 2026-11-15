"""Three fixed arms; same narrative, contract and schema in each comparison.

Length matching means whitespace-separated words, not provider tokens. Arm
names, variant labels, case IDs, split and hidden diagnostics are never sent.
"""
from .cases import CasePair
from .response_schema import model_contract


SYSTEM_MESSAGE = (
    'You advise a policy committee about a monitoring design. Work only from '
    'the supplied facts, without calculation tools or external information. '
    'Return only one JSON object matching the supplied response schema.')

ARMS = {
    'ordinary': (
        'Assess the proposed monitoring plan and give the committee your recommendation. '
        'Use the supplied case information to decide whether the existing plan meets '
        'the stated standard. If a replacement is required, specify one complete plan. '
        'Explain your recommendation clearly and briefly, and distinguish required changes from '
        'optional suggestions. State uncertainty where appropriate, and follow the '
        'common response contract for your final answer.'),
    'generic_critique': (
        'Critically review the proposed monitoring plan before giving the committee '
        'your recommendation. Examine its assumptions, weaknesses, omissions and '
        'possible alternatives using the supplied case information. Decide whether '
        'the existing plan meets the stated standard. If a replacement is required, '
        'specify one complete plan. Distinguish required changes from optional '
        'suggestions, state uncertainty where appropriate, and follow the common '
        'response contract for your answer.'),
    'targeted': (
        'If this policy were harmful, could the evaluation detect it? Consider whether '
        'acceptable and deteriorating worlds could produce identical observations under '
        'the proposed plan, then assess detection, sample size, cost and timing. '
        'Decide whether the existing plan meets the standard. If needed, '
        'specify one complete replacement. Distinguish required changes from optional '
        'suggestions, state uncertainty where appropriate, and follow the common '
        'response contract.'),
}


def validate_prompt_arms() -> int:
    lengths = {len(text.split()) for text in ARMS.values()}
    if len(lengths) != 1 or set(ARMS) != {'ordinary', 'generic_critique', 'targeted'}:
        raise ValueError('three required prompt arms must have equal word counts')
    return lengths.pop()


def messages(case: CasePair, variant: str, arm: str, brief: str = 'scaffolded') -> list[dict]:
    validate_prompt_arms()
    config = case.config(variant)
    narrative, target = case.brief_inputs(brief)
    contract = model_contract(config, world=case.world, bindings=case.bindings, target=target,
                              brief=brief)
    content = '\n\n'.join((
        'Synthetic policy scenario; all numerical inputs are design assumptions.',
        case.title, narrative, ARMS[arm], contract))
    return [{'role': 'system', 'content': SYSTEM_MESSAGE}, {'role': 'user', 'content': content}]
