"""Command line: python -m sapagent <export.xlsx|csv> [-o rapport.xlsx] [--ai]"""

from __future__ import annotations

import argparse
from pathlib import Path

from .insights import fmt_h
from .pipeline import run
from .report import build_report
from .sample_data import write_sample


def main() -> None:
    p = argparse.ArgumentParser(prog="sapagent", description="Analyse un export SAP PM et produit un rapport Excel.")
    p.add_argument("export", nargs="?", help="Fichier CSV ou Excel exporté de SAP PM (IW38/IW39, IW28/IW29)")
    p.add_argument("-o", "--output", help="Rapport Excel à produire (défaut : rapport_<fichier>.xlsx)")
    p.add_argument("--ai", action="store_true", help="Utiliser Claude (nécessite ANTHROPIC_API_KEY)")
    p.add_argument("--demo", action="store_true", help="Générer et analyser le jeu de données d'exemple")
    args = p.parse_args()

    if args.demo or not args.export:
        args.export = str(write_sample(Path("data/exemple_export_sap_pm.xlsx")))
        print(f"Données d'exemple : {args.export}")

    result = run(args.export, use_ai=args.ai)
    a, ins = result.analysis, result.insights
    out = Path(args.output or f"rapport_{Path(args.export).stem}.xlsx")
    out.write_bytes(build_report(a, ins, Path(args.export).name))

    ov = a.overview
    print(f"\n{ov['orders']} ordres · {ov['equipment']} équipements · {ov['failures']} pannes · {fmt_h(ov['downtime_h'])} d'arrêt")
    print(f"\n{ins['executive_summary']}\n")
    for r in ins["recommendations"][:5]:
        print(f"  [{r['priority']}] {r['equipment']} — {r['action']}")
    if result.ai_error:
        print(f"\n⚠ {result.ai_error}")
    print(f"\nRapport : {out.resolve()}")


if __name__ == "__main__":
    main()
