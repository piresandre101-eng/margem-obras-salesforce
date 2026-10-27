/**
 * Foto semanal da margem das obras ativas e comparação com a semana anterior.
 *
 * Para cada obra ativa (Em_Andamento__c) grava um Snapshot_Semanal__c de nível "Obra" e um de nível
 * "Disciplina" para cada disciplina dela, com margem, resultado e grupo de risco (os grupos são
 * calculados pelos CAMPOS DE FÓRMULA — este código só fotografa e compara).
 *
 * Alertas (mesmas regras do sistema original):
 *   - "Piorou de grupo"         : grupo atual pior que o da foto anterior
 *   - "Queda de margem"         : mesmo grupo, margem estimada caiu ≥ Queda_Alerta__c (p.p.)
 *   - "Nova obra em risco"      : sem foto anterior e já em prejuízo/alto risco
 *   - "AQ acima do limite"      : arquitetura sem receita orçada com custo > Limite_AQ_Sem_Escopo__c da receita da obra
 *
 * Idempotente: rodar duas vezes no mesmo dia substitui as fotos do dia.
 */
public with sharing class SnapshotSemanalService {

    public class Resultado {
        public Integer snapshots = 0;
        public List<Snapshot_Semanal__c> alertas = new List<Snapshot_Semanal__c>();
    }

    private static Parametro_Margem__mdt parametros() {
        Parametro_Margem__mdt p = Parametro_Margem__mdt.getInstance('Padrao');
        if (p == null) {
            p = new Parametro_Margem__mdt(Queda_Alerta__c = 5, Limite_AQ_Sem_Escopo__c = 3);
        }
        return p;
    }

    /** Ordem do grupo: 1 = em prejuízo … 4 = positiva; null = sem receita (não compara). */
    @TestVisible
    private static Integer ordem(String grupo) {
        if (String.isBlank(grupo) || !grupo.substring(0, 1).isNumeric()) {
            return null;
        }
        return Integer.valueOf(grupo.substring(0, 1));
    }

    public static Resultado executar(Date hoje) {
        Parametro_Margem__mdt p = parametros();
        Resultado res = new Resultado();

        delete [SELECT Id FROM Snapshot_Semanal__c WHERE Data__c = :hoje];

        // Última foto anterior de cada obra / disciplina
        Map<String, Snapshot_Semanal__c> anterior = new Map<String, Snapshot_Semanal__c>();
        AggregateResult[] ult = [SELECT MAX(Data__c) d FROM Snapshot_Semanal__c WHERE Data__c < :hoje];
        Date dataAnterior = (Date) ult[0].get('d');
        if (dataAnterior != null) {
            for (Snapshot_Semanal__c s : [SELECT Obra__c, Disciplina_Obra__c, Nivel__c, Grupo_Risco__c,
                                                 Margem_Estimada__c, Alerta__c
                                          FROM Snapshot_Semanal__c WHERE Data__c = :dataAnterior]) {
                anterior.put(chave(s.Nivel__c, s.Obra__c, s.Disciplina_Obra__c), s);
            }
        }

        List<Snapshot_Semanal__c> novos = new List<Snapshot_Semanal__c>();
        for (Obra__c o : [SELECT Id, Name, Receita__c, Margem_Estimada__c, Margem_Negociada__c,
                                 Resultado_Projetado__c, Grupo_Risco__c,
                                 (SELECT Id, Sigla__c, Receita__c, Margem_Estimada__c, Margem_Negociada__c,
                                         Resultado_Projetado__c, Grupo_Risco__c, Custo_Total__c, Sem_Receita__c
                                  FROM Disciplinas__r)
                          FROM Obra__c WHERE Em_Andamento__c = true AND Receita__c > 0]) {
            Snapshot_Semanal__c so = new Snapshot_Semanal__c(
                Data__c = hoje, Nivel__c = 'Obra', Obra__c = o.Id, Receita__c = o.Receita__c,
                Margem_Estimada__c = o.Margem_Estimada__c, Margem_Negociada__c = o.Margem_Negociada__c,
                Resultado_Projetado__c = o.Resultado_Projetado__c, Grupo_Risco__c = o.Grupo_Risco__c);
            so.Alerta__c = alerta(so, anterior.get(chave('Obra', o.Id, null)), p);
            novos.add(so);
            for (Disciplina_Obra__c d : o.Disciplinas__r) {
                Snapshot_Semanal__c sd = new Snapshot_Semanal__c(
                    Data__c = hoje, Nivel__c = 'Disciplina', Obra__c = o.Id, Disciplina_Obra__c = d.Id,
                    Receita__c = d.Receita__c, Margem_Estimada__c = d.Margem_Estimada__c,
                    Margem_Negociada__c = d.Margem_Negociada__c, Resultado_Projetado__c = d.Resultado_Projetado__c,
                    Grupo_Risco__c = d.Sem_Receita__c ? 'Sem receita orçada' : d.Grupo_Risco__c);
                Snapshot_Semanal__c ant = anterior.get(chave('Disciplina', o.Id, d.Id));
                sd.Alerta__c = alerta(sd, ant, p);
                Boolean aqAcima = d.Sem_Receita__c && d.Sigla__c == 'AQ' && o.Receita__c > 0
                    && d.Custo_Total__c / o.Receita__c * 100 > p.Limite_AQ_Sem_Escopo__c;
                Boolean antAcima = ant != null && ant.Alerta__c == 'AQ acima do limite';
                if (sd.Alerta__c == null && aqAcima && !antAcima) {
                    sd.Alerta__c = 'AQ acima do limite';
                }
                novos.add(sd);
            }
        }
        insert novos;
        res.snapshots = novos.size();
        for (Snapshot_Semanal__c s : novos) {
            if (s.Alerta__c != null) {
                res.alertas.add(s);
            }
        }
        return res;
    }

    @TestVisible
    private static String alerta(Snapshot_Semanal__c atual, Snapshot_Semanal__c ant, Parametro_Margem__mdt p) {
        Integer ga = ordem(atual.Grupo_Risco__c);
        if (ant == null) {
            return (ga != null && ga <= 2) ? 'Nova obra em risco' : null;
        }
        Integer gp = ordem(ant.Grupo_Risco__c);
        if (ga != null && gp != null && ga < gp) {
            return 'Piorou de grupo';
        }
        if (atual.Margem_Estimada__c != null && ant.Margem_Estimada__c != null
                && ant.Margem_Estimada__c - atual.Margem_Estimada__c >= p.Queda_Alerta__c) {
            return 'Queda de margem';
        }
        return null;
    }

    private static String chave(String nivel, Id obra, Id disciplina) {
        return nivel + '|' + obra + '|' + disciplina;
    }
}
