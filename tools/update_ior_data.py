"""Rebuild ior_material_list/ior_data.py from the source websites.

    python tools/update_ior_data.py                 # download the pages, write ior_data.py
    python tools/update_ior_data.py --html DIR      # use saved pages: DIR/baly.html, DIR/pixel.html,
                                                    #   DIR/refractiveindex/<data path>
    python tools/update_ior_data.py --save DIR      # also keep the downloaded pages in DIR (for --html)
    python tools/update_ior_data.py --check         # only report whether the file would change

Plain Python 3.11+, no Blender needed. Sources:

* balyberdin.com/tools/ior-list/  -> curated materials by category, plus metals (n, k per RGB)
* pixelandpoly.com/ior.html       -> the A–Z list (its "Common Materials" block repeats A–Z and is skipped)
* community.blender.it forum post -> no stable markup; the few entries missing from the two
                                     lists above were picked by hand and live in BLENDERIT_EXTRA
* refractiveindex.info database   -> the pages listed in RI_PAGES, n evaluated at 589.3 nm

Hand corrections to scraped names are in NAME_FIXES. If a site changes its HTML, the
parser stops with a clear error instead of writing a half-empty file.
"""

import argparse
import html
import os
import re
import sys
import urllib.parse
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "ior_material_list", "ior_data.py")

URLS = {
    "baly": "https://balyberdin.com/tools/ior-list/",
    "pixel": "https://pixelandpoly.com/ior.html",
}

# Typos in the scraped names, fixed so that search finds them.
NAME_FIXES = {"Garnet, Demantiod": "Garnet, Demantoid"}

# Entries from https://community.blender.it/forums/topic/indice-ior-per-materiale/ that the
# two scraped lists lack (other names for existing entries are included so search finds them).
BLENDERIT_EXTRA = [
    ("Willemite", 1.69, None, "Minerals & Gemstones"),
    ("Witherite", 1.532, None, "Minerals & Gemstones"),
    ("Rhodochrosite", 1.597, 1.816, "Minerals & Gemstones"),
    ("Microcline", 1.514, 1.539, "Minerals & Gemstones"),
    ("Halite (rock salt)", 1.544, None, "Minerals & Gemstones"),
    ("Grossularite (garnet)", 1.734, None, "Minerals & Gemstones"),
    ("Andradite (garnet)", 1.887, None, "Minerals & Gemstones"),
    ("Spessartine (garnet)", 1.8, None, "Minerals & Gemstones"),
    ("Degreaser", 1.377, None, "Household liquids"),
]

# refractiveindex.info database (CC0, github.com/polyanskiy/refractiveindex.info-database).
# Each page holds n (and maybe k) as a dispersion formula or a table over wavelength; the
# value stored is n at RI_WAVELENGTH. Pages were picked from the site's own "Selected
# materials for 3D artists" shelf plus common rendering materials. A second path makes a
# range: for birefringent crystals the ordinary/extraordinary (or alpha/gamma) indices.
# (name, category, data path, second data path or None)
RI_BASE = "https://raw.githubusercontent.com/polyanskiy/refractiveindex.info-database/main/database/data/"
RI_WAVELENGTH = 0.5893  # µm, sodium D line: the "nD" most IOR lists quote
RI_MAX_K = 0.1  # stronger absorbers (metals, soot, germanium) are not plain IOR materials
RI_PAGES = [
    ("BK7 Optical Glass (crown)", "Glass", "specs/schott/optical/N-BK7.yml", None),
    ("BAF10 Optical Glass (flint)", "Glass", "specs/schott/optical/N-BAF10.yml", None),
    ("SF10 Optical Glass (dense flint)", "Glass", "specs/schott/optical/N-SF10.yml", None),
    ("Fused Silica", "Glass", "main/SiO2/nk/Malitson.yml", None),
    # Rubin's clear/green/bronze/grey/low-iron pages share n and differ only in k (tint).
    ("Soda-Lime Glass (window, bottle)", "Glass", "glass/misc/soda-lime/nk/Rubin-clear.yml", None),
    ("Water (25 °C)", "Liquids", "main/H2O/nk/Hale.yml", None),
    ("Ethanol", "Liquids", "organic/C2H6O - ethanol/nk/Rheims.yml", None),
    ("Methanol", "Liquids", "organic/CH4O - methanol/nk/Moutzouris.yml", None),
    ("Glycerol", "Liquids", "organic/C3H8O3 - glycerol/nk/Rheims.yml", None),
    ("Ethylene Glycol (antifreeze)", "Liquids", "organic/C2H6O2 - ethylene glycol/nk/El-Kashef.yml", None),
    ("Acetone", "Liquids", "organic/C3H6O - acetone/nk/Rheims.yml", None),
    ("Acetic Acid", "Liquids", "organic/C2H4O2 - acetic acid/nk/El-Kashef.yml", None),
    ("Ethyl Acetate", "Liquids", "organic/C4H8O2 - ethyl acetate/nk/Kozma.yml", None),
    ("Oleic Acid", "Liquids", "organic/C18H34O2 - oleic acid/nk/Jones.yml", None),
    ("Benzene", "Liquids", "organic/C6H6 - benzene/nk/Moutzouris.yml", None),
    ("Toluene", "Liquids", "organic/C7H8 - toluene/nk/Kedenburg.yml", None),
    ("Xylene", "Liquids", "organic/C8H10 - xylene/nk/Li.yml", None),
    ("Cyclohexane", "Liquids", "organic/C6H12 - cyclohexane/nk/Rheims.yml", None),
    ("Hexane", "Liquids", "organic/C6H14 - hexane/nk/Kozma.yml", None),
    ("Carbon Tetrachloride", "Liquids", "organic/CCl4 - carbon tetrachloride/nk/Kedenburg.yml", None),
    ("Acrylic (PMMA)", "Plastics", "organic/(C5H8O2)n - poly(methyl methacrylate)/nk/Sultanova.yml", None),
    ("Polycarbonate (PC)", "Plastics", "organic/(C16H14O3)n - polycarbonate/nk/Sultanova.yml", None),
    ("Polystyrene (PS)", "Plastics", "organic/(C8H8)n - polystyrene/nk/Sultanova.yml", None),
    ("Polyethylene Terephthalate (PET)", "Plastics", "organic/(C10H8O4)n - polyethylene terephthalate/nk/Zhang.yml", None),
    ("Polyvinyl Chloride (PVC)", "Plastics", "organic/(C2H3Cl)n - polyvinyl chloride/nk/Zhang.yml", None),
    ("Polylactic Acid (PLA)", "Plastics", "organic/(C3H4O2)n - polylactic acid/nk/Bodurov.yml", None),
    ("Silicone (PDMS, Sylgard 184)", "Plastics", "organic/(C2H6OSi)n - polydimethylsiloxane/nk/Schneider-Sylgard184.yml", None),
    ("CR-39 (eyeglass lenses)", "Plastics", "other/commercial polymers/CR-39/nk/poly.yml", None),
    ("Cellulose", "Plastics", "organic/(C6H10O5)n - cellulose/nk/Sultanova.yml", None),
    ("Diamond", "Minerals & Gemstones", "main/C/nk/Phillip.yml", None),
    ("Quartz", "Minerals & Gemstones", "main/SiO2/nk/Ghosh-o.yml", "main/SiO2/nk/Ghosh-e.yml"),
    ("Sapphire / Ruby (corundum)", "Minerals & Gemstones", "main/Al2O3/nk/Malitson-o.yml", "main/Al2O3/nk/Malitson-e.yml"),
    ("Calcite", "Minerals & Gemstones", "main/CaCO3/nk/Ghosh-o.yml", "main/CaCO3/nk/Ghosh-e.yml"),
    ("Rutile (TiO2)", "Minerals & Gemstones", "main/TiO2/nk/Devore-o.yml", "main/TiO2/nk/Devore-e.yml"),
    ("Moissanite (6H-SiC)", "Minerals & Gemstones", "main/SiC/nk/Wang-6H-o.yml", "main/SiC/nk/Wang-6H-e.yml"),
    ("Chrysoberyl", "Minerals & Gemstones", "main/BeAl2O4/nk/Walling-alpha.yml", "main/BeAl2O4/nk/Walling-gamma.yml"),
    ("Spinel", "Minerals & Gemstones", "main/MgAl2O4/nk/Tropf.yml", None),
    ("YAG (yttrium aluminium garnet)", "Minerals & Gemstones", "main/Y3Al5O12/nk/Zelmon.yml", None),
    ("Fluorite (CaF2)", "Minerals & Gemstones", "main/CaF2/nk/Malitson.yml", None),
    ("Halite (rock salt, NaCl)", "Minerals & Gemstones", "main/NaCl/nk/Li.yml", None),
    ("Sphalerite (zinc sulfide)", "Minerals & Gemstones", "main/ZnS/nk/Debenham.yml", None),
    ("Periclase (MgO)", "Minerals & Gemstones", "main/MgO/nk/Stephens.yml", None),
    ("Ice", "Frozen", "main/H2O/nk/Warren-2008.yml", None),
    ("Air (15 °C, 1 atm)", "Gases", "other/mixed gases/air/nk/Ciddor.yml", None),
]

HEADER = '''"""IOR tables used by the add-on. Generated by tools/update_ior_data.py — edit that script, not this file.

Sources: pixelandpoly.com/ior.html, balyberdin.com/tools/ior-list/,
         community.blender.it/forums/topic/indice-ior-per-materiale/,
         refractiveindex.info (CC0 database, n at 589.3 nm)
"""

'''


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (ior-data-updater)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8")


def _save(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def clean(s):
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s).replace("★", "").replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()


def num(s):
    try:
        return float(clean(s))
    except ValueError:
        return None


def parse_pixel(t):
    """A–Z list: name, min, max ('-' when there is no range)."""
    start = t.find("A - Materials")
    if start < 0:
        raise SystemExit("pixelandpoly: 'A - Materials' heading not found; the page layout changed")
    rows = []
    pat = r'ior-name">(.*?)</span>\s*<span[^>]*ior-value">(.*?)</span>\s*<span[^>]*ior-value">(.*?)</span>'
    for m in re.finditer(pat, t[start:], re.S):
        name, lo, hi = clean(m.group(1)), num(m.group(2)), num(m.group(3))
        if name and lo is not None:
            rows.append((NAME_FIXES.get(name, name), lo, hi, "", "pixelandpoly"))
    return rows


def parse_baly(t):
    """Curated materials (by category) and metals (n, k rows for R, G, B)."""
    mats, metals = [], []
    for body in re.finditer(r'<tbody data-category="([^"]*)">(.*?)</tbody>', t, re.S):
        cat = html.unescape(body.group(1))
        for row in re.finditer(r'<tr class="material-block"[^>]*>(.*?)</tr>', body.group(2), re.S):
            tds = re.findall(r"<td([^>]*)>(.*?)</td>", row.group(1), re.S)
            name = clean(tds[0][1])
            vals = []
            for attrs, _ in tds[1:]:
                mv = re.search(r'data-value="([^"]+)"', attrs)
                vals.append(float(mv.group(1)) if mv else None)
            if vals and vals[0] is not None:
                mats.append((NAME_FIXES.get(name, name), vals[0], vals[1] if len(vals) > 1 else None, cat, "balyberdin"))
    for body in re.finditer(r'<tbody class="material-block" data-material="([^"]*)">(.*?)</tbody>', t, re.S):
        name = clean(html.unescape(body.group(1)))
        n = [float(x) for x in re.findall(r'subrow-n" data-value="([^"]*)"', body.group(2))]
        k = [float(x) for x in re.findall(r'subrow-k" data-value="([^"]*)"', body.group(2))]
        if len(n) == 3 and len(k) == 3:
            metals.append((name, tuple(n), tuple(k)))
    return mats, metals


def ri_parse(text):
    """The DATA list of a refractiveindex.info page, as [(type, coefficients or table rows, range)].

    The files are YAML, but only this small, fixed subset is needed, so no PyYAML:
        DATA:
          - type: formula 2            (or: tabulated n / nk / k)
            coefficients: 0 1.03 ...
            data: |
                0.300 1.349 1.6e-8
    """
    entries, in_data, in_table = [], False, False
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line[0].isspace():  # a top-level key: DATA starts, anything else ends it
            in_data, in_table = line.startswith("DATA:"), False
            continue
        if not in_data:
            continue
        s = line.strip()
        if s.startswith("- type:"):
            entries.append([s.split(":", 1)[1].strip(), [], None])
            in_table = False
        elif s.startswith("coefficients:"):
            entries[-1][1] = [float(x) for x in s.split(":", 1)[1].split()]
        elif s.startswith("wavelength_range:"):
            entries[-1][2] = tuple(float(x) for x in s.split(":", 1)[1].split())
        elif s.startswith("data:"):
            in_table = True
        elif in_table and entries:
            entries[-1][1].append([float(x) for x in s.split()])
    return entries


def ri_formula(kind, c, wl):
    """n at wavelength wl (µm) for the numbered dispersion formulas of refractiveindex.info
    (database/doc/Dispersion formulas.pdf)."""
    c = list(c) + [0.0] * (17 - len(c))
    w2 = wl * wl
    if kind == 1:  # Sellmeier
        return (1 + c[0] + sum(c[i] * w2 / (w2 - c[i + 1] ** 2) for i in range(1, 17, 2))) ** 0.5
    if kind == 2:  # Sellmeier-2
        return (1 + c[0] + sum(c[i] * w2 / (w2 - c[i + 1]) for i in range(1, 17, 2))) ** 0.5
    if kind == 3:  # polynomial
        return (c[0] + sum(c[i] * wl ** c[i + 1] for i in range(1, 17, 2))) ** 0.5
    if kind == 4:  # RefractiveIndex.INFO
        n2 = c[0] + c[1] * wl ** c[2] / (w2 - c[3] ** c[4]) + c[5] * wl ** c[6] / (w2 - c[7] ** c[8])
        return (n2 + sum(c[i] * wl ** c[i + 1] for i in range(9, 17, 2))) ** 0.5
    if kind == 5:  # Cauchy
        return c[0] + sum(c[i] * wl ** c[i + 1] for i in range(1, 11, 2))
    if kind == 6:  # gases
        return 1 + c[0] + sum(c[i] / (c[i + 1] - wl ** -2) for i in range(1, 11, 2))
    if kind == 7:  # Herzberger
        L = 1 / (w2 - 0.028)
        return c[0] + c[1] * L + c[2] * L * L + c[3] * w2 + c[4] * w2 ** 2 + c[5] * w2 ** 3
    if kind == 8:  # retro
        r = c[0] + c[1] * w2 / (w2 - c[2]) + c[3] * w2
        return ((1 + 2 * r) / (1 - r)) ** 0.5
    if kind == 9:  # exotic
        return (c[0] + c[1] / (w2 - c[2]) + c[3] * (wl - c[4]) / ((wl - c[4]) ** 2 + c[5])) ** 0.5
    raise ValueError(f"unknown formula {kind}")


def ri_interp(rows, col, wl):
    """Linear interpolation of column `col` of a wavelength table; None outside its range.
    A table may be a single row measured at (within 1 nm of) wl itself."""
    if len(rows) == 1 and abs(rows[0][0] - wl) <= 0.001:
        return rows[0][col]
    for a, b in zip(rows, rows[1:]):
        if a[0] <= wl <= b[0]:
            t = (wl - a[0]) / (b[0] - a[0]) if b[0] != a[0] else 0.0
            return a[col] + t * (b[col] - a[col])
    return None


def ri_nk(text, wl=RI_WAVELENGTH):
    """(n, k) of a page at wavelength wl; k is 0 when the page has none."""
    n = k = None
    for kind, vals, rng in ri_parse(text):
        if kind.startswith("formula"):
            if rng is None or rng[0] <= wl <= rng[1]:  # formulas are fits; never extrapolate
                n = ri_formula(int(kind.split()[1]), vals, wl)
        elif kind == "tabulated nk":
            n, k = ri_interp(vals, 1, wl), ri_interp(vals, 2, wl)
        elif kind == "tabulated n":
            n = ri_interp(vals, 1, wl)
        elif kind == "tabulated k":
            k = ri_interp(vals, 1, wl)
    return n, k or 0.0


def parse_ri(pages):
    """Rows for RI_PAGES from {data path: file text}. Stops if a page has no usable value."""
    rows = []
    for name, cat, path, path2 in RI_PAGES:
        vals = []
        for p in (path, path2):
            if p is None:
                continue
            n, k = ri_nk(pages[p])
            if n is None or not 1.0 <= n < 5.0:
                raise SystemExit(f"refractiveindex.info: no n at {RI_WAVELENGTH} µm in {p}")
            if k > RI_MAX_K:
                raise SystemExit(f"refractiveindex.info: {p} absorbs too strongly (k={k:.3g}) for an IOR entry")
            # Air and other gases need more than 3 decimals to differ from 1.
            vals.append(round(n, 6 if n < 1.01 else 4))
        lo, hi = min(vals), max(vals)
        rows.append((name, lo, hi if hi > lo else None, cat, "refractiveindex"))
    return rows


def render(baly, pixel, metals, ri=()):
    out = [HEADER.rstrip("\n"), "", "# (name, ior, max_ior or None, category, source)", "MATERIALS = ["]
    for name, ior, ior_max, cat, src in baly + pixel:
        out.append(f"    ({name!r}, {ior}, {ior_max}, {cat!r}, {src!r}),")
    out.append("    # --- community.blender.it (only entries not already listed above)")
    for name, ior, ior_max, cat in BLENDERIT_EXTRA:
        out.append(f"    ({name!r}, {ior}, {ior_max}, {cat!r}, 'blenderit'),")
    if ri:
        out.append(f"    # --- refractiveindex.info (n at {RI_WAVELENGTH * 1000:g} nm; ranges are birefringent o/e)")
    for name, ior, ior_max, cat, src in ri:
        out.append(f"    ({name!r}, {ior}, {ior_max}, {cat!r}, {src!r}),")
    out += ["]", "", "# (name, n_rgb, k_rgb) for conductors", "METALS = ["]
    for name, n, k in metals:
        out.append(f"    ({name!r}, {n}, {k}),")
    out.append("]")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--html", help="folder with saved baly.html and pixel.html instead of downloading")
    ap.add_argument("--save", help="folder to store the pages used, in the layout --html reads")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--check", action="store_true", help="don't write; exit 1 if the file would change")
    args = ap.parse_args()

    ri_paths = sorted({p for row in RI_PAGES for p in row[2:] if p})
    if args.html:
        pages = {k: open(os.path.join(args.html, f"{k}.html"), encoding="utf-8").read() for k in URLS}
        ri_pages = {p: open(os.path.join(args.html, "refractiveindex", p), encoding="utf-8").read()
                    for p in ri_paths}
    else:
        pages = {k: fetch(u) for k, u in URLS.items()}
        ri_pages = {p: fetch(RI_BASE + urllib.parse.quote(p)) for p in ri_paths}
    if args.save:
        for k, t in pages.items():
            _save(os.path.join(args.save, f"{k}.html"), t)
        for p, t in ri_pages.items():
            _save(os.path.join(args.save, "refractiveindex", p), t)

    baly, metals = parse_baly(pages["baly"])
    pixel = parse_pixel(pages["pixel"])
    ri = parse_ri(ri_pages)
    # Sanity limits: the pages had 112 / 364 / 16 rows when this script was written.
    for label, rows, minimum in (("balyberdin materials", baly, 80), ("pixelandpoly", pixel, 300), ("metals", metals, 10)):
        if len(rows) < minimum:
            raise SystemExit(f"{label}: only {len(rows)} rows parsed (expected {minimum}+); the page layout changed")

    text = render(baly, pixel, metals, ri)
    old = open(args.out, encoding="utf-8").read() if os.path.exists(args.out) else ""
    print(f"balyberdin {len(baly)}, pixelandpoly {len(pixel)}, blenderit {len(BLENDERIT_EXTRA)}, "
          f"refractiveindex {len(ri)}, metals {len(metals)}")
    if text == old:
        print("ior_data.py is up to date")
        return
    if args.check:
        print("ior_data.py would change")
        sys.exit(1)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
