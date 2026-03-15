---
name: "senior-prompt-engineer"
description: This skill should be used when the user asks to "optimize prompts", "design prompt templates", "evaluate LLM outputs", "build agentic systems", "implement RAG", "create few-shot examples", "analyze token usage", or "design AI workflows". Use for prompt engineering patterns, LLM evaluation frameworks, agent architectures, and structured output design.
---

# Senior Prompt Engineer

Prompt engineering patterns, LLM evaluation frameworks, and agentic system design.

## Table of Contents

- [Quick Start](#quick-start)
- [Tools Overview](#tools-overview)
  - [Prompt Optimizer](#1-prompt-optimizer)
  - [RAG Evaluator](#2-rag-evaluator)
  - [Agent Orchestrator](#3-agent-orchestrator)
- [Prompt Engineering Workflows](#prompt-engineering-workflows)
  - [Prompt Optimization Workflow](#prompt-optimization-workflow)
  - [Few-Shot Example Design](#few-shot-example-design-workflow)
  - [Structured Output Design](#structured-output-design-workflow)
- [Reference Documentation](#reference-documentation)
- [Common Patterns Quick Reference](#common-patterns-quick-reference)

---

## Quick Start

```bash
# Analyze and optimize a prompt file
python scripts/prompt_optimizer.py prompts/my_prompt.txt --analyze

# Evaluate RAG retrieval quality
python scripts/rag_evaluator.py --contexts contexts.json --questions questions.json

# Visualize agent workflow from definition
python scripts/agent_orchestrator.py agent_config.yaml --visualize
```

---

## Tools Overview

### 1. Prompt Optimizer

Analyzes prompts for token efficiency, clarity, and structure. Generates optimized versions.

**Input:** Prompt text file or string
**Output:** Analysis report with optimization suggestions

**Usage:**
```bash
# Analyze a prompt file
python scripts/prompt_optimizer.py prompt.txt --analyze

# Output:
# Token count: 847
# Estimated cost: $0.0025 (GPT-4)
# Clarity score: 72/100
# Issues found:
#   - Ambiguous instruction at line 3
#   - Missing output format specification
#   - Redundant context (lines 12-15 repeat lines 5-8)
# Suggestions:
#   1. Add explicit output format: "Respond in JSON with keys: ..."
#   2. Remove redundant context to save 89 tokens
#   3. Clarify "analyze" -> "list the top 3 issues with severity ratings"

# Generate optimized version
python scripts/prompt_optimizer.py prompt.txt --optimize --output optimized.txt

# Count tokens for cost estimation
python scripts/prompt_optimizer.py prompt.txt --tokens --model gpt-4

# Extract and manage few-shot examples
python scripts/prompt_optimizer.py prompt.txt --extract-examples --output examples.json
```

---

### 2. RAG Evaluator

Evaluates Retrieval-Augmented Generation quality by measuring context relevance and answer faithfulness.

**Input:** Retrieved contexts (JSON) and questions/answers
**Output:** Evaluation metrics and quality report

**Usage:**
```bash
# Evaluate retrieval quality
python scripts/rag_evaluator.py --contexts retrieved.json --questions eval_set.json

# Output:
# === RAG Evaluation Report ===
# Questions evaluated: 50
#
# Retrieval Metrics:
#   Context Relevance: 0.78 (target: >0.80)
#   Retrieval Precision@5: 0.72
#   Coverage: 0.85
#
# Generation Metrics:
#   Answer Faithfulness: 0.91
#   Groundedness: 0.88
#
# Issues Found:
#   - 8 questions had no relevant context in top-5
#   - 3 answers contained information not in context
#
# Recommendations:
#   1. Improve chunking strategy for technical documents
#   2. Add metadata filtering for date-sensitive queries

# Evaluate with custom metrics
python scripts/rag_evaluator.py --contexts retrieved.json --questions eval_set.json \
    --metrics relevance,faithfulness,coverage

# Export detailed results
python scripts/rag_evaluator.py --contexts retrieved.json --questions eval_set.json \
    --output report.json --verbose
```

---

### 3. Agent Orchestrator

Parses agent definitions and visualizes execution flows. Validates tool configurations.

**Input:** Agent configuration (YAML/JSON)
**Output:** Workflow visualization, validation report

**Usage:**
```bash
# Validate agent configuration
python scripts/agent_orchestrator.py agent.yaml --validate

# Output:
# === Agent Validation Report ===
# Agent: research_assistant
# Pattern: ReAct
#
# Tools (4 registered):
#   [OK] web_search - API key configured
#   [OK] calculator - No config needed
#   [WARN] file_reader - Missing allowed_paths
#   [OK] summarizer - Prompt template valid
#
# Flow Analysis:
#   Max depth: 5 iterations
#   Estimated tokens/run: 2,400-4,800
#   Potential infinite loop: No
#
# Recommendations:
#   1. Add allowed_paths to file_reader for security
#   2. Consider adding early exit condition for simple queries

# Visualize agent workflow (ASCII)
python scripts/agent_orchestrator.py agent.yaml --visualize

# Output:
# ┌─────────────────────────────────────────┐
# │            research_assistant           │
# │              (ReAct Pattern)            │
# └─────────────────┬───────────────────────┘
#                   │
#          ┌────────▼────────┐
#          │   User Query    │
#          └────────┬────────┘
#                   │
#          ┌────────▼────────┐
#          │     Think       │◄──────┐
#          └────────┬────────┘       │
#                   │                │
#          ┌────────▼────────┐       │
#          │   Select Tool   │       │
#          └────────┬────────┘       │
#                   │                │
#     ┌─────────────┼─────────────┐  │
#     ▼             ▼             ▼  │
# [web_search] [calculator] [file_reader]
#     │             │             │  │
#     └─────────────┼─────────────┘  │
#                   │                │
#          ┌────────▼────────┐       │
#          │    Observe      │───────┘
#          └────────┬────────┘
#                   │
#          ┌────────▼────────┐
#          │  Final Answer   │
#          └─────────────────┘

# Export workflow as Mermaid diagram
python scripts/agent_orchestrator.py agent.yaml --visualize --format mermaid
```

---

## Prompt Engineering Workflows

### Prompt Optimization Workflow

Use when improving an existing prompt's performance or reducing token costs.

**Step 1: Baseline current prompt**
```bash
python scripts/prompt_optimizer.py current_prompt.txt --analyze --output baseline.json
```

**Step 2: Identify issues**
Review the analysis report for:
- Token waste (redundant instructions, verbose examples)
- Ambiguous instructions (unclear output format, vague verbs)
- Missing constraints (no length limits, no format specification)

**Step 3: Apply optimization patterns**
| Issue | Pattern to Apply |
|-------|------------------|
| Ambiguous output | Add explicit format specification |
| Too verbose | Extract to few-shot examples |
| Inconsistent results | Add role/persona framing |
| Missing edge cases | Add constraint boundaries |

**Step 4: Generate optimized version**
```bash
python scripts/prompt_optimizer.py current_prompt.txt --optimize --output optimized.txt
```

**Step 5: Compare results**
```bash
python scripts/prompt_optimizer.py optimized.txt --analyze --compare baseline.json
# Shows: token reduction, clarity improvement, issues resolved
```

**Step 6: Validate with test cases**
Run both prompts against your evaluation set and compare outputs.

---

### Few-Shot Example Design Workflow

Use when creating examples for in-context learning.

**Step 1: Define the task clearly**
```
Task: Extract product entities from customer reviews
Input: Review text
Output: JSON with {product_name, sentiment, features_mentioned}
```

**Step 2: Select diverse examples (3-5 recommended)**
| Example Type | Purpose |
|--------------|---------|
| Simple case | Shows basic pattern |
| Edge case | Handles ambiguity |
| Complex case | Multiple entities |
| Negative case | What NOT to extract |

**Step 3: Format consistently**
```
Example 1:
Input: "Love my new iPhone 15, the camera is amazing!"
Output: {"product_name": "iPhone 15", "sentiment": "positive", "features_mentioned": ["camera"]}

Example 2:
Input: "The laptop was okay but battery life is terrible."
Output: {"product_name": "laptop", "sentiment": "mixed", "features_mentioned": ["battery life"]}
```

**Step 4: Validate example quality**
```bash
python scripts/prompt_optimizer.py prompt_with_examples.txt --validate-examples
# Checks: consistency, coverage, format alignment
```

**Step 5: Test with held-out cases**
Ensure model generalizes beyond your examples.

---

### Structured Output Design Workflow

Use when you need reliable JSON/XML/structured responses.

**Step 1: Define schema**
```json
{
  "type": "object",
  "properties": {
    "summary": {"type": "string", "maxLength": 200},
    "sentiment": {"enum": ["positive", "negative", "neutral"]},
    "confidence": {"type": "number", "minimum": 0, "maximum": 1}
  },
  "required": ["summary", "sentiment"]
}
```

**Step 2: Include schema in prompt**
```
Respond with JSON matching this schema:
- summary (string, max 200 chars): Brief summary of the content
- sentiment (enum): One of "positive", "negative", "neutral"
- confidence (number 0-1): Your confidence in the sentiment
```

**Step 3: Add format enforcement**
```
IMPORTANT: Respond ONLY with valid JSON. No markdown, no explanation.
Start your response with { and end with }
```

**Step 4: Validate outputs**
```bash
python scripts/prompt_optimizer.py structured_prompt.txt --validate-schema schema.json
```

---

## Reference Documentation

| File | Contains | Load when user asks about |
|------|----------|---------------------------|
| `references/prompt_engineering_patterns.md` | 10 prompt patterns with input/output examples | "which pattern?", "few-shot", "chain-of-thought", "role prompting" |
| `references/llm_evaluation_frameworks.md` | Evaluation metrics, scoring methods, A/B testing | "how to evaluate?", "measure quality", "compare prompts" |
| `references/agentic_system_design.md` | Agent architectures (ReAct, Plan-Execute, Tool Use) | "build agent", "tool calling", "multi-agent" |

---

## Common Patterns Quick Reference

| Pattern | When to Use | Example |
|---------|-------------|---------|
| **Zero-shot** | Simple, well-defined tasks | "Classify this email as spam or not spam" |
| **Few-shot** | Complex tasks, consistent format needed | Provide 3-5 examples before the task |
| **Chain-of-Thought** | Reasoning, math, multi-step logic | "Think step by step..." |
| **Role Prompting** | Expertise needed, specific perspective | "You are an expert tax accountant..." |
| **Structured Output** | Need parseable JSON/XML | Include schema + format enforcement |

---

## Common Commands

```bash
# Prompt Analysis
python scripts/prompt_optimizer.py prompt.txt --analyze          # Full analysis
python scripts/prompt_optimizer.py prompt.txt --tokens           # Token count only
python scripts/prompt_optimizer.py prompt.txt --optimize         # Generate optimized version

# RAG Evaluation
python scripts/rag_evaluator.py --contexts ctx.json --questions q.json  # Evaluate
python scripts/rag_evaluator.py --contexts ctx.json --compare baseline  # Compare to baseline

# Agent Development
python scripts/agent_orchestrator.py agent.yaml --validate       # Validate config
python scripts/agent_orchestrator.py agent.yaml --visualize      # Show workflow
python scripts/agent_orchestrator.py agent.yaml --estimate-cost  # Token estimation
```


---
name: "senior-fullstack"
description: Fullstack development toolkit with project scaffolding for Next.js, FastAPI, MERN, and Django stacks, code quality analysis with security and complexity scoring, and stack selection guidance. Use when the user asks to "scaffold a new project", "create a Next.js app", "set up FastAPI with React", "analyze code quality", "audit my codebase", "what stack should I use", "generate project boilerplate", or mentions fullstack development, project setup, or tech stack comparison.
---

# Senior Fullstack

Fullstack development skill with project scaffolding and code quality analysis tools.

---

## Table of Contents

- [Trigger Phrases](#trigger-phrases)
- [Tools](#tools)
- [Workflows](#workflows)
- [Reference Guides](#reference-guides)

---

## Trigger Phrases

Use this skill when you hear:
- "scaffold a new project"
- "create a Next.js app"
- "set up FastAPI with React"
- "analyze code quality"
- "check for security issues in codebase"
- "what stack should I use"
- "set up a fullstack project"
- "generate project boilerplate"

---

## Tools

### Project Scaffolder

Generates fullstack project structures with boilerplate code.

**Supported Templates:**
- `nextjs` - Next.js 14+ with App Router, TypeScript, Tailwind CSS
- `fastapi-react` - FastAPI backend + React frontend + PostgreSQL
- `mern` - MongoDB, Express, React, Node.js with TypeScript
- `django-react` - Django REST Framework + React frontend

**Usage:**

```bash
# List available templates
python scripts/project_scaffolder.py --list-templates

# Create Next.js project
python scripts/project_scaffolder.py nextjs my-app

# Create FastAPI + React project
python scripts/project_scaffolder.py fastapi-react my-api

# Create MERN stack project
python scripts/project_scaffolder.py mern my-project

# Create Django + React project
python scripts/project_scaffolder.py django-react my-app

# Specify output directory
python scripts/project_scaffolder.py nextjs my-app --output ./projects

# JSON output
python scripts/project_scaffolder.py nextjs my-app --json
```

**Parameters:**

| Parameter | Description |
|-----------|-------------|
| `template` | Template name (nextjs, fastapi-react, mern, django-react) |
| `project_name` | Name for the new project directory |
| `--output, -o` | Output directory (default: current directory) |
| `--list-templates, -l` | List all available templates |
| `--json` | Output in JSON format |

**Output includes:**
- Project structure with all necessary files
- Package configurations (package.json, requirements.txt)
- TypeScript configuration
- Docker and docker-compose setup
- Environment file templates
- Next steps for running the project

---

### Code Quality Analyzer

Analyzes fullstack codebases for quality issues.

**Analysis Categories:**
- Security vulnerabilities (hardcoded secrets, injection risks)
- Code complexity metrics (cyclomatic complexity, nesting depth)
- Dependency health (outdated packages, known CVEs)
- Test coverage estimation
- Documentation quality

**Usage:**

```bash
# Analyze current directory
python scripts/code_quality_analyzer.py .

# Analyze specific project
python scripts/code_quality_analyzer.py /path/to/project

# Verbose output with detailed findings
python scripts/code_quality_analyzer.py . --verbose

# JSON output
python scripts/code_quality_analyzer.py . --json

# Save report to file
python scripts/code_quality_analyzer.py . --output report.json
```

**Parameters:**

| Parameter | Description |
|-----------|-------------|
| `project_path` | Path to project directory (default: current directory) |
| `--verbose, -v` | Show detailed findings |
| `--json` | Output in JSON format |
| `--output, -o` | Write report to file |

**Output includes:**
- Overall score (0-100) with letter grade
- Security issues by severity (critical, high, medium, low)
- High complexity files
- Vulnerable dependencies with CVE references
- Test coverage estimate
- Documentation completeness
- Prioritized recommendations

**Sample Output:**

```
============================================================
CODE QUALITY ANALYSIS REPORT
============================================================

Overall Score: 75/100 (Grade: C)
Files Analyzed: 45
Total Lines: 12,500

--- SECURITY ---
  Critical: 1
  High: 2
  Medium: 5

--- COMPLEXITY ---
  Average Complexity: 8.5
  High Complexity Files: 3

--- RECOMMENDATIONS ---
1. [P0] SECURITY
   Issue: Potential hardcoded secret detected
   Action: Remove or secure sensitive data at line 42
```

---

## Workflows

### Workflow 1: Start New Project

1. Choose appropriate stack based on requirements (see Stack Decision Matrix)
2. Scaffold project structure
3. Verify scaffold: confirm `package.json` (or `requirements.txt`) exists
4. Run initial quality check — address any P0 issues before proceeding
5. Set up development environment

```bash
# 1. Scaffold project
python scripts/project_scaffolder.py nextjs my-saas-app

# 2. Verify scaffold succeeded
ls my-saas-app/package.json

# 3. Navigate and install
cd my-saas-app
npm install

# 4. Configure environment
cp .env.example .env.local

# 5. Run quality check
python ../scripts/code_quality_analyzer.py .

# 6. Start development
npm run dev
```

### Workflow 2: Audit Existing Codebase

1. Run code quality analysis
2. Review security findings — fix all P0 (critical) issues immediately
3. Re-run analyzer to confirm P0 issues are resolved
4. Create tickets for P1/P2 issues

```bash
# 1. Full analysis
python scripts/code_quality_analyzer.py /path/to/project --verbose

# 2. Generate detailed report
python scripts/code_quality_analyzer.py /path/to/project --json --output audit.json

# 3. After fixing P0 issues, re-run to verify
python scripts/code_quality_analyzer.py /path/to/project --verbose
```

### Workflow 3: Stack Selection

Use the tech stack guide to evaluate options:

1. **SEO Required?** → Next.js with SSR
2. **API-heavy backend?** → Separate FastAPI or NestJS
3. **Real-time features?** → Add WebSocket layer
4. **Team expertise** → Match stack to team skills

See `references/tech_stack_guide.md` for detailed comparison.

---

## Reference Guides

### Architecture Patterns (`references/architecture_patterns.md`)

- Frontend component architecture (Atomic Design, Container/Presentational)
- Backend patterns (Clean Architecture, Repository Pattern)
- API design (REST conventions, GraphQL schema design)
- Database patterns (connection pooling, transactions, read replicas)
- Caching strategies (cache-aside, HTTP cache headers)
- Authentication architecture (JWT + refresh tokens, sessions)

### Development Workflows (`references/development_workflows.md`)

- Local development setup (Docker Compose, environment config)
- Git workflows (trunk-based, conventional commits)
- CI/CD pipelines (GitHub Actions examples)
- Testing strategies (unit, integration, E2E)
- Code review process (PR templates, checklists)
- Deployment strategies (blue-green, canary, feature flags)
- Monitoring and observability (logging, metrics, health checks)

### Tech Stack Guide (`references/tech_stack_guide.md`)

- Frontend frameworks comparison (Next.js, React+Vite, Vue)
- Backend frameworks (Express, Fastify, NestJS, FastAPI, Django)
- Database selection (PostgreSQL, MongoDB, Redis)
- ORMs (Prisma, Drizzle, SQLAlchemy)
- Authentication solutions (Auth.js, Clerk, custom JWT)
- Deployment platforms (Vercel, Railway, AWS)
- Stack recommendations by use case (MVP, SaaS, Enterprise)

---

## Quick Reference

### Stack Decision Matrix

| Requirement | Recommendation |
|-------------|---------------|
| SEO-critical site | Next.js with SSR |
| Internal dashboard | React + Vite |
| API-first backend | FastAPI or Fastify |
| Enterprise scale | NestJS + PostgreSQL |
| Rapid prototype | Next.js API routes |
| Document-heavy data | MongoDB |
| Complex queries | PostgreSQL |

### Common Issues

| Issue | Solution |
|-------|----------|
| N+1 queries | Use DataLoader or eager loading |
| Slow builds | Check bundle size, lazy load |
| Auth complexity | Use Auth.js or Clerk |
| Type errors | Enable strict mode in tsconfig |
| CORS issues | Configure middleware properly |