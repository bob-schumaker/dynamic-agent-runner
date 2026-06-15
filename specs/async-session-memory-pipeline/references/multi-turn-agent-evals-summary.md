# Multi-Turn Agent Evaluation Summary

## Purpose

Capture the most relevant evaluation implications for future async-session and
multi-turn memory work.

## Source Notes Summarized

- `Demystifying evals for AI agents  Anthropic.md`
- `Reinforcing Multi-Turn Reasoning in LLM Agents via Turn-Level Reward Design.md`

## Key Findings

### 1. Multi-turn systems should be evaluated from transcript and outcome views

The Anthropic eval guidance distinguishes:

- transcript / trace / trajectory
- final environment outcome

This is a useful framing for future OA8 validation because session metadata
should make per-turn traces and multi-run outcomes easier to correlate.

### 2. Multi-turn systems benefit from turn-level reasoning about success

The turn-level reward note reinforces that a long-horizon agent is not well
understood by final outcome alone. Turn boundaries matter.

### 3. Session metadata should support later evals even before behavior exists

Even if OA8 remains declarative at first, good field names and validation rules
can make later evaluation cleaner by preserving:

- session identity
- continuity mode
- retained-history intent

## OA8 Implications

OA8 does not need to implement evals. It only needs to preserve enough clean
session metadata that later transcript correlation and regression evaluation can
be layered on top of it.
