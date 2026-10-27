# Roteiro de demonstração (5 minutos)

Para mostrar o projeto ao vivo numa entrevista. Antes: faça login no org, abra o app **Margem de Obras** e deixe
uma aba com o painel e outra com o VS Code no projeto. Tenha gerado ao menos uma foto semanal
(`SnapshotSemanalService.executar(Date.today());` no Execute Anonymous).

| Tempo | O que mostrar | O que dizer |
|---|---|---|
| **0:00 – 0:40** | Este README | "Este é um projeto pessoal: levei para o Salesforce o sistema de margem de contratos que eu criei no meu trabalho, em Python + Excel. Construí com IA, o Claude Code, como par de desenvolvimento. Eu defini as regras, o modelo e validei tudo, e estou estudando cada parte; tenho um manual de estudo no repositório." |
| **0:40 – 1:40** | Painel de Margem de Obras | "Aqui está a carteira: obras ativas por grupo de risco, ranking das cinco equipes pela margem ponderada e os alertas da semana. A margem é ponderada pela receita, com fórmula de resumo no relatório, para que uma obra pequena não distorça a média." |
| **1:40 – 2:40** | Lista "Obras ativas em prejuízo" → abrir a pior obra | "Os destaques no topo mostram grupo, margem estimada e resultado. A margem negociada é o resultado até agora; a estimada inclui o custo restante do cronograma. Nenhum desses campos é código: são fórmulas e roll-ups." Rolar até "Prazo e produtividade": "diária real versus orçada: se passa de 1, cada dia custa mais que o previsto." |
| **2:40 – 3:20** | Lista relacionada de disciplinas da obra | "A receita nasce por disciplina e o custo por tarefa, então modelei Obra → Disciplina → Custo da Etapa em master-detail e somo para cima com roll-up. Agreguei o custo por etapa de propósito, para não expor custo individual de colaborador." |
| **3:20 – 4:00** | Configuração → Tipos de metadados personalizados → Parâmetro de Margem | "Meta e limites de risco estão em Custom Metadata, e as fórmulas leem daqui. Mudar o limite de alto risco reclassifica as obras sem deploy." |
| **4:00 – 4:40** | VS Code: `SnapshotSemanalService.cls` e o teste | "Código só onde a configuração não resolve: fórmula não guarda histórico. Toda segunda um job agendado tira a foto, compara com a anterior e manda e-mail se algo piorou. É bulkificado (3 consultas, qualquer volume) e tem 7 testes; um deles prova que as fórmulas reproduzem o sistema original." |
| **4:40 – 5:00** | Fechamento | "Validei a carga obra a obra contra o sistema original: zero diferenças nas 86 obras. Próximos passos que estou estudando: Flow para comparar com o Apex, LWC e usuários por responsável para alertas segmentados." |

**Se perguntarem algo que você não sabe:** "Essa parte quem escreveu foi a IA; o que eu sei é X, e é exatamente o que
estou estudando agora." Honestidade sobre o uso de IA, somada a mostrar que você entende as decisões, é o ponto forte do projeto.
