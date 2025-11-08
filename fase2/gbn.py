import socket
import threading
import time
import struct
import hashlib
from utils.logger import log_info, log_error
from utils.simulator import UnreliableChannel

BUFFER_SIZE = 65535
TIMEOUT = 1.0
SEQ_NUM_SPACE = 2**32
GBN_HEADER_FORMAT = '!B I I'
GBN_HEADER_SIZE = struct.calcsize(GBN_HEADER_FORMAT)
TYPE_DATA = 0
TYPE_ACK = 1


class GBNPacket:
    def __init__(self, type, seq_num, data=b''):
        self.type = type
        self.seq_num = seq_num
        self.data = data
        self.checksum = self._calc_checksum()

    def _calc_checksum(self):
        header = struct.pack('!B I', self.type, self.seq_num)
        return int(hashlib.md5(header + self.data).hexdigest(), 16) & 0xFFFFFFFF

    def to_bytes(self):
        self.checksum = self._calc_checksum()
        return struct.pack(GBN_HEADER_FORMAT, self.type, self.seq_num, self.checksum) + self.data

    @classmethod
    def from_bytes(cls, raw):
        if len(raw) < GBN_HEADER_SIZE:
            return None
        type, seq_num, checksum = struct.unpack(GBN_HEADER_FORMAT, raw[:GBN_HEADER_SIZE])
        data = raw[GBN_HEADER_SIZE:]
        pkt = cls(type, seq_num, data)
        pkt.is_corrupt = pkt._calc_checksum() != checksum
        pkt.checksum = checksum
        return pkt


class GBNSender:
    def __init__(self, local_port, remote_addr, channel_params, window_size=5):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(('0.0.0.0', local_port))
        self.remote_addr = remote_addr
        self.channel = UnreliableChannel(**channel_params)
        self.base = 0
        self.nextseqnum = 0
        self.window_size = window_size
        self.send_buffer = {}
        self.timer = None
        self.lock = threading.Lock()
        self.is_running = True
        self.retransmission_count = 0
        self.thread = threading.Thread(target=self._recv_ack_loop)
        log_info(f"Sender iniciado na porta {local_port} (Janela={self.window_size})", "GBN")

    def _start_timer(self):
        if self.timer:
            self.timer.cancel()
        self.timer = threading.Timer(TIMEOUT, self._timeout)
        self.timer.start()

    def _stop_timer(self):
        if self.timer:
            self.timer.cancel()
            self.timer = None

    def _timeout(self):
        with self.lock:
            if not self.is_running:
                return
            log_info(f"Timeout! Retransmitindo janela base={self.base}", "GBN-SENDER")
            self.retransmission_count += (self.nextseqnum - self.base)
            for seq in range(self.base, self.nextseqnum):
                pkt = self.send_buffer.get(seq % SEQ_NUM_SPACE)
                if pkt:
                    self._udt_send(pkt)
            self._start_timer()

    def _recv_ack_loop(self):
        while self.is_running:
            try:
                raw, _ = self.socket.recvfrom(65535)
                pkt = GBNPacket.from_bytes(raw)
                if not pkt or pkt.is_corrupt or pkt.type != TYPE_ACK:
                    continue
                with self.lock:
                    ack = pkt.seq_num
                    if ack > self.base:
                        log_info(f"ACK({ack}) recebido. Base {self.base} → {ack}", "GBN-SENDER")
                        for s in range(self.base, ack):
                            self.send_buffer.pop(s % SEQ_NUM_SPACE, None)
                        self.base = ack
                        if self.base == self.nextseqnum:
                            self._stop_timer()
                        else:
                            self._start_timer()
            except OSError as e:
                if getattr(e, "winerror", None) == 10040:
                    log_error("ACK maior que buffer do socket. Ignorado com segurança.", "GBN-SENDER")
                    continue
                else:
                    if self.is_running:
                        log_error(f"Erro no loop de ACK: {e}", "GBN-SENDER")
            except Exception as e:
                if self.is_running:
                    log_error(f"Erro no loop de ACK: {e}", "GBN-SENDER")

    def rdt_send(self, data):
        while True:
            with self.lock:
                if self.nextseqnum < self.base + self.window_size:
                    break
            time.sleep(0.01)
        with self.lock:
            seq = self.nextseqnum % SEQ_NUM_SPACE
            pkt = GBNPacket(TYPE_DATA, seq, data)
            self.send_buffer[seq] = pkt
            self._udt_send(pkt)
            if self.base == self.nextseqnum:
                self._start_timer()
            self.nextseqnum += 1

    def _udt_send(self, pkt):
        self.channel.send(pkt.to_bytes(), self.socket, self.remote_addr)

    def start(self):
        self.thread.start()

    def close(self):
        self.is_running = False
        self._stop_timer()
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.sendto(b'stop', ('127.0.0.1', self.socket.getsockname()[1]))
        s.close()
        self.thread.join()
        self.socket.close()
        log_info("Sender encerrado.", "GBN")


class GBNReceiver:
    def __init__(self, local_port, remote_addr, channel_params):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 262144)
        self.socket.bind(('0.0.0.0', local_port))
        self.remote_addr = remote_addr
        self.channel = UnreliableChannel(**channel_params)
        self.expected = 0
        self.received_data = []
        self.lock = threading.Lock()
        self.is_running = True
        self.thread = threading.Thread(target=self._recv_loop)
        log_info(f"Receiver iniciado na porta {local_port}", "GBN")

    def start(self):
        self.thread.start()

    def _recv_loop(self):
        while self.is_running:
            try:
                raw, _ = self.socket.recvfrom(65535)

                # segurança: truncar pacotes fora do limite
                if len(raw) > 65507:
                    log_error(f"Pacote de {len(raw)} bytes truncado (acima do limite UDP).", "GBN-RECEIVER")
                    raw = raw[:65507]

                pkt = GBNPacket.from_bytes(raw)
                if not pkt:
                    continue

                with self.lock:
                    if pkt.is_corrupt:
                        log_info("Pacote corrompido, reenviando ACK anterior", "GBN-RECEIVER")
                        self._send_ack((self.expected - 1) % SEQ_NUM_SPACE)
                    elif pkt.seq_num == self.expected:
                        log_info(f"DATA({pkt.seq_num}) recebido corretamente", "GBN-RECEIVER")
                        self.received_data.append(pkt.data)
                        self.expected += 1
                        self._send_ack(self.expected)
                    else:
                        log_info(f"DATA({pkt.seq_num}) fora de ordem", "GBN-RECEIVER")
                        self._send_ack((self.expected - 1) % SEQ_NUM_SPACE)

            except OSError as e:
                if getattr(e, "winerror", None) == 10040:
                    log_error("Pacote excedeu buffer do socket. Ignorado com segurança.", "GBN-RECEIVER")
                    continue
                else:
                    if self.is_running:
                        log_error(f"Erro no loop de recepção: {e}", "GBN-RECEIVER")
            except Exception as e:
                if self.is_running:
                    log_error(f"Erro inesperado: {e}", "GBN-RECEIVER")

    def _send_ack(self, num):
        ack = GBNPacket(TYPE_ACK, num)
        self.channel.send(ack.to_bytes(), self.socket, self.remote_addr)

    def get_received_data(self):
        return self.received_data

    def close(self):
        self.is_running = False
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.sendto(b'stop', ('127.0.0.1', self.socket.getsockname()[1]))
        s.close()
        self.thread.join()
        self.socket.close()
        log_info("Receiver encerrado.", "GBN")
   