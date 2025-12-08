import streamlit as st
import pandas as pd
import database as db
import auth
import hashlib

st.set_page_config(page_title="Admin Usuários", layout="wide", page_icon="🔐")
if not auth.validar_sessao(): auth.tela_login(); st.stop()

# Segurança: Apenas Admin acessa
if not st.session_state.get('is_admin'):
    st.error("Acesso negado. Apenas administradores.")
    auth.barra_lateral()
    st.stop()

auth.barra_lateral()
st.title("🔐 Gestão de Usuários e Acessos")

# --- POPUP DE SUCESSO (REQUISITO 3) ---
@st.dialog("Sucesso!")
def show_success_modal(mensagem):
    st.success(mensagem)
    if st.button("OK"):
        st.rerun()

conn = db.conectar()

tab1, tab2 = st.tabs(["Novo Usuário", "Gerenciar Usuários"])

# LISTA TODAS UNIDADES PARA O CHECKBOX
todas_unidades = conn.execute("SELECT id, nome FROM unidades").fetchall()

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
        for i, u in enumerate(todas_unidades):
            with cols_u[i % 4]:
                if st.checkbox(u[1], key=f"new_u_{u[0]}"):
                    selected_units.append(u[0])
        
        if st.form_submit_button("Criar Usuário"):
            if not new_user or not new_pass or not selected_units:
                st.error("Preencha login, senha e selecione pelo menos uma unidade.")
            else:
                try:
                    # 1. Cria User
                    p_hash = hashlib.sha256(new_user.encode()).hexdigest() # Criptografa user para usar de salt simples ou senha direta
                    p_hash = hashlib.sha256(new_pass.encode()).hexdigest()
                    
                    conn.execute("INSERT INTO usuarios (username, password_hash, nome_completo, admin, ativo) VALUES (?,?,?,?,1)",
                                 (new_user, p_hash, new_nome, 1 if is_adm else 0))
                    
                    # 2. Vincula Unidades
                    for uid in selected_units:
                        conn.execute("INSERT INTO usuario_unidades (usuario_username, unidade_id) VALUES (?,?)", (new_user, uid))
                    
                    conn.commit()
                    # Chama o Popup
                    show_success_modal(f"Usuário {new_user} criado com sucesso!")
                    
                except Exception as e:
                    st.error(f"Erro (talvez usuário já exista): {e}")

with tab2:
    st.subheader("Editar Usuários")
    users = pd.read_sql("SELECT username, nome_completo, admin, ativo FROM usuarios", conn)
    
    sel_user = st.selectbox("Selecione para editar:", users['username'].tolist(), format_func=lambda x: f"{x} - {users[users['username']==x]['nome_completo'].values[0]}")
    
    if sel_user:
        u_data = users[users['username']==sel_user].iloc[0]
        st.divider()
        
        # Unidades atuais dele
        current_units_res = conn.execute("SELECT unidade_id FROM usuario_unidades WHERE usuario_username=?", (sel_user,)).fetchall()
        current_units_ids = [r[0] for r in current_units_res]

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
                    # Checkbox vem marcado se ele já tem a unidade
                    checked = u[0] in current_units_ids
                    if st.checkbox(u[1], value=checked, key=f"edit_u_{u[0]}"):
                        final_units.append(u[0])

            if st.form_submit_button("Salvar Alterações"):
                if not final_units:
                    st.error("O usuário deve ter pelo menos uma unidade.")
                else:
                    # Atualiza dados básicos
                    conn.execute("UPDATE usuarios SET nome_completo=?, admin=?, ativo=? WHERE username=?", 
                                 (enome, 1 if eadmin else 0, 1 if eativo else 0, sel_user))
                    
                    # Atualiza Senha se digitou
                    if enova_senha:
                        nhash = hashlib.sha256(enova_senha.encode()).hexdigest()
                        conn.execute("UPDATE usuarios SET password_hash=? WHERE username=?", (nhash, sel_user))
                        st.info("Senha alterada.")
                    
                    # Atualiza Unidades (Apaga tudo e recria)
                    conn.execute("DELETE FROM usuario_unidades WHERE usuario_username=?", (sel_user,))
                    for uid in final_units:
                        conn.execute("INSERT INTO usuario_unidades (usuario_username, unidade_id) VALUES (?,?)", (sel_user, uid))
                    
                    conn.commit()
                    show_success_modal("Usuário atualizado com sucesso!")

conn.close()