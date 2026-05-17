from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import sqlite3
import re
import os
from threading import Timer

app = Flask(__name__)
app.secret_key = "123"

# ================= LOGIN =================
USUARIO = "supervisor"
SENHA = "luciano"


# ================= BANCO =================
def conectar():

    conn = sqlite3.connect("frota.db")
    conn.row_factory = sqlite3.Row

    return conn


def verificar_login():

    return session.get("logado")


def remover_disponivel(cursor, codigo):

    if not codigo:
        return

    cursor.execute(
        "DELETE FROM disponiveis WHERE codigo=?",
        (codigo,)
    )


def adicionar_disponivel(cursor, codigo, tipo):

    if not codigo:
        return

    existente = cursor.execute(
        "SELECT 1 FROM disponiveis WHERE codigo=?",
        (codigo,)
    ).fetchone()

    if existente:

        cursor.execute(
            "UPDATE disponiveis SET status='Reserva' WHERE codigo=?",
            (codigo,)
        )

    else:

        cursor.execute("""
            INSERT INTO disponiveis (
                codigo,
                tipo,
                status
            )
            VALUES (?, ?, 'Reserva')
        """, (codigo, tipo))


def normalizar(texto):

    if not texto:
        return ""

    return (
        texto.strip()
        .upper()
        .replace("Á", "A")
        .replace("À", "A")
        .replace("Ã", "A")
        .replace("É", "E")
        .replace("Í", "I")
        .replace("Ó", "O")
        .replace("Ú", "U")
        .replace("Ç", "C")
    )


def codigo_valido(codigo, tipo):

    if not codigo:
        return True

    if tipo == "MOTORISTA":
        return re.fullmatch(r"M\d+", codigo) is not None

    if tipo == "COLETOR":
        return re.fullmatch(r"C\d+", codigo) is not None

    return False


def criar_tabelas():

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS equipes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        Setor_ID TEXT,
        Frota TEXT,
        Motorista TEXT,
        C1 TEXT,
        C2 TEXT,
        C3 TEXT,
        Hora_Saida TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS disponiveis (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo TEXT UNIQUE,
        tipo TEXT,
        status TEXT
    )
    """)

    conn.commit()
    conn.close()


criar_tabelas()


# ================= LOGIN =================
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        usuario = request.form.get("usuario", "").strip()
        senha = request.form.get("senha", "").strip()

        if usuario == USUARIO and senha == SENHA:

            session["logado"] = True

            return redirect(url_for("index"))

        flash("Usuário ou senha inválidos")

    return render_template("login.html")


# ================= LOGOUT =================
@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))


# ================= HOME =================
@app.route("/")
def index():

    if not verificar_login():

        return redirect(url_for("login"))

    return render_template("index.html")


# ================= EQUIPES =================
@app.route("/equipes")
def equipes():

    if not verificar_login():

        return redirect(url_for("login"))

    conn = conectar()

    dados = conn.execute("""
        SELECT * FROM equipes
        ORDER BY
            CASE
                WHEN Setor_ID LIKE 'PD%' THEN 1
                WHEN Setor_ID LIKE 'ID%' THEN 2
                ELSE 3
            END,
            CAST(
                CASE
                    WHEN LENGTH(Setor_ID) > 2
                    THEN SUBSTR(Setor_ID, 3)
                    ELSE 0
                END AS INTEGER
            )
    """).fetchall()

    conn.close()

    return render_template(
        "equipes.html",
        dados=dados
    )


# ================= DISPONIVEIS =================
@app.route("/disponiveis")
def disponiveis():

    if not verificar_login():

        return redirect(url_for("login"))

    conn = conectar()

    dados = conn.execute("""
        SELECT * FROM disponiveis
        ORDER BY tipo, status, codigo
    """).fetchall()

    conn.close()

    return render_template(
        "disponiveis.html",
        dados=dados
    )


# ================= LOCALIZAR =================
@app.route("/localizar", methods=["POST"])
def localizar():

    if not verificar_login():

        return redirect(url_for("login"))

    try:

        codigo = (
            request.form.get("codigo") or ""
        ).strip().upper()

        if not codigo:

            flash("⚠️ Informe um código")

            return redirect(url_for("equipes"))

        conn = conectar()
        cursor = conn.cursor()

        equipe = cursor.execute("""
            SELECT Setor_ID FROM equipes
            WHERE
                Motorista=?
                OR C1=?
                OR C2=?
                OR C3=?
        """, (
            codigo,
            codigo,
            codigo,
            codigo
        )).fetchone()

        if equipe:

            flash(
                f"📍 {codigo} está no setor {equipe['Setor_ID']}"
            )

            conn.close()

            return redirect(url_for("equipes"))

        disponivel = cursor.execute("""
            SELECT status FROM disponiveis
            WHERE codigo=?
        """, (codigo,)).fetchone()

        if disponivel:

            flash(
                f"📍 {codigo} está em {disponivel['status']}"
            )

            conn.close()

            return redirect(url_for("equipes"))

        conn.close()

        flash(f"❌ Código {codigo} não encontrado")

    except Exception as e:

        print("ERRO LOCALIZAR:", e)

        flash("Erro ao localizar código")

    return redirect(url_for("equipes"))


# ================= MAPA =================
@app.route("/mapa/<setor>")
def ver_mapa(setor):

    if not verificar_login():

        return redirect(url_for("login"))

    try:

        setor = (
            setor or ""
        ).strip().upper()

        extensoes = [
            ".jpeg",
            ".jpg",
            ".png"
        ]

        for ext in extensoes:

            caminho = os.path.join(
                "static",
                "mapas",
                f"{setor}{ext}"
            )

            if os.path.exists(caminho):

                arquivo = f"{setor}{ext}"

                return render_template(
                    "mapa.html",
                    arquivo=arquivo
                )

        flash(
            f"⚠️ Mapa do setor {setor} não encontrado"
        )

    except Exception as e:

        print("ERRO MAPA:", e)

        flash("Erro ao abrir mapa")

    return redirect(url_for("equipes"))


# ================= CADASTRAR =================
@app.route("/add", methods=["POST"])
def add():

    if not verificar_login():

        return redirect(url_for("login"))

    try:

        setor = normalizar(
            request.form.get("setor_id")
        )

        frota = normalizar(
            request.form.get("frota")
        )

        motorista = normalizar(
            request.form.get("motorista")
        )

        c1 = normalizar(
            request.form.get("c1")
        )

        c2 = normalizar(
            request.form.get("c2")
        )

        c3 = normalizar(
            request.form.get("c3")
        )

        hora = request.form.get("hora_saida") or ""

        if motorista and not codigo_valido(
            motorista,
            "MOTORISTA"
        ):

            flash("❌ Motorista inválido! Use M123")

            return redirect(url_for("equipes"))

        for c in [c1, c2, c3]:

            if c and not codigo_valido(
                c,
                "COLETOR"
            ):

                flash("❌ Coletor inválido! Use C123")

                return redirect(url_for("equipes"))

        if not motorista and not c1 and not c2 and not c3:

            flash(
                "❌ Informe pelo menos um motorista ou coletor!"
            )

            return redirect(url_for("equipes"))

        lista = [motorista, c1, c2, c3]
        lista = [x for x in lista if x]

        if len(lista) != len(set(lista)):

            flash("❌ Código repetido na mesma equipe!")

            return redirect(url_for("equipes"))

        conn = conectar()
        cursor = conn.cursor()

        for codigo in lista:

            conflito = cursor.execute("""
                SELECT Setor_ID FROM equipes
                WHERE
                    Motorista=?
                    OR C1=?
                    OR C2=?
                    OR C3=?
            """, (
                codigo,
                codigo,
                codigo,
                codigo
            )).fetchone()

            if conflito:

                flash(
                    f"❌ Código {codigo} já está na equipe {conflito['Setor_ID']}"
                )

                conn.close()

                return redirect(url_for("equipes"))

        cursor.execute("""
            INSERT INTO equipes (
                Setor_ID,
                Frota,
                Motorista,
                C1,
                C2,
                C3,
                Hora_Saida
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            setor,
            frota,
            motorista,
            c1,
            c2,
            c3,
            hora
        ))

        remover_disponivel(cursor, motorista)
        remover_disponivel(cursor, c1)
        remover_disponivel(cursor, c2)
        remover_disponivel(cursor, c3)

        conn.commit()
        conn.close()

        flash("✅ Equipe cadastrada com sucesso!")

    except Exception as e:

        print("ERRO ADD:", e)

        flash("Erro ao cadastrar")

    return redirect(url_for("equipes"))


# ================= SALVAR =================
@app.route("/salvar", methods=["POST"])
def salvar():

    if not verificar_login():

        return redirect(url_for("login"))

    try:

        id = request.form.get("id")

        setor = normalizar(
            request.form.get("setor_id")
        )

        frota = normalizar(
            request.form.get("frota")
        )

        motorista = normalizar(
            request.form.get("motorista")
        )

        c1 = normalizar(
            request.form.get("c1")
        )

        c2 = normalizar(
            request.form.get("c2")
        )

        c3 = normalizar(
            request.form.get("c3")
        )

        hora = request.form.get("hora_saida") or ""

        conn = conectar()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE equipes SET
                Setor_ID=?,
                Frota=?,
                Motorista=?,
                C1=?,
                C2=?,
                C3=?,
                Hora_Saida=?
            WHERE id=?
        """, (
            setor,
            frota,
            motorista,
            c1,
            c2,
            c3,
            hora,
            id
        ))

        conn.commit()
        conn.close()

        flash("✅ Equipe atualizada!")

    except Exception as e:

        print("ERRO SALVAR:", e)

        flash("Erro ao salvar")

    return redirect(url_for("equipes"))


# ================= EXCLUIR =================
@app.route("/excluir/<int:id>", methods=["POST"])
def excluir(id):

    if not verificar_login():

        return redirect(url_for("login"))

    try:

        conn = conectar()
        cursor = conn.cursor()

        equipe = cursor.execute("""
            SELECT * FROM equipes
            WHERE id=?
        """, (id,)).fetchone()

        if equipe:

            pessoas = [
                ("MOTORISTA", equipe["Motorista"]),
                ("COLETOR", equipe["C1"]),
                ("COLETOR", equipe["C2"]),
                ("COLETOR", equipe["C3"]),
            ]

            for tipo, codigo in pessoas:

                adicionar_disponivel(
                    cursor,
                    codigo,
                    tipo
                )

        cursor.execute("""
            DELETE FROM equipes
            WHERE id=?
        """, (id,))

        conn.commit()
        conn.close()

        flash("✅ Equipe excluída!")

    except Exception as e:

        print("ERRO EXCLUIR:", e)

        flash("Erro ao excluir")

    return redirect(url_for("equipes"))


# ================= CONVERTER TODOS =================
@app.route("/converter_todos", methods=["POST"])
def converter_todos():

    if not verificar_login():

        return redirect(url_for("login"))

    try:

        modo = request.form.get("modo")

        if not modo:

            flash("⚠️ Selecione PD ou ID")

            return redirect(url_for("equipes"))

        mapa = {
            "PD29":"ID01","PD20":"ID02","PD01":"ID03","PD44":"ID05",
            "PD33":"ID06","PD13":"ID07","PD14":"ID08","PD19":"ID09",
            "PD22":"ID10","PD21":"ID11","PD24":"ID12","PD04":"ID13",
            "PD23":"ID14","PD03":"ID15","PD27":"ID16","PD02":"ID17",
            "PD06":"ID18","PD31":"ID20","PD28":"ID21","PD32":"ID22",
            "PD07":"ID23","PD39":"ID24","PD43":"ID25","PD34":"ID26",
            "PD17":"ID27","PD36":"ID28","PD10":"ID29","PD37":"ID30",
            "PD05":"ID31","PD42":"ID32","PD35":"ID34","PD09":"ID37",
            "PD38":"ID38","PD18":"ID39","PD45":"ID40","PD25":"ID41",
            "PD30":"ID42","PD08":"ID43","PD41":"ID44","PD40":"ID45",
            "PD12":"ID47",
            "DD01":"DD01","DD02":"DD02",
            "VP01":"VI01","VP02":"VI02","VP03":"VI03",
            "VP04":"VI04","VP05":"VI05","VP06":"VI06",
            "4X4 EXT":"4X4 EXT","4X4 SUL":"4X4 SUL"
        }

        mapa_inverso = {
            v: k for k, v in mapa.items()
        }

        conn = conectar()
        cursor = conn.cursor()

        equipes = cursor.execute("""
            SELECT id, Setor_ID
            FROM equipes
        """).fetchall()

        alterados = 0

        for e in equipes:

            atual = (
                e["Setor_ID"] or ""
            ).strip().upper()

            novo = (
                mapa.get(atual)
                if modo == "ID"
                else mapa_inverso.get(atual)
            )

            if novo and atual != novo:

                cursor.execute("""
                    UPDATE equipes
                    SET Setor_ID=?
                    WHERE id=?
                """, (
                    novo,
                    e["id"]
                ))

                alterados += 1

        conn.commit()
        conn.close()

        flash(
            f"✅ {alterados} setores convertidos para {modo}"
        )

    except Exception as e:

        print("ERRO CONVERTER:", e)

        flash("Erro na conversão")

    return redirect(url_for("equipes"))


# ================= ATUALIZAR STATUS =================
@app.route("/atualizar_status", methods=["POST"])
def atualizar_status():

    if not verificar_login():

        return jsonify(ok=False)

    data = request.get_json()

    conn = conectar()

    conn.execute("""
        UPDATE disponiveis
        SET status=?
        WHERE codigo=?
    """, (
        data["status"],
        data["codigo"]
    ))

    conn.commit()
    conn.close()

    return jsonify(ok=True)


# ================= EXCLUIR DISPONIVEL =================
@app.route("/excluir_disponivel", methods=["POST"])
def excluir_disponivel():

    if not verificar_login():

        return jsonify(ok=False)

    data = request.get_json()

    conn = conectar()

    conn.execute("""
        DELETE FROM disponiveis
        WHERE codigo=?
    """, (
        data["codigo"],
    ))

    conn.commit()
    conn.close()

    return jsonify(ok=True)


# ================= CADASTRAR STATUS =================
@app.route("/cadastrar_status", methods=["POST"])
def cadastrar_status():

    if not verificar_login():

        return redirect(url_for("login"))

    try:

        codigo = normalizar(
            request.form.get("codigo")
        )

        status = request.form.get("status")
        tipo = request.form.get("tipo")

        if not codigo or not status or not tipo:

            flash("Preencha todos os campos")

            return redirect(url_for("disponiveis"))

        conn = conectar()
        cursor = conn.cursor()

        existe = cursor.execute("""
            SELECT 1 FROM disponiveis
            WHERE codigo=?
        """, (codigo,)).fetchone()

        if existe:

            flash("Código já cadastrado!")

            conn.close()

            return redirect(url_for("disponiveis"))

        cursor.execute("""
            INSERT INTO disponiveis (
                codigo,
                tipo,
                status
            )
            VALUES (?, ?, ?)
        """, (
            codigo,
            tipo,
            status
        ))

        conn.commit()
        conn.close()

        flash("✅ Status cadastrado!")

    except Exception as e:

        print("ERRO STATUS:", e)

        flash("Erro ao cadastrar")

    return redirect(url_for("disponiveis"))


# ================= HEALTH =================
@app.route("/health")
def health():

    return "ONLINE"


# ================= ABRIR CHROME =================
def abrir_navegador():

    try:

        chrome_path = (
            "C:/Program Files/Google/Chrome/Application/chrome.exe %s"
        )

        webbrowser.get(chrome_path).open(
            "http://127.0.0.1:5000"
        )

    except Exception as e:

        print("ERRO CHROME:", e)


# ================= START =================
if __name__ == "__main__":

    port = int(
        os.environ.get("PORT", 5000)
    )

    # ABRIR SOMENTE LOCAL
    if os.environ.get("RENDER") is None:

        Timer(1, abrir_navegador).start()

    app.run(
        host="0.0.0.0",
        port=port
    )