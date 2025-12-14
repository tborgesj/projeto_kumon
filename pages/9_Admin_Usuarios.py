import streamlit as st
import pandas as pd
import database as db
import auth
import bcrypt

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
    with st.form("new_user_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        new_user = c1.text_input("Username (Login)")
        new_nome = c2.text_input("Nome Completo")
        new_pass = c1.text_input("Senha Inicial", type="password")
        is_adm = c2.checkbox("É Administrador?")
        
        st.markdown("**Unidades Permitidas:**")
        cols_u = st.columns(4)
        selected_units = []
        
        # Gera checkboxes dinamicamente
        for i, u in enumerate(todas_unidades):
            # u[0] = id, u[1] = nome
            with cols_u[i % 4]:
                if st.checkbox(u[1], key=f"new_u_{u[0]}"):
                    selected_units.append(u[0])
        
        if st.form_submit_button("Criar Usuário"):
            if not new_user or not new_pass or not selected_units:
                st.error("Preencha login, senha e selecione pelo menos uma unidade.")
            else:
                try:
                    # Gera Hash da Senha
                    p_hash = db._gerar_hash_bcrypt(new_pass)
                    
                    # Chama função transacional do Backend
                    db.criar_usuario_completo(
                        username=new_user, 
                        password_hash=p_hash, 
                        nome=new_nome, 
                        is_admin=is_adm, 
                        lista_unidades_ids=selected_units
                    )
                    
                    show_success_modal(f"Usuário {new_user} criado com sucesso!")
                    
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
                            nhash = db._gerar_hash_bcrypt(enova_senha.encode()) if enova_senha else None
                            # nhash = hashlib.sha256(enova_senha.encode()).hexdigest() if enova_senha else None
                            
                            # Chama função transacional do Backend
                            db.atualizar_usuario_completo(
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