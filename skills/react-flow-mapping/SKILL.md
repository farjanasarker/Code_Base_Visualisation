# React Flow Visualization Mapping Skill

## Overview
Expertise in converting graph data into React Flow node/edge format with intelligent layout and optimization for different render strategies.

## When to Use This Skill
- Converting Neo4j graph data to React Flow format
- Positioning nodes hierarchically
- Applying render strategies (show_all, make_group, search_only)
- Optimizing rendering for large graphs
- Creating interactive call chain visualizations
- Grouping and collapsing nodes intelligently

## Render Strategies

### Strategy 1: Show All (< 100 nodes)
**When**: Small graphs, all nodes visible without clutter  
**Approach**:
- Display all nodes individually
- Show all edges
- Use clear hierarchy positioning
- Apply consistent styling

```javascript
const nodes = graphData.nodes.map(node => ({
  id: node.id,
  data: { label: node.label, ...node.details },
  position: layoutEngine.position(node),
  type: 'default'
}))

const edges = graphData.edges.map(edge => ({
  id: edge.id,
  source: edge.source,
  target: edge.target,
  label: edge.label
}))
```

### Strategy 2: Make Group (100-500 nodes)
**When**: Medium graphs, need selective emphasis  
**Approach**:
- Group low-importance nodes
- Highlight critical paths (high fan-in/fan-out)
- Use collapsible groups
- Show relationships between groups

```javascript
// Calculate importance for each node
const importance = nodes.map(node => ({
  id: node.id,
  score: (node.fan_in * 0.3 + node.fan_out * 0.3 + node.complexity * 0.4)
}))

// Group bottom 50% by category
const grouped = groupByImportance(nodes, 0.5)

// Create group nodes
const groupNodes = grouped.map(group => ({
  id: `group-${group.id}`,
  data: { label: group.label },
  type: 'group',
  style: { width: 200, height: 200 }
}))

// Move low-importance nodes into groups
const finalNodes = [...importantNodes, ...groupNodes]
```

### Strategy 3: Search Only (> 500 nodes)
**When**: Large graphs, need focused exploration  
**Approach**:
- Show top 100 by importance
- Provide search UI
- Load on-demand when searching
- Filter by category/type

```javascript
// Sort by importance
const sorted = nodes.sort((a, b) => 
  (b.fan_in * 0.3 + b.fan_out * 0.3 + b.complexity * 0.4) -
  (a.fan_in * 0.3 + a.fan_out * 0.3 + a.complexity * 0.4)
)

// Show only top 100
const visibleNodes = sorted.slice(0, 100)

// Store rest in search index
const hiddenNodes = sorted.slice(100)
```

## Tier-Specific Layouts

### Tier-1: Module Hierarchy
```javascript
// Layout algorithm: Hierarchical (top-down)
// Module positioning by call frequency
// Edge thickness by call count
const tier1Layout = {
  algorithm: 'dagre',
  rankdir: 'TB',
  ranksep: 100
}
```

### Tier-2: File Level
```javascript
// Layout algorithm: Force-directed
// Group files by complexity
// Edge styling by call frequency
const tier2Layout = {
  algorithm: 'force',
  attraction: 0.5,
  repulsion: 0.5
}
```

### Tier-3: Function Calls
```javascript
// Layout algorithm: Hierarchical (left-right)
// Show call chains
// Highlight entry points
const tier3Layout = {
  algorithm: 'dagre',
  rankdir: 'LR',
  ranksep: 150
}
```

## Data Transformation

### Input Format (from Backend)
```json
{
  "nodes": [
    {
      "id": "fn-1",
      "name": "parse_ast",
      "type": "function",
      "file": "parser.py",
      "complexity": 7,
      "fan_in": 3,
      "fan_out": 5,
      "line": 45
    }
  ],
  "edges": [
    {
      "source": "fn-1",
      "target": "fn-2",
      "frequency": 2
    }
  ]
}
```

### Output Format (React Flow)
```json
{
  "nodes": [
    {
      "id": "fn-1",
      "data": {
        "label": "parse_ast()",
        "complexity": 7,
        "fan_in": 3,
        "fan_out": 5
      },
      "position": { "x": 100, "y": 200 },
      "style": {
        "background": "#ff6b6b",
        "border": "2px solid #c92a2a"
      },
      "type": "default"
    }
  ],
  "edges": [
    {
      "id": "e1",
      "source": "fn-1",
      "target": "fn-2",
      "label": "2",
      "animated": true,
      "style": { "stroke": "#666" }
    }
  ]
}
```

## Styling & Color Coding

### By Node Type
```javascript
const nodeStyles = {
  module: { background: '#4c6ef5', border: '3px solid #364fc7' },
  file: { background: '#20c997', border: '2px solid #0f6448' },
  function: { background: '#ffa94d', border: '2px solid #d9480f' },
  group: { background: '#e9ecef', border: '2px dashed #495057' }
}
```

### By Importance
```javascript
const importanceColors = {
  high: '#ff6b6b',      // Red - critical
  medium: '#ffa94d',    // Orange - important
  low: '#a8e6cf'        // Green - support
}
```

### By Complexity
```javascript
const complexityColors = node =>
  node.complexity < 5 ? '#51cf66' :    // Green - simple
  node.complexity < 10 ? '#ffd43b' :   // Yellow - moderate
  '#ff6b6b'                             // Red - complex
```

## Animation & Interaction

### Hover Effects
```javascript
const handleNodeHover = (id) => {
  // Highlight connected edges
  // Show metadata tooltip
  // Enlarge node
}
```

### Click Navigation (Tier Changes)
```javascript
const handleNodeClick = (id, tier) => {
  if (tier === 1) {
    // Load Tier-2 for this module
    fetchTier2(id)
  } else if (tier === 2) {
    // Load Tier-3 for this file
    fetchTier3(id)
  }
}
```

### Edge Highlighting
```javascript
// Highlight all paths from selected node
const getConnectedNodes = (nodeId, depth = 1) => {
  // BFS to find connected nodes
  // Return with highlight styling
}
```

## Performance Optimization

### Virtual Scrolling
```javascript
// For search results with hundreds of items
<VirtualList
  height={500}
  itemCount={hiddenNodes.length}
  itemSize={40}
  renderItem={renderSearchResult}
/>
```

### Lazy Loading
```javascript
// Load edges on demand
const [edges, setEdges] = useState([])
const handleNodesChange = (newNodes) => {
  if (newNodes.length < 50) {
    // Load all edges
  } else {
    // Load edges for visible nodes only
  }
}
```

### Debounced Layout
```javascript
// Recalculate layout only after 500ms of no changes
const debouncedLayout = useMemo(
  () => debounce((nodes) => calculateLayout(nodes), 500),
  []
)
```

## Files in This Skill
- `SKILL.md` - This documentation
- `templates/` - React Flow component templates
- `examples/` - Real usage examples
- `styling/` - Color schemes and themes

## Reference
- React Flow: https://reactflow.dev/
- Dagre: https://github.com/dagrejs/dagre
- D3 Force: https://github.com/d3/d3-force
