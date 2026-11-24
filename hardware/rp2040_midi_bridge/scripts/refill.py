import sys
import pcbnew
p = sys.argv[1]
b = pcbnew.LoadBoard(p)
b.BuildConnectivity()
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
pcbnew.SaveBoard(p, b)
print("refilled", p)
