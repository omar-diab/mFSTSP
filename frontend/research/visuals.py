"""Plotly route playback from recorded assignments, with explicit interpolation limits."""
import math
import json

import numpy as np
import plotly.graph_objects as go

PALETTE = ["#39c9ff", "#ffbb66", "#a78bfa", "#49e2bb", "#fa78b0"]


def position(segments, vehicle, time, depot=0):
    timeline = sorted((s for s in segments if s["vehicle"] == vehicle), key=lambda x: x["start"])
    previous = depot
    for s in timeline:
        if time < s["start"]:
            return previous, previous, 0, "Waiting / on board (position between recorded segments not available)"
        if s["start"] <= time <= s["end"]:
            fraction = (time-s["start"]) / max(s["end"]-s["start"], 1e-9)
            return s["a"], s["b"], fraction, s["status"]
        previous = s["b"]
    return previous, previous, 0, "Recorded activities complete"


def projected_coordinates(coords):
    lon0, lat0 = coords[0]
    return {node: ((lon-lon0)*111320*math.cos(math.radians(lat0)), (lat-lat0)*111320, 0) for node, (lon, lat) in coords.items()}


def route_distance(solution, coords):
    """Straight-line geometry only; not road-network distance."""
    xy = projected_coordinates(coords)
    xy.setdefault(max(coords)+1, xy[0])
    totals = {}
    for s in solution["segments"]:
        if s["a"] in xy and s["b"] in xy:
            a, b = xy[s["a"]], xy[s["b"]]
            totals[s["vehicle"]] = totals.get(s["vehicle"], 0) + math.hypot(a[0]-b[0], a[1]-b[1])
    return totals


def route_figure(solution, coords, animated=False, speed=1, selected_vehicle=None):
    xy = projected_coordinates(coords)
    # Reference formulations use c+1 as a separate return-depot ID.
    xy.setdefault(max(coords)+1, xy[0])
    vehicles = sorted({s["vehicle"] for s in solution["segments"]})
    colors = {v: PALETTE[i % len(PALETTE)] for i, v in enumerate(vehicles)}
    fig = go.Figure()
    nodes = sorted(coords)
    fig.add_trace(go.Scatter3d(x=[xy[n][0] for n in nodes], y=[xy[n][1] for n in nodes], z=[0]*len(nodes), mode="markers+text", text=["Depot" if n == 0 else str(n) for n in nodes], textposition="top center", name="Customers", marker=dict(size=[9 if n == 0 else 4 for n in nodes], color=["#ffffff" if n == 0 else "#697e9b" for n in nodes]), hovertemplate="Node %{text}<br>East %{x:.1f} m<br>North %{y:.1f} m<extra></extra>"))
    extent = max([math.hypot(p[0], p[1]) for p in xy.values()] + [1])
    height = max(30, extent * .08)
    for vehicle in vehicles:
        xs, ys, zs = [], [], []
        for s in solution["segments"]:
            if s["vehicle"] != vehicle or s["a"] == s["b"] or s["a"] not in xy or s["b"] not in xy:
                continue
            a, b = xy[s["a"]], xy[s["b"]]
            for fraction in np.linspace(0, 1, 7):
                xs.append(a[0]+fraction*(b[0]-a[0]))
                ys.append(a[1]+fraction*(b[1]-a[1]))
                zs.append(height*math.sin(math.pi*fraction) if vehicle.startswith("UAV") else 0)
            xs.append(None); ys.append(None); zs.append(None)
        fig.add_trace(go.Scatter3d(x=xs, y=ys, z=zs, mode="lines", name=vehicle, line=dict(color=colors[vehicle], width=6 if vehicle == selected_vehicle else 3, dash="dash" if vehicle.startswith("UAV") else "solid"), opacity=1 if selected_vehicle in (None, vehicle) else .35))
    if animated and vehicles:
        moving_indices = []
        for v in vehicles:
            moving_indices.append(len(fig.data))
            fig.add_trace(go.Scatter3d(x=[xy[0][0]], y=[xy[0][1]], z=[0], mode="markers", name=v+" position", marker=dict(size=8, color=colors[v], symbol="diamond")))
        delivered_index = len(fig.data)
        fig.add_trace(go.Scatter3d(x=[], y=[], z=[], mode="markers", name="Delivered (timing caveats apply)", marker=dict(size=6, color="#49e2bb")))
        frames = []
        for t in np.linspace(0, solution["duration"], 65):
            traces = []
            for v in vehicles:
                a, b, f, status = position(solution["segments"], v, t)
                p, q = xy.get(a, xy[0]), xy.get(b, xy[0])
                z = height*math.sin(math.pi*f) if v.startswith("UAV") and a != b else 0
                traces.append(go.Scatter3d(x=[p[0]+f*(q[0]-p[0])], y=[p[1]+f*(q[1]-p[1])], z=[z], text=[f"{v} | {status} | t={t:.1f}s"], hovertemplate="%{text}<extra></extra>"))
            delivered = {n for n, end in solution["deliveries"] if end <= t and n in xy and n != 0}
            traces.append(go.Scatter3d(x=[xy[n][0] for n in delivered], y=[xy[n][1] for n in delivered], z=[0]*len(delivered)))
            frames.append(go.Frame(name=f"{t:.1f}", data=traces, traces=moving_indices+[delivered_index]))
        fig.frames = frames
        duration = int(140 / speed)
        fig.update_layout(updatemenus=[dict(type="buttons", direction="left", x=0, y=0, yanchor="top", pad=dict(t=25), buttons=[dict(label="▶ Play", method="animate", args=[None, {"frame": {"duration": duration, "redraw": True}, "transition": {"duration": 0}, "fromcurrent": True}]), dict(label="❚❚ Pause", method="animate", args=[[None], {"mode": "immediate", "frame": {"duration": 0, "redraw": False}}]), dict(label="↺ Restart", method="animate", args=[[frames[0].name], {"mode": "immediate", "frame": {"duration": 0, "redraw": True}}])])], sliders=[dict(x=.28, len=.7, y=0, currentvalue={"prefix": "Schedule time (s): "}, steps=[dict(label=f.name, method="animate", args=[[f.name], {"mode": "immediate", "frame": {"duration": 0, "redraw": True}}]) for f in frames])])
    fig.update_layout(template="plotly_dark", paper_bgcolor="#0b1426", plot_bgcolor="#0b1426", height=650, margin=dict(l=0, r=0, t=35, b=95 if animated else 15), legend=dict(orientation="h", y=1.08), scene=dict(bgcolor="#0b1426", xaxis_title="East of depot (m)", yaxis_title="North of depot (m)", zaxis_title="Illustrative height", aspectmode="data", camera=dict(eye=dict(x=1.4, y=-1.6, z=1.0))), uirevision="route-camera")
    return fig


def playback_html(solution, coords, speed=1, selected_vehicle=None):
    """Self-contained Plotly player. Pause stops a timer, never interrupts a Plotly promise."""
    fig = route_figure(solution, coords, animated=True, speed=speed, selected_vehicle=selected_vehicle)
    fig.layout.updatemenus = None
    fig.layout.sliders = None
    fig.update_layout(height=570, margin=dict(l=0, r=0, t=45, b=10))
    for trace in fig.data:
        if trace.name and trace.name.endswith(" position"):
            trace.showlegend = False
    frames = json.dumps([f.to_plotly_json() for f in fig.frames])
    fig.frames = []
    plot = fig.to_html(full_html=False, include_plotlyjs=True, div_id="delivery-scene", config={"responsive": True, "displaylogo": False})
    script = r"""
<script>
const frames=FRAME_DATA;
const scene=document.getElementById('delivery-scene');
const slider=document.getElementById('timeline');
const clock=document.getElementById('clock');
const state=document.getElementById('player-status');
let index=0, playing=false, timer=null, busy=false;
async function showFrame(next) {
  if(busy) return false;
  busy=true;
  index=Math.max(0,Math.min(frames.length-1,next));
  const f=frames[index];
  try {
    await Plotly.restyle(scene, {
      x:f.data.map(t=>t.x), y:f.data.map(t=>t.y), z:f.data.map(t=>t.z),
      text:f.data.map(t=>t.text || []), hovertemplate:f.data.map(t=>t.hovertemplate || '%{text}<extra></extra>')
    }, f.traces);
    slider.value=index; clock.textContent=f.name+' s';
    state.textContent=playing?'Playing recorded schedule':'Paused';
  } catch(error) {state.textContent='Playback error: '+String(error); playing=false;}
  finally {busy=false;}
  return true;
}
async function tick() {
  if(!playing) return;
  if(index>=frames.length-1){playing=false;state.textContent='Playback complete';return;}
  await showFrame(index+1);
  if(playing) timer=setTimeout(tick,FRAME_DELAY);
}
document.getElementById('play').onclick=()=>{
  if(playing)return;
  playing=true;
  if(index>=frames.length-1)index=-1;
  tick();
};
document.getElementById('pause').onclick=()=>{playing=false;clearTimeout(timer);state.textContent='Paused';};
document.getElementById('restart').onclick=async()=>{playing=false;clearTimeout(timer);while(busy)await new Promise(r=>setTimeout(r,10));showFrame(0);};
slider.oninput=async()=>{playing=false;clearTimeout(timer);const requested=Number(slider.value);while(busy)await new Promise(r=>setTimeout(r,10));showFrame(requested);};
document.getElementById('player-status').textContent='Ready · drag to rotate, scroll to zoom';
</script>
""".replace("FRAME_DATA", frames).replace("FRAME_DELAY", str(int(140/speed)))
    return """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>mFSTSP saved delivery playback</title><style>
body{margin:0;background:#0b1426;color:#dce6f6;font:14px system-ui,sans-serif}*{box-sizing:border-box}
.controls{padding:14px 16px;background:#12243b;border:1px solid #24415c;border-radius:12px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
button{background:#173954;color:#bceeff;border:1px solid #397692;border-radius:8px;padding:10px 15px;cursor:pointer;font-weight:600}button:hover{background:#24536d}button:focus-visible,input:focus-visible{outline:2px solid #39c9ff;outline-offset:3px}
input{flex:1;min-width:110px;accent-color:#39c9ff}#clock{min-width:75px;color:#6cddff}#player-status{font-size:12px;color:#92aecb;padding:12px 3px}
</style></head><body>""" + plot + """<div class="controls"><button id="play" aria-label="Play">▶ Play</button><button id="pause" aria-label="Pause">❚❚ Pause</button><button id="restart" aria-label="Restart">↺ Restart</button><label for="timeline">Schedule</label><input id="timeline" type="range" min="0" max="64" value="0" aria-label="Schedule timeline"><output id="clock">0.0 s</output></div><div id="player-status" role="status"></div>""" + script + "</body></html>"
