import socket
import threading
import os
from queue import Queue, Empty

# constantes gerais
HOST = '0.0.0.0'
PORT = 7891
BUFFER_SIZE = 2048
CHUNK_SIZE = 1000 #1kb exigidos
CLIENT_SESSION_TIMEOUT = 120
USUARIOS_CADASTRADOS = {"daniel": "senha123", "aluno": "ifmg"}
clientes_ativos = {} 
lock = threading.Lock()

# funcoes de comunicacao confiaveis
def enviar_confiavel(sock, fila_acks, mensagem_bytes, endereco_cliente, id_pacote):
    #Funcao que de fato envia a mensagem ja partida para o cliente
    max_tentativas = 5
    for _ in range(max_tentativas):
        try:
            sock.sendto(mensagem_bytes, endereco_cliente)
            ack_recebido = fila_acks.get(timeout=2.0) 
            if ack_recebido == f"ACK:{id_pacote}":
                return True
        except Empty: #caso nao tenha nada na fila de acks
            print(f"[{endereco_cliente}] Timeout esperando ACK para pacote {id_pacote}. Retransmitindo...")
            continue
    return False

def enviar_resposta_em_partes(sock, fila_acks, resposta_str, endereco_cliente, id_comando):
    #essa funcao serve para impedir arquivos maiores que 1kb
    resposta_bytes = resposta_str.encode('utf-8') #converte pra bytes
    id_pacote = id_comando
    offset = 0
    if not resposta_bytes: #se a resposta tiver vazia, entao terminou
        pacote = f"{id_pacote}:END:".encode('utf-8')
        return enviar_confiavel(sock, fila_acks, pacote, endereco_cliente, id_pacote)
    
    while offset < len(resposta_bytes): 
        chunk = resposta_bytes[offset:(offset + CHUNK_SIZE)]
        #verifica se os bytes da variavel resposta sao maiores que 1kb
        tipo = 'END' if (offset + len(chunk)) >= len(resposta_bytes) else 'DATA' 

        pacote = f"{id_pacote}:{tipo}:".encode('utf-8') + chunk
        if not enviar_confiavel(sock, fila_acks, pacote, endereco_cliente, id_pacote):
            print(f"[{endereco_cliente}] Falha crítica ao enviar resposta.")
            return False
        offset += len(chunk) #incrementando para o ponto incial
        id_pacote = 1 - id_pacote
    return True

def enviar_arquivo_confiavel(sock, fila_acks, nome_arquivo, dir_base, endereco_cliente, id_comando):
    #funcao que envia arquivo para o cliente (comando get do cliente)
    caminho_completo = os.path.join(dir_base, nome_arquivo)
    if not os.path.isfile(caminho_completo):
        return enviar_resposta_em_partes(sock, fila_acks, "ERRO: Arquivo não encontrado no servidor.", endereco_cliente, id_comando)

    with open(caminho_completo, 'rb') as f:
        id_pacote = id_comando
        while True:
            chunk = f.read(CHUNK_SIZE)
            tipo = 'DATA' if chunk else 'END' #verifica se o chunk tá vazio
            pacote = f"{id_pacote}:{tipo}:".encode('utf-8') + chunk #pacote com o arquivo (chunk)
            
            if not enviar_confiavel(sock, fila_acks, pacote, endereco_cliente, id_pacote):
                print(f"[{endereco_cliente}] Falha ao enviar chunk do 'get'.")
                return False
            
            if not chunk: break #se chunk esta vazio sai do looping
            id_pacote = 1 - id_pacote
    return True

def receber_arquivo_confiavel(sock, fila_comandos, fila_acks, nome_arquivo, dir_base, endereco_cliente, id_comando):
    #codigo para receber arquivo (comando put do cliente)
    caminho_completo = os.path.join(dir_base, nome_arquivo)
    id_pacote_esperado = id_comando
    try:
        with open(caminho_completo, 'wb') as f:
            while True: #looping para receber pacotes do arquivo em partes
                pacote_bytes = fila_comandos.get(timeout=15.0)
                id_recebido, tipo, dados = pacote_bytes.split(b':', 2)
                id_recebido = int(id_recebido.decode())

                if id_recebido == id_pacote_esperado:
                    sock.sendto(f"ACK:{id_recebido}".encode(), endereco_cliente) #envia ack de resposta
                    if tipo == b'END': #verifica se é a ultima parte do arquivo a ser escrito
                        if dados: f.write(dados)
                        return "OK: Arquivo salvo com sucesso."
                    f.write(dados)
                    id_pacote_esperado = 1 - id_pacote_esperado
                else:
                    sock.sendto(f"ACK:{1 - id_pacote_esperado}".encode(), endereco_cliente) #nao recebeu ack esperado
    except Empty:
        if os.path.exists(caminho_completo): os.remove(caminho_completo)
        return "ERRO: Timeout. O cliente parou de enviar o arquivo."
    except Exception as e:
        return f"ERRO: {e}"

# Lógica da thread do cliente
def processar_comando(mensagem_bytes, estado_cliente):
    sock = estado_cliente['socket']
    fila_comandos = estado_cliente['fila_comandos']
    fila_acks = estado_cliente['fila_acks']
    endereco_cliente = estado_cliente['endereco']
    
    id_pacote, comando_completo = mensagem_bytes.decode('utf-8').split(':', 1)
    id_pacote = int(id_pacote)  #converte pra int pra poder comparar

    if id_pacote != estado_cliente['id_esperado']: #condicional para duplicatas
        sock.sendto(f"ACK:{id_pacote}".encode('utf-8'), endereco_cliente)
        return False

    print(f"[{endereco_cliente}] Processando (ID={id_pacote}): '{comando_completo}'") #comeca a processar o comando
    partes_comando = comando_completo.split()
    comando = partes_comando[0].lower()
    
    if not estado_cliente['logado'] and comando != 'login':
        return enviar_resposta_em_partes(sock, fila_acks, "ERRO: Acesso negado.", endereco_cliente, id_pacote)

    # Logica completa de comandos
    if comando == 'get':
        if len(partes_comando) > 1:
            return enviar_arquivo_confiavel(sock, fila_acks, partes_comando[1], estado_cliente['dir_atual'], endereco_cliente, id_pacote)
        else:
            return enviar_resposta_em_partes(sock, fila_acks, "ERRO: 'get' requer um nome de arquivo.", endereco_cliente, id_pacote)

    elif comando == 'put':
        if len(partes_comando) > 1:
            sock.sendto(f"ACK:{id_pacote}".encode(), endereco_cliente)
            resposta_str = receber_arquivo_confiavel(sock, fila_comandos, fila_acks, partes_comando[1], estado_cliente['dir_atual'], endereco_cliente, id_pacote)
            return enviar_resposta_em_partes(sock, fila_acks, resposta_str, endereco_cliente, id_pacote)
        else:
            return enviar_resposta_em_partes(sock, fila_acks, "ERRO: 'put' requer um nome de arquivo.", endereco_cliente, id_pacote)
    
    elif comando == 'login':
        #verifica se usuario esta cadastrado e se senha eh correta.
        if len(partes_comando) >= 3 and USUARIOS_CADASTRADOS.get(partes_comando[1]) == partes_comando[2]: 
            estado_cliente['logado'] = True #cliente passa a estar logado
            resposta_str = "OK: Login bem-sucedido."
        else:
            resposta_str = "ERRO: Usuário ou senha inválidos."
        return enviar_resposta_em_partes(sock, fila_acks, resposta_str, endereco_cliente, id_pacote)
    
    elif comando == 'ls':
        #mescla todas as strings retornadas pelo listdir
        resposta_str = "\n".join(os.listdir(estado_cliente['dir_atual'])) or "Diretório vazio."
        return enviar_resposta_em_partes(sock, fila_acks, resposta_str, endereco_cliente, id_pacote)
    
    elif comando == 'cd':
        if len(partes_comando) > 1:
            nome_dir = ' '.join(partes_comando[1:]) #separando nome do dietorio
            novo_dir = os.path.abspath(os.path.join(estado_cliente['dir_atual'], nome_dir))
            if os.path.isdir(novo_dir): #se esse diretorio exitir
                estado_cliente['dir_atual'] = novo_dir #mudando diretorio do cliente
                resposta_str = f"OK: Diretório alterado para {estado_cliente['dir_atual']}"
            else:
                resposta_str = "ERRO: Diretório não encontrado."
        else:
            resposta_str = "ERRO: 'cd' requer um nome de pasta."
        return enviar_resposta_em_partes(sock, fila_acks, resposta_str, endereco_cliente, id_pacote)
    
    elif comando == 'cd..':
        estado_cliente['dir_atual'] = os.path.abspath(os.path.join(estado_cliente['dir_atual'], '..'))
        resposta_str = f"OK: Diretório alterado para {estado_cliente['dir_atual']}"
        return enviar_resposta_em_partes(sock, fila_acks, resposta_str, endereco_cliente, id_pacote)
    
    elif comando == 'mkdir':
        if len(partes_comando) > 1:
            nome_dir = ' '.join(partes_comando[1:])
            try:
                os.mkdir(os.path.join(estado_cliente['dir_atual'], nome_dir))
                resposta_str = f"OK: Diretório '{nome_dir}' criado."
            except FileExistsError:
                resposta_str = "ERRO: Diretório já existe."
            except Exception as e:
                resposta_str = f"ERRO: {e}"
        else:
            resposta_str = "ERRO: 'mkdir' requer um nome de pasta."
        return enviar_resposta_em_partes(sock, fila_acks, resposta_str, endereco_cliente, id_pacote)
    
    elif comando == 'rmdir':
        if len(partes_comando) > 1:
            nome_dir = ' '.join(partes_comando[1:])
            try:
                os.rmdir(os.path.join(estado_cliente['dir_atual'], nome_dir))
                resposta_str = f"OK: Diretório '{nome_dir}' removido."
            except FileNotFoundError:
                resposta_str = "ERRO: Diretório não encontrado."
            except OSError:
                resposta_str = "ERRO: Diretório não está vazio."
            except Exception as e:
                resposta_str = f"ERRO: {e}"
        else:
            resposta_str = "ERRO: 'rmdir' requer um nome de pasta."
        return enviar_resposta_em_partes(sock, fila_acks, resposta_str, endereco_cliente, id_pacote)
    else:
        resposta_str = f"ERRO: Comando '{comando}' desconhecido."
        return enviar_resposta_em_partes(sock, fila_acks, resposta_str, endereco_cliente, id_pacote)

def gerenciar_cliente(sock, fila_comandos, fila_acks, endereco_cliente):
    print(f"[NOVA SESSÃO] Atendimento iniciado para {endereco_cliente}")
    
    estado_cliente = { #estrutura que salva o estado atual do cliente
        'socket': sock, 'fila_comandos': fila_comandos, 'fila_acks': fila_acks,
        'endereco': endereco_cliente, 'logado': False,
        'dir_atual': os.path.abspath(os.getcwd()), 'id_esperado': 0
    }

    while True: #looping principal de gerenciar cliente
        try:
            mensagem_bytes = fila_comandos.get(timeout=CLIENT_SESSION_TIMEOUT) #tirando comando da fila para processar
            if processar_comando(mensagem_bytes, estado_cliente):
                estado_cliente['id_esperado'] = 1 - estado_cliente['id_esperado'] #se conseguiu processar, muda id expected
        except Empty:
            print(f"[TIMEOUT] Cliente {endereco_cliente} inativo.") #fila vazia do .get
            break
        except Exception as e: #qualquer tipo de erro
            print(f"[ERRO] Erro na thread do cliente {endereco_cliente}: {e}")
            break
    with lock: #depois do looping, encerra
        if endereco_cliente in clientes_ativos: del clientes_ativos[endereco_cliente]
    print(f"[SESSÃO ENCERRADA] Atendimento para {endereco_cliente} finalizado.")

def iniciar_servidor():
    serverSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) #criando socket do servidor
    serverSocket.bind((HOST, PORT)) #aqui ele binda a porta e o ip ao servidor

    print(f"Servidor MyFTP iniciado em {HOST}:{PORT}")

    while True:
        try:
            mensagem, endereco_cliente = serverSocket.recvfrom(BUFFER_SIZE) #recebendo mensagem do cliente
            with lock: #lock faz com que essa parte do bloco vai ser rodado por uma thread por vez.
                
                if endereco_cliente not in clientes_ativos: #ve se o cliente ja esta ativo
                    print(f"Novo cliente conectado: {endereco_cliente}")

                    fila_comandos, fila_acks = Queue(), Queue() # criando as filas
                    #criando a thread do cliente
                    thread_cliente = threading.Thread(target=gerenciar_cliente, args=(serverSocket, fila_comandos, fila_acks, endereco_cliente))
                    thread_cliente.daemon = True #se o programa fecha, todas as threads fecham tambem
                    #agora o cliente se torna ativo (cada cliente tem fila de commandos e de acks)
                    clientes_ativos[endereco_cliente] = {'fila_comandos': fila_comandos, 'fila_acks': fila_acks}
                    thread_cliente.start()

                msg_str = mensagem.decode('utf-8', errors='ignore')
                
                if msg_str.startswith("ACK:"):
                    if endereco_cliente in clientes_ativos: clientes_ativos[endereco_cliente]['fila_acks'].put(msg_str)
                else:
                    if endereco_cliente in clientes_ativos: clientes_ativos[endereco_cliente]['fila_comandos'].put(mensagem)
        except Exception as e:
            print(f"Erro fatal no dispatcher do servidor: {e}")
            break
    serverSocket.close()
    print("Servidor encerrado.")

if __name__ == "__main__":
    iniciar_servidor()

