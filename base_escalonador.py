import heapq
import time
from enum import Enum
from collections import deque
import random
import hashlib
from threading import Lock
from abc import ABC, abstractmethod

# CHAVE SECRETA SIMULADA PARA CERTIFICAÇÃO.
CHAVE_CERTIFICACAO_SIMULADA = "chave_super_secreta_para_o_trabalho_de_so_2025"

# --- PILAR 1: MODELAGEM DE TAREFAS E CRITICIDADE ---

class Criticidade(Enum):
    """Define a hierarquia de criticidade das tarefas, um ponto central da nossa análise."""
    CRITICA = 1  # Segurança: freio, direção. Deadlines rígidos, não pode falhar.
    TEMPO_REAL = 2  # Operacional: navegação, V2X. Deadlines importantes, mas com alguma tolerância.
    CONFORTO = 3  # Não essencial: entretenimento, logs. Sem deadline rígido.

class DeadlinePerdidoError(Exception):
    """Exceção customizada para quando uma tarefa crítica perde seu deadline."""
    pass   

class TarefaCAV:
    """
    Representa uma tarefa no sistema do Veículo Autônomo Conectado.
    Esta classe consolidada inclui todos os campos que consideramos essenciais.
    """
    def __init__(self, nome: str, duracao: float, criticidade: Criticidade,
                 deadline_relativo: float = None, periodo: float = None, recurso_necessario: str = None):
        self.id = random.randint(1000, 9999)
        self.nome = nome
        self.duracao = duracao  # Tempo total de execução (em ms)
        self.criticidade = criticidade
        self.periodo = periodo  # Intervalo para tarefas periódicas (ms)
        self.recurso_necessario = recurso_necessario
        self.deadline_relativo = deadline_relativo
        self.certificado = self._gerar_certificado()

        # Atributos de estado e tempo
        self.tempo_restante = duracao
        self.tempo_chegada = 0  # Será definido pelo relógio no momento da adição
        self.deadline_absoluto = 0 # Será definido pelo relógio
        if deadline_relativo:
            self.deadline_relativo = deadline_relativo

        # Atributos para Herança de Prioridade
        self.prioridade_original = self.criticidade.value
        self.prioridade_atual = self.criticidade.value

        # Atributos para métricas
        self.tempo_inicio_execucao = -1
        self.tempo_final_execucao = -1
        self.tempo_total_espera = 0
        self.estado = "PRONTA" # PRONTA, EXECUTANDO, BLOQUEADA, CONCLUIDA

    def _gerar_certificado(self):
        dados_essenciais = f"{self.nome}{self.duracao}{self.criticidade.name}{self.deadline_relativo}"
        return hashlib.sha256(f"{dados_essenciais}{CHAVE_CERTIFICACAO_SIMULADA}".encode()).hexdigest()

    def __lt__(self, other):
        # Critério de desempate para o heap: se os deadlines forem iguais, a tarefa que chegou primeiro tem prioridade.
        if self.deadline_absoluto == other.deadline_absoluto:
            return self.tempo_chegada < other.tempo_chegada
        return self.deadline_absoluto < other.deadline_absoluto

    def __str__(self):
        return f"Tarefa(ID: {self.id}, Nome: {self.nome}, Crit: {self.criticidade.name})"

# ==============================================================================
# GESTÃO DE RECURSOS COM ATOMICIDADE
# ==============================================================================

class GerenciadorRecursos:
    """
    Controla o acesso a recursos compartilhados e implementa o Protocolo de
    Herança de Prioridade (PIP) para evitar a inversão de prioridade.
    """
    def __init__(self):
        self.recursos = {} # Dicionário para armazenar o estado de cada recurso
        # --- CORREÇÃO 3: ADICIONAR LOCK PARA ATOMICIDADE ---
        self.lock = Lock()
        self.tarefas_bloqueadas = {}    # TarefaID: {"recurso": str, "tempo_bloqueio": float}
        self.recursos_alocados = {}     # Recurso: (tarefa, tempo_alocação)
        self.TIMEOUT_RECURSO = 50.0

    def adicionar_tarefa_bloqueada(self, tarefa: TarefaCAV, recurso: str):
        """Registra uma tarefa como bloqueada e inicia seu timeout"""
        # Criar estrutura para rastrear tarefas bloqueadas
        if not hasattr(self, 'tarefas_bloqueadas'):
            self.tarefas_bloqueadas = {}
        
        # Registrar tempo de bloqueio para controle de timeout
        self.tarefas_bloqueadas[tarefa.id] = {
            "tempo_bloqueio": time.perf_counter_ns(),
            "recurso": recurso
        }
        


    def verificar_timeouts(self, tempo_atual):
        """Verifica timeouts tanto para recursos alocados quanto para tarefas bloqueadas"""
        # 1. Timeout para posse de recursos
        for recurso, (tarefa, tempo_posse) in list(self.recursos_alocados.items()):
            if tempo_atual - tempo_posse > self.TIMEOUT_RECURSO:
                self.liberar(recurso, tarefa)
                tarefa.estado = "PRONTA"
                print(f"⏰ [TIMEOUT] Recurso {recurso} liberado de '{tarefa.nome}'")
        
        # 2. Timeout para tarefas bloqueadas
        if hasattr(self, 'tarefas_bloqueadas'):
            for tarefa_id, info in list(self.tarefas_bloqueadas.items()):
                if tempo_atual - info["tempo_bloqueio"] > self.TIMEOUT_RECURSO:
                    # Forçar liberação do recurso
                    recurso = info["recurso"]
                    if recurso in self.recursos:
                        dono_atual = self.recursos[recurso]["dono"]
                        if dono_atual:
                            self.liberar(recurso, dono_atual)
                            dono_atual.estado = "PRONTA"
                    
                    # Reativar tarefa bloqueada
                    del self.tarefas_bloqueadas[tarefa_id]
                    print(f"⏰ [TIMEOUT] Tarefa {tarefa_id} reativada após espera por {recurso}")
                    return True
        return False    

    
    
    def solicitar(self, tarefa: TarefaCAV, nome_recurso: str, escalonador):
        with self.lock: # Garante que a verificação e alocação sejam atômicas
            if nome_recurso not in self.recursos:
                self.recursos[nome_recurso] = {"dono": None, "fila_espera": []}
                
            recurso = self.recursos[nome_recurso]
            if recurso["dono"] is None:
                recurso["dono"] = tarefa
                tarefa.estado = "EXECUTANDO"

                # Registrar tempo de posse para controle de timeout
                if not hasattr(self, 'recursos_alocados'):
                    self.recursos_alocados = {}
                self.recursos_alocados[nome_recurso] = (tarefa, time.perf_counter_ns())

                return True
            else:
                # Recurso está ocupado, tarefa é bloqueada
                self.adicionar_tarefa_bloqueada(tarefa, nome_recurso)
                heapq.heappush(recurso["fila_espera"], (tarefa.prioridade_atual, tarefa.tempo_chegada, tarefa))
                
                # **Lógica da Herança de Prioridade**
                if tarefa.prioridade_atual < recurso["dono"].prioridade_atual:
                    print(f"    [HERANÇA DE PRIORIDADE] Tarefa '{recurso['dono'].nome}' herda prioridade de '{tarefa.nome}'")
                    recurso["dono"].prioridade_atual = tarefa.prioridade_atual
                return False

    def liberar(self, tarefa: TarefaCAV, nome_recurso: str):
        with self.lock:
            if nome_recurso not in self.recursos:
                return

            recurso = self.recursos[nome_recurso]
            tarefa.prioridade_atual = tarefa.prioridade_original

            if recurso["fila_espera"]:
                _, _, proxima_tarefa = heapq.heappop(recurso["fila_espera"])
                recurso["dono"] = proxima_tarefa
                proxima_tarefa.estado = "PRONTA" # A tarefa é desbloqueada
                print(f"    [RECURSO] '{tarefa.nome}' liberou '{nome_recurso}'. '{proxima_tarefa.nome}' foi desbloqueada.")
                # Remover do controle de timeout
                if nome_recurso in self.recursos_alocados:
                    del self.recursos_alocados[nome_recurso]
                recurso["dono"] = None

# ==============================================================================
# ARQUITETURA DO ESCALONADOR (COM MÉTRICAS E SEGURANÇA)
# ==============================================================================

# 3. Sistema de Mensagens
class MensagensSistema:
    ERRO_DEADLINE = "[CRÍTICO] Tarefa {nome} sem deadline válido"
    ALERTA_TIMEOUT = "[SEGURANÇA] Recurso {recurso} liberado por timeout"
    INFO_MODO_SEGURANCA = "[SISTEMA] Ativado modo segurança"

class Escalonador:
    def __init__(self, estrategias_por_criticidade: dict, quantum_rr=10.0):
        """
        Inicializador da classe unificada de Escalonador.
        Recebe as estratégias e configurações da simulação.
        """
        # --- Atributos de Configuração ---
        self.quantum_rr = quantum_rr
        self.estrategias = estrategias_por_criticidade

        # --- Atributos de Estado da Simulação ---
        self.relogio_simulado = 0.0
        self.tarefa_em_execucao = None
        self.tarefas_concluidas = []
        self.tarefas_periodicas_template = []
        
        # --- Inicialização das Filas (lógica corrigida) ---
        self.filas = {}
        for criticidade, estrategia in self.estrategias.items():
            if isinstance(estrategia, (EstrategiaRoundRobin, EstrategiaFIFO)):
                self.filas[criticidade] = deque()
            else:
                self.filas[criticidade] = []

        # --- Outros Componentes e Métricas ---
        self.gerenciador_recursos = GerenciadorRecursos()
        self.overhead_total_escalonamento = 0.0
        self.metricas = {
            "wcrt_critico": 0.0,
            "deadlines_perdidos": 0,
            "max_jitter_periodico": 0.0,
            "modos_seguranca_ativados": 0
        }

    def adicionar_tarefa(self, tarefa: TarefaCAV):
        # Lógica de adicionar tarefa (já corrigida, sem 'super')
        tarefa.tempo_chegada = self.relogio_simulado
        if tarefa.deadline_relativo:
            tarefa.deadline_absoluto = self.relogio_simulado + tarefa.deadline_relativo
        
        # Adiciona na fila usando a estratégia correta
        estrategia = self.estrategias[tarefa.criticidade]
        fila = self.filas[tarefa.criticidade]
        estrategia.adicionar(fila, tarefa)
        
        if tarefa.periodo is not None:
            # ... (lógica de tarefas periódicas, pode manter se quiser) ...
            pass

    def _adicionar_tarefa_na_fila(self, tarefa: 'TarefaCAV'):
        """
        Método auxiliar que delega a adição de uma tarefa à sua fila
        correspondente, usando a estratégia de enfileiramento correta.
        """
        if tarefa.estado != "CONCLUIDA":
            tarefa.estado = "PRONTA" # Garante que a tarefa volte ao estado PRONTA
            
        estrategia = self.estrategias[tarefa.criticidade]
        fila = self.filas[tarefa.criticidade]
        estrategia.adicionar(fila, tarefa)

    def selecionar_proxima_tarefa(self):
        # Lógica de seleção (já corrigida, usando as estratégias)
        inicio_selecao = time.perf_counter_ns()
        for nivel in [Criticidade.CRITICA, Criticidade.TEMPO_REAL, Criticidade.CONFORTO]:
            fila = self.filas[nivel]
            if fila:
                estrategia = self.estrategias[nivel]
                tarefa = estrategia.selecionar(fila)
                if tarefa:
                    if tarefa.estado != "BLOQUEADA":
                        fim_selecao = time.perf_counter_ns()
                        self.overhead_total_escalonamento += (fim_selecao - inicio_selecao) / 1e6
                        return tarefa
                    else:
                        estrategia.adicionar(fila, tarefa)
        fim_selecao = time.perf_counter_ns()
        self.overhead_total_escalonamento += (fim_selecao - inicio_selecao) / 1e6
        return None

    # Dentro da sua classe unificada 'Escalonador'

    # Na classe Escalonador, substitua o método simular por este:

    def simular(self, cenario_de_teste): # Agora recebe o cenário como argumento
        """
        Versão final do motor de simulação, agora orientado a eventos,
        capaz de adicionar tarefas dinamicamente ao longo do tempo.
        """
        print("\n--- INÍCIO DA SIMULAÇÃO ---")
        
        # Copia o cenário para não modificar o original
        proximas_tarefas_a_chegar = deque(cenario_de_teste)

        while any(self.filas.values()) or self.tarefa_em_execucao or proximas_tarefas_a_chegar:
            
            # Adiciona novas tarefas baseadas no relógio da simulação
            while proximas_tarefas_a_chegar and self.relogio_simulado >= proximas_tarefas_a_chegar[0][0]:
                _, tarefa_para_adicionar = proximas_tarefas_a_chegar.popleft()
                print(f"Tempo: {self.relogio_simulado:6.2f} ms | [CHEGADA] Tarefa '{tarefa_para_adicionar.nome}' entrou no sistema.")
                self.adicionar_tarefa(tarefa_para_adicionar)

            # O resto da lógica de simulação permanece a mesma...
            nova_tarefa = self.selecionar_proxima_tarefa()

            # Lógica de preempção, etc...
            if nova_tarefa and self.tarefa_em_execucao:
                if nova_tarefa.prioridade_atual < self.tarefa_em_execucao.prioridade_atual:
                    print(f"Tempo: {self.relogio_simulado:6.2f} ms | [PREEMPÇÃO] Tarefa '{self.tarefa_em_execucao.nome}' interrompida por '{nova_tarefa.nome}'.")
                    self._adicionar_tarefa_na_fila(self.tarefa_em_execucao)
                    self.tarefa_em_execucao = None
                else:
                    self._adicionar_tarefa_na_fila(nova_tarefa)
                    nova_tarefa = None
            
            if not self.tarefa_em_execucao and nova_tarefa:
                self.tarefa_em_execucao = nova_tarefa
                if self.tarefa_em_execucao.tempo_inicio_execucao == -1:
                    self.tarefa_em_execucao.tempo_inicio_execucao = self.relogio_simulado
                print(f"Tempo: {self.relogio_simulado:6.2f} ms | [INICIANDO] Tarefa '{self.tarefa_em_execucao.nome}' (Duração: {self.tarefa_em_execucao.duracao:.2f} ms)")

            if self.tarefa_em_execucao:
                tarefa_atual = self.tarefa_em_execucao
                
                if tarefa_atual.recurso_necessario and tarefa_atual.estado != "EXECUTANDO_COM_RECURSO":
                    recurso_obtido = self.gerenciador_recursos.solicitar(tarefa_atual, tarefa_atual.recurso_necessario, self)
                    if not recurso_obtido:
                        print(f"Tempo: {self.relogio_simulado:6.2f} ms | [BLOQUEIO] Tarefa '{tarefa_atual.nome}' aguardando recurso.")
                        tarefa_atual.estado = "BLOQUEADA"
                        self.tarefa_em_execucao = None
                        continue
                    else:
                        tarefa_atual.estado = "EXECUTANDO_COM_RECURSO"

                estrategia_da_tarefa = self.estrategias[tarefa_atual.criticidade]
                tempo_exec = tarefa_atual.tempo_restante
                
                if isinstance(estrategia_da_tarefa, EstrategiaRoundRobin):
                    tempo_exec = min(tarefa_atual.tempo_restante, estrategia_da_tarefa.quantum)
                
                self.relogio_simulado += tempo_exec
                tarefa_atual.tempo_restante -= tempo_exec

                if tarefa_atual.tempo_restante <= 0:
                    tarefa_atual.estado = "CONCLUIDA"
                    tarefa_atual.tempo_final_execucao = self.relogio_simulado
                    self.tarefas_concluidas.append(tarefa_atual)
                    print(f"Tempo: {self.relogio_simulado:6.2f} ms | [CONCLUÍDA] Tarefa '{tarefa_atual.nome}'.")

                    # Cálculo do WCRT no momento da conclusão
                    if tarefa_atual.criticidade == Criticidade.CRITICA:
                        tempo_resposta = tarefa_atual.tempo_final_execucao - tarefa_atual.tempo_chegada
                        self.metricas['wcrt_critico'] = max(self.metricas['wcrt_critico'], tempo_resposta)
                    
                    if tarefa_atual.recurso_necessario:
                        self.gerenciador_recursos.liberar(tarefa_atual, tarefa_atual.recurso_necessario)
                    self.tarefa_em_execucao = None
                
                elif isinstance(estrategia_da_tarefa, EstrategiaRoundRobin):
                    print(f"Tempo: {self.relogio_simulado:6.2f} ms | [QUANTUM] Tarefa '{tarefa_atual.nome}' volta para a fila.")
                    self._adicionar_tarefa_na_fila(tarefa_atual)
                    self.tarefa_em_execucao = None
            else:
                self.relogio_simulado += 1.0

        print("--- FIM DA SIMULAÇÃO ---")
        self.gerar_relatorio()
        
    def gerar_relatorio(self):
        # Mova o conteúdo do seu método gerar_relatorio para cá
        print("\n\n--- RELATÓRIO FINAL DE DESEMPENHO E SEGURANÇA ---")
        # (todo o código de gerar_relatorio)
        total_tarefas = len(self.tarefas_concluidas)
        if not total_tarefas:
            print("Nenhuma tarefa concluída.")
            return

        # ... e assim por diante
        tempos_resposta = [t.tempo_final_execucao - t.tempo_chegada for t in self.tarefas_concluidas]
        tempos_espera = [(t.tempo_final_execucao - t.tempo_chegada) - t.duracao for t in self.tarefas_concluidas]
        
        tempo_medio_resposta = sum(tempos_resposta) / total_tarefas
        tempo_medio_espera = sum(tempos_espera) / total_tarefas
        
        tempo_total_execucao = sum(t.duracao for t in self.tarefas_concluidas)
        utilizacao_cpu = (tempo_total_execucao / self.relogio_simulado) * 100 if self.relogio_simulado > 0 else 0

        print(f"  - Worst-Case Response Time (CRÍTICO): {self.metricas['wcrt_critico']:.2f} ms")
        print("\n[Métricas Gerais de Desempenho]")
        print(f"  - Tempo Total da Simulação: {self.relogio_simulado:.2f} ms")
        print(f"  - Utilização da CPU: {utilizacao_cpu:.2f}%")
        print(f"  - Tempo Médio de Resposta (Turnaround): {tempo_medio_resposta:.2f} ms")
        print(f"  - Tempo Médio de Espera: {tempo_medio_espera:.2f} ms")
        
        print("\n--- Relatório Final ---")
        print(f"  - Overhead Total do Escalonador: {self.overhead_total_escalonamento:.4f} ms")
        print(f"  - Jitter Máximo em Tarefas Periódicas: {self.metricas['max_jitter_periodico']:.2f} ms")
        print(f"  - Modos de Segurança Ativados: {self.metricas['modos_seguranca_ativados']} vezes")


class EstrategiaDeFila(ABC):
    """
    Classe base (Interface) para todas as estratégias de escalonamento de fila.
    Define o contrato que todas as estratégias devem seguir.
    """
    @abstractmethod
    def selecionar(self, fila):
        """Seleciona a próxima tarefa de uma fila específica."""
        pass

    def adicionar(self, fila, tarefa):
        """Método padrão para adicionar tarefas (pode ser sobrescrito)."""
        fila.append(tarefa)

# --- Implementações Concretas das Estratégias ---

class EstrategiaEDF(EstrategiaDeFila):
    """Estratégia Earliest Deadline First usando um min-heap."""
    """Estratégia Earliest Deadline First usando um min-heap."""
    def selecionar(self, fila_heap):
        if fila_heap:
            return heapq.heappop(fila_heap)
        return None

    def adicionar(self, fila_heap, tarefa):
        heapq.heappush(fila_heap, tarefa)

class EstrategiaRoundRobin(EstrategiaDeFila):
    """Estratégia Round Robin usando uma fila deque."""
    """Estratégia Round Robin usando uma fila deque."""
    def __init__(self, quantum):
        self.quantum = quantum

    def selecionar(self, fila_deque):
        if fila_deque:
            return fila_deque.popleft()
        return None
    
    # O método de adicionar padrão (append) já serve para o RR.

class EstrategiaFIFO(EstrategiaDeFila):
    """Estratégia First-In, First-Out usando uma fila deque."""
    """Estratégia First-In, First-Out usando uma fila deque."""
    def selecionar(self, fila_deque):
        if fila_deque:
            return fila_deque.popleft()
        return None

class EstrategiaSJF(EstrategiaDeFila):
    """Estratégia Shortest Job First."""
    def selecionar(self, fila_de_tarefas):
        if not fila_de_tarefas:
            return None

        # Encontra a tarefa com a menor duração (tempo_restante)
        tarefa_mais_curta = min(fila_de_tarefas, key=lambda tarefa: tarefa.tempo_restante)
        fila_de_tarefas.remove(tarefa_mais_curta)
        return tarefa_mais_curta

    def adicionar(self, fila_de_tarefas, tarefa):
        # No SJF não-preemptivo, a ordem de adição na fila não importa tanto, 
        # pois a seleção busca sempre a menor tarefa.
        fila_de_tarefas.append(tarefa)



def criar_cenario_de_teste():
    """
    Cria uma lista de tarefas realista para simular um cenário de VAC.
    Isso garante que ambos os escalonadores sejam testados com a mesma carga de trabalho.
    """
    tarefas = [
        # Tarefas Críticas (Segurança) - Devem ser executadas antes de seus deadlines.
        TarefaCAV(nome="Verificar Freios ABS", duracao=5.0, criticidade=Criticidade.CRITICA, deadline_relativo=20.0),
        TarefaCAV(nome="Ajustar Estabilidade", duracao=10.0, criticidade=Criticidade.CRITICA, deadline_relativo=50.0),

        # Tarefas de Tempo Real (Operacionais) - Devem ser responsivas.
        TarefaCAV(nome="Processar Radar Frontal", duracao=25.0, criticidade=Criticidade.TEMPO_REAL),
        TarefaCAV(nome="Calcular Rota GPS", duracao=60.0, criticidade=Criticidade.TEMPO_REAL),
        TarefaCAV(nome="Comunicacao V2V", duracao=15.0, criticidade=Criticidade.TEMPO_REAL),

        # Tarefas de Conforto (Não Essenciais) - Podem esperar.
        TarefaCAV(nome="Atualizar Display Multimidia", duracao=100.0, criticidade=Criticidade.CONFORTO),
        TarefaCAV(nome="Sincronizar Playlist", duracao=150.0, criticidade=Criticidade.CONFORTO)
    ]

def criar_cenario_balanceado():
    """Cenário com uma mistura de tarefas de todas as criticidades."""
    return [
        TarefaCAV(nome="Verificar Freios", duracao=5.0, criticidade=Criticidade.CRITICA, deadline_relativo=20.0, recurso_necessario="freios"),
        TarefaCAV(nome="Ajustar Estabilidade", duracao=10.0, criticidade=Criticidade.CRITICA, deadline_relativo=50.0),
        TarefaCAV(nome="Processar Radar", duracao=25.0, criticidade=Criticidade.TEMPO_REAL, recurso_necessario="radar"),
        TarefaCAV(nome="Calcular Rota GPS", duracao=60.0, criticidade=Criticidade.TEMPO_REAL),
        TarefaCAV(nome="Atualizar Multimidia", duracao=100.0, criticidade=Criticidade.CONFORTO),
        TarefaCAV(nome="Sincronizar Playlist", duracao=150.0, criticidade=Criticidade.CONFORTO)
    ]

def criar_cenario_critico():
    """Cenário focado em tarefas críticas e de tempo real com deadlines apertados."""
    return [
        TarefaCAV(nome="Desviar de Obstáculo", duracao=8.0, criticidade=Criticidade.CRITICA, deadline_relativo=15.0, recurso_necessario="direcao"),
        TarefaCAV(nome="Comunicacao V2V Urgente", duracao=12.0, criticidade=Criticidade.CRITICA, deadline_relativo=25.0),
        TarefaCAV(nome="Processar Lidar", duracao=20.0, criticidade=Criticidade.TEMPO_REAL),
        TarefaCAV(nome="Ajustar Velocidade", duracao=5.0, criticidade=Criticidade.TEMPO_REAL),
    ]

def criar_cenario_conflitante():
    """
    Cenário com conflito entre deadline e duração para diferenciar SJF de EDF.
    - 'Processar Câmera': Tarefa longa, mas com deadline curto (urgente).
    - 'Verificar Pressão Pneus': Tarefa curta, mas com deadline longo (não urgente).
    """
    print("\nAVISO: Usando cenário com conflito de prioridade (SJF vs EDF).")
    return [
        TarefaCAV(nome="Processar Câmera 4K", duracao=40.0, criticidade=Criticidade.CRITICA, deadline_relativo=50.0),
        TarefaCAV(nome="Verificar Pressão Pneus", duracao=5.0, criticidade=Criticidade.TEMPO_REAL, deadline_relativo=150.0),
        TarefaCAV(nome="Calcular Rota Alternativa", duracao=25.0, criticidade=Criticidade.TEMPO_REAL, deadline_relativo=100.0),
        TarefaCAV(nome="Tocar Alerta Sonoro", duracao=2.0, criticidade=Criticidade.CRITICA, deadline_relativo=20.0),
    ]

def criar_cenario_intercalado():
    """
    Um cenário de teste mais rico e realista, projetado para testar:
    - Múltiplas tarefas em todos os níveis de criticidade.
    - Conflitos de deadline vs. duração (SJF vs. EDF).
    - Intercalação de tarefas de mesma prioridade (FIFO vs. RR).
    - Disputa por recursos compartilhados e bloqueio de tarefas.
    """
    print("\nAVISO: Usando Cenário Complexo com disputa por recursos.")
    return [
        # Tarefas Críticas
        TarefaCAV(nome="Freio de Emergência", duracao=10.0, criticidade=Criticidade.CRITICA, deadline_relativo=30.0, recurso_necessario="freios"),
        TarefaCAV(nome="Ajuste de Estabilidade", duracao=15.0, criticidade=Criticidade.CRITICA, deadline_relativo=80.0),

        # Tarefas de Tempo Real (com disputa por recurso)
        TarefaCAV(nome="Processar Radar Frontal", duracao=30.0, criticidade=Criticidade.TEMPO_REAL, deadline_relativo=150.0, recurso_necessario="comunicacao"),
        TarefaCAV(nome="Comunicação V2V", duracao=10.0, criticidade=Criticidade.TEMPO_REAL, deadline_relativo=120.0, recurso_necessario="comunicacao"),

        # Tarefas de Conforto (uma delas precisa de um recurso disputado)
        TarefaCAV(nome="Atualizar Mapas HD", duracao=50.0, criticidade=Criticidade.CONFORTO, deadline_relativo=500.0, recurso_necessario="comunicacao"),
        TarefaCAV(nome="Diagnóstico do Sistema", duracao=80.0, criticidade=Criticidade.CONFORTO, deadline_relativo=800.0),
    ]

def criar_cenario_de_emergencia_urbana():
    """
    Cenário final, estressante e realista, simulando um evento de frenagem de emergência.
    As tarefas chegam em momentos diferentes para simular uma cadeia de eventos.
    Os tempos são baseados em estimativas realistas para sistemas embarcados automotivos.
    Retorna uma lista de tuplas: (tempo_de_chegada_ms, objeto_tarefa).
    """
    print("="*60)
    print("AVISO: Carregando Cenário de Emergência Urbana (realista e estressante).")
    print("="*60)
    
    # A história se desenrola em um intervalo de 100ms
    cenario = [
        # t=0ms: Tarefas de fundo estão rodando normalmente
        (0.0, TarefaCAV(nome="Diagnóstico de Bateria", duracao=100.0, criticidade=Criticidade.CONFORTO, deadline_relativo=2000.0)),
        (0.0, TarefaCAV(nome="Atualizar Posição GPS", duracao=50.0, criticidade=Criticidade.TEMPO_REAL, deadline_relativo=500.0, recurso_necessario="gps")),

        # t=10ms: Alerta V2V (Veículo-para-Veículo) sobre um perigo à frente
        (10.0, TarefaCAV(nome="Receber Alerta V2V", duracao=5.0, criticidade=Criticidade.TEMPO_REAL, deadline_relativo=50.0, recurso_necessario="comunicacao")),

        # t=20ms: O próprio LiDAR do carro detecta um obstáculo
        (20.0, TarefaCAV(nome="Processar Dados LiDAR", duracao=25.0, criticidade=Criticidade.CRITICA, deadline_relativo=60.0, recurso_necessario="processador")),

        # t=25ms: A câmera confirma que o obstáculo é um pedestre
        (25.0, TarefaCAV(nome="Análise de Imagem (Pedestre)", duracao=40.0, criticidade=Criticidade.CRITICA, deadline_relativo=70.0, recurso_necessario="processador")),

        # t=30ms: CADEIA DE AÇÕES CRÍTICAS - Devem ser imediatas
        (30.0, TarefaCAV(nome="ACIONAR FREIO DE EMERGÊNCIA", duracao=15.0, criticidade=Criticidade.CRITICA, deadline_relativo=25.0, recurso_necessario="freios")), # Deadline muito apertado!
        (30.0, TarefaCAV(nome="Apertar Cintos de Segurança", duracao=10.0, criticidade=Criticidade.CRITICA, deadline_relativo=30.0)),
        
        # t=35ms: Após a decisão, o carro avisa outros veículos
        (35.0, TarefaCAV(nome="Transmitir Alerta V2V", duracao=5.0, criticidade=Criticidade.TEMPO_REAL, deadline_relativo=50.0, recurso_necessario="comunicacao")),

        # t=100ms: Tarefa de conforto tenta rodar após o evento crítico
        (100.0, TarefaCAV(nome="Retomar Música", duracao=20.0, criticidade=Criticidade.CONFORTO, deadline_relativo=500.0))
    ]
    return sorted(cenario, key=lambda x: x[0]) # Ordena pelo tempo de chegada


if __name__ == "__main__":
    from copy import deepcopy

    # --- PASSO 1: DEFINA O CENÁRIO PARA ESTA RODADA DE TESTES ---
    # Para gerar resultados para diferentes cargas de trabalho, você só precisa
    # mudar a função chamada nesta linha (ex: para criar_cenario_critico()).

    cenario_de_teste = criar_cenario_de_emergencia_urbana()

    # --- Simulação 1: FIFO Puro ---
    print("\n--- SIMULANDO COM FIFO PURO ---")
    config_fifo = {
        Criticidade.CRITICA: EstrategiaFIFO(),
        Criticidade.TEMPO_REAL: EstrategiaFIFO(),
        Criticidade.CONFORTO: EstrategiaFIFO()
    }
    escalonador_fifo = Escalonador(estrategias_por_criticidade=config_fifo)
    escalonador_fifo.simular(deepcopy(cenario_de_teste)) # Passa o cenário para o simulador

    # --- Simulação 2: Round Robin Puro ---
    print("\n--- SIMULANDO COM ROUND ROBIN PURO (Quantum=20ms) ---")
    config_rr = {
        Criticidade.CRITICA: EstrategiaRoundRobin(quantum=20.0),
        Criticidade.TEMPO_REAL: EstrategiaRoundRobin(quantum=20.0),
        Criticidade.CONFORTO: EstrategiaRoundRobin(quantum=20.0)
    }
    escalonador_rr = Escalonador(estrategias_por_criticidade=config_rr)
    escalonador_rr.simular(deepcopy(cenario_de_teste))

    # --- Simulação 3: SJF Puro ---
    print("\n--- SIMULANDO COM SJF PURO ---")
    config_sjf = {
        Criticidade.CRITICA: EstrategiaSJF(),
        Criticidade.TEMPO_REAL: EstrategiaSJF(),
        Criticidade.CONFORTO: EstrategiaSJF()
    }
    escalonador_sjf = Escalonador(estrategias_por_criticidade=config_sjf)
    escalonador_sjf.simular(deepcopy(cenario_de_teste))

    # --- Simulação 4: EDF Puro ---
    print("\n--- SIMULANDO COM EDF PURO ---")
    config_edf = {
        Criticidade.CRITICA: EstrategiaEDF(),
        Criticidade.TEMPO_REAL: EstrategiaEDF(),
        Criticidade.CONFORTO: EstrategiaEDF()
    }
    escalonador_edf = Escalonador(estrategias_por_criticidade=config_edf)
    escalonador_edf.simular(deepcopy(cenario_de_teste))

    # --- Simulação 5: Seu Escalonador Híbrido Otimizado (PROPOSTA) ---
    print("\n--- SIMULANDO COM O ESCALONADOR HÍBRIDO PROPOSTO ---")
    config_hibrido = {
        Criticidade.CRITICA: EstrategiaEDF(),
        Criticidade.TEMPO_REAL: EstrategiaRoundRobin(quantum=20.0),
        Criticidade.CONFORTO: EstrategiaFIFO()
    }
    escalonador_hibrido = Escalonador(estrategias_por_criticidade=config_hibrido)
    escalonador_hibrido.simular(deepcopy(cenario_de_teste))
    
    print("\n" + "="*60)
    print("TODAS AS SIMULAÇÕES FORAM CONCLUÍDAS.")
    print("Use os relatórios impressos no terminal para preencher sua tabela de comparação.")
    print("="*60)

