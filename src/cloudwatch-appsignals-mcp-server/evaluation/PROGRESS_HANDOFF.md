# MCP Server Evaluation Framework - Progress Handoff

**Date:** 2025-10-23
**Status:** Phase 1 (Enablement Tool Evaluation) - Implementation Complete, Testing In Progress

---

## What We Built

A complete evaluation framework for the CloudWatch Application Signals MCP server's `enable_application_signals` tool. The framework automates testing of whether AI agents can successfully follow enablement instructions to modify code files correctly.

### Core Components Implemented

**1. Agent Loop with MCP Integration** (`evaluation/evaluate_enablement.py`)
- Connects Claude Sonnet 4 (via Bedrock) to MCP server programmatically
- Provides file operation tools (read_file, write_file, list_files) for Claude to modify code
- Tracks all tool calls with detailed timing and success metrics
- Runs evaluation tasks until completion or max turns (20)

**2. LLM-as-Judge Validation**
- Uses Claude to evaluate git diff against natural language rubrics
- Validates semantic correctness (not just pattern matching)
- Provides reasoning for each pass/fail decision
- Industry-standard approach for evaluating AI agent outputs

**3. Metrics Tracking**
- **Hit Rate:** Did Claude call the correct tool?
- **Success Rate:** Did tools execute without errors?
- **Unnecessary Tool Calls:** Count of redundant calls
- **File Operations:** Number of read/write/list operations
- **Task Duration:** Total time to complete
- **Validation Pass Rate:** LLM-as-judge assessment

**4. Report Generation**
- Generates detailed markdown reports saved to `evaluation/reports/`
- Includes: tool call trace with timing, validation results with reasoning, git diff, all metrics
- Console output shows clean summary, details in report

**5. CLI with Verbose Mode**
```bash
# Normal mode (clean output)
python evaluation/evaluate_enablement.py

# Verbose mode (all debug logs)
python evaluation/evaluate_enablement.py --verbose
```

---

## File Structure

```
evaluation/
├── evaluate_enablement.py          # Main evaluation script
├── tasks/
│   └── enablement_tasks.json       # Task definitions with validation rubrics
├── reports/                         # Generated evaluation reports (auto-created)
└── IMPLEMENTATION_HANDOFF.md        # Original implementation spec
```

**Mock Project:**
- Lives at: `/Users/yiyuanh/projects/agentic-enablement-eval`
- Contains: CDK infrastructure, Python Flask app, Dockerfile
- Used for: File operations during evaluation

---

## How It Works

1. **Load task definition** from `enablement_tasks.json`
2. **Connect to MCP server** (stdio transport, spawned as subprocess)
3. **Run agent loop:**
   - Send task prompt to Claude
   - Claude calls `enable_application_signals` to get instructions
   - Claude uses file tools to modify mock project files
   - Loop continues until Claude finishes
4. **Validate changes** using LLM-as-judge:
   - Get git diff of all changes
   - Send diff + rubric to Claude for evaluation
   - Parse pass/fail with reasoning
5. **Generate report** and save to markdown file

---

## Current Status

### ✅ Completed
- Agent loop with Bedrock + MCP integration
- File operation tools (read, write, list)
- Metrics tracking system
- LLM-as-judge validation
- Report generation
- CLI argument parsing
- Verbose logging mode

### ⚠️ In Progress
- **End-to-end testing:** Just fixed an import bug, needs full test run
- Verify report generation works correctly
- Confirm all metrics are captured accurately

### ❌ Not Started (Future Work)
- **Phase 2: Data-Returning Tools Evaluation** (13 other tools)
  - Fixture-based evaluation
  - Mock AWS API responses
  - Validate AI's final answers
  - ~80% code reuse from Phase 1

---

## Key Design Decisions

**Why LLM-as-Judge?**
- Handles semantic correctness (not just regex patterns)
- Flexible across languages/platforms (Python, Java, Node.js, .NET)
- Provides actionable feedback with reasoning
- Industry standard for AI agent evaluation
- Tradeoff: Slower (~5-10s) and costs money (~$0.01/validation), but acceptable

**Why Claude Sonnet 4 via Bedrock?**
- Latest model with best performance
- Uses AWS credentials (no separate API keys)
- Integrates with existing AWS tooling

**Why Natural Language Rubrics?**
- Easy to extend to new languages/platforms
- No need for custom parsers per language
- LLM understands context (e.g., "check requirements.txt OR Dockerfile")

---

## Dependencies

**Already in pyproject.toml:**
- `mcp[cli]>=1.11.0` - MCP Python SDK
- `boto3>=1.40.41` - AWS SDK (for Bedrock)
- `loguru>=0.7.3` - Logging

**Runtime requirements:**
- AWS credentials configured (`aws configure`)
- Python 3.11+
- Git (for diff capture and project reset)
- Mock project cloned at expected path

---

## Testing the Framework

**Run evaluation:**
```bash
python evaluation/evaluate_enablement.py
```

**Expected console output:**
```
Starting Application Signals enablement evaluation

Loaded 1 task(s)
  - ec2_python_flask: ec2 + python

Running: ec2_python_flask...

============================================================
EVALUATION COMPLETE: ec2_python_flask
============================================================
Duration: 128.46s
Turns: 16
Hit Rate: 100.0%
Success Rate: 93.3%
Unnecessary Tool Calls: 0
Validation: ✅ PASS (5/5 criteria met)
============================================================

Report saved to: evaluation/reports/enablement_eval_20251023_103045.md
```

**Check the report:**
```bash
cat evaluation/reports/enablement_eval_*.md
```

---

## Known Issues / Todos

1. **Test end-to-end** - Just fixed import bug, needs full validation
2. **Verify turns calculation** - Current formula may be off
3. **Add error handling** for MCP server crashes
4. **Consider adding:**
   - Retry logic for transient Bedrock errors
   - Progress bar for long-running evaluations
   - Summary report across multiple runs
   - CI/CD integration

---

## Adding New Tasks

Edit `evaluation/tasks/enablement_tasks.json`:

```json
{
  "id": "ec2_nodejs_express",
  "description": "Enable Application Signals for EC2 Node.js Express",
  "platform": "ec2",
  "language": "nodejs",
  "framework": "express",
  "iac_directory": "infrastructure/ec2/cdk",
  "app_directory": "sample-apps/nodejs/express",
  "mock_project_path": "/path/to/mock/project",
  "validation_rubric": [
    "CloudWatchAgentServerPolicy IAM policy attached to EC2 role",
    "ADOT dependency added to package.json",
    "Modified files have no syntax errors",
    "Existing code preserved"
  ]
}
```

The rubric is natural language - just describe what should be validated!

---

## Phase 2: Data-Returning Tools (Future)

When ready to implement evaluation for the other 13 tools:

**Architecture (from design doc):**
- Fixture-based evaluation (mock AWS API responses)
- Task definitions with prompt-response pairs
- Agent loop intercepts tool calls, returns fixtures
- Grader validates AI's final answer (exact match or LLM-as-judge)
- Reuse ~80% of agent loop + metrics code

**Estimated effort:** 1-2 weeks

---

## Questions?

**Code location:** `evaluation/evaluate_enablement.py`
**Design doc:** Main design document (updated with LLM-as-judge details)
**Mock projects:** https://github.com/yiyuan-he/agentic-enablement-eval

**Next steps:**
1. Run full end-to-end test
2. Fix any bugs discovered
3. Run multiple evaluations to verify consistency
4. Document findings and share report examples
