"""Relatórios do sistema S-01 a S-07 (Catálogo de Relatórios). Acesso: administrador."""
from dados.auditoria import TrilhaAuditoria
from dados.repositorio import RepositorioBloqueio, RepositorioUsuarios


class RelatoriosSistema:
    def __init__(self, banco):
        self.banco = banco

    def s01_log_acessos(self, limite=200):
        return self.banco.consultar(
            "SELECT id, momento, evento, usuario_id, usuario2_id, nivel_solicitado AS nivel, item_id, "
            "resultado, motivo, distancia FROM log_acesso ORDER BY id DESC LIMIT %s", (limite,))

    def s02_tentativas_negadas(self, limite=200):
        return self.banco.consultar(
            "SELECT l.id, l.momento, l.nivel_solicitado AS nivel, l.matricula_informada AS matricula, "
            "l.usuario_id, l.motivo, l.distancia, (t.id IS NOT NULL) AS foto, t.expira_em "
            "FROM log_acesso l LEFT JOIN tentativa_negada t ON t.log_id = l.id "
            "WHERE l.resultado = 'NEGADO' AND l.evento = 'AUTENTICACAO' ORDER BY l.id DESC LIMIT %s", (limite,))

    def s03_bloqueios_ativos(self):
        return RepositorioBloqueio(self.banco).ativos()

    def s04_integridade(self):
        return TrilhaAuditoria(self.banco).verificar()

    def s05_estatisticas_reconhecimento(self):
        return self.banco.consultar(
            "SELECT nivel_solicitado AS nivel, resultado, motivo, COUNT(*) AS eventos, "
            "ROUND(AVG(distancia), 2) AS distancia_media, ROUND(AVG(qualidade), 3) AS qualidade_media "
            "FROM log_acesso WHERE evento = 'AUTENTICACAO' "
            "GROUP BY nivel_solicitado, resultado, motivo ORDER BY nivel, resultado, eventos DESC")

    def s06_galeria_biometrica(self):
        return RepositorioUsuarios(self.banco).listar()

    def s07_auditoria_exportacao(self, limite=200):
        return self.banco.consultar(
            "SELECT l.id, l.momento, l.usuario_id, u.nome, l.nivel_solicitado AS nivel, i.codigo AS item, "
            "l.resultado, l.motivo FROM log_acesso l LEFT JOIN usuario u ON u.id = l.usuario_id "
            "LEFT JOIN item_acervo i ON i.id = l.item_id WHERE l.evento = 'EXPORTACAO' "
            "ORDER BY l.id DESC LIMIT %s", (limite,))

    # ------------------------------------------------------------ painel de gerenciamento
    # Indicadores de monitoramento. Cada um é uma consulta independente para que
    # o painel possa exibir "—" no indicador que falhar, em vez de não abrir.

    def contagem_usuarios(self):
        return self.banco.consultar(
            "SELECT nivel_id AS nivel, COUNT(*) AS usuarios, SUM(ativo) AS ativos "
            "FROM usuario GROUP BY nivel_id ORDER BY nivel_id")

    def contagem_amostras(self):
        return self.banco.consultar(
            "SELECT COUNT(*) AS amostras, COUNT(DISTINCT usuario_id) AS identidades, "
            "ROUND(AVG(qualidade), 3) AS qualidade_media FROM amostra")[0]

    def resumo_trilha(self):
        return self.banco.consultar(
            "SELECT COUNT(*) AS registros, MAX(momento) AS ultimo FROM log_acesso")[0]

    def contagem_negadas(self, horas=24):
        return self.banco.consultar(
            "SELECT COUNT(*) AS negadas FROM log_acesso WHERE resultado = 'NEGADO' "
            "AND evento = 'AUTENTICACAO' AND momento >= DATE_SUB(NOW(), INTERVAL %s HOUR)",
            (horas,))[0]["negadas"]

    def motivos_de_negacao(self, horas=24, limite=8):
        """Por que o acesso foi negado — orienta a calibragem dos limiares."""
        return self.banco.consultar(
            "SELECT motivo, nivel_solicitado AS nivel, COUNT(*) AS eventos, "
            "ROUND(AVG(distancia), 2) AS distancia_media FROM log_acesso "
            "WHERE resultado = 'NEGADO' AND momento >= DATE_SUB(NOW(), INTERVAL %s HOUR) "
            "GROUP BY motivo, nivel_solicitado ORDER BY eventos DESC LIMIT %s", (horas, limite))
