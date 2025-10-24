# MCP Server Evaluation Framework

Evaluation framework for CloudWatch Application Signals MCP Server tools.

## Quick Start

```bash
# Test individual tools
python tools/eval_list_monitored_services.py

# Test multi-tool scenarios
python eval_complex_scenarios.py

# Test enablement tool
python eval_enablement.py

# Debug mode
python tools/eval_list_monitored_services.py --verbose
```

## Structure

```
evaluation/
├── lib/                          # Shared utilities
├── tools/                        # Per-tool evaluators
│   └── eval_<tool_name>.py
├── tasks/
│   ├── tools/                    # Per-tool tasks
│   ├── complex/                  # Multi-tool scenarios
│   └── enablement_tasks.json
├── fixtures/                     # Mock tool responses
│   ├── audit/
│   ├── slo/
│   ├── metrics/
│   ├── trace/
│   └── service/
├── eval_enablement.py            # Enablement evaluation
└── eval_complex_scenarios.py    # Multi-tool scenarios
```

## Adding a New Tool Evaluation

1. Create `tasks/tools/<tool_name>.json`
2. Create `fixtures/<category>/<tool_name>_scenario.json`
3. Copy `tools/eval_list_monitored_services.py` to `tools/eval_<tool_name>.py`
4. Update tool schema and file paths
5. Run: `python tools/eval_<tool_name>.py`

## Reports

Reports saved to `reports/`:
- `<tool_name>_eval_YYYYMMDD_HHMMSS.md`
- `complex_data_eval_YYYYMMDD_HHMMSS.md`
- `enablement_eval_YYYYMMDD_HHMMSS.md`
