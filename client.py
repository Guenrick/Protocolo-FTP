import socket

clientSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

serverAddr = ('127.0.0.1', 7891) #Endereco do servidor para qual vamos enviar.

buffer = ""; buffer2: str #Criando Buffer

id = 0 #Esse ID serve pra verificar se o pacote chegou corretamente

while buffer != "quit":
    print("------PAINEL DE CONTROLE------")
    buffer = input("Digite algum comando: (para sair, digite quit)")
    
    if buffer.lower() == 'quit':
        break

    mensagem_para_enviar = f"{id}:{buffer}"

    ack_correto = False
    while not ack_correto:
        try:
            print(f"Enviando (ID={id}): '{buffer}'...")
            #Envia mensagem pra o endereco do server
            clientSocket.sendto(mensagem_para_enviar.encode('utf-8'), serverAddr) 
        
        except:
            print("dale")

    id = 1 - id # Serve para alterar de 0 pra 1 e vice-versa

clientSocket.close()
print("Conexão fechada.")