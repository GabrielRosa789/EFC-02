#implementação do protocolo rdt2.0
import socket
import hashlib
import threading
import time
import random

# --------------------------
# Funções auxiliares
# --------------------------

def checksum(data: bytes) -> str:
    """Calcula o checksum (MD5 simples) dos dados"""
    return hashlib.md5(data).hexdigest()
  #Essa função cria uma assinatura digital (Hash) dos dados.
  #Serve para verificar se o conteúdo foi alterado durante a transmissão.
  #Se o dado mudar (mesmo 1 bit), o checksum será diferente.

def make_packet(packet_type: int, data: bytes) -> bytes:
    chksum = checksum(data).encode()
    return bytes([packet_type]) + chksum + data
  """
    Essa função cria um pacote no formato:
    +--------+--------------+------------------+
    | Tipo   | Checksum(32) | Dados (variável) |
    +--------+--------------+------------------+
    Tipo: 0=DATA, 1=ACK, 2=NAK
    """

def parse_packet(packet: bytes):
    """Lê o tipo, checksum e dados de um pacote recebido"""
    packet_type = packet[0]
    recv_checksum = packet[1:33].decode()
    data = packet[33:]
    return packet_type, recv_checksum, data

# --------------------------
# Classes principais
# --------------------------

class RDT20Sender:
    def __init__(self, dest_ip, dest_port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.dest = (dest_ip, dest_port)

    def send(self, message: str):
        data = message.encode()
        pkt = make_packet(0, data)
        self.sock.sendto(pkt, self.dest)

        print(f"[Sender] Enviado: {message}")

        # Espera ACK ou NAK
        response, _ = self.sock.recvfrom(1024)
        pkt_type, recv_chksum, _ = parse_packet(response)

        if pkt_type == 1:
            print("[Sender] ACK recebido. OK.")
        elif pkt_type == 2:
            print("[Sender] NAK recebido. Reenviando...")
            self.sock.sendto(pkt, self.dest)

class RDT20Receiver:
    def __init__(self, listen_port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("localhost", listen_port))

    def receive(self):
        packet, addr = self.sock.recvfrom(4096)
        pkt_type, recv_chksum, data = parse_packet(packet)

        if recv_chksum != checksum(data):
            print("[Receiver] Pacote corrompido! Enviando NAK.")
            nak = make_packet(2, b'')
            self.sock.sendto(nak, addr)
        else:
            print(f"[Receiver] Recebido: {data.decode()}")
            ack = make_packet(1, b'')
            self.sock.sendto(ack, addr)

