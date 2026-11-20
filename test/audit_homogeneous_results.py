#!/usr/bin/env python3
"""Independent audit of saved formal results. Never imports or runs CBBA.

Reads CSV, input snapshots and raw solver records; preserves all input files.
"""
import argparse
import copy
import csv
import hashlib
import json
import math
import random
import sys
from collections import Counter
from pathlib import Path

METHODS = ("Standard CBBA", "ED-CBBA", "Distance-Scoped ED-CBBA")
SCALES = {6: 18, 12: 36, 24: 72}
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from test.homogeneous_artifacts import evidence_directory


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


class Audit:
    def __init__(self):
        self.checks = Counter()
        self.errors = []

    def check(self, condition, rule, context=""):
        self.checks[rule] += 1
        if not condition:
            self.errors.append({"rule": rule, "context": str(context)})

    def close(self, a, b, rule, context="", tolerance=1e-7):
        self.check(isinstance(a, (int, float)) and isinstance(b, (int, float))
                   and math.isfinite(a) and math.isfinite(b)
                   and math.isclose(a, b, abs_tol=tolerance, rel_tol=1e-10), rule, context)


def schedule(audit, snapshot, paths, times, task_ids, context, failed=None):
    """Recompute physical feasibility, unique coverage and unbonused value."""
    agents = {a["agent_id"]: a for a in snapshot["agents"]}
    tasks = {t["task_id"]: t for t in snapshot["tasks"]}
    config = snapshot["config"]
    assigned = [t for path in paths.values() for t in path]
    audit.check(len(assigned) == len(set(assigned)), "unique_ownership", context)
    audit.check(set(assigned) <= set(task_ids), "known_scoped_tasks", context)
    audit.check(set(paths) == set(times), "schedule_agent_keys", context)
    if failed is not None:
        audit.check(not paths.get(str(failed)), "failed_agent_excluded", context)
    score = 0.0
    for a_str, path in paths.items():
        agent_id = int(a_str)
        audit.check(agent_id in agents, "known_agent", context)
        if agent_id not in agents:
            continue
        agent = agents[agent_id]
        starts = times.get(a_str, [])
        audit.check(len(path) <= 4, "capacity_four", context)
        audit.check(len(path) == len(starts), "schedule_lengths", context)
        previous_end = agent["availability"]
        position = tuple(agent[k] for k in ("x", "y", "z"))
        for t_id, start in zip(path, starts):
            if t_id not in tasks:
                continue
            task = tasks[t_id]
            compatible = config["TASK_TYPES"][task["task_type"]] in config["COMPATIBILITY"][
                config["AGENT_TYPES"][agent["agent_type"]]]
            audit.check(compatible, "type_compatibility", context)
            audit.check(math.isfinite(start), "finite_start_time", context)
            target = tuple(task[k] for k in ("x", "y", "z"))
            arrival = previous_end + math.dist(position, target) / agent["nom_velocity"]
            audit.check(task["start_time"] - 1e-7 <= start <= task["end_time"] + 1e-7,
                        "start_window", (context, t_id))
            audit.check(start + 1e-7 >= arrival, "travel_and_duration", (context, t_id))
            score += task["task_value"] * math.exp(-task["discount"] * (start - task["start_time"]))
            previous_end, position = start + task["duration"], target
    return {"assigned": set(assigned), "score": score, "complete": set(assigned) == set(task_ids)}


def auction(audit, s, e, context, initial=False):
    ids, tasks = e["participant_ids"], e["task_ids"]
    audit.check(ids == sorted(set(ids)) and tasks == sorted(set(tasks)), "scope_unique_sorted", context)
    audit.check(set(e["paths"]) == {str(a) for a in ids}, "scope_path_agents", context)
    if not initial:
        audit.check(s["failed_agent"] not in ids, "failed_agent_not_participant", context)
    result = schedule(audit, s, e["paths"], e["times"], tasks, context,
                      failed=None if initial else s["failed_agent"])
    audit.check(result["complete"] == e["complete"], "episode_completeness_recomputed", context)
    history, senders = e["broadcast_history"], e["broadcast_agents_history"]
    audit.check(e["rounds"] == len(history) == len(senders), "actual_round_count", context)
    audit.check(e["broadcasts"] == sum(history), "episode_broadcast_sum", context)
    audit.check(e["rounds"] > 0 and e["runtime_seconds"] >= 0 and math.isfinite(e["runtime_seconds"]),
                "finite_episode_cost", context)
    for count, sent in zip(history, senders):
        audit.check(count == len(sent) == len(set(sent)) and set(sent) <= set(ids), "senders_accounting", context)
        if not e["event_triggered"]:
            audit.check(sent == ids, "standard_broadcasts_every_round", context)
    audit.check(e["winner_id_mapping"] == ids and e["winner_records_use_local_ids"], "winner_id_mapping", context)
    audit.check(len(e["winners"]) == len(e["winning_bids"]) == len(ids), "belief_agent_dimensions", context)
    audit.check(all(len(row) == len(tasks) for row in e["winners"] + e["winning_bids"]), "belief_task_dimensions", context)
    audit.check(len(e["path_bids"]) == len(ids), "path_bid_agent_dimensions", context)
    owners = {t: [] for t in tasks}
    task_by_id = {t["task_id"]: t for t in s["tasks"]}
    for local, agent in enumerate(ids):
        path = e["paths"][str(agent)]
        bids = e["path_bids"][local]
        audit.check(len(path) == len(bids), "path_bid_lengths", context)
        for t, start, bid in zip(path, e["times"][str(agent)], bids):
            owners[t].append((local, bid))
            task = task_by_id[t]
            reward = task["task_value"] * math.exp(-task["discount"] * (start - task["start_time"]))
            bonus = 1.1 if not initial and s["owner"].get(str(t)) == agent else 1.0
            audit.close(bid, reward * bonus, "bid_reward_and_bonus", (context, t))
    for j, task in enumerate(tasks):
        owner = owners[task]
        winner, bid = owner[0] if len(owner) == 1 else (-1, -1)
        audit.check(len(owner) <= 1, "auction_unique_owner", (context, task))
        for w, b in zip(e["winners"], e["winning_bids"]):
            audit.check(w[j] == winner, "winner_matches_path", (context, task))
            audit.close(b[j], bid, "winning_bid_matches_path_bid", (context, task), tolerance=1e-5)
    audit.check(not e["exception"] and e["termination_reason"] == "legacy_quiet", "solver_termination", context)
    # Flags are cross-checked only after independent physical/belief checks.
    audit.check(e["valid"] and not e["errors"], "episode_reported_diagnostics", context)
    return result


def audit_run(output, source_root=ROOT):
    audit = Audit()
    with (output / "trials.csv").open(encoding="utf-8", newline="") as stream:
        csv_rows = list(csv.DictReader(stream))
    manifest = read_json(output / "manifest.json")
    preflight = read_json(output / "preflight.json")
    audit.check(len(csv_rows) == 270, "total_270_rows")
    csv_by_key = {}
    for row in csv_rows:
        key = int(row["num_robots"]), int(row["seed"]), row["method"]
        audit.check(key not in csv_by_key, "no_duplicate_method_row", key)
        csv_by_key[key] = row
    expected = {(n, seed, m) for n in SCALES for seed in range(30) for m in METHODS}
    audit.check(set(csv_by_key) == expected, "all_scales_seeds_methods_exact")
    audit.check(len(list((output / "paired_inputs").glob("*.json"))) == 90, "90_snapshot_files")
    audit.check(len(list((output / "diagnostics").glob("*.json"))) == 270, "270_diagnostic_files")
    audit.check(manifest["seeds"] == list(range(30)) and manifest["robots"] == [6, 12, 24]
                and manifest["mode"] == "formal", "formal_manifest_configuration")
    audit.check(manifest["config"] == preflight["configuration"], "config_matches_preflight")
    audit.check(manifest["git_commit"] == preflight["git_commit"], "git_commit_matches_preflight")
    source_hashes = {}
    for name, h in preflight["source_sha256"].items():
        source_hashes[name] = sha(source_root / name.replace("\\", "/"))
        audit.check(source_hashes[name] == h, "preflight_source_unchanged", name)
    for name, h in manifest["source_sha256"].items():
        audit.check(sha(source_root / name.replace("\\", "/")) == h, "run_source_hash_matches", name)
    snapshots, details = {}, {}
    episode_count, local_failures, initial_broadcasts = 0, [], 0
    for n, total_tasks in SCALES.items():
        audit.check(sum(int(r["num_robots"]) == n for r in csv_rows) == 90, "90_rows_per_scale", n)
        for seed in range(30):
            context = f"n{n}/seed{seed}"
            try:
                payload = read_json(output / f"paired_inputs/n{n}_seed{seed}.json")
                s = payload["snapshot"]
                snapshots[n, seed] = payload
                audit.check(fingerprint(s) == payload["input_fingerprint"], "saved_snapshot_sha256", context)
                audit.check(s["config"] == manifest["config"] and s["seed"] == seed, "snapshot_config_seed", context)
                audit.check([a["agent_id"] for a in s["agents"]] == list(range(n)), "robot_count_ids", context)
                audit.check([t["task_id"] for t in s["tasks"]] == list(range(total_tasks)), "task_count_ids", context)
                rng = random.Random(seed)
                for item in s["agents"] + s["tasks"]:
                    audit.check(item["x"] == rng.uniform(0, 100) and item["y"] == rng.uniform(0, 100),
                                "positions_match_original_seed_no_resampling", context)
                    audit.check(item["z"] == 0, "two_dimensional_positions", context)
                audit.check(all(a["agent_type"] == 0 and a["nom_velocity"] == 5 and a["availability"] == 0
                                for a in s["agents"]), "homogeneous_robots", context)
                audit.check(all(t["task_type"] == 0 and t["task_value"] == 100 and t["duration"] == 8
                                and t["start_time"] == 0 and t["end_time"] == 240 and t["discount"] == .02
                                for t in s["tasks"]), "homogeneous_tasks", context)
                initial_owner = {str(t): int(a) for a, path in s["initial_paths"].items() for t in path}
                audit.check(initial_owner == s["owner"], "initial_owner_matches_paths", context)
                working = sorted(int(a) for a, path in s["initial_paths"].items() if path)
                audit.check(s["failed_agent"] == random.Random(100000 + seed).choice(working), "failure_fixed_rule", context)
                initial = payload["initial_auction"]
                audit.check(initial["scope"] == "initial" and initial["participant_ids"] == list(range(n))
                            and initial["task_ids"] == list(range(total_tasks)), "initial_full_scope", context)
                audit.check(initial["paths"] == s["initial_paths"] and initial["times"] == s["initial_times"],
                            "common_initial_snapshot", context)
                initial_result = auction(audit, s, initial, context + "/initial", initial=True)
                audit.check(initial_result["complete"], "initial_complete", context)
                initial_broadcasts += initial["broadcasts"]
                affected = sorted(int(t) for t, a in s["owner"].items() if a == s["failed_agent"])
                audit.check(1 <= len(affected) <= 4, "affected_count_one_to_four", context)
                active = sorted(a["agent_id"] for a in s["agents"] if a["agent_id"] != s["failed_agent"])
                for method_index, method in enumerate(METHODS):
                    key = n, seed, method
                    d = read_json(output / f"diagnostics/n{n}_seed{seed}_method{method_index}.json")
                    details[key] = d
                    r, csv_row = d["row"], csv_by_key[key]
                    for name, value in r.items():
                        expected_value = "N/A" if value is None else str(value)
                        audit.check(csv_row.get(name) == expected_value, "csv_equals_diagnostic_row", (key, name))
                    audit.check(r["input_fingerprint"] == d["input_fingerprint"] == payload["input_fingerprint"],
                                "paired_identical_input", key)
                    audit.check(r["seed"] == seed and r["num_robots"] == n and r["num_tasks"] == total_tasks
                                and r["method"] == d["method"] == method, "row_identity", key)
                    audit.check(r["failed_agent"] == s["failed_agent"] and r["affected_tasks"] == len(affected),
                                "paired_failure_and_affected_denominator", key)
                    for name, value in r.items():
                        if isinstance(value, (float, int)) and not isinstance(value, bool):
                            audit.check(math.isfinite(value) and value >= 0, "finite_nonnegative_metrics", (key, name))
                    for name in ("post_failure_broadcasts", "broadcasts_per_affected_task", "runtime_seconds",
                                 "consensus_rounds", "assigned_task_rate", "assignment_score"):
                        audit.check(r.get(name) is not None, "no_missing_key_metric", (key, name))
                    result = schedule(audit, s, d["final_paths"], d["final_times"], range(total_tasks), key, s["failed_agent"])
                    audit.close(r["assignment_score"], result["score"], "unbonused_final_score", key)
                    audit.close(r["assigned_task_rate"], len(result["assigned"]) / total_tasks, "unique_assignment_rate", key)
                    audit.check(result["complete"], "final_all_tasks_assigned", key)
                    audit.check(r["complete"] == result["complete"] and r["duplicate_tasks"] == 0, "final_flags_recomputed", key)
                    episodes = d["episodes"]
                    for index, e in enumerate(episodes):
                        auction(audit, s, e, f"{context}/{method}/episode{index}")
                    episode_count += len(episodes)
                    for scope in ("local", "global"):
                        group = [e for e in episodes if e["scope"] == scope]
                        for metric, field in (("broadcasts", "broadcasts"), ("rounds", "rounds"),
                                              ("runtime_seconds", "runtime_seconds")):
                            audit.close(r[f"{scope}_{metric}"], sum(e[field] for e in group), "scope_cost_accumulation", (key, scope, metric))
                    audit.close(r["post_failure_broadcasts"], sum(e["broadcasts"] for e in episodes), "post_cost_excludes_initial_broadcasts", key)
                    audit.close(r["consensus_rounds"], sum(e["rounds"] for e in episodes), "post_cost_excludes_initial_rounds", key)
                    audit.close(r["auction_runtime_seconds"], sum(e["runtime_seconds"] for e in episodes), "auction_runtime_sum", key)
                    audit.close(r["runtime_seconds"], r["auction_runtime_seconds"] + r["controller_validation_seconds"], "total_runtime_decomposition", key)
                    audit.check(r["runtime_seconds"] >= r["auction_runtime_seconds"], "controller_includes_all_auctions", key)
                    audit.close(r["broadcasts_per_affected_task"], r["post_failure_broadcasts"] / len(affected), "correct_affected_denominator", key)
                    audit.check(r["initial_broadcasts"] == initial["broadcasts"] and r["initial_rounds"] == initial["rounds"], "initial_cost_separate", key)
                    audit.check(r["post_failure_auctions"] == len(episodes), "post_auction_count", key)
                    if method != METHODS[2]:
                        audit.check(r["local_recovery_success"] is None and csv_row["local_recovery_success"] == "N/A", "local_rate_na_for_global", key)
                        audit.check([e["scope"] for e in episodes] == ["global"], "global_method_scope", key)
                        audit.check(episodes[0]["event_triggered"] == (method == METHODS[1]), "global_broadcast_policy", key)
                    else:
                        candidates = {str(t): sorted(a["agent_id"] for a in s["agents"] if a["agent_id"] in active
                            and math.dist((a["x"], a["y"]), (s["tasks"][t]["x"], s["tasks"][t]["y"])) <= 40)
                            for t in affected}
                        audit.check(d["candidates_by_affected_task"] == candidates, "candidates_recomputed_40m", key)
                        local_episodes = [e for e in episodes if e["scope"] == "local"]
                        audit.check(r["local_attempted"] == bool(local_episodes), "local_attempt_flag", key)
                        if not all(candidates.values()):
                            audit.check(not local_episodes and r["fallback_reason"] == "no_nearby_capable_robot", "no_candidate_precheck", key)
                        else:
                            audit.check(len(local_episodes) == 1, "eligible_local_attempt_not_skipped", key)
                        if local_episodes:
                            local = local_episodes[0]
                            participants = sorted({a for values in candidates.values() for a in values})
                            scope = set(affected) | {int(t) for t, a in s["owner"].items() if a in participants}
                            audit.check(local["participant_ids"] == participants and set(local["task_ids"]) == scope,
                                        "candidate_union_and_incumbent_scope", key)
                            expected_eligibility = [[t not in affected or a in candidates[str(t)] for t in local["task_ids"]]
                                                    for a in participants]
                            audit.check(local["radius"] == 40 and local["affected_task_ids"] == affected
                                        and local["eligibility"] == expected_eligibility and local["event_triggered"], "local_radius_matrix", key)
                            for a, path in local["paths"].items():
                                audit.check(all(t not in affected or int(a) in candidates[str(t)] for t in path), "local_assigned_radius", key)
                            if not local["complete"]:
                                local_failures.append({"num_robots": n, "seed": seed, "local_broadcasts": local["broadcasts"],
                                    "local_rounds": local["rounds"], "local_runtime_seconds": local["runtime_seconds"],
                                    "unassigned_tasks": sorted(scope - {t for path in local["paths"].values() for t in path})})
                                audit.check(len(episodes) == 2 and r["fallback_reason"] == "local_capacity_or_schedule_infeasible", "failed_attempt_followed_by_global", key)
                        success = bool(local_episodes and local_episodes[0]["complete"] and len(episodes) == 1)
                        audit.check(r["local_recovery_success"] == success, "local_success_recomputed", key)
                        if success:
                            local = local_episodes[0]
                            composed_paths = {a: p for a, p in s["initial_paths"].items() if int(a) != s["failed_agent"]}
                            composed_times = {a: p for a, p in s["initial_times"].items() if int(a) != s["failed_agent"]}
                            composed_paths.update(local["paths"])
                            composed_times.update(local["times"])
                            audit.check(d["final_paths"] == composed_paths and d["final_times"] == composed_times,
                                        "local_merge_and_unchanged_nonparticipants", key)
                            audit.check(r["auction_scope"] == "local" and not r["fallback_reason"], "local_success_scope", key)
                    if r["auction_scope"] == "global":
                        last = episodes[-1]
                        audit.check(last["scope"] == "global" and last["participant_ids"] == active
                                    and last["task_ids"] == list(range(total_tasks)), "global_all_survivors_tasks", key)
                        audit.check(d["final_paths"] == last["paths"] and d["final_times"] == last["times"], "final_equals_global_consensus_paths", key)
                    audit.check(r["status"] == "ok" and r["valid_assignment"], "reported_success_after_independent_checks", key)
                first, second = details[n, seed, METHODS[0]], details[n, seed, METHODS[1]]
                audit.check(first["final_paths"] == second["final_paths"] and first["final_times"] == second["final_times"], "global_control_schedule_equality", context)
            except Exception as exc:
                audit.check(False, "audit_exception", f"{context}: {type(exc).__name__}: {exc}")
    return audit, csv_rows, details, {"actual_post_failure_auctions": episode_count,
        "actual_initial_auctions": len(snapshots), "initial_broadcasts_excluded_total": initial_broadcasts,
        "failed_local_attempts": local_failures,
        "consensus_scope": "Every actual auction participant's complete winner/bid records checked against that auction's paths. Local final schedule composes this with unchanged outsider schedules; mission-wide dissemination to outsiders is not simulated or verified."}


def negative_controls(output, details):
    """Deliberately corrupt copies in memory; never edit raw evidence."""
    payload = read_json(output / "paired_inputs/n6_seed0.json")
    s = payload["snapshot"]
    episode = details[6, 0, METHODS[0]]["episodes"][0]
    results = {}
    for name in ("broadcast_count", "winner_record", "winning_bid", "start_window"):
        bad = copy.deepcopy(episode)
        if name == "broadcast_count":
            bad["broadcasts"] += 1
        elif name == "winner_record":
            bad["winners"][0][0] = -1
        elif name == "winning_bid":
            bad["winning_bids"][0][0] += 10
        else:
            agent = next(a for a, path in bad["paths"].items() if path)
            bad["times"][agent][0] = 241
        check = Audit()
        auction(check, s, bad, f"negative-control/{name}")
        results[name] = {"detected": bool(check.errors), "rules": sorted({e["rule"] for e in check.errors})}
    check = Audit()
    row = details[6, 0, METHODS[0]]["row"]
    score = schedule(check, s, episode["paths"], episode["times"], range(18), "score-negative")["score"]
    check.close(row["assignment_score"] * 1.1, score, "unbonused_final_score")
    results["bonus_contaminated_reported_score"] = {"detected": bool(check.errors)}
    return results


def audit_saved(data, output):
    raw_files = [data / n for n in ("trials.csv", "summary.csv", "manifest.json", "analysis.json")]
    raw_files += sorted((data / "paired_inputs").glob("*.json")) + sorted((data / "diagnostics").glob("*.json"))
    raw_hashes = {str(p.relative_to(data)).replace("\\", "/"): sha(p) for p in raw_files}
    hash_path = data / "raw_files_sha256.json"
    if hash_path.exists() and read_json(hash_path) != raw_hashes:
        raise RuntimeError("Raw evidence changed since earlier audit; preserving old hashes")
    if not hash_path.exists():
        hash_path.write_text(json.dumps(raw_hashes, indent=2), encoding="utf-8")
    source_root = data / "source_snapshot" if (data / "source_snapshot").is_dir() else ROOT
    audit, rows, details, additional = audit_run(data, source_root)
    controls = negative_controls(data, details) if not audit.errors else {}
    audit.check(bool(controls) and all(c["detected"] for c in controls.values()), "negative_controls_detected")
    report = {"audit_passed": not audit.errors, "method_rows": len(rows),
              "checks_executed": sum(audit.checks.values()), "checks_by_rule": dict(audit.checks),
              "errors": audit.errors, "negative_controls": controls, **additional,
              "raw_evidence_unchanged": all(sha(data / name) == value for name, value in raw_hashes.items()),
              "audit_source_sha256": sha(Path(__file__)),
              "does_not_import_experiment_or_solver": True}
    (output / "independent_audit.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("checks_by_rule", "failed_local_attempts")}, indent=2))
    return 0 if report["audit_passed"] and report["raw_evidence_unchanged"] else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output_dir.resolve()
    with evidence_directory(output) as data:
        return audit_saved(data, output)


if __name__ == "__main__":
    raise SystemExit(main())
