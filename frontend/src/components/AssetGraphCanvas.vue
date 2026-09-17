<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { Graph } from "@antv/g6";

import type { AssetMapData, AssetMapEdge, AssetMapNode } from "../lib/api";
import ParticleGraphCanvas from "./ParticleGraphCanvas.vue";

const props = defineProps<{ data: AssetMapData; selectedId: string; mode: "architecture" | "explore"; theme: "light" | "particle"; drawerOpen: boolean }>();
const emit = defineEmits<{ select: [node: AssetMapNode]; clear: [] }>();
const container = ref<HTMLDivElement | null>(null);
const renderError = ref("");
const hoveredId = ref("");
let graph: Graph | null = null;
let resizeObserver: ResizeObserver | null = null;
let g6Runtime: typeof import("@antv/g6") | null = null;

const nodeColors: Record<string, { fill: string; stroke: string; text: string }> = {
  company: { fill: "#e8f2ff", stroke: "#367eee", text: "#17406f" },
  platform: { fill: "#f0ebff", stroke: "#8064e8", text: "#3e2b83" },
  registration_identity: { fill: "#eff3f8", stroke: "#8290a5", text: "#35445a" },
  platform_account: { fill: "#e3faf3", stroke: "#13a77e", text: "#075d49" },
  resource: { fill: "#fff3df", stroke: "#e79124", text: "#784209" },
  system: { fill: "#fff0f5", stroke: "#db5d8a", text: "#7e2445" },
  person: { fill: "#eef2f8", stroke: "#69798e", text: "#2e3c50" },
};
const particleNodeColors: Record<string, { fill: string; stroke: string; text: string }> = {
  company: { fill: "#10223a", stroke: "#3b82f6", text: "#e0e8ff" },
  platform: { fill: "#211b42", stroke: "#a78bfa", text: "#e5ddff" },
  registration_identity: { fill: "#182432", stroke: "#94a3b8", text: "#dce7f5" },
  platform_account: { fill: "#0d2f2b", stroke: "#14b8a6", text: "#d5fff0" },
  resource: { fill: "#10273c", stroke: "#60a5fa", text: "#dbeafe" },
  system: { fill: "#241c42", stroke: "#8b5cf6", text: "#eee8ff" },
  person: { fill: "#202937", stroke: "#b9c8db", text: "#e5eef9" },
};

async function loadG6() {
  if (!g6Runtime) g6Runtime = await import("@antv/g6");
  return g6Runtime;
}

function plainData() {
  return {
    nodes: props.data.nodes.map((node) => ({ id: node.id, data: { ...node } as Record<string, unknown> })),
    edges: props.data.edges.map((edge) => ({ id: edge.id, source: edge.source, target: edge.target, data: { ...edge } as Record<string, unknown> })),
  };
}

function nodeFromDatum(datum: { data?: unknown }) { return datum.data as AssetMapNode; }
function edgeFromDatum(datum: { data?: unknown }) { return datum.data as AssetMapEdge; }
function shortLabel(value: string, length = 12) { return value.length > length ? `${value.slice(0, length)}…` : value; }
function nodeLabel(node: AssetMapNode) {
  const title = shortLabel(node.label);
  const detail = shortLabel(node.subtitle || node.kind, 10);
  return `${title}\n${detail}`;
}
function centerNodeId() {
  return props.selectedId
    || props.data.nodes.find((node) => node.kind === "platform_account")?.id
    || props.data.nodes.find((node) => node.kind === "platform")?.id
    || props.data.nodes[0]?.id;
}
function colorsFor(kind: string) { return (props.theme === "particle" ? particleNodeColors : nodeColors)[kind] ?? (props.theme === "particle" ? particleNodeColors.resource : nodeColors.resource); }
function focusId() { return hoveredId.value || props.selectedId; }
function nodeIdFromEvent(event: unknown) { return String((event as { target?: { id?: string } }).target?.id ?? ""); }

async function applyStates() {
  if (!graph) return;
  const focus = props.theme === "particle" ? props.selectedId : focusId();
  const neighbors = new Set<string>();
  const activeEdges = new Set<string>();
  if (focus) {
    neighbors.add(focus);
    props.data.edges.forEach((edge) => {
      if (edge.source === focus) { neighbors.add(edge.target); activeEdges.add(edge.id); }
      if (edge.target === focus) { neighbors.add(edge.source); activeEdges.add(edge.id); }
    });
  }
  const states: Record<string, string[]> = {};
  props.data.nodes.forEach((node) => {
    states[node.id] = !focus
      ? []
      : node.id === focus
        ? ["focus", ...(props.selectedId === node.id ? ["selected"] : [])]
        : neighbors.has(node.id) ? ["related"] : ["muted"];
  });
  props.data.edges.forEach((edge) => {
    states[edge.id] = !focus ? [] : activeEdges.has(edge.id) ? ["focus"] : ["muted"];
  });
  await graph.setElementState(states, true);
}

async function fitGraph() {
  if (!graph) return;
  await graph.fitView({ when: "always", direction: "both" }, { duration: 360, easing: "ease-out" });
  if (props.drawerOpen && props.theme !== "particle") await graph.translateBy([-128, 0], { duration: 240, easing: "ease-out" });
}

async function renderGraph() {
  graph?.destroy();
  graph = null;
  if (!container.value) return;
  try {
    const { CanvasEvent, Graph, NodeEvent } = await loadG6();
    renderError.value = "";
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    graph = new Graph({
      container: container.value,
      data: plainData(),
      autoFit: "view",
      zoomRange: [0.35, 2.35],
      layout: props.theme === "particle" ? {
        type: "force",
        linkDistance: 170,
        nodeStrength: -210,
        edgeStrength: 0.72,
        collideStrength: 0.88,
        preventOverlap: true,
        nodeSize: 42,
        nodeSpacing: 28,
        animation: !reduceMotion,
      } : {
        type: "radial",
        focusNode: centerNodeId(),
        nodeSize: [102, 102],
        unitRadius: props.mode === "architecture" ? 185 : 162,
        linkDistance: 196,
        preventOverlap: true,
        nodeSpacing: 42,
        strictRadial: false,
        animation: !reduceMotion,
      },
      node: {
        type: "circle",
        style: {
          size: props.theme === "particle" ? 30 : 94,
          cursor: "pointer",
          lineWidth: props.theme === "particle" ? 1.5 : 2.5,
          fill: (datum) => colorsFor(nodeFromDatum(datum)?.kind).fill,
          stroke: (datum) => colorsFor(nodeFromDatum(datum)?.kind).stroke,
          labelText: (datum) => props.theme === "particle" ? shortLabel(nodeFromDatum(datum).label, 18) : nodeLabel(nodeFromDatum(datum)),
          labelFill: (datum) => colorsFor(nodeFromDatum(datum)?.kind).text,
          labelFontWeight: 750,
          labelLineHeight: 15,
          labelPlacement: props.theme === "particle" ? "bottom" : "center",
          labelTextAlign: "center",
          labelOffsetY: props.theme === "particle" ? 11 : 0,
          labelFontSize: props.theme === "particle" ? 12 : 10,
          labelOpacity: props.theme === "particle" ? 0.72 : 1,
          halo: props.theme === "particle",
          haloLineWidth: props.theme === "particle" ? 10 : 0,
          haloStroke: (datum) => colorsFor(nodeFromDatum(datum)?.kind).stroke,
          haloStrokeOpacity: props.theme === "particle" ? 0.18 : 0,
          shadowColor: props.theme === "particle" ? "rgba(100, 200, 255, .5)" : "rgba(57, 91, 147, .18)",
          shadowBlur: props.theme === "particle" ? 18 : 17,
          shadowOffsetY: 0,
        },
        state: {
          focus: { size: props.theme === "particle" ? 48 : 138, lineWidth: props.theme === "particle" ? 3 : 4, halo: true, haloLineWidth: props.theme === "particle" ? 18 : 18, haloStroke: props.theme === "particle" ? "#64c8ff" : "#72a5ff", haloStrokeOpacity: props.theme === "particle" ? 0.5 : 0.28, shadowBlur: props.theme === "particle" ? 42 : 34, shadowColor: props.theme === "particle" ? "rgba(100, 200, 255, .7)" : "rgba(73, 126, 223, .42)", labelFontSize: props.theme === "particle" ? 15 : 12, labelOpacity: 1 },
          selected: { lineWidth: props.theme === "particle" ? 2.5 : 5, haloStroke: props.theme === "particle" ? "#14b8a6" : "#6952df", haloStrokeOpacity: props.theme === "particle" ? 0.42 : 0.32 },
          related: { size: props.theme === "particle" ? 30 : 82, opacity: 0.95, lineWidth: props.theme === "particle" ? 2 : 2.5, shadowBlur: props.theme === "particle" ? 18 : 12, labelOpacity: props.theme === "particle" ? 0.85 : 1 },
          muted: { size: props.theme === "particle" ? 28 : 54, opacity: props.theme === "particle" ? 0.32 : 0.22, lineWidth: props.theme === "particle" ? 1 : 1, shadowBlur: 0, labelOpacity: props.theme === "particle" ? 0.16 : 0.3 },
        },
      },
      edge: {
        type: "line",
        style: {
          stroke: props.theme === "particle" ? "#2d4964" : "#b7c7df",
          lineWidth: 1.25,
          endArrow: false,
          labelText: (datum) => edgeFromDatum(datum)?.relation ?? "",
          labelFontSize: 10,
          labelFill: props.theme === "particle" ? "#9fb7d3" : "#45617f",
          labelBackground: true,
          labelBackgroundFill: props.theme === "particle" ? "#111b29" : "#ffffff",
          labelBackgroundStroke: props.theme === "particle" ? "#2f506d" : "#d5e0ee",
          labelBackgroundLineWidth: 1,
          labelBackgroundRadius: 8,
          labelPadding: [4, 7],
          labelOpacity: 0,
        },
        state: {
          focus: { stroke: props.theme === "particle" ? "#64c8ff" : "#5b8ff9", lineWidth: 2.4, labelOpacity: 1, labelFill: props.theme === "particle" ? "#d8f3ff" : "#2d61b6", opacity: 1 },
          muted: { opacity: 0.08, labelOpacity: 0 },
        },
      },
      behaviors: ["drag-canvas", "zoom-canvas", "drag-element"],
    });
    graph.on(NodeEvent.POINTER_ENTER, (event) => { hoveredId.value = nodeIdFromEvent(event); void applyStates(); });
    graph.on(NodeEvent.POINTER_LEAVE, (event) => { if (hoveredId.value === nodeIdFromEvent(event)) { hoveredId.value = ""; void applyStates(); } });
    graph.on(NodeEvent.CLICK, (event) => {
      const node = props.data.nodes.find((item) => item.id === nodeIdFromEvent(event));
      if (node) emit("select", node);
    });
    graph.on(CanvasEvent.CLICK, () => emit("clear"));
    await graph.render();
    await applyStates();
    await fitGraph();
  } catch (reason) {
    graph?.destroy();
    graph = null;
    renderError.value = "当前内置浏览器暂不支持关系画布，可使用平台总览继续查看资产；技术团队已收到兼容性提示。";
    console.warn("Asset map canvas is unavailable", reason);
  }
}

watch(() => [props.data, props.mode, props.theme] as const, () => { hoveredId.value = ""; void renderGraph(); }, { deep: true });
watch(() => props.selectedId, () => { void applyStates(); });
watch(() => props.drawerOpen, () => { void fitGraph(); });
onMounted(() => {
  void renderGraph();
  resizeObserver = new ResizeObserver(() => { graph?.resize(); void fitGraph(); });
  if (container.value) resizeObserver.observe(container.value);
});
onBeforeUnmount(() => { resizeObserver?.disconnect(); graph?.destroy(); graph = null; });
</script>

<template>
  <ParticleGraphCanvas v-if="props.theme === 'particle'" :data="props.data" :selected-id="props.selectedId" :mode="props.mode" :drawer-open="props.drawerOpen" @select="emit('select', $event)" @clear="emit('clear')" />
  <div v-else ref="container" class="g6-asset-canvas" aria-label="资产关系图"><div v-if="renderError" class="g6-fallback">{{ renderError }}</div></div>
</template>
