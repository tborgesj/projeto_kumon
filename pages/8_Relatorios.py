import streamlit as st
import pandas as pd
import database as db
import auth
from datetime import datetime, date
import calendar
import io

# Tenta importar FPDF para PDF
try:
    from fpdf import FPDF
    HAS_FPDF = True
except ImportError:
    HAS_FPDF = False

st.set_page_config(page_title="Relatórios", layout="wide", page_icon="📈")
if not auth.validar_sessao(): auth.tela_login(); st.stop()
auth.barra_lateral()

unidade_atual = st.session_state.get('unidade_ativa')
nome_unidade = st.session_state.get('unidade_nome')
if not unidade_atual: st.error("Erro Unidade"); st.stop()

st.title(f"📈 Relatórios - {nome_unidade}")

if not HAS_FPDF:
    st.warning("⚠️ Biblioteca 'fpdf2' não encontrada. Instale com: `pip install fpdf2`")

# ==============================================================================
# 1. CLASSES DE RELATÓRIO PDF
# ==============================================================================
class PDFReportR2(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, f'R2 - Controle de Alunos - {st.session_state.get("unidade_nome")}', 0, 1, 'C')
        self.ln(5)
        self.set_font('Arial', 'B', 9)
        self.set_fill_color(220, 220, 220)
        self.cell(75, 8, 'Aluno', 1, 0, 'L', 1)
        self.cell(30, 8, 'Disciplina', 1, 0, 'L', 1)
        self.cell(25, 8, 'Estágio', 1, 0, 'C', 1)
        self.cell(25, 8, 'Lição', 1, 0, 'C', 1)
        self.cell(35, 8, 'Blocos', 1, 1, 'C', 1)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Pág {self.page_no()}/{{nb}}', 0, 0, 'C')

def gerar_pdf_r2(df):
    pdf = PDFReportR2(orientation='P', format='A4')
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_font('Arial', '', 9)
    h_line = 8
    for index, row in df.iterrows():
        nome_raw = str(row['Aluno'])
        nome = nome_raw[:35] + '...' if len(nome_raw) > 35 else nome_raw
        pdf.cell(75, h_line, nome, 1, 0, 'L')
        pdf.cell(30, h_line, str(row['Disciplina']), 1, 0, 'L')
        pdf.cell(25, h_line, '', 1, 0, 'C')
        pdf.cell(25, h_line, '', 1, 0, 'C')
        pdf.cell(35, h_line, '', 1, 1, 'C')
    return bytes(pdf.output(dest='S'))

class PDFReportTeste(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, f'Registro de Testes - {st.session_state.get("unidade_nome")}', 0, 1, 'C')
        self.ln(5)
        self.set_font('Arial', 'B', 8)
        self.set_fill_color(220, 220, 220)
        w_col = 16
        colunas_repetidas = ['Data', 'Teste', 'Tempo', 'Nota', 'Grupo', 'Passou']
        self.cell(65, 8, 'Aluno', 1, 0, 'L', 1)
        self.cell(20, 8, 'Disc.', 1, 0, 'C', 1)
        for c in colunas_repetidas:
            self.cell(w_col, 8, c, 1, 0, 'C', 1)
        for i, c in enumerate(colunas_repetidas):
            ln = 1 if i == len(colunas_repetidas) - 1 else 0
            self.cell(w_col, 8, c, 1, ln, 'C', 1)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Pág {self.page_no()}/{{nb}}', 0, 0, 'C')

def gerar_pdf_teste(df):
    pdf = PDFReportTeste(orientation='L', format='A4')
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_font('Arial', '', 8)
    h_line = 8
    w_col = 16
    for index, row in df.iterrows():
        nome_raw = str(row['Aluno'])
        nome = nome_raw[:30] + '..' if len(nome_raw) > 30 else nome_raw
        disc = str(row['Disciplina'])[:3]
        pdf.cell(65, h_line, nome, 1, 0, 'L')
        pdf.cell(20, h_line, disc, 1, 0, 'C')
        for i in range(12):
            ln = 1 if i == 11 else 0
            pdf.cell(w_col, h_line, '', 1, ln, 'C')
    return bytes(pdf.output(dest='S'))

# ==============================================================================
# LÓGICA DE ESTADO (MEMÓRIA)
# ==============================================================================
if 'rel_df' not in st.session_state: st.session_state['rel_df'] = None

# Inicializa o índice do mês com segurança (0 a 11)
idx_atual = datetime.now().month - 1
if 'rel_mes_idx' not in st.session_state: 
    st.session_state['rel_mes_idx'] = idx_atual
else:
    # Trava de segurança: Se vier lixo ou número inválido, reseta
    if st.session_state['rel_mes_idx'] < 0 or st.session_state['rel_mes_idx'] > 11:
        st.session_state['rel_mes_idx'] = idx_atual

if 'rel_ano' not in st.session_state: st.session_state['rel_ano'] = datetime.now().year

# ==============================================================================
# INTERFACE PRINCIPAL
# ==============================================================================
st.subheader("Central de Relatórios")
st.caption("Selecione o período de referência para gerar as listas de controle.")

# --- FORMULÁRIO ---
with st.form("filtro_relatorio"):
    c1, c2, c3 = st.columns([1, 1, 2])
    
    # O index pega do session_state (agora seguro)
    mes_sel_valor = c1.selectbox("Mês", range(1, 13), index=st.session_state['rel_mes_idx'])
    ano_sel = c2.number_input("Ano", min_value=2020, max_value=2030, value=st.session_state['rel_ano'])
    
    # IMPORTANTE: O botão DEVE estar indentado dentro do "with st.form"
    submit = st.form_submit_button("🔍 Pesquisar Alunos")

# --- PROCESSAMENTO ---
if submit:
    # 1. Atualiza memória (Salva o ÍNDICE para o próximo reload: valor 1 = index 0)
    st.session_state['rel_mes_idx'] = mes_sel_valor - 1
    st.session_state['rel_ano'] = ano_sel
    
    dt_inicio_mes = date(ano_sel, mes_sel_valor, 1)
    ultimo_dia = calendar.monthrange(ano_sel, mes_sel_valor)[1]
    dt_fim_mes = date(ano_sel, mes_sel_valor, ultimo_dia)
    
    conn = db.conectar()
    query = '''
        SELECT 
            a.nome as Aluno,
            m.disciplina as Disciplina
        FROM matriculas m
        JOIN alunos a ON m.aluno_id = a.id
        WHERE m.unidade_id = ?
          AND a.nome IS NOT NULL 
          AND m.aluno_id IS NOT NULL
          AND m.data_inicio <= ? 
          AND (m.ativo = 1 OR m.data_fim >= ?)
        ORDER BY a.nome, m.disciplina
    '''
    df = pd.read_sql_query(query, conn, params=(unidade_atual, dt_fim_mes, dt_inicio_mes))
    conn.close()
    
    if not df.empty:
        df = df.dropna(subset=['Aluno'])
        st.session_state['rel_df'] = df
    else:
        st.session_state['rel_df'] = pd.DataFrame() # Vazio
        st.warning("Nenhum aluno encontrado para os critérios selecionados.")

# --- EXIBIÇÃO PERSISTENTE ---
if st.session_state['rel_df'] is not None and not st.session_state['rel_df'].empty:
    df_show = st.session_state['rel_df']
    # Recupera o mês atual baseado no índice salvo (+1 para exibição)
    mes_display = st.session_state['rel_mes_idx'] + 1
    ano_display = st.session_state['rel_ano']
    
    st.divider()
    st.success(f"{len(df_show)} registros carregados.")
    st.dataframe(df_show, use_container_width=True)
    
    st.markdown("### 📥 Exportar Arquivos")
    
    col_r2, col_teste, col_xls = st.columns(3)
    
    # 1. BOTÃO R2
    if HAS_FPDF:
        try:
            pdf_bytes_r2 = gerar_pdf_r2(df_show)
            col_r2.download_button(
                label="📄 Baixar R2 (Controle)",
                data=pdf_bytes_r2,
                file_name=f"R2_Alunos_{mes_display:02d}-{ano_display}.pdf",
                mime="application/pdf",
                type="secondary"
            )
        except Exception as e:
            col_r2.error(f"Erro R2: {e}")

    # 2. BOTÃO TESTE
    if HAS_FPDF:
        try:
            pdf_bytes_teste = gerar_pdf_teste(df_show)
            col_teste.download_button(
                label="📄 Baixar Teste (Notas)",
                data=pdf_bytes_teste,
                file_name=f"Teste_Alunos_{mes_display:02d}-{ano_display}.pdf",
                mime="application/pdf",
                type="primary"
            )
        except Exception as e:
            col_teste.error(f"Erro Teste: {e}")

    # 3. BOTÃO EXCEL
    try:
        buffer_xls = io.BytesIO()
        with pd.ExcelWriter(buffer_xls, engine='xlsxwriter') as writer:
            df_show.to_excel(writer, index=False, sheet_name='Alunos')
        
        col_xls.download_button(
            label="📊 Baixar Excel",
            data=buffer_xls.getvalue(),
            file_name=f"Dados_Alunos_{mes_display:02d}-{ano_display}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        col_xls.error(f"Erro Excel: {e}")