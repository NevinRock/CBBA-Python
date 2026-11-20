"""Quick probes: push one factor until CBBA / ED-CBBA re-auction breaks."""
import math, random, statistics as st, sys, time
from multiprocessing import Pool
ROOT = "/Users/harmish/Documents/UCL/multi_agent"
sys.path[:0] = [ROOT + "/test", ROOT + "/lib", ROOT]
import run_exp3_shared as R

cfg = R.load_config()


def components(points, rng_m):
    g = R.adjacency(points, rng_m); n = len(points); seen, comps = set(), 0
    for s in range(n):
        if s in seen: continue
        comps += 1; stack = [s]; seen.add(s)
        while stack:
            u = stack.pop()
            for v in range(n):
                if g[u][v] and v not in seen: seen.add(v); stack.append(v)
    return comps


def cap_bound(agents, tasks, dead):
    a = sum(1 for x in agents if x.agent_id not in dead and x.agent_type == 0)
    g = sum(1 for x in agents if x.agent_id not in dead and x.agent_type == 1)
    A = sum(t.task_type == 0 for t in tasks); G = sum(t.task_type == 1 for t in tasks); S = sum(t.task_type == 2 for t in tasks)
    ea, eg = min(A, 4 * a), min(G, 4 * g)
    return ea + eg + min(S, 4 * a - ea + 4 * g - eg)


def one(args):
    probe, size, seed, method, knob = args
    exp = cfg["EXPERIMENT"]
    old = exp["TASKS_PER_TYPE_PER_ROBOT"]
    if probe == "load":
        exp["TASKS_PER_TYPE_PER_ROBOT"] = knob
    agents, tasks, world = R.build_mission(cfg, size, seed)
    exp["TASKS_PER_TYPE_PER_ROBOT"] = old
    ids = [a.agent_id for a in agents]
    p, t, _ = R.auction(cfg, agents, tasks, world, ids, {x.task_id for x in tasks}, True)
    owner = {x: a for a, pp in p.items() for x in pp}
    rng = random.Random(f"{probe}-{size}-{seed}")
    working = sorted(set(owner.values()))
    n_fail = 1
    if probe == "failfrac":
        n_fail = max(1, round(knob * size))
    dead = set(rng.sample(working, min(n_fail, len(working))))
    surv = [a for a in agents if a.agent_id not in dead]
    sid = [a.agent_id for a in surv]
    live_owner = {x: a for x, a in owner.items() if a not in dead}
    opts, comm = {}, None
    if probe == "loss":
        opts = dict(packet_loss_probability=knob, communication_seed=seed)
    if probe == "range":
        comm = knob
    cpu0 = time.process_time()
    pp, tt, s = R.auction(cfg, surv, tasks, world, sid, {x.task_id for x in tasks},
                          event_triggered=(method == "ed"), owner=live_owner, comm_range=comm, **opts)
    recs, dup = R.evaluate(cfg, surv, tasks, pp, tt)
    bound = cap_bound(agents, tasks, dead)
    return dict(probe=probe, size=size, method=method, knob=knob, consensus=s["consensus_ok"],
                dup=dup, assigned=len(recs), n_tasks=len(tasks), avoidable=max(0, bound - len(recs)),
                rounds=s["rounds"], conv=s["rounds_to_converge"], bc=s["broadcasts_to_converge"],
                cpu=time.process_time() - cpu0,
                comps=components([(a.x, a.y) for a in surv], comm) if comm else 1)


if __name__ == "__main__":
    jobs = []
    for size in (12, 24):
        for k in (0.0, 0.1, 0.3, 0.5):
            for m in ("cbba", "ed"):
                jobs += [("loss", size, s, m, k) for s in range(10)]
        for k in (15, 20, 25, 30, 40):
            jobs += [("range", size, s, "ed", k) for s in range(10)]
        for k in (1, 2, 3):
            jobs += [("load", size, s, "ed", k) for s in range(10)]
    for k in (0.1, 0.25, 0.5):
        jobs += [("failfrac", 24, s, "ed", k) for s in range(10)]
    for size in (48, 96):
        for m in ("cbba", "ed"):
            jobs += [("scale", size, s, m, size) for s in range(3)]
    with Pool(int(sys.argv[1]) if len(sys.argv) > 1 else 6) as pool:
        out = pool.map(one, jobs)
    groups = {}
    for r in out:
        groups.setdefault((r["probe"], r["size"], r["method"], r["knob"]), []).append(r)
    print(f"{'probe':9}{'N':>4} {'meth':5}{'knob':>6} | consensus  dup-runs  assigned/tasks  avoidable  rounds(conv)  bcast  cpu_s  comps")
    for k in sorted(groups, key=lambda k: (k[0], k[1], k[2], k[3])):
        g = groups[k]; n = len(g)
        print(f"{k[0]:9}{k[1]:>4} {k[2]:5}{k[3]:>6} | {sum(r['consensus'] for r in g)}/{n:<8} {sum(r['dup']>0 for r in g)}/{n:<7} "
              f"{st.fmean(r['assigned'] for r in g):6.1f}/{g[0]['n_tasks']:<6} {st.fmean(r['avoidable'] for r in g):6.2f}   "
              f"{st.fmean(r['rounds'] for r in g):6.1f}({st.fmean(r['conv'] for r in g):5.1f})  {st.fmean(r['bc'] for r in g):6.0f}  "
              f"{st.fmean(r['cpu'] for r in g):6.2f}  {st.fmean(r['comps'] for r in g):4.1f}")
