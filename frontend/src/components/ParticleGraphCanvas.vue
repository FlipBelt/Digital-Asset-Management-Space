<script setup lang="ts">
import { computed, ref } from "vue";

import type { AssetMapData, AssetMapEdge, AssetMapNode } from "../lib/api";

const props = defineProps<{ data: AssetMapData; selectedId: string; mode: "architecture" | "explore"; drawerOpen: boolean }>();
const emit = defineEmits<{ select: [node: AssetMapNode]; clear: [] }>();

const WIDTH = 1440;
const HEIGHT = 700;
const pan = ref({ x: 0, y: 0 });
const zoom = ref(1);
const dragging = ref(false);
const moved = ref(false);
const pointer = ref({ x: 0, y: 0 });

const colors: Record<string, { fill: string; stroke: string; label: string }> = {
  company: { fill: "#10223a", stroke: "#3b82f6", label: "#c8dcff" },
  platform: { fill: "#211b42", stroke: "#a78bfa", label: "#e5ddff" },
  registration_identity: { fill: "#182432", stroke: "#94a3b8", label: "#dce7f5" },
  platform_account: { fill: "#0d2f2b", stroke: "#14b8a6", label: "#d5fff0" },
  resource: { fill: "#10273c", stroke: "#60a5fa", label: "#dbeafe" },
  system: { fill: "#241c42", stroke: "#8b5cf6", label: "#eee8ff" },
  person: { fill: "#202937", stroke: "#b9c8db", label: "#e5eef9" },
};

function colorFor(kind: string) { return colors[kind] ?? colors.resource; }
function shortLabel(value: string, length = 18) { return value.length > length ? `${value.slice(0, length)}…` : value; }
function centerId() {
  const platform = props.data.nodes.find((node) => node.kind === "platform");
  if (platform) {
    const accountEdge = props.data.edges.find((edge) =>
      edge.source === platform.id && edge.relation === "拥有账号"
    );
    const account = accountEdge && props.data.nodes.find((node) => node.id === accountEdge.target);
    if (account) return account.id;
    return platform.id;
  }
  return props.selectedId
    || props.data.nodes.find((node) => node.kind === "platform_account")?.id
    || props.data.nodes[0]?.id
    || "";
}

const focusId = computed(() => props.selectedId || "");
const centerNodeId = computed(() => centerId());
const layoutNeighborIds = computed(() => {
  const id = centerNodeId.value;
  if (!id) return new Set<string>();
  const result = new Set<string>([id]);
  props.data.edges.forEach((edge) => {
    if (edge.source === id) result.add(edge.target);
    if (edge.target === id) result.add(edge.source);
  });
  return result;
});
const activeEdges = computed(() => {
  const id = focusId.value;
  return new Set(props.data.edges.filter((edge) => edge.source === id || edge.target === id).map((edge) => edge.id));
});

const positions = computed(() => {
  const center = centerNodeId.value;
  const result = new Map<string, { x: number; y: number }>();
  if (!center) return result;
  const centerPoint = { x: WIDTH / 2, y: HEIGHT / 2 - 8 };
  result.set(center, centerPoint);
  const others = props.data.nodes.filter((node) => node.id !== center).slice().sort((a, b) => {
    const aRelated = layoutNeighborIds.value.has(a.id) ? 0 : 1;
    const bRelated = layoutNeighborIds.value.has(b.id) ? 0 : 1;
    return aRelated - bRelated || a.kind.localeCompare(b.kind) || a.label.localeCompare(b.label);
  });
  const count = others.length;
  const relatedCount = others.filter((item) => layoutNeighborIds.value.has(item.id)).length;
  const points = others.map((node, index) => {
    const related = layoutNeighborIds.value.has(node.id);
    const ringIndex = related
      ? others.slice(0, index + 1).filter((item) => layoutNeighborIds.value.has(item.id)).length - 1
      : index - relatedCount;
    const ringSize = related ? Math.max(relatedCount, 1) : Math.max(count - relatedCount, 1);
    const radius = related
      ? Math.min(282, 226 + relatedCount * 8)
      : Math.min(380, 315 + Math.max(0, count - relatedCount - 6) * 8);
    let hash = 0;
    for (const char of node.id) hash = (hash * 31 + char.charCodeAt(0)) % 997;
    const jitter = (hash / 997 - 0.5) * 0.18;
    const angle = (ringIndex / ringSize) * Math.PI * 2 - Math.PI / 2 + jitter + (related ? 0 : 0.24);
    return {
      node,
      x: WIDTH / 2 + Math.cos(angle) * radius,
      y: HEIGHT / 2 - 8 + Math.sin(angle) * radius * 0.72,
      targetX: WIDTH / 2 + Math.cos(angle) * radius,
      targetY: HEIGHT / 2 - 8 + Math.sin(angle) * radius * 0.72,
    };
  });
  // Deterministic relaxation keeps labels and rings apart without introducing
  // a continuously running force simulation (which is what caused the old
  // constellation to drift and stutter on larger graphs).
  for (let iteration = 0; iteration < 72; iteration += 1) {
    points.forEach((point, index) => {
      for (let otherIndex = index + 1; otherIndex < points.length; otherIndex += 1) {
        const other = points[otherIndex];
        let dx = other.x - point.x;
        let dy = other.y - point.y;
        let distance = Math.hypot(dx, dy);
        if (!distance) { dx = 1; dy = 0; distance = 1; }
        const minimum = Math.min(220, 132 + Math.max(point.node.label.length, other.node.label.length) * 1.8);
        if (distance >= minimum) continue;
        const push = (minimum - distance) * 0.1;
        dx /= distance;
        dy /= distance;
        point.x -= dx * push;
        point.y -= dy * push;
        other.x += dx * push;
        other.y += dy * push;
      }
      point.x += (point.targetX - point.x) * 0.08;
      point.y += (point.targetY - point.y) * 0.08;
      point.x = Math.max(100, Math.min(WIDTH - 100, point.x));
      point.y = Math.max(104, Math.min(HEIGHT - 112, point.y));
    });
  }
  points.forEach((point) => result.set(point.node.id, { x: point.x, y: point.y }));
  return result;
});

const particles = computed(() => Array.from({ length: 74 }, (_, index) => ({
  x: 24 + ((index * 197) % 1390),
  y: 22 + ((index * 113) % 650),
  r: index % 11 === 0 ? 2.1 : index % 5 === 0 ? 1.5 : 1.05,
  kind: index % 17 === 0 ? "teal" : index % 19 === 0 ? "violet" : index % 13 === 0 ? "blue" : "",
  delay: `${(index % 9) * -1.3}s`,
})));

function nodePosition(node: AssetMapNode) { return positions.value.get(node.id) ?? { x: WIDTH / 2, y: HEIGHT / 2 }; }
function isActiveEdge(edge: AssetMapEdge) { return Boolean(focusId.value) && activeEdges.value.has(edge.id); }
function beginPan(event: PointerEvent) {
  if ((event.target as Element | null)?.closest?.(".particle-node")) return;
  dragging.value = true;
  moved.value = false;
  pointer.value = { x: event.clientX, y: event.clientY };
  (event.currentTarget as SVGElement).setPointerCapture?.(event.pointerId);
}
function movePan(event: PointerEvent) {
  if (!dragging.value) return;
  const dx = event.clientX - pointer.value.x;
  const dy = event.clientY - pointer.value.y;
  if (Math.abs(dx) + Math.abs(dy) > 2) moved.value = true;
  const speed = 1.8;
  pan.value = { x: pan.value.x + dx * speed, y: pan.value.y + dy * speed };
  pointer.value = { x: event.clientX, y: event.clientY };
}
function endPan(event: PointerEvent) {
  dragging.value = false;
  (event.currentTarget as SVGElement).releasePointerCapture?.(event.pointerId);
}
function zoomCanvas(event: WheelEvent) {
  event.preventDefault();
  zoom.value = Math.max(0.68, Math.min(1.75, zoom.value * (event.deltaY > 0 ? 0.92 : 1.08)));
}
function clickCanvas() { if (!moved.value) emit("clear"); }
function selectNode(node: AssetMapNode) { emit("select", node); }
function resetView() { pan.value = { x: 0, y: 0 }; zoom.value = 1; }
</script>

<template>
  <div class="particle-canvas-shell">
    <svg class="particle-canvas" :viewBox="`0 0 ${WIDTH} ${HEIGHT}`" role="img" aria-label="深空粒子资产关系图" @pointerdown="beginPan" @pointermove="movePan" @pointerup="endPan" @pointercancel="endPan" @wheel="zoomCanvas" @click="clickCanvas">
      <defs>
        <pattern id="particle-dot-grid" width="128" height="100" patternUnits="userSpaceOnUse"><circle cx="10" cy="10" r="1.35" fill="rgba(224,232,255,.1)" /></pattern>
        <filter id="particle-line-glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2.4" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
        <filter id="particle-core-glow" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="7" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
        <filter id="particle-soft-glow" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="3.2" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
      </defs>
      <rect class="particle-grid" width="100%" height="100%" />
      <g :transform="`translate(${pan.x} ${pan.y}) scale(${zoom})`">
        <g class="particle-dots" aria-hidden="true"><circle v-for="(particle, index) in particles" :key="index" :class="['particle-dot', particle.kind]" :cx="particle.x" :cy="particle.y" :r="particle.r" :style="{ animationDelay: particle.delay }" /></g>
        <g class="particle-edges" aria-hidden="true"><line v-for="edge in props.data.edges" :key="edge.id" :class="{ active: isActiveEdge(edge), muted: Boolean(focusId) && !isActiveEdge(edge) }" :x1="nodePosition(props.data.nodes.find((node) => node.id === edge.source) ?? props.data.nodes[0]).x" :y1="nodePosition(props.data.nodes.find((node) => node.id === edge.source) ?? props.data.nodes[0]).y" :x2="nodePosition(props.data.nodes.find((node) => node.id === edge.target) ?? props.data.nodes[0]).x" :y2="nodePosition(props.data.nodes.find((node) => node.id === edge.target) ?? props.data.nodes[0]).y" /></g>
        <g class="particle-nodes">
          <g v-for="node in props.data.nodes" :key="node.id" class="particle-node" :class="{ selected: node.id === focusId }" :transform="`translate(${nodePosition(node).x} ${nodePosition(node).y})`" tabindex="0" role="button" :aria-label="`选择 ${node.label}`" @click.stop="selectNode(node)" @keydown.enter.stop="selectNode(node)" @keydown.space.prevent.stop="selectNode(node)">
            <circle class="particle-halo particle-halo-outer" r="80" :stroke="colorFor(node.kind).stroke" />
            <circle class="particle-halo particle-halo-inner" r="58" :stroke="colorFor(node.kind).stroke" />
            <circle class="particle-ring" r="32" :stroke="colorFor(node.kind).stroke" />
            <circle class="particle-core" r="15" :fill="colorFor(node.kind).stroke" />
            <text class="particle-label" :y="node.id === focusId ? 94 : 56" :fill="colorFor(node.kind).label">{{ shortLabel(node.label) }}</text>
          </g>
        </g>
      </g>
    </svg>
    <button class="particle-reset-view" type="button" aria-label="重置视图" @click.stop="resetView">重置视图</button>
  </div>
</template>

<style scoped>
.particle-canvas-shell { position: relative; width: 100%; height: 700px; overflow: hidden; }
.particle-canvas { display: block; width: 100%; height: 100%; touch-action: none; user-select: none; cursor: grab; }
.particle-canvas:active { cursor: grabbing; }
.particle-grid { fill: url(#particle-dot-grid); }
.particle-dot { fill: rgba(224, 232, 255, .18); animation: particle-drift 13s ease-in-out infinite alternate; transform-box: fill-box; transform-origin: center; }
.particle-dot.blue { fill: rgba(100, 200, 255, .48); }
.particle-dot.teal { fill: rgba(100, 255, 200, .4); }
.particle-dot.violet { fill: rgba(167, 139, 250, .4); }
.particle-edges line { stroke: rgba(100, 200, 255, .14); stroke-width: 1.35; vector-effect: non-scaling-stroke; transition: stroke .2s ease, stroke-width .2s ease, opacity .2s ease; }
.particle-edges line.active { stroke: #3b82f6; stroke-width: 2.7; opacity: .92; filter: url(#particle-line-glow); }
.particle-edges line.muted { opacity: .16; }
.particle-node { cursor: pointer; outline: none; transition: opacity .22s ease; }
.particle-node:focus, .particle-node:focus-visible { outline: none; }
.particle-ring { fill: none; stroke-width: 1.2; stroke-opacity: .2; vector-effect: non-scaling-stroke; transition: stroke-opacity .22s ease, stroke-width .22s ease; }
.particle-halo { fill: none; opacity: 0; vector-effect: non-scaling-stroke; transition: opacity .22s ease, stroke-opacity .22s ease; }
.particle-halo-inner { stroke-width: 1.35; stroke-opacity: .74; }
.particle-halo-outer { stroke-width: 1.1; stroke-opacity: .5; }
.particle-core { stroke: none; transition: r .22s ease, filter .22s ease; }
.particle-label { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 14px; font-weight: 500; text-anchor: middle; opacity: .52; transition: opacity .22s ease, font-size .22s ease; }
.particle-node:hover .particle-ring { stroke-opacity: .72; stroke-width: 2; }
.particle-node:hover .particle-label { opacity: .78; }
.particle-node.selected .particle-ring { stroke-opacity: 0; }
.particle-node.selected .particle-halo { opacity: 1; filter: url(#particle-soft-glow); }
.particle-node.selected .particle-core { r: 30; filter: url(#particle-core-glow); animation: particle-pulse 2.4s ease-in-out infinite; }
.particle-node.selected .particle-label { fill: #64c8ff !important; font-size: 15px; opacity: 1; }
.particle-reset-view { position: absolute; top: 18px; right: 18px; padding: 6px 9px; border: 1px solid rgba(255, 255, 255, .08); border-radius: 7px; color: #8da7c4; background: rgba(10, 14, 26, .72); cursor: pointer; font-size: 10px; }
.particle-reset-view:hover { color: #64c8ff; border-color: rgba(100, 200, 255, .28); }
@keyframes particle-drift { from { transform: translate(0, 0); opacity: .35; } to { transform: translate(7px, -5px); opacity: .85; } }
@keyframes particle-pulse { 0%, 100% { opacity: .86; } 50% { opacity: 1; } }
@media (max-width: 760px) { .particle-canvas-shell { height: 570px; } .particle-label { font-size: 12px; } }
@media (prefers-reduced-motion: reduce) { .particle-dot, .particle-core { animation: none !important; } }
</style>
