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
    "querer", "quiser", "queira", "vamos", "podemos", "podem", "separa", "separar", "coloca", "colocar",
    "bota", "botar", "mande", "levo", "levarei", "ficar", "fico", "ajuda", "ajudar", "saber", "falar",
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
    "fralda": ["fralda", "frd"],
    "fraldas": ["fralda", "frd"],
    "absorvente": ["absorvente", "abs"],
    "shampoo": ["shampoo", "xampu", "sh "],
    "condicionador": ["condicionador", "cond"],
    "protetor": ["protetor", "prot"],
    "comprimido": ["comprimido", "cpr", "comp"],
    "xarope": ["xarope", "xpe", "sol", "susp"],
    "gotas": ["gotas", "gts"],
    "solucao": ["solucao", "sol"],
    "suspensao": ["suspensao", "susp"],
    "pomada": ["pomada", "pom"],
    "creme": ["creme", "cr"],
    "colirio": ["colirio", "col"],
    "efervescente": ["efervescente", "efev", "efer"],
    "injetavel": ["injetavel", "inj"],
    "espinha": ["espinha", "acne"],
    "espinhas": ["espinha", "acne"],
    "acne": ["espinha", "acne"],
    "acnes": ["espinha", "acne"],
}


def _filtro_token(t):
    # procura no nome (que o HOS corta em 25 letras, ex.: "...40M") e tambem na
    # descricao completa guardada na sincronizacao (ex.: "...40MG C/30CPR REV")
    var = SINONIMOS.get(t, [t])
    partes = []
    for v in var:
        p = _padrao(v)
        partes.append(f"nome.ilike.*{p}*")
        partes.append(f"descricao_completa.ilike.*{p}*")
    return "or(" + ",".join(partes) + ")"


def _buscar_produtos(tokens):
    """Produtos cujo nome contem TODAS as palavras (ate 4)."""
    usados = list(tokens)[:4]
    if not usados:
        return []
    filtros = ",".join(_filtro_token(t) for t in usados)
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/produtos",
        headers=_headers(),
        params={"and": f"({filtros})", "select": "id,nome,preco,preco_venda,descricao_completa", "order": "nome", "limit": 120},
        timeout=15,
    )
    if not r.ok:
        print(f"[CATALOGO] erro produtos: {r.status_code} {r.text[:150]}")
        return []
    return r.json()


def _com_estoque(produtos):
    if not produtos:
        return []
    lojas = {}
    # em lotes, para a URL nao ficar grande demais
    for ini in range(0, len(produtos), 40):
        lote = produtos[ini:ini + 40]
        ids = ",".join(p["id"] for p in lote)
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
            continue
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
    """Procura produtos COM estoque. Devolve (achados, palavras_usadas, soltou_do_fim).
    Tenta com todas as palavras; se nao achar, solta as do final (marca,
    tamanho, dosagem). Se nada, tenta sem a 1a palavra (palavra solta no
    inicio, ex.: 'vou querer ...'). So conta como PARCIAL quando soltou
    palavras do FINAL."""
    tokens = _corrigir(tokens)[:4]
    if not tokens:
        return [], [], False
    # Se o pedido tem 2+ palavras e a busca com todas nao acha nada, uma palavra rara
    # sozinha (ex.: 'espinha' em 'adesivo para espinha') pode achar o produto certo,
    # enquanto a palavra comum ('adesivo') traria itens sem relacao.
    if len(tokens) >= 2 and not _com_estoque(_buscar_produtos(tokens)):
        melhor = None
        for t in tokens:
            if re.fullmatch(r"\d+(mg|g|ml|mcg|ui)", t):
                continue
            achados_t = _com_estoque(_buscar_produtos([t]))
            if achados_t and len(achados_t) <= 6:
                if melhor is None or len(achados_t) < len(melhor[0]):
                    melhor = (achados_t, [t])
        if melhor:
            return melhor[0], melhor[1], True
    def so_dose(lista):
        # so dosagens (15mg, 500mg...) = nao e nome de produto
        return all(re.fullmatch(r"\d+(mg|g|ml|mcg|ui)", t) for t in lista)

    for ini in range(min(2, len(tokens))):
        resto = tokens[ini:]
        for k in range(len(resto), 0, -1):
            # nunca procurar so pela dose: traria remedios sem relacao com o pedido
            if so_dose(resto[:k]):
                continue
            achados = _com_estoque(_buscar_produtos(resto[:k]))
            if achados:
                return achados, resto[:k], k < len(resto)
    return [], [], False


def _segmentos(texto):
    """Divide a mensagem em pedaços, um por produto pedido
    (ex.: '3 dipirona e 2 atorvastatina. e 1 fralda personal')."""
    texto = re.sub(r"(\d),(\d)", r"\1.\2", texto or "")
    partes = re.split(r"[.;\n,]| e | mais | alem d[eo] | tambem ", " " + texto + " ", flags=re.I)
    saida = []
    for p in partes:
        tk = _tokens(p)
        if tk:
            saida.append(tk)
    return saida[:4]


def _nome_para_exibir(p):
    """Junta o nome (que o HOS corta em 25 letras, ex.: 'ATORVASTATINA CALCICA 40M')
    com a descricao (ex.: '40MG C/30CPR REV CIMED') sem repetir pedacos."""
    nome = (p.get("nome") or "").strip()
    desc = (p.get("descricao_completa") or "").strip()
    if not desc:
        return nome
    nl, dl = nome.lower(), desc.lower()
    if dl in nl:
        return nome
    if nl in dl:
        return desc
    palavras = nome.split()
    dw = dl.split()
    pn = {w for w in nl.split() if w.isalnum() or len(w) > 1}
    if pn and pn <= set(dw):
        return desc
    if palavras and dw:
        ultima = palavras[-1].lower()
        # ultimo pedaco do nome e so o comeco (cortado) da 1a palavra da descricao
        if len(ultima) >= 2:
            dwords = desc.split()
            for i, w in enumerate(dwords):
                if w.lower().startswith(ultima):
                    antes = dwords[:i]
                    marca = f"({' '.join(antes)})" if antes else ""
                    return " ".join(palavras[:-1] + ([marca] if marca else []) + dwords[i:]).strip()
    return nome


_MARCAS_CACHE = {"quando": 0.0, "dados": {}}


def _marcas():
    """marca (minuscula, sem acento) -> (principio_ativo, controlado). Cache de 10 min."""
    import time
    agora = time.time()
    if agora - _MARCAS_CACHE["quando"] < 600 and _MARCAS_CACHE["quando"]:
        return _MARCAS_CACHE["dados"]
    dados = {}
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/marcas_equivalentes",
            headers=_headers(),
            params={"select": "marca,principio_ativo,controlado", "limit": 2000},
            timeout=10,
        )
        if r.ok:
            for m in r.json():
                dados[_sem_acento(m["marca"]).strip()] = (
                    _sem_acento(m["principio_ativo"]).strip(), bool(m.get("controlado"))
                )
        else:
            print(f"[CATALOGO] marcas_equivalentes: {r.status_code} {r.text[:120]}")
    except Exception as e:
        print("[CATALOGO] erro marcas:", e)
    _MARCAS_CACHE["quando"] = agora
    _MARCAS_CACHE["dados"] = dados
    return dados


def _equivalentes_da_marca(tk):
    """Se o cliente pediu uma MARCA conhecida (ex.: vurtuoso), procura itens do mesmo
    principio ativo. Devolve (marca, principio, controlado, achados) ou None."""
    marcas = _marcas()
    if not marcas:
        return None
    for t in tk:
        if t in marcas:
            principio, controlado = marcas[t]
            doses = [x for x in tk if re.fullmatch(r"\d+(mg|g|ml|mcg|ui)", x)]
            achados = _com_estoque(_buscar_produtos([principio] + doses)) if doses else []
            if not achados:
                achados = _com_estoque(_buscar_produtos([principio]))
            return t, principio, controlado, achados
    return None


def _linhas(achados, limite):
    linhas = []
    for p in achados[:limite]:
        # preco_venda = menor preco praticado (promocao/desconto); cai para o preco de lista
        preco = float(p.get("preco_venda") or p.get("preco") or 0)
        nome_exibido = _nome_para_exibir(p)
        linhas.append(f"  - {nome_exibido} | R$ {preco:.2f} | lojas: {', '.join(p['lojas'])}")
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
    "(6) Itens marcados como ENCONTRADO ou PARCIAL neste catalogo existem: NAO diga que nao temos e NAO use "
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
    "(11) Se o cliente citou so o TIPO de produto (ex.: 'fralda', 'shampoo', 'protetor') e a lista tem "
    "varios itens diferentes (marcas, tamanhos, quantidades), NAO escolha por ele: mostre ate 5 opcoes "
    "(nome completo e preco) e pergunte qual prefere (marca/tamanho). So feche com o item que ele "
    "escolher. "
    "(12) Quando houver mais de um item parecido, sempre diga a MARCA de cada um (esta no final do nome, "
    "ex.: BIO, MEDLEY, CIMED) e nunca diga que 'tanto faz'. "
    "(13) FINALIDADE: se o cliente disse para que quer o produto (ex.: 'adesivo para espinha', 'pomada para "
    "assadura', 'remedio para tosse') e o NOME dos itens listados nao mostra claramente que servem para essa "
    "finalidade, NAO ofereca esses itens: eles so combinaram numa palavra solta (ex.: 'adesivo'). Trate como "
    "NAO ENCONTRADO e siga a regra de encomenda. Nunca explique para que serve um produto alem do que esta "
    "escrito no proprio nome; se o cliente perguntar para que serve e o nome nao diz, encaminhe ao farmaceutico. "
    "(14) COPIE o nome de cada produto EXATAMENTE como esta na linha do catalogo, do comeco ao fim, incluindo "
    "o LABORATORIO/MARCA que fica no final (ex.: '... C/30CPR REV CIMED'). Nao encurte, nao corte palavras, "
    "nao troque acentos nem reescreva o nome. "
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
        # palavras de FINALIDADE citadas pelo cliente ("adesivo PARA espinha", "pomada PRA assadura")
        sem = _sem_acento(texto_atual)
        finalidades = set()
        for m in re.finditer(r"\b(?:para|pra|contra)\s+(?:a |o |as |os |uma |um )?([a-z]{4,})", sem):
            finalidades.update(_tokens(m.group(1)))
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=len(segmentos)) as ex:
            resultados = list(ex.map(_procurar, segmentos))
        limite = MAX_PRODUTOS if len(segmentos) == 1 else 12
        partes = []
        for tk, (achados, usados, soltou) in zip(segmentos, resultados):
            tk = _corrigir(tk)[:4]
            pedido = " ".join(tk)
            marca_info = None
            if not achados or (soltou and tk and tk[0] not in usados):
                marca_info = _equivalentes_da_marca(tk)
            if marca_info:
                marca, principio, controlado, equivalentes = marca_info
                if equivalentes:
                    acao = (
                        "e um medicamento CONTROLADO: NAO feche a venda nem troque por conta propria; "
                        "se o cliente quiser, responda TRANSFERIR_FARMACEUTICO para o farmaceutico confirmar"
                        if controlado else
                        "pergunte se o cliente quer uma destas opcoes"
                    )
                    partes.append(
                        f"MARCA NAO DISPONIVEL - cliente pediu a marca \"{marca}\" (principio ativo: {principio}). "
                        f"Essa MARCA nao esta no estoque. Abaixo ha itens com o MESMO principio ativo, de outra "
                        f"marca e/ou dose (NAO sao a marca pedida; confira a dose que ele pediu): diga claramente "
                        f"que a marca pedida nao tem, cite estes itens como possibilidade e {acao}:\n"
                        + "\n".join(_linhas(equivalentes, limite))
                    )
                else:
                    partes.append(f"NAO ENCONTRADO NO ESTOQUE - cliente pediu: \"{pedido}\"")
            elif not achados:
                partes.append(f"NAO ENCONTRADO NO ESTOQUE - cliente pediu: \"{pedido}\"")
            elif soltou and any(t in finalidades for t in tk if t not in usados):
                # o que faltou e a FINALIDADE pedida: os itens achados so combinam numa palavra
                # solta e nao servem ao cliente -> tratar como nao encontrado (encomenda)
                partes.append(
                    f"NAO ENCONTRADO NO ESTOQUE - cliente pediu: \"{pedido}\" (nao ha produto "
                    f"especifico para essa finalidade; NAO ofereca itens parecidos)"
                )
            elif soltou:
                faltou = " ".join(t for t in tk if t not in usados)
                partes.append(
                    f"PARCIAL - cliente pediu: \"{pedido}\". NAO existe no estoque com \"{faltou}\"; "
                    f"abaixo ha so itens de \"{' '.join(usados)}\" (NAO sao o que o cliente pediu: "
                    f"avise que \"{faltou}\" nao esta disponivel e pergunte se quer uma destas opcoes):\n"
                    + "\n".join(_linhas(achados, limite))
                )
            else:
                partes.append(
                    f"ENCONTRADO - cliente pediu: \"{pedido}\" -> {len(achados)} item(ns) com estoque:\n"
                    + "\n".join(_linhas(achados, limite))
                )
        print(f"[CATALOGO] segmentos={len(segmentos)} encontrados={sum(1 for r in resultados if r[0])}")
        return (
            "\n\nCATALOGO REAL DA FARMACIA (consultado agora no estoque; use ISTO para esta mensagem "
            "do cliente, tem prioridade sobre a tabela fixa de precos):\n"
            + "\n".join(partes) + "\n" + REGRAS
        )
    except Exception as e:
        print("[CATALOGO] erro:", e)
        return ""
