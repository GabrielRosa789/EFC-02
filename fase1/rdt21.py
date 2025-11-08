import socket
import threading
import time
from utils.packet import RDTPacket, TYPE_DATA, TYPE_ACK, TYPE_NAK
from utils.simulator import UnreliableChannel
from utils.logger import log_info, log_error

# Constantes
BUFFER_SIZE = 1024
TIMEOUT = 1.0 # Timeout em segundos

class RDT21Sender:
    def __init__(self, local_port, remote_addr, channel_params):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(('0.0.0.0', local_port))
        self.remote_addr = remote_addr
        self.channel = UnreliableChannel(**channel_params)
        self.seq_num = 0 # Próximo número de sequência a ser usado (0 ou 1)
        self.last_packet = None
        self.retransmission_count = 0
        log_info(f"Sender iniciado na porta {local_port}", "RDT2.1")

    def rdt_send(self, data):
        """ Envia dados da aplicação, implementando Stop-and-Wait com alternância de SeqNum """
        
        # 1. Criar pacote com o número de sequência atual
        packet = RDTPacket(TYPE_DATA, self.seq_num, data)
        self.last_packet = packet
        
        while True:
            # 2. Enviar pacote
            self._udt_send(packet)
            
            # 3. Aguardar ACK com o número de sequência correto
            try:
                self.socket.settimeout(TIMEOUT)
                raw_response, _ = self.socket.recvfrom(BUFFER_SIZE)
                
                response_packet = RDTPacket.from_bytes(raw_response)
                
                if response_packet is None:
                    log_info("Pacote de resposta inválido. Reenviando...", "RDT2.1-SENDER")
                    self.retransmission_count += 1
                    continue
                
                # Verifica se o ACK está corrompido ou é o tipo errado
                if response_packet.is_corrupt() or response_packet.type != TYPE_ACK:
                    log_info("ACK corrompido ou tipo incorreto. Reenviando...", "RDT2.1-SENDER")
                    self.retransmission_count += 1
                    continue
                
                # Verifica se o número de sequência do ACK é o esperado
                if response_packet.seq_num == self.seq_num:
                    log_info(f"Recebido ACK({self.seq_num}). Dados entregues com sucesso.", "RDT2.1-SENDER")
                    # 4. Alternar número de sequência e sair do loop
                    self.seq_num = 1 - self.seq_num
                    break 
                else:
                    # ACK duplicado ou fora de ordem (o receptor pode ter reenviado o ACK anterior)
                    log_info(f"Recebido ACK({response_packet.seq_num}) inesperado. Ignorando e aguardando ACK({self.seq_num}).", "RDT2.1-SENDER")
                    # Não retransmite, apenas espera pelo ACK correto
                    
            except socket.timeout:
                # Timeout. Assume-se perda do pacote DATA ou ACK.
                log_info("Timeout. Retransmitindo pacote.", "RDT2.1-SENDER")
                self.retransmission_count += 1
            except Exception as e:
                log_error(f"Erro ao receber resposta: {e}. Reenviando...", "RDT2.1-SENDER")
                self.retransmission_count += 1

    def _udt_send(self, packet):
        """ Envia o pacote através do canal não confiável (simulador) """
        self.channel.send(packet.to_bytes(), self.socket, self.remote_addr)

    def close(self):
        self.socket.close()
        log_info("Sender encerrado.", "RDT2.1")

class RDT21Receiver:
    def __init__(self, local_port, remote_addr, channel_params):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(('0.0.0.0', local_port))
        self.remote_addr = remote_addr
        self.channel = UnreliableChannel(**channel_params)
        self.expected_seq_num = 0 # Próximo número de sequência esperado (0 ou 1)
        self.received_data = []
        self.is_running = True
        self.thread = threading.Thread(target=self._receive_loop)
        log_info(f"Receiver iniciado na porta {local_port}", "RDT2.1")

    def start(self):
        self.thread.start()

    def _receive_loop(self):
        while self.is_running:
            try:
                self.socket.settimeout(None) 
                raw_packet, addr = self.socket.recvfrom(BUFFER_SIZE)
                
                packet = RDTPacket.from_bytes(raw_packet)
                
                if packet is None:
                    log_info("Pacote inválido recebido. Ignorando.", "RDT2.1-RECEIVER")
                    continue
                
                if packet.is_corrupt():
                    log_info("Pacote DATA corrompido. Reenviando ACK do último pacote correto.", "RDT2.1-RECEIVER")
                    # Envia ACK do pacote anterior (1 - expected_seq_num)
                    self._send_ack(1 - self.expected_seq_num)
                
                elif packet.seq_num == self.expected_seq_num:
                    log_info(f"Pacote DATA({packet.seq_num}) recebido corretamente. Entregando dados.", "RDT2.1-RECEIVER")
                    # 1. Entregar dados para a aplicação
                    self.received_data.append(packet.data)
                    
                    # 2. Enviar ACK com o número de sequência esperado
                    self._send_ack(self.expected_seq_num)
                    
                    # 3. Alternar número esperado
                    self.expected_seq_num = 1 - self.expected_seq_num
                    
                else:
                    # Pacote duplicado (número de sequência incorreto)
                    log_info(f"Pacote DATA({packet.seq_num}) duplicado/fora de ordem. Descartando e reenviando ACK do último pacote correto.", "RDT2.1-RECEIVER")
                    # Reenvia ACK do pacote anterior (1 - expected_seq_num)
                    self._send_ack(1 - self.expected_seq_num)
                    
            except Exception as e:
                if self.is_running:
                    log_error(f"Erro no loop de recepção: {e}", "RDT2.1-RECEIVER")

    def _send_ack(self, seq_num):
        """ Envia um pacote ACK com o número de sequência """
        ack_packet = RDTPacket(TYPE_ACK, seq_num)
        self.channel.send(ack_packet.to_bytes(), self.socket, self.remote_addr)

    def get_received_data(self):
        return self.received_data

    def close(self):
        self.is_running = False
        temp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        temp_socket.sendto(b'stop', ('127.0.0.1', self.socket.getsockname()[1]))
        temp_socket.close()
        self.thread.join()
        self.socket.close()
        log_info("Receiver encerrado.", "RDT2.1")

# O bloco de teste foi movido para testes/test_fase1.py
