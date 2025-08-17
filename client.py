# client.py
import socket
import os #Usado para verificar se um arquivo existe no comando 'put'

SERVER_IP = '127.0.0.1' # Endereço do servidor (localhost)
SERVER_PORT = 7891      # Porta que o servidor escuta
BUFFER_SIZE = 2048      # Tamanho do buffer para recebimento de dados
CHUNK_SIZE = 1000       # Tamanho do pedaço do arquivo a ser enviado no 'put'

# FUNÇÃO DE ENVIO CONFIÁVEL 
def enviar_confiavel(sock: socket.socket, mensagem_bytes: bytes, endereco: tuple, id_pacote: int):
    """
    Envia uma mensagem EM BYTES de forma confiável.
    Retorna True em sucesso, False em falha.
    """
    max_tentativas = 5
    for tentativa in range(max_tentativas):
        try:
            print(f"Tentativa {tentativa + 1}/{max_tentativas}: Enviando (ID={id_pacote})...")
            # A mensagem já está em bytes, então envia diretamente
            sock.sendto(mensagem_bytes, endereco)

            resposta_servidor, _ = sock.recvfrom(BUFFER_SIZE)
            
            ack_recebido = resposta_servidor.decode('utf-8')
            if ack_recebido == f"ACK:{id_pacote}":
                print(f"--> ACK para o pacote {id_pacote} recebido com sucesso!")
                return True
            else:
                print(f"--> Recebido ACK inesperado: '{ack_recebido}'. Ignorando.")
        except socket.timeout:
            print("Timeout! O servidor não respondeu.")
    
    print(f"Falha no envio do pacote {id_pacote} após {max_tentativas} tentativas.")
    return False

# FUNÇÃO DE RECEBIMENTO CONFIÁVEL 
def receber_confiavel(sock: socket.socket, endereco_servidor: tuple):
    """
    Recebe uma sequência de pacotes de dados de forma confiável.
    Retorna os dados completos em bytes, ou None em caso de falha.
    """
    dados_completos = b''
    id_pacote_esperado = 0
    
    while True:
        try:
            pacote_servidor, _ = sock.recvfrom(BUFFER_SIZE) #Aqui ele recebe os dados
            
            # Separa o cabeçalho do payload (que está em bytes)
            try:
                #divide por b':' e pega a partir da seguna posicao
                id_bytes, tipo_bytes, dados_bytes = pacote_servidor.split(b':', 2)
            except ValueError:
                # Se o split falhar, pode ser um pacote mal formatado
                 print(f"--> Pacote mal formatado recebido. Ignorando.")
                 continue

            id_str = id_bytes.decode('utf-8')
            tipo_str = tipo_bytes.decode('utf-8')
            id_recebido = int(id_str) #converte para int para fazer comparação no if
            
            if id_recebido == id_pacote_esperado:
                print(f"--> Recebido pacote de dados ID={id_str}.")
                dados_completos += dados_bytes
                
                # Envia o ACK para este pacote
                sock.sendto(f"ACK:{id_str}".encode('utf-8'), endereco_servidor) #ack avisa ao servidor que chegou
                
                id_pacote_esperado = 1 - id_pacote_esperado
                
                if tipo_str == 'END':
                    print("Fim da transmissão de dados recebido.")
                    return dados_completos
            else:
                print(f"--> Recebido pacote duplicado/fora de ordem ID={id_str}. Reenviando ACK anterior.")
                ack_anterior = 1 - id_pacote_esperado
                sock.sendto(f"ACK:{ack_anterior}".encode('utf-8'), endereco_servidor)
        except socket.timeout:
            print("Erro: O servidor parou de responder durante a transmissão.")
            return None

def enviar_arquivo_confiavel(sock: socket.socket, nome_arquivo: str, endereco_servidor: tuple):
    """
    Lê um arquivo local, quebra em pedaços e envia cada pedaço de forma confiável.
    """
    # Primeiro, verifica se o arquivo existe no lado do cliente
    if not os.path.exists(nome_arquivo):
        print(f"Erro: Arquivo local '{nome_arquivo}' não encontrado.")
        return False

    try:
        # Abre o arquivo para leitura em modo binário ('rb')
        with open(nome_arquivo, 'rb') as f:
            print(f"Iniciando envio do arquivo '{nome_arquivo}'...")
            id_pacote_dados = 0
            
            while True:
                # Lê um pedaço do arquivo
                chunk = f.read(CHUNK_SIZE)
                
                # Se o chunk está vazio, chegamos ao fim do arquivo
                if not chunk:
                    # Envia o pacote final de forma confiável
                    pacote_final = f"{id_pacote_dados}:END:".encode('utf-8') #pacote final sem chunk
                    if enviar_confiavel(sock, pacote_final, endereco_servidor, id_pacote_dados):
                        print("Arquivo enviado com sucesso.")
                        return True
                    else:
                        print("Falha ao enviar o pacote final de transmissão.")
                        return False

                # Monta o pacote de dados (cabeçalho + dados em bytes)
                cabecalho = f"{id_pacote_dados}:DATA:".encode('utf-8')
                pacote_completo = cabecalho + chunk
                
                # Usa a nossa função de envio confiável para mandar o pedaço
                if not enviar_confiavel(sock, pacote_completo, endereco_servidor, id_pacote_dados):
                    # Se um dos chunks falhar após todas as tentativas, a transferência falha.
                    print(f"Falha ao enviar o chunk ID={id_pacote_dados}. Abortando.")  
                    return False
                
                # Alterna o ID para o próximo pedaço
                id_pacote_dados = 1 - id_pacote_dados
    except IOError as e:
        print(f"Erro ao ler o arquivo local: {e}")
        return False


#  LÓGICA PRINCIPAL DO CLIENTE 
if __name__ == "__main__":
    # Cria o soquete UDP do cliente
    clientSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # af = addres family. padrao da internet
    # Define um timeout global para todas as operações de recebimento
    clientSocket.settimeout(3.0) # 3 segundos para todo as operações de recv from

    print("Cliente MyFTP iniciado. Digite um comando ou 'quit' para sair.")

    id = 0 # ID para pacotes de COMANDO enviados pelo cliente (0 ou 1)

    while True: #looping principal
        comando = input("MyFTP> ")

        if not comando: # Se o usuário só apertar Enter
            continue

        if comando.lower() == 'quit':
            break

        # Prepara o comando a ser enviado
        mensagem_para_enviar = f"{id}:{comando}".encode('utf-8') #passando para bytes
        
        # Usa a função para enviar o comando de forma confiável
        if enviar_confiavel(clientSocket, mensagem_para_enviar, (SERVER_IP, SERVER_PORT), id):
            # Se o comando foi confirmado, agora lidamos com a resposta
            
            partes_comando = comando.split()
            comando_principal = partes_comando[0].lower()

            if comando_principal in ['ls', 'get', 'cd', 'cd..', 'mkdir', 'rmdir']:
                # Espera uma resposta do servidor pra cada comando
                print("Comando confirmado. Aguardando resposta do servidor...")
                
                dados_recebidos = receber_confiavel(clientSocket, (SERVER_IP, SERVER_PORT))

                if dados_recebidos is not None:
                    if comando_principal == 'get':
                        # Se o comando foi 'get', salva os dados em um arquivo
                        nome_arquivo = partes_comando[1]
                        try:
                            with open(nome_arquivo, 'wb') as f: #cria ou sobrescreve arquivo ja existente.
                                f.write(dados_recebidos)
                            print(f"Arquivo '{nome_arquivo}' baixado com sucesso.")
                        except IOError as e:
                            print(f"Erro ao salvar o arquivo: {e}")
                    else:
                        # Para outros comandos, apenas imprime a resposta do servidor
                        print("\n--- Resposta do Servidor ---")
                        print(dados_recebidos.decode('utf-8'))
                        print("--------------------------\n")

            elif comando_principal == 'put':
                if len(partes_comando) < 2:
                    print("Erro: O comando 'put' precisa de um nome de arquivo.")
                else:
                    enviar_arquivo_confiavel(clientSocket, partes_comando[1], (SERVER_IP, SERVER_PORT))
            
            # Prepara o ID para o próximo comando
            id = 1 - id
        else:
            print("Não foi possível se comunicar com o servidor. Verifique se ele está online e tente o comando novamente.")

    clientSocket.close()
    print("Conexão fechada.")