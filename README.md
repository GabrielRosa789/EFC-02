# EFC 02: Implementação de Transferência Confiável de Dados e TCP sobre UDP

## Descrição do Projeto

Este projeto implementa progressivamente mecanismos de transferência confiável de dados sobre um canal não confiável (UDP), culminando em uma versão simplificada do **TCP (Transmission Control Protocol)**. O trabalho está dividido em três fases, seguindo a progressão teórica apresentada no Capítulo 3 do livro "Redes de Computadores" (Kurose & Ross).

## Estrutura do Projeto

O projeto segue a estrutura de diretórios especificada:

```
projeto_redes/
│
├── fase1/
│ ├── rdt20.py      # Implementação rdt2.0 (Stop-and-Wait com ACK/NAK)
│ ├── rdt21.py      # Implementação rdt2.1 (com Números de Sequência)
│ └── rdt30.py      # Implementação rdt3.0 (com Timer e Perda de Pacotes)
│
├── fase2/
│ └── gbn.py        # Implementação Go-Back-N (GBN)
│
├── fase3/
│ ├── tcp_socket.py # Classe SimpleTCPSocket (TCP Simplificado)
│ ├── tcp_server.py # Aplicação servidor de exemplo
│ └── tcp_client.py # Aplicação cliente de exemplo
│
├── testes/
│ ├── test_fase1.py # Testes para rdt2.0, rdt2.1 e rdt3.0
│ ├── test_fase2.py # Testes para Go-Back-N
│ └── test_fase3.py # Testes para TCP Simplificado
│
├── utils/
│ ├── packet.py     # Estruturas de pacotes (RDT e TCP)
│ ├── simulator.py  # Simulador de Canal Não Confiável
│ └── logger.py     # Sistema de logging
│
├── relatorio/      # Diretório para o relatório final (vazio)
│
└── README.md       # Este arquivo
```

## Pré-requisitos

*   **Python 3.8+**
*   **Sistema Operacional Windows** (para as instruções de `venv`)

## Configuração do Ambiente Virtual (Windows)

É altamente recomendável utilizar um ambiente virtual (`venv`) para isolar as dependências do projeto.

1.  **Navegue até o diretório do projeto:**
    ```bash
    cd projeto_redes
    ```

2.  **Crie o ambiente virtual:**
    ```bash
    python -m venv venv
    ```

3.  **Ative o ambiente virtual (Windows):**
    ```bash
    .\venv\Scripts\activate
    ```
    *(Para sistemas Linux/macOS, o comando seria `source venv/bin/activate`)*

4.  **Instale as dependências:**
    O projeto utiliza apenas bibliotecas padrão do Python (`socket`, `threading`, `time`, `struct`, `hashlib`, `random`, `collections`). No entanto, para garantir a reprodutibilidade, você pode rodar:
    ```bash
    pip install -r requirements.txt
    ```

## Execução do Projeto

Os testes de cada fase foram separados em arquivos dedicados no diretório `testes/`.

### 1. Testando a Fase 1 (RDT)

Execute o arquivo de teste para a Fase 1. Ele rodará os testes para `rdt20.py`, `rdt21.py` e `rdt30.py` em diferentes cenários de canal.

```bash
python testes/test_fase1.py
```

### 2. Testando a Fase 2 (Go-Back-N)

Execute o arquivo de teste para a Fase 2. Ele rodará testes de eficiência e perda para o `gbn.py`.

```bash
python testes/test_fase2.py
```

### 3. Testando a Fase 3 (TCP Simplificado)

O teste da Fase 3 requer que o servidor e o cliente sejam executados em threads separadas (o script `test_fase3.py` gerencia isso automaticamente).

```bash
python testes/test_fase3.py
```

### Execução Manual (Servidor/Cliente TCP)

Para testar o TCP simplificado manualmente, você deve rodar o servidor e o cliente em terminais separados.

**Terminal 1 (Servidor):**
```bash
# Certifique-se de que o venv está ativo
python fase3/tcp_server.py
```

**Terminal 2 (Cliente):**
```bash
# Certifique-se de que o venv está ativo
python fase3/tcp_client.py
```
*(O cliente enviará 10KB de dados para o servidor e ambos encerrarão a conexão.)*

## Configuração do Canal Não Confiável

O simulador de canal (`utils/simulator.py`) permite configurar os parâmetros de perda, corrupção e atraso.

Para alterar os parâmetros de teste, edite a variável `CHANNEL_CONFIG` dentro dos arquivos de teste (`testes/test_faseX.py`).

| Parâmetro | Descrição |
| :--- | :--- |
| `loss_rate` | Probabilidade de perda de pacote (0.0 a 1.0) |
| `corrupt_rate` | Probabilidade de corrupção de pacote (0.0 a 1.0) |
| `delay_range` | Tupla `(min_delay, max_delay)` em segundos |

---
*Implementado por Manus AI*
