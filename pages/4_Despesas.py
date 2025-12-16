from repositories import despesas_rps as rps

import streamlit as st
import pandas as pd
import database as db
import auth
from datetime import datetime, date
import calendar
import time

st.set_page_config(page_title="Gestão de Despesas", layout="wide", page_icon="💸")
if not auth.validar_sessao(): auth.tela_login(); st.stop()
auth.barra_lateral()

# --- SEGURANÇA MULTI-UNIDADE ---
unidade_atual = st.session_state.get('unidade_ativa')
nome_unidade = st.session_state.get('unidade_nome', 'Unidade')

if not unidade_atual:
    st.error("Erro de Unidade. Faça login novamente.")
    st.stop()

st.title(f"💸 Gestão de Despesas - {nome_unidade}")

# --- HELPER FUNCTIONS ---
def format_brl(val): 
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def get_valid_date(year, month, day):
    last_day_of_month = calendar.monthrange(year, month)[1]
    safe_day = min(day, last_day_of_month)
    return date(year, month, safe_day)

@st.dialog("Sucesso!")
def show_success(msg):
    st.success(msg)
    if st.button("OK"):
        st.rerun()

# Carrega Categorias (Backend)
categorias = rps.buscar_categorias_despesas()
tab1, tab2 = st.tabs(["➕ Nova Despesa", "🔄 Gerenciar Recorrências (Fixas)"])

# ==============================================================================
# ABA 1: LANÇAMENTO DE NOVA DESPESA
# ==============================================================================
with tab1:
    st.subheader("Lançar Conta a Pagar")
    st.caption("Use para contas que chegam todo mês (Recorrente) ou gastos únicos (Avulsa).")
    
    with st.container():
        tipo_lancamento = st.radio("Tipo:", ["Avulsa (Única)", "Recorrente (Todo Mês)"], horizontal=True)
        
        with st.form("form_nova_despesa", clear_on_submit=True):
            c1, c2 = st.columns(2)
            desc = c1.text_input("Descrição (Ex: Manutenção Ar Condicionado)")
            
            # Busca categorias do backend (já arrumamos essa função antes)
            categorias = rps.buscar_categorias_despesas()

            map_categorias = {
                c["id"]: c["nome_categoria"]
                for c in categorias
            }

            categoria_id = c2.selectbox(
                "Categoria",
                options=list(map_categorias.keys()),
                format_func=lambda cid: map_categorias[cid]
            )

            c3, c4 = st.columns(2)
            valor = c3.number_input("Valor (R$)", min_value=0.0, step=10.0, format="%.2f")

            valor_final = round(valor, 2)
            
            # Lógica visual de inputs
            dia_venc = 10
            dt_avulsa = date.today()
            
            if tipo_lancamento == "Recorrente (Todo Mês)":
                dia_venc = c4.number_input("Dia de Vencimento Mensal", 1, 31, 10)
                st.info(f"ℹ️ O sistema gerará automaticamente uma conta todo dia {dia_venc}.")
            else:
                dt_avulsa = c4.date_input("Data de Vencimento", value=date.today())
            
            if st.form_submit_button("💾 Salvar Despesa1"):
                if not desc:
                    st.error("A descrição é obrigatória.")
                else:
                    try:
                        if tipo_lancamento == "Recorrente (Todo Mês)":
                            # Chama função complexa do backend
                            rps.adicionar_despesa_recorrente(
                                unidade_id=unidade_atual,
                                categoria=categoria_id,
                                descricao=desc,
                                valor=valor_final,
                                dia_vencimento=dia_venc
                            )
                            st.success("Despesa Fixa criada! A primeira conta já está no Financeiro.")
                        else:
                            # Chama função simples do backend
                            rps.adicionar_despesa_avulsa(
                                unidade_id=unidade_atual,
                                categoria=categoria_id,
                                descricao=desc,
                                valor=valor,
                                data_vencimento=dt_avulsa
                            )
                            st.success("Despesa Avulsa lançada no Financeiro.")
                        
                        time.sleep(1)
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"Erro ao salvar: {e}")

# ==============================================================================
# ABA 2: GERENCIAR RECORRÊNCIAS
# ==============================================================================
with tab2:
    st.subheader("Gerenciar Contas Fixas")
    
    # Lista apenas as ATIVAS por padrão
    filtro_ativo = st.checkbox("Mostrar apenas regras ativas?", value=True)
    
    # 1. Busca Lista (Backend)
    df = rps.buscar_recorrencias(unidade_atual, filtro_ativo)
    
    if not df.empty:
        col_list, col_edit = st.columns([1, 2])
        
        with col_list:
            st.markdown("##### Selecione para Editar:")
            
            # Função auxiliar para formatar texto do radio (pode manter lambda aqui pois é visual)
            def fmt_radio(x):
                row = df[df['id']==x]
                if not row.empty:
                    val = format_brl(db.from_cents(row['valor'].values[0]))
                    return f"{row['descricao'].values[0]} ({val})"
                return "Selecione"

            rec_id_sel = st.radio(
                "Lista:", 
                df['id'].tolist(), 
                format_func=fmt_radio,
                label_visibility="collapsed"
            )

        with col_edit:
            if rec_id_sel:
                # 2. Busca Detalhes (Backend)
                # O retorno é uma tupla. Índices dependem da ordem no banco (Select *)
                # Assumindo ordem: 0:id, 1:uid, 2:cat, 3:desc, 4:val, 5:dia, ... 8:ativo
                r_data = rps.buscar_detalhe_recorrencia(rec_id_sel)
                
                if r_data:
                    st.markdown(f"### ✏️ Editando: {r_data[3]}")
                    
                    with st.form(key=f"edit_rec_{rec_id_sel}"):
                        ec1, ec2 = st.columns(2)
                        
                        # Carrega lista de categorias (se já tiver a função que criamos antes)
                        lista_cats = rps.buscar_categorias_despesas() 
                        idx_cat = lista_cats.index(r_data[2]) if r_data[2] in lista_cats else 0

                        map_categorias = {
                            c["id"]: c["nome_categoria"]
                            for c in lista_cats
                        }
                        
                        categoria_id = ec1.selectbox(
                            "Categoria",
                            options=list(map_categorias.keys()),   # IDs
                            index=idx_cat,
                            format_func=lambda cid: map_categorias[cid]  # O que aparece na tela
                        )

                        n_desc = ec2.text_input("Descrição", value=r_data[3])
                        
                        ec3, ec4 = st.columns(2)
                        n_val = ec3.number_input("Valor Mensal (R$)", value=db.from_cents(float(r_data[4])), step=10.0)
                        n_dia = ec4.number_input("Dia Vencimento", 1, 31, int(r_data[5]))
                        
                        is_ativo_bd = bool(r_data[8])
                        n_ativo = st.checkbox("Despesa Ativa (Gerando cobranças)?", value=is_ativo_bd)
                        
                        if st.form_submit_button("Atualizar Regra"):
                            try:
                                # 3. Atualização Complexa (Backend)
                                rps.atualizar_recorrencia_completa(
                                    id_rec=rec_id_sel,
                                    categoria=categoria_id,
                                    descricao=n_desc,
                                    valor=n_val,
                                    dia=n_dia,
                                    ativo=n_ativo,
                                    unidade_id=unidade_atual
                                )
                                st.success("Regra atualizada e contas pendentes ajustadas!")
                                time.sleep(1)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao atualizar: {e}")
                        
                    st.markdown("---")
                    
                    # Botão de Encerrar
                    if is_ativo_bd:
                        if st.button("🗑️ Encerrar Recorrência (Parar de gerar)", type="primary"):
                            try:
                                rps.encerrar_recorrencia(rec_id_sel)
                                st.success("Recorrência encerrada.")
                                time.sleep(0.5)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro: {e}")
                    else:
                        st.info("Esta despesa já está inativa.")
    else:
        st.info("Nenhuma despesa recorrente encontrada.")