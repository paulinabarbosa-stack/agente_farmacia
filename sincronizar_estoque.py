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

FORMATO REAL DO /estoque (confirmado em producao, 28/07/2026): cada item
retornado representa um PRODUTO, com uma lista aninhada "Estoques" contendo
uma entrada por loja onde ele tem estoque. Exemplo real:

    {
      "Produto": "7896658002113",              # o proprio codigo de barras
      "CodigoInterno": 9,
      "ListaEans": [{"CodigoBarras": "7896658002113"}],
      "Estoques": [{"CNPJ": "02165564000290", "Quantidade": 3}]
    }

IMPORTANTE - pre-requisito no banco: a tabela estoque precisa de uma
constraint UNIQUE em (produto_id, unidade_id) pro upsert funcionar. Se
ainda nao existir, rode uma vez no SQL Editor do Supabase:

    ALTER TABLE estoque
    ADD CONSTRAINT estoque_produto_unidade_unique UNIQUE (produto_id, unidade_id);
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
    pela HOS (so numeros) com o cadastrado em unidades.cnpj (que pode estar
    formatado, tipo 02.165.564/0002-90)."""
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
    """O campo 'Produto' retornado pela HOS ja e o proprio codigo de
    barras (confirmado em producao). 'ListaEans' serve de fallback caso
    'Produto' venha vazio em algum registro."""
    if item.get("Produto"):
        return str(item["Produto"])
    lista_eans = item.get("ListaEans")
    if isinstance(lista_eans, list) and lista_eans:
        primeiro = lista_eans[0]
        if isinstance(primeiro, dict) and primeiro.get("CodigoBarras"):
            return str(primeiro["CodigoBarras"])
    return None


def _extrair_quantidade(estoque_item):
    for chave in ("Quantidade", "quantidade", "Qtd", "qtd"):
        if estoque_item.get(chave) is not None:
            try:
                return float(estoque_item[chave])
            except (TypeError, ValueError):
                return None
    return None


def _upsert_estoque(produto_id, unidade_id, quantidade):
    """Insere ou atualiza uma linha na tabela estoque, usando produto_id +
    unidade_id como chave de conflito. Requer a constraint UNIQUE citada no
    topo do arquivo.

    A coluna estoque.quantidade e do tipo integer no Supabase - por isso
    convertemos aqui antes de enviar (a HOS pode mandar a quantidade como
    float, tipo 3.0)."""
    try:
        quantidade_int = int(round(quantidade))

        headers = _headers_admin()
        headers["Prefer"] = "resolution=merge-duplicates"
        body = {
            "produto_id": produto_id,
            "unidade_id": unidade_id,
            "quantidade": quantidade_int,
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
    configurado, e grava no Supabase.

    Cada item do /estoque representa UM PRODUTO, com uma lista aninhada
    "Estoques" contendo uma entrada por loja onde ele tem estoque."""
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

        print(f"[SINCRONIZAR ESTOQUE] Codigo {codigo}: {len(itens)} produto(s) recebido(s)")

        if itens:
            print(f"[SINCRONIZAR ESTOQUE] Exemplo de item bruto (codigo {codigo}): {itens[0]}")

        atualizados = 0
        pulados_produto = 0
        pulados_unidade = 0
        pulados_quantidade = 0
        pulados_sem_estoques = 0

        for item in itens:
            codigo_barras = _extrair_codigo_barras(item)
            produto_id = mapa_produtos.get(codigo_barras) if codigo_barras else None

            if not produto_id:
                pulados_produto += 1
                continue

            lista_estoques = item.get("Estoques")
            if not isinstance(lista_estoques, list) or not lista_estoques:
                pulados_sem_estoques += 1
                continue

            for estoque_item in lista_estoques:
                if not isinstance(estoque_item, dict):
                    continue

                cnpj = _normalizar_cnpj(estoque_item.get("CNPJ") or estoque_item.get("Cnpj"))
                quantidade = _extrair_quantidade(estoque_item)
                unidade_id = mapa_unidades.get(cnpj) if cnpj else None

                if not unidade_id:
                    pulados_unidade += 1
                    continue
                if quantidade is None:
                    pulados_quantidade += 1
                    continue

                _upsert_estoque(produto_id, unidade_id, quantidade)
                atualizados += 1

        print(
            f"[SINCRONIZAR ESTOQUE] Codigo {codigo} concluido: {atualizados} linha(s) de estoque atualizada(s), "
            f"{pulados_produto} produto(s) sem correspondencia no Supabase, "
            f"{pulados_sem_estoques} produto(s) sem lista de Estoques, "
            f"{pulados_unidade} entrada(s) sem unidade correspondente, "
            f"{pulados_quantidade} entrada(s) sem quantidade valida"
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