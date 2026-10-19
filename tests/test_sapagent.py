import io

import pandas as pd
import pytest
from openpyxl import load_workbook

from sapagent import ai
from sapagent.classifier import classify_orders, classify_text
from sapagent.kpis import analyse
from sapagent.loader import ExportError, load_export
from sapagent.pipeline import run
from sapagent.report import build_report
from sapagent.sample_data import generate

SMALL_CSV = """AUFNR;AUART;EQUNR;EQKTX;KTEXT;ERDAT;AUSVN;AUSBS;MSAUS;STTXT;GKSTI
1;PM04;P1;Pompe;fuite garniture;01.01.2026;01.01.2026 08:00;01.01.2026 12:00;X;TECO;1.000,50
2;PM01;P1;Pompe;fuite garniture mécanique;15.01.2026;15.01.2026 08:00;15.01.2026 10:00;X;TECO;500
3;PM04;P1;Pompe;chgt garniture fuite;30.01.2026;30.01.2026 08:00;30.01.2026 14:00;X;TECO;250
4;PM02;P1;Pompe;Graissage hebdomadaire;10.01.2026;;;;TECO;100
5;PM01;C1;Convoyeur;voir chef de quart;20.01.2026;20.01.2026 08:00;20.01.2026 09:00;;REL;80
"""


def load_small():
    return load_export(SMALL_CSV.encode(), "export.csv")


def test_loader_maps_sap_technical_names_and_european_numbers():
    res = load_small()
    assert {"order_id", "order_type", "equipment_id", "malfunction_start", "actual_cost"} <= set(res.mapping)
    df = res.data
    assert df.loc[0, "actual_cost"] == pytest.approx(1000.50)
    assert df.loc[0, "downtime_h"] == pytest.approx(4.0)
    assert df.loc[4, "downtime_h"] == 0  # no breakdown flag -> not a stop
    assert df["is_failure"].tolist() == [True, True, True, False, True]
    assert df["is_open"].tolist() == [False, False, False, False, True]


def test_loader_accepts_french_alv_headers_from_sample():
    buf = io.BytesIO()
    generate(months=2).to_excel(buf, index=False)
    res = load_export(buf.getvalue(), "iw39.xlsx")
    assert not res.missing_recommended
    assert not res.unmapped


def test_loader_rejects_file_without_key_columns():
    with pytest.raises(ExportError):
        load_export(b"foo;bar\n1;2\n", "x.csv")


@pytest.mark.parametrize("text,expected", [
    ("Roulement HS côté accouplement", "bearing"),
    ("rlt chauffe palier", "bearing"),
    ("mechanical seal leak", "seal"),
    ("Bande déchirée", "belt"),
    ("flexible hydraulique éclaté", "hydraulic"),
    ("goulotte bouchée", "blockage"),
    ("voir chef de quart", "other"),
])
def test_keyword_classifier(text, expected):
    assert classify_text(text)[0] == expected


def test_kpis_on_hand_computed_example():
    res = load_small()
    a = analyse(classify_orders(res.data), res.missing_recommended)
    p1 = a.equipment.set_index("equipment_id").loc["P1"]
    assert p1["failures"] == 3
    assert p1["downtime_h"] == pytest.approx(12.0)
    assert p1["mttr_h"] == pytest.approx(4.0)
    assert p1["mtbf_h"] == pytest.approx((a.period_hours - 12) / 3)
    assert a.overview["planned_ratio"] == pytest.approx(0.2)
    # Three seal leaks on P1, two of them within 30 days of the previous one.
    assert len(a.repeats) == 1
    assert a.repeats.iloc[0]["category"] == "seal"


def test_sample_data_surfaces_the_planted_problems():
    r = run(generate().to_csv(sep=";", index=False).encode(), "demo.csv")
    a = r.analysis
    assert a.equipment.iloc[0]["equipment_desc"] == "Pompe à pulpe P-201"
    assert a.repeats.iloc[0]["failure_mode"] == "Étanchéité / Fuites"
    assert a.quality["duplicate_orders"] == 1
    assert a.quality["negative_durations"] == 1
    assert r.insights["source"] == "rules" and r.insights["recommendations"]


def test_report_is_a_valid_workbook_with_all_sheets():
    r = run(generate(months=3).to_csv(sep=";", index=False).encode(), "demo.csv")
    wb = load_workbook(io.BytesIO(build_report(r.analysis, r.insights)))
    assert wb.sheetnames[:3] == ["Synthèse", "Équipements", "Modes de défaillance"]
    assert wb["Équipements"]["D5"].value.startswith("=COUNTIFS(")


def test_ai_classification_only_overrides_uncertain_rows(monkeypatch):
    res = load_small()
    df = classify_orders(res.data)

    def fake_ask(client, system, prompt, schema, effort):
        assert "voir chef de quart" in prompt
        assert "fuite garniture" not in prompt  # confident rule hits are not sent
        return {"items": [{"id": 0, "category": "electrical", "confidence": 0.7}]}

    monkeypatch.setattr(ai, "_ask_json", fake_ask)
    monkeypatch.setattr(ai, "_client", lambda key: None)
    out = ai.classify_with_claude(df)
    row = out[out["description"] == "voir chef de quart"].iloc[0]
    assert row["category"] == "electrical" and row["category_source"] == "IA (Claude)"


def test_pipeline_falls_back_to_rules_when_ai_fails(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("réseau indisponible")

    monkeypatch.setattr(ai, "classify_with_claude", boom)
    r = run(SMALL_CSV.encode(), "export.csv", use_ai=True, api_key="sk-test")
    assert r.insights["source"] == "rules"
    assert "réseau indisponible" in r.ai_error
