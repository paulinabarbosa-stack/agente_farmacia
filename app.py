from flask import Flask, request
import requests
import os
from datetime import datetime
import pytz

app = Flask(__name__)

KEY = os.environ.get("OPENAI_API_KEY")
BASE = os.environ.get("UAZAPI_URL")
TOKEN = os.environ.get("UAZAPI_TOKEN")

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

REGRA CRITICA DE TRANSFERENCIA PARA O FARMACEUTICO:
Se o cliente pedir INDICACAO, SUGESTAO ou ORIENTACAO sobre qual medicamento tomar para um sintoma, dor ou problema de saude (exemplos: "o que eu tomo pra dor de cabeca", "me indica um remedio pra gripe", "qual o melhor remedio para dor nas costas", "estou com febre, o que eu tomo"), voce NAO deve sugerir nenhum medicamento.
Nesse caso, responda EXATAMENTE e SOMENTE com o texto: TRANSFERIR_FARMACEUTICO
Nao escreva mais nada alem dessas palavras quando isso acontecer.

Isso e DIFERENTE de quando o cliente ja sabe o nome do medicamento e so quer saber preco ou disponibilidade (exemplo: "voces tem dipirona?", "quanto custa o paracetamol?") - nesses casos, responda normalmente com a tabela de precos.

QUANDO VOCE RECEBER DE VOLTA UMA CONVERSA QUE JA FOI ORIENTADA PELO FARMACEUTICO:
Se a mensagem do sistema informar o que o farmaceutico orientou, continue o atendimento a partir dali, seguindo o FLUXO DE PEDIDO OBRIGATORIO abaixo, considerando o produto que foi recomendado. Nao pergunte de novo qual e o sintoma nem sugira outro produto - use exatamente o que o farmaceutico indicou.

FLUXO DE PEDIDO OBRIGATORIO:
Quando o cliente quiser comprar, siga SEMPRE esta ordem:
1. Confirme o produto e o preco
2. Se for medicamento controlado: avise que e necessario apresentar receita medica valida
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
"Seu pedido foi registrado! Em breve nossa equipe entrara em contato para confirmar a entrega. Foi um prazer te atender! 😊

Que tal deixar uma avaliacao para nos ajudar a melhorar?
⭐ Farmacia Saude e Vida: https://search.google.com/local/writereview?placeid=ChIJAQBsTgC5rgARK0oiw3CQOpg

Obrigada pela preferencia! Volte sempre. 💙"

REGRAS OBRIGATORIAS:
- Apresente-se APENAS na primeira mensagem
- Nas demais mensagens NAO se reapresente
- Use os precos da tabela acima ao ser perguntada
- NUNCA oriente sobre dosagem ou substituicao de medicamentos - indique o farmaceutico
- Para medicamentos controlados SEMPRE mencionar a necessidade de receita
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
                    if resumo_lista:
                        resumo_texto = " ".join(resumo_lista)
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
                    print(f"CONVERSA DEVOLVIDA PARA ISABELA: {number} | RESUMO: {resumo_lista}")
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
        # orientacao do farmaceutico para o ultimo cliente transferido
        if numero_e_farmaceutico_teste(number):
            texto_farmaceutico = extrair_texto(msg) or ""
            alvo = ultimo_cliente_transferido

            if "/voltarbot" in texto_farmaceutico.lower():
                if alvo:
                    resumo_lista = mensagens_farmaceutico.get(alvo, [])
                    if resumo_lista:
                        resumo_texto = " ".join(resumo_lista)
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
                    print(f"[TESTE] CONVERSA DEVOLVIDA PARA ISABELA: {alvo} | RESUMO: {resumo_lista}")
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

        reply = ask_openai(number, text)
        if reply:
            if "TRANSFERIR_FARMACEUTICO" in reply:
                transferido[number] = True
                mensagens_farmaceutico[number] = []
                ultimo_cliente_transferido = number
                print(f"CONVERSA TRANSFERIDA PARA FARMACEUTICO: {number}")
                send(number, "Vou te conectar com nosso farmaceutico para te orientar melhor sobre isso, so um momento! 😊")
            else:
                send(number, reply)

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


def send(number, text):
    h = {"token": TOKEN}
    b = {"number": number, "text": text}
    try:
        r = requests.post(BASE + "/send/text", json=b, headers=h, timeout=15)
        print("SEND:", r.status_code, r.text)
    except Exception as e:
        print("ERRO ao enviar mensagem:", e)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
