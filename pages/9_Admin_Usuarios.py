import streamlit as st
import auth

# --- VERIFICAÇÃO DE SEGURANÇA ---
# 1. Garante que está logado
auth.validar_sessao()

# 2. Garante que é ADMIN
if not st.session_state.get('usuario_admin'):
    st.error("⛔ Acesso Negado: Você não tem permissão de administrador.")
    st.stop()  # <--- ISSO É CRUCIAL: Interrompe o carregamento do resto da página
# ---------------------------------

# ... Resto do seu código da página ...

from repositories import admin_usuarios_rps as rps

import pandas as pd
import database as db
import time

st.set_page_config(page_title="Admin Usuários", layout="wide", page_icon="🔐")
if not auth.validar_sessao(): auth.tela_login(); st.stop()

# Segurança: Verifica se é admin usando a chave correta definida no auth.py
if not st.session_state.get('usuario_admin'):
    st.error("⛔ Acesso negado. Esta área é restrita a administradores.")
    auth.barra_lateral()
    st.stop()

auth.barra_lateral()
st.title("🔐 Gestão de Usuários e Acessos")



# --- POPUP DE SUCESSO ---
@st.dialog("Sucesso!")
def show_success_modal(mensagem):
    st.success(mensagem)
    if st.button("OK"):
        st.rerun()

tab1, tab2 = st.tabs(["Novo Usuário", "Gerenciar Usuários"])

# Carrega lista de unidades para os formulários (Backend)
todas_unidades = db.buscar_todas_unidades()

# --- ABA 1: NOVO USUÁRIO ---
with tab1:
    st.subheader("Cadastrar Novo Usuário")

    # 1. CONTROLE DE VERSÃO DO FORMULÁRIO
    # Inicializa um contador. Toda vez que ele mudar, o formulário reseta.
    if "user_form_id" not in st.session_state:
        st.session_state["user_form_id"] = 0

    # Pegamos o ID atual para usar nas chaves
    form_id = st.session_state["user_form_id"]  

    with st.form(key=f"form_cadastro_usuario_{form_id}"):
        c1, c2 = st.columns(2)
        
        new_user = c1.text_input("Username (Login)", key=f"u_login_{form_id}")
        new_nome = c2.text_input("Nome Completo", key=f"u_nome_{form_id}")
        new_pass = c1.text_input("Senha Inicial", type="password", key=f"u_pass_{form_id}")
        is_adm = c2.checkbox("É Administrador?", key=f"u_adm_{form_id}")
        
        st.markdown("**Unidades Permitidas:**")
        cols_u = st.columns(4)
        selected_units = []

        if todas_unidades:
            cols_u = st.columns(4)
            for i, u in enumerate(todas_unidades):
                # Assumindo que u[0] é ID e u[1] é Nome
                u_id, u_nome = u[0], u[1]
                
                with cols_u[i % 4]:
                    # A key combina ID da unidade + ID do formulário para resetar corretamente
                    if st.checkbox(u_nome, key=f"unit_{u_id}_{form_id}"):
                        selected_units.append(u_id)
        else:
            st.warning("Nenhuma unidade cadastrada no sistema.")

        # Botão de Envio
        submit_btn = st.form_submit_button("Criar Usuário")
        
        # 5. LÓGICA DE PROCESSAMENTO (FORA DO FORM)
if submit_btn:
    # Validações Básicas
    if len(new_pass) < 6:
        st.error("⚠️ A senha é muito fraca. Escolha uma senha com pelo menos 6 caracteres.")
    # -----------------------------------
    elif not new_user or not new_pass or not selected_units or not new_nome:
        st.error("Preencha login, senha, nome e selecione pelo menos uma unidade.")
    
    else:
        try:
            # Verifica Duplicidade (Sua função ajustada retornando True/False)
            if rps.verifica_usuario_existe(new_user):
                st.error(f"O usuário '{new_user}' já existe. Tente outro.")
            else:
                # Gera Hash
                p_hash = rps._gerar_hash_bcrypt(new_pass)
                
                # Salva no Banco
                rps.criar_usuario_completo(
                    username=new_user, 
                    password_hash=p_hash, 
                    nome=new_nome, 
                    is_admin=is_adm, 
                    lista_unidades_ids=selected_units
                )
                
                # Sucesso
                show_success_modal(f"Usuário {new_user} criado com sucesso!")
                
                # --- O PULO DO GATO (RESET) ---
                # Apenas incrementamos o contador.
                # Na próxima vez que o script rodar, todas as keys terão o número novo (ex: _1)
                # e o Streamlit criará inputs novinhos e vazios.
                st.session_state["user_form_id"] += 1
                
                time.sleep(1.5) # Tempo para ler a mensagem
                st.rerun()      # Recarrega a página para desenhar o formulário novo
                
        except Exception as e:
            st.error(f"Erro ao criar usuário (verifique se o login já existe): {e}")

# --- ABA 2: EDITAR USUÁRIO ---
with tab2:
    st.subheader("Editar Usuários")
    
    # Busca lista de usuários (Backend)
    users = db.buscar_lista_usuarios()
    
    if not users.empty:
        sel_user = st.selectbox(
            "Selecione para editar:", 
            users['username'].tolist(), 
            format_func=lambda x: f"{x} - {users[users['username']==x]['nome_completo'].values[0]}"
        )
        
        if sel_user:
            # Pega dados do DataFrame carregado
            u_data = users[users['username']==sel_user].iloc[0]
            st.divider()
            
            # Busca unidades atuais deste usuário (Backend)
            current_units_ids = db.buscar_ids_unidades_usuario(sel_user)

            with st.form("edit_user"):
                ce1, ce2 = st.columns(2)
                enome = ce1.text_input("Nome", value=u_data['nome_completo'])
                eativo = ce2.checkbox("Ativo?", value=bool(u_data['ativo']))
                eadmin = ce1.checkbox("Administrador?", value=bool(u_data['admin']))
                enova_senha = ce2.text_input("Resetar Senha (deixe vazio para manter)", type="password")
                
                st.markdown("**Acesso às Unidades:**")
                ecols = st.columns(4)
                final_units = []
                
                for i, u in enumerate(todas_unidades):
                    with ecols[i % 4]:
                        # Marca se já estiver na lista do usuário
                        is_checked = u[0] in current_units_ids
                        
                        # CORREÇÃO: Adicionamos 'sel_user' na key.
                        # Isso força o Streamlit a resetar o checkbox quando trocamos de usuário.
                        if st.checkbox(u[1], value=is_checked, key=f"edit_u_{u[0]}_{sel_user}"):
                            final_units.append(u[0])

                if st.form_submit_button("Salvar Alterações"):
                    if not final_units:
                        st.error("O usuário deve ter permissão em pelo menos uma unidade.")
                    else:
                        try:
                            # Prepara hash apenas se houve troca de senha
                            nhash = rps._gerar_hash_bcrypt(enova_senha.encode()) if enova_senha else None
                            # nhash = hashlib.sha256(enova_senha.encode()).hexdigest() if enova_senha else None
                            
                            # Chama função transacional do Backend
                            rps.atualizar_usuario_completo(
                                username=sel_user,
                                nome=enome,
                                is_admin=eadmin,
                                is_ativo=eativo,
                                lista_unidades_ids=final_units,
                                nova_password_hash=nhash
                            )
                            
                            if enova_senha:
                                st.info("Senha alterada no processo.")
                                
                            show_success_modal("Usuário atualizado com sucesso!")
                            
                        except Exception as e:
                            st.error(f"Erro ao atualizar: {e}")
    else:
        st.info("Nenhum usuário cadastrado.")