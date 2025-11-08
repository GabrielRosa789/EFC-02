import socket
import threading
import time
import random
from collections import deque
from utils.packet import TCPSegment, set_flag, is_flag_set, SYN_BIT, ACK_BIT, FIN_BIT
from utils.simulator import UnreliableChannel
from utils.logger import log_info, log_error, log_debug

# Constantes
BUFFER_SIZE = 1024 * 4 # 4KB
MSS = 1024 # Maximum Segment Size (tamanho máximo dos dados)
TIMEOUT_INITIAL = 1.0 # Timeout inicial em segundos

# Estados da Conexão
STATE_CLOSED = 'CLOSED'
STATE_LISTEN = 'LISTEN'
STATE_SYN_SENT = 'SYN_SENT'
STATE_SYN_RCVD = 'SYN_RCVD'
STATE_ESTABLISHED = 'ESTABLISHED'
STATE_FIN_WAIT_1 = 'FIN_WAIT_1'
STATE_FIN_WAIT_2 = 'FIN_WAIT_2'
STATE_CLOSING = 'CLOSING'
STATE_TIME_WAIT = 'TIME_WAIT'
STATE_CLOSE_WAIT = 'CLOSE_WAIT'
STATE_LAST_ACK = 'LAST_ACK'

class SimpleTCPSocket:
    def __init__(self, port, channel_params=None):
        """ Inicializa socket UDP subjacente e estruturas de dados """
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.bind(('0.0.0.0', port))
        self.port = port
        
        # Simulador de canal (pode ser None para canal perfeito)
        self.channel = UnreliableChannel(**channel_params) if channel_params else None
        
        # Estados da conexão
        self.state = STATE_CLOSED
        self.lock = threading.Lock()
        self.is_running = True
        
        # Números de sequência e ACK
        self.isn = random.randint(0, 2**32 - 1) # Initial Sequence Number
        self.seq_num = self.isn
        self.ack_num = 0
        self.next_seq_num = self.isn # Próximo byte a ser enviado
        self.expected_seq_num = 0 # Próximo byte esperado do peer
        self.last_ack_rcvd = self.isn # Último ACK recebido
        
        # Buffers
        self.send_buffer = deque() # Dados da aplicação a serem enviados
        self.recv_buffer = deque() # Dados recebidos a serem lidos pela aplicação
        self.unacked_segments = {} # Segmentos enviados e não confirmados {seq_num: (segment, timestamp)}
        
        # Controle de fluxo
        self.recv_window = BUFFER_SIZE # Tamanho do buffer de recepção
        self.peer_window = BUFFER_SIZE # Janela de recepção do peer (rwnd)
        
        # Controle de tempo (RTT adaptativo)
        self.estimated_rtt = TIMEOUT_INITIAL
        self.dev_rtt = TIMEOUT_INITIAL / 2
        self.retransmission_count = 0
        
        # Dados do peer
        self.peer_address = None
        
        # Threads
        self.recv_thread = threading.Thread(target=self._receive_loop)
        self.send_thread = threading.Thread(target=self._send_loop)
        
        # Eventos de sincronização
        self.handshake_complete = threading.Event()
        self.data_available = threading.Event()
        self.close_complete = threading.Event()
        
        self.recv_thread.start()
        self.send_thread.start()
        log_info(f"Socket iniciado na porta {port}", "TCP")

    def _calculate_timeout(self):
        """Calcula timeout baseado em RTT"""
        return self.estimated_rtt + 4 * self.dev_rtt

    def _update_rtt(self, sample_rtt):
        """Atualiza estimativa de RTT (Karn's Algorithm não implementado)"""
        alpha = 0.125
        beta = 0.25
        self.estimated_rtt = (1 - alpha) * self.estimated_rtt + alpha * sample_rtt
        self.dev_rtt = (1 - beta) * self.dev_rtt + beta * abs(sample_rtt - self.estimated_rtt)
        log_debug(f"RTT: Sample={sample_rtt:.3f}, Est={self.estimated_rtt:.3f}, Dev={self.dev_rtt:.3f}, Timeout={self._calculate_timeout():.3f}", "TCP-RTT")

    def _send_segment(self, flags, data=b'', seq_num=None, ack_num=None, is_retransmission=False):
        """Cria e envia segmento TCP"""
        with self.lock:
            current_seq = seq_num if seq_num is not None else self.next_seq_num
            current_ack = ack_num if ack_num is not None else self.expected_seq_num
            
            segment = TCPSegment(
                src_port=self.port,
                dest_port=self.peer_address[1] if self.peer_address else 0,
                seq_num=current_seq,
                ack_num=current_ack,
                flags=flags,
                window_size=self.recv_window - len(self.recv_buffer),
                data=data
            )
            
            raw_segment = segment.to_bytes()
            
            if self.channel:
                self.channel.send(raw_segment, self.udp_socket, self.peer_address)
            else:
                self.udp_socket.sendto(raw_segment, self.peer_address)
                
            if not is_retransmission and len(data) > 0:
                # Armazena o segmento não confirmado apenas se for um segmento de dados novo
                self.unacked_segments[current_seq] = (segment, time.time())
                self.next_seq_num += len(data)
                
            return segment

    def _retransmit_segments(self):
        """Verifica e retransmite segmentos expirados"""
        timeout = self._calculate_timeout()
        now = time.time()
        
        with self.lock:
            segments_to_retransmit = []
            for seq, (segment, timestamp) in self.unacked_segments.items():
                if now - timestamp > timeout:
                    segments_to_retransmit.append(segment)
            
            for segment in segments_to_retransmit:
                log_info(f"Timeout! Retransmitindo segmento Seq={segment.seq_num}.", "TCP-SENDER")
                self.retransmission_count += 1
                self._send_segment(segment.flags, segment.data, segment.seq_num, segment.ack_num, is_retransmission=True)
                # Atualiza o timestamp para evitar retransmissão imediata
                self.unacked_segments[segment.seq_num] = (segment, now)

    def _send_loop(self):
        """Loop principal de envio e retransmissão"""
        while self.is_running:
            if self.state == STATE_ESTABLISHED:
                self._retransmit_segments()
                
                # Envio de dados do buffer
                with self.lock:
                    if self.send_buffer and self.next_seq_num - self.last_ack_rcvd < self.peer_window:
                        data_to_send = self.send_buffer.popleft()
                        
                        # Divide em segmentos MSS
                        for i in range(0, len(data_to_send), MSS):
                            chunk = data_to_send[i:i + MSS]
                            self._send_segment(set_flag(0, ACK_BIT), chunk)
                            
            time.sleep(0.1) # Pequena pausa

    def _receive_loop(self):
        """Thread que recebe segmentos UDP e processa"""
        while self.is_running:
            try:
                self.udp_socket.settimeout(0.5)
                raw_segment, addr = self.udp_socket.recvfrom(BUFFER_SIZE)
                
                segment = TCPSegment.from_bytes(raw_segment)
                
                if segment is None or segment.is_corrupt():
                    log_info("Segmento corrompido ou inválido. Descartando.", "TCP-RECEIVER")
                    continue
                
                # Se o peer_address não estiver definido, define
                if not self.peer_address and self.state != STATE_LISTEN:
                    self.peer_address = addr
                
                self._process_segment(segment, addr)
                
            except socket.timeout:
                continue
            except Exception as e:
                if self.is_running:
                    log_error(f"Erro no loop de recepção: {e}", "TCP-RECEIVER")

    def _process_segment(self, segment, addr):
        """Processa o segmento recebido com base no estado da conexão"""
        with self.lock:
            # 1. Processamento de ACK (cumulativo)
            if is_flag_set(segment.flags, ACK_BIT):
                ack_num = segment.ack_num
                
                if ack_num > self.last_ack_rcvd:
                    # Confirmação de novos dados
                    log_debug(f"Recebido ACK={ack_num}. Confirmando dados.", "TCP-RECEIVER")
                    
                    # Remove segmentos confirmados do buffer de não confirmados
                    segments_to_remove = []
                    for seq in self.unacked_segments.keys():
                        if seq + len(self.unacked_segments[seq][0].data) <= ack_num:
                            segments_to_remove.append(seq)
                            
                    for seq in segments_to_remove:
                        del self.unacked_segments[seq]
                        
                    # Atualiza last_ack_rcvd
                    self.last_ack_rcvd = ack_num
                    
                    # Atualiza RTT (simplificado: usa o tempo do segmento mais antigo confirmado)
                    # Não implementado RTT adaptativo completo aqui por complexidade
                    
                    # Atualiza janela do peer
                    self.peer_window = segment.window_size
                    
                    # Lógica de estados de fechamento
                    if self.state == STATE_FIN_WAIT_1:
                        self.state = STATE_FIN_WAIT_2
                    elif self.state == STATE_LAST_ACK:
                        self.state = STATE_CLOSED
                        self.close_complete.set()
                        
            # 2. Processamento de SYN
            if is_flag_set(segment.flags, SYN_BIT):
                if self.state == STATE_LISTEN:
                    # Servidor: SYN recebido -> SYN_RCVD
                    self.peer_address = addr
                    self.expected_seq_num = segment.seq_num + 1
                    self.state = STATE_SYN_RCVD
                    
                    # Envia SYN-ACK
                    flags = set_flag(0, SYN_BIT)
                    flags = set_flag(flags, ACK_BIT)
                    self._send_segment(flags, seq_num=self.isn, ack_num=self.expected_seq_num)
                    
                elif self.state == STATE_SYN_SENT:
                    # Cliente: SYN-ACK recebido -> ESTABLISHED
                    if is_flag_set(segment.flags, ACK_BIT) and segment.ack_num == self.isn + 1:
                        self.expected_seq_num = segment.seq_num + 1
                        self.state = STATE_ESTABLISHED
                        
                        # Envia ACK
                        self._send_segment(set_flag(0, ACK_BIT), seq_num=self.isn + 1, ack_num=self.expected_seq_num)
                        self.handshake_complete.set()
                        
            # 3. Processamento de Dados (apenas em ESTABLISHED)
            if self.state == STATE_ESTABLISHED and len(segment.data) > 0:
                if segment.seq_num == self.expected_seq_num:
                    # Dados em ordem
                    self.recv_buffer.append(segment.data)
                    self.expected_seq_num += len(segment.data)
                    self.data_available.set()
                    
                    # Envia ACK cumulativo
                    self._send_segment(set_flag(0, ACK_BIT), seq_num=self.next_seq_num, ack_num=self.expected_seq_num)
                else:
                    # Dados fora de ordem ou duplicados (ignora e reenvia ACK do esperado)
                    self._send_segment(set_flag(0, ACK_BIT), seq_num=self.next_seq_num, ack_num=self.expected_seq_num)
                    
            # 4. Processamento de FIN
            if is_flag_set(segment.flags, FIN_BIT):
                if self.state == STATE_ESTABLISHED:
                    # Recebido FIN -> CLOSE_WAIT
                    self.expected_seq_num += 1 # FIN consome 1 byte de seq
                    self.state = STATE_CLOSE_WAIT
                    
                    # Envia ACK
                    self._send_segment(set_flag(0, ACK_BIT), seq_num=self.next_seq_num, ack_num=self.expected_seq_num)
                    
                elif self.state == STATE_FIN_WAIT_2:
                    # Recebido FIN -> TIME_WAIT
                    self.expected_seq_num += 1
                    
                    # Envia ACK
                    self._send_segment(set_flag(0, ACK_BIT), seq_num=self.next_seq_num, ack_num=self.expected_seq_num)
                    
                    self.state = STATE_TIME_WAIT
                    # Inicia timer de 2MSL (simplificado para 2 segundos)
                    threading.Timer(2.0, lambda: self._transition_to_closed()).start()

    def _transition_to_closed(self):
        with self.lock:
            if self.state == STATE_TIME_WAIT:
                self.state = STATE_CLOSED
                self.close_complete.set()

    def connect(self, dest_address):
        """ Inicia conexão com three-way handshake """
        with self.lock:
            if self.state != STATE_CLOSED:
                raise Exception("Socket já está em uso.")
            
            self.peer_address = dest_address
            self.state = STATE_SYN_SENT
            
            # 1. Envia SYN
            flags = set_flag(0, SYN_BIT)
            self._send_segment(flags, seq_num=self.isn)
            
        # Aguarda SYN-ACK e ACK
        if not self.handshake_complete.wait(timeout=5):
            raise TimeoutError("Timeout no handshake de conexão.")
        
        log_info(f"Conexão estabelecida com {dest_address}. Estado: {self.state}", "TCP-CLIENT")

    def listen(self):
        """ Coloca socket em modo de escuta """
        with self.lock:
            if self.state != STATE_CLOSED:
                raise Exception("Socket já está em uso.")
            self.state = STATE_LISTEN
            log_info(f"Escutando na porta {self.port}. Estado: {self.state}", "TCP-SERVER")

    def accept(self):
        """ Aceita conexão entrante (completa handshake) """
        if self.state != STATE_LISTEN:
            raise Exception("Socket não está em modo de escuta.")
            
        # Aguarda SYN_RCVD (recebimento do SYN)
        while self.state != STATE_SYN_RCVD:
            time.sleep(0.1)
            
        # Aguarda o ACK final do cliente
        if not self.handshake_complete.wait(timeout=5):
            raise TimeoutError("Timeout esperando ACK final do cliente.")
            
        log_info(f"Conexão aceita de {self.peer_address}. Estado: {self.state}", "TCP-SERVER")
        return self # Retorna o próprio socket (simplificação)

    def send(self, data):
        """ Envia dados (pode bloquear se buffer cheio) """
        if self.state != STATE_ESTABLISHED:
            raise Exception("Conexão não estabelecida.")
            
        with self.lock:
            self.send_buffer.append(data)
            
        # O _send_loop cuidará do envio e retransmissão

    def recv(self, buffer_size):
        """ Recebe dados do buffer de recepção """
        if self.state not in [STATE_ESTABLISHED, STATE_CLOSE_WAIT]:
            raise Exception("Conexão não estabelecida ou fechada.")
            
        # Aguarda dados disponíveis
        while not self.recv_buffer and self.is_running:
            self.data_available.wait(timeout=0.1)
            self.data_available.clear()
            
        with self.lock:
            if not self.recv_buffer:
                return b''
                
            # Junta todos os dados no buffer e retorna o tamanho solicitado
            all_data = b''.join(self.recv_buffer)
            self.recv_buffer.clear()
            
            data_to_return = all_data[:buffer_size]
            
            # Atualiza a janela de recepção (rwnd)
            self.recv_window = BUFFER_SIZE - len(self.recv_buffer)
            
            return data_to_return

    def close(self):
        """ Fecha conexão (four-way handshake) """
        with self.lock:
            if self.state == STATE_ESTABLISHED:
                self.state = STATE_FIN_WAIT_1
                # 1. Envia FIN
                self._send_segment(set_flag(0, FIN_BIT), seq_num=self.next_seq_num)
                self.next_seq_num += 1 # FIN consome 1 byte de seq
                
            elif self.state == STATE_CLOSE_WAIT:
                self.state = STATE_LAST_ACK
                # 2. Envia FIN
                self._send_segment(set_flag(0, FIN_BIT), seq_num=self.next_seq_num)
                self.next_seq_num += 1
                
            else:
                print(f"[CLOSE] Estado atual {self.state}. Fechando threads.")
                self.is_running = False
                return

        # Aguarda o fechamento completo
        if not self.close_complete.wait(timeout=5):
            log_warning("Timeout esperando fechamento completo.", "TCP-CLOSE")
            
        self.is_running = False
        self.recv_thread.join()
        self.send_thread.join()
        self.udp_socket.close()
        log_info(f"Conexão encerrada. Estado: {self.state}", "TCP-CLOSE")

# --- Aplicações de Exemplo ---

def tcp_server_example(port, channel_params=None):
    server = SimpleTCPSocket(port, channel_params)
    try:
        server.listen()
        conn = server.accept()
        
        # Recebe dados
        received_data = b''
        while True:
            data = conn.recv(MSS)
            if not data:
                break
            received_data += data
            
        print(f"[SERVER] Dados recebidos: {len(received_data)} bytes.")
        
        # Encerra a conexão
        conn.close()
        
    except Exception as e:
        print(f"[SERVER] Erro: {e}")
    finally:
        server.close()
        return received_data

def tcp_client_example(dest_addr, data_to_send, channel_params=None):
    client = SimpleTCPSocket(random.randint(10000, 20000), channel_params)
    try:
        client.connect(dest_addr)
        
        # Envia dados
        client.send(data_to_send)
        
        # Espera um pouco para garantir que os dados foram enviados
        time.sleep(1)
        
        # Encerra a conexão
        client.close()
        
    except Exception as e:
        print(f"[CLIENTE] Erro: {e}")
    finally:
        client.close()

# Exemplo de uso e Teste 3.2
if __name__ == '__main__':
    SERVER_PORT = 16000
    SERVER_ADDR = ('127.0.0.1', SERVER_PORT)
    
    # Configuração do canal (perfeito para o teste inicial)
    CHANNEL_CONFIG = {'loss_rate': 0.0, 'corrupt_rate': 0.0, 'delay_range': (0.0, 0.0)}
    
    # Teste 2: Transferência de Dados (10KB)
    data_to_send = b'x' * 10240
    
    print("\n--- INICIANDO TESTE TCP SIMPLIFICADO (10KB) ---")
    
    # Inicia o servidor em uma thread
    server_thread = threading.Thread(target=tcp_server_example, args=(SERVER_PORT, CHANNEL_CONFIG))
    server_thread.start()
    time.sleep(1) # Dá tempo para o servidor iniciar
    
    # Inicia o cliente
    tcp_client_example(SERVER_ADDR, data_to_send, CHANNEL_CONFIG)
    
    # Aguarda o servidor terminar
    server_thread.join()
    
    print("\n--- TESTE CONCLUÍDO ---")
