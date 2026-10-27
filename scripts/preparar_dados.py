"""Extrai os dados reais do sistema de margem original e gera CSVs ANONIMIZADOS para carga no Salesforce.

Uso:
    python scripts/preparar_dados.py "<pasta do projeto Python original>" "<planilha de cronograma (.xlsx)>"

Anonimização (aprovada pelo responsável em 27/10/2026):
  - obras → "OB-001"…; nomes → "Obra 001"…; clientes → "Cliente 01"…; P.O.s → "P.O. A"…
  - valores (receita, custos, dias) reais;
  - custo SEMPRE agregado por obra × disciplina × etapa — nenhum dado por colaborador (evita deduzir salário).
A tabela de correspondência (nomes reais ↔ anônimos) fica em dados/privado/ (fora do git e do Salesforce).
Saída: dados/obras.csv, dados/disciplinas.csv, dados/custos_etapas.csv, dados/privado/correspondencia.json,
       dados/privado/referencia_python.json (margens calculadas pelo sistema original, para validar a carga).
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DADOS = RAIZ / "dados"
PRIV = DADOS / "privado"

AREA = {"EC": "Estruturas", "FU": "Estruturas", "EM": "Estruturas", "IH": "Hidráulicas", "IS": "Hidráulicas",
        "IP": "Hidráulicas", "IG": "Hidráulicas", "II": "Hidráulicas", "DR": "Hidráulicas", "AQ": "Arquitetura",
        "IE": "Elétricas", "SE": "Elétricas", "ENE": "Elétricas", "AC": "HVAC"}
TIPOS = {"HIGH P.", "MEDIUM P.", "LOW P."}


def _letras(n: int) -> str:
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def main(projeto: Path, planilha: Path) -> None:
    sys.path.insert(0, str(projeto))
    from kpis.config import load_config  # noqa: E402
    import gerar_relatorio_desempenho_contratos as g  # noqa: E402

    cfg = load_config(projeto / "config" / "kpis_config.yml")
    d = g.coletar_dados(cfg, planilha)
    obra = d["obra"]

    ids = sorted(obra, key=g._id_sort)
    cod = {oid: f"OB-{n:03d}" for n, oid in enumerate(ids, start=1)}
    clientes = sorted({obra[o]["cliente"] for o in ids})
    cli = {c: f"Cliente {n:02d}" for n, c in enumerate(clientes, start=1)}
    pos = sorted({obra[o]["po"] for o in ids} - {"Sem P.O."})
    po = {p: f"P.O. {_letras(n)}" for n, p in enumerate(pos)}
    po["Sem P.O."] = "Sem P.O."

    DADOS.mkdir(exist_ok=True)
    PRIV.mkdir(exist_ok=True)

    def escrever(nome: str, linhas: list[dict]) -> None:
        with open(DADOS / nome, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(linhas[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(linhas)
        print(f"{nome}: {len(linhas)} linhas")

    escrever("obras.csv", [{
        "Codigo__c": cod[o], "Name": f"Obra {cod[o][3:]}", "Cliente__c": cli[obra[o]["cliente"]],
        "PO__c": po[obra[o]["po"]],
        "Tipo_Contrato__c": obra[o]["classe"] if obra[o]["classe"] in TIPOS else "Sem classificação",
        "Saldo_Faturar__c": round(obra[o]["saldo"], 2)} for o in ids])

    discs = []
    for r in d["obra_disc"]:
        sig = (r["disc"] or "SEM")[:10]
        rec = r["rec"]
        discs.append({
            "Chave__c": f"{cod[r['id']]}|{sig}", "Name": f"{cod[r['id']]} · {sig}",
            "Obra__r.Codigo__c": cod[r["id"]], "Sigla__c": sig, "Equipe__c": AREA.get(sig, "Outras"),
            "Receita__c": round(rec, 2),
            "Imposto_Pct__c": round(100 * r["imp"] / rec, 4) if rec > 0 else 19,
            "Meta_Margem_Pct__c": round(100 * r["meta"], 4),
            "TP_Dias__c": round(r["tp"], 2)})
    escrever("disciplinas.csv", discs)

    etapas: dict = defaultdict(lambda: defaultdict(float))
    for r in d["equipe"]:
        if r["id_obra"] not in cod:
            continue
        sig = (r["disciplina"] or "SEM")[:10]
        x = etapas[(cod[r["id_obra"]], sig, r["etapa"])]
        x["dr"] += r["dr"]; x["dt"] += r["dt"]; x["cc"] += r["cc"]; x["cr"] += r["cr"]
    escrever("custos_etapas.csv", [{
        "Chave__c": f"{c}|{s}|{e}", "Name": e, "Disciplina_Obra__r.Chave__c": f"{c}|{s}", "Etapa__c": e,
        "Dias_Realizados__c": round(x["dr"], 2), "Dias_Restantes__c": round(x["dt"], 2),
        "Custo_Consumido__c": round(x["cc"], 2), "Custo_Restante__c": round(x["cr"], 2)}
        for (c, s, e), x in sorted(etapas.items())])

    (PRIV / "correspondencia.json").write_text(json.dumps(
        {"obras": {cod[o]: {"id": o, "nome": obra[o]["nome"]} for o in ids},
         "clientes": {v: k for k, v in cli.items()}, "pos": {v: k for k, v in po.items()}},
        ensure_ascii=False, indent=1), encoding="utf-8")
    (PRIV / "referencia_python.json").write_text(json.dumps(
        {cod[o]: {"m_est": obra[o]["m_est"], "m_neg": obra[o]["m_neg"], "rec": obra[o]["rec"],
                  "ct": obra[o]["ct"]} for o in ids}, indent=1), encoding="utf-8")
    print("correspondência e referência gravadas em", PRIV)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
