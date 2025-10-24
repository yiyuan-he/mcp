# Data Tools Evaluation POC

## Overview

This POC demonstrates the **fixture-based evaluation approach** for data-returning tools, as outlined in the design doc. Unlike the enablement tool evaluation (which validates code modifications), this approach tests whether AI agents can correctly **interpret tool outputs** and provide accurate answers.

## Key Differences from Enablement Evaluation

| Aspect | Enablement Tool | Data Tools (This POC) |
|--------|-----------------|----------------------|
| **What's tested** | Can AI follow instructions to modify code? | Can AI interpret data and answer questions? |
| **Tool execution** | Real file operations on mock project | Fixtures (pre-defined responses) |
| **Validation** | LLM-as-judge on git diffs | Exact match + LLM-as-judge on answers |
| **External dependencies** | Mock project repo, git | None (self-contained) |
| **Metrics focus** | File operations, code correctness | Answer accuracy, data interpretation |

## Architecture

```
evaluate_data_tools.py
├─> Load task definition (prompt + expected answer)
├─> Initialize Claude with tool definitions
├─> For each evaluation task:
│   ├─> Send question prompt to Claude
│   ├─> Intercept tool calls, return fixtures
│   ├─> Extract Claude's final answer
│   ├─> Grade answer (exact match OR LLM-as-judge)
│   └─> Track metrics (hit rate, success rate, timing)
└─> Generate markdown report
```

## File Structure

```
evaluation/
├── evaluate_data_tools.py          # Main evaluation script (POC)
├── fixtures/
│   └── list_monitored_services.json # Sample fixture data
├── tasks/
│   └── data_tool_tasks.json         # Task definitions
└── reports/                         # Generated reports (auto-created)
```

## Task Definition Format

Each task includes:

```json
{
  "id": "count_production_services",
  "description": "Test if AI can count services in production environment",
  "prompt": "How many services are running in production?",
  "expected_tools": ["list_monitored_services"],
  "fixture_name": "list_monitored_services",
  "expected_answer": "2",
  "grading_method": "exact_match"
}
```

**Fields:**
- `id`: Unique task identifier
- `prompt`: Question for the AI agent
- `expected_tools`: Tools the AI should call
- `fixture_name`: Which fixture file to load
- `expected_answer`: Correct answer for grading
- `grading_method`: `exact_match` or `llm_judge`

## Fixture Format

Fixtures are JSON files containing mock tool responses:

```json
{
  "services": [
    {
      "service_name": "payment-service",
      "environment": "eks:production",
      "metrics_summary": {
        "latency_p99": 250.5,
        "error_rate": 0.02
      }
    }
  ],
  "total_count": 3
}
```

## Grading Methods

### 1. Exact Match
- Simple string comparison (case-insensitive, whitespace-trimmed)
- Fast and deterministic
- Best for: numeric answers, yes/no, simple facts

### 2. LLM-as-Judge
- Uses Claude to evaluate semantic correctness
- Flexible for varied phrasing
- Best for: descriptive answers, calculations, explanations

Example grading prompt:
```
Question: Which service has the highest error rate?
Expected: order-service
Agent's Answer: The order-service has the highest error rate at 5%

LLM Judge: [PASS] The answer correctly identifies order-service
```

## Metrics Tracked

- **Hit Rate**: Did the agent call the expected tool(s)?
- **Success Rate**: Were tool calls successful (no errors)?
- **Tool Call Count**: Total number of tool invocations
- **Task Duration**: Time to complete the task
- **Answer Accuracy**: Did the agent provide the correct answer?

## Running the POC

```bash
# Normal mode
python evaluation/evaluate_data_tools.py

# Verbose mode (debug logs)
python evaluation/evaluate_data_tools.py --verbose
```

**Expected output:**
```
Starting data tool evaluation (fixture-based approach)

Loaded 3 task(s)
  - count_production_services: ['list_monitored_services']
  - identify_highest_error_rate: ['list_monitored_services']
  - calculate_average_latency: ['list_monitored_services']

Running: count_production_services...

============================================================
EVALUATION COMPLETE: count_production_services
============================================================
Duration: 3.45s
Tool Calls: 1
Hit Rate: 100.0%
Success Rate: 100.0%
Grading: ✅ PASS (exact_match)
============================================================

Report saved to: evaluation/reports/data_tool_eval_20251023_143045.md
```

## Sample Tasks

### Task 1: Count Services (Exact Match)
- **Question**: "How many services are running in production?"
- **Expected Tool**: `list_monitored_services`
- **Expected Answer**: "2"
- **Grading**: Exact match

### Task 2: Identify Highest Error Rate (LLM Judge)
- **Question**: "Which service has the highest error rate?"
- **Expected Tool**: `list_monitored_services`
- **Expected Answer**: "order-service"
- **Grading**: LLM-as-judge (allows variations like "The order-service has the highest error rate")

### Task 3: Calculate Average (LLM Judge)
- **Question**: "What is the average P99 latency across all services?"
- **Expected Tool**: `list_monitored_services`
- **Expected Answer**: "183.8"
- **Grading**: LLM-as-judge (allows rounding, units)

## Extending the POC

### Adding New Tools

1. **Create fixture** in `evaluation/fixtures/<tool_name>.json`
2. **Add tool schema** to `get_bedrock_tools()` in evaluate_data_tools.py
3. **Create tasks** in `data_tool_tasks.json`

Example for adding `get_slo`:

```json
// fixtures/get_slo.json
{
  "slo_name": "payment-latency-slo",
  "goal": 0.99,
  "metric_type": "LATENCY",
  "threshold": 500,
  "current_attainment": 0.97
}
```

```json
// tasks/data_tool_tasks.json
{
  "id": "check_slo_breach",
  "prompt": "Is the payment-latency-slo currently meeting its goal?",
  "expected_tools": ["get_slo"],
  "fixture_name": "get_slo",
  "expected_answer": "No, it's at 97% attainment vs 99% goal",
  "grading_method": "llm_judge"
}
```

### Adding Multi-Tool Tasks

Tasks can require multiple tool calls:

```json
{
  "id": "compare_services",
  "prompt": "Compare payment-service and auth-service latency",
  "expected_tools": ["get_service_detail", "get_service_detail"],
  "fixture_name": "service_comparison",
  "expected_answer": "payment-service has higher latency (250ms vs 120ms)",
  "grading_method": "llm_judge"
}
```

## Code Reuse from Phase 1

This POC reuses ~60% of code from `evaluate_enablement.py`:

**Reused components:**
- ✅ `MetricsTracker` class (identical)
- ✅ Bedrock client initialization
- ✅ Agent loop structure (modified for fixtures)
- ✅ Report generation (adapted for answer grading)
- ✅ CLI argument parsing

**New components:**
- 🆕 Fixture loading system
- 🆕 Answer grading (exact match + LLM judge)
- 🆕 Simplified tool execution (no file operations)

## Next Steps for Full Implementation

1. **Expand tool coverage**: Add fixtures for all 13 data-returning tools
2. **Multi-tool tasks**: Create complex scenarios requiring multiple tool calls
3. **Batch evaluation**: Run all tasks in parallel for efficiency
4. **Regression testing**: Integrate into CI/CD pipeline
5. **Fixture generation**: Tool to auto-generate fixtures from real API responses

## Comparison with Anthropic's Approach

This POC follows the **fixture-based evaluation pattern** recommended by Anthropic:

✅ Pre-defined tool responses (fixtures)
✅ No live API calls during evaluation
✅ Deterministic, reproducible results
✅ LLM-as-judge for semantic grading
✅ Fast iteration (no infrastructure dependencies)

See: [Anthropic's MCP Evaluation Guide](https://github.com/anthropics/anthropic-cookbook/blob/main/patterns/mcp_eval.ipynb)

## Benefits of This Approach

1. **No infrastructure dependencies**: No AWS accounts, mock projects, or external services needed
2. **Fast execution**: Fixtures return instantly (vs real API calls)
3. **Reproducible**: Same fixture = same result every time
4. **Easy to extend**: Just add JSON files for new test cases
5. **Version controlled**: Fixtures in git track expected behavior over time
6. **Parallel testing**: Run many tasks simultaneously without rate limits

## Limitations

1. **Fixtures must be maintained**: API changes require fixture updates
2. **Limited error testing**: Harder to test edge cases and error handling
3. **No integration testing**: Doesn't catch real API issues
4. **Fixture realism**: Must ensure fixtures match real API responses

## Questions?

- **Code**: `evaluation/evaluate_data_tools.py`
- **Design**: See `IMPLEMENTATION_HANDOFF.md` and `PROGRESS_HANDOFF.md`
- **Phase 1 (Enablement)**: See `evaluation/evaluate_enablement.py`
