import streamlit as st
import datetime
import os
from pathlib import Path
from PIL import Image
from supabase import create_client, Client
from dotenv import load_dotenv


# --------------------------------------------------------------
# CONFIGURAÇÃO INICIAL
# --------------------------------------------------------------
st.set_page_config(page_title="Refeitório - Supabase", page_icon="🍽️", layout="wide")

load_dotenv()
# --------------------------------------------------------------
# SUPABASE CLIENT
# --------------------------------------------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("❌ SUPABASE_URL ou SUPABASE_KEY não configurados. Configure em Secrets.")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

BUCKET = "cardapio"

# --------------------------------------------------------------
# USUÁRIOS
# --------------------------------------------------------------
USERS = {
    "admin": {"pwd": "1234", "role": "admin"},
    "mylena": {"pwd": "4321", "role": "user"},
}

# --------------------------------------------------------------
# FUNÇÕES DE DATA
# --------------------------------------------------------------
def segunda_da_semana(data: datetime.date):
    return data - datetime.timedelta(days=data.weekday())

def sexta_da_semana(segunda):
    return segunda + datetime.timedelta(days=4)

def label_intervalo(segunda):
    sexta = sexta_da_semana(segunda)
    return f"Semana de {segunda.strftime('%d/%m/%Y')} a {sexta.strftime('%d/%m/%Y')}"

def chave_semana(segunda):
    return segunda.strftime("%Y-%m-%d")

# --------------------------------------------------------------
# BANCO — SUPABASE
# --------------------------------------------------------------
def listar_unidades():
    resp = supabase.table("unidades").select("nome").order("nome").execute()
    if resp.data:
        return [u["nome"] for u in resp.data]
    return []

def criar_unidade(nome):
    nome = nome.strip()
    if nome:
        supabase.table("unidades").insert({"nome": nome}).execute()

def get_unidade_id(nome):
    resp = supabase.table("unidades").select("id").eq("nome", nome).execute()
    if resp.data:
        return resp.data[0]["id"]

    novo = supabase.table("unidades").insert({"nome": nome}).execute()
    return novo.data[0]["id"]

def salvar_cardapio(unidade, semana_inicio, dia, categoria, guarnicao, proteina, sobremesa, imagem_url):
    unidade_id = get_unidade_id(unidade)

    busca = supabase.table("cardapios").select("id").match({
        "unidade_id": unidade_id,
        "semana_inicio": semana_inicio,
        "dia_semana": dia,
        "categoria": categoria
    }).execute()

    now = datetime.datetime.utcnow().isoformat()

    if busca.data:
        cid = busca.data[0]["id"]
        supabase.table("cardapios").update({
            "guarnicao": guarnicao,
            "proteina": proteina,
            "sobremesa": sobremesa,
            "imagem_url": imagem_url,
            "criado_em": now
        }).eq("id", cid).execute()
    else:
        supabase.table("cardapios").insert({
            "unidade_id": unidade_id,
            "semana_inicio": semana_inicio,
            "dia_semana": dia,
            "categoria": categoria,
            "guarnicao": guarnicao,
            "proteina": proteina,
            "sobremesa": sobremesa,
            "imagem_url": imagem_url
        }).execute()

def buscar_cardapio_semana(unidade, semana):
    unidade_id = get_unidade_id(unidade)
    resp = supabase.table("cardapios").select("*").match({
        "unidade_id": unidade_id,
        "semana_inicio": semana
    }).execute()

    dias = {}
    for r in resp.data:
        d = r["dia_semana"]
        c = r["categoria"]
        dias.setdefault(d, {})[c] = {
            "guarnicao": r["guarnicao"],
            "proteina": r["proteina"],
            "sobremesa": r["sobremesa"],
            "imagem": r["imagem_url"]
        }
    return dias

# --------------------------------------------------------------
# UPLOAD — SUPABASE STORAGE
# --------------------------------------------------------------
def salvar_imagem_upload(file_obj, prefix):
    if not file_obj:
        return None

    content = file_obj.getvalue()
    ext = Path(file_obj.name).suffix
    filename = f"{prefix}_{datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}{ext}"
    path = f"imagens/{filename}"

    supabase.storage.from_(BUCKET).upload(path, content)

    return f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{path}"

# --------------------------------------------------------------
# LOGIN UI
# --------------------------------------------------------------
def css_login():
    st.markdown("""
    <style>
        [data-testid="stSidebar"] { display:none !important; }
        button[title="Main menu"] { display:none !important; }
        button[title="Show sidebar"] { display:none !important; }
        .stTextInput, .stPasswordInput, .stButton {
            max-width: 380px; margin-left:auto; margin-right:auto;
        }
    </style>
    """, unsafe_allow_html=True)

def autenticar(usuario, senha):
    u = USERS.get(usuario)
    if u and u["pwd"] == senha:
        return u["role"]
    return None

def tela_login():
    css_login()
    st.write("")
    st.markdown("<h2 style='text-align:center'>🍽️ Refeitório — Login</h2>", unsafe_allow_html=True)

    user = st.text_input("Usuário")
    pwd = st.text_input("Senha", type="password")

    if st.button("Entrar"):
        role = autenticar(user.strip(), pwd)
        if not role:
            st.error("Usuário ou senha incorretos.")
        else:
            st.session_state.perfil = role
            st.session_state.usuario = user.strip()
            st.rerun()

# --------------------------------------------------------------
# SELEÇÃO DE UNIDADE / SEMANA
# --------------------------------------------------------------
def selecionar_unidade():
    st.sidebar.subheader("Unidade / Refeitório")
    unidades = listar_unidades()

    if st.session_state.perfil == "admin":
        escolha = st.sidebar.selectbox("Selecione a unidade:", ["-- Criar nova --"] + unidades)

        if escolha == "-- Criar nova --":
            nome = st.sidebar.text_input("Nome da nova unidade")
            if st.sidebar.button("Criar"):
                if nome.strip():
                    criar_unidade(nome.strip())
                    st.sidebar.success("Unidade criada.")
                    st.rerun()
            return None
        return escolha

    else:
        if not unidades:
            st.sidebar.warning("Nenhuma unidade cadastrada. Peça ao administrador para criar.")
            return None
        return st.sidebar.selectbox("Selecione a unidade:", unidades)

def selecionar_semana_ui():
    hoje = datetime.date.today()
    data_escolhida = st.date_input("Escolha uma data da semana", value=hoje)
    segunda = segunda_da_semana(data_escolhida)
    chave = chave_semana(segunda)
    label = label_intervalo(segunda)
    st.markdown(f"### 📅 {label}")
    return segunda, chave, label

# --------------------------------------------------------------
# TELA DE USUÁRIO (VISUALIZAR)
# --------------------------------------------------------------
def tela_usuario(unidade):
    st.sidebar.subheader(f"Usuário: {st.session_state.usuario}")
    if st.sidebar.button("Sair"):
        st.session_state.clear()
        st.rerun()

    if not unidade:
        st.info("Selecione uma unidade.")
        return

    st.title("📘 Cardápio da Semana")

    segunda, chave, label = selecionar_semana_ui()
    dados = buscar_cardapio_semana(unidade, chave)

    dias = ["segunda", "terca", "quarta", "quinta", "sexta"]
    nomes = {
        "segunda": "Segunda",
        "terca": "Terça",
        "quarta": "Quarta",
        "quinta": "Quinta",
        "sexta": "Sexta",
    }
    categorias = ["Almoço", "Jantar"]

    for d in dias:
        st.subheader(nomes[d])
        bloco = dados.get(d, {})

        if not bloco:
            st.write("_Sem informações cadastradas_")
        else:
            for c in categorias:
                item = bloco.get(c)
                if not item:
                    st.write(f"- {c}: _não definido_")
                    continue

                col1, col2 = st.columns([1, 3])

                if item["imagem"]:
                    try:
                        col1.image(item["imagem"], width=120)
                    except:
                        col1.write("(imagem indisponível)")

                texto = f"**{c}**"
                partes = []
                if item["guarnicao"]:
                    partes.append(f"Guarnição: {item['guarnicao']}")
                if item["proteina"]:
                    partes.append(f"Proteína: {item['proteina']}")
                if item["sobremesa"]:
                    partes.append(f"Sobremesa: {item['sobremesa']}")

                col2.markdown(texto + "<br>" + "<br>".join(partes), unsafe_allow_html=True)

        st.markdown("---")

# --------------------------------------------------------------
# TELA ADMIN (EDITAR)
# --------------------------------------------------------------
def tela_admin(unidade):
    st.sidebar.subheader(f"Admin: {st.session_state.usuario}")
    if st.sidebar.button("Sair"):
        st.session_state.clear()
        st.rerun()

    if not unidade:
        st.info("Selecione uma unidade.")
        return

    st.title("🛠️ Administração do Cardápio")

    segunda, chave, label = selecionar_semana_ui()

    dias = ["segunda", "terca", "quarta", "quinta", "sexta"]
    categorias = ["Almoço", "Jantar"]

    key_temp = f"temp-{unidade}-{chave}"

    if key_temp not in st.session_state:
        origem = buscar_cardapio_semana(unidade, chave)
        st.session_state[key_temp] = {
            d: {
                c: {
                    "guarnicao": origem.get(d, {}).get(c, {}).get("guarnicao", ""),
                    "proteina": origem.get(d, {}).get(c, {}).get("proteina", ""),
                    "sobremesa": origem.get(d, {}).get(c, {}).get("sobremesa", ""),
                    "imagem": origem.get(d, {}).get(c, {}).get("imagem", None),
                }
                for c in categorias
            }
            for d in dias
        }

    with st.form("form_cardapio"):
        for d in dias:
            st.subheader(f"📌 {d.capitalize()}")
            for c in categorias:
                st.markdown(f"**{c}**")

                temp = st.session_state[key_temp][d][c]

                gu = st.text_input(f"Guarnição ({d}-{c})", value=temp["guarnicao"])
                pr = st.text_input(f"Proteína ({d}-{c})", value=temp["proteina"])
                so = st.text_input(f"Sobremesa ({d}-{c})", value=temp["sobremesa"])

                img_file = st.file_uploader(f"Imagem ({d}-{c})", type=['png', 'jpg', 'jpeg'])

                if img_file:
                    temp["imagem"] = salvar_imagem_upload(img_file, prefix=f"{unidade}_{chave}_{d}_{c}")

                temp["guarnicao"] = gu
                temp["proteina"] = pr
                temp["sobremesa"] = so

        salvar = st.form_submit_button("💾 Salvar Cardápio")

    if salvar:
        for d in dias:
            for c in categorias:
                item = st.session_state[key_temp][d][c]
                if any([item["guarnicao"], item["proteina"], item["sobremesa"]]):
                    salvar_cardapio(
                        unidade, chave, d, c,
                        item["guarnicao"],
                        item["proteina"],
                        item["sobremesa"],
                        item["imagem"],
                    )

        st.success(f"Cardápio da {label} salvo com sucesso!")

        st.session_state[key_temp] = {
            d: {c: {"guarnicao": "", "proteina": "", "sobremesa": "", "imagem": None} for c in categorias}
            for d in dias
        }
        st.rerun()

# --------------------------------------------------------------
# MAIN
# --------------------------------------------------------------
def main():
    if "perfil" not in st.session_state:
        st.session_state.perfil = None

    if st.session_state.perfil is None:
        tela_login()
        return

    unidade = selecionar_unidade()

    paginas = ["Visualizar Cardápio"]
    if st.session_state.perfil == "admin":
        paginas.append("Administrar")

    escolha = st.sidebar.selectbox("Página", paginas)

    if escolha == "Visualizar Cardápio":
        tela_usuario(unidade)
    else:
        tela_admin(unidade)

if __name__ == "__main__":
    main()
