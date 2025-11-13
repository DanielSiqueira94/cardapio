import streamlit as st
import sqlite3
import datetime
import os
from pathlib import Path
from PIL import Image
import pandas as pd

# --------------------------------------------------------------
# CONFIGURAÇÃO INICIAL
# --------------------------------------------------------------
st.set_page_config(page_title="Refeitório - MVP", page_icon="🍽️", layout="wide")

DATA_DIR = Path("data")
IMG_DIR = DATA_DIR / "images"
DB_PATH = DATA_DIR / "cardapio.db"

os.makedirs(IMG_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# --------------------------------------------------------------
# BANCO DE DADOS
# --------------------------------------------------------------
def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS unidades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT UNIQUE NOT NULL
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS cardapios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        unidade_id INTEGER,
        semana_inicio TEXT,
        dia_semana TEXT,
        categoria TEXT,
        guarnicao TEXT,
        proteina TEXT,
        sobremesa TEXT,
        imagem_path TEXT,
        criado_em TEXT,
        UNIQUE(unidade_id, semana_inicio, dia_semana, categoria)
    );
    """)

    conn.commit()
    conn.close()

init_db()

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
# DB FUNÇÕES
# --------------------------------------------------------------
def listar_unidades():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT nome FROM unidades ORDER BY nome;")
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows

def criar_unidade(nome):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO unidades(nome) VALUES (?)", (nome.strip(),))
        conn.commit()
    except:
        pass
    conn.close()

def get_unidade_id(nome):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM unidades WHERE nome=?", (nome,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute("INSERT INTO unidades(nome) VALUES (?)", (nome,))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id

def salvar_cardapio(unidade, semana, dia, categoria, guarnicao, proteina, sobremesa, imagem_path):
    unidade_id = get_unidade_id(unidade)
    conn = get_conn()
    cur = conn.cursor()
    now = datetime.datetime.utcnow().isoformat()

    cur.execute("""
        SELECT id FROM cardapios
        WHERE unidade_id=? AND semana_inicio=? AND dia_semana=? AND categoria=?
    """, (unidade_id, semana, dia, categoria))

    row = cur.fetchone()

    if row:
        cur.execute("""
            UPDATE cardapios
            SET guarnicao=?, proteina=?, sobremesa=?, imagem_path=?, criado_em=?
            WHERE id=?
        """, (guarnicao, proteina, sobremesa, imagem_path, now, row[0]))
    else:
        cur.execute("""
            INSERT INTO cardapios (
                unidade_id, semana_inicio, dia_semana, categoria,
                guarnicao, proteina, sobremesa, imagem_path, criado_em
            ) VALUES (?,?,?,?,?,?,?,?,?)
        """, (unidade_id, semana, dia, categoria,
              guarnicao, proteina, sobremesa, imagem_path, now))

    conn.commit()
    conn.close()

def buscar_cardapio_semana(unidade, semana):
    unidade_id = get_unidade_id(unidade)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT dia_semana, categoria, guarnicao, proteina, sobremesa, imagem_path
        FROM cardapios
        WHERE unidade_id=? AND semana_inicio=?
    """, (unidade_id, semana))

    rows = cur.fetchall()
    conn.close()

    dias = {}
    for dia, cat, g, p, s, img in rows:
        dias.setdefault(dia, {})[cat] = {
            "guarnicao": g,
            "proteina": p,
            "sobremesa": s,
            "imagem": img
        }
    return dias


# --------------------------------------------------------------
# UPLOAD DE IMAGEM
# --------------------------------------------------------------
def salvar_imagem_upload(file_obj, prefix="img"):
    if not file_obj:
        return None
    ext = Path(file_obj.name).suffix
    filename = f"{prefix}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}{ext}"
    filepath = IMG_DIR / filename
    with open(filepath, "wb") as f:
        f.write(file_obj.getvalue())
    return str(filepath)

# --------------------------------------------------------------
# LOGIN
# --------------------------------------------------------------
def css_login():
    st.markdown("""
    <style>
        [data-testid="stSidebar"] { display:none !important; }
        button[title="Main menu"] { display:none !important; }
        button[title="Show sidebar"] { display:none !important; }
        [data-testid="collapsedControl"] { display:none !important; }
        .stTextInput, .stPasswordInput, .stButton {
            max-width: 380px;
            margin-left: auto;
            margin-right: auto;
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
    st.markdown("<h2 style='text-align:center'>🍽️ Refeitório — Login</h2>", unsafe_allow_html=True)

    user = st.text_input("Usuário")
    pwd = st.text_input("Senha", type="password")

    if st.button("Entrar"):
        role = autenticar(user.strip(), pwd)
        if role is None:
            st.error("Usuário ou senha incorretos.")
        else:
            st.session_state.perfil = role
            st.session_state.usuario = user.strip()
            st.rerun()

# --------------------------------------------------------------
# SELECIONAR UNIDADE / SEMANA
# --------------------------------------------------------------
def selecionar_unidade():
    st.sidebar.subheader("Unidade / Refeitório")
    unidades = listar_unidades()

    if st.session_state.perfil == "admin":
        opcoes = ["-- Criar nova --"] + unidades
        escolha = st.sidebar.selectbox("Selecione a unidade:", opcoes)

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
# TELA USUÁRIO
# --------------------------------------------------------------
def tela_usuario(unidade):
    st.sidebar.subheader(f"Usuário: {st.session_state.get('usuario', '-')}")
    if st.sidebar.button("Sair"):
        st.session_state.perfil = None
        st.session_state.usuario = None
        st.rerun()

    if not unidade:
        st.info("Selecione uma unidade.")
        return

    st.title("📘 Cardápio da Semana")

    segunda, chave, label = selecionar_semana_ui()
    dados = buscar_cardapio_semana(unidade, chave)

    dias = ["segunda", "terca", "quarta", "quinta", "sexta"]
    nomes = {
        "segunda": "Segunda-feira",
        "terca": "Terça-feira",
        "quarta": "Quarta-feira",
        "quinta": "Quinta-feira",
        "sexta": "Sexta-feira",
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
                        img = Image.open(item["imagem"])
                        col1.image(img, width=120)
                    except:
                        col1.write("(imagem indisponível)")
                else:
                    col1.write("")

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
# TELA ADMIN
# --------------------------------------------------------------
def tela_admin(unidade):
    st.sidebar.subheader(f"Admin: {st.session_state.get('usuario')}")
    if st.sidebar.button("Sair"):
        st.session_state.perfil = None
        st.session_state.usuario = None
        st.rerun()

    if not unidade:
        st.info("Selecione uma unidade.")
        return

    st.title("🛠️ Administração do Cardápio")

    segunda, chave, label = selecionar_semana_ui()

    dias = ["segunda", "terca", "quarta", "quinta", "sexta"]
    categorias = ["Almoço", "Jantar"]

    key_temp = f"temp_{unidade}_{chave}"

    if key_temp not in st.session_state:
        origem = buscar_cardapio_semana(unidade, chave)
        st.session_state[key_temp] = {
            d: {  
                c: {
                    "guarnicao": origem.get(d, {}).get(c, {}).get("guarnicao", ""),
                    "proteina": origem.get(d, {}).get(c, {}).get("proteina", ""),
                    "sobremesa": origem.get(d, {}).get(c, {}).get("sobremesa", ""),
                    "imagem": origem.get(d, {}).get(c, {}).get("imagem", None),
                } for c in categorias
            } for d in dias
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

                img_file = st.file_uploader(
                    f"Imagem ({d}-{c})",
                    type=['png','jpg','jpeg']
                )

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
                        item["imagem"]
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
    role = st.session_state.perfil

    paginas = ["Visualizar Cardápio"]
    if role == "admin":
        paginas.append("Administrar")

    escolha = st.sidebar.selectbox("Página", paginas)

    if escolha == "Visualizar Cardápio":
        tela_usuario(unidade)
    else:
        tela_admin(unidade)

if __name__ == "__main__":
    main()
