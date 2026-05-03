import sys
from config import get_client, MODELS


def test_basic_chat(model_key):
    print(f"  → Basic chat on {MODELS[model_key]['display_name']}...", end=" ", flush=True)
    client = get_client(model_key)
    try:
        r = client.chat.completions.create(
            model=MODELS[model_key]["model_id"],
            messages=[{"role": "user", "content": "Reply with exactly: OK"}],
            max_tokens=256,
        )
        text = (r.choices[0].message.content or "").strip()
        if text:
            print(f"PASS ({text[:40]!r})")
            return True
        else:
            print("UNEXPECTED RESPONSE: empty content (likely truncated reasoning tokens)")
            return False
    except Exception as e:
        print(f"FAIL: {e}")
        return False


def test_tool_calling(model_key):
    print(f"  → Tool calling on {MODELS[model_key]['display_name']}...", end=" ", flush=True)
    client = get_client(model_key)
    tool_spec = [{
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files in a directory.",
            "parameters": {
                "type": "object",
                "properties": {"directory": {"type": "string"}},
                "required": ["directory"],
            },
        },
    }]
    last_err = None
    for attempt in range(2):
        try:
            r = client.chat.completions.create(
                model=MODELS[model_key]["model_id"],
                messages=[{
                    "role": "user",
                    "content": "Use the list_files tool to list files in the Downloads directory. Call the tool, do not just describe it.",
                }],
                tools=tool_spec,
                tool_choice="auto",
                max_tokens=1024,
            )
            msg = r.choices[0].message
            if msg.tool_calls and any(tc.function.name == "list_files" for tc in msg.tool_calls):
                print("PASS" + (f" (attempt {attempt + 1})" if attempt else ""))
                return True
            last_err = f"no tool_calls. message content: {msg.content!r}"
        except Exception as e:
            last_err = str(e)
    print(f"FAIL: {last_err}")
    return False


if __name__ == "__main__":
    print("=" * 60)
    print("AgentSafe — Setup Verification")
    print("=" * 60)
    results = []
    for key in MODELS:
        print(f"\nTesting {MODELS[key]['display_name']}:")
        results.append(test_basic_chat(key))
        results.append(test_tool_calling(key))
    print("\n" + "=" * 60)
    if all(results):
        print("✓ ALL CHECKS PASSED — proceed to streamlit run app.py")
        sys.exit(0)
    else:
        print("✗ SOME CHECKS FAILED — see output above")
        sys.exit(1)
