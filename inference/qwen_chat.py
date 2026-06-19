"""Pure-Python Qwen3 ChatML renderer - the only thing the GGUF edge path needed
transformers for.

It reproduces, byte-for-byte, what
`transformers.AutoTokenizer.apply_chat_template(messages, tokenize=False,
add_generation_prompt=True, enable_thinking=False)` produces for the
Ohmatic-Qwen3-8B chat template, for every message shape the pipeline emits
(a leading system message + user/assistant turns; no tools). Proven byte-identical
against the real tokenizer over a corpus including adversarial cases - see
tests/test_qwen_chat.py.

Why this exists: importing `transformers` for that one call transitively loaded
torch + tokenizers (~366 MB resident) into the long-lived generation process and
was the only network-capable dependency in the loop. Rendering the prompt here
keeps generation on `llama_cpp` + `numpy` + stdlib - smaller, and fully offline
once installed. The returned string is identical to the old path's, so llama.cpp
tokenizes it identically and benchmark output is unchanged.

'tool' role and assistant tool_calls are intentionally unsupported: the pipeline
never emits them, and the template's tool branches would add surface with no use.
"""
from __future__ import annotations

_IM_START = "<|im_start|>"
_IM_END = "<|im_end|>"


def render_chat(messages, add_generation_prompt: bool = True,
                enable_thinking: bool = False) -> str:
    """Render Qwen3 ChatML for `messages` (list of {role, content})."""
    parts: list[str] = []
    # Leading system message (the template's no-tools branch).
    if messages and messages[0].get("role") == "system":
        parts.append(_IM_START + "system\n" + (messages[0].get("content") or "") + _IM_END + "\n")
    # last_query_index = index of the last non-tool-response user message (the
    # template walks messages in reverse to find it).
    last_query_index = len(messages) - 1
    multi = True
    for index in range(len(messages) - 1, -1, -1):
        cc = messages[index].get("content") or ""
        is_tool_resp = cc[:15] == "<tool_response>" and cc[-16:] == "</tool_response>"
        if multi and messages[index].get("role") == "user" and not is_tool_resp:
            multi = False
            last_query_index = index
    n = len(messages)
    for i, m in enumerate(messages):
        role = m.get("role")
        content = m.get("content") or ""
        if role == "user" or (role == "system" and i != 0):
            parts.append(_IM_START + role + "\n" + content + _IM_END + "\n")
        elif role == "assistant":
            reasoning = ""
            if "</think>" in content:
                orig = content
                content = orig.split("</think>")[-1].lstrip("\n")
                reasoning = orig.split("</think>")[0].rstrip("\n").split("<think>")[-1].lstrip("\n")
            if i > last_query_index and (i == n - 1 or reasoning):
                parts.append(_IM_START + "assistant\n<think>\n" + reasoning.strip("\n")
                             + "\n</think>\n\n" + content.lstrip("\n"))
            else:
                parts.append(_IM_START + "assistant\n" + content)
            parts.append(_IM_END + "\n")
    if add_generation_prompt:
        parts.append(_IM_START + "assistant\n")
        if enable_thinking is False:
            parts.append("<think>\n\n</think>\n\n")
    return "".join(parts)
