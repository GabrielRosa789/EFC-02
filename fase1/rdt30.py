import socket
import threading
import time
from utils.packet import RDTPacket, TYPE_DATA, TYPE_ACK
from utils.logger import log_info, log_error
from utils.simulator import UnreliableChannel

# Constantes
BUFFER_SIZE = 1024
TIMEOUT = 2.0 # Timeout em segundos (conforme especificação)

class RDT30Sender:
    def __init__(self, local_port, remote_addr, channel_params):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(('0.0.0.0', local_port))
        self.remote_addr = remote_addr
        self.channel = UnreliableChannel(**channel_params)
        self.seq_num = 0 # Próximo número de sequência a ser usado (0 ou 1)
        self.last_packet = None
        self.retransmission_count = 0
        self.timer = None
        self.lock = threading.Lock()
        self.is_running = True
        log_info(f"Sender iniciado na porta {local_port}", "RDT3.0")

    def _start_timer(self):
        if self.timer:
            self.timer.cancel()
        self.timer = threading.Timer(TIMEOUT, self._handle_timeout)
        self.timer.start()

    def _stop_timer(self):
        if self.timer:
            self.timer.cancel()
            self.timer = None

    def _handle_timeout(self):
        with self.lock:
            if not self.is_running:
                return
            log_info(f"Timeout! Retransmitindo pacote DATA({self.last_packet.seq_num}).", "RDT3.0-SENDER")
            self.retransmission_count += 1
            # Retransmite o último pacote e reinicia o timer
            self._udt_send(self.last_packet)
            self._start_timer()

    def _receive_ack_loop(self):
        while self.is_running:
            try:
                # O timeout do socket é usado para o timer, mas o loop de recepção deve ser contínuo
                self.socket.settimeout(None) 
                raw_response, _ = self.socket.recvfrom(BUFFER_SIZE)
                
                response_packet = RDTPacket.from_bytes(raw_response)
                
                if response_packet is None:
                    continue
                
                # Processamento do ACK
                with self.lock:
                    if not self.last_packet:
                        continue # Não há pacote para confirmar
                        
                    # 1. Verifica corrupção ou tipo incorreto
                    if response_packet.is_corrupt() or response_packet.type != TYPE_ACK:
                        # ACK corrompido ou NAK (rdt3.0 usa apenas ACK)
                        log_info("ACK corrompido/tipo incorreto. Ignorando.", "RDT3.0-SENDER")
                        continue
                    
                    # 2. Verifica número de sequência
                    if response_packet.seq_num == self.seq_num:
                        # ACK correto para o pacote atual
                        log_info(f"Recebido ACK({self.seq_num}). Parando timer.", "RDT3.0-SENDER")
                        self._stop_timer()
                        # Sinaliza que o pacote foi confirmado
                        self.last_packet = None 
                        
                    else:
                        # ACK duplicado ou fora de ordem (para o pacote anterior)
                        log_info(f"Recebido ACK({response_packet.seq_num}) inesperado. Ignorando.", "RDT3.0-SENDER")
                        # Não faz nada, o timer continua rodando para o pacote atual
                        
            except Exception as e:
                if self.is_running:
                    log_error(f"Erro no loop de recepção: {e}", "RDT3.0-SENDER")

    def rdt_send(self, data):
        """ Envia dados da aplicação, implementando Stop-and-Wait com alternância de SeqNum e Timer """
        
        # 1. Criar pacote com o número de sequência atual
        packet = RDTPacket(TYPE_DATA, self.seq_num, data)
        
        with self.lock:
            self.last_packet = packet
            
            # 2. Enviar pacote e iniciar timer
            self._udt_send(packet)
            self._start_timer()
            
        # 3. Aguardar confirmação (o loop de recepção em thread fará isso)
        while True:
            with self.lock:
                if self.last_packet is None:
                    # Pacote confirmado, alternar número de sequência e sair
                    self.seq_num = 1 - self.seq_num
                    break
            time.sleep(0.01) # Pequena pausa para evitar busy-waiting

    def _udt_send(self, packet):
        """ Envia o pacote através do canal não confiável (simulador) """
        self.channel.send(packet.to_bytes(), self.socket, self.remote_addr)

    def start(self):
        self.thread = threading.Thread(target=self._receive_ack_loop)
        self.thread.start()

    def close(self):
        self.is_running = False
        self._stop_timer()
        # Desbloqueia o recvfrom
        temp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        temp_socket.sendto(b'stop', ('127.0.0.1', self.socket.getsockname()[1]))
        temp_socket.close()
        self.thread.join()
        self.socket.close()
        log_info("Sender encerrado.", "RDT3.0")

class RDT30Receiver:
    def __init__(self, local_port, remote_addr, channel_params):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(('0.0.0.0', local_port))
        self.remote_addr = remote_addr
        self.channel = UnreliableChannel(**channel_params)
        self.expected_seq_num = 0 # Próximo número de sequência esperado (0 ou 1)
        self.received_data = []
        self.is_running = True
        self.thread = threading.Thread(target=self._receive_loop)
        log_info(f"Receiver iniciado na porta {local_port}", "RDT3.0")

    def start(self):
        self.thread.start()

    def _receive_loop(self):
        while self.is_running:
            try:
                self.socket.settimeout(None) 
                raw_packet, addr = self.socket.recvfrom(BUFFER_SIZE)
                
                packet = RDTPacket.from_bytes(raw_packet)
                
                if packet is None:
                    continue
                
                if packet.is_corrupt():
                    log_info("Pacote DATA corrompido. Ignorando e reenviando ACK do último pacote correto.", "RDT3.0-RECEIVER")
                    # Reenvia ACK do pacote anterior (1 - expected_seq_num)
                    self._send_ack(1 - self.expected_seq_num)
                
                elif packet.seq_num == self.expected_seq_num:
                    log_info(f"Pacote DATA({packet.seq_num}) recebido corretamente. Entregando dados.", "RDT3.0-RECEIVER")
                    # 1. Entregar dados para a aplicação
                    self.received_data.append(packet.data)
                    
                    # 2. Enviar ACK com o número de sequência esperado
                    self._send_ack(self.expected_seq_num)
                    
                    # 3. Alternar número esperado
                    self.expected_seq_num = 1 - self.expected_seq_num
                    
                else:
                    # Pacote duplicado (número de sequência incorreto)
                    log_info(f"Pacote DATA({packet.seq_num}) duplicado/fora de ordem. Descartando e reenviando ACK do último pacote correto.", "RDT3.0-RECEIVER")
                    # Reenvia ACK do pacote anterior (1 - expected_seq_num)
                    self._send_ack(1 - self.expected_seq_num)
                    
            except Exception as e:
                if self.is_running:
                    log_error(f"Erro no loop de recepção: {e}", "RDT3.0-RECEIVER")

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
        log_info("Receiver encerrado.", "RDT3.0")

