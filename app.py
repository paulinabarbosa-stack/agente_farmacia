from flask import Flask, request
import requests
import os
import re
import json
import threading
import time
from datetime import datetime
import pytz

app = Flask(__name__)

KEY = os.environ.get("OPENAI_API_KEY")
BASE = os.environ.get("UAZAPI_URL")
TOKEN = os.environ.get("UAZAPI_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

SYSTEM_PROMPT = """Voce e Isabela, atendente virtual da Farmacia Saude e Vida, localizada em Diamantina-MG. Horario de funcionamento: 7h00 as 22h00, todos os dias.
Seja sempre simpatica, acolhedora e prestativa. Represente a farmacia com cuidado e profissionalismo.

TABELA DE PRECOS (valores estimados):
ANALGESICOS E ANTITERMICOS:
- Dipirona 500mg (20 comp) - R$ 8,90
- Paracetamol 750mg (20 comp) - R$ 9,90
- Ibuprofeno 600mg (20 comp) - R$ 18,90
- Aspirina 500mg (20 comp) - R$ 12,90

ANTIGRIPAIS:
- Resfenol (16 caps) - R$ 22,90
- Coristina D (16 comp) - R$ 19,90
- Benegrip (20 comp) - R$ 17,90
- Neosoro Spray Nasal - R$ 14,90

ANTIINFLAMATORIOS:
- Nimesulida 100mg (20 comp) - R$ 16,90
- Diclofenaco 50mg (20 comp) - R$ 14,90
- Dorflex (30 comp) - R$ 24,90
- Cataflan 50mg (20 comp) - R$ 28,90

ANTIBIOTICOS (exigem receita medica):
- Amoxicilina 500mg (21 caps) - R$ 18,90
- Azitromicina 500mg (3 comp) - R$ 22,90
- Cefalexina 500mg (20 caps) - R$ 19,90
- Amoxicilina + Clavulanato 875mg (14 comp) - R$ 49,90

ANTICONCEPCIONAIS (exigem receita medica):
- Yasmin (21 comp) - R$ 39,90
- Diane 35 (21 comp) - R$ 34,90
- Microvlar (21 comp) - R$ 19,90
- Mercilon (21 comp) - R$ 44,90
- Ciclo 21 (21 comp) - R$ 16,90

PRESSAO ARTERIAL (exigem receita medica):
- Losartana 50mg (30 comp) - R$ 14,90
- Enalapril 10mg (30 comp) - R$ 12,90
- Anlodipino 5mg (30 comp) - R$ 13,90
- Hidroclorotiazida 25mg (30 comp) - R$ 9,90

ANSIEDADE E SONO (exigem receita medica):
- Clonazepam 2mg (30 comp) - R$ 19,90
- Alprazolam 0,5mg (30 comp) - R$ 18,90
- Escitalopram 10mg (30 comp) - R$ 29,90
- Sertralina 50mg (30 comp) - R$ 24,90

TDAH (exigem receita especial):
- Ritalina 10mg (30 comp) - R$ 89,90
- Ritalina LA 20mg (30 caps) - R$ 129,90
- Venvanse 30mg (28 caps) - R$ 189,90
- Concerta 36mg (30 comp) - R$ 219,90

VITAMINAS E SUPLEMENTOS:
- Vitamina C 1g (30 comp) - R$ 19,90
- Vitamina D 2000UI (30 caps) - R$ 24,90
- Complexo B (30 comp) - R$ 16,90
- Zinco + Vitamina C (30 comp) - R$ 22,90
- Centrum (30 comp) - R$ 49,90

HIGIENE E BELEZA:
- Protetor Solar FPS 50 (120ml) - R$ 39,90
- Shampoo Anticaspa (400ml) - R$ 29,90
- Creme Hidratante Corporal (400ml) - R$ 34,90
- Fio Dental (50m) - R$ 7,90
- Escova Dental - R$ 12,90

SUAS FUNCOES:
1. Recepcionar clientes com simpatia
2. Informar sobre disponibilidade e precos dos medicamentos usando a tabela acima
3. Para medicamentos que exigem receita, SEMPRE avisar o cliente que e necessario apresentar receita medica
4. Ao confirmar um pedido, coletar OBRIGATORIAMENTE nesta ordem: nome completo, endereco completo, CPF e forma de pagamento
5. Agendar entregas em domicilio
6. Agendar consultas com farmaceutico coletando: nome, telefone e melhor horario

REGRA IMPORTANTE SOBRE RECEITA MEDICA:
Mencione a necessidade de receita medica APENAS para os medicamentos marcados na tabela como "(exigem receita medica)" (antibioticos, anticoncepcionais, medicamentos para pressao arterial, ansiedade e sono, e TDAH).
Para os demais medicamentos (analgesicos e antitermicos como Dipirona, Paracetamol, Ibuprofeno e Aspirina; antigripais; antiinflamatorios; vitaminas e suplementos; produtos de higiene e beleza), NAO mencione necessidade de receita medica em nenhuma hipotese, pois sao vendidos livremente, sem prescricao.

REGRA CRITICA DE TRANSFERENCIA PARA O FARMACEUTICO:
Se o cliente pedir INDICACAO, SUGESTAO ou ORIENTACAO sobre qual medicamento tomar para um sintoma, dor ou problema de saude (exemplos: "o que eu tomo pra dor de cabeca", "me indica um remedio pra gripe", "qual o melhor remedio para dor nas costas", "estou com febre, o que eu tomo"), voce NAO deve sugerir nenhum medicamento.
Nesse caso, responda EXATAMENTE e SOMENTE com o texto: TRANSFERIR_FARMACEUTICO
Nao escreva mais nada alem dessas palavras quando isso acontecer.

Isso e DIFERENTE de quando o cliente ja sabe o nome do medicamento e so quer saber preco ou disponibilidade (exemplo: "voces tem dipirona?", "quanto custa o paracetamol?") - nesses casos, responda normalmente com a tabela de precos.

REGRA CRITICA DE CONSULTA DE ENTREGA:
Se o cliente perguntar sobre o andamento/status da entrega dele (exemplos: "meu pedido ja saiu para entrega?", "cade minha entrega", "meu pedido ja foi entregue?", "quando chega meu pedido"), voce NAO deve inventar nenhuma informacao sobre o status.
Nesse caso, responda EXATAMENTE e SOMENTE com o texto: CONSULTAR_ENTREGA
Nao escreva mais nada alem dessas palavras quando isso acontecer. O sistema vai consultar o status real e responder ao cliente automaticamente.

QUANDO VOCE RECEBER DE VOLTA UMA CONVERSA QUE JA FOI ORIENTADA PELO FARMACEUTICO:
Se a mensagem do sistema informar o que o farmaceutico orientou, continue o atendimento a partir dali, seguindo o FLUXO DE PEDIDO OBRIGATORIO abaixo, considerando o produto que foi recomendado. Nao pergunte de novo qual e o sintoma nem sugira outro produto - use exatamente o que o farmaceutico indicou.

FLUXO DE PEDIDO OBRIGATORIO:
Quando o cliente quiser comprar, siga SEMPRE esta ordem:
1. Confirme o produto e o preco
2. Se o medicamento for um dos que EXIGEM RECEITA (ver REGRA IMPORTANTE SOBRE RECEITA MEDICA acima): avise que e necessario apresentar receita medica valida. Caso contrario, NAO mencione receita.
3. Peca TODAS as informacoes de uma vez so, numa unica mensagem:
"Para finalizar seu pedido, preciso de algumas informacoes:
- Nome completo:
- Endereco completo (rua, numero, bairro):
- CPF:
- Forma de pagamento (Pix, cartao de credito, cartao de debito ou dinheiro):"
4. Aguarde o cliente responder com todos os dados
5. Confirme o resumo do pedido com todos os dados e valor total
6. Finalize com a mensagem de encerramento abaixo

MENSAGEM DE ENCERRAMENTO OBRIGATORIA:
Sempre que o atendimento for encerrado (pedido finalizado, duvida resolvida ou cliente se despedir), envie EXATAMENTE:
"Seu pedido foi registrado e a entrega ja esta sendo providenciada! Foi um prazer te atender! 😊

Que tal deixar uma avaliacao para nos ajudar a melhorar?
⭐ Farmacia Saude e Vida: https://search.google.com/local/writereview?placeid=ChIJAQBsTgC5rgARK0oiw3CQOpg

Obrigada pela preferencia! Volte sempre. 💙"

REGRAS OBRIGATORIAS:
- Apresente-se APENAS na primeira mensagem
- Nas demais mensagens NAO se reapresente
- Use os precos da tabela acima ao ser perguntada
- NUNCA oriente sobre dosagem ou substituicao de medicamentos - indique o farmaceutico
- Siga rigorosamente a REGRA IMPORTANTE SOBRE RECEITA MEDICA definida acima
- Seja breve e simpatica - maximo 3 paragrafos
- Use linguagem informal e acolhedora"""

historico = {}
mensagens_processadas = set()
transferido = {}
mensagens_farmaceutico = {}

# Numero de teste usado como "farmaceutico" enquanto o numero oficial
# da farmacia ainda nao esta conectado. Remover/ajustar quando a farmacia
# tiver seu proprio numero conectado (nesse caso o farmaceutico so precisa
# responder direto na conversa do cliente pelo WhatsApp oficial).
FARMACEUTICO_TESTE = "5538998552537"
ultimo_cliente_transferido = None


def numero_e_farmaceutico_teste(number):
    apenas_digitos = "".join(c for c in (number or "") if c.isdigit())
    alvo = "".join(c for c in FARMACEUTICO_TESTE if c.isdigit())
    if not apenas_digitos or not alvo:
        return False
    return apenas_digitos.endswith(alvo[-8:])


def extrair_resumo_apos_comando(texto):
    """Se o farmaceutico escrever, por exemplo,
    '/voltarbot Recomendei Dipirona 500mg', retorna 'Recomendei Dipirona 500mg'."""
    idx = texto.lower().find("/voltarbot")
    if idx == -1:
        return ""
    return texto[idx + len("/voltarbot"):].strip()


def get_saudacao():
    tz = pytz.timezone("America/Sao_Paulo")
    hora = datetime.now(tz).hour
    if 5 <= hora < 12:
        return "Bom dia"
    elif 12 <= hora < 18:
        return "Boa tarde"
    else:
        return "Boa noite"


def baixar_audio(url):
    headers_list = [
        {"token": TOKEN},
        {},
    ]
    for h in headers_list:
        try:
            r = requests.get(url, headers=h, timeout=20)
            print(f"DOWNLOAD {url[:60]} STATUS:{r.status_code} CT:{r.headers.get('content-type','')}")
            if r.status_code == 200 and len(r.content) > 500:
                return r.content
        except Exception as e:
            print("ERRO download:", e)
    return None


def transcrever_audio(audio_bytes):
    h = {"Authorization": "Bearer " + KEY}
    data = {"model": "whisper-1", "language": "pt"}
    formatos = [
        ("audio.mp3", "audio/mpeg"),
        ("audio.ogg", "audio/ogg"),
        ("audio.wav", "audio/wav"),
        ("audio.m4a", "audio/mp4"),
    ]
    for filename, mimetype in formatos:
        try:
            files = {"file": (filename, audio_bytes, mimetype)}
            r = requests.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers=h, files=files, data=data, timeout=30
            )
            print(f"WHISPER {filename} STATUS:{r.status_code}")
            if r.status_code == 200:
                transcricao = r.json().get("text", "").strip()
                print("TRANSCRICAO:", transcricao)
                return transcricao
        except Exception as e:
            print(f"ERRO Whisper {filename}:", e)
    return None


def extrair_texto(msg):
    texto_direto = msg.get("text")
    if isinstance(texto_direto, str) and texto_direto.strip():
        return texto_direto

    content = msg.get("content")
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, dict):
        texto_no_content = content.get("text")
        if isinstance(texto_no_content, str) and texto_no_content.strip():
            return texto_no_content

    return None


def limpar_numero(valor):
    if not isinstance(valor, str):
        return ""
    return valor.replace("@s.whatsapp.net", "").replace("@lid", "")


encerrado = {}

PALAVRAS_DESPEDIDA = [
    "obrigad", "valeu", "vlw", "tchau", "ate mais", "ate logo", "de nada",
    "por nada", "certeza", "beleza", "blz", "flw", "otimo", "otima",
    "perfeito", "perfeita", "show", "top",
]


def normalizar_texto(texto):
    t = texto.lower()
    t = re.sub(r"[^\w\s]", "", t)
    return t.strip()


def e_mensagem_de_despedida(texto):
    """Reconhece agradecimentos/despedidas curtas para nao ficar respondendo
    a toa depois que o atendimento ja foi encerrado."""
    norm = normalizar_texto(texto)
    if not norm or len(norm) > 25:
        return False
    for p in PALAVRAS_DESPEDIDA:
        if p in norm:
            return True
    return False


# ---- FOLLOW-UP AUTOMATICO (Bloco 1) ----

ultima_mensagem_cliente = {}   # number -> datetime da ultima mensagem do cliente
estagios_enviados = {}         # number -> set de estagios ja enviados ("5min", "30min", "1h")
seguimento_pendente_id = {}    # number -> id do seguimento aguardando resposta do cliente

ESTAGIOS_FOLLOWUP = [
    ("5min", 5, "Oi! Ainda esta por ai? Fico a disposicao se quiser continuar seu pedido 😊"),
    ("30min", 30, "Notei que voce ficou um tempinho sem responder. Posso te ajudar com mais alguma coisa?"),
    ("1h", 60, "So passando pra saber se ainda tem interesse no que conversamos. Se precisar, e so chamar!"),
]


def registrar_seguimento(number, estagio, mensagem):
    """Salva no Supabase que um follow-up foi enviado. Retorna o id criado, ou None se falhar."""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return None
    try:
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        body = {
            "cliente_telefone": number,
            "estagio": estagio,
            "mensagem_enviada": mensagem,
        }
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/seguimentos_ia",
            json=body, headers=headers, timeout=15
        )
        if r.status_code in (200, 201):
            dados = r.json()
            if dados:
                return dados[0].get("id")
    except Exception as e:
        print("ERRO ao registrar seguimento:", e)
    return None


def marcar_seguimento_respondido(number):
    """Quando o cliente volta a responder, marca o ultimo seguimento pendente como respondido."""
    seguimento_id = seguimento_pendente_id.get(number)
    if not seguimento_id or not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return
    try:
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
            "Content-Type": "application/json",
        }
        body = {
            "cliente_respondeu": True,
            "respondeu_em": datetime.now(pytz.timezone("America/Sao_Paulo")).isoformat(),
        }
        requests.patch(
            f"{SUPABASE_URL}/rest/v1/seguimentos_ia?id=eq.{seguimento_id}",
            json=body, headers=headers, timeout=15
        )
    except Exception as e:
        print("ERRO ao marcar seguimento respondido:", e)
    seguimento_pendente_id.pop(number, None)


def registrar_conversa(number, mensagem, resposta, transferida=False, motivo=None):
    """Grava no Supabase cada troca real entre o cliente e a Isabela."""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return
    try:
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
            "Content-Type": "application/json",
        }
        body = {
            "cliente_telefone": number,
            "mensagem": mensagem,
            "resposta": resposta,
            "transferida_humano": transferida,
        }
        if motivo:
            body["motivo_transferencia"] = motivo
        requests.post(f"{SUPABASE_URL}/rest/v1/conversas", json=body, headers=headers, timeout=15)
    except Exception as e:
        print("ERRO ao registrar conversa:", e)


def extrair_dados_venda(number):
    """Pede pra IA extrair produto/quantidade/valor/nome/endereco/forma de
    pagamento da conversa que acabou de fechar."""
    if number not in historico:
        return None

    instrucao = (
        "Baseado na conversa abaixo, extraia os dados do pedido que acabou de ser fechado. "
        "Responda APENAS em JSON puro, sem nenhum texto adicional, exatamente neste formato: "
        '{"produto": "nome do produto", "quantidade": 1, "valor_unitario": 0.00, '
        '"nome_cliente": "nome completo informado", "endereco": "endereco completo informado", '
        '"forma_pagamento": "Pix, cartao de credito, cartao de debito ou dinheiro"}. '
        'Se nao conseguir identificar o produto com certeza, responda {"produto": null}. '
        'Para os demais campos, se nao encontrar a informacao na conversa, use null.'
    )
    messages = [{"role": "system", "content": instrucao}] + historico[number][-14:]

    h = {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}
    b = {"model": "gpt-4o-mini", "messages": messages}

    try:
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            json=b, headers=h, timeout=30
        )
        r.raise_for_status()
        resultado = r.json()
        conteudo = resultado["choices"][0]["message"]["content"].strip()
        conteudo = re.sub(r"^```json|^```|```$", "", conteudo, flags=re.MULTILINE).strip()
        dados = json.loads(conteudo)
        if not dados.get("produto"):
            return None
        return dados
    except Exception as e:
        print("ERRO ao extrair dados da venda:", e)
        return None


def buscar_produto_por_nome(nome_produto):
    """Tenta encontrar o produto correspondente na tabela produtos, usando
    busca aproximada pela primeira palavra do nome (ja que o nome dito pelo
    cliente/IA pode nao bater 100% com o nome cadastrado no banco, ex:
    'Dipirona' vs 'Dipirona Sodica 500mg 20cp'). Retorna o id do produto,
    ou None se nao encontrar nada."""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY or not nome_produto:
        return None
    try:
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        }
        primeira_palavra = nome_produto.strip().split(" ")[0]
        if not primeira_palavra:
            return None
        params = f"nome=ilike.*{primeira_palavra}*&select=id,nome&limit=5"
        r = requests.get(f"{SUPABASE_URL}/rest/v1/produtos?{params}", headers=headers, timeout=15)
        dados = r.json()
        if not dados:
            print(f"AVISO: nenhum produto encontrado no banco para '{nome_produto}'")
            return None
        return dados[0]["id"]
    except Exception as e:
        print("ERRO ao buscar produto por nome:", e)
        return None


def escolher_loja_para_produto(produto_id):
    """Consulta a tabela estoque_lojas e escolhe, entre as lojas que tem
    estoque disponivel (quantidade > 0) para o produto, a de maior
    prioridade (menor numero em ordem_prioridade). Retorna o unidade_id
    escolhido, ou None se nenhuma loja tiver estoque."""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY or not produto_id:
        return None
    try:
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        }
        params = (
            f"produto_id=eq.{produto_id}&quantidade=gt.0"
            f"&select=unidade_id,quantidade,unidades(nome,ordem_prioridade)"
        )
        r = requests.get(f"{SUPABASE_URL}/rest/v1/estoque_lojas?{params}", headers=headers, timeout=15)
        dados = r.json()
        if not dados:
            print(f"AVISO: nenhuma loja com estoque disponivel para produto_id={produto_id}")
            return None

        def chave_prioridade(item):
            unidade = item.get("unidades") or {}
            valor = unidade.get("ordem_prioridade")
            return valor if valor is not None else 999

        dados.sort(key=chave_prioridade)
        escolhido = dados[0]
        nome_loja = (escolhido.get("unidades") or {}).get("nome", "desconhecida")
        print(f"LOJA ESCOLHIDA para produto_id={produto_id}: {nome_loja}")
        return escolhido["unidade_id"]
    except Exception as e:
        print("ERRO ao escolher loja para produto:", e)
        return None


def registrar_venda(number, produto, quantidade, valor_unitario, unidade_id=None):
    """Grava no Supabase a venda fechada pela Isabela. Quando a loja de
    origem e identificada (produto encontrado no banco + estoque
    disponivel em alguma loja), grava tambem o unidade_id correspondente."""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return
    try:
        quantidade_num = float(quantidade or 1)
        valor_unitario = float(valor_unitario or 0)
        valor_total = round(quantidade_num * valor_unitario, 2)

        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
            "Content-Type": "application/json",
        }
        body = {
            "produto_nome_texto": produto,
            "quantidade": int(round(quantidade_num)),
            "valor_unitario": valor_unitario,
            "valor_total": valor_total,
            "origem": "whatsapp",
            "cliente_telefone": number,
        }
        if unidade_id:
            body["unidade_id"] = unidade_id

        r = requests.post(f"{SUPABASE_URL}/rest/v1/vendas", json=body, headers=headers, timeout=15)
        print("VENDA REGISTRADA:", r.status_code, r.text)
    except Exception as e:
        print("ERRO ao registrar venda:", e)


def criar_pedido(number, dados_venda, unidade_id=None):
    """Cria o registro do pedido de entrega no Supabase, ja vinculado a
    loja escolhida, logo apos a venda ser fechada pela Isabela. O campo
    itens segue o formato ja usado no sistema: [{"qtd": N, "produto": "X"}]."""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return
    try:
        quantidade_num = int(round(float(dados_venda.get("quantidade") or 1)))
        valor_unitario = float(dados_venda.get("valor_unitario") or 0)
        valor_total = round(quantidade_num * valor_unitario, 2)
        produto_nome = dados_venda.get("produto")

        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
            "Content-Type": "application/json",
        }
        body = {
            "cliente_telefone": number,
            "itens": [{"qtd": quantidade_num, "produto": produto_nome}],
            "valor_total": valor_total,
            "forma_pagamento": dados_venda.get("forma_pagamento"),
            "status": "pendente",
            "nome_cliente": dados_venda.get("nome_cliente"),
            "endereco": dados_venda.get("endereco"),
        }
        if unidade_id:
            body["unidade_id"] = unidade_id

        r = requests.post(f"{SUPABASE_URL}/rest/v1/pedidos", json=body, headers=headers, timeout=15)
        print("PEDIDO CRIADO:", r.status_code, r.text)
    except Exception as e:
        print("ERRO ao criar pedido:", e)


def formatar_hora_br(iso_str):
    """Converte um timestamp ISO do Supabase para horario de Brasilia (HH:MM)."""
    try:
        texto = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(texto)
        dt_sp = dt.astimezone(pytz.timezone("America/Sao_Paulo"))
        return dt_sp.strftime("%H:%M")
    except Exception:
        return ""


MAPA_STATUS_ENTREGA = {
    "pendente": "seu pedido esta pendente, ainda vai ser preparado",
    "em_preparo": "seu pedido esta sendo preparado",
    "em_entrega": "seu pedido ja saiu para entrega! Deve chegar em breve",
    "entregue": "seu pedido ja foi entregue",
    "nao_encontrado": "nosso motoboy tentou entregar mas nao conseguiu te encontrar no endereco informado",
    "devolvido": "o pedido foi devolvido",
    "cancelado": "o pedido foi cancelado",
}


def consultar_status_entrega(number):
    """Busca no Supabase o pedido mais recente do cliente e monta uma
    resposta com o status real (a IA nunca inventa esse dado)."""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return "No momento nao consigo consultar o status da sua entrega. Tente novamente em instantes."
    try:
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        }
        params = f"cliente_telefone=eq.{number}&order=criado_em.desc&limit=1"
        r = requests.get(f"{SUPABASE_URL}/rest/v1/pedidos?{params}", headers=headers, timeout=15)
        dados = r.json()

        if not dados:
            return "Nao encontrei nenhum pedido recente no seu numero. Posso te ajudar com um novo pedido?"

        pedido = dados[0]
        status = pedido.get("status")
        entregue_em = pedido.get("entregue_em")
        texto_status = MAPA_STATUS_ENTREGA.get(status, "nao consegui identificar o status do seu pedido no momento")

        if status == "entregue" and entregue_em:
            hora = formatar_hora_br(entregue_em)
            if hora:
                return f"Oi! {texto_status}, as {hora}. Precisa de mais alguma coisa? 😊"

        return f"Oi! {texto_status}. Qualquer novidade, te aviso por aqui! 😊"

    except Exception as e:
        print("ERRO ao consultar status de entrega:", e)
        return "Tive um probleminha para consultar o status agora. Pode tentar de novo em instantes?"


def verificar_seguimentos():
    """Roda em segundo plano, verificando periodicamente quais clientes
    pararam de responder e enviando o follow-up no estagio certo."""
    while True:
        try:
            agora = datetime.now(pytz.timezone("America/Sao_Paulo"))
            for number in list(ultima_mensagem_cliente.keys()):
                if transferido.get(number):
                    continue
                if encerrado.get(number):
                    continue

                ultima = ultima_mensagem_cliente.get(number)
                if not ultima:
                    continue

                decorridos_min = (agora - ultima).total_seconds() / 60
                enviados = estagios_enviados.setdefault(number, set())

                for nome_estagio, minutos, mensagem in ESTAGIOS_FOLLOWUP:
                    if decorridos_min >= minutos and nome_estagio not in enviados:
                        send(number, mensagem)
                        seguimento_id = registrar_seguimento(number, nome_estagio, mensagem)
                        if seguimento_id:
                            seguimento_pendente_id[number] = seguimento_id
                        enviados.add(nome_estagio)
                        print(f"[FOLLOWUP] Estagio {nome_estagio} enviado para {number}")
        except Exception as e:
            print("ERRO no verificador de seguimentos:", e)

        time.sleep(30)


@app.route("/webhook", methods=["POST"])
def webhook():
    global ultimo_cliente_transferido
    data = request.json
    print("PAYLOAD COMPLETO:", data)
    try:
        msg = data.get("message", {})
        chat = data.get("chat", {})

        is_from_me = msg.get("wasSentByApi") or msg.get("fromMe")

        if is_from_me:
            number = limpar_numero(msg.get("chatid"))
            if not number:
                number = limpar_numero(chat.get("wa_chatid"))

            texto_fromme = extrair_texto(msg) or ""

            if "/voltarbot" in texto_fromme.lower():
                if number:
                    resumo_lista = mensagens_farmaceutico.get(number, [])
                    resumo_inline = extrair_resumo_apos_comando(texto_fromme)
                    partes_resumo = []
                    if resumo_lista:
                        partes_resumo.append(" ".join(resumo_lista))
                    if resumo_inline:
                        partes_resumo.append(resumo_inline)
                    resumo_texto = " ".join(partes_resumo).strip()
                    if resumo_texto:
                        if number not in historico:
                            historico[number] = []
                        historico[number].append({
                            "role": "system",
                            "content": (
                                f"O farmaceutico orientou o cliente da seguinte forma: \"{resumo_texto}\". "
                                "Continue o atendimento a partir daqui, seguindo o FLUXO DE PEDIDO OBRIGATORIO "
                                "considerando esse produto recomendado, sem perguntar novamente qual e o sintoma."
                            )
                        })
                    mensagens_farmaceutico[number] = []
                    transferido[number] = False
                    print(f"CONVERSA DEVOLVIDA PARA ISABELA: {number} | RESUMO: {resumo_texto}")
                    if resumo_texto:
                        oferecer_produto_proativamente(number)
            else:
                if number and transferido.get(number) and texto_fromme.strip():
                    mensagens_farmaceutico.setdefault(number, []).append(texto_fromme.strip())
                    print(f"MENSAGEM DO FARMACEUTICO GUARDADA: {number} -> {texto_fromme.strip()}")

            return "ok", 200

        number = limpar_numero(msg.get("sender_pn"))
        if not number:
            number = limpar_numero(chat.get("wa_chatid"))
        if not number:
            number = limpar_numero(msg.get("chatid"))

        # Se a mensagem veio do numero de teste do farmaceutico, trata como
        # orientacao do farmaceutico para o ultimo cliente transferido.
        # Nesse fluxo, o farmaceutico conversa DIRETAMENTE com o cliente pelo
        # proprio celular (fora do sistema) e so manda mensagem para este
        # numero quando quiser devolver o atendimento, com o resumo do que
        # foi recomendado escrito junto com o comando /voltarbot.
        if numero_e_farmaceutico_teste(number):
            texto_farmaceutico = extrair_texto(msg) or ""
            alvo = ultimo_cliente_transferido

            if "/voltarbot" in texto_farmaceutico.lower():
                if alvo:
                    resumo_lista = mensagens_farmaceutico.get(alvo, [])
                    resumo_inline = extrair_resumo_apos_comando(texto_farmaceutico)
                    partes_resumo = []
                    if resumo_lista:
                        partes_resumo.append(" ".join(resumo_lista))
                    if resumo_inline:
                        partes_resumo.append(resumo_inline)
                    resumo_texto = " ".join(partes_resumo).strip()
                    if resumo_texto:
                        if alvo not in historico:
                            historico[alvo] = []
                        historico[alvo].append({
                            "role": "system",
                            "content": (
                                f"O farmaceutico orientou o cliente da seguinte forma: \"{resumo_texto}\". "
                                "Continue o atendimento a partir daqui, seguindo o FLUXO DE PEDIDO OBRIGATORIO "
                                "considerando esse produto recomendado, sem perguntar novamente qual e o sintoma."
                            )
                        })
                    mensagens_farmaceutico[alvo] = []
                    transferido[alvo] = False
                    print(f"[TESTE] CONVERSA DEVOLVIDA PARA ISABELA: {alvo} | RESUMO: {resumo_texto}")
                    if resumo_texto:
                        oferecer_produto_proativamente(alvo)
            else:
                if alvo and transferido.get(alvo) and texto_farmaceutico.strip():
                    mensagens_farmaceutico.setdefault(alvo, []).append(texto_farmaceutico.strip())
                    print(f"[TESTE] MENSAGEM DO FARMACEUTICO GUARDADA PARA {alvo}: {texto_farmaceutico.strip()}")

            return "ok", 200

        message_id = msg.get("id", "")
        if message_id in mensagens_processadas:
            return "ok", 200
        if message_id:
            mensagens_processadas.add(message_id)
            if len(mensagens_processadas) > 10000:
                mensagens_processadas.clear()

        if number and transferido.get(number):
            return "ok", 200

        msg_type = msg.get("type", "")
        media_type = msg.get("mediaType", "")
        mimetype = str(msg.get("mimetype", ""))
        is_ptt = msg.get("PTT", False) or msg.get("ptt", False)

        is_audio = (
            msg_type in ("audio", "ptt") or
            media_type == "ptt" or
            is_ptt or
            mimetype.startswith("audio")
        )

        print(f"TYPE:{msg_type} MEDIA:{media_type} PTT:{is_ptt} IS_AUDIO:{is_audio}")

        text = None

        if is_audio:
            content = msg.get("content")
            audio_url = None
            if isinstance(content, dict):
                audio_url = content.get("URL") or content.get("url")
            elif isinstance(content, str) and content.startswith("http"):
                audio_url = content

            if not audio_url:
                direct_path = msg.get("directPath", "")
                if direct_path:
                    audio_url = BASE + "/proxy/media?path=" + direct_path

            print("AUDIO URL:", audio_url)

            if audio_url:
                audio_bytes = baixar_audio(audio_url)
                if audio_bytes:
                    text = transcrever_audio(audio_bytes)
                    if not text:
                        send(number, "Desculpe, nao consegui entender o audio. Pode digitar sua mensagem?")
                        return "ok", 200
                else:
                    send(number, "Desculpe, nao consegui processar o audio. Pode digitar sua mensagem?")
                    return "ok", 200
            else:
                send(number, "Desculpe, nao consegui acessar o audio. Pode digitar sua mensagem?")
                return "ok", 200
        else:
            text = extrair_texto(msg) or chat.get("wa_lastMessageTextVote")

        if not number or not text:
            return "ok", 200

        if not isinstance(text, str):
            return "ok", 200

        text = text.strip()
        if not text:
            return "ok", 200

        if number and encerrado.get(number):
            if e_mensagem_de_despedida(text):
                print(f"[SILENCIO] Despedida ignorada apos encerramento para {number}: {text}")
                return "ok", 200
            else:
                encerrado[number] = False

        # Cliente esta ativo: reinicia o contador do follow-up e marca
        # como respondido qualquer seguimento que estivesse pendente
        if number:
            marcar_seguimento_respondido(number)
            ultima_mensagem_cliente[number] = datetime.now(pytz.timezone("America/Sao_Paulo"))
            estagios_enviados[number] = set()

        reply = ask_openai(number, text)
        if reply:
            if "TRANSFERIR_FARMACEUTICO" in reply:
                transferido[number] = True
                mensagens_farmaceutico[number] = []
                ultimo_cliente_transferido = number
                print(f"CONVERSA TRANSFERIDA PARA FARMACEUTICO: {number}")
                mensagem_transferencia = "Vou te conectar com nosso farmaceutico para te orientar melhor sobre isso, so um momento! 😊"
                send(number, mensagem_transferencia)
                registrar_conversa(
                    number, text, mensagem_transferencia,
                    transferida=True,
                    motivo="Cliente pediu indicacao/sugestao de medicamento",
                )

                resumo_para_farmaceutico = (
                    f"📋 Novo atendimento transferido!\n"
                    f"Cliente: {number}\n"
                    f"Abrir conversa direto com o cliente: https://wa.me/{number}\n"
                    f"Pergunta do cliente: \"{text}\"\n\n"
                    f"Fale diretamente com o cliente pelo link acima. Quando terminar, "
                    f"envie aqui /voltarbot seguido do resumo da orientacao "
                    f"(ex: /voltarbot Recomendei Dipirona 500mg, 1 comprimido a cada 6 horas)."
                )
                send(FARMACEUTICO_TESTE, resumo_para_farmaceutico)
            elif "CONSULTAR_ENTREGA" in reply:
                mensagem_status = consultar_status_entrega(number)
                send(number, mensagem_status)
                registrar_conversa(number, text, mensagem_status)
            else:
                send(number, reply)
                registrar_conversa(number, text, reply)
                if "Foi um prazer te atender" in reply:
                    encerrado[number] = True
                    print(f"CONVERSA ENCERRADA (aguardando so despedidas): {number}")
                    dados_venda = extrair_dados_venda(number)
                    if dados_venda:
                        produto_id = buscar_produto_por_nome(dados_venda.get("produto"))
                        unidade_id = escolher_loja_para_produto(produto_id) if produto_id else None
                        registrar_venda(
                            number,
                            dados_venda.get("produto"),
                            dados_venda.get("quantidade", 1),
                            dados_venda.get("valor_unitario", 0),
                            unidade_id=unidade_id,
                        )
                        criar_pedido(number, dados_venda, unidade_id=unidade_id)

    except Exception as e:
        print("ERROR:", e)

    return "ok", 200


def ask_openai(number, text):
    if number not in historico:
        historico[number] = []

    historico[number].append({"role": "user", "content": text})

    historico[number] = [
        m for m in historico[number]
        if isinstance(m.get("content"), str) and m["content"].strip()
    ]

    saudacao = get_saudacao()

    if len(historico[number]) == 1:
        instrucao = (
            SYSTEM_PROMPT
            + f" Esta e a PRIMEIRA mensagem. Voce DEVE responder EXATAMENTE com:"
            + f" {saudacao}! Sou a Isabela, atendente virtual da Farmacia Saude e Vida."
            + f" Como posso te ajudar hoje? e nada mais."
        )
    else:
        instrucao = SYSTEM_PROMPT + " Esta NAO e a primeira mensagem. NAO se apresente. Responda diretamente."

    messages = [{"role": "system", "content": instrucao}] + historico[number][-12:]

    h = {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}
    b = {"model": "gpt-4o-mini", "messages": messages}

    try:
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            json=b, headers=h, timeout=30
        )
        r.raise_for_status()
        resultado = r.json()

        if not resultado.get("choices"):
            return "Desculpe, tive um problema interno. Pode repetir sua mensagem?"

        reply = resultado["choices"][0]["message"]["content"]
        historico[number].append({"role": "assistant", "content": reply})
        return reply

    except requests.exceptions.Timeout:
        return "Desculpe, demorei para responder. Pode repetir?"

    except requests.exceptions.HTTPError as e:
        print("ERRO HTTP OpenAI:", str(e))
        return "Estou com uma instabilidade agora. Tente novamente em instantes!"

    except Exception as e:
        print("ERRO inesperado OpenAI:", str(e))
        return "Ocorreu um erro inesperado. Por favor, tente novamente."


def oferecer_produto_proativamente(number):
    """Chamada logo apos o farmaceutico devolver o atendimento (/voltarbot).
    Faz a Isabela oferecer o produto recomendado, com preco, sem esperar
    o cliente falar antes."""
    if number not in historico:
        historico[number] = []

    instrucao = (
        SYSTEM_PROMPT
        + " O farmaceutico acabou de orientar o cliente (veja a mensagem de sistema mais recente"
        + " no historico). Agora, SEM esperar o cliente responder, ofereca proativamente o produto"
        + " recomendado, informando o nome e o preco da tabela, seguindo rigorosamente a REGRA"
        + " IMPORTANTE SOBRE RECEITA MEDICA definida acima. Pergunte se o cliente deseja finalizar"
        + " a compra. Nao se apresente novamente."
    )

    messages = [{"role": "system", "content": instrucao}] + historico[number][-12:]

    h = {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}
    b = {"model": "gpt-4o-mini", "messages": messages}

    try:
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            json=b, headers=h, timeout=30
        )
        r.raise_for_status()
        resultado = r.json()

        if not resultado.get("choices"):
            return

        reply = resultado["choices"][0]["message"]["content"]
        historico[number].append({"role": "assistant", "content": reply})
        send(number, reply)
        registrar_conversa(number, "[Retomado apos orientacao do farmaceutico]", reply)

    except Exception as e:
        print("ERRO ao oferecer produto proativamente:", e)


def send(number, text):
    h = {"token": TOKEN}
    b = {"number": number, "text": text}
    try:
        r = requests.post(BASE + "/send/text", json=b, headers=h, timeout=15)
        print("SEND:", r.status_code, r.text)
    except Exception as e:
        print("ERRO ao enviar mensagem:", e)


# Inicia o verificador de follow-up em segundo plano assim que o app carrega
# (funciona tanto rodando localmente quanto no Railway/gunicorn)
threading.Thread(target=verificar_seguimentos, daemon=True).start()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
