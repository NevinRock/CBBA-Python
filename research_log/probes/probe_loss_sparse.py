"""Packet loss on a sparse but connected graph (R = factor x connectivity threshold)."""
import random, statistics as st, sys
from multiprocessing import Pool
ROOT = "/Users/harmish/Documents/UCL/multi_agent"
sys.path[:0] = [ROOT + "/test", ROOT + "/lib", ROOT]
import run_exp3_shared as R
cfg = R.load_config()

def one(args):
    size, seed, method, loss, factor = args
    agents, tasks, world = R.build_mission(cfg, size, seed)
    ids = [a.agent_id for a in agents]
    p, t, _ = R.auction(cfg, agents, tasks, world, ids, {x.task_id for x in tasks}, True)
    owner = {x: a for a, pp in p.items() for x in pp}
    dead = {random.Random(f"loss-{size}-{seed}").choice(sorted(set(owner.values())))}
    surv = [a for a in agents if a.agent_id not in dead]
    comm = factor * R.connect_threshold([(a.x, a.y) for a in surv])
    opts = dict(packet_loss_probability=loss, communication_seed=seed)
    if method == "ed_refresh":
        opts["refresh_interval"] = 5
    pp, tt, s = R.auction(cfg, surv, tasks, world, [a.agent_id for a in surv], {x.task_id for x in tasks},
                          event_triggered=(method != "cbba"), owner={x: a for x, a in owner.items() if a not in dead},
                          comm_range=comm, **opts)
    recs, dup = R.evaluate(cfg, surv, tasks, pp, tt)
    diam = R.graph_stats(R.adjacency([(a.x, a.y) for a in surv], comm))[1]
    return dict(key=(size, factor, loss, method), ok=s["consensus_ok"], dup=dup, lost=len(tasks) - len(recs),
                bc=s["broadcasts"], conv=s["rounds_to_converge"], diam=diam)

if __name__ == "__main__":
    jobs = [(size, seed, m, loss, f) for size in (12, 24) for f in (1.0, 1.2) for loss in (0.1, 0.3, 0.5)
            for m in ("cbba", "ed", "ed_refresh") for seed in range(20)]
    with Pool(8) as pool:
        out = pool.map(one, jobs)
    g = {}
    for r in out: g.setdefault(r["key"], []).append(r)
    print(f"{'N':>3} {'R/thr':>5} {'loss':>5} {'method':11}| agree  dup-runs  lost  bcast(all)  conv-rounds  diam")
    for k in sorted(g):
        v = g[k]; n = len(v)
        print(f"{k[0]:>3} {k[1]:>5} {k[2]:>5} {k[3]:11}| {sum(x['ok'] for x in v):>2}/{n}  {sum(x['dup']>0 for x in v):>2}/{n}   "
              f"{st.fmean(x['lost'] for x in v):4.2f}  {st.fmean(x['bc'] for x in v):8.0f}  {st.fmean(x['conv'] for x in v):8.1f}  {st.fmean(x['diam'] for x in v):4.1f}")
