import struct
import hashlib
import random

# Constantes para Tipos de Pacote
TYPE_DATA = 0
TYPE_ACK = 1
TYPE_NAK = 2
TYPE_SYN = 3
TYPE_SYN_ACK = 4
TYPE_FIN = 5

# Formato do cabeçalho rdt (Tipo, SeqNum, Checksum)
# Tipo: 1 byte (B), SeqNum: 1 byte (B), Checksum: 4 bytes (I)
RDT_HEADER_FORMAT = '!BB I'
RDT_HEADER_SIZE = struct.calcsize(RDT_HEADER_FORMAT)

# Formato do cabeçalho TCP simplificado
# Source Port (H), Dest Port (H), Seq Num (I), Ack Num (I), Header Len (B), Flags (B), Window Size (H), Checksum (H), Urgent Ptr (H)
TCP_HEADER_FORMAT = '!HH II B B H H H'
TCP_HEADER_SIZE = struct.calcsize(TCP_HEADER_FORMAT)

class RDTPacket:
    def __init__(self, type, seq_num, data=b''):
        self.type = type
        self.seq_num = seq_num
        self.data = data
        self.checksum = self._calculate_checksum()

    def _calculate_checksum(self):
        # Calcula o checksum do cabeçalho (sem o campo checksum) + dados
        # Usaremos um hash MD5 simples para simular o checksum
        header_without_checksum = struct.pack('!BB', self.type, self.seq_num)
        data_to_hash = header_without_checksum + self.data
        return int(hashlib.md5(data_to_hash).hexdigest(), 16) & 0xFFFFFFFF

    def to_bytes(self):
        # Recalcula o checksum antes de empacotar
        self.checksum = self._calculate_checksum()
        header = struct.pack(RDT_HEADER_FORMAT, self.type, self.seq_num, self.checksum)
        return header + self.data

    @classmethod
    def from_bytes(cls, raw_bytes):
        if len(raw_bytes) < RDT_HEADER_SIZE:
            return None # Pacote incompleto

        header_bytes = raw_bytes[:RDT_HEADER_SIZE]
        data = raw_bytes[RDT_HEADER_SIZE:]

        try:
            type, seq_num, received_checksum = struct.unpack(RDT_HEADER_FORMAT, header_bytes)
        except struct.error:
            return None # Erro de desempacotamento

        # Cria um pacote temporário para verificar o checksum
        temp_packet = cls(type, seq_num, data)
        
        # Retorna o pacote com o checksum recebido para que o receptor possa verificar
        packet = cls(type, seq_num, data)
        packet.checksum = received_checksum
        return packet

    def is_corrupt(self):
        # Verifica se o checksum recebido é igual ao checksum calculado
        return self.checksum != self._calculate_checksum()

    def __repr__(self):
        return f"RDTPacket(Type={self.type}, SeqNum={self.seq_num}, DataLen={len(self.data)}, Corrupt={self.is_corrupt()})"

class TCPSegment:
    def __init__(self, src_port, dest_port, seq_num, ack_num, flags, window_size, data=b''):
        self.src_port = src_port
        self.dest_port = dest_port
        self.seq_num = seq_num
        self.ack_num = ack_num
        self.header_len = TCP_HEADER_SIZE // 4 # Em palavras de 4 bytes
        self.flags = flags
        self.window_size = window_size
        self.data = data
        self.checksum = 0 # O checksum será calculado no to_bytes

    def _calculate_checksum(self):
        # Simplificação: Apenas um hash MD5 dos campos importantes + dados
        # Em um TCP real, o checksum é mais complexo (pseudo-cabeçalho + cabeçalho + dados)
        data_to_hash = struct.pack('!HH II B B H H', 
                                   self.src_port, self.dest_port, 
                                   self.seq_num, self.ack_num, 
                                   self.header_len, self.flags, 
                                   self.window_size, 0) # Checksum temporário 0
        data_to_hash += self.data
        return int(hashlib.md5(data_to_hash).hexdigest(), 16) & 0xFFFF

    def to_bytes(self):
        self.checksum = self._calculate_checksum()
        header = struct.pack(TCP_HEADER_FORMAT, 
                             self.src_port, self.dest_port, 
                             self.seq_num, self.ack_num, 
                             self.header_len, self.flags, 
                             self.window_size, self.checksum, 
                             0) # Urgent Ptr
        return header + self.data

    @classmethod
    def from_bytes(cls, raw_bytes):
        if len(raw_bytes) < TCP_HEADER_SIZE:
            return None

        header_bytes = raw_bytes[:TCP_HEADER_SIZE]
        data = raw_bytes[TCP_HEADER_SIZE:]

        try:
            (src_port, dest_port, seq_num, ack_num, header_len, flags, 
             window_size, received_checksum, urgent_ptr) = struct.unpack(TCP_HEADER_FORMAT, header_bytes)
        except struct.error:
            return None

        # Cria um segmento temporário para verificar o checksum
        temp_segment = cls(src_port, dest_port, seq_num, ack_num, flags, window_size, data)
        
        is_corrupt = temp_segment._calculate_checksum() != received_checksum
        
        # Retorna o segmento com o checksum recebido
        segment = cls(src_port, dest_port, seq_num, ack_num, flags, window_size, data)
        segment.checksum = received_checksum
        segment.is_corrupt = is_corrupt
        
        return segment

    def is_corrupt(self):
        return self.checksum != self._calculate_checksum()

    def __repr__(self):
        flags_str = []
        if self.flags & (1 << 0): flags_str.append('FIN')
        if self.flags & (1 << 1): flags_str.append('SYN')
        if self.flags & (1 << 4): flags_str.append('ACK')
        
        return f"TCPSegment(Src={self.src_port}, Dest={self.dest_port}, Seq={self.seq_num}, Ack={self.ack_num}, Flags={'-'.join(flags_str)}, Win={self.window_size}, DataLen={len(self.data)}, Corrupt={self.is_corrupt()})"

# Funções auxiliares para flags TCP
def set_flag(flags, flag_bit):
    return flags | (1 << flag_bit)

def is_flag_set(flags, flag_bit):
    return (flags & (1 << flag_bit)) != 0

# Bit positions (do menos significativo para o mais significativo)
FIN_BIT = 0
SYN_BIT = 1
ACK_BIT = 4
