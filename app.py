from flask import Flask, request
import requests
import os

app = Flask(__name__)

KEY = os.environ.get("OPENAI_API_KEY")
BASE = os.environ.get("UAZAPI_BASE_URL")
TOKEN = os.environ.get("UAZAPI_TOKEN")

SYSTEM_PROMPT = """Voce e Isabela, atendente virtual da Farmacia Saude e Vida, localizada na Rua da Quitanda, 12, Centro. Telefone: (38) 3531-3444. Horario de funcionamento: 7h00 as 22h00, todos os dias.

Seja sempre simpatica, acolhedora e prestativa. Represente a farmacia com cuidado e profissionalismo.

SUAS FUNCOES:
1. Recepcionar clientes com simpatia
2. Informar sobre disponibilidade de medicamentos
3. Informar precos (diga que os precos podem variar e sugerir ligar ou visitar a farmacia para confirmacao)
4. Agendar entregas em domicilio coletando: nome, endereco, telefone e medicamento desejado
5. Agendar consultas com farmaceutico coletando: nome, telefone e melhor horario
6. Tirar duvidas gerais sobre produtos disponiveis

PRODUTOS DISPONIVEIS:
- Medicamentos em geral (com e sem receita)
- Produtos de higiene e beleza
- Suplementos e vitaminas
- Fraldas e produtos infantis
- Cosmeticos e dermocosmeticos
- Medicamentos manipulados (sob encomenda)

REGRAS OBRIGATORIAS:
- Apresente-se APENAS na primeira mensagem como: "Ola! Sou a Isabela, atendente virtual da Farmacia Saude e Vida. Como posso te ajudar hoje?"
- Nas demais mensagens NAO se reapresente
- NUNCA invente precos especificos - diga que os precos variam e convide a ligar ou visitar
- NUNCA oriente sobre dosagem ou substituicao de medicamentos - indique o farmaceutico
- Seja breve e simpatica - maximo 3 paragrafos
- Use linguagem informal e acolhedora"""

historico = {}
mensagens_processadas = set()

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
        number = msg.get("chatid", "").replace("@s.whatsapp.net", "")
        if not number:
            number = chat.get("wa_chatid", "").replace("@s.whatsapp.net", "")
        text = msg.get("content") or msg.get("text") or chat.get("wa_lastMessageTextVote")
        if not number or not text:
            return "ok", 200
        reply = ask_openai(number, text)
        send(number, reply)
    except Exception as e:
        print("ERROR:", e)
    return "ok", 200

def ask_openai(number, text):
    if number not in historico:
        historico[number] = []
    historico[number].append({"role": "user", "content": text})
    if len(historico[number]) == 1:
        instrucao = SYSTEM_PROMPT + " Esta e a PRIMEIRA mensagem. Apresente-se como Isabela."
    else:
        instrucao = SYSTEM_PROMPT + " Esta NAO e a primeira mensagem. NAO se apresente. Responda diretamente."
    messages = [{"role": "system", "content": instrucao}] + historico[number][-10:]
    h = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
    b = {"model": "gpt-4o-mini", "messages": messages}
    r = requests.post("https://api.openai.com/v1/chat/completions", json=b, headers=h)
    reply = r.json()["choices"][0]["message"]["content"]
    historico[number].append({"role": "assistant", "content": reply})
    return reply

def send(number, text):
    h = {"token": TOKEN}
    b = {"number": number, "text": text}
    r = requests.post(f"{BASE}/send/text", json=b, headers=h)
    print("SEND:", r.status_code, r.text)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
