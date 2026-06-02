# Odyssey ADK Evalset

`odyssey.evalset.json` is an ADK `EvalSet` artifact encoding 2 eval cases for the
Odyssey concierge agent. It targets the `google.adk.evaluation.AgentEvaluator` API
(ADK >= 2.1).

## Schema

The file was generated with `EvalSet.model_dump_json()` from the live ADK library
(`google.adk.evaluation.eval_set.EvalSet`). Key structure:

```
EvalSet
  eval_set_id   : str
  eval_cases[]  : EvalCase
    eval_id          : str
    conversation[]   : Invocation
      invocation_id  : str
      user_content   : genai.Content  (role="user")
      final_response : genai.Content  (role="model", reference/expected)
      intermediate_data : IntermediateData
        tool_uses[]      : FunctionCall  — expected tool trajectory
        tool_responses[] : FunctionResponse
    session_input : SessionInput  (app_name, user_id, state)
    final_session_state : dict
```

## Cases

| eval_id | What it tests |
|---------|--------------|
| `bali-2500-happy-path` | Turn 1: `plan_trip` fires → within_budget=True. Turn 2: user confirms → `complete_trip` fires → status=confirmed, note contains SIMULATED |
| `bali-700-infeasible-no-booking` | `plan_trip` fires → within_budget=False. `complete_trip` must NOT fire (guardrail + HITL gate). |

## How to run (requires GOOGLE_API_KEY or Vertex AI credentials)

### CLI

```bash
# Set your Gemini API key
export GOOGLE_API_KEY=<your-key>
export ODYSSEY_DATA_MODE=SEED

# From the repo root
adk eval deploy_agents/concierge evals/odyssey.evalset.json
```

### Python API

```python
import asyncio
from google.adk.evaluation import AgentEvaluator

asyncio.run(
    AgentEvaluator.evaluate(
        agent_module="deploy_agents/concierge",
        eval_dataset_file_path_or_dir="evals/odyssey.evalset.json",
    )
)
```

## Assumptions / Notes

- The `final_response` and `intermediate_data.tool_responses` fields are
  **reference/expected** values. ADK uses them for trajectory matching and
  response quality scoring. The actual LLM response may differ in phrasing.
- `final_session_state` is left empty (`{}`) for case 1 because ADK 2.1 does
  not expose a stable API to assert session state keys outside the agent loop.
- The `conversation_scenario` field (user simulator) is intentionally omitted;
  the static `conversation` form is simpler and more deterministic for a demo.
- `tool_uses[].args` in turn 2 (`complete_trip`) uses `{}` because
  `complete_trip` reads its cart from session state, not from call arguments.
- If ADK adds a `rubrics` field to `EvalCase` for custom scoring criteria in a
  future version, add `rubrics: [{criterion: "complete_trip only fires after confirmation"}]`.
