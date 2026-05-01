# CodeFlow - BMAD Method Implementation

## Welcome to Your AI-Enhanced Project! 🚀

This project uses the **BMAD Method (Breakthrough Method for Agile AI-Driven Development)** to structure all work, enable powerful AI collaboration, and maintain clear context.

---

## 🎯 Project Overview

**CodeFlow** is a multi-language code visualization and analysis system that transforms complex codebases into interactive, navigable call graphs with intelligent rendering strategies.

**Your Stack**:
- 🐍 **Backend**: Python + FastAPI
- 🗄️ **Database**: Neo4j (Graph Database)
- 🎨 **Frontend**: Vue.js + React Flow
- 🔧 **Languages**: Python, JavaScript, TypeScript, Java, Go, Rust (via Tree-sitter)

**End Goal**: Developers can upload large codebases and explore them through 3 levels:
1. **Tier-1**: Module view (top-level folders)
2. **Tier-2**: File view (files in modules)
3. **Tier-3**: Function view (functions in files)

---

## 📁 BMAD Project Structure

```
.
├── .instructions.md          ← MAIN: Complete system overview
├── AGENTS.md                 ← Specialized agent roles
├── CONTEXT.md                ← Technical architecture & schema
├── PHASES.md                 ← Implementation roadmap
├── .prompt.md                ← Custom prompts & guidelines
├── SKILLS.md                 ← Reusable skill modules
├── skills/                   ← Skill implementations
│   ├── tree-sitter-parsing/
│   ├── neo4j-queries/
│   ├── god-file-chunking/
│   ├── upload-security/
│   ├── react-flow-mapping/
│   ├── performance-optimization/
│   └── test-strategy/
├── Backend/                  ← Your backend code
├── Frontend/                 ← Your frontend code
└── .bmad/                    ← Configuration directory
```

---

## 🤖 Key BMAD Files & Their Purpose

### `.instructions.md`
**The Master Document** - Contains:
- Complete system architecture (3-tier hierarchy)
- Component descriptions
- Data flow diagrams
- Key constraints & business rules
- Implementation phases
- Success metrics

👉 **Read this first** when starting work.

---

### `AGENTS.md`
**Agent Role Definitions** - Who does what:
- **@pm** - Project management, timelines, priorities
- **@architect** - System design, optimization strategy
- **@backend-dev** - Backend implementation
- **@frontend-dev** - Frontend implementation
- **@qa-engineer** - Testing strategy, quality
- **@devops** - Deployment, infrastructure
- **@security** - Security review, vulnerabilities
- **@skills-engineer** - Skill creation and maintenance

👉 **Use this to invoke the right agent for your task.**

Example:
```
@architect: Design the Neo4j schema for Tier-1 queries
@backend-dev: Implement the folder walker with security
@frontend-dev: Build the Tier-1 visualization with React Flow
```

---

### `CONTEXT.md`
**Technical Reference** - Contains:
- Neo4j node and relationship types
- Database schema with examples
- API contract (endpoint specifications)
- Tree-sitter parsing configuration
- God file chunking strategies
- Render strategy decision logic
- Performance requirements
- Caching strategy
- Security checklist

👉 **Reference this for technical decisions.**

---

### `PHASES.md`
**Implementation Roadmap** - Contains:
- 5 implementation phases (10 weeks total)
- Task breakdown per phase
- Dependencies between phases
- Success criteria and gates
- Resource allocation
- Risk assessment
- Weekly check-in structure

👉 **Use this to plan and track progress.**

---

### `.prompt.md`
**Quick Prompts & Guidelines** - Contains:
- Quick prompts by role
- How to ask questions effectively
- Information to provide
- Skill invocation patterns
- Progress tracking
- Debugging tips
- Best practices

👉 **Reference when asking AI for help.**

---

### `SKILLS.md`
**Reusable Skill Modules** - Contains:
- 8 specialized skills with detailed documentation
- When to use each skill
- Input/output contracts
- Common patterns and examples
- Best practices
- Files in each skill

👉 **Invoke skills when tackling specialized work.**

**Skills available**:
1. `tree-sitter-parsing` - Multi-language code analysis
2. `neo4j-queries` - Graph database optimization
3. `god-file-chunking` - Intelligent file splitting
4. `upload-security` - Security validation
5. `react-flow-mapping` - UI visualization
6. `performance-optimization` - Speed tuning
7. `test-strategy` - QA planning
8. (More can be added)

---

## 🚀 Getting Started

### Step 1: Understand the Project
1. Read [.instructions.md](.instructions.md) (15 min)
2. Skim [AGENTS.md](AGENTS.md) (5 min)
3. Review [PHASES.md](PHASES.md) (10 min)

### Step 2: Start Work
Pick your role and get started:

**If you're the Project Manager**:
```
@pm: Help me plan Phase 1 implementation.
What should be our priorities this week?
```

**If you're the Architect**:
```
@architect: Review our Neo4j schema design.
Is it optimized for all 3 tiers?
What indexes should we create?
```

**If you're a Backend Developer**:
```
@backend-dev: Implement the folder walker with security.
Use the upload-security skill for validation.
Include zip-slip prevention and file filtering.
```

**If you're a Frontend Developer**:
```
@frontend-dev: Build the Tier-1 module view with React Flow.
Use the react-flow-mapping skill.
Target: <1 second render for <100 modules.
```

### Step 3: Ask for Help
When you need guidance, reference the documentation:

```
@pm: I just finished Phase 1. What's next?
Can we parallelize any Phase 2 tasks?
```

```
@architect: We need to optimize the Tier-2 query.
Current time: 3 seconds
Target: <1 second
Use the performance-optimization skill to analyze.
```

---

## 📊 Understanding Render Strategies

The frontend renders graphs differently based on size:

| Nodes | Strategy | Behavior |
|-------|----------|----------|
| < 100 | **Show All** | Display everything clearly |
| 100-500 | **Make Group** | Group less-important nodes, show highlights |
| > 500 | **Search Only** | Show top 100, search for others |

This is calculated automatically and sent in the API response.

---

## 🔄 Typical Workflow with BMAD

### Scenario: Implement Tier-2 File Query

**Step 1: Plan** (with @pm)
```
@pm: Planning Tier-2 implementation.
Scope: Neo4j query for file-level call graphs.
Dependencies: Tier-1 working, Neo4j schema complete.
Timeline estimate?
```

**Step 2: Design** (with @architect)
```
@architect: Design Tier-2 query structure.
Requirements:
- Query all files in a module
- Calculate inter-file calls  
- Support all 6 languages
- Response: <1 second
Include: index recommendations, caching hints.
```

**Step 3: Implement** (with @backend-dev)
```
@backend-dev: Implement Tier-2 endpoint using neo4j-queries skill.
Design from architect: [paste response]
Include: error handling, response formatting
```

**Step 4: Test** (with @qa-engineer)
```
@qa-engineer: Design Tier-2 tests using test-strategy skill.
Coverage: 90%+
Include: edge cases (single file, 50+ files, circular calls)
```

**Step 5: Optimize** (with @architect)
```
@architect: Performance test Tier-2.
Current: 1.5 seconds
Target: <1 second
Use performance-optimization skill.
```

**Step 6: Complete**
```
@pm: Tier-2 complete! Tests 100% passing.
Ready to move to frontend implementation.
```

---

## 💡 BMAD Principles

### 1. **Clarity Through Structure**
- Each file has a clear purpose
- Documentation is comprehensive but organized
- No surprises, no ambiguity

### 2. **AI-Enhanced Collaboration**
- Invoke specialized agents for specific tasks
- Agents have full context from BMAD files
- Reduces cognitive load, accelerates work

### 3. **Reusable Knowledge**
- Skills capture domain expertise
- Skills are invoked by name with clear contracts
- Skills can be shared across projects

### 4. **Traceability**
- Every decision is documented (CONTEXT.md, PHASES.md)
- Every role has clear responsibilities (AGENTS.md)
- Every task has success criteria (PHASES.md gates)

### 5. **Scale-Adaptive**
- Project grows from Phase 1 → Phase 5
- Each phase builds on previous
- Clear dependencies prevent confusion

---

## 🎯 Next Steps

1. **Read** [.instructions.md](.instructions.md) - Full system overview
2. **Choose your role** - PM, Architect, Backend Dev, Frontend Dev, etc.
3. **Start Phase 1** - Begin implementation
4. **Use agents & skills** - @agent: Use skill-id skill to task
5. **Track progress** - Reference [PHASES.md](PHASES.md) for milestones
6. **Ask for help** - Use [.prompt.md](.prompt.md) patterns

---

## 📞 Quick Reference

### Asking for Help by Role

| Need | Ask | Skill |
|------|-----|-------|
| Parse code | @backend-dev | tree-sitter-parsing |
| Optimize queries | @architect | neo4j-queries |
| Chunk God files | @architect | god-file-chunking |
| Validate uploads | @security | upload-security |
| Build UI | @frontend-dev | react-flow-mapping |
| Speed tuning | @architect | performance-optimization |
| Design tests | @qa-engineer | test-strategy |

### Key Documents

| Document | Read When | Time |
|----------|-----------|------|
| `.instructions.md` | First thing | 15 min |
| `AGENTS.md` | Starting work | 5 min |
| `CONTEXT.md` | Technical decisions | 20 min |
| `PHASES.md` | Planning/tracking | 10 min |
| `.prompt.md` | Asking AI help | 5 min |
| `SKILLS.md` | Complex tasks | 15 min |

---

## ✅ Success Criteria

Your project is successful when:

✅ **Phase 1**: Secure upload + folder walker + basic parser working  
✅ **Phase 2**: God file detection + chunking algorithm complete  
✅ **Phase 3**: All 6 language parsers working accurately  
✅ **Phase 4**: All API endpoints <5 sec response, render strategies calculated  
✅ **Phase 5**: Full UI working, all tiers navigable, <500ms render time  

**Overall**: 95%+ function detection accuracy, <5 sec to parse 100k LOC

---

## 🤝 Team Structure

This BMAD project is designed for multiple specialists working together:

- **Architect** (1): System design, optimization
- **Backend Developers** (1-2): API, database, parsing
- **Frontend Developers** (1): UI, visualization
- **QA Engineer** (1): Testing, validation
- **DevOps** (1): Deployment, monitoring
- **Project Manager** (1): Planning, coordination
- **Security Engineer** (1): Validation, hardening

**Each role has clear responsibilities** defined in [AGENTS.md](AGENTS.md).

---

## 📚 Additional Resources

- Tree-sitter Docs: https://tree-sitter.github.io/
- Neo4j Docs: https://neo4j.com/docs/
- React Flow: https://reactflow.dev/
- FastAPI: https://fastapi.tiangolo.com/
- Vue.js: https://vuejs.org/
- BMAD Method: https://docs.bmad-method.org/

---

## 🎓 Learning Path

**If you're new to this project**:

1. Read `.instructions.md` (understand the what)
2. Read `CONTEXT.md` (understand the how)
3. Pick a phase in `PHASES.md` (understand the plan)
4. Choose your role in `AGENTS.md` (understand your part)
5. Reference `.prompt.md` when asking for help
6. Invoke `SKILLS.md` for specialized work

**Questions?** Ask your PM or use the prompts in `.prompt.md`!

---

## 📝 Maintenance

### Updating Documentation
1. **Change in architecture?** → Update `CONTEXT.md`
2. **Change in timeline?** → Update `PHASES.md`
3. **New agent needed?** → Update `AGENTS.md`
4. **New skill created?** → Update `SKILLS.md`
5. **New prompt pattern?** → Update `.prompt.md`
6. **System overview changed?** → Update `.instructions.md`

### Tracking Progress
Use `PHASES.md` milestones to track work. Each phase has:
- Clear deliverables
- Success criteria
- Approval gates
- Estimated timeline

---

## 🏁 Ready to Start?

Your next action depends on your role:

**Project Manager**: `@pm: Help me plan the full 10-week timeline for CodeFlow.`

**Architect**: `@architect: Review the system architecture in .instructions.md. Any improvements needed?`

**Developer**: `@backend-dev: Start Phase 1 implementation. What's the first task?`

**QA/Testing**: `@qa-engineer: Design the testing strategy for CodeFlow using the test-strategy skill.`

---

**Happy coding! 🚀**

*This project uses the BMAD Method for Agile AI-Driven Development.*  
*Learn more: https://docs.bmad-method.org/*
