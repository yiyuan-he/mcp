# Application Signals Enablement Evaluation

Evaluation framework for testing if an AI agent can enable AWS Application Signals by modifying Infrastructure as Code.

## Quick Start

```bash
# Run all tasks
python eval_enablement.py

# Run with verbose logging
python eval_enablement.py -v

# Run specific task without cleanup
python eval_enablement.py --task ec2_python_flask --no-cleanup
```

## CLI Options

| Option | Description |
|--------|-------------|
| `-v, --verbose` | Enable debug logging |
| `--task TASK_ID` | Run specific task (default: all). Example: `--task ec2_python_flask` |
| `--no-cleanup` | Keep git changes for inspection |

## How It Works

1. **Agent Loop**: AI reads enablement guide, modifies IaC files
2. **Build Validation**: Runs `npm run build` to verify compilation
3. **LLM-as-Judge**: Evaluates git diff against validation rubric

## Task Configuration

Define tasks in `tasks/enablement_tasks.json`:

```json
{
  "id": "ec2_python_flask",
  "platform": "ec2",
  "language": "python",
  "framework": "flask",
  "iac_directory": "infrastructure/ec2/cdk",
  "app_directory": "sample-apps/python/flask",
  "expected_tools": ["get_enablement_guide"],
  "validation_rubric": [
    "IAM: CloudWatchAgentServerPolicy is attached",
    "Prerequisites: wget, docker, python3-pip installed",
    "CloudWatch Agent: Downloaded, installed, and configured",
    "..."
  ]
}
```

## Validation Rubric

Each criterion is evaluated by LLM examining git diff + build results.

**Best Practices:**
- Be specific (include exact values)
- Use category prefixes (`IAM:`, `OTel Config:`)
- Make conditionals explicit (`Dockerfile (if Docker):`)

## Metrics

- Task duration, tool usage, success rates
- Validation pass/fail per criterion
- File operation counts

## Output Example

```
Running: ec2_python_flask...
✓ Build succeeded
============================================================
EVALUATION COMPLETE: ec2_python_flask
============================================================
Duration: 73.10s
Hit Rate: 100.0%
Success Rate: 100.0%
File Operations: 8
Validation: ✅ PASS (14/14 criteria met)
============================================================
```

## Troubleshooting

- **No changes detected**: Check paths in task config
- **Build fails**: Verify syntax, run `npm install`
- **Unexpected validation**: Use `--no-cleanup` + inspect `git diff`
