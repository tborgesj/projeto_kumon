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