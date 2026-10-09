#!/usr/bin/env python3
"""Generate the TikZ/pgfplots sources of the new figures and the ledger table.

Standard library only.  Output goes to ``manuscript/figures`` and
``manuscript/tables``.  Run ``verify_manuscript.py`` first: it writes
``ancillary/data/ledger.json`` that this script reads.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ANC = HERE.parent
MAN = ANC.parent
REPO = MAN.parent
sys.path.insert(0, str(REPO / "scripts" / "boundary"))
from upper_bounds import ORDINARY_MAXIMUM as M  # noqa: E402

DCORR = (26, 23, 18, 23, 20, 23, 26, 11)
LED = json.loads((ANC / "data" / "ledger.json").read_text())
LOW = {int(k): v for k, v in LED["lower"].items()}
UPP = {int(k): v for k, v in LED["upper"].items()}
SPECIAL = {int(k): v for k, v in LED["special_upper"].items()}


def U(n):
    return (4 * n * n + 5 * n - DCORR[n % 8]) // 8


def board(n):
    p = ANC / "constructions" / f"n{n:02d}.json"
    if not p.exists():
        p = REPO / "constructions" / f"n{n:02d}.json"
    return json.loads(p.read_text())["grid"]


def tikz_board(grid, unit, bands=None, band_color="black!14"):
    """Rows of live cells as merged rectangles; optional shaded index bands."""
    n = len(grid)
    out = [f"\\begin{{scope}}[x={unit}cm,y={unit}cm]"]
    out.append(f"\\fill[black!7] (-1,-1) rectangle ({n + 1},{n + 1});")
    out.append(f"\\fill[white] (0,0) rectangle ({n},{n});")
    if bands:
        (r0, r1), (c0, c1) = bands
        out.append(f"\\fill[{band_color}] (0,{n - r1}) rectangle ({n},{n - r0});")
        out.append(f"\\fill[{band_color}] ({c0},0) rectangle ({c1},{n});")
    out.append(f"\\draw[black,line width=.35pt] (0,0) rectangle ({n},{n});")
    for i, row in enumerate(grid):
        y = n - 1 - i
        j = 0
        while j < n:
            if row[j]:
                k = j
                while k + 1 < n and row[k + 1]:
                    k += 1
                out.append(f"\\fill ({j},{y}) rectangle ({k + 1},{y + 1});")
                j = k + 1
            else:
                j += 1
    out.append("\\end{scope}")
    return "\n".join(out)


def figure_boards(name, sizes, labels, unit_cm=4.0):
    parts = ["\\begin{tikzpicture}"]
    x = 0.0
    for n, lab in zip(sizes, labels):
        unit = unit_cm / (n + 2)
        parts.append(f"\\begin{{scope}}[xshift={x:.3f}cm]")
        parts.append(tikz_board(board(n), f"{unit:.4f}"))
        parts.append(f"\\node[align=center,font=\\footnotesize] at ({unit_cm / 2 - unit:.3f},-0.45) {{{lab}}};")
        parts.append("\\end{scope}")
        x += unit_cm + 0.35
    parts.append("\\end{tikzpicture}")
    (MAN / "figures" / name).write_text("\n".join(parts) + "\n")


def figure_density():
    ns = range(7, 51)
    m = " ".join(f"({n},{M[n] / n ** 2:.5f})" for n in ns)
    u = " ".join(f"({n},{min(M[n], U(n)) / n ** 2:.5f})" for n in range(14, 51))
    up = " ".join(f"({n},{UPP[n] / n ** 2:.5f})" for n in ns)
    lo_open = " ".join(f"({n},{LOW[n] / n ** 2:.5f})" for n in ns if LOW[n] < UPP[n])
    lo_exact = " ".join(f"({n},{LOW[n] / n ** 2:.5f})" for n in ns if LOW[n] == UPP[n])
    tex = rf"""\begin{{tikzpicture}}
\begin{{axis}}[width=.93\textwidth,height=6.4cm,xlabel={{$n$}},ylabel={{population$/n^2$}},
 xmin=6,xmax=51,ymin=0.495,ymax=0.585,grid=both,grid style={{black!10}},
 legend style={{font=\footnotesize,at={{(0.98,0.97)}},anchor=north east,draw=black!30}},
 tick label style={{font=\footnotesize}},label style={{font=\small}}]
\addplot[black!55,thick,mark=none] coordinates {{{m}}};
\addlegendentry{{unrestricted optimum $M(n)$}}
\addplot[black,thick,dashed,mark=none] coordinates {{{u}}};
\addlegendentry{{$\min\{{M(n),U(n)\}}$}}
\addplot[black,thin,mark=none] coordinates {{{up}}};
\addlegendentry{{final upper bound $\overline C(n)$}}
\addplot[only marks,mark=*,mark size=1.5pt,black] coordinates {{{lo_exact}}};
\addlegendentry{{lower bound, proved optimum}}
\addplot[only marks,mark=o,mark size=1.6pt,black] coordinates {{{lo_open}}};
\addlegendentry{{lower bound, open size}}
\end{{axis}}
\end{{tikzpicture}}
"""
    (MAN / "figures" / "fig_bounds_density.tex").write_text(tex)


def figure_gaps():
    ns = range(18, 51)
    pts = " ".join(f"({n},{UPP[n] - LOW[n]})" for n in ns)
    tex = rf"""\begin{{tikzpicture}}
\begin{{axis}}[ybar,bar width=4.2pt,width=.88\textwidth,height=5.2cm,xlabel={{$n$}},
 ylabel={{gap $\overline C(n)-L_n$}},xmin=17,xmax=51,ymin=0,ymax=6,
 ytick={{0,1,2,3,4,5}},xtick={{18,22,...,50}},ymajorgrids=true,grid style={{black!10}},
 tick label style={{font=\footnotesize}},label style={{font=\small}}]
\addplot[fill=black!55,draw=black!70] coordinates {{{pts}}};
\end{{axis}}
\end{{tikzpicture}}
"""
    (MAN / "figures" / "fig_gaps.tex").write_text(tex)


def figure_band():
    import json as _j
    fams = _j.loads((ANC / "data" / "families.json").read_text())
    fam = next(f for f in fams if f["id"] == "base_r5")
    seed = [[1 if ch == "#" else 0 for ch in r] for r in fam["seed_rows"]]
    rs, cs, p = fam["row_start"], fam["column_start"], fam["period"]

    def f(i, h, k):
        return i if i < h else (h + ((i - h) % p) if i < h + p * k else i - p * (k - 1))

    def build(k):
        n = len(seed) + p * (k - 1)
        return [[seed[f(i, rs, k)][f(j, cs, k)] for j in range(n)] for i in range(n)]

    parts = ["\\begin{tikzpicture}"]
    x = 0.0
    for k, unit_cm in ((1, 5.6), (2, 6.6)):
        g = build(k)
        n = len(g)
        unit = unit_cm / (n + 2)
        band = ((rs, rs + p * k), (cs, cs + p * k))
        parts.append(f"\\begin{{scope}}[xshift={x:.3f}cm]")
        parts.append(tikz_board(g, f"{unit:.4f}", bands=band))
        lab = f"$k={k}$, $n={n}$, population ${n * (n + 1) // 2 - fam['deficit']}$"
        parts.append(f"\\node[font=\\footnotesize] at ({unit_cm / 2 - unit:.3f},-0.45) {{{lab}}};")
        parts.append("\\end{scope}")
        x += unit_cm + 0.6
    parts.append("\\end{tikzpicture}")
    (MAN / "figures" / "fig_band_family.tex").write_text("\n".join(parts) + "\n")


def table_ledger():
    def row(n):
        lo, up = LOW[n], UPP[n]
        mark = "$^{\\dagger}$" if n in SPECIAL else ""
        return f"{n} & {lo} & {M[n]} & {U(n)} & {up}{mark} & {up - lo}"
    left = list(range(18, 35))
    right = list(range(35, 51))
    lines = []
    for i, n in enumerate(left):
        r = row(right[i]) if i < len(right) else "& & & & &"
        lines.append(row(n) + " & & " + r + " \\\\")
    head = "$n$ & $L_n$ & $M(n)$ & $U(n)$ & $\\overline C(n)$ & gap"
    tex = ("\\begin{tabular}{@{}rrrrrr@{\\hspace{1.6em}}c@{\\hspace{1.6em}}rrrrrr@{}}\n\\toprule\n"
           + head + " & & " + head + " \\\\\n\\midrule\n" + "\n".join(lines)
           + "\n\\bottomrule\n\\end{tabular}\n")
    (MAN / "tables" / "bounds_18_50.tex").write_text(tex)


def table_families():
    fams = json.loads((ANC / "data" / "families.json").read_text())
    rows = []
    for f in fams:
        seed = [[1 if ch == "#" else 0 for ch in r] for r in f["seed_rows"]]
        p, rs, cs, n0 = f["period"], f["row_start"], f["column_start"], f["seed_n"]
        rr = {"T": (0, rs), "I": (rs, rs + p), "B": (rs + p, n0)}
        cc = {"L": (0, cs), "I": (cs, cs + p), "R": (cs + p, n0)}
        pop = {a + b: sum(seed[i][j] for i in range(*rr[a]) for j in range(*cc[b])) for a in rr for b in cc}
        A = pop["II"]
        B = sum(pop[s] for s in ("TI", "IL", "IR", "BI"))
        C = sum(pop[s] for s in ("TL", "TR", "BL", "BR"))
        name = {"base": "residue", "large": "residue"}[f["id"].split("_")[0]]
        tag = f"{f['residue']}" + ("$'$" if f["id"].startswith("large") else "")
        rows.append(f"{tag} & {n0} & {rs} & {A} & {B} & {C} & {f['deficit']} & "
                    f"{f['local_radius']} \\\\")
    body = "\n".join(rows)
    tex = ("\\begin{tabular}{@{}ccccrrcc@{}}\n\\toprule\n"
           "$r$ & $n_0$ & $h$ & $A$ & $B$ & $C$ & $a_r$ & $R$ \\\\\n\\midrule\n" + body +
           "\n\\bottomrule\n\\end{tabular}\n")
    (MAN / "tables" / "band_families.tex").write_text(tex)


def board_pdf(grid, path, exact):
    """Write a one-page vector PDF of a board (standard library only)."""
    n = len(grid)
    c = 10
    pad = 3
    size = n * c + 2 * pad
    ops = ["0 0 0 rg"]
    for i, r in enumerate(grid):
        y = pad + (n - 1 - i) * c
        j = 0
        while j < n:
            if r[j]:
                k = j
                while k + 1 < n and r[k + 1]:
                    k += 1
                ops.append(f"{pad + j * c} {y} {(k - j + 1) * c} {c} re f")
                j = k + 1
            else:
                j += 1
    lw = 0.014 * size
    if exact:
        ops.append(f"0.086 0.306 0.388 RG {lw:.3f} w [] 0 d")
    else:
        ops.append(f"0.4 0.4 0.4 RG {0.9 * lw:.3f} w [{3 * lw:.2f} {2 * lw:.2f}] 0 d")
    ops.append(f"{pad} {pad} {n * c} {n * c} re S")
    content = "\n".join(ops).encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {size} {size}] /Contents 4 0 R /Resources << >> >>".encode(),
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))


def figure_atlas():
    """All verified boards n = 2..50 and the exact boards n = 53, 57, 65."""
    sizes = list(range(2, 51)) + [53, 57, 65]
    exact_beyond = {int(k): v for k, v in LED["exact_beyond_50"].items()}
    folder = MAN / "figures" / "atlas"
    folder.mkdir(parents=True, exist_ok=True)
    lines = []
    for idx, n in enumerate(sizes):
        g = board(n)
        pop = sum(map(sum, g))
        exact = (n in exact_beyond) or (n <= 50 and LOW[n] == UPP[n])
        board_pdf(g, folder / f"n{n:02d}.pdf", exact)
        lab = f"$n={n}$: $C(n)={pop}$" if exact else f"$n={n}$: ${pop}\\le C(n)\\le{UPP[n]}$"
        lines.append("\\begin{minipage}[t]{.235\\textwidth}\\centering"
                     f"\\includegraphics[width=.92\\linewidth]{{atlas/n{n:02d}.pdf}}\\\\[1pt]"
                     f"{{\\scriptsize {lab}}}\\end{{minipage}}%")
        lines.append("\\par\\medskip\\noindent" if idx % 4 == 3 else "\\hfill%")
    (MAN / "figures" / "atlas.tex").write_text("\\noindent\n" + "\n".join(lines) + "\n")


def main():
    (MAN / "figures").mkdir(exist_ok=True)
    (MAN / "tables").mkdir(exist_ok=True)
    figure_boards("fig_new_exact.tex", [18, 19, 22, 29],
                  ["$n=18$, $170$", "$n=19$, $188$", "$n=22$, $251$", "$n=29$, $435$"], unit_cm=3.9)
    figure_boards("fig_open.tex", [26, 28, 40, 47],
                  ["$n=26$, $350$", "$n=28$, $406$", "$n=40$, $817$", "$n=47$, $1131$"], unit_cm=3.9)
    figure_density()
    figure_gaps()
    figure_band()
    table_ledger()
    figure_atlas()
    table_families()
    print("figures and tables written to", MAN)


if __name__ == "__main__":
    main()
