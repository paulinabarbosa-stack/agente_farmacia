"""
sincronizar_produtos.py
Traz da HOS (/produto/ativos) os dados que faltam no cadastro `produtos` do
Supabase: descricao completa (com apresentacao e marca), fabricante e os
precos (Preco = lista, Prc_Venda = venda). Roda em background no Railway:
uma vez ~2 minutos depois de subir e depois a cada 6 horas.

Grava via a funcao SQL `atualizar_produtos_hos` (ver SQL de instalacao).
Nao mexe em nome, preco, categoria nem em nada que ja existe: so preenche
as colunas novas. Se der erro, so registra no log e tenta de novo depois.
"""
import os
import time
import requests

from hos_api import _hos_request, CHAVE_POR_CODIGO

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

ATRASO_INICIAL_SEGUNDOS = 120
INTERVALO_SEGUNDOS = 6 * 60 * 60
EAN_DE_CONFERENCIA = "7896523201078"  # Atorvastatina 40mg Cimed (conferencia no log)


def _headers_admin():
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }


def _minusculas(item):
    return {str(k).lower(): v for k, v in item.items()}


def _num(valor):
    try:
        if valor is None or valor == "":
            return None
        return float(str(valor).replace(",", "."))
    except Exception:
        return None


def _texto(valor):
    if valor is None:
        return None
    t = str(valor).strip()
    return t or None


def _ean_do_item(it):
    ean = _texto(it.get("codigobarras"))
    if ean:
        return ean
    lista = it.get("codigosbarras")
    if isinstance(lista, list) and lista:
        primeiro = lista[0]
        if isinstance(primeiro, dict):
            return _texto(primeiro.get("codigobarras") or primeiro.get("CodigoBarras"))
        return _texto(primeiro)
    return None


def _montar_registro(item):
    it = _minusculas(item)
    ean = _ean_do_item(it)
    if not ean:
        return None
    desc = _texto(it.get("descricao")) or ""
    apresentacao = _texto(it.get("apresentacao"))
    fabricante = _texto(it.get("fabricante") or it.get("laboratorio") or it.get("marca"))
    partes = [desc] if desc else []
    base = desc.lower()
    for extra in (apresentacao, fabricante):
        if extra and extra.lower() not in base:
            partes.append(extra)
            base += " " + extra.lower()
    return {
        "ean": ean,
        "descricao_completa": " ".join(partes) or None,
        "apresentacao": apresentacao,
        "fabricante": fabricante,
        "preco_lista": _num(it.get("preco")),
        "preco_venda": _num(it.get("prc_venda")),
        "hos_raw": item,
    }


def sincronizar_produtos_uma_vez():
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        print("[SINC PRODUTOS] SUPABASE_URL/SERVICE_ROLE_KEY nao configurados")
        return
    codigo = next((c for c in (139, 98, 97) if CHAVE_POR_CODIGO.get(c)), None)
    if not codigo:
        print("[SINC PRODUTOS] nenhuma chave HOS configurada")
        return

    dados = _hos_request(codigo, "/produto/ativos?limit=30000&offset=0")
    if isinstance(dados, dict):
        for chave in ("itens", "items", "produtos", "data", "result"):
            if isinstance(dados.get(chave), list):
                dados = dados[chave]
                break
    if not isinstance(dados, list):
        print("[SINC PRODUTOS] resposta inesperada da HOS:", str(dados)[:200])
        return
    print(f"[SINC PRODUTOS] {len(dados)} produtos ativos recebidos da HOS (codigo {codigo})")
    if dados and isinstance(dados[0], dict):
        print("[SINC PRODUTOS] campos de um item:", sorted(dados[0].keys()))

    registros = []
    for item in dados:
        if isinstance(item, dict):
            reg = _montar_registro(item)
            if reg:
                registros.append(reg)
                if reg["ean"] == EAN_DE_CONFERENCIA:
                    print("[SINC PRODUTOS] CONFERENCIA Atorvastatina Cimed:",
                          {k: v for k, v in reg.items() if k != "hos_raw"})

    atualizados = 0
    for i in range(0, len(registros), 500):
        lote = registros[i:i + 500]
        try:
            r = requests.post(
                f"{SUPABASE_URL}/rest/v1/rpc/atualizar_produtos_hos",
                headers=_headers_admin(), json={"p": lote}, timeout=120,
            )
            if r.ok:
                atualizados += int(r.json() or 0)
            else:
                print(f"[SINC PRODUTOS] erro no lote {i}: {r.status_code} {r.text[:300]}")
        except Exception as e:
            print(f"[SINC PRODUTOS] erro de rede no lote {i}:", e)
    print(f"[SINC PRODUTOS] concluido: {atualizados} produtos atualizados no Supabase")


def verificar_sincronizacao_produtos():
    time.sleep(ATRASO_INICIAL_SEGUNDOS)
    while True:
        try:
            sincronizar_produtos_uma_vez()
        except Exception as e:
            print("[SINC PRODUTOS] erro no ciclo:", e)
        time.sleep(INTERVALO_SEGUNDOS)
