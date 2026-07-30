from flask import Flask, request, jsonify, make_response
import requests
import os
import re
import json
import base64
import random
import threading
import time
from datetime import datetime, timedelta
import pytz

from sincronizar_estoque import verificar_sincronizacao_estoque

app = Flask(__name__)

KEY = os.environ.get("OPENAI_API_KEY")
BASE = os.environ.get("UAZAPI_URL")
TOKEN = os.environ.get("UAZAPI_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

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
Antes de transferir, verifique se voce ja sabe o nome do cliente - seja porque ele disse nesta conversa, seja porque o sistema ja informou o nome dele (por exemplo, se voce ja o cumprimentou pelo nome no inicio da conversa, ou se ha uma mensagem de sistema dizendo que o nome ja e conhecido). Se ainda NAO souber o nome de nenhuma dessas formas, pergunte PRIMEIRO e SOMENTE: "Antes de te transferir para o nosso farmaceutico, qual e o seu nome?" e aguarde a resposta dele. Se ja souber o nome, pule essa pergunta e prossiga direto para a transferencia de verdade.
Assim que souber o nome (ou se ja sabia desde antes), responda EXATAMENTE e SOMENTE com o texto: TRANSFERIR_FARMACEUTICO
Nao escreva mais nada alem dessas palavras quando isso acontecer.

Isso e DIFERENTE de quando o cliente ja sabe o nome do medicamento e so quer saber preco ou disponibilidade (exemplo: "voces tem dipirona?", "quanto custa o paracetamol?") - nesses casos, responda normalmente com a tabela de precos.

REGRA CRITICA DE TRANSFERENCIA PARA ATENDENTE HUMANO (DESCONTO):
Se o cliente pedir DESCONTO, pechinchar o preco, ou perguntar se "tem como baixar o preco" / "faz um precinho" / "tem algum desconto", voce NAO deve conceder nenhum desconto nem negociar preco.
Antes de transferir, verifique se voce ja sabe o nome do cliente - seja porque ele disse nesta conversa, seja porque o sistema ja informou o nome dele (por exemplo, se voce ja o cumprimentou pelo nome no inicio da conversa, ou se ha uma mensagem de sistema dizendo que o nome ja e conhecido). Se ainda NAO souber o nome de nenhuma dessas formas, pergunte PRIMEIRO e SOMENTE: "Antes de te transferir para um atendente, qual e o seu nome?" e aguarde a resposta dele. Se ja souber o nome, pule essa pergunta e prossiga direto para a transferencia de verdade.
Assim que souber o nome (ou se ja sabia desde antes), responda EXATAMENTE e SOMENTE com o texto: TRANSFERIR_HUMANO
Nao escreva mais nada alem dessas palavras quando isso acontecer.

REGRA CRITICA DE ENCOMENDA (MEDICAMENTO INDISPONIVEL):
Se o cliente perguntar por um medicamento ou produto que NAO esta na tabela de precos acima (ou seja, a farmacia nao tem esse item em estoque), voce NAO deve simplesmente dizer que nao tem e encerrar o assunto. Nesse caso, voce vai transferir para um atendente humano verificar a possibilidade de encomendar o produto para o cliente.
Antes de transferir, verifique se voce ja sabe o nome do cliente - seja porque ele disse nesta conversa, seja porque o sistema ja informou o nome dele (por exemplo, se voce ja o cumprimentou pelo nome no inicio da conversa, ou se ha uma mensagem de sistema dizendo que o nome ja e conhecido). Se ainda NAO souber o nome de nenhuma dessas formas, pergunte PRIMEIRO e SOMENTE: "Antes de te transferir para um atendente, qual e o seu nome?" e aguarde a resposta dele. Se ja souber o nome, pule essa pergunta e prossiga direto para a transferencia de verdade.
Assim que souber o nome (ou se ja sabia desde antes), responda EXATAMENTE e SOMENTE com o texto: TRANSFERIR_ENCOMENDA
Nao escreva mais nada alem dessas palavras quando isso acontecer.
Isso e DIFERENTE de quando o produto pedido ESTA na tabela de precos (nesse caso, responda normalmente com o preco, sem transferir).

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
3. Se houver uma mensagem de sistema no inicio desta conversa dizendo que esse cliente ja comprou antes (com nome/endereco/forma de pagamento conhecidos), confirme esses dados com ele numa unica mensagem curta (ex: "Posso confirmar a entrega no mesmo endereco de sempre, [endereco]?") e peca so o que estiver faltando (normalmente so o CPF, que nunca fica salvo). Se ele disser que mudou algo, peca o dado atualizado.
   Se houver uma mensagem de sistema dizendo que o cliente ja informou o nome dele durante a conversa (por exemplo, na transferencia para humano/farmaceutico), NAO peca o nome de novo - use o nome ja informado e peca so os demais dados que faltarem.
   Se NAO houver nenhuma dessas informacoes, peca TODAS as informacoes de uma vez so, numa unica mensagem:
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

REGRA CRITICA CONTRA SUGESTOES REDUNDANTES:
Quando o cliente ja pedir um medicamento especifico (por nome, marca ou princípio ativo), voce NAO deve oferecer espontaneamente outro produto parecido, similar ou alternativo como se fosse mais uma opcao - isso e redundante e confunde quem ja sabe exatamente o que quer comprar.
Responda APENAS sobre o item que o cliente pediu, usando a tabela de precos.
A UNICA sugestao de produto adicional permitida e a oferta de produto complementar, que e feita automaticamente pelo sistema no momento de fechar a compra (nao por voce, na conversa). Voce NUNCA deve, por conta propria, sugerir um segundo produto (similar, generico, de outra marca, etc.) durante a conversa.

REGRA CRITICA E ABSOLUTA CONTRA ALTERACAO DE DOSAGEM (28/07/2026 e 29/07/2026):
Voce JAMAIS pode trocar, inventar ou "arredondar" a dosagem (miligramas/mg, concentracao, quantidade de comprimidos) de um medicamento. Isso ja causou erro real em producao mais de uma vez (ex: cliente pediu um medicamento e voce respondeu com uma dosagem diferente da que ele pediu, ou ofereceu uma dosagem que nao existe na tabela).
REGRAS SEM EXCECAO:
1. Voce SO pode oferecer exatamente as dosagens que estao literalmente escritas na TABELA DE PRECOS acima. Nunca calcule, estime ou "converta" uma dosagem para outra.
2. Se o cliente pedir uma dosagem que NAO esta na tabela (ex: pedir 2mg de um produto que so existe na tabela como 5mg), voce NUNCA deve oferecer a dosagem que existe como se fosse a que ele pediu, nem inventar uma dosagem nova. Responda informando claramente que essa dosagem especifica nao esta disponivel, e diga exatamente quais dosagens desse medicamento estao na tabela, perguntando se ele quer uma dessas.
3. Nunca presuma que uma dosagem parecida "deve ser a mesma coisa" ou "deve servir". Miligrama errado de medicamento e um erro grave, nao um detalhe.
4. Em caso de qualquer duvida sobre qual dosagem o cliente quer, PERGUNTE explicitamente antes de confirmar produto e preco - nunca assuma.

REGRAS OBRIGATORIAS:
- Apresente-se APENAS na primeira mensagem
- Nas demais mensagens NAO se reapresente
- Use os precos da tabela acima ao ser perguntada
- NUNCA oriente sobre dosagem ou substituicao de medicamentos - indique o farmaceutico
- Siga rigorosamente a REGRA CRITICA E ABSOLUTA CONTRA ALTERACAO DE DOSAGEM definida acima - isso e mais importante que ser prestativa
- Siga rigorosamente a REGRA IMPORTANTE SOBRE RECEITA MEDICA definida acima
- Seja breve e simpatica - maximo 3 paragrafos
- Use linguagem informal e acolhedora"""

historico = {}
mensagens_processadas = set()
transferido = {}
mensagens_farmaceutico = {}

FARMACEUTICO_TESTE = "5538998552537"
ultimo_cliente_transferido = None

CONTROLADOS_PALAVRAS_CHAVE = [
    "amoxicilina", "azitromicina", "cefalexina",
    "yasmin", "diane", "microvlar", "mercilon", "ciclo 21",
    "losartana", "enalapril", "anlodipino", "hidroclorotiazida",
    "clonazepam", "alprazolam", "escitalopram", "sertralina",
    "ritalina", "venvanse", "concerta",
]

aguardando_receita = {}
aguardando_oferta_complementar = {}
aguardando_avaliacao = {}
conversa_ativa_id = {}

TABELA_PRECOS = {
    "dipirona 500mg (20 comp)": 8.90,
    "paracetamol 750mg (20 comp)": 9.90,
    "ibuprofeno 600mg (20 comp)": 18.90,
    "aspirina 500mg (20 comp)": 12.90,
    "resfenol (16 caps)": 22.90,
    "coristina d (16 comp)": 19.90,
    "benegrip (20 comp)": 17.90,
    "neosoro spray nasal": 14.90,
    "nimesulida 100mg (20 comp)": 16.90,
    "diclofenaco 50mg (20 comp)": 14.90,
    "dorflex (30 comp)": 24.90,
    "cataflan 50mg (20 comp)": 28.90,
    "amoxicilina 500mg (21 caps)": 18.90,
    "azitromicina 500mg (3 comp)": 22.90,
    "cefalexina 500mg (20 caps)": 19.90,
    "amoxicilina + clavulanato 875mg (14 comp)": 49.90,
    "yasmin (21 comp)": 39.90,
    "diane 35 (21 comp)": 34.90,
    "microvlar (21 comp)": 19.90,
    "mercilon (21 comp)": 44.90,
    "ciclo 21 (21 comp)": 16.90,
    "losartana 50mg (30 comp)": 14.90,
    "enalapril 10mg (30 comp)": 12.90,
    "anlodipino 5mg (30 comp)": 13.90,
    "hidroclorotiazida 25mg (30 comp)": 9.90,
    "clonazepam 2mg (30 comp)": 19.90,
    "alprazolam 0,5mg (30 comp)": 18.90,
    "escitalopram 10mg (30 comp)": 29.90,
    "sertralina 50mg (30 comp)": 24.90,
    "ritalina 10mg (30 comp)": 89.90,
    "ritalina la 20mg (30 caps)": 129.90,
    "venvanse 30mg (28 caps)": 189.90,
    "concerta 36mg (30 comp)": 219.90,
    "vitamina c 1g (30 comp)": 19.90,
    "vitamina d 2000ui (30 caps)": 24.90,
    "complexo b (30 comp)": 16.90,
    "zinco + vitamina c (30 comp)": 22.90,
    "centrum (30 comp)": 49.90,
    "protetor solar fps 50 (120ml)": 39.90,
    "shampoo anticaspa (400ml)": 29.90,
    "creme hidratante corporal (400ml)": 34.90,
    "fio dental (50m)": 7.90,
    "escova dental": 12.90,
}


def buscar_preco_por_nome(nome_produto):
    """Busca o preco de referencia de um produto pelo nome, comparando com a
    tabela de precos usada pela Isabela. Usado para saber quanto cobrar pelo
    produto complementar sugerido, sem precisar consultar o banco."""
    if not nome_produto:
        return None
    nome = nome_produto.lower()
    for chave, preco in TABELA_PRECOS.items():
        if chave in nome or nome in chave:
            return preco
    primeira_palavra = nome.split(" ")[0]
    for chave, preco in TABELA_PRECOS.items():
        if chave.startswith(primeira_palavra):
            return preco
    return None


def eh_controlado(nome_produto):
    """Verifica se o produto identificado na venda e um dos que exigem
    receita medica, com base na lista de palavras-chave acima."""
    if not nome_produto:
        return False
    nome = nome_produto.lower()
    return any(palavra in nome for palavra in CONTROLADOS_PALAVRAS_CHAVE)


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
    """Baixa qualquer arquivo de midia do UAZAPI (audio, imagem etc), tentando
    primeiro com o token e depois sem, ja que o comportamento pode variar."""
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


def extrair_url_midia(msg):
    """Extrai a URL de download de uma midia a partir do payload do UAZAPI.
    Usado apenas como fallback para audio; para imagens, o caminho principal
    e a funcao baixar_midia_uazapi(), que usa o endpoint oficial
    /message/download (evita o link criptografado direto do WhatsApp)."""
    content = msg.get("content")
    url = None
    if isinstance(content, dict):
        url = content.get("URL") or content.get("url")
    elif isinstance(content, str) and content.startswith("http"):
        url = content

    if not url:
        direct_path = msg.get("directPath", "")
        if direct_path:
            url = BASE + "/proxy/media?path=" + direct_path

    return url


def baixar_midia_uazapi(message_id):
    """Usa o endpoint oficial da UAZAPI (/message/download) para baixar uma
    midia (imagem, audio etc) ja decodificada, a partir do ID completo da
    mensagem (formato owner:messageid, que e o proprio msg['id']). Isso evita
    lidar com o link criptografado direto do WhatsApp (mmg.whatsapp.net), que
    nao funciona como arquivo de verdade sem decodificacao. Retorna os bytes
    do arquivo, ou None se falhar."""
    if not BASE or not TOKEN or not message_id:
        return None
    try:
        headers = {"token": TOKEN, "Content-Type": "application/json"}
        body = {"id": message_id, "return_base64": True}
        r = requests.post(f"{BASE}/message/download", json=body, headers=headers, timeout=30)
        print(f"MESSAGE DOWNLOAD STATUS:{r.status_code}")
        if r.status_code != 200:
            print("ERRO message/download:", r.text[:300])
            return None
        resultado = r.json()
        base64_data = (
            resultado.get("base64Data")
            or resultado.get("base64")
            or resultado.get("data")
            or resultado.get("fileBase64")
            or resultado.get("file")
        )
        if not base64_data:
            print("AVISO: resposta de message/download sem base64:", str(resultado)[:300])
            return None
        if isinstance(base64_data, str) and base64_data.startswith("data:") and "," in base64_data:
            base64_data = base64_data.split(",", 1)[1]
        return base64.b64decode(base64_data)
    except Exception as e:
        print("ERRO ao baixar midia via message/download:", e)
        return None


def limpar_numero(valor):
    if not isinstance(valor, str):
        return ""
    return valor.replace("@s.whatsapp.net", "").replace("@lid", "")


encerrado = {}

PALAVRAS_DESPEDIDA = [
    "obrigad", "valeu", "vlw", "tchau", "ate mais", "ate logo", "de nada",
    "por nada", "certeza", "beleza", "blz", "flw", "otimo", "otima",
    "perfeito", "perfeita", "show", "top", "ok", "blza", "suave",
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


PALAVRAS_AFIRMATIVAS = [
    "sim", "quero", "pode", "claro", "aceito", "adiciona", "vou querer",
    "uhum", "bora", "manda", "perfeito", "com certeza", "isso", "positivo",
]


def e_resposta_afirmativa(texto):
    """Reconhece uma resposta afirmativa curta (usado para saber se o
    cliente aceitou a oferta de produto complementar)."""
    norm = normalizar_texto(texto)
    if not norm:
        return False
    for p in PALAVRAS_AFIRMATIVAS:
        if p in norm:
            return True
    return False


ultima_mensagem_cliente = {}
estagios_enviados = {}
seguimento_pendente_id = {}

ESTAGIOS_FOLLOWUP = [
    ("5min", 5, "Oi! Ainda esta por ai? Fico a disposicao se quiser continuar seu pedido 😊"),
    ("30min", 30, "Notei que voce ficou um tempinho sem responder. Posso te ajudar com mais alguma coisa?"),
    ("1h", 60, "So passando pra saber se ainda tem interesse no que conversamos. Se precisar, e so chamar!"),
]


def registrar_seguimento(number, estagio, mensagem):
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


def salvar_nota_avaliacao(conversa_id, nota):
    """Grava a nota de avaliacao (1 a 5) do cliente na linha da tabela
    conversas correspondente ao atendimento avaliado."""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY or not conversa_id:
        return
    try:
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
            "Content-Type": "application/json",
        }
        body = {"nota_avaliacao": nota}
        r = requests.patch(
            f"{SUPABASE_URL}/rest/v1/conversas?id=eq.{conversa_id}",
            json=body, headers=headers, timeout=15
        )
        print(f"SALVAR NOTA AVALIACAO STATUS:{r.status_code} BODY:{r.text[:300]}")
    except Exception as e:
        print("ERRO ao salvar nota de avaliacao:", e)


def registrar_conversa(number, mensagem, resposta, transferida=False, motivo=None, retornar_id=False):
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return None
    try:
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
            "Content-Type": "application/json",
        }
        if retornar_id:
            headers["Prefer"] = "return=representation"
        body = {
            "cliente_telefone": number,
            "mensagem": mensagem,
            "resposta": resposta,
            "transferida_humano": transferida,
        }
        if motivo:
            body["motivo_transferencia"] = motivo
        r = requests.post(f"{SUPABASE_URL}/rest/v1/conversas", json=body, headers=headers, timeout=15)
        print(f"REGISTRAR CONVERSA STATUS:{r.status_code} BODY:{r.text[:500]}")
        if retornar_id and r.status_code in (200, 201):
            dados = r.json()
            if dados:
                return dados[0].get("id")
        return None
    except Exception as e:
        print("ERRO ao registrar conversa:", e)
        return None


def escolher_atendente_menos_ocupada():
    """Escolhe, entre as atendentes ativas e que nao estao em pausa agora,
    quem tem menos atendimentos em andamento no momento (distribuicao
    automatica por carga, nao por ordem fixa). Em caso de empate, a
    escolha e aleatoria entre as empatadas, para nao favorecer sempre a
    mesma pessoa. Retorna {"id", "nome"} ou None se ninguem disponivel."""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return None
    try:
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        }
        params_atendentes = {"ativo": "eq.true", "em_pausa": "eq.false", "select": "id,nome"}
        r = requests.get(f"{SUPABASE_URL}/rest/v1/atendentes", headers=headers, params=params_atendentes, timeout=15)
        disponiveis = r.json()
        if not isinstance(disponiveis, list) or not disponiveis:
            return None

        params_conversas = {
            "atendimento_encerrado": "eq.false",
            "atendente_id": "not.is.null",
            "select": "atendente_id",
        }
        r2 = requests.get(f"{SUPABASE_URL}/rest/v1/conversas", headers=headers, params=params_conversas, timeout=15)
        conversas_ativas = r2.json()

        contagem = {}
        if isinstance(conversas_ativas, list):
            for c in conversas_ativas:
                aid = c.get("atendente_id")
                if aid:
                    contagem[aid] = contagem.get(aid, 0) + 1

        random.shuffle(disponiveis)
        disponiveis.sort(key=lambda a: contagem.get(a["id"], 0))
        escolhida = disponiveis[0]
        print(f"ATENDENTE ESCOLHIDA AUTOMATICAMENTE: {escolhida.get('nome')} (carga atual: {contagem.get(escolhida['id'], 0)})")
        return escolhida
    except Exception as e:
        print("ERRO ao escolher atendente menos ocupada:", e)
        return None


def atribuir_atendente_automaticamente(conversa_id, atendente_id):
    """Marca a conversa como ja assumida pela atendente escolhida
    automaticamente, pulando o status 'aberta' - a conversa entra direto
    como 'em atendimento' na tela Conversas."""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY or not conversa_id:
        return False
    try:
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
            "Content-Type": "application/json",
        }
        body = {
            "atendente_id": atendente_id,
            "atendimento_assumido_em": datetime.now(pytz.utc).isoformat(),
        }
        r = requests.patch(
            f"{SUPABASE_URL}/rest/v1/conversas?id=eq.{conversa_id}", json=body, headers=headers, timeout=15
        )
        print(f"AUTO-ATRIBUICAO STATUS:{r.status_code}")
        return r.status_code in (200, 204)
    except Exception as e:
        print("ERRO ao atribuir atendente automaticamente:", e)
        return False


def transferir_com_distribuicao_automatica(number, conversa_id_criada):
    """Depois de criar a conversa transferida para a fila humana, tenta
    distribuir automaticamente para a atendente disponivel com menos
    atendimentos em andamento agora. Se conseguir, ja manda a mensagem de
    apresentacao pro cliente (igual acontece quando alguem assume
    manualmente pela tela). Se ninguem estiver disponivel, a conversa
    fica como 'aberta' na fila, esperando alguem assumir manualmente."""
    if not conversa_id_criada:
        return

    atendente = escolher_atendente_menos_ocupada()
    if not atendente:
        print("Nenhuma atendente disponivel agora - conversa fica na fila 'aberta'.")
        return

    sucesso = atribuir_atendente_automaticamente(conversa_id_criada, atendente["id"])
    if not sucesso:
        return

    saudacao_apresentacao = get_saudacao()
    mensagem_apresentacao = f"{saudacao_apresentacao}! Me chamo {atendente['nome']} e estou aqui para lhe ajudar. 😊"
    send(number, mensagem_apresentacao)
    inserir_mensagem_atendimento(conversa_id_criada, "atendente", mensagem_apresentacao)


def buscar_conversa_humana_ativa(number):
    """Verifica no Supabase se existe uma conversa transferida para humano
    e ainda nao encerrada para esse telefone. Serve de fonte da verdade
    além da memória do processo (dicionario transferido/conversa_ativa_id),
    que se perde toda vez que o Railway reinicia ou faz um redeploy - sem
    isso, um atendimento em andamento "esquecia" que estava transferido
    assim que o servidor reiniciava, e a Isabela reiniciava a conversa do
    zero com o cliente."""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return None
    try:
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        }
        params = {
            "cliente_telefone": f"eq.{number}",
            "transferida_humano": "eq.true",
            "atendimento_encerrado": "eq.false",
            "select": "id",
            "order": "criado_em.desc",
            "limit": "1",
        }
        r = requests.get(f"{SUPABASE_URL}/rest/v1/conversas", headers=headers, params=params, timeout=15)
        dados = r.json()
        if isinstance(dados, list) and dados:
            return dados[0].get("id")
        return None
    except Exception as e:
        print("ERRO ao buscar conversa humana ativa:", e)
        return None


def inserir_mensagem_atendimento(conversa_id, remetente, texto):
    """Grava uma mensagem no historico de thread de um atendimento (usado
    tanto para a resposta da atendente quanto para as mensagens que o
    cliente manda de volta durante o atendimento humano)."""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY or not conversa_id:
        return
    try:
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
            "Content-Type": "application/json",
        }
        body = {
            "conversa_id": conversa_id,
            "remetente": remetente,
            "texto": texto,
        }
        requests.post(f"{SUPABASE_URL}/rest/v1/mensagens_atendimento", json=body, headers=headers, timeout=15)
    except Exception as e:
        print("ERRO ao inserir mensagem de atendimento:", e)


def extrair_nome_e_pergunta_original(number):
    """Usa a IA para identificar, dentro do historico da conversa, o nome que
    o cliente informou quando perguntado antes da transferencia, E a
    pergunta/pedido original do cliente que motivou a transferencia (a
    mensagem de ANTES do pedido de nome, nao a resposta com o nome em si).
    Retorna (nome, pergunta_original), qualquer um podendo ser None."""
    if number not in historico:
        return None, None

    instrucao = (
        "Na conversa abaixo, em algum momento o cliente fez uma pergunta ou pedido (por exemplo, sobre "
        "sintomas, indicacao de remedio, ou desconto). Logo depois, o atendente perguntou o nome do "
        "cliente antes de transferir, e o cliente respondeu com o nome dele. "
        "Responda APENAS em JSON puro, sem nenhum texto adicional, exatamente neste formato: "
        '{"nome": "nome informado pelo cliente ou null", '
        '"pergunta_original": "a pergunta ou pedido original do cliente, ANTES dele informar o nome, ou null"}.'
    )
    messages = [{"role": "system", "content": instrucao}] + historico[number][-10:]

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
        nome = dados.get("nome")
        pergunta = dados.get("pergunta_original")
        if isinstance(nome, str) and nome.lower() == "null":
            nome = None
        if isinstance(pergunta, str) and pergunta.lower() == "null":
            pergunta = None
        return nome, pergunta
    except Exception as e:
        print("ERRO ao extrair nome e pergunta original:", e)
        return None, None


def registrar_nome_conhecido(number, nome):
    """Grava na memoria da propria conversa (historico[number]) que o nome
    do cliente ja foi informado durante a transferencia (farmaceutico,
    humano ou encomenda). CORRECAO (29/07/2026): sem isso, quando a
    conversa voltava pra Isabela fechar a venda, o FLUXO DE PEDIDO
    OBRIGATORIO pedia nome/endereco/CPF/pagamento do zero, mesmo o cliente
    ja tendo dito o nome minutos antes, na etapa "antes de te transferir,
    qual e o seu nome?"."""
    if not nome:
        return
    if number not in historico:
        historico[number] = []
    historico[number].append({
        "role": "system",
        "content": (
            f"O cliente ja informou o nome dele nesta conversa: {nome}. "
            "Quando for pedir os dados para fechar um pedido (FLUXO DE PEDIDO "
            "OBRIGATORIO), NAO peca o nome de novo - use esse nome que ja foi "
            "informado. Peca so o que realmente ainda falta (endereco, CPF, "
            "forma de pagamento)."
        )
    })


def extrair_dados_venda(number):
    """Extrai os dados do pedido que acabou de ser fechado. IMPORTANTE: o
    pedido pode ter MAIS DE UM PRODUTO (ex: cliente pede Nimesulida e
    Amoxicilina na mesma conversa) - por isso o retorno sempre traz uma
    LISTA em "produtos", nunca um produto unico solto. Isso e critico para
    a checagem de medicamento controlado (ver eh_controlado/
    algum_item_controlado) nao pular nenhum item do carrinho."""
    if number not in historico:
        return None

    instrucao = (
        "Baseado na conversa abaixo, extraia os dados do pedido que acabou de ser fechado. "
        "O pedido pode ter UM OU MAIS produtos - inclua TODOS os produtos mencionados como "
        "parte da compra, nao só o primeiro. "
        "Responda APENAS em JSON puro, sem nenhum texto adicional, exatamente neste formato: "
        '{"produtos": [{"produto": "nome do produto", "quantidade": 1, "valor_unitario": 0.00}], '
        '"nome_cliente": "nome completo informado", "endereco": "endereco completo informado", '
        '"forma_pagamento": "Pix, cartao de credito, cartao de debito ou dinheiro"}. '
        'Se nao conseguir identificar nenhum produto com certeza, responda {"produtos": []}. '
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
        if not dados.get("produtos"):
            return None
        return dados
    except Exception as e:
        print("ERRO ao extrair dados da venda:", e)
        return None


def produtos_da_venda(dados_venda):
    """Retorna sempre uma lista de itens do pedido (cada um com produto/
    quantidade/valor_unitario), a partir do dados_venda retornado por
    extrair_dados_venda. Funcao central usada em todos os lugares que
    processam o carrinho, para nunca tratar so o primeiro item."""
    if not dados_venda:
        return []
    itens = dados_venda.get("produtos")
    if isinstance(itens, list):
        return [item for item in itens if item.get("produto")]
    return []


def algum_item_controlado(itens):
    """Verifica TODOS os itens do carrinho, nao so o primeiro - e a
    correcao do bug em que um pedido com 2+ produtos (ex: Nimesulida +
    Amoxicilina) deixava passar o item controlado sem pedir receita."""
    return any(eh_controlado(item.get("produto")) for item in itens)


def formatar_lista_itens(itens):
    """Monta uma descricao legivel do carrinho, tipo
    "Amoxicilina 500mg (21 caps) x1 + Nimesulida 100mg (20 comp) x1",
    usada para exibir o pedido completo nas telas e mensagens que hoje so
    tem um campo de texto para "produto"."""
    partes = []
    for item in itens:
        qtd = item.get("quantidade", 1)
        partes.append(f"{item.get('produto')} x{qtd}")
    return " + ".join(partes) if partes else ""


def extrair_dados_receita(image_bytes):
    """Usa a IA de visao para ler a foto da receita e extrair os dados
    necessarios para o lancamento posterior no SNGPC (via HOS). O prompt e
    rigoroso de proposito: a IA NAO pode adivinhar ou usar dados de outras
    partes da conversa, apenas o que estiver escrito de forma legivel na
    propria imagem, para evitar alucinacao (inventar nome de paciente etc)."""
    try:
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        instrucao = (
            "Voce esta analisando a foto de um documento que pode ou nao ser uma receita medica de verdade. "
            "Sua tarefa e EXTRAIR APENAS o que estiver escrito de forma clara e legivel NA PROPRIA IMAGEM. "
            "REGRAS OBRIGATORIAS, SEM EXCECAO: "
            "1. NUNCA infira, adivinhe ou reutilize nomes, datas ou numeros vindos de qualquer outra fonte "
            "que nao seja o texto visivel na imagem. "
            "2. Se a imagem NAO for uma receita medica (por exemplo, for outro tipo de documento, foto, "
            "anotacao ou papel qualquer), retorne null em TODOS os campos. "
            "3. Se um campo nao estiver escrito com clareza na imagem, retorne null para aquele campo "
            "especifico - nunca invente ou complete com suposicoes. "
            "4. Nomes de pessoas so podem ser preenchidos se estiverem escritos literalmente na imagem, "
            "associados claramente a um campo tipo 'Paciente:', 'Nome:' ou similar. "
            "Responda APENAS em JSON puro, sem nenhum texto adicional, exatamente neste formato: "
            '{"e_receita_medica": true ou false, "data_receita": "DD/MM/AAAA ou null", '
            '"nome_paciente": "nome completo ou null", '
            '"sexo_paciente": "M, F ou null", "idade_paciente": "idade em anos ou null", '
            '"registro_profissional": "numero e sigla do CRM/CRO/CRMV/RMS de quem prescreveu ou null"}.'
        )
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": instrucao},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ],
            }
        ]
        h = {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}
        b = {"model": "gpt-4o-mini", "messages": messages}
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            json=b, headers=h, timeout=30
        )
        r.raise_for_status()
        resultado = r.json()
        conteudo = resultado["choices"][0]["message"]["content"].strip()
        conteudo = re.sub(r"^```json|^```|```$", "", conteudo, flags=re.MULTILINE).strip()
        dados = json.loads(conteudo)
        for chave, valor in list(dados.items()):
            if isinstance(valor, str) and valor.strip().lower() == "null":
                dados[chave] = None
        return dados
    except Exception as e:
        print("ERRO ao extrair dados da receita:", e)
        return {}


def subir_foto_receita(image_bytes, number):
    """Envia a foto da receita para o bucket 'receitas' no Supabase Storage
    e retorna a URL publica da imagem, ou None se falhar."""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return None
    try:
        timestamp = int(time.time())
        filename = f"{number}_{timestamp}.jpg"
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
            "Content-Type": "image/jpeg",
        }
        r = requests.post(
            f"{SUPABASE_URL}/storage/v1/object/receitas/{filename}",
            headers=headers, data=image_bytes, timeout=30
        )
        if r.status_code in (200, 201):
            return f"{SUPABASE_URL}/storage/v1/object/public/receitas/{filename}"
        print("ERRO upload receita:", r.status_code, r.text)
        return None
    except Exception as e:
        print("ERRO ao subir foto da receita:", e)
        return None


def salvar_receita_pendente(number, dados_venda, dados_receita, foto_url):
    """Grava no Supabase o registro da receita aguardando aprovacao do
    farmaceutico, com os dados do pedido e os dados extraidos da receita.

    IMPORTANTE (correcao 28/07/2026): o pedido pode ter varios produtos, nao
    so o controlado. Por isso gravamos a lista completa em "itens_json"
    (nova coluna, precisa existir na tabela receitas_pendentes - ver
    instrucao de ALTER TABLE), preservando cada item com produto/
    quantidade/valor_unitario para reconstruir a venda certinho quando o
    farmaceutico aprovar. Os campos antigos (produto/quantidade/
    valor_unitario) continuam preenchidos, com um resumo legivel de TODOS
    os itens, so para a tela atual de Receitas Pendentes continuar
    mostrando algo com sentido sem precisar mudar o frontend agora."""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return
    try:
        itens = produtos_da_venda(dados_venda)
        descricao_itens = formatar_lista_itens(itens) or dados_venda.get("produto")
        quantidade_total = sum(int(round(float(item.get("quantidade", 1)))) for item in itens) if itens else dados_venda.get("quantidade", 1)
        valor_total = (
            sum(float(item.get("quantidade", 1)) * float(item.get("valor_unitario", 0)) for item in itens)
            if itens else dados_venda.get("valor_unitario", 0)
        )

        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
            "Content-Type": "application/json",
        }
        body = {
            "cliente_telefone": number,
            "produto": descricao_itens,
            "quantidade": quantidade_total,
            "valor_unitario": round(valor_total, 2),
            "itens_json": itens,
            "nome_cliente": dados_venda.get("nome_cliente"),
            "endereco": dados_venda.get("endereco"),
            "forma_pagamento": dados_venda.get("forma_pagamento"),
            "foto_receita_url": foto_url,
            "data_receita_extraida": dados_receita.get("data_receita"),
            "nome_paciente": dados_receita.get("nome_paciente"),
            "sexo_paciente": dados_receita.get("sexo_paciente"),
            "idade_paciente": dados_receita.get("idade_paciente"),
            "registro_profissional": dados_receita.get("registro_profissional"),
            "status": "pendente",
        }
        r = requests.post(f"{SUPABASE_URL}/rest/v1/receitas_pendentes", json=body, headers=headers, timeout=15)
        print("RECEITA PENDENTE SALVA:", r.status_code, r.text)
    except Exception as e:
        print("ERRO ao salvar receita pendente:", e)


def notificar_farmaceutico_receita_pendente(number, dados_venda):
    """Manda um aviso curto para o farmaceutico (sem a foto, para nao lotar
    o WhatsApp dele) informando que ha uma receita nova aguardando revisao
    no sistema. Lista TODOS os itens do pedido, nao so o controlado, para
    o farmaceutico ter o contexto completo da compra."""
    itens = produtos_da_venda(dados_venda)
    descricao = formatar_lista_itens(itens) or dados_venda.get("produto", "medicamento controlado")
    mensagem = (
        f"📋 Nova receita aguardando aprovacao!\n"
        f"Pedido: {descricao}\n"
        f"Cliente: {number}\n"
        f"Acesse o VidaFarma, na aba Receitas Pendentes, para revisar a foto e aprovar ou recusar."
    )
    send(FARMACEUTICO_TESTE, mensagem)


def buscar_produto_complementar(produto_id):
    """Busca na tabela produtos_associados se existe algum produto marcado
    como 'complementar' para o produto informado (usado para a Isabela
    oferecer um item extra na hora de fechar a venda, tipo 'leva tambem').
    Retorna {"id", "nome", "preco"} ou None se nao houver associacao."""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY or not produto_id:
        return None
    try:
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        }
        params = f"produto_id=eq.{produto_id}&tipo=eq.complementar&select=produto_associado_id&limit=1"
        r = requests.get(f"{SUPABASE_URL}/rest/v1/produtos_associados?{params}", headers=headers, timeout=15)
        dados = r.json()
        if not dados:
            return None
        associado_id = dados[0].get("produto_associado_id")
        if not associado_id:
            return None
        params2 = f"id=eq.{associado_id}&select=nome&limit=1"
        r2 = requests.get(f"{SUPABASE_URL}/rest/v1/produtos?{params2}", headers=headers, timeout=15)
        produtos = r2.json()
        if not produtos:
            return None
        nome = produtos[0].get("nome")
        preco = buscar_preco_por_nome(nome)
        return {"id": associado_id, "nome": nome, "preco": preco}
    except Exception as e:
        print("ERRO ao buscar produto complementar:", e)
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
    """Consulta a tabela estoque (estoque real por loja, ja existente no
    sistema) e escolhe, entre as lojas que tem estoque disponivel
    (quantidade > 0) para o produto, a de maior prioridade (menor numero
    em ordem_prioridade). Retorna o unidade_id escolhido, ou None se
    nenhuma loja tiver estoque."""
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
        r = requests.get(f"{SUPABASE_URL}/rest/v1/estoque?{params}", headers=headers, timeout=15)
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


def registrar_venda(number, produto, quantidade, valor_unitario, unidade_id=None, produto_id=None):
    """Grava no Supabase a venda fechada pela Isabela. Quando a loja de
    origem e identificada (produto encontrado no banco + estoque
    disponivel em alguma loja), grava tambem o unidade_id correspondente.
    Grava tambem produto_id quando encontrado, para permitir relatorios
    precisos de categoria/custo/margem no futuro."""
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
        if produto_id:
            body["produto_id"] = produto_id

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


def criar_pedido_com_itens(number, nome_cliente, endereco, forma_pagamento, itens, valor_total, unidade_id=None):
    """Igual a criar_pedido, mas aceita uma lista de itens e um valor total
    ja calculados - usado quando o cliente aceita levar tambem um produto
    complementar junto com a compra original."""
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
            "itens": itens,
            "valor_total": valor_total,
            "forma_pagamento": forma_pagamento,
            "status": "pendente",
            "nome_cliente": nome_cliente,
            "endereco": endereco,
        }
        if unidade_id:
            body["unidade_id"] = unidade_id

        r = requests.post(f"{SUPABASE_URL}/rest/v1/pedidos", json=body, headers=headers, timeout=15)
        print("PEDIDO CRIADO (com itens):", r.status_code, r.text)
    except Exception as e:
        print("ERRO ao criar pedido com itens:", e)


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


DIAS_ANTECEDENCIA_LEMBRETE = 3


def buscar_vendas_uso_continuo():
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        print("[DEBUG LEMBRETE] SUPABASE_URL ou SUPABASE_ANON_KEY nao configurados")
        return []
    try:
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        }
        params = (
            "select=id,cliente_telefone,produto_id,data_venda,quantidade,"
            "produtos!inner(nome,uso_continuo,dias_duracao_estimados)"
            "&produtos.uso_continuo=eq.true"
        )
        r = requests.get(f"{SUPABASE_URL}/rest/v1/vendas?{params}", headers=headers, timeout=15)
        print(f"[DEBUG LEMBRETE] Status da consulta: {r.status_code}")
        print(f"[DEBUG LEMBRETE] Resposta: {r.text[:1000]}")
        dados = r.json()
        if isinstance(dados, list):
            return dados
        return []
    except Exception as e:
        print("ERRO ao buscar vendas de uso continuo:", e)
        return []


def ja_foi_lembrado(venda_id):
    if not SUPABASE_URL or not SUPABASE_ANON_KEY or not venda_id:
        return True
    try:
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        }
        params = f"venda_id=eq.{venda_id}&select=id&limit=1"
        r = requests.get(f"{SUPABASE_URL}/rest/v1/lembretes_recompra?{params}", headers=headers, timeout=15)
        dados = r.json()
        return bool(dados)
    except Exception as e:
        print("ERRO ao verificar lembrete existente:", e)
        return True


def registrar_lembrete_enviado(cliente_telefone, produto_id, venda_id):
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return
    try:
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
            "Content-Type": "application/json",
        }
        body = {
            "cliente_telefone": cliente_telefone,
            "produto_id": produto_id,
            "venda_id": venda_id,
        }
        requests.post(f"{SUPABASE_URL}/rest/v1/lembretes_recompra", json=body, headers=headers, timeout=15)
    except Exception as e:
        print("ERRO ao registrar lembrete de recompra:", e)


def verificar_lembretes_recompra():
    while True:
        try:
            hoje = datetime.now(pytz.timezone("America/Sao_Paulo")).date()
            print(f"[DEBUG LEMBRETE] Verificacao iniciada. Hoje: {hoje}")
            vendas = buscar_vendas_uso_continuo()
            print(f"[DEBUG LEMBRETE] Vendas encontradas: {len(vendas)}")

            for venda in vendas:
                produto_info = venda.get("produtos") or {}
                dias_duracao = produto_info.get("dias_duracao_estimados")
                print(f"[DEBUG LEMBRETE] Venda {venda.get('id')} - produto: {produto_info.get('nome')} - dias_duracao: {dias_duracao}")
                if not dias_duracao:
                    continue

                data_venda_str = venda.get("data_venda", "")
                try:
                    data_venda = datetime.fromisoformat(data_venda_str.replace("Z", "+00:00"))
                except Exception:
                    continue

                data_venda_sp = data_venda.astimezone(pytz.timezone("America/Sao_Paulo")).date()
                data_prevista_recompra = data_venda_sp + timedelta(days=int(dias_duracao))
                data_envio_lembrete = data_prevista_recompra - timedelta(days=DIAS_ANTECEDENCIA_LEMBRETE)
                print(f"[DEBUG LEMBRETE] data_venda: {data_venda_sp} | previsao: {data_prevista_recompra} | envia a partir de: {data_envio_lembrete}")

                if hoje < data_envio_lembrete or hoje > data_prevista_recompra:
                    print("[DEBUG LEMBRETE] Fora da janela de envio, pulando.")
                    continue

                venda_id = venda.get("id")
                if ja_foi_lembrado(venda_id):
                    continue

                cliente_telefone = venda.get("cliente_telefone")
                produto_id = venda.get("produto_id")
                nome_produto = produto_info.get("nome", "seu medicamento")

                if not cliente_telefone:
                    continue

                mensagem = (
                    f"Oi! Passando para lembrar que seu {nome_produto} deve estar acabando em breve. "
                    f"Quer que eu já separe uma nova caixa para você? 😊"
                )
                send(cliente_telefone, mensagem)
                registrar_lembrete_enviado(cliente_telefone, produto_id, venda_id)
                print(f"[LEMBRETE RECOMPRA] Enviado para {cliente_telefone} - {nome_produto}")

        except Exception as e:
            print("ERRO no verificador de lembretes de recompra:", e)

        time.sleep(6 * 60 * 60)


def buscar_reaberturas_pendentes():
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return []
    try:
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        }
        agora_iso = datetime.now(pytz.utc).isoformat()
        params = {
            "processada": "eq.false",
            "reabre_em": f"lte.{agora_iso}",
            "select": "id,conversa_id,cliente_telefone",
        }
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/reaberturas_agendadas",
            headers=headers, params=params, timeout=15
        )
        print(f"BUSCAR REABERTURAS PENDENTES STATUS:{r.status_code} BODY:{r.text[:300]}")
        dados = r.json()
        if isinstance(dados, list):
            return dados
        return []
    except Exception as e:
        print("ERRO ao buscar reaberturas pendentes:", e)
        return []


def reabrir_conversa(conversa_id):
    """Volta a conversa para o estado 'aberta' no painel (sem atendente
    atribuido, sem encerramento), para que apareca na fila normal de
    atendimentos abertos e alguem possa contatar o cliente."""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY or not conversa_id:
        return False
    try:
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
            "Content-Type": "application/json",
        }
        body = {
            "atendimento_encerrado": False,
            "atendimento_assumido_em": None,
            "aguardando_cliente": False,
            "atendente_id": None,
        }
        r = requests.patch(
            f"{SUPABASE_URL}/rest/v1/conversas?id=eq.{conversa_id}",
            json=body, headers=headers, timeout=15
        )
        print(f"REABRIR CONVERSA {conversa_id} STATUS:{r.status_code}")
        return r.status_code in (200, 204)
    except Exception as e:
        print("ERRO ao reabrir conversa:", e)
        return False


def marcar_reabertura_processada(reabertura_id):
    if not SUPABASE_URL or not SUPABASE_ANON_KEY or not reabertura_id:
        return
    try:
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
            "Content-Type": "application/json",
        }
        requests.patch(
            f"{SUPABASE_URL}/rest/v1/reaberturas_agendadas?id=eq.{reabertura_id}",
            json={"processada": True}, headers=headers, timeout=15
        )
    except Exception as e:
        print("ERRO ao marcar reabertura como processada:", e)


def verificar_reaberturas_agendadas():
    while True:
        try:
            pendentes = buscar_reaberturas_pendentes()
            for item in pendentes:
                conversa_id = item.get("conversa_id")
                reabertura_id = item.get("id")
                sucesso = reabrir_conversa(conversa_id)
                if sucesso:
                    marcar_reabertura_processada(reabertura_id)
                    print(f"[REABERTURA] Conversa {conversa_id} reaberta com sucesso")
        except Exception as e:
            print("ERRO no verificador de reaberturas agendadas:", e)

        time.sleep(60)


@app.route("/aprovar-receita", methods=["POST", "OPTIONS"])
def aprovar_receita_endpoint():
    if request.method == "OPTIONS":
        resp = make_response()
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return resp

    def com_cors(resposta_json, status=200):
        resp = jsonify(resposta_json)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.status_code = status
        return resp

    try:
        data = request.json or {}
        receita_id = data.get("id")
        if not receita_id:
            return com_cors({"erro": "id da receita e obrigatorio"}, 400)

        if not SUPABASE_URL or not SUPABASE_ANON_KEY:
            return com_cors({"erro": "Supabase nao configurado"}, 500)

        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        }
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/receitas_pendentes?id=eq.{receita_id}&select=*",
            headers=headers, timeout=15
        )
        registros = r.json()
        if not registros:
            return com_cors({"erro": "receita nao encontrada"}, 404)

        receita = registros[0]
        number = receita.get("cliente_telefone")

        # CORRECAO (28/07/2026): usa itens_json quando existir (pedidos com
        # 1+ produtos, salvos pela versao corrigida de salvar_receita_pendente).
        # Registros antigos sem itens_json caem no fallback de item unico,
        # para nao quebrar receitas que ja estavam pendentes antes da correcao.
        itens = receita.get("itens_json")
        if not isinstance(itens, list) or not itens:
            itens = [{
                "produto": receita.get("produto"),
                "quantidade": receita.get("quantidade", 1),
                "valor_unitario": receita.get("valor_unitario", 0),
            }]

        nome_cliente = receita.get("nome_cliente")
        endereco = receita.get("endereco")
        forma_pagamento = receita.get("forma_pagamento")

        itens_pedido = []
        valor_total_pedido = 0.0
        unidade_id_escolhida = None

        for item in itens:
            produto_id_item = buscar_produto_por_nome(item.get("produto"))
            unidade_id_item = escolher_loja_para_produto(produto_id_item) if produto_id_item else None
            if unidade_id_escolhida is None:
                unidade_id_escolhida = unidade_id_item

            qtd = item.get("quantidade", 1)
            valor_unit = item.get("valor_unitario", 0)

            registrar_venda(
                number,
                item.get("produto"),
                qtd,
                valor_unit,
                unidade_id=unidade_id_item,
                produto_id=produto_id_item,
            )
            itens_pedido.append({"qtd": int(round(float(qtd))), "produto": item.get("produto")})
            valor_total_pedido += float(qtd) * float(valor_unit)

        criar_pedido_com_itens(
            number,
            nome_cliente=nome_cliente,
            endereco=endereco,
            forma_pagamento=forma_pagamento,
            itens=itens_pedido,
            valor_total=round(valor_total_pedido, 2),
            unidade_id=unidade_id_escolhida,
        )

        # CORRECAO (29/07/2026): mensagem simplificada, seguindo feedback da
        # reuniao com Daniel/Lucas/Henrique - a descricao longa sobre "receita
        # aprovada pelo farmaceutico" foi tirada; o foco agora e confirmar a
        # entrega e lembrar de ter a receita fisica/original em maos.
        mensagem_aprovado = (
            "Tudo certo! Sua entrega já está sendo providenciada. 😊\n"
            "Só não esqueça de ter a receita original em mãos na hora da entrega.\n\n"
            "Foi um prazer te atender!\n\n"
            "Que tal deixar uma avaliação para nos ajudar a melhorar?\n"
            "⭐ Farmacia Saude e Vida: https://search.google.com/local/writereview?placeid=ChIJAQBsTgC5rgARK0oiw3CQOpg\n\n"
            "Obrigada pela preferência! Volte sempre. 💙"
        )
        send(number, mensagem_aprovado)
        registrar_conversa(number, "[Receita aprovada pelo farmaceutico]", mensagem_aprovado)
        encerrado[number] = True

        return com_cors({"ok": True})
    except Exception as e:
        print("ERRO ao aprovar receita:", e)
        return com_cors({"erro": str(e)}, 500)


@app.route("/recusar-receita", methods=["POST", "OPTIONS"])
def recusar_receita_endpoint():
    """Endpoint chamado pela tela Receitas Pendentes quando o farmaceutico
    recusa uma receita. CORRECAO (28/07/2026): antes, o botao "Recusar" so
    atualizava o status no Supabase direto do frontend - o cliente nunca
    recebia nenhuma resposta, ficava esperando pra sempre. Agora o cliente
    e avisado do motivo da recusa e pode reenviar uma nova foto."""
    if request.method == "OPTIONS":
        resp = make_response()
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return resp

    def com_cors(resposta_json, status=200):
        resp = jsonify(resposta_json)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.status_code = status
        return resp

    try:
        data = request.json or {}
        receita_id = data.get("id")
        motivo = (data.get("motivo") or "").strip()

        if not receita_id:
            return com_cors({"erro": "id da receita e obrigatorio"}, 400)

        if not SUPABASE_URL or not SUPABASE_ANON_KEY:
            return com_cors({"erro": "Supabase nao configurado"}, 500)

        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        }
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/receitas_pendentes?id=eq.{receita_id}&select=*",
            headers=headers, timeout=15
        )
        registros = r.json()
        if not registros:
            return com_cors({"erro": "receita nao encontrada"}, 404)

        receita = registros[0]
        number = receita.get("cliente_telefone")
        motivo_texto = motivo or receita.get("motivo_recusa") or "não foi possível confirmar a validade da receita enviada"

        mensagem_recusa = (
            "Poxa, sua receita não foi aprovada pelo nosso farmacêutico responsável.\n"
            f"Motivo: {motivo_texto}\n\n"
            "Se puder, envie uma nova foto da receita (bem legível e completa) que a gente "
            "reavalia com prazer! Qualquer dúvida, é só chamar. 💙"
        )
        send(number, mensagem_recusa)
        registrar_conversa(number, "[Receita recusada pelo farmaceutico]", mensagem_recusa)

        # CORRECAO 2 (28/07/2026): o estado aguardando_receita[number] ja
        # tinha sido apagado la atras, no momento em que a PRIMEIRA foto foi
        # recebida (ver o "aguardando_receita.pop(number)" no webhook) - nao
        # era mais nada a "nao apagar" aqui, como a correcao anterior supos.
        # Por isso a proxima foto do cliente nunca era processada: o numero
        # simplesmente nao estava mais marcado como "aguardando receita".
        # A correcao de verdade e RECRIAR esse estado aqui, reconstruindo o
        # pedido a partir do que ja esta salvo no Supabase, para a proxima
        # foto ser aceita normalmente pelo mesmo trecho do webhook.
        itens_reconstruidos = receita.get("itens_json")
        if not isinstance(itens_reconstruidos, list) or not itens_reconstruidos:
            itens_reconstruidos = [{
                "produto": receita.get("produto"),
                "quantidade": receita.get("quantidade", 1),
                "valor_unitario": receita.get("valor_unitario", 0),
            }]

        aguardando_receita[number] = {
            "produtos": itens_reconstruidos,
            "nome_cliente": receita.get("nome_cliente"),
            "endereco": receita.get("endereco"),
            "forma_pagamento": receita.get("forma_pagamento"),
        }

        return com_cors({"ok": True})
    except Exception as e:
        print("ERRO ao recusar receita:", e)
        return com_cors({"erro": str(e)}, 500)


@app.route("/responder-atendimento", methods=["POST", "OPTIONS"])
def responder_atendimento_endpoint():
    """Endpoint usado pela tela de Conversas do VidaFarma para a atendente
    humana enviar uma mensagem de verdade pro cliente, via UAZAPI. Recebe
    telefone e mensagem; nao mexe na tabela conversas (o status do
    atendimento continua controlado pelos campos ja existentes)."""
    if request.method == "OPTIONS":
        resp = make_response()
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return resp

    def com_cors(resposta_json, status=200):
        resp = jsonify(resposta_json)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.status_code = status
        return resp

    try:
        data = request.json or {}
        telefone = data.get("telefone")
        mensagem = data.get("mensagem")
        conversa_id = data.get("conversa_id")

        if not telefone or not mensagem:
            return com_cors({"erro": "telefone e mensagem sao obrigatorios"}, 400)

        send(telefone, mensagem)

        if conversa_id:
            conversa_ativa_id[telefone] = conversa_id
            inserir_mensagem_atendimento(conversa_id, "atendente", mensagem)

        return com_cors({"ok": True})
    except Exception as e:
        print("ERRO ao responder atendimento:", e)
        return com_cors({"erro": str(e)}, 500)


@app.route("/criar-acesso", methods=["POST", "OPTIONS"])
def criar_acesso_endpoint():
    """Cria um login individual (Supabase Auth) + o perfil correspondente
    (papel henrique/atendente, vinculado opcionalmente a um atendente_id).
    Usa a service_role key, que so existe aqui no servidor - nunca deve
    ir para o codigo do painel (frontend)."""
    if request.method == "OPTIONS":
        resp = make_response()
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return resp

    def com_cors(resposta_json, status=200):
        resp = jsonify(resposta_json)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.status_code = status
        return resp

    try:
        data = request.json or {}
        nome = (data.get("nome") or "").strip()
        email = (data.get("email") or "").strip()
        senha = data.get("senha") or ""
        papel = data.get("papel")
        atendente_id = data.get("atendente_id")

        if not nome or not email or not senha or papel not in ("henrique", "atendente", "separador"):
            return com_cors({"erro": "Preencha nome, e-mail, senha e papel corretamente"}, 400)

        if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
            return com_cors({"erro": "Service role key nao configurada no servidor"}, 500)

        headers_admin = {
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": "application/json",
        }

        r = requests.post(
            f"{SUPABASE_URL}/auth/v1/admin/users",
            json={"email": email, "password": senha, "email_confirm": True},
            headers=headers_admin, timeout=20,
        )

        if r.status_code not in (200, 201):
            print("ERRO ao criar usuario auth:", r.status_code, r.text)
            return com_cors({"erro": "Nao foi possivel criar o login (e-mail ja existe ou senha fraca)"}, 400)

        usuario = r.json()
        user_id = usuario.get("id")

        body_perfil = {"user_id": user_id, "nome": nome, "email": email, "papel": papel}
        if atendente_id:
            body_perfil["atendente_id"] = atendente_id

        r2 = requests.post(
            f"{SUPABASE_URL}/rest/v1/perfis", json=body_perfil, headers=headers_admin, timeout=15
        )

        if r2.status_code not in (200, 201):
            print("ERRO ao criar perfil:", r2.status_code, r2.text)
            requests.delete(f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}", headers=headers_admin, timeout=15)
            return com_cors({"erro": "Login criado, mas houve erro ao salvar o perfil. Tente novamente."}, 500)

        return com_cors({"ok": True})
    except Exception as e:
        print("ERRO ao criar acesso:", e)
        return com_cors({"erro": str(e)}, 500)


@app.route("/excluir-acesso", methods=["POST", "OPTIONS"])
def excluir_acesso_endpoint():
    """Exclui um login individual (Supabase Auth). O perfil correspondente
    e apagado automaticamente por CASCADE."""
    if request.method == "OPTIONS":
        resp = make_response()
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return resp

    def com_cors(resposta_json, status=200):
        resp = jsonify(resposta_json)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.status_code = status
        return resp

    try:
        data = request.json or {}
        user_id = data.get("user_id")
        if not user_id:
            return com_cors({"erro": "user_id e obrigatorio"}, 400)

        if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
            return com_cors({"erro": "Service role key nao configurada no servidor"}, 500)

        headers_admin = {
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        }
        r = requests.delete(f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}", headers=headers_admin, timeout=20)

        if r.status_code not in (200, 204):
            print("ERRO ao excluir usuario auth:", r.status_code, r.text)
            return com_cors({"erro": "Nao foi possivel excluir o login"}, 400)

        return com_cors({"ok": True})
    except Exception as e:
        print("ERRO ao excluir acesso:", e)
        return com_cors({"erro": str(e)}, 500)


@app.route("/pedir-avaliacao", methods=["POST", "OPTIONS"])
def pedir_avaliacao_endpoint():
    """Endpoint usado pela tela de Conversas do VidaFarma quando a atendente
    clica em 'Encerrar atendimento'. Manda a pergunta de nota (1 a 5) pro
    cliente e guarda qual conversa deve receber a nota quando ele responder.

    IMPORTANTE: aqui tambem encerramos o vinculo desse telefone com o
    atendimento humano que acabou de ser fechado (transferido[telefone] e
    conversa_ativa_id[telefone]). Sem isso, o sistema continuava achando
    para sempre que aquele numero "ja estava transferido", e um pedido novo
    do mesmo cliente no futuro nunca chegava a abrir uma conversa nova no
    painel - so ficava caindo (ou se perdendo) dentro do atendimento antigo
    ja encerrado.
    """
    if request.method == "OPTIONS":
        resp = make_response()
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return resp

    def com_cors(resposta_json, status=200):
        resp = jsonify(resposta_json)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.status_code = status
        return resp

    try:
        data = request.json or {}
        telefone = data.get("telefone")
        conversa_id = data.get("conversa_id")

        if not telefone or not conversa_id:
            return com_cors({"erro": "telefone e conversa_id sao obrigatorios"}, 400)

        aguardando_avaliacao[telefone] = conversa_id

        transferido[telefone] = False
        conversa_ativa_id.pop(telefone, None)
        # Impede que o verificador de follow-up automatico (mensagens tipo
        # "notei que voce sumiu...") mande algo pra esse cliente logo
        # depois que um humano acabou de encerrar o atendimento.
        encerrado[telefone] = True

        mensagem = (
            "Antes de encerrarmos, que nota de 1 a 5 voce da para o atendimento que "
            "acabou de receber? Basta responder com um numero. 😊"
        )
        send(telefone, mensagem)

        return com_cors({"ok": True})
    except Exception as e:
        print("ERRO ao pedir avaliacao:", e)
        return com_cors({"erro": str(e)}, 500)


def retomar_atendimento_com_ia(number):
    """Depois que um atendente humano devolve a conversa pra Isabela (via
    /voltar-para-ia), gera proativamente a proxima mensagem dela SEM
    esperar o cliente escrever de novo - mesmo padrao ja usado quando o
    farmaceutico devolve a conversa via /voltarbot (oferecer_produto_proativamente)."""
    if number not in historico:
        return

    instrucao = (
        SYSTEM_PROMPT
        + " O atendimento acabou de ser devolvido para voce depois de uma negociacao com um"
        + " atendente humano (veja a mensagem de sistema mais recente no historico, com o resumo"
        + " do que foi combinado - por exemplo, um desconto aceito). Continue o atendimento a"
        + " partir dai, seguindo o FLUXO DE PEDIDO OBRIGATORIO, considerando o que foi combinado."
        + " Nao se apresente novamente e nao peca informacoes que ja tenham sido informadas antes"
        + " nesta conversa."
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
        registrar_conversa(number, "[Retomado apos negociacao com atendente humano]", reply)

    except Exception as e:
        print("ERRO ao retomar atendimento com a IA:", e)


@app.route("/voltar-para-ia", methods=["POST", "OPTIONS"])
def voltar_para_ia_endpoint():
    """Endpoint chamado pela tela de Conversas quando a atendente clica em
    'Voltar para Isabela' - devolve o atendimento pra IA fechar a venda
    (por exemplo, apos negociar desconto), em vez de so encerrar o
    atendimento e pedir avaliacao (que e o que /pedir-avaliacao faz)."""
    if request.method == "OPTIONS":
        resp = make_response()
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return resp

    def com_cors(resposta_json, status=200):
        resp = jsonify(resposta_json)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.status_code = status
        return resp

    try:
        data = request.json or {}
        telefone = data.get("telefone")
        conversa_id = data.get("conversa_id")
        resumo = (data.get("resumo") or "").strip()

        if not telefone:
            return com_cors({"erro": "telefone e obrigatorio"}, 400)

        if telefone not in historico:
            historico[telefone] = []

        if resumo:
            historico[telefone].append({
                "role": "system",
                "content": (
                    f"O atendente humano conversou com o cliente e o resultado foi: \"{resumo}\". "
                    "Continue o atendimento a partir daqui, seguindo o FLUXO DE PEDIDO OBRIGATORIO, "
                    "considerando esse resultado (por exemplo, aplicando um desconto combinado, se "
                    "houver). Se o nome do cliente ja tiver sido informado nesta conversa, NAO peca "
                    "de novo."
                )
            })

        transferido[telefone] = False
        mensagens_farmaceutico[telefone] = []
        conversa_ativa_id.pop(telefone, None)

        if conversa_id and SUPABASE_URL and SUPABASE_ANON_KEY:
            headers = {
                "apikey": SUPABASE_ANON_KEY,
                "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
                "Content-Type": "application/json",
            }
            body = {
                "atendimento_encerrado": True,
                "atendimento_encerrado_em": datetime.now(pytz.utc).isoformat(),
            }
            requests.patch(
                f"{SUPABASE_URL}/rest/v1/conversas?id=eq.{conversa_id}",
                json=body, headers=headers, timeout=15
            )

        retomar_atendimento_com_ia(telefone)

        return com_cors({"ok": True})
    except Exception as e:
        print("ERRO ao voltar atendimento para a IA:", e)
        return com_cors({"erro": str(e)}, 500)


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

        # CORRECAO (30/07/2026): antes, "sender_pn" era a primeira opcao pra
        # identificar o numero do cliente - mas o WhatsApp atual pode
        # retornar um sender_pn diferente do numero real da conversa
        # (sistema de identificadores LID), o que fazia a Isabela responder
        # a um numero errado (a mensagem gerada ia pro sender_pn, nao pro
        # chatid de quem realmente estava conversando). Agora priorizamos
        # chatid/wa_chatid, que representam de forma confiavel a conversa
        # 1:1 em si, e usamos sender_pn so como ultimo recurso.
        number = limpar_numero(chat.get("wa_chatid"))
        if not number:
            number = limpar_numero(msg.get("chatid"))
        if not number:
            number = limpar_numero(msg.get("sender_pn"))

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

        if number in aguardando_avaliacao:
            texto_avaliacao = (extrair_texto(msg) or "").strip()
            if texto_avaliacao in ("1", "2", "3", "4", "5"):
                conversa_id = aguardando_avaliacao.pop(number)
                salvar_nota_avaliacao(conversa_id, int(texto_avaliacao))
                mensagem_obrigado = "Muito obrigada pela sua avaliação! Isso nos ajuda muito a melhorar. 💙"
                send(number, mensagem_obrigado)
                return "ok", 200
            # Se a resposta nao for um numero de 1 a 5, deixa cair no fluxo
            # normal abaixo (nao trava o cliente esperando uma nota valida).

        conversa_id_atual = conversa_ativa_id.get(number)
        esta_transferido = bool(number and transferido.get(number))

        if number and not esta_transferido:
            # A memoria pode ter sido limpa por um restart/redeploy do
            # servidor - confirma no banco antes de tratar como conversa nova.
            conversa_ativa_no_banco = buscar_conversa_humana_ativa(number)
            if conversa_ativa_no_banco:
                esta_transferido = True
                transferido[number] = True
                conversa_ativa_id[number] = conversa_ativa_no_banco
                conversa_id_atual = conversa_ativa_no_banco

        if esta_transferido:
            texto_cliente_thread = extrair_texto(msg) or chat.get("wa_lastMessageTextVote")
            if isinstance(texto_cliente_thread, str) and texto_cliente_thread.strip():
                if conversa_id_atual:
                    inserir_mensagem_atendimento(conversa_id_atual, "cliente", texto_cliente_thread.strip())
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

        is_image = (
            msg_type in ("image",) or
            media_type == "image" or
            mimetype.startswith("image")
        )

        print(f"TYPE:{msg_type} MEDIA:{media_type} PTT:{is_ptt} IS_AUDIO:{is_audio} IS_IMAGE:{is_image}")

        if is_image and number in aguardando_receita:
            message_id_completo = msg.get("id", "")
            image_bytes = baixar_midia_uazapi(message_id_completo) if message_id_completo else None

            if image_bytes:
                dados_venda = aguardando_receita.pop(number)
                dados_receita = extrair_dados_receita(image_bytes) or {}
                foto_url = subir_foto_receita(image_bytes, number)
                salvar_receita_pendente(number, dados_venda, dados_receita, foto_url)

                mensagem_confirmacao = (
                    "Recebemos sua receita! Ela sera analisada pelo nosso farmaceutico responsavel, "
                    "e assim que for aprovada, ja providenciamos a entrega. Te aviso por aqui assim que "
                    "tiver novidade! 😊"
                )
                send(number, mensagem_confirmacao)
                registrar_resposta_no_historico(number, mensagem_confirmacao)
                registrar_conversa(number, "[Foto da receita recebida]", mensagem_confirmacao)
                notificar_farmaceutico_receita_pendente(number, dados_venda)
                encerrado[number] = True
            else:
                send(number, "Nao consegui acessar a foto da receita. Pode tentar enviar novamente?")

            return "ok", 200

        text = None

        if is_audio:
            audio_url = extrair_url_midia(msg)
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
        elif is_image:
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

        if number in aguardando_oferta_complementar:
            oferta = aguardando_oferta_complementar.pop(number)
            dados_venda_original = oferta["dados_venda"]
            produto_id_original = oferta["produto_id"]
            complementar = oferta["complementar"]

            aceitou = e_resposta_afirmativa(text)

            unidade_id = escolher_loja_para_produto(produto_id_original) if produto_id_original else None

            quantidade_original = dados_venda_original.get("quantidade", 1)
            valor_unit_original = dados_venda_original.get("valor_unitario", 0)
            valor_total_pedido = round(float(quantidade_original) * float(valor_unit_original), 2)

            registrar_venda(
                number,
                dados_venda_original.get("produto"),
                quantidade_original,
                valor_unit_original,
                unidade_id=unidade_id,
                produto_id=produto_id_original,
            )

            itens_pedido = [{"qtd": int(round(float(quantidade_original))), "produto": dados_venda_original.get("produto")}]

            if aceitou:
                preco_complementar = complementar.get("preco") or 0
                registrar_venda(
                    number,
                    complementar.get("nome"),
                    1,
                    preco_complementar,
                    unidade_id=unidade_id,
                    produto_id=complementar.get("id"),
                )
                itens_pedido.append({"qtd": 1, "produto": complementar.get("nome")})
                valor_total_pedido = round(valor_total_pedido + float(preco_complementar), 2)

            criar_pedido_com_itens(
                number,
                nome_cliente=dados_venda_original.get("nome_cliente"),
                endereco=dados_venda_original.get("endereco"),
                forma_pagamento=dados_venda_original.get("forma_pagamento"),
                itens=itens_pedido,
                valor_total=valor_total_pedido,
                unidade_id=unidade_id,
            )

            mensagem_final = (
                "Seu pedido foi registrado e a entrega ja esta sendo providenciada! "
                "Foi um prazer te atender! 😊\n\n"
                "Que tal deixar uma avaliacao para nos ajudar a melhorar?\n"
                "⭐ Farmacia Saude e Vida: https://search.google.com/local/writereview?placeid=ChIJAQBsTgC5rgARK0oiw3CQOpg\n\n"
                "Obrigada pela preferencia! Volte sempre. 💙"
            )
            send(number, mensagem_final)
            registrar_conversa(number, text, mensagem_final)
            encerrado[number] = True
            return "ok", 200

        # CORRECAO (29/07/2026): antes, essa checagem so rodava quando a
        # conversa JA estava marcada como encerrada (encerrado[number]=True,
        # o que so acontece apos um pedido fechado de verdade). Numa
        # conversa de agradecimento solto (cliente so manda "Ok", "Não
        # obrigado" etc sem nunca ter fechado pedido), esse estado nunca
        # chegava a ser True, e a Isabela ficava gerando uma resposta nova
        # via IA pra cada "Ok" pra sempre, num loop de gentilezas ("Tudo
        # bem!", "Fico a disposicao!"...). Agora a checagem de despedida
        # roda sempre, independente do estado anterior, e silencia+marca
        # como encerrada assim que reconhece esse tipo de mensagem curta.
        if number and e_mensagem_de_despedida(text):
            print(f"[SILENCIO] Mensagem de despedida/reconhecimento curto ignorada para {number}: {text}")
            encerrado[number] = True
            return "ok", 200

        if number and encerrado.get(number):
            encerrado[number] = False

        if number:
            marcar_seguimento_respondido(number)
            ultima_mensagem_cliente[number] = datetime.now(pytz.timezone("America/Sao_Paulo"))
            estagios_enviados[number] = set()

        reply = ask_openai(number, text)
        if reply:
            if "TRANSFERIR_FARMACEUTICO" in reply:
                nome_cliente_transferencia, pergunta_original = extrair_nome_e_pergunta_original(number)
                registrar_nome_conhecido(number, nome_cliente_transferencia)
                pergunta_para_exibir = pergunta_original or text
                transferido[number] = True
                mensagens_farmaceutico[number] = []
                ultimo_cliente_transferido = number
                print(f"CONVERSA TRANSFERIDA PARA FARMACEUTICO: {number}")
                mensagem_transferencia = "Vou te conectar com nosso farmaceutico para te orientar melhor sobre isso, so um momento! 😊"
                send(number, mensagem_transferencia)
                registrar_resposta_no_historico(number, mensagem_transferencia)
                motivo_texto = "Cliente pediu indicacao/sugestao de medicamento"
                if nome_cliente_transferencia:
                    motivo_texto += f" - Nome: {nome_cliente_transferencia}"
                conversa_id_criada = registrar_conversa(
                    number, pergunta_para_exibir, mensagem_transferencia,
                    transferida=True,
                    motivo=motivo_texto,
                    retornar_id=True,
                )
                if conversa_id_criada:
                    conversa_ativa_id[number] = conversa_id_criada

                nome_txt = f"Nome: {nome_cliente_transferencia}\n" if nome_cliente_transferencia else ""
                resumo_para_farmaceutico = (
                    f"📋 Novo atendimento transferido!\n"
                    f"{nome_txt}"
                    f"Cliente: {number}\n"
                    f"Abrir conversa direto com o cliente: https://wa.me/{number}\n"
                    f"Pergunta do cliente: \"{pergunta_para_exibir}\"\n\n"
                    f"Fale diretamente com o cliente pelo link acima. Quando terminar, "
                    f"envie aqui /voltarbot seguido do resumo da orientacao "
                    f"(ex: /voltarbot Recomendei Dipirona 500mg, 1 comprimido a cada 6 horas)."
                )
                send(FARMACEUTICO_TESTE, resumo_para_farmaceutico)
            elif "TRANSFERIR_HUMANO" in reply:
                nome_cliente_transferencia, pergunta_original = extrair_nome_e_pergunta_original(number)
                registrar_nome_conhecido(number, nome_cliente_transferencia)
                pergunta_para_exibir = pergunta_original or text
                transferido[number] = True
                print(f"CONVERSA TRANSFERIDA PARA ATENDENTE HUMANO (fila do painel): {number}")
                mensagem_transferencia = "Vou te conectar com uma de nossas atendentes, so um momento! 😊"
                send(number, mensagem_transferencia)
                registrar_resposta_no_historico(number, mensagem_transferencia)
                motivo_texto = "Cliente pediu desconto"
                if nome_cliente_transferencia:
                    motivo_texto += f" - Nome: {nome_cliente_transferencia}"
                conversa_id_criada = registrar_conversa(
                    number, pergunta_para_exibir, mensagem_transferencia,
                    transferida=True,
                    motivo=motivo_texto,
                    retornar_id=True,
                )
                if conversa_id_criada:
                    conversa_ativa_id[number] = conversa_id_criada
                transferir_com_distribuicao_automatica(number, conversa_id_criada)
            elif "TRANSFERIR_ENCOMENDA" in reply:
                nome_cliente_transferencia, pergunta_original = extrair_nome_e_pergunta_original(number)
                registrar_nome_conhecido(number, nome_cliente_transferencia)
                pergunta_para_exibir = pergunta_original or text
                transferido[number] = True
                print(f"CONVERSA TRANSFERIDA PARA ATENDENTE HUMANO (encomenda, fila do painel): {number}")
                mensagem_transferencia = (
                    "Vou verificar com nossa equipe a possibilidade de encomendar esse item para "
                    "voce, so um momento! 😊"
                )
                send(number, mensagem_transferencia)
                registrar_resposta_no_historico(number, mensagem_transferencia)
                motivo_texto = "Encomenda de medicamento indisponivel"
                if nome_cliente_transferencia:
                    motivo_texto += f" - Nome: {nome_cliente_transferencia}"
                conversa_id_criada = registrar_conversa(
                    number, pergunta_para_exibir, mensagem_transferencia,
                    transferida=True,
                    motivo=motivo_texto,
                    retornar_id=True,
                )
                if conversa_id_criada:
                    conversa_ativa_id[number] = conversa_id_criada
                transferir_com_distribuicao_automatica(number, conversa_id_criada)
            elif "CONSULTAR_ENTREGA" in reply:
                mensagem_status = consultar_status_entrega(number)
                send(number, mensagem_status)
                registrar_resposta_no_historico(number, mensagem_status)
                registrar_conversa(number, text, mensagem_status)
            elif "Foi um prazer te atender" in reply:
                dados_venda = extrair_dados_venda(number)
                itens_pedido_extraidos = produtos_da_venda(dados_venda)

                if dados_venda and algum_item_controlado(itens_pedido_extraidos):
                    # CORRECAO DE SEGURANCA (28/07/2026): antes, so o primeiro
                    # produto do carrinho era checado - um pedido com 2+ itens
                    # (ex: Nimesulida + Amoxicilina) podia fechar sem pedir
                    # receita se o controlado nao fosse o primeiro identificado.
                    # Agora TODO o carrinho fica pendente ate a receita ser
                    # aprovada, mesmo que so 1 dos itens exija receita.
                    aguardando_receita[number] = dados_venda
                    nomes_controlados = [
                        item.get("produto") for item in itens_pedido_extraidos
                        if eh_controlado(item.get("produto"))
                    ]
                    mensagem_receita = (
                        "Para finalizar a compra, preciso que voce me envie uma foto da receita "
                        f"medica de: {', '.join(nomes_controlados)}, por favor! 📋"
                    )
                    send(number, mensagem_receita)
                    registrar_resposta_no_historico(number, mensagem_receita)
                    registrar_conversa(number, text, mensagem_receita)
                else:
                    itens_resolvidos = []
                    for item in itens_pedido_extraidos:
                        produto_id_item = buscar_produto_por_nome(item.get("produto"))
                        itens_resolvidos.append({**item, "produto_id": produto_id_item})

                    produto_id_principal = itens_resolvidos[0]["produto_id"] if itens_resolvidos else None
                    complementar = buscar_produto_complementar(produto_id_principal) if produto_id_principal else None

                    if complementar and complementar.get("nome"):
                        aguardando_oferta_complementar[number] = {
                            "dados_venda": dados_venda,
                            "produto_id": produto_id_principal,
                            "complementar": complementar,
                        }
                        preco_txt = ""
                        if complementar.get("preco"):
                            preco_formatado = f"{complementar['preco']:.2f}".replace(".", ",")
                            preco_txt = f" por apenas R$ {preco_formatado}"
                        mensagem_oferta = (
                            f"Antes de finalizar, que tal aproveitar e levar também "
                            f"{complementar['nome']}{preco_txt}? É um ótimo complemento "
                            f"para o que você está comprando! Posso incluir? 😊"
                        )
                        send(number, mensagem_oferta)
                        registrar_resposta_no_historico(number, mensagem_oferta)
                        registrar_conversa(number, text, mensagem_oferta)
                    else:
                        send(number, reply)
                        registrar_conversa(number, text, reply)
                        encerrado[number] = True
                        print(f"CONVERSA ENCERRADA (aguardando so despedidas): {number}")
                        if itens_resolvidos:
                            itens_pedido = []
                            valor_total_pedido = 0.0
                            unidade_id_escolhida = None
                            for item in itens_resolvidos:
                                unidade_id_item = (
                                    escolher_loja_para_produto(item["produto_id"])
                                    if item["produto_id"] else None
                                )
                                if unidade_id_escolhida is None:
                                    unidade_id_escolhida = unidade_id_item
                                qtd = item.get("quantidade", 1)
                                valor_unit = item.get("valor_unitario", 0)
                                registrar_venda(
                                    number,
                                    item.get("produto"),
                                    qtd,
                                    valor_unit,
                                    unidade_id=unidade_id_item,
                                    produto_id=item["produto_id"],
                                )
                                itens_pedido.append({
                                    "qtd": int(round(float(qtd))),
                                    "produto": item.get("produto"),
                                })
                                valor_total_pedido += float(qtd) * float(valor_unit)

                            criar_pedido_com_itens(
                                number,
                                nome_cliente=dados_venda.get("nome_cliente"),
                                endereco=dados_venda.get("endereco"),
                                forma_pagamento=dados_venda.get("forma_pagamento"),
                                itens=itens_pedido,
                                valor_total=round(valor_total_pedido, 2),
                                unidade_id=unidade_id_escolhida,
                            )
            else:
                send(number, reply)
                registrar_conversa(number, text, reply)

    except Exception as e:
        print("ERROR:", e)

    return "ok", 200


def registrar_resposta_no_historico(number, texto):
    """Registra na memoria da propria IA (historico[number]) uma mensagem
    que foi enviada pro cliente por fora do ask_openai() - por exemplo,
    o pedido de foto da receita, a confirmacao de recebimento dela, a
    oferta de produto complementar, ou o status de entrega.

    Sem isso, a IA "esquece" que essas mensagens foram enviadas de
    verdade: ela so lembra do ultimo texto que ELA MESMA gerou via
    OpenAI (normalmente a mensagem de fechamento generica), e ao
    responder a proxima mensagem do cliente, tende a gerar essa mesma
    mensagem de fechamento de novo - o que faz o codigo reiniciar todo
    o fluxo (por exemplo, pedir a foto da receita outra vez, mesmo ja
    tendo recebido)."""
    if number not in historico:
        historico[number] = []
    historico[number].append({"role": "assistant", "content": texto})


def buscar_ultimo_pedido_cliente(number):
    """Busca o pedido mais recente desse telefone (nome/endereco/forma de
    pagamento), para a Isabela poder confirmar esses dados em vez de pedir
    tudo de novo do zero a cada novo pedido - decisao de reuniao (29/07/2026),
    motivada pelo caso de clientes com varios cadastros de endereco na Rede
    Soma: usar o endereco/dados da ULTIMA conversa/pedido, nao o primeiro
    cadastro. Retorna None se nao houver pedido anterior ou em caso de erro."""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return None
    try:
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        }
        params = f"cliente_telefone=eq.{number}&order=criado_em.desc&limit=1&select=nome_cliente,endereco,forma_pagamento"
        r = requests.get(f"{SUPABASE_URL}/rest/v1/pedidos?{params}", headers=headers, timeout=15)
        dados = r.json()
        if not dados:
            return None
        pedido = dados[0]
        if not pedido.get("nome_cliente") and not pedido.get("endereco"):
            return None
        return pedido
    except Exception as e:
        print("ERRO ao buscar ultimo pedido do cliente:", e)
        return None


def ask_openai(number, text):
    eh_conversa_nova = number not in historico
    ultimo_pedido = None
    if eh_conversa_nova:
        historico[number] = []

        # So busca o pedido anterior na primeira vez que esse numero aparece
        # nesta sessao do processo (evita ficar repetindo a consulta e
        # repetindo a mensagem de sistema a cada mensagem da conversa).
        ultimo_pedido = buscar_ultimo_pedido_cliente(number)
        if ultimo_pedido:
            partes_conhecidas = []
            if ultimo_pedido.get("nome_cliente"):
                partes_conhecidas.append(f"Nome: {ultimo_pedido['nome_cliente']}")
            if ultimo_pedido.get("endereco"):
                partes_conhecidas.append(f"Endereco: {ultimo_pedido['endereco']}")
            if ultimo_pedido.get("forma_pagamento"):
                partes_conhecidas.append(f"Forma de pagamento usada da ultima vez: {ultimo_pedido['forma_pagamento']}")
            if partes_conhecidas:
                historico[number].append({
                    "role": "system",
                    "content": (
                        "Este cliente ja comprou antes. Dados do pedido mais recente dele: "
                        + "; ".join(partes_conhecidas) + ". "
                        "Quando ele for fechar um novo pedido, NAO peca essas informacoes do zero - "
                        "confirme com ele se nome, endereco e forma de pagamento continuam os mesmos "
                        "(pode perguntar de forma direta, tipo 'posso confirmar a entrega no mesmo "
                        "endereco de sempre?'), e so peca de novo o que ele disser que mudou ou o que "
                        "estiver faltando (por exemplo, o CPF, que nao fica salvo)."
                    )
                })

    historico[number].append({"role": "user", "content": text})

    historico[number] = [
        m for m in historico[number]
        if isinstance(m.get("content"), str) and m["content"].strip()
    ]

    saudacao = get_saudacao()

    # CORRECAO (29/07/2026): antes checava len(historico[number]) == 1 para
    # saber se era a primeira mensagem - isso quebrava para clientes
    # conhecidos, porque agora a primeira "mensagem" da conversa pode vir
    # acompanhada de uma mensagem de sistema com os dados do pedido
    # anterior (ver buscar_ultimo_pedido_cliente), deixando o historico com
    # 2 itens em vez de 1 logo de cara. Usamos eh_conversa_nova, que reflete
    # corretamente se esta e a primeira vez que esse numero aparece nesta
    # sessao, independente de quantas mensagens de sistema foram injetadas.
    if eh_conversa_nova:
        # CORRECAO (29/07/2026): quando ja sabemos o nome do cliente (pedido
        # anterior encontrado), a saudacao completa (Bom dia/Boa tarde/Boa
        # noite) precisa continuar aparecendo, mesmo cumprimentando pelo
        # nome - antes a IA as vezes pulava direto pro nome ("Ola, Fulano!")
        # sem a saudacao, quando esse contexto de cliente conhecido entrava
        # em jogo.
        nome_conhecido = None
        if ultimo_pedido and ultimo_pedido.get("nome_cliente"):
            nome_conhecido = ultimo_pedido["nome_cliente"].strip().split(" ")[0]

        if nome_conhecido:
            instrucao = (
                SYSTEM_PROMPT
                + f" Esta e a PRIMEIRA mensagem. Voce DEVE responder EXATAMENTE com:"
                + f" {saudacao}, {nome_conhecido}! Sou a Isabela, atendente virtual da Farmacia Saude e Vida."
                + f" Como posso te ajudar hoje? e nada mais."
            )
        else:
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


threading.Thread(target=verificar_seguimentos, daemon=True).start()
threading.Thread(target=verificar_lembretes_recompra, daemon=True).start()
threading.Thread(target=verificar_reaberturas_agendadas, daemon=True).start()
threading.Thread(target=verificar_sincronizacao_estoque, daemon=True).start()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))