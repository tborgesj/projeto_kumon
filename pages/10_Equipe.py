import sys
import os

# 1. Pega o caminho absoluto de onde o arquivo '1_Aluno.py' está
diretorio_atual = os.path.dirname(os.path.abspath(__file__))

# 2. Sobe um nível para chegar na raiz do projeto (o pai do diretorio_atual)
diretorio_raiz = os.path.dirname(diretorio_atual)

# 3. Adiciona a raiz à lista de lugares onde o Python procura arquivos
sys.path.append(diretorio_raiz)

from repositories import equipe_rps as rps

import streamlit as st
import auth
import database as db
from datetime import datetime, date, time

st.set_page_config(page_title="Gestão de Equipe", layout="wide", page_icon="👥")
if not auth.validar_sessao(): auth.tela_login(); st.stop()
auth.barra_lateral()

# --- SEGURANÇA ---
unidade_atual = st.session_state.get('unidade_ativa')
nome_unidade = st.session_state.get('unidade_nome', 'Unidade')
if not unidade_atual:
    st.error("Erro de Unidade. Faça login novamente.")
    st.stop()

st.title(f"👥 Gestão de Funcionários - {nome_unidade}")

lista_tipos = rps.buscar_tipos_contratacao()
dict_tipos = {t['nome']: t['id'] for t in lista_tipos}
opcoes_tipos = list(dict_tipos.keys())

# Utilitário visual (apenas formatação)
def format_brl(val): 
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# --- POPUP DE SUCESSO ---
@st.dialog("Sucesso!")
def show_success(msg):
    st.success(msg)
    if st.button("OK"):
        st.rerun()

tab1, tab2 = st.tabs(["Novo Funcionário", "Gerenciar Equipe"])

# ==============================================================================
# ABA 1: NOVO CADASTRO
# ==============================================================================
with tab1:
    st.subheader("Cadastrar Colaborador")
    
    if 'temp_custos' not in st.session_state: st.session_state['temp_custos'] = []
    
    def clear_form():
        st.session_state['temp_custos'] = []
        # Limpa chaves do form se necessário (Streamlit reseta auto com clear_on_submit na maioria dos casos)

    with st.container():
        c1, c2 = st.columns(2)
        nome = c1.text_input("Nome Completo", key="n_nome")
        nome_tipo_sel = c2.selectbox("Contratação", options=opcoes_tipos, key="n_tipo")

        c3, c4 = st.columns(2)
        salario = c3.number_input("Salário Base (R$)", min_value=0.0, step=100.0, key="n_sal")
        dia_pag = c4.number_input("Dia Pagamento", 1, 31, 5, key="n_dia")

        st.divider()
        st.markdown("#### ➕ Benefícios e Impostos Iniciais")
        
        col_tipo, col_nome, col_val, col_dia, col_btn = st.columns([1.5, 2, 1.5, 1, 1])
        tipo_item = col_tipo.selectbox("Tipo", ["Benefício (Despesa)", "Imposto"], key="add_tipo")
        
        sugestoes = ["Vale Alimentação", "Vale Transporte", "Plano de Saúde"] if "Benefício" in tipo_item else ["FGTS", "INSS", "IRRF", "DAS (Simples)"]
        nome_sel = col_nome.selectbox("Descrição", sugestoes + ["Outro..."], key="add_nome_sel")
        nome_final = nome_sel
        if nome_sel == "Outro...": 
            nome_final = col_nome.text_input("Digite o nome", key="add_nome_txt")
            
        val_item = col_val.number_input("Valor (R$)", min_value=0.0, step=10.0, key="add_val")
        dia_item = col_dia.number_input("Dia Venc.", 1, 31, 7 if "Imposto" in tipo_item else dia_pag, key="add_dia")
        
        if col_btn.button("Incluir Item"):
            if nome_final:
                st.session_state['temp_custos'].append({
                    "tipo": "BENEFICIO" if "Benefício" in tipo_item else "IMPOSTO",
                    "nome": nome_final,
                    "valor": val_item,
                    "dia": dia_item
                })
                st.rerun()

        # Lista visual
        if st.session_state['temp_custos']:
            st.caption("Itens a cadastrar:")
            for i, item in enumerate(st.session_state['temp_custos']):
                ic = "🍔" if item['tipo'] == "BENEFICIO" else "🏛️"
                cols = st.columns([4, 2, 1])
                cols[0].text(f"{ic} {item['nome']}")
                cols[1].text(f"{format_brl(item['valor'])} (Dia {item['dia']})")
                if cols[2].button("🗑️", key=f"del_temp_{i}"):
                    st.session_state['temp_custos'].pop(i)
                    st.rerun()

    st.divider()
    
    if st.button("💾 Salvar Funcionário", type="primary"):
        if not nome:
            st.error("Nome é obrigatório.")
        else:
            try:

                id_tipo_sel = dict_tipos.get(nome_tipo_sel)

                # Chama função transacional do Backend
                rps.cadastrar_funcionario_completo(
                    unidade_id=unidade_atual,
                    nome=nome,
                    id_tipo=id_tipo_sel,
                    salario=salario,
                    dia_pag=dia_pag,
                    lista_custos_iniciais=st.session_state['temp_custos']
                )
                clear_form()
                show_success(f"{nome} cadastrado com sucesso!")
                
            except Exception as e:
                st.error(f"Erro ao cadastrar: {e}")

# ==============================================================================
# ABA 2: GERENCIAR
# ==============================================================================
with tab2:
    cf1, cf2 = st.columns([1, 3])
    filtro_status = cf1.radio("Exibir:", ["Ativos", "Inativos", "Todos"], horizontal=True)
    
    # Busca Lista (Backend)
    df = rps.buscar_funcionarios(unidade_atual, filtro_status)
    
    if not df.empty:
        col_esq, col_dir = st.columns([1, 2])
        
        with col_esq:
            st.markdown("### Lista de Colaboradores")
            func_id_sel = st.radio(
                "Selecione:", 
                df['id'].tolist(), 
                format_func=lambda x: df[df['id']==x]['nome'].values[0]
            )
        
        with col_dir:
            st.markdown("### 📝 Edição e Custos")
            if func_id_sel:
                # Busca Detalhes (Backend)
                f_data = rps.buscar_detalhe_funcionario(func_id_sel)
                # indices: 0:id, 1:uid, 2:nome, 3:tipo, 4:salario, 5:dt, 6:dia, 7:ativo, 8:demissao
                
                # --- BLOCO 1: DADOS BÁSICOS E SALÁRIO ---
                with st.form(key=f"edit_func_{func_id_sel}"):
                    ce1, ce2 = st.columns(2)
                    n_nome = ce1.text_input("Nome", value=f_data[2])

                    id_tipo_atual = f_data[3]
                    nome_tipo_atual = next((k for k, v in dict_tipos.items() if v == id_tipo_atual), None)
                    idx_tipo = opcoes_tipos.index(nome_tipo_atual) if nome_tipo_atual in opcoes_tipos else 0
                    
                    n_tipo_nome = ce2.selectbox("Contrato", options=opcoes_tipos, index=idx_tipo)

                    ce3, ce4 = st.columns(2)
                    n_sal = ce3.number_input("Salário (R$)", value=float(db.from_cents(f_data['salario_base'])), step=100.0)
                    n_dia = ce4.number_input("Dia Pagamento", value=int(f_data[6]), min_value=1, max_value=31)
                    
                    is_ativo = f_data[7] == 1
                    novo_status = st.checkbox("Funcionário Ativo?", value=is_ativo)
                    
                    dt_demissao = None
                    if not novo_status:
                        val_date = datetime.strptime(f_data[8], '%Y-%m-%d').date() if f_data[8] else date.today()
                        dt_demissao = st.date_input("Data de Demissão", value=val_date)
                    
                    if st.form_submit_button("Atualizar Dados Básicos"):
                        try:
                            # Passa o ID
                            n_tipo_id = dict_tipos[n_tipo_nome]

                            # Prepara data de demissão para string se necessário
                            dem_str = dt_demissao if not novo_status else None
                            
                            # Chama função inteligente do Backend (com propagação)
                            rps.atualizar_funcionario_completo(
                                func_id=func_id_sel,
                                nome_novo=n_nome,
                                id_tipo=n_tipo_id,
                                salario=n_sal,
                                dia=n_dia,
                                ativo=novo_status,
                                data_demissao=dem_str,
                                unidade_id=unidade_atual,
                                nome_antigo=f_data[2] # Necessário para achar as contas antigas
                            )
                            show_success("Dados atualizados com sucesso!")
                        except Exception as e:
                            st.error(f"Erro: {e}")

                st.divider()
                st.markdown("#### 💲 Custos Adicionais (Benefícios/Impostos)")
                
                # --- BLOCO 2: LISTA DE CUSTOS (Backend) ---
                custos = rps.buscar_custos_funcionario(func_id_sel)
                
                if custos:
                    for c in custos:
                        cid, ctipo, cnome, cval, cdia = c
                        cval = db.from_cents(cval)
                        cc1, cc2, cc3, cc4 = st.columns([3, 2, 2, 1])
                        cc1.text(f"{cnome} ({ctipo})")
                        cc2.text(format_brl(cval))
                        cc3.text(f"Dia {cdia}")
                        
                        if cc4.button("🗑️", key=f"del_cost_{cid}"):
                            try:
                                # Chama função segura do Backend
                                rps.excluir_custo_pessoal(
                                    custo_id=cid,
                                    nome_item=cnome,
                                    nome_funcionario=f_data[2],
                                    unidade_id=unidade_atual
                                )
                                st.toast("Custo removido e despesa cancelada.")
                                time.sleep(1)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro: {e}")
                        st.markdown("<hr style='margin:0; opacity:0.1'>", unsafe_allow_html=True)
                else:
                    st.info("Nenhum custo adicional cadastrado.")
                
                # --- BLOCO 3: ADICIONAR NOVO CUSTO ---
                with st.expander("➕ Adicionar Novo Custo (Para este funcionário)", expanded=False):
                    with st.form(key=f"add_cost_exist_{func_id_sel}", clear_on_submit=True):
                        ac1, ac2, ac3, ac4 = st.columns([2, 2, 1.5, 1])
                        ntipo = ac1.selectbox("Tipo", ["Benefício", "Imposto"])
                        nnome = ac2.text_input("Nome (Ex: Vale Refeição)")
                        nval = ac3.number_input("Valor", min_value=0.0, step=10.0)
                        ndia = ac4.number_input("Dia", 1, 31, 5)
                        
                        if st.form_submit_button("Adicionar"):
                            if not nnome:
                                st.error("Preencha o nome.")
                            else:
                                try:
                                    tipo_bd = "BENEFICIO" if ntipo == "Benefício" else "IMPOSTO"
                                    
                                    # Chama função do Backend (que já gera a despesa do mês)
                                    rps.adicionar_custo_extra_funcionario(
                                        unidade_id=unidade_atual,
                                        func_id=func_id_sel,
                                        tipo_item=tipo_bd,
                                        nome_item=nnome,
                                        valor=nval,
                                        dia_venc=ndia,
                                        nome_funcionario=f_data[2]
                                    )
                                    st.success("Custo adicionado e lançamento financeiro gerado!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Erro: {e}")

    else:
        st.warning("Nenhum funcionário encontrado para o filtro selecionado.")