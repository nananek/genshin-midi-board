import sys, math, re
sys.path.insert(0, "/work/hardware/rp2040_midi_bridge/scripts")
import pcbnew
import pcb_router as R

TIGHT = ("+3V3", "VBUS_USB_A", "VBUS_PC", "VBUS_IPAD", "SW6_RESET",
         "SWCLK", "SWDIO", "SW3_SUSTAIN", "STATUS_LED", "TPS_FAULT",
         "MIDI_UART_TX", "MIDI_UART_RX")

b = pcbnew.LoadBoard("/work/hardware/rp2040_midi_bridge/rp2040_midi_bridge.kicad_pcb")
router = R.Router(62.0, 35.0, cell=0.05)
router.set_outline([(2,0),(60,0),(62,2),(62,33),(60,35),(2,35),(0,33),(0,2)])
pads = {}
gnd_pads = []
for fp in b.GetFootprints():
    for pad in fp.Pads():
        bb = pad.GetBoundingBox()
        name = pad.GetNetname() or "NC"
        layers = ["F"] + (["B"] if pad.GetLayerSet().Contains(pcbnew.B_Cu) else [])
        clr = 0.1
        if pad.GetDrillSize().x > 0:
            clr = max(clr, 0.35)
        router.add_pad(name, pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                       pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()), layers, clr)
        if pad.GetNumber() and pad.GetNetname():
            e = (pcbnew.ToMM(bb.GetCenter().x), pcbnew.ToMM(bb.GetCenter().y),
                 "FB" if len(layers) > 1 else "F")
            pads.setdefault(name, []).append(e)
            if name == "GND" and len(layers) == 1:
                gnd_pads.append((fp.GetReference(), pad.GetNumber(), e))
vias = []
for t in b.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA):
        p = t.GetPosition()
        pos = (pcbnew.ToMM(p.x), pcbnew.ToMM(p.y))
        router.commit_via(t.GetNetname(), pos)
        if t.GetNetname() == "GND":
            vias.append(pos)
    else:
        a, c = t.GetStart(), t.GetEnd()
        router.commit_track(t.GetNetname(), "F" if t.GetLayer() == pcbnew.F_Cu else "B",
                            (pcbnew.ToMM(a.x), pcbnew.ToMM(a.y)),
                            (pcbnew.ToMM(c.x), pcbnew.ToMM(c.y)), pcbnew.ToMM(t.GetWidth()))

def emit(net, before):
    ni = b.FindNet(net)
    for item in router.net_geom.get(net, [])[before:]:
        if item[0] == "trk":
            _, layer, p0, p1, width, extra = item
            t = pcbnew.PCB_TRACK(b)
            t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(p0[0]), pcbnew.FromMM(p0[1])))
            t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(p1[0]), pcbnew.FromMM(p1[1])))
            t.SetLayer(pcbnew.F_Cu if layer == "F" else pcbnew.B_Cu)
            t.SetWidth(pcbnew.FromMM(width)); t.SetNet(ni); b.Add(t)
        else:
            _, p, drill, radius = item
            v = pcbnew.PCB_VIA(b)
            v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(p[0]), pcbnew.FromMM(p[1])))
            v.SetWidth(pcbnew.FromMM(2*radius)); v.SetDrill(pcbnew.FromMM(drill))
            v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetNet(ni); b.Add(v)

# --- GND: strap each isolated pad to the nearest ground via (0.2 mm track)
iso = []
for blk in open("/work/hardware/rp2040_midi_bridge/drc.rpt").read().split("[unconnected_items]")[1:]:
    for m in re.finditer(r"Pad (\S+) \[GND\] of (\S+)", blk):
        iso.append((m.group(2), m.group(1)))
iso = list(dict.fromkeys(iso))
print("isolated GND pads:", iso)
before = len(router.net_geom.get("GND", []))
for ref, pin in iso:
    cand = [p for p in gnd_pads if p[0] == ref and p[1] == pin]
    if not cand:
        continue
    src = cand[0][2]
    near = sorted(vias, key=lambda v: math.hypot(v[0]-src[0], v[1]-src[1]))[:6]
    for v in near:
        if router.connect("GND", src, (v[0], v[1], "FB"), 0.2, 0.1, 8, 200000, 0.225):
            break
print("GND items:", len(router.net_geom.get("GND", [])) - before)
emit("GND", before)

# --- the tight nets: nearest-pair chain at 0.1 mm clearance
for net in TIGHT:
    pts = pads.get(net, [])
    if len(pts) < 2:
        continue
    before = len(router.net_geom.get(net, []))
    connected = [0]
    todo = list(range(1, len(pts)))
    for w in (0.15, 0.127, 0.2):
        remaining = []
        for i in todo:
            best = min(connected, key=lambda j: math.hypot(
                pts[i][0] - pts[j][0], pts[i][1] - pts[j][1]))
            if router.connect(net, pts[i], pts[best], w, 0.1, 8, 400000, 0.225):
                connected.append(i)
            else:
                remaining.append(i)
        todo = remaining
        if not todo:
            break
    n = len(router.net_geom.get(net, [])) - before
    print(f"{net:14s} {len(connected)}/{len(pts)} {n} items")
    emit(net, before)
b.BuildConnectivity()
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
pcbnew.SaveBoard("/work/hardware/rp2040_midi_bridge/rp2040_midi_bridge.kicad_pcb", b)
print("saved")
