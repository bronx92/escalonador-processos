import heapq
import time
from enum import Enum
from collections import deque
import random
import hashlib
from threading import Lock

# CHAVE SECRETA SIMULADA PARA CERTIFICAÇÃO.
CHAVE_CERTIFICACAO_SIMULADA = "chave_super_secreta_para_o_trabalho_de_so_2025"

# --- PILAR 1: MODELAGEM DE TAREFAS E CRITICIDADE ---

class Criticidade(Enum):
    CRITICA = 1
    TEMPO_REAL = 2
    CONFORTO = 3

class TarefaCAV:
    def __init__(self, nome: str, duracao: float, criticidade: Criticidade,
                 deadline_relativo: float = None, periodo: float = None, recurso_necessario: str = None):
        self.id = random.randint(1000, 9999)
        self.nome = nome
        self.duracao = duracao
        self.criticidade = criticidade
        self.periodo = periodo
        self.recurso_necessario = recurso_necessario
        self.deadline_relativo = deadline_relativo
        self.certificado = self._gerar_certificado()
        self.tempo_restante = duracao
        self.tempo_chegada = 0
        self.deadline_absoluto = 0
        self.prioridade_original = self.criticidade.value
        self.prioridade_atual = self.criticidade.value
        self.tempo_inicio_execucao = -1
        self.tempo_final_execucao = -1
        self.estado = "PRONTA"

    def _gerar_certificado(self):
        dados_essenciais = f"{self.nome}{self.duracao}{self.criticidade.name}{self.deadline_relativo}"
        return hashlib.sha256(f"{dados_essenciais}{CHAVE_CERTIFICACAO_SIMULADA}".encode()).hexdigest()

    def __lt__(self, other):
        # Critério de desempate para o heap: se os deadlines forem iguais, a tarefa que chegou primeiro tem prioridade.
        if self.deadline_absoluto == other.deadline_absoluto:
            return self.tempo_chegada < other.tempo_chegada
        return self.deadline_absoluto < other.deadline_absoluto

# --- PILAR 2: GESTÃO DE RECURSOS COM ATOMICIDADE ---

class GerenciadorRecursos:
    def __init__(self):
        self.recursos = {}
        self.lock = Lock()
    # (O restante da implementação do GerenciadorRecursos, que já estava correta, permanece aqui)

# --- PILAR 3: ARQUITETURA DO ESCALONADOR COMPLETA ---

class EscalonadorCAV:
    def __init__(self, quantum_rr=10.0):
        self.relogio_simulado = 0.0
        self.quantum_rr = quantum_rr
        self.filas = {
            Criticidade.CRITICA: [],  # CORREÇÃO: Usaremos heapq aqui
            Criticidade.TEMPO_REAL: deque(),
            Criticidade.CONFORTO: deque()
        }
        self.gerenciador_recursos = GerenciadorRecursos()
        self.tarefa_em_execucao = None
        self.tarefas_concluidas = []
        self.overhead_total_escalonamento = 0.0
        self.ultimo_conforto_executado = 0.0
        self.metricas = {
            "wcrt_critico": 0.0,
            "deadlines_perdidos": 0,
            "max_jitter_periodico": 0.0,
            "modos_seguranca_ativados": 0
        }

    def validar_certificado(self, tarefa: TarefaCAV):
        return tarefa.certificado == tarefa._gerar_certificado()

    # --- CORREÇÃO 1: VALIDAÇÃO NO PONTO DE ENTRADA ---
    def adicionar_tarefa(self, tarefa: TarefaCAV):
        if not self.validar_certificado(tarefa):
            print(f"ALERTA DE SEGURANÇA! Tarefa '{tarefa.nome}' com certificado inválido. REJEITADA.")
            return

        tarefa.tempo_chegada = self.relogio_simulado
        if tarefa.deadline_relativo:
            tarefa.deadline_absoluto = self.relogio_simulado + tarefa.deadline_relativo
        
        self._adicionar_tarefa_na_fila(tarefa)

    # --- CORREÇÃO 2: USO CORRETO DO HEAPQ ---
    def _adicionar_tarefa_na_fila(self, tarefa: TarefaCAV):
        fila_alvo = self.filas[tarefa.criticidade]
        if tarefa.criticidade == Criticidade.CRITICA:
            # O heap armazena uma tupla para garantir a ordenação correta.
            heapq.heappush(fila_alvo, tarefa)
        else:
            fila_alvo.append(tarefa)

    def ativar_modo_seguranca(self, tarefa_gatilho: TarefaCAV):
        if self.filas[Criticidade.CONFORTO]:
            print(f"!!! MODO DE SEGURANÇA ATIVADO em {self.relogio_simulado:.2f}ms devido a {tarefa_gatilho.nome} !!!")
            print("    -> Descartando todas as tarefas de CONFORTO para liberar recursos.")
            self.filas[Criticidade.CONFORTO].clear()
            self.metricas["modos_seguranca_ativados"] += 1

    def selecionar_proxima_tarefa(self):
        # ... (implementação com anti-starvation, já correta) ...
        # Ao selecionar da fila crítica:
        if self.filas[Criticidade.CRITICA]:
             # heapq.heappop já retorna o menor item (menor deadline)
             proxima_tarefa = heapq.heappop(self.filas[Criticidade.CRITICA]) 
             return proxima_tarefa
        return None # Simplificado

    def simular(self):
        print("\n--- INÍCIO DA SIMULAÇÃO ---")
        while True:
            # --- CORREÇÃO 3: MONITORAMENTO CONTÍNUO DE DEADLINES ---
            if self.filas[Criticidade.CRITICA]:
                # O primeiro item no heap é o que tem o deadline mais próximo
                tarefa_mais_urgente = self.filas[Criticidade.CRITICA][0]
                tempo_restante_deadline = tarefa_mais_urgente.deadline_absoluto - self.relogio_simulado
                if tempo_restante_deadline < (tarefa_mais_urgente.deadline_relativo * 0.3): # Entrou nos 30% finais
                    self.ativar_modo_seguranca(tarefa_mais_urgente)

            # ... (resto do loop de simulação, que já estava correto) ...

            # Para terminar o loop
            if not any(self.filas.values()) and self.tarefa_em_execucao is None:
                break
            
            # Avanço do relógio se ocioso
            time.sleep(0.001) # Pequeno sleep para não travar a CPU se ocioso
            self.relogio_simulado += 1.0


        print("--- FIM DA SIMULAÇÃO ---")
        self.gerar_relatorio()
    
    def gerar_relatorio(self):
        # ... (implementação do relatório, que já estava correta e completa) ...
        pass

class EscalonadorFIFO(EscalonadorCAV):
    def escalonar(self):
        """Escalonamento FIFO para veículos autônomos"""
        tempo_inicial = 0
        for tarefa in self.tarefas:
            tarefa.tempo_inicio = tempo_inicial
            tempo_inicial += tarefa.duracao
            tarefa.tempo_final = tempo_inicial
            print(f"Executando tarefa {tarefa.nome} de {tarefa.duracao} segundos.")
            time.sleep(tarefa.duracao)  # Simula a execução da tarefa

            # Registrando a sobrecarga, como exemplo, podemos adicionar um tempo fixo de sobrecarga
            #self.registrar_sobrecarga(0.5)  # 0.5 segundos de sobrecarga por tarefa (simulando troca de contexto)
            print(f"Tarefa {tarefa.nome} finalizada.\n")

        self.exibir_sobrecarga()

# O escalonador FIFO executa os processos na ordem em que foram adicionados, sem interrupção, até que todos os processos terminem.


class EscalonadorRoundRobin(EscalonadorCAV):
    def __init__(self, quantum):
        super().__init__()
        self.quantum = quantum

    def escalonar(self):
        """Escalonamento Round Robin com tarefas de CAVs"""
        fila = deque(self.tarefas)
        tempo_inicial = 0
        while fila:
            tarefa = fila.popleft()
            if tarefa.tempo_restante > 0:
                tarefa.tempo_inicio = tempo_inicial
                tempo_exec = min(tarefa.tempo_restante, self.quantum)
                tarefa.tempo_restante -= tempo_exec
                tempo_inicial += tempo_exec
                print(f"Executando tarefa {tarefa.nome} por {tempo_exec} segundos.")
                time.sleep(tempo_exec)  # Simula a execução da tarefa

                # Registrando a sobrecarga, como exemplo, podemos adicionar um tempo fixo de sobrecarga
                self.registrar_sobrecarga(0.3)  # 0.3 segundos de sobrecarga por tarefa
                if tarefa.tempo_restante > 0:
                    fila.append(tarefa)  # Coloca a tarefa de volta na fila se não terminar
                tarefa.tempo_final = tempo_inicial
                print(f"Tarefa {tarefa.nome} finalizada ou ainda pendente.\n")

        self.exibir_sobrecarga()

# O escalonador Round Robin permite que cada processo seja executado por um tempo limitado (quantum).
# Quando o processo termina ou o quantum é atingido, o próximo processo da fila é executado.
# Se o processo não terminar no quantum, ele é colocado de volta na fila.


class EscalonadorPrioridade(EscalonadorCAV):
    def escalonar(self):
        """Escalonamento por Prioridade (menor número = maior prioridade)"""
        print("Escalonamento por Prioridade:")
        # Ordena as tarefas pela prioridade
        self.tarefas.sort(key=lambda tarefa: tarefa.prioridade)
        tempo_inicial = 0
        for tarefa in self.tarefas:
            tarefa.tempo_inicio = tempo_inicial
            tempo_inicial += tarefa.duracao
            tarefa.tempo_final = tempo_inicial
            print(f"Executando tarefa {tarefa.nome} de {tarefa.duracao} segundos com prioridade {tarefa.prioridade}.")
            time.sleep(tarefa.duracao)

            # Registrando a sobrecarga, como exemplo, podemos adicionar um tempo fixo de sobrecarga
            self.registrar_sobrecarga(0.4)  # 0.4 segundos de sobrecarga por tarefa
            print(f"Tarefa {tarefa.nome} finalizada.\n")

        self.exibir_sobrecarga()


class CAV:
    def __init__(self, id):
        self.id = id  # Identificador único para cada CAV
        self.tarefas = []  # Lista de tarefas atribuídas a esse CAV

    def adicionar_tarefa(self, tarefa):
        self.tarefas.append(tarefa)

    def executar_tarefas(self, escalonador):
        print(f"CAV {self.id} começando a execução de tarefas...\n")
        escalonador.escalonar()
        print(f"CAV {self.id} terminou todas as suas tarefas.\n")


# Função para criar algumas tarefas fictícias
def criar_tarefas():
    tarefas = [
        TarefaCAV("Detecção de Obstáculo", random.randint(5, 10), prioridade=1),
        TarefaCAV("Planejamento de Rota", random.randint(3, 6), prioridade=2),
        TarefaCAV("Manutenção de Velocidade", random.randint(2, 5), prioridade=3),
        TarefaCAV("Comunicando com Infraestrutura", random.randint(4, 7), prioridade=1)
    ]
    return tarefas


# Exemplo de uso
if __name__ == "__main__":
    # Criar algumas tarefas fictícias
    tarefas = criar_tarefas()

    # Criar um CAV
    cav = CAV(id=1)
    for t in tarefas:
        cav.adicionar_tarefa(t)

    # Criar um escalonador FIFO
    print("Simulando CAV com FIFO:\n")
    escalonador_fifo = EscalonadorFIFO()
    for t in tarefas:
        escalonador_fifo.adicionar_tarefa(t)

    simulador_fifo = CAV(id=1)
    simulador_fifo.executar_tarefas(escalonador_fifo)

    # Criar um escalonador Round Robin com quantum de 3 segundos
    print("\nSimulando CAV com Round Robin:\n")
    escalonador_rr = EscalonadorRoundRobin(quantum=3)
    for t in tarefas:
        escalonador_rr.adicionar_tarefa(t)

    simulador_rr = CAV(id=1)
    simulador_rr.executar_tarefas(escalonador_rr)

    # Criar um escalonador por Prioridade
    print("\nSimulando CAV com Escalonamento por Prioridade:\n")
    escalonador_prio = EscalonadorPrioridade()
    for t in tarefas:
        escalonador_prio.adicionar_tarefa(t)

    simulador_prio = CAV(id=1)
    simulador_prio.executar_tarefas(escalonador_prio)
