import time
from fase3.tcp_socket import SimpleTCPSocket, MSS
from utils.logger import log_info, log_error

def tcp_server_app(port, channel_params=None):
    server = SimpleTCPSocket(port, channel_params)
    try:
        server.listen()
        log_info(f"Servidor escutando na porta {port}...", "APP-SERVER")
        
        # Aceita a conexão (bloqueante)
        conn = server.accept()
        log_info(f"Conexão estabelecida com {conn.peer_address}", "APP-SERVER")
        
        # Recebe dados
        received_data = b''
        while True:
            data = conn.recv(MSS)
            if not data:
                # Se a conexão estiver fechada e não houver mais dados
                if conn.state in ['CLOSE_WAIT', 'CLOSED']:
                    break
                # Pequena pausa para evitar loop de CPU
                time.sleep(0.01)
                continue
                
            received_data += data
            log_info(f"Recebido {len(data)} bytes. Total: {len(received_data)}", "APP-SERVER")
            
        log_info(f"Transferência concluída. Total de dados recebidos: {len(received_data)} bytes.", "APP-SERVER")
        
        # Encerra a conexão
        conn.close()
        
    except Exception as e:
        log_error(f"Erro: {e}", "APP-SERVER")
    finally:
        server.close()
        return received_data

# Removido bloco de teste
    SERVER_PORT = 17000
    
    # Canal perfeito para teste
    CHANNEL_CONFIG = {'loss_rate': 0.0, 'corrupt_rate': 0.0, 'delay_range': (0.0, 0.0)}
    
    tcp_server_app(SERVER_PORT, CHANNEL_CONFIG)
