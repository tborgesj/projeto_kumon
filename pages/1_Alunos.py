import sys
import os

# 1. Pega o caminho absoluto de onde o arquivo '1_Aluno.py' está
diretorio_atual = os.path.dirname(os.path.abspath(__file__))

# 2. Sobe um nível para chegar na raiz do projeto (o pai do diretorio_atual)
diretorio_raiz = os.path.dirname(diretorio_atual)

# 3. Adiciona a raiz à lista de lugares onde o Python procura arquivos
sys.path.append(diretorio_raiz)

from repositories import alunos_rps as rps
from services import geral_svc as g_svc

import streamlit as st
import database as db
import auth
import time

# Tenta importar docxtpl para gerar contratos
try:
    from docxtpl import DocxTemplate
    HAS_DOCXTPL = True
except ImportError:
    HAS_DOCXTPL = False

st.set_page_config(page_title="Gestão de Alunos", layout="wide", page_icon="🎓")
if not auth.validar_sessao(): auth.tela_login(); st.stop()
auth.barra_lateral()

unidade_atual = st.session_state.get('unidade_ativa')
if not unidade_atual:
    st.error("Erro de Unidade. Faça login novamente.")
    st.stop()

st.title(f"🎓 Alunos - {st.session_state.get('unidade_nome')}")

# --- POPUP DE SUCESSO ---
@st.dialog("Sucesso!")
def show_success(msg):
    st.success(msg)
    if st.button("OK"):
        st.rerun()

# --- POPUP DE BOLSA ---
@st.dialog("Conceder Bolsa")
def popup_bolsa(mid, disc, val_base):
    st.write(f"**Disciplina:** {disc}")
    st.write(f"**Valor Base:** {g_svc.format_brl(db.from_cents(val_base))}")
    st.info("A bolsa aplica 50% de desconto por um período determinado.")

    
    meses = st.number_input("Duração (Meses)", 1, 12, 6)
    st.write(f"Novo Valor: **{g_svc.format_brl(db.from_cents(val_base) * 0.5)}**")
    
    if st.button("✅ Confirmar Bolsa"):
        try:
            rps.aplicar_bolsa_desconto(mid, meses, unidade_atual)
            st.success("Bolsa aplicada com sucesso!")
            time.sleep(1)
            st.rerun()
        except Exception as e:
            st.error(f"Erro: {e}")

# No início do arquivo 1_Alunos.py (Junto com os outros @st.dialog)

@st.dialog("Alterar Valor da Mensalidade")
def popup_editar_valor(mid, disc, valor_atual):
    st.write(f"Disciplina: **{disc}**")
    
    # Campo para digitar o novo valor
    novo_valor = st.number_input(
        "Novo Valor Acordado (R$)", 
        min_value=0.0, 
        step=10.0, 
        value=float(valor_atual),
        format="%.2f"
    )
    
    st.warning("⚠️ Atenção: Isso alterará o contrato e o valor do boleto atual (se estiver pendente).")
    
    if st.button("💾 Salvar Novo Valor"):
        try:
            rps.atualizar_valor_matricula(mid, novo_valor, unidade_atual)
            st.success("Valor atualizado com sucesso!")
            time.sleep(1)
            st.rerun()
        except Exception as e:
            st.error(f"Erro: {e}")

# --- INIT SESSION STATE ---
if 'disciplinas_temp' not in st.session_state: st.session_state['disciplinas_temp'] = []

# Busca parâmetros globais para usar nas abas (taxa, mensalidade padrão)
params = db.get_parametros_unidade(unidade_atual)

# [NOVO] Carregar lista de canais para os formulários
lista_canais = db.buscar_canais_aquisicao()
# Cria um dicionário auxiliar: {'Indicação': 1, 'Google': 2}
dict_canais = {c['nome']: c['id'] for c in lista_canais}
# Lista apenas os nomes para exibir no selectbox
opcoes_canais = list(dict_canais.keys())

# Carrega disciplinas do banco
lista_disc_bd = db.buscar_disciplinas() # Retorna [{'id':1, 'nome':'Matemática'}, ...]
dict_disc = {d['nome']: d['id'] for d in lista_disc_bd} # {'Matemática': 1}
opcoes_disc = list(dict_disc.keys())

tab1, tab2 = st.tabs(["Matricular Novo Aluno", "Gerenciar Alunos"])

# ==============================================================================
# ABA 1: MATRÍCULA (Transacional)
# ==============================================================================
with tab1:
    st.header("📝 Matricular Novo Aluno")

    # print(f"DEBUG: Valor Original={params}")
    
    # 1. Gestão de Disciplinas Temporárias
    ja_tem = [x['disc_nome'] for x in st.session_state['disciplinas_temp']]
    disp = [d for d in opcoes_disc if d not in ja_tem]
    
    c_sel, c_btn = st.columns([3, 1])
    d_sel = c_sel.selectbox("Disciplina:", ["Selecione..."] + disp)
    
    if c_btn.button("➕ Incluir") and d_sel != "Selecione...":
        val_padrao = float(params['mensalidade']) if params else 0.0
        st.session_state['disciplinas_temp'].append({
            'id_disc': dict_disc[d_sel],
            'disc_nome': d_sel,
            'val': val_padrao, 
            'just': ''
            })
        st.rerun()

    if st.session_state['disciplinas_temp']:
        for i, item in enumerate(st.session_state['disciplinas_temp']):
            cc1, cc2, cc3, cc4 = st.columns([2, 2, 3, 1])
            cc1.markdown(f"**{item['disc_nome']}**") # Mostra o nome
            nv = cc2.number_input(f"R$", value=float(item['val']), step=10.0, key=f"v_{i}")
            nj = cc3.text_input(f"Obs.", value=item['just'], key=f"j_{i}")
            
            st.session_state['disciplinas_temp'][i]['val'] = nv
            st.session_state['disciplinas_temp'][i]['just'] = nj
            
            if cc4.button("🗑️", key=f"d_{i}"):
                st.session_state['disciplinas_temp'].pop(i)
                st.rerun()
    st.divider()

    # 2. Formulário Principal
    with st.form("form_matricula", clear_on_submit=False):
        col_n, col_r = st.columns(2)
        nome = col_n.text_input("Nome do Aluno")
        resp = col_r.text_input("Nome do Responsável")
        
        col_c, col_m = st.columns(2)
        cpf_input = col_c.text_input("CPF Responsável", placeholder="Apenas números ou com pontos", max_chars=14)
        # canal = col_m.selectbox("Canal", ["Indicação", "Google", "Instagram", "Passante", "Outro"])
        nome_canal_selecionado = col_m.selectbox("Canal", opcoes_canais)
        
        col_v, col_t = st.columns(2)
        dia_venc = col_v.number_input("Dia de Vencimento", 1, 31, 10)
        
        # Taxa de Matrícula (Lógica Visual)
        v_taxa = 0.0
        if params and params['campanha']: 
            col_t.warning("Campanha: Taxa Isenta")
        else: 
            v_padrao_taxa = float(params['taxa_matr']) if params else 0.0
            v_taxa = col_t.number_input("Taxa Matrícula", value=v_padrao_taxa)
        
        submitted = st.form_submit_button("✅ Finalizar Matrícula")
        
        if submitted:
            cpf_clean = g_svc.limpar_cpf(cpf_input)
            
            if not nome or not resp or not st.session_state['disciplinas_temp']:
                st.error("Preencha Nome, Responsável e Disciplinas.")
            elif cpf_clean and not g_svc.validar_cpf(cpf_clean):
                st.error("CPF Inválido!")
            else:
                try:
                    # [ALTERADO] Busca o ID correspondente ao nome selecionado
                    id_canal_selecionado = dict_canais.get(nome_canal_selecionado)

                    # Prepara dados
                    dados_aluno = {
                        'nome': nome, 
                        'responsavel': resp, 
                        'cpf': g_svc.formatar_cpf(cpf_clean), 
                        'id_canal': id_canal_selecionado # Envia o ID, não a string
                    }
                    
                    # Chama Backend Seguro
                    rps.realizar_matricula_completa(
                        unidade_id=unidade_atual,
                        dados_aluno=dados_aluno,
                        lista_disciplinas=st.session_state['disciplinas_temp'],
                        dia_vencimento=dia_venc,
                        valor_taxa=v_taxa,
                        campanha_ativa=params['campanha'] if params else False
                    )
                    
                    st.session_state['disciplinas_temp'] = []
                    show_success(f"Aluno {nome} cadastrado com sucesso!")
                    
                except Exception as e:
                    st.error(f"Erro ao matricular: {e}")

# ==============================================================================
# ABA 2: GERENCIAR ALUNOS
# ==============================================================================

# No arquivo pages/1_Alunos.py -> Dentro de "with tab2:"

with tab2:
    # --- BLOCO 1: MESA DE BUSCA E FILTROS ---
    st.markdown("### 🔎 Buscar Alunos")
    
    # Layout de Filtros (Horizontal)
    col_search, col_filter, col_metrics = st.columns([3, 2, 1.5])
    
    termo = col_search.text_input("Nome ou CPF", placeholder="Digite para pesquisar...", key="search_term")
    filtro_status = col_filter.radio("Exibir:", ["Ativos", "Inativos", "Todos"], index=0, horizontal=True)
    
    # Busca no Banco (Função nova)
    df_grid = rps.listar_alunos_grid(unidade_atual, termo, filtro_status)
    
    # Exibe Métricas Rápidas
    total_filtrado = len(df_grid)
    col_metrics.metric("Alunos Encontrados", total_filtrado)

    # Configuração da Tabela Interativa
    st.markdown("Selecione um aluno na tabela para ver o dossiê completo:")
    
    event = st.dataframe(
        df_grid,
        column_config={
            "id": st.column_config.NumberColumn("ID", width="small"),
            "status": st.column_config.TextColumn("Status", width="small"),
            "nome": st.column_config.TextColumn("Nome do Aluno", width="large"),
            "responsavel_nome": st.column_config.TextColumn("Responsável", width="medium"),
            "cpf_responsavel": st.column_config.TextColumn("CPF", width="medium"),
        },
        use_container_width=True,
        hide_index=True,
        selection_mode="single-row", # Permite selecionar apenas 1 por vez
        on_select="rerun",           # Recarrega a página ao clicar
        height=300                   # Altura fixa para não empurrar a tela
    )

    if event.selection.rows:
        # Pega o índice da linha selecionada
        idx_selecionado = event.selection.rows[0]
        
        # O SQLite às vezes não entende o tipo 'int64' do Pandas/Numpy
        aluno_id = int(df_grid.iloc[idx_selecionado]['id'])
        nome_aluno = df_grid.iloc[idx_selecionado]['nome']
        
        st.divider()
        st.header(f"📂 Aluno: {nome_aluno}")
        
        # Busca dados profundos
        a_data = rps.buscar_dados_aluno_completo(aluno_id)
        
        # [CORREÇÃO 2] Verificação de Segurança
        # Se por algum motivo o banco não retornar nada, paramos aqui para não quebrar o formulário
        if a_data is None:
            st.error(f"Erro: Não foi possível carregar os dados do aluno ID {aluno_id}. Tente recarregar a página.")
            st.stop()
            
        # --- ESTRUTURA DE ABAS DO DOSSIÊ ---
        tab_cad, tab_mat, tab_fin, tab_doc = st.tabs(["👤 Cadastro", "📚 Matrículas", "💰 Financeiro", "📄 Documentos"])
        
        # ---------------- ABA CADASTRO ----------------
        with tab_cad:
            # O formulário só abre agora que temos certeza que a_data existe
            with st.form(f"form_edit_{aluno_id}"):
                c1, c2 = st.columns(2)
                
                # Tratamento do Canal (Selectbox)
                # O Erro original acontecia aqui porque a_data era None
                id_atual = a_data['id_canal_aquisicao']
                
                # Tenta achar o nome correspondente a esse ID no dicionário global
                nome_atual_canal = next((k for k, v in dict_canais.items() if v == id_atual), "Outro")
                
                # Verifica se o nome está na lista de opções, senão usa o primeiro
                if nome_atual_canal in opcoes_canais:
                    idx_canal = opcoes_canais.index(nome_atual_canal)
                else:
                    idx_canal = 0

                enome = c1.text_input("Nome", value=a_data['nome'])
                eresp = c2.text_input("Responsável", value=a_data['responsavel_nome'])
                ecpf = c1.text_input("CPF Responsável", value=a_data['cpf_responsavel'])
                ecanal_nome = c2.selectbox("Canal de Aquisição", opcoes_canais, index=idx_canal)
                
                # Agora o botão será alcançado porque o código não quebrou antes
                if st.form_submit_button("💾 Salvar Alterações Cadastrais"):
                    try:
                        ecanal_id = dict_canais[ecanal_nome]
                        rps.atualizar_dados_aluno(aluno_id, enome, eresp, ecpf, ecanal_id)
                        st.success("Cadastro atualizado com sucesso!")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar: {e}")

        # ---------------- ABA MATRÍCULAS ----------------
        with tab_mat:
            mats = rps.buscar_matriculas_aluno(aluno_id, unidade_atual)
            
            # Lista Matrículas Existentes
            if mats:
                for m in mats:
                    mid, disc, val, dia, ativo, b_ativa, b_rest = m
                    
                    with st.container(border=True):
                        cm1, cm2, cm3, cm4 = st.columns([2, 2, 2, 1.5])
                        
                        icon = "🟢 Ativo" if ativo else "🔴 Inativo"
                        cm1.markdown(f"**{disc}**")
                        cm1.caption(icon)
                        
                        with cm2:
                            # Layout de colunas aninhadas para ficar "Valor + Ícone" na mesma linha
                            cv_txt, cv_btn = st.columns([3, 1])
                            valor_reais = db.from_cents(val)
                            
                            cv_txt.metric("Mensalidade", g_svc.format_brl(valor_reais))
                            
                            if ativo:
                                # Botão pequeno (use_container_width=False)
                                if cv_btn.button("✏️", key=f"edit_val_{mid}", help="Alterar valor da mensalidade"):
                                    popup_editar_valor(mid, disc, valor_reais)
                        
                        if ativo:
                            if b_ativa:
                                cm3.info(f"🏷️ Bolsa Ativa: restam {b_rest} meses")
                            else:
                                if cm3.button("Aplicar Bolsa", key=f"btn_b_{mid}"):
                                    popup_bolsa(mid, disc, val)
                            
                            if cm4.button("Inativar", key=f"btn_in_{mid}", type="primary"):
                                rps.inativar_matricula(mid)
                                st.rerun()
                        else:
                            cm3.caption("Matrícula encerrada")
            else:
                st.info("Nenhuma matrícula encontrada.")

            st.markdown("#### ➕ Nova Matrícula")
            with st.expander("Adicionar Disciplina para este aluno"):

                # 1. LÓGICA DE FILTRO (A Mágica acontece aqui)
                # mats[i][1] é o nome da disciplina vindo do banco
                disciplinas_ja_tem = [m[1] for m in mats if m[4]]
                
                # Cria lista apenas com o que o aluno NÃO tem
                disciplinas_livres = [d for d in opcoes_disc if d not in disciplinas_ja_tem]

                with st.form(f"new_mat_{aluno_id}"):
                    c_add1, c_add2 = st.columns(2)
                    ndisc_nome = c_add1.selectbox("Disciplina", disciplinas_livres)
                    nval = c_add2.number_input("Valor Negociado (R$)", min_value=0.0, step=10.0, value=350.00)
                    ndia = c_add1.number_input("Dia Vencimento", 1, 31, 10)
                    njust = c_add2.text_input("Observação")
                    
                    if st.form_submit_button("Matricular Disciplina"):
                        try:
                            ndisc_id = dict_disc[ndisc_nome]
                            rps.adicionar_nova_matricula_aluno_existente(
                                unidade_atual, aluno_id, ndisc_id, nval, ndia, njust
                            )
                            st.success("Disciplina adicionada!")
                            st.rerun()
                        except Exception as e:
                            st.error(e)

        # ---------------- ABA FINANCEIRO ----------------
        with tab_fin:
            df_hist = rps.buscar_historico_financeiro_aluno(aluno_id, unidade_atual)
            
            if not df_hist.empty:
                # Tratamento visual do dataframe financeiro
                df_hist['Valor'] = df_hist['valor_pago'].apply(lambda x: g_svc.format_brl(db.from_cents(x)))
                
                st.dataframe(
                    df_hist[['mes_referencia', 'Valor', 'status', 'tipo']],
                    column_config={
                        "mes_referencia": "Mês Ref",
                        "status": st.column_config.Column("Status"),
                        "tipo": "Tipo Lançamento"
                    },
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("Nenhum histórico financeiro registrado.")

        # ---------------- ABA DOCUMENTOS ----------------
        with tab_doc:
            st.markdown("### Emissão de Contratos")
            st.info("O contrato será gerado com os dados cadastrais atuais e a matrícula mais recente.")
            
            if HAS_DOCXTPL:
                if st.button("📄 Gerar Contrato em Word", key=f"btn_doc_{aluno_id}"):
                    blob = rps.buscar_binario_contrato(unidade_atual)
                    if blob:
                        try:
                            dados_doc = rps.buscar_dados_para_doc_word(aluno_id, unidade_atual)
                            # ... (Lógica de geração do Word igual à anterior) ...
                            # Vou abreviar aqui, mas você mantém o bloco 'try/except' original
                            # que gera e oferece o download_button
                            
                            # (Se quiser posso colar o bloco completo do Word aqui também)
                            st.success("Contrato gerado! (Simulação visual)")
                        except Exception as e:
                            st.error(f"Erro: {e}")
                    else:
                        st.warning("Template de contrato não encontrado nos Parâmetros.")
            else:
                st.warning("Biblioteca docxtpl não instalada.")

    else:
        # ESTADO VAZIO (Ninguém selecionado)
        st.info("👆 Selecione um aluno na tabela acima para visualizar os detalhes.")