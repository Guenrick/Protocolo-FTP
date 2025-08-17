# server.py
import socket
import threading
import os

# Usa '0.0.0.0' para escutar em todas as interfaces de rede disponíveis
# Isso permite que outros computadores na mesma rede se conectem
HOST = '0.0.0.0'
PORT = 7891         # A mesma porta que o cliente usa para se conectar
BUFFER_SIZE = 2048

# DICIONÁRIO SIMPLES DE USUÁRIOS E SENHAS 
USUARIOS_CADASTRADOS = {
    "daniel": "senha123",
    "aluno": "ifmg"
}


# A LÓGICA DO ATENDENTE (O QUE RODA NA THREAD FILHA) 
def gerenciar_cliente(mensagem_inicial: bytes, endereco_cliente: tuple):
    """
    Esta função é o coração do atendimento. Cada thread executa esta função
    para gerenciar a sessão completa de um único cliente.
    """
    print(f"[NOVA SESSÃO] Iniciando atendimento para o cliente {endereco_cliente}")

    # Para responder, a thread cria seu próprio socket temporário.
    # Isso evita que todas as threads tentem usar o mesmo socket principal para enviar,
    # o que poderia causar condições de corrida e outros problemas.
    sock_thread = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    #  Processamento da primeira mensagem (geralmente o login) 
    try:
        # A primeira mensagem já foi recebida pela thread principal, vamos processá-la
        mensagem_str = mensagem_inicial.decode('utf-8')
        partes = mensagem_str.split(':', 2)
        id_pacote = int(partes[0])
        comando_completo = partes[1]
        
        print(f"[{endereco_cliente}] Recebido comando inicial (ID={id_pacote}): '{comando_completo}'")

        #  enviar o ACK de recebimento
        ack_mensagem = f"ACK:{id_pacote}".encode('utf-8')
        sock_thread.sendto(ack_mensagem, endereco_cliente)
        print(f"[{endereco_cliente}] ACK para o pacote {id_pacote} enviado.")

        #
        # AQUI ENTRARÁ TODA A LÓGICA DE COMANDOS (login, ls, get, put, etc.)
        #
        
    except Exception as e:
        print(f"[ERRO] Erro ao processar mensagem inicial de {endereco_cliente}: {e}")

    # Loop principal para esta thread continuar atendendo o mesmo cliente
    # (Será implementado nos próximos passos)
    # while True:
    #     ...

    # Por enquanto, a thread encerra após lidar com a primeira mensagem
    sock_thread.close()
    print(f"[SESSÃO ENCERRADA] Atendimento para {endereco_cliente} finalizado.")



#  A LÓGICA DA RECEPCIONISTA (A THREAD PRINCIPAL) 
if __name__ == "__main__":
    # Cria o socket do servidor
    serverSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # binda o socket ao endereço e porta definidos para que ele possa escutar
    serverSocket.bind((HOST, PORT))
    
    print(f"Servidor MyFTP iniciado e escutando em {HOST}:{PORT}")
    
    # Dicionário para rastrear clientes ativos e suas threads
    clientes_ativos = {}

    #looping principal do server
    while True:
        try:
            # Espera bloqueada até que qualquer mensagem de qualquer cliente chegue
            mensagem, endereco_cliente = serverSocket.recvfrom(BUFFER_SIZE)
            
            # Verifica se já existe uma thread cuidando deste cliente
            if endereco_cliente not in clientes_ativos or not clientes_ativos[endereco_cliente].is_alive():
                # Se for um cliente novo (ou se a thread anterior morreu), cria e inicia uma nova thread para ele
                print(f"Novo cliente conectado: {endereco_cliente}. Criando thread de atendimento.")
                
                # Criando thread que vai executar a função 'gerenciar_cliente'
                thread_cliente = threading.Thread(target=gerenciar_cliente, args=(mensagem, endereco_cliente))
                
                # Armazenando a referência da thread
                clientes_ativos[endereco_cliente] = thread_cliente
                thread_cliente.start()
            
            # Se já existe uma thread ativa para este cliente, ela é responsável
            # por lidar com as próximas mensagens. 
            

        except Exception as e:
            print(f"Erro fatal no servidor principal: {e}")
            break
            
    serverSocket.close()
    print("Servidor encerrado.")