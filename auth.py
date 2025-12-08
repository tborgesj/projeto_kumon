import streamlit as st
import time
import database as db

# --- 1. LÓGICA DE SESSÃO E LOGIN ---

def validar_sessao():
    """
    Verifica se existe usuário logado.
    Usa .get() para não quebrar com erros de chave inexistente.
    """
    return st.session_state.get('usuario_logado') is not None

def logout():
    """
    Remove as chaves de sessão e recarrega.
    """
    keys = ['usuario_logado', 'usuario_nome', 'usuario_admin', 'unidade_ativa', 'unidade_nome', 'seletor_unidade_key']
    for k in keys:
        if k in st.session_state:
            del st.session_state[k]
    st.rerun()

def realizar_login(usuario, senha):
    """
    Valida credenciais e inicializa a sessão.
    """
    try:
        sucesso, nome, admin = db.verificar_credenciais(usuario, senha)
        if sucesso:
            st.session_state['usuario_logado'] = usuario
            st.session_state['usuario_nome'] = nome
            st.session_state['usuario_admin'] = admin
            
            # Carrega unidade inicial padrão
            try:
                unis = db.get_unidades_usuario(usuario)
                if unis:
                    st.session_state['unidade_ativa'] = unis[0][0]
                    st.session_state['unidade_nome'] = unis[0][1]
            except:
                st.session_state['unidade_ativa'] = None
                
            return True
        return False
    except Exception as e:
        st.error(f"Erro de conexão: {e}")
        return False

# --- 2. CALLBACKS (O Segredo da Atualização) ---

def atualizar_unidade_selecionada():
    """
    Função chamada AUTOMATICAMENTE quando o usuário muda o selectbox.
    Ela garante que a troca de unidade seja registrada na hora.
    """
    novo_id = st.session_state['seletor_unidade_key']
    usuario = st.session_state.get('usuario_logado')
    
    # Atualiza o ID na sessão
    st.session_state['unidade_ativa'] = novo_id
    
    # Atualiza o Nome na sessão (busca rápida para garantir consistência)
    if usuario:
        unis = db.get_unidades_usuario(usuario)
        for u in unis:
            if u[0] == novo_id:
                st.session_state['unidade_nome'] = u[1]
                break

# --- 3. COMPONENTES VISUAIS ---

def tela_login():
    c1, c2, c3 = st.columns([1, 1, 1])
    with c2:
        st.title("🔐 Acesso")
        with st.form("login_form"):
            user_input = st.text_input("Usuário")
            pass_input = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar", type="primary", use_container_width=True):
                if realizar_login(user_input, pass_input):
                    st.success("Bem-vindo!")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("Dados incorretos.")

def barra_lateral():
    with st.sidebar:
        st.write(f"👤 **{st.session_state.get('usuario_nome', 'Usuário')}**")
        
        usuario = st.session_state.get('usuario_logado')
        
        # --- SELETOR DE UNIDADE (CORRIGIDO) ---
        if usuario:
            try:
                unis = db.get_unidades_usuario(usuario)
                if unis:
                    opcoes = {u[0]: u[1] for u in unis}
                    atual = st.session_state.get('unidade_ativa')
                    
                    # Verifica índice para posicionar o seletor corretamente
                    lista_ids = list(opcoes.keys())
                    idx = lista_ids.index(atual) if atual in lista_ids else 0
                    
                    # A MÁGICA ESTÁ AQUI: key + on_change
                    st.selectbox(
                        "Unidade:", 
                        options=lista_ids, 
                        format_func=lambda x: opcoes[x], 
                        index=idx,
                        key='seletor_unidade_key',          # Chave única para este widget
                        on_change=atualizar_unidade_selecionada # Chama a função ao mudar
                    )
            except Exception as e:
                st.error("Erro ao carregar unidades.")

        st.divider()
        
        # === MENU DE NAVEGAÇÃO ===
        
        # 1. HOME (Capa)
        st.page_link("Home.py", label="Home", icon="🏠")
        
        # 2. VISÃO ESTRATÉGICA (Dashboard Dedicado)
        st.markdown("### Visão Estratégica")
        st.page_link("pages/5_Dashboard.py", label="Dashboard", icon="📊")
        
        # 3. SECRETARIA
        st.markdown("### Secretaria")
        st.page_link("pages/1_Alunos.py", label="Alunos & Matrículas", icon="🎓")
        
        # 4. FINANCEIRO
        st.markdown("### Financeiro")
        st.page_link("pages/2_Financeiro.py", label="Movimentações", icon="💸")
        st.page_link("pages/4_Despesas.py", label="Contas a Pagar", icon="🧾")
        st.page_link("pages/6_Cofres.py", label="Cofres e Reservas", icon="🏦")
        st.page_link("pages/7_Bolsas.py", label="Gestão de Bolsas", icon="🎗️")
        
        # 5. RELATÓRIOS
        st.markdown("### Relatórios")
        st.page_link("pages/8_Relatorios.py", label="Relatório Geral", icon="📈")
        
        # 6. CONFIGURAÇÕES
        st.markdown("### Configurações")
        with st.expander("Ajustes do Sistema", expanded=False):
            st.page_link("pages/3_Parametros.py", label="Parâmetros", icon="🛠️")
            st.page_link("pages/11_Migracao.py", label="Migração", icon="🚚")
            st.page_link("pages/10_Equipe.py", label="Equipe & RH", icon="👥") 

            
            if st.session_state.get('usuario_admin'):
                st.page_link("pages/9_Admin_Usuarios.py", label="Admin Usuários", icon="🔑")
        
        st.divider()
       
        st.divider()
        if st.button("Sair / Logout", use_container_width=True):
            logout()