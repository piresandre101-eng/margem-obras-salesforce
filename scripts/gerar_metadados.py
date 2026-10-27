"""Gera os metadados do modelo de dados (objetos, campos, custom metadata) em force-app/.

Rodar: python scripts/gerar_metadados.py   (idempotente — sobrescreve os arquivos gerados)

Modelo (espelha o sistema de margem original, em Python + Excel, de um escritório de projetos de engenharia):
  Obra__c                 1 por contrato                         (dados: cadastro + PLAN. ALOC.)
   └─ Disciplina_Obra__c  obra × disciplina: receita, impostos, meta, dias previstos (TP)   [master-detail]
       └─ Custo_Etapa__c  obra × disciplina × etapa: dias e custos do cronograma           [master-detail]
  Snapshot_Semanal__c     histórico semanal por obra e por disciplina (gravado por Apex agendado)
  Parametro_Margem__mdt   meta, limites de risco (editáveis sem código)
  Area_Disciplina__mdt    sigla → equipe e nome da disciplina
"""
from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

RAIZ = Path(__file__).resolve().parents[1] / "force-app" / "main" / "default"
API = "67.0"
CABEC = '<?xml version="1.0" encoding="UTF-8"?>\n'
P = "$CustomMetadata.Parametro_Margem__mdt.Padrao"


def _x(tag: str, valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, bool):
        valor = "true" if valor else "false"
    return f"    <{tag}>{escape(str(valor))}</{tag}>\n"


def campo(nome: str, rotulo: str, tipo: str, *, descricao: str = "", ajuda: str = "", formula: str | None = None,
          precisao: int = 18, escala: int = 2, tamanho: int | None = None, obrigatorio: bool = False,
          externo: bool = False, unico: bool = False, referencia: str | None = None, rel_nome: str | None = None,
          rel_rotulo: str | None = None, rollup: tuple | None = None, valores: list | None = None,
          vazio_formula: str = "BlankAsZero") -> str:
    """XML de um CustomField. rollup = (operação, campo_resumido, campo_relacionamento)."""
    corpo = _x("fullName", nome) + _x("label", rotulo)
    if descricao:
        corpo += _x("description", descricao)
    if ajuda:
        corpo += _x("inlineHelpText", ajuda[:510])
    if formula is not None:
        corpo += _x("formula", formula) + _x("formulaTreatBlanksAs", vazio_formula)
    if rollup:
        op, resumido, chave = rollup
        corpo += _x("summarizedField", resumido) + _x("summaryForeignKey", chave) + _x("summaryOperation", op)
        tipo_xml = "Summary"
    else:
        tipo_xml = tipo
    if tipo in ("Number", "Currency", "Percent") and not rollup:
        corpo += _x("precision", precisao) + _x("scale", escala)
    if tipo == "Text" and formula is None:
        corpo += _x("length", tamanho or 255)
    if tipo == "Checkbox" and formula is None:
        corpo += _x("defaultValue", False)
    if tipo == "MasterDetail":
        corpo += (_x("referenceTo", referencia) + _x("relationshipName", rel_nome) + _x("relationshipLabel", rel_rotulo)
                  + _x("relationshipOrder", 0) + _x("reparentableMasterDetail", False)
                  + _x("writeRequiresMasterRead", False))
    if tipo == "Lookup":
        corpo += (_x("referenceTo", referencia) + _x("relationshipName", rel_nome) + _x("relationshipLabel", rel_rotulo)
                  + _x("deleteConstraint", "SetNull"))
    if tipo == "Picklist":
        vals = "".join(f"            <value><fullName>{escape(v)}</fullName><default>false</default>"
                       f"<label>{escape(v)}</label></value>\n" for v in valores)
        corpo += ("    <valueSet>\n        <restricted>true</restricted>\n        <valueSetDefinition>\n"
                  "            <sorted>false</sorted>\n" + vals + "        </valueSetDefinition>\n    </valueSet>\n")
    if externo:
        corpo += _x("externalId", True)
    if unico:
        corpo += _x("unique", True) + _x("caseSensitive", False)
    if obrigatorio and tipo not in ("MasterDetail",) and formula is None and not rollup:
        corpo += _x("required", True)
    corpo += _x("type", tipo_xml)
    return CABEC + '<CustomField xmlns="http://soap.sforce.com/2006/04/metadata">\n' + corpo + "</CustomField>\n"


def objeto(nome: str, rotulo: str, plural: str, descricao: str, nome_campo: tuple, *, compartilhamento: str) -> str:
    rot_nome, tipo_nome = nome_campo
    nf = f"    <nameField>\n        <label>{escape(rot_nome)}</label>\n        <type>{tipo_nome}</type>\n"
    if tipo_nome == "AutoNumber":
        nf += "        <displayFormat>SNP-{000000}</displayFormat>\n        <startingNumber>1</startingNumber>\n"
    nf += "    </nameField>\n"
    return (CABEC + '<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">\n'
            + _x("label", rotulo) + _x("pluralLabel", plural) + _x("description", descricao) + nf
            + _x("deploymentStatus", "Deployed") + _x("sharingModel", compartilhamento)
            + _x("enableActivities", False) + _x("enableHistory", True) + _x("enableReports", True)
            + _x("enableSearch", True) + _x("enableBulkApi", True) + _x("enableSharing", True)
            + _x("enableStreamingApi", True)
            + "</CustomObject>\n")


def gravar(caminho: Path, conteudo: str) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(conteudo, encoding="utf-8")


# ── Fórmulas comuns (mesma regra em Disciplina e Obra) ────────────────────────
def formulas_margem(rec: str, imp: str, cc: str, cr: str, orc: str, tp: str, dr: str, dt: str) -> dict:
    ct = f"({cc} + {cr})"
    dproj = f"({dr} + {dt})"
    return {
        "Custo_Total__c": ("Custo Total no Cronograma", "Currency", f"{cc} + {cr}",
                           "Custo consumido + custo restante lançado no cronograma."),
        "Resultado_Projetado__c": ("Resultado Projetado", "Currency", f"{rec} - {imp} - {ct}",
                                   "Receita − impostos − custo total no cronograma. Negativo = prejuízo projetado."),
        "Margem_Negociada__c": ("Margem Negociada", "Percent", f"IF({rec} > 0, ({rec} - {imp} - {cc}) / {rec}, NULL)",
                                "Resultado até agora: (receita − impostos − custo já consumido) ÷ receita."),
        "Margem_Estimada__c": ("Margem Estimada", "Percent", f"IF({rec} > 0, ({rec} - {imp} - {ct}) / {rec}, NULL)",
                               "Leitura principal: margem ao término com o cronograma atual. Meta: 20%."),
        "Pct_Orcamento_Producao__c": ("% do Orçamento de Produção no Cronograma", "Percent",
                                      f"IF({orc} > 0, {ct} / {orc}, NULL)",
                                      "Custo no cronograma ÷ Orçamento de Produção. Acima de 100% = abaixo da meta."),
        "Saldo_Orcamento__c": ("Saldo do Orçamento de Produção", "Currency", f"{orc} - {ct}",
                               "Quanto ainda pode virar dias de produção sem consumir a margem."),
        "Cobertura_Cronograma__c": ("Cobertura do Cronograma", "Percent", f"IF({tp} > 0, {dproj} / {tp}, NULL)",
                                    "Dias lançados (realizados + restantes) ÷ dias previstos (TP)."),
        "Diaria_Orcada__c": ("Diária Orçada", "Currency", f"IF(AND({tp} > 0, {orc} > 0), {orc} / {tp}, NULL)",
                             "Orçamento de Produção ÷ dias previstos (TP)."),
        "Diaria_Real__c": ("Diária Real", "Currency", f"IF({dproj} > 0, {ct} / {dproj}, NULL)",
                           "Custo total no cronograma ÷ dias lançados."),
    }


def gerar() -> None:
    obj = RAIZ / "objects"

    # ── Obra__c ────────────────────────────────────────────────────────────────
    gravar(obj / "Obra__c" / "Obra__c.object-meta.xml", objeto(
        "Obra__c", "Obra", "Obras", "Contrato de projeto. Receita e custos vêm das disciplinas (roll-up).",
        ("Nome da Obra", "Text"), compartilhamento="ReadWrite"))
    f_obra = {
        "Codigo__c": campo("Codigo__c", "Código da Obra", "Text", tamanho=20, externo=True, unico=True,
                           descricao="Código da obra (chave externa para carga)."),
        "Cliente__c": campo("Cliente__c", "Cliente", "Text", tamanho=120),
        "PO__c": campo("PO__c", "P.O.", "Text", tamanho=80, descricao="Product Owner responsável pela obra."),
        "Tipo_Contrato__c": campo("Tipo_Contrato__c", "Classificação do Contrato", "Picklist",
                                  valores=["HIGH P.", "MEDIUM P.", "LOW P.", "Sem classificação"]),
        "Saldo_Faturar__c": campo("Saldo_Faturar__c", "Saldo a Faturar", "Currency",
                                  descricao="Saldo a faturar do contrato (PLAN. ALOC.)."),
        # roll-ups das disciplinas
        "Receita__c": campo("Receita__c", "Receita Orçada", "Currency",
                            rollup=("sum", "Disciplina_Obra__c.Receita__c", "Disciplina_Obra__c.Obra__c")),
        "Impostos__c": campo("Impostos__c", "Impostos", "Currency",
                             rollup=("sum", "Disciplina_Obra__c.Impostos__c", "Disciplina_Obra__c.Obra__c")),
        "Meta_Valor__c": campo("Meta_Valor__c", "Meta de Margem (R$)", "Currency",
                               rollup=("sum", "Disciplina_Obra__c.Meta_Valor__c", "Disciplina_Obra__c.Obra__c")),
        "Orcamento_Producao__c": campo("Orcamento_Producao__c", "Orçamento de Produção", "Currency",
                                       rollup=("sum", "Disciplina_Obra__c.Orcamento_Producao__c",
                                               "Disciplina_Obra__c.Obra__c")),
        "TP_Dias__c": campo("TP_Dias__c", "Dias Previstos (TP)", "Number",
                            rollup=("sum", "Disciplina_Obra__c.TP_Dias__c", "Disciplina_Obra__c.Obra__c")),
        "Custo_Consumido__c": campo("Custo_Consumido__c", "Custo Consumido", "Currency",
                                    rollup=("sum", "Disciplina_Obra__c.Custo_Consumido__c",
                                            "Disciplina_Obra__c.Obra__c")),
        "Custo_Restante__c": campo("Custo_Restante__c", "Custo Restante Lançado", "Currency",
                                   rollup=("sum", "Disciplina_Obra__c.Custo_Restante__c",
                                           "Disciplina_Obra__c.Obra__c")),
        "Dias_Realizados__c": campo("Dias_Realizados__c", "Dias Consumidos", "Number",
                                    rollup=("sum", "Disciplina_Obra__c.Dias_Realizados__c",
                                            "Disciplina_Obra__c.Obra__c")),
        "Dias_Restantes__c": campo("Dias_Restantes__c", "Dias Restantes Lançados", "Number",
                                   rollup=("sum", "Disciplina_Obra__c.Dias_Restantes__c",
                                           "Disciplina_Obra__c.Obra__c")),
        "Meta_Pct__c": campo("Meta_Pct__c", "Meta de Margem", "Percent",
                             formula=f"IF(Receita__c > 0, Meta_Valor__c / Receita__c, {P}.Meta_Margem__c)"),
        "Em_Andamento__c": campo("Em_Andamento__c", "Em Andamento", "Checkbox",
                                 formula="OR(Saldo_Faturar__c > 0, Dias_Restantes__c > 0)",
                                 descricao="Ativa = saldo a faturar ou dias restantes no cronograma."),
    }
    _gravar_formulas(obj / "Obra__c", f_obra, "Receita__c", "Impostos__c", "Custo_Consumido__c", "Custo_Restante__c",
                     "Orcamento_Producao__c", "TP_Dias__c", "Dias_Realizados__c", "Dias_Restantes__c")

    # ── Disciplina_Obra__c ────────────────────────────────────────────────────
    gravar(obj / "Disciplina_Obra__c" / "Disciplina_Obra__c.object-meta.xml", objeto(
        "Disciplina_Obra__c", "Disciplina da Obra", "Disciplinas da Obra",
        "Obra × disciplina: receita, impostos, meta e dias previstos; custos vêm das etapas (roll-up).",
        ("Disciplina da Obra", "Text"), compartilhamento="ControlledByParent"))
    f_disc = {
        "Obra__c": campo("Obra__c", "Obra", "MasterDetail", referencia="Obra__c", rel_nome="Disciplinas",
                         rel_rotulo="Disciplinas"),
        "Chave__c": campo("Chave__c", "Chave (obra|disciplina)", "Text", tamanho=40, externo=True, unico=True),
        "Sigla__c": campo("Sigla__c", "Sigla", "Text", tamanho=10, obrigatorio=True,
                          descricao="Sigla da disciplina (EC, IH, AQ…)."),
        "Equipe__c": campo("Equipe__c", "Equipe", "Picklist",
                           valores=["Estruturas", "Hidráulicas", "Arquitetura", "Elétricas", "HVAC", "Outras"]),
        "Receita__c": campo("Receita__c", "Receita Orçada", "Currency",
                            descricao="$ ORÇADO + aditivos da disciplina."),
        "Imposto_Pct__c": campo("Imposto_Pct__c", "% Impostos", "Percent", precisao=5, escala=2),
        "Meta_Margem_Pct__c": campo("Meta_Margem_Pct__c", "% Meta de Margem", "Percent", precisao=5, escala=2),
        "TP_Dias__c": campo("TP_Dias__c", "Dias Previstos (TP)", "Number", escala=2),
        "Impostos__c": campo("Impostos__c", "Impostos", "Currency", formula="Receita__c * Imposto_Pct__c"),
        "Meta_Valor__c": campo("Meta_Valor__c", "Meta de Margem (R$)", "Currency",
                               formula="Receita__c * Meta_Margem_Pct__c"),
        "Orcamento_Producao__c": campo("Orcamento_Producao__c", "Orçamento de Produção", "Currency",
                                       formula="Receita__c * (1 - Imposto_Pct__c - Meta_Margem_Pct__c)",
                                       descricao="Receita − impostos − margem: o que vira dias de produção."),
        "Custo_Consumido__c": campo("Custo_Consumido__c", "Custo Consumido", "Currency",
                                    rollup=("sum", "Custo_Etapa__c.Custo_Consumido__c",
                                            "Custo_Etapa__c.Disciplina_Obra__c")),
        "Custo_Restante__c": campo("Custo_Restante__c", "Custo Restante Lançado", "Currency",
                                   rollup=("sum", "Custo_Etapa__c.Custo_Restante__c",
                                           "Custo_Etapa__c.Disciplina_Obra__c")),
        "Dias_Realizados__c": campo("Dias_Realizados__c", "Dias Consumidos", "Number",
                                    rollup=("sum", "Custo_Etapa__c.Dias_Realizados__c",
                                            "Custo_Etapa__c.Disciplina_Obra__c")),
        "Dias_Restantes__c": campo("Dias_Restantes__c", "Dias Restantes Lançados", "Number",
                                   rollup=("sum", "Custo_Etapa__c.Dias_Restantes__c",
                                           "Custo_Etapa__c.Disciplina_Obra__c")),
        "Sem_Receita__c": campo("Sem_Receita__c", "Custo sem Receita Orçada", "Checkbox",
                                formula="AND(Receita__c <= 0, (Custo_Consumido__c + Custo_Restante__c) > 0)",
                                descricao="Trabalho lançado numa disciplina não vendida na obra (custo absorvido)."),
    }
    _gravar_formulas(obj / "Disciplina_Obra__c", f_disc, "Receita__c", "Impostos__c", "Custo_Consumido__c",
                     "Custo_Restante__c", "Orcamento_Producao__c", "TP_Dias__c", "Dias_Realizados__c",
                     "Dias_Restantes__c")

    # ── Custo_Etapa__c ────────────────────────────────────────────────────────
    gravar(obj / "Custo_Etapa__c" / "Custo_Etapa__c.object-meta.xml", objeto(
        "Custo_Etapa__c", "Custo da Etapa", "Custos das Etapas",
        "Obra × disciplina × etapa: dias e custos agregados do cronograma (sem dado individual de colaborador).",
        ("Etapa", "Text"), compartilhamento="ControlledByParent"))
    for nome, xml in {
        "Disciplina_Obra__c": campo("Disciplina_Obra__c", "Disciplina da Obra", "MasterDetail",
                                    referencia="Disciplina_Obra__c", rel_nome="Custos_Etapas",
                                    rel_rotulo="Custos das Etapas"),
        "Chave__c": campo("Chave__c", "Chave (obra|disciplina|etapa)", "Text", tamanho=60, externo=True, unico=True),
        "Etapa__c": campo("Etapa__c", "Etapa", "Text", tamanho=20, descricao="EP, AP, PB, EX ou outra."),
        "Dias_Realizados__c": campo("Dias_Realizados__c", "Dias Consumidos", "Number", escala=2),
        "Dias_Restantes__c": campo("Dias_Restantes__c", "Dias Restantes Lançados", "Number", escala=2),
        "Custo_Consumido__c": campo("Custo_Consumido__c", "Custo Consumido", "Currency"),
        "Custo_Restante__c": campo("Custo_Restante__c", "Custo Restante Lançado", "Currency"),
    }.items():
        gravar(obj / "Custo_Etapa__c" / "fields" / f"{nome}.field-meta.xml", xml)

    # ── Snapshot_Semanal__c ───────────────────────────────────────────────────
    gravar(obj / "Snapshot_Semanal__c" / "Snapshot_Semanal__c.object-meta.xml", objeto(
        "Snapshot_Semanal__c", "Snapshot Semanal", "Snapshots Semanais",
        "Foto semanal da margem e do grupo de risco por obra (e por disciplina), gravada por Apex agendado.",
        ("Snapshot", "AutoNumber"), compartilhamento="ReadWrite"))
    for nome, xml in {
        "Data__c": campo("Data__c", "Data", "Date", obrigatorio=True),
        "Obra__c": campo("Obra__c", "Obra", "Lookup", referencia="Obra__c", rel_nome="Snapshots",
                         rel_rotulo="Snapshots Semanais"),
        "Disciplina_Obra__c": campo("Disciplina_Obra__c", "Disciplina da Obra", "Lookup",
                                    referencia="Disciplina_Obra__c", rel_nome="Snapshots",
                                    rel_rotulo="Snapshots Semanais"),
        "Nivel__c": campo("Nivel__c", "Nível", "Picklist", valores=["Obra", "Disciplina"]),
        "Grupo_Risco__c": campo("Grupo_Risco__c", "Grupo de Risco", "Text", tamanho=40),
        "Margem_Estimada__c": campo("Margem_Estimada__c", "Margem Estimada", "Percent"),
        "Margem_Negociada__c": campo("Margem_Negociada__c", "Margem Negociada", "Percent"),
        "Resultado_Projetado__c": campo("Resultado_Projetado__c", "Resultado Projetado", "Currency"),
        "Receita__c": campo("Receita__c", "Receita Orçada", "Currency"),
        "Alerta__c": campo("Alerta__c", "Alerta", "Text", tamanho=80,
                           descricao="Piorou de grupo / Queda de margem / Nova obra em risco / AQ acima do limite."),
    }.items():
        gravar(obj / "Snapshot_Semanal__c" / "fields" / f"{nome}.field-meta.xml", xml)

    _custom_metadata()
    _acesso_e_app()
    _telas()
    print("Metadados gerados em", RAIZ)


def _grupo_risco_formula(me: str, meta: str, dnl: str, res: str, orc: str, ct: str, cmd: str, ativo: str) -> str:
    """Mesmos grupos do sistema Python (D-10): prejuízo, alto, moderado, positiva."""
    d_prej = f"IF({cmd} > 0, {res} / {cmd}, NULL)"
    d_meta = f"IF({cmd} > 0, ({orc} - {ct}) / {cmd}, NULL)"
    return (f"IF(ISBLANK({me}), \"Sem receita\",\n"
            f"IF({me} < 0, \"1. Em prejuízo\",\n"
            f"IF(OR({me} < {P}.Limite_Alto_Risco__c, AND({ativo}, NOT(ISBLANK({d_prej})), {dnl} > {d_prej})), "
            f"\"2. Alto risco\",\n"
            f"IF(OR({me} < {meta}, AND({ativo}, NOT(ISBLANK({d_meta})), {dnl} > MAX({d_meta}, 0))), "
            f"\"3. Risco moderado\", \"4. Positiva\"))))")


def _gravar_formulas(pasta: Path, campos: dict, rec, imp, cc, cr, orc, tp, dr, dt) -> None:
    for nome, xml in campos.items():
        gravar(pasta / "fields" / f"{nome}.field-meta.xml", xml)
    for nome, (rot, tipo, f, desc) in formulas_margem(rec, imp, cc, cr, orc, tp, dr, dt).items():
        gravar(pasta / "fields" / f"{nome}.field-meta.xml", campo(nome, rot, tipo, formula=f, descricao=desc,
                                                                  ajuda=desc))
    gravar(pasta / "fields" / "Diaria_Real_vs_Orcada__c.field-meta.xml", campo(
        "Diaria_Real_vs_Orcada__c", "Diária Real ÷ Orçada", "Number", escala=2,
        formula="IF(AND(Diaria_Real__c > 0, Diaria_Orcada__c > 0), Diaria_Real__c / Diaria_Orcada__c, NULL)",
        descricao="Acima de 1: cada dia custa mais do que o orçamento previa."))
    ativo = "Em_Andamento__c" if "Em_Andamento__c" in campos else "Obra__r.Em_Andamento__c"
    meta = "Meta_Pct__c" if "Meta_Pct__c" in campos else "Meta_Margem_Pct__c"
    gravar(pasta / "fields" / "Dias_TP_Nao_Lancados__c.field-meta.xml", campo(
        "Dias_TP_Nao_Lancados__c", "Dias do TP Ainda Não Lançados", "Number", escala=1,
        formula=f"IF(AND({ativo}, {tp} > 0), MAX(0, {tp} - {dr} - {dt}), 0)",
        descricao="Prazo disponível ainda fora do cronograma (não é custo)."))
    gravar(pasta / "fields" / "Grupo_Risco__c.field-meta.xml", campo(
        "Grupo_Risco__c", "Grupo de Risco", "Text",
        formula=_grupo_risco_formula("Margem_Estimada__c", meta, "Dias_TP_Nao_Lancados__c",
                                     "Resultado_Projetado__c", orc, "Custo_Total__c", "Diaria_Real__c", ativo),
        vazio_formula="BlankAsBlank",
        descricao="Em prejuízo: margem < 0 · Alto risco: < 10% ou o TP restante na diária real levaria ao prejuízo · "
                  "Risco moderado: < meta ou o TP restante levaria abaixo da meta · Positiva: demais."))


def _custom_metadata() -> None:
    obj = RAIZ / "objects"
    for nome, rotulo, plural, desc in (
            ("Parametro_Margem__mdt", "Parâmetro de Margem", "Parâmetros de Margem",
             "Meta e limites dos critérios de risco — editáveis sem código."),
            ("Area_Disciplina__mdt", "Área da Disciplina", "Áreas das Disciplinas",
             "Sigla da disciplina → equipe e nome.")):
        gravar(obj / nome / f"{nome}.object-meta.xml",
               CABEC + '<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">\n'
               + _x("label", rotulo) + _x("pluralLabel", plural) + _x("description", desc)
               + _x("visibility", "Public") + "</CustomObject>\n")

    def cmd_campo(obj_nome, nome, rotulo, tipo, **kw):
        xml = campo(nome, rotulo, tipo, **kw).replace("    <type>", "    <fieldManageability>DeveloperControlled"
                                                      "</fieldManageability>\n    <type>")
        gravar(obj / obj_nome / "fields" / f"{nome}.field-meta.xml", xml)

    for nome, rot, desc in (("Meta_Margem__c", "Meta de Margem", "Meta padrão (20%)."),
                            ("Limite_Alto_Risco__c", "Limite Alto Risco", "Margem abaixo disso = alto risco (10%)."),
                            ("Queda_Alerta__c", "Queda para Alerta", "Queda de margem que gera alerta (5 p.p.)."),
                            ("Limite_AQ_Sem_Escopo__c", "Limite Arquitetura sem Escopo",
                             "Custo de AQ sem receita ÷ receita da obra (3%)."),
                            ("Cobertura_Minima__c", "Cobertura Mínima", "Cobertura do cronograma mínima (90%).")):
        cmd_campo("Parametro_Margem__mdt", nome, rot, "Percent", precisao=5, escala=2, descricao=desc)
    cmd_campo("Area_Disciplina__mdt", "Equipe__c", "Equipe", "Text", tamanho=40)
    cmd_campo("Area_Disciplina__mdt", "Nome_Disciplina__c", "Nome da Disciplina", "Text", tamanho=80)

    reg = RAIZ / "customMetadata"

    def registro(tipo, dev, rotulo, valores: dict) -> None:
        vals = "".join(f"    <values>\n        <field>{k}</field>\n        <value xsi:type=\"xsd:{t}\">{escape(str(v))}"
                       f"</value>\n    </values>\n" for k, (t, v) in valores.items())
        gravar(reg / f"{tipo}.{dev}.md-meta.xml",
               CABEC + '<CustomMetadata xmlns="http://soap.sforce.com/2006/04/metadata" '
               'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">\n'
               + _x("label", rotulo) + _x("protected", False) + vals + "</CustomMetadata>\n")

    registro("Parametro_Margem", "Padrao", "Padrão", {
        "Meta_Margem__c": ("double", 20), "Limite_Alto_Risco__c": ("double", 10), "Queda_Alerta__c": ("double", 5),
        "Limite_AQ_Sem_Escopo__c": ("double", 3), "Cobertura_Minima__c": ("double", 90)})
    for sigla, (equipe, nome) in {
        "EC": ("Estruturas", "Estrutura de concreto"), "FU": ("Estruturas", "Fundações"),
        "EM": ("Estruturas", "Estrutura metálica"), "IH": ("Hidráulicas", "Hidráulica"),
        "IS": ("Hidráulicas", "Sanitária"), "IP": ("Hidráulicas", "Pluvial"), "IG": ("Hidráulicas", "Gás"),
        "II": ("Hidráulicas", "Incêndio"), "DR": ("Hidráulicas", "Drenagem"), "AQ": ("Arquitetura", "Arquitetura"),
        "IE": ("Elétricas", "Elétrica"), "SE": ("Elétricas", "SPDA / Subestação"), "ENE": ("Elétricas", "Energia"),
        "AC": ("HVAC", "Ar-condicionado")}.items():
        registro("Area_Disciplina", sigla, sigla, {"Equipe__c": ("string", equipe), "Nome_Disciplina__c": ("string", nome)})


def _acesso_e_app() -> None:
    """Permission Set (acesso a objetos/campos), abas e app Lightning."""
    obj = RAIZ / "objects"
    objetos = ["Obra__c", "Disciplina_Obra__c", "Custo_Etapa__c", "Snapshot_Semanal__c"]

    def bloco(tag: str, itens: dict) -> str:
        return f"    <{tag}>\n" + "".join(f"        <{k}>{v}</{k}>\n" for k, v in itens.items()) + f"    </{tag}>\n"

    perm_obj, perm_campo = "", ""
    for o in objetos:
        perm_obj += bloco("objectPermissions", {
            "allowCreate": "true", "allowDelete": "true", "allowEdit": "true", "allowRead": "true",
            "modifyAllRecords": "true", "object": o, "viewAllRecords": "true"})
        for f in sorted((obj / o / "fields").glob("*.field-meta.xml")):
            xml = f.read_text(encoding="utf-8")
            if "<type>MasterDetail</type>" in xml or "<required>true</required>" in xml:
                continue  # sempre visíveis; o Salesforce não aceita permissão de campo para eles
            calculado = "<formula>" in xml or "<type>Summary</type>" in xml
            nome = f.name.replace(".field-meta.xml", "")
            perm_campo += bloco("fieldPermissions", {
                "editable": "false" if calculado else "true", "field": f"{o}.{nome}", "readable": "true"})
    abas = ["Inicio_Margem_de_Obras", "Obra__c", "Disciplina_Obra__c", "Snapshot_Semanal__c"]
    perm_aba = "".join(bloco("tabSettings", {"tab": t, "visibility": "Visible"}) for t in abas)
    app_vis = bloco("applicationVisibilities", {"application": "Margem_de_Obras", "visible": "true"})
    gravar(RAIZ / "permissionsets" / "Margem_Obras.permissionset-meta.xml",
           CABEC + '<PermissionSet xmlns="http://soap.sforce.com/2006/04/metadata">\n' + app_vis
           + _x("description", "Acesso completo ao app Margem de Obras.") + perm_campo
           + _x("hasActivationRequired", False) + _x("label", "Margem de Obras") + perm_obj + perm_aba
           + "</PermissionSet>\n")
    for t, motivo in (("Obra__c", "Custom24: Building"), ("Disciplina_Obra__c", "Custom55: Books"),
                      ("Snapshot_Semanal__c", "Custom62: Chalkboard")):
        gravar(RAIZ / "tabs" / f"{t}.tab-meta.xml",
               CABEC + '<CustomTab xmlns="http://soap.sforce.com/2006/04/metadata">\n'
               + _x("customObject", True) + _x("motif", motivo) + "</CustomTab>\n")
    # Aba da página inicial (Lightning App Page em flexipages/Inicio_Margem_de_Obras)
    gravar(RAIZ / "tabs" / "Inicio_Margem_de_Obras.tab-meta.xml",
           CABEC + '<CustomTab xmlns="http://soap.sforce.com/2006/04/metadata">\n'
           + _x("flexiPage", "Inicio_Margem_de_Obras") + _x("label", "Início")
           + _x("motif", "Custom24: Building") + "</CustomTab>\n")
    # Página de registro da Obra (flexipages/Obra_Pagina) ativada como padrão dentro deste app
    sobrescrita = ("    <actionOverrides>\n        <actionName>View</actionName>\n        <comment>Página Lightning da Obra</comment>\n"
                   "        <content>Obra_Pagina</content>\n        <formFactor>Large</formFactor>\n"
                   "        <skipRecordTypeSelect>false</skipRecordTypeSelect>\n        <type>Flexipage</type>\n"
                   "        <pageOrSobjectType>Obra__c</pageOrSobjectType>\n    </actionOverrides>\n")
    gravar(RAIZ / "applications" / "Margem_de_Obras.app-meta.xml",
           CABEC + '<CustomApplication xmlns="http://soap.sforce.com/2006/04/metadata">\n' + sobrescrita
           + _x("description", "Margem, risco e histórico semanal das obras (réplica de um sistema de margem de projetos de engenharia).")
           + _x("formFactors", "Large") + _x("isNavAutoTempTabsDisabled", False)
           + _x("isNavPersonalizationDisabled", True) + _x("isNavTabPersistenceDisabled", False)
           + _x("label", "Margem de Obras") + _x("navType", "Standard")
           + "".join(_x("tabs", t) for t in ["Inicio_Margem_de_Obras", "Obra__c", "Disciplina_Obra__c", "Snapshot_Semanal__c",
                                             "standard-report", "standard-Dashboard"])
           + _x("uiType", "Lightning") + "</CustomApplication>\n")


def _telas() -> None:
    """Layouts de página (seções), destaques (compact layouts) e listas filtradas (list views)."""
    obj = RAIZ / "objects"

    def eh_calculado(o: str, f: str) -> bool:
        p = obj / o / "fields" / f"{f}.field-meta.xml"
        if not p.exists():
            return False
        xml = p.read_text(encoding="utf-8")
        return "<formula>" in xml or "<type>Summary</type>" in xml

    def item(o: str, f: str, obrigatorios=("Name",)) -> str:
        comport = "Required" if f in obrigatorios else ("Readonly" if (eh_calculado(o, f) or (
            f == "Name" and o == "Snapshot_Semanal__c")) else "Edit")
        return (f"            <layoutItems>\n                <behavior>{comport}</behavior>\n"
                f"                <field>{f}</field>\n            </layoutItems>\n")

    def secao(o: str, titulo: str, col1: list, col2: list, obrig=("Name",)) -> str:
        cols = ""
        for c in (col1, col2):
            cols += "        <layoutColumns>\n" + "".join(item(o, f, obrig) for f in c) + "        </layoutColumns>\n"
        return (f"    <layoutSections>\n        <customLabel>true</customLabel>\n        <detailHeading>true</detailHeading>\n"
                f"        <editHeading>true</editHeading>\n        <label>{escape(titulo)}</label>\n" + cols
                + "        <style>TwoColumnsTopToBottom</style>\n    </layoutSections>\n")

    def lista_rel(rel: str, campos: list, ordem: str | None = None) -> str:
        x = "    <relatedLists>\n" + "".join(f"        <fields>{c}</fields>\n" for c in campos)
        x += f"        <relatedList>{rel}</relatedList>\n"
        if ordem:
            x += f"        <sortField>{ordem}</sortField>\n        <sortOrder>Asc</sortOrder>\n"
        return x + "    </relatedLists>\n"

    def layout(o: str, nome: str, secoes: str, relacionadas: str = "") -> None:
        gravar(obj.parent / "layouts" / f"{o}-{nome}.layout-meta.xml",
               CABEC + '<Layout xmlns="http://soap.sforce.com/2006/04/metadata">\n' + secoes
               + "    <showEmailCheckbox>false</showEmailCheckbox>\n    <showHighlightsPanel>false</showHighlightsPanel>\n"
               + "    <showInteractionLogPanel>false</showInteractionLogPanel>\n    <showRunAssignmentRulesCheckbox>false"
               + "</showRunAssignmentRulesCheckbox>\n    <showSubmitAndAttachButton>false</showSubmitAndAttachButton>\n"
               + relacionadas + "</Layout>\n")

    margem_col1 = ["Grupo_Risco__c", "Margem_Estimada__c", "Margem_Negociada__c"]
    margem_col2 = ["Resultado_Projetado__c", "Pct_Orcamento_Producao__c", "Saldo_Orcamento__c"]
    receita_col1 = ["Receita__c", "Impostos__c", "Orcamento_Producao__c"]
    custo_col2 = ["Custo_Consumido__c", "Custo_Restante__c", "Custo_Total__c"]
    prazo_col1 = ["TP_Dias__c", "Dias_Realizados__c", "Dias_Restantes__c", "Dias_TP_Nao_Lancados__c"]
    prazo_col2 = ["Cobertura_Cronograma__c", "Diaria_Orcada__c", "Diaria_Real__c", "Diaria_Real_vs_Orcada__c"]

    layout("Obra__c", "Layout de Obra",
           secao("Obra__c", "Obra", ["Name", "Codigo__c", "Cliente__c"],
                 ["PO__c", "Tipo_Contrato__c", "Em_Andamento__c", "Saldo_Faturar__c"])
           + secao("Obra__c", "Margem e risco", margem_col1 + ["Meta_Pct__c"], margem_col2)
           + secao("Obra__c", "Receita e custo", receita_col1, custo_col2)
           + secao("Obra__c", "Prazo e produtividade", prazo_col1, prazo_col2),
           lista_rel("Disciplina_Obra__c.Obra__c",
                     ["NAME", "Equipe__c", "Receita__c", "Margem_Estimada__c", "Resultado_Projetado__c",
                      "Grupo_Risco__c", "Diaria_Real_vs_Orcada__c"])
           + lista_rel("Snapshot_Semanal__c.Obra__c",
                       ["NAME", "Data__c", "Nivel__c", "Grupo_Risco__c", "Margem_Estimada__c", "Alerta__c"]))

    obrig_disc = ("Name", "Obra__c", "Sigla__c")
    layout("Disciplina_Obra__c", "Layout de Disciplina da Obra",
           secao("Disciplina_Obra__c", "Disciplina", ["Name", "Obra__c", "Sigla__c"], ["Equipe__c", "Chave__c",
                                                                                         "Sem_Receita__c"], obrig_disc)
           + secao("Disciplina_Obra__c", "Margem e risco", margem_col1, margem_col2, obrig_disc)
           + secao("Disciplina_Obra__c", "Receita e custo",
                   receita_col1 + ["Imposto_Pct__c", "Meta_Margem_Pct__c"], custo_col2, obrig_disc)
           + secao("Disciplina_Obra__c", "Prazo e produtividade", prazo_col1, prazo_col2, obrig_disc),
           lista_rel("Custo_Etapa__c.Disciplina_Obra__c",
                     ["NAME", "Dias_Realizados__c", "Dias_Restantes__c", "Custo_Consumido__c", "Custo_Restante__c"]))

    layout("Custo_Etapa__c", "Layout de Custo da Etapa",
           secao("Custo_Etapa__c", "Etapa", ["Name", "Disciplina_Obra__c", "Etapa__c"], ["Chave__c"],
                 ("Name", "Disciplina_Obra__c"))
           + secao("Custo_Etapa__c", "Dias e custos", ["Dias_Realizados__c", "Dias_Restantes__c"],
                   ["Custo_Consumido__c", "Custo_Restante__c"], ("Name", "Disciplina_Obra__c")))

    layout("Snapshot_Semanal__c", "Layout de Snapshot Semanal",
           secao("Snapshot_Semanal__c", "Foto semanal", ["Name", "Data__c", "Nivel__c", "Obra__c", "Disciplina_Obra__c"],
                 ["Grupo_Risco__c", "Alerta__c", "Margem_Estimada__c", "Margem_Negociada__c", "Resultado_Projetado__c",
                  "Receita__c"], ("Data__c",)))

    # Destaques no topo do registro (compact layout)
    for o, nome, campos in (
            ("Obra__c", "Destaques_Obra", ["Name", "Grupo_Risco__c", "Margem_Estimada__c", "Resultado_Projetado__c",
                                           "PO__c", "Receita__c"]),
            ("Disciplina_Obra__c", "Destaques_Disciplina", ["Name", "Grupo_Risco__c", "Margem_Estimada__c",
                                                            "Resultado_Projetado__c", "Equipe__c", "Receita__c"])):
        gravar(obj / o / "compactLayouts" / f"{nome}.compactLayout-meta.xml",
               CABEC + '<CompactLayout xmlns="http://soap.sforce.com/2006/04/metadata">\n'
               + _x("fullName", nome) + "".join(_x("fields", c) for c in campos)
               + _x("label", "Destaques") + "</CompactLayout>\n")
        arq = obj / o / f"{o}.object-meta.xml"
        xml = arq.read_text(encoding="utf-8")
        if o == "Obra__c" and "<actionOverrides>" not in xml:
            # Página Lightning da Obra como padrão do ORG (vale em qualquer app, busca ou link)
            override = ("    <actionOverrides>\n        <actionName>View</actionName>\n"
                        "        <comment>Pagina Lightning da Obra (padrao do org)</comment>\n"
                        "        <content>Obra_Pagina</content>\n        <formFactor>Large</formFactor>\n"
                        "        <skipRecordTypeSelect>false</skipRecordTypeSelect>\n"
                        "        <type>Flexipage</type>\n    </actionOverrides>\n")
            ancora = "    <compactLayoutAssignment>" if "<compactLayoutAssignment>" in xml else "    <deploymentStatus>"
            xml = xml.replace(ancora, override + ancora, 1)
            arq.write_text(xml, encoding="utf-8")
        if "<compactLayoutAssignment>" not in xml:
            xml = xml.replace("    <deploymentStatus>", f"    <compactLayoutAssignment>{nome}</compactLayoutAssignment>\n"
                                                         "    <deploymentStatus>", 1)
            arq.write_text(xml, encoding="utf-8")

    # Listas filtradas
    def list_view(o: str, nome: str, rotulo: str, colunas: list, filtros: list) -> None:
        f = "".join(f"    <filters>\n        <field>{c}</field>\n        <operation>{op}</operation>\n"
                    f"        <value>{escape(v)}</value>\n    </filters>\n" for c, op, v in filtros)
        gravar(obj / o / "listViews" / f"{nome}.listView-meta.xml",
               CABEC + '<ListView xmlns="http://soap.sforce.com/2006/04/metadata">\n' + _x("fullName", nome)
               + "".join(_x("columns", c) for c in colunas) + _x("filterScope", "Everything") + f
               + _x("label", rotulo) + "</ListView>\n")

    cols = ["NAME", "PO__c", "Grupo_Risco__c", "Margem_Estimada__c", "Resultado_Projetado__c", "Receita__c",
            "Cobertura_Cronograma__c", "Diaria_Real_vs_Orcada__c"]
    ativas = [("Em_Andamento__c", "equals", "1"), ("Receita__c", "greaterThan", "0")]
    list_view("Obra__c", "Todas_Obras", "Todas as obras", cols + ["Em_Andamento__c"], [])
    list_view("Obra__c", "Obras_Ativas", "Obras ativas", cols, ativas)
    list_view("Obra__c", "Obras_Em_Prejuizo", "Obras ativas em prejuízo", cols,
              ativas + [("Grupo_Risco__c", "equals", "1. Em prejuízo")])
    list_view("Obra__c", "Obras_Alto_Risco", "Obras ativas em alto risco", cols,
              ativas + [("Grupo_Risco__c", "equals", "2. Alto risco")])
    list_view("Obra__c", "Obras_Risco_Moderado", "Obras ativas em risco moderado", cols,
              ativas + [("Grupo_Risco__c", "equals", "3. Risco moderado")])
    list_view("Disciplina_Obra__c", "Disciplinas_Sem_Receita", "Trabalho sem receita orçada",
              ["NAME", "Equipe__c", "Custo_Total__c", "Resultado_Projetado__c"], [("Sem_Receita__c", "equals", "1")])
    list_view("Disciplina_Obra__c", "Disciplinas_Em_Prejuizo", "Disciplinas em prejuízo",
              ["NAME", "Equipe__c", "Receita__c", "Margem_Estimada__c", "Resultado_Projetado__c"],
              [("Grupo_Risco__c", "equals", "1. Em prejuízo")])
    list_view("Snapshot_Semanal__c", "Alertas", "Alertas",
              ["NAME", "Data__c", "Obra__c", "Disciplina_Obra__c", "Alerta__c", "Grupo_Risco__c", "Margem_Estimada__c"],
              [("Alerta__c", "notEqual", "")])


if __name__ == "__main__":
    gerar()
