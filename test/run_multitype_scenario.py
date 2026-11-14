#!/usr/bin/env python3
"""Deterministic four-robot-type, six-task-type CBBA scheduling example."""

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from Agent import Agent
from CBBA import CBBA
from Task import Task
from WorldInfo import WorldInfo


AGENT_SPECS = [
    ("survey_quad", 5.0, [(10, 10), (50, 10), (90, 10)]),
    ("cargo_quad", 4.0, [(15, 25), (50, 25), (85, 25)]),
    ("rescue_car", 3.0, [(10, 70), (50, 70), (90, 70)]),
    ("supply_truck", 2.5, [(15, 85), (50, 85), (85, 85)]),
]

# ID, type, description, x, y, value, release, deadline, duration.
TASK_SPECS = [
    (0, "survey", "西区航拍", 8, 17, 120, 0, 45, 6),
    (1, "survey", "西中区航拍", 30, 10, 105, 4, 52, 6),
    (2, "survey", "东中区航拍", 64, 13, 110, 2, 55, 6),
    (3, "survey", "东区航拍", 92, 18, 125, 0, 45, 6),
    (4, "relay", "西区通信中继", 18, 20, 130, 5, 50, 7),
    (5, "relay", "西中区通信中继", 43, 22, 115, 0, 54, 7),
    (6, "relay", "东中区通信中继", 66, 25, 120, 6, 56, 7),
    (7, "relay", "东区通信中继", 84, 19, 135, 0, 50, 7),
    (8, "air_drop", "西区空投", 12, 35, 130, 8, 62, 8),
    (9, "air_drop", "西中区空投", 38, 33, 120, 5, 65, 8),
    (10, "air_drop", "东中区空投", 62, 35, 125, 7, 65, 8),
    (11, "air_drop", "东区空投", 88, 33, 140, 8, 62, 8),
    (12, "rescue", "西区救援", 8, 63, 150, 0, 52, 9),
    (13, "rescue", "西中区救援", 32, 68, 135, 5, 60, 9),
    (14, "rescue", "东中区救援", 65, 64, 145, 2, 58, 9),
    (15, "rescue", "东区救援", 92, 62, 155, 0, 52, 9),
    (16, "ground_inspect", "西区地面巡检", 18, 75, 105, 4, 58, 5),
    (17, "ground_inspect", "西中区地面巡检", 42, 80, 100, 0, 60, 5),
    (18, "ground_inspect", "东中区地面巡检", 63, 78, 110, 5, 62, 5),
    (19, "ground_inspect", "东区地面巡检", 84, 75, 115, 3, 58, 5),
    (20, "supply", "西区重物补给", 12, 93, 125, 8, 72, 10),
    (21, "supply", "西中区重物补给", 38, 90, 115, 5, 72, 10),
    (22, "supply", "东中区重物补给", 63, 92, 120, 7, 75, 10),
    (23, "supply", "东区重物补给", 90, 92, 130, 8, 72, 10),
]


def build_scenario():
    with (ROOT / "config_multitype_scenario.json").open(encoding="utf-8") as file:
        config = json.load(file)
    agents = []
    for type_name, speed, positions in AGENT_SPECS:
        for x, y in positions:
            agents.append(Agent(agent_id=len(agents),
                                agent_type=config["AGENT_TYPES"].index(type_name),
                                x=x, y=y, nom_velocity=speed))
    tasks = [Task(task_id=task_id,
                  task_type=config["TASK_TYPES"].index(type_name),
                  task_value=value, start_time=release, end_time=deadline,
                  duration=duration, discount=0.02, x=x, y=y)
             for task_id, type_name, _, x, y, value, release, deadline, duration
             in TASK_SPECS]
    return config, agents, tasks, WorldInfo([0, 100], [0, 100], [0, 0])


def run():
    config, agents, tasks, world = build_scenario()
    solver = CBBA(config)
    paths, times = solver.solve(agents, tasks, world, max_depth=4,
                                time_window_flag=True, event_triggered=True)
    task_by_id = {task.task_id: task for task in tasks}
    descriptions = {row[0]: row[2] for row in TASK_SPECS}
    assigned = [task_id for path in paths for task_id in path]
    if len(assigned) != len(set(assigned)):
        raise AssertionError("A task was assigned more than once")
    lines = [
        "# 多类型机器人任务安排清单", "",
        "此表由 `test/run_multitype_scenario.py` 调用当前 CBBA 实际计算生成。",
        "时间单位为秒；时间窗限制任务的开始时间，任务结束时间 = 开始时间 + 持续时间。",
        "所有坐标单位为米，",
        "空中/地面是任务能力分类，场景使用二维位置，不模拟飞行高度或道路障碍。", "",
        f"机器人 {len(agents)} 台；任务 {len(tasks)} 个；已分配 {len(assigned)} 个；"
        f"ED-CBBA 共 {solver.iterations} 轮、{solver.total_broadcasts} 次广播。", "",
        "## 能力与机器人", "",
        "| 类型 | 台数 | 速度 m/s | 可竞价任务 |", "| --- | ---: | ---: | --- |",
    ]
    for type_name, speed, positions in AGENT_SPECS:
        allowed = "、".join(config["COMPATIBILITY"][type_name])
        lines.append(f"| {type_name} | {len(positions)} | {speed:g} | {allowed} |")
    lines += ["", "| 机器人 | 类型 | 起点 (x,y) |", "| --- | --- | --- |"]
    for agent in agents:
        lines.append(f"| R{agent.agent_id:02d} | {config['AGENT_TYPES'][agent.agent_type]} "
                     f"| ({agent.x:g}, {agent.y:g}) |")
    lines += ["", "## 任务清单", "",
              "| 任务 | 类型 | 内容 | 坐标 (x,y) | 价值 | 时间窗 | 时长 |",
              "| --- | --- | --- | --- | ---: | --- | ---: |"]
    for task in tasks:
        lines.append(f"| T{task.task_id:02d} | {config['TASK_TYPES'][task.task_type]} "
                     f"| {descriptions[task.task_id]} | ({task.x:g}, {task.y:g}) "
                     f"| {task.task_value:g} | {task.start_time:g}–{task.end_time:g} "
                     f"| {task.duration:g} |")
    lines += ["", "## 实际分配与执行顺序", "",
              "| 机器人 | 类型 | 顺序 | 任务 | 内容 | 开始 | 结束 | 本轮出价 |",
              "| --- | --- | ---: | --- | --- | ---: | ---: | ---: |"]
    for agent, path, starts, scores in zip(agents, paths, times, solver.scores_list):
        previous_end = agent.availability
        previous_position = (agent.x, agent.y, agent.z)
        for order, (task_id, start, score) in enumerate(zip(path, starts, scores), 1):
            task = task_by_id[task_id]
            if config["TASK_TYPES"][task.task_type] not in config["COMPATIBILITY"][config["AGENT_TYPES"][agent.agent_type]]:
                raise AssertionError("Incompatible robot-task assignment")
            if not task.start_time <= start <= task.end_time:
                raise AssertionError("Task starts outside its time window")
            position = (task.x, task.y, task.z)
            arrival = previous_end + math.dist(previous_position, position) / agent.nom_velocity
            if start + 1e-7 < arrival:
                raise AssertionError("Robot cannot reach the task in time")
            lines.append(f"| R{agent.agent_id:02d} | {config['AGENT_TYPES'][agent.agent_type]} "
                         f"| {order} | T{task_id:02d} | {descriptions[task_id]} "
                         f"| {start:.1f} | {start + task.duration:.1f} | {score:.1f} |")
            previous_end = start + task.duration
            previous_position = position
    unassigned = sorted(set(task_by_id) - set(assigned))
    lines += ["", "未分配任务：" + ("、".join(f"T{i:02d}" for i in unassigned) if unassigned else "无"), ""]
    result = "\n".join(lines)
    output = ROOT / "doc" / "multitype_schedule.md"
    output.write_text(result, encoding="utf-8")
    print(result)
    return solver, paths, times


if __name__ == "__main__":
    run()
