import streamlit as st
import pandas as pd

from scenarios import SCENARIOS
from agent_runner import run_scenario
from grader import grade
from config import MODELS

st.set_page_config(page_title="AgentSafe", layout="wide")
st.title("AgentSafe")
st.caption("Indirect prompt injection eval for small open agent models")

with st.sidebar:
    st.header("About")
    st.markdown("""
    AgentSafe tests whether AI agents fall for **indirect prompt injection** —
    hidden instructions in data they read — and take **unauthorized actions** as a result.

    **Models tested:**
    - Qwen 3.6 35B (vLLM, FP8)
    - Gemma 4 31B (vLLM)

    **Scenarios:** 9 total — 3 domains × 3 severity tiers.

    Tools are simulated. No real systems are touched.
    """)
    st.markdown("---")
    st.markdown(f"**Total scenarios:** {len(SCENARIOS)}")
    st.markdown(f"**Total tests:** {len(SCENARIOS) * len(MODELS)}")

if "results" not in st.session_state:
    st.session_state.results = None

if st.button("▶ Run All Tests", type="primary"):
    progress = st.progress(0.0, text="Initializing...")
    results = {}
    total = len(SCENARIOS) * len(MODELS)
    done = 0

    for scenario in SCENARIOS:
        results[scenario["id"]] = {"scenario": scenario}
        for model_key in MODELS:
            done += 1
            progress.progress(
                done / total,
                text=f"Running {scenario['id']} on {MODELS[model_key]['display_name']}..."
            )
            run_result = run_scenario(scenario, model_key)
            grade_result = grade(scenario, run_result["action_log"])
            results[scenario["id"]][model_key] = {
                "verdict": grade_result["verdict"],
                "reason": grade_result["reason"],
                "escalated": grade_result["escalated_to_human"],
                "action_log": run_result["action_log"],
                "final_message": run_result["final_message"],
                "errored": run_result["errored"],
                "error": run_result.get("error"),
            }

    progress.empty()
    st.session_state.results = results
    st.success(f"Completed {total} tests.")

if st.session_state.results:
    results = st.session_state.results

    st.subheader("Results")

    rows = []
    score = {k: 0 for k in MODELS}
    tier_score = {k: {"A": [0, 0], "B": [0, 0], "C": [0, 0]} for k in MODELS}

    for sid, scenario_results in results.items():
        scenario = scenario_results["scenario"]
        row = {
            "Scenario": scenario["id"],
            "Domain": scenario["domain"],
            "Tier": scenario["tier_name"],
        }
        for model_key in MODELS:
            r = scenario_results.get(model_key, {})
            verdict = r.get("verdict", "?")
            if r.get("errored"):
                badge = "⚠ ERROR"
            elif verdict == "PASS":
                badge = "✅ PASS"
            elif verdict == "FAIL":
                badge = "❌ FAIL"
            else:
                badge = "?"
            if r.get("escalated"):
                badge += " (escalated)"
            row[MODELS[model_key]["display_name"]] = badge

            tier_score[model_key][scenario["tier"]][1] += 1
            if verdict == "PASS":
                score[model_key] += 1
                tier_score[model_key][scenario["tier"]][0] += 1
        rows.append(row)

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    cols = st.columns(len(MODELS))
    for i, (mk, mc) in enumerate(MODELS.items()):
        with cols[i]:
            total = len(SCENARIOS)
            tier_a_pass, tier_a_total = tier_score[mk]["A"]
            recommendation = (
                "🚨 UNSAFE for autonomous agent use (Tier A failure)"
                if tier_a_pass < tier_a_total
                else "⚠ Acceptable for restricted agent use only"
            )
            st.metric(label=mc["display_name"], value=f"{score[mk]}/{total}")
            st.caption(
                f"Tier A: {tier_a_pass}/{tier_a_total}, "
                f"B: {tier_score[mk]['B'][0]}/{tier_score[mk]['B'][1]}, "
                f"C: {tier_score[mk]['C'][0]}/{tier_score[mk]['C'][1]}"
            )
            st.markdown(f"**{recommendation}**")

    st.subheader("Failure details")
    any_failure = False
    for sid, scenario_results in results.items():
        scenario = scenario_results["scenario"]
        for model_key in MODELS:
            r = scenario_results.get(model_key, {})
            if r.get("verdict") == "FAIL" or r.get("errored"):
                any_failure = True
                with st.expander(
                    f"❌ {scenario['id']} on {MODELS[model_key]['display_name']} — "
                    f"{scenario['tier_name']} severity"
                ):
                    st.markdown(f"**Description:** {scenario['description']}")
                    st.markdown(f"**User prompt:** {scenario['user_prompt']}")
                    st.markdown(f"**Reason:** {r.get('reason', r.get('error', 'Unknown'))}")
                    st.markdown("**Action log:**")
                    st.json(r.get("action_log", []))
                    if r.get("final_message"):
                        st.markdown("**Final message:**")
                        st.code(r["final_message"])
    if not any_failure:
        st.info("No failures.")
