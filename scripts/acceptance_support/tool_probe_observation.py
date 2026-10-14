"""Safe field-level tool diagnostics. Never retain content, argument values or secrets."""

from app.services.provider_protocol import strict_json

CHECKS = (
    "model_identity",
    "single_choice",
    "choice_index",
    "tool_finish_reason",
    "assistant_role",
    "no_refusal",
    "single_tool",
    "function_type",
    "function_name",
    "arguments_schema",
)


def tool_shape(raw, *, models):
    flags = dict.fromkeys(CHECKS, False)
    if not isinstance(raw, dict):
        return flags
    model = raw.get("model")
    flags["model_identity"] = isinstance(model, str) and model in models
    choices = raw.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        return flags
    flags["single_choice"] = True
    choice = choices[0]
    flags["choice_index"] = type(choice.get("index")) is int and choice["index"] == 0
    flags["tool_finish_reason"] = choice.get("finish_reason") == "tool_calls"
    message = choice.get("message")
    if not isinstance(message, dict):
        return flags
    flags["assistant_role"] = message.get("role") == "assistant"
    flags["no_refusal"] = not bool(message.get("refusal"))
    calls = message.get("tool_calls")
    if not isinstance(calls, list) or len(calls) != 1 or not isinstance(calls[0], dict):
        return flags
    flags["single_tool"] = True
    call = calls[0]
    flags["function_type"] = call.get("type") == "function"
    function = call.get("function")
    if not isinstance(function, dict):
        return flags
    flags["function_name"] = function.get("name") == "emit_probe"
    arguments = function.get("arguments")
    if isinstance(arguments, str):
        try:
            value = strict_json(arguments)
            flags["arguments_schema"] = (
                isinstance(value, dict) and set(value) == {"ok"} and value["ok"] is True
            )
        except Exception:
            pass
    return flags


def tool_metadata(raw):
    """Only fixed enums/types/counts and the expected boolean, no arbitrary strings."""
    meta = {
        "finish_reason": None,
        "argument_wire_type": None,
        "argument_json_type": None,
        "ok_type": None,
        "ok_boolean": None,
        "argument_keys_exact": None,
    }
    try:
        choice = raw["choices"][0]
        finish = choice.get("finish_reason")
        meta["finish_reason"] = (
            finish
            if finish in {"stop", "tool_calls", "length", "content_filter", "function_call", None}
            else "other"
        )
        arguments = choice["message"]["tool_calls"][0]["function"]["arguments"]
        meta["argument_wire_type"] = type(arguments).__name__
        value = strict_json(arguments) if isinstance(arguments, str) else arguments
        meta["argument_json_type"] = type(value).__name__
        if isinstance(value, dict):
            meta["argument_keys_exact"] = set(value) == {"ok"}
            ok = value.get("ok")
            meta["ok_type"] = type(ok).__name__
            meta["ok_boolean"] = ok if type(ok) is bool else None
    except Exception:
        pass
    return meta
