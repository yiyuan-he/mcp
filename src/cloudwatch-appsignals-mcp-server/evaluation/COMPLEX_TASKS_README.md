# Complex Multi-Tool Evaluation Tasks

## Overview

This document describes the **complex, multi-tool evaluation tasks** designed to test realistic root cause analysis scenarios. These tasks are significantly more challenging than simple single-tool queries and provide much more interesting metrics on AI agent performance.

## Why Complex Tasks Matter

### Simple vs Complex Task Comparison

| Aspect | Simple Task | Complex Task |
|--------|-------------|--------------|
| **Example** | "How many services?" | "Why is payment-service slow?" |
| **Tools needed** | 1 tool | 3-4 tools |
| **Reasoning** | Direct lookup | Multi-step analysis |
| **Hit rate insight** | Binary (called it or not) | Shows tool selection strategy |
| **Success rate insight** | Single point of failure | Chain of tool calls |
| **Real-world value** | Low | High (mimics actual debugging) |

### What Makes Metrics Interesting

**Hit Rate** becomes meaningful:
- Did agent call ALL expected tools? (33%, 66%, 100%)
- Did it choose the RIGHT tools vs unnecessary ones?
- Did it discover the problem systematically?

**Success Rate** shows resilience:
- Can agent recover from errors mid-investigation?
- Does it handle multi-step tool chains correctly?

**Tool Call Count** reveals efficiency:
- How many calls to get the answer?
- Did it over-investigate or under-investigate?
- Comparison across different agents/prompts

## Task Catalog

### 1. Root Cause Analysis: Payment Latency (`root_cause_payment_latency`)

**Scenario:** Payment service is experiencing 2,450ms P99 latency (vs 450ms baseline)

**Question:** *"The payment-service in production is experiencing high latency. Investigate the root cause and explain what's causing the performance issue."*

**Expected Tools:**
- `audit_services` - Get overview of service health and findings
- `query_service_metrics` - Analyze latency trends over time
- `search_transaction_spans` - Examine specific error traces

**Expected Answer:**
Database connection pool exhaustion causing timeouts. Payment-db showing 2,100ms response times with DatabaseTimeoutException (72.8%) and ConnectionPoolExhaustedException (27.2%).

**Why It's Hard:**
- Requires synthesizing data from 3 different tools
- Must identify root cause from symptoms
- Needs to prioritize which dependency is problematic

**Metrics to Watch:**
- **Hit Rate:** Did agent call all 3 diagnostic tools?
- **Tool Order:** Did it start with overview (audit) then drill down?
- **Answer Quality:** Did it identify specific root cause (not just "database is slow")?

---

### 2. SLO Breach Investigation (`slo_breach_investigation`)

**Scenario:** payment-latency-slo is breaching at 84.7% attainment (goal: 99%)

**Question:** *"The payment-latency-slo is currently breaching. What is the current attainment rate, what's causing the breach, and which operation is the primary contributor?"*

**Expected Tools:**
- `get_slo` - Understand SLO configuration and current state
- `audit_services` - Identify which operations are problematic

**Expected Answer:**
Attainment is 84.7% (below 99% goal). POST /payments operation showing 2,800ms P99 latency exceeds 500ms threshold. Underlying cause is database performance degradation.

**Why It's Hard:**
- Must correlate SLO config with actual service behavior
- Requires identifying specific operation (not just service)
- Needs to connect breach to underlying technical issue

**Metrics to Watch:**
- **Hit Rate:** Called both get_slo AND audit_services?
- **Answer Completeness:** Provided all 3 requested pieces (attainment, cause, operation)?

---

### 3. Performance Comparison (`performance_comparison_services`)

**Scenario:** Compare payment-service (2,450ms P99) vs auth-service (120ms P99)

**Question:** *"Compare the performance of payment-service and auth-service in production. Why is there such a large difference in their P99 latency?"*

**Expected Tools:**
- `get_service_detail` x2 (once for each service)

**Expected Answer:**
Payment-service: 2,450ms P99, calls slow database (2,100ms). Auth-service: 120ms P99, uses Redis cache (12.5ms). Caching strategy makes auth-service 20x faster.

**Why It's Hard:**
- Same tool called twice with different parameters
- Must compare and contrast two datasets
- Requires identifying architectural difference (database vs cache)

**Metrics to Watch:**
- **Tool Call Count:** Did it call get_service_detail exactly twice?
- **Fixture Handling:** Script must support multiple fixtures for same tool

---

### 4. Error Trend Analysis (`error_trend_analysis`)

**Scenario:** Error rate spiked 540% correlating with latency increase

**Question:** *"Looking at the payment-service metrics over the past 72 hours, how has the error rate changed and is it correlated with latency?"*

**Expected Tools:**
- `query_service_metrics`

**Expected Answer:**
Error rate increased 540% from 0.5% to 3.2%, strongly correlated with latency spike (445% increase). Both started Oct 21. Correlation suggests latency is causing timeout errors.

**Why It's Hard:**
- Requires analyzing time-series data
- Must calculate percentage changes
- Needs to identify correlation between two metrics

---

### 5. Exception Type Analysis (`exception_type_analysis`)

**Scenario:** Multiple exception types in traces, need to identify pattern

**Question:** *"What are the most common types of exceptions occurring in the slow payment transactions?"*

**Expected Tools:**
- `search_transaction_spans`

**Expected Answer:**
DatabaseTimeoutException (72.8%, 342 occurrences) is most common, followed by ConnectionPoolExhaustedException (27.2%, 128 occurrences). Indicates database connection pool exhaustion.

**Why It's Hard:**
- Must parse and summarize trace data
- Requires identifying patterns across multiple exceptions
- Needs to connect exceptions to root cause

---

### 6. Comprehensive Diagnosis (`multi_tool_comprehensive_diagnosis`) ⭐ **HARDEST**

**Scenario:** Complete end-to-end diagnosis requiring synthesis from 4 tools

**Question:** *"Provide a comprehensive diagnosis of the payment-service issue: What's wrong, what's the severity, what's the root cause, and what specific technical problem needs to be fixed?"*

**Expected Tools:**
- `audit_services`
- `get_slo`
- `query_service_metrics`
- `search_transaction_spans`

**Expected Answer:**
SEVERITY: Critical - SLO at 84.7%, 470 slow requests, 68,850 bad requests.
ROOT CAUSE: Database connection pool exhaustion.
SPECIFIC PROBLEM: Pool maxed at 20 connections, DatabaseTimeoutException (72.8%), queries timing out after 5s, 2,100ms avg latency.
FIX: Increase connection pool, optimize queries, add read replicas.

**Why It's the Hardest:**
- Requires ALL 4 tools for complete picture
- Must synthesize data into structured diagnosis
- Needs to provide actionable recommendations
- Tests full root cause analysis workflow

**Evaluation Criteria:**
1. ✅ Identifies critical severity and SLO breach
2. ✅ Pinpoints database connection pool as root cause
3. ✅ Mentions specific exceptions
4. ✅ Provides actionable fix recommendations
5. ✅ Uses data from multiple tools to support conclusion

**Metrics to Watch:**
- **Hit Rate:** 100% means all 4 tools called
- **Tool Call Efficiency:** How many total calls? (4 is optimal, >6 suggests over-investigation)
- **Answer Structure:** Did agent organize findings clearly?

---

## Fixture Design

### Realistic Data Patterns

All fixtures are designed with **realistic patterns** found in production systems:

**Audit Services Fixture:**
- Critical findings with severity levels
- Dependency performance breakdown
- Specific recommendations

**SLO Fixture:**
- Breach status and attainment rate
- Budget exhaustion metrics
- Primary contributor identified

**Metrics Fixture:**
- Time-series data showing degradation
- Anomaly detection results
- Trend analysis

**Trace Spans Fixture:**
- Real exception types
- Stack traces and error messages
- Frequency distributions

### Multi-Fixture Support

The evaluation framework supports:

**Single fixture per tool:**
```json
{
  "fixtures": {
    "audit_services": "audit_services_payment_issue"
  }
}
```

**Multiple fixtures for same tool:**
```json
{
  "fixtures": {
    "get_service_detail": [
      "get_service_detail_payment",
      "get_service_detail_auth"
    ]
  }
}
```

Fixtures are popped in order, allowing the same tool to return different data on successive calls.

---

## Running Complex Tasks

### Run All Complex Tasks

```bash
# Use the complex task file
python evaluation/evaluate_data_tools.py

# Load tasks from:
evaluation/tasks/data_tool_tasks_complex.json
```

### Expected Output Example

```
Starting data tool evaluation (fixture-based approach)

Loaded 7 task(s)
  - root_cause_payment_latency: ['audit_services', 'query_service_metrics', 'search_transaction_spans']
  - slo_breach_investigation: ['get_slo', 'audit_services']
  ...

Running: root_cause_payment_latency...

============================================================
EVALUATION COMPLETE: root_cause_payment_latency
============================================================
Duration: 15.32s
Tool Calls: 3
Hit Rate: 100.0% (3/3 expected tools)
Expected Tools: audit_services, query_service_metrics, search_transaction_spans
Success Rate: 100.0%
Grading: ✅ PASS (llm_judge)
============================================================

Report saved to: evaluation/reports/data_tool_eval_20251023_153045.md
```

---

## Metrics Analysis Guide

### Hit Rate Interpretation

| Hit Rate | Meaning | Implications |
|----------|---------|--------------|
| **100%** | Called all expected tools | Agent has good diagnostic strategy |
| **66%** | Called 2 of 3 tools | Partial investigation, may miss root cause |
| **33%** | Called 1 of 3 tools | Surface-level analysis only |
| **0%** | Called wrong tools | Agent misunderstood the problem |

### Tool Call Efficiency

| Scenario | Optimal | Acceptable | Concerning |
|----------|---------|------------|------------|
| 3-tool task | 3 calls | 3-5 calls | >6 calls |
| 4-tool task | 4 calls | 4-7 calls | >8 calls |
| 1-tool task | 1-2 calls | 2-3 calls | >4 calls |

**Why it matters:**
- Too few calls → Incomplete investigation
- Too many calls → Inefficient, may hit rate limits in production

### Success Rate Patterns

**100% Success Rate:**
- All tools executed without errors
- Fixtures were well-formed
- Agent used tools correctly

**<100% Success Rate:**
- Investigate tool_calls_detail in report
- Check if errors were recoverable
- Verify fixture format matches tool expectations

---

## Extending Complex Tasks

### Creating New Scenarios

1. **Identify Real Problem:** Use actual production issues
2. **Design Fixture Set:** Create 2-4 related fixtures
3. **Write Clear Prompt:** Open-ended question, not leading
4. **Define Expected Answer:** Include specific data points
5. **Set Evaluation Criteria:** 3-5 checkpoints for LLM judge

**Example Template:**

```json
{
  "id": "your_scenario_name",
  "description": "Brief description",
  "prompt": "Open-ended diagnostic question",
  "expected_tools": ["tool1", "tool2", "tool3"],
  "fixtures": {
    "tool1": "fixture_name_1",
    "tool2": "fixture_name_2"
  },
  "expected_answer": "Detailed expected answer with specifics",
  "grading_method": "llm_judge",
  "evaluation_criteria": [
    "Criterion 1: What must be mentioned",
    "Criterion 2: What analysis is needed",
    "Criterion 3: What conclusion is expected"
  ]
}
```

### Fixture Creation Tips

**Make it realistic:**
- Use actual metric values (not perfect numbers)
- Include noise and edge cases
- Add realistic timestamps and IDs

**Ensure interconnection:**
- Fixtures should tell consistent story
- Cross-reference data (same service names, timestamps)
- Make root cause discoverable across tools

**Test fixture quality:**
- Can YOU answer the question from fixtures?
- Are there multiple valid interpretations?
- Is the root cause unambiguous?

---

## Comparison: Simple vs Complex Tasks

### Original Simple Tasks

**File:** `evaluation/tasks/data_tool_tasks.json`

1. Count production services (exact match)
2. Identify highest error rate (llm_judge)
3. Calculate average latency (llm_judge)

**Metrics from simple tasks:**
- Hit rate: Always 100% or 0% (binary)
- Tool calls: Always 1
- Limited diagnostic value

### Complex Tasks (This File)

**File:** `evaluation/tasks/data_tool_tasks_complex.json`

1. Root cause payment latency (3 tools)
2. SLO breach investigation (2 tools)
3. Performance comparison (2 calls, 1 tool)
4. Error trend analysis (1 tool, complex analysis)
5. Exception type analysis (1 tool, pattern recognition)
6. Comprehensive diagnosis (4 tools, synthesis)
7. Dependency identification (1 tool, extraction)

**Metrics from complex tasks:**
- Hit rate: 0% - 100% spectrum
- Tool calls: 1-8+ range
- High diagnostic value for agent capabilities

---

## Future Enhancements

### Task Complexity Levels

**Level 1: Simple (1 tool)**
- Direct lookup
- Single data point
- Exact match grading

**Level 2: Analytical (1-2 tools)**
- Requires calculation
- Pattern identification
- LLM judge grading

**Level 3: Investigative (2-3 tools)** ← **Current complex tasks**
- Multi-tool synthesis
- Root cause analysis
- Evaluation criteria

**Level 4: Expert (4+ tools)** ← **Future**
- Cross-service correlation
- Historical trend analysis
- Recommendation generation

### Proposed Advanced Scenarios

1. **Cross-Service Cascade Failure**
   - Tools: audit_services x3, search_transaction_spans x2
   - Identify failure propagation path

2. **Capacity Planning**
   - Tools: query_service_metrics, audit_services, get_slo
   - Predict when service will hit limits

3. **Cost-Performance Tradeoff**
   - Tools: audit_services, query_service_metrics, get_service_detail
   - Recommend optimization strategy

---

## Questions?

- **Code:** `evaluation/evaluate_data_tools.py`
- **Fixtures:** `evaluation/fixtures/`
- **Task Definitions:** `evaluation/tasks/data_tool_tasks_complex.json`
- **POC Overview:** `evaluation/DATA_TOOLS_POC.md`
