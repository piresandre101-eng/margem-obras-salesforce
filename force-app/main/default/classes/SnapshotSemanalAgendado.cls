/**
 * Job agendado: toda segunda às 8h tira a foto semanal e envia o resumo de alertas por e-mail.
 *
 * Agendar (uma vez):  sf apex run --file scripts/apex/agendar_snapshot.apex
 */
public with sharing class SnapshotSemanalAgendado implements Schedulable {

    public static final String CRON_SEGUNDA_8H = '0 0 8 ? * MON';

    public void execute(SchedulableContext ctx) {
        SnapshotSemanalService.Resultado r = SnapshotSemanalService.executar(Date.today());
        AlertaEmailService.enviarResumo(r.alertas, Date.today());
    }

    public static Id agendar() {
        return System.schedule('Margem de Obras - snapshot semanal', CRON_SEGUNDA_8H, new SnapshotSemanalAgendado());
    }
}
