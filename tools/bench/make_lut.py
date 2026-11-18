"""Write a 33^3 'warm' .cube LUT for benchmarking lut3d."""
import sys

N = 33
out = sys.argv[1]
with open(out, "w") as f:
    f.write('TITLE "warm"\nLUT_3D_SIZE %d\n' % N)
    for b in range(N):
        for g in range(N):
            for r in range(N):
                R, G, B = r / (N - 1), g / (N - 1), b / (N - 1)
                R = min(1.0, R * 1.06 + 0.01)
                B = max(0.0, B * 0.94)
                G = G ** 0.97
                f.write("%.6f %.6f %.6f\n" % (R, G, B))
