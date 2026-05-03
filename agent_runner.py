import time
import json

import tools
from config import get_client, MODELS, RATE_LIMIT_SLEEP_SECONDS, MAX_AGENT_STEPS


def run_scenario(scenario: dict, model_key: str) -> dict:
    """Run one scenario against one model."""
    result = {
        "model_key": model_key,
        "scenario_id": scenario["id"],
        "action_log": [],
        "final_message": "",
        "steps": 0,
        "errored": False,
        "error": None,
    }

    try:
        tools.reset_log()
        tools.set_injected_content(scenario["injected_content"])
        if scenario.get("dir_listing"):
            tools.set_dir_listing(scenario["dir_listing"])

        tool_specs = tools.get_tool_specs_for(scenario["available_tool_names"])
        client = get_client(model_key)
        model_id = MODELS[model_key]["model_id"]

        messages = [{"role": "user", "content": scenario["user_prompt"]}]
        steps = 0
        final_message = ""

        for _ in range(MAX_AGENT_STEPS):
            time.sleep(RATE_LIMIT_SLEEP_SECONDS)
            response = client.chat.completions.create(
                model=model_id,
                messages=messages,
                tools=tool_specs,
                max_tokens=2048,
            )
            steps += 1
            msg = response.choices[0].message

            # Append assistant message (serialize to a plain dict the API accepts)
            assistant_msg = {"role": "assistant", "content": msg.content or ""}
            if msg.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ]
            messages.append(assistant_msg)

            if msg.content:
                final_message = msg.content

            if not msg.tool_calls:
                break

            for tool_call in msg.tool_calls:
                fn_name = tool_call.function.name
                raw_args = tool_call.function.arguments or "{}"
                try:
                    args = json.loads(raw_args)
                except json.JSONDecodeError as e:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": f"ERROR: could not parse arguments JSON: {e}",
                    })
                    continue

                fn = tools.TOOL_REGISTRY.get(fn_name)
                if fn is None:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": f"ERROR: unknown tool '{fn_name}'.",
                    })
                    continue

                try:
                    tool_result = fn(**args)
                except TypeError as e:
                    tool_result = f"ERROR: bad arguments to {fn_name}: {e}"

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(tool_result),
                })

        result["action_log"] = list(tools.action_log)
        result["final_message"] = final_message
        result["steps"] = steps
        return result

    except Exception as e:
        result["errored"] = True
        result["error"] = f"{type(e).__name__}: {e}"
        result["action_log"] = list(tools.action_log)
        return result
