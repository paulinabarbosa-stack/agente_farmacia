"""
sincronizar_estoque.py
Job de sincronizacao periodica do estoque da HOS pro Supabase (tabela
estoque). Roda em background, no mesmo padrao dos outros jobs do backend
(verificar_seguimentos, verificar_lembretes_recompra, verificar_reaberturas_agendadas).

Fluxo de cada ciclo:
1. Busca o mapa de produtos (ean -> produto_id) e unidades (cnpj -> unidade_id)
   no Supabase.
2. Para cada codigo de empresa HOS configurado (ver hos_api.CHAVE_POR_CODIGO),
   busca o /estoque e faz upsert na tabela estoque.

IMPORTANTE - pre-requisito no banco: a tabela estoque precisa de uma
constraint UNIQUE em (produto_id, unidade_id) pro upsert funcionar. Se
ainda nao existir, rode uma vez no SQL Editor do Supabase:

    ALTER TABLE estoque
    ADD CONSTRAINT estoque_produto_unidade_unique UNIQUE (produto_id, unidade_id);

AVISO SOBRE O FORMATO DO /estoque DA HOS: a API nao documenta oficialmente
os nomes dos campos de cada item retornado. As funcoes _extrair_* abaixo
tentam os nomes mais provaveis (baseados no padrao Capitalizado usado nos
outros endpoints, tipo Cnpj, Descricao, CodigoBarras). No primeiro ciclo
rodando de verdade, o log vai imprimir um item bruto de exemplo - se algum
campo nao for encontrado (aparecer nos contadores de "pulados"), me manda
esse log que eu ajusto rapido.
"""

import os
import re
import time
import requests

from hos_api import get_estoque, CHAVE_POR_CODIGO

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

INTERVALO_SINCRONIZACAO_SEGUNDOS = 10 * 60  # 10 minutos


def _headers_admin():
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }


def _normalizar_cnpj(valor):
    """Remove tudo que nao for digito, pra poder comparar o CNPJ retornado
    pela HOS (geralmente so numeros) com o cadastrado em unidades.cnpj
    (que pode estar formatado, tipo 02.165.564/0002-90)."""
    if not valor:
        return ""
    return re.sub(r"\D", "", str(valor))


def buscar_todos_produtos():
    """Busca todos os produtos do Supabase (ean -> id), paginando de 1000 em
    1000 - o catalogo tem quase 15 mil itens e o Supabase limita por padrao
    a 1000 registros por consulta (mesmo problema ja resolvido antes nos
    dropdowns de Produtos Associados)."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        print("[SINCRONIZAR ESTOQUE] SUPABASE_URL ou SUPABASE_SERVICE_ROLE_KEY nao configurados")
        return {}

    mapa_ean_para_id = {}
    offset = 0
    tamanho_pagina = 1000

    while True:
        params = {
            "select": "id,ean",
            "ean": "not.is.null",
            "limit": tamanho_pagina,
            "offset": offset,
        }
        try:
            r = requests.get(f"{SUPABASE_URL}/rest/v1/produtos", headers=_headers_admin(), params=params, timeout=30)
        except Exception as e:
            print(f"[SINCRONIZAR ESTOQUE] Erro de rede ao buscar produtos (offset {offset}):", e)
            break

        if not r.ok:
            print(f"[SINCRONIZAR ESTOQUE] Erro ao buscar produtos (offset {offset}): {r.status_code} {r.text[:300]}")
            break

        pagina = r.json()
        if not isinstance(pagina, list) or not pagina:
            break

        for p in pagina:
            ean = p.get("ean")
            if ean:
                mapa_ean_para_id[str(ean)] = p["id"]

        if len(pagina) < tamanho_pagina:
            break
        offset += tamanho_pagina

    print(f"[SINCRONIZAR ESTOQUE] {len(mapa_ean_para_id)} produtos carregados (com ean) para o mapa de sincronizacao")
    return mapa_ean_para_id


def buscar_todas_unidades():
    """Busca todas as unidades do Supabase (cnpj normalizado -> id)."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return {}
    try:
        params = {"select": "id,cnpj,nome"}
        r = requests.get(f"{SUPABASE_URL}/rest/v1/unidades", headers=_headers_admin(), params=params, timeout=30)
        if not r.ok:
            print(f"[SINCRONIZAR ESTOQUE] Erro ao buscar unidades: {r.status_code} {r.text[:300]}")
            return {}
        dados = r.json()
        mapa = {}
        for u in dados:
            cnpj_norm = _normalizar_cnpj(u.get("cnpj"))
            if cnpj_norm:
                mapa[cnpj_norm] = u["id"]
        print(f"[SINCRONIZAR ESTOQUE] {len(mapa)} unidades carregadas para o mapa de sincronizacao")
        return mapa
    except Exception as e:
        print("[SINCRONIZAR ESTOQUE] Erro ao buscar unidades:", e)
        return {}


def _extrair_codigo_barras(item):
    """Tenta os nomes de campo mais provaveis pro codigo de barras dentro
    de um item retornado por /estoque. Retorna None se nao encontrar."""
    for chave in ("CodigoBarras", "codigoBarras", "codigo_barras", "Ean", "ean"):
        if item.get(chave):
            return str(item[chave])
    produto = item.get("Produto") or item.get("produto")
    if isinstance(produto, dict):
        for chave in ("CodigoBarras", "codigoBarras", "Ean", "ean"):
            if produto.get(chave):
                return str(produto[chave])
    return None


def _extrair_cnpj(item):
    for chave in ("Cnpj", "cnpj", "CnpjUnidade", "cnpjUnidade"):
        if item.get(chave):
            return str(item[chave])
    unidade = item.get("Unidade") or item.get("unidade")
    if isinstance(unidade, dict):
        for chave in ("Cnpj", "cnpj"):
            if unidade.get(chave):
                return str(unidade[chave])
    return None


def _extrair_quantidade(item):
    for chave in ("Quantidade", "quantidade", "Qtd", "qtd"):
        if item.get(chave) is not None:
            try:
                return float(item[chave])
            except (TypeError, ValueError):
                return None
    return None


def _upsert_estoque(produto_id, unidade_id, quantidade):
    """Insere ou atualiza uma linha na tabela estoque, usando produto_id +
    unidade_id como chave de conflito. Requer a constraint UNIQUE citada no
    topo do arquivo."""
    try:
        headers = _headers_admin()
        headers["Prefer"] = "resolution=merge-duplicates"
        body = {
            "produto_id": produto_id,
            "unidade_id": unidade_id,
            "quantidade": quantidade,
        }
        params = {"on_conflict": "produto_id,unidade_id"}
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/estoque", json=body, headers=headers, params=params, timeout=15
        )
        if not r.ok:
            print(
                f"[SINCRONIZAR ESTOQUE] Erro no upsert (produto_id={produto_id}, "
                f"unidade_id={unidade_id}): {r.status_code} {r.text[:300]}"
            )
    except Exception as e:
        print("[SINCRONIZAR ESTOQUE] Erro ao fazer upsert de estoque:", e)


def sincronizar_uma_vez():
    """Roda um ciclo completo de sincronizacao: busca os mapas de produtos
    e unidades, chama o /estoque da HOS para cada codigo de empresa
    configurado, e grava no Supabase."""
    mapa_produtos = buscar_todos_produtos()
    mapa_unidades = buscar_todas_unidades()

    if not mapa_produtos or not mapa_unidades:
        print("[SINCRONIZAR ESTOQUE] Mapa de produtos ou unidades vazio - abortando ciclo")
        return

    for codigo, chave in CHAVE_POR_CODIGO.items():
        if not chave:
            print(f"[SINCRONIZAR ESTOQUE] Codigo {codigo} sem chave configurada - pulando")
            continue

        try:
            itens = get_estoque(codigo)
        except Exception as e:
            print(f"[SINCRONIZAR ESTOQUE] Erro ao buscar /estoque do codigo {codigo}:", e)
            continue

        if not isinstance(itens, list):
            print(f"[SINCRONIZAR ESTOQUE] Resposta inesperada do /estoque (codigo {codigo}): {str(itens)[:300]}")
            continue

        print(f"[SINCRONIZAR ESTOQUE] Codigo {codigo}: {len(itens)} registro(s) recebido(s)")

        if itens:
            print(f"[SINCRONIZAR ESTOQUE] Exemplo de item bruto (codigo {codigo}): {itens[0]}")

        atualizados = 0
        pulados_produto = 0
        pulados_unidade = 0
        pulados_quantidade = 0

        for item in itens:
            codigo_barras = _extrair_codigo_barras(item)
            cnpj = _normalizar_cnpj(_extrair_cnpj(item))
            quantidade = _extrair_quantidade(item)

            produto_id = mapa_produtos.get(codigo_barras) if codigo_barras else None
            unidade_id = mapa_unidades.get(cnpj) if cnpj else None

            if not produto_id:
                pulados_produto += 1
                continue
            if not unidade_id:
                pulados_unidade += 1
                continue
            if quantidade is None:
                pulados_quantidade += 1
                continue

            _upsert_estoque(produto_id, unidade_id, quantidade)
            atualizados += 1

        print(
            f"[SINCRONIZAR ESTOQUE] Codigo {codigo} concluido: {atualizados} atualizado(s), "
            f"{pulados_produto} sem produto correspondente, {pulados_unidade} sem unidade correspondente, "
            f"{pulados_quantidade} sem quantidade valida"
        )


def verificar_sincronizacao_estoque():
    """Loop em background - roda a sincronizacao a cada
    INTERVALO_SINCRONIZACAO_SEGUNDOS. Mesmo padrao dos outros verificadores
    do backend (verificar_seguimentos, verificar_lembretes_recompra etc)."""
    while True:
        try:
            print("[SINCRONIZAR ESTOQUE] Iniciando ciclo de sincronizacao...")
            sincronizar_uma_vez()
        except Exception as e:
            print("[SINCRONIZAR ESTOQUE] Erro no ciclo de sincronizacao:", e)

        time.sleep(INTERVALO_SINCRONIZACAO_SEGUNDOS)