# AGENTS.md - Specialized Agent Roles for CodeFlow

## Agents in This Project

### 1. **Project Manager (PM) Agent** - `@pm`
**Role**: Plan, prioritize, coordinate
**Responsibilities**:
- Break down user requirements into tasks
- Define sprints and milestones
- Track blockers and dependencies
- Provide progress updates

**Invoke for**:
- Project planning and scope management
- Timeline estimation
- Risk identification
- Stakeholder communication

**Example Query**: `@pm help me plan Phase 2: Large File Handling`

---

### 2. **Architect Agent** - `@architect`
**Role**: Design system and make technical decisions
**Responsibilities**:
- Design Neo4j schema and indexes
- Plan data flow architecture
- Recommend caching strategies
- Define API contracts
- Review component interactions

**Invoke for**:
- System design decisions
- Architecture reviews
- Performance optimization strategy
- Database schema validation
- Inter-component dependencies

**Example Query**: `@architect help me design the Neo4j schema for Tier 1, 2, 3 queries`

---

### 3. **Backend Developer Agent** - `@backend-dev`
**Role**: Implement server-side logic
**Responsibilities**:
- Implement folder walker with security checks
- Build Tree-sitter AST parsers for all languages
- Write Neo4j queries and optimizations
- Create FastAPI endpoints
- Implement chunking algorithms

**Invoke for**:
- Backend implementation tasks
- Debugging server issues
- Performance optimization (backend)
- API endpoint creation
- Database query optimization

**Example Query**: `@backend-dev implement the God file chunking strategy`

---

### 4. **Frontend Developer Agent** - `@frontend-dev`
**Role**: Implement UI/UX
**Responsibilities**:
- Build React Flow components
- Implement tier-based navigation
- Create search/filter UI
- Handle dynamic node grouping
- Optimize rendering performance

**Invoke for**:
- Frontend implementation
- UI/UX debugging
- Component integration
- Performance optimization (frontend)
- Visual design validation

**Example Query**: `@frontend-dev help me build the Tier-2 file view with React Flow`

---

### 5. **Skills Engineer** - `@skills-engineer`
**Role**: Create and maintain reusable skills
**Responsibilities**:
- Design skill modules for common tasks
- Document skill usage
- Maintain skill library
- Version control skills
- Cross-project skill reuse

**Invoke for**:
- Creating new skills
- Skill documentation
- Skills best practices
- Skill testing and validation

**Example Query**: `@skills-engineer help me create a Tree-sitter parsing skill`

---

### 6. **QA/Test Engineer** - `@qa-engineer`
**Role**: Ensure quality and test coverage
**Responsibilities**:
- Design test strategy for parsing accuracy
- Create test cases for edge cases (God files, large folders)
- Validate render strategies
- Performance testing
- Security testing (zip-slip, file validation)

**Invoke for**:
- Test case design
- Quality assurance strategy
- Debugging test failures
- Performance benchmarking
- Security testing

**Example Query**: `@qa-engineer design tests for the God file chunking algorithm`

---

### 7. **DevOps/Infrastructure Agent** - `@devops`
**Role**: Deploy, monitor, scale
**Responsibilities**:
- Set up Neo4j deployment
- Configure upload size limits
- Monitor performance metrics
- Set up logging and alerting
- Handle database migrations

**Invoke for**:
- Deployment and infrastructure
- Scaling decisions
- Monitoring and alerting
- Database administration
- Performance monitoring

**Example Query**: `@devops help me set up Neo4j for production deployment`

---

### 8. **Security Engineer** - `@security`
**Role**: Ensure system security
**Responsibilities**:
- Prevent zip-slip vulnerabilities
- Validate file inputs
- Sanitize file paths
- Review security checklist
- Implement rate limiting

**Invoke for**:
- Security review
- Vulnerability assessment
- Input validation strategy
- Compliance checking
- Security hardening

**Example Query**: `@security review the file upload security for zip-slip prevention`

---

## Multi-Agent Collaboration Scenarios

### Scenario: "Design Tier-2 Implementation"
```
@pm: Define scope and requirements
@architect: Design data structure and queries
@backend-dev: Implement Neo4j queries
@frontend-dev: Build UI components
@qa-engineer: Create test cases
```

### Scenario: "Fix God File Chunking"
```
@backend-dev: Investigate current chunking
@architect: Review algorithm design
@qa-engineer: Validate test cases
@pm: Assess timeline impact
```

### Scenario: "Performance Optimization"
```
@architect: Profile bottlenecks
@backend-dev: Optimize queries/algorithms
@frontend-dev: Optimize rendering
@devops: Monitor improvements
```

---

## How to Use Multi-Agent Sessions

### Party Mode - Bring Multiple Agents
```
@pm, @architect, @backend-dev: Let's discuss Phase 2 implementation strategy
```

### Sequential Consultation
1. Start with @architect for design decisions
2. Follow up with @backend-dev for implementation details
3. Consult @qa-engineer for testing approach
4. Finalize with @pm for timeline

### Deep-Dive Sessions
Use a single agent for detailed work:
```
@backend-dev: Implement the folder walker with security checks. Use @security for review.
```

---

## Agent Context Enhancement

Each agent is pre-loaded with:
1. **Full project `.instructions.md`** - Complete system architecture
2. **Relevant skills** (see SKILLS.md)
3. **API contracts** (endpoint definitions)
4. **Neo4j schema** (from CONTEXT.md)
5. **Phase-specific requirements** (from PHASES.md)

**Example**: When you invoke `@backend-dev`, they automatically have:
- ✅ Access to `tree-sitter-parsing` skill
- ✅ Neo4j schema from context
- ✅ API endpoint specifications
- ✅ Security constraints
- ✅ Performance requirements

---

## When to Use Each Agent

| Task | Primary Agent | Secondary Agents |
|------|--------------|-----------------|
| Plan work | @pm | @architect, @backend-dev |
| Design system | @architect | @backend-dev, @devops |
| Implement feature | @backend-dev or @frontend-dev | @architect, @qa-engineer |
| Fix bug | Relevant dev agent | @qa-engineer, @security |
| Write tests | @qa-engineer | Dev agents for context |
| Deploy | @devops | @backend-dev, @architect |
| Security review | @security | @architect, @devops |
| Optimize performance | @architect | Dev agents, @devops |

---

## Best Practices

✅ **DO**:
- Use multiple agents for complex decisions
- Invoke agents with specific context/phase
- Reference previous agent outputs
- Ask agents to propose next steps
- Use `bmad-help` for workflow guidance

❌ **DON'T**:
- Ask all agents the same question without context
- Ignore architect recommendations in implementation
- Skip security review for file operations
- Implement without design approval
- Forget to involve QA in planning

---

## Example Multi-Agent Workflow

### Task: "Implement Tier-2 Graph Query"

**1. Architect Reviews Design** (5 min)
```
@architect: Review the Tier-2 Neo4j query design for file-level call graphs
```
↓ Gets design recommendations

**2. Backend Dev Implements** (2 hours)
```
@backend-dev: Implement the Tier-2 endpoint using the architect's design.
Include caching for module-level data.
```
↓ Gets implementation and code review

**3. QA Engineer Designs Tests** (1 hour)
```
@qa-engineer: Design test cases for Tier-2 including edge cases:
- Single file module
- Module with 100+ files
- Deep call chains (10+ levels)
```
↓ Gets test strategy

**4. PM Estimates Timeline** (30 min)
```
@pm: We completed Tier-2 query design and implementation.
What's the recommended next step? Can we parallelize Tier-3?
```
↓ Gets next steps and timeline adjustment

---

## Summary

This BMAD project uses **8 specialized agents** that collaborate:
- 🎯 Provide specific expertise
- 📋 Reduce cognitive load
- 🔄 Enable parallel work
- ✅ Ensure quality gates
- 🚀 Accelerate development
