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
            <span class="legend-swatch rootfiles"></span>
            <span class="legend-icon">📂</span>
            <span>Root Files (no module)</span>
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
          <div class="legend-divider"></div>
          <div class="legend-item">
            <span class="legend-swatch risk-high-swatch"></span>
            <span>High Risk (≥10 callers)</span>
          </div>
          <div class="legend-item">
            <span class="legend-swatch risk-medium-swatch"></span>
            <span>Medium Risk (3–9)</span>
          </div>
          <div class="legend-item">
            <span class="legend-swatch risk-low-swatch"></span>
            <span>Low Risk (1–2)</span>
          </div>
          <div class="legend-item">
            <span class="legend-swatch dead-swatch"></span>
            <span>Potentially Unreachable</span>
          </div>
        </div>
      </div>

      <!-- Tips -->
      <div class="sidebar-section tips">
        <div class="section-title">How to use</div>
        <ol class="tips-list">
          <li>Upload a file, ZIP, or folder</li>
          <li>Click a <strong>Module</strong> to see files</li>
          <li>Click a <strong>Root Files</strong> to see orphan files</li>
          <li>Click a <strong>File</strong> to see functions</li>
          <li>Click a <strong>Function</strong> to expand callers &amp; callees</li>
          <li>Hover any node to highlight its edges</li>
        </ol>
      </div>

      <!-- ── Integrated Metrics Dashboard ──────────────────── -->
      <div v-if="metricsData && metricsData.total_functions != null" class="sidebar-section metrics-panel">
        <div class="section-title">Code Metrics</div>
        <div class="metrics-grid">
          <div class="mrow"><span class="mlabel">Lines of Code</span><span class="mval">{{ metricsData.loc?.toLocaleString() }}</span></div>
          <div class="mrow"><span class="mlabel">Significant Lines</span><span class="mval">{{ metricsData.sloc?.toLocaleString() }}</span></div>
          <div class="mrow mrow-sep"></div>
          <div class="mrow"><span class="mlabel">Files</span><span class="mval">{{ metricsData.total_files }}</span></div>
          <div class="mrow"><span class="mlabel">Functions</span><span class="mval">{{ metricsData.total_functions }}</span></div>
          <div class="mrow"><span class="mlabel">Edges / Calls</span><span class="mval">{{ metricsData.total_calls }}</span></div>
          <div class="mrow mrow-sep"></div>
          <div class="mrow"><span class="mlabel">Avg Cyclomatic CC</span><span class="mval" :class="metricsData.avg_cyclomatic > 10 ? 'mv-warn' : metricsData.avg_cyclomatic > 5 ? 'mv-caution' : 'mv-ok'">{{ metricsData.avg_cyclomatic }}</span></div>
          <div class="mrow"><span class="mlabel">Max Cyclomatic CC</span><span class="mval" :class="metricsData.max_cyclomatic > 20 ? 'mv-warn' : metricsData.max_cyclomatic > 10 ? 'mv-caution' : 'mv-ok'">{{ metricsData.max_cyclomatic }}</span></div>
          <div class="mrow"><span class="mlabel">Decision Points</span><span class="mval">{{ metricsData.decision_points }}</span></div>
          <div class="mrow"><span class="mlabel">Cognitive Complexity</span><span class="mval">{{ metricsData.cognitive_complexity }}</span></div>
          <div class="mrow mrow-sep"></div>
          <div class="mrow"><span class="mlabel">Avg Parameters</span><span class="mval">{{ metricsData.avg_parameters }}</span></div>
          <div class="mrow"><span class="mlabel">Max Parameters</span><span class="mval" :class="metricsData.max_parameters > 7 ? 'mv-warn' : ''">{{ metricsData.max_parameters }}</span></div>
          <div class="mrow mrow-sep"></div>
          <div class="mrow"><span class="mlabel">Halstead Volume</span><span class="mval">{{ metricsData.halstead_volume?.toLocaleString() }}</span></div>
          <div class="mrow"><span class="mlabel">Halstead Difficulty</span><span class="mval">{{ metricsData.halstead_difficulty }}</span></div>
          <div class="mrow mrow-sep"></div>
          <div class="mrow"><span class="mlabel">Maintainability Index</span>
            <span class="mval mi-val" :class="metricsData.maintainability_index >= 65 ? 'mv-ok' : metricsData.maintainability_index >= 40 ? 'mv-caution' : 'mv-warn'">
              {{ metricsData.maintainability_index }} <span class="mi-label">{{ metricsData.maintainability_label }}</span>
            </span>
          </div>
          <div class="mrow mrow-sep"></div>
          <div class="mrow"><span class="mlabel">Call Chain Depth</span><span class="mval">{{ metricsData.max_call_chain_depth }}</span></div>
          <div class="mrow"><span class="mlabel">Circular Deps</span><span class="mval" :class="metricsData.circular_deps > 0 ? 'mv-warn' : 'mv-ok'">{{ metricsData.circular_deps }}</span></div>
          <div class="mrow"><span class="mlabel">Orphan Nodes</span><span class="mval" :class="metricsData.orphan_nodes > 0 ? 'mv-caution' : 'mv-ok'">{{ metricsData.orphan_nodes }}</span></div>
        </div>
        <div v-if="metricsData.circular_dep_details?.length" class="circ-details">
          <div class="dead-section-label">Circular Chains</div>
          <div v-for="c in metricsData.circular_dep_details" :key="c" class="circ-chain">{{ c }}</div>
        </div>
      </div>

      <!-- ── Git History Panel ───────────────────────────────── -->
      <div v-if="gitHistory" class="sidebar-section git-panel">
        <div class="section-title">Git History — Metrics Trend</div>
        <div class="git-meta">
          <span class="git-branch">🌿 {{ gitHistory.current_branch }}</span>
          <span class="git-total">{{ gitHistory.total_commits }} commits</span>
        </div>

        <!-- Column headers -->
        <div class="git-trend-header">
          <span class="gth-commit">Commit</span>
          <span class="gth-loc">LOC</span>
          <span class="gth-fns">Fns</span>
          <span class="gth-delta">Δ</span>
        </div>

        <div class="git-list">
          <div
            v-for="c in gitCommitsWithLoc"
            :key="c.hash"
            class="git-item"
            :title="`${c.message}\nAuthor: ${c.author}\nFiles changed: ${c.files_changed}`"
          >
            <div class="git-left">
              <span class="git-hash">{{ c.hash }}</span>
              <div class="git-info">
                <div class="git-msg">{{ c.message }}</div>
                <span class="git-date">{{ c.date }}</span>
              </div>
            </div>
            <!-- Metrics columns -->
            <div class="git-metrics-col">
              <span class="git-loc-val">{{ c.estimatedLoc.toLocaleString() }}</span>
              <span class="git-fns-val">{{ c.estimatedFns }}</span>
              <span class="git-delta-val"
                :class="c.netDelta > 0 ? 'delta-pos' : c.netDelta < 0 ? 'delta-neg' : 'delta-zero'">
                {{ c.netDelta > 0 ? '+' : '' }}{{ c.netDelta }}
              </span>
            </div>
          </div>
        </div>

        <div class="git-note">
          LOC and function counts estimated backwards from the current upload state.
        </div>
      </div>

      <!-- ── Git History: "How to Enable" hint ────────────────── -->
      <div v-else-if="layerViolations !== null || deadCodeData !== null" class="sidebar-section git-hint-panel">
        <div class="section-title">Git History</div>
        <div class="git-hint-box">
          <div class="git-hint-icon">🔒</div>
          <div>
            <div class="git-hint-title">Not detected in this upload</div>
            <div class="git-hint-sub">To see per-version metrics, upload a ZIP that includes the <code>.git</code> folder.</div>
          </div>
        </div>
        <div class="git-how-steps-wrap">
          <div class="git-how-label">How to create the ZIP on Windows</div>
          <ol class="git-how-steps">
            <li>Open your project folder in <strong>File Explorer</strong></li>
            <li>Select <strong>all files including hidden ones</strong> (View → Hidden items ✓)</li>
            <li>Right-click → <strong>Send to → Compressed (zipped) folder</strong></li>
            <li>Upload the ZIP — it will contain <code>.git</code></li>
          </ol>
          <div class="git-how-alt">
            <strong>Git Bash / Terminal:</strong><br>
            <code>cd your-project && zip -r ../project.zip .</code>
          </div>
        </div>
      </div>

      <!-- ── Code Smell Analysis Panel ──────────────────────────── -->
      <div v-if="smellData && smellData.summary?.total > 0" class="sidebar-section smell-panel">
        <div class="section-title">Code Smell Analysis</div>

        <!-- Severity summary -->
        <div class="smell-summary">
          <span v-if="smellData.summary.critical" class="smell-chip smell-critical">💀 {{ smellData.summary.critical }} Critical</span>
          <span v-if="smellData.summary.high"     class="smell-chip smell-high">🔴 {{ smellData.summary.high }} High</span>
          <span v-if="smellData.summary.medium"   class="smell-chip smell-medium">🟡 {{ smellData.summary.medium }} Med</span>
          <span v-if="smellData.summary.low"      class="smell-chip smell-low">🟢 {{ smellData.summary.low }} Low</span>
        </div>

        <!-- Root cause smells (top by root_cause_score) -->
        <div class="dead-section-label">Root Cause Smells</div>
        <div class="smell-list">
          <div
            v-for="rc in smellData.graph_summary?.top_root_causes?.slice(0, 5)"
            :key="rc.target + rc.type"
            class="smell-item"
            :class="`smell-sev-${rc.severity}`"
            :title="`Score: ${rc.root_cause_score} | Resolves ${rc.downstream_resolves} downstream smells`"
          >
            <span class="smell-item-icon">{{ rc.severity === 'critical' ? '💀' : rc.severity === 'high' ? '🔴' : '🟡' }}</span>
            <div class="smell-item-body">
              <div class="smell-item-type">{{ rc.type.replace(/_/g, ' ') }}</div>
              <div class="smell-item-target">{{ rc.target?.split('/').pop() || rc.target }}</div>
            </div>
            <div class="smell-item-score">
              <span class="smell-score-val">{{ rc.root_cause_score }}</span>
              <span class="smell-score-label">score</span>
            </div>
          </div>
        </div>

        <!-- AI Refactor Plan button -->
        <button
          class="smell-llm-btn"
          :class="{ 'smell-llm-btn-loading': llmLoading }"
          :disabled="llmLoading"
          @click="fetchLLMPlan"
        >
          <span v-if="llmLoading">⏳ Analysing architecture…</span>
          <span v-else-if="llmPlan">🔄 Refresh AI Refactor Plan</span>
          <span v-else>✨ Generate AI Refactor Plan</span>
        </button>

        <!-- LLM Reasoning Output -->
        <div v-if="llmPlan" class="llm-plan-box">
          <div class="llm-plan-source">
            {{ llmPlan._source === 'llm' ? '🤖 Groq / llama-3.1-8b-instant' : '📊 Static Analysis Fallback' }}
          </div>
          <div v-if="llmPlan.executive_summary" class="llm-exec-summary">
            {{ llmPlan.executive_summary }}
          </div>
          <div v-if="llmPlan.primary_root_cause" class="llm-root-cause">
            <strong>Root cause:</strong> {{ llmPlan.primary_root_cause }}
          </div>

          <!-- Refactor steps -->
          <div v-if="llmPlan.refactor_plan?.length" class="llm-steps">
            <div class="dead-section-label" style="margin-top:6px">Refactor Plan</div>
            <div
              v-for="step in llmPlan.refactor_plan"
              :key="step.priority"
              class="llm-step"
              :class="`llm-step-${step.risk || 'medium'}`"
            >
              <div class="llm-step-head">
                <span class="llm-step-num">#{{ step.priority }}</span>
                <span class="llm-step-pattern">{{ step.pattern }}</span>
                <span class="llm-step-effort" :class="`effort-${step.estimated_effort}`">{{ step.estimated_effort }}</span>
              </div>
              <div class="llm-step-target">→ {{ step.target }}</div>
              <div class="llm-step-what">{{ step.what_to_do }}</div>
              <div v-if="step.why_this_first" class="llm-step-why">💡 {{ step.why_this_first }}</div>
              <div v-if="step.resolves_smells?.length" class="llm-step-resolves">
                Resolves: {{ step.resolves_smells.join(', ') }}
              </div>
            </div>
          </div>

          <div v-if="llmPlan.long_term_recommendation" class="llm-longterm">
            <strong>Long-term:</strong> {{ llmPlan.long_term_recommendation }}
          </div>
          <div v-if="llmPlan._error" class="llm-error">⚠ {{ llmPlan._error }}</div>
        </div>
      </div>

      <!-- Dependency Risk Panel -->
      <div v-if="riskData" class="sidebar-section risk-panel">
        <div class="section-title">Dependency Risk</div>

        <!-- Summary chips -->
        <div class="risk-summary">
          <span class="risk-chip risk-chip-high">🔴 {{ riskData.summary?.high || 0 }} High</span>
          <span class="risk-chip risk-chip-medium">🟡 {{ riskData.summary?.medium || 0 }} Med</span>
          <span class="risk-chip risk-chip-low">🟢 {{ riskData.summary?.low || 0 }} Low</span>
        </div>

        <!-- Top risky functions list -->
        <div v-if="riskData.functions?.length" class="risk-list">
          <div
            v-for="fn in riskData.functions.slice(0, 10)"
            :key="fn.name + fn.file"
            class="risk-item"
            :class="`risk-item-${fn.risk_level}`"
            :title="fn.warning"
          >
            <span class="risk-item-icon">
              {{ fn.risk_level === 'high' ? '🔴' : fn.risk_level === 'medium' ? '🟡' : '🟢' }}
            </span>
            <div class="risk-item-body">
              <div class="risk-item-name">{{ fn.name }}</div>
              <div class="risk-item-warn">{{ fn.warning }}</div>
            </div>
            <span class="risk-item-count">{{ fn.fan_in }}</span>
          </div>
        </div>
        <div v-else class="risk-empty">No high-risk dependencies found.</div>
      </div>

      <!-- Potentially Unreachable Panel -->
      <div v-if="deadCodeData" class="sidebar-section dead-panel">
        <div class="section-title">Potentially Unreachable</div>

        <!-- Summary chips -->
        <div class="dead-summary">
          <span class="dead-chip dead-chip-high" :title="'High confidence: private functions with no callers'">
            🔒 {{ deadCodeData.summary?.high_confidence || 0 }} private
          </span>
          <span class="dead-chip dead-chip-medium" :title="'Medium confidence: may be called dynamically or externally'">
            👻 {{ deadCodeData.summary?.medium_confidence || 0 }} public
          </span>
          <span class="dead-chip dead-chip-imp">📦 {{ deadCodeData.summary?.total_unused_imports || 0 }} imports</span>
        </div>

        <!-- Unreachable functions -->
        <div v-if="deadCodeData.unreachable_functions?.length" class="dead-section-label">Unreachable Functions</div>
        <div v-if="deadCodeData.unreachable_functions?.length" class="dead-list">
          <div
            v-for="fn in deadCodeData.unreachable_functions.slice(0, 8)"
            :key="fn.name + fn.file"
            class="dead-item"
            :class="fn.dead_confidence === 'high' ? 'dead-item-high' : 'dead-item-medium'"
            :title="fn.suggestion"
          >
            <span class="dead-item-icon">{{ fn.dead_confidence === 'high' ? '🔒' : '👻' }}</span>
            <div class="dead-item-body">
              <div class="dead-item-name">{{ fn.name }}</div>
              <div class="dead-item-file">{{ fn.file.split('/').pop() }}:{{ fn.line_start }}</div>
            </div>
            <span class="dead-conf-badge" :class="fn.dead_confidence === 'high' ? 'conf-high' : 'conf-med'">
              {{ fn.dead_confidence === 'high' ? 'high' : 'med' }}
            </span>
          </div>
        </div>

        <!-- Unused imports -->
        <div v-if="deadCodeData.unused_imports?.length" class="dead-section-label" style="margin-top:8px">Unused Imports</div>
        <div v-if="deadCodeData.unused_imports?.length" class="dead-list">
          <div
            v-for="entry in deadCodeData.unused_imports.slice(0, 5)"
            :key="entry.file"
            class="dead-item dead-import-item"
            :title="entry.suggestion"
          >
            <span class="dead-item-icon">📦</span>
            <div class="dead-item-body">
              <div class="dead-item-name" style="text-decoration:none;color:#92400e">{{ entry.file.split('/').pop() }}</div>
              <div class="dead-item-file">{{ entry.unused.join(', ') }}</div>
            </div>
          </div>
        </div>

        <div v-if="!deadCodeData.unreachable_functions?.length && !deadCodeData.unused_imports?.length" class="risk-empty">
          No potentially unreachable code found.
        </div>

        <!-- Static analysis disclaimer -->
        <div class="dead-note">
          ⚠ Static analysis only. Cross-file calls within this upload are handled.
          Dynamic calls, reflection, and external callers cannot be detected.
        </div>
      </div>

      <!-- Layer Analysis Panel (folder / ZIP only) -->
      <div v-if="layerViolations" class="sidebar-section layer-panel">
        <div class="section-title">Layer Analysis</div>

        <!-- Clean state -->
        <div v-if="layerViolations.summary?.total === 0" class="layer-clean">
          <span class="layer-clean-icon">✅</span>
          <div>
            <div class="layer-clean-title">No layer violations detected.</div>
            <div class="layer-clean-sub">Perfect layered architecture — every module respects its boundaries.</div>
          </div>
        </div>

        <!-- Violations found -->
        <template v-else>
          <div class="layer-summary">
            <span v-if="layerViolations.summary?.high" class="layer-chip layer-chip-high">
              🔴 {{ layerViolations.summary.high }} critical
            </span>
            <span v-if="layerViolations.summary?.medium" class="layer-chip layer-chip-medium">
              🟡 {{ layerViolations.summary.medium }} warning
            </span>
          </div>

          <div class="layer-list">
            <div
              v-for="v in (layerViolations.violations || []).slice(0, 8)"
              :key="v.source_file + v.target_ref"
              class="layer-item"
              :class="v.severity === 'high' ? 'layer-item-high' : 'layer-item-medium'"
              :title="v.message"
            >
              <span class="layer-item-icon">{{ v.severity === 'high' ? '🔴' : '🟡' }}</span>
              <div class="layer-item-body">
                <div class="layer-item-msg">{{ v.message }}</div>
                <div class="layer-item-src">{{ v.source_file.split('/').pop() }} → {{ v.target_ref.split('/').pop() }}</div>
              </div>
            </div>
          </div>
        </template>
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
          :node-color="(n) => {
            if (n.data?.nodeType === 'module') return '#3b82f6';
            if (n.data?.nodeType === 'rootfiles') return '#f59e0b';
            if (n.data?.nodeType === 'file') return '#f59e0b';
            if (n.data?.nodeType === 'chunk') return '#8b5cf6';
            if (n.data?.isDead) return '#94a3b8';
            if (n.data?.riskLevel === 'high') return '#ef4444';
            if (n.data?.riskLevel === 'medium') return '#f59e0b';
            if (n.data?.riskLevel === 'low') return '#22c55e';
            return '#6366f1';
          }"
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
import dagre from 'dagre';
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
const riskData = ref(null);         // { functions: [...], summary: {...}, total: N }
const deadCodeData = ref(null);     // { unreachable_functions: [...], unused_imports: [...], summary: {...} }
const layerViolations = ref(null);  // { by_module: {id: {count, severity}}, summary: {...} }
const metricsData = ref(null);      // Integrated Metrics Dashboard
const gitHistory = ref(null);       // { total_commits, current_branch, commits: [...] }
const smellData = ref(null);        // { smells, summary, graph_summary, plan, fn_smell_map }
const llmPlan = ref(null);          // LLM architectural reasoning result
const llmLoading = ref(false);      // LLM request in progress
const { fitView } = useVueFlow();
const nodeTypes = {
  functionNode: markRaw(FunctionNode)
};
const edgeTypes = {
  backcall: markRaw(BottomBackEdge)
};

const nodeCount = computed(() => nodes.value.length);

// Map function name → worst smell severity for node coloring
const smellSeverityMap = computed(() => smellData.value?.fn_smell_map || {});

// Enrich git commits with estimated LOC + function count at each point in history.
// Commits arrive newest-first; we walk backwards from current state.
const gitCommitsWithLoc = computed(() => {
  if (!gitHistory.value?.commits?.length) return [];
  const currentLoc = metricsData.value?.sloc ?? 0;
  const currentFns = metricsData.value?.total_functions ?? 0;
  const commits = gitHistory.value.commits.slice(0, 15);
  let loc = currentLoc;
  let fns = currentFns;
  return commits.map((c) => {
    const netDelta  = (c.insertions  || 0) - (c.deletions   || 0);
    const fnDelta   = (c.fn_added    || 0) - (c.fn_removed  || 0);
    const estimatedLoc = Math.max(0, loc);
    const estimatedFns = Math.max(0, fns);
    loc = Math.max(0, loc - netDelta);
    fns = Math.max(0, fns - fnDelta);
    return { ...c, estimatedLoc, netDelta, estimatedFns, fnDelta };
  });
});

const TREE_DEPTH_GAP = 200;         // vertical gap between parent and children rows
const TREE_SIBLING_GAP = 320;       // horizontal gap between sibling nodes
const FUNCTION_TREE_DEPTH_GAP = 200;
const FUNCTION_TREE_SIBLING_GAP = 320;
const MAX_CHILDREN_PER_COLUMN = 2;

// ── Dagre Auto Layout ──────────────────────────────
const applyDagreLayout = (rawNodes, rawEdges, opts = {}) => {
  const { rankdir = 'LR', nodesep = 80, ranksep = 160 } = opts;
  
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir, nodesep, ranksep, marginx: 40, marginy: 40 });

  rawNodes.forEach(n => {
    g.setNode(n.id, { width: 170, height: 58 });
  });

  rawEdges.forEach(e => {
    if (g.hasNode(e.source) && g.hasNode(e.target)) {
      g.setEdge(e.source, e.target);
    }
  });

  dagre.layout(g);

  return rawNodes.map(n => {
    const pos = g.node(n.id);
    return {
      ...n,
      position: {
        x: pos.x - 85,  // center: width/2
        y: pos.y - 29   // center: height/2
      }
    };
  });
};

// ── Root Module Detection (Option C) ──────────────────
const detectRootModule = (moduleNodes) => {
  if (moduleNodes.length < 2) return null;
  
  const ids = moduleNodes.map(m => m.id);
  
  // প্রতিটা module check করো — সে কি অন্য সবার prefix?
  for (const candidate of ids) {
    const prefix = candidate + '/';
    const isRootOf = ids.filter(id => id !== candidate).every(id => id.startsWith(prefix));
    if (isRootOf) return candidate;
  }
  return null;
};

const getOrphanFiles = (allTier2Files, subModuleIds) => {
  // যে files কোনো sub-module-এর অধীনে নয়
  return allTier2Files.filter(f => {
    return !subModuleIds.some(modId => f.id.startsWith(modId + '/'));
  });
};

// Virtual "Root Files" node ID
const ROOT_FILES_VIRTUAL_ID = '__root_files__';

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
  const {
    label, fullLabel, nodeType = 'module', callCount = 0, isRoot = false,
    language, riskLevel = 'none', fanIn = 0, isDead = false, deadConfidence = 'none',
    violationCount = 0, violationSeverity = 'none', smellSeverity = 'none'
  } = opts;
  return {
    id,
    type: 'functionNode',
    data: {
      label: label || getDisplayLabel(fullLabel || id, nodeType),
      fullLabel: fullLabel || id,
      callCount,
      nodeType,
      language,
      isRoot,
      riskLevel,
      fanIn,
      isDead,
      deadConfidence,
      violationCount,
      violationSeverity,
      smellSeverity,
    },
    position,
    sourcePosition: Position.Bottom,
    targetPosition: Position.Top,
    style: {
      width: '170px',
      height: '58px',
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

  // ── Option C: detect & strip root module ──
  const rootModuleId = detectRootModule(moduleNodes);
  const visibleModules = rootModuleId
    ? moduleNodes.filter(m => m.id !== rootModuleId)
    : moduleNodes;

  // Root module-এর orphan files fetch করো (background)
  let orphanFiles = [];
  if (rootModuleId) {
    try {
      const t2Res = await sessionManager.apiCall(`/graph/tier2/${encodeURIComponent(rootModuleId)}`, { method: 'GET' });
      const t2 = await t2Res.json();
      const subModuleIds = visibleModules.map(m => m.id);
      orphanFiles = getOrphanFiles(t2.nodes || [], subModuleIds);
    } catch (_) { /* ignore, no orphan files node */ }
  }

  const mixedNodes = [];
  const totalCols = visibleModules.length + (orphanFiles.length > 0 ? 1 : 0);

  // Sub-modules layout
  visibleModules.forEach((m, index) => {
    const viol = layerViolations.value?.by_module?.[m.id] || null;
    mixedNodes.push(
      createNode(
        m.id,
        { x: index * 300 - ((totalCols - 1) * 150), y: 0 },
        {
          fullLabel: m.label || m.id,
          nodeType: 'module',
          language: (m.languages && m.languages[0]) || null,
          violationCount: viol?.count || 0,
          violationSeverity: viol?.severity || 'none',
        }
      )
    );
  });

  // "Root Files" virtual node (যদি orphan files থাকে)
  if (orphanFiles.length > 0) {
    const rfIndex = visibleModules.length;
    mixedNodes.push(
      createNode(
        ROOT_FILES_VIRTUAL_ID,
        { x: rfIndex * 300 - ((totalCols - 1) * 150), y: 0 },
        {
          label: `Root Files`,
          fullLabel: `Root Files (${orphanFiles.length})`,
          nodeType: 'rootfiles',
          language: null
        }
      )
    );
    // orphan files data store করো পরে click-এ লাগবে
    window.__orphanFiles = orphanFiles;
  }

  // tier1 edges — root module involve করা edges বাদ দাও
  const filteredEdges = (tier1.edges || []).filter(e =>
    e.source !== rootModuleId && e.target !== rootModuleId
  );

  // file nodes (যদি tier1-এ থাকে)
  fileNodes.forEach((f, index) => {
    mixedNodes.push(
      createNode(f.id, { x: index * 210 - ((fileNodes.length - 1) * 105), y: 180 },
        { fullLabel: f.id, nodeType: 'file', language: f.language })
    );
  });
  // ── Dagre layout apply করো ──
  const layoutedNodes = applyDagreLayout(mixedNodes, filteredEdges, { rankdir: 'LR', nodesep: 80, ranksep: 180 });
  nodes.value = layoutedNodes;
  edges.value = toVueFlowEdges(filteredEdges, layoutedNodes);  // ← mixedNodes এর বদলে layoutedNodes
  // nodes.value = mixedNodes;
  // edges.value = toVueFlowEdges(filteredEdges, mixedNodes);
  expandedNodes.value.clear();
  nodeLevelMap.value.clear();
  layoutedNodes.forEach((n) => nodeLevelMap.value.set(n.id, 0));
  navStack.value = [];
  currentLabel.value = 'Modules';
  await nextTick();
  fitView({ padding: 0.45, duration: 300, maxZoom: 0.95 });
};

const renderModuleRoot = async (moduleNodes) => {
  // moduleNodes: [{ id, loc, fn_count, languages }]
  nodes.value = moduleNodes.map((m, i) => {
    const viol = layerViolations.value?.by_module?.[m.id] || null;
    return createNode(
      m.id,
      { x: i * 210 - ((moduleNodes.length - 1) * 105), y: 0 },
      {
        fullLabel: m.id, nodeType: 'module',
        language: (m.languages && m.languages[0]) || null,
        violationCount: viol?.count || 0,
        violationSeverity: viol?.severity || 'none',
      }
    );
  });
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

// Fetch all analysis sidebar panels (risk, dead code, metrics, git, layers).
// Called from both single-file and multi-file upload paths.
const fetchLLMPlan = async () => {
  llmLoading.value = true;
  llmPlan.value = null;
  try {
    const res  = await sessionManager.apiCall('/llm-refactor-reason', { method: 'POST' });
    const data = await res.json();
    llmPlan.value = data.llm_plan;
  } catch (e) {
    llmPlan.value = { _error: e.message || 'LLM request failed', _source: 'error' };
  } finally {
    llmLoading.value = false;
  }
};

const fetchAnalysisPanels = async (isSingleFile, sourceName) => {
  try {
    const isFolder = !isSingleFile || sourceName.toLowerCase().endsWith('.zip');
    const requests = [
      sessionManager.apiCall('/risk-score',    { method: 'GET' }),
      sessionManager.apiCall('/dead-code',     { method: 'GET' }),
      sessionManager.apiCall('/metrics',       { method: 'GET' }),
      sessionManager.apiCall('/git-history',   { method: 'GET' }),
      sessionManager.apiCall('/smell-analysis',{ method: 'GET' }),
    ];
    if (isFolder) {
      requests.push(sessionManager.apiCall('/layer-violations', { method: 'GET' }));
    }
    const results = await Promise.all(requests);
    riskData.value     = await results[0].json();
    deadCodeData.value = await results[1].json();
    metricsData.value  = await results[2].json();
    const gh           = await results[3].json();
    gitHistory.value   = gh?.available ? gh : null;
    smellData.value    = await results[4].json();
    if (isFolder && results[5]) {
      layerViolations.value = await results[5].json();
    }
  } catch (_) { /* non-critical — panels stay hidden */ }
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
        await fetchAnalysisPanels(isSingleFile, sourceName);   // ← panels for single file
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
                      return createNode(fn.id, pos, { fullLabel: fn.label || fn.id, nodeType: fn.type === 'chunk' ? 'chunk' : 'function', language: fn.language, callCount: fn.fan_out });
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

    // fetch all analysis panels in background (non-critical)
    await fetchAnalysisPanels(isSingleFile, sourceName);
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

  // Deduplicate node IDs (safety net against backend sending duplicate IDs)
  const seenIds = new Set();
  const dedupedNodes = functionGraph.nodes.filter(n => {
    if (seenIds.has(n.id)) return false;
    seenIds.add(n.id);
    return true;
  });

  // Limit to MAX_TIER3_DISPLAY nodes — sort by most connected first
  const MAX_TIER3_DISPLAY = 300;
  const sortedNodes = [...dedupedNodes].sort(
    (a, b) => ((b.fan_in || 0) + (b.fan_out || 0)) - ((a.fan_in || 0) + (a.fan_out || 0))
  );
  const limitedNodes = sortedNodes.length > MAX_TIER3_DISPLAY
    ? sortedNodes.slice(0, MAX_TIER3_DISPLAY)
    : sortedNodes;
  const limitedIds = new Set(limitedNodes.map(n => n.id));
  functionGraph = {
    ...functionGraph,
    nodes: limitedNodes,
    edges: (functionGraph.edges || []).filter(e => limitedIds.has(e.source) && limitedIds.has(e.target))
  };

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
    return createNode(fn.id, pos, {
      fullLabel: fn.label || fn.id,
      nodeType: fn.type === 'chunk' ? 'chunk' : 'function',
      language: fn.language,
      callCount: fn.fan_out,
      riskLevel: fn.risk_level || 'none',
      fanIn: fn.fan_in || 0,
      isDead: fn.is_dead || false,
      deadConfidence: fn.dead_confidence || 'none',
      smellSeverity: smellSeverityMap.value[fn.label || fn.id] || 'none',
    });
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
  if (type === 'module' || type === 'rootfiles') {
    if (node.id === ROOT_FILES_VIRTUAL_ID) {
    const orphans = window.__orphanFiles || [];
    if (orphans.length === 0) return;
    pushNav('Root Files');
    const childNodes = orphans.map((f, index) => {
      const pos = getRootChildPosition(node, index, orphans.length);
      nodeLevelMap.value.set(f.id, 1);
      return createNode(f.id, pos, { fullLabel: f.id, nodeType: 'file', language: f.language });
    });
    nodes.value = [node, ...childNodes];
    edges.value = makeParentChildEdges(node, childNodes);
    expandedNodes.value.clear();
    expandedNodes.value.add(node.id);
    await nextTick();
    fitView({ padding: 0.5, duration: 250, maxZoom: 0.9 });
    return;
    }
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
    const allEdgesRaw = [...structuralEdges, ...peerEdges];

    // ← Dagre layout: module উপরে, files নিচে (TB = top to bottom)
    const layoutedNodes = applyDagreLayout([node, ...newChildNodes], res.edges, { rankdir: 'TB', nodesep: 60, ranksep: 140 });

    nodes.value = layoutedNodes;
    edges.value = toVueFlowEdges(allEdgesRaw, layoutedNodes);
    expandedNodes.value.clear();
    expandedNodes.value.add(node.id);
    nodeLevelMap.value.clear();
    layoutedNodes.forEach((n, i) => nodeLevelMap.value.set(n.id, n.id === node.id ? 0 : 1));

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
        newNodes.push(createNode(n.id, pos, { fullLabel: fnIdToLabel(n.id), nodeType: 'function' }));
      });

      rightSideNodes.forEach((n, index) => {
        const level = parentLevel + 1;
        const pos = getFunctionChildPosition(node, index, rightSideNodes.length, "right");
        nodeLevelMap.value.set(n.id, level);
        newNodes.push(createNode(n.id, pos, { fullLabel: fnIdToLabel(n.id), nodeType: 'function' }));
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

// name:line_start format থেকে display name বের করো (expand response এ label নেই)
const fnIdToLabel = (id) => {
  const lastColon = id.lastIndexOf(':');
  if (lastColon > 0 && /^\d+$/.test(id.slice(lastColon + 1))) {
    return id.slice(0, lastColon);
  }
  return id;
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
.legend-swatch.module          { background: #3b82f6; }
.legend-swatch.rootfiles       { background: #22c55e; }
.legend-swatch.file            { background: #f59e0b; }
.legend-swatch.function        { background: #10b981; }
.legend-swatch.chunk           { background: #8b5cf6; }
.legend-swatch.risk-high-swatch   { background: #ef4444; }
.legend-swatch.risk-medium-swatch { background: #f59e0b; }
.legend-swatch.risk-low-swatch    { background: #22c55e; }
.legend-swatch.dead-swatch        { background: #94a3b8; border-style: dashed; }
.legend-divider {
  width: 100%;
  height: 1px;
  background: #e2e8f0;
  margin: 4px 0;
}
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

/* ── Code Smell Panel ───────────────────────────────── */
.smell-panel { padding-bottom: 10px; }

.smell-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-bottom: 10px;
}
.smell-chip {
  padding: 3px 8px;
  border-radius: 12px;
  font-size: 10px;
  font-weight: 700;
  white-space: nowrap;
}
.smell-critical { background: #f3e8ff; color: #6b21a8; border: 1px solid #d8b4fe; }
.smell-high     { background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; }
.smell-medium   { background: #fef3c7; color: #92400e; border: 1px solid #fde68a; }
.smell-low      { background: #f0fdf4; color: #166534; border: 1px solid #86efac; }

.smell-list { display: flex; flex-direction: column; gap: 4px; margin-bottom: 10px; }

.smell-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 8px;
  border-radius: 8px;
  background: #f8fafc;
  border-left: 3px solid #cbd5e1;
  cursor: default;
}
.smell-sev-critical { border-left-color: #7c3aed; background: #faf5ff; }
.smell-sev-high     { border-left-color: #ef4444; background: #fef2f2; }
.smell-sev-medium   { border-left-color: #f59e0b; background: #fffbeb; }

.smell-item-icon  { font-size: 13px; flex-shrink: 0; }
.smell-item-body  { flex: 1; min-width: 0; }
.smell-item-type  {
  font-size: 11px; font-weight: 700; color: #1e293b;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  text-transform: capitalize;
}
.smell-item-target {
  font-size: 10px; color: #64748b; font-family: monospace;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.smell-item-score  { display: flex; flex-direction: column; align-items: flex-end; flex-shrink: 0; }
.smell-score-val   { font-size: 13px; font-weight: 800; color: #334155; font-family: monospace; }
.smell-score-label { font-size: 9px; color: #94a3b8; }

/* LLM button */
.smell-llm-btn {
  width: 100%;
  padding: 8px 0;
  border-radius: 10px;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  border: none;
  cursor: pointer;
  transition: opacity 140ms, transform 140ms;
  margin-bottom: 8px;
}
.smell-llm-btn:hover:not(:disabled) { opacity: 0.9; transform: translateY(-1px); }
.smell-llm-btn:disabled { opacity: 0.65; cursor: wait; }
.smell-llm-btn-loading { background: #94a3b8; }

/* LLM plan box */
.llm-plan-box {
  background: #0f172a;
  border-radius: 10px;
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.llm-plan-source {
  font-size: 9px;
  color: #6366f1;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.llm-exec-summary {
  font-size: 11px;
  color: #cbd5e1;
  line-height: 1.5;
  border-left: 3px solid #6366f1;
  padding-left: 8px;
}
.llm-root-cause {
  font-size: 10px;
  color: #f87171;
  padding: 4px 8px;
  background: rgba(239,68,68,0.1);
  border-radius: 6px;
}
.llm-root-cause strong { color: #fca5a5; }

/* Refactor steps */
.llm-steps { display: flex; flex-direction: column; gap: 5px; }
.llm-step {
  border-radius: 8px;
  padding: 7px 9px;
  background: #1e293b;
  border-left: 3px solid #475569;
}
.llm-step-high   { border-left-color: #ef4444; }
.llm-step-medium { border-left-color: #f59e0b; }
.llm-step-low    { border-left-color: #22c55e; }

.llm-step-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 3px;
}
.llm-step-num {
  font-size: 10px;
  font-weight: 800;
  color: #94a3b8;
  background: #334155;
  padding: 1px 5px;
  border-radius: 4px;
  flex-shrink: 0;
}
.llm-step-pattern {
  font-size: 11px;
  font-weight: 700;
  color: #e2e8f0;
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.llm-step-effort {
  font-size: 9px;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 8px;
  flex-shrink: 0;
}
.effort-high   { background: #fef2f2; color: #991b1b; }
.effort-medium { background: #fef3c7; color: #92400e; }
.effort-low    { background: #f0fdf4; color: #166534; }

.llm-step-target  { font-size: 10px; color: #7dd3fc; font-family: monospace; margin-bottom: 2px; }
.llm-step-what    { font-size: 10px; color: #94a3b8; line-height: 1.4; }
.llm-step-why     { font-size: 10px; color: #4ade80; line-height: 1.4; margin-top: 2px; font-style: italic; }
.llm-step-resolves {
  font-size: 9px; color: #64748b; margin-top: 3px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

.llm-longterm {
  font-size: 10px;
  color: #fbbf24;
  line-height: 1.5;
  padding: 5px 8px;
  background: rgba(251,191,36,0.08);
  border-radius: 6px;
}
.llm-longterm strong { color: #fde68a; }
.llm-error {
  font-size: 10px;
  color: #f87171;
  padding: 4px 8px;
  background: rgba(239,68,68,0.1);
  border-radius: 6px;
}

/* ── Dependency Risk Panel ─────────────────────────── */
.risk-panel { padding-bottom: 12px; }

.risk-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}
.risk-chip {
  padding: 3px 8px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 700;
  white-space: nowrap;
}
.risk-chip-high   { background: #fee2e2; color: #b91c1c; }
.risk-chip-medium { background: #fef3c7; color: #92400e; }
.risk-chip-low    { background: #dcfce7; color: #166534; }

.risk-list {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.risk-item {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 8px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  cursor: default;
  transition: background 120ms;
}
.risk-item:hover { background: #f1f5f9; }
.risk-item-high   { border-left: 3px solid #ef4444; }
.risk-item-medium { border-left: 3px solid #f59e0b; }
.risk-item-low    { border-left: 3px solid #22c55e; }

.risk-item-icon { font-size: 12px; flex-shrink: 0; margin-top: 1px; }

.risk-item-body { flex: 1; min-width: 0; }
.risk-item-name {
  font-size: 12px;
  font-weight: 700;
  color: #1e293b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.risk-item-warn {
  font-size: 10px;
  color: #64748b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.risk-item-count {
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 800;
  color: #475569;
  background: #e2e8f0;
  border-radius: 10px;
  padding: 1px 6px;
  margin-top: 1px;
}

.risk-empty {
  font-size: 12px;
  color: #94a3b8;
  text-align: center;
  padding: 8px 0;
}

/* ── Potentially Unreachable Panel ──────────────── */
.dead-panel { padding-bottom: 12px; }

.dead-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-bottom: 8px;
}
.dead-chip {
  padding: 3px 7px;
  border-radius: 12px;
  font-size: 10px;
  font-weight: 700;
  white-space: nowrap;
}
.dead-chip-high { background: #f1f5f9; color: #334155; }
.dead-chip-medium { background: #f8fafc; color: #64748b; }
.dead-chip-imp  { background: #fef9c3; color: #854d0e; }

.dead-section-label {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #94a3b8;
  margin-bottom: 4px;
}

.dead-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.dead-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 8px;
  border-radius: 8px;
  background: #f8fafc;
  border: 1px dashed #cbd5e1;
  cursor: default;
  transition: background 120ms;
}
.dead-item:hover { background: #f1f5f9; }
/* high confidence: darker dashed border */
.dead-item-high   { border-color: #94a3b8; background: #f1f5f9; }
.dead-item-high:hover { background: #e2e8f0; }
/* medium confidence: lighter */
.dead-item-medium { border-color: #cbd5e1; }
.dead-import-item { border-color: #fde68a; background: #fffbeb; }
.dead-import-item:hover { background: #fef3c7; }

.dead-item-icon { font-size: 12px; flex-shrink: 0; }

.dead-item-body { flex: 1; min-width: 0; }
.dead-item-name {
  font-size: 12px;
  font-weight: 700;
  color: #64748b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-decoration: line-through;
}
.dead-item-file {
  font-size: 10px;
  color: #94a3b8;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: monospace;
}

/* confidence badge */
.dead-conf-badge {
  flex-shrink: 0;
  font-size: 9px;
  font-weight: 800;
  padding: 1px 5px;
  border-radius: 8px;
  letter-spacing: 0.03em;
}
.conf-high { background: #e2e8f0; color: #334155; }
.conf-med  { background: #f1f5f9; color: #64748b; }

/* static analysis disclaimer */
.dead-note {
  margin-top: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  background: #fefce8;
  border: 1px solid #fde68a;
  font-size: 10px;
  color: #78350f;
  line-height: 1.5;
}

/* ── Layer Analysis Panel ───────────────────────── */
.layer-panel { padding-bottom: 12px; }

.layer-clean {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 10px;
  background: #f0fdf4;
  border: 1px solid #86efac;
}
.layer-clean-icon { font-size: 18px; flex-shrink: 0; margin-top: 1px; }
.layer-clean-title {
  font-size: 12px;
  font-weight: 700;
  color: #166534;
  line-height: 1.3;
}
.layer-clean-sub {
  font-size: 10px;
  color: #4ade80;
  margin-top: 2px;
  line-height: 1.4;
  color: #15803d;
}

.layer-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-bottom: 8px;
}
.layer-chip {
  padding: 3px 8px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 700;
  white-space: nowrap;
}
.layer-chip-high   { background: #fee2e2; color: #991b1b; }
.layer-chip-medium { background: #fef3c7; color: #92400e; }

.layer-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.layer-item {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 5px 8px;
  border-radius: 8px;
  background: #f8fafc;
  border-left: 3px solid transparent;
}
.layer-item-high   { border-left-color: #ef4444; background: #fef2f2; }
.layer-item-medium { border-left-color: #f59e0b; background: #fffbeb; }

.layer-item-icon { font-size: 12px; flex-shrink: 0; margin-top: 1px; }
.layer-item-body { flex: 1; min-width: 0; }
.layer-item-msg {
  font-size: 11px;
  font-weight: 600;
  color: #1e293b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.3;
}
.layer-item-src {
  font-size: 10px;
  color: #94a3b8;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: monospace;
  margin-top: 1px;
}

/* ── Integrated Metrics Dashboard ───────────────── */
.metrics-panel { padding-bottom: 10px; }

.metrics-grid {
  background: #0f172a;
  border-radius: 10px;
  padding: 6px 0;
  overflow: hidden;
}
.mrow {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 12px;
  gap: 8px;
}
.mrow:hover { background: rgba(255,255,255,0.04); }
.mrow-sep {
  height: 1px;
  background: rgba(255,255,255,0.07);
  padding: 0;
  margin: 2px 0;
}
.mlabel {
  font-size: 11px;
  color: #94a3b8;
  white-space: nowrap;
  flex-shrink: 0;
}
.mval {
  font-size: 12px;
  font-weight: 700;
  color: #e2e8f0;
  font-family: 'JetBrains Mono', 'Fira Mono', monospace;
  text-align: right;
  white-space: nowrap;
}
.mv-ok      { color: #4ade80; }
.mv-caution { color: #fbbf24; }
.mv-warn    { color: #f87171; }

.mi-val { display: flex; flex-direction: column; align-items: flex-end; gap: 1px; }
.mi-label { font-size: 9px; font-weight: 500; color: #64748b; font-family: inherit; }

.circ-details {
  margin-top: 8px;
  background: #1e1e2e;
  border-radius: 8px;
  padding: 6px 8px;
}
.circ-chain {
  font-size: 10px;
  color: #f87171;
  font-family: monospace;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding: 1px 0;
}

/* ── Git History Panel ───────────────────────────── */
.git-panel { padding-bottom: 10px; }

.git-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.git-branch {
  font-size: 11px;
  font-weight: 700;
  color: #4ade80;
  background: #052e16;
  padding: 2px 8px;
  border-radius: 10px;
  border: 1px solid #166534;
}
.git-total {
  font-size: 11px;
  color: #64748b;
  font-weight: 600;
}

.git-list {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.git-item {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  padding: 5px 8px;
  border-radius: 7px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  cursor: default;
  transition: background 100ms;
}
.git-item:hover { background: #f1f5f9; }

.git-hash {
  font-size: 10px;
  font-family: monospace;
  font-weight: 700;
  color: #6366f1;
  background: #eef2ff;
  padding: 1px 5px;
  border-radius: 4px;
  flex-shrink: 0;
  margin-top: 1px;
}
.git-info { flex: 1; min-width: 0; }
.git-msg {
  font-size: 11px;
  font-weight: 600;
  color: #1e293b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.git-stat {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-top: 2px;
}
.git-date { font-size: 9px; color: #94a3b8; }
.git-diff { display: flex; gap: 4px; font-size: 10px; font-weight: 700; font-family: monospace; }
.git-ins  { color: #16a34a; }
.git-del  { color: #dc2626; }

.git-trend-header {
  display: flex;
  align-items: center;
  padding: 3px 8px 3px 6px;
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #94a3b8;
  margin-bottom: 2px;
}
.gth-commit { flex: 1; }
.gth-loc   { width: 44px; text-align: right; }
.gth-fns   { width: 32px; text-align: right; }
.gth-delta { width: 38px; text-align: right; margin-left: 2px; }

.git-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 6px;
  border-radius: 7px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  cursor: default;
  transition: background 100ms;
}
.git-item:hover { background: #f1f5f9; }

.git-left {
  flex: 1;
  display: flex;
  align-items: flex-start;
  gap: 6px;
  min-width: 0;
}
.git-hash {
  font-size: 10px;
  font-family: monospace;
  font-weight: 700;
  color: #6366f1;
  background: #eef2ff;
  padding: 1px 5px;
  border-radius: 4px;
  flex-shrink: 0;
  margin-top: 1px;
}
.git-info { flex: 1; min-width: 0; }
.git-msg {
  font-size: 11px;
  font-weight: 600;
  color: #1e293b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.git-date { font-size: 9px; color: #94a3b8; }

.git-metrics-col {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}
.git-loc-val {
  font-size: 10px;
  font-weight: 700;
  color: #334155;
  font-family: monospace;
  width: 44px;
  text-align: right;
}
.git-fns-val {
  font-size: 10px;
  font-weight: 700;
  color: #6366f1;
  font-family: monospace;
  width: 32px;
  text-align: right;
}
.git-delta-val {
  font-size: 10px;
  font-weight: 700;
  font-family: monospace;
  width: 38px;
  text-align: right;
}
.delta-pos  { color: #16a34a; }
.delta-neg  { color: #dc2626; }
.delta-zero { color: #94a3b8; }

.git-note {
  margin-top: 6px;
  font-size: 9.5px;
  color: #94a3b8;
  line-height: 1.5;
  font-style: italic;
}

/* ── Git "How to Enable" hint panel ─────────────── */
.git-hint-panel { padding-bottom: 12px; }

.git-hint-box {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 8px 10px;
  border-radius: 10px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  margin-bottom: 10px;
}
.git-hint-icon { font-size: 20px; flex-shrink: 0; }
.git-hint-title {
  font-size: 12px;
  font-weight: 700;
  color: #334155;
  margin-bottom: 3px;
}
.git-hint-sub {
  font-size: 10px;
  color: #64748b;
  line-height: 1.5;
}
.git-hint-sub code, .git-how-alt code {
  background: #e2e8f0;
  padding: 1px 4px;
  border-radius: 3px;
  font-family: monospace;
  font-size: 10px;
  color: #334155;
}

.git-how-steps-wrap {
  padding: 8px 10px;
  border-radius: 10px;
  background: #fffbeb;
  border: 1px solid #fde68a;
}
.git-how-label {
  font-size: 10px;
  font-weight: 700;
  color: #92400e;
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.git-how-steps {
  margin: 0 0 8px 0;
  padding-left: 16px;
}
.git-how-steps li {
  font-size: 11px;
  color: #78350f;
  line-height: 1.7;
}
.git-how-steps strong { color: #451a03; }
.git-how-alt {
  font-size: 10px;
  color: #78350f;
  line-height: 1.6;
  background: rgba(0,0,0,0.04);
  padding: 5px 8px;
  border-radius: 6px;
}
</style>
