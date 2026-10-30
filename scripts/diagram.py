"""Draws a Haiko app as one draw.io file, a tab per diagram.

    python scripts/diagram.py --app workspace/<app> --out workspace/<app>/<app>.drawio
    python scripts/diagram.py --snapshot <snapshot.json> [--metadata workspace/<app>/metadata] --out app.drawio

--app reads app-definition.json and security-manifest.json (studio.py pull writes them)
and, if it's there, the CRM metadata crm.py saved in metadata/. --snapshot reads a
Studio snapshot export. Open the result in draw.io desktop, diagrams.net or VS Code's
draw.io extension. Offline and deterministic: the same app always draws the same file.
"""

import argparse
import html
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

FONT = "fontFamily=Helvetica;"
STYLES = {
    "title": "text;html=1;fontSize=22;fontStyle=1;align=left;verticalAlign=top;" + FONT,
    "note": "text;html=1;fontSize=12;align=left;verticalAlign=top;whiteSpace=wrap;fontColor=#475569;" + FONT,
    "box": "rounded=1;whiteSpace=wrap;html=1;arcSize=8;fillColor=#FFFFFF;strokeColor=#94A3B8;align=left;verticalAlign=top;spacing=10;fontSize=12;" + FONT,
    "nav": "rounded=1;whiteSpace=wrap;html=1;arcSize=30;fillColor=#1E3A5F;strokeColor=#1E3A5F;fontColor=#FFFFFF;fontSize=13;fontStyle=1;" + FONT,
    "screen": "rounded=1;whiteSpace=wrap;html=1;arcSize=6;fillColor=#EFF6FF;strokeColor=#3B82F6;align=left;verticalAlign=top;spacing=10;fontSize=12;" + FONT,
    "plugin": "rounded=1;whiteSpace=wrap;html=1;arcSize=6;fillColor=#F5F3FF;strokeColor=#7C3AED;dashed=1;align=left;verticalAlign=top;spacing=10;fontSize=12;" + FONT,
    "workflow": "rounded=1;whiteSpace=wrap;html=1;arcSize=6;fillColor=#ECFDF5;strokeColor=#059669;align=left;verticalAlign=top;spacing=10;fontSize=12;" + FONT,
    "endpoint": "shape=hexagon;perimeter=hexagonPerimeter2;size=0.06;whiteSpace=wrap;html=1;fillColor=#FFF7ED;strokeColor=#EA580C;align=left;verticalAlign=top;spacing=12;spacingLeft=30;spacingRight=24;fontSize=12;" + FONT,
    "entity": "shape=cylinder3;boundedLbl=1;size=10;whiteSpace=wrap;html=1;fillColor=#F1F5F9;strokeColor=#334155;align=left;verticalAlign=top;spacing=10;fontSize=12;" + FONT,
    "action": "shape=process;whiteSpace=wrap;html=1;size=0.06;fillColor=#FEF3C7;strokeColor=#B45309;align=left;verticalAlign=top;spacing=12;fontSize=12;" + FONT,
    "automation": "rounded=0;whiteSpace=wrap;html=1;fillColor=#FDF2F8;strokeColor=#BE185D;align=left;verticalAlign=top;spacing=10;fontSize=12;" + FONT,
    "api": "rounded=1;whiteSpace=wrap;html=1;arcSize=4;fillColor=#F8FAFC;strokeColor=#1E3A5F;strokeWidth=2;dashed=1;verticalAlign=top;align=left;spacing=12;fontSize=14;fontStyle=1;fontColor=#1E3A5F;" + FONT,
    "stage_none": "rounded=1;whiteSpace=wrap;html=1;arcSize=6;fillColor=#F8FAFC;strokeColor=#94A3B8;align=left;verticalAlign=top;spacing=10;fontSize=12;" + FONT,
    "stage_waiting": "rounded=1;whiteSpace=wrap;html=1;arcSize=6;fillColor=#EFF6FF;strokeColor=#2563EB;align=left;verticalAlign=top;spacing=10;fontSize=12;" + FONT,
    "stage_action_required": "rounded=1;whiteSpace=wrap;html=1;arcSize=6;fillColor=#FFFBEB;strokeColor=#D97706;strokeWidth=2;align=left;verticalAlign=top;spacing=10;fontSize=12;" + FONT,
    "stage_terminal": "rounded=1;whiteSpace=wrap;html=1;arcSize=6;fillColor=#FEF2F2;strokeColor=#DC2626;dashed=1;align=left;verticalAlign=top;spacing=10;fontSize=12;" + FONT,
    "start": "ellipse;whiteSpace=wrap;html=1;fillColor=#1E3A5F;strokeColor=none;fontColor=#FFFFFF;fontSize=11;" + FONT,
    "edge": "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=block;endFill=1;strokeColor=#475569;fontSize=11;labelBackgroundColor=#FFFFFF;" + FONT,
    "edge_dashed": "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=block;endFill=1;dashed=1;strokeColor=#94A3B8;fontSize=11;labelBackgroundColor=#FFFFFF;" + FONT,
    "edge_read": "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=open;dashed=1;dashPattern=1 3;strokeColor=#3B82F6;fontSize=11;labelBackgroundColor=#FFFFFF;" + FONT,
    "edge_crm": "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=block;endFill=1;strokeColor=#BE185D;fontSize=11;labelBackgroundColor=#FFFFFF;" + FONT,
}


def esc(text) -> str:
    return html.escape(str(text), quote=False)


def card(heading: str, *lines: str, sub: str = "") -> str:
    """A box label: bold heading, optional grey subheading, then lines (already escaped HTML)."""
    out = f"<b>{esc(heading)}</b>"
    if sub:
        out += f"<br><span style='color:#64748B;font-size:11px'>{esc(sub)}</span>"
    for line in lines:
        if line:
            out += f"<br>{line}"
    return out


def code(text) -> str:
    return f"<span style='font-family:Menlo,monospace;font-size:11px'>{esc(text)}</span>"


class Page:
    def __init__(self, name: str):
        self.name, self.cells, self.ids = name, [], set()

    def _id(self, key: str) -> str:
        cid = "".join(c if c.isalnum() or c in "_-" else "_" for c in key)
        while cid in self.ids:
            cid += "_"
        self.ids.add(cid)
        return cid

    @staticmethod
    def style(name: str) -> str:
        """A named style, optionally with overrides: "box;align=center"."""
        base, _, extra = name.partition(";")
        return STYLES[base] + extra if base in STYLES else name

    def box(self, key: str, label: str, x, y, w, h, style: str) -> str:
        cid = self._id(key)
        self.cells.append(("v", cid, label, self.style(style), (x, y, w, h)))
        return cid

    def edge(self, source: str, target: str, label: str = "", style: str = "edge", points=(), label_at: float | None = None) -> str:
        """points: waypoints the arrow must pass through, for routing it round boxes.
        label_at: where the label sits along the arrow, -1 (source) to 1 (target)."""
        cid = self._id(f"e_{source}_{target}")
        self.cells.append(("e", cid, label, self.style(style), (source, target, tuple(points), label_at)))
        return cid

    def xml(self, index: int) -> ET.Element:
        d = ET.Element("diagram", id=f"page{index}", name=self.name)
        model = ET.SubElement(d, "mxGraphModel", dx="1400", dy="900", grid="1", gridSize="10", guides="1", tooltips="1",
                              connect="1", arrows="1", fold="1", page="0", pageScale="1", math="0", shadow="0")
        root = ET.SubElement(model, "root")
        ET.SubElement(root, "mxCell", id="0")
        ET.SubElement(root, "mxCell", id="1", parent="0")
        for kind, cid, label, style, geo in self.cells:
            if kind == "v":
                c = ET.SubElement(root, "mxCell", id=cid, value=label, style=style, vertex="1", parent="1")
                x, y, w, h = geo
                ET.SubElement(c, "mxGeometry", x=str(x), y=str(y), width=str(w), height=str(h), **{"as": "geometry"})
            else:
                c = ET.SubElement(root, "mxCell", id=cid, value=label, style=style, edge="1", parent="1", source=geo[0], target=geo[1])
                g = ET.SubElement(c, "mxGeometry", relative="1", **({"x": str(geo[3])} if geo[3] is not None else {}), **{"as": "geometry"})
                if geo[2]:
                    arr = ET.SubElement(g, "Array", **{"as": "points"})
                    for px, py in geo[2]:
                        ET.SubElement(arr, "mxPoint", x=str(px), y=str(py))
        return d


def write(pages: list[Page], out: Path):
    mxfile = ET.Element("mxfile", host="haiko-dev-kit", agent="Haiko Dev Kit diagram.py", version="24.0.0", type="device")
    for i, p in enumerate(pages):
        mxfile.append(p.xml(i))
    ET.indent(mxfile)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(ET.tostring(mxfile, encoding="unicode") + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Reading the app
# ---------------------------------------------------------------------------

class App:
    def __init__(self, definition: dict, manifest: dict | None, metadata: Path | None):
        self.d, self.m = definition, manifest or {"entities": {}, "endpoints": []}
        self.metadata = metadata if metadata and metadata.is_dir() else None
        self.screens = {s["id"]: s for s in definition.get("screens", [])}
        self.endpoints = {e["id"]: e for e in definition.get("endpoints", [])}
        self.workflows = {w["id"]: w for w in definition.get("workflows", [])}
        self.manifest_eps = {e["id"]: e for e in self.m.get("endpoints", [])}

    def journeys(self):
        return [(s, s["journey"]) for s in self.screens.values() if s.get("journey")]

    def meta(self, name: str):
        if not self.metadata:
            return None
        p = self.metadata / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def load(args) -> App:
    if args.snapshot:
        snap = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
        return App(snap["definition"], snap.get("securityManifest"), Path(args.metadata) if args.metadata else None)
    app = Path(args.app)
    d = json.loads((app / "app-definition.json").read_text(encoding="utf-8"))
    m = app / "security-manifest.json"
    meta = Path(args.metadata) if args.metadata else app / "metadata"
    return App(d.get("definition", d), json.loads(m.read_text(encoding="utf-8")) if m.exists() else None, meta)


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

def overview(app: App, tabs: list[str]) -> Page:
    p = Page("Overview")
    d = app.d
    p.box("title", esc(d.get("name", d.get("id", "Haiko app"))), 40, 30, 900, 40, "title")
    sources = ["the app's definition"] + (["its security manifest"] if app.m.get("entities") else []) + (["CRM metadata"] if app.metadata else [])
    sources = ", ".join(sources[:-1]) + " and " + sources[-1] if len(sources) > 1 else sources[0]
    p.box("sub", esc(f"App id {d.get('id')} · drawn by the Haiko Dev Kit from {sources}"), 40, 72, 900, 24, "note")
    entities = sorted({s.get("entity") for s in app.screens.values() if s.get("entity")} | set(app.m.get("entities", {})))
    counts = [("Screens", len(app.screens)), ("Journeys", len(app.journeys())), ("Multi-step forms", len(app.workflows)),
              ("Endpoints", len(app.endpoints)), ("Entities", len(entities)), ("Plugins", len(d.get("plugins", [])))]
    for i, (label, n) in enumerate(counts):
        p.box(f"count_{label}", f"<b style='font-size:26px'>{n}</b><br>{esc(label)}", 40 + i * 150, 120, 130, 80,
              "box;align=center;verticalAlign=middle")
    p.box("tabs", card("In this file", *[f"• {esc(t)}" for t in tabs]), 40, 230, 430, 40 + 20 * len(tabs), "box")
    p.box("entities", card("CRM entities", *[code(e) for e in entities]), 500, 230, 280, 70 + 18 * max(1, len(entities)), "entity")
    return p


def lines_for(text: str, width_chars: int = 52) -> int:
    return max(1, -(-len(text) // width_chars))


def predicate_fields(expr: str) -> set[str]:
    import re
    expr = re.sub(r'"[^"]*"', '""', expr or "")
    words = {"isEmpty", "hasValue", "isTrue", "isFalse", "contains", "isPast", "isFuture", "AND", "OR", "NOT", "true", "false", "null"}
    return {m.group(1) for m in re.finditer(r"\b([A-Za-z_]\w*)(?:\.\w+)?\b", expr) if m.group(1) not in words}


def box_height(lines: list[str], width_chars: int = 62) -> int:
    """Room for a card's heading, subheading and lines, wrapped at about width_chars."""
    import re
    plain = [html.unescape(re.sub(r"<[^>]+>", "", line)) for line in lines]
    return 50 + 17 * sum(lines_for(t, width_chars) for t in plain) + 10


CONTACT_ACTION = {"none": "Nothing to do", "waiting": "Waiting on the organisation", "action_required": "The contact needs to act"}
NEVER = {"isEmpty(createdon)"}


def journey_pages(app: App) -> list[Page]:
    pages = []
    for screen, j in app.journeys():
        p = Page(f"Journey - {j.get('name', screen['id'])}")
        p.box("title", esc(f"Journey: {j.get('name', screen['id'])}"), 40, 30, 900, 36, "title")
        p.box("sub", esc(f"On the {screen.get('name', screen['id'])} screen ({screen['id']}), for {j.get('entity', screen.get('entity'))} records. "
                         f"Default message: \u201c{j.get('defaultMessage', '')}\u201d"), 40, 68, 900, 24, "note")
        stages = sorted(j.get("stages", []), key=lambda st: (st.get("order", 0), st.get("id", "")))
        terminal = [st for st in stages if st.get("pathRole") == "terminal"]
        main_line = [st for st in stages if st.get("pathRole") != "terminal"]
        fields = set()
        width = 460
        prev = p.box("start", "Created", 40 + width // 2 - 40, 110, 80, 36, "start")
        y = 170
        for st in main_line:
            fields |= predicate_fields(st.get("activeWhen")) | predicate_fields(st.get("completeWhen")) | predicate_fields(st.get("appliesWhen"))
            act = st.get("contactAction") or j.get("defaultContactAction") or "none"
            body = ["<span style='color:#64748B'>Never current: shown as done once created</span>" if st.get("activeWhen") in NEVER
                    else f"Current when {code(st.get('activeWhen', ''))}"]
            if st.get("completeWhen") and st.get("completeWhen") not in NEVER:
                body.append(f"Done when {code(st['completeWhen'])}")
            if st.get("appliesWhen"):
                body.append(f"Only when {code(st['appliesWhen'])}")
            if st.get("message"):
                body.append(f"<i>\u201c{esc(st['message'])}\u201d</i>")
            shown = [f for f in st.get("showFields", [])]
            if shown:
                ro = set(st.get("readOnlyFields") or [])
                body.append("Shows " + ", ".join(code(f) + ("" if f in ro else " (editable)") for f in shown))
            h = box_height(body)
            cid = p.box(f"stage_{st.get('id')}", card(f"{st.get('order', '')}. {st.get('label', st.get('id'))}", *body, sub=CONTACT_ACTION.get(act, act)),
                        40, y, width, h, f"stage_{act}" if f"stage_{act}" in STYLES else "stage_none")
            p.edge(prev, cid)
            a_ = st.get("action")
            if a_:
                where = a_.get("screenId") or a_.get("endpointId") or a_.get("workflowId") or a_.get("formScreenId") or ""
                kind = "endpoint" if a_.get("endpointId") else "screen"
                lines = [f"{esc(a_.get('type', ''))} \u2192 {code(where)}"] + ([f"<i>{esc(a_['confirmMessage'])}</i>"] if a_.get("confirmMessage") else [])
                bid = p.box(f"button_{st.get('id')}", card(f"\u201c{a_.get('label', '')}\u201d button", *lines), width + 100, y + 10, 300,
                            box_height(lines, 38) - 10, kind)
                p.edge(cid, bid, "", "edge_dashed")
            prev, y = cid, y + h + 50
        p.box("end", "Done", 40 + width // 2 - 40, y - 10, 80, 36, "start")
        p.edge(prev, f"end")
        ty = 170
        if terminal:
            p.box("ways_out", card("Ways out", "<span style='color:#64748B'>can happen at any stage</span>"), width + 100 + 340, 120, 300, 46, "note")
        for st in terminal:
            fields |= predicate_fields(st.get("activeWhen"))
            body = [f"When {code(st.get('activeWhen', ''))}"] + ([f"<i>\u201c{esc(st['message'])}\u201d</i>"] if st.get("message") else [])
            h = box_height(body, 40)
            p.box(f"out_{st.get('id')}", card(st.get("label", st.get("id")), *body, sub="Ends the journey"), width + 100 + 340, ty, 300, h, "stage_terminal")
            ty += h + 30
        legend = [("stage_action_required", "The contact needs to act"), ("stage_waiting", "Waiting on the organisation"),
                  ("stage_none", "Nothing to do"), ("stage_terminal", "A way out")]
        lx = width + 100 + 340 + 340
        for i, (style, label) in enumerate(legend):
            p.box(f"legend_{i}", esc(label), lx, 120 + i * 44, 200, 34, f"{style};align=center;verticalAlign=middle;spacing=2")
        fields.discard("")
        p.box("fields", card("CRM fields it depends on", *[code(f) for f in sorted(fields)]), lx, 120 + 4 * 44 + 20, 200, 50 + 17 * len(fields), "entity")
        pages.append(p)
    return pages


STEP_TYPE = {"form": "Form", "confirmation": "Check and confirm", "summary": "Summary", "info": "Information", "plugin": "Plugin step"}


def policy_line(app: App, entity: str) -> str:
    pol = app.m.get("entities", {}).get(entity)
    if not pol:
        return "<span style='color:#B91C1C'>no security policy: the API will refuse it</span>"
    owner = f"linked by {code(pol['customerField'])}" if pol.get("customerField") else "no contact link"
    return f"read {esc(pol.get('read'))} ({owner}) · create {'yes' if pol.get('create') else 'no'} · update {esc(pol.get('update'))}"


def wizard_pages(app: App) -> list[Page]:
    pages = []
    for w in app.workflows.values():
        p = Page(f"Wizard - {w.get('name', w['id'])}")
        p.box("title", esc(f"Multi-step form: {w.get('name', w['id'])}"), 40, 30, 900, 36, "title")
        p.box("sub", esc(f"Workflow {w['id']}, creating a {w.get('entity', '?')} record"), 40, 68, 900, 24, "note")
        steps = sorted(w.get("steps", []), key=lambda st: (st.get("order", 0), st.get("id", "")))
        ids, y, width = {}, 170, 460
        prev = p.box("start", "Start", 40 + width // 2 - 40, 110, 80, 36, "start")
        for st in steps:
            lines = []
            screen = app.screens.get(st.get("formScreenId", ""))
            if screen:
                lines.append(f"Screen {code(screen['id'])}")
                for f in sorted(screen.get("fields", []), key=lambda f: f.get("order", 0)):
                    if f.get("showOnCreate", True):
                        lines.append(f"\u2022 {esc(f.get('label', f.get('name')))} {code(f.get('name'))}" + (" <b>*</b>" if f.get("required") else "")
                                     + ("" if f.get("crmField", True) else " <span style='color:#64748B'>(screen only)</span>"))
            if st.get("plugin"):
                lines.append(f"Plugin {code(st['plugin'].get('pluginId'))} \u2192 {code(st['plugin'].get('export'))}")
            if st.get("content"):
                lines.append(f"<i>{esc(st['content'])}</i>")
            if st.get("skipCondition"):
                lines.append(f"Skipped when {code(st['skipCondition'])}")
            if st.get("completionRule"):
                lines.append(f"Done when {code(st['completionRule'])}")
            style = "workflow" if st.get("type") == "form" else ("plugin" if st.get("type") == "plugin" else "box")
            cid = p.box(f"step_{st.get('id')}", card(f"{st.get('order', '')}. {st.get('label', st.get('id'))}", *lines,
                                                     sub=STEP_TYPE.get(st.get("type"), st.get("type", ""))), 40, y, width, box_height(lines), style)
            ids[st.get("id")] = cid
            y += box_height(lines) + 50
        nav = w.get("navigation") or []
        if nav:
            for n in nav:
                a_, b_ = ids.get(n.get("fromStepId")), ids.get(n.get("toStepId"))
                if a_ and b_:
                    label = esc(n.get("navigationType", "")) + (f": {code(n['condition'])}" if n.get("condition") else "")
                    p.edge(a_, b_, label, "edge" if n.get("navigationType") in (None, "next") else "edge_dashed")
            if steps:
                p.edge(prev, ids[steps[0].get("id")])
        else:
            for st in steps:
                p.edge(prev, ids[st.get("id")])
                prev = ids[st.get("id")]
        last = ids[steps[-1].get("id")] if steps else prev
        ep = app.endpoints.get(w.get("submitEndpointId", ""))
        if ep:
            mep = app.manifest_eps.get(ep["id"], {})
            writable = mep.get("writableFields")
            lines = [f"{esc(ep.get('type'))} \u2192 {code(ep.get('uri') or mep.get('entity') or '')}"]
            if writable is not None:
                lines.append("May write " + (", ".join(code(f) for f in writable) or "nothing"))
            elif ep["id"] not in app.manifest_eps:
                lines.append("<span style='color:#B91C1C'>not in the security manifest: the API will refuse it</span>")
            if ep.get("submitMessage"):
                lines.append(f"<i>\u201c{esc(ep['submitMessage'])}\u201d</i>")
            eid = p.box("submit", card(f"Submits through {ep['id']}", *lines, sub=f"the \u201c{ep.get('name', ep['id'])}\u201d button"), 40, y, width, box_height(lines, 56) + 10, "endpoint")
            p.edge(last, eid, "submit")
            entity = ep.get("uri") if ep.get("type") == "d365_direct" else mep.get("entity")
            if entity:
                tid = p.box("entity", card(entity, policy_line(app, entity), sub="CRM entity created"), width + 120, y, 340, 110, "entity")
                p.edge(eid, tid, "creates")
            y += box_height(lines, 56) + 60
        if w.get("completionMessage") or w.get("completionNavigateTo"):
            lines = ([f"<i>\u201c{esc(w['completionMessage'])}\u201d</i>"] if w.get("completionMessage") else []) + \
                    ([f"then opens {code(w['completionNavigateTo'])}"] if w.get("completionNavigateTo") else [])
            did = p.box("done", card("Done", *lines), 40, y, width, box_height(lines), "box")
            p.edge("submit" if ep else last, did)
        pages.append(p)
    return pages


SCREEN_KIND = {"list": "List", "record": "Record page", "form": "Form", "plugin": "Plugin screen", "rss-feed": "News feed", "webview": "Web page"}
SCREEN_ORDER = {"list": 0, "record": 1, "form": 2}


def navigation_page(app: App) -> list[Page]:
    """Navigation across the top; multi-step forms, then a column per entity, below. Arrows run in the gaps
    between columns: into a screen from its left, along the right for "+ new", straight down for "opens"."""
    p = Page("Screens and navigation")
    p.box("title", "Screens and navigation", 40, 30, 900, 36, "title")
    p.box("sub", esc("What the contact can reach from where. Columns group screens by the CRM entity they show."), 40, 68, 900, 24, "note")
    INTO_LEFT = "exitX=0.5;exitY=1;exitDx=0;exitDy=0;entryX=0;entryY=0.5;entryDx=0;entryDy=0;"
    ACROSS = "exitX=1;exitY=0.5;exitDx=0;exitDy=0;entryX=0;entryY=0.5;entryDx=0;entryDy=0;"
    DOWN = "exitX=0.5;exitY=1;exitDx=0;exitDy=0;entryX=0.5;entryY=0;entryDx=0;entryDy=0;"
    RIGHT_SIDE = "exitX=1;exitY=0.5;exitDx=0;exitDy=0;entryX=1;entryY=0.5;entryDx=0;entryDy=0;"
    ids, where = {}, {}  # where: id -> (x, y, h) of each screen, for routing
    top, col_w, gap = 260, 300, 120
    x = 40
    if app.workflows:
        p.box("col_workflows", "<b>Multi-step forms</b>", x, top - 60, col_w, 52, "note;fontColor=#0F172A")
        wy = top
        for w in app.workflows.values():
            lines = [code(w["id"]), f"{len(w.get('steps', []))} steps, creates {code(w.get('entity', '?'))}"]
            h = box_height(lines, 38)
            ids[f"wf:{w['id']}"] = p.box(f"w_{w['id']}", card(w.get("name", w["id"]), *lines, sub="Multi-step form"), x, wy, col_w, h, "workflow")
            where[ids[f"wf:{w['id']}"]] = (x, wy, h)
            wy += h + 40
        x += col_w + gap
    groups: dict[str, list] = {}
    for sc in app.screens.values():
        groups.setdefault(sc.get("entity") or "~other", []).append(sc)
    for entity in sorted(groups):
        title = "Other screens" if entity == "~other" else entity
        p.box(f"col_{entity}", f"<b>{esc(title)}</b>" + ("" if entity == "~other" else "<br>" + policy_line(app, entity)), x, top - 60, col_w, 52,
              "note;fontColor=#0F172A")
        y = top
        step_of = {st.get("formScreenId"): st.get("order", 0) for w in app.workflows.values() for st in w.get("steps", [])}
        for sc in sorted(groups[entity], key=lambda sc: (SCREEN_ORDER.get(sc.get("type"), 3), step_of.get(sc["id"], 99), sc.get("id"))):
            lines = [f"{code(sc['id'])}"]
            crm = [f for f in sc.get("fields", []) if f.get("crmField", True)]
            if crm:
                lines.append(f"{len(crm)} field(s)")
            if sc.get("journey"):
                lines.append(f"Journey: {esc(sc['journey'].get('name', ''))} ({len(sc['journey'].get('stages', []))} stages)")
            if sc.get("customerField"):
                lines.append(f"The contact's own, by {code(sc['customerField'])}")
            if sc.get("type") == "plugin" and sc.get("plugin"):
                lines.append(f"Plugin {code(sc['plugin'].get('pluginId'))}")
            if sc.get("feedUrl") or sc.get("url"):
                lines.append(esc(sc.get("feedUrl") or sc.get("url")))
            h = box_height(lines, 38)
            ids[sc["id"]] = p.box(f"s_{sc['id']}", card(sc.get("name", sc["id"]), *lines, sub=SCREEN_KIND.get(sc.get("type"), sc.get("type", ""))),
                                  x, y, col_w, h, "plugin" if sc.get("type") == "plugin" else "screen")
            where[ids[sc["id"]]] = (x, y, h)
            y += h + 50
        x += col_w + gap

    # Navigation across the top, the dashboard's plugin widgets after it.
    nx = 40
    for i, n in enumerate(sorted(app.d.get("navigation", []), key=lambda n: n.get("order", 0))):
        t = n.get("target") or {}
        nid = p.box(f"n_{n.get('id', n.get('label'))}", esc(n.get("label", "")), nx, 110, 190, 40, "nav")
        target = ids.get(t.get("screenId", "")) or ids.get(f"wf:{t.get('workflowId', '')}")
        if target:
            # Down into the band above the columns, across it, down the gap left of the target's column, in from the left.
            tx, ty, th = where[target]
            band, lane = 162 + 5 * i, tx - gap // 2 + 6 * i - 15
            p.edge(nid, target, "", "edge;" + INTO_LEFT, points=[(nx + 95, band), (lane, band), (lane, ty + th // 2)])
        nx += 210
        if t.get("type") == "dashboard":
            for i, wdg in enumerate(app.d.get("dashboardWidgets", []) or []):
                cfg = wdg.get("config") or {}
                wid = p.box(f"widget_{i}", card(wdg.get("pluginId", ""), code(wdg.get("export", "")), sub="Dashboard widget (plugin)"), nx, 100, 220, 60, "plugin")
                p.edge(nid, wid, "", "edge_dashed")
                if cfg.get("screenId") in ids:
                    p.edge(wid, ids[cfg["screenId"]], "opens", "edge_dashed;" + INTO_LEFT)
                nx += 240

    # How screens lead to each other.
    for w in app.workflows.values():
        for st in w.get("steps", []):
            if st.get("formScreenId") in ids:
                p.edge(ids[f"wf:{w['id']}"], ids[st["formScreenId"]], f"step {st.get('order', '')}", "edge_dashed;" + ACROSS, label_at=0.8)
    for sc in app.screens.values():
        me = ids[sc["id"]]
        if sc.get("detailScreenId") in ids:
            p.edge(me, ids[sc["detailScreenId"]], "opens", "edge;" + DOWN)
        if sc.get("createScreenId") in ids:
            p.edge(me, ids[sc["createScreenId"]], "+ new", "edge_dashed;" + RIGHT_SIDE)
        for st in (sc.get("journey") or {}).get("stages", []):
            a_ = st.get("action") or {}
            dest = ids.get(a_.get("screenId", "")) or ids.get(a_.get("formScreenId", "")) or ids.get(f"wf:{a_.get('workflowId', '')}")
            if dest:
                p.edge(me, dest, f"\u201c{esc(a_.get('label', ''))}\u201d", "edge_dashed;" + ACROSS)
    return [p]


def automation(app: App) -> tuple[list, list]:
    """Plugin steps and cloud flows from the kit's CRM metadata (crm.py plugin-steps / processes), if read."""
    if not app.metadata:
        return [], []
    steps, flows = [], []
    for f in sorted(app.metadata.glob("*plugins*.json")):
        steps += json.loads(f.read_text(encoding="utf-8"))
    for f in sorted(app.metadata.glob("*processes*.json")):
        flows += [x for x in json.loads(f.read_text(encoding="utf-8")) if x.get("kind") == "cloud flow" and x.get("active")]
    seen, unique = set(), []
    for x in steps + flows:
        k = json.dumps(x, sort_keys=True)
        if k not in seen:
            seen.add(k)
            unique.append(x)
    return [x for x in unique if "plugin" in x], [x for x in unique if x.get("kind") == "cloud flow"]


def few(items, n=3) -> str:
    items = sorted(items)
    return ", ".join(items[:n]) + (f" +{len(items) - n} more" if len(items) > n else "")


def architecture_page(app: App) -> list[Page]:
    p = Page("Endpoints and architecture")
    p.box("title", "Endpoints and architecture", 40, 30, 1200, 36, "title")
    p.box("sub", esc("What the app calls, through the customer's Haiko API, and what happens in Dynamics 365 when it does. "
                     + ("Plugins and flows come from the CRM metadata the kit read." if app.metadata else
                        "Read CRM metadata with the kit (crm.py plugin-steps / processes) to see the plugins and flows that react.")),
          40, 68, 1200, 24, "note")
    top = 170
    LR = "exitX=1;exitY=0.5;exitDx=0;exitDy=0;entryX=0;entryY=0.5;entryDx=0;entryDy=0;"

    # Who calls what (the same rules the app and manifest.py follow).
    calls: dict[str, set] = {}
    callers = {}
    def use(eid, key, how, name, kind, style):
        if eid in app.endpoints:
            calls.setdefault(eid, set()).add((key, how))
            callers[key] = (name, kind, style)
    for sc in app.screens.values():
        key, nm, kd = f"s:{sc['id']}", sc.get("name", sc["id"]), SCREEN_KIND.get(sc.get("type"), "")
        for eid in sc.get("createEndpointIds") or []:
            use(eid, key, "creates", nm, kd, "screen")
        for eid in sc.get("actionEndpointIds") or []:
            use(eid, key, "runs", nm, kd, "screen")
        for f in sc.get("fields", []):
            if (f.get("lookupConfig") or {}).get("endpointId"):
                use(f["lookupConfig"]["endpointId"], key, "options", nm, kd, "screen")
        stages = (sc.get("journey") or {}).get("stages", [])
        for st in stages:
            a_ = st.get("action") or {}
            if a_.get("endpointId"):
                use(a_["endpointId"], key, f"\u201c{a_.get('label', '')}\u201d", nm, kd, "screen")
        if sc.get("type") == "record" and stages:
            files = {f["name"] for f in sc.get("fields", []) if f.get("type") in ("file", "camera", "signature")}
            editable = set().union(*[set(st.get("showFields", [])) - set(st.get("readOnlyFields") or []) - files for st in stages])
            ent = sc.get("entity")
            target = next((e for e in app.endpoints if any(x.get("type") == "form" and x.get("entity") == ent and e in (x.get("updateEndpointIds") or [])
                                                            for x in app.screens.values())), None) or \
                next((e["id"] for e in app.endpoints.values() if e.get("uri") == ent), None)
            if editable and target:
                use(target, key, "saves edits", nm, kd, "screen")
    for w in app.workflows.values():
        use(w.get("submitEndpointId"), f"w:{w['id']}", "submits", w.get("name", w["id"]), "Multi-step form", "workflow")

    # Order endpoints by what they reach, and callers by the endpoints they call, to keep lines short.
    def reach(e):
        kind, name = target_of(app, e)
        ent = name if kind == "entity" else app.manifest_eps.get(e, {}).get("entity") or "~"
        return (ent, kind != "entity", name, e)
    eps = sorted(calls, key=reach)
    first = {}
    for i, e in enumerate(eps):
        for caller, _ in calls[e]:
            first.setdefault(caller, i)

    ids, y = {}, top
    p.box("h_app", "<b>The app</b>", 40, top - 50, 280, 30, "note;fontColor=#0F172A")
    for key in sorted(callers, key=lambda k: (first[k], callers[k][0])):
        name, kind, style = callers[key]
        ids[key] = p.box(f"c_{key}", card(name, sub=kind), 40, y, 280, 56, style)
        y += 72
    api_h = 70 + sum(box_height(endpoint_lines(app, e, calls[e]), 44) + 24 for e in eps)
    p.box("api", "Customer's Haiko API<br><span style='font-size:11px;font-weight:normal'>checks the signed-in contact and the security manifest on every call</span>",
          440, top - 50, 400, max(api_h, 120), "api")
    ey = top + 20
    for e in eps:
        lines = endpoint_lines(app, e, calls[e])
        h = box_height(lines, 44)
        ids[f"e:{e}"] = p.box(f"ep_{e}", card(e, *lines, sub=f"{app.endpoints[e].get('type', '')} endpoint"), 460, ey, 360, h, "endpoint")
        for caller, how in sorted(calls[e]):
            p.edge(ids[caller], ids[f"e:{e}"], esc(how), "edge;" + LR, label_at=-0.55)
        ey += h + 24

    # What it reaches in Dynamics: tables first, each followed by the Custom APIs bound to it.
    tx, ty = 960, top
    p.box("h_crm", "<b>Dynamics 365</b>", tx, top - 50, 320, 30, "note;fontColor=#0F172A")
    readers: dict[str, list] = {}
    for sc in app.screens.values():
        if sc.get("entity") and sc.get("type") in ("list", "record"):
            readers.setdefault(sc["entity"], []).append(sc.get("name", sc["id"]))
    for e in eps:
        kind, name = target_of(app, e)
        key = f"t:{kind}:{name}"
        if key not in ids:
            if kind == "entity":
                lines = [policy_line(app, name)] + ([f"Read by {esc(', '.join(sorted(readers[name])))}"] if readers.get(name) else [])
                h = box_height(lines, 44) + 24
                ids[key] = p.box(f"ent_{name}", card(name, *lines, sub="table"), tx, ty, 320, h, "entity")
            else:
                bound = app.manifest_eps.get(e, {}).get("entity")
                lines = [f"on an {code(bound)} record" if bound else "not bound to a record"] if kind == "action" else [esc(name)]
                h = box_height(lines, 44)
                ids[key] = p.box(f"t_{kind}_{name}", card(name if kind == "action" else "Logic App", *lines,
                                                         sub="Custom API / action" if kind == "action" else "outside Dynamics"), tx, ty, 320, h,
                                 "action" if kind == "action" else "box")
            ty += h + 26
        p.edge(ids[f"e:{e}"], ids[key], "", "edge;" + LR)

    # CRM automation that reacts to what the app writes, one box per plugin or flow.
    written: dict[str, set] = {}
    created = set()
    for e in eps:
        kind, name = target_of(app, e)
        ent = name if kind == "entity" else app.manifest_eps.get(e, {}).get("entity")
        if ent:
            written.setdefault(ent, set()).update(app.manifest_eps.get(e, {}).get("writableFields") or [])
            if any(how in ("creates", "submits") for _, how in calls[e]):
                created.add(ent)
    steps, flows = automation(app)
    reactions: dict[tuple, dict] = {}
    for x in steps:
        if x["plugin"].startswith(("Microsoft.", "ActivityFeeds.")):
            continue  # Dynamics' own
        ent, msg, fields = x.get("entity"), (x.get("message") or "").lower(), set(x.get("fields") or [])
        if ent in written and ((msg == "create" and ent in created) or (msg == "update" and (not fields or fields & written[ent]))):
            r = reactions.setdefault((ent, x["plugin"]), {"title": x["plugin"].split(".")[-1], "sub": "plugin", "lines": [code(x["plugin"])], "on": []})
            r["on"].append(msg if msg == "create" else f"update of {few(fields & written[ent])}" if fields else "update")
            r["sub"] = f"plugin, {x.get('stage', '')}{', async' if x.get('async') else ''}"
    for x in flows:
        trig = next((t for t in x.get("triggers", []) if t.get("kind") == "dataverse"), None)
        if not trig:
            continue
        ent, when, fields = trig.get("entity"), trig.get("when", ""), set(trig.get("fields") or [])
        if ent in written and (("create" in when and ent in created) or ("update" in when and (not fields or fields & written[ent]))):
            r = reactions.setdefault((ent, x.get("name")), {"title": x.get("name", ""), "sub": "cloud flow", "on": [],
                                                           "lines": [f"then {esc(ef.get('op'))} {code(ef.get('entity') or ef.get('action') or '')}"
                                                                     for ef in x.get("effects", [])][:4]})
            r["on"].append(when + (f" of {few(fields)}" if fields else ""))
    ax, ay = 1400, top
    if reactions:
        p.box("h_auto", "<b>CRM automation that reacts</b>", ax, top - 50, 340, 30, "note;fontColor=#0F172A")
    order = {k: i for i, k in enumerate(ids)}
    for (ent, name), r in sorted(reactions.items(), key=lambda kv: (order.get(f"t:entity:{kv[0][0]}", 0), kv[1]["title"])):
        if f"t:entity:{ent}" not in ids:
            continue
        lines = r["lines"] + [f"<span style='color:#BE185D'>on {esc('; '.join(sorted(set(r['on']))))}</span>"]
        h = box_height(lines, 44)
        aid = p.box(f"auto_{name}", card(r["title"], *lines, sub=r["sub"]), ax, ay, 340, h, "automation")
        p.edge(ids[f"t:entity:{ent}"], aid, "", "edge_crm;" + LR)
        ay += h + 20
    return [p]


def endpoint_lines(app: App, e: str, uses=()) -> list[str]:
    mep = app.manifest_eps.get(e)
    if mep is None:
        return ["<span style='color:#B91C1C'>not in the security manifest: the API refuses it</span>"]
    lines = []
    if mep.get("customerField"):
        lines.append(f"sets {code(mep['customerField'])} to the contact")
    if uses and all(how == "options" for _, how in uses):
        lines.append("supplies a lookup's options; writes nothing")
    elif mep.get("writableFields") is not None:
        lines.append("may write " + (", ".join(code(f) for f in mep["writableFields"]) or "nothing"))
    else:
        lines.append("<span style='color:#B45309'>no writableFields: may write any field</span>")
    return lines


def target_of(app: App, e: str) -> tuple[str, str]:
    ep, mep = app.endpoints[e], app.manifest_eps.get(e, {})
    if ep.get("type") == "d365_action":
        return "action", mep.get("action") or ep.get("uri") or e
    if ep.get("type") == "logic_app":
        return "logic_app", (ep.get("uri") or "Logic App").split("?")[0].split("/")[2] if "://" in (ep.get("uri") or "") else "Logic App"
    return "entity", mep.get("entity") or ep.get("uri") or "?"


TAB_BUILDERS = [navigation_page, architecture_page, journey_pages, wizard_pages]


def build(app: App) -> list[Page]:
    pages = []
    for builder in TAB_BUILDERS:
        pages += builder(app)
    return [overview(app, [p.name for p in pages])] + pages


def main(argv=None):
    ap = argparse.ArgumentParser(description="Draw a Haiko app as a draw.io file, a tab per diagram.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--app", help="workspace/<app> folder (app-definition.json, security-manifest.json, metadata/)")
    src.add_argument("--snapshot", help="a Studio snapshot export (.json)")
    ap.add_argument("--metadata", help="CRM metadata folder from crm.py (default: <app>/metadata)")
    ap.add_argument("--out", required=True, help="the .drawio file to write")
    args = ap.parse_args(argv)
    pages = build(load(args))
    write(pages, Path(args.out))
    print(f"wrote {args.out}: {', '.join(p.name for p in pages)}")


if __name__ == "__main__":
    main()
