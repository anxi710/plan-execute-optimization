"""Render pending and stopped benchmark cohorts from observed checkpoints."""

import argparse
from collections import Counter
from datetime import datetime
from itertools import combinations
from math import fsum
from pathlib import Path
from zoneinfo import ZoneInfo

from report import BENCHMARK_EVIDENCE, MODES, ROOT, STYLE, benchmark_matrix, html, link, matched_trials, terminal_protocol
from toolkit.utils.files import read_json, write_text_atomic


EXPERIMENT = ROOT / "experiments/planner-centered"
RUNS = EXPERIMENT / "runs"
OUTPUT = EXPERIMENT / "audit-preview.html"
CHINA = ZoneInfo("Asia/Shanghai")
PENDING = {"尚无当前轨迹", "轨迹尚未结束"}


def load_run(name):
    directory = RUNS / name
    manifest = read_json(directory / "manifest.json")
    return manifest, matched_trials(directory, manifest, preview=True)


def combine_science(active, archived):
    latest, current = active
    earlier, saved = archived
    models = latest["model_order"]
    if (latest["run_id"] != earlier["run_id"] or latest["benchmark"] != earlier["benchmark"]
            or not set(models) <= set(earlier["model_order"])
            or any(earlier["models"][model] != latest["models"][model] for model in models)):
        raise ValueError("ScienceWorld snapshots differ in task or model settings")
    for trial_id, trial in latest["trials"].items():
        fields = ("model", "task_id", "mode", "executor_limit", "planner_limit", "return_every")
        if any(trial[field] != earlier["trials"][trial_id][field] for field in fields):
            raise ValueError(f"ScienceWorld trial settings changed for {trial_id}")
    if set(current) != {key for key in saved if key[0] in models}:
        raise ValueError("ScienceWorld snapshots do not align")
    return earlier, saved | current


def mean_text(scores):
    return f"{fsum(scores) / len(scores):.3f}" if scores else "—"


def paired_tasks(tasks):
    if not tasks:
        return "0"
    names = html(" · ".join(str(task) for task in tasks))
    return f'<details class="sample"><summary>{len(tasks):,}</summary><code>{names}</code></details>'


def score_table(title, headers, rows):
    columns = "".join(f'<th scope="col">{column}</th>' for column in headers)
    return f'''<div class="table-wrap" tabindex="0" role="region" aria-label="{html(title)}">
<table><thead><tr>{columns}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'''


def four_way_rows(task_ids, models, trials):
    matches = {}
    rows = []
    for model in models:
        matches[model] = [
            task for task in task_ids if all(trials[model, task, mode].score is not None for mode in MODES)
        ]
        means = [mean_text([trials[model, task, mode].score for task in matches[model]]) for mode in MODES]
        rows.append(score_row(model, paired_tasks(matches[model]), means))
    shared = [task for task in task_ids if all(task in matches[model] for model in models)]
    means = [mean_text([trials[model, task, mode].score for model in models for task in shared]) for mode in MODES]
    rows.append(score_row("全部模型", paired_tasks(shared), means))
    return rows, len(shared)


def score_row(label, tasks, values):
    cells = "".join(f'<td class="number">{value}</td>' for value in values)
    return f'<tr><th scope="row">{html(label)}</th><td>{tasks}</td>{cells}</tr>'


def pair_rows(task_ids, models, trials):
    rows = []
    for model in models:
        for left, right in combinations(MODES, 2):
            tasks = [task for task in task_ids if trials[model, task, left].score is not None
                     and trials[model, task, right].score is not None]
            values = [MODES[left][0], mean_text([trials[model, task, left].score for task in tasks]),
                      MODES[right][0], mean_text([trials[model, task, right].score for task in tasks])]
            rows.append(score_row(model, paired_tasks(tasks), values))
    return rows


def render_section(section_id, manifest, trials, tasks, run_names, phase, *, pairs_open=False):
    benchmark = manifest["benchmark"]
    name, models = benchmark["name"], manifest["model_order"]
    task_ids = [task["task_id"] for task in tasks]
    rows, shared = four_way_rows(task_ids, models, trials)
    four = score_table(f"{name} 四框架配对", ("模型", "共同任务数", *(labels[0] for labels in MODES.values())), rows)
    pairs = score_table(f"{name} 框架两两比较", ("模型", "共同任务数", "框架 A", "A 均分", "框架 B", "B 均分"),
                        pair_rows(task_ids, models, trials))
    scored = [trial for trial in trials.values() if trial.score is not None]
    pending = sum(trial.score is None and trial.stop in PENDING for trial in trials.values())
    missing = Counter(trial.stop for trial in trials.values() if trial.score is None and trial.stop not in PENDING)
    reasons = " · ".join(f"{html(reason)} {count:,} 格" for reason, count in missing.most_common())
    success = sum(trial.success is True for trial in scored)
    native = sum(trial.replay is not None or trial.harbor_budget is not None for trial in scored)
    native_note = f"。其中 {native:,} 格由原生评分凭证补全" if native else ""
    scope = f"{len(tasks):,} 个官方任务"
    if benchmark["selection"] == "reviewed_subset":
        scope = f'{len(tasks):,} / {benchmark["canonical_task_count"]:,} 个官方任务'
    evidence_tasks = [task for task in tasks if any(
        trials[model, task["task_id"], mode].score is not None
        for model in models for mode in MODES
    )]
    matrix = benchmark_matrix(evidence_tasks, models, trials, OUTPUT)
    sources = "".join(link(RUNS / dirname / "manifest.json", f"{dirname} 清单", OUTPUT) for dirname in run_names)
    entrypoint, scoring = BENCHMARK_EVIDENCE[name]
    sources += link(Path(__file__).with_name(entrypoint), "评测入口", OUTPUT)
    if benchmark.get("canonical_task_file"):
        sources += link(Path(benchmark["canonical_task_file"]), "官方任务映射", OUTPUT)
    return f'''<section id="{section_id}" class="benchmark">
<h2>{html(name)}</h2>
<p class="muted">{html(phase)} · {scope} · {len(models)} 模型 × {len(MODES)} 框架</p>
<p class="metrics"><strong>{len(scored):,} / {len(trials):,} 格有效评分</strong>
<span>{success:,} 格成功</span><span>{sum(missing.values()):,} 格结束缺评</span>
<span>{pending:,} 格尚无终局</span></p>
<p class="small">全配置共同任务 {shared:,} / {len(tasks):,}{native_note}。{'结束缺评 · ' + reasons + '。' if reasons else ''}</p>
<p class="small">{html(scoring)}</p>
{four}
<details{" open" if pairs_open else ""}><summary>六组框架两两比较</summary>
<p class="small">每行只用该模型两种框架都取得有效评分的任务。展开任务数可查样本 ID。</p>{pairs}</details>
<details><summary>查看逐任务得分与最终评分轨迹</summary>
<p class="small">这里显示至少有一格取得有效评分的任务。点击分值可打开最终评分轨迹。缺评格提供停止原因。</p>{matrix}</details>
<p class="links">{sources}</p>
</section>'''


def build_preview(alf_name="alfworld-test-01"):
    start = datetime.now(CHINA)
    alf, alf_trials = load_run(alf_name)
    terminal_names = ["terminalbench-reviewed-01", *(RUNS / "runtime/terminal-supplements.txt").read_text().splitlines()]
    terminal, terminal_trials = load_run(terminal_names[0])
    terminal_tasks = list(terminal["benchmark"]["tasks"])
    for name in terminal_names[1:]:
        supplement, trials = load_run(name)
        if terminal_protocol(terminal) != terminal_protocol(supplement) or terminal_trials.keys() & trials.keys():
            raise ValueError(f"Terminal-Bench supplement differs or overlaps: {name}")
        terminal_tasks.extend(supplement["benchmark"]["tasks"])
        terminal_trials.update(trials)
    if len(terminal_tasks) > terminal["benchmark"]["canonical_task_count"]:
        raise ValueError("Terminal-Bench task coverage exceeds the official suite")
    web_name = "webshop-test-01"
    web, web_trials = load_run(web_name)
    science_names = ["sciworld-test-01", "sciworld-test-01-four-models"]
    science, science_trials = combine_science(*(load_run(name) for name in science_names))
    end = datetime.now(CHINA)
    terminal_phase = ("评分已终止 · 待人工核验" if (RUNS / "runtime/terminal-disabled").is_file()
                      else "正式评分进行中 · 已审阅任务")
    alf_phase = "正式评分已结束" if alf["status"] == "complete" else "正式评分进行中"
    sections = "".join([
        render_section("alfworld", alf, alf_trials, alf["benchmark"]["tasks"], [alf_name], alf_phase),
        render_section("terminal", terminal, terminal_trials, terminal_tasks, terminal_names, terminal_phase),
        render_section("webshop", web, web_trials, web["benchmark"]["tasks"], [web_name], "评分已停止 · 部分样本", pairs_open=True),
        render_section("scienceworld", science, science_trials, science["benchmark"]["tasks"], science_names,
                       "评分已停止 · DeepSeek 取最后快照，其余模型取四模型归档", pairs_open=True),
    ])
    interval = f"{start:%Y-%m-%d %H:%M:%S}–{end:%H:%M:%S}（北京时间）"
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>四种规划框架 · 阶段性比较</title>
<style>{STYLE}
.hero {{ display: block; }}
.metrics {{ display: flex; gap: .4rem 1rem; flex-wrap: wrap; max-width: none; }}
.benchmark > details {{ margin-top: 1rem; }}
.sample {{ margin: 0; }}
.sample code {{ display: block; max-width: 24ch; max-height: 8rem; overflow: auto; }}
</style></head>
<body><a class="skip" href="#main">跳至主要内容</a>
<header><div class="wrap masthead"><strong>Planner 实验</strong>
<nav aria-label="评测目录"><a href="#alfworld">ALFWorld</a><a href="#terminal">Terminal-Bench</a>
<a href="#webshop">WebShop</a><a href="#scienceworld">ScienceWorld</a></nav></div></header>
<main class="wrap" id="main">
<div class="hero"><h1>四种规划框架的阶段性比较</h1>
<p class="small">原始轨迹读取时段 {interval}</p>
<p>每张主表比较同模型、同任务的四种框架。全部模型行进一步要求所有配置都有分。得分为各 benchmark 的原生分数均值，本页没有跨 benchmark 平均。</p>
<p class="muted">分母保留清单中的计划组合。缺评和未结束均不进入配对均值。样本可能随运行变化，分数描述现有配对样本，未估计重复运行波动。</p>
<p class="links">{link(EXPERIMENT / "audit.html", "查看运行审查与控制流", OUTPUT)}{link(EXPERIMENT / "README.md", "实验范围与证据", OUTPUT)}</p></div>
{sections}</main>
</body></html>'''


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alfworld-run", default="alfworld-test-01", metavar="RUN_NAME")
    args = parser.parse_args()
    if args.alfworld_run in {"", ".."} or Path(args.alfworld_run).name != args.alfworld_run:
        parser.error("Select a run name under the experiment's runs directory")
    write_text_atomic(OUTPUT, build_preview(args.alfworld_run))
    print(OUTPUT)
