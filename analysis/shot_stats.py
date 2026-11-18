"""Shot-length stats from a list of cut times (seconds).

Usage: python3 -I shot_stats.py DURATION CUT1 CUT2 ...
"""
import statistics
import sys

duration = float(sys.argv[1])
cuts = sorted(float(c) for c in sys.argv[2:])
edges = [0.0] + cuts + [duration]
shots = [round(b - a, 2) for a, b in zip(edges, edges[1:])]

print(f"duration_s      {duration:.2f}")
print(f"cuts            {len(cuts)}")
print(f"cuts_per_min    {len(cuts) / duration * 60:.1f}")
print(f"shots           {len(shots)}")
print(f"median_shot_s   {statistics.median(shots):.2f}")
print(f"mean_shot_s     {statistics.mean(shots):.2f}")
print(f"cv_shot         {statistics.pstdev(shots) / statistics.mean(shots):.2f}")
print(f"first_cut_s     {cuts[0] if cuts else None}")
print(f"longest_shot    {max(shots):.2f}s at {edges[shots.index(max(shots))]:.2f}s")
print(f"shots_under_1s  {sum(s < 1.0 for s in shots)}")
print("shot_list       " + " ".join(f"{s:.2f}" for s in shots))
