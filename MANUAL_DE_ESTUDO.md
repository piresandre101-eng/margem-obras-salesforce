# Manual de Estudo — Sistema de Margem de Obras no Salesforce

Este manual explica **o que foi construído, por que cada decisão foi tomada e como funciona por dentro**,
na ordem em que você deve estudar. Cada capítulo termina com exercícios práticos no seu org.

Projeto: pasta `margem-obras-salesforce` · Org: `margem-dev` (Developer Edition) · API 67.0

---

## Sumário

1. [O ponto de partida: o sistema que já existia](#1-o-ponto-de-partida)
2. [Conceitos do Salesforce que você precisa conhecer](#2-conceitos-do-salesforce)
3. [Ferramentas: org, CLI e projeto SFDX](#3-ferramentas)
4. [O modelo de dados](#4-o-modelo-de-dados)
5. [A lógica de margem em campos de fórmula e roll-up](#5-a-lógica-de-margem)
6. [Parâmetros sem código: Custom Metadata](#6-custom-metadata)
7. [Segurança: Permission Set](#7-segurança)
8. [Carga de dados: anonimização e upsert](#8-carga-de-dados)
9. [Apex: histórico semanal, alertas e agendamento](#9-apex)
10. [Testes em Apex](#10-testes)
11. [Relatórios e dashboard](#11-relatórios-e-dashboard)
12. [O que deu errado no caminho (e o que isso ensina)](#12-o-que-deu-errado)
13. [Como operar no dia a dia](#13-operação)
14. [Próximos passos para continuar aprendendo](#14-próximos-passos)
15. [Glossário](#15-glossário)

---

## 1. O ponto de partida

O escritório de projetos de engenharia onde trabalho tem um sistema em **Python + Excel** que calcula a margem
de cada obra a partir do cronograma (planilha de cronograma da operação). As regras de negócio são:

| Conceito | Regra |
|---|---|
| Receita | $ orçado + aditivos, por obra e disciplina |
| Impostos | 19% da receita (ISS, IRPJ, CSLL…) |
| Meta de margem | 20% da receita |
| **Orçamento de Produção** | receita × (1 − 19% − 20%) = 61%: o que pode virar dias de trabalho |
| Margem negociada | (receita − impostos − custo **consumido**) ÷ receita: "até agora" |
| **Margem estimada** | (receita − impostos − custo consumido − custo **restante lançado**) ÷ receita: leitura principal |
| Diária orçada / real | orçamento ÷ dias previstos (TP) / custo ÷ dias lançados |
| Grupos de risco | em prejuízo (< 0), alto risco (< 10% ou o prazo restante leva ao prejuízo), moderado (< 20% ou o prazo restante leva abaixo da meta), positiva |
| Alertas semanais | piorou de grupo, margem caiu ≥ 5 p.p., nova obra já em risco, arquitetura sem escopo > 3% |

**O objetivo deste projeto** foi reproduzir exatamente essas regras no Salesforce, usando o jeito "Salesforce"
de fazer as coisas: **configuração primeiro, código só onde é necessário**.

> Pergunta para fixar: por que a margem negociada costuma ser maior que a estimada numa obra em andamento?
> (Resposta: porque ainda não inclui o custo do trabalho que falta.)

---

## 2. Conceitos do Salesforce

| Conceito | O que é | Equivalente no sistema antigo |
|---|---|---|
| **Org** | Uma instância do Salesforce: banco de dados + aplicação + configuração | A pasta inteira do projeto |
| **Objeto** (`__c`) | Uma tabela. Objetos personalizados terminam em `__c` | Uma aba de planilha |
| **Campo** | Uma coluna. Pode ser dado, **fórmula** ou **roll-up** | Uma coluna, com valor ou fórmula |
| **Registro** | Uma linha | Uma linha |
| **Relacionamento** | Ligação entre objetos: **Lookup** (fraca) ou **Master-Detail** (forte) | PROCV/SUMIFS entre abas |
| **Metadados** | A *configuração* do org (objetos, campos, relatórios, código), descrita em XML | O código Python e o layout das abas |
| **Apex** | Linguagem de programação do Salesforce (parecida com Java) | O Python |
| **SOQL** | Linguagem de consulta (parecida com SQL) | Ler a planilha |
| **Custom Metadata** (`__mdt`) | Configuração que se edita sem código e viaja junto com o deploy | A aba Metas / constantes |
| **Permission Set** | Conjunto de permissões atribuído a usuários | Quem pode abrir a pasta |

**A ideia central:** no Salesforce você descreve *o quê* (objetos, campos, fórmulas, relatórios) como metadados, e
a plataforma cuida de *como* (banco, telas, cálculo, segurança). Você só escreve código para o que a configuração não resolve.

---

## 3. Ferramentas

### 3.1 Developer Edition × Starter
O primeiro org criado foi um **Base Edition (Salesforce Starter, trial de 30 dias)**: quase nenhum objeto personalizado,
sem Custom Metadata e sem Apex. O **Developer Edition** é gratuito, não expira e tem tudo isso. **Lição:** confira a edição
em *Configuração → Informações da empresa* antes de começar qualquer projeto.

### 3.2 Salesforce CLI (`sf`)
Ferramenta de linha de comando que conversa com o org. Comandos usados neste projeto:

| Comando | Para quê |
|---|---|
| `sf org login web --alias margem-dev --set-default` | Conectar a um org (abre o navegador) |
| `sf org list` | Ver os orgs conectados |
| `sf project generate --name ...` | Criar a estrutura de um projeto SFDX |
| `sf project deploy start --source-dir force-app` | Enviar metadados (objetos, código…) para o org |
| `sf project deploy start ... --test-level RunSpecifiedTests --tests X` | Deploy rodando testes |
| `sf org assign permset --name Margem_Obras` | Atribuir um Permission Set ao seu usuário |
| `sf data query --query "SELECT ..."` | Consultar dados (SOQL) |
| `sf data upsert bulk --sobject X --file Y.csv --external-id Z` | Carregar/atualizar dados em massa |
| `sf apex run --file script.apex` | Executar Apex anônimo (ex.: agendar o job) |
| `sf org open` | Abrir o org no navegador |

### 3.3 Projeto SFDX
```
margem-obras-salesforce/
├── sfdx-project.json            ← define a pasta de metadados (force-app) e a versão de API
├── force-app/main/default/      ← TODOS os metadados (o "código-fonte" do org)
│   ├── objects/                 ← objetos e campos (1 arquivo XML por campo)
│   ├── customMetadata/          ← registros de Custom Metadata (parâmetros, áreas)
│   ├── classes/                 ← Apex (.cls) e seus metadados (.cls-meta.xml)
│   ├── permissionsets/          ← Permission Set
│   ├── tabs/, applications/     ← abas e o app Lightning
│   ├── reports/, dashboards/    ← relatórios e painel
├── scripts/
│   ├── gerar_metadados.py       ← GERA os XMLs de objetos/campos/permissões/app (fonte da verdade do modelo)
│   ├── preparar_dados.py        ← extrai e anonimiza os dados reais em CSV
│   ├── carregar_dados.ps1       ← carrega os CSVs no org
│   ├── validar_carga.py         ← confere margens Salesforce × sistema original
│   ├── resultado_deploy.py      ← resume o resultado de um deploy
│   └── apex/agendar_snapshot.apex
└── dados/                       ← CSVs e correspondência de nomes (fora do git; nunca publicar)
```
**Por que metadados como arquivo:** o org pode ser recriado do zero com um comando, você versiona tudo no git
(como num projeto de software) e consegue revisar mudanças linha a linha. Isso se chama **source-driven development**.

**Por que um script Python gera os XMLs:** escrever 80 arquivos de campo à mão é repetitivo e sujeito a erro. O script
`gerar_metadados.py` descreve o modelo uma vez (ex.: as mesmas fórmulas de margem servem para Obra e para Disciplina)
e gera os XMLs. **Regra:** mudou o modelo → altere o script → rode → faça o deploy.

### Exercícios
1. Rode `sf org list` e identifique o seu org padrão.
2. Abra `force-app/main/default/objects/Obra__c/fields/Margem_Estimada__c.field-meta.xml` e localize a fórmula.
3. Rode `sf org open` e encontre o app **Margem de Obras** no App Launcher (ícone de 9 pontos).

---

## 4. O modelo de dados

```
Obra__c  (1 por contrato)
  │  Master-Detail
  └── Disciplina_Obra__c  (obra × disciplina: receita, % impostos, % meta, TP)
        │  Master-Detail
        └── Custo_Etapa__c  (obra × disciplina × etapa: dias e custos do cronograma)

Snapshot_Semanal__c  (foto semanal; Lookup para Obra e Disciplina)
Parametro_Margem__mdt / Area_Disciplina__mdt  (configuração)
```

### 4.1 Por que três níveis
O dado nasce em níveis diferentes: a **receita** é por obra × disciplina (CADASTRO OBRAS) e o **custo** por tarefa
(CRONO GERAL). Guardar cada coisa no nível em que nasce e **somar para cima** evita duplicar números.

### 4.2 Por que o custo é por *etapa* e não por *tarefa/pessoa*
O cronograma tem custo por colaborador. Carregar isso permitiria deduzir o salário de cada pessoa (dado pessoal, LGPD).
Agregando por **obra × disciplina × etapa**, a margem fica **idêntica** e nenhum valor individual vai para a nuvem.
Esse é um exemplo de **minimização de dados**: guarde só o necessário para o objetivo.

### 4.3 Master-Detail × Lookup
| | Master-Detail | Lookup |
|---|---|---|
| Vínculo | Forte: o filho não existe sem o pai | Fraco: pode ficar vazio |
| Excluir o pai | Exclui os filhos | Mantém os filhos |
| Segurança | Filho herda do pai (`ControlledByParent`) | Independente |
| **Roll-up summary** | **Sim** (soma, contagem, mín., máx. dos filhos) | Não (só via código/Flow) |

Obra → Disciplina → Etapa usa **Master-Detail** porque precisamos de **roll-up** (somar custos para cima) e uma etapa
não faz sentido sem a disciplina. O **Snapshot** usa **Lookup** porque o histórico deve sobreviver mesmo se a obra for apagada.

### 4.4 Chaves externas (External ID)
`Obra__c.Codigo__c` (ex.: `OB-001`), `Disciplina_Obra__c.Chave__c` (`OB-001|EC`) e `Custo_Etapa__c.Chave__c`
(`OB-001|EC|EX`) são marcados como **External ID + único**. Eles permitem:
- **upsert**: recarregar o mesmo CSV atualiza em vez de duplicar;
- ligar filho ao pai **pelo código**, sem conhecer o Id do Salesforce (coluna `Obra__r.Codigo__c` no CSV).

### Exercícios
1. Em *Configuração → Gerenciador de Objetos → Obra*, veja "Campos e relacionamentos" e identifique os tipos: Texto,
   Moeda, Fórmula, Resumo de totalização (roll-up).
2. Por que `Sigla__c` é obrigatório e `Equipe__c` não? (Dica: veja a seção 7.)

---

## 5. A lógica de margem

Toda a regra de margem e risco está em **campos**, não em código. Assim ela é **visível** (qualquer admin lê a fórmula),
**instantânea** (recalcula sozinha quando um dado muda) e **auditável**.

### 5.1 Roll-up summary (somar para cima)
Na Disciplina: `Custo_Consumido__c = SOMA(Custo_Etapa__c.Custo_Consumido__c)`, idem para custo restante e dias.
Na Obra: `Receita__c = SOMA(Disciplina_Obra__c.Receita__c)`, `Custo_Consumido__c = SOMA(Disciplina.Custo_Consumido__c)`…
Repare que a Obra soma um campo que **já é roll-up** na Disciplina: roll-up em dois níveis funciona no Salesforce.

### 5.2 Fórmulas (as mesmas em Obra e Disciplina)
```
Custo_Total__c          = Custo_Consumido__c + Custo_Restante__c
Resultado_Projetado__c  = Receita__c - Impostos__c - Custo_Total__c
Margem_Negociada__c     = IF(Receita__c > 0, (Receita__c - Impostos__c - Custo_Consumido__c) / Receita__c, NULL)
Margem_Estimada__c      = IF(Receita__c > 0, (Receita__c - Impostos__c - Custo_Total__c) / Receita__c, NULL)
Orcamento_Producao__c   = Receita__c * (1 - Imposto_Pct__c - Meta_Margem_Pct__c)     (na Disciplina; somado na Obra)
Diaria_Orcada__c        = IF(AND(TP > 0, Orçamento > 0), Orçamento / TP, NULL)
Diaria_Real__c          = IF(dias lançados > 0, Custo_Total / dias lançados, NULL)
Dias_TP_Nao_Lancados__c = IF(AND(ativa, TP > 0), MAX(0, TP - dias realizados - dias restantes), 0)
Em_Andamento__c         = OR(Saldo_Faturar__c > 0, Dias_Restantes__c > 0)
```
Detalhes que importam:
- **`IF(Receita > 0, …, NULL)`**: evita divisão por zero e deixa a margem *em branco* (não 0%) quando não há receita.
- **Campos Percent:** na fórmula o valor é fração (`0.20`); na tela aparece `20%`; **no Apex e na API aparece `20`**
  (veja a seção 9).
- **`formulaTreatBlanksAs`**: `BlankAsZero` nas contas (vazio = 0) e `BlankAsBlank` no grupo de risco (para distinguir "sem receita").

### 5.3 O grupo de risco por fórmula
```
IF(ISBLANK(Margem_Estimada__c), "Sem receita",
IF(Margem_Estimada__c < 0, "1. Em prejuízo",
IF(OR(Margem_Estimada__c < [limite alto risco],
      AND(Em_Andamento__c, dias do TP não lançados > dias até o prejuízo)), "2. Alto risco",
IF(OR(Margem_Estimada__c < Meta,
      AND(Em_Andamento__c, dias do TP não lançados > dias que cabem no orçamento)), "3. Risco moderado",
"4. Positiva"))))
```
"Dias até o prejuízo" = resultado ÷ diária real; "dias que cabem no orçamento" = (orçamento − custo) ÷ diária real.
O número no início ("1.", "2."…) serve para **ordenar** nos relatórios e para o Apex comparar grupos (seção 9).

### 5.4 Verificação
O teste `formulasReproduzemAMargemDoSistemaOriginal` cria uma obra com receita 100.000 e custo 30.000 e confere:
margem estimada 51%, negociada 61%, orçamento 61.000, diária real 300, diária orçada 610. É a prova de que as fórmulas
implementam a mesma regra do sistema Python.

### Exercícios
1. Crie manualmente uma Obra, uma Disciplina (receita 50.000, impostos 19, meta 20, TP 50) e uma Etapa (custo consumido
   10.000, restante 5.000, dias 20 + 10). Calcule a margem estimada no papel e confira na tela. (Resposta: 51%.)
2. Mude o custo restante para 30.000 e observe o grupo de risco mudar. Qual grupo e por quê?
3. Desafio: crie um campo de fórmula `Margem_vs_Meta__c` (margem estimada − meta) na Obra **pela interface** e depois
   rode `sf project retrieve start --metadata CustomField:Obra__c.Margem_vs_Meta__c` para ver o XML gerado.

---

## 6. Custom Metadata

`Parametro_Margem__mdt` (registro **Padrao**) guarda: meta 20%, alto risco 10%, queda de alerta 5 p.p., limite de
arquitetura sem escopo 3%, cobertura mínima 90%. `Area_Disciplina__mdt` guarda sigla → equipe e nome (14 registros).

**Por que Custom Metadata e não um objeto comum ou valor fixo na fórmula:**
- as fórmulas leem direto: `$CustomMetadata.Parametro_Margem__mdt.Padrao.Limite_Alto_Risco__c`;
- é **metadado**: vai junto no deploy (o org novo já nasce configurado), e não é "dado" que alguém apaga sem querer;
- o Apex lê sem gastar consulta: `Parametro_Margem__mdt.getInstance('Padrao')`.

### Exercício
Em *Configuração → Tipos de metadados personalizados → Parâmetro de Margem → Gerenciar registros*, mude o limite de
alto risco para 15% e veja obras mudarem de grupo nos relatórios **sem nenhum deploy**. Depois volte para 10%.

---

## 7. Segurança

No Salesforce, ter o objeto não basta: cada **campo** precisa de permissão de leitura/edição (**FLS — Field-Level
Security**). Campos criados por deploy nascem **invisíveis** para todos os perfis. Por isso existe o Permission Set
`Margem_Obras`, gerado pelo script, que dá:
- acesso total aos 4 objetos;
- leitura em todos os campos e edição só nos campos de dado (fórmulas e roll-ups são só leitura por natureza);
- visibilidade das abas e do app.

Duas regras que o script respeita (e que causam erro de deploy se ignoradas):
- **campos obrigatórios** e **Master-Detail** não entram no Permission Set (o Salesforce já os torna sempre visíveis);
- Permission Set é o jeito moderno: em vez de alterar perfis, você **soma** permissões a quem precisa.

Atribuição: `sf org assign permset --name Margem_Obras`.

---

## 8. Carga de dados

### 8.1 Preparação (`scripts/preparar_dados.py`)
1. Reaproveita o **mesmo cálculo do sistema original** (`coletar_dados` do projeto KPIs). Não há reimplementação, então
   não há risco de divergir.
2. **Anonimiza:** obras → `OB-001` / "Obra 001"; clientes → "Cliente 01"; P.O.s → "P.O. A". Valores reais, aprovados.
3. **Agrega o custo por etapa** (seção 4.2).
4. Grava os CSVs em `dados/` e, em `dados/privado/`, a tabela de correspondência e as margens de referência.
   `dados/` está no `.gitignore`.
5. Confere que **nenhum nome real** aparece nos CSVs.

### 8.2 Carga (`scripts/carregar_dados.ps1`)
Ordem **pai → filho** (Obra, Disciplina, Etapa), por **upsert** pela chave externa, usando a **Bulk API** (feita para
grandes volumes). Os filhos se ligam ao pai pela coluna de relacionamento: `Obra__r.Codigo__c`, `Disciplina_Obra__r.Chave__c`.

### 8.3 Validação (`scripts/validar_carga.py`)
Consulta no Salesforce, obra a obra, receita, custo, margem estimada e negociada **calculadas pelas fórmulas** e compara
com a referência do sistema Python. Tolerância: R$ 1 e 0,01 p.p. Se bater, as fórmulas e a carga estão corretas.

> **Status:** os CSVs estão prontos (86 obras, 637 disciplinas, 1.092 etapas; base de 16/09/2026). O envio para o org
> ficou para você executar (o assistente de IA não envia dados da empresa a serviços externos por conta própria).
> Ver seção 13.

---

## 9. Apex

O que a configuração **não** resolve: guardar o histórico (fórmula não "lembra" o valor da semana passada), comparar com a
semana anterior, enviar e-mail e rodar no horário. Para isso há três classes:

### 9.1 `SnapshotSemanalService`: a lógica
1. Apaga as fotos de hoje (**idempotência**: rodar duas vezes no mesmo dia não duplica).
2. Descobre a data da última foto anterior (`SELECT MAX(Data__c) …`) e carrega essas fotos num `Map` por chave.
3. Uma única consulta traz obras ativas **com suas disciplinas** (subconsulta `(SELECT … FROM Disciplinas__r)`).
4. Para cada obra e disciplina cria um `Snapshot_Semanal__c` com margem, resultado e grupo (lidos das **fórmulas**).
5. Calcula o alerta comparando com a foto anterior.
6. **Um único `insert`** de todos os registros.

Conceitos de Apex que aparecem aqui:
- **Bulkificação:** nunca faça consulta (SOQL) ou gravação (DML) dentro de laço. O Salesforce tem **limites por transação**
  (100 consultas, 150 gravações). O serviço faz 3 consultas e 2 gravações, qualquer que seja o número de obras.
- **`with sharing`:** respeita as regras de compartilhamento do usuário.
- **`@TestVisible`:** deixa métodos privados acessíveis aos testes.
- **Percent no Apex vem como número inteiro** (`48.5` = 48,5%). Por isso a queda de 5 p.p. é comparada direto
  (`anterior - atual >= 5`), e o limite de arquitetura usa `custo / receita * 100 > 3`.

### 9.2 `AlertaEmailService`: o e-mail
Monta uma tabela HTML com os alertas e envia com `Messaging.SingleEmailMessage` para o usuário que agendou
(`setTargetObjectId(UserInfo.getUserId())`). Só envia se houver alerta. Textos passam por `escapeHtml4()` (evita HTML injetado).
No sistema original o envio é segmentado por P.O. e líder; aqui os P.O.s são anônimos e não têm usuário no org
(veja Próximos passos).

### 9.3 `SnapshotSemanalAgendado`: o agendamento
Implementa `Schedulable`. A expressão **cron** `'0 0 8 ? * MON'` = segundo 0, minuto 0, 8h, qualquer dia do mês, todo mês,
segunda-feira. Agendar uma vez: `sf apex run --file scripts/apex/agendar_snapshot.apex`. Para ver ou cancelar:
*Configuração → Trabalhos agendados*.

### Exercícios
1. Em *Configuração → Console do desenvolvedor → Debug → Open Execute Anonymous*, rode
   `System.debug(SnapshotSemanalService.executar(Date.today()).snapshots);` e veja os registros em *Snapshots Semanais*.
2. Altere um custo e rode de novo com `Date.today().addDays(7)`. Que alertas aparecem?
3. Explique por que o método começa com `delete [SELECT … WHERE Data__c = :hoje]`.

---

## 10. Testes

O Salesforce **exige** testes: para ir a produção, pelo menos **75% das linhas de Apex** precisam ser executadas por testes
(o projeto tem ~99%). Testes rodam isolados: os dados criados neles somem ao final e **não veem os dados reais do org**.

`SnapshotSemanalServiceTest` tem 7 testes:

| Teste | O que prova |
|---|---|
| `formulasReproduzemAMargemDoSistemaOriginal` | As fórmulas calculam igual ao sistema Python |
| `gruposDeRisco` | Margens −9%, 6% e 16% caem em prejuízo, alto risco e moderado |
| `primeiraFotoGravaSnapshotsEAlertaObraJaEmRisco` | Primeira semana: grava fotos e alerta "nova obra em risco" |
| `segundaSemanaDetectaPioraEQuedaEIdempotencia` | Detecta "piorou de grupo" e não duplica fotos no mesmo dia |
| `quedaDeMargemSemTrocarDeGrupo` | Queda de 6 p.p. alerta; queda de 3 p.p. não |
| `arquiteturaSemEscopoAcimaDoLimite` | AQ sem receita a 5% da receita da obra gera alerta |
| `jobAgendadoEEmail` | O job agenda e envia exatamente 1 e-mail quando há alerta |

Padrões usados: `Test.startTest()` / `Test.stopTest()` (dá limites novos e executa o que é assíncrono), a classe `Assert`
(`Assert.areEqual`, `Assert.isTrue`) e um método auxiliar (`criarObra`) para montar dados de teste.

Rodar: `sf apex run test --class-names SnapshotSemanalServiceTest --result-format human --code-coverage --target-org margem-dev`

---

## 11. Relatórios e dashboard

| Relatório | Tipo de relatório | Destaques |
|---|---|---|
| Obras ativas por grupo de risco | `CustomEntity$Obra__c` | Agrupado por `Grupo_Risco__c`, filtro ativas com receita, **fórmula de resumo** "margem ponderada" |
| Ranking das equipes e subdisciplinas | `CustomEntityCustomEntity$Obra__c$Disciplina_Obra__c` | Agrupado por Equipe e Sigla, margem ponderada = Σ resultado ÷ Σ receita |
| Alertas por semana | `CustomEntity$Snapshot_Semanal__c` | Agrupado por data e tipo de alerta |

**Fórmula de resumo** (`Resultado_Projetado__c:SUM / Receita__c:SUM`): calcula a margem **ponderada pela receita** do
grupo, não a média das margens. Uma obra de R$ 2 mil não pesa o mesmo que uma de R$ 1 milhão (mesma regra do sistema original).

O **dashboard** "Painel de Margem de Obras" reúne os três, usando o gráfico definido em cada relatório (`useReportChart`).
É do tipo `LoggedInUser` (dinâmico): cada pessoa vê com as próprias permissões.

### 11.1 Telas: layout × página Lightning (duas camadas diferentes)

| Camada | O que controla | Neste projeto |
|---|---|---|
| **Page Layout** (`layouts/`) | *Quais campos* aparecem, em que **seções**, e quais listas relacionadas | Seções "Margem e risco", "Receita e custo", "Prazo e produtividade" |
| **Compact Layout** (`compactLayouts/`) | Os campos de **destaque** no topo do registro | Grupo de risco, margem estimada, resultado, P.O., receita |
| **List View** (`listViews/`) | Listas filtradas na aba do objeto | "Obras ativas em prejuízo", "em alto risco"… |
| **Lightning Page / FlexiPage** (`flexipages/`) | A **moldura** da página: regiões, abas, componentes | Página da Obra com abas e quadro "Como ler"; página inicial com o painel |

Só mudar o *layout* não muda a "cara" da página: ela continua na moldura padrão (cabeçalho + Detalhes/Relacionado).
A página Lightning é montada no **Lightning App Builder** (engrenagem → Editar página), ou como metadado XML, como aqui.

- `Obra_Pagina` (tipo **RecordPage**, modelo de cabeçalho + coluna principal + lateral): `force:highlightsPanel` (usa o
  compact layout), um `flexipage:tabset` com três `flexipage:tab` ("Margem e risco" = `force:detailPanel`, ou seja, o
  page layout; "Disciplinas" e "Histórico semanal" = `force:relatedListSingleContainer`) e um `flexipage:richText` na lateral.
- `Inicio_Margem_de_Obras` (tipo **AppPage**): texto de apresentação + `desktopDashboards:embeddedDashboard` (o painel).
  Uma **aba** (`tabs/Inicio_Margem_de_Obras.tab-meta.xml`) a coloca como primeiro item do app.
- **Ativação:** uma página Lightning só aparece depois de ativada. Aqui a ativação está no próprio app
  (`<actionOverrides>` com `type Flexipage` para a ação **View** de `Obra__c`), então ela vale **dentro do app Margem de Obras**.
  No App Builder o equivalente é "Ativação → Padrão do app".

### Exercício
Abra uma obra → engrenagem → **Editar página**. Arraste um componente "Gráfico de relatório" para a lateral, escolha
"Ranking das equipes e subdisciplinas", salve e veja o resultado. Depois rode
`sf project retrieve start --metadata FlexiPage:Obra_Pagina` e compare o XML com a versão anterior (`git diff`).

---

## 12. O que deu errado

Erros reais deste projeto e o que eles ensinam:

| Erro | Causa | Lição |
|---|---|---|
| "reached maximum number of custom objects" e "sem permissão Personalizar aplicativo" | Org criado era Salesforce **Starter** (Base Edition), não Developer Edition | Confira a edição do org antes de começar |
| "Report is Obsolete" no relatório de disciplinas | Objeto filho de Master-Detail **não tem tipo de relatório próprio** | Para relatar o filho, use o tipo pai → filho (`CustomEntityCustomEntity$Pai$Filho`) e `CHILD_NAME` |
| Fórmula de texto com `<length>` | Campo de fórmula não aceita tamanho | Os XMLs de metadados têm regras por tipo; o deploy avisa |
| Permission Set rejeitaria campos obrigatórios e Master-Detail | Esses campos são sempre visíveis | O gerador os exclui do Permission Set |
| Percent: 0.20 na fórmula × 20 no Apex | Representações diferentes do mesmo campo | Sempre confira a unidade ao comparar valores no código |
| `.ps1` com "Token inesperado" e textos como `â€”` / `Ã` | O Windows PowerShell 5.1 lê `.ps1` **sem BOM** como ANSI; acentos e travessão em UTF-8 viram lixo e quebram as aspas | Em scripts `.ps1`, use só ASCII (ou salve como "UTF-8 com BOM"). Para rodar scripts pela 1ª vez: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| Planilha na nuvem travada no momento da extração | Arquivo aberto/sincronizando | A carga usou a cópia de 16/09; basta rodar `preparar_dados.py` de novo depois |

Ciclo de trabalho que resolveu tudo: **deploy → ler o erro → ajustar o gerador → deploy de novo**. O deploy é atômico:
se um componente falha, nada é aplicado, e o org nunca fica pela metade.

---

## 13. Operação

### Primeira carga (você executa)
```powershell
cd <pasta>\margem-obras-salesforce
.\scripts\carregar_dados.ps1          # carrega obras, disciplinas e etapas
python scripts\validar_carga.py       # deve mostrar "diferenças: 0"
sf apex run --file scripts\apex\agendar_snapshot.apex   # agenda a foto de segunda, 8h
sf org open                            # App Launcher → Margem de Obras
```
Depois, em Execute Anonymous: `SnapshotSemanalService.executar(Date.today());` para criar a primeira foto.

### Atualizar os dados
```powershell
python scripts\preparar_dados.py "<pasta do projeto Python original>" "<planilha de cronograma>"
.\scripts\carregar_dados.ps1
python scripts\validar_carga.py
```
O upsert atualiza o que mudou e cria o que é novo (obras removidas não são apagadas, então exclua manualmente se precisar).

### Mudar o modelo
Edite `scripts/gerar_metadados.py` → `python scripts/gerar_metadados.py` → `sf project deploy start --source-dir force-app`.

### Mudar o Apex
Edite a classe e o teste → `sf project deploy start --source-dir force-app --test-level RunSpecifiedTests --tests SnapshotSemanalServiceTest`.

---

## 14. Próximos passos

Sugestões em ordem de aprendizado, todas possíveis no Developer Edition:

1. **Git:** `git init` nesta pasta e um commit por etapa. É o padrão de mercado em projetos Salesforce.
2. **Lightning App Builder:** monte uma página de registro da Obra com os campos de margem em destaque e a lista de disciplinas.
3. **Flow:** recrie o alerta de "nova obra em risco" como um *Record-Triggered Flow* e compare com o Apex.
4. **Usuários por P.O.:** crie usuários e um campo Lookup(User) em P.O. para e-mails segmentados como no sistema original.
5. **LWC (Lightning Web Component):** um componente que mostra o "semáforo" da carteira na página inicial.
6. **Validation Rules:** impedir `Imposto_Pct__c + Meta_Margem_Pct__c > 100`.
7. **Trailhead** (trailhead.salesforce.com), trilhas gratuitas e alinhadas a este projeto: *Data Modeling*, *Formulas and
   Validations*, *Apex Basics & Database*, *Apex Testing*, *Reports & Dashboards*, *Salesforce DX*.
8. **Certificação:** este projeto cobre boa parte do conteúdo de *Salesforce Certified Platform App Builder* e uma
   introdução ao *Platform Developer I*.

---

## 15. Glossário

| Termo | Significado |
|---|---|
| Org | Instância do Salesforce (seu ambiente) |
| `__c` / `__r` / `__mdt` | Sufixos: campo/objeto personalizado / relacionamento / Custom Metadata |
| Master-Detail | Relacionamento forte, com roll-up e segurança herdada |
| Lookup | Relacionamento fraco |
| Roll-up summary | Campo que soma/conta registros filhos de Master-Detail |
| Fórmula | Campo calculado na leitura, nunca gravado |
| External ID | Campo marcado como chave externa, usado em upsert e ligações por código |
| Upsert | Inserir ou atualizar conforme a chave |
| Bulk API | API para cargas grandes, em lotes |
| FLS | Field-Level Security: permissão por campo |
| Permission Set | Pacote de permissões somado ao perfil do usuário |
| SOQL | Linguagem de consulta do Salesforce |
| DML | Operações de gravação (insert, update, delete, upsert) |
| Governor limits | Limites de recursos por transação no Apex |
| Bulkificação | Escrever Apex sem consulta/gravação dentro de laços |
| Schedulable / cron | Interface e expressão para agendar Apex |
| Deploy | Enviar metadados do projeto para o org |
| SFDX / `sf` | Formato de projeto e linha de comando do Salesforce |
