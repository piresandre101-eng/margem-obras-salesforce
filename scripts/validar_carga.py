"""Confere se as margens calculadas PELO SALESFORCE (campos de fórmula/roll-up) batem com o sistema original.

Uso: python scripts/validar_carga.py [alias-do-org]
Compara, obra a obra, Receita, Custo Total, Margem Estimada e Margem Negociada com dados/privado/referencia_python.json
(gerado por preparar_dados.py a partir do sistema Python original). Tolerância: R$ 1 e 0,01 p.p.
"""
import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
org = sys.argv[1] if len(sys.argv) > 1 else "margem-dev"
ref = json.loads((RAIZ / "dados" / "privado" / "referencia_python.json").read_text(encoding="utf-8"))

saida = subprocess.run(
    ["sf", "data", "query", "--target-org", org, "--json", "--query",
     "SELECT Codigo__c, Receita__c, Custo_Total__c, Margem_Estimada__c, Margem_Negociada__c, Grupo_Risco__c, "
     "Em_Andamento__c FROM Obra__c"],
    capture_output=True, text=True, encoding="utf-8", shell=(sys.platform == "win32"))
registros = json.loads(saida.stdout)["result"]["records"]
sf = {r["Codigo__c"]: r for r in registros}

difs, faltando = [], [c for c in ref if c not in sf]
for cod, esperado in ref.items():
    r = sf.get(cod)
    if not r:
        continue
    checks = [("receita", r["Receita__c"] or 0, esperado["rec"], 1.0),
              ("custo", r["Custo_Total__c"] or 0, esperado["ct"], 1.0)]
    if esperado["m_est"] is not None:
        checks += [("m_est", (r["Margem_Estimada__c"] or 0) / 100, esperado["m_est"], 1e-4),
                   ("m_neg", (r["Margem_Negociada__c"] or 0) / 100, esperado["m_neg"], 1e-4)]
    for nome, obtido, esp, tol in checks:
        if abs(obtido - esp) > tol:
            difs.append(f"{cod} {nome}: Salesforce {obtido:.4f} × original {esp:.4f}")

print(f"obras no Salesforce: {len(sf)} | na referência: {len(ref)} | faltando: {len(faltando)}")
print(f"diferenças: {len(difs)}")
for d in difs[:20]:
    print("  ", d)
grupos = {}
for r in registros:
    if r["Em_Andamento__c"] and (r["Receita__c"] or 0) > 0:
        grupos[r["Grupo_Risco__c"]] = grupos.get(r["Grupo_Risco__c"], 0) + 1
print("obras ativas por grupo:", dict(sorted(grupos.items())))
sys.exit(1 if difs or faltando else 0)
