"""Resume o JSON de `sf project deploy start --json` (status, falhas, testes, cobertura).

Uso: sf project deploy start ... --json > deploy.json ; python scripts/resultado_deploy.py deploy.json
"""
import json
import sys

d = json.load(open(sys.argv[1], encoding="utf-8"))
r = d.get("result", d)
print("status:", r.get("status"), "| sucesso:", r.get("success"))
det = r.get("details", {}) or {}
for f in (det.get("componentFailures") or []):
    print("ERRO", f.get("componentType"), f.get("fullName"), f.get("lineNumber"), f.get("problem"))
t = det.get("runTestResult", {}) or {}
if t:
    print("testes:", t.get("numTestsRun"), "| falhas:", t.get("numFailures"))
    for f in (t.get("failures") or []):
        print("FALHA", f.get("methodName"), f.get("message"))
    for c in (t.get("codeCoverage") or []):
        print("cobertura", c.get("name"), int(c["numLocations"]) - int(c["numLocationsNotCovered"]), "/", c["numLocations"])
if "message" in d:
    print(d["message"])
