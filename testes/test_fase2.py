import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)

import time
import threading
from fase2.gbn import GBNSender, GBNReceiver
from utils.logger import log_info

# Constantes de Teste
SENDER_PORT = 15000
RECEIVER_PORT = 15001
DATA_SIZE = 1024 * 1000 # 1MB
CHUNK_SIZE = 1000
NUM_CHUNKS = DATA_SIZE // CHUNK_SIZE

def run_gbn_test(window_size, channel_config, test_name):
    log_info(f"\n--- INICIANDO TESTE: {test_name} (Janela={window_size}) ---", "TEST_MAIN")
    
    SENDER_ADDR = ('127.0.0.1', SENDER_PORT)
    RECEIVER_ADDR = ('127.0.0.1', RECEIVER_PORT)
    
    # 1. Inicializar Receiver
    receiver = GBNReceiver(RECEIVER_PORT, SENDER_ADDR, channel_config)
    receiver.start()
    time.sleep(0.5) 
    
    # 2. Inicializar Sender
    # Nota: O tamanho da janela está fixo em 5 no gbn.py. Para variar, seria necessário refatorar a classe.
    # Usaremos a implementação atual e focaremos no teste de perda.
    sender = GBNSender(SENDER_PORT, RECEIVER_ADDR, channel_config, window_size)
    sender.start()
    
    # 3. Enviar dados
    log_info(f"Enviando {DATA_SIZE/1024/1024:.2f}MB ({NUM_CHUNKS} pacotes)...", "TEST_MAIN")
    start_time = time.time()
    
    for i in range(NUM_CHUNKS):
        data = f"Chunk {i:04d}: {'x' * (CHUNK_SIZE - 15)}".encode('utf-8')
        sender.rdt_send(data)
        
    # Espera até que todos os pacotes sejam confirmados
    while True:
        with sender.lock:
            if sender.base == sender.nextseqnum:
                break
        time.sleep(0.1)
        
    end_time = time.time()
    
    # 4. Verificar resultados
    time.sleep(1) 
    
    received_data = receiver.get_received_data()
    
    log_info("\n--- RESULTADOS ---", "TEST_MAIN")
    log_info(f"Pacotes enviados: {NUM_CHUNKS}", "TEST_MAIN")
    log_info(f"Pacotes recebidos (aplicação): {len(received_data)}", "TEST_MAIN")
    log_info(f"Contagem de retransmissões: {sender.retransmission_count}", "TEST_MAIN")
    
    total_time = end_time - start_time
    throughput = (DATA_SIZE * 8) / (total_time * 10**6) # Mbps
    log_info(f"Tempo total: {total_time:.2f}s", "TEST_MAIN")
    log_info(f"Throughput efetivo: {throughput:.2f} Mbps", "TEST_MAIN")
    
    all_correct = len(received_data) == NUM_CHUNKS
    log_info(f"Todas as mensagens chegaram corretamente: {'SIM' if all_correct else 'NÃO'}", "TEST_MAIN")
    
    # 5. Encerrar
    sender.close()
    receiver.close()
    
    return all_correct, sender.retransmission_count, throughput

if __name__ == '__main__':
    # --- Teste 2: Go-Back-N ---
    
    # 1. Teste de Eficiência (Canal Perfeito)
    CHANNEL_CONFIG_PERFECT = {'loss_rate': 0.0, 'corrupt_rate': 0.0, 'delay_range': (0.0, 0.0)}
    run_gbn_test(5, CHANNEL_CONFIG_PERFECT, "GBN - Canal Perfeito (Eficiência)")
    
    # 2. Teste com Perdas (10% de perda)
    CHANNEL_CONFIG_LOSS = {'loss_rate': 0.1, 'corrupt_rate': 0.0, 'delay_range': (0.0, 0.0)}
    run_gbn_test(5, CHANNEL_CONFIG_LOSS, "GBN - Perda (10%)")
    
    # Nota: Para o Teste 4 (Análise de Desempenho com Janela Variável), seria necessário
    # refatorar a classe GBNSender para aceitar o tamanho da janela como parâmetro.
    # O teste atual usa o valor fixo de 5.
