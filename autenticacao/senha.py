"""Senhas com bcrypt (custo 12, sal automático).

bcrypt é lento de propósito. SHA-256 puro aqui seria erro grave: hash rápido
serve à integridade (trilha de auditoria), não a credenciais.
"""
import re

import bcrypt

CUSTO = 12
# bcrypt só considera os primeiros 72 bytes; acima disso, rejeitamos explicitamente
LIMITE_BYTES = 72


def gerar_hash(senha, custo=CUSTO):
    dados = senha.encode("utf-8")
    if len(dados) > LIMITE_BYTES:
        raise ValueError("Senha acima de 72 bytes não é suportada pelo bcrypt")
    return bcrypt.hashpw(dados, bcrypt.gensalt(rounds=custo)).decode("ascii")


def verificar(senha, senha_hash):
    """True só se a senha confere. Qualquer anomalia (hash nulo/corrompido) -> False."""
    if not senha or not senha_hash:
        return False
    try:
        return bcrypt.checkpw(senha.encode("utf-8"), senha_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False


def avaliar_senha_forte(senha, minimo):
    """Política de senha forte do nível 3. Devolve a lista de pendências (vazia = forte)."""
    pendencias = []
    if len(senha) < minimo:
        pendencias.append(f"ao menos {minimo} caracteres")
    if not re.search(r"[a-z]", senha):
        pendencias.append("uma letra minúscula")
    if not re.search(r"[A-Z]", senha):
        pendencias.append("uma letra maiúscula")
    if not re.search(r"\d", senha):
        pendencias.append("um dígito")
    if not re.search(r"[^\w\s]", senha):
        pendencias.append("um símbolo")
    return pendencias
