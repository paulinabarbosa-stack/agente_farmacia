"""Catalogo real da Drogaria Saude e Vida para a Isabela.

Busca em `produtos` + `estoque` (Supabase) o que o cliente pediu e devolve um
texto para ser colocado no contexto da IA. So lista produtos COM estoque.
Se der qualquer erro, devolve "" e a Isabela segue como antes (tabela fixa).
"""
import os
import re
import unicodedata
import requests

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

MAX_PRODUTOS = 8

PALAVRAS_IGNORADAS = {
    "tem", "tenho", "temos", "quero", "queria", "gostaria", "preciso", "precisa", "voces",
    "vcs", "para", "pra", "uma", "umas", "uns", "com", "sem", "por", "favor", "pode",
    "poderia", "verificar", "verifica", "valor", "preco", "quanto", "custa", "fica",
    "sobre", "esse", "essa", "esse", "aqui", "ola", "oi", "bom", "boa", "dia", "tarde",
    "noite", "obrigado", "obrigada", "sim", "nao", "isso", "isto", "outro", "outra",
    "mais", "menos", "estoque", "disponivel", "remedio", "medicamento", "comprar",
    "compra", "pedido", "pagamento", "pix", "cartao", "dinheiro", "entrega", "entregar",
    "retirar", "buscar", "endereco", "cpf", "nome", "cidade", "rua", "numero", "casa",
    "ficou", "total", "frete", "taxa", "caixa", "caixas", "cartela", "unidade",
    "unidades", "comprimido", "comprimidos", "capsula", "capsulas", "ainda", "tambem",
    "quais", "qual", "como", "esta", "estao", "vai", "vou", "muito", "tudo", "certo",
    "claro", "ok", "blz", "beleza", "obg", "vlw", "valeu", "agora", "hoje", "amanha",
    "preciso", "gostei", "pegar", "levar", "leva", "manda", "mandar", "envia", "enviar",
}


def _sem_acento(texto):
    return "".join(
        c for c in unicodedata.normalize("NFD", texto or "") if unicodedata.category(c) != "Mn"
    ).lower()


def _padrao(token):
    # vogais viram '_' (coringa) para achar com ou sem acento no catalogo
    return "".join("_" if c in "aeiou" else c for c in token)


def _tokens(texto):
    t = _sem_acento(texto)
    achados = re.findall(r"[a-z0-9]+", t)
    saida = []
    for p in achados:
        if p in PALAVRAS_IGNORADAS:
            continue
        # dosagens (500mg, 40mg, 10ml) valem; palavras curtas nao
        if re.fullmatch(r"\d+(mg|g|ml|mcg|ui)", p) or len(p) >= 4:
            if p not in saida:
                saida.append(p)
    return saida


def _headers():
    return {"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {SUPABASE_ANON_KEY}"}


def _buscar_produtos(tokens):
    """Produtos cujo nome contem TODOS os tokens (ate 3, os mais longos primeiro)."""
    usados = sorted(tokens, key=len, reverse=True)[:3]
    if not usados:
        return []
    filtros = ",".join(f"nome.ilike.*{_padrao(t)}*" for t in usados)
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/produtos",
        headers=_headers(),
        params={"and": f"({filtros})", "select": "id,nome,preco", "order": "nome", "limit": 60},
        timeout=15,
    )
    if not r.ok:
        print(f"[CATALOGO] erro produtos: {r.status_code} {r.text[:150]}")
        return []
    return r.json()


def _com_estoque(produtos):
    if not produtos:
        return []
    ids = ",".join(p["id"] for p in produtos)
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/estoque",
        headers=_headers(),
        params={
            "produto_id": f"in.({ids})",
            "quantidade": "gt.0",
            "select": "produto_id,quantidade,unidades(nome)",
            "limit": 1000,
        },
        timeout=15,
    )
    if not r.ok:
        print(f"[CATALOGO] erro estoque: {r.status_code} {r.text[:150]}")
        return []
    lojas = {}
    for e in r.json():
        nome_loja = (e.get("unidades") or {}).get("nome") or "loja"
        lojas.setdefault(e["produto_id"], []).append(nome_loja)
    resultado = []
    for p in produtos:
        if p["id"] in lojas:
            resultado.append({**p, "lojas": sorted(set(lojas[p["id"]]))})
    return resultado


def contexto_catalogo(texto_atual, textos_anteriores=None):
    """Devolve um bloco de texto com produtos reais em estoque, ou ''."""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return ""
    try:
        tokens = _tokens(texto_atual)
        if not tokens:
            return ""
        tentativas = [tokens]
        # mensagem curta (ex.: "40mg", "o da cimed"): junta com o que veio antes
        if textos_anteriores and len(tokens) <= 2:
            extra = []
            for t in reversed(textos_anteriores[-3:]):
                extra += [x for x in _tokens(t) if x not in extra and x not in tokens]
            if extra:
                tentativas.insert(0, tokens + extra[:2])
        achados = []
        for tk in tentativas:
            achados = _com_estoque(_buscar_produtos(tk))
            if achados:
                break
        if not achados and len(tokens) > 1:
            achados = _com_estoque(_buscar_produtos([max(tokens, key=len)]))
        if not achados:
            return ""
        total = len(achados)
        linhas = []
        for p in achados[:MAX_PRODUTOS]:
            preco = float(p.get("preco") or 0)
            linhas.append(
                f"- {p['nome']} | R$ {preco:.2f} | disponivel em: {', '.join(p['lojas'])}"
            )
        bloco = (
            "\n\nCATALOGO REAL DA FARMACIA (consultado agora no estoque; use ISTO para esta "
            "mensagem do cliente, tem prioridade sobre a tabela fixa de precos): "
            f"{total} produto(s) com estoque encontrado(s)"
            + (f", mostrando os {MAX_PRODUTOS} primeiros" if total > MAX_PRODUTOS else "")
            + ":\n" + "\n".join(linhas) + "\n"
            "REGRAS DESTE CATALOGO: (1) Use somente nome, dosagem e preco EXATAMENTE como "
            "listados; nunca invente nem troque dosagem, apresentacao ou marca. "
            "(2) Se houver varias opcoes (dosagens/marcas diferentes), mostre as principais "
            "e pergunte qual o cliente quer, sem escolher por ele. (3) Se o cliente nao disse "
            "a dosagem e ela muda o produto, pergunte antes de fechar. (4) Nao diga a loja ao "
            "cliente a menos que ele pergunte; basta confirmar que temos. (5) Medicamentos que "
            "exigem receita continuam seguindo a regra de receita do seu roteiro. "
            "(6) Como o produto esta neste catalogo, NAO use TRANSFERIR_ENCOMENDA por ele "
            "nem diga que nao temos."
        )
        return bloco
    except Exception as e:
        print("[CATALOGO] erro:", e)
        return ""
