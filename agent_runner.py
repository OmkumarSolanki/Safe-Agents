import json
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import tools
from config import get_client, MODELS, RATE_LIMIT_SLEEP_SECONDS, MAX_AGENT_STEPS
from report import build_trial_record, save_run_metadata, save_trial_record


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


def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, check=False, timeout=5,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return "unknown"


def _new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:6]}"


def run_full_eval(
    scenarios: list[dict],
    model_keys: list[str],
    *,
    trials_per_scenario: int = 1,
    results_root: Path | str = "results",
    run_id: Optional[str] = None,
    on_trial: Optional[Callable[[dict], None]] = None,
) -> tuple[str, Path]:
    """Run every (scenario × model × trial) combination and persist results.

    Writes one record per trial to `{results_root}/{run_id}/trials.jsonl` and
    a single `run.json` metadata file. Returns (run_id, run_dir).

    `on_trial(trial_record)` is called after each trial — useful for UI progress.
    """
    run_id = run_id or _new_run_id()
    run_dir = Path(results_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    started_at = datetime.now(timezone.utc).isoformat()

    save_run_metadata(run_dir, {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": None,
        "models": [MODELS[k]["model_id"] for k in model_keys],
        "model_keys": list(model_keys),
        "scenarios_count": len(scenarios),
        "trials_per_scenario": trials_per_scenario,
        "git_sha": _git_sha(),
    })

    for scenario in scenarios:
        for model_key in model_keys:
            for _trial_idx in range(trials_per_scenario):
                run_result = run_scenario(scenario, model_key)
                record = build_trial_record(
                    run_id=run_id,
                    model_id=MODELS[model_key]["model_id"],
                    scenario=scenario,
                    action_log=run_result["action_log"],
                    final_message=run_result.get("final_message", ""),
                )
                save_trial_record(run_dir, record)
                if on_trial is not None:
                    on_trial(record)

    finished_at = datetime.now(timezone.utc).isoformat()
    save_run_metadata(run_dir, {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "models": [MODELS[k]["model_id"] for k in model_keys],
        "model_keys": list(model_keys),
        "scenarios_count": len(scenarios),
        "trials_per_scenario": trials_per_scenario,
        "git_sha": _git_sha(),
    })

    return run_id, run_dir
