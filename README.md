# Margem de Obras — Salesforce

Projeto pessoal (out/2026): réplica, na plataforma Salesforce, de um sistema de **margem e risco de contratos de
projetos de engenharia** que eu defini e uso no meu trabalho, originalmente em Python + Excel.
Os dados carregados no org são reais, com nomes de obras, clientes e responsáveis anonimizados, e sem nenhum
custo individual de colaborador.

> **Sobre o uso de IA.** Construí este projeto com o **Claude Code** (IA da Anthropic) como par de desenvolvimento.
> Eu defini o problema, as regras de negócio, o modelo de dados e os critérios de risco, decidi cada etapa,
> validei os resultados contra o sistema original e conduzi os testes. A IA escreveu a maior parte dos metadados e
> do código Apex. Estou estudando cada parte do que foi feito; o [Manual de Estudo](MANUAL_DE_ESTUDO.md) é o meu
> material, com os conceitos, o porquê de cada decisão, os erros reais do caminho e exercícios.

## O que faz
- Calcula, para cada obra e disciplina, **margem negociada** (até agora) e **margem estimada** (até o término),
  resultado projetado, orçamento de produção, cobertura do cronograma e **diária real × orçada**.
- Classifica obras e disciplinas em **grupos de risco** (em prejuízo, alto risco, risco moderado, positiva).
- Tira uma **foto semanal** (job agendado) e envia **alertas por e-mail** quando algo piora: mudança de grupo,
  queda de margem ≥ 5 p.p., nova obra já em risco, arquitetura sem escopo acima do limite.
- Telas, listas filtradas, relatórios e painel: obras por grupo de risco, **ranking das equipes** (margem ponderada),
  trabalho sem receita orçada, alertas por semana.

## Como foi construído
| Camada | Recurso Salesforce |
|---|---|
| Modelo | Objetos personalizados com Master-Detail em 3 níveis (Obra → Disciplina → Custo da Etapa) + histórico (Snapshot, Lookup) |
| Regras | **Campos de fórmula e roll-up summary** (sem código); parâmetros em **Custom Metadata** lidos pelas fórmulas |
| Automação | **Apex**: serviço de snapshot bulkificado, e-mail (`Messaging`), job `Schedulable` |
| Qualidade | 7 testes Apex, cobertura ~99%; validação da carga: margens no Salesforce = sistema original (0 diferenças em 86 obras) |
| Segurança | Permission Set com FLS; minimização de dados (custo agregado por etapa, nomes anonimizados) |
| Interface | Layouts por seção, compact layouts, list views, app Lightning, relatórios com fórmula de resumo, dashboard |
| Entrega | Projeto SFDX (source-driven), metadados gerados por script Python, Salesforce CLI, carga por Bulk API (upsert com External ID) |

## Estrutura
| Pasta / arquivo | Conteúdo |
|---|---|
| `force-app/` | Metadados (objetos, campos, layouts, Apex, relatórios, dashboard, permissões) |
| `scripts/gerar_metadados.py` | Gera os XMLs do modelo de dados, permissões e telas |
| `scripts/preparar_dados.py` · `carregar_dados.ps1` · `validar_carga.py` | Extração anonimizada, carga e validação |
| `scripts/apex/agendar_snapshot.apex` | Agenda o job semanal |
| `MANUAL_DE_ESTUDO.md` | Explicação completa do projeto |
| `ROTEIRO_DEMONSTRACAO.md` | Demonstração de 5 minutos |

## Rodar
```bash
sf org login web --alias margem-dev --set-default
python scripts/gerar_metadados.py
sf project deploy start --source-dir force-app
sf org assign permset --name Margem_Obras
sf apex run --file scripts/apex/agendar_snapshot.apex
```
Os dados não são versionados (ver seção 13 do manual).
