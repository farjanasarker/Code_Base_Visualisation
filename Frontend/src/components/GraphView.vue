<template>
  <div class="graph-container">

    <!-- ── Sidebar ─────────────────────────────────── -->
    <aside class="sidebar">
      <!-- Brand -->
      <div class="sidebar-brand">
        <span class="brand-icon">⬡</span>
        <div>
          <div class="brand-name">CodeLens</div>
          <div class="brand-sub">Codebase Visualizer</div>
        </div>
      </div>

      <!-- Back navigation -->
      <div v-if="navStack.length > 0" class="sidebar-section">
        <button class="back-btn" @click="goBack">← Back</button>
        <div class="breadcrumb">
          <span v-for="(crumb, i) in navStack" :key="i" class="crumb">
            <span v-if="i > 0" class="crumb-sep">›</span>
            {{ crumb.label }}
          </span>
          <span class="crumb-sep">›</span>
          <span class="crumb crumb-current">{{ currentLabel }}</span>
        </div>
      </div>

      <!-- Upload zone -->
      <div class="sidebar-section">
        <div class="section-title">Upload Source</div>

        <label for="file-input" class="upload-zone" :class="{ disabled: uploading }">
          <div class="upload-zone-icon">{{ uploading ? '⏳' : '📦' }}</div>
          <div class="upload-zone-text">
            {{ uploading ? 'Uploading…' : 'Drop file or click to browse' }}
          </div>
          <div class="upload-zone-hint">.py .js .ts .java .go .rs .zip</div>
        </label>
        <input
          id="file-input"
          type="file"
          accept=".py,.js,.jsx,.ts,.tsx,.java,.go,.rs,.cpp,.c,.cs,.zip"
          @change="handleFileUpload"
          :disabled="uploading"
          class="file-input"
        />

        <label for="folder-input" class="upload-btn-folder" :class="{ disabled: uploading }">
          📁 Upload Folder
        </label>
        <input
          id="folder-input"
          type="file"
          multiple
          webkitdirectory
          directory
          @change="handleFolderUpload"
          :disabled="uploading"
          class="file-input"
        />
      </div>

      <!-- Status -->
      <div v-if="uploadedFile || uploadError || uploadSuccess" class="sidebar-section">
        <div class="section-title">Status</div>
        <div v-if="uploadedFile" class="status-file">
          <span class="status-dot ok"></span>
          <span class="status-filename" :title="uploadedFile">{{ uploadedFile }}</span>
        </div>
        <div v-if="uploadSuccess" class="status-msg ok">
          Graph loaded — click nodes to drill down
        </div>
        <div v-if="nodeCount > 0" class="status-count">
          <span class="count-num">{{ nodeCount }}</span> nodes visible
        </div>
        <div v-if="uploadError" class="status-msg err">
          {{ uploadError }}
        </div>
      </div>

      <!-- Legend -->
      <div class="sidebar-section">
        <div class="section-title">Legend</div>
        <div class="legend">
          <div class="legend-item">
            <span class="legend-swatch module"></span>
            <span class="legend-icon">⬡</span>
            <span>Module / Package</span>
          </div>
          <div class="legend-item">
            <span class="legend-swatch file"></span>
            <span class="legend-icon">◫</span>
            <span>Source File</span>
          </div>
          <div class="legend-item">
            <span class="legend-swatch function"></span>
            <span class="legend-icon">ƒ</span>
            <span>Function</span>
          </div>
          <div class="legend-item">
            <span class="legend-swatch chunk"></span>
            <span class="legend-icon">⚡</span>
            <span>Chunk (large file)</span>
          </div>
        </div>
      </div>

      <!-- Tips -->
      <div class="sidebar-section tips">
        <div class="section-title">How to use</div>
        <ol class="tips-list">
          <li>Upload a file, ZIP, or folder</li>
          <li>Click a <strong>Module</strong> to see files</li>
          <li>Click a <strong>File</strong> to see functions</li>
          <li>Click a <strong>Function</strong> to expand callers &amp; callees</li>
          <li>Hover any node to highlight its edges</li>
        </ol>
      </div>
    </aside>

    <!-- ── Graph canvas ─────────────────────────────── -->
    <div class="graph-section">
      <VueFlow
        v-if="nodes.length > 0"
        :nodes="nodes"
        :edges="edges"
        :node-types="nodeTypes"
        :edge-types="edgeTypes"
        :default-edge-options="defaultEdgeOptions"
        @node-click="onNodeClick"
        @node-mouseenter="onNodeHover"
        @node-mouseleave="onNodeUnhover"
        @nodes-initialized="() => fitView({ padding: 0.45, duration: 400, maxZoom: 0.95 })"
        fit-view-on-init
        class="vue-flow"
      >
        <Controls position="bottom-right" />
        <MiniMap
          position="bottom-left"
          :node-color="(n) => n.data?.nodeType === 'module' ? '#3b82f6' : n.data?.nodeType === 'file' ? '#f59e0b' : n.data?.nodeType === 'chunk' ? '#8b5cf6' : '#6366f1'"
          :minimap-style="{ background: '#f1f5f9', border: '1px solid #e2e8f0', borderRadius: '8px' }"
        />
      </VueFlow>
      <div v-else class="empty-state">
        <div class="empty-icon">⬡</div>
        <h2 class="empty-title">No graph loaded</h2>
        <p class="empty-sub">Upload a source file, ZIP archive, or folder<br>using the panel on the left to get started.</p>
        <div class="empty-badges">
          <span>.py</span><span>.js</span><span>.ts</span><span>.java</span><span>.go</span><span>.zip</span>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { markRaw, nextTick, ref, inject, computed } from "vue";
import { MarkerType, Position, useVueFlow, VueFlow } from "@vue-flow/core";
import { MiniMap } from "@vue-flow/minimap";
import { Controls } from "@vue-flow/controls";
import "@vue-flow/minimap/dist/style.css";
import "@vue-flow/controls/dist/style.css";
import FunctionNode from "./FunctionNode.vue";
import BottomBackEdge from "./BottomBackEdge.vue";

// Inject session manager
const sessionManager = inject('sessionManager');

const nodes = ref([]);
const edges = ref([]);
const uploading = ref(false);
const uploadedFile = ref(null);
const uploadError = ref(null);
const uploadSuccess = ref(false);
const expandedNodes = ref(new Set());
const nodeLevelMap = ref(new Map());
const discoveredFunctions = ref([]);
const selectedRoot = ref("");
const functionLayoutMode = ref(false);
const navStack = ref([]);   // [{label, nodes, edges, expandedNodes, nodeLevelMap}]
const currentLabel = ref('');
const { fitView } = useVueFlow();
const nodeTypes = {
  functionNode: markRaw(FunctionNode)
};
const edgeTypes = {
  backcall: markRaw(BottomBackEdge)
};

const nodeCount = computed(() => nodes.value.length);

const TREE_DEPTH_GAP = 200;         // vertical gap between parent and children rows
const TREE_SIBLING_GAP = 320;       // horizontal gap between sibling nodes
const FUNCTION_TREE_DEPTH_GAP = 200;
const FUNCTION_TREE_SIBLING_GAP = 320;
const MAX_CHILDREN_PER_COLUMN = 2;

// Edge color per source node type
const EDGE_COLORS = {
  module:   '#3b82f6',
  file:     '#f59e0b',
  function: '#6366f1',
  chunk:    '#8b5cf6',
  default:  '#6366f1'
};

const defaultEdgeOptions = {
  markerEnd: {
    type: MarkerType.ArrowClosed,
    width: 18,
    height: 18,
    color: EDGE_COLORS.default
  },
  style: {
    stroke: EDGE_COLORS.default,
    strokeWidth: 2,
    strokeLinecap: 'round',
    strokeLinejoin: 'round'
  },
  animated: false
};

const rootNodeStyle = {
  width: "72px",
  height: "72px",
  borderRadius: "50%",
  background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
  border: "3px solid #667eea",
  color: "#fff",
  fontWeight: "700",
  fontSize: "12px",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  textAlign: "center",
  boxShadow: "0 10px 20px rgba(102, 126, 234, 0.35)",
  padding: "0"
};

const functionNodeStyle = {
  width: "66px",
  height: "66px",
  borderRadius: "50%",
  background: "#3f8f7a",
  border: "2px solid #2f6f61",
  color: "#fff",
  fontWeight: "600",
  fontSize: "11px",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  textAlign: "center",
  boxShadow: "0 8px 18px rgba(63, 143, 122, 0.3)",
  padding: "0"
};

const formatNodeLabel = (name) => {
  if (!name) {
    return "";
  }

  if (name.length <= 12) {
    return name;
  }

  const parts = name.split("_").filter(Boolean);
  if (parts.length >= 2) {
    const preview = parts.slice(0, 2).join("_");
    return preview.length <= 12 ? preview : `${preview.slice(0, 9)}...`;
  }

  return `${name.slice(0, 8)}...`;
};

const getDisplayLabel = (fullLabel, nodeType = 'module') => {
  if (!fullLabel) {
    return '';
  }

  if (nodeType === 'file') {
    const normalized = fullLabel.replace(/\\/g, '/');
    const baseName = normalized.split('/').filter(Boolean).pop() || normalized;
    return formatNodeLabel(baseName);
  }

  return formatNodeLabel(fullLabel);
};

const createNode = (id, position, opts = {}) => {
  const { label, fullLabel, nodeType = 'module', callCount = 0, isRoot = false, language } = opts;
  return {
    id,
    type: 'functionNode',
    data: {
      label: label || getDisplayLabel(fullLabel || id, nodeType),
      fullLabel: fullLabel || id,
      callCount,
      nodeType,
      language,
      isRoot
    },
    position,
    sourcePosition: Position.Bottom,
    targetPosition: Position.Top,
    style: {
      width: '170px',
      height: '58px'
    },
    draggable: false
  };
};

const getChildPosition = (parentNode, childIndex, totalChildren) => {
  const centerOffset = (totalChildren - 1) / 2;
  return {
    x: parentNode.position.x + (childIndex - centerOffset) * TREE_SIBLING_GAP,
    y: parentNode.position.y + TREE_DEPTH_GAP
  };
};

const getRootChildPosition = (parentNode, childIndex, totalChildren) => {
  const centerOffset = (totalChildren - 1) / 2;
  return {
    x: parentNode.position.x + (childIndex - centerOffset) * TREE_SIBLING_GAP,
    y: parentNode.position.y + TREE_DEPTH_GAP
  };
};

const getFunctionChildPosition = (parentNode, childIndex, totalChildren, direction = "right") => {
  // direction "right" = callees → go DOWN; "left" = callers → go UP
  const centerOffset = (totalChildren - 1) / 2;
  const xOffset = (childIndex - centerOffset) * FUNCTION_TREE_SIBLING_GAP;
  const yDir = direction === "left" ? -FUNCTION_TREE_DEPTH_GAP : FUNCTION_TREE_DEPTH_GAP;

  return {
    x: parentNode.position.x + xOffset,
    y: parentNode.position.y + yDir
  };
};

const toVueFlowEdges = (rawEdges, knownNodes, opts = {}) => {
  const nodePositionMap = new Map(knownNodes.map((n) => [n.id, n.position]));
  const forceStraight = !!opts.forceStraight;

  return rawEdges.map((e) => {
    const sourcePos = nodePositionMap.get(e.source);
    const targetPos = nodePositionMap.get(e.target);
    const isForward = !sourcePos || !targetPos || sourcePos.y <= targetPos.y;
    const horizontalDistance = sourcePos && targetPos
      ? Math.abs(sourcePos.x - targetPos.x)
      : 0;
    const backwardOffset = Math.max(80, horizontalDistance + 60);
    const useStraight = forceStraight;

    // pick color from the source node's type
    const srcNode = knownNodes.find(n => n.id === e.source);
    const edgeColor = EDGE_COLORS[srcNode?.data?.nodeType] || EDGE_COLORS.default;

    return {
      id: `${e.source}-${e.target}`,
      source: e.source,
      target: e.target,
      animated: false,
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
      markerEnd: {
        type: MarkerType.ArrowClosed,
        width: 16,
        height: 16,
        color: edgeColor
      },
      style: {
        stroke: edgeColor,
        strokeWidth: 2,
        strokeLinecap: 'round',
        strokeLinejoin: 'round',
        strokeDasharray: isForward ? '0' : '6 3'
      },
      type: isForward ? 'smoothstep' : 'backcall',
      pathOptions: isForward
        ? { borderRadius: 8 }
        : { borderRadius: 14, offset: backwardOffset }
    };
  });
};

// Save current state to nav stack before drilling down
const pushNav = (label) => {
  navStack.value.push({
    label: currentLabel.value || 'Root',
    nodes: JSON.parse(JSON.stringify(nodes.value)),
    edges: JSON.parse(JSON.stringify(edges.value)),
    expandedNodes: new Set(expandedNodes.value),
    nodeLevelMap: new Map(nodeLevelMap.value)
  });
  currentLabel.value = label;
};

const goBack = async () => {
  const prev = navStack.value.pop();
  if (!prev) return;
  nodes.value = prev.nodes;
  edges.value = prev.edges;
  expandedNodes.value = prev.expandedNodes;
  nodeLevelMap.value = prev.nodeLevelMap;
  currentLabel.value = prev.label;
  await nextTick();
  fitView({ padding: 0.45, duration: 300, maxZoom: 0.95 });
};

// Build structural parent→child edges (module→file, file→function)
const makeParentChildEdges = (parentNode, childNodes) => {
  return childNodes.map(child => {
    const edgeColor = EDGE_COLORS[parentNode.data?.nodeType] || EDGE_COLORS.default;
    return {
      id: `${parentNode.id}->${child.id}`,
      source: parentNode.id,
      target: child.id,
      animated: false,
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
      markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16, color: edgeColor },
      style: { stroke: edgeColor, strokeWidth: 2, strokeLinecap: 'round', strokeDasharray: '0' },
      type: 'smoothstep',
      pathOptions: { borderRadius: 8 }
    };
  });
};

const renderFileRelationsView = async (fileGraph) => {
  if (!fileGraph || !fileGraph.nodes || fileGraph.nodes.length === 0) {
    uploadError.value = 'No files found in the uploaded source.';
    return;
  }
  // Grid layout: sqrt-based columns
  const count = fileGraph.nodes.length;
  const cols = Math.max(1, Math.ceil(Math.sqrt(count)));
  const newNodes = fileGraph.nodes.map((f, i) => {
    const col = i % cols;
    const row = Math.floor(i / cols);
    return createNode(f.id,
      { x: (col - (cols - 1) / 2) * 260, y: row * 180 },
      { fullLabel: f.id, nodeType: 'file', language: f.language }
    );
  });
  const newEdges = toVueFlowEdges(fileGraph.edges || [], newNodes);
  nodes.value = newNodes;
  edges.value = newEdges;
  expandedNodes.value.clear();
  nodeLevelMap.value.clear();
  fileGraph.nodes.forEach(f => nodeLevelMap.value.set(f.id, 0));
  navStack.value = [];
  currentLabel.value = 'Files';
  await nextTick();
  fitView({ padding: 0.45, duration: 300, maxZoom: 0.95 });
};

const renderTier1Graph = async (tier1) => {
  if (!tier1 || !Array.isArray(tier1.nodes) || tier1.nodes.length === 0) {
    uploadError.value = 'No graph data returned from backend.';
    nodes.value = [];
    edges.value = [];
    return;
  }

  const moduleNodes = tier1.nodes.filter((n) => n.type === 'module');
  const fileNodes = tier1.nodes.filter((n) => n.type === 'file');

  if (moduleNodes.length === 0) {
    await renderFileRelationsView(tier1);
    return;
  }

  const mixedNodes = [];
  const moduleCols = Math.max(1, moduleNodes.length);
  const fileCols = Math.max(1, fileNodes.length);

  // renderTier1Graph এ module spacing fix করো (210 → 300)
  moduleNodes.forEach((m, index) => {
    mixedNodes.push(
      createNode(
        m.id,
        { x: index * 300 - ((moduleCols - 1) * 150), y: 0 }, // 210→300, 105→150
        { fullLabel: m.label || m.id, nodeType: 'module', language: (m.languages && m.languages[0]) || null }
      )
    );
  });

  fileNodes.forEach((f, index) => {
    mixedNodes.push(
      createNode(
        f.id,
        { x: index * 210 - ((fileCols - 1) * 105), y: 180 },
        { fullLabel: f.id, nodeType: 'file', language: f.language }
      )
    );
  });

  nodes.value = mixedNodes;
  edges.value = toVueFlowEdges(tier1.edges || [], mixedNodes);
  expandedNodes.value.clear();
  nodeLevelMap.value.clear();
  tier1.nodes.forEach((n) => nodeLevelMap.value.set(n.id, 0));
  navStack.value = [];
  currentLabel.value = 'Modules';
  await nextTick();
  fitView({ padding: 0.45, duration: 300, maxZoom: 0.95 });
};

const renderModuleRoot = async (moduleNodes) => {
  // moduleNodes: [{ id, loc, fn_count, languages }]
  // Spread modules horizontally across the top
  nodes.value = moduleNodes.map((m, i) =>
    createNode(m.id, { x: i * 210 - ((moduleNodes.length - 1) * 105), y: 0 }, { fullLabel: m.id, nodeType: 'module', language: (m.languages && m.languages[0]) || null })
  );
  edges.value = [];
  expandedNodes.value.clear();
  nodeLevelMap.value.clear();
  moduleNodes.forEach((m) => nodeLevelMap.value.set(m.id, 0));
  navStack.value = [];
  currentLabel.value = 'Modules';
  await nextTick();
  fitView({ padding: 0.45, duration: 300, maxZoom: 0.95 });
};

const resetGraphState = () => {
  uploadError.value = null;
  uploadSuccess.value = false;
  uploading.value = true;
  uploadedFile.value = null;
  discoveredFunctions.value = [];
  selectedRoot.value = "";
  nodes.value = [];
  edges.value = [];
  expandedNodes.value.clear();
  nodeLevelMap.value.clear();
};

const uploadWithFormData = async (formData, sourceName) => {
  resetGraphState();

  try {
    const response = await sessionManager.apiCall('/upload', {
      method: 'POST',
      body: formData,
    });
    const data = await response.json();

    uploadedFile.value = sourceName;
    uploadSuccess.value = true;

    const render = data.render_strategy;
    const tier1 = data.tier1_graph || null;

    const resolvedTier1 = tier1 || await (async () => {
      const tier1Response = await sessionManager.apiCall('/graph/tier1', {
        method: 'GET',
      });
      return await tier1Response.json();
    })();

    if (!resolvedTier1 || !Array.isArray(resolvedTier1.nodes)) {
      uploadError.value = 'No graph data returned from backend.';
      nodes.value = [];
      edges.value = [];
      return;
    }

    const isSingleFile = (data.total_files ?? 0) === 1;
    const hasModuleNodes = resolvedTier1.nodes.some((n) => n.type === 'module');
    const hasFileNodes = resolvedTier1.nodes.some((n) => n.type === 'file');

    // If single-file upload (.py/.js/etc, NOT zip), show all functions directly
    if (isSingleFile && !sourceName.toLowerCase().endsWith('.zip')) {
      const fileId = sourceName;
      try {
        const fnRes = await sessionManager.apiCall(`/graph/tier3?file_path=${encodeURIComponent(fileId)}`, {
          method: 'GET',
        });
        const fnData = await fnRes.json();
        if (fnData?.nodes?.length) {
          await renderFunctionView(fileId, fnData);
        } else {
          nodes.value = [];
          edges.value = [];
          uploadError.value = 'No function graph found for this file.';
        }
        window.__render_strategy = render;
        return;
      } catch (err) {
        console.warn('Failed to fetch tier3 for single file, falling back to module view', err);
        // fall through to module view
      }
    }

    // Render tier1 exactly as the backend classified it.
    if (hasModuleNodes && !hasFileNodes && resolvedTier1.nodes.length === 1) {
      // Auto-expand: if only 1 module, skip the module layer and show files directly
      const singleModule = resolvedTier1.nodes[0];
      try {
        const t2Res = await sessionManager.apiCall(`/graph/tier2/${encodeURIComponent(singleModule.id)}`, { method: 'GET' });
        const t2 = await t2Res.json();
        if (t2?.nodes?.length) {
          // Render module root first (needed for position anchor), then auto-expand it
          await renderModuleRoot(resolvedTier1.nodes);
          const moduleNode = nodes.value.find(n => n.id === singleModule.id);
          if (moduleNode) {
            const newNodes = t2.nodes.map((f, index) => {
              const pos = getRootChildPosition(moduleNode, index, t2.nodes.length);
              nodeLevelMap.value.set(f.id, 1);
              return createNode(f.id, pos, { fullLabel: f.id, nodeType: 'file', language: f.language });
            });
            const newEdges = toVueFlowEdges(t2.edges, [...nodes.value, ...newNodes]);
            nodes.value = [...nodes.value, ...newNodes];
            edges.value = [...edges.value, ...newEdges];
            expandedNodes.value.add(singleModule.id);
            if (t2.nodes.length === 1) {
              const singleFile = t2.nodes[0];
              try {
                const t3Res = await sessionManager.apiCall(`/graph/tier3?file_path=${encodeURIComponent(singleFile.id)}`, { method: 'GET' });
                const t3 = await t3Res.json();
                if (t3?.nodes?.length) {
                  const fileNode = nodes.value.find(n => n.id === singleFile.id);
                  if (fileNode) {
                    const fnNodes = t3.nodes.map((fn, i) => {
                      const pos = getChildPosition(fileNode, i, t3.nodes.length);
                      nodeLevelMap.value.set(fn.id, 2);
                      return createNode(fn.id, pos, { fullLabel: fn.id, nodeType: fn.type === 'chunk' ? 'chunk' : 'function', language: fn.language, callCount: fn.fan_out });
                    });
                    const structEdges = makeParentChildEdges(fileNode, fnNodes);
                    const fnCallEdges = toVueFlowEdges(t3.edges, [...nodes.value, ...fnNodes]);
                    nodes.value = [...nodes.value, ...fnNodes];
                    edges.value = [...edges.value, ...structEdges, ...fnCallEdges];
                    expandedNodes.value.add(singleFile.id);
                  }
                }
              } catch (_) { /* ignore */ }
            }
            await nextTick();
            fitView({ padding: 0.4, duration: 400, maxZoom: 0.9 });
          }
        } else {
          await renderModuleRoot(resolvedTier1.nodes);
        }
      } catch (_) {
        await renderModuleRoot(resolvedTier1.nodes);
      }
    } else if (hasModuleNodes || hasFileNodes) {
      await renderTier1Graph(resolvedTier1);
    } else {
      // No module structure – fetch and show file-level relations graph
        try {
        const filesRes = await sessionManager.apiCall('/graph/files', { method: 'GET' });
        const filesData = await filesRes.json();
        if (filesData?.nodes?.length) {
          await renderFileRelationsView(filesData);
        } else {
          uploadError.value = 'No files found in the uploaded source.';
          nodes.value = [];
          edges.value = [];
        }
      } catch (err) {
        console.warn('Failed to fetch file graph', err);
        uploadError.value = 'Could not build file relations graph.';
        nodes.value = [];
        edges.value = [];
      }
    }
    // save render strategy for frontend decisions
    window.__render_strategy = render;
    // expose basic stats
    discoveredFunctions.value = [];
    selectedRoot.value = '';
    functionLayoutMode.value = false;
  } catch (err) {
    console.error("Error uploading file:", err);
    uploadError.value =
      err.message || "Failed to upload file. Make sure backend is running.";
    nodes.value = [];
    edges.value = [];
  }
};

const renderFunctionView = async (fileId, functionGraph) => {
  // functionGraph: { nodes: [...], edges: [...], chunked: bool }
  if (!functionGraph || !functionGraph.nodes) {
    nodes.value = [];
    edges.value = [];
    return;
  }

  const center = { x: 0, y: 0 };
  const count = functionGraph.nodes.length || 1;
  const radius = Math.max(180, 60 * Math.sqrt(count));

  // Build a BFS tree layout from edges so it flows top-down like the image
  const edgeList = functionGraph.edges || [];
  const childMap = new Map(functionGraph.nodes.map(n => [n.id, []]));
  const inDeg = new Map(functionGraph.nodes.map(n => [n.id, 0]));
  edgeList.forEach(e => {
    if (childMap.has(e.source) && childMap.has(e.target)) {
      childMap.get(e.source).push(e.target);
      inDeg.set(e.target, (inDeg.get(e.target) || 0) + 1);
    }
  });
  let roots = functionGraph.nodes.filter(n => inDeg.get(n.id) === 0).map(n => n.id);
  if (roots.length === 0) roots = [functionGraph.nodes[0].id];
  const levelMap = new Map();
  const queue = roots.map(r => ({ id: r, lvl: 0 }));
  const visited = new Set();
  while (queue.length) {
    const { id, lvl } = queue.shift();
    if (visited.has(id)) continue;
    visited.add(id); levelMap.set(id, lvl);
    (childMap.get(id) || []).forEach(c => queue.push({ id: c, lvl: lvl + 1 }));
  }
  functionGraph.nodes.forEach(n => { if (!levelMap.has(n.id)) levelMap.set(n.id, 0); });
  const byLevel = new Map();
  levelMap.forEach((lvl, id) => { if (!byLevel.has(lvl)) byLevel.set(lvl, []); byLevel.get(lvl).push(id); });
  const posMap = new Map();
  byLevel.forEach((ids, lvl) => {
    ids.forEach((id, i) => posMap.set(id, {
      x: (i - (ids.length - 1) / 2) * FUNCTION_TREE_SIBLING_GAP,
      y: lvl * FUNCTION_TREE_DEPTH_GAP
    }));
  });

  const newNodes = functionGraph.nodes.map((fn) => {
    const pos = posMap.get(fn.id) || { x: 0, y: 0 };
    nodeLevelMap.value.set(fn.id, levelMap.get(fn.id) || 1);
    return createNode(fn.id, pos, { fullLabel: fn.id, nodeType: fn.type === 'chunk' ? 'chunk' : 'function', language: fn.language, callCount: fn.fan_out });
  });

  const newEdges = toVueFlowEdges(edgeList, newNodes, { forceStraight: false });
  nodes.value = newNodes;
  edges.value = newEdges;
  expandedNodes.value.clear();
  functionLayoutMode.value = true;
  await nextTick();
  fitView({ padding: 0.45, duration: 300, maxZoom: 0.95 });
};

const handleFileUpload = async (event) => {
  const file = event.target.files[0];
  if (!file) return;

  const lowerName = file.name.toLowerCase();
  const supportedExtensions = [".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".cpp", ".c", ".cs", ".zip"];
  if (!supportedExtensions.some((ext) => lowerName.endsWith(ext))) {
    uploadError.value = "Please upload a supported source file or .zip";
    event.target.value = "";
    return;
  }

  try {
    const formData = new FormData();
    formData.append("file", file);
    await uploadWithFormData(formData, file.name);
  } catch (err) {
    console.error("Error uploading file:", err);
    uploadError.value =
      err.response?.data?.detail || "Failed to upload file. Make sure backend is running.";
    nodes.value = [];
    edges.value = [];
  } finally {
    uploading.value = false;
    event.target.value = "";
  }
};

const handleFolderUpload = async (event) => {
  const selectedFiles = Array.from(event.target.files || []);
  if (selectedFiles.length === 0) return;

  try {
    const CLIENT_SKIP_DIRS = ["node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build", ".idea", ".vscode", "uploads"];
    const formData = new FormData();
    let accepted = 0;
    let skipped = 0;

    selectedFiles.forEach((file) => {
      const relPath = file.webkitRelativePath || file.name;
      const parts = relPath.split("/").map(p => p.toLowerCase());
      const isSkipped = parts.some(p => CLIENT_SKIP_DIRS.includes(p));
      if (isSkipped) {
        skipped += 1;
        return;
      }
      formData.append("files", file, relPath);
      accepted += 1;
    });

    if (skipped > 0) {
      uploadError.value = `${skipped} files were skipped (ignored folders like venv/node_modules).`;
    }

    const firstPath = selectedFiles.find(f => f.webkitRelativePath)?.webkitRelativePath || selectedFiles[0].name || "folder";
    const folderName = firstPath.split("/")[0] || "folder";
    await uploadWithFormData(formData, `${folderName} (${accepted} files, ${skipped} skipped)`);
  } catch (err) {
    console.error("Error uploading folder:", err);
    uploadError.value =
      err.response?.data?.detail || "Failed to upload folder. Make sure backend is running.";
    nodes.value = [];
    edges.value = [];
  } finally {
    uploading.value = false;
    event.target.value = "";
  }
};

const onNodeClick = async ({ node }) => {
  if (expandedNodes.value.has(node.id)) return;

  const type = node.data?.nodeType || 'module';
  try {
    // onNodeClick এর module branch-এ — drill down করার সময় clean state রাখো
  if (type === 'module') {
    const response = await sessionManager.apiCall(`/graph/tier2/${encodeURIComponent(node.id)}`, {
      method: 'GET',
    });
    const res = await response.json();
    pushNav(node.data?.label || node.id);
    
    // ← এইটাই key fix: শুধু clicked module + তার children দেখাও
    const parentLevel = nodeLevelMap.value.get(node.id) ?? 0;
    const newChildNodes = res.nodes.map((f, index) => {
      const pos = getRootChildPosition(node, index, res.nodes.length);
      nodeLevelMap.value.set(f.id, parentLevel + 1);
      return createNode(f.id, pos, { fullLabel: f.id, nodeType: 'file', language: f.language });
    });

    const structuralEdges = makeParentChildEdges(node, newChildNodes);
    const peerEdges = toVueFlowEdges(res.edges, [node, ...newChildNodes]);

    // পুরো graph replace করো — শুধু এই module + তার files
    nodes.value = [node, ...newChildNodes];
    edges.value = [...structuralEdges, ...peerEdges];
    expandedNodes.value.clear();
    expandedNodes.value.add(node.id);
    nodeLevelMap.value.clear();
    nodeLevelMap.value.set(node.id, 0);
    newChildNodes.forEach(n => nodeLevelMap.value.set(n.id, 1));

    await nextTick();
    fitView({ padding: 0.5, duration: 250, maxZoom: 0.9 });
  } else if (type === 'file' || type === 'chunk') {
      // Drill into function call graph for this file
      const response = await sessionManager.apiCall(`/graph/tier3?file_path=${encodeURIComponent(node.id)}`, {
        method: 'GET',
      });
      const res = await response.json();
      pushNav(node.data?.label || node.id);
      await renderFunctionView(node.id, res);
    } else {
      // function node - optionally expand via existing expand endpoint
      const response = await sessionManager.apiCall(`/expand/${encodeURIComponent(node.id)}`, {
        method: 'GET',
      });
      const res = await response.json();
      const parentLevel = nodeLevelMap.value.get(node.id) ?? 0;
      const incomingIds = new Set();
      const outgoingIds = new Set();
      (res.edges || []).forEach((edge) => {
        if (edge.target === node.id) {
          incomingIds.add(edge.source);
        }
        if (edge.source === node.id) {
          outgoingIds.add(edge.target);
        }
      });

      const incomingNodes = [];
      const outgoingNodes = [];
      const neutralNodes = [];

      res.nodes.forEach((n) => {
        if (outgoingIds.has(n.id)) {
          outgoingNodes.push(n);
        } else if (incomingIds.has(n.id)) {
          incomingNodes.push(n);
        } else {
          neutralNodes.push(n);
        }
      });

      const rightSideNodes = [...outgoingNodes, ...neutralNodes];
      const newNodes = [];

      incomingNodes.forEach((n, index) => {
        const level = parentLevel + 1;
        const pos = getFunctionChildPosition(node, index, incomingNodes.length, "left");
        nodeLevelMap.value.set(n.id, level);
        newNodes.push(createNode(n.id, pos, { fullLabel: n.id, nodeType: 'function' }));
      });

      rightSideNodes.forEach((n, index) => {
        const level = parentLevel + 1;
        const pos = getFunctionChildPosition(node, index, rightSideNodes.length, "right");
        nodeLevelMap.value.set(n.id, level);
        newNodes.push(createNode(n.id, pos, { fullLabel: n.id, nodeType: 'function' }));
      });
      pushNav(node.data?.label || node.id);
      const newEdges = toVueFlowEdges(res.edges, [...nodes.value, ...newNodes], { forceStraight: true });
      const existingIds = new Set(nodes.value.map((n) => n.id));
      const existingEdgeIds = new Set(edges.value.map((e) => e.id));
      nodes.value = [...nodes.value, ...newNodes.filter(n => !existingIds.has(n.id))];
      edges.value = [...edges.value, ...newEdges.filter(e => !existingEdgeIds.has(e.id))];
      expandedNodes.value.add(node.id);
      functionLayoutMode.value = true;
      await nextTick();
      fitView({ padding: 0.5, duration: 250, maxZoom: 0.9 });
    }
  } catch (err) {
    console.error('Error fetching graph:', err);
    alert('Failed to fetch graph data. Make sure backend is running.');
  }
};

const onNodeHover = ({ node }) => {
  // Find directly connected node IDs
  const connectedIds = new Set([node.id]);
  edges.value.forEach((e) => {
    if (e.source === node.id) connectedIds.add(e.target);
    if (e.target === node.id) connectedIds.add(e.source);
  });

  // Brighten related edges, dim unrelated
  edges.value = edges.value.map((e) => {
    const isRelated = e.source === node.id || e.target === node.id;
    const baseColor = e.style?.stroke || EDGE_COLORS.default;
    return {
      ...e,
      markerEnd: {
        type: MarkerType.ArrowClosed,
        width: isRelated ? 18 : 14,
        height: isRelated ? 18 : 14,
        color: isRelated ? baseColor : '#e2e8f0'
      },
      style: {
        ...(e.style || {}),
        stroke: isRelated ? baseColor : '#e2e8f0',
        strokeWidth: isRelated ? 3 : 1.5,
        opacity: isRelated ? 1 : 0.25
      },
      animated: isRelated,
    };
  });

  // Highlight connected nodes, fade unconnected
  nodes.value = nodes.value.map((n) => ({
    ...n,
    style: {
      ...n.style,
      opacity: connectedIds.has(n.id) ? 1 : 0.25,
      filter: n.id === node.id ? 'drop-shadow(0 0 6px rgba(99,102,241,0.5))' : 'none'
    }
  }));
};

const onNodeUnhover = () => {
  // restore original edge colors and node opacity
  edges.value = edges.value.map((e) => ({
    ...e,
    markerEnd: {
      type: MarkerType.ArrowClosed,
      width: 16,
      height: 16,
      color: e.style?.stroke || EDGE_COLORS.default
    },
    style: {
      ...(e.style || {}),
      strokeWidth: 2,
      opacity: 1
    },
    animated: false,
  }));
  nodes.value = nodes.value.map((n) => ({
    ...n,
    style: {
      ...n.style,
      opacity: 1,
      filter: 'none'
    }
  }));
};

const collapseOthers = (nodeType, keepId) => {
  nodes.value = nodes.value.map((n) => {
    const t = n.data && n.data.nodeType;
    if (t === nodeType && n.id !== keepId) {
      return {
        ...n,
        style: {
          ...(n.style || {}),
          opacity: 0.15,
          transform: 'scale(0.85)'
        }
      };
    }
    if (t === nodeType && n.id === keepId) {
      return {
        ...n,
        style: {
          ...(n.style || {}),
          opacity: 1,
          transform: 'scale(1.03)'
        }
      };
    }
    return n;
  });
};
</script>

<style scoped>
/* ── Layout ────────────────────────────────────────── */
.graph-container {
  display: flex;
  flex-direction: row;
  height: 100vh;
  overflow: hidden;
}

/* ── Sidebar ───────────────────────────────────────── */
.sidebar {
  width: 264px;
  min-width: 264px;
  background: #0f172a;
  color: #e2e8f0;
  display: flex;
  flex-direction: column;
  gap: 0;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-width: thin;
  scrollbar-color: #334155 transparent;
}

/* Brand */
.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 20px 18px 16px;
  border-bottom: 1px solid #1e293b;
}
.brand-icon {
  font-size: 28px;
  line-height: 1;
  color: #818cf8;
}
.brand-name {
  font-size: 17px;
  font-weight: 700;
  color: #f1f5f9;
  letter-spacing: -0.01em;
}
.brand-sub {
  font-size: 11px;
  color: #64748b;
  margin-top: 1px;
}

/* Sidebar sections */
.sidebar-section {
  padding: 16px 18px;
  border-bottom: 1px solid #1e293b;
}
.sidebar-section.tips {
  flex: 1;
}
.section-title {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #475569;
  margin-bottom: 10px;
}

/* Back button */
.back-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 7px 12px;
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 7px;
  color: #94a3b8;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  margin-bottom: 8px;
}
.back-btn:hover {
  background: #334155;
  color: #e2e8f0;
}
.breadcrumb {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 2px;
  font-size: 10px;
  color: #475569;
}
.crumb { color: #64748b; }
.crumb-current { color: #94a3b8; font-weight: 600; }
.crumb-sep { color: #334155; margin: 0 2px; 
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 7px 12px;
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 7px;
  color: #94a3b8;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  margin-bottom: 8px;
}
.back-btn:hover {
  background: #334155;
  color: #e2e8f0;
}
.breadcrumb {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 2px;
  font-size: 10px;
  color: #475569;
}
.crumb { color: #64748b; }
.crumb-current { color: #94a3b8; font-weight: 600; }
.crumb-sep { color: #334155; margin: 0 2px; }

/* Upload zone */
.upload-zone {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 18px 12px;
  border: 2px dashed #334155;
  border-radius: 10px;
  cursor: pointer;
  text-align: center;
  transition: border-color 180ms, background 180ms;
  background: #1e293b;
  margin-bottom: 8px;
}
.upload-zone:hover:not(.disabled) {
  border-color: #818cf8;
  background: #1e2a45;
}
.upload-zone.disabled { opacity: 0.5; cursor: not-allowed; }
.upload-zone-icon { font-size: 24px; }
.upload-zone-text { font-size: 12px; font-weight: 600; color: #cbd5e1; line-height: 1.3; }
.upload-zone-hint { font-size: 10px; color: #475569; margin-top: 2px; }

.upload-btn-folder {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  padding: 9px 14px;
  border-radius: 8px;
  background: #1e293b;
  border: 1px solid #334155;
  color: #94a3b8;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: background 180ms, border-color 180ms, color 180ms;
}
.upload-btn-folder:hover:not(.disabled) {
  background: #253347;
  border-color: #64748b;
  color: #e2e8f0;
}
.upload-btn-folder.disabled { opacity: 0.5; cursor: not-allowed; }
.file-input { display: none; }

/* Status */
.status-file {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 6px;
}
.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.status-dot.ok  { background: #22c55e; }
.status-dot.err { background: #f87171; }
.status-filename {
  font-size: 12px;
  font-weight: 600;
  color: #94a3b8;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.status-msg {
  font-size: 12px;
  line-height: 1.4;
  border-radius: 6px;
  padding: 7px 10px;
}
.status-msg.ok  { background: #14532d33; color: #86efac; }
.status-msg.err { background: #7f1d1d33; color: #fca5a5; }
.status-count {
  margin-top: 6px;
  font-size: 11px;
  color: #475569;
  display: flex;
  align-items: center;
  gap: 5px;
}
.count-num {
  font-weight: 700;
  color: #818cf8;
}

/* Legend */
.legend { display: flex; flex-direction: column; gap: 7px; }
.legend-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #94a3b8;
}
.legend-swatch {
  width: 12px;
  height: 12px;
  border-radius: 3px;
  flex-shrink: 0;
}
.legend-swatch.module   { background: #3b82f6; }
.legend-swatch.file     { background: #f59e0b; }
.legend-swatch.function { background: #10b981; }
.legend-swatch.chunk    { background: #8b5cf6; }
.legend-icon {
  font-size: 13px;
  width: 16px;
  text-align: center;
  color: #cbd5e1;
}

/* Tips */
.tips-list {
  padding-left: 16px;
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.tips-list li {
  font-size: 12px;
  color: #64748b;
  line-height: 1.4;
}
.tips-list strong { color: #94a3b8; }

/* ── Graph canvas ──────────────────────────────────── */
.graph-section {
  flex: 1;
  position: relative;
  overflow: hidden;
  background: #f4f6f9;
  background-image: radial-gradient(circle, #d1d9e6 1px, transparent 1px);
  background-size: 24px 24px;
}

.vue-flow {
  width: 100%;
  height: 100%;
}

/* ── Empty state ───────────────────────────────────── */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 12px;
  text-align: center;
  padding: 40px;
}
.empty-icon {
  font-size: 56px;
  opacity: 0.15;
  line-height: 1;
}
.empty-title {
  font-size: 20px;
  font-weight: 700;
  color: #334155;
}
.empty-sub {
  font-size: 14px;
  color: #64748b;
  line-height: 1.6;
}
.empty-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: center;
  margin-top: 4px;
}
.empty-badges span {
  padding: 3px 10px;
  border-radius: 20px;
  background: #e2e8f0;
  color: #475569;
  font-size: 12px;
  font-weight: 600;
  font-family: monospace;
}
</style>
