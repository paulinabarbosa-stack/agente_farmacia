from flask import Flask, request
import requests
import os
import base64
from datetime import datetime
import pytz
from google import genai
from google.genai import types

app = Flask(__name__)

GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
BASE = os.environ.get("UAZAPI_URL")
TOKEN = os.environ.get("UAZAPI_TOKEN")

client = genai.Client(api_key=GEMINI_KEY)

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
7. Se o cliente enviar um audio, transcreva e responda normalmente como se fosse texto

FLUXO DE PEDIDO OBRIGATORIO:
Quando o cliente quiser comprar, siga SEMPRE esta ordem:
1. Confirme o produto e o preco
2. Se for medicamento controlado: avise que e necessario apresentar receita medica valida
3. Pergunte: "Para finalizar seu pedido, preciso de algumas informacoes:"
4. Colete: Nome completo
5. Colete: Endereco completo (rua, numero, bairro)
6. Colete: CPF
7. Pergunte: "Qual sera a forma de pagamento? Aceitamos Pix, cartao de credito, cartao de debito ou dinheiro."
8. Confirme o resumo do pedido com todos os dados e valor total
9. Finalize com a mensagem de encerramento abaixo

MENSAGEM DE ENCERRAMENTO OBRIGATORIA:
Sempre que o atendimento for encerrado (pedido finalizado, duvida resolvida ou cliente se despedir), envie EXATAMENTE:
"Seu pedido foi registrado! Em breve nossa equipe entrara em contato para confirmar a entrega. Foi um prazer te atender! 😊

Que tal deixar uma avaliacao para nos ajudar a melhorar?
⭐ Farmacia Saude e Vida: https://search.google.com/local/writereview?placeid=ChIJAQBsTgC5rgARK0oiw3CQOpg

Obrigada pela preferencia! Volte sempre. 💙"

REGRAS OBRIGATORIAS:
- Nas demais mensagens NAO se reapresente
- Use os precos da tabela acima ao ser perguntada
- NUNCA oriente sobre dosagem ou substituicao de medicamentos - indique o farmaceutico
- Para medicamentos controlados SEMPRE mencionar a necessidade de receita
- Seja breve e simpatica - maximo 3 paragrafos
- Use linguagem informal e acolhedora"""

historico = {}
mensagens_processadas = set()


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
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            return r.content
    except Exception as e:
        print("ERRO ao baixar audio:", e)
    return None


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    try:
        msg = data.get("message", {})
        chat = data.get("chat", {})

        if msg.get("wasSentByApi") or msg.get("fromMe"):
            return "ok", 200

        message_id = msg.get("id", "")
        if message_id in mensagens_processadas:
            return "ok", 200
        if message_id:
            mensagens_processadas.add(message_id)
            if len(mensagens_processadas) > 10000:
                mensagens_processadas.clear()

        number = msg.get("chatid", "").replace("@s.whatsapp.net", "")
        if not number:
            number = chat.get("wa_chatid", "").replace("@s.whatsapp.net", "")

        msg_type = msg.get("type", "")
        audio_bytes = None
        text = None

        if msg_type in ("audio", "ptt"):
            audio_url = msg.get("content") or msg.get("url") or msg.get("mediaUrl")
            if audio_url:
                audio_bytes = baixar_audio(audio_url)
                text = "[audio]"
            else:
                return "ok", 200
        else:
            text = msg.get("content") or msg.get("text") or chat.get("wa_lastMessageTextVote")

        if not number or (not text and not audio_bytes):
            return "ok", 200

        if text and not isinstance(text, str):
            return "ok", 200

        if text:
            text = text.strip()

        reply = ask_gemini(number, text, audio_bytes)
        if reply:
            send(number, reply)

    except Exception as e:
        print("ERROR:", e)

    return "ok", 200


def ask_gemini(number, text, audio_bytes=None):
    if number not in historico:
        historico[number] = []

    is_primeira = len(historico[number]) == 0
    saudacao = get_saudacao()

    # Montar histórico no formato do google-genai
    gemini_history = []
    for m in historico[number][-10:]:
        role = "user" if m["role"] == "user" else "model"
        gemini_history.append(types.Content(role=role, parts=[types.Part(text=m["content"])]))

    # Montar mensagem atual
    parts = []
    if audio_bytes:
        parts.append(types.Part(inline_data=types.Blob(mime_type="audio/ogg", data=audio_bytes)))
        instrucao = "Transcreva e responda ao audio como Isabela."
        if is_primeira:
            instrucao += f" Comece com '{saudacao}! Sou a Isabela, atendente virtual da Farmacia Saude e Vida. Como posso te ajudar hoje?'"
        parts.append(types.Part(text=instrucao))
    else:
        msg_text = text
        if is_primeira:
            msg_text += f"\n\n[INSTRUCAO: Esta e a PRIMEIRA mensagem. Responda EXATAMENTE com: '{saudacao}! Sou a Isabela, atendente virtual da Farmacia Saude e Vida. Como posso te ajudar hoje?' e nada mais.]"
        parts.append(types.Part(text=msg_text))

    gemini_history.append(types.Content(role="user", parts=parts))

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=gemini_history,
            config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT)
        )
        reply = response.text

        historico[number].append({"role": "user", "content": text or "[audio]"})
        historico[number].append({"role": "assistant", "content": reply})

        return reply

    except Exception as e:
        print("ERRO Gemini:", e)
        return "Desculpe, tive um problema interno. Pode repetir sua mensagem?"


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
