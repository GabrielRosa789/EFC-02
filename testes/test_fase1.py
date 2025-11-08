import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)

import time
import threading
from fase1.rdt20 import RDT20Sender, RDT20Receiver
from fase1.rdt21 import RDT21Sender, RDT21Receiver
from fase1.rdt30 import RDT30Sender, RDT30Receiver
from utils.logger import log_info

# Constantes de Teste
SENDER_PORT_BASE = 12000
RECEIVER_PORT_BASE = 12001
NUM_MESSAGES = 10
MESSAGES = [f"Mensagem de teste {i}".encode('utf-8') for i in range(NUM_MESSAGES)]

def run_rdt_test(SenderClass, ReceiverClass, sender_port, receiver_port, channel_config, test_name):
    log_info(f"\n--- INICIANDO TESTE: {test_name} ---", "TEST_MAIN")
    
    SENDER_ADDR = ('127.0.0.1', sender_port)
    RECEIVER_ADDR = ('127.0.0.1', receiver_port)
    
    # 1. Inicializar Receiver
    receiver = ReceiverClass(receiver_port, SENDER_ADDR, channel_config)
    receiver.start()
    time.sleep(0.5) # Dá tempo para o socket do receiver iniciar
    
    # 2. Inicializar Sender
    sender = SenderClass(sender_port, RECEIVER_ADDR, channel_config)
    if hasattr(sender, 'start'):
        sender.start()
    
    # 3. Enviar mensagens
    start_time = time.time()
    
    for i, msg in enumerate(MESSAGES):
        log_info(f"Enviando mensagem {i+1}/{NUM_MESSAGES}: {msg.decode()}", "TEST_MAIN")
        sender.rdt_send(msg)
        
    end_time = time.time()
    
    # 4. Verificar resultados
    time.sleep(1) # Dá tempo para o último ACK chegar
    
    received_data = receiver.get_received_data()
    
    log_info("\n--- RESULTADOS ---", "TEST_MAIN")
    log_info(f"Mensagens enviadas: {NUM_MESSAGES}", "TEST_MAIN")
    log_info(f"Mensagens recebidas (aplicação): {len(received_data)}", "TEST_MAIN")
    log_info(f"Contagem de retransmissões: {sender.retransmission_count}", "TEST_MAIN")
    log_info(f"Tempo total: {end_time - start_time:.2f}s", "TEST_MAIN")
    
    all_correct = True
    if len(MESSAGES) != len(received_data):
        all_correct = False
    else:
        for sent, received in zip(MESSAGES, received_data):
            if sent != received:
                all_correct = False
                break
                
    log_info(f"Todas as mensagens chegaram corretamente: {'SIM' if all_correct else 'NÃO'}", "TEST_MAIN")
    
    # 5. Encerrar
    sender.close()
    receiver.close()
    
    return all_correct, sender.retransmission_count, end_time - start_time

if __name__ == '__main__':
    # --- Teste 1A: rdt2.0 ---
    # 1. Canal perfeito
    CHANNEL_CONFIG_20_PERFECT = {'loss_rate': 0.0, 'corrupt_rate': 0.0, 'delay_range': (0.0, 0.0)}
    run_rdt_test(RDT20Sender, RDT20Receiver, SENDER_PORT_BASE, RECEIVER_PORT_BASE, CHANNEL_CONFIG_20_PERFECT, "RDT2.0 - Canal Perfeito")
    
    # 2. Corrupção de 30%
    CHANNEL_CONFIG_20_CORRUPT = {'loss_rate': 0.0, 'corrupt_rate': 0.3, 'delay_range': (0.0, 0.0)}
    run_rdt_test(RDT20Sender, RDT20Receiver, SENDER_PORT_BASE + 2, RECEIVER_PORT_BASE + 2, CHANNEL_CONFIG_20_CORRUPT, "RDT2.0 - Corrupção (30%)")
    
    # --- Teste 1B: rdt2.1 ---
    # 1. Corromper 20% dos pacotes DATA e 20% dos ACKs
    CHANNEL_CONFIG_21_CORRUPT = {'loss_rate': 0.0, 'corrupt_rate': 0.2, 'delay_range': (0.0, 0.0)}
    run_rdt_test(RDT21Sender, RDT21Receiver, SENDER_PORT_BASE + 4, RECEIVER_PORT_BASE + 4, CHANNEL_CONFIG_21_CORRUPT, "RDT2.1 - Corrupção (20% DATA/ACK)")
    
    # --- Teste 1C: rdt3.0 ---
    # 1. Simular perda de 15% dos pacotes DATA e 15% dos ACKs, com atraso variável
    CHANNEL_CONFIG_30_LOSS = {'loss_rate': 0.15, 'corrupt_rate': 0.0, 'delay_range': (0.05, 0.5)}
    run_rdt_test(RDT30Sender, RDT30Receiver, SENDER_PORT_BASE + 6, RECEIVER_PORT_BASE + 6, CHANNEL_CONFIG_30_LOSS, "RDT3.0 - Perda (15%) e Atraso")
