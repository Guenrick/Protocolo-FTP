import socket
import os

# constantes
SERVER_IP = '127.0.0.1'
SERVER_PORT = 7891
BUFFER_SIZE = 2048
TIMEOUT_GERAL = 5.0

# funçoes auxiliares
def receber_resposta_geral(sock, id_comando_enviado):
    # recebe uma resposta (que nao é um arquivo) do servidor
    sock.settimeout(TIMEOUT_GERAL)
    dados_completos = b''
    id_pacote_esperado = id_comando_enviado
    
    while True:
        try:
            pacote_servidor, _ = sock.recvfrom(BUFFER_SIZE)
            id_recebido, tipo_pacote, dados_bytes = pacote_servidor.split(b':', 2)
            id_recebido = int(id_recebido.decode())

            if id_recebido == id_pacote_esperado:
                sock.sendto(f"ACK:{id_recebido}".encode(), (SERVER_IP, SERVER_PORT))
                dados_completos += dados_bytes
                if tipo_pacote.decode() == 'END':
                    return dados_completos
                id_pacote_esperado = 1 - id_pacote_esperado
            else:
                sock.sendto(f"ACK:{1 - id_pacote_esperado}".encode(), (SERVER_IP, SERVER_PORT))
        except (socket.timeout, ConnectionResetError):
            print("Timeout: Servidor não respondeu a tempo.")
            return None
        except ValueError:
            continue

def enviar_arquivo_confiavel(sock, nome_arquivo, id_comando):
    """Envia um arquivo para o servidor, chunk por chunk."""
    if not os.path.exists(nome_arquivo):
        print(f"ERRO: Arquivo local '{nome_arquivo}' não encontrado.")
        # Envia um pacote de finalização vazio para desbloquear o servidor
        pacote_final_vazio = f"{id_comando}:END:".encode()
        sock.sendto(pacote_final_vazio, (SERVER_IP, SERVER_PORT))
        return False

    with open(nome_arquivo, 'rb') as f:
        id_pacote = id_comando
        while True:
            chunk = f.read(1000)
            tipo = 'DATA' if chunk else 'END'
            # Usando aspas duplas para a f-string e aspas simples para o encode
            pacote = f"{id_pacote}:{tipo}:".encode('utf-8') + chunk
            
            # Envia o chunk e espera ACK
            max_tentativas = 5
            sucesso_envio = False
            for _ in range(max_tentativas):
                try:
                    #logica de envio. Recebe e envia acks enquanto envia partes do arquivo em bytes
                    sock.sendto(pacote, (SERVER_IP, SERVER_PORT))
                    sock.settimeout(2.0)
                    ack, _ = sock.recvfrom(BUFFER_SIZE)
                    if ack.decode() == f"ACK:{id_pacote}":
                        sucesso_envio = True
                        break
                except (socket.timeout, ConnectionResetError):
                    print(f"Retransmitindo chunk ID={id_pacote}...")
                    continue
            
            if not sucesso_envio:
                print("Falha crítica ao enviar chunk. Abortando 'put'.")
                return False

            if not chunk: break
            id_pacote = 1 - id_pacote
    return True

def receber_arquivo_confiavel(sock, nome_arquivo, id_comando):
    """Recebe um arquivo do servidor e o salva localmente."""
    try:
        with open(nome_arquivo, 'wb') as f:
            id_pacote_esperado = id_comando
            while True:
                pacote_servidor, _ = sock.recvfrom(BUFFER_SIZE)
                id_recebido, tipo, dados = pacote_servidor.split(b':', 2)
                id_recebido = int(id_recebido.decode())

                if id_recebido == id_pacote_esperado:
                    sock.sendto(f"ACK:{id_recebido}".encode(), (SERVER_IP, SERVER_PORT))
                    if tipo == b'END':
                        if dados: f.write(dados)
                        print(f"Arquivo '{nome_arquivo}' baixado com sucesso.")
                        return True
                    f.write(dados)
                    id_pacote_esperado = 1 - id_pacote_esperado
                else:
                    sock.sendto(f"ACK:{1 - id_pacote_esperado}".encode(), (SERVER_IP, SERVER_PORT))
    except Exception as e:
        print(f"Erro ao receber ou salvar o arquivo: {e}")
        return False


# Lógica do main
if __name__ == "__main__":
    clientSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # criando socket do cliente
    print("Cliente MyFTP iniciado. Digite 'quit' para sair.")
    id_comando = 0 # O id altera entre 0 e 1

    #looping principal so cliente
    while True:
        comando_usuario = input("MyFTP> ")
        if not comando_usuario: continue # caso ele aperte enter somente
        if comando_usuario.lower() == 'quit': break # caso ele aperte quit
        
        partes_comando = comando_usuario.split()
        comando_principal = partes_comando[0].lower() # pegando o comando
        sucesso_comando = False # flag para ver se o comando foi entregue (mesmo que seja um comando invalido)
        
        # Envia o comando inicial
        mensagem_para_enviar = f"{id_comando}:{comando_usuario}".encode('utf-8') #colocando no padrao de mensagem em bytes
        clientSocket.sendto(mensagem_para_enviar, (SERVER_IP, SERVER_PORT))
        print(f"\nEnviando comando (ID={id_comando}): '{comando_usuario}'...")

        try:
            if comando_principal == 'put':
                if len(partes_comando) < 2:
                    dados_recebidos = receber_resposta_geral(clientSocket, id_comando)
                    if dados_recebidos: print(f"Servidor: {dados_recebidos.decode('utf-8')}") #verifica se os dados sao none
                    sucesso_comando = True #comando foi entregue com sucesso e recebeu a resposta
                else:
                    # espera o ACK de confirmação do servidor
                    clientSocket.settimeout(TIMEOUT_GERAL)
                    ack_put, _ = clientSocket.recvfrom(BUFFER_SIZE) #ack_put = ack recebido do server
                    if ack_put.decode() == f"ACK:{id_comando}":
                        print("Servidor confirmou 'put'. Iniciando envio do arquivo...")
                        # 2. Envia o arquivo
                        if enviar_arquivo_confiavel(clientSocket, partes_comando[1], id_comando):
                            # 3. Recebe a resposta final do servidor
                            resposta_final = receber_resposta_geral(clientSocket, id_comando)
                            if resposta_final:
                                print("\n--- Resposta do Servidor ---")
                                print(resposta_final.decode('utf-8'))
                                print("--------------------------")
                                sucesso_comando = True
            
            elif comando_principal == 'get':
                if len(partes_comando) < 2:
                    print("ERRO: 'get' requer um nome de arquivo.")
                    dados_recebidos = receber_resposta_geral(clientSocket, id_comando)
                    if dados_recebidos: print(f"Servidor: {dados_recebidos.decode()}")
                    sucesso_comando = True
                else:
                    # A função de receber arquivo já lida com tudo
                    if receber_arquivo_confiavel(clientSocket, partes_comando[1], id_comando):
                        sucesso_comando = True

            else: # Para todos os outros comandos (ls, cd, mkdir, etc.)
                dados_recebidos = receber_resposta_geral(clientSocket, id_comando)
                if dados_recebidos is not None:
                    print("\n--- Resposta do Servidor ---")
                    print(dados_recebidos.decode('utf-8'))
                    print("--------------------------")
                    sucesso_comando = True

        except (socket.timeout, ConnectionResetError):
            print("Falha: O servidor não respondeu a tempo.")
        except Exception as e:
            print(f"Ocorreu um erro inesperado: {e}")

        if sucesso_comando: #aqui faz a verificao da flag. Caso tenha sido entregue, volta para 0   
            id_comando = 1 - id_comando
        else:
            print(f"Falha ao executar o comando '{comando_usuario}'. Tente novamente.")

    clientSocket.close()
    print("Conexão fechada.")

