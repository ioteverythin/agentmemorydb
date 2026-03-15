import { useEffect, useRef } from 'react';
import * as d3 from 'd3';
import type { GraphNode } from '../lib/types';
import { colorForType } from '../lib/utils';

/* ── Types for the D3 simulation ─────────────────────────── */
interface SimNode extends d3.SimulationNodeDatum {
  id: string;
  key: string;
  content: string;
  depth: number;
  type: string;
  linkType: string;
}

interface SimLink extends d3.SimulationLinkDatum<SimNode> {
  type: string;
}

interface GraphLink {
  source: string;
  target: string;
  type: string;
}

interface GraphVisualizationProps {
  nodes: GraphNode[];
  links: GraphLink[];
  seedId: string;
  onNodeClick?: (nodeId: string) => void;
}

/* ── Legend items ─────────────────────────────────────────── */
const LEGEND = [
  { color: '#58a6ff', label: 'Seed / Semantic' },
  { color: '#bc8cff', label: 'Episodic' },
  { color: '#3fb950', label: 'Procedural' },
  { color: '#d29922', label: 'Working' },
  { color: '#484f58', label: 'Other' },
];

export default function GraphVisualization({
  nodes,
  links,
  seedId,
  onNodeClick,
}: GraphVisualizationProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const simRef = useRef<d3.Simulation<SimNode, SimLink> | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    // Clean up previous render
    container.innerHTML = '';
    simRef.current?.stop();

    const rect = container.getBoundingClientRect();
    const W = rect.width || 800;
    const H = rect.height || 600;

    // Map domain data → simulation data
    const simNodes: SimNode[] = nodes.map((n) => ({
      id: n.memory_id,
      key: n.memory_key,
      content: n.content,
      depth: n.depth,
      type: n.memory_type || 'unknown',
      linkType: n.link_type,
    }));

    const simLinks: SimLink[] = links.map((l) => ({
      source: l.source,
      target: l.target,
      type: l.type,
    }));

    // Create SVG
    const svg = d3
      .select(container)
      .append('svg')
      .attr('width', W)
      .attr('height', H);

    const g = svg.append('g');

    // Zoom / pan
    const zoom = d3
      .zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.15, 5])
      .on('zoom', (e) => g.attr('transform', e.transform));
    (svg as any).call(zoom);

    // Force simulation
    const sim = d3
      .forceSimulation<SimNode>(simNodes)
      .force(
        'link',
        d3.forceLink<SimNode, SimLink>(simLinks).id((d) => d.id).distance(120),
      )
      .force('charge', d3.forceManyBody().strength(-350))
      .force('center', d3.forceCenter(W / 2, H / 2))
      .force('collision', d3.forceCollide().radius(35));

    simRef.current = sim;

    // Draw links
    const linkEl = g
      .append('g')
      .selectAll('line')
      .data(simLinks)
      .enter()
      .append('line')
      .attr('stroke', '#30363d')
      .attr('stroke-opacity', 0.6)
      .attr('stroke-width', 1.5);

    // Link labels
    const linkLabel = g
      .append('g')
      .selectAll('text')
      .data(simLinks)
      .enter()
      .append('text')
      .text((d) => d.type || '')
      .attr('font-size', 8)
      .attr('fill', '#484f58')
      .attr('text-anchor', 'middle')
      .attr('dy', -4);

    // Drag handlers
    const drag = d3
      .drag<SVGGElement, SimNode>()
      .on('start', (e, d) => {
        if (!e.active) sim.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
      })
      .on('drag', (e, d) => {
        d.fx = e.x;
        d.fy = e.y;
      })
      .on('end', (e, d) => {
        if (!e.active) sim.alphaTarget(0);
        d.fx = null;
        d.fy = null;
      });

    // Draw node groups
    const nodeGroup = g
      .append('g')
      .selectAll<SVGGElement, SimNode>('g')
      .data(simNodes)
      .enter()
      .append('g')
      .style('cursor', 'pointer');

    (nodeGroup as any).call(drag);

    // Circles
    nodeGroup
      .append('circle')
      .attr('r', (d) => (d.id === seedId ? 16 : 11))
      .attr('fill', (d) => (d.id === seedId ? '#58a6ff' : colorForType(d.type)))
      .attr('stroke', (d) => (d.id === seedId ? '#58a6ff' : '#30363d'))
      .attr('stroke-width', (d) => (d.id === seedId ? 3 : 1.5));

    // Labels beneath nodes
    nodeGroup
      .append('text')
      .attr('dy', (d) => (d.id === seedId ? 28 : 22))
      .attr('text-anchor', 'middle')
      .attr('font-size', 10)
      .attr('fill', '#8b949e')
      .attr('pointer-events', 'none')
      .text((d) => (d.key?.length > 18 ? d.key.slice(0, 16) + '…' : d.key));

    // Tooltip events
    const tooltip = tooltipRef.current;
    nodeGroup
      .on('mouseover', function (event: MouseEvent, d: SimNode) {
        if (!tooltip || !container) return;
        const cr = container.getBoundingClientRect();
        tooltip.style.display = 'block';
        tooltip.style.left = event.clientX - cr.left + 16 + 'px';
        tooltip.style.top = event.clientY - cr.top - 12 + 'px';
        tooltip.innerHTML = `
          <div style="font-weight:600;margin-bottom:4px">${d.key}</div>
          <div style="font-size:11px;color:#8b949e;margin-bottom:4px">${(d.content || '').slice(0, 150)}</div>
          <div style="font-size:10px;color:#484f58">
            Type: ${d.type} · Depth: ${d.depth}${d.linkType ? ' · Via: ' + d.linkType : ''}
          </div>
          <div style="font-size:9px;color:#484f58;font-family:monospace;margin-top:4px">${d.id}</div>`;
      })
      .on('mousemove', function (event: MouseEvent) {
        if (!tooltip || !container) return;
        const cr = container.getBoundingClientRect();
        tooltip.style.left = event.clientX - cr.left + 16 + 'px';
        tooltip.style.top = event.clientY - cr.top - 12 + 'px';
      })
      .on('mouseout', () => {
        if (tooltip) tooltip.style.display = 'none';
      })
      .on('click', (_event: MouseEvent, d: SimNode) => {
        onNodeClick?.(d.id);
      });

    // Tick
    sim.on('tick', () => {
      linkEl
        .attr('x1', (d: any) => d.source.x)
        .attr('y1', (d: any) => d.source.y)
        .attr('x2', (d: any) => d.target.x)
        .attr('y2', (d: any) => d.target.y);

      linkLabel
        .attr('x', (d: any) => (d.source.x + d.target.x) / 2)
        .attr('y', (d: any) => (d.source.y + d.target.y) / 2);

      nodeGroup.attr('transform', (d) => `translate(${d.x},${d.y})`);
    });

    return () => {
      sim.stop();
    };
  }, [nodes, links, seedId, onNodeClick]);

  return (
    <div className="relative w-full h-full">
      <div ref={containerRef} className="w-full h-full bg-gh-bg" />

      {/* Tooltip (hidden by default) */}
      <div
        ref={tooltipRef}
        className="absolute bg-gh-canvas border border-gh-border rounded-lg p-3 pointer-events-none z-20 max-w-[280px] shadow-lg"
        style={{ display: 'none' }}
      />

      {/* Legend */}
      <div className="absolute bottom-3 left-3 bg-gh-canvas border border-gh-border rounded-lg p-3 text-xs z-10">
        <div className="font-semibold text-[10px] uppercase tracking-wider text-gh-dim mb-2">
          Legend
        </div>
        {LEGEND.map(({ color, label }) => (
          <div key={label} className="flex items-center gap-2 my-1">
            <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: color }} />
            <span className="text-gh-muted">{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
