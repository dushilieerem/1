"""Build portable review documents and editable fishbone diagrams; no service access.

Run: python path/to/build.py
Requires Pillow and a CJK font; FISHBONE_FONT / FISHBONE_BOLD_FONT can override fonts.
All inputs and outputs are relative to this file. This is document generation only.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
FIGURES = ROOT / "figures"
W, H = 1680, 1060
INK, MUTED, PURPLE, LINE = "#272332", "#625D6C", "#65517F", "#B8AFCA"
BG, SOFT = "#FFFFFF", "#F3F0F7"


def choose_font(bold=False):
    override = os.getenv("FISHBONE_BOLD_FONT" if bold else "FISHBONE_FONT")
    windir = os.getenv("WINDIR")
    candidates = [Path(override)] if override else []
    if windir:
        candidates += [Path(windir) / "Fonts" / ("msyhbd.ttc" if bold else "msyh.ttc")]
    candidates += [
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/System/Library/Fonts/PingFang.ttc"),
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise RuntimeError("CJK font required; set FISHBONE_FONT and FISHBONE_BOLD_FONT")


FONT, BOLD = choose_font(), choose_font(True)


class Figure:
    def __init__(self, title, description):
        self.image = Image.new("RGB", (W, H), BG)
        self.draw = ImageDraw.Draw(self.image)
        self.parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img">',
                      f'<title>{html.escape(title)}</title><desc>{html.escape(description)}</desc>',
                      f'<rect width="{W}" height="{H}" fill="{BG}"/>']
        self.text_boxes = []

    def text(self, x, y, value, size=27, color=INK, bold=False, max_width=None, center=False):
        font = ImageFont.truetype(str(BOLD if bold else FONT), size)
        width = self.draw.textlength(value, font=font)
        if max_width is not None and width > max_width:
            raise ValueError(f"Text too wide ({width:.1f}>{max_width}): {value}")
        if center:
            x -= width / 2
        bbox = self.draw.textbbox((x, y), value, font=font, anchor="lt")
        if not (0 <= bbox[0] <= bbox[2] <= W and 0 <= bbox[1] <= bbox[3] <= H):
            raise ValueError(f"Out of figure: {value} {bbox}")
        self.text_boxes.append((value, bbox))
        self.draw.text((x, y), value, font=font, fill=color, anchor="lt")
        self.parts.append(f'<text x="{x:.2f}" y="{y:.2f}" dominant-baseline="text-before-edge" font-family="Microsoft YaHei, Noto Sans CJK SC, PingFang SC, sans-serif" font-size="{size}" font-weight="{600 if bold else 400}" fill="{color}">{html.escape(value)}</text>')

    def line(self, points, color=LINE, width=2):
        self.draw.line(points, fill=color, width=width)
        coords = " ".join(f"{x},{y}" for x, y in points)
        self.parts.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="{width}"/>')

    def circle(self, x, y, radius, color):
        self.draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=color)
        self.parts.append(f'<circle cx="{x}" cy="{y}" r="{radius}" fill="{color}"/>')

    def polygon(self, points, color):
        self.draw.polygon(points, fill=color)
        coords = " ".join(f"{x},{y}" for x, y in points)
        self.parts.append(f'<polygon points="{coords}" fill="{color}"/>')

    def save(self, stem):
        # Text collisions would make a fishbone unreviewable; fail the build instead.
        for i, (label, box) in enumerate(self.text_boxes):
            for other, ob in self.text_boxes[i+1:]:
                if min(box[2], ob[2]) > max(box[0], ob[0]) and min(box[3], ob[3]) > max(box[1], ob[1]):
                    raise ValueError(f"Text overlap: {label} / {other}")
        svg = "\n".join(self.parts + ["</svg>"])
        ET.fromstring(svg)
        (FIGURES / f"{stem}.svg").write_text(svg, encoding="utf-8")
        self.image.save(FIGURES / f"{stem}.png", optimize=True)


def draw_fishbone(module, number):
    fig = Figure(module["name"], module["flow"] + "；各支骨列出功能和责任角色，详细输入输出见配套说明。")
    fig.text(48, 35, f'{number:02d}  {module["name"]}', 43, bold=True, max_width=1240)
    fig.text(1390, 48, "设计评审 · V2", 23, MUTED, max_width=250)
    caption = "业务分解鱼骨图 · 按编号读取推荐流程；支骨列功能，角色对应表见说明"
    if module["code"] == "T":
        caption = "业务分解鱼骨图 · 两条路径并行：T1–T4 事件处置；T5–T6 定期评价"
    fig.text(48, 105, caption, 25, MUTED, max_width=1570)
    # A true fishbone silhouette: six numbered joins, alternating angled ribs,
    # and branch function lists; these are suggested stages, not a serial lock.
    axis = 505
    if module["code"] == "T":
        fig.line([(48, axis), (916, axis)], PURPLE, 3)
        fig.polygon([(928, axis), (908, axis-10), (908, axis+10)], PURPLE)
        fig.text(957, axis-14, "并行", 22, MUTED, center=True)
        fig.line([(991, axis), (1455, axis)], PURPLE, 3)
    else:
        fig.line([(48, axis), (1455, axis)], PURPLE, 3)
    fig.polygon([(1467, axis), (1447, axis-10), (1447, axis+10)], PURPLE)
    fig.text(1480, 421, "模块交付", 24, MUTED, max_width=175)
    fig.text(1480, 464, module["head"][0], 29, bold=True, max_width=175)
    fig.text(1480, 508, module["head"][1], 29, bold=True, max_width=175)
    for idx, stage in enumerate(module["stages"]):
        top = idx % 2 == 0
        col = 48 + 404 * (idx // 2) + (0 if top else 202)
        node_x = col + 200
        start_y = 409 if top else 622
        fig.line([(col+60, start_y), (node_x, axis)], LINE, 2)
        # Small ribs reinforce functional decomposition without running through text.
        for frac in (0.28, 0.58):
            px = col + 60 + frac * 140
            py = start_y + frac * (axis-start_y)
            fig.line([(px-30, py), (px, py)], LINE, 2)
        fig.circle(node_x, axis, 24, PURPLE)
        fig.text(node_x, axis-16, str(idx+1), 27, BG, bold=True, center=True)
        title_y = 160 if top else 655
        fig.text(col, title_y, stage["id"] + "  " + stage["name"], 29, bold=True, max_width=376)
        fig.text(col, title_y+45, stage["label"], 24, PURPLE, max_width=376)
        for n, feature in enumerate(stage["features"]):
            y = title_y+91+39*n
            fig.circle(col+5, y+13, 3, MUTED)
            fig.text(col+19, y, feature, 27, max_width=357)
    fig.line([(48, 955), (1632, 955)], LINE, 1)
    fig.text(48, 976, module["gate_note"], 24, MUTED, max_width=1584)
    fig.text(48, 1015, module["loop_note"], 24, MUTED, max_width=1584)
    fig.save(f'{number:02d}-{module["id"]}')


def cell(value):
    return str(value).replace("|", "／").replace("\n", "<br>")


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"] +
                     ["| " + " | ".join(cell(item) for item in row) + " |" for row in rows])


def write_doc(design, public):
    modules, roles = design["modules"], design["roles"]
    text = [f'# {design["title"]}', "", f'{design["version"]}。**{design["status"]}。**', "",
            '适用范围：本聊天维护的机构量化流程方案版。价值投资属于同事独立产品；本稿不修改另一聊天的自主研究版。', "",
            '## 阅读方法与设计边界', "",
            '这里采用“业务分解鱼骨图”：主骨按编号呈现推荐进展，支骨展开功能和责任角色，鱼头表示模块交付。它用于产品与工程拆解，不是因果诊断图，也不表示全公司只能串行工作。每张图附有输入、人工工具、AI职责、输出和检查条件。', "",
            '- 五个核心业务模块、30个业务步骤；另附三个公共入口的分解，避免遗漏管理能力。',
            '- 建议18类逻辑职责：16类模块职责、2类共享研究验证/评审职责。它们不是18个必需进程、18个模型或18个人类岗位；需要隔离权限或验证数据的职责必须有实际隔离。',
            '- 每个业务工具先具备可操作、可测试的输入输出；人和Agent调用同一服务。表单是工具参数的呈现，Agent通过工具接口工作，不靠模拟鼠标填写网页。',
            '- 数值计算、权限检查、状态机、定时任务、硬风控由确定性程序执行；Agent承担理解、计划、工具选择、诊断、解释和有限迭代。',
            '- 流程允许复用、并行和返工，合法的准入/资金/风险关口不能通过跳转页面绕过。',
            '- 本稿的工具均为所需能力目录；是否已接SVQuant API、是否已真实验证，须后续逐项核对，不能把设计表当作已实现接口。', "",
            '## 一、整体模块和责任分配', "",
            table(["模块", "主要职责", "模块角色", "共享协作", "主要交付"], [
                [m["name"], m["purpose"], "、".join(f'{rid} {roles[rid]["short"]}' for rid in m["roles"] if rid.startswith(m["code"] + "-")),
                 "、".join(f'{rid} {roles[rid]["short"]}' for rid in m["roles"] if not rid.startswith(m["code"] + "-")) or "—", m["output"]] for m in modules]), "",
            '数据版本、因子库、策略库是共享资产。策略研究可直接使用存量因子或数据/模型，组合可直接使用存量策略；不等待上游本轮产出。不要求所有策略都通过新因子挖掘起步。', "",
            '因子描述可计算的特征，信号是策略使用这些特征或模型作出的预测/排序/触发判断，策略还要定义信号如何变成持仓和交易规则；组合则进一步在策略与账户之间分配资金。', ""]

    for num, m in enumerate(modules + public, 1):
        kind = "核心业务模块" if num <= 5 else "公共管理入口"
        text += [f'## {num+1}、{m["name"]}（{kind}）', "", m["purpose"], "",
                 f'![{m["name"]}鱼骨图](figures/{num:02d}-{m["id"]}.png)', "",
                 f'[可编辑矢量图](figures/{num:02d}-{m["id"]}.svg)', "",
                 f'**推荐流程：** {m["flow"]}', "", f'**输入：** {m["input"]}', "",
                 f'**交付：** {m["output"]}', "", f'**任务入口：** {m["entry"]}', "",
                 f'**回退与循环：** {m["feedback"]}', "", '### 流程、功能、Agent与交付', ""]
        if num <= 5:
            text += [table(["步骤", "输入", "人工功能与工具", "Agent角色及工作", "输出", "检查／人工介入"], [
                [s["id"]+" "+s["name"], s["input"], s["manual"], "、".join(s["roles"])+"："+s["ai"], s["output"], s["check"]] for s in m["stages"]]), ""]
        else:
            text += [table(["步骤", "功能", "承担者／AI工作", "输出"], [
                [s["id"]+" "+s["name"], s["manual"], s["label"]+"："+s["ai"], s["output"]] for s in m["stages"]]), ""]
        text += ['### 角色与步骤对应', "", table(["角色", "本模块覆盖步骤", "职责"], [
            [f'{rid} {roles[rid]["name"]}', "、".join(s["id"] for s in m["stages"] if rid in s["roles"]) or "提供已有独立证据，不重复生成", roles[rid]["mission"]] for rid in m["roles"]]), "",
            m["gate_note"], "", m["loop_note"], ""]

    text += ['## 十、Agent职责卡：工具、交付、权限与评测', "",
             '这些职责可分别维护Prompt、Skill、知识和评测集，但不要为每个按钮再增加一个Agent。一个研究Agent可以覆盖多个步骤；单次任务也可以调用共享的独立验证角色。', ""]
    for rid, r in roles.items():
        coverage = []
        for m in modules:
            coverage += [s["id"] for s in m["stages"] if rid in s["roles"]]
        text += [f'### {rid} · {r["name"]}', "", table(["项目", "设计"], [
            ["对应业务步骤", "、".join(coverage)], ["核心任务", r["mission"]], ["工具能力", r["tools"]],
            ["交付物", r["output"]], ["权限边界", r["boundary"]], ["评测关注", r["evaluation"]]]), ""]
    text += ['## 十一、人工、规则与Agent如何协作', "",
             table(["事项", "默认处理", "何时需要人工"], [
                 ["保存定义、计算、普通实验留档", "程序自动保存，Agent可按授权执行", "主动研究、纠错或异常处理时介入，不逐条签字"],
                 ["差候选、重复候选、证据不全", "硬条件拦截；AI整理理由、去重或提出补证", "有争议或需要修改政策时介入，不为凑产出降低门槛"],
                 ["正式因子/策略准入", "冻结证据＋独立验证＋候选评审后送审", "按用途与权限决定正式准入；研究留档与准入分开"],
                 ["资金、账户与重大方案变更", "独立风险检查＋授权匹配＋方案流转", "有权限的人批准资金方案，批准绑定准确版本"],
                 ["已获批策略的例行运行", "预授权规则内自动执行和监测", "超范围、异常或风险升级时介入，无需逐条信号签字"],
                 ["硬风险触发", "规则服务按预授权立即阻断或限制，并通知人员", "负责处置、复核与必要的恢复决定；不等待模型给意见"],
                 ["Agent方法与工具更新", "草案、离线评测、版本比较、受控发布", "业务人员审核知识/方法；平台团队管理工具、权限、发布与回滚"]]), "",
             '默认允许实验和草案资产被后续探索复用，但保留来源、验证状态和用途限制。正式部署不得把“研究可用”自动升级为“获准配置资金”。因子对某个具体策略是否有价值，仍由策略实验验证，不能用单因子门槛作普适结论。', "",
             '## 十二、持续运行与Agent实况', "",
             '人工一次性设定研究范围、预算、运行计划和筛选政策后，系统可由定时计划、新数据发布、资产变更或风险反馈持续触发任务，不必每次手填研究目标。调度服务负责触发、队列、依赖、并发、预算和停机；Agent在任务权限与预算内选择工具、补证、迭代、结束或报告等待。', "",
             '没有可用数据、缺少授权、预算不足、任务重复或没有值得推进的候选时，应显示明确原因，不用重复调用模型假装忙碌。一个候选等人工审查不应锁住全部研究。', "",
             '每个步骤页面采用同一个工作对象：输入/参数与工具、产物与报告、Agent运行实况。人可以手动执行、委托本步骤、委托一段任务、取消并接续；中途改输入需要新版本或明确确认，不能覆盖正在执行的快照。', "",
             '运行实况展示：目标与输入版本；简短执行计划与当前动作；实际工具参数、起止时间、状态与返回值；错误、重试与改动依据；可点击的产物与证据；用量、等待原因与人工介入记录。展示的是实际事件与可解释摘要，不伪造进度，也不要求披露模型私有推理。', "",
             '## 十三、独立验证与第一轮开发边界', "",
             '独立验证不是换一个提示词再评论一遍。需要冻结候选及输入、独立工具权限、受控验证数据、明确的预设标准和完整尝试记录。研究方不能用验证结果无限调参；重复查询须有额度、反馈粒度和版本政策。统计、回测与硬条件由工具给出，Agent组织检查并解释证据。', "",
             '工具优先复用已经核对的SVQuant、ResearchEngine和数据服务接口。不存在的能力要单独开发；完整数据采集维护、封存验证、持续调度、模拟/实盘执行不能只画按钮或用大模型回复冒充实现。', "",
             '本轮只交付设计与图，没有修改应用、重启服务、触发研究、调用付费模型或交易。当前可复用能力依据既有验收包括部分数据查询、表达式与因子检验、策略回测、组合研究、实验档案与送审；本稿扩展能力仍需逐项接线、测试和验收。', "",
             '建议下一步先确认因子工厂F1—F6的业务边界，再把每步细化成页面字段、工具输入输出、Agent提示/Skill、权限和验收用例；不要先一次性重做全平台页面。', "",
             '与2026-11-03旧角色文档的关系：这是在新确认的五模块范围上形成的V2目标设计。组合模块补足执行，对P-A2/P-A3职责重新划分，组合独立风险复用T-A3；任务协调与方法管理先由公共服务/人员承担，未强设U类Agent。旧文档保留，角色编号是设计编号，不直接替换现有接口。', "",
             '## 文件与复现', "",
             '- `design.json`：五模块、30步骤、18类角色的编辑源。',
             '- `public.json`：三个公共入口及18个支撑步骤。',
             '- `figures/`：八张PNG预览及对应可编辑SVG。',
             '- `build.py`：离线生成与结构/版面检查；使用相对路径，不读取密钥或业务数据库。',
             '- `验证记录.md`：本轮图文检查与范围记录。', "",
             '修改JSON后运行同目录的`build.py`重新生成。需要Python、Pillow和中文字体；可通过FISHBONE_FONT/FISHBONE_BOLD_FONT指定字体。', ""]
    (ROOT / "业务模块鱼骨图与Agent设计.md").write_text("\n".join(text), encoding="utf-8")


def main():
    design = json.loads((ROOT / "design.json").read_text(encoding="utf-8"))
    public = json.loads((ROOT / "public.json").read_text(encoding="utf-8"))
    modules, roles = design["modules"], design["roles"]
    assert len(modules) == 5 and len(public) == 3 and len(roles) == 18
    all_steps = [s for m in modules+public for s in m["stages"]]
    assert len({s["id"] for s in all_steps}) == len(all_steps) == 48
    assert all(len(m["stages"]) == 6 for m in modules+public)
    used = set()
    for m in modules+public:
        assert set(m["roles"]) <= set(roles)
        for s in m["stages"]:
            assert len(s["features"]) == 4
            assert set(s["roles"]) <= set(roles)
            used.update(s["roles"])
            if m in modules:
                assert all(s.get(k) for k in ("input", "manual", "ai", "output", "check"))
    assert used == set(roles)
    FIGURES.mkdir(exist_ok=True)
    for num, module in enumerate(modules+public, 1):
        draw_fishbone(module, num)
    write_doc(design, public)
    images = list(FIGURES.glob("*.png"))
    assert len(images) == 8
    for image in images:
        with Image.open(image) as im:
            assert im.size == (W, H)
    outputs = sorted([ROOT / "业务模块鱼骨图与Agent设计.md", *FIGURES.glob("*.png"), *FIGURES.glob("*.svg")])
    manifest = {str(p.relative_to(ROOT)).replace(os.sep, "/"): hashlib.sha256(p.read_bytes()).hexdigest() for p in outputs}
    (ROOT / "outputs.sha256.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"business_modules":5,"business_steps":30,"public_entries":3,"support_steps":18,"roles":18,"figures":8,"checks":"all roles mapped; required step fields; SVG XML; text width/bounds/collisions; PNG dimensions"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
