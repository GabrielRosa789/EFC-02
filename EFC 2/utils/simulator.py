import random
import threading
import time

MAX_PACKET_SIZE = 65507  # Limite real do UDP
HEADER_OVERHEAD = 64     # Margem de segurança

class UnreliableChannel:
    def __init__(self, loss_rate=0.0, corrupt_rate=0.0, delay_range=(0.0, 0.0)):
        self.loss_rate = loss_rate
        self.corrupt_rate = corrupt_rate
        self.delay_range = delay_range
        print(f"[SIMULADOR] Canal inicializado: Perda={loss_rate*100:.1f}%, Corrupção={corrupt_rate*100:.1f}%, Atraso={delay_range[0]:.3f}-{delay_range[1]:.3f}s")

    def send(self, packet_bytes, dest_socket, dest_addr):
        """Divide e envia pacotes grandes de forma segura."""
        if random.random() < self.loss_rate:
            print(f"[SIMULADOR] Pacote para {dest_addr} PERDIDO.")
            return

        # Quebra o pacote em pedaços menores que o limite UDP
        fragments = []
        for i in range(0, len(packet_bytes), MAX_PACKET_SIZE - HEADER_OVERHEAD):
            frag = packet_bytes[i:i + (MAX_PACKET_SIZE - HEADER_OVERHEAD)]
            fragments.append(frag)

        for frag in fragments:
            # Corrupção simulada
            if random.random() < self.corrupt_rate:
                frag = self._corrupt_packet(frag)
                print(f"[SIMULADOR] Fragmento CORROMPIDO ({len(frag)} bytes).")

            delay = random.uniform(*self.delay_range)
            if delay > 0:
                print(f"[SIMULADOR] Atrasando fragmento {len(frag)} bytes por {delay:.3f}s.")

            threading.Timer(delay, lambda f=frag: self._safe_send(dest_socket, f, dest_addr)).start()

    def _safe_send(self, sock, frag, addr):
        try:
            if len(frag) > MAX_PACKET_SIZE:
                frag = frag[:MAX_PACKET_SIZE]
            sock.sendto(frag, addr)
        except Exception as e:
            print(f"[SIMULADOR] Erro ao enviar fragmento: {e}")

    def _corrupt_packet(self, packet):
        if not packet:
            return packet
        p = bytearray(packet)
        i = random.randint(0, len(p) - 1)
        p[i] ^= 1 << random.randint(0, 7)
        return bytes(p)
