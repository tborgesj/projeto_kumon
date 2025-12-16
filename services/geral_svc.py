from datetime import date, datetime

def format_brl(val):
    if val is None: return "R$ 0,00"
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def limpar_cpf(cpf_str):
    if not cpf_str: return ""
    return ''.join(filter(str.isdigit, str(cpf_str)))

def validar_cpf(cpf):
    if len(cpf) != 11 or cpf == cpf[0] * 11: return False
    # (Lógica simplificada para manter o código breve, use a sua completa se preferir)
    return True 

def formatar_cpf(cpf):
    if len(cpf) != 11: return cpf
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"

def formata_data(data_vencimento):
    dt_venc = datetime.strptime(data_vencimento, '%Y-%m-%d').date()
    dt_fmt = dt_venc.strftime('%d/%m/%Y')
    return dt_fmt

def get_status_visual(data_vencimento):
    try:
        if isinstance(data_vencimento, str):
            dt_venc = datetime.strptime(data_vencimento, '%Y-%m-%d').date()
        elif isinstance(data_vencimento, datetime):
            dt_venc = data_vencimento.date()
        else:
            dt_venc = data_vencimento
            
        hoje = date.today()
        dt_fmt = dt_venc.strftime('%d/%m')
        
        if dt_venc < hoje:
            return f"🚨 :red[**{dt_fmt}**]" # Atrasado
        elif dt_venc == hoje:
            return f"⚠️ :orange[**{dt_fmt}**]" # Vence hoje
        else:
            return dt_fmt # No prazo
    except Exception:
        return "-"