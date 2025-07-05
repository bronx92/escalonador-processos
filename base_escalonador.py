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

    def __lt__(self, other):
        # Critério de desempate para o heap: se os deadlines forem iguais, a tarefa que chegou primeiro tem prioridade.
        if self.deadline_absoluto == other.deadline_absoluto:
            return self.tempo_chegada < other.tempo_chegada
        return self.deadline_absoluto < other.deadline_absoluto

# ==============================================================================
# PILAR 2: GESTÃO DE RECURSOS COM ATOMICIDADE (PIP CORRIGIDO)
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
    
    def solicitar(self, tarefa: TarefaCAV, nome_recurso: str, escalonador):
        with self.lock: # Garante que a verificação e alocação sejam atômicas
            if nome_recurso not in self.recursos:
                self.recursos[nome_recurso] = {"dono": None, "fila_espera": []}
                
            recurso = self.recursos[nome_recurso]
            if recurso["dono"] is None:
                recurso["dono"] = tarefa
                tarefa.estado = "EXECUTANDO"
                return True
            else:
                # Recurso está ocupado, tarefa é bloqueada
                tarefa.estado = "BLOQUEADA"
                heapq.heappush(recurso["fila_espera"], (tarefa.prioridade_atual, tarefa.tempo_chegada, tarefa))
                
                # **Lógica da Herança de Prioridade**
                if tarefa.prioridade_atual < recurso["dono"].prioridade_atual:
                    print(f"    [HERANÇA DE PRIORIDADE] Tarefa '{recurso['dono'].nome}' herda prioridade de '{tarefa.nome}'")
                    recurso["dono"].prioridade_atual = tarefa.prioridade_atual
                
                # Adiciona a tarefa de volta na fila apropriada do escalonador, mas ela não será escolhida
                # enquanto estiver bloqueada.
                escalonador.adicionar_tarefa_na_fila(tarefa)
                return False

    def liberar(self, tarefa: TarefaCAV, nome_recurso: str):
        with self.lock: # Garante que a liberação seja atômica
            if nome_recurso not in self.recursos:
                return

            recurso = self.recursos[nome_recurso]
            if recurso["dono"] == tarefa:
                # Restaura a prioridade original da tarefa que está liberando
                tarefa.prioridade_atual = tarefa.prioridade_original
                
                if recurso["fila_espera"]:
                    # Passa o recurso para a próxima tarefa de maior prioridade na fila de espera
                    _, _, proxima_tarefa = heapq.heappop(recurso["fila_espera"])
                    recurso["dono"] = proxima_tarefa
                    proxima_tarefa.estado = "PRONTA"
                    print(f"    [RECURSO] '{tarefa.nome}' liberou '{nome_recurso}'. '{proxima_tarefa.nome}' agora é dona.")
                else:
                    recurso["dono"] = None

# ==============================================================================
# PILAR 3: ARQUITETURA DO ESCALONADOR (COM MÉTRICAS E SEGURANÇA)
# ==============================================================================

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

        # --- CORREÇÃO 2: MEDIÇÃO DE OVERHEAD ---
        self.overhead_total_escalonamento = 0.0

        # --- CORREÇÃO 5: CONTROLE DE STARVATION ---
        self.ultimo_conforto_executado = 0.0

        # --- CORREÇÃO 6: MÉTRICAS DE SEGURANÇA ADICIONAIS ---
        self.metricas = {
            "wcrt_critico": 0.0,
            "deadlines_perdidos": 0,
            "max_jitter_periodico": 0.0,
            "modos_seguranca_ativados": 0
        }

    def validar_certificado(self, tarefa: TarefaCAV):
        """Verifica a integridade da tarefa."""
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
        '''
        inicio_selecao = time.perf_counter_ns()

        # --- LÓGICA ANTI-STARVATION ---
        if (self.relogio_simulado - self.ultimo_conforto_executado) > 500.0: # A cada 500ms
            if self.filas[Criticidade.CONFORTO]:
                tarefa_conforto = self.filas[Criticidade.CONFORTO][0]
                if tarefa_conforto.estado != "BLOQUEADA":
                    print(f"    [ANTI-STARVATION] Forçando execução de '{tarefa_conforto.nome}'")
                    self.ultimo_conforto_executado = self.relogio_simulado
                    return self.filas[Criticidade.CONFORTO].popleft()

        """
        Implementa a lógica de seleção hierárquica e preemptiva.
        Sempre prioriza CRITICA > TEMPO_REAL > CONFORTO.
        """
        # 1. Verifica fila CRÍTICA (EDF - Earliest Deadline First)
        if self.filas[Criticidade.CRITICA]:
            tarefa = self.filas[Criticidade.CRITICA][0] # Pega o menor deadline (topo do heap)
            if tarefa.estado != "BLOQUEADA":
                return heapq.heappop(self.filas[Criticidade.CRITICA])
        
        # Se a tarefa atual não for crítica, pode ser preemptada
        if self.tarefa_em_execucao and self.tarefa_em_execucao.criticidade != Criticidade.CRITICA:
            # Se chegou uma tarefa crítica, ela preempta qualquer outra coisa
             if self.filas[Criticidade.CRITICA]:
                return heapq.heappop(self.filas[Criticidade.CRITICA])
        
        # Se não há tarefa em execução, continua a busca
        if self.tarefa_em_execucao is None:
            # 2. Verifica fila TEMPO REAL (Round Robin)
            if self.filas[Criticidade.TEMPO_REAL]:
                for _ in range(len(self.filas[Criticidade.TEMPO_REAL])):
                    tarefa = self.filas[Criticidade.TEMPO_REAL].popleft()
                    if tarefa.estado != "BLOQUEADA":
                         return tarefa
                    self.filas[Criticidade.TEMPO_REAL].append(tarefa) # Devolve para o fim da fila

            # 3. Verifica fila CONFORTO (FIFO)
            if self.filas[Criticidade.CONFORTO]:
                for _ in range(len(self.filas[Criticidade.CONFORTO])):
                    tarefa = self.filas[Criticidade.CONFORTO].popleft()
                    if tarefa.estado != "BLOQUEADA":
                        return tarefa
                    self.filas[Criticidade.CONFORTO].append(tarefa)
        proxima_tarefa = None # Simulação simplificada
        
        fim_selecao = time.perf_counter_ns()
        self.overhead_total_escalonamento += (fim_selecao - inicio_selecao) / 1e6 # ns -> ms
        return proxima_tarefa

        
        # Ao selecionar da fila crítica:
        if self.filas[Criticidade.CRITICA]:
             # heapq.heappop já retorna o menor item (menor deadline)
             proxima_tarefa = heapq.heappop(self.filas[Criticidade.CRITICA]) 
             return proxima_tarefa
        return None # Simplificado
        '''
        """
    Este método agora atua como um maestro, impondo a hierarquia de criticidade
    e delegando a seleção da tarefa para a estratégia correspondente.
    """
    inicio_selecao = time.perf_counter_ns() # Para medir o overhead

    # 1. PRIORIDADE MÁXIMA: Fila de tarefas CRÍTICAS
    # Acessa a fila e a estratégia para este nível de criticidade.
    fila_critica = self.filas[Criticidade.CRITICA]
    estrategia_critica = self.estrategias[Criticidade.CRITICA]

    if fila_critica:
        # Pede para a ESTRATÉGIA selecionar a tarefa. Não importa se é EDF ou outra.
        tarefa_selecionada = estrategia_critica.selecionar(fila_critica)
        
        # A lógica de verificar se a tarefa está bloqueada continua aqui, pois é uma
        # responsabilidade do escalonador principal, não da estratégia de seleção.
        if tarefa_selecionada and tarefa_selecionada.estado != "BLOQUEADA":
            # Mede o overhead e retorna a tarefa
            fim_selecao = time.perf_counter_ns()
            self.overhead_total_escalonamento += (fim_selecao - inicio_selecao) / 1e6
            return tarefa_selecionada
        elif tarefa_selecionada: # Se estava bloqueada, devolve para a fila
            self._adicionar_tarefa_na_fila(tarefa_selecionada)


    # 2. SEGUNDA PRIORIDADE: Fila de tarefas de TEMPO REAL
    # A lógica se repete, mas para a próxima fila e sua respectiva estratégia.
    fila_tempo_real = self.filas[Criticidade.TEMPO_REAL]
    estrategia_tempo_real = self.estrategias[Criticidade.TEMPO_REAL]

    if fila_tempo_real:
        tarefa_selecionada = estrategia_tempo_real.selecionar(fila_tempo_real)
        if tarefa_selecionada and tarefa_selecionada.estado != "BLOQUEADA":
            fim_selecao = time.perf_counter_ns()
            self.overhead_total_escalonamento += (fim_selecao - inicio_selecao) / 1e6
            return tarefa_selecionada
        elif tarefa_selecionada:
            self._adicionar_tarefa_na_fila(tarefa_selecionada)
    

    # 3. ÚLTIMA PRIORIDADE: Fila de tarefas de CONFORTO
    fila_conforto = self.filas[Criticidade.CONFORTO]
    estrategia_conforto = self.estrategias[Criticidade.CONFORTO]

    if fila_conforto:
        tarefa_selecionada = estrategia_conforto.selecionar(fila_conforto)
        if tarefa_selecionada and tarefa_selecionada.estado != "BLOQUEADA":
            fim_selecao = time.perf_counter_ns()
            self.overhead_total_escalonamento += (fim_selecao - inicio_selecao) / 1e6
            return tarefa_selecionada
        elif tarefa_selecionada:
            self._adicionar_tarefa_na_fila(tarefa_selecionada)

    # Se nenhuma tarefa de nenhuma fila pôde ser selecionada, retorna None.
    fim_selecao = time.perf_counter_ns()
    self.overhead_total_escalonamento += (fim_selecao - inicio_selecao) / 1e6
    return None

    def simular(self):
        """
        Motor principal da simulação. Roda em ciclos, permitindo preempção
        e tratamento de eventos a cada passo.
        """

        # Validação de certificados no início da simulação
        for fila in self.filas.values():
            for tarefa in list(fila): # itera sobre uma cópia
                if not self.validar_certificado(tarefa):
                    print(f"ALERTA DE SEGURANÇA! Tarefa '{tarefa.nome}' com certificado inválido. Removendo.")
                    fila.remove(tarefa)
        
        # O loop principal da simulação...
        tarefa_atual = self.selecionar_proxima_tarefa() # Exemplo
        if tarefa_atual:
            # --- CORREÇÃO 4: MODO DE SEGURANÇA REATIVO ---
            if tarefa_atual.criticidade == Criticidade.CRITICA:
                tempo_restante_deadline = tarefa_atual.deadline_absoluto - self.relogio_simulado
                if tempo_restante_deadline < (tarefa_atual.deadline_relativo * 0.2): # Entrou nos 20% finais
                    self.ativar_modo_seguranca(tarefa_atual)

        
        print("\n--- INÍCIO DA SIMULAÇÃO ---")
        while True:
            # --- CORREÇÃO 3: MONITORAMENTO CONTÍNUO DE DEADLINES ---
            if self.filas[Criticidade.CRITICA]:
                # O primeiro item no heap é o que tem o deadline mais próximo
                tarefa_mais_urgente = self.filas[Criticidade.CRITICA][0]
                tempo_restante_deadline = tarefa_mais_urgente.deadline_absoluto - self.relogio_simulado
                if tempo_restante_deadline < (tarefa_mais_urgente.deadline_relativo * 0.3): # Entrou nos 30% finais
                    self.ativar_modo_seguranca(tarefa_mais_urgente)

           self._verificar_tarefas_periodicas()
            
            proxima_tarefa = self.selecionar_proxima_tarefa()

            if self.tarefa_em_execucao is None:
                if proxima_tarefa:
                    self.tarefa_em_execucao = proxima_tarefa
                else:
                    # Verifica se todas as filas estão vazias para terminar
                    if not any(self.filas.values()):
                        break
                    # Se não há tarefas prontas, avança o tempo
                    self.relogio_simulado += 1.0
                    continue
            
            # **Lógica de Preempção**
            if proxima_tarefa and proxima_tarefa != self.tarefa_em_execucao:
                 if proxima_tarefa.criticidade.value < self.tarefa_em_execucao.criticidade.value:
                    print(f"    [PREEMPÇÃO] Tarefa '{self.tarefa_em_execucao.nome}' preemptada por '{proxima_tarefa.nome}'")
                    self.adicionar_tarefa_na_fila(self.tarefa_em_execucao)
                    self.tarefa_em_execucao = proxima_tarefa

            # Execução da tarefa
            tarefa_atual = self.tarefa_em_execucao
            if tarefa_atual.tempo_inicio_execucao == -1:
                tarefa_atual.tempo_inicio_execucao = self.relogio_simulado

            # Verifica se precisa de recurso
            if tarefa_atual.recurso_necessario:
                if not self.gerenciador_recursos.solicitar(tarefa_atual, tarefa_atual.recurso_necessario, self):
                    print(f"    [BLOQUEIO] Tarefa '{tarefa_atual.nome}' bloqueada aguardando recurso '{tarefa_atual.recurso_necessario}'")
                    self.tarefa_em_execucao = None
                    continue
            
            tempo_de_execucao = 1.0 # Simula um tick de clock

            if tarefa_atual.criticidade == Criticidade.TEMPO_REAL:
                tempo_de_execucao = min(self.quantum_rr, tarefa_atual.tempo_restante)
            else: # Tarefas críticas e de conforto rodam até o fim ou preempção
                tempo_de_execucao = tarefa_atual.tempo_restante

            tarefa_atual.tempo_restante -= tempo_de_execucao
            self.relogio_simulado += tempo_de_execucao
            print(f"Tempo: {self.relogio_simulado:6.2f} ms | Executando: {tarefa_atual.nome} ({tarefa_atual.tempo_restante:.2f} ms restantes)")


            if tarefa_atual.tempo_restante <= 0:
                tarefa_atual.estado = "CONCLUIDA"
                tarefa_atual.tempo_final_execucao = self.relogio_simulado
                self.tarefas_concluidas.append(tarefa_atual)
                print(f"    [CONCLUÍDA] Tarefa '{tarefa_atual.nome}' finalizada.")
                if tarefa_atual.recurso_necessario:
                    self.gerenciador_recursos.liberar(tarefa_atual, tarefa_atual.recurso_necessario)
                self.tarefa_em_execucao = None
            
            # Se for Round Robin e ainda não terminou, volta para a fila
            elif tarefa_atual.criticidade == Criticidade.TEMPO_REAL:
                 self.adicionar_tarefa_na_fila(tarefa_atual)
                 self.tarefa_em_execucao = None

            # Para terminar o loop
            if not any(self.filas.values()) and self.tarefa_em_execucao is None:
                break
            
            # Avanço do relógio se ocioso
            time.sleep(0.001) # Pequeno sleep para não travar a CPU se ocioso
            self.relogio_simulado += 1.0


        print("--- FIM DA SIMULAÇÃO ---")
        self.gerar_relatorio()
    
    def gerar_relatorio(self):        
        """Calcula e exibe as métricas de desempenho e segurança."""
        print("\n\n--- RELATÓRIO FINAL DE DESEMPENHO E SEGURANÇA ---")
        
        total_tarefas = len(self.tarefas_concluidas)
        if total_tarefas == 0:
            print("Nenhuma tarefa foi concluída.")
            return

        # Métricas Críticas
        tarefas_criticas = [t for t in self.tarefas_concluidas if t.criticidade == Criticidade.CRITICA and hasattr(t, 'deadline_relativo')]
        deadlines_perdidos = 0
        if tarefas_criticas:
            for t in tarefas_criticas:
                if t.tempo_final_execucao > t.deadline_absoluto:
                    deadlines_perdidos += 1
            taxa_perda = (deadlines_perdidos / len(tarefas_criticas)) * 100
            print(f"\n[Métricas de Segurança (Criticidade.CRITICA)]")
            print(f"  - Taxa de Deadlines Perdidos: {deadlines_perdidos}/{len(tarefas_criticas)} ({taxa_perda:.2f}%)")

        # Métricas Gerais
        tempos_resposta = [t.tempo_final_execucao - t.tempo_chegada for t in self.tarefas_concluidas]
        tempos_espera = [(t.tempo_final_execucao - t.tempo_chegada) - t.duracao for t in self.tarefas_concluidas]
        
        tempo_medio_resposta = sum(tempos_resposta) / total_tarefas
        tempo_medio_espera = sum(tempos_espera) / total_tarefas
        
        tempo_total_execucao = sum(t.duracao for t in self.tarefas_concluidas)
        utilizacao_cpu = (tempo_total_execucao / self.relogio_simulado) * 100 if self.relogio_simulado > 0 else 0

        print("\n[Métricas Gerais de Desempenho]")
        print(f"  - Tempo Total da Simulação: {self.relogio_simulado:.2f} ms")
        print(f"  - Utilização da CPU: {utilizacao_cpu:.2f}%")
        print(f"  - Tempo Médio de Resposta (Turnaround): {tempo_medio_resposta:.2f} ms")
        print(f"  - Tempo Médio de Espera: {tempo_medio_espera:.2f} ms")
        
        # --- Cálculo do Jitter ---
        tempos_execucao_periodicas = {}
        for t in self.tarefas_concluidas:
            if t.periodo:
                if t.nome not in tempos_execucao_periodicas:
                    tempos_execucao_periodicas[t.nome] = []
                tempos_execucao_periodicas[t.nome].append(t.tempo_inicio_execucao)
        
        max_jitter = 0.0
        for nome, tempos in tempos_execucao_periodicas.items():
            if len(tempos) > 1:
                intervalos = [tempos[i] - tempos[i-1] for i in range(1, len(tempos))]
                jitter = max(intervalos) - min(intervalos)
                max_jitter = max(max_jitter, jitter)
        self.metricas["max_jitter_periodico"] = max_jitter

        # Exibição das novas métricas no relatório
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
    def selecionar(self, fila_heap):
        if fila_heap:
            return heapq.heappop(fila_heap)
        return None

    def adicionar(self, fila_heap, tarefa):
        heapq.heappush(fila_heap, tarefa)

class EstrategiaRoundRobin(EstrategiaDeFila):
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
    def selecionar(self, fila_deque):
        if fila_deque:
            return fila_deque.popleft()
        return None

class EscalonadorHibrido(EscalonadorCAV): # A classe base EscalonadorCAV continua a mesma
    """
    Um escalonador configurável que utiliza diferentes estratégias para cada
    nível de criticidade.
    """
    def __init__(self, estrategias_por_criticidade: dict):
        super().__init__() # Chama o init da classe base
        
        # Em vez de lógica hard-coded, agora ele armazena as estratégias
        self.estrategias = estrategias_por_criticidade
        
        # O motor de simulação (avançar tempo, preempção, etc.) permanece na classe base.

    def adicionar_tarefa_na_fila(self, tarefa: TarefaCAV):
        """Delega a adição da tarefa para a estratégia correta."""
        fila_alvo = self.filas[tarefa.criticidade]
        estrategia_alvo = self.estrategias[tarefa.criticidade]
        estrategia_alvo.adicionar(fila_alvo, tarefa)

    def selecionar_proxima_tarefa(self):
        """
        Lógica de seleção hierárquica, mas agora muito mais limpa.
        Ela delega a seleção para a estratégia apropriada.
        """
        # 1. Verifica fila CRÍTICA
        fila_critica = self.filas[Criticidade.CRITICA]
        if fila_critica:
            # Pede para a estratégia EDF selecionar a próxima tarefa
            tarefa = self.estrategias[Criticidade.CRITICA].selecionar(fila_critica)
            if tarefa:
                # É preciso verificar se a tarefa não está bloqueada
                if tarefa.estado != "BLOQUEADA":
                    return tarefa
                else:
                    # Se estiver bloqueada, devolve para a fila e continua a busca
                    self.adicionar_tarefa_na_fila(tarefa)
        
        # A lógica de preempção continua a mesma...
        
        # 2. Verifica fila TEMPO REAL
        fila_tr = self.filas[Criticidade.TEMPO_REAL]
        if fila_tr:
            tarefa = self.estrategias[Criticidade.TEMPO_REAL].selecionar(fila_tr)
            if tarefa:
                if tarefa.estado != "BLOQUEADA":
                    # No RR, a tarefa é devolvida à fila no loop principal se não terminar
                    return tarefa
                else:
                    self.adicionar_tarefa_na_fila(tarefa)
        
        # 3. Verifica fila CONFORTO
        fila_conforto = self.filas[Criticidade.CONFORTO]
        if fila_conforto:
            tarefa = self.estrategias[Criticidade.CONFORTO].selecionar(fila_conforto)
            if tarefa:
                if tarefa.estado != "BLOQUEADA":
                     return tarefa
                else:
                    self.adicionar_tarefa_na_fila(tarefa)
        
        return None












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

if __name__ == "__main__":
    # --- Cenário 1: Escalonador Híbrido Padrão (EDF + RR + FIFO) ---
    print("--- CONFIGURANDO ESCALONADOR HÍBRIDO PADRÃO ---")
    
    # 1. Crie instâncias das estratégias que você quer usar
    estrategia_edf = EstrategiaEDF()
    estrategia_rr = EstrategiaRoundRobin(quantum=20.0)
    estrategia_fifo = EstrategiaFIFO()

    # 2. Crie um dicionário que mapeia criticidade para a estratégia desejada
    configuracao_escalonador1 = {
        Criticidade.CRITICA: estrategia_edf,
        Criticidade.TEMPO_REAL: estrategia_rr,
        Criticidade.CONFORTO: estrategia_fifo
    }

    # 3. Crie o escalonador passando a configuração
    escalonador_hibrido1 = EscalonadorHibrido(estrategias_por_criticidade=configuracao_escalonador1)
    
    # Adicione as tarefas...
    # ...
    # escalonador_hibrido1.simular()

    
    # --- Cenário 2: Uma Nova Combinação Experimental (EDF + FIFO + FIFO) ---
    print("\n--- CONFIGURANDO ESCALONADOR HÍBRIDO EXPERIMENTAL ---")
    
    # Você não precisa recriar tudo! Apenas componha de forma diferente.
    # Vamos supor que você queira testar se usar FIFO para tarefas de TEMPO REAL
    # é melhor em algum cenário específico.
    
    configuracao_escalonador2 = {
        Criticidade.CRITICA: EstrategiaEDF(),
        Criticidade.TEMPO_REAL: EstrategiaFIFO(), # <-- A única mudança está aqui!
        Criticidade.CONFORTO: EstrategiaFIFO()
    }

    escalonador_hibrido2 = EscalonadorHibrido(estrategias_por_criticidade=configuracao_escalonador2)
    
    print("Escalonador experimental criado com sucesso. Pronto para simulação.")

'''
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
'''
