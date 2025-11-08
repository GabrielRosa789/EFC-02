import socket
import threading
import time
from utils.packet import RDTPacket, TYPE_DATA, TYPE_ACK, TYPE_NAK
from utils.simulator import UnreliableChannel
from utils.logger import log_info, log_error

# Constantes
BUFFER_SIZE = 1024
TIMEOUT = 1.0 # Timeout em segundos

class RDT20Sender:
    def __init__(self, local_port, remote_addr, channel_params):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(('0.0.0.0', local_port))
        self.remote_addr = remote_addr
        self.channel = UnreliableChannel(**channel_params)
        self.is_waiting_for_ack = False
        self.last_packet = None
        self.retransmission_count = 0
        log_info(f"Sender iniciado na porta {local_port}", "RDT2.0")

    def rdt_send(self, data):
        """ Envia dados da aplicação, implementando Stop-and-Wait """
        
        # 1. Criar pacote
        # No rdt2.0, o número de sequência não é usado para alternância, mas é necessário para o formato do pacote
        # Usaremos 0 como número de sequência fixo
        packet = RDTPacket(TYPE_DATA, 0, data)
        self.last_packet = packet
        
        while True:
            # 2. Enviar pacote
            self._udt_send(packet)
            self.is_waiting_for_ack = True
            
            # 3. Aguardar ACK/NAK
            try:
                # Configura um timeout para o socket
                self.socket.settimeout(TIMEOUT)
                
                # Recebe a resposta do receptor
                raw_response, _ = self.socket.recvfrom(BUFFER_SIZE)
                
                # Processa a resposta
                response_packet = RDTPacket.from_bytes(raw_response)
                
                if response_packet is None:
                    log_info("Pacote de resposta inválido. Reenviando...", "RDT2.0-SENDER")
                    self.retransmission_count += 1
                    continue
                
                if response_packet.is_corrupt():
                    # ACK/NAK corrompido. No rdt2.0, o remetente não sabe o que fazer.
                    # A especificação do rdt2.0 (Fig 3.10) não lida com ACK/NAK corrompido.
                    # Vamos assumir que o receptor enviará NAK se o DATA estiver corrompido,
                    # e o remetente retransmitirá. Se o ACK/NAK estiver corrompido, 
                    # o remetente pode interpretar como perda e retransmitir após timeout,
                    # mas como estamos em um loop de espera, vamos retransmitir.
                    log_info("ACK/NAK corrompido. Reenviando...", "RDT2.0-SENDER")
                    self.retransmission_count += 1
                    continue
                
                if response_packet.type == TYPE_ACK:
                    log_info("Recebido ACK. Dados entregues com sucesso.", "RDT2.0-SENDER")
                    self.is_waiting_for_ack = False
                    break # Sai do loop e aceita novos dados
                
                elif response_packet.type == TYPE_NAK:
                    log_info("Recebido NAK. Retransmitindo pacote.", "RDT2.0-SENDER")
                    self.retransmission_count += 1
                    # Continua o loop para retransmitir
                
                else:
                    log_info(f"Tipo de pacote inesperado ({response_packet.type}). Reenviando...", "RDT2.0-SENDER")
                    self.retransmission_count += 1
                    
            except socket.timeout:
                # Timeout. Assume-se perda ou corrupção do ACK/NAK.
                log_info("Timeout. Retransmitindo pacote.", "RDT2.0-SENDER")
                self.retransmission_count += 1
            except Exception as e:
                log_error(f"Erro ao receber resposta: {e}. Reenviando...", "RDT2.0-SENDER")
                self.retransmission_count += 1

    def _udt_send(self, packet):
        """ Envia o pacote através do canal não confiável (simulador) """
        self.channel.send(packet.to_bytes(), self.socket, self.remote_addr)

    def close(self):
        self.socket.close()
        log_info("Sender encerrado.", "RDT2.0")

class RDT20Receiver:
    def __init__(self, local_port, remote_addr, channel_params):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(('0.0.0.0', local_port))
        self.remote_addr = remote_addr
        self.channel = UnreliableChannel(**channel_params)
        self.received_data = []
        self.is_running = True
        self.thread = threading.Thread(target=self._receive_loop)
        log_info(f"Receiver iniciado na porta {local_port}", "RDT2.0")

    def start(self):
        self.thread.start()

    def _receive_loop(self):
        while self.is_running:
            try:
                # Remove o timeout para esperar indefinidamente
                self.socket.settimeout(None) 
                raw_packet, addr = self.socket.recvfrom(BUFFER_SIZE)
                
                packet = RDTPacket.from_bytes(raw_packet)
                
                if packet is None:
                    log_info("Pacote inválido recebido. Ignorando.", "RDT2.0-RECEIVER")
                    continue
                
                if packet.is_corrupt():
                    log_info("Pacote DATA corrompido. Enviando NAK.", "RDT2.0-RECEIVER")
                    self._send_nak()
                else:
                    log_info("Pacote DATA recebido corretamente. Entregando dados.", "RDT2.0-RECEIVER")
                    # Entregar dados para a aplicação
                    self.received_data.append(packet.data)
                    
                    # Enviar ACK
                    self._send_ack()
                    
            except Exception as e:
                if self.is_running:
                    log_error(f"Erro no loop de recepção: {e}", "RDT2.0-RECEIVER")

    def _send_ack(self):
        """ Envia um pacote ACK (sem dados) """
        ack_packet = RDTPacket(TYPE_ACK, 0)
        self.channel.send(ack_packet.to_bytes(), self.socket, self.remote_addr)

    def _send_nak(self):
        """ Envia um pacote NAK (sem dados) """
        nak_packet = RDTPacket(TYPE_NAK, 0)
        self.channel.send(nak_packet.to_bytes(), self.socket, self.remote_addr)

    def get_received_data(self):
        return self.received_data

    def close(self):
        self.is_running = False
        # Cria um socket temporário para desbloquear o recvfrom
        temp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        temp_socket.sendto(b'stop', ('127.0.0.1', self.socket.getsockname()[1]))
        temp_socket.close()
        self.thread.join()
        self.socket.close()
        log_info("Receiver encerrado.", "RDT2.0")
