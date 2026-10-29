"""Command line: python -m sapagent <export.xlsx|csv> [-o rapport.xlsx] [--ai] [--provider openrouter --model ...]"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import __version__
from .ai import PROVIDERS, AIConfig
from .insights import fmt_h
from .kpis import daily_brief
from .pipeline import run
from .report import build_daily_brief, build_report
from .sample_data import write_sample


def main() -> None:
    p = argparse.ArgumentParser(prog="sapagent", description="Analyse un export SAP PM et produit un rapport Excel.")
    p.add_argument("export", nargs="?", help="Fichier CSV ou Excel exporté de SAP PM (IW38/IW39, IW28/IW29, ZGMT_IW29)")
    p.add_argument("-o", "--output", help="Rapport Excel à produire (défaut : rapport_<fichier>.xlsx)")
    p.add_argument("--ai", action="store_true", help="Rédaction et classification par IA")
    p.add_argument("--provider", choices=list(PROVIDERS),
                   help="anthropic (ANTHROPIC_API_KEY) ou openrouter (OPENROUTER_API_KEY). Défaut : selon la clé présente")
    p.add_argument("--model", help="Modèle IA, ex. claude-opus-5-5 ou, sur OpenRouter, anthropic/claude-sonnet-4.5")
    p.add_argument("--work-centers", help="Filtre poste de travail principal, joker accepté : 'MECA*,ELEC-01'")
    p.add_argument("--j1", nargs="?", const="last", metavar="AAAA-MM-JJ",
                   help="Produit aussi la fiche réunion J-1 (dernier jour de l'export par défaut)")
    p.add_argument("--demo", action="store_true", help="Générer et analyser le jeu de données d'exemple")
    p.add_argument("--version", action="version", version=f"SAP PM Analyst {__version__}")
    args = p.parse_args()

    if args.demo or not args.export:
        args.export = str(write_sample(Path("data/exemple_export_sap_pm.xlsx")))
        print(f"Données d'exemple : {args.export}")

    cfg = AIConfig.from_env(args.provider, args.model) if args.ai else None
    result = run(args.export, ai_config=cfg, work_centers=args.work_centers)
    a, ins = result.analysis, result.insights
    out = Path(args.output or f"rapport_{Path(args.export).stem}.xlsx")
    out.write_bytes(build_report(a, ins, Path(args.export).name))

    ov = a.overview
    print(f"\n{ov['orders']} ordres · {ov['equipment']} équipements · {ov['failures']} pannes · "
          f"{fmt_h(ov['downtime_h'])} d'arrêt · {ov['overdue_orders']} ordres en retard")
    source = f"IA · {ins['model']}" if ins.get("source") == "ai" else "règles"
    print(f"\n[{source}] {ins['executive_summary']}\n")
    for r in ins["recommendations"][:5]:
        print(f"  [{r['priority']}] {r['equipment']} — {r['action']}")
    if result.ai_error:
        print(f"\n⚠ {result.ai_error}")
    print(f"\nRapport : {out.resolve()}")

    if args.j1:
        brief = daily_brief(a, None if args.j1 == "last" else args.j1)
        j1 = out.with_name(f"reunion_J-1_{brief['day']:%Y-%m-%d}.xlsx")
        j1.write_bytes(build_daily_brief(brief, Path(args.export).name))
        print(f"Fiche J-1 ({brief['day']:%d/%m/%Y}, {brief['n_interventions']} interventions, "
              f"{len(brief['still_down'])} à l'arrêt) : {j1.resolve()}")


if __name__ == "__main__":
    main()
