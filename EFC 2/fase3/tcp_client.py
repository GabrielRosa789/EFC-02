import time
import random
from fase3.tcp_socket import SimpleTCPSocket
from utils.logger import log_info, log_error

def tcp_client_app(dest_addr, data_to_send, channel_params=None):
    client_port = random.randint(10000, 20000)
    client = SimpleTCPSocket(client_port, channel_params)
    try:
        log_info(f"Tentando conectar a {dest_addr}...", "APP-CLIENTE")
        client.connect(dest_addr)
        log_info(f"Conexão estabelecida. Enviando {len(data_to_send)} bytes.", "APP-CLIENTE")
        
        # Envia dados
        client.send(data_to_send)
        
        # Espera um pouco para garantir que os dados foram enviados
        time.sleep(2)
        
        # Encerra a conexão
        client.close()
        
    except Exception as e:
        log_error(f"Erro: {e}", "APP-CLIENTE")
    finally:
        client.close()

# Removido bloco de teste
    SERVER_PORT = 17000
    SERVER_ADDR = ('192.168.0.166', SERVER_PORT)
    
    # Canal perfeito para teste
    CHANNEL_CONFIG = {'loss_rate': 0.0, 'corrupt_rate': 0.0, 'delay_range': (0.0, 0.0)}
    
    # Dados de teste (10KB)
    data_to_send = b'x' * 10240
    
    tcp_client_app(SERVER_ADDR, data_to_send, CHANNEL_CONFIG)
