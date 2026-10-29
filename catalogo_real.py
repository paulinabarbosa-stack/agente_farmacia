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

MAX_PRODUTOS = 30

PALAVRAS_IGNORADAS = {
    "duas", "tres", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez", "onze", "doze",
    "meia", "duzia", "pacote", "pacotes", "frasco", "frascos", "tubo", "tubos", "blister", "cartelas",
    "preciso", "precisamos", "queremos", "necessito", "levar", "pegar", "adicionar", "incluir", "tambem",
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
    "preciso", "gostei", "tamanho", "tamanhos", "medicamentos", "produto", "produtos", "itens", "item", "dois", "tres", "quatro", "cinco", "pedir", "pedido", "somente", "apenas", "teria", "seria", "queria", "quer", "ser", "tinha", "existe", "haveria", "entao", "mesmo", "so", "porem", "mas", "tambem", "talvez", "acho", "pois", "devia", "deveria", "laboratorio", "lab", "marca", "generico", "similar", "referencia", "opcao", "opcoes", "outras", "gostaria", "alguma", "algum", "aquele", "aquela", "mesmo", "mesma", "pegar", "levar", "leva", "manda", "mandar", "envia", "enviar",
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
    # "40 mg" / "40 Mg" -> "40mg"
    t = re.sub(r"(\d)\s*(mg|mcg|ml|ui|g)\b", r"\1\2", t)
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


SINONIMOS = {
    "xarope": ["xarope", "xpe"],
    "gotas": ["gotas", "gts"],
    "solucao": ["solucao", "sol"],
    "suspensao": ["suspensao", "susp"],
    "pomada": ["pomada", "pom"],
    "creme": ["creme", "cr"],
    "colirio": ["colirio", "col"],
    "efervescente": ["efervescente", "efev", "efer"],
    "injetavel": ["injetavel", "inj"],
}


def _filtro_token(t):
    var = SINONIMOS.get(t)
    if not var:
        return f"nome.ilike.*{_padrao(t)}*"
    return "or(" + ",".join(f"nome.ilike.*{_padrao(v)}*" for v in var) + ")"


def _buscar_produtos(tokens):
    """Produtos cujo nome contem TODAS as palavras (ate 4)."""
    usados = list(tokens)[:4]
    if not usados:
        return []
    filtros = ",".join(_filtro_token(t) for t in usados)
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/produtos",
        headers=_headers(),
        params={"and": f"({filtros})", "select": "id,nome,preco", "order": "nome", "limit": 120},
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


ERROS_COMUNS = {
    "flauda": "fralda", "fralsa": "fralda", "frauda": "fralda", "fraldas": "fralda",
    "dipiron": "dipirona", "dipirina": "dipirona", "paracetamo": "paracetamol",
    "atorvastatina": "atorvastatina", "atorvastatia": "atorvastatina",
}


def _corrigir(tokens):
    return [ERROS_COMUNS.get(t, t) for t in tokens]


def _procurar(tokens):
    """Procura produtos COM estoque. A 1a palavra e o produto (nunca e solta).
    Se nao achar com todas, vai soltando as palavras do final (marca, tamanho,
    dosagem), uma por vez."""
    tokens = _corrigir(tokens)[:4]
    if not tokens:
        return []
    # tenta com a 1a palavra como produto; se nada, tenta sem ela (palavra solta no inicio)
    for ini in range(min(2, len(tokens))):
        resto = tokens[ini:]
        for k in range(len(resto), 0, -1):
            achados = _com_estoque(_buscar_produtos(resto[:k]))
            if achados:
                return achados
    return []


def _segmentos(texto):
    """Divide a mensagem em pedaços, um por produto pedido
    (ex.: '3 dipirona e 2 atorvastatina. e 1 fralda personal')."""
    partes = re.split(r"[.;\n,]| e | mais | alem d[eo] | tambem ", " " + (texto or "") + " ", flags=re.I)
    saida = []
    for p in partes:
        tk = _tokens(p)
        if tk:
            saida.append(tk)
    return saida[:4]


def _linhas(achados, limite):
    linhas = []
    for p in achados[:limite]:
        preco = float(p.get("preco") or 0)
        linhas.append(f"  - {p['nome']} | R$ {preco:.2f} | lojas: {', '.join(p['lojas'])}")
    if len(achados) > limite:
        linhas.append(f"  (+ {len(achados) - limite} outros itens parecidos nao listados)")
    return linhas


REGRAS = (
    "REGRAS DESTE CATALOGO: (1) Use somente nome, dosagem e preco EXATAMENTE como listados; "
    "nunca invente nem troque dosagem, apresentacao ou marca. "
    "(2) Cada linha e uma apresentacao diferente (marca, quantidade de comprimidos). Se houver varias "
    "opcoes, mostre cada uma com o nome completo e o preco dela, SEM inventar faixa de preco; se forem "
    "muitas, mostre as principais e pergunte qual o cliente prefere. Liste TODAS as dosagens diferentes "
    "(ex.: 10mg, 20mg, 40mg, 80mg), nao so as primeiras. "
    "(3) Se a dosagem ou o tipo muda o produto e o cliente nao disse, pergunte antes de fechar. "
    "(4) Nao diga a loja ao cliente a menos que ele pergunte. "
    "(5) Medicamentos que exigem receita seguem a regra de receita do roteiro. "
    "(6) Itens marcados como ENCONTRADO neste catalogo existem: NAO diga que nao temos e NAO use "
    "TRANSFERIR_ENCOMENDA para eles. "
    "(7) A tabela fixa de precos do roteiro tem valores ESTIMADOS e NAO vale mais para os produtos "
    "pedidos nesta mensagem: use SOMENTE os precos deste catalogo. Itens marcados NAO ENCONTRADO: mesmo que "
    "aparecam na tabela fixa, siga a regra de ENCOMENDA (pergunte o nome se ainda nao souber, depois "
    "TRANSFERIR_ENCOMENDA), mas SO depois de responder o que for possivel dos outros itens do pedido. "
    "(9) Se o cliente pediu uma dosagem, tamanho ou apresentacao (ex.: 40mg, tamanho G) e NENHUM item "
    "listado tem exatamente isso, diga com clareza que essa opcao nao esta disponivel e mostre o que ha, "
    "sem fingir que e a mesma coisa. "
    "(10) NUNCA informe um preco que nao esteja escrito neste catalogo. Se um item for NAO ENCONTRADO, nao "
    "cite preco dele, nao use precos de memoria, da tabela fixa ou de mensagens antigas desta conversa. "
    "Ao confirmar um pedido, use o nome completo e o preco exatos de uma linha deste catalogo. "
    "(8) NUNCA diga 'so um instante', 'ja volto', 'vou buscar o preco' ou 'vou verificar e retorno': voce "
    "nao consegue voltar depois. Responda tudo o que sabe AGORA, na mesma mensagem, e peca so o que "
    "realmente falta ao cliente."
)


def contexto_catalogo(texto_atual, textos_anteriores=None):
    """Devolve um bloco de texto com produtos reais em estoque, ou ''."""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return ""
    try:
        segmentos = _segmentos(texto_atual)
        if not segmentos:
            return ""
        # mensagem curta (ex.: "40mg", "o da cimed"): junta com o que veio antes
        if len(segmentos) == 1 and textos_anteriores and len(segmentos[0]) <= 3:
            atual = segmentos[0]
            extra = []
            for t in reversed(textos_anteriores[-3:]):
                extra += [x for x in _tokens(t) if x not in extra and x not in atual]
            if extra:
                segmentos = [atual + extra[:2]]
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=len(segmentos)) as ex:
            resultados = list(ex.map(_procurar, segmentos))
        limite = MAX_PRODUTOS if len(segmentos) == 1 else 12
        partes = []
        algum = False
        for tk, achados in zip(segmentos, resultados):
            pedido = " ".join(_corrigir(tk))
            if achados:
                algum = True
                partes.append(
                    f"ENCONTRADO - cliente pediu: \"{pedido}\" -> {len(achados)} item(ns) com estoque:\n"
                    + "\n".join(_linhas(achados, limite))
                )
            else:
                partes.append(f"NAO ENCONTRADO NO ESTOQUE - cliente pediu: \"{pedido}\"")
        print(f"[CATALOGO] segmentos={len(segmentos)} encontrados={sum(1 for r in resultados if r)}")
        return (
            "\n\nCATALOGO REAL DA FARMACIA (consultado agora no estoque; use ISTO para esta mensagem "
            "do cliente, tem prioridade sobre a tabela fixa de precos):\n"
            + "\n".join(partes) + "\n" + REGRAS
        )
    except Exception as e:
        print("[CATALOGO] erro:", e)
        return ""
