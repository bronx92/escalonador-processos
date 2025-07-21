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
        print(f"⚡ Tarefa {tarefa.nome} bloqueada aguardando {recurso}")


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
            if recurso["dono"] == tarefa:
                # Remover do controle de timeout
                if nome_recurso in self.recursos_alocados:
                    del self.recursos_alocados[nome_recurso]
                
                # Restaurar prioridade original
                tarefa.prioridade_atual = tarefa.prioridade_original
                
                if recurso["fila_espera"]:
                    _, _, proxima_tarefa = heapq.heappop(recurso["fila_espera"])
                    recurso["dono"] = proxima_tarefa
                    proxima_tarefa.estado = "PRONTA"
                    
                    # Registrar nova alocação para timeout
                    self.recursos_alocados[nome_recurso] = (proxima_tarefa, time.perf_counter_ns())
                    
                    print(f"    [RECURSO] '{tarefa.nome}' liberou '{nome_recurso}'. '{proxima_tarefa.nome}' agora é dona.")
                else:
                    recurso["dono"] = None

# ==============================================================================
# PILAR 3: ARQUITETURA DO ESCALONADOR (COM MÉTRICAS E SEGURANÇA)
# ==============================================================================

# 3. Sistema de Mensagens
class MensagensSistema:
    ERRO_DEADLINE = "[CRÍTICO] Tarefa {nome} sem deadline válido"
    ALERTA_TIMEOUT = "[SEGURANÇA] Recurso {recurso} liberado por timeout"
    INFO_MODO_SEGURANCA = "[SISTEMA] Ativado modo segurança"


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
        if tarefa.criticidade == Criticidade.CRITICA:
            if not hasattr(tarefa, 'deadline_relativo') or tarefa.deadline_relativo <= 0:
                raise ValueError(f"Tarefa crítica {tarefa.nome} requer deadline positivo")
        super().adicionar_tarefa(tarefa)

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
                self.gerenciador_recursos.adicionar_tarefa_bloqueada(tarefa)
    
        # 2. Verifica tarefas de TEMPO REAL (RR)
        if self.filas[Criticidade.TEMPO_REAL]:
            for _ in range(len(self.filas[Criticidade.TEMPO_REAL])):
                tarefa = self.filas[Criticidade.TEMPO_REAL].popleft()
                if tarefa.estado != "BLOQUEADA":
                    fim_selecao = time.perf_counter_ns()
                    self.overhead_total_escalonamento += (fim_selecao - inicio_selecao) / 1e6
                    return tarefa
                else:
                # ALTERAÇÃO AQUI: Não recoloca, envia para gerenciador
                self.gerenciador_recursos.adicionar_tarefa_bloqueada(tarefa)
    
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
        tempo_inicio = time.perf_counter_ns()
        
        while self.tempo_simulacao < TEMPO_TOTAL_SIMULACAO:
            tempo_atual = (time.perf_counter_ns() - tempo_inicio) / 1e6  # ms

            # 1. Verificar timeouts periodicamente            
            if self.gerenciador_recursos.verificar_timeouts(tempo_atual):
                continue # Se houve timeout, reiniciar seleção
        
            """Motor principal da simulação."""
            print("\n--- INÍCIO DA SIMULAÇÃO ---")
            
            # Validação inicial de certificados
            for fila in list(self.filas.values()):
                for tarefa in list(fila):
                    if not self.validar_certificado(tarefa):
                        print(f"ALERTA! Tarefa '{tarefa.nome}' com certificado inválido. Removendo.")
                        if isinstance(fila, list):
                            fila.remove(tarefa)
                        elif isinstance(fila, deque):
                            if tarefa in fila:
                                fila.remove(tarefa)
            
            # Loop principal de simulação
            while any([self.tarefa_em_execucao, 
                    self.filas[Criticidade.CRITICA],
                    self.filas[Criticidade.TEMPO_REAL],
                    self.filas[Criticidade.CONFORTO]]):
                
                # 1. Verificar e gerar novas instâncias de tarefas periódicas
                self._verificar_tarefas_periodicas()
                
                # 2. Monitorar deadlines críticos para ativação do modo segurança
                if self.filas[Criticidade.CRITICA]:
                    tarefa_critica = self.filas[Criticidade.CRITICA][0]
                    tempo_restante = tarefa_critica.deadline_absoluto - self.relogio_simulado
                    if tempo_restante < (tarefa_critica.deadline_relativo * 0.3):
                        self.ativar_modo_seguranca(tarefa_critica)
                
                # 3. Selecionar próxima tarefa para execução (com preempção)
                nova_tarefa = self.selecionar_proxima_tarefa()
                if nova_tarefa:
                    # Verificar se precisa preemptar a tarefa atual
                    if self.tarefa_em_execucao and (nova_tarefa.criticidade.value < self.tarefa_em_execucao.criticidade.value):
                        print(f"    [PREEMPÇÃO] '{self.tarefa_em_execucao.nome}' por '{nova_tarefa.nome}'")
                        self.adicionar_tarefa_na_fila(self.tarefa_em_execucao)
                        self.tarefa_em_execucao = None
                    
                    # Iniciar execução da nova tarefa
                    if not self.tarefa_em_execucao:
                        self.tarefa_em_execucao = nova_tarefa
                        if self.tarefa_em_execucao.tempo_inicio_execucao == -1:
                            self.tarefa_em_execucao.tempo_inicio_execucao = self.relogio_simulado
                        print(f"Tempo: {self.relogio_simulado:6.2f} ms | Iniciando: {self.tarefa_em_execucao.nome}")
                
                # 4. Executar a tarefa atual (se existir)
                if self.tarefa_em_execucao:
                    # Verificar se precisa de recurso
                    if self.tarefa_em_execucao.recurso_necessario:
                        recurso_obtido = self.gerenciador_recursos.solicitar(
                            self.tarefa_em_execucao, 
                            self.tarefa_em_execucao.recurso_necessario, 
                            self
                        )
                        if not recurso_obtido:
                            print(f"    [BLOQUEIO] '{self.tarefa_em_execucao.nome}' aguardando recurso")
                            self.tarefa_em_execucao = None
                            continue
                    
                    # Determinar tempo de execução neste ciclo
                    if self.tarefa_em_execucao.criticidade == Criticidade.TEMPO_REAL:
                        tempo_exec = min(self.quantum_rr, self.tarefa_em_execucao.tempo_restante)
                    else:
                        tempo_exec = min(1.0, self.tarefa_em_execucao.tempo_restante)  # Passo de 1ms
                    
                    # Executar a tarefa
                    self.tarefa_em_execucao.tempo_restante -= tempo_exec
                    self.relogio_simulado += tempo_exec
                    
                    print(f"Tempo: {self.relogio_simulado:6.2f} ms | Executando: {self.tarefa_em_execucao.nome} ({self.tarefa_em_execucao.tempo_restante:.2f}ms rest.)")
                    
                    # Verificar se tarefa concluiu
                    if self.tarefa_em_execucao.tempo_restante <= 0:
                        self.tarefa_em_execucao.estado = "CONCLUIDA"
                        self.tarefa_em_execucao.tempo_final_execucao = self.relogio_simulado
                        self.tarefas_concluidas.append(self.tarefa_em_execucao)
                        print(f"    [CONCLUÍDA] '{self.tarefa_em_execucao.nome}' finalizada")
                        
                        # Liberar recursos se necessário
                        if self.tarefa_em_execucao.recurso_necessario:
                            self.gerenciador_recursos.liberar(
                                self.tarefa_em_execucao, 
                                self.tarefa_em_execucao.recurso_necessario
                            )
                        
                        self.tarefa_em_execucao = None
                    
                    # Devolver à fila se for RR e não terminou
                    elif self.tarefa_em_execucao.criticidade == Criticidade.TEMPO_REAL:
                        self.adicionar_tarefa_na_fila(self.tarefa_em_execucao)
                        self.tarefa_em_execucao = None
                        
                if tarefa.concluida:
                    # Atualiza WCRT para tarefas críticas
                    if tarefa.criticidade == Criticidade.CRITICA:
                        tempo_resposta = tarefa.tempo_conclusao - tarefa.tempo_liberacao
                        self.metricas['wcrt_critico'] = max(self.metricas['wcrt_critico'], tempo_resposta)
                    
                    # Verifica deadlines perdidos
                    if hasattr(tarefa, 'deadline_relativo') and tarefa.tempo_conclusao > tarefa.deadline_absoluto:
                        self.metricas['deadlines_perdidos'] += 1
                        raise DeadlinePerdidoError(tarefa.nome)

                # 5. Avançar tempo se sistema ocioso
                else:
                    self.relogio_simulado += 1.0
                    time.sleep(0.001)  # Evitar consumo excessivo de CPU
            
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

    def relatorio_metricas(self):
        """Método UNIFICADO para todos os escalonadores"""
        print("\n=== METRICAS DE DESEMPENHO ===")
        print(f"● Worst-Case Response Time (Crítico): {self.metricas['wcrt_critico']}ms")
        print(f"● Deadlines Perdidos: {self.metricas['deadlines_perdidos']}")
        print(f"● Máximo Jitter Periódico: {self.metricas['max_jitter_periodico']:.2f}ms")
        print(f"● Modos Segurança Ativados: {self.metricas['modos_seguranca_ativados']}")
        print(f"● Overhead Total de Escalonamento: {self.overhead_total_escalonamento:.2f}ms")


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

class EscalonadorHibrido(EscalonadorCAV):
    """
    Um escalonador configurável que utiliza diferentes estratégias para cada
    nível de criticidade.
    """
    def __init__(self, estrategias_por_criticidade: dict):
        super().__init__()  # Chama o init da classe base
        
        # Inicializa filas com os tipos corretos para cada estratégia
        self.filas = {
            Criticidade.CRITICA: [],  # Heap para EDF
            Criticidade.TEMPO_REAL: deque() if isinstance(estrategias_por_criticidade[Criticidade.TEMPO_REAL], (EstrategiaRoundRobin, EstrategiaFIFO)) else [],
            Criticidade.CONFORTO: deque() if isinstance(estrategias_por_criticidade[Criticidade.CONFORTO], (EstrategiaRoundRobin, EstrategiaFIFO)) else []
        }
        
        self.estrategias = estrategias_por_criticidade
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
        self.tarefas_periodicas_template = []

    def _adicionar_tarefa_na_fila(self, tarefa: TarefaCAV):
        """Delega a adição da tarefa para a estratégia correta."""
        estrategia = self.estrategias[tarefa.criticidade]
        fila = self.filas[tarefa.criticidade]
        estrategia.adicionar(fila, tarefa)

    def selecionar_proxima_tarefa(self):
        for nivel in [Criticidade.CRITICA, Criticidade.TEMPO_REAL, Criticidade.CONFORTO]:
            fila = self.filas[nivel]
            if fila:
                tarefa = self.estrategias[nivel].selecionar(fila)
                if tarefa:
                    if tarefa.estado == "BLOQUEADA":
                        self.gerenciador_recursos.adicionar_tarefa_bloqueada(tarefa)
                    else:
                        return tarefa

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
    escalonador_hibrido1.simular() # Descomente esta linha quando o método simular estiver pronto.
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
    escalonador_hibrido2.simular() # Descomente esta linha quando o método simular estiver pronto.
    print("\nSimulação para o cenário 2 estaria completa aqui.")
    print("\n\n" + "="*60)
    print("COMPARAÇÃO FINAL: Analise os relatórios gerados por cada simulação.")
    print("="*60)
