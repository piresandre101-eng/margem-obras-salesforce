/**
 * Resumo semanal de alertas por e-mail ao usuário que agendou o job (no sistema original, o envio é
 * segmentado por P.O. e líder; aqui os P.O.s são texto anonimizado, sem usuário no org).
 * Só envia se houver alerta — mesma regra do sistema original ("só quando algo piora").
 */
public with sharing class AlertaEmailService {

    public static Boolean enviarResumo(List<Snapshot_Semanal__c> alertas, Date data) {
        if (alertas == null || alertas.isEmpty()) {
            return false;
        }
        Map<Id, Obra__c> obras = new Map<Id, Obra__c>();
        Set<Id> ids = new Set<Id>();
        for (Snapshot_Semanal__c s : alertas) {
            ids.add(s.Obra__c);
        }
        for (Obra__c o : [SELECT Id, Name, PO__c FROM Obra__c WHERE Id IN :ids]) {
            obras.put(o.Id, o);
        }
        Map<Id, Disciplina_Obra__c> discs = new Map<Id, Disciplina_Obra__c>();
        for (Snapshot_Semanal__c s : alertas) {
            if (s.Disciplina_Obra__c != null) {
                discs.put(s.Disciplina_Obra__c, null);
            }
        }
        for (Disciplina_Obra__c d : [SELECT Id, Sigla__c FROM Disciplina_Obra__c WHERE Id IN :discs.keySet()]) {
            discs.put(d.Id, d);
        }

        String linhas = '';
        for (Snapshot_Semanal__c s : alertas) {
            Obra__c o = obras.get(s.Obra__c);
            Disciplina_Obra__c d = s.Disciplina_Obra__c == null ? null : discs.get(s.Disciplina_Obra__c);
            linhas += '<tr><td>' + s.Alerta__c.escapeHtml4() + '</td><td>' + o.Name.escapeHtml4() + '</td><td>'
                + (d == null ? '—' : d.Sigla__c.escapeHtml4()) + '</td><td>'
                + (o.PO__c == null ? '' : o.PO__c.escapeHtml4()) + '</td><td>'
                + (s.Grupo_Risco__c == null ? '' : s.Grupo_Risco__c.escapeHtml4()) + '</td><td align="right">'
                + (s.Margem_Estimada__c == null ? '—' : s.Margem_Estimada__c.setScale(1) + '%') + '</td></tr>';
        }
        String corpo = '<p style="font-family:Arial">Atualização de <b>' + data.format() + '</b>: '
            + alertas.size() + ' alerta(s).</p>'
            + '<table border="1" cellpadding="4" style="border-collapse:collapse;font-family:Arial;font-size:9pt">'
            + '<tr><th>Alerta</th><th>Obra</th><th>Disciplina</th><th>P.O.</th><th>Grupo</th><th>Margem estimada</th></tr>'
            + linhas + '</table>';

        Messaging.SingleEmailMessage m = new Messaging.SingleEmailMessage();
        m.setTargetObjectId(UserInfo.getUserId());
        m.setSaveAsActivity(false);
        m.setSubject('[Margem de Obras] ' + alertas.size() + ' alerta(s) em ' + data.format());
        m.setHtmlBody(corpo);
        Messaging.sendEmail(new Messaging.SingleEmailMessage[] { m });
        return true;
    }
}
