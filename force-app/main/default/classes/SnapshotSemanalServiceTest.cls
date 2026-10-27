@IsTest
private class SnapshotSemanalServiceTest {

    /** Obra ativa com uma disciplina (EC) e uma etapa; receita 100.000, impostos 19%, meta 20% (orçamento 61.000). */
    private static Obra__c criarObra(String codigo, Decimal custoConsumido, Decimal custoRestante) {
        Obra__c o = new Obra__c(Name = 'Obra ' + codigo, Codigo__c = codigo, Saldo_Faturar__c = 1000, PO__c = 'P.O. A');
        insert o;
        Disciplina_Obra__c d = new Disciplina_Obra__c(Name = codigo + ' · EC', Obra__c = o.Id, Chave__c = codigo + '|EC',
            Sigla__c = 'EC', Equipe__c = 'Estruturas', Receita__c = 100000, Imposto_Pct__c = 19,
            Meta_Margem_Pct__c = 20, TP_Dias__c = 100);
        insert d;
        insert new Custo_Etapa__c(Name = 'EX', Disciplina_Obra__c = d.Id, Chave__c = codigo + '|EC|EX', Etapa__c = 'EX',
            Dias_Realizados__c = 50, Dias_Restantes__c = 50, Custo_Consumido__c = custoConsumido,
            Custo_Restante__c = custoRestante);
        return o;
    }

    @IsTest
    static void formulasReproduzemAMargemDoSistemaOriginal() {
        Obra__c o = criarObra('T1', 20000, 10000);
        o = [SELECT Margem_Estimada__c, Margem_Negociada__c, Resultado_Projetado__c, Orcamento_Producao__c,
                    Diaria_Real__c, Diaria_Orcada__c, Grupo_Risco__c FROM Obra__c WHERE Id = :o.Id];
        // estimada = (100.000 − 19.000 − 30.000) / 100.000 = 51%; negociada = (100.000 − 19.000 − 20.000) / 100.000 = 61%
        Assert.areEqual(51, o.Margem_Estimada__c.setScale(2));
        Assert.areEqual(61, o.Margem_Negociada__c.setScale(2));
        Assert.areEqual(51000, o.Resultado_Projetado__c);
        Assert.areEqual(61000, o.Orcamento_Producao__c);
        Assert.areEqual(300, o.Diaria_Real__c);   // 30.000 / 100 dias
        Assert.areEqual(610, o.Diaria_Orcada__c); // 61.000 / 100 dias
        Assert.areEqual('4. Positiva', o.Grupo_Risco__c);
    }

    @IsTest
    static void gruposDeRisco() {
        Obra__c prej = criarObra('P', 70000, 20000);  // custo 90.000 > 81.000 → margem −9%
        Obra__c alto = criarObra('A', 60000, 15000);  // margem 6%
        Obra__c mod = criarObra('M', 50000, 15000);   // margem 16%
        Map<Id, Obra__c> r = new Map<Id, Obra__c>([SELECT Grupo_Risco__c FROM Obra__c]);
        Assert.areEqual('1. Em prejuízo', r.get(prej.Id).Grupo_Risco__c);
        Assert.areEqual('2. Alto risco', r.get(alto.Id).Grupo_Risco__c);
        Assert.areEqual('3. Risco moderado', r.get(mod.Id).Grupo_Risco__c);
    }

    @IsTest
    static void primeiraFotoGravaSnapshotsEAlertaObraJaEmRisco() {
        criarObra('P', 70000, 20000);
        criarObra('OK', 20000, 10000);
        Test.startTest();
        SnapshotSemanalService.Resultado r = SnapshotSemanalService.executar(Date.today());
        Test.stopTest();
        Assert.areEqual(4, r.snapshots, '2 obras × (obra + 1 disciplina)');
        Set<String> alertas = new Set<String>();
        for (Snapshot_Semanal__c s : r.alertas) {
            alertas.add(s.Nivel__c + ':' + s.Alerta__c);
        }
        Assert.isTrue(alertas.contains('Obra:Nova obra em risco'));
        Assert.areEqual(2, r.alertas.size(), 'obra P em nível obra e disciplina; obra OK sem alerta');
    }

    @IsTest
    static void segundaSemanaDetectaPioraEQuedaEIdempotencia() {
        Obra__c o = criarObra('W', 20000, 10000); // 51% positiva
        SnapshotSemanalService.executar(Date.today().addDays(-7));
        Custo_Etapa__c c = [SELECT Id FROM Custo_Etapa__c LIMIT 1];
        c.Custo_Restante__c = 45000;              // custo 65.000 → margem 16% (risco moderado)
        update c;
        Test.startTest();
        SnapshotSemanalService.executar(Date.today());
        SnapshotSemanalService.Resultado r = SnapshotSemanalService.executar(Date.today()); // de novo: substitui
        Test.stopTest();
        Assert.areEqual(2, [SELECT COUNT() FROM Snapshot_Semanal__c WHERE Data__c = :Date.today()]);
        Assert.areEqual('Piorou de grupo', r.alertas[0].Alerta__c);
    }

    @IsTest
    static void quedaDeMargemSemTrocarDeGrupo() {
        Parametro_Margem__mdt p = new Parametro_Margem__mdt(Queda_Alerta__c = 5);
        Snapshot_Semanal__c ant = new Snapshot_Semanal__c(Grupo_Risco__c = '4. Positiva', Margem_Estimada__c = 60);
        Snapshot_Semanal__c atu = new Snapshot_Semanal__c(Grupo_Risco__c = '4. Positiva', Margem_Estimada__c = 54);
        Assert.areEqual('Queda de margem', SnapshotSemanalService.alerta(atu, ant, p));
        atu.Margem_Estimada__c = 57;
        Assert.isNull(SnapshotSemanalService.alerta(atu, ant, p));
        Assert.isNull(SnapshotSemanalService.ordem('Sem receita'));
    }

    @IsTest
    static void arquiteturaSemEscopoAcimaDoLimite() {
        Obra__c o = criarObra('AQ', 20000, 10000);
        Disciplina_Obra__c aq = new Disciplina_Obra__c(Name = 'AQ · AQ', Obra__c = o.Id, Chave__c = 'AQ|AQ', Sigla__c = 'AQ',
            Equipe__c = 'Arquitetura', Receita__c = 0, Imposto_Pct__c = 19, Meta_Margem_Pct__c = 20, TP_Dias__c = 0);
        insert aq;
        insert new Custo_Etapa__c(Name = 'EP', Disciplina_Obra__c = aq.Id, Chave__c = 'AQ|AQ|EP', Etapa__c = 'EP',
            Dias_Realizados__c = 10, Dias_Restantes__c = 0, Custo_Consumido__c = 5000, Custo_Restante__c = 0); // 5% da receita
        SnapshotSemanalService.Resultado r = SnapshotSemanalService.executar(Date.today());
        Boolean achou = false;
        for (Snapshot_Semanal__c s : r.alertas) {
            achou = achou || (s.Disciplina_Obra__c == aq.Id && s.Alerta__c == 'AQ acima do limite');
        }
        Assert.isTrue(achou);
    }

    @IsTest
    static void jobAgendadoEEmail() {
        criarObra('P', 70000, 20000);
        Test.startTest();
        Id job = SnapshotSemanalAgendado.agendar();
        new SnapshotSemanalAgendado().execute(null);
        Integer emails = Limits.getEmailInvocations();
        Test.stopTest();
        Assert.isNotNull(job);
        Assert.areEqual(1, emails, 'há alerta → envia 1 e-mail');
        Assert.isFalse(AlertaEmailService.enviarResumo(new List<Snapshot_Semanal__c>(), Date.today()));
    }
}
