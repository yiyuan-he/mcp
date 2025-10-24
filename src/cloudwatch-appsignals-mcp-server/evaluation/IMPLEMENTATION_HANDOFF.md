# MCP Server Evaluation Framework - Implementation Handoff

## Context

We need to build an evaluation framework for the CloudWatch Application Signals MCP Server (14 tools). The framework will automate testing of tool effectiveness, track quality metrics, and provide actionable feedback for improving tool descriptions and functionality.

## Design Doc

Full design is documented in the main design doc. Key points:

**Two Tool Types, Two Evaluation Approaches:**

1. **Enablement Tool (`get_enablement_guide`)** - Instruction execution evaluation
   - Tests if AI can follow returned instructions to modify code files correctly
   - Validates IAM policies added, dependencies updated, no syntax errors
   - **Priority: Implement this first**

2. **Data-Returning Tools (13 tools)** - Data interpretation evaluation
   - Tests if AI can interpret tool output and give correct answers
   - Uses fixture-based mocking (Anthropic approach)
   - **Priority: Implement after enablement**

## What You're Building

### Phase 1: Enablement Tool Evaluation (Immediate Priority)

Build a Python script (`evaluation/evaluate_enablement.py`) that:

**1. Connects Claude API to MCP Server Programmatically**
- Use Python MCP SDK (`mcp[cli]>=1.11.0` already in dependencies)
- Spawn MCP server process (stdio transport)
- Connect Claude API to the server to enable tool calling

**2. Runs Evaluation Tasks**
- Task definition: "Enable Application Signals for EC2 Python app"
- Claude calls `get_enablement_guide(platform="ec2", language="python", ...)`
- Claude uses file tools (read_file, write_file, edit_file) to modify project files
- Uses mock project from: https://github.com/yiyuan-he/agentic-enablement-eval

**3. Tracks Detailed Metrics**
- Hit rate: Did Claude call the correct tool?
- Success rate: Did tool execute without errors?
- Unnecessary tool calls: Did Claude make redundant calls?
- File operation count: How many read/write operations?
- Task duration: Time to complete
- Tool call timing: Duration of each tool invocation

**4. Validates Code Modifications**
- Check if IAM policy (CloudWatchAgentServerPolicy) was added to CDK stack
- Check if dependencies (aws-opentelemetry-distro) were added to requirements.txt
- Check if modified files still compile/have no syntax errors
- Check if existing code was preserved

**5. Generates Detailed Report**
- Markdown report with all metrics
- Per-task results showing tool calls, validations, pass/fail
- AI's feedback on instruction clarity
- Actionable recommendations for improving enablement guide

### Technical Architecture

```
evaluate_enablement.py
├─> Spawn MCP Server (stdio): python -m awslabs.cloudwatch_appsignals_mcp_server.server
├─> Connect Claude API via MCP Python SDK
├─> For each evaluation task:
│   ├─> Send task prompt to Claude
│   ├─> Track all tool calls (name, parameters, timing)
│   ├─> Capture file modifications
│   └─> Validate modifications
└─> Generate comprehensive markdown report
```

### Key Files to Reference

**Existing work:**
- Design doc: Main evaluation framework design document
- MCP Server: `awslabs/cloudwatch_appsignals_mcp_server/server.py` (uses FastMCP, stdio transport)
- Mock projects: https://github.com/yiyuan-he/agentic-enablement-eval
- Existing Q CLI test script: `agentic-enablement-eval/scripts/cdk/test-ec2.sh` (shows how enablement works end-to-end)

**To create:**
- `evaluation/evaluate_enablement.py` - Main evaluation script
- `evaluation/tasks/enablement_tasks.json` - Task definitions
- `evaluation/reports/` - Generated reports directory

### Dependencies

Already installed in project:
- `mcp[cli]>=1.11.0` - Python MCP SDK
- `boto3` - For AWS clients (already present)

May need to add:
- `anthropic>=0.18.0` - For Claude API

### Success Criteria

The implementation is complete when:

1. ✅ Script runs Claude with MCP server connected programmatically
2. ✅ Evaluation task completes: Claude calls enablement tool → follows instructions → modifies files
3. ✅ All metrics tracked and captured (hit rate, success rate, tool calls, timing)
4. ✅ Validation system checks code modifications are correct
5. ✅ Markdown report generated with all metrics and findings
6. ✅ Script can be run via: `python evaluation/evaluate_enablement.py`

### Phase 2: Data-Returning Tools Evaluation (Future)

**After Phase 1 is complete**, build similar evaluation for the 13 data-returning tools using the Anthropic fixture-based approach. The agent loop, metrics tracking, and reporting infrastructure built in Phase 1 will be reused (~80% code reuse).

## Resources

**MCP Python SDK Documentation:**
- https://github.com/modelcontextprotocol/python-sdk

**Anthropic Tool Use:**
- https://docs.anthropic.com/en/docs/build-with-claude/tool-use

**Reference Implementation (Anthropic MCP Eval - TypeScript):**
- https://github.com/openai/openai-cookbook/blob/main/examples/evaluation/use-cases/mcp_eval_notebook.ipynb
- Note: We're building Python version, not using their platform

## Getting Started

1. Clone the mock project repo: `git clone https://github.com/yiyuan-he/agentic-enablement-eval`
2. Review the design doc to understand the evaluation approach
3. Start with `evaluation/evaluate_enablement.py` - build the agent loop first
4. Test against the EC2 Python mock project from the repo
5. Iterate on validation and reporting

## Questions?

Refer to the main design doc or reach out to the team for clarification.
