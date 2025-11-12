from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterable

from flask import Flask, flash, redirect, render_template, request, url_for

app = Flask(__name__)
app.secret_key = "dev-secret-change-me"

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
EXPENSES_FILE = DATA_DIR / "expenses.csv"
CATEGORIES_FILE = DATA_DIR / "categories.csv"


def ensure_storage() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not CATEGORIES_FILE.exists():
        with CATEGORIES_FILE.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "nome"])
            writer.writerow(["1", "Outros"])
    else:
        upgrade_categories_file()

    if not EXPENSES_FILE.exists():
        with EXPENSES_FILE.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "data", "descricao", "valor", "categoria_id", "anotacao"])
    else:
        upgrade_expenses_file()


def upgrade_categories_file() -> None:
    with CATEGORIES_FILE.open("r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = [row for row in reader if any(cell.strip() for cell in row)]

    if not rows:
        with CATEGORIES_FILE.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "nome"])
            writer.writerow(["1", "Outros"])
        return

    header = [cell.strip() for cell in rows[0]]
    if header and header[0] == "id":
        return

    names: list[str] = []
    for row in rows[1:]:
        if not row:
            continue
        name = row[0].strip()
        if name:
            names.append(name)

    seen: set[str] = set()
    normalized_names: list[str] = []
    for name in names:
        if name not in seen:
            seen.add(name)
            normalized_names.append(name)

    if "Outros" not in seen:
        normalized_names.insert(0, "Outros")

    with CATEGORIES_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "nome"])
        for idx, name in enumerate(normalized_names, start=1):
            writer.writerow([str(idx), name])


def load_categories_for_upgrade() -> list[dict[str, str]]:
    if not CATEGORIES_FILE.exists():
        return []
    with CATEGORIES_FILE.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [
            {"id": row.get("id", "").strip(), "nome": row.get("nome", "").strip()}
            for row in reader
            if row.get("id") and row.get("nome")
        ]


def append_categories(entries: Iterable[tuple[str, str]]) -> None:
    with CATEGORIES_FILE.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for cat_id, name in entries:
            writer.writerow([cat_id, name])


def upgrade_expenses_file() -> None:
    with EXPENSES_FILE.open("r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = [row for row in reader if any(cell.strip() for cell in row)]

    if not rows:
        with EXPENSES_FILE.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "data", "descricao", "valor", "categoria_id", "anotacao"])
        return

    header = [cell.strip() for cell in rows[0]]
    if header and header[0] == "id":
        return

    old_rows: list[dict[str, str]] = []
    for row in rows[1:]:
        if len(row) < 5:
            continue
        old_rows.append(
            {
                "data": row[0].strip(),
                "descricao": row[1].strip(),
                "valor": row[2].strip(),
                "categoria": row[3].strip() or "Outros",
                "anotacao": row[4].strip(),
            }
        )

    categories = load_categories_for_upgrade()
    name_to_id = {cat["nome"]: cat["id"] for cat in categories}
    next_category_id = max((int(cat["id"]) for cat in categories), default=0) + 1
    new_categories: list[tuple[str, str]] = []

    new_rows: list[list[str]] = []
    for idx, row in enumerate(old_rows, start=1):
        categoria_nome = row["categoria"] or "Outros"
        categoria_id = name_to_id.get(categoria_nome)
        if not categoria_id:
            categoria_id = str(next_category_id)
            next_category_id += 1
            name_to_id[categoria_nome] = categoria_id
            new_categories.append((categoria_id, categoria_nome))
        new_rows.append(
            [
                str(idx),
                row["data"],
                row["descricao"],
                row["valor"],
                categoria_id,
                row["anotacao"],
            ]
        )

    with EXPENSES_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "data", "descricao", "valor", "categoria_id", "anotacao"])
        writer.writerows(new_rows)

    if new_categories:
        append_categories(new_categories)


def load_categories_raw() -> list[dict[str, str]]:
    ensure_storage()
    categories: list[dict[str, str]] = []
    with CATEGORIES_FILE.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cat_id = row.get("id", "").strip()
            nome = row.get("nome", "").strip()
            if cat_id and nome:
                categories.append({"id": cat_id, "nome": nome})
    return categories


def save_categories(categories: list[dict[str, str]]) -> None:
    ensure_storage()
    with CATEGORIES_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "nome"])
        for category in categories:
            writer.writerow([category["id"], category["nome"]])


def read_categories() -> list[dict[str, str]]:
    categories = load_categories_raw()
    return sorted(categories, key=lambda c: c["nome"].lower())


def add_category(nome: str) -> None:
    nome = nome.strip()
    if not nome:
        return
    categories = read_categories()
    existing = {c["nome"].lower() for c in categories}
    if nome.lower() in existing:
        return
    next_id = str(max((int(c["id"]) for c in categories), default=0) + 1)
    with CATEGORIES_FILE.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([next_id, nome])


def load_expenses_raw() -> list[dict[str, str]]:
    ensure_storage()
    expenses: list[dict[str, str]] = []
    with EXPENSES_FILE.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            exp_id = row.get("id", "").strip()
            if not exp_id:
                continue
            expenses.append(
                {
                    "id": exp_id,
                    "data": row.get("data", "").strip(),
                    "descricao": row.get("descricao", "").strip(),
                    "valor": (row.get("valor") or "").strip(),
                    "categoria_id": row.get("categoria_id", "").strip(),
                    "anotacao": row.get("anotacao", "").strip(),
                }
            )
    return expenses


def save_expenses(expenses: list[dict[str, str]]) -> None:
    ensure_storage()
    with EXPENSES_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "data", "descricao", "valor", "categoria_id", "anotacao"])
        for expense in expenses:
            writer.writerow(
                [
                    expense["id"],
                    expense.get("data", ""),
                    expense.get("descricao", ""),
                    expense.get("valor", ""),
                    expense.get("categoria_id", ""),
                    expense.get("anotacao", ""),
                ]
            )


def read_expenses() -> list[dict[str, str]]:
    expenses_raw = load_expenses_raw()
    categories = read_categories()
    categories_by_id = {cat["id"]: cat["nome"] for cat in categories}
    processed: list[dict[str, str]] = []

    for expense in expenses_raw:
        valor_raw = (expense.get("valor") or "0").replace(",", ".")
        try:
            valor_float = float(valor_raw)
        except ValueError:
            valor_float = 0.0
        categoria_id = expense.get("categoria_id", "")
        categoria_nome = categories_by_id.get(categoria_id) or "Categoria removida"

        processed.append(
            {
                "id": expense["id"],
                "data": expense.get("data", ""),
                "descricao": expense.get("descricao", ""),
                "valor": f"{valor_float:.2f}",
                "valor_float": valor_float,
                "categoria_id": categoria_id,
                "categoria_nome": categoria_nome,
                "categoria": categoria_nome,
                "anotacao": expense.get("anotacao", ""),
            }
        )

    return sorted(processed, key=lambda item: int(item["id"]), reverse=True)


def get_next_id(file_path: Path, field: str = "id") -> str:
    max_id = 0
    if not file_path.exists():
        return "1"
    with file_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                current = int(row.get(field, "0"))
            except (ValueError, TypeError):
                continue
            if current > max_id:
                max_id = current
    return str(max_id + 1)


def resolve_category_id(identifier: str) -> str | None:
    identifier = identifier.strip()
    if not identifier:
        return None
    categories = read_categories()
    lowered = identifier.lower()
    for category in categories:
        if identifier == category["id"] or lowered == category["nome"].lower():
            return category["id"]
    return None


def update_category(category_id: str, novo_nome: str) -> bool:
    novo_nome = novo_nome.strip()
    if not novo_nome:
        return False

    categories = load_categories_raw()
    target = None
    for category in categories:
        if category["id"] == category_id:
            target = category
            break
    if not target:
        return False

    if any(
        novo_nome.lower() == category["nome"].lower() and category["id"] != category_id
        for category in categories
    ):
        return False

    target["nome"] = novo_nome
    save_categories(categories)
    return True


def reassign_expenses_category(old_id: str, new_id: str) -> None:
    expenses = load_expenses_raw()
    changed = False
    for expense in expenses:
        if expense.get("categoria_id") == old_id:
            expense["categoria_id"] = new_id
            changed = True
    if changed:
        save_expenses(expenses)


def delete_category(category_id: str) -> bool:
    if category_id == "1":  # Não remover categoria padrão
        return False
    categories = load_categories_raw()
    filtered = [category for category in categories if category["id"] != category_id]
    if len(filtered) == len(categories):
        return False
    save_categories(filtered)
    reassign_expenses_category(category_id, "1")
    return True


def update_expense(
    expense_id: str,
    data: str,
    descricao: str,
    valor: float,
    categoria_id: str,
    anotacao: str,
) -> bool:
    expenses = load_expenses_raw()
    updated = False
    for expense in expenses:
        if expense["id"] == expense_id:
            expense["data"] = data
            expense["descricao"] = descricao
            expense["valor"] = f"{valor:.2f}"
            expense["categoria_id"] = categoria_id
            expense["anotacao"] = anotacao
            updated = True
            break
    if not updated:
        return False
    save_expenses(expenses)
    return True


def delete_expense(expense_id: str) -> bool:
    expenses = load_expenses_raw()
    filtered = [expense for expense in expenses if expense["id"] != expense_id]
    if len(filtered) == len(expenses):
        return False
    save_expenses(filtered)
    return True


def write_expense(
    data: str,
    descricao: str,
    valor: float,
    categoria_id: str,
    anotacao: str,
) -> None:
    ensure_storage()
    expense_id = get_next_id(EXPENSES_FILE)
    with EXPENSES_FILE.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([expense_id, data, descricao, f"{valor:.2f}", categoria_id, anotacao])


@app.route("/")
def index():
    expenses = read_expenses()
    category_records = read_categories()
    return render_template(
        "index.html",
        expenses=expenses,
        category_records=category_records,
    )


@app.route("/adicionar", methods=["POST"])
def adicionar():
    data_str = request.form.get("data", "").strip()
    descricao = request.form.get("descricao", "").strip()
    valor_str = request.form.get("valor", "").strip()
    categoria_input = (
        request.form.get("categoria_id")
        or request.form.get("categoria")
        or ""
    ).strip()
    anotacao = request.form.get("anotacao", "").strip()

    if not data_str or not descricao or not valor_str or not categoria_input:
        flash("Preencha data, descrição, valor e categoria.", "error")
        return redirect(url_for("index"))

    try:
        data_obj = datetime.strptime(data_str, "%Y-%m-%d")
    except ValueError:
        flash("Data inválida. Use o formato AAAA-MM-DD.", "error")
        return redirect(url_for("index"))

    try:
        valor = float(valor_str.replace(",", "."))
    except ValueError:
        flash("Valor inválido.", "error")
        return redirect(url_for("index"))

    categoria_id = resolve_category_id(categoria_input)
    if not categoria_id:
        flash("Categoria informada não foi encontrada.", "error")
        return redirect(url_for("index"))

    write_expense(data_obj.strftime("%Y-%m-%d"), descricao, valor, categoria_id, anotacao)
    flash("Lançamento registrado com sucesso!", "success")
    return redirect(url_for("index"))


@app.route("/categorias", methods=["GET", "POST"])
def categorias():
    if request.method == "POST":
        nome = request.form.get("nome", "")
        if not nome.strip():
            flash("Informe um nome de categoria.", "error")
        else:
            add_category(nome)
            flash("Categoria criada!", "success")
        return redirect(url_for("categorias"))

    category_records = read_categories()
    return render_template(
        "categorias.html",
        category_records=category_records,
    )


@app.post("/categorias/<category_id>/renomear")
def renomear_categoria(category_id: str):
    novo_nome = request.form.get("nome", "")
    if update_category(category_id, novo_nome):
        flash("Categoria atualizada com sucesso!", "success")
    else:
        flash("Não foi possível atualizar a categoria.", "error")
    return redirect(url_for("categorias"))


@app.post("/categorias/<category_id>/excluir")
def excluir_categoria(category_id: str):
    if delete_category(category_id):
        flash("Categoria removida. Lançamentos associados foram movidos para 'Outros'.", "success")
    else:
        flash("Não foi possível remover a categoria.", "error")
    return redirect(url_for("categorias"))


@app.route("/admin")
def admin():
    expenses = read_expenses()
    total_geral = 0.0
    por_categoria: defaultdict[str, float] = defaultdict(float)

    for item in expenses:
        valor = item.get("valor_float", 0.0)
        total_geral += valor
        por_categoria[item["categoria_nome"]] += valor

    labels = list(por_categoria.keys())
    values = [round(v, 2) for v in por_categoria.values()]

    return render_template(
        "admin.html",
        total_geral=round(total_geral, 2),
        por_categoria=dict(sorted(por_categoria.items(), key=lambda x: x[0])),
        chart_labels=json.dumps(labels, ensure_ascii=False),
        chart_values=json.dumps(values),
    )


@app.post("/lancamentos/<expense_id>/editar")
def editar_lancamento(expense_id: str):
    data_str = request.form.get("data", "").strip()
    descricao = request.form.get("descricao", "").strip()
    valor_str = request.form.get("valor", "").strip()
    categoria_input = (
        request.form.get("categoria_id")
        or request.form.get("categoria")
        or ""
    ).strip()
    anotacao = request.form.get("anotacao", "").strip()

    if not data_str or not descricao or not valor_str or not categoria_input:
        flash("Preencha data, descrição, valor e categoria.", "error")
        return redirect(url_for("index"))

    try:
        data_obj = datetime.strptime(data_str, "%Y-%m-%d")
    except ValueError:
        flash("Data inválida. Use o formato AAAA-MM-DD.", "error")
        return redirect(url_for("index"))

    try:
        valor = float(valor_str.replace(",", "."))
    except ValueError:
        flash("Valor inválido.", "error")
        return redirect(url_for("index"))

    categoria_id = resolve_category_id(categoria_input)
    if not categoria_id:
        flash("Categoria informada não foi encontrada.", "error")
        return redirect(url_for("index"))

    if update_expense(
        expense_id,
        data_obj.strftime("%Y-%m-%d"),
        descricao,
        valor,
        categoria_id,
        anotacao,
    ):
        flash("Lançamento atualizado com sucesso!", "success")
    else:
        flash("Não foi possível atualizar o lançamento.", "error")
    return redirect(url_for("index"))


@app.post("/lancamentos/<expense_id>/excluir")
def excluir_lancamento(expense_id: str):
    if delete_expense(expense_id):
        flash("Lançamento removido.", "success")
    else:
        flash("Não foi possível remover o lançamento.", "error")
    return redirect(url_for("index"))


if __name__ == "__main__":
    ensure_storage()
    app.run(debug=True)

