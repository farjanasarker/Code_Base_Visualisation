<template>
  <div class="graph-container">

    <!-- ── Sidebar ─────────────────────────────────── -->
    <aside class="sidebar" :style="{ width: sidebarWidth + 'px', minWidth: sidebarWidth + 'px' }">
      <!-- Brand -->
      <div class="sidebar-brand">
        <span class="brand-icon">⬡</span>
        <div>
          <div class="brand-name">CodeLens</div>
          <div class="brand-sub">Codebase Visualizer</div>
        </div>
      </div>

      <!-- Back navigation -->
      <div v-if="navStack.length > 0" class="sidebar-section sidebar-back-sticky">
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

      <!-- Onboarding: what this tool does, shown until the first upload -->
      <div v-if="!uploadedFile" class="sidebar-section onboarding-panel">
        <div class="section-title">Get Started</div>
        <div class="section-subtitle">CodeLens turns your source code into an explorable map — structure, quality issues, and design patterns, all in one place.</div>
        <ol class="onboarding-steps">
          <li><strong>Upload</strong> — a source file, ZIP, or folder</li>
          <li><strong>Analyze</strong> — CodeLens builds the call graph, metrics, and pattern report automatically</li>
          <li><strong>Explore</strong> — click any node to drill in, hover to trace impact</li>
        </ol>
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

        <!-- Upload Progress -->
        <div v-if="uploading && uploadStage" class="upload-progress-wrap">
          <div class="upload-stage-text">{{ uploadStage }}</div>
          <div class="upload-progress-track">
            <div class="upload-progress-fill"></div>
          </div>
        </div>
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

      <!-- Search -->
      <div v-if="uploadSuccess" class="sidebar-section">
        <div class="section-title">Search</div>
        <div class="search-wrap">
          <input
            v-model="searchQuery"
            @input="performSearch(searchQuery)"
            @blur="setTimeout(() => { showSearchDropdown = false }, 200)"
            @focus="showSearchDropdown = searchResults.length > 0"
            placeholder="🔍 Functions, files..."
            class="search-input"
          />
          <div v-if="showSearchDropdown" class="search-dropdown">
            <div
              v-for="r in searchResults"
              :key="r.id + r.file"
              @mousedown.prevent="focusSearchResult(r)"
              class="search-result-item"
            >
              <span class="search-result-icon" :class="r.type">
                {{ r.type === 'function' ? 'ƒ' : r.type === 'file' ? '◫' : '⬡' }}
              </span>
              <div class="search-result-body">
                <div class="search-result-name">{{ r.label }}</div>
                <div v-if="r.file" class="search-result-file">{{ r.file }}</div>
              </div>
              <span v-if="r.risk && r.risk !== 'none'" class="search-risk-badge" :class="'risk-' + r.risk">
                {{ r.risk === 'high' ? 'H' : r.risk === 'medium' ? 'M' : 'L' }}
              </span>
              <span v-if="!r.inGraph" title="Not in current view" class="search-not-visible">◌</span>
            </div>
          </div>
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

      <!-- ── Sidebar Tabs ──────────────────────────────────── -->
      <div v-if="uploadSuccess" class="sidebar-tabs" role="tablist">
        <button
          v-for="t in sidebarTabs" :key="t.id"
          class="sidebar-tab" :class="{ active: activeSidebarTab === t.id }"
          role="tab" :aria-selected="activeSidebarTab === t.id"
          @click="activeSidebarTab = t.id"
        >{{ t.label }}</button>
      </div>

      <div v-show="activeSidebarTab === 'overview'">
      <!-- ── Integrated Metrics Dashboard ──────────────────── -->
      <div v-if="metricsData && metricsData.total_functions != null" class="sidebar-section metrics-panel">
        <div class="section-title">Code Metrics</div>
        <div class="section-subtitle">Quick health check — high complexity or low maintainability usually means harder, riskier changes ahead.</div>
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
        <div class="section-subtitle">See whether code quality is trending better or worse as the project evolves.</div>
        <div class="git-meta">
          <span class="git-branch">🌿 {{ gitHistory.current_branch }}</span>
          <span class="git-total">{{ gitHistory.total_commits }} commits</span>
        </div>

        <!-- Quality snapshot (current snapshot metrics) -->
        <div v-if="metricsData" class="git-quality-bar">
          <div class="gq-item" title="Maintainability Index (0–100, higher = better)">
            <span class="gq-label">MI</span>
            <span class="gq-val" :class="metricsData.maintainability_index >= 65 ? 'gq-ok' : metricsData.maintainability_index >= 40 ? 'gq-caution' : 'gq-warn'">
              {{ metricsData.maintainability_index }}
            </span>
            <span class="gq-sub">{{ metricsData.maintainability_label }}</span>
          </div>
          <div class="gq-divider"></div>
          <div class="gq-item" title="Average Cyclomatic Complexity (lower = simpler)">
            <span class="gq-label">Cyclo CC</span>
            <span class="gq-val" :class="metricsData.avg_cyclomatic > 10 ? 'gq-warn' : metricsData.avg_cyclomatic > 5 ? 'gq-caution' : 'gq-ok'">
              {{ metricsData.avg_cyclomatic }}
            </span>
          </div>
          <div class="gq-divider"></div>
          <div class="gq-item" title="Cognitive Complexity (lower = easier to read)">
            <span class="gq-label">Cognitive</span>
            <span class="gq-val" :class="metricsData.cognitive_complexity > 15 ? 'gq-warn' : metricsData.cognitive_complexity > 8 ? 'gq-caution' : 'gq-ok'">
              {{ metricsData.cognitive_complexity }}
            </span>
          </div>
        </div>

        <!-- Column headers -->
        <div class="git-trend-header">
          <span class="gth-commit">Commit</span>
          <span class="gth-loc">LOC</span>
          <span class="gth-fns">Fns</span>
          <span class="gth-mi" title="Estimated Maintainability Index (0–100)">MI</span>
          <span class="gth-delta" title="Δ LOC = net lines added/removed (insertions − deletions)">Δ LOC</span>
        </div>

        <div class="git-list">
          <div
            v-for="c in gitCommitsPage"
            :key="c.hash"
            class="git-item"
            :title="`${c.message}\nAuthor: ${c.author}\nFiles changed: ${c.files_changed}\nChurn (ins+del): ${c.churn}`"
          >
            <div class="git-left">
              <span class="git-hash">{{ c.hash }}</span>
              <div class="git-info">
                <div class="git-msg">{{ c.message }}</div>
                <div class="git-meta-row">
                  <span class="git-date">{{ c.date }}</span>
                  <span class="git-churn" :class="c.churn > 200 ? 'churn-high' : c.churn > 50 ? 'churn-med' : 'churn-low'"
                    title="Code churn (insertions + deletions) — higher = more volatile">
                    ⚡{{ c.churn }}
                  </span>
                  <span class="git-files" title="Files changed">📄{{ c.files_changed }}</span>
                </div>
              </div>
            </div>
            <!-- Metrics columns -->
            <div class="git-metrics-col">
              <span class="git-loc-val">{{ c.estimatedLoc.toLocaleString() }}</span>
              <span class="git-fns-val">{{ c.estimatedFns }}</span>
              <span class="git-mi-val" :class="c.estimatedMi >= 65 ? 'mi-ok' : c.estimatedMi >= 40 ? 'mi-caution' : 'mi-warn'">
                {{ c.estimatedMi }}
              </span>
              <span class="git-delta-val"
                :class="c.netDelta > 0 ? 'delta-pos' : c.netDelta < 0 ? 'delta-neg' : 'delta-zero'">
                {{ c.netDelta > 0 ? '+' : '' }}{{ c.netDelta }}
              </span>
            </div>
          </div>
        </div>

        <!-- Pagination -->
        <div class="git-pagination" v-if="gitCommitsWithLoc.length > 10">
          <button v-if="gitPageSize < gitCommitsWithLoc.length"
            class="git-page-btn"
            @click="gitPageSize = Math.min(gitPageSize + 10, gitCommitsWithLoc.length)">
            Show more ({{ gitCommitsWithLoc.length - gitPageSize }} remaining)
          </button>
          <button v-if="gitPageSize > 10"
            class="git-page-btn git-page-less"
            @click="gitPageSize = 10">
            Show less
          </button>
        </div>

        <div class="git-note">
          LOC, Fns, MI estimated backwards from current snapshot. Churn = lines inserted + deleted per commit.
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
      </div>

      <div v-show="activeSidebarTab === 'quality'">
      <!-- ── Code Smell Analysis Panel ──────────────────────────── -->
      <div v-if="smellData && smellData.summary?.total > 0" class="sidebar-section smell-panel">
        <div class="section-title">Code Smell Analysis</div>
        <div class="section-subtitle">The concrete things worth fixing first, ranked by effort vs. payoff.</div>

        <!-- Severity summary chips -->
        <div class="smell-summary">
          <span v-if="smellData.summary.critical" class="smell-chip smell-critical">💀 {{ smellData.summary.critical }} Critical</span>
          <span v-if="smellData.summary.high"     class="smell-chip smell-high">🔴 {{ smellData.summary.high }} High</span>
          <span v-if="smellData.summary.medium"   class="smell-chip smell-medium">🟡 {{ smellData.summary.medium }} Med</span>
          <span v-if="smellData.summary.low"      class="smell-chip smell-low">🟢 {{ smellData.summary.low }} Low</span>
        </div>

        <!-- Feature 1: Technical debt estimate -->
        <div v-if="smellData.total_debt_score != null" class="debt-stats">
          <div class="debt-stat">
            <span class="debt-stat-value">{{ smellData.total_debt_score }}</span>
            <span class="debt-stat-label">Debt Score</span>
          </div>
          <div class="debt-stat">
            <span class="debt-stat-value">{{ smellData.estimated_dev_days }}</span>
            <span class="debt-stat-label">Est. Dev Days</span>
          </div>
        </div>

        <!-- View mode tabs -->
        <div class="smell-tabs">
          <button class="smell-tab" :class="{ active: smellViewMode === 'files' }" @click="smellViewMode = 'files'">Files</button>
          <button class="smell-tab" :class="{ active: smellViewMode === 'plan' }" @click="smellViewMode = 'plan'">ROI Plan</button>
          <button class="smell-tab" :class="{ active: smellViewMode === 'layers' }" @click="smellViewMode = 'layers'">By Layer</button>
          <button class="smell-tab" :class="{ active: smellViewMode === 'tree' }" @click="smellViewMode = 'tree'">Fix Tree</button>
        </div>

        <!-- ── Files tab (existing type distribution + ranked files + detail) ── -->
        <template v-if="smellViewMode === 'files'">
          <div class="dead-section-label">Top Root Smells</div>
          <div class="smell-type-list">
            <div v-for="(t, i) in smellTypeDistribution" :key="t.type" class="smell-type-row">
              <span class="smell-type-rank">{{ i + 1 }}.</span>
              <span class="smell-type-name">{{ t.type.replace(/_/g, ' ') }}</span>
              <span class="smell-type-count">({{ t.count }})</span>
            </div>
          </div>

          <template v-if="!selectedSmellFile">
            <div class="dead-section-label" style="margin-top:10px">Ranked Files</div>
            <div class="smell-file-list">
              <div
                v-for="(f, i) in smellFileRanking"
                :key="f.file"
                class="smell-file-row"
                @click="selectedSmellFile = f.file"
              >
                <span class="smell-file-rank">{{ i + 1 }}.</span>
                <div class="smell-file-body">
                  <div class="smell-file-name">{{ f.file.split(/[/\\]/).pop() }}</div>
                  <div class="smell-file-meta">Score: <strong>{{ f.score }}</strong> &nbsp;·&nbsp; Smells: <strong>{{ f.count }}</strong></div>
                </div>
                <span class="smell-file-arrow">›</span>
              </div>
            </div>
          </template>

          <template v-else>
            <div class="smell-detail-header">
              <button class="smell-back-btn" @click="selectedSmellFile = null">← Back</button>
              <span class="smell-detail-filename">{{ selectedSmellFile.split(/[/\\]/).pop() }}</span>
            </div>
            <div class="smell-detail-list">
              <div
                v-for="s in selectedFileSmells"
                :key="s.smell_id"
                class="smell-detail-item"
                :class="`smell-sev-${s.severity}`"
              >
                <span class="smell-detail-icon">{{ s.severity === 'critical' ? '💀' : s.severity === 'high' ? '🔴' : s.severity === 'medium' ? '🟡' : '🟢' }}</span>
                <div class="smell-detail-body">
                  <div class="smell-item-type">{{ s.type.replace(/_/g, ' ') }}</div>
                  <div class="smell-item-target">{{ s.target_name }}</div>
                </div>
                <span class="smell-sev-badge" :class="`sev-badge-${s.severity}`">{{ s.severity }}</span>
              </div>
            </div>
          </template>
        </template>

        <!-- ── Feature 1 & 2: ROI-ranked refactor plan + before/after preview ── -->
        <template v-else-if="smellViewMode === 'plan'">
          <div class="dead-section-label">Refactor Plan (ranked by ROI = resolves / effort)</div>
          <div class="roi-plan-list">
            <div
              v-for="item in smellRoiPlan"
              :key="item.smell_id"
              class="roi-plan-item"
              :class="`smell-sev-${item.severity}`"
            >
              <div class="roi-plan-head">
                <span class="roi-plan-step">#{{ item.step }}</span>
                <span class="smell-item-type" style="flex:1">{{ item.type.replace(/_/g, ' ') }}</span>
                <span class="smell-sev-badge" :class="`sev-badge-${item.severity}`">{{ item.severity }}</span>
              </div>
              <div class="smell-item-target">{{ item.target_name }}</div>
              <div class="roi-plan-meta">
                <span>Effort: <strong>{{ item.effort }}</strong></span>
                <span>Resolves: <strong>{{ item.resolves_count }}</strong></span>
                <span>ROI: <strong>{{ item.roi_score }}</strong></span>
              </div>
              <div v-if="item.description" class="roi-plan-desc">{{ item.description }}</div>
              <div v-if="item.refactor_suggestions?.length" class="roi-plan-suggestions">
                {{ item.refactor_suggestions.join(' · ') }}
              </div>
              <button
                v-if="item.code_preview"
                class="roi-preview-toggle"
                @click="togglePreview(item.smell_id)"
              >
                {{ expandedPreviews[item.smell_id] ? '▾ Hide before/after' : '▸ View before/after' }}
              </button>
              <div v-if="item.code_preview && expandedPreviews[item.smell_id]" class="code-preview-box">
                <div class="code-preview-col">
                  <div class="code-preview-label">Before</div>
                  <pre class="code-preview-pre">{{ item.code_preview.before }}</pre>
                </div>
                <div class="code-preview-col">
                  <div class="code-preview-label">After</div>
                  <pre class="code-preview-pre">{{ item.code_preview.after }}</pre>
                </div>
                <div v-if="item.code_preview.explanation" class="code-preview-explanation">
                  💡 {{ item.code_preview.explanation }}
                </div>
              </div>
            </div>
            <div v-if="!smellRoiPlan.length" class="smell-empty-note">No plan items available.</div>
          </div>
        </template>

        <!-- ── Feature 3: Smells grouped by architecture layer ── -->
        <template v-else-if="smellViewMode === 'layers'">
          <div class="layer-accordion">
            <div v-for="[layerName, layerSmells] in smellLayerEntries" :key="layerName" class="layer-group">
              <div class="layer-header" @click="toggleLayer(layerName)">
                <span class="tree-toggle">{{ expandedLayers[layerName] ? '▾' : '▸' }}</span>
                <span class="layer-name">{{ layerName }}</span>
                <span class="layer-count">{{ layerSmells.length }}</span>
              </div>
              <div v-if="expandedLayers[layerName]" class="smell-detail-list" style="margin-top:4px">
                <div
                  v-for="s in layerSmells"
                  :key="s.smell_id"
                  class="smell-detail-item"
                  :class="`smell-sev-${s.severity}`"
                >
                  <span class="smell-detail-icon">{{ s.severity === 'critical' ? '💀' : s.severity === 'high' ? '🔴' : s.severity === 'medium' ? '🟡' : '🟢' }}</span>
                  <div class="smell-detail-body">
                    <div class="smell-item-type">{{ s.type.replace(/_/g, ' ') }}</div>
                    <div class="smell-item-target">{{ s.target_name }}</div>
                  </div>
                  <span class="smell-sev-badge" :class="`sev-badge-${s.severity}`">{{ s.severity }}</span>
                </div>
                <div v-if="!layerSmells.length" class="smell-empty-note">No smells at this layer.</div>
              </div>
            </div>
          </div>
        </template>

        <!-- ── Feature 4: Dependency-aware fix tree ── -->
        <template v-else-if="smellViewMode === 'tree'">
          <div class="dead-section-label">Upstream → Downstream Causation</div>
          <div class="fix-tree-container">
            <FixTreeNode
              v-for="(root, i) in smellData.fix_tree"
              :key="`${root.smell_id}-${i}`"
              :node="root"
            />
            <div v-if="!smellData.fix_tree?.length" class="smell-empty-note">No causation chains detected.</div>
          </div>
        </template>

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
        <div class="section-subtitle">Functions many other things depend on — breaking these has the widest blast radius.</div>

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
        <div v-else class="risk-empty">No high-risk dependencies found — no function has 10+ callers. That's a good sign for decoupling.</div>
      </div>

      <!-- Potentially Unreachable Panel -->
      <div v-if="deadCodeData" class="sidebar-section dead-panel">
        <div class="section-title">Potentially Unreachable</div>
        <div class="section-subtitle">Code that looks unused — candidates to double-check and safely delete.</div>

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
              <div class="dead-item-name" style="text-decoration:none;color:#fbbf24">{{ entry.file.split('/').pop() }}</div>
              <div class="dead-item-file">{{ entry.unused.join(', ') }}</div>
            </div>
          </div>
        </div>

        <div v-if="!deadCodeData.unreachable_functions?.length && !deadCodeData.unused_imports?.length" class="risk-empty">
          No potentially unreachable code found — every function and import appears to be in use.
        </div>

        <!-- Static analysis disclaimer -->
        <div class="dead-note">
          ⚠ Static analysis only. Cross-file calls within this upload are handled.
          Dynamic calls, reflection, and external callers cannot be detected.
        </div>
      </div>
      </div>

      <div v-show="activeSidebarTab === 'architecture'">
      <!-- ── Architecture Patterns Panel ──────────────────────── -->
      <div v-if="patternsData && patternsData.patterns_found > 0" class="sidebar-section patterns-panel">
        <div class="section-title">Architecture Patterns</div>
        <div class="section-subtitle">How this codebase is organized at a high level, and whether that structure is holding up.</div>
        <div class="patterns-summary-chip">
          {{ patternsData.patterns_found }} pattern{{ patternsData.patterns_found !== 1 ? 's' : '' }} detected
        </div>
        <div class="patterns-list">
          <div v-for="p in patternsData.patterns" :key="p.pattern" class="pattern-card">
            <div class="pattern-card-head">
              <span class="pattern-name">{{ p.pattern }}</span>
              <span
                class="pattern-conf-badge"
                :class="p.confidence >= 0.8 ? 'pconf-high' : p.confidence >= 0.65 ? 'pconf-med' : 'pconf-low'"
              >
                {{ Math.round(p.confidence * 100) }}%
              </span>
            </div>
            <div v-if="p.evidence?.length" class="pattern-evidence">
              <div v-for="e in p.evidence" :key="e" class="pattern-evidence-item">· {{ e }}</div>
            </div>
            <div v-if="p.components && Object.keys(p.components).filter(k => p.components[k]?.length).length" class="pattern-components">
              <div class="pattern-components-label">Components</div>
              <template v-for="(files, layer) in p.components" :key="layer">
                <div v-if="files?.length" class="pattern-layer-row">
                  <span class="ptree-prefix">├──</span>
                  <span class="pattern-layer-name">{{ layer }}:</span>
                  <span class="pattern-layer-files" :title="files.join(', ')">
                    {{ files.map(f => f.split(/[\\/]/).pop()).slice(0, 3).join(', ') }}{{ files.length > 3 ? ` +${files.length - 3}` : '' }}
                  </span>
                </div>
              </template>
            </div>
            <div v-if="p.violations?.length" class="pattern-violations">
              <div class="pattern-violations-label">⚠ Violations ({{ p.violations.length }})</div>
              <div v-for="v in p.violations.slice(0, 3)" :key="v" class="pattern-violation-item">{{ v }}</div>
              <div v-if="p.violations.length > 3" class="pattern-violation-more">
                +{{ p.violations.length - 3 }} more
              </div>
            </div>
          </div>
        </div>
      </div>
      <div v-else-if="patternsData && patternsData.patterns_found === 0" class="sidebar-section patterns-panel">
        <div class="section-title">Architecture Patterns</div>
        <div class="section-subtitle">How this codebase is organized at a high level, and whether that structure is holding up.</div>
        <div class="patterns-empty">No standard pattern (MVC, Layered, Hexagonal, Repository) matched this codebase's structure — common for smaller or script-style projects, and not necessarily a problem.</div>
      </div>

      <!-- ── GoF Design Patterns Panel ────────────────────────── -->
      <div v-if="gofPatternsData && gofPatternsData.patterns_found > 0" class="sidebar-section patterns-panel">
        <div class="section-title">GoF Design Patterns</div>
        <div class="section-subtitle">Recognized design patterns already in the code — useful context before you extend it.</div>
        <div class="patterns-summary-chip">
          {{ gofPatternsData.patterns_found }} pattern{{ gofPatternsData.patterns_found !== 1 ? 's' : '' }} detected
        </div>
        <div class="patterns-list">
          <div v-for="grp in groupedGofPatterns" :key="grp.pattern" class="pattern-card">
            <div class="pattern-card-head">
              <div class="pattern-name-group">
                <div class="pattern-name-row">
                  <span class="pattern-name">{{ grp.pattern }}</span>
                  <span v-if="grp.category" class="pattern-category-badge">{{ grp.category }}</span>
                  <span v-if="grp.instances.length > 1" class="pattern-instance-count" :title="`${grp.instances.length} separate instances of this pattern`">
                    ×{{ grp.instances.length }}
                  </span>
                </div>
                <InfoTooltip
                  v-if="!grp.heuristic"
                  text="Tier reflects how many of this pattern's required structural signals were found: high = all matched strongly, medium/low = fewer or weaker."
                  :icon="false"
                >
                  <span class="pattern-tier-label">tier: {{ grp.tier }}</span>
                </InfoTooltip>
              </div>
              <span
                v-if="grp.heuristic"
                class="pattern-conf-badge pconf-heuristic"
                title="Heuristic match — not from structural analysis, verify manually"
              >
                ⚠ heuristic
              </span>
              <InfoTooltip
                v-else
                text="How completely the code's structure matches this pattern's expected shape, for the best-matching instance."
                :icon="false"
              >
                <span
                  class="pattern-conf-badge"
                  :class="grp.tier === 'high' ? 'pconf-high' : grp.tier === 'medium' ? 'pconf-med' : 'pconf-low'"
                >
                  {{ Math.round(grp.instances[0].confidence * 100) }}%
                </span>
              </InfoTooltip>
            </div>

            <div v-if="grp.definition" class="pattern-definition">
              {{ grp.definition }}
              <span v-if="grp.why_it_matters" class="pattern-why">{{ grp.why_it_matters }}</span>
            </div>

            <!-- One collapsible entry per matched instance (e.g. per class,
                 for patterns like Adapter that can match several
                 independently) — auto-open when there's only one, since
                 there's nothing to disambiguate by collapsing it. -->
            <details
              v-for="(p, idx) in grp.instances" :key="idx"
              class="pattern-instance" :open="grp.instances.length === 1"
            >
              <summary class="pattern-instance-summary">
                <span class="pattern-instance-binding">
                  {{ (p.bindings && Object.values(p.bindings).join(' · ')) || `instance ${idx + 1}` }}
                </span>
                <span v-if="!p.heuristic" class="pattern-instance-conf">{{ Math.round(p.confidence * 100) }}%</span>
              </summary>

              <!-- Evidence grouped per structural requirement (why it
                   matched, requirement by requirement) — falls back to the
                   flat list if an older cached response has no
                   evidence_detail. Demoted behind its own toggle since it's
                   raw predicate output, not something a non-technical
                   reader needs by default. -->
              <details class="pattern-evidence-details">
                <summary class="pattern-evidence-summary">Technical details (raw evidence)</summary>
                <div v-if="p.evidence_detail?.length" class="pattern-evidence-groups">
                  <div v-for="(eg, gi) in p.evidence_detail" :key="gi" class="pattern-evidence-group">
                    <div class="pattern-evidence-group-head">
                      <span class="pattern-evidence-label">{{ eg.label }}</span>
                      <span
                        v-if="eg.role"
                        class="pattern-evidence-role"
                        :title="`bound as '${eg.role}'`"
                      >→ {{ eg.role }}</span>
                      <span
                        v-if="eg.strength !== null && eg.strength !== undefined && eg.strength < 1"
                        class="pattern-evidence-weak"
                        title="Weaker evidence — matched, but not as certainly as a full-strength requirement"
                      >~ approximate</span>
                    </div>
                    <div v-for="(line, li) in eg.evidence" :key="li" class="pattern-evidence-item">· {{ line }}</div>
                  </div>
                </div>
                <div v-else-if="p.evidence?.length" class="pattern-evidence">
                  <div v-for="e in p.evidence" :key="e" class="pattern-evidence-item">· {{ e }}</div>
                </div>
              </details>

              <div v-if="p.bindings && Object.keys(p.bindings).length" class="pattern-components">
                <div class="pattern-components-label">Roles</div>
                <PatternRoleDiagram :bindings="p.bindings" :pattern-name="grp.pattern" />
              </div>
            </details>
          </div>
        </div>
      </div>
      <div v-else-if="gofPatternsData && gofPatternsData.patterns_found === 0" class="sidebar-section patterns-panel">
        <div class="section-title">GoF Design Patterns</div>
        <div class="section-subtitle">Recognized design patterns already in the code — useful context before you extend it.</div>
        <div class="patterns-empty">No classic GoF design patterns detected. That's normal for smaller or straightforward codebases — patterns tend to emerge as reuse and abstraction grow.</div>
      </div>

      <!-- Layer Analysis Panel (folder / ZIP only) -->
      <div v-if="layerViolations" class="sidebar-section layer-panel">
        <div class="section-title">Layer Analysis</div>
        <div class="section-subtitle">Whether your architecture's boundaries (e.g. controller → service → repository) are actually being respected.</div>

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
              v-for="v in (layerViolations.violations || [])"
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
      </div>
    </aside>
    <div class="sidebar-resize-handle" :class="{ resizing: isResizing }" @mousedown.prevent="startResize"></div>

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
        @node-mouse-enter="onNodeHover"
        @node-mouse-leave="onNodeUnhover"
        @nodes-initialized="() => fitView({ padding: 0.45, duration: 400, maxZoom: 1.4 })"
        fit-view-on-init
        class="vue-flow"
      >
        <Controls position="bottom-right" />
        <MiniMap
          position="bottom-left"
          :node-color="(n) => {
            if (n.data?.nodeType === 'service') return '#14b8a6';
            if (n.data?.nodeType === 'service-unresolved') return '#ef4444';
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
        <template v-if="emptyGraphReason">
          <div class="empty-icon">∅</div>
          <h2 class="empty-title">No navigable functions</h2>
          <p class="empty-sub">{{ emptyGraphReason }}</p>
        </template>
        <template v-else>
          <div class="empty-icon">⬡</div>
          <h2 class="empty-title">No graph loaded</h2>
          <p class="empty-sub">Upload a source file, ZIP archive, or folder<br>using the panel on the left to get started.</p>
          <div class="empty-badges">
            <span>.py</span><span>.js</span><span>.ts</span><span>.java</span><span>.go</span><span>.zip</span>
          </div>
          <ol class="empty-steps">
            <li>Upload a file, ZIP, or folder</li>
            <li>Wait a few seconds while it's analyzed</li>
            <li>Click nodes to explore the structure</li>
          </ol>
        </template>
      </div>

      <!-- ── Change-Impact Overlay (reverse call graph on hover) ──────── -->
      <div v-if="hoveredImpact.visible" class="impact-overlay">
        <div class="impact-head">🔗 Impact: <span class="impact-fn-target">{{ hoveredImpact.fnName }}</span></div>
        <div v-if="hoveredImpact.loading" class="impact-loading">Tracing call graph…</div>
        <template v-else-if="hoveredImpact.data">
          <div class="impact-summary">
            Changing this affects
            <strong>{{ hoveredImpact.data.total_affected }}</strong> function(s)
            across <strong>{{ hoveredImpact.data.affected_files?.length || 0 }}</strong> file(s)
            <span v-if="hoveredImpact.data.affected_modules?.length">
              / <strong>{{ hoveredImpact.data.affected_modules.length }}</strong> module(s)
            </span>
          </div>
          <div v-if="hoveredImpact.data.affected_functions?.length" class="impact-fn-list">
            <div
              v-for="fn in hoveredImpact.data.affected_functions.slice(0, 8)"
              :key="fn.name + fn.file"
              class="impact-fn-row"
            >
              <span class="impact-fn-arrow" :title="fn.direct ? 'Direct caller' : `${fn.depth} call(s) away`">
                {{ fn.direct ? '→' : '⇢' }}
              </span>
              <span class="impact-fn-name">{{ fn.name }}</span>
              <span class="impact-fn-file">{{ fn.file?.split(/[\\/]/).pop() }}</span>
            </div>
            <div v-if="hoveredImpact.data.affected_functions.length > 8" class="impact-fn-more">
              +{{ hoveredImpact.data.total_affected - 8 }} more
            </div>
          </div>
          <div v-else class="impact-none">No other functions depend on this.</div>
        </template>
      </div>
    </div>

    <SliceParamForm
      v-if="dynamicSliceTarget"
      :function-node-id="dynamicSliceTarget.functionNodeId"
      :function-label="dynamicSliceTarget.functionLabel"
      @close="() => { dynamicSliceTarget = null; clearExecStateHighlight(); }"
      @run-complete="applyExecStateHighlight"
    />
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
import FixTreeNode from "./FixTreeNode.vue";
import InfoTooltip from "./InfoTooltip.vue";
import PatternRoleDiagram from "./PatternRoleDiagram.vue";
import SliceParamForm from "./SliceParamForm.vue";

// Inject session manager
const sessionManager = inject('sessionManager');

const nodes = ref([]);
const edges = ref([]);
const uploading = ref(false);
const uploadedFile = ref(null);
const uploadError = ref(null);
const uploadSuccess = ref(false);
// Message shown in the canvas empty-state when a file/chunk was opened but had zero
// navigable functions (e.g. only inline anonymous callbacks) — distinct from
// uploadError, which is for actual failures reported in the sidebar.
const emptyGraphReason = ref(null);
const expandedNodes = ref(new Set());
const nodeLevelMap = ref(new Map());
const discoveredFunctions = ref([]);
const selectedRoot = ref("");
const functionLayoutMode = ref(false);
const navStack = ref([]);   // [{label, nodes, edges, expandedNodes, nodeLevelMap}]

// ── Dynamic-analysis (Python-only) state ──────────────────────────────────
const dynamicSliceTarget = ref(null); // {functionNodeId, functionLabel} while the param form is open
const execStateByNode = ref(new Map()); // node.id (function name) -> 'executed' | 'slice'
const activeServiceId = ref(null);   // set while drilled into one service (Tier 0 -> Tier 1+), null at the top / in single-project mode
const currentLabel = ref('');
const riskData = ref(null);         // { functions: [...], summary: {...}, total: N }
const deadCodeData = ref(null);     // { unreachable_functions: [...], unused_imports: [...], summary: {...} }
const layerViolations = ref(null);  // { by_module: {id: {count, severity}}, summary: {...} }
const metricsData = ref(null);      // Integrated Metrics Dashboard
const gitHistory = ref(null);       // { total_commits, current_branch, commits: [...] }
const smellData = ref(null);        // { smells, summary, graph_summary, plan, fn_smell_map,
                                     //   smells_by_layer, fix_tree, total_debt_score, estimated_dev_days }
const llmPlan = ref(null);          // LLM architectural reasoning result
const llmLoading = ref(false);      // LLM request in progress
const selectedSmellFile = ref(null);
const patternsData = ref(null);
const gofPatternsData = ref(null);  // GoF design patterns from /api/gof-patterns

// /api/gof-patterns reports one entry per matched instance — e.g. Adapter
// matches FanOffCommand, FanOnCommand, LightOffCommand and LightOnCommand
// as four separate, independently-valid instances of the same pattern.
// That's correct detection, but four near-identical cards is noisy — group
// same-named patterns into one card with one instance per class inside it.
// `patterns` is already confidence-sorted server-side, so both the group
// order (by first-seen = highest-confidence instance) and each group's
// instance order fall out of that for free.
const groupedGofPatterns = computed(() => {
  const patterns = gofPatternsData.value?.patterns;
  if (!patterns) return [];
  const groups = new Map();
  for (const p of patterns) {
    if (!groups.has(p.pattern)) {
      groups.set(p.pattern, {
        pattern: p.pattern, category: p.category, tier: p.tier,
        heuristic: p.heuristic, instances: [],
        definition: p.definition, why_it_matters: p.why_it_matters,
      });
    }
    groups.get(p.pattern).instances.push(p);
  }
  return Array.from(groups.values());
});
const smellViewMode = ref('files'); // 'files' | 'plan' | 'layers' | 'tree'
const activeSidebarTab = ref('overview'); // 'overview' | 'quality' | 'architecture'
const sidebarTabs = [
  { id: 'overview', label: 'Overview' },
  { id: 'quality', label: 'Quality' },
  { id: 'architecture', label: 'Architecture' },
];
const expandedLayers = ref({});     // { [layerName]: bool }
const expandedPreviews = ref({});   // { [smell_id]: bool } — code_preview toggle in ROI plan

const uploadStage = ref('');
const searchQuery = ref('');
const searchResults = ref([]);
const showSearchDropdown = ref(false);

const SEV_WEIGHT = { critical: 4, high: 3, medium: 2, low: 1 };

const smellTypeDistribution = computed(() => {
  if (!smellData.value?.smells?.length) return [];
  const counts = {};
  for (const s of smellData.value.smells) {
    counts[s.type] = (counts[s.type] || 0) + 1;
  }
  return Object.entries(counts)
    .map(([type, count]) => ({ type, count }))
    .sort((a, b) => b.count - a.count);
});

const smellFileRanking = computed(() => {
  if (!smellData.value?.smells?.length) return [];
  const files = {};
  for (const s of smellData.value.smells) {
    const key = s.target_file || '(unknown)';
    if (!files[key]) files[key] = { file: key, score: 0, count: 0, smells: [] };
    files[key].score += SEV_WEIGHT[s.severity] || 1;
    files[key].count += 1;
    files[key].smells.push(s);
  }
  return Object.values(files).sort((a, b) => b.score - a.score);
});

const selectedFileSmells = computed(() => {
  if (!selectedSmellFile.value) return [];
  return smellFileRanking.value.find(f => f.file === selectedSmellFile.value)?.smells || [];
});

// Feature 3 — smells grouped by architecture layer, as [name, smells[]] pairs
const smellLayerEntries = computed(() => {
  const byLayer = smellData.value?.smells_by_layer;
  if (!byLayer) return [];
  return Object.entries(byLayer);
});
function toggleLayer(name) {
  expandedLayers.value = { ...expandedLayers.value, [name]: !expandedLayers.value[name] };
}

// Feature 1 — static ROI-ranked refactor plan (resolves_count / effort), already sorted by backend
const smellRoiPlan = computed(() => smellData.value?.plan || []);
function togglePreview(smellId) {
  expandedPreviews.value = { ...expandedPreviews.value, [smellId]: !expandedPreviews.value[smellId] };
}
const sidebarWidth = ref(380);
const isResizing = ref(false);
const { fitView, findNode, setCenter } = useVueFlow();

function startResize() {
  isResizing.value = true;
  document.addEventListener('mousemove', onResize);
  document.addEventListener('mouseup', stopResize);
}
function onResize(e) {
  if (!isResizing.value) return;
  sidebarWidth.value = Math.min(Math.max(e.clientX, 220), 750);
}
function stopResize() {
  isResizing.value = false;
  document.removeEventListener('mousemove', onResize);
  document.removeEventListener('mouseup', stopResize);
}
const nodeTypes = {
  functionNode: markRaw(FunctionNode)
};
const edgeTypes = {
  backcall: markRaw(BottomBackEdge)
};

const nodeCount = computed(() => nodes.value.length);

// Map function name → worst smell severity for node coloring
const smellSeverityMap = computed(() => smellData.value?.fn_smell_map || {});

// Enrich git commits with estimated LOC + function count + MI at each point in history.
// Commits arrive newest-first; we walk backwards from current state.
const gitCommitsWithLoc = computed(() => {
  if (!gitHistory.value?.commits?.length) return [];
  const currentLoc = metricsData.value?.sloc ?? 0;
  const currentFns = metricsData.value?.total_functions ?? 0;
  const numFiles   = Math.max(1, metricsData.value?.total_files ?? 1);
  const hv         = Math.max(1, metricsData.value?.halstead_volume ?? 1);
  const avgCc      = metricsData.value?.avg_cyclomatic ?? 1;

  const estimateMi = (loc) => {
    const avgLocPerFile = Math.max(1, loc / numFiles);
    const raw = 171 - 5.2 * Math.log(hv) - 0.23 * avgCc - 16.2 * Math.log(avgLocPerFile);
    return Math.round(Math.max(0, Math.min(100, raw * 100 / 171)));
  };

  let loc = currentLoc;
  let fns = currentFns;
  return gitHistory.value.commits.map((c) => {
    const netDelta     = (c.insertions  || 0) - (c.deletions  || 0);
    const fnDelta      = (c.fn_added    || 0) - (c.fn_removed || 0);
    const churn        = (c.insertions  || 0) + (c.deletions  || 0);
    const estimatedLoc = Math.max(0, loc);
    const estimatedFns = Math.max(0, fns);
    const estimatedMi  = estimateMi(estimatedLoc);
    loc = Math.max(0, loc - netDelta);
    fns = Math.max(0, fns - fnDelta);
    return { ...c, estimatedLoc, netDelta, estimatedFns, fnDelta, churn, estimatedMi };
  });
});

const gitPageSize = ref(10);
const gitCommitsPage = computed(() => gitCommitsWithLoc.value.slice(0, gitPageSize.value));

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
    g.setNode(n.id, { width: 210, height: 74 });
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
        x: pos.x - 105,  // center: width/2
        y: pos.y - 37    // center: height/2
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
  service:  '#14b8a6',
  module:   '#3b82f6',
  file:     '#f59e0b',
  function: '#6366f1',
  chunk:    '#8b5cf6',
  default:  '#6366f1'
};

// Auto-detected inter-service connection "type" -> edge color, for the Tier 0 service graph
const CONNECTION_TYPE_COLORS = {
  REST:         '#22c55e',
  gRPC:         '#0ea5e9',
  MessageQueue: '#a855f7',
  DB:           '#f59e0b',
  Other:        '#94a3b8',
};
const UNRESOLVED_EDGE_COLOR = '#ef4444';

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
    violationCount = 0, violationSeverity = 'none', smellSeverity = 'none',
    parentFile = null, fnCount = 0, className = null, filePath = null,
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
      parentFile,
      fnCount,
      className,
      filePath,
    },
    position,
    sourcePosition: Position.Bottom,
    targetPosition: Position.Top,
    style: {
      width: '210px',
      height: '74px',
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
      _origStroke: edgeColor,
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
  emptyGraphReason.value = null;
  nodes.value = prev.nodes;
  edges.value = prev.edges;
  expandedNodes.value = prev.expandedNodes;
  nodeLevelMap.value = prev.nodeLevelMap;
  currentLabel.value = prev.label;
  if (prev.label === 'Services' && activeServiceId.value !== null) {
    activeServiceId.value = null;
    fetchAnalysisPanels(false, uploadedFile.value || '').catch(() => {});
  }
  await nextTick();
  fitView({ padding: 0.45, duration: 300, maxZoom: 1.4 });
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
      _origStroke: edgeColor,
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
  fitView({ padding: 0.45, duration: 300, maxZoom: 1.4 });
};

// Build Tier 0 (service) edges, colored by connection type rather than by
// source-node type (toVueFlowEdges' default rule doesn't apply here).
const makeServiceEdges = (rawConnections) => {
  return rawConnections.map((c, i) => {
    const color = c.unresolved
      ? UNRESOLVED_EDGE_COLOR
      : (CONNECTION_TYPE_COLORS[c.type] || CONNECTION_TYPE_COLORS.Other);
    const labelText = c.unresolved ? `⚠ ${c.label || c.type}` : (c.label || c.type);
    return {
      id: `svc-${c.from}-${c.to}-${i}`,
      source: c.from,
      target: c.to,
      animated: false,
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      label: labelText,
      labelStyle: { fill: color, fontWeight: 600, fontSize: '10px' },
      markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16, color },
      style: {
        stroke: color,
        strokeWidth: 2,
        strokeLinecap: 'round',
        strokeDasharray: c.unresolved ? '6 4' : '0',
      },
      type: 'smoothstep',
      pathOptions: { borderRadius: 8 },
    };
  });
};

const renderTier0Graph = async (serviceGraph) => {
  activeServiceId.value = null;
  if (!serviceGraph || !Array.isArray(serviceGraph.services) || serviceGraph.services.length === 0) {
    uploadError.value = 'No services detected.';
    nodes.value = [];
    edges.value = [];
    return;
  }

  const connections = serviceGraph.connections || [];
  const knownServiceIds = new Set(serviceGraph.services.map((s) => s.service_id));

  // Defensive: a connection referencing a service_id with no matching folder
  // still needs an endpoint node — render it as a warning node. Auto-detection
  // only resolves against known services, so this shouldn't normally trigger.
  const phantomIds = [];
  connections.forEach((c) => {
    if (!knownServiceIds.has(c.from) && !phantomIds.includes(c.from)) phantomIds.push(c.from);
    if (!knownServiceIds.has(c.to) && !phantomIds.includes(c.to)) phantomIds.push(c.to);
  });

  const serviceNodes = serviceGraph.services.map((s, index) =>
    createNode(
      s.service_id,
      { x: index * 300, y: 0 },
      {
        fullLabel: s.service_id,
        nodeType: 'service',
        className: `${s.module_count} module${s.module_count === 1 ? '' : 's'} · ${s.file_count} file${s.file_count === 1 ? '' : 's'}`,
      }
    )
  );

  const phantomNodes = phantomIds.map((id, index) =>
    createNode(
      id,
      { x: (serviceNodes.length + index) * 300, y: 0 },
      { fullLabel: id, nodeType: 'service-unresolved' }
    )
  );

  const allNodes = [...serviceNodes, ...phantomNodes];
  const dagreEdges = connections.map((c) => ({ source: c.from, target: c.to }));
  const layoutedNodes = applyDagreLayout(allNodes, dagreEdges, { rankdir: 'LR', nodesep: 80, ranksep: 180 });

  nodes.value = layoutedNodes;
  edges.value = makeServiceEdges(connections);
  expandedNodes.value.clear();
  nodeLevelMap.value.clear();
  layoutedNodes.forEach((n) => nodeLevelMap.value.set(n.id, 0));
  navStack.value = [];
  currentLabel.value = 'Services';
  await nextTick();
  fitView({ padding: 0.45, duration: 300, maxZoom: 1.4 });
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
  fitView({ padding: 0.45, duration: 300, maxZoom: 1.4 });
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
  fitView({ padding: 0.45, duration: 300, maxZoom: 1.4 });
};

const resetGraphState = () => {
  uploadError.value = null;
  emptyGraphReason.value = null;
  uploadSuccess.value = false;
  uploading.value = true;
  uploadedFile.value = null;
  uploadStage.value = '';
  searchQuery.value = '';
  searchResults.value = [];
  showSearchDropdown.value = false;
  discoveredFunctions.value = [];
  selectedRoot.value = "";
  nodes.value = [];
  edges.value = [];
  expandedNodes.value.clear();
  nodeLevelMap.value.clear();
  // Clear all analysis panel results so previous upload data never bleeds into a new session
  layerViolations.value = null;
  llmPlan.value = null;
  riskData.value = null;
  deadCodeData.value = null;
  metricsData.value = null;
  gitHistory.value = null;
  smellData.value = null;
  smellViewMode.value = 'files';
  expandedLayers.value = {};
  expandedPreviews.value = {};
  patternsData.value = null;
  gofPatternsData.value = null;
  impactCache.clear();
  hoveredImpact.value = { visible: false, loading: false, fnName: '', data: null };
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
    const sid = sessionManager.getSessionId();
    // While drilled into one service of a monorepo, scope these panels to it —
    // absent (top-level Services view, or a plain single-project upload) they're unfiltered.
    const svcQuery = activeServiceId.value ? `?service_id=${encodeURIComponent(activeServiceId.value)}` : '';
    const requests = [
      sessionManager.apiCall('/risk-score',                          { method: 'GET' }),
      sessionManager.apiCall(`/dead-code${svcQuery}`,                { method: 'GET' }),
      sessionManager.apiCall('/metrics',                             { method: 'GET' }),
      sessionManager.apiCall('/git-history',                         { method: 'GET' }),
      sessionManager.apiCall(`/smell-analysis${svcQuery}`,           { method: 'GET' }),
      sessionManager.apiCall(`/api/patterns/${sid}${svcQuery}`,      { method: 'GET' }),
      // No service_id filtering here yet — /api/gof-patterns scans the
      // whole session's class graph regardless of the active monorepo
      // service, unlike the panels above. Fine for single-project uploads;
      // worth revisiting if per-service GoF scoping turns out to matter.
      sessionManager.apiCall(`/api/gof-patterns/${sid}`,             { method: 'GET' }),
    ];
    if (isFolder) {
      requests.push(sessionManager.apiCall(`/layer-violations${svcQuery}`, { method: 'GET' }));
    }
    const results = await Promise.all(requests);
    riskData.value     = await results[0].json();
    deadCodeData.value = await results[1].json();
    metricsData.value  = await results[2].json();
    const gh           = await results[3].json();
    gitHistory.value   = gh?.available ? gh : null;
    smellData.value    = await results[4].json();
    patternsData.value = await results[5].json();
    gofPatternsData.value = await results[6].json();
    if (isFolder && results[7]) {
      layerViolations.value = await results[7].json();
    }
  } catch (_) { /* non-critical — panels stay hidden */ }
};

const uploadWithFormData = async (formData, sourceName) => {
  resetGraphState();

  const stages = ['Uploading file...', 'Parsing code...', 'Computing metrics...', 'Building graph...'];
  let stageIdx = 0;
  uploadStage.value = stages[0];
  const stageTimer = setInterval(() => {
    stageIdx = Math.min(stageIdx + 1, stages.length - 1);
    uploadStage.value = stages[stageIdx];
  }, 1800);

  try {
    const response = await sessionManager.apiCall('/upload', {
      method: 'POST',
      body: formData,
    });
    clearInterval(stageTimer);
    uploadStage.value = '';
    const data = await response.json();

    uploadedFile.value = sourceName;
    uploadSuccess.value = true;

    const render = data.render_strategy;

    // Monorepo with 2+ detected services — land on Tier 0 instead of Tier 1.
    // Single-project uploads never set this flag, so this branch is a no-op for them.
    if (data.is_multi_service && data.service_graph) {
      await renderTier0Graph(data.service_graph);
      window.__render_strategy = render;
      discoveredFunctions.value = [];
      selectedRoot.value = '';
      functionLayoutMode.value = false;
      await fetchAnalysisPanels(false, sourceName);
      return;
    }

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
            fitView({ padding: 0.4, duration: 400, maxZoom: 1.4});
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
    clearInterval(stageTimer);
    uploadStage.value = '';
    console.error("Error uploading file:", err);
    uploadError.value =
      err.message || "Failed to upload file. Make sure backend is running.";
    nodes.value = [];
    edges.value = [];
  }
};

const renderFunctionView = async (fileId, functionGraph) => {
  // functionGraph: { nodes: [...], edges: [...], chunked: bool }
  if (!functionGraph || !functionGraph.nodes || functionGraph.nodes.length === 0) {
    // A file/chunk can legitimately have zero navigable nodes — e.g. it only contains
    // inline anonymous callbacks (db.query/.then/addEventListener arguments), which the
    // backend excludes since there's no name to click through to. Show that plainly
    // instead of falling into the BFS-layout code below, which assumes at least one
    // node exists (functionGraph.nodes[0]) and throws when it doesn't.
    nodes.value = [];
    edges.value = [];
    emptyGraphReason.value = 'No navigable functions in this file — it likely only contains inline/anonymous callbacks (e.g. route handlers passed directly as arguments).';
    return;
  }
  emptyGraphReason.value = null;

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
      parentFile: fn.type === 'chunk' ? fileId : null,
      fnCount: fn.fn_count || 0,
      className: fn.class_name || null,
      // Dynamic-analysis (Python-only) needs "<file_path>::<function_name>" to
      // identify the target — chunks aren't individual functions, so only tag it there.
      filePath: fn.type === 'chunk' ? null : fileId,
    });
  });

  const newEdges = toVueFlowEdges(edgeList, newNodes, { forceStraight: false });
  nodes.value = newNodes;
  edges.value = newEdges;
  expandedNodes.value.clear();
  functionLayoutMode.value = true;
  await nextTick();
  fitView({ padding: 0.45, duration: 300, maxZoom: 1.4 });
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

const onNodeClick = async ({ event, node }) => {
  // "Run Dynamic Slice" badge (Python function nodes only — see FunctionNode.vue's
  // §4.0 gate) intercepts the click before the normal drill-down logic below;
  // it isn't a separate emit since vue-flow's nodeTypes-rendered components
  // aren't wired into this component's own event listeners.
  if (event?.target?.closest?.('.dynamic-slice-badge')) {
    dynamicSliceTarget.value = {
      functionNodeId: `${node.data?.filePath}::${node.id}`,
      functionLabel: node.data?.label || node.id,
    };
    return;
  }

  if (expandedNodes.value.has(node.id)) return;

  const type = node.data?.nodeType || 'module';
  if (type === 'service-unresolved') return; // phantom warning node — nothing to drill into
  try {
    if (type === 'service') {
      const response = await sessionManager.apiCall(`/graph/tier1?service_id=${encodeURIComponent(node.id)}`, {
        method: 'GET',
      });
      const res = await response.json();
      // renderTier1Graph resets navStack itself, so snapshot the Tier 0 state
      // and re-seed navStack afterward — this keeps "Back" returning to Services.
      const tier0Snapshot = {
        label: 'Services',
        nodes: JSON.parse(JSON.stringify(nodes.value)),
        edges: JSON.parse(JSON.stringify(edges.value)),
        expandedNodes: new Set(expandedNodes.value),
        nodeLevelMap: new Map(nodeLevelMap.value),
      };
      activeServiceId.value = node.id;
      await renderTier1Graph(res);
      navStack.value = [tier0Snapshot];
      fetchAnalysisPanels(false, uploadedFile.value || '').catch(() => {});
      return;
    }
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
    fitView({ padding: 0.5, duration: 250, maxZoom: 1.4});
    return;
    }
    const response = await sessionManager.apiCall(`/graph/tier2/${encodeURIComponent(node.id)}`, {
      method: 'GET',
    });
    const res = await response.json();
    pushNav(node.data?.label || node.id);

    // Mirror the file→function drill-down (Tier-3): show only this module's
    // own files, connected by their real cross-file call edges — not the
    // module box re-drawn as a parent above its children.
    const newChildNodes = res.nodes.map((f, index) => {
      const pos = getRootChildPosition(node, index, res.nodes.length);
      nodeLevelMap.value.set(f.id, 0);
      return createNode(f.id, pos, { fullLabel: f.id, nodeType: 'file', language: f.language });
    });

    const layoutedNodes = applyDagreLayout(newChildNodes, res.edges, { rankdir: 'TB', nodesep: 60, ranksep: 140 });

    nodes.value = layoutedNodes;
    edges.value = toVueFlowEdges(res.edges, layoutedNodes);
    expandedNodes.value.clear();
    expandedNodes.value.add(node.id);
    nodeLevelMap.value.clear();
    layoutedNodes.forEach((n) => nodeLevelMap.value.set(n.id, 0));

    await nextTick();
    fitView({ padding: 0.5, duration: 250, maxZoom: 1.4});
  } else if (type === 'file') {
      // Drill into chunk/function graph for this file
      const response = await sessionManager.apiCall(`/graph/tier3?file_path=${encodeURIComponent(node.id)}`, {
        method: 'GET',
      });
      const res = await response.json();
      pushNav(node.data?.label || node.id);
      await renderFunctionView(node.id, res);
    } else if (type === 'chunk') {
      // Drill into functions inside this chunk (god file sub-group)
      const parentFile = node.data?.parentFile || node.id;
      const response = await sessionManager.apiCall(
        `/graph/chunk?file_path=${encodeURIComponent(parentFile)}&chunk_name=${encodeURIComponent(node.id)}`,
        { method: 'GET' }
      );
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
      fitView({ padding: 0.5, duration: 250, maxZoom: 1.4});
    }
  } catch (err) {
    console.error('Error fetching graph:', err);
    alert('Failed to fetch graph data. Make sure backend is running.');
  }
};

const HOVER_COLOR_OUT = '#22d3ee';  // outgoing: this node → callee (cyan)
const HOVER_COLOR_IN  = '#f97316';  // incoming: caller → this node (orange)

// ── Change-Impact Panel (reverse call graph) ──────────────────────────
const impactCache = new Map();   // function name -> resolved impact payload
const hoveredImpact = ref({ visible: false, loading: false, fnName: '', data: null });

const fetchImpact = async (fnName) => {
  if (impactCache.has(fnName)) return impactCache.get(fnName);
  try {
    const res  = await sessionManager.apiCall(`/impact-analysis/${encodeURIComponent(fnName)}`, { method: 'GET' });
    const data = await res.json();
    impactCache.set(fnName, data);
    return data;
  } catch (_) {
    return null;
  }
};

const showImpactForNode = (node) => {
  if (node.data?.nodeType !== 'function' || !(node.data?.fanIn > 0)) {
    hoveredImpact.value = { visible: false, loading: false, fnName: '', data: null };
    return;
  }
  const fnName = node.data.fullLabel || node.id;
  hoveredImpact.value = { visible: true, loading: true, fnName, data: null };
  fetchImpact(fnName).then((data) => {
    // guard against fast hover swaps landing out of order
    if (hoveredImpact.value.fnName === fnName) {
      hoveredImpact.value = { visible: true, loading: false, fnName, data };
    }
  });
};

const onNodeHover = ({ node }) => {
  showImpactForNode(node);
  const connectedIds = new Set([node.id]);
  edges.value.forEach((e) => {
    if (e.source === node.id) connectedIds.add(e.target);
    if (e.target === node.id) connectedIds.add(e.source);
  });

  edges.value = edges.value.map((e) => {
    const isOut = e.source === node.id;   // this node calls someone
    const isIn  = e.target === node.id;   // someone calls this node
    const isRelated = isOut || isIn;
    const highlightColor = isOut ? HOVER_COLOR_OUT : HOVER_COLOR_IN;
    return {
      ...e,
      markerEnd: {
        type: MarkerType.ArrowClosed,
        width: isRelated ? 22 : 12,
        height: isRelated ? 22 : 12,
        color: isRelated ? highlightColor : '#334155'
      },
      style: {
        ...(e.style || {}),
        stroke: isRelated ? highlightColor : '#334155',
        strokeWidth: isRelated ? 5 : 1,
        opacity: isRelated ? 1 : 0.08,
        filter: isRelated ? `drop-shadow(0 0 4px ${highlightColor})` : 'none',
      },
      animated: isRelated,
    };
  });

  nodes.value = nodes.value.map((n) => ({
    ...n,
    style: {
      ...n.style,
      opacity: connectedIds.has(n.id) ? 1 : 0.2,
      filter: n.id === node.id
        ? 'drop-shadow(0 0 8px rgba(99,102,241,0.8))'
        : connectedIds.has(n.id)
          ? 'drop-shadow(0 0 4px rgba(255,255,255,0.3))'
          : 'none'
    }
  }));
};

const onNodeUnhover = () => {
  hoveredImpact.value = { visible: false, loading: false, fnName: '', data: null };
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
      stroke: e._origStroke || e.style?.stroke || EDGE_COLORS.default,
      strokeWidth: 2,
      opacity: 1,
      filter: 'none',
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

// ── Dynamic-analysis execution highlight ──────────────────────────────────
// Coarse, function-node-granularity signal: the analyzed function itself
// ("slice" — emphasized) and the functions it actually called during this
// run ("executed" — dimmed but visible), against everything else in the
// current graph (faded). Statement-level slice detail (S1..S11, reads/writes)
// has no representation in this call-graph view — it's shown inside
// SliceParamForm's own criterion picker instead.
const applyExecStateHighlight = (runResult) => {
  const targetFnName = dynamicSliceTarget.value?.functionNodeId?.split('::').pop();
  const called = new Set(runResult.called_functions || []);
  const relevant = new Set([targetFnName, ...called]);

  const map = new Map();
  nodes.value.forEach((n) => {
    if (n.data?.nodeType !== 'function') return;
    if (n.id === targetFnName) map.set(n.id, 'slice');
    else if (called.has(n.id)) map.set(n.id, 'executed');
  });
  execStateByNode.value = map;

  nodes.value = nodes.value.map((n) => ({
    ...n,
    data: { ...n.data, execState: map.get(n.id) || null },
    style: { ...n.style, opacity: relevant.has(n.id) ? 1 : 0.25 },
  }));
};

const clearExecStateHighlight = () => {
  execStateByNode.value = new Map();
  nodes.value = nodes.value.map((n) => {
    const { execState, ...restData } = n.data || {};
    return { ...n, data: restData, style: { ...n.style, opacity: 1 } };
  });
};

const performSearch = (query) => {
  if (!query || !query.trim()) {
    searchResults.value = [];
    showSearchDropdown.value = false;
    return;
  }
  const q = query.toLowerCase();
  const results = [];
  const seen = new Set();

  // Search visible graph nodes first
  for (const node of nodes.value) {
    const label = (node.data?.label || node.data?.fullLabel || node.id || '').toLowerCase();
    if (label.includes(q)) {
      if (!seen.has(node.id)) {
        seen.add(node.id);
        results.push({
          id: node.id,
          label: node.data?.label || node.data?.fullLabel || node.id,
          type: node.data?.nodeType || 'node',
          inGraph: true,
          file: node.data?.nodeType === 'function' ? (node.data?.fullLabel || '') : '',
          risk: null,
        });
      }
    }
  }

  // Search all known functions from riskData
  if (riskData.value?.functions) {
    for (const fn of riskData.value.functions) {
      const name = (fn.name || '').toLowerCase();
      const file = (fn.file || '').toLowerCase();
      if (name.includes(q) || file.includes(q)) {
        const key = fn.name + '|' + fn.file;
        if (!seen.has(key)) {
          seen.add(key);
          const inGraph = nodes.value.some(n => n.data?.label === fn.name || n.id === fn.name);
          results.push({
            id: fn.name,
            label: fn.name,
            type: 'function',
            inGraph,
            file: fn.file,
            risk: fn.risk_level,
          });
        }
      }
    }
  }

  searchResults.value = results.slice(0, 10);
  showSearchDropdown.value = results.length > 0;
};

const focusSearchResult = async (result) => {
  showSearchDropdown.value = false;

  const graphNode = nodes.value.find(
    n => n.id === result.id || n.data?.label === result.label
  );

  if (graphNode) {
    await nextTick();
    setCenter(graphNode.position.x + 75, graphNode.position.y + 30, { duration: 400, zoom: 1.5 });

    // Flash highlight for 2 seconds
    nodes.value = nodes.value.map(n =>
      n.id === graphNode.id
        ? { ...n, style: { ...n.style, outline: '3px solid #818cf8', filter: 'drop-shadow(0 0 14px #818cf8)' } }
        : n
    );
    setTimeout(() => {
      nodes.value = nodes.value.map(n =>
        n.id === graphNode.id
          ? { ...n, style: { ...n.style, outline: '', filter: 'none' } }
          : n
      );
    }, 2000);
  }
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
/* ── Design tokens ─────────────────────────────────── */
.graph-container {
  --radius-sm: 6px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --shadow-sm: 0 1px 4px rgba(0, 0, 0, 0.14);
  --shadow-md: 0 4px 14px rgba(0, 0, 0, 0.24);
  --shadow-lg: 0 10px 32px rgba(0, 0, 0, 0.4);
  --transition-fast: 140ms ease;
  --transition-base: 200ms ease;
  --surface-card: #1e293b;
  --surface-card-hover: #273549;
  --border-card: #334155;
  --text-primary: #e2e8f0;
  --text-secondary: #94a3b8;
  --text-muted: #64748b;
  --accent: #6366f1;
  --accent-soft: #818cf8;
}

@media (prefers-reduced-motion: no-preference) {
  @keyframes panel-fade-in {
    from { opacity: 0; transform: translateY(6px); }
    to   { opacity: 1; transform: translateY(0); }
  }
}

/* Consistent keyboard focus ring across every interactive element in this view */
.graph-container button:focus-visible,
.graph-container input:focus-visible,
.graph-container textarea:focus-visible,
.graph-container summary:focus-visible,
.graph-container [tabindex]:focus-visible {
  outline: 2px solid var(--accent-soft);
  outline-offset: 2px;
  border-radius: var(--radius-sm);
}

/* Custom scrollbars (WebKit) to complement the thin Firefox scrollbar on .sidebar */
.sidebar::-webkit-scrollbar,
.search-dropdown::-webkit-scrollbar,
.code-preview-pre::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}
.sidebar::-webkit-scrollbar-track,
.search-dropdown::-webkit-scrollbar-track,
.code-preview-pre::-webkit-scrollbar-track {
  background: transparent;
}
.sidebar::-webkit-scrollbar-thumb,
.search-dropdown::-webkit-scrollbar-thumb,
.code-preview-pre::-webkit-scrollbar-thumb {
  background: var(--border-card);
  border-radius: 8px;
}
.sidebar::-webkit-scrollbar-thumb:hover,
.search-dropdown::-webkit-scrollbar-thumb:hover,
.code-preview-pre::-webkit-scrollbar-thumb:hover {
  background: #475569;
}

/* ── Layout ────────────────────────────────────────── */
.graph-container {
  display: flex;
  flex-direction: row;
  height: 100vh;
  overflow: hidden;
}

/* ── Sidebar ───────────────────────────────────────── */
.sidebar {
  background: #0f172a;
  color: #e2e8f0;
  display: flex;
  flex-direction: column;
  gap: 0;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-width: thin;
  scrollbar-color: #334155 transparent;
  flex-shrink: 0;
}

.sidebar-resize-handle {
  width: 5px;
  flex-shrink: 0;
  cursor: col-resize;
  background: transparent;
  transition: background var(--transition-base);
  position: relative;
  z-index: 10;
}
.sidebar-resize-handle::before {
  content: "";
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 3px;
  height: 28px;
  border-radius: 3px;
  background: #475569;
  opacity: 0;
  transition: opacity var(--transition-base), background var(--transition-base);
  pointer-events: none;
}
.sidebar-resize-handle:hover,
.sidebar-resize-handle.resizing {
  background: rgba(99, 102, 241, 0.25);
}
.sidebar-resize-handle:hover::before,
.sidebar-resize-handle.resizing::before {
  opacity: 1;
  background: var(--accent-soft);
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
  font-size: 29px;
  line-height: 1;
  color: #818cf8;
  filter: drop-shadow(0 0 10px rgba(129, 140, 248, 0.45));
}
.brand-name {
  font-size: 18px;
  font-weight: 700;
  color: #f1f5f9;
  letter-spacing: -0.01em;
}
.brand-sub {
  font-size: 12px;
  color: #cbd5e1;
  margin-top: 1px;
}

/* Sidebar sections */
.sidebar-section {
  padding: 16px 18px;
  border-bottom: 1px solid #1e293b;
}
@media (prefers-reduced-motion: no-preference) {
  .sidebar-section,
  .search-dropdown,
  .impact-overlay,
  .llm-plan-box {
    animation: panel-fade-in 220ms ease-out both;
  }
}
.sidebar-section.tips {
  flex: 1;
}
.section-title {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #a5b4fc;
  margin-bottom: 10px;
}
.section-subtitle {
  font-size: 12px;
  color: #e2e8f0;
  line-height: 1.5;
  margin: -6px 0 10px;
}

.sidebar-tabs {
  display: flex;
  gap: 4px;
  padding: 14px 18px 12px;
  border-bottom: 1px solid #1e293b;
  margin-bottom: 4px;
}
.sidebar-tab {
  flex: 1;
  padding: 7px 8px;
  font-size: 12px;
  font-weight: 700;
  border-radius: var(--radius-sm);
  border: 1px solid #334155;
  background: #1e293b;
  color: #e2e8f0;
  cursor: pointer;
  white-space: nowrap;
  transition: background var(--transition-fast), color var(--transition-fast), border-color var(--transition-fast), transform var(--transition-fast);
}
.sidebar-tab:hover { background: #273549; border-color: #475569; color: #e2e8f0; }
.sidebar-tab:active { transform: scale(0.97); }
.sidebar-tab.active { background: var(--accent); border-color: var(--accent); color: #fff; box-shadow: var(--shadow-sm); }

/* Sticky back navigation */
.sidebar-back-sticky {
  position: sticky;
  top: 0;
  z-index: 10;
  background: #0f172a;
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
  color: #e2e8f0;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background var(--transition-fast), color var(--transition-fast), border-color var(--transition-fast), transform var(--transition-fast);
  margin-bottom: 8px;
}
.back-btn:hover {
  background: #334155;
  border-color: #475569;
  color: #e2e8f0;
  transform: translateX(-1px);
}
.back-btn:active {
  transform: translateX(0);
}
.breadcrumb {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 2px;
  font-size: 12px;
  color: #cbd5e1;
}
.crumb { color: #cbd5e1; }
.crumb-current { color: #e2e8f0; font-weight: 600; }
.crumb-sep { color: #cbd5e1; margin: 0 2px; }

/* Upload zone */
.upload-zone {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 18px 12px;
  border: 2px dashed #334155;
  border-radius: var(--radius-lg);
  cursor: pointer;
  text-align: center;
  transition: border-color var(--transition-base), background var(--transition-base), transform var(--transition-fast), box-shadow var(--transition-base);
  background: #1e293b;
  margin-bottom: 8px;
}
.upload-zone:hover:not(.disabled) {
  border-color: #818cf8;
  background: #1e2a45;
  box-shadow: var(--shadow-sm);
}
.upload-zone:active:not(.disabled) { transform: scale(0.99); }
.upload-zone.disabled { opacity: 0.5; cursor: not-allowed; }
.upload-zone-icon { font-size: 25px; transition: transform var(--transition-base); }
.upload-zone:hover:not(.disabled) .upload-zone-icon { transform: translateY(-2px); }
.upload-zone-text { font-size: 13px; font-weight: 600; color: #cbd5e1; line-height: 1.3; }
.upload-zone-hint { font-size: 12px; color: #cbd5e1; margin-top: 2px; }

.upload-btn-folder {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  padding: 9px 14px;
  border-radius: var(--radius-md);
  background: #1e293b;
  border: 1px solid #334155;
  color: #e2e8f0;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background var(--transition-base), border-color var(--transition-base), color var(--transition-base), transform var(--transition-fast);
}
.upload-btn-folder:hover:not(.disabled) {
  background: #253347;
  border-color: #64748b;
  color: #e2e8f0;
  transform: translateY(-1px);
}
.upload-btn-folder:active:not(.disabled) { transform: translateY(0); }
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
  box-shadow: 0 0 0 0 currentColor;
}
.status-dot.ok  { background: #22c55e; color: rgba(34,197,94,0.35); }
.status-dot.err { background: #f87171; }
@media (prefers-reduced-motion: no-preference) {
  .status-dot.ok { animation: status-pulse 2.2s ease-out infinite; }
  @keyframes status-pulse {
    0%   { box-shadow: 0 0 0 0 currentColor; }
    70%  { box-shadow: 0 0 0 5px transparent; }
    100% { box-shadow: 0 0 0 0 transparent; }
  }
}
.status-filename {
  font-size: 13px;
  font-weight: 600;
  color: #e2e8f0;
  overflow-wrap: break-word;
  word-break: break-word;
}
.status-msg {
  font-size: 13px;
  line-height: 1.4;
  border-radius: var(--radius-sm);
  padding: 7px 10px;
}
.status-msg.ok  { background: #14532d33; color: #86efac; }
.status-msg.err { background: #7f1d1d33; color: #fca5a5; }
.status-count {
  margin-top: 6px;
  font-size: 12px;
  color: #cbd5e1;
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
  font-size: 13px;
  color: #e2e8f0;
}
.legend-swatch {
  width: 12px;
  height: 12px;
  border-radius: 4px;
  flex-shrink: 0;
  box-shadow: var(--shadow-sm);
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
  background: #1e293b;
  margin: 4px 0;
}
.legend-icon {
  font-size: 14px;
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
  font-size: 13px;
  color: #cbd5e1;
  line-height: 1.4;
}
.tips-list strong { color: #e2e8f0; }

.onboarding-steps {
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.onboarding-steps li {
  font-size: 13px;
  color: #e2e8f0;
  line-height: 1.4;
}
.onboarding-steps strong { color: #e2e8f0; }

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

/* ── Vue Flow chrome (Controls / MiniMap) ────────────── */
.graph-section :deep(.vue-flow__controls) {
  box-shadow: var(--shadow-md, 0 4px 14px rgba(0,0,0,0.18));
  border-radius: var(--radius-md, 8px);
  overflow: hidden;
  border: 1px solid #e2e8f0;
}
.graph-section :deep(.vue-flow__controls-button) {
  border: none;
  border-bottom: 1px solid #e2e8f0;
  background: #ffffff;
  transition: background 140ms ease;
}
.graph-section :deep(.vue-flow__controls-button:last-child) {
  border-bottom: none;
}
.graph-section :deep(.vue-flow__controls-button:hover) {
  background: #eef2ff;
}
.graph-section :deep(.vue-flow__controls-button svg) {
  fill: #475569;
}
.graph-section :deep(.vue-flow__minimap) {
  border-radius: var(--radius-md, 8px);
  overflow: hidden;
  box-shadow: var(--shadow-md, 0 4px 14px rgba(0,0,0,0.18));
  transition: box-shadow 200ms ease;
}
.graph-section :deep(.vue-flow__minimap:hover) {
  box-shadow: var(--shadow-lg, 0 10px 32px rgba(0,0,0,0.3));
}

/* ── Change-Impact Overlay ─────────────────────────── */
.impact-overlay {
  position: absolute;
  top: 16px;
  right: 16px;
  z-index: 20;
  width: 280px;
  max-width: calc(100% - 32px);
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: var(--radius-lg);
  padding: 12px 14px;
  box-shadow: var(--shadow-lg);
  pointer-events: none;
}
.impact-head {
  font-size: 13px;
  font-weight: 700;
  color: #e2e8f0;
  margin-bottom: 7px;
}
.impact-fn-target { color: #f97316; }
.impact-loading {
  font-size: 12px;
  color: #cbd5e1;
  font-style: italic;
}
.impact-summary {
  font-size: 12px;
  color: #cbd5e1;
  line-height: 1.5;
  margin-bottom: 7px;
}
.impact-summary strong { color: #e2e8f0; }
.impact-fn-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  border-top: 1px solid #334155;
  padding-top: 7px;
}
.impact-fn-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.impact-fn-arrow {
  color: #f97316;
  font-size: 12px;
  flex-shrink: 0;
}
.impact-fn-name {
  font-size: 12px;
  font-weight: 600;
  color: #e2e8f0;
  flex-shrink: 0;
}
.impact-fn-file {
  font-size: 11px;
  color: #cbd5e1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.impact-fn-more {
  font-size: 11px;
  color: #cbd5e1;
  margin-top: 2px;
}
.impact-none {
  font-size: 12px;
  color: #cbd5e1;
  border-top: 1px solid #334155;
  padding-top: 7px;
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
@media (prefers-reduced-motion: no-preference) {
  .empty-state {
    animation: panel-fade-in 320ms ease-out both;
  }
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
  box-shadow: var(--shadow-sm);
  transition: transform var(--transition-fast);
}
.empty-badges span:hover {
  transform: translateY(-1px);
}
.empty-steps {
  margin-top: 18px;
  padding-left: 20px;
  text-align: left;
  color: #cbd5e1;
  font-size: 13px;
  line-height: 1.9;
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
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
  transition: transform var(--transition-fast);
}
.smell-chip:hover { transform: translateY(-1px); }
.smell-critical { background: #f3e8ff; color: #6b21a8; border: 1px solid #d8b4fe; }
.smell-high     { background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; }
.smell-medium   { background: #fef3c7; color: #92400e; border: 1px solid #fde68a; }
.smell-low      { background: #f0fdf4; color: #166534; border: 1px solid #86efac; }

/* Level 1 – smell type distribution */
.smell-type-list { display: flex; flex-direction: column; gap: 2px; margin-bottom: 4px; }
.smell-type-row  { display: flex; align-items: baseline; gap: 5px; padding: 2px 4px; }
.smell-type-rank { font-size: 12px; color: #cbd5e1; min-width: 14px; }
.smell-type-name {
  flex: 1; font-size: 12px; font-weight: 600; color: #cbd5e1;
  text-transform: capitalize;
}
.smell-type-count { font-size: 12px; font-weight: 700; color: #818cf8; }

/* Level 2 – ranked file list */
.smell-file-list { display: flex; flex-direction: column; gap: 4px; margin-bottom: 10px; }
.smell-file-row {
  display: flex; align-items: center; gap: 7px;
  padding: 6px 8px; border-radius: var(--radius-md);
  background: #1e293b; border: 1px solid #334155;
  cursor: pointer; transition: background var(--transition-fast), border-color var(--transition-fast), transform var(--transition-fast), box-shadow var(--transition-fast);
}
.smell-file-row:hover { background: #273549; border-color: #6366f1; transform: translateY(-1px); box-shadow: var(--shadow-sm); }
.smell-file-row:active { transform: translateY(0); }
.smell-file-rank { font-size: 12px; color: #cbd5e1; min-width: 14px; flex-shrink: 0; }
.smell-file-body { flex: 1; min-width: 0; }
.smell-file-name {
  font-size: 12px; font-weight: 700; color: #e2e8f0;
  font-family: monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.smell-file-meta { font-size: 12px; color: #e2e8f0; margin-top: 1px; }
.smell-file-meta strong { color: #a5b4fc; }
.smell-file-arrow { font-size: 17px; color: #cbd5e1; flex-shrink: 0; }

/* Level 3 – file detail */
.smell-detail-header {
  display: flex; align-items: center; gap: 8px; margin-bottom: 8px;
}
.smell-back-btn {
  padding: 3px 8px; border-radius: var(--radius-sm); border: 1px solid #334155;
  background: #1e293b; font-size: 12px; font-weight: 600; color: #e2e8f0;
  cursor: pointer; flex-shrink: 0;
  transition: background var(--transition-fast), color var(--transition-fast), border-color var(--transition-fast);
}
.smell-back-btn:hover { background: #273549; border-color: #475569; color: #e2e8f0; }
.smell-detail-filename {
  font-size: 13px; font-weight: 700; color: #e2e8f0;
  font-family: monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.smell-detail-list { display: flex; flex-direction: column; gap: 4px; margin-bottom: 10px; }
.smell-detail-item {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 8px; border-radius: var(--radius-md);
  background: #1e293b; border-left: 3px solid #334155;
  transition: background var(--transition-fast), transform var(--transition-fast);
}
.smell-detail-item:hover { background: #273549; transform: translateY(-1px); }
.smell-sev-critical { border-left-color: #a855f7; background: #1a1025; }
.smell-sev-high     { border-left-color: #ef4444; background: #1c1010; }
.smell-sev-medium   { border-left-color: #f59e0b; background: #1c1800; }
.smell-sev-low      { border-left-color: #22c55e; background: #0f1c12; }
.smell-detail-icon { font-size: 14px; flex-shrink: 0; }
.smell-detail-body { flex: 1; min-width: 0; }
.smell-sev-badge {
  font-size: 11px; font-weight: 700; padding: 2px 5px;
  border-radius: 6px; flex-shrink: 0; text-transform: uppercase;
}
.sev-badge-critical { background: #3b0764; color: #d8b4fe; }
.sev-badge-high     { background: #450a0a; color: #fca5a5; }
.sev-badge-medium   { background: #451a03; color: #fde68a; }
.sev-badge-low      { background: #052e16; color: #86efac; }

/* shared item text */
.smell-item-type  {
  font-size: 12px; font-weight: 700; color: #e2e8f0;
  text-transform: capitalize;
  line-height: 1.4;
  overflow-wrap: break-word; word-break: break-word;
}
.smell-item-target {
  font-size: 12px; color: #e2e8f0; font-family: monospace;
  line-height: 1.5;
  overflow-wrap: break-word; word-break: break-word;
}

/* LLM button */
.smell-llm-btn {
  width: 100%;
  padding: 8px 0;
  border-radius: var(--radius-lg);
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  background-size: 200% 200%;
  color: #fff;
  font-size: 13px;
  font-weight: 700;
  border: none;
  cursor: pointer;
  box-shadow: var(--shadow-sm);
  transition: opacity var(--transition-fast), transform var(--transition-fast), box-shadow var(--transition-fast);
  margin-bottom: 8px;
}
.smell-llm-btn:hover:not(:disabled) { opacity: 0.94; transform: translateY(-1px); box-shadow: var(--shadow-md); }
.smell-llm-btn:active:not(:disabled) { transform: translateY(0); }
.smell-llm-btn:disabled { opacity: 0.65; cursor: wait; }
.smell-llm-btn-loading { background: linear-gradient(135deg, #94a3b8 0%, #64748b 100%); }
@media (prefers-reduced-motion: no-preference) {
  .smell-llm-btn-loading {
    background-size: 200% 200%;
    animation: llm-btn-shimmer 1.6s ease-in-out infinite;
  }
  @keyframes llm-btn-shimmer {
    0%, 100% { background-position: 0% 50%; }
    50%      { background-position: 100% 50%; }
  }
}

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
  font-size: 11px;
  color: #6366f1;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.llm-exec-summary {
  font-size: 12px;
  color: #cbd5e1;
  line-height: 1.5;
  border-left: 3px solid #6366f1;
  padding-left: 8px;
}
.llm-root-cause {
  font-size: 12px;
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
  font-size: 12px;
  font-weight: 800;
  color: #e2e8f0;
  background: #334155;
  padding: 1px 5px;
  border-radius: 4px;
  flex-shrink: 0;
}
.llm-step-pattern {
  font-size: 12px;
  font-weight: 700;
  color: #e2e8f0;
  flex: 1;
  overflow-wrap: break-word;
  word-break: break-word;
}
.llm-step-effort {
  font-size: 11px;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 8px;
  flex-shrink: 0;
}
.effort-high   { background: #fef2f2; color: #991b1b; }
.effort-medium { background: #fef3c7; color: #92400e; }
.effort-low    { background: #f0fdf4; color: #166534; }

.llm-step-target  { font-size: 12px; color: #7dd3fc; font-family: monospace; margin-bottom: 2px; }
.llm-step-what    { font-size: 12px; color: #e2e8f0; line-height: 1.4; }
.llm-step-why     { font-size: 12px; color: #4ade80; line-height: 1.4; margin-top: 2px; font-style: italic; }
.llm-step-resolves {
  font-size: 11px; color: #cbd5e1; margin-top: 3px;
  overflow-wrap: break-word; word-break: break-word;
}

.llm-longterm {
  font-size: 12px;
  color: #fbbf24;
  line-height: 1.5;
  padding: 5px 8px;
  background: rgba(251,191,36,0.08);
  border-radius: 6px;
}
.llm-longterm strong { color: #fde68a; }
.llm-error {
  font-size: 12px;
  color: #f87171;
  padding: 4px 8px;
  background: rgba(239,68,68,0.1);
  border-radius: 6px;
}

/* ── Feature 1: Debt score stats ─────────────────────── */
.debt-stats { display: flex; gap: 8px; margin-bottom: 10px; }
.debt-stat {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 6px 4px;
  border-radius: 8px;
  background: #1e293b;
  border: 1px solid #334155;
}
.debt-stat-value { font-size: 16px; font-weight: 800; color: #f59e0b; }
.debt-stat-label { font-size: 11px; color: #e2e8f0; text-transform: uppercase; letter-spacing: 0.03em; margin-top: 1px; }

/* ── Smell panel view-mode tabs ──────────────────────── */
.smell-tabs { display: flex; gap: 4px; margin-bottom: 10px; flex-wrap: wrap; }
.smell-tab {
  flex: 1;
  padding: 5px 6px;
  font-size: 12px;
  font-weight: 700;
  border-radius: var(--radius-sm);
  border: 1px solid #334155;
  background: #1e293b;
  color: #e2e8f0;
  cursor: pointer;
  white-space: nowrap;
  transition: background var(--transition-fast), color var(--transition-fast), border-color var(--transition-fast);
}
.smell-tab:hover { background: #273549; border-color: #475569; color: #e2e8f0; }
.smell-tab.active { background: var(--accent); border-color: var(--accent); color: #fff; box-shadow: var(--shadow-sm); }

.smell-empty-note { font-size: 12px; color: #cbd5e1; padding: 6px 0; text-align: center; }

/* ── Feature 1 & 2: ROI-ranked plan + code preview ───── */
.roi-plan-list { display: flex; flex-direction: column; gap: 6px; margin-bottom: 10px; }
.roi-plan-item {
  padding: 7px 9px;
  border-radius: var(--radius-md);
  background: #1e293b;
  border-left: 3px solid #334155;
  display: flex;
  flex-direction: column;
  gap: 3px;
  transition: background var(--transition-fast), transform var(--transition-fast), box-shadow var(--transition-fast);
}
.roi-plan-item:hover { background: #232f45; transform: translateY(-1px); box-shadow: var(--shadow-sm); }
.roi-plan-head { display: flex; align-items: center; gap: 6px; }
.roi-plan-step {
  font-size: 12px; font-weight: 800; color: #e2e8f0;
  background: #334155; padding: 1px 5px; border-radius: 4px; flex-shrink: 0;
}
.roi-plan-meta {
  display: flex; gap: 10px; font-size: 12px; color: #e2e8f0;
}
.roi-plan-meta strong { color: #a5b4fc; }
.roi-plan-desc { font-size: 12px; color: #cbd5e1; line-height: 1.4; }
.roi-plan-suggestions { font-size: 12px; color: #4ade80; font-style: italic; }
.roi-preview-toggle {
  align-self: flex-start;
  margin-top: 2px;
  padding: 2px 7px;
  font-size: 12px;
  font-weight: 700;
  border-radius: var(--radius-sm);
  border: 1px solid #6366f1;
  background: transparent;
  color: #a5b4fc;
  cursor: pointer;
  transition: background var(--transition-fast), transform var(--transition-fast);
}
.roi-preview-toggle:hover { background: rgba(99,102,241,0.15); }
.roi-preview-toggle:active { transform: scale(0.97); }

.code-preview-box {
  margin-top: 4px;
  padding: 8px;
  border-radius: var(--radius-md);
  background: #0f172a;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
@media (prefers-reduced-motion: no-preference) {
  .code-preview-box { animation: panel-fade-in 180ms ease-out both; }
}
.code-preview-col { display: flex; flex-direction: column; gap: 2px; }
.code-preview-label {
  font-size: 11px; font-weight: 700; color: #cbd5e1; text-transform: uppercase;
}
.code-preview-pre {
  margin: 0;
  padding: 6px;
  border-radius: 6px;
  background: #131c2e;
  font-size: 12px;
  font-family: monospace;
  color: #e2e8f0;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-x: auto;
}
.code-preview-explanation {
  font-size: 12px; color: #fbbf24; line-height: 1.4; font-style: italic;
}

/* ── Feature 3: Layer accordion ──────────────────────── */
.layer-accordion { display: flex; flex-direction: column; gap: 6px; margin-bottom: 10px; }
.layer-group { border-radius: var(--radius-md); background: #1e293b; border: 1px solid #334155; padding: 6px 8px; transition: border-color var(--transition-fast); }
.layer-group:hover { border-color: #475569; }
.layer-header { display: flex; align-items: center; gap: 6px; cursor: pointer; border-radius: var(--radius-sm); transition: background var(--transition-fast); }
.layer-header:hover { background: rgba(255,255,255,0.03); }
.layer-name { flex: 1; font-size: 12px; font-weight: 700; color: #e2e8f0; }
.layer-count {
  font-size: 12px; font-weight: 700; color: #818cf8;
  background: rgba(99,102,241,0.15); padding: 1px 7px; border-radius: 10px;
}

/* ── Feature 4: Fix tree container ───────────────────── */
.fix-tree-container { margin-bottom: 10px; }

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
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
  transition: transform var(--transition-fast);
}
.risk-chip:hover { transform: translateY(-1px); }
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
  border-radius: var(--radius-md);
  background: var(--surface-card);
  border: 1px solid var(--border-card);
  cursor: default;
  transition: background var(--transition-fast), transform var(--transition-fast), box-shadow var(--transition-fast);
}
.risk-item:hover { background: var(--surface-card-hover); transform: translateY(-1px); box-shadow: var(--shadow-sm); }
.risk-item-high   { border-left: 3px solid #ef4444; }
.risk-item-medium { border-left: 3px solid #f59e0b; }
.risk-item-low    { border-left: 3px solid #22c55e; }

.risk-item-icon { font-size: 13px; flex-shrink: 0; margin-top: 1px; }

.risk-item-body { flex: 1; min-width: 0; }
.risk-item-name {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
  overflow-wrap: break-word;
  word-break: break-word;
}
.risk-item-warn {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.4;
  overflow-wrap: break-word;
  word-break: break-word;
}

.risk-item-count {
  flex-shrink: 0;
  font-size: 13px;
  font-weight: 800;
  color: #cbd5e1;
  background: #334155;
  border-radius: 10px;
  padding: 1px 6px;
  margin-top: 1px;
}

.risk-empty {
  font-size: 13px;
  color: #e2e8f0;
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
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}
.dead-chip-high { background: #f1f5f9; color: #334155; }
.dead-chip-medium { background: #f8fafc; color: #64748b; }
.dead-chip-imp  { background: #fef9c3; color: #854d0e; }

.dead-section-label {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #e2e8f0;
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
  border-radius: var(--radius-md);
  background: var(--surface-card);
  border: 1px dashed #475569;
  cursor: default;
  transition: background var(--transition-fast), transform var(--transition-fast), box-shadow var(--transition-fast);
}
.dead-item:hover { background: var(--surface-card-hover); transform: translateY(-1px); box-shadow: var(--shadow-sm); }
/* high confidence: brighter dashed border */
.dead-item-high   { border-color: #64748b; }
.dead-item-high:hover { background: #2a3852; }
/* medium confidence: dimmer */
.dead-item-medium { border-color: #3f4d64; }
.dead-import-item { border-color: #92620f; background: #241d0c; }
.dead-import-item:hover { background: #2e2510; }

.dead-item-icon { font-size: 13px; flex-shrink: 0; }

.dead-item-body { flex: 1; min-width: 0; }
.dead-item-name {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-secondary);
  text-decoration: line-through;
  overflow-wrap: break-word;
  word-break: break-word;
}
.dead-item-file {
  font-size: 12px;
  color: var(--text-muted);
  font-family: monospace;
  overflow-wrap: break-word;
  word-break: break-word;
}

/* confidence badge */
.dead-conf-badge {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 800;
  padding: 1px 5px;
  border-radius: 8px;
  letter-spacing: 0.03em;
}
.conf-high { background: #334155; color: #e2e8f0; }
.conf-med  { background: #263041; color: #e2e8f0; }

/* static analysis disclaimer */
.dead-note {
  margin-top: 8px;
  padding: 7px 9px;
  border-radius: var(--radius-sm);
  background: #fefce8;
  border: 1px solid #fde68a;
  font-size: 12px;
  color: #78350f;
  line-height: 1.6;
}

/* ── Layer Analysis Panel ───────────────────────── */
.layer-panel { padding-bottom: 12px; }

.layer-clean {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  border-radius: var(--radius-lg);
  background: #052e1655;
  border: 1px solid #166534;
}
.layer-clean-icon { font-size: 19px; flex-shrink: 0; margin-top: 1px; }
.layer-clean-title {
  font-size: 13px;
  font-weight: 700;
  color: #86efac;
  line-height: 1.3;
}
.layer-clean-sub {
  font-size: 12px;
  color: #4ade80;
  margin-top: 2px;
  line-height: 1.5;
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
  font-size: 12px;
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
  padding: 6px 8px;
  border-radius: var(--radius-md);
  background: var(--surface-card);
  border-left: 3px solid transparent;
  transition: background var(--transition-fast), transform var(--transition-fast);
}
.layer-item:hover { transform: translateY(-1px); }
.layer-item-high   { border-left-color: #ef4444; background: #1c1010; }
.layer-item-high:hover   { background: #241414; }
.layer-item-medium { border-left-color: #f59e0b; background: #1c1800; }
.layer-item-medium:hover { background: #241f04; }

.layer-item-icon { font-size: 13px; flex-shrink: 0; margin-top: 1px; }
.layer-item-body { flex: 1; min-width: 0; }
.layer-item-msg {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.4;
  overflow-wrap: break-word;
  word-break: break-word;
}
.layer-item-src {
  font-size: 12px;
  color: var(--text-secondary);
  font-family: monospace;
  margin-top: 1px;
  overflow-wrap: break-word;
  word-break: break-word;
}

/* ── Integrated Metrics Dashboard ───────────────── */
.metrics-panel { padding-bottom: 10px; }

.metrics-grid {
  background: #0f172a;
  border-radius: var(--radius-lg);
  padding: 6px 0;
  overflow: hidden;
  border: 1px solid var(--border-card);
}
.mrow {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 5px 12px;
  gap: 8px;
  transition: background var(--transition-fast);
}
.mrow:hover { background: rgba(255,255,255,0.04); }
.mrow-sep {
  height: 1px;
  background: rgba(255,255,255,0.07);
  padding: 0;
  margin: 2px 0;
}
.mlabel {
  font-size: 12px;
  color: #e2e8f0;
  white-space: nowrap;
  flex-shrink: 0;
}
.mval {
  font-size: 13px;
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
.mi-label { font-size: 11px; font-weight: 500; color: #cbd5e1; font-family: inherit; }

.circ-details {
  margin-top: 8px;
  background: #1e1e2e;
  border-radius: 8px;
  padding: 6px 8px;
}
.circ-chain {
  font-size: 12px;
  color: #f87171;
  font-family: monospace;
  overflow-wrap: break-word;
  word-break: break-word;
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
  font-size: 12px;
  font-weight: 700;
  color: #4ade80;
  background: #052e16;
  padding: 2px 8px;
  border-radius: 10px;
  border: 1px solid #166534;
}
.git-total {
  font-size: 12px;
  color: #cbd5e1;
  font-weight: 600;
}

/* Quality snapshot bar */
.git-quality-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  background: var(--surface-card);
  border: 1px solid var(--border-card);
  border-radius: var(--radius-lg);
  padding: 7px 10px;
  margin-bottom: 8px;
}
.gq-item { display: flex; flex-direction: column; align-items: center; flex: 1; }
.gq-label { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-secondary); }
.gq-val   { font-size: 14px; font-weight: 800; font-family: monospace; line-height: 1.2; }
.gq-sub   { font-size: 9px; color: var(--text-secondary); text-align: center; }
.gq-divider { width: 1px; height: 28px; background: var(--border-card); flex-shrink: 0; }
.gq-ok      { color: #4ade80; }
.gq-caution { color: #fbbf24; }
.gq-warn    { color: #f87171; }

.git-list {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.git-trend-header {
  display: flex;
  align-items: center;
  padding: 3px 8px 3px 6px;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #e2e8f0;
  margin-bottom: 2px;
}
.gth-commit { flex: 1; }
.gth-loc   { width: 44px; text-align: right; }
.gth-fns   { width: 32px; text-align: right; }
.gth-mi    { width: 28px; text-align: right; cursor: help; }
.gth-delta { width: 42px; text-align: right; margin-left: 2px; cursor: help; }

.git-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-radius: var(--radius-md);
  background: var(--surface-card);
  border: 1px solid var(--border-card);
  cursor: default;
  transition: background var(--transition-fast), transform var(--transition-fast), box-shadow var(--transition-fast);
}
.git-item:hover { background: var(--surface-card-hover); transform: translateY(-1px); box-shadow: var(--shadow-sm); }

.git-left {
  flex: 1;
  display: flex;
  align-items: flex-start;
  gap: 6px;
  min-width: 0;
}
.git-hash {
  font-size: 12px;
  font-family: monospace;
  font-weight: 700;
  color: #a5b4fc;
  background: rgba(99,102,241,0.18);
  padding: 1px 5px;
  border-radius: 4px;
  flex-shrink: 0;
  margin-top: 1px;
}
.git-info { flex: 1; min-width: 0; }
.git-msg {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.4;
  overflow-wrap: break-word;
  word-break: break-word;
}
.git-date { font-size: 11px; color: var(--text-secondary); }

/* meta row under commit message: date + churn + files */
.git-meta-row {
  display: flex;
  align-items: center;
  gap: 5px;
  flex-wrap: wrap;
  margin-top: 1px;
}
.git-churn {
  font-size: 11px;
  font-weight: 700;
  font-family: monospace;
  padding: 0px 3px;
  border-radius: 3px;
}
.churn-high { color: #dc2626; background: #fee2e2; }
.churn-med  { color: #d97706; background: #fef3c7; }
.churn-low  { color: #64748b; background: #f1f5f9; }
.git-files  { font-size: 11px; color: #e2e8f0; }

.git-metrics-col {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 3px;
  flex-shrink: 0;
}
.git-loc-val {
  font-size: 12px;
  font-weight: 700;
  color: #cbd5e1;
  font-family: monospace;
  width: 44px;
  text-align: right;
}
.git-fns-val {
  font-size: 12px;
  font-weight: 700;
  color: #6366f1;
  font-family: monospace;
  width: 32px;
  text-align: right;
}
.git-mi-val {
  font-size: 12px;
  font-weight: 800;
  font-family: monospace;
  width: 28px;
  text-align: right;
}
.mi-ok      { color: #4ade80; }
.mi-caution { color: #fbbf24; }
.mi-warn    { color: #f87171; }
.git-delta-val {
  font-size: 12px;
  font-weight: 700;
  font-family: monospace;
  width: 42px;
  text-align: right;
}
.delta-pos  { color: #4ade80; }
.delta-neg  { color: #f87171; }
.delta-zero { color: #e2e8f0; }

/* Pagination */
.git-pagination {
  display: flex;
  gap: 6px;
  margin-top: 6px;
  flex-wrap: wrap;
}
.git-page-btn {
  flex: 1;
  font-size: 12px;
  font-weight: 600;
  padding: 5px 8px;
  border-radius: var(--radius-sm);
  border: 1px solid #6366f1;
  background: #eef2ff;
  color: #4f46e5;
  cursor: pointer;
  transition: background var(--transition-fast), transform var(--transition-fast);
}
.git-page-btn:hover { background: #e0e7ff; transform: translateY(-1px); }
.git-page-less { border-color: #94a3b8; background: #f8fafc; color: #64748b; }
.git-page-less:hover { background: #f1f5f9; }

.git-note {
  margin-top: 6px;
  font-size: 11px;
  color: #e2e8f0;
  line-height: 1.5;
  font-style: italic;
}

/* ── Git "How to Enable" hint panel ─────────────── */
.git-hint-panel { padding-bottom: 12px; }

.git-hint-box {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 9px 11px;
  border-radius: var(--radius-lg);
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  margin-bottom: 10px;
}
.git-hint-icon { font-size: 21px; flex-shrink: 0; }
.git-hint-title {
  font-size: 13px;
  font-weight: 700;
  color: #334155;
  margin-bottom: 3px;
}
.git-hint-sub {
  font-size: 12px;
  color: #64748b;
  line-height: 1.5;
}
.git-hint-sub code, .git-how-alt code {
  background: #e2e8f0;
  padding: 1px 4px;
  border-radius: 3px;
  font-family: monospace;
  font-size: 12px;
  color: #334155;
}

.git-how-steps-wrap {
  padding: 9px 11px;
  border-radius: var(--radius-lg);
  background: #fffbeb;
  border: 1px solid #fde68a;
}
.git-how-label {
  font-size: 12px;
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
  font-size: 12px;
  color: #78350f;
  line-height: 1.7;
}
.git-how-steps strong { color: #451a03; }
.git-how-alt {
  font-size: 12px;
  color: #78350f;
  line-height: 1.6;
  background: rgba(0,0,0,0.04);
  padding: 5px 8px;
  border-radius: 6px;
}

/* ── Upload Progress ──────────────────────────────── */
.upload-progress-wrap {
  margin-top: 10px;
}
.upload-stage-text {
  font-size: 12px;
  font-weight: 600;
  color: #818cf8;
  margin-bottom: 6px;
}
.upload-progress-track {
  height: 4px;
  background: #1e293b;
  border-radius: 3px;
  overflow: hidden;
}
.upload-progress-fill {
  height: 100%;
  width: 40%;
  background: linear-gradient(90deg, #818cf8, #6366f1);
  border-radius: 3px;
  box-shadow: 0 0 8px rgba(129, 140, 248, 0.5);
}
@media (prefers-reduced-motion: no-preference) {
  .upload-progress-fill {
    animation: progress-slide 1.5s cubic-bezier(0.4, 0, 0.2, 1) infinite;
  }
  @keyframes progress-slide {
    0%   { transform: translateX(-150%); }
    100% { transform: translateX(350%); }
  }
}

/* ── Search ───────────────────────────────────────── */
.search-wrap {
  position: relative;
}
.search-input {
  width: 100%;
  padding: 8px 12px;
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: var(--radius-md);
  color: #e2e8f0;
  font-size: 13px;
  outline: none;
  box-sizing: border-box;
  transition: border-color var(--transition-base), box-shadow var(--transition-base);
}
.search-input:hover {
  border-color: #475569;
}
.search-input:focus {
  border-color: #818cf8;
  box-shadow: 0 0 0 3px rgba(129, 140, 248, 0.18);
}
.search-input::placeholder {
  color: #cbd5e1;
}
.search-dropdown {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: var(--radius-md);
  overflow: hidden;
  z-index: 50;
  box-shadow: var(--shadow-lg);
  max-height: 260px;
  overflow-y: auto;
  transform-origin: top center;
}
.search-result-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  transition: background var(--transition-fast);
  border-bottom: 1px solid #0f172a;
}
.search-result-item:last-child { border-bottom: none; }
.search-result-item:hover { background: #253347; }
.search-result-icon {
  font-size: 14px;
  width: 18px;
  text-align: center;
  flex-shrink: 0;
  color: #cbd5e1;
}
.search-result-icon.function { color: #10b981; }
.search-result-icon.file     { color: #f59e0b; }
.search-result-icon.module   { color: #3b82f6; }
.search-result-body {
  flex: 1;
  min-width: 0;
}
.search-result-name {
  font-size: 13px;
  font-weight: 600;
  color: #e2e8f0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.search-result-file {
  font-size: 12px;
  color: #cbd5e1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.search-risk-badge {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 5px;
  border-radius: 4px;
  flex-shrink: 0;
}
.search-risk-badge.risk-high   { background: #ef444433; color: #f87171; }
.search-risk-badge.risk-medium { background: #f59e0b33; color: #fbbf24; }
.search-risk-badge.risk-low    { background: #22c55e33; color: #4ade80; }
.search-not-visible {
  font-size: 12px;
  color: #cbd5e1;
  flex-shrink: 0;
}

/* ── Architecture Patterns Panel ───────────────────── */
.patterns-summary-chip {
  display: inline-block;
  background: #1e3a5f;
  color: #93c5fd;
  font-size: 12px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 10px;
  margin-bottom: 10px;
}
.patterns-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.pattern-card {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: var(--radius-md);
  padding: 10px 11px;
  transition: border-color var(--transition-base), box-shadow var(--transition-base), transform var(--transition-base);
}
.pattern-card:hover {
  border-color: #475569;
  box-shadow: var(--shadow-sm);
  transform: translateY(-1px);
}
.pattern-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.pattern-name {
  font-size: 15px;
  font-weight: 700;
  color: #e2e8f0;
}
.pattern-name-group {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.pattern-subtitle {
  font-size: 12px;
  color: #7dd3fc;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pattern-name-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.pattern-category-badge {
  font-size: 10.5px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #a78bfa;
  background: #2e1065;
  border-radius: 6px;
  padding: 1px 6px;
  flex-shrink: 0;
}
.pattern-tier-label {
  font-size: 10.5px;
  color: #e2e8f0;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.pattern-definition {
  font-size: 14px;
  color: #e2e8f0;
  line-height: 1.55;
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 6px;
  padding: 9px 11px;
  margin: 6px 0 8px;
}
.pattern-why {
  display: block;
  font-size: 13px;
  color: #e2e8f0;
  margin-top: 5px;
}
.pattern-evidence-details {
  margin-top: 4px;
  margin-bottom: 5px;
}
.pattern-evidence-summary {
  cursor: pointer;
  list-style: none;
  font-size: 10.5px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #e2e8f0;
  padding: 2px 0;
  border-radius: var(--radius-sm);
  transition: color var(--transition-fast);
}
.pattern-evidence-summary:hover {
  color: #cbd5e1;
}
.pattern-evidence-summary::-webkit-details-marker {
  display: none;
}
.pattern-evidence-summary::before {
  content: "▸ ";
}
.pattern-evidence-details[open] > .pattern-evidence-summary::before {
  content: "▾ ";
}
.pattern-evidence-details .pattern-evidence-groups,
.pattern-evidence-details .pattern-evidence {
  margin-top: 5px;
}
.pattern-instance-count {
  font-size: 10.5px;
  font-weight: 700;
  color: #e2e8f0;
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 6px;
  padding: 1px 6px;
  flex-shrink: 0;
}
.pattern-instance {
  border-top: 1px solid #334155;
  padding-top: 6px;
  margin-top: 6px;
}
.pattern-instance:first-of-type {
  border-top: none;
  padding-top: 0;
  margin-top: 4px;
}
.pattern-instance-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  cursor: pointer;
  list-style: none;
  padding: 3px 4px;
  margin: 0 -4px;
  border-radius: var(--radius-sm);
  transition: background var(--transition-fast);
}
.pattern-instance-summary:hover {
  background: rgba(255,255,255,0.04);
}
.pattern-instance-summary::-webkit-details-marker {
  display: none;
}
.pattern-instance-summary::before {
  content: "▸";
  color: #cbd5e1;
  font-size: 11px;
  margin-right: 4px;
}
details[open] > .pattern-instance-summary::before {
  content: "▾";
}
.pattern-instance-binding {
  font-size: 14px;
  font-weight: 600;
  color: #e2e8f0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pattern-instance-conf {
  font-size: 11.5px;
  font-weight: 700;
  color: #e2e8f0;
  flex-shrink: 0;
}
.pattern-evidence-groups {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 5px;
}
.pattern-evidence-group {
  border-left: 2px solid #334155;
  padding-left: 6px;
}
.pattern-evidence-group-head {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-bottom: 1px;
}
.pattern-evidence-label {
  font-size: 11.5px;
  font-weight: 700;
  color: #7dd3fc;
}
.pattern-evidence-role {
  font-size: 10.5px;
  color: #e2e8f0;
}
.pattern-evidence-weak {
  font-size: 10.5px;
  color: #fb923c;
}
.pattern-conf-badge {
  font-size: 13px;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 8px;
  flex-shrink: 0;
}
.pconf-high { background: #14532d; color: #4ade80; }
.pconf-med  { background: #422006; color: #fbbf24; }
.pconf-low  { background: #1e1b4b; color: #a5b4fc; }
.pconf-heuristic { background: #422006; color: #fb923c; border: 1px dashed #fb923c66; }
.pattern-evidence {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-bottom: 5px;
}
.pattern-evidence-item {
  font-size: 11.5px;
  color: #e2e8f0;
  line-height: 1.5;
}
.pattern-components {
  margin-top: 7px;
  border-top: 1px solid #334155;
  padding-top: 6px;
  margin-bottom: 2px;
}
.pattern-components-label {
  font-size: 10.5px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #e2e8f0;
  margin-bottom: 5px;
}
.pattern-layer-row {
  display: flex;
  align-items: baseline;
  gap: 4px;
  line-height: 1.6;
}
.ptree-prefix {
  font-size: 12px;
  color: #cbd5e1;
  flex-shrink: 0;
  font-family: monospace;
}
.pattern-layer-name {
  font-size: 12px;
  font-weight: 600;
  color: #7dd3fc;
  flex-shrink: 0;
}
.pattern-layer-files {
  font-size: 12px;
  color: #e2e8f0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.pattern-violations {
  margin-top: 6px;
  border-top: 1px solid #334155;
  padding-top: 6px;
}
.pattern-violations-label {
  font-size: 12px;
  font-weight: 600;
  color: #f87171;
  margin-bottom: 4px;
}
.pattern-violation-item {
  font-size: 11px;
  color: #fca5a5;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pattern-violation-more {
  font-size: 11px;
  color: #cbd5e1;
  margin-top: 2px;
}
.patterns-empty {
  font-size: 12px;
  color: #cbd5e1;
  padding: 6px 0;
}
</style>
