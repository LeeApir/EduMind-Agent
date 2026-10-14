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
