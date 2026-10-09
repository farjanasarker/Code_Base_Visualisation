<script setup>
import { ref, watch, inject } from 'vue';

const sessionManager = inject('sessionManager');

const props = defineProps({
  functionNodeId: { type: String, required: true }, // "<file_path>::<function_name>"
  functionLabel: { type: String, default: '' },
});

const emit = defineEmits(['close', 'run-complete', 'slice-complete']);

const loadingParams = ref(true);
const paramError = ref(null);
const params = ref([]); // [{name, type_hint, unsupported}]
const values = ref({}); // name -> raw string/bool input value
const isMethod = ref(false);

const running = ref(false);
const runError = ref(null);
const runResult = ref(null); // the /run response

const sliceVariable = ref('');
const sliceStatementId = ref('');
const slicing = ref(false);
const sliceError = ref(null);

async function loadParams() {
  loadingParams.value = true;
  paramError.value = null;
  try {
    const res = await sessionManager.apiCall(
      `/dynamic/functions/${encodeURIComponent(props.functionNodeId)}/params`,
      { method: 'POST' }
    );
    const data = await res.json();
    isMethod.value = data.is_method;
    params.value = data.params;
    const initial = {};
    for (const p of data.params) {
      initial[p.name] = p.type_hint === 'bool' ? false : '';
    }
    values.value = initial;
  } catch (e) {
    paramError.value = e.message || 'Failed to load parameters';
  } finally {
    loadingParams.value = false;
  }
}

watch(() => props.functionNodeId, loadParams, { immediate: true });

function widgetFor(param) {
  if (param.type_hint === 'int' || param.type_hint === 'float') return 'number';
  if (param.type_hint === 'bool') return 'checkbox';
  if (param.type_hint === 'str') return 'text';
  return 'json'; // list/tuple/dict, or no annotation at all
}

function coerceValue(param) {
  const raw = values.value[param.name];
  const widget = widgetFor(param);
  if (widget === 'number') {
    const n = Number(raw);
    if (Number.isNaN(n)) throw new Error(`'${param.name}' must be a number`);
    return n;
  }
  if (widget === 'checkbox') return !!raw;
  if (widget === 'text') return String(raw ?? '');
  // JSON-literal widget (list/tuple/dict/unannotated)
  try {
    return JSON.parse(raw === '' || raw == null ? 'null' : raw);
  } catch {
    throw new Error(`'${param.name}' must be valid JSON (e.g. [1, 2, 3] or {"a": 1})`);
  }
}

const hasUnsupportedParam = () => params.value.some((p) => p.unsupported);

async function runFunction() {
  runError.value = null;
  runResult.value = null;
  if (isMethod.value) {
    runError.value = 'Dynamic analysis of class methods is not supported yet.';
    return;
  }
  if (hasUnsupportedParam()) {
    runError.value = 'One or more parameters have an unsupported type — cannot run.';
    return;
  }

  let inputs;
  try {
    inputs = {};
    for (const p of params.value) inputs[p.name] = coerceValue(p);
  } catch (e) {
    runError.value = e.message;
    return;
  }

  running.value = true;
  try {
    const res = await sessionManager.apiCall(
      `/dynamic/functions/${encodeURIComponent(props.functionNodeId)}/run`,
      { method: 'POST', body: JSON.stringify({ inputs }) }
    );
    const data = await res.json();
    if (data.status === 'error' || data.status === 'sandbox_unavailable') {
      runError.value = data.error || 'Execution failed';
      return;
    }
    runResult.value = data;
    emit('run-complete', data);
  } catch (e) {
    runError.value = e.message || 'Execution failed';
  } finally {
    running.value = false;
  }
}

function pickCriterion(stmt, variable) {
  sliceStatementId.value = stmt.id;
  sliceVariable.value = variable;
}

async function runSlice() {
  if (!sliceStatementId.value || !sliceVariable.value) return;
  slicing.value = true;
  sliceError.value = null;
  try {
    const res = await sessionManager.apiCall(
      `/dynamic/runs/${encodeURIComponent(runResult.value.run_id)}/slice`,
      { method: 'POST', body: JSON.stringify({
        statement_node_id: sliceStatementId.value,
        variable_name: sliceVariable.value,
      }) }
    );
    const data = await res.json();
    emit('slice-complete', data);
  } catch (e) {
    sliceError.value = e.message || 'Slicing failed';
  } finally {
    slicing.value = false;
  }
}
</script>

<template>
  <div class="slice-form-backdrop" @click.self="emit('close')">
    <div class="slice-form-panel">
      <div class="slice-form-head">
        <span>▶ Run Dynamic Slice: <strong>{{ functionLabel || functionNodeId }}</strong></span>
        <button class="slice-close-btn" @click="emit('close')">✕</button>
      </div>

      <div v-if="loadingParams" class="slice-loading">Loading parameters…</div>
      <div v-else-if="paramError" class="slice-error">{{ paramError }}</div>

      <template v-else-if="isMethod">
        <div class="slice-error">Dynamic analysis of class methods is not supported in this MVP.</div>
      </template>

      <template v-else>
        <div v-if="params.length === 0" class="slice-hint">This function takes no parameters.</div>

        <div v-for="p in params" :key="p.name" class="slice-param-row">
          <label class="slice-param-label">
            {{ p.name }}
            <span v-if="p.type_hint" class="slice-param-type">: {{ p.type_hint }}</span>
          </label>

          <div v-if="p.unsupported" class="slice-error slice-param-unsupported">
            Unsupported type ({{ p.type_hint }}) — cannot run this function.
          </div>
          <input v-else-if="widgetFor(p) === 'number'" type="number" v-model="values[p.name]" />
          <input v-else-if="widgetFor(p) === 'checkbox'" type="checkbox" v-model="values[p.name]" />
          <input v-else-if="widgetFor(p) === 'text'" type="text" v-model="values[p.name]" />
          <textarea v-else v-model="values[p.name]" placeholder='JSON literal, e.g. [1, 2, 3]' rows="2"></textarea>
        </div>

        <button class="slice-run-btn" :disabled="running || hasUnsupportedParam()" @click="runFunction">
          {{ running ? 'Running…' : 'Run' }}
        </button>

        <div v-if="runError" class="slice-error">{{ runError }}</div>

        <template v-if="runResult">
          <div class="slice-run-summary">
            <div v-if="runResult.truncated" class="slice-warning">
              ⚠ Execution hit the step limit — trace is partial.
            </div>
            Executed {{ runResult.executed_node_ids.length }} statement(s).
          </div>

          <div class="slice-criterion-hint">Click a variable below to slice on it:</div>
          <div class="slice-stmt-list">
            <div v-for="stmt in runResult.statements" :key="stmt.id" class="slice-stmt-row">
              <span class="slice-stmt-code">{{ stmt.source_text }}</span>
              <span
                v-for="v in [...new Set([...stmt.reads, ...stmt.writes])]"
                :key="v"
                class="slice-var-chip"
                :class="{ active: sliceStatementId === stmt.id && sliceVariable === v }"
                @click="pickCriterion(stmt, v)"
              >{{ v }}</span>
            </div>
          </div>

          <button
            v-if="sliceStatementId && sliceVariable"
            class="slice-run-btn"
            :disabled="slicing"
            @click="runSlice"
          >
            {{ slicing ? 'Slicing…' : `Slice on ${sliceVariable}` }}
          </button>
          <div v-if="sliceError" class="slice-error">{{ sliceError }}</div>
        </template>
      </template>
    </div>
  </div>
</template>

<style scoped>
.slice-form-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  backdrop-filter: blur(2px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}
.slice-form-panel {
  width: 360px;
  max-width: calc(100% - 32px);
  max-height: calc(100% - 64px);
  overflow-y: auto;
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 12px;
  padding: 16px;
  box-shadow: 0 12px 32px rgba(0,0,0,0.45);
  color: #e2e8f0;
  font-size: 13px;
}
.slice-form-panel::-webkit-scrollbar { width: 8px; }
.slice-form-panel::-webkit-scrollbar-track { background: transparent; }
.slice-form-panel::-webkit-scrollbar-thumb { background: #334155; border-radius: 8px; }
.slice-form-panel::-webkit-scrollbar-thumb:hover { background: #475569; }
@media (prefers-reduced-motion: no-preference) {
  .slice-form-backdrop {
    animation: slice-backdrop-in 160ms ease-out both;
  }
  .slice-form-panel {
    animation: slice-panel-in 200ms cubic-bezier(0.2, 0.8, 0.2, 1) both;
  }
  @keyframes slice-backdrop-in {
    from { opacity: 0; }
    to   { opacity: 1; }
  }
  @keyframes slice-panel-in {
    from { opacity: 0; transform: translateY(8px) scale(0.98); }
    to   { opacity: 1; transform: translateY(0) scale(1); }
  }
}
.slice-form-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 700;
  margin-bottom: 12px;
  color: #34d399;
}
.slice-close-btn {
  background: transparent;
  border: none;
  border-radius: 6px;
  color: #94a3b8;
  cursor: pointer;
  font-size: 13px;
  padding: 2px 6px;
  transition: background 140ms ease, color 140ms ease;
}
.slice-close-btn:hover {
  background: #1e293b;
  color: #e2e8f0;
}
.slice-loading, .slice-hint {
  color: #94a3b8;
  font-style: italic;
  font-size: 12px;
}
.slice-error {
  color: #fca5a5;
  font-size: 12px;
  margin: 6px 0;
}
.slice-param-row {
  margin-bottom: 10px;
}
.slice-param-label {
  display: block;
  font-size: 12px;
  color: #cbd5e1;
  margin-bottom: 4px;
}
.slice-param-type {
  color: #64748b;
}
.slice-param-row input,
.slice-param-row textarea {
  width: 100%;
  box-sizing: border-box;
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 6px;
  color: #e2e8f0;
  padding: 6px 8px;
  font-size: 12px;
  font-family: inherit;
  transition: border-color 140ms ease, box-shadow 140ms ease;
}
.slice-param-row input:hover,
.slice-param-row textarea:hover {
  border-color: #475569;
}
.slice-param-row input:focus,
.slice-param-row textarea:focus {
  outline: none;
  border-color: #34d399;
  box-shadow: 0 0 0 3px rgba(52, 211, 153, 0.18);
}
.slice-param-row input[type="checkbox"] {
  width: auto;
}
.slice-run-btn {
  width: 100%;
  background: #059669;
  border: none;
  border-radius: 6px;
  color: #fff;
  font-weight: 700;
  padding: 8px;
  cursor: pointer;
  margin-top: 4px;
  transition: background 140ms ease, transform 140ms ease, box-shadow 140ms ease;
}
.slice-run-btn:hover:not(:disabled) {
  background: #047857;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(5, 150, 105, 0.35);
}
.slice-run-btn:active:not(:disabled) { transform: translateY(0); }
.slice-run-btn:disabled {
  background: #334155;
  cursor: not-allowed;
}
.slice-run-summary {
  margin-top: 12px;
  font-size: 12px;
  color: #cbd5e1;
}
.slice-warning {
  color: #fbbf24;
  margin-bottom: 4px;
}
.slice-criterion-hint {
  margin-top: 10px;
  font-size: 11px;
  color: #64748b;
}
.slice-stmt-list {
  margin-top: 6px;
  max-height: 160px;
  overflow-y: auto;
}
.slice-stmt-list::-webkit-scrollbar { width: 6px; }
.slice-stmt-list::-webkit-scrollbar-track { background: transparent; }
.slice-stmt-list::-webkit-scrollbar-thumb { background: #334155; border-radius: 8px; }
.slice-stmt-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  padding: 4px 0;
  border-bottom: 1px solid #1e293b;
}
.slice-stmt-code {
  font-family: monospace;
  font-size: 11px;
  color: #94a3b8;
  flex: 1;
  min-width: 100px;
}
.slice-var-chip {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 4px;
  padding: 1px 6px;
  font-size: 11px;
  color: #34d399;
  cursor: pointer;
  transition: background 120ms ease, border-color 120ms ease, transform 120ms ease;
}
.slice-var-chip:hover {
  background: #263a33;
  border-color: #34d399;
  transform: translateY(-1px);
}
.slice-var-chip.active {
  background: #059669;
  color: #fff;
  border-color: #059669;
}
</style>
