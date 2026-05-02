<template>
  <div class="graph-container">
    <!-- Upload Section -->
    <div class="upload-section">
      <div class="upload-content">
        <div class="upload-actions">
          <label for="file-input" class="upload-label" :class="{ disabled: uploading }">
            <span v-if="!uploading" class="upload-text">
              📦 Upload File / ZIP
            </span>
            <span v-else class="upload-text uploading">
              ⏳ Uploading...
            </span>
          </label>
          <input
            id="file-input"
            type="file"
            accept=".py,.js,.jsx,.ts,.tsx,.java,.go,.rs,.cpp,.c,.cs,.zip"
            @change="handleFileUpload"
            :disabled="uploading"
            class="file-input"
          />

          <label for="folder-input" class="upload-label secondary" :class="{ disabled: uploading }">
            <span class="upload-text">📁 Upload Folder</span>
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
        <p class="upload-hint">Supported: .py, .js, .jsx, .ts, .tsx, .java, .go, .rs, .cpp, .c, .cs, .zip, or folder</p>
        <p v-if="uploadedFile" class="file-info">
          Source: <strong>{{ uploadedFile }}</strong>
        </p>
        <p v-if="uploadError" class="error-message">
          ❌ {{ uploadError }}
        </p>
        <p v-if="uploadSuccess" class="success-message">
          ✅ Upload complete! Click modules, files, or functions to drill down.
        </p>
      </div>
    </div>

    <!-- Graph Section -->
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
        fit-view
        class="vue-flow"
      />
      <div v-else class="empty-state">
        <p>👆 Upload a supported source file, ZIP, or folder to see the graph</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { markRaw, nextTick, ref, inject } from "vue";
import { MarkerType, Position, useVueFlow, VueFlow } from "@vue-flow/core";
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
const { fitView } = useVueFlow();
const nodeTypes = {
  functionNode: markRaw(FunctionNode)
};
const edgeTypes = {
  backcall: markRaw(BottomBackEdge)
};

const TREE_DEPTH_GAP = 240;
const TREE_SIBLING_GAP = 150;
const FUNCTION_TREE_DEPTH_GAP = 260;
const FUNCTION_TREE_SIBLING_GAP = 140;
const MAX_CHILDREN_PER_COLUMN = 2;

const defaultEdgeOptions = {
  markerEnd: {
    type: MarkerType.ArrowClosed,
    width: 26,
    height: 26,
    color: "#0f3b33"
  },
  style: {
    stroke: "#0f3b33",
    strokeWidth: 3.5,
    strokeLinecap: "round",
    strokeLinejoin: "round"
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

const createNode = (id, position, opts = {}) => {
  const { label, fullLabel, nodeType = 'module', callCount = 0, isRoot = false, language } = opts;
  return {
    id,
    type: 'functionNode',
    data: {
      label: label || formatNodeLabel(fullLabel || id),
      fullLabel: fullLabel || id,
      callCount,
      nodeType,
      language,
      isRoot
    },
    position,
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    style: {
      width: isRoot ? '88px' : nodeType === 'module' ? '92px' : '68px',
      height: isRoot ? '88px' : nodeType === 'module' ? '92px' : '68px'
    },
    draggable: false
  };
};

const getChildPosition = (parentNode, childIndex, totalChildren) => {
  const columnCount = Math.max(1, Math.ceil(totalChildren / MAX_CHILDREN_PER_COLUMN));
  const column = Math.floor(childIndex / MAX_CHILDREN_PER_COLUMN);
  const columnStart = column * MAX_CHILDREN_PER_COLUMN;
  const itemsInColumn = Math.min(MAX_CHILDREN_PER_COLUMN, totalChildren - columnStart);
  const rowInColumn = childIndex % MAX_CHILDREN_PER_COLUMN;
  const yOffset = rowInColumn - (itemsInColumn - 1) / 2;
  const xOffset = (column + 1) * TREE_DEPTH_GAP + Math.max(0, columnCount - 2) * 35;

  return {
    x: parentNode.position.x + xOffset,
    y: parentNode.position.y + yOffset * TREE_SIBLING_GAP
  };
};

const getRootChildPosition = (parentNode, childIndex, totalChildren) => {
  const fanGap = 145;
  const centerOffset = (totalChildren - 1) / 2;

  return {
    x: parentNode.position.x + 250,
    y: parentNode.position.y + (childIndex - centerOffset) * fanGap
  };
};

const getFunctionChildPosition = (parentNode, childIndex, totalChildren, direction = "right") => {
  const centerOffset = (totalChildren - 1) / 2;
  const yOffset = (childIndex - centerOffset) * FUNCTION_TREE_SIBLING_GAP;
  const xDir = direction === "left" ? -FUNCTION_TREE_DEPTH_GAP : FUNCTION_TREE_DEPTH_GAP;

  return {
    x: parentNode.position.x + xDir,
    y: parentNode.position.y + yOffset
  };
};

const toVueFlowEdges = (rawEdges, knownNodes, opts = {}) => {
  const nodePositionMap = new Map(knownNodes.map((n) => [n.id, n.position]));
  const forceStraight = !!opts.forceStraight;

  return rawEdges.map((e) => {
    const sourcePos = nodePositionMap.get(e.source);
    const targetPos = nodePositionMap.get(e.target);
    const isForward = !sourcePos || !targetPos || sourcePos.x <= targetPos.x;
    const verticalDistance = sourcePos && targetPos
      ? Math.abs(sourcePos.y - targetPos.y)
      : 0;
    const backwardOffset = Math.max(110, verticalDistance + 90);
    const useStraight = forceStraight;

    return {
      id: `${e.source}-${e.target}`,
      source: e.source,
      target: e.target,
      animated: false,
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      markerEnd: {
        type: MarkerType.ArrowClosed,
        width: 26,
        height: 26,
        color: "#0f3b33"
      },
      style: {
        stroke: "#0f3b33",
        strokeWidth: 3.5,
        strokeLinecap: "round",
        strokeLinejoin: "round",
        strokeDasharray: useStraight ? "0" : (isForward ? "0" : "7 4")
      },
      type: useStraight ? "straight" : (isForward ? "smoothstep" : "backcall"),
      pathOptions: useStraight
        ? { }
        : (isForward
          ? { borderRadius: 10, offset: 20 }
          : { borderRadius: 14, offset: backwardOffset })
    };
  });
};

const renderModuleRoot = async (moduleNodes) => {
  // moduleNodes: [{ id, loc, fn_count, languages }]
  nodes.value = moduleNodes.map((m, i) =>
    createNode(m.id, { x: 40, y: i * 110 - (moduleNodes.length * 55) }, { fullLabel: m.id, nodeType: 'module', language: (m.languages && m.languages[0]) || null })
  );
  edges.value = [];
  expandedNodes.value.clear();
  nodeLevelMap.value.clear();
  moduleNodes.forEach((m) => nodeLevelMap.value.set(m.id, 0));
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
    
    const tier1Response = await sessionManager.apiCall('/graph/tier1', {
      method: 'GET',
    });
    const tier1 = await tier1Response.json();

    if (!tier1 || !Array.isArray(tier1.nodes)) {
      uploadError.value = 'No graph data returned from backend.';
      nodes.value = [];
      edges.value = [];
      return;
    }

    const isSingleFile = (data.total_files ?? 0) === 1;
    const hasModuleNodes = tier1.nodes.length > 0;

    // If single-file upload, show function view directly
    if (isSingleFile) {
      const fileId = sourceName;
      try {
        const fnRes = await sessionManager.apiCall(`/graph/tier3?file_path=${encodeURIComponent(fileId)}`, {
          method: 'GET',
        });
        const fnData = await fnRes.json();
        if (fnData?.nodes?.length) {
          // For single-file uploads, initially show only the main/root function
          await renderFunctionView(fileId, fnData, { rootOnly: true });
        } else {
          // If backend returns nothing, at least keep the screen clear instead of showing a fake module layer.
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

    // present module view for ZIP/folder uploads, or fallback to nodes only when no edges exist
    if (hasModuleNodes) {
      await renderModuleRoot(tier1.nodes);
    } else {
      nodes.value = [];
      edges.value = [];
      uploadError.value = 'No module nodes were returned by the backend.';
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

  // support options: { rootOnly: true }
  const opts = arguments[2] || {};
  if (opts.rootOnly) {
    // pick a sensible root: look for 'main', else highest importance (fan_in + fan_out)
    let root = null;
    if (Array.isArray(functionGraph.nodes)) {
      root = functionGraph.nodes.find((n) => n.id === 'main' || n.id.toLowerCase() === 'main');
      if (!root) {
        // compute score
        root = functionGraph.nodes.reduce((best, n) => {
          const score = (n.fan_in || 0) + (n.fan_out || 0);
          const bestScore = best ? ((best.fan_in || 0) + (best.fan_out || 0)) : -1;
          return score > bestScore ? n : best;
        }, null);
      }
    }

    if (!root) {
      // fallback to first node
      root = functionGraph.nodes[0];
    }

    // place the root on the left so graph flows left->right
    const pos = { x: -420, y: 0 };
    nodeLevelMap.value.set(root.id, 1);
    nodes.value = [createNode(root.id, pos, { fullLabel: root.id, nodeType: 'function', language: root.language, callCount: root.fan_out, isRoot: true })];
    edges.value = [];
    expandedNodes.value.clear();
    functionLayoutMode.value = true;
    await nextTick();
    fitView({ padding: 0.45, duration: 300, maxZoom: 0.95 });
    return;
  }

  const newNodes = functionGraph.nodes.map((fn, i) => {
    const angle = (i / count) * Math.PI * 2;
    const pos = { x: Math.round(center.x + Math.cos(angle) * radius), y: Math.round(center.y + Math.sin(angle) * radius) };
    nodeLevelMap.value.set(fn.id, 1);
    return createNode(fn.id, pos, { fullLabel: fn.id, nodeType: fn.type === 'chunk' ? 'chunk' : 'function', language: fn.language, callCount: fn.fan_out });
  });

  const newEdges = toVueFlowEdges(functionGraph.edges, newNodes, { forceStraight: true });
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
    const formData = new FormData();
    selectedFiles.forEach((file) => {
      const relPath = file.webkitRelativePath || file.name;
      formData.append("files", file, relPath);
    });

    const firstPath = selectedFiles[0].webkitRelativePath || "folder";
    const folderName = firstPath.split("/")[0] || "folder";
    await uploadWithFormData(formData, `${folderName} (${selectedFiles.length} files)`);
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
    if (type === 'module') {
      // fetch files for module
      const response = await sessionManager.apiCall(`/graph/tier2/${encodeURIComponent(node.id)}`, {
        method: 'GET',
      });
      const res = await response.json();
      const parentLevel = nodeLevelMap.value.get(node.id) ?? 0;
      const newNodes = res.nodes.map((f, index) => {
        const pos = getRootChildPosition(node, index, res.nodes.length);
        nodeLevelMap.value.set(f.id, parentLevel + 1);
        return createNode(f.id, pos, { fullLabel: f.id, nodeType: 'file', language: f.language });
      });
      const newEdges = toVueFlowEdges(res.edges, [...nodes.value, ...newNodes]);
      const existingIds = new Set(nodes.value.map((n) => n.id));
      const existingEdgeIds = new Set(edges.value.map((e) => e.id));
      nodes.value = [...nodes.value, ...newNodes.filter(n => !existingIds.has(n.id))];
      edges.value = [...edges.value, ...newEdges.filter(e => !existingEdgeIds.has(e.id))];
      // collapse other modules visually
      collapseOthers('module', node.id);
      expandedNodes.value.add(node.id);
      await nextTick();
      fitView({ padding: 0.5, duration: 250, maxZoom: 0.9 });
    } else if (type === 'file' || type === 'chunk') {
      // fetch functions for file
      const response = await sessionManager.apiCall(`/graph/tier3?file_path=${encodeURIComponent(node.id)}`, {
        method: 'GET',
      });
      const res = await response.json();
      const parentLevel = nodeLevelMap.value.get(node.id) ?? 0;
      const newNodes = res.nodes.map((fn, index) => {
        const pos = getChildPosition(node, index, res.nodes.length);
        nodeLevelMap.value.set(fn.id, parentLevel + 1);
        // respect backend-provided node type (chunk vs function vs file)
        const nodeType = fn.type === 'chunk' ? 'chunk' : (fn.type === 'file' ? 'file' : 'function');
        return createNode(fn.id, pos, { fullLabel: fn.id, nodeType, language: fn.language, callCount: fn.fan_out });
      });
      const newEdges = toVueFlowEdges(res.edges, [...nodes.value, ...newNodes]);
      const existingIds = new Set(nodes.value.map((n) => n.id));
      const existingEdgeIds = new Set(edges.value.map((e) => e.id));
      nodes.value = [...nodes.value, ...newNodes.filter(n => !existingIds.has(n.id))];
      edges.value = [...edges.value, ...newEdges.filter(e => !existingEdgeIds.has(e.id))];
      // collapse other files within view
      collapseOthers('file', node.id);
      expandedNodes.value.add(node.id);
      await nextTick();
      fitView({ padding: 0.5, duration: 250, maxZoom: 0.9 });
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
  // highlight edges connected to this node, dim others
  edges.value = edges.value.map((e) => {
    const isRelated = e.source === node.id || e.target === node.id;
    return {
      ...e,
      style: {
        ...(e.style || {}),
        stroke: isRelated ? '#e11d48' : '#94a3b8',
        strokeWidth: isRelated ? 4 : 1,
        opacity: isRelated ? 1 : 0.25
      },
      animated: !!isRelated,
    };
  });
  // optionally highlight node
  nodes.value = nodes.value.map((n) => ({
    ...n,
    style: {
      ...(n.style || {}),
      opacity: n.id === node.id ? 1 : 0.35
    }
  }));
};

const onNodeUnhover = ({ node }) => {
  // restore default edge/node styles
  edges.value = edges.value.map((e) => ({
    ...e,
    style: {
      ...(e.style || {}),
      stroke: defaultEdgeOptions.style.stroke,
      strokeWidth: defaultEdgeOptions.style.strokeWidth,
      opacity: 1
    },
    animated: false,
  }));
  nodes.value = nodes.value.map((n) => ({
    ...n,
    style: {
      ...(n.style || {}),
      opacity: 1
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
.graph-container {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 80px);
  background: white;
}

.upload-section {
  background: #f8f9fa;
  border-bottom: 2px solid #e0e0e0;
  padding: 20px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
}

.upload-content {
  max-width: 1200px;
  margin: 0 auto;
}

.upload-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}

.upload-label {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 12px 24px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 500;
  transition: transform 0.2s, box-shadow 0.2s;
}

.upload-label:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.upload-label.secondary {
  background: linear-gradient(135deg, #2f6f61 0%, #3f8f7a 100%);
}

.upload-label.secondary:hover {
  box-shadow: 0 4px 12px rgba(63, 143, 122, 0.4);
}

.upload-label.disabled {
  cursor: not-allowed;
  opacity: 0.65;
  transform: none;
  box-shadow: none;
}

.upload-text.uploading {
  opacity: 0.7;
}

.upload-hint {
  margin-top: 10px;
  color: #666;
  font-size: 13px;
}

.root-picker {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 10px;
}

.root-label {
  font-size: 13px;
  color: #3a3a3a;
  font-weight: 600;
}

.root-select {
  min-width: 220px;
  border: 1px solid #cfd8dc;
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 13px;
  color: #1f2a37;
  background: #fff;
}

.root-select:focus {
  outline: none;
  border-color: #667eea;
  box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.15);
}

.file-input {
  display: none;
}

.file-info {
  margin-top: 12px;
  color: #666;
  font-size: 14px;
}

.file-info strong {
  color: #667eea;
  font-family: monospace;
}

.error-message {
  margin-top: 12px;
  color: #d32f2f;
  font-size: 14px;
  font-weight: 500;
}

.success-message {
  margin-top: 12px;
  color: #388e3c;
  font-size: 14px;
  font-weight: 500;
}

.graph-section {
  flex: 1;
  position: relative;
  overflow: hidden;
}

.vue-flow {
  width: 100%;
  height: 100%;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #999;
  font-size: 18px;
  background: linear-gradient(
    135deg,
    rgba(102, 126, 234, 0.05) 0%,
    rgba(118, 75, 162, 0.05) 100%
  );
}
</style>
