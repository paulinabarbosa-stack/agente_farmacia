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

INTERVALO_SINCRONIZACAO_SEGUNDOS = 5 * 60  # 5 minutos (orientacao da HOS: 3 a 5 min)

# Margem de seguranca ao gravar o "lastupdate": volta 2 min no relogio pra nao
# perder alteracao que aconteceu durante a propria consulta. Reprocessar um
# item duas vezes e inofensivo (o upsert so sobrescreve com o mesmo valor).
MARGEM_LASTUPDATE_SEGUNDOS = 120

# A cada quanto tempo faz uma carga COMPLETA (lastupdate=0) como rede de
# seguranca, caso alguma alteracao incremental tenha escapado.
INTERVALO_CARGA_COMPLETA_SEGUNDOS = 6 * 60 * 60  # 6 horas

# Cache dos mapas ean->produto e cnpj->unidade (evita baixar 15 mil produtos
# do Supabase a cada 5 minutos).
VALIDADE_MAPAS_SEGUNDOS = 30 * 60  # 30 minutos

# Estado em memoria. Se o Railway reiniciar, o primeiro ciclo faz carga completa.
_ultimo_lastupdate = {}        # codigo -> timestamp unix da ultima consulta
_ultima_carga_completa = {}    # codigo -> timestamp da ultima carga completa
_cache_mapas = {"produtos": {}, "unidades": {}, "carregado_em": 0}


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


LIMITE_PAGINAS_ESTOQUE = 200          # trava de seguranca contra loop infinito
PAUSA_ENTRE_PAGINAS_SEGUNDOS = 1      # evita bloqueio do Cloudflare


def _buscar_estoque_paginado(codigo, lastupdate):
    """Busca o /estoque inteiro. Pede limit alto; se a HOS devolver so uma
    parte (ex: 200 por chamada), continua pedindo com offset ate acabar.
    Para sozinho se a pagina vier vazia, menor que a primeira, ou repetida
    (caso o offset seja ignorado pela HOS)."""
    primeira = get_estoque(codigo, lastupdate=lastupdate)
    if not isinstance(primeira, list):
        return primeira
    todos = list(primeira)
    tamanho_pagina = len(primeira)
    if tamanho_pagina == 0:
        return todos

    # Se veio menos que 200, nao ha o que paginar (resposta ja completa).
    if tamanho_pagina < 200:
        return todos

    chave_primeiro = str(primeira[0])
    offset = tamanho_pagina
    for _ in range(LIMITE_PAGINAS_ESTOQUE):
        time.sleep(PAUSA_ENTRE_PAGINAS_SEGUNDOS)
        pagina = get_estoque(codigo, offset=offset, lastupdate=lastupdate)
        if not isinstance(pagina, list) or not pagina:
            break
        if str(pagina[0]) == chave_primeiro:
            print(f"[SINCRONIZAR ESTOQUE] Codigo {codigo}: HOS ignorou o offset ({offset}) - parando paginacao")
            break
        todos.extend(pagina)
        if len(pagina) < tamanho_pagina:
            break
        offset += len(pagina)

    print(f"[SINCRONIZAR ESTOQUE] Codigo {codigo}: paginacao concluida com {len(todos)} produto(s)")
    return todos


def _obter_mapas():
    """Retorna (mapa_produtos, mapa_unidades), recarregando do Supabase so
    quando o cache venceu."""
    agora = time.time()
    if (
        _cache_mapas["produtos"]
        and _cache_mapas["unidades"]
        and (agora - _cache_mapas["carregado_em"]) < VALIDADE_MAPAS_SEGUNDOS
    ):
        return _cache_mapas["produtos"], _cache_mapas["unidades"]

    mapa_produtos = buscar_todos_produtos()
    mapa_unidades = buscar_todas_unidades()
    if mapa_produtos and mapa_unidades:
        _cache_mapas["produtos"] = mapa_produtos
        _cache_mapas["unidades"] = mapa_unidades
        _cache_mapas["carregado_em"] = agora
    return mapa_produtos, mapa_unidades


def sincronizar_uma_vez():
    """Roda um ciclo de sincronizacao. Para cada codigo de empresa:
    - primeira vez (ou a cada 6h): carga COMPLETA (lastupdate=0);
    - demais ciclos: INCREMENTAL, so o que mudou desde a ultima consulta.

    Cada item do /estoque representa UM PRODUTO, com uma lista aninhada
    "Estoques" contendo uma entrada por loja onde ele tem estoque."""
    mapa_produtos, mapa_unidades = _obter_mapas()

    if not mapa_produtos or not mapa_unidades:
        print("[SINCRONIZAR ESTOQUE] Mapa de produtos ou unidades vazio - abortando ciclo")
        return

    for codigo, chave in CHAVE_POR_CODIGO.items():
        if not chave:
            print(f"[SINCRONIZAR ESTOQUE] Codigo {codigo} sem chave configurada - pulando")
            continue

        agora = time.time()
        precisa_completa = (
            codigo not in _ultimo_lastupdate
            or (agora - _ultima_carga_completa.get(codigo, 0)) >= INTERVALO_CARGA_COMPLETA_SEGUNDOS
        )
        lastupdate = 0 if precisa_completa else _ultimo_lastupdate[codigo]
        modo = "COMPLETA" if precisa_completa else f"incremental (lastupdate={lastupdate})"

        # Guarda o instante ANTES da consulta (menos a margem), pra nao perder
        # nada que mude enquanto a chamada esta em andamento.
        marca_desta_consulta = int(agora) - MARGEM_LASTUPDATE_SEGUNDOS

        try:
            itens = _buscar_estoque_paginado(codigo, lastupdate)
        except Exception as e:
            print(f"[SINCRONIZAR ESTOQUE] Erro ao buscar /estoque do codigo {codigo}:", e)
            continue

        if not isinstance(itens, list):
            print(f"[SINCRONIZAR ESTOQUE] Resposta inesperada do /estoque (codigo {codigo}): {str(itens)[:300]}")
            continue

        print(f"[SINCRONIZAR ESTOQUE] Codigo {codigo} [{modo}]: {len(itens)} produto(s) recebido(s)")

        atualizados = 0
        pulados_produto = 0
        pulados_unidade = 0
        pulados_quantidade = 0
        pulados_sem_estoques = 0
        exemplos_sem_correspondencia = []

        for item in itens:
            codigo_barras = _extrair_codigo_barras(item)
            produto_id = mapa_produtos.get(codigo_barras) if codigo_barras else None

            if not produto_id:
                pulados_produto += 1
                if len(exemplos_sem_correspondencia) < 5:
                    exemplos_sem_correspondencia.append(codigo_barras)
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
        if exemplos_sem_correspondencia:
            print(f"[SINCRONIZAR ESTOQUE] Exemplos sem correspondencia (ate 5): {exemplos_sem_correspondencia}")

        # So avanca o lastupdate depois de processar com sucesso.
        _ultimo_lastupdate[codigo] = marca_desta_consulta
        if precisa_completa:
            _ultima_carga_completa[codigo] = agora


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