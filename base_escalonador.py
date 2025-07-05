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

        self.tarefas_periodicas_template = []  # Linha nova a ser adicionada

    def validar_certificado(self, tarefa: TarefaCAV):
        """Verifica a integridade da tarefa."""
        return tarefa.certificado == tarefa._gerar_certificado()

    # --- CORREÇÃO 1: VALIDAÇÃO NO PONTO DE ENTRADA ---
    def adicionar_tarefa(self, tarefa: TarefaCAV):
        if not self.validar_certificado(tarefa):
            print(f"ALERTA DE SEGURANÇA! Tarefa '{tarefa.nome}' com certificado inválido. REJEITADA.")
            return

        # Registro de tarefas periódicas (novo)
        if tarefa.periodo is not None:
            # Cria template separado da instância
            template = TarefaCAV(
                nome=tarefa.nome,
                duracao=tarefa.duracao,
                criticidade=tarefa.criticidade,
                deadline_relativo=tarefa.deadline_relativo,
                periodo=tarefa.periodo,
                recurso_necessario=tarefa.recurso_necessario
            )
            template.tempo_ultima_liberacao = self.relogio_simulado
        
            self.tarefas_periodicas_template.append(template)
            print(f"-> [PERIÓDICA] Template registrado para '{tarefa.nome}' com período {tarefa.periodo}ms")

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

    def _verificar_tarefas_periodicas(self):
        """Verifica e gera novas instâncias de tarefas periódicas."""
        for template in self.tarefas_periodicas_template[:]:
            proxima_liberacao = template.tempo_ultima_liberacao + template.periodo
            
            if self.relogio_simulado >= proxima_liberacao:
                nova_instancia = TarefaCAV(
                    nome=template.nome,
                    duracao=template.duracao,
                    criticidade=template.criticidade,
                    deadline_relativo=template.deadline_relativo,
                    periodo=template.periodo,
                    recurso_necessario=template.recurso_necessario
                )
                
                # Configura tempos da nova instância
                nova_instancia.tempo_chegada = proxima_liberacao
                if nova_instancia.deadline_relativo:
                    nova_instancia.deadline_absoluto = proxima_liberacao + nova_instancia.deadline_relativo
                
                # Atualiza template para próxima liberação
                template.tempo_ultima_liberacao = proxima_liberacao
                
                self._adicionar_tarefa_na_fila(nova_instancia)
                print(f"-> [PERIÓDICA] Nova instância de '{template.nome}' gerada em {self.relogio_simulado:.2f}ms")

    def ativar_modo_seguranca(self, tarefa_gatilho: TarefaCAV):
        if self.filas[Criticidade.CONFORTO]:
            print(f"!!! MODO DE SEGURANÇA ATIVADO em {self.relogio_simulado:.2f}ms devido a {tarefa_gatilho.nome} !!!")
            print("    -> Descartando todas as tarefas de CONFORTO para liberar recursos.")
            self.filas[Criticidade.CONFORTO].clear()
            self.metricas["modos_seguranca_ativados"] += 1

    
    def selecionar_proxima_tarefa(self):
        """
        Este método implementa a lógica hierárquica de seleção de tarefas:
        1. CRÍTICA (EDF)
        2. TEMPO REAL (Round Robin)
        3. CONFORTO (FIFO)
        """
        inicio_selecao = time.perf_counter_ns()
    
        # Anti-starvation para tarefas de CONFORTO
        if (self.relogio_simulado - self.ultimo_conforto_executado) > 500.0:
            for _ in range(len(self.filas[Criticidade.CONFORTO])):
                tarefa = self.filas[Criticidade.CONFORTO].popleft()
                if tarefa.estado != "BLOQUEADA":
                    print(f"    [ANTI-STARVATION] Forçando execução de '{tarefa.nome}'")
                    self.ultimo_conforto_executado = self.relogio_simulado
                    return tarefa
                self.filas[Criticidade.CONFORTO].append(tarefa)
    
        # 1. Verifica tarefas CRÍTICAS (EDF)
        if self.filas[Criticidade.CRITICA]:
            tarefa = heapq.heappop(self.filas[Criticidade.CRITICA])
            if tarefa.estado != "BLOQUEADA":
                fim_selecao = time.perf_counter_ns()
                self.overhead_total_escalonamento += (fim_selecao - inicio_selecao) / 1e6
                return tarefa
            else:
                heapq.heappush(self.filas[Criticidade.CRITICA], tarefa)
    
        # 2. Verifica tarefas de TEMPO REAL (RR)
        if self.filas[Criticidade.TEMPO_REAL]:
            for _ in range(len(self.filas[Criticidade.TEMPO_REAL])):
                tarefa = self.filas[Criticidade.TEMPO_REAL].popleft()
                if tarefa.estado != "BLOQUEADA":
                    fim_selecao = time.perf_counter_ns()
                    self.overhead_total_escalonamento += (fim_selecao - inicio_selecao) / 1e6
                    return tarefa
                self.filas[Criticidade.TEMPO_REAL].append(tarefa)
    
        # 3. Verifica tarefas de CONFORTO (FIFO)
        if self.filas[Criticidade.CONFORTO]:
            for _ in range(len(self.filas[Criticidade.CONFORTO])):
                tarefa = self.filas[Criticidade.CONFORTO].popleft()
                if tarefa.estado != "BLOQUEADA":
                    fim_selecao = time.perf_counter_ns()
                    self.overhead_total_escalonamento += (fim_selecao - inicio_selecao) / 1e6
                    return tarefa
                self.filas[Criticidade.CONFORTO].append(tarefa)
    
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
            while any([
                self.tarefa_em_execucao,
                self.filas[Criticidade.CRITICA],
                self.filas[Criticidade.TEMPO_REAL],
                self.filas[Criticidade.CONFORTO]
            ]):
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
        wcrt = 0.0  # Novo
        
        if tarefas_criticas:
            for t in tarefas_criticas:
                tempo_resposta = t.tempo_final_execucao - t.tempo_chegada
                wcrt = max(wcrt, tempo_resposta)  # Calcula WCRT
                if t.tempo_final_execucao > t.deadline_absoluto:
                    deadlines_perdidos += 1
            
            # Adicionar ao relatório
            print(f"  - Worst-Case Response Time (CRÍTICO): {wcrt:.2f} ms")

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
    return tarefas


if __name__ == "__main__":
    # --- Cenário 1: Escalonador Híbrido Padrão (EDF + RR + FIFO) ---
    print("="*60)
    print("--- EXECUTANDO CENÁRIO 1: ESCALONADOR HÍBRIDO PADRÃO (EDF + RR) ---")
    print("="*60)
    
    # 1. Crie instâncias das estratégias que você quer usar
    estrategia_edf_1 = EstrategiaEDF()
    estrategia_rr_1 = EstrategiaRoundRobin(quantum=20.0) # Quantum de 20ms
    estrategia_fifo_1 = EstrategiaFIFO()

    # 2. Crie um dicionário que mapeia criticidade para a estratégia desejada
    configuracao_escalonador1 = {
        Criticidade.CRITICA: estrategia_edf_1,
        Criticidade.TEMPO_REAL: estrategia_rr_1,
        Criticidade.CONFORTO: estrategia_fifo_1
    }

    # 3. Crie o escalonador passando a configuração
    escalonador_hibrido1 = EscalonadorHibrido(estrategias_por_criticidade=configuracao_escalonador1)
    
    # 4. Adicione as tarefas do cenário de teste
    cenario1 = criar_cenario_de_teste()
    for tarefa in cenario1:
        escalonador_hibrido1.adicionar_tarefa(tarefa)
    
    # 5. Execute a simulação
    # O método simular() agora também será responsável por gerar o relatório no final.
    # escalonador_hibrido1.simular() # Descomente esta linha quando o método simular estiver pronto.
    print("\nSimulação para o cenário 1 estaria completa aqui.")


    # --- Cenário 2: Uma Nova Combinação Experimental (EDF + FIFO + FIFO) ---
    print("\n\n" + "="*60)
    print("--- EXECUTANDO CENÁRIO 2: ESCALONADOR EXPERIMENTAL (EDF + FIFO) ---")
    print("="*60)
    
    # Reutilizamos as estratégias ou criamos novas para clareza
    configuracao_escalonador2 = {
        Criticidade.CRITICA: EstrategiaEDF(),
        Criticidade.TEMPO_REAL: EstrategiaFIFO(), # <-- A única mudança está aqui!
        Criticidade.CONFORTO: EstrategiaFIFO()
    }

    escalonador_hibrido2 = EscalonadorHibrido(estrategias_por_criticidade=configuracao_escalonador2)
    
    # Usamos o MESMO cenário de teste para uma comparação justa
    cenario2 = criar_cenario_de_teste()
    for tarefa in cenario2:
        escalonador_hibrido2.adicionar_tarefa(tarefa)

    # Execute a segunda simulação para comparar os resultados
    # escalonador_hibrido2.simular() # Descomente esta linha quando o método simular estiver pronto.
    print("\nSimulação para o cenário 2 estaria completa aqui.")
    print("\n\n" + "="*60)
    print("COMPARAÇÃO FINAL: Analise os relatórios gerados por cada simulação.")
    print("="*60)
