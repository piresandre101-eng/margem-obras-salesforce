# Carrega os CSVs anonimizados (pasta dados/) no org, na ordem pai -> filho, por UPSERT
# (rodar de novo atualiza, nao duplica).
# Uso (na pasta do projeto):  .\scripts\carregar_dados.ps1      (org padrao: margem-dev)
# Obs.: arquivo propositalmente sem acentos - o Windows PowerShell 5.1 le .ps1 sem BOM como ANSI.
param([string]$Org = "margem-dev")
$ErrorActionPreference = "Stop"
$cargas = @(
    @{ Objeto = "Obra__c";            Arquivo = "dados/obras.csv";          Chave = "Codigo__c" },
    @{ Objeto = "Disciplina_Obra__c"; Arquivo = "dados/disciplinas.csv";    Chave = "Chave__c" },
    @{ Objeto = "Custo_Etapa__c";     Arquivo = "dados/custos_etapas.csv";  Chave = "Chave__c" }
)
foreach ($c in $cargas) {
    Write-Host "=== $($c.Objeto) ($($c.Arquivo))"
    sf data upsert bulk --sobject $c.Objeto --file $c.Arquivo --external-id $c.Chave --target-org $Org --wait 10 --line-ending LF
    if ($LASTEXITCODE -ne 0) { throw "Falha na carga de $($c.Objeto) - veja o arquivo de erros indicado acima." }
}
Write-Host "Carga concluida. Valide com: python scripts/validar_carga.py"
