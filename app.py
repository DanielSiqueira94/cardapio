# --------------------------------------------------------------
# app.py — Refeitório migrado para Supabase Auth + profiles (Free / Premium por unidade)
# --------------------------------------------------------------
import os
import datetime
import re
import unicodedata
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")  # public anon key
SERVICE_ROLE_KEY = os.getenv("SERVICE_ROLE_KEY")  # ONLY for admin functions

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("❌ SUPABASE_URL e/ou SUPABASE_KEY não configurados.")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
BUCKET = "cardapio"

# -------------------- HELPERS --------------------
def segunda_da_semana(data: datetime.date):
    return data - datetime.timedelta(days=data.weekday())

def sexta_da_semana(segunda):
    return segunda + datetime.timedelta(days=4)

def label_intervalo(segunda):
    sexta = sexta_da_semana(segunda)
    return f"Semana de {segunda.strftime('%d/%m/%Y')} a {sexta.strftime('%d/%m/%Y')}"

def chave_semana(segunda):
    return segunda.strftime("%Y-%m-%d")

def sanitize_filename(text: str):
    text = unicodedata.normalize("NFD", text)
    text = text.encode("ascii", "ignore").decode("utf-8")
    text = re.sub(r"[^a-zA-Z0-9_\-]", "_", text)
    return text

# -------------------- DB WRAPPERS --------------------
def listar_unidades():
    try:
        resp = supabase.table("unidades").select("nome, plano").order("nome").execute()
        return resp.data or []
    except:
        return []

def criar_unidade(nome, plano="free"):
    try:
        nm = nome.strip()
        if not nm:
            return
        exist = supabase.table("unidades").select("id").eq("nome", nm).limit(1).execute()
        if exist.data:
            return
        supabase.table("unidades").insert({"nome": nm, "plano": plano}).execute()
    except Exception:
        pass

def get_unidade_id(nome):
    try:
        if not nome:
            return None
        resp = supabase.table("unidades").select("id").eq("nome", nome).execute()
        if resp.data:
            return resp.data[0]["id"]
        novo = supabase.table("unidades").insert({"nome": nome}).execute()
        if novo.data:
            return novo.data[0]["id"]
        return None
    except:
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
    }).execute()
    if busca.data:
        supabase.table("cardapios").update({
            "guarnicao": guarnicao,
            "proteina": proteina,
            "sobremesa": sobremesa,
            "imagem_url": imagem_url,
            "criado_em": datetime.datetime.utcnow().isoformat()
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

# Avisos
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

# Upload imagem
def salvar_imagem_upload(file_obj, prefix):
    if not file_obj:
        return None
    try:
        content = file_obj.read()
        ext = Path(file_obj.name).suffix.lower()
        ext_clean = ext.replace(".", "")
        prefix_clean = sanitize_filename(prefix)
        filename = f"{prefix_clean}_{datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}{ext}"
        unidade = prefix_clean.split("_")[0]
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

# -------------------- AUTH / PROFILES --------------------
def sign_in(email_or_usuario, senha):
    email = email_or_usuario.strip()
    if "@" not in email:
        resp = supabase.table("profiles").select("email").ilike("usuario_text", email_or_usuario).execute()
        if resp.data:
            email = resp.data[0]["email"]
        else:
            return None, None

    try:
        auth_resp = supabase.auth.sign_in_with_password({"email": email, "password": senha})
        return auth_resp.user, auth_resp.session
    except Exception:
        return None, None

def get_profile(user_id):
    if not user_id:
        return None
    resp = supabase.table("profiles").select("*").eq("id", str(user_id)).execute()
    if resp.data:
        return resp.data[0]
    return None

def get_unidade_plano(unidade_nome):
    resp = supabase.table("unidades").select("plano").eq("nome", unidade_nome).execute()
    if resp.data:
        return resp.data[0].get("plano", "free")
    return "free"

def count_users_in_unidade(unidade_nome):
    resp = supabase.table("profiles").select("id").eq("unidade", unidade_nome).execute()
    return len(resp.data or [])

def count_admin_unidade_in_unidade(unidade_nome):
    resp = supabase.table("profiles").select("id").eq("unidade", unidade_nome).eq("role", "admin_unidade").execute()
    return len(resp.data or [])

def create_user_via_service_role(email, password, usuario_text, role, unidade):
    if not SERVICE_ROLE_KEY:
        return False, "SERVICE_ROLE_KEY não configurada."

    import requests, json
    url = SUPABASE_URL.rstrip("/") + "/auth/v1/admin/users"
    headers = {
        "apikey": SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SERVICE_ROLE_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "email": email,
        "password": password,
        "email_confirm": True,
        "user_metadata": {"usuario_text": usuario_text}
    }

    r = requests.post(url, headers=headers, data=json.dumps(payload))
    if r.status_code not in (200, 201):
        return False, f"Erro criando auth user: {r.status_code} {r.text}"

    user = r.json()
    user_id = user.get("id")

    try:
        supabase.table("profiles").insert({
            "id": user_id,
            "email": email,
            "usuario_text": usuario_text,
            "role": role,
            "unidade": unidade
        }).execute()
    except Exception as e:
        return False, f"Erro ao inserir profile: {e}"

    return True, "Usuário criado com sucesso."

# -------------------- UI: LOGIN --------------------
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

    usuario = st.text_input("Usuário ou email")
    senha = st.text_input("Senha", type="password")

    if st.button("Entrar"):
        user, session = sign_in(usuario.strip(), senha)
        if not user:
            st.error("Usuário ou senha incorretos.")
        else:
            st.session_state.user = user
            st.session_state.session = session

            profile = get_profile(user.id)
            st.session_state.perfil = profile["role"] if profile else "user"
            st.session_state.unidade_user = profile.get("unidade") if profile else ""
            st.session_state.usuario = profile.get("usuario_text") or user.email

            st.success("Logado!")
            st.rerun()

# -------------------- TELAS / SELETORES --------------------
def selecionar_unidade():
    st.sidebar.subheader("Unidade / Refeitório")

    unidades = supabase.table("unidades").select("id, nome, plano").order("nome").execute().data or []
    unidades_nomes = [u["nome"] for u in unidades]

    if st.session_state.perfil == "admin":
        escolha = st.sidebar.selectbox("Selecione a unidade:", ["-- Criar nova --"] + unidades_nomes)

        if escolha == "-- Criar nova --":
            nome = st.sidebar.text_input("Nome da nova unidade")
            plano_novo = st.sidebar.selectbox("Plano da nova unidade", ["free", "premium"])
            if st.sidebar.button("Criar"):
                if nome.strip():
                    criar_unidade(nome.strip(), plano_novo)
                    st.success("Unidade criada.")
                    st.rerun()
            return None

        unidade_sel = next((u for u in unidades if u["nome"] == escolha), None)

        if unidade_sel:
            st.sidebar.markdown(f"### Plano atual: **{unidade_sel['plano'].upper()}**")

            novo_plano = st.sidebar.selectbox(
                "Alterar plano:",
                ["free", "premium"],
                index=0 if unidade_sel["plano"] == "free" else 1
            )

            if st.sidebar.button("Salvar novo plano"):
                supabase.table("unidades").update({"plano": novo_plano}).eq("id", unidade_sel["id"]).execute()
                st.success("Plano atualizado!")
                st.rerun()

        return escolha

    if st.session_state.perfil in ["user", "admin_unidade"]:
        return st.session_state.unidade_user

    return None

def selecionar_semana_ui():
    hoje = datetime.date.today()
    data_escolhida = st.date_input("Escolha uma data da semana", value=hoje)
    segunda = segunda_da_semana(data_escolhida)
    chave = chave_semana(segunda)
    label = label_intervalo(segunda)
    st.markdown(f"### 📅 {label}")
    return segunda, chave, label

def tela_usuario(unidade):
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

def tela_admin(unidade):
    if not unidade:
        st.info("Selecione uma unidade.")
        return

    st.title("🛠️ Administração do Cardápio")

    segunda, chave, label = selecionar_semana_ui()
    dias = ["segunda", "terca", "quarta", "quinta", "sexta"]
    categorias = ["Almoço", "Jantar"]
    key_temp = f"tmp_{unidade}_{chave}"

    if key_temp not in st.session_state:
        origem = buscar_cardapio_semana(unidade, chave)
        st.session_state[key_temp] = {
            d: {
                c: {
                    "guarnicao": origem.get(d, {}).get(c, {}).get("guarnicao", ""),
                    "proteina": origem.get(d, {}).get(c, {}).get("proteina", ""),
                    "sobremesa": origem.get(d, {}).get(c, {}).get("sobremesa", ""),
                    "imagem": origem.get(d, {}).get(c, {}).get("imagem", None),
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

                temp["guarnicao"] = st.text_input(f"Guarnição ({d}-{c})", temp["guarnicao"])
                temp["proteina"] = st.text_input(f"Proteína ({d}-{c})", temp["proteina"])
                temp["sobremesa"] = st.text_input(f"Sobremesa ({d}-{c})", temp["sobremesa"])

                img = st.file_uploader(
                    f"Imagem ({d}-{c})",
                    type=["jpg", "jpeg", "png"],
                    key=f"img_{unidade}_{chave}_{d}_{c}"
                )
                if img:
                    temp["img_file"] = img

        salvar = st.form_submit_button("💾 Salvar Cardápio")

    if salvar:
        for d in dias:
            for c in categorias:
                item = st.session_state[key_temp][d][c]
                img_url = item.get("imagem")

                if item["img_file"] is not None:
                    prefix = f"{unidade}_{chave}_{d}_{c}"
                    img_url = salvar_imagem_upload(item["img_file"], prefix)
                    item["imagem"] = img_url

                if any([item["guarnicao"], item["proteina"], item["sobremesa"]]):
                    salvar_cardapio(unidade, chave, d, c, item["guarnicao"],
                                    item["proteina"], item["sobremesa"], img_url)

        st.success(f"Cardápio da {label} salvo com sucesso!")
        st.rerun()

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
                if st.session_state.perfil in ["admin", "admin_unidade"]:
                    if st.button(f"Desativar aviso {av['id']}", key=f"del_{av['id']}"):
                        desativar_aviso(av["id"])
                        st.success("Aviso desativado!")
                        st.rerun()

def tela_usuarios():
    if st.session_state.perfil not in ["admin", "admin_unidade"]:
        st.error("Acesso negado.")
        return

    st.title("👥 Gerenciamento de Usuários")
    st.subheader("Cadastrar novo usuário")

    with st.form("form_user"):
        novo_usuario = st.text_input("Usuário (nome de exibição)")
        novo_email = st.text_input("Email do usuário (opcional)")
        nova_senha = st.text_input("Senha (temporária)", type="password")

        if st.session_state.perfil == "admin":
            role = st.selectbox("Perfil", ["user", "admin", "admin_unidade"])
            unidades = listar_unidades()
            unidades_nomes = [u["nome"] for u in unidades]
            unidade_user = st.selectbox("Unidade do usuário", unidades_nomes)
        else:
            role = st.selectbox("Perfil", ["user", "admin_unidade"])
            unidade_user = st.session_state.unidade_user
            st.write(f"Unidade: **{unidade_user}**")

        criar = st.form_submit_button("Cadastrar")

    if criar:
        if not novo_usuario.strip() or not nova_senha.strip():
            st.error("Usuário e senha obrigatórios.")
        else:
            email = novo_email.strip() if novo_email.strip() else novo_usuario.strip().replace(" ", "_") + "@local.invalid"

            plano = get_unidade_plano(unidade_user)
            total_users = count_users_in_unidade(unidade_user)
            total_admins = count_admin_unidade_in_unidade(unidade_user)

            if plano == "free":
                if total_users >= 3:
                    st.error("Limite do plano Free alcançado (máx 3 usuários).")
                elif role == "admin_unidade" and total_admins >= 1:
                    st.error("Plano Free permite apenas 1 admin unidade.")
                else:
                    ok, msg = create_user_via_service_role(email, nova_senha, novo_usuario.strip(), role, unidade_user)
                    if ok:
                        st.success("Usuário criado!")
                        st.rerun()
                    else:
                        st.error(msg)

            else:  # plano premium = sem limites
                ok, msg = create_user_via_service_role(email, nova_senha, novo_usuario.strip(), role, unidade_user)
                if ok:
                    st.success("Usuário criado!")
                    st.rerun()
                else:
                    st.error(msg)

    st.subheader("Usuários Cadastrados")

    if st.session_state.perfil == "admin":
        lista = supabase.table("profiles").select("*").execute().data or []
    else:
        lista = supabase.table("profiles").select("*").eq("unidade", st.session_state.unidade_user).execute().data or []

    if not lista:
        st.info("Nenhum usuário cadastrado.")
        return

    for u in lista:
        col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
        col1.write(f"👤 {u.get('usuario_text') or u.get('email')}")
        col2.write(f"🔑 {u.get('role')}")
        col3.write(f"🏢 {u.get('unidade')}")

        pode_excluir = (
            st.session_state.perfil == "admin"
            or (st.session_state.perfil == "admin_unidade" and u.get("unidade") == st.session_state.unidade_user)
        )

        if pode_excluir:
            if col4.button("Excluir", key=f"del_{u['id']}"):
                import requests
                url = SUPABASE_URL.rstrip("/") + f"/auth/v1/admin/users/{u['id']}"
                headers = {"apikey": SERVICE_ROLE_KEY, "Authorization": f"Bearer {SERVICE_ROLE_KEY}"}
                r = requests.delete(url, headers=headers)
                if r.status_code in (200, 204):
                    supabase.table("profiles").delete().eq("id", u["id"]).execute()
                    st.success("Usuário removido!")
                    st.rerun()
                else:
                    st.error(f"Erro ao excluir: {r.text}")
        else:
            col4.write("—")


# -------------------- TELA MEU PLANO --------------------
def tela_meu_plano(unidade):
    st.title("📦 Meu Plano")

    if not unidade:
        st.info("Selecione uma unidade.")
        return

    resp = supabase.table("unidades").select("nome, plano").eq("nome", unidade).limit(1).execute()
    if not resp.data:
        st.error("Unidade não encontrada.")
        return

    unidade_info = resp.data[0]
    plano = unidade_info["plano"]

    st.subheader(f"🏢 Unidade: **{unidade_info['nome']}**")
    st.markdown(f"### 🌟 Plano atual: **{plano.upper()}**")

    st.markdown("---")

    pode_mudar = st.session_state.perfil in ["admin", "admin_unidade"]

    # ------------------------
    # PLANO FREE
    # ------------------------
    if plano == "free":
        st.info("""
### 🆓 Plano FREE
- Até **3 usuários**
- Cadastro de cardápio
- Avisos
- Upload de imagens
- 1 admin unidade
        """)

        st.markdown("### 🚀 Benefícios do Premium")
        st.markdown("""
- Usuários ilimitados  
- Suporte  
- Sem limite de admin unidade  
""")

        if pode_mudar:
            if st.button("💳 Fazer upgrade para Premium"):
                st.markdown("""
### 🔗 Chave PIX para pagamento  
**123.456.789-10**

Assim que o pagamento for identificado, o plano será atualizado.

""")
        else:
            st.caption("🔒 Apenas administradores podem alterar o plano.")
            
    # PLANO PREMIUM
    else:
        st.success("""
    ### 🏆 Plano PREMIUM
    - Usuários ilimitados  
    - Suporte incluído  
    """)

        if not pode_mudar:
            st.caption("🔒 Apenas administradores podem acessar opções de assinatura.")


# -------------------- MAIN --------------------
def main():
    if "perfil" not in st.session_state:
        st.session_state.perfil = None

    if st.session_state.perfil is None:
        tela_login()
        return

    # Sidebar sempre visível
    st.markdown("<style>[data-testid='stSidebar'] { display:block !important; }</style>", unsafe_allow_html=True)

    # Botão de sair sempre no sidebar
    st.sidebar.markdown(f"👤 **{st.session_state.usuario}**")
    if st.sidebar.button("Sair"):
        supabase.auth.sign_out()
        st.session_state.clear()
        st.rerun()

    unidade = selecionar_unidade()
    role = st.session_state.perfil

    # Menu lateral — Meu Plano só para admin/admin_unidade
    if role in ["admin", "admin_unidade"]:
        paginas = ["Visualizar Cardápio", "Meu Plano", "Administrar", "Avisos", "Usuarios"]
    else:
        paginas = ["Visualizar Cardápio"]

    escolha = st.sidebar.selectbox("Página", paginas)

    if escolha == "Visualizar Cardápio":
        tela_usuario(unidade)

    elif escolha == "Meu Plano":
        tela_meu_plano(unidade)

    elif escolha == "Administrar":
        tela_admin(unidade)

    elif escolha == "Avisos":
        tela_avisos(unidade)

    elif escolha == "Usuarios":
        tela_usuarios()


if __name__ == "__main__":
    main()
