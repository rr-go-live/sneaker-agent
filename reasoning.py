"""
reasoning.py
------------
Helper for parsing LLM responses that contain both a plain-English
explanation of the model's thinking and a machine-readable answer.

Several agents ask the LLM to respond in this two-part format:

    REASONING: <2-3 sentences explaining the decision>
    ANSWER: <the value the agent code needs to act on>

Returning both in a single call (rather than making a second "explain
yourself" call) keeps API costs flat while still surfacing the model's
logic to the user in the logging panel.
"""


def split_reasoning_answer(text):
    """
    split_reasoning_answer
    ----------------------
    Splits a two-part LLM response into its reasoning and answer halves.

    The parser is deliberately forgiving: the labels may appear in any
    case, and if the model omits one of the labels the function degrades
    gracefully instead of raising.

    Args:
        text (str): the raw LLM response content.

    Returns:
        tuple[str, str]: (reasoning, answer).
          - If both labels are present, each half is returned trimmed.
          - If only "ANSWER:" is present, reasoning is "" and the rest is
            the answer.
          - If neither label is present, reasoning is "" and the whole
            string is returned as the answer (backwards-compatible).
    """
    if text is None:
        return "", ""

    cleaned = text.strip()
    lowered = cleaned.lower()

    answer_marker = "answer:"
    reasoning_marker = "reasoning:"

    answer_index = lowered.find(answer_marker)

    # No explicit ANSWER label — treat the whole response as the answer.
    if answer_index == -1:
        return "", cleaned

    answer = cleaned[answer_index + len(answer_marker):].strip()

    # Pull out the reasoning that sits before the ANSWER label, dropping
    # the optional "REASONING:" prefix if the model included it.
    before_answer = cleaned[:answer_index].strip()
    reasoning_index = before_answer.lower().find(reasoning_marker)
    if reasoning_index != -1:
        reasoning = before_answer[reasoning_index + len(reasoning_marker):].strip()
    else:
        reasoning = before_answer

    return reasoning, answer
