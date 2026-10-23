#!/usr/bin/env python3
"""Read-only textual evidence for legal reviews. Never issues legal approval."""
import argparse
from collections import Counter, defaultdict
import difflib
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
from zipfile import ZipFile, BadZipFile

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}
Q = lambda s: "{" + W + "}" + s
LIMITS = [
    "Extração textual, sem OCR, paginação ou validação visual.",
    "Não valida fatos, fontes externas, normas, jurisprudência ou prontidão jurídica.",
    "Revisões de formatação, fusões de parágrafos/tabelas e numeração automática não são simuladas.",
    "Objetos embutidos, imagens e campos sem texto em cache não são interpretados.",
    "Repetições e remissões são indícios heurísticos, sujeitos à revisão humana/modelo.",
]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def visible(node, view, paragraph_root=None):
    if node.tag in {Q("pPrChange"), Q("rPrChange"), Q("tblPrChange"), Q("sectPrChange")}:
        return
    skip = {Q("del"), Q("moveFrom")} if view == "current" else {Q("ins"), Q("moveTo")}
    if node.tag in skip:
        return
    if paragraph_root is not None and node.tag == Q("p") and node is not paragraph_root:
        return
    yield node
    for child in node:
        yield from visible(child, view, paragraph_root)


def para_value(p, view):
    buf, refs = [], []
    for el in visible(p, view, p):
        if el.tag in {Q("t"), Q("delText")}:
            buf.append(el.text or "")
        elif el.tag == Q("tab"):
            buf.append("\t")
        elif el.tag in {Q("br"), Q("cr")}:
            buf.append("\n")
        elif el.tag in {Q("footnoteReference"), Q("endnoteReference")}:
            kind = "footnote" if el.tag == Q("footnoteReference") else "endnote"
            refs.append({"kind": kind, "id": el.get(Q("id"))})
            buf.append("[" + kind + ":" + str(el.get(Q("id"))) + "]")
    return "".join(buf).strip(), refs


def part_kind(name):
    if name == "word/document.xml": return "body"
    if name == "word/footnotes.xml": return "footnote"
    if name == "word/endnotes.xml": return "endnote"
    if re.fullmatch(r"word/header\d*\.xml", name): return "header"
    if re.fullmatch(r"word/footer\d*\.xml", name): return "footer"
    if name == "word/comments.xml": return "comment"
    return None


def read_snapshot(path, view="current"):
    path = Path(path).resolve(strict=True)
    data = path.read_bytes()
    snap = {
        "contract": "minuta_text_snapshot_v1",
        "source": {"path": str(path), "sha256": sha(data), "bytes": len(data)},
        "view": view, "units": [], "parts_read": [], "notes_defined": [],
        "revision_elements": {}, "features_requiring_document_review": {},
        "limits": list(LIMITS), "legal_approval": "not_assessed",
    }
    units = snap["units"]
    if path.suffix.lower() in {".txt", ".md", ".markdown"}:
        content = data.decode("utf-8-sig")
        for line_no, line in enumerate(content.splitlines(), 1):
            if line.strip():
                units.append({"part": "text", "kind": "body", "locator": f"line:{line_no}",
                              "text": line, "style": None, "note_id": None, "note_refs": []})
        snap["parts_read"] = ["text"]
    elif path.suffix.lower() == ".docx":
        revisions, features = Counter(), Counter()
        with ZipFile(io.BytesIO(data)) as z:
            names = {}
            for info in z.infolist():
                normal = info.filename.replace("\\", "/")
                if normal in names:
                    raise ValueError("Membros ZIP com nomes normalizados duplicados")
                names[normal] = info.filename
            if "word/document.xml" not in names:
                raise ValueError("DOCX sem word/document.xml")
            for name in sorted(names, key=lambda s: (s != "word/document.xml", s)):
                kind = part_kind(name)
                if kind is None:
                    continue
                root = ET.fromstring(z.read(names[name]))
                snap["parts_read"].append(name)
                parents = {c: p for p in root.iter() for c in p}
                for el in root.iter():
                    local = el.tag.rsplit("}", 1)[-1]
                    if el.tag in {Q(t) for t in ["ins", "del", "moveFrom", "moveTo", "pPrChange", "rPrChange"]}:
                        revisions[local] += 1
                    if el.tag in {Q(t) for t in ["drawing", "object", "altChunk", "vanish", "numPr", "fldChar", "tbl"]}:
                        features[local] += 1
                    if kind in {"footnote", "endnote"} and el.tag == Q(kind):
                        note_id = el.get(Q("id"))
                        if note_id not in {None, "-1", "0"}:
                            snap["notes_defined"].append({"kind": kind, "id": note_id})
                count = 0
                for p in visible(root, view):
                    if p.tag != Q("p"):
                        continue
                    count += 1
                    text, refs = para_value(p, view)
                    note_id, ancestor = None, parents.get(p)
                    while ancestor is not None:
                        if ancestor.tag in {Q("footnote"), Q("endnote"), Q("comment")}:
                            note_id = ancestor.get(Q("id")); break
                        ancestor = parents.get(ancestor)
                    if kind in {"footnote", "endnote"} and note_id in {"-1", "0"}:
                        continue
                    if not text and not refs:
                        continue
                    style = p.find("w:pPr/w:pStyle", NS)
                    units.append({"part": name, "kind": kind, "note_id": note_id,
                                  "locator": f"{name}:p[{count}]", "text": text,
                                  "style": style.get(Q("val")) if style is not None else None,
                                  "note_refs": refs})
        snap["revision_elements"] = dict(revisions)
        snap["features_requiring_document_review"] = dict(features)
        if revisions:
            snap["limits"].append("A vista é extração lógica de revisões simples, não prova bidirecional de redline Word.")
    else:
        raise ValueError("Formato não suportado. Use DOCX/TXT/Markdown; converta PDF com o fluxo documental/OCR.")
    snap["checks"] = formal_checks(units, snap["notes_defined"])
    return snap


def normalize(text):
    return " ".join(text.split()).casefold()


def formal_checks(units, definitions):
    repeats, duplicate_map, labels, references, used_notes = [], defaultdict(list), set(), [], set()
    for u in units:
        if u["kind"] == "comment":
            continue  # Editorial instructions are not substantive source text.
        text = u["text"]
        for match in re.finditer(r"\b([^\W\d_]+)\s+\1\b", text, re.I):
            repeats.append({"locator": u["locator"], "excerpt": match.group(0)})
        key = normalize(text)
        if len(key) >= 60:
            duplicate_map[key].append(u["locator"])
        candidate = re.sub(r"^\s*#+\s*", "", text)
        m = re.match(r"^\s*(\d+(?:\.\d+)+|[a-z](?:\.\d+)*)[.)]?\s+", candidate)
        if m:
            labels.add(m.group(1))
        for m in re.finditer(r'\b(?:item|itens)\s+[“\"\x27]?([0-9]+(?:\.[0-9]+)*|[a-z](?:\.[0-9]+)*)', text, re.I):
            references.append({"locator": u["locator"], "label": m.group(1)})
        used_notes.update((x["kind"], x["id"]) for x in u["note_refs"])
    declared = {(x["kind"], x["id"]) for x in definitions}
    for ref in references:
        ref["target_label_detected"] = ref["label"] in labels
    return {
        "status": "instrumental_only",
        "adjacent_word_repetitions": repeats,
        "duplicate_text_candidates": [v for v in duplicate_map.values() if len(v) > 1],
        "labels_detected_heuristically": sorted(labels), "references_observed": references,
        "note_references_without_definition": sorted(used_notes - declared),
        "note_definitions_without_visible_reference": sorted(declared - used_notes),
        "warning": "Sem detecção de label não prova remissão inválida; numeração automática e listas exigem inspeção.",
    }


def comparison_units(snap):
    return [u for u in snap["units"] if u["kind"] != "comment"]


def compare(base, candidate):
    aa, bb = comparison_units(base), comparison_units(candidate)
    a = [u["kind"] + "\t" + u["text"] for u in aa]
    b = [u["kind"] + "\t" + u["text"] for u in bb]
    locations = defaultdict(list)
    for u in bb:
        locations[normalize(u["text"])].append(u["locator"])
    changes, losses = [], []
    for op, i, j, k, l in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal": continue
        changes.append({"operation": op, "base_units": aa[i:j], "candidate_units": bb[k:l]})
        for u in aa[i:j]:
            found = locations.get(normalize(u["text"]), [])
            losses.append({"base_locator": u["locator"], "text": u["text"],
                           "exact_text_elsewhere_in_candidate": found,
                           "semantic_classification": "required"})
    report = {
        "contract": "minuta_text_comparison_v1", "base": base["source"], "candidate": candidate["source"],
        "view": base["view"], "changes": changes, "removed_or_rewritten_candidates": losses,
        "limits": LIMITS, "legal_approval": "not_assessed",
    }
    diff = "\n".join(difflib.unified_diff(a, b, fromfile=base["source"]["path"],
                                           tofile=candidate["source"]["path"], lineterm=""))
    return report, diff


def write_outputs(folder, objects, texts):
    folder = Path(folder)
    if folder.exists() and any(folder.iterdir()):
        raise ValueError("Diretório de saída não vazio; escolha novo destino para preservar evidências.")
    folder.mkdir(parents=True, exist_ok=True)
    for name, obj in objects.items():
        (folder / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for name, text in texts.items():
        (folder / name).write_text(text + "\n", encoding="utf-8")


def annotated(snap):
    return "\n\n".join(f'[{u["kind"]}; {u["locator"]}; note={u["note_id"]}]\n{u["text"]}' for u in snap["units"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    ins = sub.add_parser("inspect"); ins.add_argument("file")
    cmp = sub.add_parser("compare"); cmp.add_argument("base"); cmp.add_argument("candidate")
    for p in [ins, cmp]:
        p.add_argument("--view", choices=["current", "original"], default="current")
        p.add_argument("--out", required=True)
    ver = sub.add_parser("verify-delivery"); ver.add_argument("reviewed"); ver.add_argument("destination")
    args = parser.parse_args(argv)
    try:
        if args.action == "verify-delivery":
            paths = [Path(args.reviewed).resolve(strict=True), Path(args.destination).resolve(strict=True)]
            records = [{"path": str(p), "sha256": sha(p.read_bytes())} for p in paths]
            same = records[0]["sha256"] == records[1]["sha256"]
            print(json.dumps({"same_bytes": same, "reviewed": records[0], "destination": records[1],
                              "legal_approval": "not_assessed"}, ensure_ascii=False, indent=2))
            return 0 if same else 1
        if args.action == "inspect":
            s = read_snapshot(args.file, args.view)
            write_outputs(args.out, {"snapshot.json": s}, {"text.txt": annotated(s)})
        else:
            a, b = read_snapshot(args.base, args.view), read_snapshot(args.candidate, args.view)
            report, diff = compare(a, b)
            write_outputs(args.out, {"base.json": a, "candidate.json": b, "comparison.json": report},
                          {"base.txt": annotated(a), "candidate.txt": annotated(b), "text.diff": diff})
        print(json.dumps({"output": str(Path(args.out).resolve()), "status": "instrumental_only"}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, ET.ParseError, BadZipFile) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
