# --------------------------------------------------------------
# app.py — Refeitório com Supabase (Versão Revisada com admin_unidade)
# --------------------------------------------------------------
import os
import datetime
import re
import unicodedata
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from supabase import create_client, Client

# -------------------- CONFIG --------------------
st.set_page_config(page_title="Refeitório - Supabase", page_icon="🍽️", layout="wide")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("❌ SUPABASE_URL e/ou SUPABASE_KEY não configurados.")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
BUCKET = "cardapio"  # bucket público

# -------------------- HELPERS DE DATA --------------------
def segunda_da_semana(data: datetime.date):
    return data - datetime.timedelta(days=data.weekday())

def sexta_da_semana(segunda):
    return segunda + datetime.timedelta(days=4)

def label_intervalo(segunda):
    sexta = sexta_da_semana(segunda)
    return f"Semana de {segunda.strftime('%d/%m/%Y')} a {sexta.strftime('%d/%m/%Y')}"

def chave_semana(segunda):
    return segunda.strftime("%Y-%m-%d")

# -------------------- DB FUNÇÕES --------------------
def listar_unidades():
    try:
        resp = supabase.table("unidades").select("nome").order("nome", desc=False).execute()
        return [r["nome"] for r in resp.data] if resp.data else []
    except Exception as e:
        st.error(f"Erro ao listar unidades: {e}")
        return []

def criar_unidade(nome):
    try:
        nm = nome.strip()
        if not nm:
            return
        # evita duplicatas
        exist = supabase.table("unidades").select("id").eq("nome", nm).limit(1).execute()
        if exist.data:
            return
        supabase.table("unidades").insert({"nome": nm}).execute()
    except Exception as e:
        st.error(f"Erro ao criar unidade: {e}")

def get_unidade_id(nome):
    try:
        if not nome:
            return None
        resp = supabase.table("unidades").select("id").eq("nome", nome).limit(1).execute()
        if resp.data:
            return resp.data[0]["id"]

        # se não existe, cria e retorna id
        novo = supabase.table("unidades").insert({"nome": nome}).execute()
        if novo.data:
            return novo.data[0]["id"]
        return None
    except Exception as e:
        # não propagar erro para UX
        return None

def salvar_cardapio(unidade, semana, dia, categoria, guarnicao, proteina, sobremesa, imagem_url):
    unidade_id = get_unidade_id(unidade)
    if not unidade_id:
        return

    busca = supabase.table("cardapios").select("id").match({
        "unidade_id": unidade_id,
        "semana_inicio": semana,
        "dia_semana": dia,
        "categoria": categoria
    }).limit(1).execute()

    if busca.data:
        supabase.table("cardapios").update({
            "guarnicao": guarnicao,
            "proteina": proteina,
            "sobremesa": sobremesa,
            "imagem_url": imagem_url,
            "criado_em": datetime.datetime.utcnow().isoformat(),
        }).eq("id", busca.data[0]["id"]).execute()
    else:
        supabase.table("cardapios").insert({
            "unidade_id": unidade_id,
            "semana_inicio": semana,
            "dia_semana": dia,
            "categoria": categoria,
            "guarnicao": guarnicao,
            "proteina": proteina,
            "sobremesa": sobremesa,
            "imagem_url": imagem_url
        }).execute()

def buscar_cardapio_semana(unidade, semana):
    unidade_id = get_unidade_id(unidade)
    if not unidade_id:
        return {}
    resp = supabase.table("cardapios").select("*").match({
        "unidade_id": unidade_id,
        "semana_inicio": semana
    }).execute()

    dias = {}
    for r in resp.data or []:
        dias.setdefault(r["dia_semana"], {})[r["categoria"]] = {
            "guarnicao": r.get("guarnicao", ""),
            "proteina": r.get("proteina", ""),
            "sobremesa": r.get("sobremesa", ""),
            "imagem": r.get("imagem_url")
        }
    return dias

# -------------------- AVISOS --------------------
def criar_aviso(unidade_nome, titulo, mensagem):
    unidade_id = get_unidade_id(unidade_nome)
    if not unidade_id:
        return
    supabase.table("avisos").insert({
        "unidade_id": unidade_id,
        "titulo": titulo,
        "mensagem": mensagem,
        "ativo": True,
        "criado_em": datetime.datetime.utcnow().isoformat()
    }).execute()

def listar_avisos(unidade_nome):
    unidade_id = get_unidade_id(unidade_nome)
    if not unidade_id:
        return []
    resp = (
        supabase.table("avisos")
        .select("*")
        .eq("unidade_id", unidade_id)
        .eq("ativo", True)
        .order("criado_em", desc=True)
        .execute()
    )
    return resp.data or []

def desativar_aviso(aviso_id):
    supabase.table("avisos").update({"ativo": False}).eq("id", aviso_id).execute()

# -------------------- UPLOAD COM SANITIZAÇÃO --------------------
def sanitize_filename(text: str):
    text = unicodedata.normalize("NFD", text)
    text = text.encode("ascii", "ignore").decode("utf-8")
    text = re.sub(r"[^a-zA-Z0-9_\-]", "_", text)
    return text

def salvar_imagem_upload(file_obj, prefix):
    if not file_obj:
        return None

    try:
        content = file_obj.read()
        ext = Path(file_obj.name).suffix.lower()
        ext_clean = ext.replace(".", "")
        prefix_clean = sanitize_filename(prefix)

        filename = f"{prefix_clean}_{datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}{ext}"

        # AGRUPAR IMAGENS POR UNIDADE
        unidade = prefix_clean.split("_")[0]   # usa a unidade como pasta
        path = f"imagens/{unidade}/{filename}"

        supabase.storage.from_(BUCKET).upload(
            path=path,
            file=content,
            file_options={"content-type": f"image/{ext_clean}"}
        )

        public_url = f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{path}"
        return public_url
    except Exception as e:
        st.error(f"Erro ao enviar imagem: {e}")
        return None

# -------------------- LOGIN --------------------
def autenticar(usuario, senha):
    try:
        resp = (
            supabase.table("usuarios")
            .select("senha, role, unidade")
            .eq("usuario", usuario)
            .limit(1)
            .execute()
        )
        if not resp.data:
            return None

        user = resp.data[0]

        if user["senha"] == senha:
            # garante que role e unidade existem
            role = user.get("role") or "user"
            unidade = user.get("unidade") or ""
            return {"role": role, "unidade": unidade}

        return None

    except Exception as e:
        st.error(f"Erro ao autenticar: {e}")
        return None

def css_login():
    st.markdown("""
    <style>
        [data-testid="stSidebar"] { display:none !important; }
        button[title="Main menu"] { display:none !important; }
        button[title="Show sidebar"] { display:none !important; }
        .stTextInput, .stButton, .stPasswordInput {
            max-width: 380px;
            margin-left: auto;
            margin-right: auto;
        }
    </style>
    """, unsafe_allow_html=True)

def tela_login():
    css_login()
    st.markdown("<h2 style='text-align:center'>🍽️ Refeitório — Login</h2>", unsafe_allow_html=True)

    usuario = st.text_input("Usuário")
    senha = st.text_input("Senha", type="password")

    if st.button("Entrar"):
        auth = autenticar(usuario.strip(), senha)
        if not auth:
            st.error("Usuário ou senha incorretos.")
        else:
            st.session_state.perfil = auth["role"]
            st.session_state.usuario = usuario.strip()
            st.session_state.unidade_user = auth["unidade"]
            st.rerun()

# -------------------- SELETOR DE UNIDADE/SEMANA --------------------
def selecionar_unidade():
    st.sidebar.subheader("Unidade / Refeitório")
    unidades = listar_unidades()

    # ADMIN → pode escolher qualquer unidade e criar novas
    if st.session_state.perfil == "admin":
        escolha = st.sidebar.selectbox("Selecione a unidade:", ["-- Criar nova --"] + unidades)

        if escolha == "-- Criar nova --":
            nome = st.sidebar.text_input("Nome da nova unidade")
            if st.sidebar.button("Criar"):
                if nome.strip():
                    criar_unidade(nome.strip())
                    st.success("Unidade criada.")
                    st.rerun()
            return None

        return escolha

    # USER e ADMIN_UNIDADE → só podem usar sua própria unidade
    if st.session_state.perfil in ["user", "admin_unidade"]:
        return st.session_state.unidade_user

    # fallback
    return None

def selecionar_semana_ui():
    hoje = datetime.date.today()
    data_escolhida = st.date_input("Escolha uma data da semana", value=hoje)
    segunda = segunda_da_semana(data_escolhida)
    chave = chave_semana(segunda)
    label = label_intervalo(segunda)

    st.markdown(f"### 📅 {label}")
    return segunda, chave, label

# -------------------- TELA USUÁRIO --------------------
def tela_usuario(unidade):
    st.sidebar.subheader(f"Usuário: {st.session_state.usuario}")

    if st.sidebar.button("Sair"):
        st.session_state.clear()
        st.rerun()

    if not unidade:
        st.info("Selecione uma unidade.")
        return

    st.title("📘 Cardápio da Semana")

    avisos = listar_avisos(unidade)
    if avisos:
        st.markdown("## 🔔 Avisos do Refeitório")
        for av in avisos:
            st.info(f"**{av['titulo']}**\n\n{av['mensagem']}")
        st.markdown("---")

    segunda, chave, label = selecionar_semana_ui()
    dados = buscar_cardapio_semana(unidade, chave)

    dias = ["sexta", "quinta", "quarta", "terca", "segunda"][::-1]
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
                    st.write(f"• {c}: _não definido_")
                    continue

                col1, col2 = st.columns([1, 3])

                if item["imagem"]:
                    try:
                        col1.image(item["imagem"], width=120)
                    except Exception:
                        pass

                col2.markdown(
                    f"**{c}**<br>"
                    f"Guarnição: {item['guarnicao']}<br>"
                    f"Proteína: {item['proteina']}<br>"
                    f"Sobremesa: {item['sobremesa']}",
                    unsafe_allow_html=True
                )
        st.markdown("---")

# -------------------- TELA ADMIN (CARDÁPIO) --------------------
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

    # estado temporário por (unidade + semana)
    key_temp = f"tmp_{unidade}_{chave}"

    # carregar dados existentes no estado
    if key_temp not in st.session_state:
        origem = buscar_cardapio_semana(unidade, chave)
        st.session_state[key_temp] = {
            d: {
                c: {
                    "guarnicao": origem.get(d, {}).get(c, {}).get("guarnicao", ""),
                    "proteina": origem.get(d, {}).get(c, {}).get("proteina", ""),
                    "sobremesa": origem.get(d, {}).get(c, {}).get("sobremesa", ""),
                    "imagem": origem.get(d, {}).get(c, {}).get("imagem", None),
                    # aqui não fazemos upload; apenas placeholder
                    "img_file": None
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

                temp["guarnicao"] = st.text_input(
                    f"Guarnição ({d}-{c})", temp["guarnicao"]
                )
                temp["proteina"] = st.text_input(
                    f"Proteína ({d}-{c})", temp["proteina"]
                )
                temp["sobremesa"] = st.text_input(
                    f"Sobremesa ({d}-{c})", temp["sobremesa"]
                )

                # 🔥 AGORA: upload NÃO faz mais upload real
                img = st.file_uploader(
                    f"Imagem ({d}-{c})",
                    type=["jpg", "jpeg", "png"],
                    key=f"img_{unidade}_{chave}_{d}_{c}"
                )

                if img:
                    temp["img_file"] = img  # apenas guarda o arquivo

        salvar = st.form_submit_button("💾 Salvar Cardápio")

    # Upload real só acontece aqui
    if salvar:
        for d in dias:
            for c in categorias:
                item = st.session_state[key_temp][d][c]

                # imagem atual salva no BD (se já existia)
                img_url = item.get("imagem")

                # se o usuário anexou uma nova imagem, agora sim fazemos upload:
                if item["img_file"] is not None:
                    prefix = f"{unidade}_{chave}_{d}_{c}"
                    img_url = salvar_imagem_upload(item["img_file"], prefix)
                    item["imagem"] = img_url  # atualizar

                # só salva se houver alguma informação
                if any([item["guarnicao"], item["proteina"], item["sobremesa"]]):
                    salvar_cardapio(
                        unidade,
                        chave,
                        d,
                        c,
                        item["guarnicao"],
                        item["proteina"],
                        item["sobremesa"],
                        img_url  # imagem final (antiga ou nova)
                    )

        st.success(f"Cardápio da {label} salvo com sucesso!")
        st.rerun()

# -------------------- TELA AVISOS --------------------
def tela_avisos(unidade):
    st.title("🔔 Avisos do Refeitório")

    if not unidade:
        st.info("Selecione uma unidade.")
        return

    st.subheader("Criar novo aviso")
    with st.form("form_aviso"):
        titulo = st.text_input("Título")
        mensagem = st.text_area("Mensagem", height=120)
        publicar = st.form_submit_button("📣 Publicar Aviso")

    if publicar:
        if titulo.strip() and mensagem.strip():
            criar_aviso(unidade, titulo.strip(), mensagem.strip())
            st.success("Aviso publicado!")
            st.rerun()
        else:
            st.error("Título e mensagem obrigatórios.")

    st.subheader("Avisos ativos")
    avisos = listar_avisos(unidade)

    if not avisos:
        st.write("Nenhum aviso ativo.")
    else:
        for av in avisos:
            with st.expander(f"{av['titulo']} — {av['criado_em']}"):
                st.write(av["mensagem"])
                # permissões: admin pode desativar qualquer; admin_unidade pode desativar apenas da sua unidade
                pode_desativar = st.session_state.perfil in ["admin", "admin_unidade"]
                if pode_desativar:
                    if st.button(f"Desativar aviso {av['id']}", key=f"del_{av['id']}"):
                        desativar_aviso(av["id"])
                        st.success("Aviso desativado!")
                        st.rerun()

# -------------------- TELA USUÁRIOS --------------------
def tela_usuarios():
    if st.sidebar.button("Sair"):
        st.session_state.clear()
        st.rerun()

    # controle de acesso: apenas admin e admin_unidade
    if st.session_state.perfil not in ["admin", "admin_unidade"]:
        st.error("Acesso negado.")
        return

    st.sidebar.subheader(f"Admin: {st.session_state.usuario}")
    st.title("👥 Gerenciamento de Usuários")

    st.subheader("Cadastrar novo usuário")

    with st.form("form_user"):
        novo_usuario = st.text_input("Usuário")
        nova_senha = st.text_input("Senha", type="password")

        # role selection: admin pode criar qualquer role; admin_unidade só user ou admin_unidade
        if st.session_state.perfil == "admin":
            role = st.selectbox("Perfil", ["user", "admin", "admin_unidade"])
        else:
            role = st.selectbox("Perfil", ["user", "admin_unidade"])

        # unidade selection: admin escolhe, admin_unidade fixa na sua unidade
        if st.session_state.perfil == "admin":
            unidades = listar_unidades()
            unidade_user = st.selectbox("Unidade do usuário", unidades)
        else:
            unidade_user = st.session_state.unidade_user
            st.write(f"Unidade: **{unidade_user}**")

        criar = st.form_submit_button("Cadastrar")

    if criar:
        if not novo_usuario.strip() or not nova_senha.strip():
            st.error("Usuário e senha são obrigatórios.")
        else:
            try:
                supabase.table("usuarios").insert({
                    "usuario": novo_usuario.strip(),
                    "senha": nova_senha.strip(),
                    "role": role,
                    "unidade": unidade_user
                }).execute()
                st.success("Usuário cadastrado com sucesso!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao cadastrar: {e}")

    st.subheader("Usuários Cadastrados")
    # lista: admin vê todos; admin_unidade vê só usuários da sua unidade
    if st.session_state.perfil == "admin":
        lista = supabase.table("usuarios").select("id, usuario, role, unidade").execute().data or []
    else:
        lista = supabase.table("usuarios").select("id, usuario, role, unidade").eq("unidade", st.session_state.unidade_user).execute().data or []

    if lista:
        for u in lista:
            col1, col2, col3, col4 = st.columns([3,2,2,2])
            col1.write(f"👤 {u['usuario']}")
            col2.write(f"🔑 {u['role']}")
            col3.write(f"🏢 {u['unidade']}")

            # permissões de exclusão: admin sempre; admin_unidade apenas para usuários da mesma unidade
            pode_excluir = False
            if st.session_state.perfil == "admin":
                pode_excluir = True
            elif st.session_state.perfil == "admin_unidade" and u["unidade"] == st.session_state.unidade_user:
                pode_excluir = True

            if pode_excluir:
                if col4.button("Excluir", key=f"del_{u['id']}"):
                    try:
                        supabase.table("usuarios").delete().eq("id", u["id"]).execute()
                        st.success("Usuário removido.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao remover usuário: {e}")
            else:
                col4.write("—")
    else:
        st.info("Nenhum usuário cadastrado.")

# -------------------- MAIN --------------------
def main():
    if "perfil" not in st.session_state:
        st.session_state.perfil = None

    # Se não logado -> tela de login + sidebar oculta
    if st.session_state.perfil is None:
        tela_login()
        return

    # Após login → sidebar aparece
    st.markdown("""
    <style>
        [data-testid="stSidebar"] { display:block !important; }
    </style>
    """, unsafe_allow_html=True)

    unidade = selecionar_unidade()
    role = st.session_state.perfil

    paginas = ["Visualizar Cardápio"]
    if role == "admin":
        paginas += ["Administrar", "Avisos", "Usuarios"]
    elif role == "admin_unidade":
        # admin_unidade tem acesso às mesmas páginas, mas as ações são limitadas pelo código acima
        paginas += ["Administrar", "Avisos", "Usuarios"]

    escolha = st.sidebar.selectbox("Página", paginas)

    if escolha == "Visualizar Cardápio":
        tela_usuario(unidade)
    elif escolha == "Administrar":
        tela_admin(unidade)
    elif escolha == "Avisos":
        tela_avisos(unidade)
    elif escolha == "Usuarios":
        tela_usuarios()

if __name__ == "__main__":
    main()
