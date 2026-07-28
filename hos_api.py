"""
hos_api.py
Cliente Python para a API HOS E-commerce (autorizadorfarma.hos.com.br).
Portado do hosApi.ts (TypeScript) ja existente no projeto VidaFarma.

Faz login automatico por unidade (codigo de empresa), guarda o token em
cache e renova sozinho antes de expirar. Todas as chamadas a API da HOS
devem passar por este arquivo - nunca chamar requests direto pra HOS em
outro lugar do backend.

CONFIGURACAO NECESSARIA (variaveis de ambiente no Railway):
    HOS_BASE_URL=http://autorizadorfarma.hos.com.br/ecommerce/api/v2
    HOS_CHAVE_98=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    HOS_CHAVE_139=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    HOS_CHAVE_97=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

Nunca commitar as chaves reais no codigo - elas ficam so nas variaveis
de ambiente do Railway.
"""

import os
import time
import requests

HOS_BASE_URL = os.environ.get("HOS_BASE_URL", "http://autorizadorfarma.hos.com.br/ecommerce/api/v2")

# Mapa de codigo de empresa -> variavel de ambiente com a chave de acesso.
# Adicione uma linha aqui pra cada nova unidade que for integrada (ex: quando
# o codigo 97/Cazuza tiver o servidor instalado).
CHAVE_POR_CODIGO = {
    98: os.environ.get("HOS_CHAVE_98"),    # Matriz + Filial 2/Rio Grande (confirmado)
    139: os.environ.get("HOS_CHAVE_139"),  # Parceiro integrador (Inova IA)
    97: os.environ.get("HOS_CHAVE_97"),    # Filial 1/Cazuza - ainda nao instalada
}

# Margem de seguranca: renova o token se faltar menos que isso pra expirar.
MARGEM_RENOVACAO_SEGUNDOS = 2 * 60  # 2 minutos

# Cache de token em memoria, por codigo de empresa.
# Cada entrada: {"access_token": str, "expira_em": epoch em segundos}
_token_cache = {}


def _login(codigo):
    """Faz login na HOS para um codigo de empresa especifico e retorna o
    token. Nao usa cache - sempre gera um token novo."""
    chave_acesso = CHAVE_POR_CODIGO.get(codigo)
    if not chave_acesso:
        raise Exception(
            f"Nao ha chave de acesso configurada para o codigo de empresa {codigo}. "
            f"Verifique a variavel de ambiente HOS_CHAVE_{codigo}."
        )

    resposta = requests.post(
        f"{HOS_BASE_URL}/login",
        json={"codigo": codigo, "chave_acesso": chave_acesso},
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        timeout=20,
    )

    if not resposta.ok:
        raise Exception(f"Falha no login HOS para o codigo {codigo}: HTTP {resposta.status_code}")

    dados = resposta.json()

    if not dados.get("authenticated"):
        raise Exception(f"Login HOS recusado para o codigo {codigo}: {dados.get('message')}")

    # A API retorna "expiration" como "YYYY-MM-DD HH:mm:ss" (horario do servidor).
    expiracao_str = dados["expiration"].replace(" ", "T")
    expira_em = time.mktime(time.strptime(expiracao_str, "%Y-%m-%dT%H:%M:%S"))

    entrada = {"access_token": dados["accessToken"], "expira_em": expira_em}
    _token_cache[codigo] = entrada
    return entrada


def _get_token_valido(codigo):
    """Retorna um token valido pro codigo de empresa informado, fazendo
    login automaticamente se nao houver token em cache ou se ele estiver
    vencido (ou perto de vencer)."""
    cacheado = _token_cache.get(codigo)
    agora = time.time()

    if cacheado and (cacheado["expira_em"] - agora) > MARGEM_RENOVACAO_SEGUNDOS:
        return cacheado["access_token"]

    novo = _login(codigo)
    return novo["access_token"]


def _hos_request(codigo, path, method="GET", body=None, tentativa_de_retry=False):
    """Faz uma chamada autenticada a API HOS pro codigo de empresa informado.
    Renova o token automaticamente se necessario, e tenta de novo uma vez se
    a API responder 401 mesmo com um token que parecia valido."""
    access_token = _get_token_valido(codigo)

    headers = {
        "Accept": "application/json",
        "Empresa": str(codigo),
        "Authorization": f"Bearer {access_token}",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"

    resposta = requests.request(
        method,
        f"{HOS_BASE_URL}{path}",
        headers=headers,
        json=body if body is not None else None,
        timeout=60,
    )

    if resposta.status_code == 401 and not tentativa_de_retry:
        # Token pode ter sido revogado antes da hora prevista - forca um
        # novo login e tenta a chamada mais uma vez.
        _token_cache.pop(codigo, None)
        return _hos_request(codigo, path, method=method, body=body, tentativa_de_retry=True)

    if not resposta.ok:
        raise Exception(
            f"Erro na chamada HOS ({method} {path}) para o codigo {codigo}: HTTP {resposta.status_code}"
        )

    return resposta.json()


def get_unidades(codigo):
    """GET /unidade - lista os estabelecimentos vinculados ao codigo de empresa."""
    return _hos_request(codigo, "/unidade")


def get_estoque(codigo, limit=100000, offset=0):
    """GET /estoque - lista o estoque reportado pela unidade.

    IMPORTANTE: o parametro offset da API HOS e quebrado (offset>0 sempre
    retorna vazio, mesmo havendo mais registros por tras) - a mesma falha
    ja confirmada em /produto/ativos. Por isso usamos sempre offset=0 com
    um limit bem alto numa unica chamada, igual foi feito em
    sincronizarProdutos.ts.
    """
    return _hos_request(codigo, f"/estoque?limit={limit}&offset={offset}")