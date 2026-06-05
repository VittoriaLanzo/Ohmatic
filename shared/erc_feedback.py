"""
shared/erc_feedback.py — single source of truth for the ERC correction-feedback message.

GROUND TRUTH = the loopback TRAINING data. The loopback rows (built by
dataset/scripts/build_erc_loopback_jsonl.py) presented ERC errors to the model in exactly
this format, so prod serving (inference/pipeline.py) and eval (eval/benchmark/prod_eval.py)
MUST format errors identically — otherwise the model is fed out-of-distribution feedback at
correction time and the 2nd-shot capability underperforms what it actually learned.

All three (data builder, serving pipeline, eval) import this one function so they can never
drift — same discipline as shared/prompt_builder.build_system_prompt().
"""
from __future__ import annotations


def format_erc_errors(diags: list[dict]) -> str:
    """Format ERC diagnostics into the correction request the model was trained on.

    Byte-identical to the format used to build the loopback training data:

        ERC ERRORS DETECTED:
        - [CODE] message
          Why: ...
          Fix: ...

        Fix ALL errors above and regenerate the complete circuit JSON.

    Only `error`/`warning` severities are surfaced (info is non-blocking). Accepts both the
    canonical (`why`/`repair`) and legacy (`why_it_matters`/`repair_hint`) diagnostic keys.
    """
    lines = []
    for d in diags:
        # Blocking = severity != "info" (the codebase convention, per _passes_erc). MANY
        # ERC rules (esp. the INTERACTION_* family) return complete diagnostics — code,
        # message, why_it_matters, repair_hint — but DO NOT set `severity` (it is None).
        # Filtering on ("error","warning") silently dropped all of those, which is why the
        # original loopback covered only the few severity-setting rules. Treat any fired,
        # non-info finding as blocking so every rule's feedback is surfaced.
        if d.get("severity") != "info":
            code   = d.get("code", "ERC")
            msg    = d.get("message", "")
            why    = d.get("why_it_matters", "") or d.get("why", "")
            repair = d.get("repair_hint", "") or d.get("repair", "")
            line = f"- [{code}] {msg}"
            if why:
                line += f"\n  Why: {why}"
            if repair:
                line += f"\n  Fix: {repair}"
            lines.append(line)

    if not lines:
        return ("ERC ERRORS DETECTED:\n(unspecified error)\n"
                "Fix and regenerate the complete circuit JSON.")

    return ("ERC ERRORS DETECTED:\n" + "\n".join(lines)
            + "\n\nFix ALL errors above and regenerate the complete circuit JSON.")
