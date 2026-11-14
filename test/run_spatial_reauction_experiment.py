#!/usr/bin/env python3
"""Paired spatial local/global re-auction experiment after one robot fails."""

import copy
import csv
import math
import random
import statistics
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "lib"))

from CBBA import CBBA
from test.run_multitype_scenario import build_scenario


RADII = (20, 40, 60)
SEEDS = range(30)
MAX_DEPTH = 4
INCUMBENCY_BONUS = 0.10
MAX_LOCAL_AFFECTED = 2


def make_trial(seed):
    """Jitter one fixed 100 m x 100 m mission; preserve paired inputs."""
    config, agents, tasks, world = build_scenario()
    rng = random.Random(seed)
    for item in agents + tasks:
        item.x = min(100.0, max(0.0, item.x + rng.uniform(-4, 4)))
        item.y = min(100.0, max(0.0, item.y + rng.uniform(-4, 4)))
    initial = CBBA(config)
    paths, starts = initial.solve(agents, tasks, world, max_depth=MAX_DEPTH,
                                  time_window_flag=True, event_triggered=True)
    owner = {task_id: agent.agent_id
             for agent, path in zip(agents, paths) for task_id in path}
    if len(owner) != len(tasks):
        raise AssertionError("The initial mission must allocate every task")
    working = [agent.agent_id for agent, path in zip(agents, paths) if path]
    failed_id = rng.choice(working)
    initial_paths = {agent.agent_id: path for agent, path in zip(agents, paths)}
    initial_times = {agent.agent_id: row for agent, row in zip(agents, starts)}
    return config, agents, tasks, world, owner, failed_id, initial_paths, initial_times


def bid_for_scope(config, agents, tasks, world, owner, participant_ids, task_ids,
                  affected_ids=(), radius=None, event_triggered=True):
    """Run one ED-CBBA auction, optionally restricting affected-task bids by radius."""
    participant_ids = sorted(participant_ids)
    task_ids = sorted(task_ids)
    by_agent = {agent.agent_id: agent for agent in agents}
    by_task = {task.task_id: task for task in tasks}
    local_id = {agent_id: index for index, agent_id in enumerate(participant_ids)}
    local_agents = []
    for agent_id in participant_ids:
        agent = copy.deepcopy(by_agent[agent_id])
        agent.agent_id = local_id[agent_id]
        local_agents.append(agent)
    local_tasks = [copy.deepcopy(by_task[task_id]) for task_id in task_ids]
    incumbents = {task_id: local_id[agent_id]
                  for task_id, agent_id in owner.items()
                  if task_id in task_ids and agent_id in local_id}
    eligibility = None
    if radius is not None:
        affected_ids = set(affected_ids)
        eligibility = [[task.task_id not in affected_ids or
                        math.dist((by_agent[agent_id].x, by_agent[agent_id].y),
                                  (task.x, task.y)) <= radius
                        for task in local_tasks] for agent_id in participant_ids]
    solver = CBBA(config)
    paths, times = solver.solve(
        local_agents, local_tasks, world, max_depth=MAX_DEPTH,
        time_window_flag=True, event_triggered=event_triggered,
        incumbent_owners=incumbents, incumbency_bonus=INCUMBENCY_BONUS,
        agent_task_eligibility=eligibility)
    mapped_paths = {agent_id: path for agent_id, path in zip(participant_ids, paths)}
    mapped_times = {agent_id: row for agent_id, row in zip(participant_ids, times)}
    return mapped_paths, mapped_times, solver.total_broadcasts


def schedule_result(config, agents, tasks, owner, failed_id, paths, times,
                    scope, reason, radius, broadcasts, participants, task_count, seed,
                    event_triggered=True):
    task_by_id = {task.task_id: task for task in tasks}
    assigned = [task_id for path in paths.values() for task_id in path]
    if len(assigned) != len(set(assigned)):
        raise AssertionError("Duplicate task assignment")
    true_score = 0.0
    handoffs = 0
    for agent in agents:
        if agent.agent_id == failed_id:
            continue
        path = paths.get(agent.agent_id, [])
        starts = times.get(agent.agent_id, [])
        if len(path) > MAX_DEPTH or len(path) != len(starts):
            raise AssertionError("Invalid robot capacity or schedule length")
        previous_end = agent.availability
        previous_position = (agent.x, agent.y, agent.z)
        type_name = config["AGENT_TYPES"][agent.agent_type]
        for task_id, start in zip(path, starts):
            task = task_by_id[task_id]
            if config["TASK_TYPES"][task.task_type] not in config["COMPATIBILITY"][type_name]:
                raise AssertionError("Incompatible assignment")
            position = (task.x, task.y, task.z)
            arrival = previous_end + math.dist(previous_position, position) / agent.nom_velocity
            if not task.start_time - 1e-7 <= start <= task.end_time + 1e-7 or start + 1e-7 < arrival:
                raise AssertionError("Infeasible assignment time")
            true_score += task.task_value * math.exp(-task.discount * (start - task.start_time))
            handoffs += owner[task_id] != agent.agent_id
            previous_end = start + task.duration
            previous_position = position
    label = radius if radius is not None else ("global_ed" if event_triggered else "global_cbba")
    return dict(seed=seed, radius=label,
                failed_agent=failed_id, affected_tasks=sum(value == failed_id for value in owner.values()),
                scope=scope, fallback_reason=reason, participants=participants,
                auction_tasks=task_count, broadcasts=broadcasts,
                assigned_tasks=len(assigned), true_score=round(true_score, 3),
                changed_owners=handoffs)


def run_trial(seed, radius, event_triggered=True):
    config, agents, tasks, world, owner, failed_id, original_paths, original_times = make_trial(seed)
    active_ids = [agent.agent_id for agent in agents if agent.agent_id != failed_id]
    affected = {task_id for task_id, agent_id in owner.items() if agent_id == failed_id}
    task_by_id = {task.task_id: task for task in tasks}
    agent_by_id = {agent.agent_id: agent for agent in agents}
    reason = ""
    attempted_broadcasts = 0

    if radius is not None:
        if len(affected) > MAX_LOCAL_AFFECTED:
            reason = "too_many_affected_tasks"
        else:
            eligible_by_task = {}
            for task_id in affected:
                task = task_by_id[task_id]
                task_type = config["TASK_TYPES"][task.task_type]
                eligible_by_task[task_id] = [agent_id for agent_id in active_ids
                    if task_type in config["COMPATIBILITY"][config["AGENT_TYPES"][agent_by_id[agent_id].agent_type]]
                    and math.dist((agent_by_id[agent_id].x, agent_by_id[agent_id].y),
                                  (task.x, task.y)) <= radius]
            if any(not eligible for eligible in eligible_by_task.values()):
                reason = "no_nearby_capable_robot"
            else:
                participants = sorted({agent_id for eligible in eligible_by_task.values()
                                       for agent_id in eligible})
                scoped_tasks = affected | {task_id for task_id, agent_id in owner.items()
                                           if agent_id in participants}
                local_paths, local_times, local_broadcasts = bid_for_scope(
                    config, agents, tasks, world, owner, participants, scoped_tasks,
                    affected_ids=affected, radius=radius)
                attempted_broadcasts += local_broadcasts
                assigned_local = {task_id for path in local_paths.values() for task_id in path}
                if assigned_local != scoped_tasks:
                    reason = "local_capacity_or_schedule_infeasible"
                else:
                    final_paths = {agent_id: copy.deepcopy(original_paths[agent_id])
                                   for agent_id in active_ids}
                    final_times = {agent_id: copy.deepcopy(original_times[agent_id])
                                   for agent_id in active_ids}
                    final_paths.update(local_paths)
                    final_times.update(local_times)
                    return schedule_result(
                        config, agents, tasks, owner, failed_id, final_paths, final_times,
                        "local", "", radius, local_broadcasts,
                        len(participants), len(scoped_tasks), seed)

    global_paths, global_times, global_broadcasts = bid_for_scope(
        config, agents, tasks, world, owner, active_ids,
        {task.task_id for task in tasks}, event_triggered=event_triggered)
    return schedule_result(
        config, agents, tasks, owner, failed_id, global_paths, global_times,
        "global", reason, radius, global_broadcasts + attempted_broadcasts,
        len(active_ids), len(tasks), seed, event_triggered=event_triggered)


def write_results(rows):
    doc = ROOT / "doc"
    csv_path = doc / "spatial_reauction_trials.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    summary = []
    for radius in (*RADII, "global_ed", "global_cbba"):
        sample = [row for row in rows if row["radius"] == radius]
        summary.append(dict(radius=radius, runs=len(sample),
                            local=sum(row["scope"] == "local" for row in sample),
                            global_count=sum(row["scope"] == "global" for row in sample),
                            broadcasts=statistics.mean(row["broadcasts"] for row in sample),
                            complete=sum(row["assigned_tasks"] == 24 for row in sample),
                            score=statistics.mean(row["true_score"] for row in sample),
                            handoffs=statistics.mean(row["changed_owners"] for row in sample)))
    global_ed = summary[-2]
    global_cbba = summary[-1]

    lines = ["# 距离分级重新竞价实验", "",
             "故障发生在任务执行前，使用同一批 30 个随机种子做配对比较。",
             "地图 100 m × 100 m，4 类机器人共 12 台，6 类任务共 24 个；",
             "每台最多 4 个任务，机器人坐标和任务坐标在基础场景上独立扰动 ±4 m。",
             "每个种子先运行一次初始 ED-CBBA，再随机选一台获得任务的机器人故障。", "",
             "局部候选人必须在线、能力匹配且与受影响任务的欧氏距离不超过 R。",
             "局部拍卖包含候选机器人原有任务，以计入已有安排与容量；受影响任务",
             "对超出 R 的机器人禁投。受影响任务超过 2 个、附近没有合格机器人，",
             "或局部拍卖无法安排全部相关任务时，升级为全局拍卖。",
             "全局拍卖由所有存活机器人对所有任务竞价。所有模式均使用 10% 原持有者奖励。", "",
             "本实验是静态故障后的重新规划，不模拟移动、任务执行时间或故障检测延迟。",
             "R 限制受影响任务的竞标资格，不代表无线电覆盖半径；",
             "参与同一拍卖的机器人在本实验中假定能直接通信。",
             "广播次数只统计故障后的拍卖，不含初始拍卖；一次机器人广播记为 1 次。",
             "若先尝试局部拍卖再升级全局，两次拍卖的广播都会计入。",
             "真实分数按任务原价值和计划开始时间重算，不含原持有者奖励。", "",
             "| R / 方法 | 试验数 | 局部成功 | 升级全局 | 平均广播 | 相比全局ED节省 | 全部24任务分配 | 平均真实分数 | 平均换手任务 |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for item in summary:
        saving = (f"{100 * (1 - item['broadcasts'] / global_ed['broadcasts']):.1f}%"
                  if isinstance(item["radius"], int) else "—")
        lines.append(f"| {item['radius']} | {item['runs']} | {item['local']} | "
                     f"{item['global_count'] if isinstance(item['radius'], int) else '—'} | "
                     f"{item['broadcasts']:.1f} | {saving} | {item['complete']}/{item['runs']} | "
                     f"{item['score']:.1f} | {item['handoffs']:.1f} |")
    lines += ["", f"全局 ED-CBBA 相比传统 CBBA 的平均广播减少 "
              f"{100 * (1 - global_ed['broadcasts'] / global_cbba['broadcasts']):.1f}%。",
              f"R=60 相比全局 ED-CBBA 的平均真实分数变化为 "
              f"{100 * (summary[2]['score'] / global_ed['score'] - 1):.2f}%。", ""]
    for radius in RADII:
        subset = [row for row in rows if row["radius"] == radius]
        reasons = {reason: sum(row["fallback_reason"] == reason for row in subset)
                   for reason in ("too_many_affected_tasks", "no_nearby_capable_robot",
                                  "local_capacity_or_schedule_infeasible")}
        lines.append(f"R={radius} 升级原因：任务过多 {reasons['too_many_affected_tasks']} 次，"
                     f"附近无合格机器人 {reasons['no_nearby_capable_robot']} 次，"
                     f"局部排程不可行 {reasons['local_capacity_or_schedule_infeasible']} 次。")
    lines += ["", "![距离阈值结果](spatial_reauction_radius.png)", "",
              "逐次结果见 `spatial_reauction_trials.csv`。", ""]
    (doc / "spatial_reauction_summary.md").write_text("\n".join(lines), encoding="utf-8")

    fig, axes = plt.subplots(1, 3, figsize=(15, 4), constrained_layout=True)
    x = list(range(5))
    labels = ["20", "40", "60", "Global ED", "Global CBBA"]
    axes[0].bar(x, [item["broadcasts"] for item in summary],
                color=["#f59e0b"] * 3 + ["#2176ae", "#29465b"])
    axes[0].set_xticks(x, labels)
    axes[0].tick_params(axis="x", labelrotation=25)
    axes[0].set_xlabel("Auction radius R (m)")
    axes[0].set_ylabel("Mean post-failure broadcasts")
    axes[0].grid(axis="y", alpha=.25)
    axes[1].bar(x[:3], [item["local"] / item["runs"] * 100 for item in summary[:3]], color="#2176ae")
    axes[1].set_xticks(x[:3], labels[:3])
    axes[1].set_xlabel("Auction radius R (m)")
    axes[1].set_ylabel("Local auction success (%)")
    axes[1].set_ylim(0, 100)
    axes[1].grid(axis="y", alpha=.25)
    score_loss = [100 * (1 - item["score"] / global_ed["score"])
                  for item in summary[:3]]
    axes[2].bar(x[:3], score_loss, color="#b56576")
    axes[2].set_xticks(x[:3], labels[:3])
    axes[2].set_xlabel("Auction radius R (m)")
    axes[2].set_ylabel("Mean score loss vs global ED (%)")
    axes[2].set_ylim(0, max(score_loss) * 1.25)
    axes[2].grid(axis="y", alpha=.25)
    fig.savefig(doc / "spatial_reauction_radius.png", dpi=180)
    plt.close(fig)
    return summary


def main():
    variants = [(radius, True) for radius in RADII] + [(None, True), (None, False)]
    rows = [run_trial(seed, radius, event_triggered=triggered)
            for seed in SEEDS for radius, triggered in variants]
    summary = write_results(rows)
    for item in summary:
        print(item)


if __name__ == "__main__":
    main()
