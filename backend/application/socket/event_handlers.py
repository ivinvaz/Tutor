from flask import request
from flask_socketio import SocketIO, emit
from application.config.vector_database import collection
from application.services.service_chat import criar_chat
from application.services.service_mensagem import criar_mensagem, buscar_ultimas_n_mensagens
from application.libs.mistral_handler import contar_tokens_mensagens, formatar_mensagens_para_texto, formatar_mensagem_salva, formatar_mensagens_recentes, formatar_mensagens_tokenizacao
from application.constants import LLM_UUID

from Impl.Prompt import CriarPrompt
from Impl.CriarNomeChat import GerarNomeDoChat
from Impl.ResumoChat import CriarResumoDasMensagensDoChat
from Impl.BuscaMaterialSem import RealizarBuscaNoMaterialSemanticoDaMateria
from Impl.Embedding import GerarEmbeddingDeMaterial, GerarEmbeddingDeMensagem

import uuid
import ollama

socketio = SocketIO(cors_allowed_origins="*", async_mode="eventlet")

client = ollama.Client(host='http://localhost:11434')

pendentes = {}
materiais = {}
resumo_local = {}

@socketio.on("connect")
def handle_connect():
    emit("connection-confirmation", {"data": "Conexão estabelecida"})


@socketio.on('abrindo_novo_chat')
def handle_abrir_novo_chat(data: dict[str,str]):
    """
    Função responsável por lidar com a criação de um novo chat

    Espera receber:
        - `aluno_id`: o ID do usuário que enviou a mensagem
        - `materia_id`: o ID da matéria selecionada para o chat
        - `mensagem`: o conteúdo da mensagem 

        1 - criar nome do novo chat
        2 - criar um novo chat no banco
        3 - buscar os materiais da matéria no banco(se não existirem localmente)
        4 - criar os embeddings dos materiais da matéria(se não existirem localmente)
    """
    sid = request.sid

    aluno_id = data['aluno_id']
    materia_id = data['materia_id']
    mensagem = data['mensagem']

    # 1 - criar o nome do novo chat
    nome_chat = GerarNomeDoChat(mensagem)

    # 2 - criar um novo chat no banco
    chat = criar_chat(aluno_id, nome_chat)
    print(f"Chat criado:\n{chat}")

    # 3 - busca os materiais da matéria no banco
    if materia_id not in materiais:
        arquivos = 'query no banco de dados para verificar a existência dos arquivos'

        # 4 - criar os embeddings dos materiais da matéria
        arquivos_embedded = GerarEmbeddingDeMaterial(arquivos)

        materiais[materia_id] = {
            'arquivos':arquivos,
            'arquivos_embedded':arquivos_embedded
        }        

    socketio.emit("novo_chat", chat, to=sid)
    socketio.sleep(0)

@socketio.on('abrindo_chat')
def handle_abrir_chat(data: dict[str,str]):
    """
    Função responsável por lidar com a abertura de um chat existente

    Espera receber:
        - `aluno_id`: o ID do usuário que enviou a mensagem
        - `materia_id`: o ID da matéria selecionada para o chat

        1 - buscar os materiais da matéria no banco(se não existirem localmente)
        2 - criar os embeddings dos materiais da matéria(se não existirem localmente)
    """
    sid = request.sid

    aluno_id = data['aluno_id']
    materia_id = data['materia_id']

    # 1 - busca os materiais da matéria no banco
    if materia_id not in materiais:
        arquivos = 'query no banco de dados para verificar a existência dos arquivos'

        # 2 - criar os embeddings dos materiais da matéria
        arquivos_embedded = GerarEmbeddingDeMaterial(arquivos)

        materiais[materia_id] = {
            'arquivos':arquivos,
            'arquivos_embedded':arquivos_embedded
        }        

    chat = 'query que busca o chat no banco'

    socketio.emit("novo_chat", chat, to=sid)
    socketio.sleep(0)

@socketio.on('nova_mensagem')
def handle_nova_mensagem(data: dict[str, str]):
    """
    Função responsável por lidar com a criação de um novo chat

    Espera receber:
        - `aluno_id`: o ID do usuário que enviou a mensagem
        - `materia_id`: o ID da matéria selecionada para o chat
        - `chat_id`: o ID do chat onde a mensagem foi enviada
        - `mensagem`: o conteúdo da mensagem 

        1 - busca as informações do aluno e salva localmente
        2 - salva a mensagem no banco de dados
        3 - adiciona a mensagem ao resumo local
        4 - cria o embedding da mensagem
        5 - verifica se a mensagem tem alguma similaridade com os embeddings da matéria
        6 - cria e envia o promt
        7 - salva a resposta da llm no banco de dados
        8 - envia a resposta
    """
    
    sid = request.sid
    
    aluno_id = data['aluno_id']
    chat_id = data['chat_id']
    materia_id = data['materia_id']
    mensagem_sent = data['mensagem']

    # 1 - busca as informações do aluno e salva localmente
    nome = 'buscar o nome do aluno no banco pelo id'
    materia = 'buscar o nome da materia no banco pelo id'

    # 2 - salva a mensagem no banco de dados
    mensagem = criar_mensagem(chat_id, aluno_id, mensagem_sent)

    # 3 - adiciona a mensagem ao resumo local
    if chat_id not in resumo_local:
        resumo_local[chat_id]['resumo'] = mensagem_sent
        resumo_local[chat_id]['iteracao'] = 1
    else:
        if resumo_local[chat_id]['iteracao'] >= 7: 
            resumo_local[chat_id]['resumo'] = CriarResumoDasMensagensDoChat(resumo_local[chat_id],mensagem)
            resumo_local[chat_id]['iteracao'] = 0
        else:
            resumo_local[chat_id]['resumo'] = f"{resumo_local[chat_id]['resumo']}\n{mensagem}"
            resumo_local[chat_id]['iteracao'] = resumo_local[chat_id]['iteracao'] + 1 



    # 4 - cria o embedding da mensagem
    mensagem_emb = GerarEmbeddingDeMensagem(mensagem)

    # 5 - verifica se a mensagem tem alguma similaridade com os embeddings da matéria
    documentos = RealizarBuscaNoMaterialSemanticoDaMateria(materiais[materia_id]['arquivos_embedded'],mensagem_emb)

    # 6 - cria e envia o promt
    prompt = CriarPrompt(nome,materia,documentos,resumo_local[chat_id],mensagem_sent)

    resposta = client.generate(
        model="mistral",
        prompt=prompt,
        stream=False,
        options={
            'num_predict': 512,
            'temperature': 0.7,
        }
    )

    # 7 - salva a resposta da llm no banco de dados
    mensagem_llm = criar_mensagem(chat['id'], LLM_UUID, resposta)

    # 8 - envia a resposta
    socketio.emit("resposta", mensagem_llm, to=sid)
    socketio.sleep(0)