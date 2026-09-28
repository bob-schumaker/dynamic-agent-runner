#!/usr/bin/env python3
"""Question-blind Von turn scoring callback for the gated DMS-13 harness."""

from __future__ import annotations

import hashlib
import math
import re
import ast
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

MAX_INPUT_TOKENS = 8192
OFFICIAL_SCORER_SHA256 = "ecce9c4c79dc89d99534ac17b383a5cbb5b9f0c69ee98adaf0684742e3d95251"
_DIGITS = re.compile(r"\d+")


class ManualRunError(RuntimeError):
    """Raised when the pinned compactor returns unusable scores."""


def verify_run_approval(approval: Mapping[str, Any], *, expected: Mapping[str, Any]) -> None:
    if approval.get("approved") is not True or any(
        approval.get(key) != value for key, value in expected.items()
    ):
        raise ManualRunError("DMS-13 run approval is absent or does not match the pinned run")


def load_official_prompt_builder(scorer_source: Path, *, expected_sha256: str):
    """Load only the official prompt function from its hash-pinned source file."""

    try:
        source = scorer_source.read_bytes()
    except OSError as exc:
        raise ManualRunError("official scorer source is unavailable") from exc
    if hashlib.sha256(source).hexdigest() != expected_sha256:
        raise ManualRunError("official scorer source digest differs")
    try:
        module = ast.parse(source, filename=str(scorer_source))
        prompt_function = next(
            node
            for node in module.body
            if isinstance(node, ast.FunctionDef) and node.name == "get_anscheck_prompt"
        )
        namespace: dict[str, Any] = {}
        exec(compile(ast.Module(body=[prompt_function], type_ignores=[]), str(scorer_source), "exec"), namespace)
        return namespace["get_anscheck_prompt"]
    except (StopIteration, SyntaxError, TypeError) as exc:
        raise ManualRunError("official scorer prompt function is invalid") from exc


def get_official_judge_prompt(
    prompt_builder: Any,
    question_type: str,
    question: str,
    gold_answer: Any,
    hypothesis: str,
    is_abstention: bool,
) -> str:
    """Build the exact pinned LongMemEval scorer prompt for one answer."""

    prompt = prompt_builder(
        question_type,
        question,
        gold_answer,
        hypothesis,
        abstention=is_abstention,
    )
    if not isinstance(prompt, str) or not prompt:
        raise ManualRunError("official scorer prompt is invalid")
    return prompt


class VonTurnScorer:
    """Score one complete history turn with Von's keep/drop decision head."""

    def __init__(
        self,
        *,
        backend: Any,
        choice_factory: Any,
        tokenizer: Any,
        digit_split: bool = False,
    ) -> None:
        self._backend = backend
        self._choice_factory = choice_factory
        self._tokenizer = tokenizer
        self._digit_split = digit_split

    def __call__(self, turn: Sequence[Mapping[str, Any]]) -> float:
        if not turn or any(
            not isinstance(message.get("id"), str)
            or message.get("role") not in {"user", "assistant"}
            or not isinstance(message.get("content"), str)
            for message in turn
        ):
            raise ManualRunError("conversation turn is invalid")
        state = "\n".join(
            f"[{message.get('session_date', '')}] session "
            f"{message.get('session_id', '')} {message['role']}: {message['content']}"
            for message in turn
        )
        token_text = (
            _DIGITS.sub(lambda match: " ".join(match.group()), state)
            if self._digit_split
            else state
        )
        try:
            token_count = len(self._tokenizer.encode(token_text, add_special_tokens=False))
        except Exception as exc:  # noqa: BLE001 - tokenizer details may contain history text.
            raise ManualRunError("Von input tokenization failed") from exc
        if token_count > MAX_INPUT_TOKENS:
            raise ManualRunError("Von turn exceeds the pinned input limit")

        turn_key = hashlib.sha256(
            "\0".join(str(message["id"]) for message in turn).encode("utf-8")
        ).hexdigest()[:16]
        choice = self._choice_factory(
            instructions="Should this conversation turn be retained in active context to help answer future requests?",
            criteria={
                "keep": "Retain this turn in active context.",
                "drop": "The active context can omit this turn.",
            },
        )
        try:
            answer = self._backend.evaluate_choice(turn_key, state, choice)
        except Exception as exc:  # noqa: BLE001 - model errors may contain history text.
            raise ManualRunError("Von turn scoring failed") from exc
        raw = getattr(answer, "probabilities", None)
        if not isinstance(raw, Mapping) or set(raw) != {"keep", "drop"}:
            raise ManualRunError("Von returned an incomplete keep/drop distribution")
        try:
            probabilities = {key: float(value) for key, value in raw.items()}
        except (TypeError, ValueError) as exc:
            raise ManualRunError("Von returned invalid keep/drop probabilities") from exc
        if any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in probabilities.values()):
            raise ManualRunError("Von returned invalid keep/drop probabilities")
        total = sum(probabilities.values())
        if total <= 0.0:
            raise ManualRunError("Von returned an empty keep/drop distribution")
        probabilities = {key: value / total for key, value in probabilities.items()}
        expected_choice = max(probabilities, key=probabilities.get)
        if getattr(answer, "choice", None) != expected_choice:
            raise ManualRunError("Von choice does not match its keep/drop distribution")
        return probabilities["keep"] - probabilities["drop"]
