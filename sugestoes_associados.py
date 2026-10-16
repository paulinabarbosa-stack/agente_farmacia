"""
sugestoes_associados.py
Gera SUGESTOES de produtos complementares com IA, para o farmaceutico aprovar
na tela "Produtos Associados" do VidaFarma.

Como funciona (um lote por vez, chamado pelo job de sincronizacao de estoque):
1. Pega produtos que TEM ESTOQUE e ainda nao foram analisados.
2. Pede pra IA (gpt-4o-mini) ate 2 TIPOS de produto complementar (ex: "vitamina
   c", "soro fisiologico") - a IA NAO escolhe produto especifico. Cada ideia
   vem com uma nota de confianca de 1 a 5; so ficam as de nota 4 ou 5.
3. Procura no catalogo real um produto com esse termo, com estoque, e grava na
   tabela sugestoes_associados com status 'pendente'.

NADA vai pra Isabela sem aprovacao: a Isabela so le a tabela
produtos_associados, e uma sugestao so entra la quando o farmaceutico aprova.

Seguranca: a IA so sugere COMPLEMENTARES (nunca substitutos). Produtos que
precisam de receita, controlados, antibioticos, corticoides e de uso
dermatologico especifico NAO recebem sugestao.

LIGADO/DESLIGADO: so roda se a variavel de ambiente SUGESTOES_ATIVAS=true
estiver configurada no Railway.
"""

import os
import json
import requests

OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

PRODUTOS_POR_LOTE = 10          # quantos produtos analisa por ciclo (5 min)
MAX_SUGESTOES_POR_PRODUTO = 2
CONFIANCA_MINIMA = 4            # so grava ideias com nota >= 4 (escala 1 a 5)
MODELO = "gpt-4o-mini"

# Produtos que ja foram analisados nesta execucao (evita repetir a mesma
# analise a cada ciclo quando a IA nao acha nada util).
_ja_analisados = set()


def _ativo():
    return (
        os.environ.get("SUGESTOES_ATIVAS", "").strip().lower() == "true"
        and OPENAI_KEY
        and SUPABASE_URL
        and SUPABASE_SERVICE_ROLE_KEY
    )


def _headers():
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }


def _get_paginado(tabela, params, tamanho=1000, maximo=20000):
    """GET paginado no Supabase (limite padrao e 1000 por consulta)."""
    resultado = []
    offset = 0
    while offset < maximo:
        p = dict(params)
        p["limit"] = tamanho
        p["offset"] = offset
        r = requests.get(f"{SUPABASE_URL}/rest/v1/{tabela}", headers=_headers(), params=p, timeout=30)
        if not r.ok:
            print(f"[SUGESTOES] Erro ao ler {tabela}: {r.status_code} {r.text[:200]}")
            break
        pagina = r.json()
        if not isinstance(pagina, list) or not pagina:
            break
        resultado.extend(pagina)
        if len(pagina) < tamanho:
            break
        offset += tamanho
    return resultado


def _produtos_candidatos():
    """IDs de produtos com estoque, que ainda nao tem sugestao nem
    complementar cadastrado e nao foram analisados nesta execucao."""
    com_estoque = {
        e["produto_id"]
        for e in _get_paginado("estoque", {"select": "produto_id", "quantidade": "gt.0"})
        if e.get("produto_id")
    }
    ja_sugeridos = {
        s["produto_id"] for s in _get_paginado("sugestoes_associados", {"select": "produto_id"})
    }
    ja_cadastrados = {
        a["produto_id"]
        for a in _get_paginado("produtos_associados", {"select": "produto_id", "tipo": "eq.complementar"})
    }
    return [
        pid
        for pid in com_estoque
        if pid not in ja_sugeridos and pid not in ja_cadastrados and pid not in _ja_analisados
    ]


def _dados_produto(produto_id):
    """Le o nome do produto. (Nao pede 'marca': a coluna nao existe na tabela
    produtos e o Supabase devolvia erro.)"""
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/produtos",
        headers=_headers(),
        params={"id": f"eq.{produto_id}", "select": "id,nome", "limit": 1},
        timeout=20,
    )
    if not r.ok:
        print(f"[SUGESTOES] Erro ao ler produto {produto_id}: {r.status_code} {r.text[:200]}")
        return None
    dados = r.json()
    if dados:
        return dados[0]
    return None


def _pedir_ideias_ia(nome, marca):
    """Pergunta pra IA que TIPOS de produto combinam com esse. Retorna lista
    de {"termo": str, "motivo": str} ja filtrada por confianca."""
    prompt = (
        "Voce e um farmaceutico experiente de uma drogaria brasileira. Sua tarefa e indicar produtos "
        "COMPLEMENTARES: itens que o farmaceutico recomendaria NO BALCAO para quem esta comprando o "
        "produto abaixo, porque ajudam no MESMO problema de saude ou no mesmo tratamento.\n\n"
        f"Produto: {nome}" + (f" (marca {marca})" if marca else "") + "\n\n"
        "REGRAS (siga todas):\n"
        "1. Se o produto exige receita, e controlado, antibiotico, corticoide (ex: dexametasona, "
        "betametasona), anti-inflamatorio de uso sob prescricao, ou e de uso dermatologico "
        "especifico, devolva a lista VAZIA.\n"
        "2. So sugira item de venda livre que tenha ligacao DIRETA com a condicao que o produto trata "
        "(ex: para tosse com catarro, sugerir vitamina C ou xarope de apoio; para curativo, sugerir "
        "antisseptico). Nao use a ligacao generica 'faz bem a saude'.\n"
        "3. NAO sugira itens genericos so para preencher: hidratante, protetor solar, soro "
        "fisiologico e vitaminas sao proibidos, a menos que tenham ligacao direta e clara com o "
        "produto.\n"
        "4. NUNCA sugira outro medicamento para a mesma finalidade (isso seria substituto, nao "
        "complementar).\n"
        f"5. No maximo {MAX_SUGESTOES_POR_PRODUTO} sugestoes. Menos e melhor: se nao houver um "
        "complementar claro, devolva lista vazia. Lista vazia e uma resposta correta e comum.\n"
        '6. "termo" e a palavra de busca no catalogo: 1 ou 2 palavras, generica, sem marca '
        '(ex: "vitamina c", "antisseptico").\n'
        '7. "motivo" e uma frase curta em portugues explicando a ligacao direta com o produto.\n'
        '8. "confianca" e um numero de 1 a 5: 5 = recomendacao classica e segura; 4 = boa; '
        "3 ou menos = duvidosa (nesse caso, nem inclua).\n\n"
        'Responda SOMENTE com JSON: {"sugestoes": [{"termo": "...", "motivo": "...", "confianca": 5}]}'
    )
    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"},
        json={
            "model": MODELO,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        },
        timeout=60,
    )
    if not r.ok:
        print(f"[SUGESTOES] Erro na IA: {r.status_code} {r.text[:200]}")
        return []
    try:
        conteudo = r.json()["choices"][0]["message"]["content"]
        itens = json.loads(conteudo).get("sugestoes", [])
    except Exception as e:
        print("[SUGESTOES] Resposta da IA invalida:", e)
        return []

    ideias = []
    for item in itens[:MAX_SUGESTOES_POR_PRODUTO]:
        termo = str(item.get("termo", "")).strip()
        motivo = str(item.get("motivo", "")).strip()
        try:
            confianca = int(item.get("confianca", 0))
        except (TypeError, ValueError):
            confianca = 0
        if termo and confianca >= CONFIANCA_MINIMA:
            ideias.append({"termo": termo, "motivo": motivo})
    return ideias


def _buscar_no_catalogo(termo, excluir_id):
    """Acha no catalogo um produto COM ESTOQUE que combine com o termo.
    Tenta a expressao inteira; se nao achar, tenta a palavra mais longa."""
    tentativas = [termo]
    palavras = sorted([p for p in termo.split() if len(p) >= 5], key=len, reverse=True)
    if palavras and palavras[0].lower() != termo.lower():
        tentativas.append(palavras[0])

    for t in tentativas:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/produtos",
            headers=_headers(),
            params={"nome": f"ilike.*{t}*", "select": "id,nome", "limit": 40},
            timeout=20,
        )
        if not r.ok:
            print(f"[SUGESTOES]    Erro ao buscar '{t}' no catalogo: {r.status_code} {r.text[:200]}")
            continue
        candidatos = [p for p in r.json() if p.get("id") != excluir_id]
        if not candidatos:
            continue

        ids = ",".join(p["id"] for p in candidatos)
        re_est = requests.get(
            f"{SUPABASE_URL}/rest/v1/estoque",
            headers=_headers(),
            params={"produto_id": f"in.({ids})", "quantidade": "gt.0", "select": "produto_id,quantidade"},
            timeout=20,
        )
        if not re_est.ok:
            print(f"[SUGESTOES]    Erro ao ler estoque dos candidatos: {re_est.status_code} {re_est.text[:200]}")
            continue
        estoque_por_produto = {}
        for e in re_est.json():
            estoque_por_produto[e["produto_id"]] = estoque_por_produto.get(e["produto_id"], 0) + (e.get("quantidade") or 0)
        if not estoque_por_produto:
            continue
        # Escolhe o de maior estoque (mais facil de a farmacia ter pra entregar).
        melhor_id = max(estoque_por_produto, key=estoque_por_produto.get)
        return melhor_id
    return None


def _salvar_sugestao(produto_id, sugerido_id, motivo):
    headers = _headers()
    headers["Prefer"] = "resolution=ignore-duplicates"
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/sugestoes_associados",
        headers=headers,
        params={"on_conflict": "produto_id,produto_sugerido_id"},
        json={
            "produto_id": produto_id,
            "produto_sugerido_id": sugerido_id,
            "motivo": motivo or None,
            "status": "pendente",
        },
        timeout=20,
    )
    if not r.ok:
        print(f"[SUGESTOES] Erro ao salvar sugestao: {r.status_code} {r.text[:200]}")
        return False
    return True


def gerar_lote_de_sugestoes():
    """Analisa ate PRODUTOS_POR_LOTE produtos e grava as sugestoes pendentes.
    Chamado a cada ciclo do job de sincronizacao de estoque."""
    if not _ativo():
        return

    candidatos = _produtos_candidatos()
    if not candidatos:
        return

    lote = candidatos[:PRODUTOS_POR_LOTE]
    novas = 0
    for produto_id in lote:
        _ja_analisados.add(produto_id)
        produto = _dados_produto(produto_id)
        if not produto or not produto.get("nome"):
            print(f"[SUGESTOES] Produto {produto_id} sem nome no catalogo, pulado")
            continue

        ideias = _pedir_ideias_ia(produto["nome"], produto.get("marca"))
        termos = [i["termo"] for i in ideias]
        print(f"[SUGESTOES] '{produto['nome']}' -> IA sugeriu: {termos if termos else 'nada'}")
        for ideia in ideias:
            sugerido_id = _buscar_no_catalogo(ideia["termo"], produto_id)
            if not sugerido_id:
                print(f"[SUGESTOES]    '{ideia['termo']}': nenhum produto com estoque no catalogo")
                continue
            if _salvar_sugestao(produto_id, sugerido_id, ideia["motivo"]):
                novas += 1
                print(f"[SUGESTOES]    '{ideia['termo']}': sugestao salva")

    print(
        f"[SUGESTOES] Lote concluido: {len(lote)} produto(s) analisado(s), {novas} sugestao(oes) nova(s); "
        f"restam {max(0, len(candidatos) - len(lote))} produto(s) na fila"
    )